"""Batch monitoring: feature/prediction drift, matured performance, feed quality and campaigns.

Every check is a review signal with an owner action, never an automatic retrain.
The feed-quality monitor is calendar- and weather-aware and is scored against
the defects planted in the bronze feed.
"""

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


def data_quality_monitor(cfg, context):
    """Daily bronze-feed profile with robust anomaly scores, scored against planted defects.

    Volume is compared with the median of the same weekday over the previous four
    weeks; a regression fitted on pre-June history explains the part of the
    change due to rain and public holidays. Rate checks (duplicate natural keys,
    out-of-range values, nulls) use robust z-scores against a trailing window.
    """
    feed = pd.read_parquet(
        cfg.path("data", "bronze", "fact_trip.parquet"),
        columns=[
            "customer_id",
            "timestamp",
            "entry_zone",
            "exit_zone",
            "toll",
            "distance_km",
            "final_charge",
            "ingested_at",
        ],
    )
    feed["day"] = feed.ingested_at.dt.normalize()
    key = ["customer_id", "timestamp", "entry_zone", "exit_zone", "toll"]
    feed["duplicate"] = feed.duplicated(key, keep="first")
    feed["out_of_range"] = (
        ~feed.distance_km.between(0.5, 120) | ~feed.toll.between(0, 150) | (feed.final_charge < 0)
    )
    feed["null_key"] = feed[["customer_id", "timestamp"]].isna().any(axis=1)
    daily = (
        feed.groupby("day")
        .agg(
            rows=("customer_id", "size"),
            duplicate_rate=("duplicate", "mean"),
            out_of_range_rate=("out_of_range", "mean"),
            null_rate=("null_key", "mean"),
        )
        .reindex(
            pd.date_range(cfg.start, pd.Timestamp(cfg.decision_date) - pd.Timedelta(days=1)), fill_value=0
        )
        .rename_axis("day")
        .reset_index()
    )
    daily = daily.merge(
        context[["date", "precipitation_mm", "holiday"]], left_on="day", right_on="date", how="left"
    ).drop(columns="date")
    reference = np.full(len(daily), np.nan)
    rows = daily.rows.to_numpy(float)
    for i in range(28, len(daily)):
        reference[i] = np.median(rows[[i - 7, i - 14, i - 21, i - 28]])
    daily["expected_rows"] = reference
    daily["log_ratio"] = np.log((daily.rows + 1) / (daily.expected_rows + 1))
    train = daily[(daily.day < "2025-06-01") & daily.expected_rows.notna()]
    design = lambda f: np.column_stack([np.ones(len(f)), f.precipitation_mm, f.holiday])  # noqa: E731
    coef, *_ = np.linalg.lstsq(design(train), train.log_ratio, rcond=None)
    daily["explained"] = design(daily) @ coef
    daily["residual"] = daily.log_ratio - daily.explained
    scale = 1.4826 * np.median(
        np.abs(train.log_ratio - design(train) @ coef - np.median(train.log_ratio - design(train) @ coef))
    )
    daily["volume_z"] = daily.residual / max(scale, 1e-6)
    for metric in ["duplicate_rate", "out_of_range_rate", "null_rate"]:
        history = daily[metric].shift(1).rolling(56, min_periods=28)
        median = history.median()
        mad = (daily[metric].shift(1) - median).abs().rolling(56, min_periods=28).median() * 1.4826
        daily[metric + "_z"] = (daily[metric] - median) / np.maximum(mad, 0.002)
    window = daily[(daily.day >= "2025-06-01")].copy()
    window["flag_volume"] = window.volume_z.abs() >= 4
    window["flag_rates"] = (window[["duplicate_rate_z", "out_of_range_rate_z", "null_rate_z"]] >= 6).any(
        axis=1
    )
    window["flagged"] = window.flag_volume | window.flag_rates
    window["reason"] = np.select(
        [window.flag_rates & (window.duplicate_rate_z >= 6), window.flag_rates, window.flag_volume],
        ["duplicate natural keys", "out-of-range values", "volume vs same weekday"],
        default="",
    )
    planted_path = cfg.path("data", "simulation_audit", "planted_data_defects.parquet")
    evaluation = {}
    if planted_path.exists():
        planted = set(pd.to_datetime(pd.read_parquet(planted_path).ingestion_date))
        truth = window.day.isin(planted)
        hits = int((window.flagged & truth).sum())
        evaluation = {
            "monitored_days": len(window),
            "planted_defect_days": int(truth.sum()),
            "flagged_days": int(window.flagged.sum()),
            "caught": hits,
            "precision": hits / max(int(window.flagged.sum()), 1),
            "recall": hits / max(int(truth.sum()), 1),
            "false_alarm_days": int((window.flagged & ~truth).sum()),
        }
    window.to_csv(cfg.path("outputs", "data_quality_daily.csv"), index=False)
    result = {
        "method": "Same-weekday volume ratio with a rain/holiday adjustment fitted before June 2025; robust "
        "z-scores for duplicate, out-of-range and null rates. Flags: |volume z| >= 4 or rate z >= 6.",
        "weather_coefficient": float(coef[1]),
        "holiday_coefficient": float(coef[2]),
        "evaluation_against_planted": evaluation,
        "flags": window.loc[window.flagged, ["day", "rows", "expected_rows", "volume_z", "reason"]].to_dict(
            orient="records"
        ),
    }
    write_json(cfg.path("outputs", "data_quality_monitor.json"), result)
    return result
