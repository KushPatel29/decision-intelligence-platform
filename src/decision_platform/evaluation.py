"""Score every targeting policy against the simulator's ground truth.

A real operator can only estimate a campaign's incremental value. A simulation
can do better: it knows each customer's true response to every offer, so each
plan can be scored by the value it would really create. The comparison set:

- naive plans a team could run without causal models (random, propensity,
  RFM playbook);
- a greedy uplift heuristic;
- the production mixed-integer plan and its risk-averse (robust) variant;
- the oracle optimum: the same MIP solved on the true effects, an upper bound
  no real system can reach.

The truth is read here and nowhere upstream of a decision.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from .config import PARQUET, write_json
from .optimization import candidates, solve
from .policy import baseline_plans, summarise
from .simulation import OFFERS, Population, expected_tolls, expected_window_trips, offer_truth


def decision_truth(cfg, current, hidden, context, customers):
    """True 30-day effects of every offer for the October decision population."""
    frame = hidden.set_index("customer_id").loc[current.customer_id].reset_index()
    population = Population(frame[[c for c in frame if c.startswith("latent_")]])
    vehicle = customers.set_index("customer_id").loc[current.customer_id, "vehicle_class"].to_numpy()
    base = expected_window_trips(population, context, cfg.decision_date, 30, frame.created_day.to_numpy())
    tolls = expected_tolls(population, vehicle, 2025)
    parts = []
    for offer in OFFERS:
        truth = offer_truth(population, base, tolls, offer, cfg.contribution_margin)
        truth.insert(0, "offer_id", offer)
        truth.insert(0, "customer_id", current.customer_id.to_numpy())
        parts.append(truth)
    truth = pd.concat(parts, ignore_index=True)
    mu = base.sum(axis=1).to_numpy()
    avg_toll = np.where(
        mu > 0, (base * tolls).sum(axis=1).to_numpy() / np.maximum(mu, 1e-9), tolls["Off-peak"]
    )
    truth["true_baseline_trips"] = np.tile(mu, len(OFFERS))
    # The same relief value the planner uses, applied to the true rush-hour trips.
    truth["true_relief_value"] = cfg.relief_value * truth.true_trips_peak
    truth["true_value"] = truth.true_value + truth.true_relief_value
    truth["true_avg_toll"] = np.tile(avg_toll, len(OFFERS))
    return truth


def oracle_plan(cfg, everything, truth, capacity):
    """The same MIP with true effects in place of estimates: the achievable ceiling."""
    frame = everything.drop(columns=[c for c in everything if c.startswith("true_")]).merge(
        truth, on=["customer_id", "offer_id"], validate="one_to_one"
    )
    frame["cost"] = frame.true_cost
    frame["net_contribution"] = frame.true_net_contribution
    frame["objective_value"] = frame.true_value
    frame["trips_peak"] = frame.true_trips_peak
    frame["trips_offpeak"] = frame.true_trips_offpeak
    frame["trips_weekend"] = frame.true_trips_weekend
    frame["incremental_trips"] = frame.true_incremental_trips
    frame = frame[(frame.objective_value > 0) | (frame.trips_peak < 0)].reset_index(drop=True)
    return solve(
        frame,
        capacity,
        budget=cfg.budget,
        campaign_limit=cfg.campaign_limit,
        min_roi=cfg.min_roi,
        solver="highs",
        points_budget=cfg.points_budget,
    )


def evaluate_policies(cfg, current, uplift, offers, capacity, production, robust, hidden, context, customers):
    truth = decision_truth(cfg, current, hidden, context, customers)
    truth.to_parquet(cfg.path("data", "simulation_audit", "decision_truth.parquet"), index=False, **PARQUET)
    everything = candidates(cfg, current, uplift, offers, keep_all=True)
    useful = candidates(cfg, current, uplift, offers)
    plans = baseline_plans(cfg, everything, useful, capacity, cfg.seed + 5)
    plans["Optimized (MIP)"] = production
    plans["Optimized, risk-averse (MIP on LCB)"] = robust
    oracle = oracle_plan(cfg, everything, truth, capacity)
    plans["Oracle optimum (true effects)"] = oracle.selected
    summary = summarise(plans, truth)
    ceiling = float(summary.loc[summary.policy.eq("Oracle optimum (true effects)"), "true_value"].iloc[0])
    summary["share_of_oracle"] = summary.true_value / ceiling if ceiling else np.nan
    summary["winners_curse"] = summary.predicted_value - summary.true_value
    summary.loc[summary.policy.eq("Oracle optimum (true effects)"), "winners_curse"] = np.nan
    summary.to_csv(cfg.path("outputs", "policy_comparison.csv"), index=False)

    # Does travel propensity find the customers whom an offer actually moves?
    eligible = current[current.eligible]
    best_true = truth.groupby("customer_id").true_value.max().reindex(eligible.customer_id).to_numpy()
    best_model = uplift.groupby("customer_id").value_uplift.max().reindex(eligible.customer_id).to_numpy()
    propensity = eligible.propensity_probability.to_numpy()
    top = propensity >= np.quantile(propensity, 0.8)
    insight = {
        "spearman_propensity_vs_true_best_value": float(spearmanr(propensity, best_true).statistic),
        "spearman_model_vs_true_best_value": float(spearmanr(best_model, best_true).statistic),
        "top_quintile_propensity_mean_true_value": float(best_true[top].mean()),
        "other_customers_mean_true_value": float(best_true[~top].mean()),
        "eligible_customers_with_positive_true_value": int((best_true > 0).sum()),
        "eligible_customers": int(len(eligible)),
    }
    offer_mix = {
        name: plan.offer_id.value_counts().reindex(OFFERS, fill_value=0).astype(int).to_dict()
        for name, plan in plans.items()
    }
    pd.DataFrame(offer_mix).rename_axis("offer_id").reset_index().to_csv(
        cfg.path("outputs", "policy_offer_mix.csv"), index=False
    )
    selected = truth.set_index(["customer_id", "offer_id"]).loc[
        list(zip(production.customer_id, production.offer_id, strict=True))
    ]
    calibration = pd.DataFrame(
        {
            "predicted_value": production.objective_value.to_numpy(),
            "true_value": selected.true_value.to_numpy(),
            "value_sd": production.value_uplift_sd.to_numpy(),
            "offer_id": production.offer_id.to_numpy(),
        }
    )
    calibration["decile"] = pd.qcut(calibration.predicted_value.rank(method="first"), 10, labels=False) + 1
    deciles = (
        calibration.groupby("decile")
        .agg(
            predicted=("predicted_value", "mean"),
            actual=("true_value", "mean"),
            customers=("true_value", "size"),
        )
        .reset_index()
    )
    deciles.to_csv(cfg.path("outputs", "value_calibration.csv"), index=False)
    result = {
        "policies": summary.astype(object).where(summary.notna(), None).to_dict(orient="records"),
        "oracle_ceiling": ceiling,
        "propensity_insight": insight,
        "production_true_value": float(selected.true_value.sum()),
        "production_predicted_value": float(production.objective_value.sum()),
        "scope": "Simulation-only evaluation. Every plan obeys the same guardrails; value is the simulator's true "
        "expected 30-day net contribution plus discounted days 31-90 margin for the chosen customer-offer pairs.",
    }
    write_json(cfg.path("outputs", "policy_value.json"), result)
    return result, truth
