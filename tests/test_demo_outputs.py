"""Run after `decision-platform demo`; skip on a clean CI checkout."""
import json
import pandas as pd
import pytest
from decision_platform.config import ROOT

@pytest.fixture
def outputs():
    if not (ROOT/"outputs"/"summary.json").exists():pytest.skip("Run demo to enable artifact integration checks")
    return ROOT/"outputs"

def test_end_to_end_evidence(outputs):
    summary=json.loads((outputs/"summary.json").read_text())
    assert summary["constraints_passed"]
    assert summary["trips"]>1000
    assert summary["selected_contacts"]>0
    assert (outputs/"dashboard.html").stat().st_size>10000
    metrics=json.loads((outputs/"model_metrics.json").read_text())
    for name in ["propensity","churn","attrition"]:
        assert metrics["customer"][name]["test_calibrated"]["roc_auc"]>=.55

def test_combined_campaign_constraints(outputs):
    opt=json.loads((outputs/"optimization_results.json").read_text())
    decisions=pd.read_csv(outputs/"decision_table.csv")
    cap=pd.read_csv(outputs/"capacity.csv")
    assert decisions.cost.sum()<=opt["combined"]["budget"]+1e-6
    assert not decisions.customer_id.duplicated().any()
    assert decisions.eligible.all()
    assert (cap.remaining_with_reserve>=-1e-6).all()
    if not decisions.empty:
        assert decisions.net_contribution.sum()/decisions.cost.sum()>=.15-1e-6

def test_folds_are_purged_and_labels_complete(outputs):
    frame=pd.read_parquet(ROOT/"data"/"gold"/"customer_month.parquet")
    train=frame[frame.split.eq("train")];val=frame[frame.split.eq("validation")];test=frame[frame.split.eq("test")]
    assert train.label_end.max()<=val.as_of.min()
    assert val.label_end.max()<=test.as_of.min()
    assert (frame.feature_max_timestamp.dropna()<frame.loc[frame.feature_max_timestamp.notna(),"as_of"]).all()

def test_all_required_tracking_runs_exist(outputs):
    names=["propensity","churn","attrition","clv","uplift","elasticity","demand"]
    statuses=[]
    for name in names:
        file=outputs/"models"/f"{name}.tracking.json"
        if not file.exists():pytest.skip("Tracking disabled for this run")
        statuses.append(json.loads(file.read_text())["status"])
    assert set(statuses)=={"tracked"}
