"""Customer models, pricing elasticity and demand forecasting.

Every model is chosen on a validation fold and judged once on an untouched test
fold. Where a simple baseline wins, the baseline serves and the loss is
recorded rather than tuned away.
"""

from __future__ import annotations

import os
import time
import warnings

import joblib
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor, IsolationForest
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.metrics import (
    adjusted_rand_score,
    average_precision_score,
    brier_score_loss,
    davies_bouldin_score,
    mean_absolute_error,
    roc_auc_score,
    root_mean_squared_error,
    silhouette_score,
)
from sklearn.mixture import GaussianMixture
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from .config import frame_hash, write_json
from .features import FEATURES
from .quality import HistoricalMargin, select_regression

SEGMENT_FEATURES = [
    "trips_90d",
    "spend_90d",
    "avg_distance_km",
    "peak_share",
    "weekend_share",
    "digital_events_30d",
    "recency_days",
]
ANOMALY_FEATURES = [
    "trips_7d",
    "trips_30d",
    "trips_90d",
    "night_share_30d",
    "zones_visited_30d",
    "max_daily_trips_30d",
    "active_days_30d",
    "spend_30d",
]


def classifier_metrics(y, score):
    y = np.asarray(y)
    score = np.asarray(score)
    if len(np.unique(y)) < 2:
        raise ValueError("Classification evaluation requires both target classes")
    bins = np.minimum((score * 10).astype(int), 9)
    ece = sum(
        (bins == b).mean() * abs(y[bins == b].mean() - score[bins == b].mean())
        for b in range(10)
        if (bins == b).any()
    )
    order = np.argsort(-score, kind="stable")

    def lift(fraction):
        return float(y[order[: max(1, int(len(y) * fraction))]].mean() / y.mean())

    return {
        "roc_auc": float(roc_auc_score(y, score)),
        "pr_auc": float(average_precision_score(y, score)),
        "brier": float(brier_score_loss(y, score)),
        "ece_10bins": float(ece),
        "lift_at_10": lift(0.1),
        "lift_at_20": lift(0.2),
        "n": len(y),
        "prevalence": float(y.mean()),
    }


def reg_metrics(y, pred):
    return {
        "mae": float(mean_absolute_error(y, pred)),
        "rmse": float(root_mean_squared_error(y, pred)),
        "n": len(y),
    }


def log_experiment(cfg, name, model, metrics, params, tracking, artifact=None):
    """Persist a model locally and, when enabled, as an MLflow run with lineage tags."""
    folder = cfg.path("outputs", "models")
    folder.mkdir(parents=True, exist_ok=True)
    if model is not None:
        artifact = folder / f"{name}.joblib"
        joblib.dump(model, artifact, compress=3)
    write_json(folder / f"{name}.metrics.json", {"metrics": metrics, "parameters": params})
    if not tracking:
        return
    try:
        import mlflow

        # A local SQLite store by default; on Databricks the job sets MLFLOW_TRACKING_URI=databricks
        # and a workspace experiment path, and the same runs land in the workspace tracking server.
        local = "sqlite:///" + str(cfg.path("outputs", "mlflow.db")).replace("\\", "/")
        mlflow.set_tracking_uri(os.environ.get("MLFLOW_TRACKING_URI") or local)
        mlflow.set_experiment(
            os.environ.get("CORRIDOR_MLFLOW_EXPERIMENT", "transportation-decision-intelligence")
        )
        with mlflow.start_run(run_name=name) as run:
            mlflow.log_params({k: str(v)[:250] for k, v in params.items()})
            mlflow.log_metrics({k: float(v) for k, v in metrics.items() if isinstance(v, int | float)})
            mlflow.set_tags(
                {
                    "data_kind": "synthetic",
                    "feature_version": "2.0",
                    "artifact_status": os.environ.get("CORRIDOR_ARTIFACT_STATUS", "local-candidate"),
                }
            )
            if artifact is not None:
                mlflow.log_artifact(str(artifact), artifact_path="models")
            mlflow.log_artifact(str(folder / f"{name}.metrics.json"))
            if cfg.path("outputs", "manifest.json").exists():
                mlflow.log_artifact(str(cfg.path("outputs", "manifest.json")))
            write_json(folder / f"{name}.tracking.json", {"status": "tracked", "run_id": run.info.run_id})
    except Exception as exc:  # Tracking is optional; local artifacts are complete either way.
        write_json(folder / f"{name}.tracking.json", {"status": "failed", "error": str(exc)})


