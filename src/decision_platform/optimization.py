"""Campaign allocation: a mixed-integer program over the whole eligible population.

Decision: x[c, o] = 1 if customer c receives offer o. Maximise expected
incremental value (30-day net contribution after incentive costs, plus the
discounted days 31-90 margin effect) subject to the incentive budget, a contact
limit, a portfolio net-ROI floor, a loyalty-points liability cap, offer
inventory, one offer per customer and protected roadway capacity in every zone
and travel period. Capacity coefficients are signed: an off-peak offer that
moves a commuter out of the peak frees peak capacity.

HiGHS solves the full problem. The LP relaxation supplies shadow prices (what
one more dollar, contact, point or trip of capacity is worth) and reduced
costs. Reduced-cost fixing then removes every variable that provably cannot
appear in a better plan, which shrinks the problem enough for the size-limited
Gurobi licence to certify the HiGHS plan as globally optimal.
"""

from __future__ import annotations

import time
from contextlib import nullcontext
from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.optimize import Bounds, LinearConstraint, linprog, milp
from scipy.sparse import coo_matrix

from .config import write_json
from .runtime import bounded_operation

PERIOD_COLUMNS = {"Peak": "trips_peak", "Off-peak": "trips_offpeak", "Weekend": "trips_weekend"}
GUROBI_LICENCE_LIMIT = 2000


@dataclass
class Allocation:
    selected: pd.DataFrame
    solver: str
    status: str
    objective: float
    gap: float | None
    diagnostics: dict


def candidates(cfg, current, uplift, offers, risk_aversion=0.0, keep_all=False):
    """Eligible customer-offer pairs with model-estimated economics.

    `risk_aversion` subtracts that many bootstrap standard deviations from the
    30-day value estimate, in both the objective and the ROI floor. `keep_all`
    keeps pairs with no modelled upside (rule-based baselines need them).
    """
    customer_columns = [
        "customer_id",
        "eligible",
        "home_zone",
        "avg_toll",
        "clv_12m",
        "rfm_segment",
        "propensity_probability",
        "churn_probability",
        "trips_90d",
    ]
    frame = uplift.merge(current[customer_columns], on="customer_id", validate="many_to_one")
    frame = frame.merge(offers, on="offer_id", validate="many_to_one")
    frame = frame[frame.eligible].copy()
    frame["zone_id"] = frame.home_zone.astype(int)
    frame["cost"] = frame.expected_cost.clip(lower=0.35)
    frame["value_lcb"] = frame.value_uplift - frame.value_uplift_sd
    frame["net_contribution"] = frame.value_uplift - risk_aversion * frame.value_uplift_sd
    frame["incremental_gross_contribution"] = frame.value_uplift + frame.cost
    frame["relief_value"] = cfg.relief_value * frame.trips_peak
    frame["objective_value"] = frame.net_contribution + frame.later_value_uplift + frame.relief_value
    frame["points"] = frame.points.astype(int)
    # Pairs with no upside are never chosen in an optimal plan unless they free capacity.
    useful = (frame.objective_value > 0) | (frame[list(PERIOD_COLUMNS.values())] < 0).any(axis=1)
    frame = (
        frame[useful | keep_all]
        .sort_values(["customer_id", "offer_id"], kind="stable")
        .reset_index(drop=True)
    )
    frame["candidate_id"] = np.arange(len(frame))
    return frame


def _period_usage(frame):
    if set(PERIOD_COLUMNS.values()).issubset(frame.columns):
        return {period: frame[column].to_numpy(float) for period, column in PERIOD_COLUMNS.items()}
    return {
        period: np.where(frame.period.eq(period), frame.incremental_trips.to_numpy(float), 0.0)
        for period in PERIOD_COLUMNS
    }


