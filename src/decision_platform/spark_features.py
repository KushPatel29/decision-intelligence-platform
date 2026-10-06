"""Complete PySpark implementation of the DuckDB feature allowlist."""


def build_features(spark, raw_path, as_of="2025-10-01", table_reader=None):
    from pyspark.sql import functions as F

    def read(name):
        return (
            table_reader(name)
            if table_reader
            else spark.read.parquet(str(raw_path) + "/" + name + ".parquet")
        )

    cutoff = F.to_timestamp(F.lit(as_of))
    trip = read("fact_trip").filter(F.col("timestamp") < cutoff)

    def recent(days):
        return F.col("timestamp") >= cutoff - F.expr(f"INTERVAL {days} DAYS")

    expressions = []
    for days in [7, 30, 90]:
        expressions.append(F.sum(F.when(recent(days), 1).otherwise(0)).alias(f"trips_{days}d"))
    expressions.append(F.sum(F.when(recent(180) & ~recent(90), 1).otherwise(0)).alias("trips_previous90d"))
    for days in [30, 90, 365]:
        expressions.append(
            F.sum(F.when(recent(days), F.col("final_charge")).otherwise(0)).alias(f"spend_{days}d")
        )
    for field, alias in [("toll", "avg_toll"), ("distance_km", "avg_distance_km")]:
        expressions.append(F.avg(F.when(recent(90), F.col(field))).alias(alias))
    for period, alias in [("Peak", "peak_share"), ("Weekend", "weekend_share")]:
        expressions.append(
            F.avg(F.when(recent(90), F.col("period").eqNullSafe(period).cast("double"))).alias(alias)
        )
    expressions.extend(
        [
            F.sum(F.when(recent(90), F.col("discount")).otherwise(0)).alias("discount_90d"),
            F.datediff(cutoff, F.max("timestamp")).alias("recency_days"),
            F.max("timestamp").alias("feature_max_timestamp"),
        ]
    )
    travel = trip.groupBy("customer_id").agg(*expressions)
    events = read("fact_digital_event").filter((F.col("timestamp") < cutoff) & recent(30))
    digital = events.groupBy("customer_id").agg(
        F.count("*").alias("digital_events_30d"),
        *[
            F.sum(F.when(F.col("event_type") == kind, 1).otherwise(0)).alias(alias)
            for kind, alias in [
                ("app_login", "app_logins_30d"),
                ("offer_view", "offer_views_30d"),
                ("email_open", "email_opens_30d"),
            ]
        ],
    )
    loyalty = (
        read("fact_loyalty_points")
        .filter(F.col("timestamp") < cutoff)
        .groupBy("customer_id")
        .agg(F.sum("points_earned").alias("points_earned_to_date"))
    )
    customer = read("dim_customer").filter(F.col("created_at") < cutoff)
    customer = (
        customer.withColumn("tenure_days", F.datediff(cutoff, "created_at"))
        .withColumn("business_flag", (F.col("customer_type") == "Business").cast("int"))
        .withColumn("autopay", F.col("autopay").cast("int"))
        .withColumn("transponder_flag", F.col("transponder_flag").cast("int"))
    )
    frame = (
        customer.join(travel, "customer_id", "left")
        .join(digital, "customer_id", "left")
        .join(loyalty, "customer_id", "left")
    )
    frame = frame.fillna(730, subset=["recency_days"]).fillna(
        0,
        subset=[
            e
            for e in [
                "trips_7d",
                "trips_30d",
                "trips_90d",
                "trips_previous90d",
                "spend_30d",
                "spend_90d",
                "spend_365d",
                "avg_toll",
                "avg_distance_km",
                "peak_share",
                "weekend_share",
                "discount_90d",
                "digital_events_30d",
                "app_logins_30d",
                "offer_views_30d",
                "email_opens_30d",
                "points_earned_to_date",
            ]
        ],
    )
    return (
        frame.withColumn("as_of", cutoff)
        .withColumn("frequency_trend", (F.col("trips_90d") + 1) / (F.col("trips_previous90d") + 1))
        .withColumn("digital_engagement_score", F.log1p("digital_events_30d"))
    )
