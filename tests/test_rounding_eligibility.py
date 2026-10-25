"""Eligibility must survive LP rounding, exact-core solves and timeout fallback."""

from itertools import product

import numpy as np
import pandas as pd
import pytest
from scipy.sparse import csr_matrix

from decision_platform import optimization


def candidates(cost, objective, eligible, trips=None):
    size = len(cost)
    frame = pd.DataFrame(
        {
            "customer_id": [f"C{i}" for i in range(size)],
            "offer_id": ["one"] * size,
            "eligible": eligible,
            "zone_id": [0] * size,
            "period": ["Off-peak"] * size,
            "cost": cost,
            "net_contribution": objective,
            "incremental_trips": trips if trips is not None else [1.0] * size,
            "objective_value": objective,
            "inventory": [size] * size,
            "points": [0] * size,
        }
    )
    capacity = pd.DataFrame(
        {"zone_id": [0], "period": ["Off-peak"], "available_trips": [10.0], "baseline_over_capacity": [False]}
    )
    return frame, capacity


@pytest.mark.parametrize("eligible", [[True, False], [False, True], [False, False], [True, True]])
def test_rounding_cannot_fill_a_candidate_with_zero_upper_bound(eligible):
    ub = np.asarray(eligible, dtype=float)
    selection = optimization._round(
        ub * 0.75, np.array([3.0, 100.0]), csr_matrix([[1.0, 1.0]]), np.array([2.0]), ub
    )
    assert not (selection & ~ub.astype(bool)).any()
    assert selection.tolist() == eligible


@pytest.mark.parametrize("core_timeout", [False, True])
def test_large_path_keeps_a_valid_incumbent_when_forbidden_offer_is_more_valuable(monkeypatch, core_timeout):
    # The LP bound is 8.5; the legal integer optimum is 6. An illegal extra contact
    # would inflate the rounded incumbent to 106 and prevent accepting the legal core.
    frame, capacity = candidates([2.0, 2.0, 1.0], [6.0, 5.0, 100.0], [True, True, False])
    monkeypatch.setattr(optimization, "GUROBI_LICENCE_LIMIT", 1)
    if core_timeout:

        def no_incumbent(*args, **kwargs):
            raise RuntimeError("injected core timeout without an incumbent")

        monkeypatch.setattr(optimization, "_solve_highs", no_incumbent)
    result = optimization.solve(frame, capacity, budget=3, campaign_limit=3, min_roi=0, solver="highs")
    assert result.selected.customer_id.tolist() == ["C0"]
    assert result.objective == pytest.approx(6)
    certificate = result.diagnostics["certificate"]
    assert certificate["rounded_incumbent"] <= certificate["lp_bound"] + 1e-8
    assert certificate["relative_gap_to_lp_bound"] >= -1e-8
    assert result.diagnostics["all_constraints_passed"]
    if core_timeout:
        assert "core_timeout" in certificate
        assert result.status == "feasible" and not certificate["proven_optimal"]


@pytest.mark.parametrize("seed", range(16))
def test_reduced_core_matches_exhaustive_eligible_plan_search(monkeypatch, seed):
    rng = np.random.default_rng(seed)
    costs = rng.integers(1, 6, size=6)
    values = rng.integers(5, 21, size=6)
    trips = rng.integers(1, 6, size=6)
    eligible = rng.random(6) > 0.4
    frame, capacity = candidates(costs, values, eligible, trips)
    monkeypatch.setattr(optimization, "GUROBI_LICENCE_LIMIT", 1)
    best = 0
    for bits in product([False, True], repeat=6):
        selected = np.asarray(bits)
        if (
            (selected & ~eligible).any()
            or selected.sum() > 3
            or costs[selected].sum() > 8
            or trips[selected].sum() > 10
        ):
            continue
        best = max(best, values[selected].sum())
    result = optimization.solve(frame, capacity, budget=8, campaign_limit=3, min_roi=0, solver="highs")
    assert result.selected.eligible.all()
    assert result.objective == pytest.approx(best)
    assert (
        result.diagnostics["certificate"]["rounded_incumbent"]
        <= result.diagnostics["certificate"]["lp_bound"] + 1e-8
    )