def constraint_matrix(frame, capacity, budget, campaign_limit, min_roi, points_budget=None):
    """Sparse A x <= b for every policy constraint, with a name per row."""
    n = len(frame)
    rows, cols, vals, upper, names = [], [], [], [], []
    column_index = np.arange(n)

    def add(values, bound, name, index=column_index):
        values = np.asarray(values, dtype=float)
        keep = values != 0
        row = len(upper)
        rows.extend([row] * int(keep.sum()))
        cols.extend(np.asarray(index)[keep].tolist())
        vals.extend(values[keep].tolist())
        upper.append(float(bound))
        names.append(name)

    cost = frame.cost.to_numpy(float)
    add(cost, budget, "budget")
    add(np.ones(n), campaign_limit, "campaign_size")
    # Portfolio net ROI >= floor is linear: sum(floor * cost - net) <= 0.
    add(min_roi * cost - frame.net_contribution.to_numpy(float), 0, "minimum_net_roi")
    if points_budget is not None:
        add(frame.points.to_numpy(float), points_budget, "loyalty_points")
    for offer, group in frame.groupby("offer_id", sort=True):
        add(np.ones(len(group)), group.inventory.iloc[0], f"inventory:{offer}", group.index.to_numpy())
    usage = _period_usage(frame)
    zones = frame.zone_id.to_numpy()
    for cell in capacity.itertuples():
        mask = zones == cell.zone_id
        if cell.period in usage:
            name = f"capacity:{cell.zone_id}:{cell.period}"
            add(usage[cell.period][mask], cell.available_trips, name, column_index[mask])
    for customer, positions in frame.groupby("customer_id", sort=True).indices.items():
        if len(positions) > 1:
            add(np.ones(len(positions)), 1, f"contact:{customer}", np.asarray(positions))
    matrix = coo_matrix((vals, (rows, cols)), shape=(len(upper), n)).tocsr()
    return matrix, np.asarray(upper), names


def validate_inputs(frame, capacity, budget, campaign_limit, min_roi, solver, points_budget):
    if solver not in {"auto", "gurobi", "highs"}:
        raise ValueError("Unknown solver")
    limits = [budget, campaign_limit, min_roi] + ([] if points_budget is None else [points_budget])
    if not all(np.isfinite(v) and v >= 0 for v in limits):
        raise ValueError("Limits must be finite and nonnegative")
    if (
        int(campaign_limit) != campaign_limit
        or points_budget is not None
        and int(points_budget) != points_budget
    ):
        raise ValueError("Contacts and points must be integers")
    required = {
        "customer_id",
        "offer_id",
        "eligible",
        "zone_id",
        "cost",
        "net_contribution",
        "incremental_trips",
        "objective_value",
        "inventory",
        "points",
    }
    if not required.issubset(frame):
        raise ValueError("Candidate schema is incomplete")
    if frame[list(required)].isna().any().any():
        raise ValueError("Missing candidate values")
    numeric = ["cost", "net_contribution", "incremental_trips", "objective_value", "inventory", "points"]
    if not np.isfinite(frame[numeric].to_numpy(dtype=float)).all():
        raise ValueError("Nonfinite candidate values")
    if (frame[["cost", "inventory", "points"]] < 0).any().any():
        raise ValueError("Negative candidate resources")
    signed = set(PERIOD_COLUMNS.values()).issubset(frame.columns)
    if not signed and (frame.incremental_trips < 0).any():
        raise ValueError("Negative candidate resources")
    if not frame.eligible.isin([True, False]).all():
        raise ValueError("Eligibility must be boolean")
    if frame.duplicated(["customer_id", "offer_id"]).any():
        raise ValueError("Duplicate customer/offer candidates")
    if (frame.groupby("offer_id").inventory.nunique() > 1).any():
        raise ValueError("Inconsistent offer inventory")
    if not {"zone_id", "period", "available_trips", "baseline_over_capacity"}.issubset(capacity):
        raise ValueError("Capacity schema is incomplete")
    if capacity.duplicated(["zone_id", "period"]).any():
        raise ValueError("Duplicate capacity cells")
    if (
        capacity[["zone_id", "period", "available_trips"]].isna().any().any()
        or not np.isfinite(capacity.available_trips).all()
        or (capacity.available_trips < 0).any()
    ):
        raise ValueError("Invalid capacity values")
    if not signed:
        cells = set(zip(capacity.zone_id, capacity.period, strict=True))
        if any(pair not in cells for pair in zip(frame.zone_id, frame.period, strict=True)):
            raise ValueError("Candidate has no matching capacity cell")
    elif not set(frame.zone_id).issubset(set(capacity.zone_id)):
        raise ValueError("Candidate has no matching capacity cell")


