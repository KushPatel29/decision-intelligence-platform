"""Probabilistic value benchmark, exact model explanations and reward accounting."""

import joblib
import numpy as np
import pandas as pd

from .config import PARQUET, write_json
from .features import FEATURES
from .models import reg_metrics


def explain(cfg, current):
    import shap

    bundle = joblib.load(cfg.path("outputs", "models", "propensity.joblib"))
    model = bundle["model"]
    sample = current.sample(min(300, len(current)), random_state=cfg.seed)
    if hasattr(model, "named_steps"):
        scaler = model.steps[0][1]
        estimator = model.steps[-1][1]
        background = scaler.transform(current[FEATURES].sample(min(500, len(current)), random_state=cfg.seed))
        transformed = scaler.transform(sample[FEATURES])
        explanation = shap.LinearExplainer(estimator, background)(transformed)
    else:
        explanation = shap.TreeExplainer(model)(sample[FEATURES])
    values = np.asarray(explanation.values)
    if values.ndim == 3:
        values = values[:, :, 1]
    global_values = pd.DataFrame(
        {"feature": FEATURES, "mean_absolute_shap": np.abs(values).mean(axis=0)}
    ).sort_values("mean_absolute_shap", ascending=False)
    global_values.to_csv(cfg.path("outputs", "shap_global.csv"), index=False)
    local = pd.DataFrame(values, columns=FEATURES)
    local.insert(0, "customer_id", sample.customer_id.to_numpy())
    local.to_csv(cfg.path("outputs", "shap_customers.csv"), index=False)
    write_json(
        cfg.path("outputs", "explanation_metadata.json"),
        {
            "method": "SHAP TreeExplainer or LinearExplainer for selected propensity champion",
            "customers": len(sample),
            "units": "Uncalibrated model log odds. Contributions explain predictions, not causal effects; calibration is a separate transform.",
            "seed": cfg.seed,
        },
    )


def probabilistic_value(cfg, trips, current):
    from lifetimes import BetaGeoFitter, GammaGammaFitter
    from lifetimes.utils import summary_data_from_transaction_data

    def summary(cutoff):
        history = trips[trips.timestamp < pd.Timestamp(cutoff)].copy()
        # Purchase occasion = customer-day; value = total contribution that day.
        daily = (
            history.assign(
                day=history.timestamp.dt.normalize(), margin=history.final_charge * cfg.contribution_margin
            )
            .groupby(["customer_id", "day"])
            .margin.sum()
            .reset_index()
        )
        return summary_data_from_transaction_data(
            daily,
            "customer_id",
            "day",
            "margin",
            observation_period_end=pd.Timestamp(cutoff) - pd.Timedelta(days=1),
            freq="D",
        )

    calibration = summary("2025-07-01")
    bg = BetaGeoFitter(penalizer_coef=0.01).fit(calibration.frequency, calibration.recency, calibration["T"])
    predicted = bg.conditional_expected_number_of_purchases_up_to_time(
        90, calibration.frequency, calibration.recency, calibration["T"]
    )
    if not np.isfinite(predicted).all():
        raise ValueError("BG/NBD produced non-finite held-out predictions")
    observed = (
        trips[(trips.timestamp >= "2025-07-01") & (trips.timestamp < "2025-09-29")]
        .assign(day=lambda x: x.timestamp.dt.normalize())
        .groupby("customer_id")
        .day.nunique()
        .reindex(calibration.index, fill_value=0)
    )
    validation = reg_metrics(observed, predicted)
    validation["baseline_mae"] = float(
        np.abs(observed - 90 * calibration.frequency / calibration["T"].clip(lower=1)).mean()
    )
    s = summary(cfg.decision_date)
    bg = BetaGeoFitter(penalizer_coef=0.01).fit(s.frequency, s.recency, s["T"])
    repeat = s[(s.frequency > 0) & (s.monetary_value > 0)]
    # q>1 gives a finite positive population mean for one-purchase customers.
    gg = GammaGammaFitter(penalizer_coef=0.01).fit(repeat.frequency, repeat.monetary_value, q_constraint=True)
    if gg.params_["q"] <= 1:
        raise ValueError("Gamma-Gamma population contribution mean is undefined (q<=1)")
    expected_value = gg.conditional_expected_average_profit(s.frequency, s.monetary_value.clip(lower=0.01))
    if not np.isfinite(expected_value).all() or (expected_value < 0).any():
        raise ValueError("Invalid Gamma-Gamma expected contribution")
    value = np.zeros(len(s))
    previous = np.zeros(len(s))
    monthly_discount = 1.10 ** (1 / 12) - 1
    for month in range(1, 13):
        cumulative = np.asarray(
            bg.conditional_expected_number_of_purchases_up_to_time(
                month * 365.25 / 12, s.frequency, s.recency, s["T"]
            )
        )
        if not np.isfinite(cumulative).all():
            raise ValueError("BG/NBD produced non-finite customer-value predictions")
        value += (cumulative - previous) * expected_value.to_numpy() / (1 + monthly_discount) ** month
        previous = cumulative
    result = s.copy()
    result["probabilistic_clv_12m"] = value
    result["probability_alive"] = bg.conditional_probability_alive(s.frequency, s.recency, s["T"])
    result.reset_index().to_csv(cfg.path("outputs", "probabilistic_clv.csv"), index=False)
    write_json(
        cfg.path("outputs", "probabilistic_clv_metrics.json"),
        {
            "method": "BG/NBD customer-day frequency plus Gamma-Gamma mean contribution, 12 months, 10% annual discount",
            "validation_90d_customer_days": validation,
            "customers_with_history": len(s),
            "frequency_monetary_correlation": float(repeat.frequency.corr(repeat.monetary_value)),
            "limitations": "Left-truncated history begins January 2024. Stationarity and frequency/value independence are assumptions, not established business facts. Held-out 90-day purchase-day evaluation does not validate 12-month CLV. Customers without a prior purchase have no estimate.",
        },
    )
    return current.merge(
        result[["probabilistic_clv_12m", "probability_alive"]],
        left_on="customer_id",
        right_index=True,
        how="left",
        validate="one_to_one",
    )


