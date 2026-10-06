import json

import numpy as np
import pandas as pd
import pytest

from decision_platform.config import ROOT
from decision_platform.optimization import constraint_matrix


@pytest.fixture
def outputs():
    if not (ROOT / "outputs/joint_candidates.csv").exists():
        pytest.skip("Run version 0.2 demo first")
    return ROOT / "outputs"


def test_powered_four_arm_trial_and_test_identity_isolation(outputs):
    trial = pd.read_parquet(ROOT / "data/silver/fact_campaign_result.parquet")
    result = json.loads((outputs / "experiment_results.json").read_text())
    assert len(result["actual_per_arm"]) == 4
    assert min(result["actual_per_arm"].values()) >= result["required_per_arm"]
    scored = pd.read_csv(outputs / "heldout_policy_scores.csv")
    assert set(scored.customer_id) == set(trial.loc[trial.split.eq("test"), "customer_id"])
    assert set(scored.customer_id).isdisjoint(set(trial.loc[trial.split.eq("train"), "customer_id"]))


def test_joint_solution_has_reward_and_full_shared_constraints(outputs):
    frame = pd.read_csv(outputs / "joint_candidates.csv")
    selected = pd.read_csv(outputs / "decision_table.csv")
    capacity = pd.read_csv(outputs / "capacity.csv")
    assert set(frame.offer_id) == {"offpeak_15", "weekend_20", "loyalty_500"}
    matrix, upper, _ = constraint_matrix(frame, capacity, 1600, 180, 0.15, 35000)
    selection = frame.candidate_id.isin(selected.candidate_id).to_numpy(dtype=float)
    assert (matrix @ selection <= upper + 1e-6).all()
    assert (frame.loc[frame.offer_id.eq("loyalty_500"), "cost"] == 5.35).all()


def test_reward_ledger_reconciles_without_negative_balance(outputs):
    ledger = pd.read_csv(outputs / "loyalty_ledger.csv")
    np.testing.assert_allclose(
        ledger.points_balance, ledger.points_earned + ledger.points_awarded - ledger.points_redeemed
    )
    assert (ledger.points_balance >= 0).all()
    assert ledger.points_redeemed.sum() > 0


def test_probabilistic_value_has_finite_predictions_including_one_purchase(outputs):
    values = pd.read_csv(outputs / "probabilistic_clv.csv")
    assert (values.frequency.eq(0)).any()
    assert np.isfinite(values.probabilistic_clv_12m).all()
    assert (values.probabilistic_clv_12m >= 0).all()
    assert values.probability_alive.between(0, 1).all()


def test_policy_frontier_is_monotone_on_fixed_candidate_population(outputs):
    frontier = pd.read_csv(outputs / "budget_frontier.csv")
    assert (frontier.objective_value.diff().dropna() >= -1e-6).all()
    assert (frontier.spend <= frontier.budget + 1e-6).all()
    comparison = pd.read_csv(outputs / "policy_comparison.csv")
    assert comparison.iloc[0].objective >= comparison.iloc[1:].objective.max() - 1e-6


def test_all_causal_learner_comparisons_exist_and_are_finite(outputs):
    metrics = json.loads((outputs / "model_metrics.json").read_text())["uplift"]
    for offer in ["offpeak_15", "weekend_20", "loyalty_500"]:
        for learner in ["t_learner", "s_learner", "x_learner"]:
            assert np.isfinite(metrics[offer][learner]["qini"])


def test_native_bi_structural_receipt_is_clean(outputs):
    path = outputs / "powerbi_validation.json"
    if not path.exists():
        pytest.skip("Validate native Power BI project")
    receipt = json.loads(path.read_text())
    assert receipt["files_validated"] >= 25 and receipt["errors"] == []


def test_sagemaker_definition_gates_registry_and_batch(outputs):
    path = outputs / "sagemaker_pipeline.json"
    if not path.exists():
        pytest.skip("Compile SDK pipeline")
    pipeline = json.loads(path.read_text())
    steps = pipeline["Steps"]
    assert [s["Type"] for s in steps] == ["Processing", "Training", "Processing", "Condition"]
    names = {s["Name"] for s in steps[-1]["Arguments"]["IfSteps"]}
    assert {"RegisterCandidate-RegisterModel", "CreateBatchModel", "BatchScoreTestFeatures"} <= names
