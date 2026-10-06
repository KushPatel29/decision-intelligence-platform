"""Execute all six cloud contracts locally; preserve failed model gates honestly."""

import json
import sys
import tarfile

import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

from decision_platform.config import ROOT, write_json

sys.path.insert(0, str(ROOT / "aws"))
from evaluate_portfolio import evaluate
from portfolio_entry import predictions, train
from prepare_portfolio import prepare
from process_portfolio import process


def main():
    destination, counts = prepare()
    results = []
    with threadpool_limits(limits=1):
        for row in counts:
            task = row["task"]
            folder = destination / task
            process(folder / "input", folder / "prepared")
            bundle = train(
                folder / "prepared/train",
                folder / "prepared/validation",
                folder / "model",
                folder / "validation",
            )
            archive = folder / "model.tar.gz"
            with tarfile.open(archive, "w:gz") as out:
                out.add(folder / "model/model.joblib", arcname="model.joblib")
            report = evaluate(archive, folder / "prepared/test/test.csv", folder / "evaluation.json")
            sample = pd.read_csv(folder / "prepared/inference/features.csv", header=None)
            sample.columns = bundle["contract"]["features"]
            scored = predictions(bundle, sample)
            if not np.isfinite(scored).all():
                raise ValueError("Nonfinite cloud inference")
            pd.DataFrame(scored).to_csv(folder / "batch_predictions.csv", index=False, header=False)
            np.testing.assert_allclose(
                pd.read_csv(folder / "batch_predictions.csv", header=None).to_numpy().squeeze(),
                np.asarray(scored).squeeze(),
                rtol=1e-8,
                atol=1e-10,
            )
            results.append({**row, "stages_passed": True, "batch_roundtrip": True, "evaluation": report})
    write_json(
        ROOT / "outputs/cloud_portfolio_validation.json",
        {
            "status": "local contracts passed",
            "aws_api_calls": 0,
            "container_build_tested": False,
            "models": results,
            "scope": "Preparation, training, untouched test gate and CSV inference executed locally; Docker/ECR and hosted AWS jobs remain unverified",
        },
    )
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