class CalibratedClassifier:
    """A fitted classifier plus a Platt calibrator fitted on a separate fold."""

    def __init__(self, model, calibrator, features):
        self.model, self.calibrator, self.features = model, calibrator, features

    def predict_proba(self, frame):
        raw = np.clip(self.model.predict_proba(frame[self.features])[:, 1], 1e-5, 1 - 1e-5)
        logit = np.log(raw / (1 - raw)).reshape(-1, 1)
        return self.calibrator.predict_proba(logit)[:, 1]


def _classifier_candidates(seed):
    candidates = {
        "logistic": make_pipeline(
            StandardScaler(), LogisticRegression(max_iter=2000, C=0.5, random_state=seed)
        ),
        "hist_gradient_boosting": HistGradientBoostingClassifier(
            max_iter=120, max_leaf_nodes=15, min_samples_leaf=40, l2_regularization=3, random_state=seed
        ),
    }
    try:
        from xgboost import XGBClassifier

        candidates["xgboost"] = XGBClassifier(
            n_estimators=200,
            max_depth=4,
            learning_rate=0.06,
            subsample=0.85,
            colsample_bytree=0.8,
            min_child_weight=8,
            reg_lambda=2.0,
            n_jobs=1,
            random_state=seed,
            eval_metric="logloss",
        )
    except ImportError:
        pass
    return candidates


def fit_customer_models(cfg, snapshots, current, tracking=True):
    result, scored = {}, current.copy()
    train = snapshots[snapshots.split.eq("train")]
    val = snapshots[snapshots.split.eq("validation")]
    test = snapshots[snapshots.split.eq("test")]
    cfg.path("outputs", "performance").mkdir(parents=True, exist_ok=True)
    for name in ["propensity", "churn", "attrition"]:
        target = "target_" + name
        tr, va, te = train, val, test
        if name != "propensity":
            tr, va, te = (
                train[train.historically_active],
                val[val.historically_active],
                test[test.historically_active],
            )
        leaderboard, started = {}, time.perf_counter()
        candidates = _classifier_candidates(cfg.seed)
        for algorithm, model in candidates.items():
            model.fit(tr[FEATURES], tr[target])
            leaderboard[algorithm] = classifier_metrics(va[target], model.predict_proba(va[FEATURES])[:, 1])
        # Brier score rewards calibrated probabilities, which decisions consume directly.
        champion = min(leaderboard, key=lambda k: leaderboard[k]["brier"])
        model = candidates[champion]
        raw = np.clip(model.predict_proba(va[FEATURES])[:, 1], 1e-5, 1 - 1e-5)
        calibrator = LogisticRegression(C=1.0, random_state=cfg.seed).fit(
            np.log(raw / (1 - raw)).reshape(-1, 1), va[target]
        )
        calibrated = CalibratedClassifier(model, calibrator, FEATURES)
        metrics = classifier_metrics(te[target], calibrated.predict_proba(te))
        pd.DataFrame(
            {
                "customer_id": te.customer_id,
                "as_of": te.as_of,
                "target": te[target],
                "predicted_probability": calibrated.predict_proba(te),
            }
        ).to_csv(cfg.path("outputs", "performance", name + "_predictions.csv"), index=False)
        metrics["training_seconds"] = time.perf_counter() - started
        result[name] = {
            "champion": champion,
            "validation_uncalibrated": leaderboard,
            "test_calibrated": metrics,
            "calibration_population": "Separate April 2025 validation fold; test is July 2025",
            "population": "historically active (>=3 trips / prior 90 days)"
            if name != "propensity"
            else "all customers",
        }
        scored[name + "_probability"] = calibrated.predict_proba(current)
        if name != "propensity":
            scored.loc[scored.trips_90d < 3, name + "_probability"] = np.nan
        log_experiment(
            cfg,
            name,
            {"model": model, "calibrator": calibrator, "features": FEATURES},
            metrics,
            {
                "algorithm": champion,
                "seed": cfg.seed,
                "dataset_sha256": frame_hash(snapshots),
                "feature_version": "2.0",
            },
            tracking,
        )
        print(f"  {name}: {champion} test AUC {metrics['roc_auc']:.3f}", flush=True)

    scored, result["clv"] = _contribution(cfg, train, val, test, current, scored, tracking)
    scored, result["segmentation"] = _segments(cfg, train, current, scored)
    scored, result["anomaly"] = _anomalies(cfg, train, current, scored)
    return scored, result


