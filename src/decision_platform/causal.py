"""Incremental trips for every offer, turned into money with the offer's own terms.

Learn behaviour, compute economics. The uncertain quantity is how many extra
trips, by travel period, an offer causes for a given customer; that is what the
causal learners estimate from the July trial. What the offer then costs (a
discount paid on every eligible trip, including trips that would have happened
anyway; a credit paid only if a threshold is reached; a fixed points liability)
follows from the offer terms in `economics.py`, a calibrated baseline-trips
forecast and the customer's observed tolls. Modelling revenue or net
contribution directly drowns the signal in heavy travellers' noise.

Four meta-learners compete per offer: T, S, X and a cross-fitted doubly robust
(DR) learner. The production learner for each offer is the one with the lowest
doubly robust loss on the validation fold - an observable criterion that needs
no access to the truth. Held-out customers are then scored two ways: Qini on
observed outcomes, and error against the simulator's true effects.
"""

from __future__ import annotations

import time

import joblib
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from .config import write_json
from .economics import PERIODS, window_value
from .features import FEATURES
from .models import classifier_metrics, log_experiment
from .simulation import LOYALTY_OFFERS, OFFER_ARMS

OUTCOMES = {"Peak": "trips_peak", "Off-peak": "trips_offpeak", "Weekend": "trips_weekend"}
TOLL_COLUMNS = {"Peak": "avg_toll_peak", "Off-peak": "avg_toll_offpeak", "Weekend": "avg_toll_weekend"}
LEARNERS = ["s_learner", "t_learner", "x_learner", "dr_learner"]
BOOTSTRAPS = 15
# The BLP test is reported for every offer. Applying its calibration to production estimates was tested
# and rejected: the validation fold is too small to estimate the level, and held-out bias got worse.
APPLY_BLP_CALIBRATION = False
LATER_DISCOUNT = 1.10**0.25


def _poisson(seed, iterations=150):
    return HistGradientBoostingRegressor(
        loss="poisson",
        max_iter=iterations,
        learning_rate=0.06,
        max_leaf_nodes=15,
        min_samples_leaf=40,
        l2_regularization=1.0,
        random_state=seed,
    )


def _effect_regressor(seed, iterations=80):
    """Deliberately conservative final stage: individual pseudo-outcomes are very noisy."""
    return HistGradientBoostingRegressor(
        max_iter=iterations,
        learning_rate=0.04,
        max_depth=3,
        min_samples_leaf=300,
        l2_regularization=5.0,
        random_state=seed,
    )


