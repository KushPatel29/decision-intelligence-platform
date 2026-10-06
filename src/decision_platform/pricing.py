"""Joint discrete price strategy and incentive optimization with shared capacity.

Price interventions affect baseline demand/revenue; campaign effects remain fixed
at baseline prices. This is an explicit separability assumption, not a fitted
price-by-promotion interaction. No offer-response/price effect is counted twice.
"""

import numpy as np
import pandas as pd
from scipy.optimize import Bounds, LinearConstraint, linprog, milp
from scipy.sparse import coo_matrix, csr_matrix, hstack, vstack

from .config import write_json
from .optimization import constraint_matrix
from .runtime import bounded_operation


def price_options(capacity, scenarios, trips, cutoff, margin=0.72, reserve=0.2):
    historical = trips[trips.timestamp < pd.Timestamp(cutoff)]
    prices = (
        historical.groupby(["zone_id", "period"]).final_charge.mean().rename("baseline_price").reset_index()
    )
    options = (
        capacity[["zone_id", "period", "baseline_forecast", "capacity_trips"]]
        .merge(scenarios, on=["zone_id", "period"], validate="one_to_many")
        .merge(prices, on=["zone_id", "period"], validate="many_to_one")
    )
    options["forecast_trips"] = options.baseline_forecast * options.demand_index / 100
    options["protected_load"] = options.forecast_trips * (1 + reserve)
    options["available_trips"] = options.capacity_trips - options.protected_load
    options["revenue"] = options.baseline_forecast * options.baseline_price * options.revenue_index / 100
    options["baseline_revenue"] = options.baseline_forecast * options.baseline_price
    options["incremental_contribution"] = margin * (options.revenue - options.baseline_revenue)
    # Integral under constant elasticity. Net surplus changes are negative for price increases.
    beta = options.elasticity.to_numpy()
    multiplier = (1 + options.price_change).to_numpy()
    integral = np.where(
        abs(beta + 1) < 1e-8,
        np.log(multiplier),
        (multiplier ** (beta + 1) - 1) / np.where(abs(beta + 1) < 1e-8, 1, beta + 1),
    )
    options["consumer_surplus_change"] = -options.baseline_revenue * integral
    options["eligible"] = options.available_trips >= -1e-8
    return options


def _lp_guided(objective, a, lower, upper, bounds, n, keep_rc=2.0, time_limit=90):
    """LP relaxation, then an exact MIP over every price option and the campaign variables still in play.

    Campaign variables at zero in the LP whose reduced cost exceeds `keep_rc` dollars are dropped; the gap to
    the LP bound is reported so the reduction's cost is visible.
    """
    from .optimization import _quiet

    equality = lower > -np.inf
    with _quiet():
        lp = linprog(
            -objective,
            A_ub=a[~equality],
            b_ub=upper[~equality],
            A_eq=a[equality],
            b_eq=upper[equality],
            bounds=np.column_stack([np.zeros(len(bounds)), bounds]),
            method="highs",
        )
    if lp.status != 0:
        raise RuntimeError(f"Joint pricing LP failed: {lp.message}")
    reduced = np.asarray(lp.lower.marginals)
    keep = np.ones(len(objective), dtype=bool)
    keep[:n] = (lp.x[:n] > 1e-9) | (reduced[:n] <= keep_rc)
    keep &= bounds > 0
    keep[n:] = True
    sub = a[:, keep]
    with _quiet():
        result = milp(
            -objective[keep],
            integrality=np.ones(int(keep.sum())),
            bounds=Bounds(np.zeros(int(keep.sum())), bounds[keep]),
            constraints=LinearConstraint(sub, lower, upper),
            options={"time_limit": time_limit, "mip_rel_gap": 1e-5},
        )
    if result.x is None:
        raise RuntimeError("No feasible joint pricing plan")
    selected = np.zeros(len(objective), dtype=bool)
    selected[np.flatnonzero(keep)[result.x > 0.5]] = True
    bound = float(-lp.fun)
    gap = (bound - float(objective[selected].sum())) / max(abs(bound), 1e-9)
    return selected, gap, bound, int(keep[:n].sum())


