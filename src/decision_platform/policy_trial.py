"""Fresh randomized constrained-policy simulation, distinct from model training."""

import numpy as np
import pandas as pd

from .config import write_json
from .experiments import difference
from .optimization import solve


def policy_trial(cfg, current, hidden, capacity, solver="auto"):
    rng = np.random.default_rng(cfg.seed + 810)
    trial = current[["customer_id", "trips_30d", "avg_toll"]].merge(
        hidden, on="customer_id", validate="one_to_one"
    )
    assignment = rng.permutation(np.resize(np.array(["Control", "Optimized policy"]), len(trial)))
    trial["arm"] = assignment
    candidates = pd.read_csv(cfg.path("outputs", "joint_candidates.csv"))
    eligible_ids = trial.loc[trial.arm.eq("Optimized policy"), "customer_id"]
    candidate = candidates[candidates.customer_id.isin(eligible_ids)].copy()
    fraction = len(eligible_ids) / len(trial)
    candidate["inventory"] = np.floor(candidate.inventory * fraction)
    cells = capacity.copy()
    cells["available_trips"] *= fraction
    allocation = solve(
        candidate,
        cells,
        cfg.budget * fraction,
        int(cfg.campaign_limit * fraction),
        cfg.min_roi,
        solver,
        points_budget=int(35000 * fraction),
    )
    trial = trial.merge(
        allocation.selected[["customer_id", "offer_id"]], on="customer_id", how="left", validate="one_to_one"
    )
    exposed = trial.offer_id.notna().to_numpy()
    factor = np.where(
        trial.offer_id.eq("loyalty_500"), 0.72, np.where(trial.offer_id.eq("weekend_20"), 1.08, 1.0)
    )
    mean = 0.20 + np.clip(trial.trips_30d.to_numpy() * 0.22, 0, 9)
    effect = (
        (0.6 + 2.3 * trial.latent_sensitivity.to_numpy() / 2)
        * (0.6 + 0.4 * trial.latent_digital_affinity.to_numpy())
        * factor
    )
    trial["trip_count"] = rng.poisson(mean + exposed * effect)
    prices = trial.avg_toll.clip(lower=8).to_numpy()
    discount = np.where(
        trial.offer_id.eq("weekend_20"), 0.20, np.where(trial.offer_id.eq("offpeak_15"), 0.15, 0.0)
    )
    trial["cost"] = (
        np.where(trial.offer_id.eq("loyalty_500"), 5.0, trial.trip_count * prices * discount) + exposed * 0.35
    )
    trial["net_contribution"] = trial.trip_count * prices * cfg.contribution_margin - trial.cost
    trial = trial.drop(columns=[c for c in trial if c.startswith("latent_")])
    treated = trial[trial.arm.eq("Optimized policy")]
    control = trial[trial.arm.eq("Control")]
    stats = difference(treated.net_contribution, control.net_contribution, comparisons=1)
    result = {
        "unit": "customer",
        "assignment": "New October 2025 balanced customer randomization, independent simulation seed; intention to treat including uncontacted customers",
        "n_policy": len(treated),
        "n_control": len(control),
        "policy_contacts": len(allocation.selected),
        "planning_constraints_passed": allocation.diagnostics["all_constraints_passed"],
        "expected_spend": allocation.diagnostics["spend"],
        "realized_synthetic_spend": float(treated.cost.sum()),
        "incremental_net_contribution_per_customer": stats,
        "incremental_trips_per_customer": difference(treated.trip_count, control.trip_count, comparisons=1),
        "limitations": "Pilot uncertainty may be wide because few customers receive offers. Budget, inventory, contact, points and campaign headroom scaled to the policy half. Estimated-cost constraints do not guarantee realized stochastic spending or traffic; operational caps still required.",
    }
    trial.to_csv(cfg.path("outputs", "policy_trial.csv"), index=False)
    write_json(cfg.path("outputs", "policy_trial_results.json"), result)
    return result