def _empty(frame, budget, min_roi):
    return Allocation(
        frame,
        "none",
        "empty",
        0.0,
        0.0,
        {
            "reason": "no candidates",
            "candidate_count": 0,
            "customer_count": 0,
            "budget": budget,
            "spend": 0.0,
            "net_contribution": 0.0,
            "objective_value": 0.0,
            "incremental_trips": 0.0,
            "net_roi": None,
            "all_constraints_passed": True,
            "min_roi": min_roi,
            "binding_constraints": [],
        },
    )


def _solve_gurobi(objective, matrix, upper, ub, time_limit):
    import gurobipy as gp

    with gp.Env(empty=True) as env:
        env.setParam("OutputFlag", 0)
        env.start()
        with gp.Model("corridor_allocation", env=env) as model:
            x = model.addMVar(len(objective), vtype=gp.GRB.BINARY, ub=ub)
            model.setObjective(objective @ x, gp.GRB.MAXIMIZE)
            model.addMConstr(matrix, x, "<", upper, name="policy")
            model.Params.TimeLimit = time_limit
            model.Params.MIPGap = 1e-4
            model.Params.Seed = 407
            model.optimize()
            if model.SolCount < 1:
                raise RuntimeError(f"Gurobi returned no feasible incumbent, status {model.Status}")
            status = "optimal" if model.Status == gp.GRB.OPTIMAL else "feasible_time_limit"
            return x.X > 0.5, float(model.MIPGap), status, float(model.ObjVal)


def _quiet():
    """Keep solver contexts compatible without redirecting process-wide file descriptors.

    HiGHS logging is disabled by its default solver options. Native diagnostic lines
    may still appear; suppressing them with dup2 races with concurrent requests and
    can close another thread's stdout (including pytest's Linux capture descriptor).
    """
    return nullcontext()


def _fixing(lp, ub, gap, bound):
    tolerance = 1e-9 * max(1.0, abs(bound))
    lower_rc, upper_rc = np.asarray(lp.lower.marginals), np.asarray(lp.upper.marginals)
    fixed_zero = (ub <= 0) | (lower_rc > gap + tolerance)
    fixed_one = (-upper_rc > gap + tolerance) & ~fixed_zero
    return fixed_zero, fixed_one


def _lp(objective, matrix, upper, ub):
    with _quiet():
        result = linprog(
            -objective,
            A_ub=matrix,
            b_ub=upper,
            bounds=np.column_stack([np.zeros(len(ub)), ub]),
            method="highs",
        )
    if result.status != 0:
        raise RuntimeError(f"LP relaxation failed: {result.message}")
    return result


def _repair(selection, objective, matrix, upper):
    """Drop the cheapest-to-lose selected variables until every row holds."""
    selection = selection.copy()
    for _ in range(len(selection)):
        violation = matrix @ selection.astype(float) - upper
        row = int(np.argmax(violation))
        if violation[row] <= 1e-9:
            return selection
        coefficients = np.asarray(matrix[row].toarray()).ravel()
        options = np.flatnonzero(selection & (coefficients > 0))
        if not len(options):
            return None
        loss = objective[options] / coefficients[options]
        selection[options[int(np.argmin(loss))]] = False
    return None


def _fill(selection, order, objective, matrix, upper):
    """Greedily add candidates in `order` while every row they touch still holds."""
    selection = selection.copy()
    lhs = matrix @ selection.astype(float)
    csc = matrix.tocsc()
    for j in order:
        if selection[j] or objective[j] <= 0:
            continue
        rows = csc.indices[csc.indptr[j] : csc.indptr[j + 1]]
        values = csc.data[csc.indptr[j] : csc.indptr[j + 1]]
        if np.all(lhs[rows] + values <= upper[rows] + 1e-9):
            selection[j] = True
            lhs[rows] += values
    return selection


def _round(x, objective, matrix, upper, ub):
    """Feasible incumbent from an LP solution: keep integral ones, repair, then fill by LP weight."""
    selection = (x > 1 - 1e-6) & (ub > 0)
    repaired = _repair(selection, objective, matrix, upper)
    if repaired is None:
        repaired = np.zeros(len(x), dtype=bool)
    order = np.lexsort((-objective, -x))
    return _fill(repaired, order, objective, matrix, upper)


