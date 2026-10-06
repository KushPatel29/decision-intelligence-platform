"""Execute SageMaker-compatible stages locally without an AWS API call."""

import json
import shutil
import sys
import tarfile

import numpy as np
from threadpoolctl import threadpool_limits

from decision_platform.config import ROOT, write_json

sys.path.insert(0, str(ROOT / "aws"))
from evaluate_entry import evaluate
from process_entry import process
from train_entry import input_fn, model_fn, output_fn, predict_fn, train


def main():
    destination = ROOT / "outputs/sagemaker_local"
    source = destination / "source"
    source.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "data/gold/customer_month.parquet", source)
    shutil.copy2(ROOT / "outputs/feature_contract.json", source)
    channels = destination / "channels"
    counts = process(source, channels)
    with threadpool_limits(limits=1):
        validation = train(
            channels / "train", channels / "validation", destination / "model", destination / "training"
        )
    archive = destination / "model.tar.gz"
    with tarfile.open(archive, "w:gz") as bundle:
        bundle.add(destination / "model/model.joblib", arcname="model.joblib")
    test = evaluate(archive, channels / "test/test.csv", destination / "evaluation/evaluation.json")
    body = "\n".join((channels / "inference/features.csv").read_text().splitlines()[:12])
    predictions = predict_fn(input_fn(body, "text/csv"), model_fn(destination / "model"))
    response, mime = output_fn(predictions, "text/csv")
    np.testing.assert_allclose(np.array(response.splitlines(), dtype=float), predictions)
    assert len(predictions) == 12 and np.isfinite(predictions).all()
    assert ((predictions >= 0) & (predictions <= 1)).all() and mime == "text/csv"
    quality_gate = test["classification"]["roc_auc"]["value"] >= 0.70
    assert quality_gate
    receipt = {
        "status": "passed",
        "scope": "local stage execution; hosted AWS execution pending",
        "channel_rows": counts,
        "validation": validation,
        "heldout_test": test,
        "quality_gate_passed": quality_gate,
        "batch_inference_rows": len(predictions),
        "csv_prediction_roundtrip_passed": True,
        "aws_api_calls": 0,
        "cloud_cost": 0,
    }
    write_json(ROOT / "outputs/sagemaker_local_validation.json", receipt)
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
