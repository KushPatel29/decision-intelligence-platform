"""Integration checks over a completed pipeline run; skipped on a clean checkout."""

import json

import numpy as np
import pandas as pd
import pytest

from decision_platform.config import ROOT, Config
from decision_platform.features import FEATURES
from decision_platform.optimization import constraint_matrix
from decision_platform.simulation import OFFERS


@pytest.fixture
def outputs():
    if not (ROOT / "outputs" / "summary.json").exists():
        pytest.skip("Run the pipeline to enable artifact integration checks")
    return ROOT / "outputs"


def test_end_to_end_evidence(outputs):
    summary = json.loads((outputs / "summary.json").read_text())
    assert summary["constraints_passed"] and summary["optimality_certified"]
    assert summary["trips"] > 1_000_000 and summary["selected_contacts"] > 0
    metrics = json.loads((outputs / "model_metrics.json").read_text())
    for name in ["propensity", "churn", "attrition"]:
        assert metrics["customer"][name]["test_calibrated"]["roc_auc"] >= 0.7


def test_plan_satisfies_every_shared_constraint(outputs):
    cfg = Config()
    frame = pd.read_csv(outputs / "joint_candidates.csv")
    selected = pd.read_csv(outputs / "decision_table.csv")
    capacity = pd.read_csv(outputs / "capacity.csv")
    assert set(frame.offer_id) <= set(OFFERS)
    matrix, upper, _ = constraint_matrix(
        frame, capacity, cfg.budget, cfg.campaign_limit, cfg.min_roi, cfg.points_budget
    )
    x = frame.candidate_id.isin(selected.candidate_id).to_numpy(dtype=float)
    assert (matrix @ x <= upper + 1e-6).all()
    assert not selected.customer_id.duplicated().any() and selected.eligible.all()
    assert (capacity.remaining_with_reserve >= -1e-6).all()


def test_certificate_proves_optimality(outputs):
    result = json.loads((outputs / "optimization_results.json").read_text())
    certificate = result["certification"]
    assert certificate["proven_optimal"]
    assert certificate["relative_gap_to_lp_bound"] <= 1e-4
    assert (
        certificate["fixed_to_zero"] + certificate["fixed_to_one"] + certificate["free_variables"]
        == certificate["variables"]
    )


def test_folds_are_purged_and_features_end_before_cutoff(outputs):
    frame = pd.read_parquet(ROOT / "data" / "gold" / "customer_month.parquet")
    train, val, test = (frame[frame.split.eq(s)] for s in ["train", "validation", "test"])
    assert train.label_end.max() <= val.as_of.min()
    assert val.label_end.max() <= test.as_of.min()
    present = frame.feature_max_timestamp.notna()
    assert (frame.loc[present, "feature_max_timestamp"] < frame.loc[present, "as_of"]).all()


def test_trial_is_powered_balanced_and_isolated(outputs):
    result = json.loads((outputs / "experiment_results.json").read_text())
    assert len(result["actual_per_arm"]) == len(OFFERS) + 1
    assert result["powered_for_planned_mde"] and result["srm_p_value"] > 0.01
    assert result["max_abs_smd"] < 0.1
    trial = pd.read_parquet(ROOT / "data/silver/fact_campaign_result.parquet")
    assert not any(c.startswith(("latent_", "true_")) for c in trial.columns)
    scored = pd.read_csv(outputs / "heldout_policy_scores.csv")
    assert set(scored.customer_id) == set(trial.loc[trial.split.eq("test"), "customer_id"])


def test_truth_never_enters_features_or_serving(outputs):
    assert not any(c.startswith(("future_", "target_", "latent_", "true_")) for c in FEATURES)
    serving = outputs / "serving"
    for name in ["customers", "candidates", "decisions"]:
        columns = pd.read_parquet(serving / f"{name}.parquet").columns
        assert not any(c.startswith(("latent_", "true_")) for c in columns), name


