"""Joint discrete price strategy and incentive optimization with shared capacity.

Price interventions affect baseline demand/revenue; campaign effects remain fixed
at baseline prices. This is an explicit separability assumption, not a fitted
price-by-promotion interaction. No offer-response/price effect is counted twice.
"""

import numpy as np
import pandas as pd
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import csr_matrix

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
    from .optimization import validate_inputs

    cells = options.drop_duplicates(["zone_id", "period"])[["zone_id", "period", "capacity_trips"]].copy()
    cells["available_trips"] = cells.capacity_trips
    cells["baseline_over_capacity"] = False
    validate_inputs(candidates, cells, budget, contacts, roi, solver, points)
    if not np.isfinite(surplus_weight) or not 0 <= surplus_weight <= 1:
        raise ValueError("Surplus weight must be between zero and one")
    options = options.reset_index(drop=True)
    for _, g in options.groupby(["zone_id", "period"]):
        if not g.eligible.any():
            raise ValueError("No price strategy fits capacity in a zone/period")
    n = len(candidates)
    k = len(options)
    matrix, upper, names = constraint_matrix(candidates, cells, budget, contacts, roi, points)
    rows = [np.r_[row, np.zeros(k)] for row in matrix.toarray()]
    lower = [-np.inf] * len(rows)
    upper = upper.tolist()
    for i, name in enumerate(names):
        if name.startswith("capacity:"):
            _, zone, period = name.split(":", 2)
            mask = options.zone_id.eq(int(zone)) & options.period.eq(period)
            rows[i][n:] = np.where(mask, options.protected_load, 0)
    for (zone, period), g in options.groupby(["zone_id", "period"]):
        row = np.zeros(n + k)
        row[n + g.index.to_numpy()] = 1
        rows.append(row)
        lower.append(1.0)
        upper.append(1.0)
    objective = np.r_[
        candidates.objective_value,
        options.incremental_contribution + surplus_weight * options.consumer_surplus_change,
    ]
    bounds = np.r_[candidates.eligible.astype(float), options.eligible.astype(float)]
    a = csr_matrix(np.asarray(rows))
    actual = "HiGHS (SciPy)"
    gap = None
    selected = None
    if solver in ("auto", "gurobi"):
        try:
            import gurobipy as gp

            with gp.Env(empty=True) as env:
                env.setParam("OutputFlag", 0)
                env.start()
                with gp.Model("joint_price_campaign", env=env) as model:
                    x = model.addMVar(n + k, vtype=gp.GRB.BINARY, ub=bounds)
                    model.setObjective(objective @ x, gp.GRB.MAXIMIZE)
                    for row, lo, hi in zip(rows, lower, upper):
                        if lo == hi:
                            model.addConstr(row @ x == hi)
                        else:
                            model.addConstr(row @ x <= hi)
                    model.Params.TimeLimit = 30
                    model.Params.MIPGap = 0.001
                    model.optimize()
                    if model.SolCount < 1:
                        raise RuntimeError("No feasible joint pricing plan")
                    selected = x.X > 0.5
                    gap = float(model.MIPGap)
                    actual = "Gurobi"
        except Exception as exc:
            if (
                solver == "gurobi"
                or not isinstance(exc, ImportError)
                and exc.__class__.__name__ != "GurobiError"
            ):
                raise
    if selected is None:
        result = milp(
            -objective,
            integrality=np.ones(n + k),
            bounds=Bounds(np.zeros(n + k), bounds),
            constraints=LinearConstraint(a, lower, upper),
            options={"time_limit": 30, "mip_rel_gap": 0.001},
        )
        if result.x is None:
            raise RuntimeError("No feasible joint pricing plan")
        selected = result.x > 0.5
        gap = float(result.mip_gap)
    lhs = a @ selected.astype(float)
    if np.any(lhs > np.asarray(upper) + 1e-6) or np.any(lhs < np.asarray(lower) - 1e-6):
        raise RuntimeError("Joint pricing constraint violation")
    chosen = options[selected[n:]].copy()
    campaign = candidates[selected[:n]].copy()
    additions = campaign.groupby(["zone_id", "period"]).incremental_trips.sum()
    chosen["campaign_trips"] = [additions.get((r.zone_id, r.period), 0.0) for r in chosen.itertuples()]
    chosen["remaining_with_reserve"] = chosen.available_trips - chosen.campaign_trips
    summary = {
        "solver": actual,
        "gap": gap,
        "all_constraints_passed": True,
        "price_contribution": float(chosen.incremental_contribution.sum()),
        "campaign_net_contribution": float(campaign.net_contribution.sum()),
        "consumer_surplus_change": float(chosen.consumer_surplus_change.sum()),
        "contacts": len(campaign),
        "spend": float(campaign.cost.sum()),
        "surplus_weight": surplus_weight,
        "assumptions": "Constant elasticity; baseline-price promotion effects held fixed; no estimated price/offer interactions. Surplus is illustrative, not a measured welfare outcome.",
    }
    return chosen, campaign, summary


def build_pricing(cfg, scenarios, capacity, trips, solver):
    options = price_options(capacity, scenarios, trips, cfg.decision_date, cfg.contribution_margin)
    candidates = pd.read_csv(cfg.path("outputs", "joint_candidates.csv"))
    chosen, campaign, summary = optimize_prices(
        options, candidates, cfg.budget, cfg.campaign_limit, cfg.min_roi, solver=solver
    )
    options.to_csv(cfg.path("outputs", "price_options.csv"), index=False)
    chosen.to_csv(cfg.path("outputs", "price_allocation.csv"), index=False)
    campaign.to_csv(cfg.path("outputs", "price_campaign_allocation.csv"), index=False)
    write_json(cfg.path("outputs", "price_optimization.json"), summary)
    return summary
