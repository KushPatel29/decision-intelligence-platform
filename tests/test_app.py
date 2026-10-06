"""Streamlit smoke tests: every page renders against the real serving snapshot, and key actions work."""

import pytest

from decision_platform.config import ROOT

PAGES = [
    "views/decision_centre.py",
    "views/next_best_offer.py",
    "views/pricing.py",
    "views/customers.py",
    "views/offers_loyalty.py",
    "views/transportation.py",
    "views/policy_value.py",
    "views/experiments.py",
    "views/model_operations.py",
    "views/operations_centre.py",
    "views/analyst_workbench.py",
    "views/about.py",
]


@pytest.fixture
def app_test():
    if not (ROOT / "outputs" / "serving" / "manifest.json").exists():
        pytest.skip("Run the pipeline first")
    testing = pytest.importorskip("streamlit.testing.v1")
    return testing.AppTest.from_file(str(ROOT / "app.py"), default_timeout=120).run()


@pytest.mark.parametrize("page", PAGES)
def test_every_page_renders_without_errors(app_test, page):
    app_test.switch_page(page).run()
    assert not app_test.exception, app_test.exception
    assert not app_test.error
    assert app_test.title


def test_decision_centre_scenario_respects_limits(app_test):
    app_test.number_input(key="scenario_budget").set_value(4000.0)
    app_test.number_input(key="scenario_limit").set_value(1500)
    app_test.radio[0].set_value("HiGHS only")
    app_test.button[0].click().run()
    assert not app_test.exception and not app_test.error
    scenario = app_test.session_state["scenario"]
    assert scenario["diagnostics"]["spend"] <= 4000 + 1e-6
    assert len(scenario["frame"]) <= 1500
    assert scenario["diagnostics"]["all_constraints_passed"]


def test_zero_points_scenario_excludes_loyalty_offers(app_test):
    app_test.number_input(key="scenario_points").set_value(0)
    app_test.radio[0].set_value("HiGHS only")
    app_test.button[0].click().run()
    assert not app_test.exception and not app_test.error
    assert app_test.session_state["scenario"]["frame"].points.sum() == 0


def test_template_applies_and_history_accumulates(app_test):
    app_test.selectbox(key="scenario_template").set_value("Lean budget").run()
    assert app_test.number_input(key="scenario_budget").value == 6000.0
    assert app_test.number_input(key="scenario_limit").value == 3000
    app_test.radio[0].set_value("HiGHS only")
    app_test.button[0].click().run()
    assert not app_test.exception and not app_test.error
    assert len(app_test.session_state["scenario_history"]) == 1


def test_reviewed_plan_persists_with_release_identity(app_test):
    app_test.number_input(key="scenario_budget").set_value(3000.0)
    app_test.radio[0].set_value("HiGHS only")
    app_test.button[0].click().run()
    save = next(item for item in app_test.button if item.label == "Save reviewed scenario")
    save.click().run()
    assert not app_test.exception and any("audit reference" in item.value for item in app_test.success)
    from decision_platform.runtime import saved_plans

    plans = saved_plans(ROOT, "local-owner")
    assert plans and len(plans[0]["release_id"]) == 64


def test_next_best_offer_shows_ranked_offers(app_test):
    app_test.switch_page("views/next_best_offer.py").run()
    assert not app_test.exception
    assert app_test.dataframe, "offer table should render for a planned customer"


@pytest.mark.parametrize(
    "case",
    ["weekend_decline", "segment_decline", "cannibalization", "unused_capacity", "enrollment_vs_value"],
)
def test_analyst_case_shows_sql_and_conclusion(app_test, case):
    app_test.switch_page("views/analyst_workbench.py").run()
    app_test.selectbox[0].set_value(case).run()
    assert not app_test.exception and not app_test.error
    assert app_test.code and "SELECT" in app_test.code[0].value.upper()


def test_production_refuses_anonymous_local_mode(monkeypatch):
    monkeypatch.setenv("CORRIDOR_ENV", "production")
    monkeypatch.setenv("CORRIDOR_AUTH", "local")
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_file(str(ROOT / "app.py")).run()
    assert not app.exception and app.error
