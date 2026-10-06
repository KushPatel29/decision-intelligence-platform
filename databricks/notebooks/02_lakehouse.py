# Databricks notebook source
# MAGIC %md
# MAGIC # 2 · Lakehouse: Delta medallion and PySpark features
# MAGIC
# MAGIC Lands the run's bronze, silver and gold layers as Unity Catalog Delta tables, puts the silver trip
# MAGIC contract into the table itself (CHECK constraints, an informational primary key), and recomputes all
# MAGIC 39 customer features in **PySpark** from the silver Delta tables. The PySpark features must equal the
# MAGIC DuckDB features the models were trained on to 1e-7, or the task fails: two engines, one feature contract.

# COMMAND ----------

import json
import os
import sys

import numpy as np
import pandas as pd

dbutils.widgets.text("code_root", "")
dbutils.widgets.text("catalog", "workspace")
dbutils.widgets.text("schema", "corridor")
dbutils.widgets.text("run_path", "")

code_root = dbutils.widgets.get("code_root").rstrip("/")
catalog, schema = dbutils.widgets.get("catalog"), dbutils.widgets.get("schema")
for name in (catalog, schema):
    if not name.replace("_", "").isalnum():
        raise ValueError(f"invalid identifier {name!r}")
prefix = f"{catalog}.{schema}"
run_path = dbutils.jobs.taskValues.get(
    taskKey="pipeline",
    key="run_path",
    default=dbutils.widgets.get("run_path"),
    debugValue=dbutils.widgets.get("run_path"),
)
if not run_path:
    raise ValueError("run_path: set by the pipeline task, or passed by hand for an interactive run")
sys.path.insert(0, f"{code_root}/src")
spark.conf.set("spark.sql.session.timeZone", "America/Toronto")

from decision_platform.features import FEATURES  # noqa: E402
from decision_platform.spark_features import build_features  # noqa: E402

# COMMAND ----------

# Bronze keeps the feed as delivered, planted defects included; silver is the conformed layer with
# its quarantine table; gold is the marts. Each is a Delta table, replaced whole on every run.
landed = {}
for layer in ("bronze", "silver", "gold"):
    folder = f"{run_path}/data/{layer}"
    for entry in sorted(os.listdir(folder)):
        if not entry.endswith(".parquet"):
            continue
        table = f"{prefix}.{layer}_{entry.removesuffix('.parquet')}"
        (
            spark.read.parquet(f"{folder}/{entry}")
            .write.mode("overwrite")
            .option("overwriteSchema", "true")
            .saveAsTable(table)
        )
        landed[table] = spark.table(table).count()
print(f"{len(landed)} Delta tables landed")

# COMMAND ----------

# The silver trip contract, enforced by Delta on every future write rather than checked once.
trip = f"{prefix}.silver_fact_trip"
contract = {
    "toll_non_negative": "toll >= 0",
    "charge_within_toll": "final_charge >= 0 AND final_charge <= toll + 0.000001",
    "distance_positive": "distance_km > 0",
    "known_period": "period IN ('Peak', 'Off-peak', 'Weekend')",
}
for name, rule in contract.items():
    spark.sql(f"ALTER TABLE {trip} DROP CONSTRAINT IF EXISTS {name}")
    spark.sql(f"ALTER TABLE {trip} ADD CONSTRAINT {name} CHECK ({rule})")
spark.sql(
    f"COMMENT ON TABLE {trip} IS 'Conformed 407-style trips: one row per trip_id; defects are in silver_quarantine_trip'"
)
duplicates = spark.sql(f"SELECT COUNT(*) - COUNT(DISTINCT trip_id) AS d FROM {trip}").first()["d"]
if duplicates:
    raise AssertionError(f"{duplicates} duplicate trip_id values in silver")
quarantine = {
    row["reason"]: row["n"]
    for row in spark.sql(
        f"SELECT reason, COUNT(*) AS n FROM {prefix}.silver_quarantine_trip GROUP BY reason"
    ).collect()
}
spark.sql(f"OPTIMIZE {trip} ZORDER BY (customer_id)")

# COMMAND ----------

# PySpark features over the silver Delta tables, then the parity gate against DuckDB.
features = build_features(
    spark, None, as_of="2025-10-01", table_reader=lambda name: spark.table(f"{prefix}.silver_{name}")
).select("customer_id", *FEATURES)
gold = f"{prefix}.gold_customer_features_spark"
features.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(gold)
spark.sql(f"ALTER TABLE {gold} ALTER COLUMN customer_id SET NOT NULL")
spark.sql(f"ALTER TABLE {gold} DROP CONSTRAINT IF EXISTS customer_features_pk")
spark.sql(f"ALTER TABLE {gold} ADD CONSTRAINT customer_features_pk PRIMARY KEY (customer_id)")

computed = spark.table(gold).toPandas().sort_values("customer_id").reset_index(drop=True)
reference = (
    pd.read_parquet(f"{run_path}/data/gold/customer_360.parquet")
    .sort_values("customer_id")
    .reset_index(drop=True)
)
if not computed.customer_id.equals(reference.customer_id):
    raise AssertionError("PySpark and DuckDB features cover different customers")
errors = {
    f: float(np.max(np.abs(computed[f].to_numpy(float) - reference[f].to_numpy(float)))) for f in FEATURES
}
worst = max(errors, key=errors.get)
if errors[worst] >= 1e-7:
    raise AssertionError(f"feature parity failed: {worst} differs by {errors[worst]}")

history = spark.sql(f"DESCRIBE HISTORY {trip}").count()
receipt = {
    "tables": len(landed),
    "silver_trips": landed[trip],
    "bronze_trips": landed[f"{prefix}.bronze_fact_trip"],
    "quarantined": quarantine,
    "check_constraints": sorted(contract),
    "features_checked": len(FEATURES),
    "customers": len(computed),
    "max_feature_error": errors[worst],
    "worst_feature": worst,
    "delta_history_versions": history,
}
dbutils.jobs.taskValues.set(key="lakehouse", value=json.dumps(receipt))
print(json.dumps(receipt, indent=2))
