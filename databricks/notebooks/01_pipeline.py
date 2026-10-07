# Databricks notebook source
# MAGIC %md
# MAGIC # 1 · Decision pipeline
# MAGIC
# MAGIC Runs the whole Corridor pipeline on serverless compute: the synthetic toll-road ecosystem, point-in-time
# MAGIC features, the customer models (tracked in this workspace's MLflow), the ten-arm randomised trial, the
# MAGIC causal learners, the full-population campaign MIP (HiGHS LP bound and rounding, the residual core
# MAGIC solved and independently checked by **Gurobi**), pricing, marts, monitoring and the release gate.
# MAGIC
# MAGIC The pipeline needs a POSIX file system for DuckDB, so it runs on the task's local disk and then copies
# MAGIC its layers and outputs to a Unity Catalog volume, which is how the later tasks receive them.
# MAGIC
# MAGIC Packages are pinned to `databricks/job-packages.txt`, the versions the local run was tested with,
# MAGIC except numpy, pandas and pyarrow, which serverless fixes; the run's manifest records the versions used.

# COMMAND ----------

# MAGIC %pip install --quiet "scipy==1.18.1" "scikit-learn==1.9.0" "duckdb==1.5.4" "joblib==1.6.0" "threadpoolctl==3.6.0" "xgboost==2.0.3" "lifetimes==0.11.3" "shap==0.52.0" "gurobipy==13.0.3" "mlflow==3.14.0"

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

dbutils.widgets.text("code_root", "")
dbutils.widgets.text("catalog", "workspace")
dbutils.widgets.text("schema", "corridor")
dbutils.widgets.text("customers", "25000")
dbutils.widgets.text("solver", "auto")

code_root = dbutils.widgets.get("code_root").rstrip("/")
catalog, schema = dbutils.widgets.get("catalog"), dbutils.widgets.get("schema")
customers, solver = int(dbutils.widgets.get("customers")), dbutils.widgets.get("solver")
if not code_root:
    raise ValueError("code_root: the workspace folder that holds src/, sql/ and data/external/")
for name in (catalog, schema):
    if not name.replace("_", "").isalnum():
        raise ValueError(f"invalid identifier {name!r}")
if solver not in {"auto", "gurobi", "highs"}:
    raise ValueError(f"solver must be auto, gurobi or highs, not {solver!r}")
sys.path.insert(0, f"{code_root}/src")

# COMMAND ----------

# The pipeline reads its SQL and the cached public context (weather, holidays, CAD/USD) from its root.
work = Path(tempfile.mkdtemp(prefix="corridor-"))
shutil.copytree(f"{code_root}/sql", work / "sql")
shutil.copytree(f"{code_root}/data/external", work / "data" / "external")

user = spark.sql("SELECT current_user()").first()[0]
experiment = f"/Users/{user}/corridor-decision-platform"
os.environ["MLFLOW_TRACKING_URI"] = "databricks"
os.environ["CORRIDOR_MLFLOW_EXPERIMENT"] = experiment
os.environ["CORRIDOR_ARTIFACT_STATUS"] = "databricks-candidate"

from decision_platform.cli import run  # noqa: E402
from decision_platform.config import Config  # noqa: E402

# Budget, contact limit and points cap scale with the population, as in the CLI.
scale = customers / Config().customers
cfg = Config(
    customers=customers,
    root=work,
    budget=Config().budget * scale,
    campaign_limit=int(Config().campaign_limit * scale),
    points_budget=int(Config().points_budget * scale),
)
started = time.perf_counter()
run(cfg, solver, tracking=True)
runtime = time.perf_counter() - started

# COMMAND ----------


def copy_tree(source: Path, target: Path) -> int:
    """Plain file copies: volumes do not take the metadata calls shutil.copytree makes."""
    count = 0
    for folder, _dirs, files in os.walk(source):
        destination = target / Path(folder).relative_to(source)
        destination.mkdir(parents=True, exist_ok=True)
        for name in files:
            shutil.copyfile(Path(folder) / name, destination / name)
            count += 1
    return count


spark.sql(f"CREATE SCHEMA IF NOT EXISTS {catalog}.{schema}")
spark.sql(f"CREATE VOLUME IF NOT EXISTS {catalog}.{schema}.runs")
outputs = work / "outputs"
run_id = json.loads((outputs / "run_status.json").read_text())["run_id"]
# CORRIDOR_VOLUME_ROOT exists for databricks/local_run.py; on Databricks it is unset and this is /Volumes.
target = Path(os.environ.get("CORRIDOR_VOLUME_ROOT", "/Volumes")) / catalog / schema / "runs" / run_id
copied = 0
for part in ["data/bronze", "data/silver", "data/gold", "outputs/serving", "outputs/models", "powerbi/data"]:
    copied += copy_tree(work / part, target / part)
for document in outputs.glob("*.json"):
    shutil.copyfile(document, target / "outputs" / document.name)
    copied += 1

summary = json.loads((outputs / "summary.json").read_text())
certificate = json.loads((outputs / "optimization_results.json").read_text())["certification"]
gate = json.loads((outputs / "quality_gate.json").read_text())
receipt = {
    "run_id": run_id,
    "runtime_seconds": round(runtime, 1),
    "files_copied": copied,
    "mlflow_experiment": experiment,
    "solver": summary["solver"],
    "proven_optimal": bool(certificate.get("proven_optimal")),
    "gurobi_check": certificate.get("gurobi_check", {}),
    "gate_passed": bool(gate["passed"]),
    "contacts": summary["selected_contacts"],
    "spend": round(summary["campaign_spend"], 2),
    "expected_value": round(summary["expected_total_value"], 2),
    "true_value": round(summary["true_value_optimized"], 2),
    "share_of_oracle": round(summary["share_of_oracle_optimized"], 4),
}
dbutils.jobs.taskValues.set(key="run_path", value=target.as_posix())
dbutils.jobs.taskValues.set(key="pipeline", value=json.dumps(receipt))
print(json.dumps(receipt, indent=2))
if not receipt["gate_passed"]:
    raise RuntimeError("The release acceptance gate failed; later tasks must not publish this run.")
