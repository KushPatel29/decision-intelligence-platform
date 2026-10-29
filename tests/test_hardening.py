import json
from dataclasses import replace

import numpy as np
import pandas as pd
import pytest
from test_contracts import allocation_fixture

from decision_platform.config import ROOT, Config, write_json
from decision_platform.monitoring import psi
from decision_platform.optimization import solve
from decision_platform.quality import evaluate_quality, select_regression
from decision_platform.runtime import (
    audit_event,
    pipeline_run,
    saved_plans,
    validate_release,
)


@pytest.mark.parametrize(
    "field,value",
    [("cost", np.nan), ("objective_value", np.inf), ("incremental_trips", -1), ("eligible", "yes")],
)
def test_invalid_optimizer_inputs_are_rejected(field, value):
    frame, capacity = allocation_fixture()
    frame[field] = frame[field].astype(object)
    frame.loc[0, field] = value
    with pytest.raises(ValueError):
        solve(frame, capacity, solver="highs")


def test_missing_capacity_cannot_be_silently_unconstrained():
    frame, capacity = allocation_fixture()
    frame.loc[0, "zone_id"] = 99
    with pytest.raises(ValueError, match="matching capacity"):
        solve(frame, capacity, solver="highs")


@pytest.mark.parametrize(
    "kwargs", [{"budget": np.inf}, {"points_budget": -1}, {"campaign_limit": 1.5}, {"solver": "imaginary"}]
)
def test_bad_limits_are_rejected(kwargs):
    frame, capacity = allocation_fixture()
    with pytest.raises(ValueError):
        solve(frame, capacity, **kwargs)


def test_empty_candidate_shortlist_has_complete_diagnostics():
    frame, capacity = allocation_fixture()
    result = solve(frame.iloc[:0], capacity, solver="highs")
    assert result.selected.empty and result.diagnostics["all_constraints_passed"]
    assert result.diagnostics["spend"] == 0


def test_baseline_wins_validation_without_using_test_outcomes():
    assert (
        select_regression([1, 2, 3], {"learned": [2, 3, 4], "baseline": [1, 2, 3]})["selected"] == "baseline"
    )


def test_constant_reference_shift_is_detected():
    assert psi(np.ones(100), np.ones(100)) == 0
    assert psi(np.ones(100), np.full(100, 2)) > 0.2


def test_run_lock_refuses_parallel_refresh_and_partial_serving(tmp_path):
    cfg = replace(Config(), root=tmp_path)
    with pipeline_run(cfg):
        with pytest.raises(RuntimeError, match="run lock"):
            with pipeline_run(cfg):
                pass
        with pytest.raises(ValueError, match="refresh"):
            validate_release(tmp_path)
        write_json(tmp_path / "outputs/example.json", {"ok": True})
    assert validate_release(tmp_path)["status"] == "verified"
    write_json(tmp_path / "outputs/example.json", {"ok": False})
    with pytest.raises(ValueError, match="integrity"):
        validate_release(tmp_path)


def test_failed_run_does_not_leave_readable_partial_release(tmp_path):
    cfg = replace(Config(), root=tmp_path)
    with pytest.raises(RuntimeError):
        with pipeline_run(cfg):
            raise RuntimeError("injected failure")
    assert not (tmp_path / ".pipeline.lock").exists()
    with pytest.raises(ValueError, match="did not complete"):
        validate_release(tmp_path)


def test_saved_decisions_are_isolated_by_owner(tmp_path):
    audit_event(tmp_path, "owner-a", "save_plan", {"allocation": [{"customer_id": "synthetic"}], "budget": 1})
    audit_event(tmp_path, "owner-b", "save_plan", {"budget": 2})
    assert [p["budget"] for p in saved_plans(tmp_path, "owner-a")] == [1]
    assert saved_plans(tmp_path, "unknown") == []


def test_joint_pricing_uses_capacity_and_exactly_one_price_per_cell(monkeypatch):
    import decision_platform.pricing as pricing
    from decision_platform.pricing import optimize_prices

    original = pricing._lp_guided
    observed = []

    def checked(*args, **kwargs):
        observed.append(kwargs["time_limit"])
        return original(*args, **kwargs)

    monkeypatch.setattr(pricing, "_lp_guided", checked)
    frame, capacity = allocation_fixture()
    options = pd.DataFrame(
        {
            "zone_id": [0, 0],
            "period": ["Off-peak"] * 2,
            "capacity_trips": [10.0, 10.0],
            "protected_load": [9.0, 5.0],
            "available_trips": [1.0, 5.0],
            "incremental_contribution": [30.0, 20.0],
            "consumer_surplus_change": [-2.0, 1.0],
            "eligible": [True, True],
        }
    )
    prices, campaign, receipt = optimize_prices(
        options, frame, budget=11, contacts=2, roi=0.5, solver="highs", time_limit=7
    )
    assert observed == [7]
    assert len(prices) == 1
    assert prices.protected_load.sum() + campaign.incremental_trips.sum() <= 10 + 1e-8
    assert campaign.cost.sum() <= 11 and receipt["all_constraints_passed"]


