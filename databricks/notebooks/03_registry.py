# Databricks notebook source
# MAGIC %md
# MAGIC # 3 · Unity Catalog model registry
# MAGIC
# MAGIC Registers the run's champion models in Unity Catalog as MLflow pyfunc models with a signature, an
# MAGIC input example and pinned requirements: the three calibrated customer classifiers (travel propensity,
# MAGIC 90-day inactivity, attrition) and the causal uplift ensemble, which returns incremental trips for every
# MAGIC offer and travel period. Each version gets the alias `candidate`, never `champion`: promotion stays a
# MAGIC reviewed step. Every registered version is loaded back from the registry and must score a sample
# MAGIC exactly as the pipeline did, or the task fails.

# COMMAND ----------

# MAGIC %pip install --quiet "numpy>=2.0" "pandas>=2.2" "scipy>=1.14" "scikit-learn>=1.5" "joblib>=1.4" "xgboost>=2.0" "mlflow>=3"

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

import json
import sys

import joblib
import mlflow
import numpy as np
import pandas as pd
import scipy
import sklearn
import xgboost
from mlflow import MlflowClient
from mlflow.models import infer_signature

dbutils.widgets.text("code_root", "")
dbutils.widgets.text("catalog", "workspace")
dbutils.widgets.text("schema", "corridor")
dbutils.widgets.text("run_path", "")

code_root = dbutils.widgets.get("code_root").rstrip("/")
catalog, schema = dbutils.widgets.get("catalog"), dbutils.widgets.get("schema")
for name in (catalog, schema):
    if not name.replace("_", "").isalnum():
        raise ValueError(f"invalid identifier {name!r}")
run_path = dbutils.jobs.taskValues.get(
    taskKey="pipeline",
    key="run_path",
    default=dbutils.widgets.get("run_path"),
    debugValue=dbutils.widgets.get("run_path"),
)
sys.path.insert(0, f"{code_root}/src")
from decision_platform.features import FEATURES  # noqa: E402
from decision_platform.scoring import score_bundle  # noqa: E402

user = spark.sql("SELECT current_user()").first()[0]
mlflow.set_tracking_uri("databricks")
mlflow.set_registry_uri("databricks-uc")
mlflow.set_experiment(f"/Users/{user}/corridor-decision-platform")
client = MlflowClient()

# COMMAND ----------


class CorridorScorer(mlflow.pyfunc.PythonModel):
    """Scores one Corridor model bundle with the same adapter the pipeline and batch clients use."""

    def __init__(self, name):
        self.name = name

    def load_context(self, context):
        self.bundle = joblib.load(context.artifacts["bundle"])

    def predict(self, context, model_input, params=None):
        from decision_platform.scoring import score_bundle

        return score_bundle(self.name, self.bundle, model_input)


sample = pd.read_parquet(f"{run_path}/data/gold/customer_360.parquet")[FEATURES].head(50)
run_id = run_path.rstrip("/").rsplit("/", 1)[-1]
metrics = json.loads(open(f"{run_path}/outputs/model_metrics.json").read())
gate = json.loads(open(f"{run_path}/outputs/quality_gate.json").read())
requirements = [
    f"numpy=={np.__version__}",
    f"pandas=={pd.__version__}",
    f"scipy=={scipy.__version__}",
    f"scikit-learn=={sklearn.__version__}",
    f"xgboost=={xgboost.__version__}",
    f"joblib=={joblib.__version__}",
]
registered = {}
for name in ["propensity", "churn", "attrition", "uplift"]:
    artifact = f"{run_path}/outputs/models/{name}.joblib"
    expected = score_bundle(name, joblib.load(artifact), sample)
    full_name = f"{catalog}.{schema}.corridor_{name}"
    with mlflow.start_run(run_name=f"register-{name}"):
        mlflow.set_tags(
            {"pipeline_run_id": run_id, "data_kind": "synthetic", "gate_passed": str(gate["passed"])}
        )
        if name in metrics["customer"]:
            test = metrics["customer"][name]["test_calibrated"]
            mlflow.log_metrics({k: float(test[k]) for k in ("roc_auc", "pr_auc", "brier", "ece_10bins")})
            mlflow.set_tag("champion_algorithm", metrics["customer"][name]["champion"])
        info = mlflow.pyfunc.log_model(
            name=name,
            python_model=CorridorScorer(name),
            artifacts={"bundle": artifact},
            code_paths=[f"{code_root}/src/decision_platform"],
            input_example=sample.head(5),
            signature=infer_signature(sample, expected),
            pip_requirements=requirements,
            registered_model_name=full_name,
        )
    version = str(info.registered_model_version)
    client.set_registered_model_alias(full_name, "candidate", version)
    client.set_model_version_tag(full_name, version, "pipeline_run_id", run_id)
    client.set_model_version_tag(full_name, version, "approval", "pending-review")
    # Load back through the registry and score: the round trip is the receipt.
    loaded = mlflow.pyfunc.load_model(f"models:/{full_name}@candidate")
    scored = loaded.predict(sample)
    np.testing.assert_allclose(np.asarray(scored, float), np.asarray(expected, float), rtol=0, atol=1e-12)
    registered[full_name] = version

dbutils.jobs.taskValues.set(key="registry", value=json.dumps(registered))
print(json.dumps(registered, indent=2))
