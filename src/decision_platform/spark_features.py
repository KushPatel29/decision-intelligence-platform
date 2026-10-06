"""PySpark implementation of `sql/customer_features.sql`, column for column.

Parity is enforced by `scripts/benchmark_spark.py`, which runs this kernel over the
full silver layer and compares every feature with the DuckDB result (tolerance 1e-7).
"""

COUNT_DEFAULTS = [
    "trips_7d",
    "trips_30d",
    "trips_90d",
    "trips_previous90d",
    "spend_30d",
    "spend_90d",
    "spend_365d",
    "avg_toll",
    "avg_toll_peak",
    "avg_toll_offpeak",
    "avg_toll_weekend",
    "avg_distance_km",
    "peak_share",
    "weekend_share",
    "night_share_30d",
    "zones_visited_30d",
    "active_days_30d",
    "max_daily_trips_30d",
    "discount_90d",
    "digital_events_30d",
    "app_logins_30d",
    "offer_views_30d",
    "email_opens_30d",
    "sessions_30d",
    "offer_views_90d",
    "offer_clicks_90d",
    "offer_enrolls_90d",
    "email_opens_90d",
    "email_clicks_90d",
    "pricing_views_90d",
    "loyalty_views_90d",
    "app_logins_90d",
    "logins_90d",
    "points_earned_to_date",
]