def test_optimized_plan_beats_naive_targeting_on_true_value(outputs):
    policy = pd.read_csv(outputs / "policy_comparison.csv").set_index("policy")
    optimized = policy.loc["Optimized (MIP)", "true_value"]
    for naive in ["Random targeting", "RFM segment playbook"] + [
        p for p in policy.index if p.startswith("Propensity")
    ]:
        assert optimized > policy.loc[naive, "true_value"]
    assert policy.loc["Oracle optimum (true effects)", "true_value"] >= optimized - 1e-6


def test_reward_ledger_reconciles(outputs):
    ledger = pd.read_csv(outputs / "loyalty_ledger.csv")
    np.testing.assert_allclose(
        ledger.points_balance, ledger.points_earned + ledger.points_awarded - ledger.points_redeemed
    )
    assert (ledger.points_balance >= 0).all() and ledger.points_redeemed.sum() > 0


def test_planted_defects_and_anomalies_are_detected(outputs):
    monitor = json.loads((outputs / "data_quality_monitor.json").read_text())["evaluation_against_planted"]
    assert monitor["recall"] >= 0.75
    metrics = json.loads((outputs / "model_metrics.json").read_text())["customer"]["anomaly"]
    assert metrics["evaluation_against_planted"]["isolation_forest"]["recall"] >= 0.5


def test_budget_frontier_is_monotone(outputs):
    frontier = pd.read_csv(outputs / "budget_frontier.csv")
    assert (frontier.objective_value.diff().dropna() >= -1e-6).all()
    assert (frontier.spend <= frontier.budget + 1e-6).all()


def test_tracking_runs_exist_when_enabled(outputs):
    statuses = []
    for name in ["propensity", "churn", "attrition", "clv", "uplift", "elasticity", "demand"]:
        file = outputs / "models" / f"{name}.tracking.json"
        if not file.exists():
            pytest.skip("Tracking disabled for this run")
        statuses.append(json.loads(file.read_text())["status"])
    assert set(statuses) == {"tracked"}


def test_uplift_scorer_reproduces_the_pipeline_effects(outputs):
    """The registry scorer rebuilds the ensemble from stored parts; it must match what the plan used."""
    import joblib

    from decision_platform.scoring import uplift_effects

    bundle = joblib.load(outputs / "models" / "uplift.joblib")
    customers = pd.read_parquet(ROOT / "data/gold/customer_360.parquet").set_index("customer_id")
    candidates = pd.read_parquet(outputs / "serving" / "candidates.parquet").sample(300, random_state=7)
    effects = uplift_effects(bundle, customers.loc[candidates.customer_id].reset_index())
    for period, column in [
        ("Peak", "trips_peak"),
        ("Off-peak", "trips_offpeak"),
        ("Weekend", "trips_weekend"),
    ]:
        scored = [effects.iloc[i][f"{o}|{period}"] for i, o in enumerate(candidates.offer_id)]
        np.testing.assert_allclose(scored, candidates[column].to_numpy(), atol=1e-9)


def test_demand_scorer_reproduces_the_plan_forecast(outputs):
    """The registered demand model is the refit one the capacity plan used, scored the same way."""
    import joblib

    from decision_platform.forecasting import daily_cells, horizon_dataset
    from decision_platform.scoring import score_bundle

    bundle = joblib.load(outputs / "models" / "demand.joblib")
    context = pd.read_parquet(ROOT / "data/silver/external_context.parquet")
    trips = pd.read_parquet(
        ROOT / "data/silver/fact_trip.parquet", columns=["timestamp", "zone_id", "period"]
    )
    future = horizon_dataset(
        daily_cells(Config(), trips, context), context, origins=[pd.Timestamp("2025-10-01")]
    )
    plan = pd.read_csv(outputs / "decision_forecast.csv")
    np.testing.assert_allclose(score_bundle("demand", bundle, future), plan.baseline_forecast, rtol=1e-9)