def _contribution(cfg, train, val, test, current, scored, tracking):
    forecast = HistGradientBoostingRegressor(
        loss="poisson", max_iter=150, max_leaf_nodes=15, l2_regularization=3, random_state=cfg.seed
    ).fit(train[FEATURES], train.future_margin_90d)
    baseline = HistoricalMargin(cfg.contribution_margin)
    selection = select_regression(
        val.future_margin_90d,
        {
            "hist_gradient_boosting": forecast.predict(val[FEATURES]),
            "historical_margin": baseline.predict(val[FEATURES]),
        },
    )
    selected = forecast if selection["selected"] == "hist_gradient_boosting" else baseline
    pred = np.maximum(selected.predict(test[FEATURES]), 0)
    metrics = reg_metrics(test.future_margin_90d, pred)
    metrics["baseline_mae"] = float(
        mean_absolute_error(test.future_margin_90d, baseline.predict(test[FEATURES]))
    )
    first = np.maximum(selected.predict(current[FEATURES]), 0)
    retention = 1 - scored.churn_probability.fillna(0.5).to_numpy()
    scored["expected_margin_90d"] = first
    scored["clv_12m"] = sum(first * retention ** (q - 1) / 1.10 ** (q / 4) for q in range(1, 5))
    log_experiment(
        cfg, "clv", selected, metrics, {"algorithm": selection["selected"], "seed": cfg.seed}, tracking
    )
    return scored, {
        "test": metrics,
        "selection": selection,
        "champion": selection["selected"],
        "method": "Validation-selected 90-day contribution forecast projected four quarters with churn-based "
        "survival decay and a 10% annual discount rate. A heuristic projection, not validated 12-month CLV.",
    }


