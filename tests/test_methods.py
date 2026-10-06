"""Unit tests for the statistical and optimization methods, independent of any pipeline run."""

import itertools

import numpy as np
import pandas as pd
import pytest

from decision_platform import economics
from decision_platform.experiments import (
    ARMS,
    benjamini_hochberg,
    blocked_assignment,
    cuped,
    difference,
    obrien_fleming_boundaries,
)
from decision_platform.optimization import constraint_matrix, solve

PERIODS = ["Peak", "Off-peak", "Weekend"]


def frame(rows):
    return pd.DataFrame(rows, columns=PERIODS)


# Offer economics -------------------------------------------------------------------------------


def test_discount_cost_includes_trips_that_would_have_happened_anyway():
    base, trips, tolls = frame([[0, 10, 0]]), frame([[0, 2, 0]]), frame([[10, 8, 8]])
    cost = economics.incentive_cost("offpeak_15", base, trips, tolls)
    assert cost[0] == pytest.approx(0.15 * 8 * 12 + economics.CONTACT_COST)
    value = economics.window_value("offpeak_15", base, trips, tolls, margin=0.72)
    assert value.net[0] == pytest.approx(0.72 * 2 * 8 - cost[0])


def test_loyalty_liability_is_fixed_and_threshold_reward_is_probabilistic():
    base, trips, tolls = frame([[2, 2, 1]]), frame([[0, 0, 0]]), frame([[9, 8, 8]])
    assert economics.incentive_cost("loyalty_1500", base, trips, tolls)[0] == pytest.approx(15.35)
    paid = economics.incentive_cost("spend_10", base, trips, tolls)[0] - economics.CONTACT_COST
    assert 0 < paid < 10


def test_offpeak_pass_cost_is_the_exact_poisson_excess():
    base, trips, tolls = frame([[0, 5, 0]]), frame([[0, 0, 0]]), frame([[0, 10, 0]])
    exact = economics.expected_excess(np.array([30.0]), np.array([10.0]), np.array([5.0]))[0]
    from scipy.stats import poisson

    brute = sum(max(10 * k - 30, 0) * poisson.pmf(k, 5) for k in range(80))
    assert exact == pytest.approx(brute)
    assert economics.incentive_cost("offpeak_pass", base, trips, tolls)[0] == pytest.approx(
        exact + economics.CONTACT_COST
    )


def test_unknown_offer_is_rejected():
    with pytest.raises(ValueError):
        economics.incentive_cost("mystery", frame([[1, 1, 1]]), frame([[0, 0, 0]]), frame([[1, 1, 1]]))


# Experiment design and analysis ----------------------------------------------------------------


def test_blocked_assignment_balances_every_block():
    rng = np.random.default_rng(1)
    blocks = np.repeat(np.arange(30), 90)
    arms = blocked_assignment(rng, blocks)
    counts = pd.Series(arms).value_counts()
    assert set(counts.index) == set(ARMS)
    assert counts.max() - counts.min() <= 1
    for block in range(30):
        inside = pd.Series(arms[blocks == block]).value_counts()
        assert inside.max() - inside.min() <= 1


def test_cuped_is_unbiased_and_shrinks_variance():
    rng = np.random.default_rng(2)
    pre = rng.gamma(2, 3, 20000)
    effect = 0.5
    control = pre + rng.normal(0, 1, 20000)
    treated_pre = rng.gamma(2, 3, 20000)
    treated = treated_pre + effect + rng.normal(0, 1, 20000)
    adjusted = cuped(treated, control, treated_pre, pre, comparisons=1)
    raw = difference(treated, control, comparisons=1)
    assert adjusted["difference"] == pytest.approx(effect, abs=0.05)
    assert adjusted["se"] < 0.5 * raw["se"]
    assert adjusted["variance_reduction"] > 0.75


def test_benjamini_hochberg_matches_definition_and_is_monotone():
    p = np.array([0.001, 0.008, 0.039, 0.041, 0.042, 0.06, 0.074, 0.205])
    q = benjamini_hochberg(p)
    expected = np.minimum.accumulate((p * len(p) / np.arange(1, len(p) + 1))[::-1])[::-1]
    np.testing.assert_allclose(q, np.minimum(expected, 1))
    assert (np.diff(q) >= -1e-12).all()
    assert benjamini_hochberg([]).size == 0


def test_obrien_fleming_boundaries_hold_the_family_alpha():
    boundaries = obrien_fleming_boundaries(looks=3, alpha=0.05, draws=200_000, seed=3)
    assert boundaries[0] > boundaries[1] > boundaries[2] > 1.96
    rng = np.random.default_rng(9)
    z = np.cumsum(rng.standard_normal((200_000, 3)), axis=1) / np.sqrt([1, 2, 3])
    crossed = (np.abs(z) >= np.array(boundaries)).any(axis=1).mean()
    assert crossed == pytest.approx(0.05, abs=0.004)


