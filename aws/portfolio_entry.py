"""SageMaker six-family training/evaluation/inference contract, locally executable."""

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.metrics import brier_score_loss, mean_absolute_error, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

TASKS = {"propensity", "churn", "attrition", "uplift", "elasticity", "demand"}


def validate(frame, contract, labelled=True):
    features = contract["features"]
    allowed = features + ([contract["target"]] if labelled else [])
    if set(frame.columns) != set(allowed):
        raise ValueError("Cloud channel schema mismatch")
    if any(f.startswith(("latent_", "true_", "future_", "target_")) for f in features):
        raise ValueError("Forbidden predictor")
    if not len(frame) or not np.isfinite(frame[allowed].to_numpy(dtype=float)).all():
        raise ValueError("Cloud channel must be finite and nonempty")
    return frame


def predictions(bundle, frame):
    frame = frame.copy()
    features = bundle["contract"]["features"]
    task = bundle["contract"]["task"]
    validate(frame, bundle["contract"], labelled=False)
    if task in {"propensity", "churn", "attrition"}:
        raw = np.clip(bundle["model"].predict_proba(frame[features])[:, 1], 1e-6, 1 - 1e-6)
        return bundle["calibrator"].predict_proba(np.log(raw / (1 - raw)).reshape(-1, 1))[:, 1]
    if task == "uplift":
        base = frame.copy()
        base["assigned_arm"] = 0
        p0 = bundle["model"].predict_proba(base[features])[:, 1]
        scores = []
        for arm in [1, 2, 3]:
            other = frame.copy()
            other["assigned_arm"] = arm
            scores.append(bundle["model"].predict_proba(other[features])[:, 1] - p0)
        return np.column_stack(scores)
    if bundle.get("selected") == "seasonal_naive":
        return frame.lag7.to_numpy()
    result = bundle["model"].predict(frame[features])
    return np.maximum(np.exp(result) if task == "elasticity" else result, 0)


def evaluate_bundle(bundle, test):
    contract = bundle["contract"]
    task = contract["task"]
    features = contract["features"]
    validate(test, contract)
    y = test[contract["target"]].to_numpy()
    pred = predictions(bundle, test[features])
    if task in {"propensity", "churn", "attrition"}:
        if len(np.unique(y)) != 2:
            raise ValueError("Two classes required for cloud evaluation")
        auc = float(roc_auc_score(y, pred))
        brier = float(brier_score_loss(y, pred))
        baseline = float(y.mean() * (1 - y.mean()))
        bins = np.minimum((pred * 10).astype(int), 9)
        ece = float(
            sum(
                (bins == b).mean() * abs(y[bins == b].mean() - pred[bins == b].mean())
                for b in range(10)
                if (bins == b).any()
            )
        )
        quality = auc >= 0.70 and brier <= baseline and ece <= 0.10
        metrics = {"auc": auc, "brier": brier, "baseline_brier": baseline, "ece": ece}
    elif task == "uplift":
        gains = []
        for arm in [1, 2, 3]:
            mask = test.assigned_arm.isin([0, arm])
            outcome = y[mask]
            w = (test.loc[mask, "assigned_arm"].to_numpy() == arm).astype(int)
            if not w.any() or w.all():
                raise ValueError("Uplift evaluation needs control and treatment")
            u = pred[mask, arm - 1]
            e = w.mean()
            z = outcome * w / e - outcome * (1 - w) / (1 - e)
            gain = np.r_[0, np.cumsum(z[np.argsort(-u)])] / len(z)
            fraction = np.linspace(0, 1, len(gain))
            gains.append(float(np.trapezoid(gain - fraction * gain[-1], fraction)))
        metrics = {"qini_by_offer": gains, "mean_qini": float(np.mean(gains))}
        quality = all(g >= 0 for g in gains)
    else:
        mae = float(mean_absolute_error(y, pred))
        metrics = {"mae": mae}
        if task == "demand":
            baseline = float(mean_absolute_error(y, test.lag7))
            metrics["baseline_mae"] = baseline
            quality = mae <= baseline + 1e-8
        else:
            baseline = float(mean_absolute_error(y, np.full(len(y), bundle["validation_baseline"])))
            metrics["baseline_mae"] = baseline
            quality = mae <= baseline
    return {
        "task": task,
        "quality": {"passed": int(quality)},
        "metrics": metrics,
        "n_test": len(test),
        "data_kind": "synthetic",
        "approval": "PendingManualApproval even when quality passes",
    }


def train(train_dir, validation_dir, model_dir, output_dir):
    train_dir = Path(train_dir)
    validation_dir = Path(validation_dir)
    contract = json.loads((train_dir / "feature_contract.json").read_text())
    task = contract["task"]
    if task not in TASKS:
        raise ValueError("Unsupported cloud model family")
    tr = validate(pd.read_csv(train_dir / "train.csv"), contract)
    va = validate(pd.read_csv(validation_dir / "validation.csv"), contract)
    features = contract["features"]
    target = contract["target"]
    seed = contract.get("seed", 407)
    if task in {"propensity", "churn", "attrition"}:
        if tr[target].nunique() != 2 or va[target].nunique() != 2:
            raise ValueError("Two target classes required")
        candidates = {
            "logistic": make_pipeline(StandardScaler(), LogisticRegression(max_iter=1500, random_state=seed)),
            "hist_gradient_boosting": HistGradientBoostingClassifier(
                max_iter=75, max_leaf_nodes=12, min_samples_leaf=40, l2_regularization=3, random_state=seed
            ),
        }
        scores = {}
        for name, candidate in candidates.items():
            candidate.fit(tr[features], tr[target])
            scores[name] = float(brier_score_loss(va[target], candidate.predict_proba(va[features])[:, 1]))
        selected = min(scores, key=scores.get)
        model = candidates[selected]
        raw = np.clip(model.predict_proba(va[features])[:, 1], 1e-6, 1 - 1e-6)
        calibrator = LogisticRegression(C=1, random_state=seed).fit(
            np.log(raw / (1 - raw)).reshape(-1, 1), va[target]
        )
        bundle = {
            "model": model,
            "calibrator": calibrator,
            "contract": contract,
            "selected": selected,
            "validation_selection": scores,
        }
    elif task == "uplift":
        if set(tr.assigned_arm.unique()) != {0, 1, 2, 3}:
            raise ValueError("Four training arms required")
        model = HistGradientBoostingClassifier(
            max_iter=65, max_leaf_nodes=8, min_samples_leaf=35, l2_regularization=4, random_state=seed
        ).fit(tr[features], tr[target])
        bundle = {"model": model, "contract": contract}
    else:
        model = (
            LinearRegression()
            if task == "elasticity"
            else HistGradientBoostingRegressor(
                max_iter=100, max_leaf_nodes=18, l2_regularization=4, random_state=seed
            )
        )
        outcome = np.log(tr[target].clip(lower=1)) if task == "elasticity" else tr[target]
        model.fit(tr[features], outcome)
        selected = "model"
        if task == "demand" and mean_absolute_error(va[target], va.lag7) <= mean_absolute_error(
            va[target], np.maximum(model.predict(va[features]), 0)
        ):
            selected = "seasonal_naive"
        bundle = {
            "model": model,
            "contract": contract,
            "selected": selected,
            "validation_baseline": float(tr[target].mean()),
        }
    model_dir = Path(model_dir)
    model_dir.mkdir(parents=True, exist_ok=True)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, model_dir / "model.joblib")
    result = evaluate_bundle(bundle, va)
    (output_dir / "validation.json").write_text(json.dumps(result, indent=2))
    return bundle