def _segments(cfg, train, current, scored):
    """Rule-based RFM segments plus K-Means and Gaussian-mixture behavioural clusters."""
    reference = train[train.as_of.eq(train.as_of.max())]
    scaler = StandardScaler().fit(np.log1p(reference[SEGMENT_FEATURES]))
    scaled = scaler.transform(np.log1p(reference[SEGMENT_FEATURES]))
    current_scaled = scaler.transform(np.log1p(current[SEGMENT_FEATURES]))
    kmeans = KMeans(n_clusters=5, n_init=10, random_state=cfg.seed).fit(scaled)
    bics = {}
    for k in range(3, 9):
        bics[k] = float(
            GaussianMixture(k, covariance_type="full", random_state=cfg.seed).fit(scaled).bic(scaled)
        )
    best_k = min(bics, key=bics.get)
    gmm = GaussianMixture(best_k, covariance_type="full", random_state=cfg.seed).fit(scaled)
    scored["cluster"] = kmeans.predict(current_scaled)
    scored["gmm_cluster"] = gmm.predict(current_scaled)
    scored["gmm_confidence"] = gmm.predict_proba(current_scaled).max(axis=1)
    scored["rfm_segment"] = np.select(
        [
            scored.recency_days > 90,
            (scored.recency_days > 30) & (scored.trips_previous90d >= 3),
            scored.trips_90d >= 25,
            scored.trips_90d >= 8,
            scored.tenure_days < 180,
        ],
        ["Dormant", "At risk", "Champions", "Loyal", "New"],
        default="Occasional",
    )
    rng = np.random.default_rng(cfg.seed)
    stability = []
    for b in range(5):
        idx = rng.integers(len(scaled), size=len(scaled))
        boot = KMeans(n_clusters=5, n_init=5, random_state=cfg.seed + b + 1).fit(scaled[idx])
        stability.append(float(adjusted_rand_score(kmeans.labels_, boot.predict(scaled))))
    sample = rng.choice(len(scaled), min(3000, len(scaled)), replace=False)
    metrics = {
        "kmeans": {
            "clusters": 5,
            "silhouette": float(
                silhouette_score(scaled[sample], kmeans.labels_[sample], random_state=cfg.seed)
            ),
            "davies_bouldin": float(davies_bouldin_score(scaled, kmeans.labels_)),
            "bootstrap_adjusted_rand": stability,
        },
        "gmm": {
            "clusters": best_k,
            "bic_by_k": bics,
            "silhouette": float(
                silhouette_score(scaled[sample], gmm.predict(scaled)[sample], random_state=cfg.seed)
            ),
            "mean_assignment_confidence": float(scored.gmm_confidence.mean()),
        },
        "agreement": {
            "kmeans_vs_gmm_ari": float(adjusted_rand_score(scored.cluster, scored.gmm_cluster)),
            "kmeans_vs_rfm_ari": float(adjusted_rand_score(scored.cluster, scored.rfm_segment)),
        },
        "fit_as_of": str(reference.as_of.max()),
    }
    joblib.dump(
        {"scaler": scaler, "model": kmeans, "gmm": gmm, "features": SEGMENT_FEATURES},
        cfg.path("outputs", "models", "segmentation.joblib"),
        compress=3,
    )
    return scored, metrics


def _robust_z(reference, current):
    median = np.median(reference, axis=0)
    mad = np.median(np.abs(reference - median), axis=0) * 1.4826
    return np.abs(current - median) / np.where(mad > 0, mad, np.std(reference, axis=0) + 1e-9)


def _anomalies(cfg, train, current, scored):
    """Isolation Forest review flags, scored against the planted anomalies."""
    reference = train[train.as_of.eq(train.as_of.max())]
    transform = StandardScaler().fit(np.log1p(reference[ANOMALY_FEATURES]))
    ref = transform.transform(np.log1p(reference[ANOMALY_FEATURES]))
    cur = transform.transform(np.log1p(current[ANOMALY_FEATURES]))
    forest = IsolationForest(n_estimators=300, contamination="auto", random_state=cfg.seed).fit(ref)
    scored["anomaly_score"] = -forest.score_samples(cur)
    review_rate = 0.005  # Review capacity: the top 0.5% of accounts each month.
    threshold = np.quantile(scored.anomaly_score, 1 - review_rate)
    scored["anomaly_flag"] = scored.anomaly_score >= threshold
    z = _robust_z(ref, cur).max(axis=1)
    z_flag = z >= np.quantile(z, 1 - review_rate)
    planted_path = cfg.path("data", "simulation_audit", "planted_anomalies.parquet")
    evaluation = {}
    if planted_path.exists():
        planted = set(pd.read_parquet(planted_path).customer_id)
        truth = scored.customer_id.isin(planted).to_numpy()
        for method, flags, score in [
            ("isolation_forest", scored.anomaly_flag.to_numpy(), scored.anomaly_score.to_numpy()),
            ("robust_z_score", z_flag, z),
        ]:
            hits = int((flags & truth).sum())
            evaluation[method] = {
                "flagged": int(flags.sum()),
                "planted": int(truth.sum()),
                "caught": hits,
                "precision": hits / max(int(flags.sum()), 1),
                "recall": hits / max(int(truth.sum()), 1),
                "pr_auc": float(average_precision_score(truth, score)),
            }
    joblib.dump(
        {"scaler": transform, "model": forest, "features": ANOMALY_FEATURES},
        cfg.path("outputs", "models", "anomaly.joblib"),
        compress=3,
    )
    return scored, {
        "flagged": int(scored.anomaly_flag.sum()),
        "review_rate": review_rate,
        "evaluation_against_planted": evaluation,
        "method": "Isolation Forest on log-scaled velocity, night-travel and zone-spread features with a "
        "fixed review capacity; a robust z-score detector is the baseline. Review signal, not fraud adjudication.",
    }