def uplift_curve(y, w, uplift):
    """Cumulative transformed-outcome gain when customers are ranked by predicted uplift."""
    y, w, uplift = np.asarray(y, float), np.asarray(w, float), np.asarray(uplift, float)
    order = np.argsort(-uplift, kind="stable")
    e = float(w.mean())
    transformed = y * w / e - y * (1 - w) / (1 - e)
    gain = np.r_[0, np.cumsum(transformed[order])] / len(y)
    fraction = np.linspace(0, 1, len(gain))
    random_line = fraction * gain[-1]
    step = max(1, len(fraction) // 40)
    return {
        "auuc": float(np.trapezoid(gain, fraction)),
        "qini": float(np.trapezoid(gain - random_line, fraction)),
        "fraction": fraction[::step].tolist(),
        "gain": gain[::step].tolist(),
    }


def tolls(frame):
    """Observed average toll by period, falling back to the customer's overall average."""
    fallback = frame.avg_toll.where(frame.avg_toll > 0, 8.0)
    return pd.DataFrame(
        {
            period: frame[column].where(frame[column] > 0, fallback).to_numpy()
            for period, column in TOLL_COLUMNS.items()
        }
    )


class Effects:
    """Per-period effect predictors for one learner and one offer."""

    def __init__(self, predict):
        self.predict = predict

    def frame(self, x):
        return pd.DataFrame({period: self.predict[period](x) for period in PERIODS})


class SLearner:
    """One Poisson model per period over all arms, with explicit arm indicators."""

    def __init__(self, seed, rows):
        self.arms = list(OFFER_ARMS.values())
        x = self._design(rows[FEATURES].to_numpy(float), rows.arm.to_numpy())
        self.models = {p: _poisson(seed, 300).fit(x, rows[c]) for p, c in OUTCOMES.items()}

    def _design(self, x, arms):
        indicators = np.column_stack([(arms == a).astype(float) for a in self.arms])
        return np.column_stack([x, indicators])

    def effect(self, x, arm, period):
        on = self._design(x, np.full(len(x), arm, dtype=object))
        off = self._design(x, np.full(len(x), "Control", dtype=object))
        return self.models[period].predict(on) - self.models[period].predict(off)


def _fit_learners(seed, train, arm, s_models, mu0, folds=2):
    """T, S, X and DR effect predictors for one offer, fitted on the training fold only."""
    treated = train[train.arm.eq(arm)]
    control = train[train.arm.eq("Control")]
    group = pd.concat([treated, control])
    w = group.arm.eq(arm).astype(int).to_numpy()
    xt, xc, xg = (frame[FEATURES].to_numpy(float) for frame in (treated, control, group))
    mu1 = {p: _poisson(seed + 1).fit(xt, treated[c]) for p, c in OUTCOMES.items()}
    learners = {
        "t_learner": {p: (lambda x, p=p: mu1[p].predict(x) - mu0[p].predict(x)) for p in PERIODS},
        "s_learner": {p: (lambda x, p=p: s_models.effect(x, arm, p)) for p in PERIODS},
    }
    x_models = {}
    for p, column in OUTCOMES.items():
        d1 = treated[column].to_numpy() - mu0[p].predict(xt)
        d0 = mu1[p].predict(xc) - control[column].to_numpy()
        x_models[p] = (_effect_regressor(seed + 2).fit(xt, d1), _effect_regressor(seed + 3).fit(xc, d0))
    learners["x_learner"] = {
        p: (lambda x, p=p: 0.5 * x_models[p][0].predict(x) + 0.5 * x_models[p][1].predict(x)) for p in PERIODS
    }
    fold = np.random.default_rng(seed + 4).integers(0, folds, len(group))
    dr_final, pseudo = {}, {}
    for p, column in OUTCOMES.items():
        y = group[column].to_numpy(float)
        m1, m0 = np.zeros(len(y)), np.zeros(len(y))
        for k in range(folds):
            fit, out = fold != k, fold == k
            m1[out] = _poisson(seed + 5 + k).fit(xg[fit & (w == 1)], y[fit & (w == 1)]).predict(xg[out])
            m0[out] = _poisson(seed + 7 + k).fit(xg[fit & (w == 0)], y[fit & (w == 0)]).predict(xg[out])
        pseudo[p] = m1 - m0 + 2 * w * (y - m1) - 2 * (1 - w) * (y - m0)
        dr_final[p] = _effect_regressor(seed + 9).fit(xg, pseudo[p])
    learners["dr_learner"] = {p: dr_final[p].predict for p in PERIODS}
    nuisance = {"mu1": mu1, "x_models": x_models, "dr_final": dr_final, "dr_pseudo": pseudo, "dr_x": xg}
    return {name: Effects(funcs) for name, funcs in learners.items()}, nuisance


def blp_calibration(effects, rows, arm, mu1, mu0):
    """Best-linear-predictor test of heterogeneity (Chernozhukov, Demirer, Duflo and Fernandez-Val).

    On held-out rows, regress the doubly robust pseudo-outcome for total trips on
    [1, prediction - mean prediction]. The intercept estimates the average effect;
    the slope says how much of the predicted spread is real (1 = calibrated,
    0 = no detectable heterogeneity, below 1 = over-dispersed predictions, which is
    what makes an optimizer's chosen customers look better than they are).
    """
    group = rows[rows.arm.isin([arm, "Control"])]
    w = group.arm.eq(arm).astype(int).to_numpy()
    x = group[FEATURES].to_numpy(float)
    predicted = effects.frame(x).sum(axis=1).to_numpy()
    pseudo = np.zeros(len(group))
    for p, column in OUTCOMES.items():
        y = group[column].to_numpy(float)
        a, b = mu1[p].predict(x), mu0[p].predict(x)
        pseudo += a - b + 2 * w * (y - a) - 2 * (1 - w) * (y - b)
    centred = predicted - predicted.mean()
    design = np.column_stack([np.ones(len(pseudo)), centred])
    coef, *_ = np.linalg.lstsq(design, pseudo, rcond=None)
    residual = pseudo - design @ coef
    bread = np.linalg.pinv(design.T @ design)
    meat = design.T @ (design * residual[:, None] ** 2)
    se = np.sqrt(np.diag(bread @ meat @ bread))
    return {
        "ate": float(coef[0]),
        "ate_se": float(se[0]),
        "slope": float(coef[1]),
        "slope_se": float(se[1]),
        "heterogeneity_detected": bool(coef[1] - 1.96 * se[1] > 0),
        "mean_prediction": float(predicted.mean()),
        "n": len(group),
    }


def calibrate(effect, blp, reference_mean):
    """Shrink predicted per-period effects with the held-out BLP slope and level.

    tau_cal = level * mean + slope * (tau - mean), applied per period so signed
    effects (a peak shift) keep their direction. Slope is held to [0, 1]: the
    calibration may remove spread, never invent it.
    """
    slope = float(np.clip(blp["slope"], 0.0, 1.0))
    level = (
        float(np.clip(blp["ate"] / blp["mean_prediction"], 0.0, 1.5))
        if blp["mean_prediction"] > 1e-9
        else 1.0
    )
    means = reference_mean
    return pd.DataFrame({p: level * means[p] + slope * (effect[p].to_numpy() - means[p]) for p in PERIODS}), {
        "slope_used": slope,
        "level_used": level,
    }


def _dr_loss(effects, rows, arm, mu1, mu0):
    """Doubly robust validation loss: mean squared gap to the DR pseudo-outcome, summed over periods."""
    group = rows[rows.arm.isin([arm, "Control"])]
    w = group.arm.eq(arm).astype(int).to_numpy()
    x = group[FEATURES].to_numpy(float)
    predicted = effects.frame(x)
    loss = 0.0
    for p, column in OUTCOMES.items():
        y = group[column].to_numpy(float)
        a, b = mu1[p].predict(x), mu0[p].predict(x)
        pseudo = a - b + 2 * w * (y - a) - 2 * (1 - w) * (y - b)
        loss += float(np.mean((pseudo - predicted[p].to_numpy()) ** 2))
    return loss


PRE_PERIOD = ["spend_30d", "spend_90d", "spend_365d", "trips_30d", "trips_90d", "recency_days"]


def adjusted_effect(y, w, x):
    """Regression-adjusted treatment effect (OLS with centred pre-period covariates)."""
    design = np.column_stack([np.ones(len(y)), w, x - x.mean(axis=0)])
    coef, *_ = np.linalg.lstsq(design, y, rcond=None)
    return float(coef[1])


def _persistence(trial, seed, draws=200, quantile=0.2):
    """Days 31-90 margin effect per dollar of in-window incremental gross contribution, by offer family.

    Effects are regression-adjusted on pre-period behaviour to strip the large
    customer-level variance. The ratio is noisy - every arm shares one control
    group - so planning uses a conservative bootstrap quantile, not the point
    estimate.
    """
    families = {
        "discount": [o for o in OFFER_ARMS if o not in LOYALTY_OFFERS],
        "loyalty": sorted(LOYALTY_OFFERS),
    }
    rng = np.random.default_rng(seed + 55)
    by_arm = {arm: group for arm, group in trial.groupby("arm")}
    control = by_arm["Control"]

    def ratio(offers, resample):
        later = gross = 0.0
        c = control.iloc[rng.integers(0, len(control), len(control))] if resample else control
        for offer in offers:
            g = by_arm[OFFER_ARMS[offer]]
            g = g.iloc[rng.integers(0, len(g), len(g))] if resample else g
            rows = pd.concat([g, c])
            w = np.r_[np.ones(len(g)), np.zeros(len(c))]
            x = rows[PRE_PERIOD].to_numpy(float)
            later += adjusted_effect(rows.margin_days31_90.to_numpy(float), w, x)
            gross += adjusted_effect(rows.gross_contribution.to_numpy(float), w, x)
        return later, gross

    result = {}
    for family, offers in families.items():
        later, gross = ratio(offers, False)
        point = later / gross if gross > 0 else 0.0
        boot = np.array([np.divide(*ratio(offers, True)) for _ in range(draws)])
        boot = boot[np.isfinite(boot)]
        planning = float(np.clip(np.quantile(boot, quantile), 0, 1.5))
        result[family] = {
            "ratio": planning,
            "point_estimate": float(point),
            "ci_low": float(np.quantile(boot, 0.05)),
            "ci_high": float(np.quantile(boot, 0.95)),
            "planning_quantile": quantile,
            "later_effect_per_customer": later / len(offers),
            "gross_effect_per_customer": gross / len(offers),
            "offers": offers,
        }
    return result


def _economics(offer, base, effect, toll, cfg, persistence):
    money = window_value(offer, base, effect, toll, cfg.contribution_margin)
    family = "loyalty" if offer in LOYALTY_OFFERS else "discount"
    later = persistence[family]["ratio"] * money.gross.to_numpy() / LATER_DISCOUNT
    return money, later


class _Bootstrap:
    """Effect draws for a selected learner. Nuisance models stay fixed; the effect stage is resampled."""

    def __init__(self, train, mu0, x, seed):
        self.train, self.mu0, self.x, self.seed = train, mu0, x, seed
        self._s_draws = None

    def s_draws(self):
        if self._s_draws is None:
            rng = np.random.default_rng(self.seed + 700)
            self._s_draws = []
            for b in range(BOOTSTRAPS):
                sample = self.train.iloc[rng.integers(0, len(self.train), len(self.train))]
                self._s_draws.append(SLearner(self.seed + b, sample))
        return self._s_draws

    def draws(self, name, arm, nuisance, index):
        rng = np.random.default_rng(self.seed + 900 + index)
        x, mu0 = self.x, self.mu0
        treated = self.train[self.train.arm.eq(arm)]
        control = self.train[self.train.arm.eq("Control")]
        xt, xc = treated[FEATURES].to_numpy(float), control[FEATURES].to_numpy(float)
        out = []
        if name == "s_learner":
            return [pd.DataFrame({p: model.effect(x, arm, p) for p in PERIODS}) for model in self.s_draws()]
        for b in range(BOOTSTRAPS):
            if name == "dr_learner":
                xg = nuisance["dr_x"]
                idx = rng.integers(0, len(xg), len(xg))
                frame = {
                    p: _effect_regressor(self.seed + b, 60)
                    .fit(xg[idx], nuisance["dr_pseudo"][p][idx])
                    .predict(x)
                    for p in PERIODS
                }
            elif name == "t_learner":
                idx = rng.integers(0, len(xt), len(xt))
                frame = {
                    p: _poisson(self.seed + b).fit(xt[idx], treated[c].to_numpy()[idx]).predict(x)
                    - mu0[p].predict(x)
                    for p, c in OUTCOMES.items()
                }
            else:
                i1 = rng.integers(0, len(xt), len(xt))
                i0 = rng.integers(0, len(xc), len(xc))
                frame = {}
                for p, column in OUTCOMES.items():
                    d1 = treated[column].to_numpy()[i1] - mu0[p].predict(xt[i1])
                    d0 = nuisance["mu1"][p].predict(xc[i0]) - control[column].to_numpy()[i0]
                    tau1 = _effect_regressor(self.seed + b, 60).fit(xt[i1], d1)
                    tau0 = _effect_regressor(self.seed + b + 50, 60).fit(xc[i0], d0)
                    frame[p] = 0.5 * tau1.predict(x) + 0.5 * tau0.predict(x)
            out.append(pd.DataFrame(frame))
        return out


def fit_uplift(cfg, trial, current, forecast_totals=None, tracking=True):
    """Fit, select and score effect models for all offers; return one row per customer and offer."""
    started = time.perf_counter()
    seed = cfg.seed
    oracle_path = cfg.path("data", "simulation_audit", "trial_oracle.parquet")
    oracle = pd.read_parquet(oracle_path) if oracle_path.exists() else None
    train = trial[trial.split.eq("train")]
    validation = trial[trial.split.eq("validation")]
    test = trial[trial.split.eq("test")]
    control = train[train.arm.eq("Control")]
    xc = control[FEATURES].to_numpy(float)
    mu0 = {p: _poisson(seed + 21).fit(xc, control[c]) for p, c in OUTCOMES.items()}
    s_models = SLearner(seed + 31, train)
    persistence = _persistence(trial, seed)

    x_current = current[FEATURES].to_numpy(float)
    base_current = pd.DataFrame({p: mu0[p].predict(x_current) for p in PERIODS})
    calibration = {}
    if forecast_totals:
        # Consistency check only: customer-level baseline vs the zone/period demand forecast.
        for period in PERIODS:
            calibration[period] = float(forecast_totals[period] / max(base_current[period].sum(), 1e-9))
    tolls_current = tolls(current)
    x_test = test[FEATURES].to_numpy(float)
    base_test = pd.DataFrame({p: mu0[p].predict(x_test) for p in PERIODS})
    tolls_test = tolls(test)
    bootstrap = _Bootstrap(train, mu0, x_current, seed)

    metrics, scores, chosen = {}, [], {}
    heldout = test[["customer_id", "arm", "net_contribution", "trip_count"]].copy()
    for index, (offer, arm) in enumerate(OFFER_ARMS.items()):
        learners, nuisance = _fit_learners(seed + 100 * (index + 1), train, arm, s_models, mu0)
        losses = {
            name: _dr_loss(effects, validation, arm, nuisance["mu1"], mu0)
            for name, effects in learners.items()
        }
        best = min(losses, key=losses.get)
        blp = blp_calibration(learners[best], validation, arm, nuisance["mu1"], mu0)
        reference_mean = learners[best].frame(validation[FEATURES].to_numpy(float)).mean()
        sample = test[test.arm.isin(["Control", arm])]
        sample_w = sample.arm.eq(arm).astype(int)
        positions = test.index.get_indexer(sample.index)
        offer_metrics = {"n_test": len(sample), "selected": best, "validation_dr_loss": losses, "blp": blp}
        truth = None
        if oracle is not None:
            truth = oracle[oracle.offer_id.eq(offer)].set_index("customer_id").loc[test.customer_id]
        for name, effects in learners.items():
            effect = effects.frame(x_test)
            money, later = _economics(offer, base_test, effect, tolls_test, cfg, persistence)
            value = money.net.to_numpy() + later
            entry = uplift_curve(sample.net_contribution, sample_w, value[positions])
            if truth is not None:
                true_trips = truth.true_incremental_trips.to_numpy()
                trips = effect.sum(axis=1).to_numpy()
                true_value = truth.true_value.to_numpy()
                entry["oracle"] = {
                    "trips_pehe": float(np.sqrt(np.mean((trips - true_trips) ** 2))),
                    "trips_spearman": float(spearmanr(trips, true_trips).statistic),
                    "value_pehe": float(np.sqrt(np.mean((value - true_value) ** 2))),
                    "value_spearman": float(spearmanr(value, true_value).statistic),
                    "true_trips_sd": float(true_trips.std()),
                    "true_value_sd": float(true_value.std()),
                }
            offer_metrics[name] = entry
        calibrated_test, adjustment = calibrate(learners[best].frame(x_test), blp, reference_mean)
        raw_money, raw_later = _economics(
            offer, base_test, learners[best].frame(x_test), tolls_test, cfg, persistence
        )
        money, later = _economics(offer, base_test, calibrated_test, tolls_test, cfg, persistence)
        value = money.net.to_numpy() + later
        heldout[offer + "_value"] = value if APPLY_BLP_CALIBRATION else raw_money.net.to_numpy() + raw_later
        entry = uplift_curve(sample.net_contribution, sample_w, value[positions])
        if truth is not None:
            entry["oracle"] = {
                "trips_pehe": float(
                    np.sqrt(np.mean((calibrated_test.sum(axis=1).to_numpy() - true_trips) ** 2))
                ),
                "value_pehe": float(np.sqrt(np.mean((value - truth.true_value.to_numpy()) ** 2))),
                "value_spearman": float(spearmanr(value, truth.true_value.to_numpy()).statistic),
                "value_bias": float(np.mean(value - truth.true_value.to_numpy())),
                "raw_value_bias": float(
                    np.mean(
                        _economics(
                            offer, base_test, learners[best].frame(x_test), tolls_test, cfg, persistence
                        )[0].net.to_numpy()
                        + _economics(
                            offer, base_test, learners[best].frame(x_test), tolls_test, cfg, persistence
                        )[1]
                        - truth.true_value.to_numpy()
                    )
                ),
            }
        offer_metrics["calibrated"] = {**entry, **adjustment}
        metrics[offer] = offer_metrics

        effect = learners[best].frame(x_current)
        if APPLY_BLP_CALIBRATION:
            effect, _ = calibrate(effect, blp, reference_mean)
        money, later = _economics(offer, base_current, effect, tolls_current, cfg, persistence)
        values = []
        for draw in bootstrap.draws(best, arm, nuisance, index):
            if APPLY_BLP_CALIBRATION:
                draw, _ = calibrate(draw, blp, reference_mean)
            draw_money, draw_later = _economics(offer, base_current, draw, tolls_current, cfg, persistence)
            values.append(draw_money.net.to_numpy() + draw_later)
        sd = np.std(np.column_stack(values), axis=1, ddof=1)
        mu = base_current.sum(axis=1).to_numpy()
        total = effect.sum(axis=1).to_numpy()
        scores.append(
            pd.DataFrame(
                {
                    "customer_id": current.customer_id.to_numpy(),
                    "offer_id": offer,
                    "value_uplift": money.net.to_numpy(),
                    "value_uplift_sd": sd,
                    "later_value_uplift": later,
                    "expected_cost": money.cost.to_numpy(),
                    "incremental_gross": money.gross.to_numpy(),
                    "trips_peak": effect["Peak"].to_numpy(),
                    "trips_offpeak": effect["Off-peak"].to_numpy(),
                    "trips_weekend": effect["Weekend"].to_numpy(),
                    "incremental_trips": total,
                    "baseline_trips": mu,
                    "incremental_response": np.exp(-mu) - np.exp(-(mu + total)),
                    "learner": best,
                }
            )
        )
        chosen[offer] = {
            "learner": best,
            "blp": blp,
            "reference_mean": reference_mean.to_dict(),
            "nuisance": {k: v for k, v in nuisance.items() if k != "dr_x"},
        }
        print(f"  {offer}: {best}, BLP slope {blp['slope']:.2f} (se {blp['slope_se']:.2f})", flush=True)

    uplift = pd.concat(scores, ignore_index=True)
    heldout.to_csv(cfg.path("outputs", "heldout_policy_scores.csv"), index=False)

    fit_rows = pd.concat([train, validation])
    treated_rows = fit_rows[fit_rows.treated.eq(1)]
    held = test[test.treated.eq(1)]
    enroll = make_pipeline(StandardScaler(), LogisticRegression(C=0.2, max_iter=2000)).fit(
        treated_rows[FEATURES], treated_rows.enrolled
    )
    metrics["offer_enrollment"] = classifier_metrics(
        held.enrolled, enroll.predict_proba(held[FEATURES])[:, 1]
    )
    loyalty_rows = fit_rows[fit_rows.offer_id.isin(LOYALTY_OFFERS)]
    loyalty_test = test[test.offer_id.isin(LOYALTY_OFFERS)]
    redemption = make_pipeline(StandardScaler(), LogisticRegression(C=0.2, max_iter=2000)).fit(
        loyalty_rows[FEATURES], loyalty_rows.redeemed
    )
    metrics["loyalty_redemption"] = classifier_metrics(
        loyalty_test.redeemed, redemption.predict_proba(loyalty_test[FEATURES])[:, 1]
    )
    enrollment = enroll.predict_proba(x_current)[:, 1]
    redeem = redemption.predict_proba(x_current)[:, 1]
    uplift["enrollment_probability"] = np.tile(enrollment, len(OFFER_ARMS))
    uplift["redemption_probability"] = np.where(
        uplift.offer_id.isin(LOYALTY_OFFERS), np.tile(redeem, len(OFFER_ARMS)), np.nan
    )

    rows = []
    for offer in OFFER_ARMS:
        row = {
            "offer_id": offer,
            "selected": metrics[offer]["selected"],
            "blp_slope": metrics[offer]["blp"]["slope"],
            "blp_slope_se": metrics[offer]["blp"]["slope_se"],
            "blp_ate": metrics[offer]["blp"]["ate"],
            "heterogeneity_detected": metrics[offer]["blp"]["heterogeneity_detected"],
            "calibrated_qini": metrics[offer]["calibrated"]["qini"],
        }
        for key, value in metrics[offer]["calibrated"].get("oracle", {}).items():
            row["calibrated_" + key] = value
        for learner in LEARNERS:
            entry = metrics[offer][learner]
            row[learner + "_qini"] = entry["qini"]
            row[learner + "_dr_loss"] = metrics[offer]["validation_dr_loss"][learner]
            for key, value in entry.get("oracle", {}).items():
                if not key.startswith("true_"):
                    row[f"{learner}_{key}"] = value
        for key in ["true_value_sd", "true_trips_sd"]:
            if "oracle" in metrics[offer]["dr_learner"]:
                row[key] = metrics[offer]["dr_learner"]["oracle"][key]
        rows.append(row)
    summary = pd.DataFrame(rows)
    summary.to_csv(cfg.path("outputs", "uplift_learner_comparison.csv"), index=False)
    metrics["learner_summary"] = {
        learner: {
            "mean_value_pehe": float(summary[learner + "_value_pehe"].mean()) if oracle is not None else None,
            "mean_value_spearman": float(summary[learner + "_value_spearman"].mean())
            if oracle is not None
            else None,
            "mean_trips_spearman": float(summary[learner + "_trips_spearman"].mean())
            if oracle is not None
            else None,
            "mean_qini": float(summary[learner + "_qini"].mean()),
            "times_selected": int((summary.selected == learner).sum()),
        }
        for learner in LEARNERS
    }
    if oracle is not None:
        selected = [metrics[o][metrics[o]["selected"]]["oracle"] for o in OFFER_ARMS]
        metrics["selected_value_spearman"] = float(np.mean([m["value_spearman"] for m in selected]))
        metrics["selected_value_pehe"] = float(np.mean([m["value_pehe"] for m in selected]))
        metrics["blp_calibration_check"] = {
            "applied": APPLY_BLP_CALIBRATION,
            "mean_value_bias_raw": float(
                np.mean([metrics[o]["calibrated"]["oracle"]["raw_value_bias"] for o in OFFER_ARMS])
            ),
            "mean_value_bias_calibrated": float(
                np.mean([metrics[o]["calibrated"]["oracle"]["value_bias"] for o in OFFER_ARMS])
            ),
            "offers_where_calibration_increased_bias": int(
                sum(
                    abs(metrics[o]["calibrated"]["oracle"]["value_bias"])
                    > abs(metrics[o]["calibrated"]["oracle"]["raw_value_bias"])
                    for o in OFFER_ARMS
                )
            ),
        }
    metrics["heterogeneity_detected_offers"] = int(
        sum(metrics[o]["blp"]["heterogeneity_detected"] for o in OFFER_ARMS)
    )
    metrics["persistence"] = persistence
    metrics["forecast_to_customer_baseline_ratio"] = calibration
    metrics["selection_rule"] = (
        "Lowest doubly robust validation loss per offer (observable; no simulator truth)"
    )
    metrics["training_seconds"] = time.perf_counter() - started
    folder = cfg.path("outputs", "models")
    folder.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {
            "baseline": mu0,
            "forecast_to_customer_baseline_ratio": calibration,
            "s_learner": s_models,
            "offers": chosen,
            "enrollment": enroll,
            "redemption": redemption,
            "persistence": persistence,
            "features": FEATURES,
        },
        folder / "uplift.joblib",
        compress=3,
    )
    log_experiment(
        cfg,
        "uplift",
        None,
        {
            "selected_value_spearman": metrics.get("selected_value_spearman", 0.0),
            "mean_qini_selected": float(
                np.mean([metrics[o][metrics[o]["selected"]]["qini"] for o in OFFER_ARMS])
            ),
        },
        {
            "seed": seed,
            "assignment": "customer-randomised, 9 equal arms",
            "selection": metrics["selection_rule"],
            "bootstraps": BOOTSTRAPS,
        },
        tracking,
        artifact=folder / "uplift.joblib",
    )
    write_json(cfg.path("outputs", "uplift_metrics.json"), metrics)
    return uplift, metrics
