"""Targeting baselines under the same guardrails, and held-out offer-rule evaluation.

Every baseline spends the same budget, contacts, points, inventory and
capacity as the optimizer, so differences come from *who* gets *which* offer.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import write_json
from .optimization import PERIOD_COLUMNS
from .simulation import OFFER_ARMS


def greedy(frame, capacity, limits, order, per_item_roi=False):
    """Accept candidates in `order` while every guardrail still holds; one offer per customer."""
    budget, contacts = limits["budget"], limits["campaign_limit"]
    points_left = limits.get("points_budget") or np.inf
    roi = limits.get("min_roi", 0.0)
    headroom = {(int(c.zone_id), c.period): float(c.available_trips) for c in capacity.itertuples()}
    inventory = frame.groupby("offer_id").inventory.first().to_dict()
    cost = frame.cost.to_numpy(float)
    net = frame.net_contribution.to_numpy(float)
    points = frame.points.to_numpy(float)
    zone = frame.zone_id.to_numpy()
    offer = frame.offer_id.to_numpy()
    customer = frame.customer_id.to_numpy()
    usage = {period: frame[column].to_numpy(float) for period, column in PERIOD_COLUMNS.items()}
    spent, used, chosen, seen = 0.0, 0, [], set()
    for i in order:
        if used >= contacts:
            break
        if customer[i] in seen or spent + cost[i] > budget + 1e-9 or points[i] > points_left:
            continue
        if inventory[offer[i]] < 1 or (per_item_roi and net[i] < roi * cost[i]):
            continue
        if any(usage[p][i] > 0 and usage[p][i] > headroom[(int(zone[i]), p)] + 1e-9 for p in usage):
            continue
        for p in usage:
            headroom[(int(zone[i]), p)] -= usage[p][i]
        spent += cost[i]
        points_left -= points[i]
        inventory[offer[i]] -= 1
        used += 1
        seen.add(customer[i])
        chosen.append(i)
    return frame.iloc[chosen].copy()


SEGMENT_PLAYBOOK = {
    "Champions": "weekend_20",
    "Loyal": "pct_10",
    "At risk": "loyalty_500",
    "Occasional": "free_trip",
    "New": "free_trip",
    "Dormant": "offpeak_15",
}


def baseline_plans(cfg, everything, useful, capacity, seed):
    """Plans a team could run without causal models, plus a model-based greedy heuristic."""
    limits = dict(
        budget=cfg.budget,
        campaign_limit=cfg.campaign_limit,
        min_roi=cfg.min_roi,
        points_budget=cfg.points_budget,
    )
    rng = np.random.default_rng(seed)
    plans = {}
    shuffled = rng.permutation(len(everything))
    plans["Random targeting"] = greedy(everything, capacity, limits, shuffled)
    blanket = everything[everything.offer_id.eq("pct_10")]
    order = blanket.sort_values("propensity_probability", ascending=False, kind="stable").index
    plans["Propensity: 10% off top travellers"] = greedy(everything, capacity, limits, order)
    playbook = everything[everything.offer_id.eq(everything.rfm_segment.map(SEGMENT_PLAYBOOK))]
    priority = {"At risk": 0, "Champions": 1, "Loyal": 2, "Occasional": 3, "New": 4, "Dormant": 5}
    order = (
        playbook.assign(rank=playbook.rfm_segment.map(priority))
        .sort_values(["rank", "clv_12m"], ascending=[True, False], kind="stable")
        .index
    )
    plans["RFM segment playbook"] = greedy(everything, capacity, limits, order)
    density = useful.objective_value / useful.cost
    order = density.sort_values(ascending=False, kind="stable").index
    plans["Uplift ranking (greedy)"] = greedy(useful, capacity, limits, order, per_item_roi=True)
    return plans


def heldout_offer_rule(cfg, scores):
    """Inverse-propensity estimate of 'give each customer its best modelled offer' on untouched customers."""
    arms = {offer: arm for offer, arm in OFFER_ARMS.items()}
    columns = [offer + "_value" for offer in arms]
    values = scores[columns].to_numpy()
    best = np.array(list(arms.values()))[values.argmax(axis=1)]
    recommended = np.where(values.max(axis=1) > 0, best, "Control")
    k = len(arms) + 1  # Every arm, control included, was assigned with probability 1/k.
    policy = np.where(scores.arm.eq(recommended), scores.net_contribution * k, 0.0)
    control = np.where(scores.arm.eq("Control"), scores.net_contribution * k, 0.0)
    delta = policy - control
    rng = np.random.default_rng(cfg.seed + 73)
    bootstrap = np.array([rng.choice(delta, len(delta), replace=True).mean() for _ in range(1000)])
    result = {
        "n_test": len(scores),
        "incremental_contribution_per_customer": float(delta.mean()),
        "ci_low": float(np.quantile(bootstrap, 0.025)),
        "ci_high": float(np.quantile(bootstrap, 0.975)),
        "bootstrap_replicates": 1000,
        "share_recommended_control": float((recommended == "Control").mean()),
        "policy": "Each held-out customer gets the offer with the highest positive modelled value; otherwise control",
        "interpretation": "Inverse-propensity-weighted estimate on randomised customers the models never saw. "
        "It is the estimate a real team could compute; the simulation's oracle evaluation sits alongside it.",
    }
    write_json(cfg.path("outputs", "policy_evaluation.json"), result)
    return result


def summarise(plans, truth):
    rows = []
    keyed = truth.set_index(["customer_id", "offer_id"])
    for name, plan in plans.items():
        actual = (
            keyed.loc[list(zip(plan.customer_id, plan.offer_id, strict=True))]
            if len(plan)
            else keyed.iloc[:0]
        )
        rows.append(
            {
                "policy": name,
                "contacts": len(plan),
                "predicted_value": float((plan.value_uplift + plan.later_value_uplift).sum())
                if len(plan)
                else 0.0,
                "planned_spend": float(plan.cost.sum()) if len(plan) else 0.0,
                "true_value": float(actual.true_value.sum()),
                "true_net_contribution_30d": float(actual.true_net_contribution.sum()),
                "true_spend": float(actual.true_cost.sum()),
                "true_incremental_trips": float(actual.true_incremental_trips.sum()),
                "true_peak_trips": float(actual.true_trips_peak.sum()),
                "customers_losing_money": int((actual.true_value < 0).sum()),
            }
        )
    return pd.DataFrame(rows)
