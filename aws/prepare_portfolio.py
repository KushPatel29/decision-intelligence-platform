"""Build six independent purged/model-specific input bundles; no AWS API calls."""

import json
from pathlib import Path

import numpy as np
import pandas as pd

from decision_platform.config import ROOT
from decision_platform.features import FEATURES


def prepare(root=ROOT):
    root = Path(root)
    destination = root / "outputs/cloud_portfolio"
    rows = []
    snapshots = pd.read_parquet(root / "data/gold/customer_month.parquet")
    trial = pd.read_parquet(root / "data/silver/fact_campaign_result.parquet")
    pricing = pd.read_parquet(root / "data/silver/fact_pricing_scenario.parquet").copy()
    pricing["log_price"] = np.log(pricing.effective_price)
    pricing["period_code"] = pricing.period.map({"Peak": 0, "Off-peak": 1, "Weekend": 2})
    demand = pd.read_parquet(root / "data/gold/zone_day.parquet")
    for task in ["propensity", "churn", "attrition", "uplift", "elasticity", "demand"]:
        if task in {"propensity", "churn", "attrition"}:
            frame = snapshots.copy()
            features = FEATURES
            target = "target_" + task
            if task != "propensity":
                frame = frame[frame.historically_active]
            groups = {s: frame[frame.split.eq(s)] for s in ["train", "validation", "test"]}
        elif task == "uplift":
            frame = trial.copy()
            frame["assigned_arm"] = frame.arm.map(
                {"Control": 0, "Off-peak 15%": 1, "Weekend 20%": 2, "500 loyalty points": 3}
            )
            features = FEATURES + ["assigned_arm"]
            target = "response"
            groups = {s: frame[frame.split.eq(s)] for s in ["train", "validation", "test"]}
        else:
            frame = pricing if task == "elasticity" else demand
            features = (
                [
                    "zone_id",
                    "period_code",
                    "log_price",
                    "temperature_c",
                    "precipitation_mm",
                    "weekend",
                    "holiday",
                    "month_sin",
                    "month_cos",
                ]
                if task == "elasticity"
                else [
                    "zone_id",
                    "period_code",
                    "dow",
                    "weekend",
                    "holiday",
                    "month_sin",
                    "month_cos",
                    "lag7",
                    "rolling28",
                    "weather_lag1",
                    "temperature_lag1",
                    "economic_lag1",
                ]
            )
            target = "demand" if task == "elasticity" else "trips"
            frame = frame.dropna(subset=features + [target])
            groups = {
                "train": frame[frame.date < "2025-04-01"],
                "validation": frame[(frame.date >= "2025-04-01") & (frame.date < "2025-07-01")],
                "test": frame[(frame.date >= "2025-07-01") & (frame.date < "2025-10-01")],
            }
        folder = destination / task / "input"
        folder.mkdir(parents=True, exist_ok=True)
        contract = {
            "task": task,
            "features": features,
            "target": target,
            "seed": 407,
            "version": "2.0",
            "scope": "Synthetic; chronological customer/price/demand or customer-randomized trial folds",
        }
        (folder / "feature_contract.json").write_text(json.dumps(contract, indent=2))
        for split, g in groups.items():
            g[features + [target]].to_csv(folder / (split + ".csv"), index=False)
        groups["test"][features].head(12).to_csv(folder / "features.csv", index=False, header=False)
        rows.append(
            {
                "task": task,
                "train": len(groups["train"]),
                "validation": len(groups["validation"]),
                "test": len(groups["test"]),
                "features": len(features),
            }
        )
    return destination, rows


if __name__ == "__main__":
    folder, rows = prepare()
    print(json.dumps(rows, indent=2))