# Optimization ---------------------------------------------------------------------------------


def random_problem(seed, customers=7, offers=3):
    rng = np.random.default_rng(seed)
    rows = []
    for c, o in itertools.product(range(customers), range(offers)):
        cost = float(rng.uniform(1, 6))
        value = float(rng.normal(3, 3))
        rows.append(
            {
                "customer_id": f"C{c}",
                "offer_id": f"O{o}",
                "eligible": bool(rng.random() > 0.1),
                "zone_id": int(c % 2),
                "cost": cost,
                "net_contribution": value,
                "objective_value": value + float(rng.uniform(0, 1)),
                "trips_peak": float(rng.normal(0.2, 0.5)),
                "trips_offpeak": float(rng.uniform(0, 1)),
                "trips_weekend": float(rng.uniform(0, 0.5)),
                "points": int(rng.choice([0, 500])),
                "inventory": 4,
            }
        )
    frame = pd.DataFrame(rows)
    frame["incremental_trips"] = frame[["trips_peak", "trips_offpeak", "trips_weekend"]].sum(axis=1)
    capacity = pd.DataFrame(
        [(z, p, 1.5, False) for z in range(2) for p in PERIODS],
        columns=["zone_id", "period", "available_trips", "baseline_over_capacity"],
    )
    return frame, capacity


def brute_force(frame, capacity, budget, limit, roi, points):
    matrix, upper, _ = constraint_matrix(frame, capacity, budget, limit, roi, points)
    best = 0.0
    customers = frame.customer_id.unique()
    choices = [[None, *frame.index[frame.customer_id.eq(c) & frame.eligible]] for c in customers]
    for combo in itertools.product(*choices):
        x = np.zeros(len(frame))
        x[[i for i in combo if i is not None]] = 1
        if np.all(matrix @ x <= upper + 1e-9):
            best = max(best, float(frame.objective_value.to_numpy() @ x))
    return best


@pytest.mark.parametrize("seed", range(6))
def test_solver_matches_brute_force_with_signed_capacity(seed):
    frame, capacity = random_problem(seed)
    limits = dict(budget=12.0, campaign_limit=4, min_roi=0.15, points_budget=1000)
    result = solve(frame, capacity, solver="highs", **limits)
    expected = brute_force(frame, capacity, 12.0, 4, 0.15, 1000)
    assert result.objective == pytest.approx(expected, abs=1e-6)
    assert result.diagnostics["spend"] <= 12.0 + 1e-9


def test_exact_method_certifies_a_large_problem(monkeypatch):
    import decision_platform.optimization as optimization

    monkeypatch.setattr(optimization, "GUROBI_LICENCE_LIMIT", 40)
    frame, capacity = random_problem(11, customers=60, offers=3)
    capacity["available_trips"] = 15.0
    small = solve(
        frame.copy(),
        capacity,
        budget=60.0,
        campaign_limit=20,
        min_roi=0.15,
        solver="highs",
        points_budget=6000,
    )
    certificate = small.diagnostics["certificate"]
    assert certificate is not None and certificate["proven_optimal"]
    assert certificate["fixed_to_zero"] + certificate["fixed_to_one"] + certificate["free_variables"] == len(
        frame
    )
    assert certificate["relative_gap_to_lp_bound"] >= -1e-9
    monkeypatch.setattr(optimization, "GUROBI_LICENCE_LIMIT", 100_000)
    direct = solve(
        frame.copy(),
        capacity,
        budget=60.0,
        campaign_limit=20,
        min_roi=0.15,
        solver="highs",
        points_budget=6000,
    )
    assert small.objective == pytest.approx(direct.objective, rel=1e-6)


# Causal calibration ---------------------------------------------------------------------------


def test_blp_slope_detects_real_and_absent_heterogeneity():
    from decision_platform.causal import calibrate

    effect = pd.DataFrame({"Peak": [0.0, 0.0], "Off-peak": [1.0, 3.0], "Weekend": [0.0, 0.0]})
    means = effect.mean()
    calibrated, used = calibrate(effect, {"slope": 0.5, "ate": 1.0, "mean_prediction": 2.0}, means)
    assert used["slope_used"] == 0.5 and used["level_used"] == 0.5
    np.testing.assert_allclose(calibrated["Off-peak"], [0.5, 1.5])
    unchanged, _ = calibrate(effect, {"slope": 3.0, "ate": 2.0, "mean_prediction": 2.0}, means)
    np.testing.assert_allclose(unchanged["Off-peak"], effect["Off-peak"])