def fit_elasticity(cfg, pricing, tracking=True):
    """Cell-level log-log elasticities with empirical-Bayes shrinkage, checked against the truth."""
    controls = ["temperature_c", "precipitation_mm", "weekend", "holiday", "month_sin", "month_cos"]
    frame = pricing.copy()
    frame["log_price"] = np.log(frame.effective_price)
    frame["log_demand"] = np.log(np.maximum(frame.demand, 1))
    train = frame[frame.date < "2025-07-01"]
    test = frame[(frame.date >= "2025-07-01") & (frame.date < "2025-10-01")]
    rows, models = [], {}
    for (zone, period, segment), group in train.groupby(["zone_id", "period", "segment"]):
        x = group[["log_price", *controls]].to_numpy(float)
        y = group.log_demand.to_numpy()
        model = LinearRegression().fit(x, y)
        residual = y - model.predict(x)
        design = np.column_stack([np.ones(len(x)), x])
        sigma2 = residual @ residual / max(len(y) - design.shape[1], 1)
        cov = sigma2 * np.linalg.pinv(design.T @ design)
        held = test[(test.zone_id == zone) & (test.period == period) & (test.segment == segment)]
        pred = np.exp(model.predict(held[["log_price", *controls]].to_numpy(float)))
        rows.append(
            {
                "zone_id": int(zone),
                "period": period,
                "segment": segment,
                "ols_elasticity": float(model.coef_[0]),
                "ols_se": float(np.sqrt(cov[1, 1])),
                **reg_metrics(held.demand, pred),
            }
        )
        models[f"{zone}:{period}:{segment}"] = model
    cells = pd.DataFrame(rows)
    # Empirical Bayes: shrink each cell toward its period x segment mean by its noise.
    parts = []
    for _, group in cells.groupby(["period", "segment"]):
        prior = float(np.average(group.ols_elasticity, weights=1 / group.ols_se**2))
        tau2 = max(float(group.ols_elasticity.var(ddof=1) - (group.ols_se**2).mean()), 1e-4)
        weight = tau2 / (tau2 + group.ols_se**2)
        parts.append(
            group.assign(
                prior_mean=prior,
                shrinkage_weight=weight,
                elasticity=weight * group.ols_elasticity + (1 - weight) * prior,
                elasticity_se=np.sqrt(weight) * group.ols_se,
            )
        )
    cells = pd.concat(parts).sort_values(["zone_id", "period", "segment"]).reset_index(drop=True)
    cells["ci_low"] = cells.elasticity - 1.96 * cells.elasticity_se
    cells["ci_high"] = cells.elasticity + 1.96 * cells.elasticity_se
    pooled = (
        train.groupby(["period", "segment"])
        .apply(
            lambda g: LinearRegression().fit(g[["log_price", *controls]], g.log_demand).coef_[0],
            include_groups=False,
        )
        .rename("pooled_elasticity")
        .reset_index()
    )
    cells = cells.merge(pooled, on=["period", "segment"], validate="many_to_one")
    boosted = HistGradientBoostingRegressor(
        max_iter=200,
        max_leaf_nodes=20,
        monotonic_cst=[-1] + [0] * (len(controls) + 3),
        random_state=cfg.seed,
    )
    code = {"Peak": 0, "Off-peak": 1, "Weekend": 2}
    gb_x = lambda f: np.column_stack(  # noqa: E731
        [f.log_price, f[controls], f.zone_id, f.period.map(code), f.segment.eq("Business")]
    )
    boosted.fit(gb_x(train), train.log_demand)
    gb = []
    for _, row in cells.iterrows():
        group = test[
            (test.zone_id == row.zone_id) & (test.period == row.period) & (test.segment == row.segment)
        ]
        up, down = group.copy(), group.copy()
        up["log_price"] += 0.05
        down["log_price"] -= 0.05
        gb.append(float(np.mean(boosted.predict(gb_x(up)) - boosted.predict(gb_x(down))) / 0.10))
    cells["boosting_elasticity"] = gb
    truth_path = cfg.path("data", "simulation_audit", "true_elasticity.parquet")
    recovery = {}
    if truth_path.exists():
        truth = pd.read_parquet(truth_path)
        merged = cells.merge(truth, on=["zone_id", "period", "segment"], validate="one_to_one")
        for method in ["ols_elasticity", "elasticity", "pooled_elasticity", "boosting_elasticity"]:
            recovery[method] = float(np.sqrt(((merged[method] - merged.true_elasticity) ** 2).mean()))
        recovery["ci_coverage"] = float(
            ((merged.true_elasticity >= merged.ci_low) & (merged.true_elasticity <= merged.ci_high)).mean()
        )
    gb_pred = np.exp(boosted.predict(gb_x(test)))
    metrics = {
        "cell_ols_test_mae": float(cells.mae.mean()),
        "boosting_test_mae": float(mean_absolute_error(test.demand, gb_pred)),
        "elasticity_rmse_vs_truth": recovery,
        "selected": "elasticity (empirical Bayes)",
        "identification": "Independently randomised synthetic price assignments by day, zone, period and segment",
    }
    log_experiment(
        cfg,
        "elasticity",
        {"models": models, "features": ["log_price", *controls], "cells": cells},
        {"mean_test_mae": metrics["cell_ols_test_mae"]},
        {"identification": "randomised synthetic price tests", "seed": cfg.seed},
        tracking,
    )
    cells.to_csv(cfg.path("outputs", "elasticity.csv"), index=False)
    write_json(cfg.path("outputs", "elasticity_metrics.json"), metrics)

    # Decision cells are zone x period: weight segments by their historical traffic share.
    weights = pricing.groupby(["zone_id", "period", "segment"]).demand.sum().rename("weight").reset_index()
    blended = cells.merge(weights, on=["zone_id", "period", "segment"])
    zone_period = (
        blended.groupby(["zone_id", "period"])
        .apply(
            lambda g: pd.Series(
                {
                    "elasticity": np.average(g.elasticity, weights=g.weight),
                    "elasticity_se": np.sqrt(np.average(g.elasticity_se**2, weights=g.weight)),
                }
            ),
            include_groups=False,
        )
        .reset_index()
    )
    scenarios = []
    for _, row in zone_period.iterrows():
        for change in [-0.30, -0.20, -0.10, 0, 0.05, 0.10]:
            ratio = (1 + change) ** row.elasticity
            low = (1 + change) ** (row.elasticity - 1.96 * row.elasticity_se)
            high = (1 + change) ** (row.elasticity + 1.96 * row.elasticity_se)
            scenarios.append(
                {
                    "zone_id": int(row.zone_id),
                    "period": row.period,
                    "price_change": change,
                    "demand_index": 100 * ratio,
                    "demand_index_low": 100 * min(low, high),
                    "demand_index_high": 100 * max(low, high),
                    "revenue_index": 100 * ratio * (1 + change),
                    "elasticity": row.elasticity,
                    "elasticity_se": row.elasticity_se,
                }
            )
    scenarios = pd.DataFrame(scenarios)
    scenarios.to_csv(cfg.path("outputs", "pricing_scenarios.csv"), index=False)
    return cells, scenarios, metrics


