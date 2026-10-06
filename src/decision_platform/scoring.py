"""Registry scoring adapters shared with batch clients; no simulator access."""

import numpy as np
import pandas as pd

PERIODS = ["Peak", "Off-peak", "Weekend"]


def uplift_effects(bundle, frame):
    """Incremental trips per offer and travel period from the production ensemble in uplift.joblib.

    The bundle stores each learner's fitted parts rather than the closures the pipeline
    predicts with (closures do not pickle), so this rebuilds the same arithmetic as
    causal._fit_learners: one column per offer and period, averaged over the offer's
    ensemble members.
    """
    from .simulation import OFFER_ARMS

    x = frame[bundle["features"]].to_numpy(float)
    out = {}
    for offer, chosen in bundle["offers"].items():
        arm, parts = OFFER_ARMS[offer], chosen["nuisance"]
        for period in PERIODS:
            members = []
            for member in chosen["members"]:
                if member == "s_learner":
                    members.append(bundle["s_learner"].effect(x, arm, period))
                elif member == "t_learner":
                    members.append(parts["mu1"][period].predict(x) - bundle["baseline"][period].predict(x))
                elif member == "x_learner":
                    treated, control = parts["x_models"][period]
                    members.append(0.5 * treated.predict(x) + 0.5 * control.predict(x))
                elif member == "dr_learner":
                    members.append(parts["dr_final"][period].predict(x))
                else:
                    raise ValueError(f"unknown learner {member!r}")
            out[f"{offer}|{period}"] = np.mean(members, axis=0)
    return pd.DataFrame(out, index=frame.index)


def score_bundle(name, bundle, frame):
    if name in {"propensity", "churn", "attrition"}:
        raw = np.clip(bundle["model"].predict_proba(frame[bundle["features"]])[:, 1], 1e-5, 1 - 1e-5)
        return bundle["calibrator"].predict_proba(np.log(raw / (1 - raw)).reshape(-1, 1))[:, 1]
    if name == "clv":
        return bundle.predict(frame)
    if name == "demand":
        prediction = bundle["model"].predict(frame[bundle["features"]])
        if bundle.get("selected") == "ratio_boosting":
            # The model predicts log(trips + 1) relative to the same-weekday mean of the last four weeks.
            prediction = np.expm1(frame["log_sdw4"].to_numpy(float) + prediction)
        return np.maximum(prediction, 0)
    if name == "uplift":
        return uplift_effects(bundle, frame)
    if name == "elasticity":
        result = []
        for _, row in frame.iterrows():
            # Cells are zone:period:segment since segment-level price tests; zone:period before them.
            key = f"{int(row.zone_id)}:{row.period}" + (f":{row.segment}" if "segment" in row else "")
            x = pd.DataFrame([row])[bundle["features"]]
            result.append(float(np.exp(bundle["models"][key].predict(x.to_numpy(float))[0])))
        return np.asarray(result)
    scaled = bundle["scaler"].transform(np.log1p(frame[bundle["features"]]))
    if name == "segmentation":
        return bundle["model"].predict(scaled)
    if name == "anomaly":
        return -bundle["model"].score_samples(scaled)
    raise ValueError("Unsupported model")