def reward_ledger(cfg):
    earned = pd.read_parquet(cfg.path("data", "silver", "fact_loyalty_points.parquet"))
    redemption = pd.read_parquet(cfg.path("data", "silver", "fact_loyalty_redemption.parquet"))
    trial = pd.read_parquet(cfg.path("data", "silver", "fact_campaign_result.parquet"))
    loyalty = trial[trial.offer_id.isin(["loyalty_500", "loyalty_1500"])]
    awards = loyalty[["customer_id", "offer_id"]].assign(
        points_awarded=np.where(loyalty.offer_id.eq("loyalty_1500"), 1500, 500),
        awarded_at=pd.Timestamp("2025-07-01"),
        award_id="trial_july",
    )
    awards.to_parquet(cfg.path("data", "silver", "fact_loyalty_award.parquet"), index=False, **PARQUET)
    ledger = (
        earned[earned.timestamp < pd.Timestamp(cfg.decision_date)]
        .groupby("customer_id")
        .points_earned.sum()
        .to_frame()
    )
    ledger = (
        ledger.join(awards.groupby("customer_id").points_awarded.sum(), how="outer")
        .join(redemption.groupby("customer_id").points_redeemed.sum(), how="outer")
        .fillna(0)
    )
    ledger["points_balance"] = ledger.points_earned + ledger.points_awarded - ledger.points_redeemed
    if (ledger.points_balance < 0).any():
        raise ValueError("Loyalty ledger has a negative balance")
    ledger.reset_index().to_csv(cfg.path("outputs", "loyalty_ledger.csv"), index=False)
    write_json(
        cfg.path("outputs", "loyalty_accounting.json"),
        {
            "points_earned": int(ledger.points_earned.sum()),
            "points_awarded": int(ledger.points_awarded.sum()),
            "points_redeemed": int(ledger.points_redeemed.sum()),
            "points_balance": int(ledger.points_balance.sum()),
            "reconciled": True,
            "point_value_cad": 0.01,
            "note": "Illustrative portfolio accounting, not company reward rules. Trial reward liability is reserved at award even if not redeemed.",
        },
    )