# Planning capacity as a multiple of each cell's pre-decision 95th-percentile day.
# The central peak cells are deliberately tight: that is where the network has
# no room, and where a promotion that adds peak trips should be refused.
CAPACITY_FACTORS = {
    "Peak": {0: 1.0, 1: 0.85, 2: 0.85, 3: 0.85, 4: 1.0, 5: 1.0},
    "Off-peak": 1.3,
    "Weekend": 1.3,
}


def _capacity_factor(zone, period):
    factor = CAPACITY_FACTORS[period]
    return factor[zone] if isinstance(factor, dict) else factor


def fit_demand(cfg, trips, context, tracking=True):
    from .forecasting import bounds, daily_cells, horizon_dataset, hourly_forecast, interval_radius

    frame = daily_cells(cfg, trips, context)
    data = horizon_dataset(frame, context)
    inputs = [
        "zone_id",
        "period_code",
        "dow",
        "horizon",
        "holiday",
        "month_sin",
        "month_cos",
        "log_sdw4",
        "log_rolling28",
        "trend",
    ]
    tr = data[data.origin < pd.Timestamp("2025-03-02")]
    va = data[(data.origin >= pd.Timestamp("2025-04-01")) & (data.origin < pd.Timestamp("2025-06-02"))]
    te = data[(data.origin >= pd.Timestamp("2025-07-01")) & (data.origin < pd.Timestamp("2025-09-02"))]
    model = HistGradientBoostingRegressor(
        max_iter=250, learning_rate=0.05, max_leaf_nodes=20, l2_regularization=2, random_state=cfg.seed
    ).fit(tr[inputs], tr.log_ratio)

    def predict(rows):
        return np.maximum(np.expm1(np.log1p(rows.sdw4) + model.predict(rows[inputs])), 0)

    candidates = {
        "ratio_boosting": predict(va),
        "same_weekday_mean": va.sdw4.to_numpy(),
        "seasonal_naive": va.lag7.to_numpy(),
    }
    selection = select_regression(va.trips, candidates)
    baseline_test = reg_metrics(te.trips, te.sdw4)
    candidate_test = reg_metrics(te.trips, predict(te))
    serving = selection["selected"]
    # Predeclared acceptance gate: the learned model must also beat the strongest naive baseline on test.
    if serving == "ratio_boosting" and candidate_test["mae"] > baseline_test["mae"]:
        serving = "same_weekday_mean"
        selection["promotion_gate"] = "Rejected: held-out error exceeds the same-weekday baseline."
    elif serving == "ratio_boosting":
        selection["promotion_gate"] = "Accepted: beats the same-weekday baseline on validation and test."
    forecaster = {
        "ratio_boosting": predict,
        "same_weekday_mean": lambda rows: rows.sdw4.to_numpy(),
        "seasonal_naive": lambda rows: rows.lag7.to_numpy(),
    }[serving]
    radius = interval_radius(va, forecaster(va))
    test_pred = forecaster(te)
    metrics = reg_metrics(te.trips, test_pred)
    metrics["same_weekday_mean_mae"] = baseline_test["mae"]
    metrics["seasonal_naive_mae"] = float(mean_absolute_error(te.trips, te.lag7))
    metrics["candidate_test"] = candidate_test
    lower, upper = bounds(test_pred, te.period, radius)
    metrics["interval_coverage_90"] = float(((te.trips >= lower) & (te.trips <= upper)).mean())
    metrics["horizon_days"] = 30
    metrics["test_origins"] = int(te.origin.nunique())
    log_experiment(
        cfg,
        "demand",
        {"model": model, "features": inputs, "selected": serving, "interval_radius": radius},
        {k: v for k, v in metrics.items() if not isinstance(v, dict)},
        {"horizon": "30-day fixed origin", "seed": cfg.seed, "serving_algorithm": serving},
        tracking,
    )
    pd.DataFrame(
        {
            "origin": te.origin,
            "date": te.date,
            "zone_id": te.zone_id,
            "period": te.period,
            "trips": te.trips,
            "prediction": test_pred,
            "lower_90": lower,
            "upper_90": upper,
        }
    ).to_csv(cfg.path("outputs", "demand_horizon_backtest.csv"), index=False)

    decision = pd.Timestamp(cfg.decision_date)
    future = horizon_dataset(frame, context, origins=[decision])
    if serving == "ratio_boosting":
        # Selection and acceptance are done; refit on every origin whose targets end before the decision date.
        history = data[data.date < decision]
        final = HistGradientBoostingRegressor(
            max_iter=250, learning_rate=0.05, max_leaf_nodes=20, l2_regularization=2, random_state=cfg.seed
        ).fit(history[inputs], history.log_ratio)
        future["baseline_forecast"] = np.maximum(
            np.expm1(np.log1p(future.sdw4) + final.predict(future[inputs])), 0
        )
        metrics["refit_rows"] = int(len(history))
        # The registry should hold the model that produced the plan's forecast, not the selection-time fit.
        joblib.dump(
            {
                "model": final,
                "features": inputs,
                "selected": serving,
                "interval_radius": radius,
                "refit": True,
            },
            cfg.path("outputs", "models", "demand.joblib"),
            compress=3,
        )
    else:
        future["baseline_forecast"] = forecaster(future)
    future["forecast_low"], future["forecast_high"] = bounds(future.baseline_forecast, future.period, radius)
    future.to_csv(cfg.path("outputs", "decision_forecast.csv"), index=False)
    history = frame[(frame.date < decision) & (frame.date >= decision - pd.Timedelta(days=180))]
    # A period only runs on its own days (peak/off-peak on weekdays, weekend on weekends): ignore structural zeros.
    weekend_day = history.date.dt.dayofweek >= 5
    operating = history[history.period.eq("Weekend") == weekend_day]
    caps = operating.groupby(["zone_id", "period"]).trips.quantile(0.95).rename("p95_daily").reset_index()
    caps["daily_capacity"] = [
        np.ceil(row.p95_daily * _capacity_factor(int(row.zone_id), row.period)) for row in caps.itertuples()
    ]
    cell = (
        future.groupby(["zone_id", "period"])
        .agg(baseline_forecast=("baseline_forecast", "sum"), forecast_high=("forecast_high", "sum"))
        .reset_index()
        .merge(caps, on=["zone_id", "period"], validate="one_to_one")
    )
    days = future.groupby(["zone_id", "period"]).date.nunique().rename("operating_days").reset_index()
    cell = cell.merge(days, on=["zone_id", "period"], validate="one_to_one")
    cell["capacity_trips"] = cell.daily_capacity * cell.operating_days
    cell["reserve_trips"] = 0.2 * cell.baseline_forecast
    cell["available_trips"] = np.maximum(cell.capacity_trips - cell.baseline_forecast - cell.reserve_trips, 0)
    cell["baseline_over_capacity"] = (cell.baseline_forecast + cell.reserve_trips) > cell.capacity_trips
    cell.to_csv(cfg.path("outputs", "capacity.csv"), index=False)
    frame.to_parquet(cfg.path("data", "gold", "zone_day.parquet"), index=False)
    hourly_forecast(cfg, trips, future)
    return cell, {
        "test": metrics,
        "selection": selection,
        "champion": serving,
        "interval_radius": radius,
        "decision_forecast": "30-day fixed-origin forecast from the validation-selected champion, with split-conformal "
        "90% intervals from validation residuals. Weather enters as monthly climatology, not a weather forecast.",
        "reserve_fraction": 0.20,
    }


warnings.filterwarnings("ignore", message=".*does not have valid feature names.*")
