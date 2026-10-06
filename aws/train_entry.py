"""Initial SageMaker-compatible propensity training entry point.

Local-testable; no AWS call is made. Cloud train channel must contain labelled
CSV columns matching the persisted feature contract, and validation is a separate
time-purged fold. This is the first cloud model, not the full portfolio pipeline.
"""

import argparse
import json
import os
from pathlib import Path

import joblib
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


def train(train_dir, validation_dir, model_dir, output_dir, seed=407):
    tr = pd.read_csv(Path(train_dir) / "train.csv")
    va = pd.read_csv(Path(validation_dir) / "validation.csv")
    contract = json.loads((Path(train_dir) / "feature_contract.json").read_text())
    features = contract["features"]
    if any(c.startswith(("target_", "future_", "latent_", "true_")) for c in features):
        raise ValueError("Forbidden feature in contract")
    if set(tr.columns) != set(features + ["target_propensity"]):
        raise ValueError("Unexpected train schema")
    model = make_pipeline(StandardScaler(), LogisticRegression(max_iter=1500, random_state=seed))
    model.fit(tr[features], tr.target_propensity)
    scores = model.predict_proba(va[features])[:, 1]
    metrics = {
        "validation_auc": float(roc_auc_score(va.target_propensity, scores)),
        "validation_brier": float(brier_score_loss(va.target_propensity, scores)),
        "validation_rows": len(va),
    }
    model_dir = Path(model_dir)
    model_dir.mkdir(parents=True, exist_ok=True)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": model, "features": features, "contract": contract}, model_dir / "model.joblib")
    (output_dir / "validation.json").write_text(json.dumps(metrics, indent=2))
    print(json.dumps(metrics))
    return metrics


def model_fn(model_dir):
    return joblib.load(Path(model_dir) / "model.joblib")


def input_fn(body, content_type):
    from io import StringIO

    if content_type != "text/csv":
        raise ValueError("Only feature CSV is supported")
    return pd.read_csv(StringIO(body), header=None)


def predict_fn(frame, model):
    if len(frame.columns) != len(model["features"]):
        raise ValueError("Inference feature count mismatch")
    frame.columns = model["features"]
    return model["model"].predict_proba(frame)[:, 1]


def output_fn(predictions, accept):
    if accept != "text/csv":
        raise ValueError("Only CSV predictions are supported")
    return "\n".join(str(float(p)) for p in predictions), "text/csv"


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--train-dir", default=os.getenv("SM_CHANNEL_TRAIN", "/opt/ml/input/data/train"))
    parser.add_argument(
        "--validation-dir", default=os.getenv("SM_CHANNEL_VALIDATION", "/opt/ml/input/data/validation")
    )
    parser.add_argument("--model-dir", default=os.getenv("SM_MODEL_DIR", "/opt/ml/model"))
    parser.add_argument("--output-dir", default=os.getenv("SM_OUTPUT_DATA_DIR", "/opt/ml/output/data"))
    args = parser.parse_args()
    train(args.train_dir, args.validation_dir, args.model_dir, args.output_dir)
