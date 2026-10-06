import argparse
import json
import shutil
from pathlib import Path

import pandas as pd
from portfolio_entry import validate


def process(source, destination):
    source = Path(source)
    destination = Path(destination)
    contract = json.loads((source / "feature_contract.json").read_text())
    for split in ["train", "validation", "test"]:
        frame = validate(pd.read_csv(source / (split + ".csv")), contract)
        folder = destination / split
        folder.mkdir(parents=True, exist_ok=True)
        frame.to_csv(folder / (split + ".csv"), index=False)
        shutil.copy2(source / "feature_contract.json", folder / "feature_contract.json")
    folder = destination / "inference"
    folder.mkdir(parents=True, exist_ok=True)
    inference = pd.read_csv(source / "features.csv", header=None)
    inference.columns = contract["features"]
    validate(inference, contract, labelled=False)
    inference.to_csv(folder / "features.csv", header=False, index=False)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--source", default="/opt/ml/processing/input")
    p.add_argument("--destination", default="/opt/ml/processing/output")
    a = p.parse_args()
    process(a.source, a.destination)
