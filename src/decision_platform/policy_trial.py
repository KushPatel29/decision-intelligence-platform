"""A fresh randomised test of the optimized policy itself, separate from model training.

October customers are split in half. The optimizer plans for the policy half
with every guardrail scaled to its size; the control half receives nothing.
Outcomes are drawn from the simulator, and the intention-to-treat difference
is compared with what the plan predicted and what the truth says it is worth.
"""

from __future__ import annotations

import numpy as np

from .config import write_json
from .experiments import difference
from .optimization import solve


def policy_trial(cfg, current, truth, frame, capacity, solver="auto"):
    rng = np.random.default_rng(cfg.seed + 810)
    trial = current[["customer_id", "eligible"]].copy()
    trial["arm"] = rng.permutation(np.resize(np.array(["Control", "Optimized policy"]), len(trial)))
    fraction = trial.arm.eq("Optimized policy").mean()
    policy_ids = set(trial.loc[trial.arm.eq("Optimized policy"), "customer_id"])
    pool = frame[frame.customer_id.isin(policy_ids)].copy()
    pool["inventory"] = np.floor(pool.inventory * fraction)
    cells = capacity.copy()
    cells["available_trips"] = cells.available_trips * fraction
    allocation = solve(
        pool,
        cells,
        budget=cfg.budget * fraction,
        campaign_limit=int(cfg.campaign_limit * fraction),
        min_roi=cfg.min_roi,
        solver="highs" if solver == "highs" else "auto",
        points_budget=int(cfg.points_budget * fraction),
    )
    plan = allocation.selected[["customer_id", "offer_id", "objective_value"]]
    trial = trial.merge(plan, on="customer_id", how="left", validate="one_to_one")
    base = truth.drop_duplicates("customer_id").set_index("customer_id").loc[trial.customer_id]
    effects = truth.set_index(["customer_id", "offer_id"])
    exposed = trial.offer_id.notna().to_numpy()
    keys = list(zip(trial.customer_id[exposed], trial.offer_id[exposed], strict=True))
    tau = np.zeros(len(trial))
    cost = np.zeros(len(trial))
    later = np.zeros(len(trial))
    if keys:
        tau[exposed] = effects.loc[keys, "true_incremental_trips"].to_numpy()
        cost[exposed] = effects.loc[keys, "true_cost"].to_numpy()
        later[exposed] = effects.loc[keys, "true_later_margin"].to_numpy()
    toll = base.true_avg_toll.to_numpy()
    trips = rng.poisson(np.maximum(base.true_baseline_trips.to_numpy() + tau, 0))
    trial["trip_count"] = trips
    trial["incentive_cost"] = cost
    trial["net_contribution"] = trips * toll * cfg.contribution_margin - cost
    treated = trial[trial.arm.eq("Optimized policy")]
    control = trial[trial.arm.eq("Control")]
    stats = difference(treated.net_contribution, control.net_contribution, comparisons=1)
    true_effect = float(effects.loc[keys, "true_net_contribution"].sum() / len(treated) if keys else 0.0)
    result = {
        "unit": "customer",
        "assignment": "New October 2025 balanced randomisation, independent seed; intention to treat including "
        "customers the policy chose not to contact",
        "n_policy": len(treated),
        "n_control": len(control),
        "policy_contacts": int(exposed.sum()),
        "planning_constraints_passed": allocation.diagnostics["all_constraints_passed"],
        "planned_spend": allocation.diagnostics["spend"],
        "expected_spend": float(cost.sum()),
        "predicted_effect_per_customer": float(allocation.selected.net_contribution.sum() / len(treated)),
        "true_effect_per_customer": true_effect,
        "incremental_net_contribution_per_customer": stats,
        "incremental_trips_per_customer": difference(treated.trip_count, control.trip_count, comparisons=1),
        "limitations": "Guardrails are scaled to the policy half. Only a minority of the policy half is contacted, "
        "so the per-customer effect is diluted and its interval is wide by design. Estimated-cost constraints do "
        "not guarantee realised spend; operational caps still apply.",
    }
    trial.to_csv(cfg.path("outputs", "policy_trial.csv"), index=False)
    write_json(cfg.path("outputs", "policy_trial_results.json"), result)
    return result