def _solve_highs(objective, matrix, upper, ub, time_limit):
    with _quiet():
        solution = _milp(objective, matrix, upper, ub, time_limit)
    if solution.x is None:
        raise RuntimeError(f"HiGHS did not return an incumbent: {solution.message}")
    status = "optimal" if solution.success else "feasible_time_limit"
    return solution.x > 0.5, float(getattr(solution, "mip_gap", 0.0) or 0.0), status, float(-solution.fun)


def _milp(objective, matrix, upper, ub, time_limit):
    return milp(
        -objective,
        integrality=np.ones(len(objective)),
        bounds=Bounds(np.zeros(len(objective)), ub),
        constraints=LinearConstraint(matrix, np.full(len(upper), -np.inf), upper),
        options={"time_limit": time_limit, "mip_rel_gap": 1e-6},
    )


def _exact(objective, matrix, upper, ub, solver, time_limit):
    """LP relaxation, rounding, reduced-cost fixing, then an exact solve of the free core.

    For a maximisation with LP bound z_LP and incumbent z_I, a variable whose
    reduced cost exceeds z_LP - z_I takes the same value in every plan worth
    more than z_I, so it can be fixed. The core left free is small enough to
    solve exactly; if it cannot beat z_I, the incumbent is globally optimal.
    """
    lp = _lp(objective, matrix, upper, ub)
    bound = float(-lp.fun)
    incumbent = _round(lp.x, objective, matrix, upper, ub)
    value = float(objective[incumbent].sum())
    gap = max(bound - value, 0.0)
    fixed_zero, fixed_one = _fixing(lp, ub, gap, bound)
    free = ~(fixed_zero | fixed_one)
    residual = upper - np.asarray(matrix[:, fixed_one].sum(axis=1)).ravel()
    core = matrix[:, free].tocsr()
    active = np.diff(core.indptr) > 0
    certificate = {
        "lp_bound": bound,
        "rounded_incumbent": value,
        "absolute_gap_before_core": gap,
        "variables": len(objective),
        "fixed_to_zero": int(fixed_zero.sum()),
        "fixed_to_one": int(fixed_one.sum()),
        "free_variables": int(free.sum()),
        "free_constraints": int(active.sum()),
        "licence_limit": GUROBI_LICENCE_LIMIT,
    }
    selection, core_solver, status = incumbent, "rounding", "feasible"
    mip_gap = gap / max(abs(bound), 1e-9)
    if free.any() and (residual[~active] >= -1e-6).all():
        sub_objective = objective[free]
        sub_matrix, sub_upper = core[active], residual[active]
        fits = free.sum() <= GUROBI_LICENCE_LIMIT and active.sum() <= GUROBI_LICENCE_LIMIT
        chosen = None
        if solver in ("auto", "gurobi") and fits:
            try:
                chosen, mip_gap, status, _ = _solve_gurobi(
                    sub_objective, sub_matrix, sub_upper, np.ones(int(free.sum())), time_limit
                )
                core_solver = "Gurobi"
            except Exception as exc:
                if solver == "gurobi" and exc.__class__.__name__ != "GurobiError":
                    raise
                certificate["gurobi_unavailable"] = str(exc)
        if chosen is None:
            try:
                chosen, mip_gap, status, _ = _solve_highs(
                    sub_objective, sub_matrix, sub_upper, np.ones(int(free.sum())), time_limit
                )
                core_solver = "HiGHS"
            except RuntimeError as exc:
                # No incumbent inside the time limit: keep the rounded plan, which is always feasible.
                certificate["core_timeout"] = str(exc)
                core_solver, status = "rounding (core timed out)", "feasible"
        if chosen is not None:
            candidate = fixed_one.copy()
            candidate[np.flatnonzero(free)[chosen]] = True
            if objective[candidate].sum() >= value - 1e-9:
                selection = candidate
    elif not free.any():
        status, mip_gap = "optimal", 0.0
    final = float(objective[selection].sum())
    if core_solver == "HiGHS" and solver != "highs" and status == "optimal":
        # Second opinion: re-fix with the final gap; the core left is usually licence-sized for Gurobi.
        certificate["gurobi_check"] = _gurobi_check(
            lp, objective, matrix, upper, ub, bound, final, time_limit
        )
    certificate.update(
        core_solver=core_solver,
        core_status=status,
        objective=final,
        proven_optimal=bool(status == "optimal" and mip_gap <= 1e-4 and "core_timeout" not in certificate),
        relative_gap_to_lp_bound=(bound - final) / max(abs(bound), 1e-9),
    )
    return selection, certificate, lp