def test_joint_pricing_publishes_a_labelled_price_only_plan_when_the_solver_returns_none(monkeypatch):
    """CI on 2026-10-29 crashed with 'No feasible joint pricing plan': HiGHS returned no incumbent,
    though keeping each cell's best eligible price and contacting nobody is always feasible."""
    from types import SimpleNamespace

    import decision_platform.pricing as pricing

    monkeypatch.setattr(
        pricing,
        "milp",
        lambda *a, **k: SimpleNamespace(x=None, success=False, status=1, message="Time limit reached"),
    )
    frame, _ = allocation_fixture()
    options = pd.DataFrame(
        {
            "zone_id": [0, 0, 0],
            "period": ["Off-peak"] * 3,
            "capacity_trips": [10.0] * 3,
            "protected_load": [9.0, 5.0, 12.0],
            "available_trips": [1.0, 5.0, -2.0],
            "incremental_contribution": [30.0, 20.0, 99.0],
            "consumer_surplus_change": [-2.0, 1.0, 0.0],
            "eligible": [True, True, False],
        }
    )
    prices, campaign, receipt = pricing.optimize_prices(
        options, frame, budget=11, contacts=2, roi=0.5, solver="highs", time_limit=7
    )
    assert prices.incremental_contribution.tolist() == [30.0], "best ELIGIBLE price, never the infeasible one"
    assert campaign.empty and receipt["contacts"] == 0
    assert "price-only fallback" in receipt["solver"] and receipt["all_constraints_passed"]


def test_local_model_gate_and_mart_grains():
    path = ROOT / "outputs/quality_gate.json"
    if not path.exists():
        pytest.skip("Generate data first")
    assert json.loads(path.read_text())["passed"]
    customers = pd.read_csv(ROOT / "outputs/customer_360.csv")
    assert not customers.customer_id.duplicated().any()
    np.testing.assert_allclose(
        customers.points_balance,
        customers.points_earned + customers.points_awarded - customers.points_redeemed,
    )
    offers = pd.read_csv(ROOT / "outputs/customer_offer.csv")
    assert not offers.duplicated(["customer_id", "offer_id"]).any()


def test_production_refuses_anonymous_local_mode(monkeypatch):
    monkeypatch.setenv("CORRIDOR_ENV", "production")
    monkeypatch.setenv("CORRIDOR_AUTH", "local")
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_file(str(ROOT / "app.py")).run()
    assert not app.exception and app.error
    assert not app.radio


def test_app_solver_slots_turn_away_extra_solves(monkeypatch):
    import threading

    import decision_platform.webapp as webapp

    monkeypatch.setattr(webapp, "_SOLVER_SLOTS", threading.BoundedSemaphore(1))
    with webapp.solver_slot() as first:
        with webapp.solver_slot() as second:
            assert first and not second
    with webapp.solver_slot() as again:
        assert again  # released on exit, including after the refused attempt


def test_demo_mode_gives_each_session_its_own_owner(monkeypatch):
    from types import SimpleNamespace

    from decision_platform.access import require_access

    monkeypatch.setenv("CORRIDOR_AUTH", "demo")
    monkeypatch.delenv("CORRIDOR_ENV", raising=False)
    first, second = SimpleNamespace(session_state={}), SimpleNamespace(session_state={})
    owner = require_access(first)
    assert owner.startswith("demo-") and require_access(first) == owner  # stable within a session
    assert require_access(second) != owner  # never shared across sessions


def test_production_refuses_demo_mode(monkeypatch):
    import pytest

    from decision_platform.access import require_access

    class Stop(Exception):
        pass

    class FakeSt:
        session_state: dict = {}

        def error(self, *_):
            pass

        def stop(self):
            raise Stop

    monkeypatch.setenv("CORRIDOR_AUTH", "demo")
    monkeypatch.setenv("CORRIDOR_ENV", "production")
    with pytest.raises(Stop):
        require_access(FakeSt())


def test_quality_gate_reads_an_ensemble_of_uplift_learners():
    """The selected uplift model can be an ensemble ("s_learner+x_learner"), which has no metrics entry of its own.

    CI's Linux pipeline chose one on 2026-10-15 and the gate raised KeyError instead of scoring it.
    """
    ensemble = json.loads((ROOT / "outputs" / "serving" / "metrics.json").read_text(encoding="utf-8"))
    offers = [o for o, v in ensemble["uplift"].items() if isinstance(v, dict) and "selected" in v]
    assert offers
    for offer in offers:
        ensemble["uplift"][offer]["selected"] = "s_learner+x_learner"
    check = next(c for c in evaluate_quality(ensemble)["checks"] if c["model"] == "uplift")
    expected = sum(ensemble["uplift"][o]["ensemble"]["qini"] for o in offers) / len(offers)
    assert check["value"] == pytest.approx(expected)
