import pytest

from decision_platform.config import ROOT


@pytest.fixture
def app_test():
    if not (ROOT / "outputs" / "dashboard_data.json").exists():
        pytest.skip("Run demo first")
    streamlit = pytest.importorskip("streamlit.testing.v1")
    return streamlit.AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()


@pytest.mark.parametrize(
    "page",
    [
        "Decision centre",
        "Customer intelligence",
        "Pricing",
        "Promotions",
        "Loyalty",
        "Transportation",
        "Experiments",
        "Policy lab",
        "Model operations",
        "Operations centre",
        "Analyst workbench",
        "Evidence & delivery",
    ],
)
def test_all_decision_pages_render(app_test, page):
    app_test.radio[0].set_value(page).run()
    assert not app_test.exception
    assert app_test.title[0].value == page


def test_streamlit_scenario_runs_real_gurobi(app_test):
    pytest.importorskip("gurobipy")
    app_test.number_input[0].set_value(500)
    app_test.number_input[1].set_value(30)
    app_test.button[0].click().run()
    assert not app_test.exception
    assert not app_test.error
    scenario = app_test.session_state["scenario"]
    assert scenario["solver"] == "Gurobi"
    assert scenario["diagnostics"]["spend"] <= 500 + 1e-6
    assert len(scenario["frame"]) <= 30
    assert scenario["diagnostics"]["all_constraints_passed"]


def test_customer_segment_filter_changes_export_population(app_test):
    app_test.radio[0].set_value("Customer intelligence").run()
    app_test.selectbox[0].set_value("Dormant").run()
    assert not app_test.exception
    grid = next(
        item.value
        for item in app_test.dataframe
        if "rfm_segment" in item.value and "customer_id" in item.value
    )
    assert set(grid.rfm_segment) == {"Dormant"}


def test_zero_reward_budget_excludes_loyalty_offers(app_test):
    app_test.number_input[3].set_value(0)
    app_test.button[0].click().run()
    assert not app_test.exception and not app_test.error
    assert not app_test.session_state["scenario"]["frame"].offer_id.eq("loyalty_500").any()


def test_zero_spending_budget_renders_empty_scenario(app_test):
    app_test.number_input[0].set_value(0)
    app_test.button[0].click().run()
    assert not app_test.exception and not app_test.error
    assert app_test.session_state["scenario"]["frame"].empty


def test_scenario_template_applies_limits_and_preserves_comparison(app_test):
    app_test.selectbox[0].set_value("Lean budget").run()
    assert app_test.number_input[0].value == 800
    assert app_test.number_input[1].value == 100
    assert app_test.number_input[2].value == 0.25
    assert app_test.number_input[3].value == 15000
    app_test.button[0].click().run()
    assert not app_test.exception and not app_test.error
    scenario = app_test.session_state["scenario"]
    assert scenario["diagnostics"]["spend"] <= 800 + 1e-6
    assert len(scenario["frame"]) <= 100
    assert scenario["frame"].points.sum() <= 15000
    assert scenario["reserve"] == 0.2
    assert len(app_test.session_state["scenario_history"]) == 1
    assert any("vs baseline" in str(metric.delta) for metric in app_test.metric)
    app_test.selectbox[0].set_value("No reward points").run()
    assert app_test.number_input[3].value == 0
    app_test.button[0].click().run()
    assert not app_test.exception and not app_test.error
    assert app_test.session_state["scenario"]["frame"].points.sum() == 0
    assert len(app_test.session_state["scenario_history"]) == 2


def test_streamlit_scenario_works_with_free_solver(app_test):
    app_test.selectbox[1].set_value("HiGHS").run()
    app_test.number_input[0].set_value(400)
    app_test.number_input[1].set_value(40)
    app_test.button[0].click().run()
    assert not app_test.exception and not app_test.error
    scenario = app_test.session_state["scenario"]
    assert scenario["solver"] == "HiGHS (SciPy)"
    assert scenario["diagnostics"]["spend"] <= 400 + 1e-6
    assert len(scenario["frame"]) <= 40
    assert scenario["diagnostics"]["all_constraints_passed"]


def test_reviewed_plan_persists_and_has_release_identity(app_test):
    app_test.button[0].click().run()
    assert not app_test.exception and not app_test.error
    button = next(item for item in app_test.button if item.label == "Save reviewed scenario")
    button.click().run()
    assert not app_test.exception and any("audit reference" in item.value for item in app_test.success)
    from decision_platform.runtime import saved_plans

    plans = saved_plans(ROOT, "local-owner")
    assert plans and plans[0]["release_id"] != "unverified"
    assert len(plans[0]["allocation"]) == len(app_test.session_state["scenario"]["frame"])


def test_joint_price_action_returns_feasible_shared_capacity(app_test):
    app_test.radio[0].set_value("Pricing").run()
    button = next(item for item in app_test.button if item.label == "Optimize price strategies")
    button.click().run()
    assert not app_test.exception and not app_test.error
    _, prices, campaign, receipt = app_test.session_state["price_plan"]
    assert receipt["all_constraints_passed"]
    assert not prices.duplicated(["zone_id", "period"]).any()
    assert (prices.remaining_with_reserve >= -1e-6).all()
    assert campaign.cost.sum() <= 1600 + 1e-6


@pytest.mark.parametrize(
    "case,conclusion",
    [
        ("weekend_decline", "Weekend trips changed by"),
        ("segment_decline", "segment has the lowest current-to-prior frequency ratio"),
        ("cannibalization", "The best observed treatment mean is"),
        ("unused_capacity", "has the most forecast off-peak headroom"),
        ("enrollment_vs_value", "The highest observed enrollment rate is"),
    ],
)
def test_analyst_case_displays_its_business_conclusion(app_test, case, conclusion):
    app_test.radio[0].set_value("Analyst workbench").run()
    app_test.selectbox[0].set_value(case).run()
    assert not app_test.exception and not app_test.error
    assert any(conclusion in item.value for item in app_test.markdown)
    assert app_test.code