def _gurobi_check(lp, objective, matrix, upper, ub, bound, incumbent, time_limit):
    """Independent proof by Gurobi that no plan beats the incumbent, over the variables still free."""
    fixed_zero, fixed_one = _fixing(lp, ub, max(bound - incumbent, 0.0), bound)
    free = ~(fixed_zero | fixed_one)
    residual = upper - np.asarray(matrix[:, fixed_one].sum(axis=1)).ravel()
    core = matrix[:, free].tocsr()
    active = np.diff(core.indptr) > 0
    check = {"free_variables": int(free.sum()), "free_constraints": int(active.sum())}
    if free.sum() > GUROBI_LICENCE_LIMIT or active.sum() > GUROBI_LICENCE_LIMIT:
        return {**check, "status": "exceeds_licence"}
    if not free.any():
        return {**check, "status": "optimal", "confirmed": True}
    try:
        _, _, status, value = _solve_gurobi(
            objective[free], core[active], residual[active], np.ones(int(free.sum())), time_limit
        )
    except Exception as exc:  # Licence or package unavailable: report, never fail the plan.
        return {**check, "status": "unavailable", "detail": str(exc)}
    total = value + float(objective[fixed_one].sum())
    return {
        **check,
        "status": status,
        "gurobi_objective": total,
        "confirmed": bool(status == "optimal" and total <= incumbent + max(1e-6, 1e-6 * abs(incumbent))),
    }


@bounded_operation
def solve(
    frame,
    capacity,
    budget=1600,
    campaign_limit=180,
    min_roi=0.15,
    solver="auto",
    points_budget=None,
    time_limit=60,
):
    """Optimal allocation. Licence-sized problems go straight to a MIP solver; large ones use `_exact`."""
    validate_inputs(frame, capacity, budget, campaign_limit, min_roi, solver, points_budget)
    if capacity.baseline_over_capacity.any():
        raise ValueError("Baseline plus safety reserve exceeds capacity before campaign allocation")
    frame = frame.reset_index(drop=True)
    if frame.empty:
        return _empty(frame, budget, min_roi)
    started = time.perf_counter()
    matrix, upper, names = constraint_matrix(frame, capacity, budget, campaign_limit, min_roi, points_budget)
    objective = frame.objective_value.to_numpy(float)
    ub = frame.eligible.astype(float).to_numpy()
    small = len(objective) <= GUROBI_LICENCE_LIMIT and len(upper) <= GUROBI_LICENCE_LIMIT
    certificate, fallback, lp = None, None, None
    if small:
        selection = None
        if solver in ("auto", "gurobi"):
            try:
                selection, gap, status, _ = _solve_gurobi(objective, matrix, upper, ub, time_limit)
                actual = "Gurobi"
            except (ImportError, ModuleNotFoundError) as exc:
                if solver == "gurobi":
                    raise
                fallback = str(exc)
            except Exception as exc:
                # Only a Gurobi availability/licence failure may fall back to HiGHS.
                if solver == "gurobi" or exc.__class__.__name__ != "GurobiError":
                    raise
                fallback = str(exc)
        if selection is None:
            selection, gap, status, _ = _solve_highs(objective, matrix, upper, ub, time_limit)
            actual = "HiGHS"
    else:
        selection, certificate, lp = _exact(objective, matrix, upper, ub, solver, time_limit)
        actual = f"HiGHS LP + {certificate['core_solver']} core"
        status = "optimal" if certificate["proven_optimal"] else "feasible"
        gap = certificate["relative_gap_to_lp_bound"]
    lhs = matrix @ selection.astype(float)
    violated = [names[i] for i in np.flatnonzero(lhs > upper + 1e-6)]
    if violated:
        raise RuntimeError(f"Solver result violates policy: {violated[:5]}")
    chosen = frame[selection].copy()
    if chosen.customer_id.duplicated().any() or not chosen.eligible.all():
        raise RuntimeError("Customer contact/eligibility violation")
    binding = [names[i] for i in np.flatnonzero(np.abs(lhs - upper) < 1e-5)]
    spend = float(chosen.cost.sum())
    diagnostics = {
        "candidate_count": len(frame),
        "customer_count": int(frame.customer_id.nunique()),
        "constraint_count": len(names),
        "budget": budget,
        "spend": spend,
        "net_contribution": float(chosen.net_contribution.sum()),
        "objective_value": float(chosen.objective_value.sum()),
        "incremental_trips": float(chosen.incremental_trips.sum()),
        "net_roi": float(chosen.net_contribution.sum() / spend) if spend else None,
        "all_constraints_passed": True,
        "fallback_reason": fallback,
        "min_roi": min_roi,
        "binding_constraints": [b for b in binding if not b.startswith("contact:")],
        "binding_contact_rows": sum(b.startswith("contact:") for b in binding),
        "certificate": certificate,
        "solve_seconds": time.perf_counter() - started,
    }
    if lp is not None:
        duals = -lp.ineqlin.marginals
        diagnostics["shadow_prices"] = {
            name: float(price)
            for name, price in zip(names, duals, strict=True)
            if not name.startswith("contact:") and abs(price) > 1e-9
        }
    return Allocation(chosen, actual, status, float(chosen.objective_value.sum()), gap, diagnostics)