def build_features(spark, raw_path, as_of="2025-10-01", table_reader=None):
    from pyspark.sql import functions as F

    def read(name):
        return (
            table_reader(name)
            if table_reader
            else spark.read.parquet(str(raw_path) + "/" + name + ".parquet")
        )

    cutoff = F.to_timestamp(F.lit(as_of))

    def recent(days):
        return F.col("timestamp") >= cutoff - F.expr(f"INTERVAL {days} DAYS")

    trips = read("fact_trip").filter(F.col("timestamp") < cutoff)
    expressions = [F.sum(F.when(recent(d), 1).otherwise(0)).alias(f"trips_{d}d") for d in (7, 30, 90)]
    expressions.append(F.sum(F.when(recent(180) & ~recent(90), 1).otherwise(0)).alias("trips_previous90d"))
    for days in (30, 90, 365):
        expressions.append(
            F.sum(F.when(recent(days), F.col("final_charge")).otherwise(0)).alias(f"spend_{days}d")
        )
    expressions += [
        F.avg(F.when(recent(90), F.col("toll"))).alias("avg_toll"),
        F.avg(F.when(recent(90) & (F.col("period") == "Peak"), F.col("toll"))).alias("avg_toll_peak"),
        F.avg(F.when(recent(90) & (F.col("period") == "Off-peak"), F.col("toll"))).alias("avg_toll_offpeak"),
        F.avg(F.when(recent(90) & (F.col("period") == "Weekend"), F.col("toll"))).alias("avg_toll_weekend"),
        F.avg(F.when(recent(90), F.col("distance_km"))).alias("avg_distance_km"),
        F.avg(F.when(recent(90), (F.col("period") == "Peak").cast("double"))).alias("peak_share"),
        F.avg(F.when(recent(90), (F.col("period") == "Weekend").cast("double"))).alias("weekend_share"),
        F.avg(F.when(recent(30), (F.hour("timestamp") < 6).cast("double"))).alias("night_share_30d"),
        F.countDistinct(F.when(recent(30), F.col("zone_id"))).alias("zones_visited_30d"),
        F.countDistinct(F.when(recent(30), F.to_date("timestamp"))).alias("active_days_30d"),
        F.sum(F.when(recent(90), F.col("discount")).otherwise(0)).alias("discount_90d"),
        F.datediff(cutoff, F.max("timestamp")).alias("recency_days"),
        F.max("timestamp").alias("feature_max_timestamp"),
    ]
    travel = trips.groupBy("customer_id").agg(*expressions)
    busiest = (
        trips.filter(recent(30))
        .groupBy("customer_id", F.to_date("timestamp").alias("day"))
        .count()
        .groupBy("customer_id")
        .agg(F.max("count").alias("max_daily_trips_30d"))
    )

    events = read("fact_digital_event").filter((F.col("timestamp") < cutoff) & recent(90))

    def kind(name, window=None):
        condition = F.col("event_type") == name
        if window:
            condition = condition & recent(window)
        return F.sum(F.when(condition, 1).otherwise(0))

    digital = events.groupBy("customer_id").agg(
        F.sum(F.when(recent(30), 1).otherwise(0)).alias("digital_events_30d"),
        kind("app_login", 30).alias("app_logins_30d"),
        kind("offer_view", 30).alias("offer_views_30d"),
        kind("email_open", 30).alias("email_opens_30d"),
        F.countDistinct(F.when(recent(30), F.to_date("timestamp"))).alias("sessions_30d"),
        kind("offer_view").alias("offer_views_90d"),
        kind("offer_click").alias("offer_clicks_90d"),
        kind("offer_enroll").alias("offer_enrolls_90d"),
        kind("email_open").alias("email_opens_90d"),
        kind("email_click").alias("email_clicks_90d"),
        kind("pricing_page_view").alias("pricing_views_90d"),
        kind("loyalty_page_view").alias("loyalty_views_90d"),
        kind("app_login").alias("app_logins_90d"),
        F.sum(F.when(F.col("event_type").isin("app_login", "web_login"), 1).otherwise(0)).alias("logins_90d"),
    )
    last_login = (
        read("fact_digital_event")
        .filter((F.col("timestamp") < cutoff) & F.col("event_type").isin("app_login", "web_login"))
        .groupBy("customer_id")
        .agg(F.datediff(cutoff, F.max("timestamp")).alias("days_since_last_login"))
    )
    loyalty = (
        read("fact_loyalty_points")
        .filter(F.col("timestamp") < cutoff)
        .groupBy("customer_id")
        .agg(F.sum("points_earned").alias("points_earned_to_date"))
    )
    customer = (
        read("dim_customer")
        .filter(F.col("created_at") < cutoff)
        .withColumn("tenure_days", F.datediff(cutoff, "created_at"))
        .withColumn("business_flag", (F.col("customer_type") == "Business").cast("int"))
        .withColumn("autopay", F.col("autopay").cast("int"))
        .withColumn("transponder_flag", F.col("transponder_flag").cast("int"))
        .withColumn("heavy_vehicle", (F.col("vehicle_class") == "Heavy").cast("int"))
    )
    frame = (
        customer.join(travel, "customer_id", "left")
        .join(busiest, "customer_id", "left")
        .join(digital, "customer_id", "left")
        .join(last_login, "customer_id", "left")
        .join(loyalty, "customer_id", "left")
        .fillna(730, subset=["recency_days"])
        .fillna(0, subset=COUNT_DEFAULTS)
    )
    return (
        frame.withColumn("as_of", cutoff)
        .withColumn(
            "days_since_last_login",
            F.least(F.coalesce(F.col("days_since_last_login"), F.lit(365)), F.lit(365)),
        )
        .withColumn(
            "offer_click_rate_90d", (F.col("offer_clicks_90d") + 0.5) / (F.col("offer_views_90d") + 3.0)
        )
        .withColumn("enroll_rate_90d", (F.col("offer_enrolls_90d") + 0.5) / (F.col("offer_clicks_90d") + 2.0))
        .withColumn(
            "email_click_rate_90d", (F.col("email_clicks_90d") + 0.5) / (F.col("email_opens_90d") + 3.0)
        )
        .withColumn(
            "app_share_90d",
            F.when(F.col("logins_90d") == 0, F.lit(0.0)).otherwise(
                F.col("app_logins_90d") / F.col("logins_90d")
            ),
        )
        .withColumn("frequency_trend", (F.col("trips_90d") + 1) / (F.col("trips_previous90d") + 1))
        .withColumn("digital_engagement_score", F.log1p("digital_events_30d"))
    )
