# Databricks notebook source
# Complete synthetic bronze/silver/gold feature pipeline. No hidden simulator inputs.
from pyspark.sql import functions as F

dbutils.widgets.text("catalog", "workspace")
dbutils.widgets.text("project_schema", "corridor_v2")
dbutils.widgets.text("raw_path", "")
dbutils.widgets.text("gold_path", "")
dbutils.widgets.text("as_of", "2025-10-01")
catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("project_schema")
raw_path = dbutils.widgets.get("raw_path")
as_of = dbutils.widgets.get("as_of")
gold_path = dbutils.widgets.get("gold_path")
if not raw_path:
    raise ValueError("Provide the Unity Catalog volume path with delivered bronze Parquet files")
if not gold_path:
    raise ValueError(
        "Provide the delivered scored gold mart volume path; ML scores are inputs, not recomputed in this notebook"
    )
for name in [catalog, schema]:
    if not name.replace("_", "").isalnum():
        raise ValueError("Invalid identifier")
prefix = f"{catalog}.{schema}"
spark.conf.set("spark.sql.session.timeZone", "America/Toronto")
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {prefix}")
# COMMAND ----------
domains = [
    "dim_customer",
    "dim_account",
    "dim_vehicle",
    "dim_zone",
    "dim_offer",
    "fact_trip",
    "fact_digital_event",
    "fact_loyalty_points",
    "fact_pricing_scenario",
    "external_context",
    "dim_transponder",
    "customer_preferences",
    "customer_status_history",
    "dim_entry_point",
    "dim_exit_point",
    "dim_time",
    "dim_rate",
    "fact_effective_price",
    "dim_reward",
    "fact_loyalty_tier",
]
domains += [
    "fact_campaign_result",
    "fact_offer_exposure",
    "fact_offer_enrollment",
    "fact_offer_redemption",
    "fact_loyalty_redemption",
    "fact_loyalty_award",
]
for name in domains:
    raw = spark.read.parquet(raw_path.rstrip("/") + "/" + name + ".parquet")
    raw.withColumn("ingested_at", F.current_timestamp()).write.format("delta").mode(
        "errorifexists"
    ).saveAsTable(f"{prefix}.bronze_{name}")
trip = spark.table(f"{prefix}.bronze_fact_trip")
customer = spark.table(f"{prefix}.bronze_dim_customer")
invalid = trip.filter(
    F.col("customer_id").isNull()
    | F.col("timestamp").isNull()
    | (F.col("final_charge") < 0)
    | (F.abs(F.col("toll") - F.col("discount") - F.col("final_charge")) > 1e-6)
)
if invalid.limit(1).count():
    raise ValueError("Trip contract failed")
if trip.count() != trip.select("trip_id").distinct().count():
    raise ValueError("Duplicate trip keys")
if trip.join(customer.select("customer_id"), "customer_id", "left_anti").limit(1).count():
    raise ValueError("Customer foreign key failed")
if (
    trip.join(spark.table(f"{prefix}.bronze_dim_zone").select("zone_id"), "zone_id", "left_anti")
    .limit(1)
    .count()
):
    raise ValueError("Zone foreign key failed")
for name in domains:
    spark.table(f"{prefix}.bronze_{name}").drop("ingested_at").write.format("delta").mode(
        "errorifexists"
    ).saveAsTable(f"{prefix}.silver_{name}")
# COMMAND ----------
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


# COMMAND ----------
gold = build_features(
    spark, raw_path, as_of, table_reader=lambda name: spark.table(f"{prefix}.silver_{name}")
)
if gold.filter(F.col("feature_max_timestamp") >= F.col("as_of")).limit(1).count():
    raise ValueError("Point-in-time leakage")
gold.write.format("delta").mode("errorifexists").saveAsTable(f"{prefix}.gold_customer_features")
history = spark.table(f"{prefix}.silver_fact_trip").filter(F.col("timestamp") < F.to_timestamp(F.lit(as_of)))
zone_day = history.groupBy(F.to_date("timestamp").alias("date"), "zone_id", "period").agg(
    F.count("*").alias("trips"), F.sum("final_charge").alias("revenue")
)
zone_day.write.format("delta").mode("errorifexists").saveAsTable(f"{prefix}.gold_zone_day")

# Reproducible scored marts are generated by the local/cloud model stage, then
# published with explicit grains. This is an import, not hosted model training.
mart_grains = {
    "customer_360": ["customer_id"],
    "customer_month": ["customer_id", "as_of"],
    "customer_offer": ["customer_id", "offer_id"],
    "customer_activity_month": ["customer_id", "month"],
    "campaign_performance": ["arm"],
    "pricing_elasticity": ["zone_id", "period"],
    "loyalty_performance": ["customer_id"],
    "zone_hour": ["date", "zone_id", "period", "direction", "hour"],
}
for name, grain in mart_grains.items():
    mart = spark.read.parquet(gold_path.rstrip("/") + "/" + name + ".parquet")
    if mart.count() != mart.select(*grain).distinct().count():
        raise ValueError("Duplicate grain in " + name)
    if "feature_max_timestamp" in mart.columns:
        if mart.filter(F.col("feature_max_timestamp") >= F.col("as_of")).limit(1).count():
            raise ValueError("Scored mart cutoff leakage")
    if "customer_id" in mart.columns:
        if mart.join(customer.select("customer_id"), "customer_id", "left_anti").limit(1).count():
            raise ValueError("Mart customer FK failed")
    mart.write.format("delta").mode("errorifexists").saveAsTable(f"{prefix}.gold_{name}")

# Silver campaign dates precede decision cutoff. Never publish simulator oracle.
events = spark.table(f"{prefix}.silver_fact_digital_event").filter(
    F.col("timestamp") < F.to_timestamp(F.lit(as_of))
)
engagement = events.groupBy("customer_id", F.to_date("timestamp").alias("date"), "channel").agg(
    F.count("*").alias("events"), F.countDistinct("event_type").alias("event_types")
)
engagement.write.format("delta").mode("errorifexists").saveAsTable(f"{prefix}.gold_digital_customer_day")
display(
    gold.select("customer_id", "as_of", "trips_30d", "spend_30d", "digital_events_30d", "frequency_trend")
)
print(
    {
        "trip_rows": trip.count(),
        "customer_rows": gold.count(),
        "features": "complete local reference allowlist",
        "mart_grains": mart_grains,
        "tables": prefix,
        "scored_marts": "Imported from upstream scoring stage; not hosted training",
    }
)