def lp_relaxation(frame, capacity, budget, campaign_limit, min_roi, points_budget=None):
    """LP bound and shadow prices of the named side constraints."""
    frame = frame.reset_index(drop=True)
    matrix, upper, names = constraint_matrix(frame, capacity, budget, campaign_limit, min_roi, points_budget)
    result = _lp(
        frame.objective_value.to_numpy(float), matrix, upper, frame.eligible.astype(float).to_numpy()
    )
    duals = -result.ineqlin.marginals  # Value of relaxing each <= row by one unit.
    prices = [
        {
            "constraint": name,
            "shadow_price": float(price),
            "limit": float(limit),
            "binding": bool(abs(price) > 1e-9),
        }
        for name, price, limit in zip(names, duals, upper, strict=True)
        if not name.startswith("contact:")
    ]
    return {"bound": float(-result.fun), "shadow_prices": prices}


def capacity_after(capacity, selected):
    """Add a plan's signed trips by zone and period to the capacity cells."""
    usage = _period_usage(selected)
    parts = [
        pd.DataFrame({"zone_id": selected.zone_id.to_numpy(), "period": period, "allocated_trips": values})
        for period, values in usage.items()
    ]
    added = pd.concat(parts).groupby(["zone_id", "period"]).allocated_trips.sum().reset_index()
    view = capacity.drop(columns=["allocated_trips"], errors="ignore")
    view = view.merge(added, on=["zone_id", "period"], how="left", validate="one_to_one")
    view["allocated_trips"] = view.allocated_trips.fillna(0.0)
    view["final_utilization"] = (view.baseline_forecast + view.allocated_trips) / view.capacity_trips
    view["remaining_with_reserve"] = view.available_trips - view.allocated_trips
    return view


