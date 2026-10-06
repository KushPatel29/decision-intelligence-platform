"""Register calibrated candidates in the local MLflow registry with review aliases."""

import json

import joblib
import mlflow
import numpy as np
import pandas as pd
from mlflow.tracking import MlflowClient

from decision_platform.config import ROOT, write_json
from decision_platform.features import FEATURES
from decision_platform.scoring import score_bundle


class CustomerScorer(mlflow.pyfunc.PythonModel):
    def __init__(self, bundle, name="propensity"):
        self.bundle = bundle
        self.name = name

    def predict(self, context, model_input, params=None):
        return score_bundle(self.name, self.bundle, model_input)


def main():
    mlflow.set_tracking_uri("sqlite:///" + str(ROOT / "outputs/mlflow.db").replace("\\", "/"))
    mlflow.set_experiment("transportation-decision-intelligence")
    client = MlflowClient()
    customer_sample = pd.read_parquet(ROOT / "data/gold/customer_360.parquet")[FEATURES].head(5)
    metrics = json.loads((ROOT / "outputs/model_metrics.json").read_text())
    rows = []
    manifest = json.loads((ROOT / "outputs/manifest.json").read_text())
    for name in [
        "propensity",
        "churn",
        "attrition",
        "clv",
        "uplift",
        "elasticity",
        "demand",
        "segmentation",
        "anomaly",
    ]:
        bundle = joblib.load(ROOT / "outputs/models" / (name + ".joblib"))
        scorer = CustomerScorer(bundle, name)
        sample = customer_sample
        if name == "demand":
            sample = (
                pd.read_parquet(ROOT / "data/gold/zone_day.parquet")
                .dropna(subset=bundle["features"])[bundle["features"]]
                .tail(5)
            )
        if name == "elasticity":
            sample = pd.read_parquet(ROOT / "data/silver/fact_pricing_scenario.parquet").tail(5).copy()
            sample["log_price"] = np.log(sample.effective_price)
            sample = sample[["zone_id", "period"] + bundle["features"]]
        registered = "Corridor-" + name
        with mlflow.start_run(run_name="registry-" + name):
            info = mlflow.pyfunc.log_model(
                name=name,
                python_model=scorer,
                input_example=sample,
                pip_requirements=["mlflow==" + mlflow.__version__, "scikit-learn", "numpy", "pandas"],
                code_paths=[str(ROOT / "src/decision_platform")],
                registered_model_name=registered,
            )
            version = str(info.registered_model_version)
            client.set_registered_model_alias(registered, "Candidate", version)
            client.set_model_version_tag(registered, version, "data_kind", "synthetic")
            client.set_model_version_tag(registered, version, "release", "0.4.0")
            client.set_model_version_tag(registered, version, "git_sha", manifest["git_sha"])
            client.set_model_version_tag(registered, version, "approval", "PendingReview")
            for artifact in [
                ROOT / "outputs/shap_global.csv",
                ROOT / "outputs/feature_contract.json",
                ROOT / "outputs/quality_gate.json",
            ]:
                if artifact.exists():
                    mlflow.log_artifact(str(artifact), artifact_path="provenance")
            # Candidate status deliberately requires independent production review.
            loaded = mlflow.pyfunc.load_model(f"models:/{registered}@Candidate")
            np.testing.assert_allclose(loaded.predict(sample), scorer.predict(None, sample), rtol=1e-9)
            row = {
                "model": registered,
                "version": version,
                "alias": "Candidate",
                "roundtrip_predictions_match": True,
                "git_sha": manifest["git_sha"],
                "scope": "local registry; requires review before operational champion promotion",
            }
            if name in {"propensity", "churn", "attrition"}:
                row["test_auc"] = metrics["customer"][name]["test_calibrated"]["roc_auc"]
            rows.append(row)
    write_json(ROOT / "outputs/model_registry.json", rows)
    print(rows)


if __name__ == "__main__":
    main()
