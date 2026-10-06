"""Validation-only model selection and explicit release acceptance criteria."""
import numpy as np
from sklearn.metrics import mean_absolute_error


class HistoricalMargin:
    def __init__(self, margin=.72):
        self.margin = margin

    def predict(self, frame):
        return np.maximum(frame["spend_90d"].to_numpy(dtype=float) * self.margin, 0)

class SeasonalNaive:
    def predict(self,frame):
        return np.maximum(frame["lag7"].to_numpy(dtype=float),0)


def select_regression(target, predictions):
    if len(target) == 0:
        raise ValueError("Empty validation population")
    scores = {}
    for name, values in predictions.items():
        values = np.asarray(values, dtype=float)
        if len(values) != len(target) or not np.isfinite(values).all():
            raise ValueError("Invalid validation predictions")
        scores[name] = float(mean_absolute_error(target, np.maximum(values, 0)))
    # Prefer the simpler baseline when errors tie; test outcomes never select a model.
    selected = min(reversed(list(scores)), key=lambda name: scores[name])
    return {"selected": selected, "validation_mae": scores, "selection_split": "April–June 2025 validation; test untouched"}


def evaluate_quality(metrics):
    checks = []
    for name in ["propensity", "churn", "attrition"]:
        m = metrics["customer"][name]["test_calibrated"]
        baseline_brier = m["prevalence"] * (1-m["prevalence"])
        checks.append({"model": name, "passed": bool(m["roc_auc"] >= .70 and m["ece_10bins"] <= .10 and m["brier"] <= baseline_brier),
                       "criteria": "AUC ≥0.70, ECE ≤0.10, Brier no worse than constant prevalence", "auc": m["roc_auc"], "ece": m["ece_10bins"]})
    for name, m, baseline in [("contribution", metrics["customer"]["clv"]["test"], "baseline_mae"), ("demand", metrics["demand"]["test"], "seasonal_naive_mae")]:
        checks.append({"model": name, "passed": bool(m["mae"] <= m[baseline] + 1e-8), "criteria": "Held-out MAE no worse than declared baseline", "mae": m["mae"], "baseline_mae": m[baseline]})
    return {"passed": all(c["passed"] for c in checks), "checks": checks, "scope": "Synthetic local quality gate; production population validation required"}
