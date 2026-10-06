"""Customer-randomized multi-arm synthetic trial and intention-to-treat analysis."""

import numpy as np
import pandas as pd
from scipy.stats import chi2, norm

from .config import write_json

ARMS = ["Control", "Off-peak 15%", "Weekend 20%", "500 loyalty points"]
OFFER_ARMS = {"offpeak_15": "Off-peak 15%", "weekend_20": "Weekend 20%", "loyalty_500": "500 loyalty points"}


def sample_size(baseline=0.35, mde=0.05, alpha=0.05, power=0.8, comparisons=2):
    if not (0 < baseline < 1 and 0 < baseline + mde < 1 and 0 < alpha < 1 and 0 < power < 1):
        raise ValueError("Invalid experiment-design probabilities")
    p1, p2 = baseline, baseline + mde
    pbar = (p1 + p2) / 2
    z_alpha = norm.ppf(1 - alpha / (2 * comparisons))
    z_power = norm.ppf(power)
    n = (
        z_alpha * np.sqrt(2 * pbar * (1 - pbar)) + z_power * np.sqrt(p1 * (1 - p1) + p2 * (1 - p2))
    ) ** 2 / mde**2
    return int(np.ceil(n))


def simulate(cfg, features, hidden):
    rng = np.random.default_rng(cfg.seed + 20)
    # One randomized assignment per customer. No repeat exposure across model folds.
    trial = features.merge(hidden, on="customer_id", validate="one_to_one")
    n = len(trial)
    arms = rng.permutation(np.resize(np.array(ARMS), n))
    trial["arm"] = arms
    trial["treated"] = (arms != "Control").astype(int)
    frequency = trial.trips_30d.to_numpy()
    p0 = np.clip(0.08 + 0.50 * (1 - np.exp(-frequency / 6)), 0.04, 0.75)
    response_effect = (
        0.035
        + 0.17 * trial.latent_sensitivity.to_numpy() / 2
        + 0.06 * trial.latent_digital_affinity.to_numpy()
        - 0.045 * np.clip(frequency / 15, 0, 1)
    )
    response_effect *= np.where(
        arms == "Weekend 20%", 1.08, np.where(arms == "500 loyalty points", 0.78, 1.0)
    )
    p1 = np.clip(p0 + response_effect, 0.01, 0.94)
    trial["response"] = rng.binomial(1, np.where(trial.treated, p1, p0))
    trial["enrolled"] = trial.treated.to_numpy() * rng.binomial(
        1, np.clip(0.15 + 0.4 * trial.latent_digital_affinity.to_numpy(), 0, 1)
    )
    trial["redeemed"] = trial.enrolled.to_numpy() * trial.response.to_numpy()
    incremental_mean = (0.6 + 2.3 * trial.latent_sensitivity.to_numpy() / 2) * (
        0.6 + 0.4 * trial.latent_digital_affinity.to_numpy()
    )
    incremental_mean *= np.where(
        arms == "500 loyalty points", 0.72, np.where(arms == "Weekend 20%", 1.08, 1.0)
    )
    baseline_mean = 0.20 + np.clip(frequency * 0.22, 0, 9)
    trial["trip_count"] = rng.poisson(baseline_mean + trial.treated.to_numpy() * incremental_mean)
    avg_toll = trial.avg_toll.clip(lower=8).to_numpy()
    discount = (
        np.where(arms == "Weekend 20%", 0.20, np.where(arms == "500 loyalty points", 0.0, 0.15))
        * trial.treated.to_numpy()
    )
    trial["incentive_cost"] = (
        np.where(arms == "500 loyalty points", 5.0, trial.trip_count * avg_toll * discount)
        + 0.35 * trial.treated.to_numpy()
    )
    trial["gross_contribution"] = trial.trip_count * avg_toll * cfg.contribution_margin
    trial["net_contribution"] = trial.gross_contribution - trial.incentive_cost
    # Separate post-30-day outcome windows support long-term incremental effects.
    # These are simulator outcomes, never pre-treatment predictors.
    retention_base = np.clip(0.35 + 0.45 * (1 - np.exp(-frequency / 6)), 0.15, 0.90)
    retention_effect = (0.015 + 0.065 * trial.latent_digital_affinity.to_numpy()) * np.where(
        arms == "500 loyalty points", 1.3, 1.0
    )
    trial["retained_90d"] = rng.binomial(
        1, np.clip(retention_base + trial.treated.to_numpy() * retention_effect, 0, 1)
    )
    later_trips = rng.poisson(baseline_mean * 2 + trial.treated.to_numpy() * incremental_mean * 0.4)
    trial["margin_days31_90"] = later_trips * avg_toll * cfg.contribution_margin
    # Evaluation-only potential means. Saved separately, never features or optimizer inputs.
    oracle = trial[["customer_id"]].copy()
    oracle["true_response_effect"] = p1 - p0
    oracle["true_incremental_trips"] = incremental_mean
    oracle["true_baseline_trips"] = baseline_mean
    cfg.path("data", "simulation_audit").mkdir(parents=True, exist_ok=True)
    oracle.to_parquet(cfg.path("data", "simulation_audit", "trial_oracle.parquet"), index=False)
    trial = trial.drop(columns=[c for c in trial if c.startswith("latent_")])
    # Customer-level holdout; treatment/control both occur in each fold.
    perm = rng.permutation(n)
    split = np.empty(n, dtype=object)
    split[perm[: int(0.65 * n)]] = "train"
    split[perm[int(0.65 * n) : int(0.8 * n)]] = "validation"
    split[perm[int(0.8 * n) :]] = "test"
    trial["split"] = split
    trial.to_parquet(cfg.path("data", "silver", "fact_campaign_result.parquet"), index=False)
    campaign_facts = {
        "fact_offer_exposure": trial.loc[trial.treated.eq(1), ["customer_id", "arm"]].assign(
            exposed_at=pd.Timestamp("2025-07-01"), campaign_id="trial_july"
        ),
        "fact_offer_enrollment": trial.loc[trial.enrolled.eq(1), ["customer_id", "arm"]].assign(
            enrolled_at=pd.Timestamp("2025-07-02"), campaign_id="trial_july"
        ),
        "fact_offer_redemption": trial.loc[
            trial.redeemed.eq(1), ["customer_id", "arm", "incentive_cost"]
        ].assign(redeemed_at=pd.Timestamp("2025-07-20"), campaign_id="trial_july"),
        "fact_loyalty_redemption": trial.loc[
            (trial.arm == "500 loyalty points") & trial.redeemed.eq(1), ["customer_id"]
        ].assign(
            points_redeemed=500,
            reward_cost=5.0,
            redeemed_at=pd.Timestamp("2025-07-20"),
            reward_id="loyalty_500",
        ),
    }
    for name, frame in campaign_facts.items():
        frame.to_parquet(cfg.path("data", "silver", name + ".parquet"), index=False)
    return trial


