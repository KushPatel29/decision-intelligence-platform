from dataclasses import replace
import numpy as np
import pandas as pd
import pytest
from decision_platform.config import Config
from decision_platform.features import connect,snapshot,FEATURES
from decision_platform.optimization import solve
from decision_platform.experiments import sample_size,difference
from decision_platform.monitoring import psi

@pytest.fixture
def small_db(tmp_path):
    cfg=replace(Config(),root=tmp_path)
    (tmp_path/"data").mkdir()
    from decision_platform.config import ROOT
    (tmp_path/"sql").mkdir()
    for name in ["customer_features.sql","customer_labels.sql"]:
        (tmp_path/"sql"/name).write_text((ROOT/"sql"/name).read_text())
    customer=pd.DataFrame({"customer_id":["C1","C2"],"created_at":pd.to_datetime(["2023-01-01","2023-02-01"]),
        "customer_type":["Personal","Business"],"autopay":[True,False],"transponder_flag":[True,True],
        "home_zone":[0,1],"eligible":[True,False],"account_status":["Active","Active"]})
    trips=pd.DataFrame({"customer_id":["C1","C1","C1"],"timestamp":pd.to_datetime(["2025-03-01 12:00","2025-04-01 00:00","2025-04-12 12:00"]),
        "final_charge":[10.,999.,20.],"toll":[10.,999.,20.],"distance_km":[20.,20.,20.],"discount":[0.,0.,0.],"period":["Peak","Peak","Off-peak"]})
    digital=pd.DataFrame({"customer_id":["C1"],"timestamp":pd.to_datetime(["2025-04-01 00:00"]),"event_type":["app_login"]})
    loyalty=pd.DataFrame({"customer_id":["C1"],"timestamp":pd.to_datetime(["2025-03-01"]),"points_earned":[20]})
    db=connect(cfg,{"dim_customer":customer,"fact_trip":trips,"fact_digital_event":digital,"fact_loyalty_points":loyalty})
    yield db,cfg
    db.close()

def test_future_events_cannot_change_features(small_db):
    db,cfg=small_db
    before=snapshot(db,cfg,"2025-04-01")
    assert before.loc[before.customer_id.eq("C1"),"trips_30d"].iloc[0]==0  # March 1 is outside March 2+.
    assert before.loc[before.customer_id.eq("C1"),"digital_events_30d"].iloc[0]==0
    db.execute("UPDATE silver.fact_trip SET final_charge=123456, toll=123456 WHERE timestamp >= '2025-04-01'")
    after=snapshot(db,cfg,"2025-04-01")
    pd.testing.assert_frame_equal(before[FEATURES],after[FEATURES])
    assert before.future_margin_90d.sum()!=after.future_margin_90d.sum()

def test_target_boundary_and_cold_start(small_db):
    db,cfg=small_db
    frame=snapshot(db,cfg,"2025-04-01").set_index("customer_id")
    assert frame.loc["C1","future_trips_30d"]==2
    assert frame.loc["C2","trips_90d"]==0
    assert frame.loc["C2","target_propensity"]==0
    assert frame[FEATURES].notna().all().all()

def test_censored_labels_rejected(small_db):
    db,cfg=small_db
    with pytest.raises(ValueError,match="censored"):
        snapshot(db,cfg,"2025-11-01")

def allocation_fixture():
    rows=pd.DataFrame({"customer_id":["A","A","B","C","D"],"offer_id":["one","two","one","two","one"],
        "eligible":[True,True,True,False,True],"zone_id":[0]*5,"period":["Off-peak"]*5,
        "cost":[8.,5.,6.,1.,9.],"net_contribution":[10.,8.,7.,100.,-8.],
        "incremental_trips":[3.,2.,2.,1.,4.],"objective_value":[10.,8.,7.,100.,-8.],
        "inventory":[1,2,1,2,1],"points":[0]*5})
    capacity=pd.DataFrame({"zone_id":[0],"period":["Off-peak"],"available_trips":[4.],"baseline_over_capacity":[False]})
    return rows,capacity

def test_optimizer_enforces_scarce_resources():
    rows,capacity=allocation_fixture()
    result=solve(rows,capacity,budget=11,campaign_limit=2,min_roi=.5,solver="highs")
    assert set(result.selected.customer_id)=={"A","B"}
    assert result.selected.cost.sum()==11
    assert result.selected.incremental_trips.sum()==4
    assert result.objective==15
    assert result.diagnostics["all_constraints_passed"]

def test_zero_budget_allows_empty_campaign():
    rows,capacity=allocation_fixture()
    result=solve(rows,capacity,budget=0,solver="highs")
    assert result.selected.empty

def test_ineligible_customer_is_never_selected():
    rows,capacity=allocation_fixture()
    result=solve(rows,capacity,budget=100,campaign_limit=10,solver="highs")
    assert "C" not in set(result.selected.customer_id)
    assert not result.selected.customer_id.duplicated().any()

def test_roi_constraint_can_reject_otherwise_positive_objective():
    rows,capacity=allocation_fixture()
    rows.loc[:,"net_contribution"]=-2
    rows.loc[:,"objective_value"]=10
    result=solve(rows,capacity,budget=100,min_roi=.15,solver="highs")
    assert result.selected.empty

def test_baseline_capacity_failure_is_explicit():
    rows,capacity=allocation_fixture();capacity["baseline_over_capacity"]=True
    with pytest.raises(ValueError,match="Baseline"):
        solve(rows,capacity,solver="highs")

def test_gurobi_and_highs_have_same_optimal_objective():
    pytest.importorskip("gurobipy")
    rows,capacity=allocation_fixture()
    a=solve(rows,capacity,budget=11,min_roi=.5,solver="highs")
    try:
        b=solve(rows,capacity,budget=11,min_roi=.5,solver="gurobi")
    except Exception as exc:
        if exc.__class__.__name__=="GurobiError":pytest.skip(str(exc))
        raise
    assert a.objective==pytest.approx(b.objective)

def test_power_scales_with_effect_size_and_comparisons():
    assert sample_size(mde=.03)>sample_size(mde=.05)
    assert sample_size(comparisons=2)>sample_size(comparisons=1)
    with pytest.raises(ValueError):sample_size(baseline=.99,mde=.05)

def test_interval_contains_zero_under_equal_observed_means():
    result=difference([0,1]*100,[0,1]*100)
    assert result["ci_low"]<0<result["ci_high"]
    assert result["p_adjusted"]==1

def test_drift_distinguishes_stationarity_from_shift():
    rng=np.random.default_rng(123)
    reference=rng.normal(0,1,10000)
    assert psi(reference,reference)==pytest.approx(0)
    assert psi(reference,rng.normal(2,1,10000))>.2

def test_feature_allowlist_excludes_outcomes_and_simulator_oracle():
    assert not any(c.startswith(("future_","target_","latent_","true_")) for c in FEATURES)
