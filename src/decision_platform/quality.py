"""Validation-only model selection and explicit release acceptance criteria."""

import numpy as np
from sklearn.metrics import mean_absolute_error


class HistoricalMargin:
    def __init__(self, margin=0.72):
        self.margin = margin

    def predict(self, frame):
        return np.maximum(frame["spend_90d"].to_numpy(dtype=float) * self.margin, 0)


class SeasonalNaive:
    def predict(self, frame):
        return np.maximum(frame["lag7"].to_numpy(dtype=float), 0)


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
    return {
        "selected": selected,
        "validation_mae": scores,
        "selection_split": "April–June 2025 validation; test untouched",
    }


def evaluate_quality(metrics):
    """Predeclared release acceptance criteria. Simulation-only checks are labelled as such."""
    checks = []
    for name in ["propensity", "churn", "attrition"]:
        m = metrics["customer"][name]["test_calibrated"]
        baseline_brier = m["prevalence"] * (1 - m["prevalence"])
        checks.append(
            {
                "model": name,
                "passed": bool(
                    m["roc_auc"] >= 0.70 and m["ece_10bins"] <= 0.10 and m["brier"] <= baseline_brier
                ),
                "criteria": "AUC >= 0.70, ECE <= 0.10, Brier no worse than constant prevalence",
                "value": m["roc_auc"],
                "reference": 0.70,
            }
        )
    clv = metrics["customer"]["clv"]["test"]
    checks.append(
        {
            "model": "contribution",
            "passed": bool(clv["mae"] <= clv["baseline_mae"] + 1e-8),
            "criteria": "Held-out MAE no worse than the historical-margin baseline",
            "value": clv["mae"],
            "reference": clv["baseline_mae"],
        }
    )
    demand = metrics["demand"]["test"]
    checks.append(
        {
            "model": "demand",
            "passed": bool(
                demand["mae"] <= demand["same_weekday_mean_mae"] + 1e-8
                and demand["interval_coverage_90"] >= 0.80
            ),
            "criteria": "30-day MAE no worse than the same-weekday baseline; 90% interval coverage >= 80%",
            "value": demand["mae"],
            "reference": demand["same_weekday_mean_mae"],
        }
    )
    uplift = metrics["uplift"]
    qini = [
        uplift[offer][uplift[offer]["selected"]]["qini"]
        for offer in uplift
        if isinstance(uplift[offer], dict) and "selected" in uplift[offer]
    ]
    checks.append(
        {
            "model": "uplift",
            "passed": bool(np.mean(qini) > 0),
            "criteria": "Mean held-out value Qini of the selected learners above zero (observed outcomes)",
            "value": float(np.mean(qini)),
            "reference": 0.0,
        }
    )
    policy = metrics.get("policy")
    if policy:
        share, beats = policy["share_of_oracle"], policy["beats_naive"]
        checks.append(
            {
                "model": "targeting policy (simulation check)",
                "passed": bool(share >= 0.60 and beats),
                "criteria": "Simulation only: the optimized plan captures >= 60% of the perfect-knowledge ceiling "
                "and beats every approach that uses no causal model",
                "value": share,
                "reference": 0.60,
            }
        )
    coverage = metrics["elasticity"]["elasticity_rmse_vs_truth"].get("ci_coverage")
    if coverage is not None:
        checks.append(
            {
                "model": "elasticity (simulation check)",
                "passed": bool(coverage >= 0.80),
                "criteria": "Simulation only: 95% intervals cover the true elasticity in >= 80% of cells",
                "value": coverage,
                "reference": 0.80,
            }
        )
    observable = [c for c in checks if "simulation" not in c["model"]]
    return {
        # Only evidence a real team could compute gates a release; simulation checks are reported alongside.
        "passed": all(c["passed"] for c in observable),
        "simulation_checks_passed": all(c["passed"] for c in checks if c not in observable),
        "checks": checks,
        "scope": "Synthetic local quality gate; a production population needs its own validation",
    }
