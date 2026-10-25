"""Every native optimization phase must receive the caller's finite solve limit."""

from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from scipy.sparse import csr_matrix

from decision_platform import optimization, pricing


def allocation_data():
    frame = pd.DataFrame(
        {
            "customer_id": [1, 2, 3],
            "offer_id": [1, 1, 1],
            "eligible": [True] * 3,
            "zone_id": [0] * 3,
            "period": ["Off-peak"] * 3,
            "cost": [1.0] * 3,
            "net_contribution": [5.0] * 3,
            "incremental_trips": [1.0] * 3,
            "objective_value": [5.0] * 3,
            "inventory": [10] * 3,
            "points": [0] * 3,
        }
    )
    capacity = pd.DataFrame(
        {"zone_id": [0], "period": ["Off-peak"], "available_trips": [10.0], "baseline_over_capacity": [False]}
    )
    return frame, capacity


@pytest.mark.parametrize("entrypoint", ["allocation", "shadow_prices", "pricing"])
def test_lp_time_limit_is_honored_and_timeout_is_never_an_optimal_result(monkeypatch, entrypoint):
    seen = []

    def limited(*args, **kwargs):
        seen.append(kwargs.get("options", {}).get("time_limit"))
        assert seen[-1] == 0.25, "LP stage must not run without its configured limit"
        return SimpleNamespace(status=1, message="Time limit reached", x=None)

    monkeypatch.setattr(optimization, "linprog", limited)
    monkeypatch.setattr(pricing, "linprog", limited)
    monkeypatch.setattr(optimization, "GUROBI_LICENCE_LIMIT", 1)
    frame, capacity = allocation_data()
    with pytest.raises(RuntimeError, match="LP"):
        if entrypoint == "allocation":
            optimization.solve(frame, capacity, solver="highs", time_limit=0.25)
        elif entrypoint == "shadow_prices":
            optimization.lp_relaxation(frame, capacity, 10, 3, 0, time_limit=0.25)
        else:
            pricing._lp_guided(
                np.ones(2),
                csr_matrix([[1.0, 1.0]]),
                np.array([-np.inf]),
                np.array([2.0]),
                np.ones(2),
                1,
                time_limit=0.25,
            )
    assert seen == [0.25]


@pytest.mark.parametrize("entrypoint", ["allocation", "shadow_prices"])
@pytest.mark.parametrize("limit", [0, -1, float("nan"), float("inf"), True])
def test_invalid_time_limits_fail_before_native_solver_access(monkeypatch, entrypoint, limit):
    def forbidden(*args, **kwargs):
        pytest.fail("invalid solve limits must not reach a native solver")

    monkeypatch.setattr(optimization, "linprog", forbidden)
    monkeypatch.setattr(optimization, "_solve_highs", forbidden)
    frame, capacity = allocation_data()
    with pytest.raises(ValueError, match="time_limit"):
        if entrypoint == "allocation":
            optimization.solve(frame, capacity, solver="highs", time_limit=limit)
        else:
            optimization.lp_relaxation(frame, capacity, 10, 3, 0, time_limit=limit)


def test_valid_lp_bound_and_shadow_prices_remain_available():
    frame, capacity = allocation_data()
    result = optimization.lp_relaxation(frame, capacity, 10, 3, 0)
    assert result["bound"] == pytest.approx(15)
    assert all(np.isfinite(row["shadow_price"]) for row in result["shadow_prices"])