def allocate(cfg, current, uplift, offers, capacity, solver="auto"):
    frame = candidates(cfg, current, uplift, offers)
    limits = dict(
        budget=cfg.budget,
        campaign_limit=cfg.campaign_limit,
        min_roi=cfg.min_roi,
        points_budget=cfg.points_budget,
    )
    joint = solve(frame, capacity, solver="highs" if solver == "highs" else "auto", **limits)
    relaxation = lp_relaxation(frame, capacity, **limits)
    certification = joint.diagnostics.get("certificate") or {"proven_optimal": joint.status == "optimal"}
    robust_frame = candidates(cfg, current, uplift, offers, risk_aversion=1.0)
    robust = solve(robust_frame, capacity, solver="highs", **limits)

    frame.to_csv(cfg.path("outputs", "joint_candidates.csv"), index=False)
    selected = joint.selected
    sensitivity = []
    for multiple in [0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0]:
        budget = cfg.budget * multiple
        scenario = (
            joint
            if multiple == 1.0
            else solve(frame, capacity, solver="highs", **{**limits, "budget": budget})
        )
        sensitivity.append(
            {
                "budget": budget,
                "contacts": len(scenario.selected),
                "spend": scenario.diagnostics["spend"],
                "net_contribution": scenario.diagnostics["net_contribution"],
                "objective_value": scenario.objective,
                "incremental_value_days31_90": float(scenario.selected.later_value_uplift.sum()),
                "incremental_trips": scenario.diagnostics["incremental_trips"],
                "budget_shadow_price": scenario.diagnostics.get("shadow_prices", {}).get("budget", 0.0),
            }
        )
    frontier = pd.DataFrame(sensitivity)
    frontier["marginal_value_per_dollar"] = frontier.objective_value.diff() / frontier.budget.diff()
    frontier.to_csv(cfg.path("outputs", "budget_frontier.csv"), index=False)

    capacity = capacity_after(capacity, selected)
    if (capacity.remaining_with_reserve < -1e-6).any():
        raise RuntimeError("Combined capacity violated")
    capacity.to_csv(cfg.path("outputs", "capacity.csv"), index=False)
    selected.to_csv(cfg.path("outputs", "decision_table.csv"), index=False)
    robust.selected.to_csv(cfg.path("outputs", "robust_decision_table.csv"), index=False)
    pd.DataFrame(relaxation["shadow_prices"]).to_csv(cfg.path("outputs", "shadow_prices.csv"), index=False)

    def subtotal(rows):
        return {
            "contacts": len(rows),
            "spend": float(rows.cost.sum()),
            "net_contribution": float(rows.net_contribution.sum()),
            "objective_value": float(rows.objective_value.sum()),
            "incremental_trips": float(rows.incremental_trips.sum()),
            "points": int(rows.points.sum()),
        }

    result = {
        "joint": {"solver": joint.solver, "status": joint.status, "gap": joint.gap, **joint.diagnostics},
        "combined": {
            "contacts": len(selected),
            "budget": cfg.budget,
            "contact_limit": cfg.campaign_limit,
            "points_limit": cfg.points_budget,
            "min_roi": cfg.min_roi,
            "spend": float(selected.cost.sum()),
            "net_contribution": float(selected.net_contribution.sum()),
            "later_value": float(selected.later_value_uplift.sum()),
            "objective_value": float(selected.objective_value.sum()),
            "incremental_trips": float(selected.incremental_trips.sum()),
            "peak_trips": float(selected.trips_peak.sum()),
            "offpeak_trips": float(selected.trips_offpeak.sum()),
            "weekend_trips": float(selected.trips_weekend.sum()),
            "points_awarded": int(selected.points.sum()),
            "relief_value": float(selected.relief_value.sum()),
            "rush_hour_trips_per_workday": float(selected.trips_peak.sum() / 22),
            "all_constraints_passed": True,
        },
        "by_offer": {offer: subtotal(group) for offer, group in selected.groupby("offer_id")},
        "robust": {"risk_aversion": 1.0, "solver": robust.solver, **subtotal(robust.selected)},
        "lp_relaxation": {
            "bound": relaxation["bound"],
            "integrality_gap": relaxation["bound"] - joint.objective,
            "shadow_prices": [p for p in relaxation["shadow_prices"] if p["binding"]],
        },
        "certification": certification,
        "scope": "One mixed-integer program over every eligible customer and offer, with shared budget, contacts, "
        "net-ROI floor, points liability, inventory and signed zone/period capacity.",
        "economics": "Objective = model-estimated 30-day incremental net contribution after incentive costs "
        "(discounts paid on baseline trips included) plus the discounted incremental margin on days 31-90. "
        "Retention is reported separately to avoid double counting.",
    }
    write_json(cfg.path("outputs", "optimization_results.json"), result)
    return selected, capacity, result, frame, robust
