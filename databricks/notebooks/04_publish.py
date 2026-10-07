# Databricks notebook source
# MAGIC %md
# MAGIC # 4 · Publish the decision and the run receipt
# MAGIC
# MAGIC Publishes the serving snapshot (the October campaign plan, every candidate offer, the policy
# MAGIC comparison, the budget frontier, capacity, prices, trial results) as Delta tables for Power BI and
# MAGIC SQL users, reconciles the published plan against the optimizer's own certificate, and appends one
# MAGIC row to `run_receipts`: what ran, on which data, with what result, and whether every check held.

# COMMAND ----------

import json
import os
import re
from datetime import UTC, datetime

dbutils.widgets.text("catalog", "workspace")
dbutils.widgets.text("schema", "corridor")
dbutils.widgets.text("run_path", "")
dbutils.widgets.text("job_run_id", "")

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


def task_value(task, key):
    return json.loads(dbutils.jobs.taskValues.get(taskKey=task, key=key, default="{}", debugValue="{}"))


# COMMAND ----------

serving = f"{run_path}/outputs/serving"


def delta_safe(frame):
    """Snake-case column names: Delta rejects spaces and ,;{}()= in names, and SQL users prefer them anyway.

    One serving table is a pivot whose columns are policy names such as "Optimized (MIP)".
    """
    names, seen = [], set()
    for column in frame.columns:
        name = re.sub(r"[^0-9A-Za-z_]+", "_", column).strip("_").lower() or "column"
        while name in seen:
            name += "_"
        seen.add(name)
        names.append(name)
    return frame.toDF(*names)


published = {}
for entry in sorted(os.listdir(serving)):
    if entry.endswith(".parquet"):
        table = f"{prefix}.serving_{entry.removesuffix('.parquet')}"
        delta_safe(spark.read.parquet(f"{serving}/{entry}")).write.mode("overwrite").option(
            "overwriteSchema", "true"
        ).saveAsTable(table)
        published[table] = spark.table(table).count()
documents = [
    (entry.removesuffix(".json"), open(f"{serving}/{entry}").read())
    for entry in sorted(os.listdir(serving))
    if entry.endswith(".json")
]
spark.createDataFrame(documents, "name STRING, body STRING").write.mode("overwrite").option(
    "overwriteSchema", "true"
).saveAsTable(f"{prefix}.serving_documents")

# COMMAND ----------

# The published plan must be the plan the optimizer certified: same contacts, same spend, inside every limit.
optimization = json.loads(open(f"{run_path}/outputs/optimization_results.json").read())
combined, certificate = optimization["combined"], optimization["certification"]
plan = spark.sql(
    f"SELECT COUNT(*) AS contacts, COUNT(DISTINCT customer_id) AS customers, SUM(cost) AS spend, "
    f"SUM(objective_value) AS value, SUM(points) AS points FROM {prefix}.serving_decisions"
).first()
checks = {
    "one_offer_per_customer": plan["contacts"] == plan["customers"],
    "contacts_match_certificate": plan["contacts"] == combined["contacts"],
    "spend_matches_certificate": abs(plan["spend"] - combined["spend"]) < 0.01,
    "value_matches_certificate": abs(plan["value"] - combined["objective_value"]) < 0.01,
    "within_budget": plan["spend"] <= combined["budget"] + 1e-6,
    "within_contact_limit": plan["contacts"] <= combined["contact_limit"],
    "within_points_cap": plan["points"] <= combined["points_limit"],
    "proven_optimal": bool(certificate.get("proven_optimal")),
}
failed = [name for name, ok in checks.items() if not ok]

# COMMAND ----------

pipeline, lakehouse, registry = (
    task_value("pipeline", "pipeline"),
    task_value("lakehouse", "lakehouse"),
    task_value("registry", "registry"),
)
receipt = {
    "recorded_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
    "databricks_job_run_id": dbutils.widgets.get("job_run_id"),
    "pipeline": pipeline,
    "lakehouse": lakehouse,
    "registry": registry,
    "published_tables": len(published) + 1,
    "plan_checks": checks,
    "status": "passed" if not failed else "failed: " + ", ".join(failed),
}
spark.sql(
    f"CREATE TABLE IF NOT EXISTS {prefix}.run_receipts (pipeline_run_id STRING, recorded_at_utc STRING, "
    "status STRING, receipt STRING) COMMENT 'One row per Corridor job run: what ran and whether every check held'"
)
spark.createDataFrame(
    [(pipeline.get("run_id", ""), receipt["recorded_at_utc"], receipt["status"], json.dumps(receipt))],
    "pipeline_run_id STRING, recorded_at_utc STRING, status STRING, receipt STRING",
).write.mode("append").saveAsTable(f"{prefix}.run_receipts")
with open(f"{run_path}/receipt.json", "w") as handle:
    json.dump(receipt, handle, indent=2)
print(json.dumps(receipt, indent=2))
if failed:
    raise AssertionError(f"plan reconciliation failed: {failed}")
dbutils.notebook.exit(json.dumps(receipt))
