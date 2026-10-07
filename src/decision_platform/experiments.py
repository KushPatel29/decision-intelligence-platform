"""July 2025 customer-randomised offer trial: design, simulation and analysis.

Design: ten equal arms (control plus nine offers), customer-level
randomisation, intention-to-treat. Primary metrics are trips and net
contribution per customer over the 30-day offer window; the binary "travelled"
response is kept for the classic proportion test.

Analysis adds three things a production experimentation team uses:
- CUPED: regress out the pre-period (June) trips/spend to shrink variance
  without biasing the treatment effect.
- Group-sequential monitoring: O'Brien-Fleming boundaries at days 10/20/30,
  calibrated by simulation to the per-comparison alpha.
- Multiplicity control: Bonferroni for the nine primary comparisons and
  Benjamini-Hochberg for exploratory subgroups.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import chi2, norm

from .config import PARQUET, write_json
from .simulation import (
    ARMS,
    LOYALTY_OFFERS,
    OFFER_ARMS,
    OFFER_CATALOG,
    PERIODS,
    Population,
    expected_tolls,
    expected_window_trips,
    offer_truth,
)

TRIAL_START = "2025-07-01"
LOOKS = (10, 20, 30)


def sample_size(baseline=0.35, mde=0.05, alpha=0.05, power=0.8, comparisons=2):
    """Customers per arm for a two-sided two-proportion test with Bonferroni alpha."""
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


def continuous_sample_size(sd, mde, alpha=0.05, power=0.8, comparisons=1):
    z = norm.ppf(1 - alpha / (2 * comparisons)) + norm.ppf(power)
    return int(np.ceil(2 * (z * sd / mde) ** 2))


def difference(treatment, control, comparisons=3):
    """Difference in means, normal-approximation CI and Bonferroni-adjusted p-value."""
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
    z = norm.ppf(1 - 0.05 / (2 * comparisons))
    p = float(2 * norm.sf(abs(diff / se))) if se else (1.0 if diff == 0 else 0.0)
    return {
        "difference": diff,
        "se": se,
        "ci_low": diff - z * se,
        "ci_high": diff + z * se,
        "p_value": p,
        "p_adjusted": min(1.0, comparisons * p),
    }


def cuped(treatment_y, control_y, treatment_x, control_x, comparisons=3):
    """CUPED-adjusted difference using a pooled theta from pre-period covariate x."""
    y = np.r_[treatment_y, control_y].astype(float)
    x = np.r_[treatment_x, control_x].astype(float)
    theta = float(np.cov(y, x, ddof=1)[0, 1] / np.var(x, ddof=1)) if np.var(x) > 0 else 0.0
    mean_x = x.mean()
    adjusted_t = np.asarray(treatment_y, float) - theta * (np.asarray(treatment_x, float) - mean_x)
    adjusted_c = np.asarray(control_y, float) - theta * (np.asarray(control_x, float) - mean_x)
    result = difference(adjusted_t, adjusted_c, comparisons)
    raw = difference(treatment_y, control_y, comparisons)
    result["theta"] = theta
    result["variance_reduction"] = float(1 - (result["se"] / raw["se"]) ** 2) if raw["se"] else 0.0
    return result


def benjamini_hochberg(p_values):
    p = np.asarray(p_values, dtype=float)
    if not len(p):
        return p
    order = np.argsort(p)
    ranked = p[order] * len(p) / np.arange(1, len(p) + 1)
    q = np.minimum.accumulate(ranked[::-1])[::-1]
    out = np.empty_like(q)
    out[order] = np.minimum(q, 1.0)
    return out


def obrien_fleming_boundaries(looks=3, alpha=0.05, draws=400_000, seed=11):
    """Two-sided O'Brien-Fleming critical values c*sqrt(K/k), calibrated by simulation.

    Brownian motion with equally spaced information: Z_k = S_k/sqrt(k). The
    constant c is chosen so that the chance of crossing at any look under the
    null equals alpha.
    """
    rng = np.random.default_rng(seed)
    increments = rng.standard_normal((draws, looks))
    z = np.cumsum(increments, axis=1) / np.sqrt(np.arange(1, looks + 1))
    scale = np.sqrt(looks / np.arange(1, looks + 1))
    worst = np.max(np.abs(z) / scale, axis=1)
    c = float(np.quantile(worst, 1 - alpha))
    return (c * scale).tolist()


BALANCE_COVARIATES = [
    "trips_30d",
    "trips_90d",
    "spend_90d",
    "recency_days",
    "frequency_trend",
    "digital_events_30d",
]


def strata(frame):
    """Blocks for randomisation: 10 bands of 90-day trips x 3 bands of trip trend."""
    trips = pd.qcut(frame.trips_90d.rank(method="first"), 10, labels=False)
    trend = pd.qcut(frame.frequency_trend.rank(method="first"), 3, labels=False)
    return (trips * 3 + trend).astype(int)


def blocked_assignment(rng, blocks):
    """Equal allocation of every arm inside each block, so pre-period behaviour is balanced by design."""
    arms = np.empty(len(blocks), dtype=object)
    offset = 0
    for block in np.unique(blocks):
        index = np.flatnonzero(blocks == block)
        # Rotate the starting arm so remainders spread across arms instead of always favouring control.
        sequence = np.roll(np.array(ARMS, dtype=object), -offset)
        arms[index] = rng.permutation(np.resize(sequence, len(index)))
        offset = (offset + len(index)) % len(ARMS)
    return arms


def balance(trial):
    """Standardised mean difference of each pre-period covariate, every arm against control."""
    control = trial[trial.arm.eq("Control")]
    rows = []
    for arm, group in trial.groupby("arm"):
        if arm == "Control":
            continue
        for column in BALANCE_COVARIATES:
            pooled = np.sqrt((group[column].var() + control[column].var()) / 2)
            rows.append(
                {
                    "arm": arm,
                    "covariate": column,
                    "smd": float((group[column].mean() - control[column].mean()) / pooled) if pooled else 0.0,
                }
            )
    return rows


def _population(hidden, customer_ids):
    frame = hidden.set_index("customer_id").loc[customer_ids].reset_index(drop=True)
    return Population(frame[[c for c in frame if c.startswith("latent_")]]), frame.created_day.to_numpy()


def simulate(cfg, features, hidden, context, customers):
    """Randomise and simulate realised trial outcomes from the true offer effects."""
    rng = np.random.default_rng(cfg.seed + 20)
    trial = features.copy().reset_index(drop=True)
    population, created_day = _population(hidden, trial.customer_id)
    vehicle = customers.set_index("customer_id").loc[trial.customer_id, "vehicle_class"].to_numpy()
    base = expected_window_trips(population, context, TRIAL_START, 30, created_day)
    later = expected_window_trips(population, context, "2025-07-31", 60, created_day).sum(axis=1).to_numpy()
    tolls = expected_tolls(population, vehicle, 2025)
    n = len(trial)
    trial["stratum"] = strata(trial)
    trial["arm"] = blocked_assignment(rng, trial.stratum.to_numpy())
    trial["treated"] = (trial.arm != "Control").astype(int)
    arm_to_offer = {name: offer for offer, name in OFFER_ARMS.items()}
    trial["offer_id"] = trial.arm.map(arm_to_offer)

    truths = {
        offer: offer_truth(population, base, tolls, offer, cfg.contribution_margin) for offer in OFFER_ARMS
    }
    effect = pd.DataFrame(0.0, index=trial.index, columns=["Peak", "Off-peak", "Weekend"])
    for offer, truth in truths.items():
        mask = trial.offer_id.eq(offer).to_numpy()
        effect.loc[mask, "Peak"] = truth.true_trips_peak.to_numpy()[mask]
        effect.loc[mask, "Off-peak"] = truth.true_trips_offpeak.to_numpy()[mask]
        effect.loc[mask, "Weekend"] = truth.true_trips_weekend.to_numpy()[mask]
    mean = (base + effect).clip(lower=0)

    # Trips arrive in three 10-day blocks so interim looks see cumulative outcomes.
    blocks = {p: rng.poisson(mean[p].to_numpy()[:, None] / 3, size=(n, 3)) for p in PERIODS}
    for k in range(3):
        trial[f"trips_by_day{LOOKS[k]}"] = sum(blocks[p][:, : k + 1].sum(axis=1) for p in PERIODS)
    counts = {p: blocks[p].sum(axis=1) for p in PERIODS}
    trial["trips_peak"], trial["trips_offpeak"], trial["trips_weekend"] = (
        counts["Peak"],
        counts["Off-peak"],
        counts["Weekend"],
    )
    trial["trip_count"] = trial.trips_peak + trial.trips_offpeak + trial.trips_weekend
    revenue = sum(counts[p] * tolls[p].to_numpy() for p in PERIODS)
    mu = base.sum(axis=1).to_numpy()
    avg_toll = np.where(
        trial.trip_count > 0, revenue / np.maximum(trial.trip_count, 1), tolls["Off-peak"].to_numpy()
    )

    cost = np.zeros(n)
    offer = trial.offer_id.fillna("").to_numpy()
    spend_threshold = np.maximum(25.0, 5 * np.ceil(1.3 * (base * tolls).sum(axis=1).to_numpy() / 5))
    reached = np.zeros(n, dtype=bool)
    cost += np.where(offer == "rush_hour_25", 0.25 * counts["Peak"] * tolls["Peak"].to_numpy(), 0)
    cost += np.where(offer == "offpeak_15", 0.15 * counts["Off-peak"] * tolls["Off-peak"].to_numpy(), 0)
    cost += np.where(offer == "pct_10", 0.10 * revenue, 0)
    cost += np.where(offer == "weekend_20", 0.20 * counts["Weekend"] * tolls["Weekend"].to_numpy(), 0)
    spend_hit = revenue >= spend_threshold
    cost += np.where((offer == "spend_10") & spend_hit, 10.0, 0)
    free = trial.trip_count.to_numpy() >= 5
    cost += np.where((offer == "free_trip") & free, avg_toll, 0)
    excess = np.maximum(counts["Off-peak"] * tolls["Off-peak"].to_numpy() - 30.0, 0)
    cost += np.where(offer == "offpeak_pass", excess, 0)
    cost += np.where(offer == "loyalty_500", 5.0, 0) + np.where(offer == "loyalty_1500", 15.0, 0)
    cost += 0.35 * trial.treated.to_numpy()
    reached |= (offer == "spend_10") & spend_hit
    reached |= (offer == "free_trip") & free
    reached |= (offer == "offpeak_pass") & (excess > 0)

    trial["incentive_cost"] = cost
    trial["gross_contribution"] = revenue * cfg.contribution_margin
    trial["net_contribution"] = trial.gross_contribution - trial.incentive_cost
    trial["response"] = (trial.trip_count > 0).astype(int)
    a = population.col("latent_digital_affinity")
    s = population.col("latent_sensitivity")
    trial["enrolled"] = trial.treated.to_numpy() * rng.binomial(1, np.clip(0.15 + 0.40 * a + 0.05 * s, 0, 1))
    discount_offer = np.isin(offer, ["rush_hour_25", "offpeak_15", "pct_10", "weekend_20"]) | np.isin(
        offer, list(LOYALTY_OFFERS)
    )
    trial["redeemed"] = trial.enrolled.to_numpy() * np.where(
        discount_offer, trial.response.to_numpy(), reached
    )

    persistence = np.where(np.isin(offer, list(LOYALTY_OFFERS)), 0.40, 0.25)
    retention_effect = np.zeros(n)
    later_effect = np.zeros(n)
    for name, truth in truths.items():
        mask = offer == name
        retention_effect[mask] = truth.true_retention_effect.to_numpy()[mask]
        later_effect[mask] = (2 * persistence * truth.true_incremental_trips.to_numpy())[mask]
    retention_base = 1 - np.exp(-later)
    trial["retained_90d"] = rng.binomial(1, np.clip(retention_base + retention_effect, 0, 1))
    later_trips = rng.poisson(np.maximum(later + later_effect, 0))
    # Price later trips at the customer's expected toll: the in-window average is itself moved by treatment.
    expected_toll = (base * tolls).sum(axis=1).to_numpy() / np.maximum(mu, 1e-9)
    expected_toll = np.where(mu > 1e-9, expected_toll, tolls["Off-peak"].to_numpy())
    trial["trips_days31_90"] = later_trips
    trial["margin_days31_90"] = later_trips * expected_toll * cfg.contribution_margin
    trial["pre_trips_30d"] = trial.trips_30d
    trial["pre_spend_30d"] = trial.spend_30d

    oracle = []
    for name, truth in truths.items():
        frame = truth.copy()
        frame.insert(0, "offer_id", name)
        frame.insert(0, "customer_id", trial.customer_id.to_numpy())
        oracle.append(frame)
    oracle = pd.concat(oracle, ignore_index=True)
    audit = cfg.path("data", "simulation_audit")
    audit.mkdir(parents=True, exist_ok=True)
    oracle.to_parquet(audit / "trial_oracle.parquet", index=False, **PARQUET)
    pd.DataFrame(
        {"customer_id": trial.customer_id, "true_baseline_trips": mu, "true_later_trips": later}
    ).to_parquet(audit / "trial_baseline.parquet", index=False, **PARQUET)

    perm = rng.permutation(n)
    split = np.empty(n, dtype=object)
    split[perm[: int(0.65 * n)]] = "train"
    split[perm[int(0.65 * n) : int(0.8 * n)]] = "validation"
    split[perm[int(0.8 * n) :]] = "test"
    trial["split"] = split
    trial["spend_threshold"] = np.where(offer == "spend_10", spend_threshold, np.nan)
    trial.to_parquet(cfg.path("data", "silver", "fact_campaign_result.parquet"), index=False, **PARQUET)

    start = pd.Timestamp(TRIAL_START)
    treated = trial[trial.treated.eq(1)]
    facts = {
        "fact_offer_exposure": treated[["customer_id", "arm", "offer_id"]].assign(
            exposed_at=start, campaign_id="trial_july"
        ),
        "fact_offer_enrollment": trial.loc[trial.enrolled.eq(1), ["customer_id", "arm", "offer_id"]].assign(
            enrolled_at=start + pd.Timedelta(days=1), campaign_id="trial_july"
        ),
        "fact_offer_redemption": trial.loc[
            trial.redeemed.eq(1), ["customer_id", "arm", "offer_id", "incentive_cost"]
        ].assign(redeemed_at=start + pd.Timedelta(days=19), campaign_id="trial_july"),
        "fact_loyalty_redemption": trial.loc[
            trial.offer_id.isin(LOYALTY_OFFERS) & trial.redeemed.eq(1), ["customer_id", "offer_id"]
        ]
        .assign(
            points_redeemed=lambda x: np.where(x.offer_id.eq("loyalty_1500"), 1500, 500),
            reward_cost=lambda x: np.where(x.offer_id.eq("loyalty_1500"), 15.0, 5.0),
            redeemed_at=start + pd.Timedelta(days=19),
        )
        .rename(columns={"offer_id": "reward_id"}),
    }
    for name, frame in facts.items():
        frame.to_parquet(cfg.path("data", "silver", name + ".parquet"), index=False, **PARQUET)
    return trial


def _sequential(trial, arm, boundaries, comparisons):
    control = trial[trial.arm.eq("Control")]
    group = trial[trial.arm.eq(arm)]
    looks = []
    stop = None
    for k, day in enumerate(LOOKS):
        column = f"trips_by_day{day}"
        stats = cuped(group[column], control[column], group.pre_trips_30d, control.pre_trips_30d, comparisons)
        z = stats["difference"] / stats["se"] if stats["se"] else 0.0
        crossed = abs(z) >= boundaries[k]
        looks.append({"day": day, "z": z, "boundary": boundaries[k], "crossed": bool(crossed)})
        if crossed and stop is None:
            stop = day
    return {"looks": looks, "stopped_at_day": stop}


def analyze(cfg, trial):
    control = trial[trial.arm.eq("Control")]
    comparisons = len(ARMS) - 1
    boundaries = obrien_fleming_boundaries(alpha=0.05 / comparisons)
    results = []
    for offer, arm in OFFER_ARMS.items():
        group = trial[trial.arm.eq(arm)]
        stats = difference(group.response, control.response, comparisons)
        trips_raw = difference(group.trip_count, control.trip_count, comparisons)
        trips_cuped = cuped(
            group.trip_count, control.trip_count, group.pre_trips_30d, control.pre_trips_30d, comparisons
        )
        value_raw = difference(group.net_contribution, control.net_contribution, comparisons)
        value_cuped = cuped(
            group.net_contribution,
            control.net_contribution,
            group.pre_spend_30d,
            control.pre_spend_30d,
            comparisons,
        )
        later = difference(group.margin_days31_90, control.margin_days31_90, comparisons)
        retention = difference(group.retained_90d, control.retained_90d, comparisons)
        stats.update(
            {
                "offer_id": offer,
                "arm": arm,
                "n": len(group),
                "conversion": float(group.response.mean()),
                "relative_lift": stats["difference"] / float(control.response.mean()),
                "enrollment_rate": float(group.enrolled.mean()),
                "redemption_rate": float(group.redeemed.mean()),
                "incremental_trips_per_customer": trips_raw,
                "incremental_trips_cuped": trips_cuped,
                "incremental_net_contribution_per_customer": value_raw,
                "incremental_net_contribution_cuped": value_cuped,
                "incremental_later_margin": later,
                "retention_effect": retention,
                "sequential": _sequential(trial, arm, boundaries, comparisons),
            }
        )
        results.append(stats)

    counts = trial.arm.value_counts().reindex(ARMS).to_numpy()
    expected = len(trial) / len(ARMS)
    statistic = float(((counts - expected) ** 2 / expected).sum())
    control_rate = float(control.response.mean())
    design_baseline = min(max(control_rate, 0.05), 0.90)
    required = sample_size(baseline=design_baseline, mde=0.05, comparisons=comparisons)
    # Achieved minimum detectable effects at 80% power, using the CUPED-residual spread
    # (pre-period correlation is known before launch from historical data).
    z = norm.ppf(1 - 0.05 / (2 * comparisons)) + norm.ppf(0.8)
    n = int(counts.min())

    def achieved(outcome, covariate):
        y, x = control[outcome].to_numpy(float), control[covariate].to_numpy(float)
        theta = np.cov(y, x, ddof=1)[0, 1] / np.var(x, ddof=1)
        return float(z * np.sqrt(2 / n) * np.std(y - theta * x, ddof=1)), float(
            z * np.sqrt(2 / n) * np.std(y, ddof=1)
        )

    mde_trips, mde_trips_raw = achieved("trip_count", "pre_trips_30d")
    mde_value, mde_value_raw = achieved("net_contribution", "pre_spend_30d")
    subgroup = _subgroups(trial, comparisons)
    balance_rows = balance(trial)
    pd.DataFrame(subgroup).to_csv(cfg.path("outputs", "experiment_subgroups.csv"), index=False)
    variance = [r["incremental_trips_cuped"]["variance_reduction"] for r in results]
    result = {
        "unit": "customer",
        "analysis": "Intention to treat; all randomised customers included",
        "arms": ARMS,
        "comparisons": comparisons,
        "design": {
            "primary_metric": "Trips per customer over the 30-day window (CUPED on June trips)",
            "binary_metric": "Travelled at least once in the window",
            "binary_baseline": design_baseline,
            "binary_mde": 0.05,
            "power": 0.80,
            "family_alpha": 0.05,
            "required_per_arm_binary": required,
            "achieved_mde_trips_cuped": mde_trips,
            "achieved_mde_trips_raw": mde_trips_raw,
            "achieved_mde_value_cuped": mde_value,
            "achieved_mde_value_raw": mde_value_raw,
        },
        "required_per_arm": required,
        "actual_per_arm": trial.arm.value_counts().reindex(ARMS).astype(int).to_dict(),
        "powered_for_planned_mde": bool(n >= required),
        "srm_p_value": float(chi2.sf(statistic, len(ARMS) - 1)),
        "randomisation": "Blocked: equal allocation within 30 strata of 90-day trips x trip trend",
        "balance": balance_rows,
        "max_abs_smd": max(abs(r["smd"]) for r in balance_rows),
        "control_conversion": control_rate,
        "cuped_mean_variance_reduction": float(np.mean(variance)),
        "sequential_boundaries": boundaries,
        "results": results,
        "subgroups": subgroup,
        "subgroup_scope": "Exploratory net-contribution effects by pre-treatment group; Benjamini-Hochberg q-values across all subgroup tests.",
        "limitations": "Synthetic trial; normal-approximation intervals. Sequential looks use CUPED trips with simulation-calibrated O'Brien-Fleming boundaries. A separate policy experiment evaluates the constrained allocation.",
    }
    write_json(cfg.path("outputs", "experiment_results.json"), result)
    return result


def _subgroups(trial, comparisons):
    enriched = trial.copy()
    enriched["frequency_group"] = np.select(
        [enriched.trips_90d >= 25, enriched.trips_90d >= 8], ["Frequent", "Regular"], default="Occasional"
    )
    enriched["value_tercile"] = pd.qcut(
        enriched.spend_90d.rank(method="first"), 3, labels=["Low", "Mid", "High"]
    ).astype(str)
    enriched["travel_pattern"] = np.where(enriched.peak_share >= 0.5, "Peak-led", "Other travel")
    enriched["digital_group"] = np.where(
        enriched.digital_events_30d >= enriched.digital_events_30d.median(),
        "Higher engagement",
        "Lower engagement",
    )
    rows = []
    for dimension in ["frequency_group", "value_tercile", "travel_pattern", "digital_group"]:
        for label, g in enriched.groupby(dimension):
            base = g[g.arm.eq("Control")]
            for offer, arm in OFFER_ARMS.items():
                treated = g[g.arm.eq(arm)]
                if min(len(base), len(treated)) < 30:
                    continue
                stats = difference(treated.net_contribution, base.net_contribution, comparisons=1)
                rows.append(
                    {
                        "dimension": dimension,
                        "group": str(label),
                        "offer_id": offer,
                        "arm": arm,
                        "n_treatment": len(treated),
                        "n_control": len(base),
                        **stats,
                    }
                )
    q = benjamini_hochberg([r["p_value"] for r in rows])
    for row, value in zip(rows, q, strict=True):
        row["q_value"] = float(value)
        row["significant_fdr10"] = bool(value <= 0.10)
    return rows


OFFER_PERIODS = dict(zip(OFFER_CATALOG.offer_id, OFFER_CATALOG.period, strict=True))
