"""Prepare explicit train/validation/test/inference artifacts; local file operations only."""

import json

import pandas as pd

from decision_platform.config import ROOT
from decision_platform.features import FEATURES


def prepare(root=ROOT):
    snapshots = pd.read_parquet(root / "data" / "gold" / "customer_month.parquet")
    destination = root / "outputs" / "sagemaker_channels"
    for split in ["train", "validation", "test"]:
        folder = destination / split
        folder.mkdir(parents=True, exist_ok=True)
        frame = snapshots[snapshots.split.eq(split)]
        frame[FEATURES + ["target_propensity"]].to_csv(folder / f"{split}.csv", index=False)
        if split == "train":
            (folder / "feature_contract.json").write_text(
                json.dumps(
                    {
                        "features": FEATURES,
                        "version": "1.0",
                        "seed": 407,
                        "population": "synthetic",
                        "target": "trip in following 30 days",
                    },
                    indent=2,
                )
            )
    current = pd.read_parquet(root / "data" / "gold" / "customer_360.parquet")
    inference = destination / "inference"
    inference.mkdir(parents=True, exist_ok=True)
    current[FEATURES].to_csv(inference / "features.csv", index=False, header=False)
    current[["customer_id"]].to_csv(inference / "keys.csv", index=False)
    print(destination)
    return destination


if __name__ == "__main__":
    prepare()