def difference(treatment, control, comparisons=3):
    treatment = np.asarray(treatment, dtype=float)
    control = np.asarray(control, dtype=float)
    if (
        len(treatment) < 2
        or len(control) < 2
        or not np.isfinite(treatment).all()
        or not np.isfinite(control).all()
    ):
        raise ValueError("Effect comparison requires two finite observations per group")
    diff = float(treatment.mean() - control.mean())
    se = float(np.sqrt(treatment.var(ddof=1) / len(treatment) + control.var(ddof=1) / len(control)))
    # Bonferroni-adjusted intervals for the three primary treatment/control comparisons.
    z = norm.ppf(1 - 0.05 / (2 * comparisons))
    p = float(2 * norm.sf(abs(diff / se))) if se else (1.0 if diff == 0 else 0.0)
    return {
        "difference": diff,
        "ci_low": diff - z * se,
        "ci_high": diff + z * se,
        "p_value": p,
        "p_adjusted": min(1.0, comparisons * p),
    }


def analyze(cfg, trial):
    control = trial[trial.arm.eq("Control")]
    comparisons = []
    for arm in ARMS[1:]:
        group = trial[trial.arm.eq(arm)]
        stats = difference(group.response, control.response)
        stats.update(
            {
                "arm": arm,
                "n": len(group),
                "conversion": float(group.response.mean()),
                "relative_lift": stats["difference"] / float(control.response.mean()),
                "incremental_trips_per_customer": difference(group.trip_count, control.trip_count),
                "incremental_net_contribution_per_customer": difference(
                    group.net_contribution, control.net_contribution
                ),
            }
        )
        comparisons.append(stats)
    counts = trial.arm.value_counts().to_numpy()
    expected = len(trial) / len(ARMS)
    statistic = float(((counts - expected) ** 2 / expected).sum())
    required = sample_size(comparisons=3)
    enriched = trial.copy()
    enriched["travel_pattern"] = np.where(enriched.peak_share >= 0.5, "Peak-led", "Other travel")
    enriched["digital_group"] = np.where(
        enriched.digital_events_30d >= enriched.digital_events_30d.median(),
        "Higher engagement",
        "Lower engagement",
    )
    enriched["pre_treatment_value_decile"] = pd.qcut(
        enriched.spend_90d.rank(method="first"), 10, labels=False
    ).astype(str)
    enriched["frequency_group"] = np.select(
        [enriched.trips_90d >= 25, enriched.trips_90d >= 8], ["Frequent", "Regular"], default="Occasional"
    )
    subgroup = []
    for dimension in ["frequency_group", "pre_treatment_value_decile", "travel_pattern", "digital_group"]:
        groups = list(enriched.groupby(dimension))
        for label, g in groups:
            base = g[g.arm.eq("Control")]
            for arm in ARMS[1:]:
                treated = g[g.arm.eq(arm)]
                if min(len(base), len(treated)) < 20:
                    continue
                subgroup.append(
                    {
                        "dimension": dimension,
                        "group": str(label),
                        "arm": arm,
                        "n_treatment": len(treated),
                        "n_control": len(base),
                        **difference(
                            treated.response,
                            base.response,
                            comparisons=3
                            * sum(
                                enriched[d].nunique()
                                for d in [
                                    "frequency_group",
                                    "pre_treatment_value_decile",
                                    "travel_pattern",
                                    "digital_group",
                                ]
                            ),
                        ),
                    }
                )
    pd.DataFrame(subgroup).to_csv(cfg.path("outputs", "experiment_subgroups.csv"), index=False)
    result = {
        "unit": "customer",
        "analysis": "Intention to treat; all randomized customers included",
        "baseline_assumption": 0.35,
        "mde": 0.05,
        "power": 0.80,
        "family_alpha": 0.05,
        "comparisons": 3,
        "required_per_arm": required,
        "actual_per_arm": trial.arm.value_counts().to_dict(),
        "powered_for_planned_mde": bool(min(counts) >= required),
        "srm_p_value": float(chi2.sf(statistic, len(ARMS) - 1)),
        "control_conversion": float(control.response.mean()),
        "results": comparisons,
        "subgroups": subgroup,
        "subgroup_scope": "Exploratory; pre-treatment spend deciles proxy value, digital groups proxy engagement. Neither is a customer-level causal price-sensitivity measure.",
        "limitations": "Synthetic trial; normal-approximation intervals. Model uplift uses held-out customers. A separate policy experiment evaluates constrained allocation.",
    }
    write_json(cfg.path("outputs", "experiment_results.json"), result)
    return result
