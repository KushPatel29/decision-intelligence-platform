import numpy as np
import pandas as pd
from scipy.stats import ks_2samp

from .config import write_json
from .features import FEATURES


def psi(reference, current):
    reference = np.asarray(reference, dtype=float)
    current = np.asarray(current, dtype=float)
    reference = reference[np.isfinite(reference)]
    current = current[np.isfinite(current)]
    if not len(reference) or not len(current):
        raise ValueError("PSI requires finite nonempty populations")
    edges = np.unique(np.quantile(reference, np.linspace(0, 1, 11)))
    if len(edges) < 3:
        center = float(np.median(reference))
        epsilon = max(abs(center) * 1e-6, 1e-6)
        edges = np.array([-np.inf, center - epsilon, center + epsilon, np.inf])
    edges[0] = -np.inf
    edges[-1] = np.inf
    a = np.histogram(reference, edges)[0] / len(reference)
    b = np.histogram(current, edges)[0] / len(current)
    a = np.maximum(a, 1e-6)
    b = np.maximum(b, 1e-6)
    return float(np.sum((b - a) * np.log(b / a)))


def monitor(cfg, snapshots, current, frames=None, trial=None):
    reference = snapshots[
        (snapshots.split == "train") & (snapshots.as_of == snapshots[snapshots.split.eq("train")].as_of.max())
    ]
    rows = []
    for feature in FEATURES:
        p = psi(reference[feature], current[feature])
        ks = ks_2samp(reference[feature], current[feature])
        rows.append(
            {
                "feature": feature,
                "psi": p,
                "ks_statistic": float(ks.statistic),
                "ks_p_value": float(ks.pvalue),
                "status": "Review" if p > 0.2 else "Stable",
            }
        )
    from .models import classifier_metrics

    performance = {}
    for name in ["propensity", "churn", "attrition"]:
        file = cfg.path("outputs", "performance", name + "_predictions.csv")
        if file.exists():
            frame = pd.read_csv(file)
            performance[name] = classifier_metrics(frame.target, frame.predicted_probability)
    predictions = []
    alerts = []
    for name in performance:
        baseline = pd.read_csv(
            cfg.path("outputs", "performance", name + "_predictions.csv")
        ).predicted_probability
        score = current[name + "_probability"].dropna()
        drift = psi(baseline, score)
        predictions.append(
            {
                "model": name,
                "psi": drift,
                "reference": "July held-out scores",
                "current": cfg.decision_date,
                "status": "Review" if drift > 0.2 else "Stable",
            }
        )
        if drift > 0.2:
            alerts.append(
                {
                    "category": "prediction_drift",
                    "key": name,
                    "severity": "review",
                    "value": drift,
                    "action": "Review population, calibration and matured labels; no automatic retraining",
                }
            )
    volumes = []
    data_quality = []
    if frames is not None:
        for name, key in [("fact_trip", "trip_id"), ("fact_digital_event", "event_id")]:
            frame = frames[name]
            data_quality.append(
                {
                    "table": name,
                    "rows": len(frame),
                    "null_key": int(frame[key].isna().sum()),
                    "duplicates": int(frame[key].duplicated().sum()),
                    "null_timestamp": int(frame.timestamp.isna().sum()),
                    "columns": list(frame.columns),
                }
            )
            daily = (
                frame[frame.timestamp < pd.Timestamp(cfg.decision_date)]
                .groupby(frame.timestamp.dt.normalize())
                .size()
            )
            recent = daily.tail(7)
            baseline = daily.iloc[-35:-7]
            center = float(baseline.median())
            mad = float(np.median(abs(baseline - center)))
            threshold = max(4 * 1.4826 * mad, 0.3 * max(center, 1))
            for day, count in recent.items():
                review = bool(abs(count - center) > threshold)
                volumes.append(
                    {
                        "table": name,
                        "date": str(day.date()),
                        "rows": int(count),
                        "historical_median": center,
                        "review": review,
                    }
                )
                if review:
                    alerts.append(
                        {
                            "category": "volume_change",
                            "key": name + ":" + str(day.date()),
                            "severity": "review",
                            "value": int(count),
                            "action": "Check calendar, upstream freshness and completeness",
                        }
                    )
    campaign = []
    if trial is not None:
        for arm, g in trial.groupby("arm"):
            campaign.append(
                {
                    "arm": arm,
                    "enrollment_rate": float(g.enrolled.mean()),
                    "conversion": float(g.response.mean()),
                    "redemption_rate": float(g.redeemed.mean()),
                    "net_contribution": float(g.net_contribution.sum()),
                    "rows": len(g),
                }
            )
        # Explicit operational thresholds, not learned fraud claims.
        for row in campaign:
            if row["redemption_rate"] > row["enrollment_rate"] + 1e-8 or row["conversion"] < 0.02:
                alerts.append(
                    {
                        "category": "campaign_rate",
                        "key": row["arm"],
                        "severity": "review",
                        "value": row["conversion"],
                        "action": "Inspect redemption linkage or conversion collapse before further contact",
                    }
                )
    for row in rows:
        if row["status"] == "Review":
            alerts.append(
                {
                    "category": "feature_drift",
                    "key": row["feature"],
                    "severity": "review",
                    "value": row["psi"],
                    "action": "Review drift with business context and matured performance",
                }
            )
    result = {
        "reference_as_of": str(reference.as_of.max()),
        "current_as_of": cfg.decision_date,
        "features": rows,
        "matured_july_performance": performance,
        "prediction_drift": predictions,
        "data_quality": data_quality,
        "volume_checks": volumes,
        "campaign_checks": campaign,
        "alerts": alerts,
        "review_count": sum(r["status"] == "Review" for r in rows),
        "threshold": 0.2,
        "interpretation": "Drift is a review signal; seasonality and changing tenure need context. July synthetic labels are mature by October and their discrimination/calibration is recorded. Current October performance awaits later labels. No automatic retraining based on PSI alone.",
    }
    write_json(cfg.path("outputs", "monitoring.json"), result)
    write_json(
        cfg.path("outputs", "alert_queue.json"),
        {
            "alerts": alerts,
            "review_required": bool(alerts),
            "workflow": "Triage → investigate upstream/model/business causes → approve retraining → validate untouched outcomes → reviewed promotion. Alerts do not automatically deploy models.",
            "scope": "Batch checks; live notifications and CloudWatch execution require hosted configuration",
        },
    )
    return result