@bounded_operation
def optimize_prices(
    options,
    candidates,
    budget=1600.0,
    contacts=180,
    roi=0.15,
    points=35000,
    solver="auto",
    surplus_weight=0.0,
):
    """Choose one effective price per zone/period and the campaign contacts in a single MIP."""
    from .optimization import GUROBI_LICENCE_LIMIT, _period_usage, _solve_gurobi, validate_inputs

    cells = options.drop_duplicates(["zone_id", "period"])[["zone_id", "period", "capacity_trips"]].copy()
    cells["available_trips"] = cells.capacity_trips
    cells["baseline_over_capacity"] = False
    validate_inputs(candidates, cells, budget, contacts, roi, solver, points)
    if not np.isfinite(surplus_weight) or not 0 <= surplus_weight <= 1:
        raise ValueError("Surplus weight must be between zero and one")
    options = options.reset_index(drop=True)
    candidates = candidates.reset_index(drop=True)
    for _, g in options.groupby(["zone_id", "period"]):
        if not g.eligible.any():
            raise ValueError("No price strategy fits capacity in a zone/period")
    n, k = len(candidates), len(options)
    matrix, upper, names = constraint_matrix(candidates, cells, budget, contacts, roi, points)
    row_of = {name: i for i, name in enumerate(names)}
    price_rows, price_cols, price_vals = [], [], []
    for j, option in enumerate(options.itertuples()):
        name = f"capacity:{option.zone_id}:{option.period}"
        if name not in row_of:
            raise ValueError("Price option has no capacity row")
        price_rows.append(row_of[name])
        price_cols.append(j)
        price_vals.append(option.protected_load)
    price_block = coo_matrix((price_vals, (price_rows, price_cols)), shape=(len(upper), k))
    groups = list(options.groupby(["zone_id", "period"]).indices.values())
    pick_rows = np.concatenate([np.full(len(g), i) for i, g in enumerate(groups)])
    pick_cols = np.concatenate(groups)
    pick = coo_matrix((np.ones(len(pick_cols)), (pick_rows, pick_cols)), shape=(len(groups), k))
    a = vstack([hstack([matrix, price_block]), hstack([csr_matrix((len(groups), n)), pick])]).tocsr()
    lower = np.r_[np.full(len(upper), -np.inf), np.ones(len(groups))]
    upper = np.r_[upper, np.ones(len(groups))]
    objective = np.r_[
        candidates.objective_value.to_numpy(float),
        (options.incremental_contribution + surplus_weight * options.consumer_surplus_change).to_numpy(float),
    ]
    bounds = np.r_[candidates.eligible.astype(float), options.eligible.astype(float)]
    selected, gap, actual = None, None, "HiGHS"
    small = n + k <= GUROBI_LICENCE_LIMIT and a.shape[0] + len(groups) <= GUROBI_LICENCE_LIMIT
    if solver == "gurobi" or (solver == "auto" and small):
        try:
            # Equalities as paired inequalities so one solver interface serves both problems.
            stacked = vstack([a, -a[len(upper) - len(groups) :]]).tocsr()
            limits = np.r_[upper, -lower[len(upper) - len(groups) :]]
            selected, gap, _, _ = _solve_gurobi(objective, stacked, limits, bounds, 30)
            actual = "Gurobi"
        except Exception as exc:
            if (
                solver == "gurobi"
                or not isinstance(exc, ImportError)
                and exc.__class__.__name__ != "GurobiError"
            ):
                raise
    if selected is None:
        selected, gap, lp_bound, kept = _lp_guided(objective, a, lower, upper, bounds, n)
        actual = f"HiGHS (LP-guided, {kept:,} campaign variables kept)"
    lhs = a @ selected.astype(float)
    if np.any(lhs > upper + 1e-6) or np.any(lhs < lower - 1e-6):
        raise RuntimeError("Joint pricing constraint violation")
    chosen = options[selected[n:]].copy()
    campaign = candidates[selected[:n]].copy()
    usage = _period_usage(campaign)
    added = {}
    for period, values in usage.items():
        for zone, value in zip(campaign.zone_id, values, strict=True):
            added[(zone, period)] = added.get((zone, period), 0.0) + value
    chosen["campaign_trips"] = [added.get((r.zone_id, r.period), 0.0) for r in chosen.itertuples()]
    chosen["remaining_with_reserve"] = chosen.available_trips - chosen.campaign_trips
    summary = {
        "solver": actual,
        "gap": gap,
        "gap_definition": "Relative distance to the LP bound of the full joint problem",
        "all_constraints_passed": True,
        "price_contribution": float(chosen.incremental_contribution.sum()),
        "campaign_net_contribution": float(campaign.net_contribution.sum()),
        "campaign_objective": float(campaign.objective_value.sum()),
        "consumer_surplus_change": float(chosen.consumer_surplus_change.sum()),
        "contacts": len(campaign),
        "spend": float(campaign.cost.sum()),
        "surplus_weight": surplus_weight,
        "price_changes": int((chosen["price_change"] != 0).sum()) if "price_change" in chosen else 0,
        "assumptions": "Constant elasticity within the tested range; campaign effects estimated at baseline prices "
        "(no fitted price-by-offer interaction). Consumer surplus is illustrative, not measured welfare.",
    }
    return chosen, campaign, summary


def build_pricing(cfg, scenarios, capacity, trips, solver):
    options = price_options(capacity, scenarios, trips, cfg.decision_date, cfg.contribution_margin)
    candidates = pd.read_csv(cfg.path("outputs", "joint_candidates.csv"))
    chosen, campaign, summary = optimize_prices(
        options, candidates, cfg.budget, cfg.campaign_limit, cfg.min_roi, cfg.points_budget, solver=solver
    )
    options.to_csv(cfg.path("outputs", "price_options.csv"), index=False)
    chosen.to_csv(cfg.path("outputs", "price_allocation.csv"), index=False)
    campaign.to_csv(cfg.path("outputs", "price_campaign_allocation.csv"), index=False)
    write_json(cfg.path("outputs", "price_optimization.json"), summary)
    return summary
