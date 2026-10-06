from dataclasses import replace
import json
import numpy as np
import pandas as pd
import pytest
from decision_platform.config import Config,write_json,ROOT
from decision_platform.quality import select_regression
from decision_platform.runtime import pipeline_run,validate_release,artifact_manifest,audit_event,saved_plans
from decision_platform.optimization import solve
from decision_platform.monitoring import psi
from test_contracts import allocation_fixture

@pytest.mark.parametrize("field,value",[("cost",np.nan),("objective_value",np.inf),("incremental_trips",-1),("eligible","yes")])
def test_invalid_optimizer_inputs_are_rejected(field,value):
    frame,capacity=allocation_fixture();frame[field]=frame[field].astype(object);frame.loc[0,field]=value
    with pytest.raises(ValueError):solve(frame,capacity,solver="highs")

def test_missing_capacity_cannot_be_silently_unconstrained():
    frame,capacity=allocation_fixture();frame.loc[0,"zone_id"]=99
    with pytest.raises(ValueError,match="matching capacity"):solve(frame,capacity,solver="highs")

@pytest.mark.parametrize("kwargs",[{"budget":np.inf},{"points_budget":-1},{"campaign_limit":1.5},{"solver":"imaginary"}])
def test_bad_limits_are_rejected(kwargs):
    frame,capacity=allocation_fixture()
    with pytest.raises(ValueError):solve(frame,capacity,**kwargs)

def test_empty_candidate_shortlist_has_complete_diagnostics():
    frame,capacity=allocation_fixture();result=solve(frame.iloc[:0],capacity,solver="highs")
    assert result.selected.empty and result.diagnostics["all_constraints_passed"]
    assert result.diagnostics["spend"]==0

def test_baseline_wins_validation_without_using_test_outcomes():
    assert select_regression([1,2,3],{"learned":[2,3,4],"baseline":[1,2,3]})["selected"]=="baseline"

def test_constant_reference_shift_is_detected():
    assert psi(np.ones(100),np.ones(100))==0
    assert psi(np.ones(100),np.full(100,2))>.2

def test_run_lock_refuses_parallel_refresh_and_partial_serving(tmp_path):
    cfg=replace(Config(),root=tmp_path)
    with pipeline_run(cfg):
        with pytest.raises(RuntimeError,match="run lock"):
            with pipeline_run(cfg):pass
        with pytest.raises(ValueError,match="refresh"):validate_release(tmp_path)
        write_json(tmp_path/"outputs/example.json",{"ok":True})
    assert validate_release(tmp_path)["status"]=="verified"
    write_json(tmp_path/"outputs/example.json",{"ok":False})
    with pytest.raises(ValueError,match="integrity"):validate_release(tmp_path)

def test_failed_run_does_not_leave_readable_partial_release(tmp_path):
    cfg=replace(Config(),root=tmp_path)
    with pytest.raises(RuntimeError):
        with pipeline_run(cfg):raise RuntimeError("injected failure")
    assert not (tmp_path/".pipeline.lock").exists()
    with pytest.raises(ValueError,match="did not complete"):validate_release(tmp_path)

def test_saved_decisions_are_isolated_by_owner(tmp_path):
    audit_event(tmp_path,"owner-a","save_plan",{"allocation":[{"customer_id":"synthetic"}],"budget":1})
    audit_event(tmp_path,"owner-b","save_plan",{"budget":2})
    assert [p["budget"] for p in saved_plans(tmp_path,"owner-a")]==[1]
    assert saved_plans(tmp_path,"unknown")==[]

def test_joint_pricing_uses_capacity_and_exactly_one_price_per_cell():
    from decision_platform.pricing import optimize_prices
    frame,capacity=allocation_fixture()
    options=pd.DataFrame({"zone_id":[0,0],"period":["Off-peak"]*2,"capacity_trips":[10.,10.],"protected_load":[9.,5.],"available_trips":[1.,5.],"incremental_contribution":[30.,20.],"consumer_surplus_change":[-2.,1.],"eligible":[True,True]})
    prices,campaign,receipt=optimize_prices(options,frame,budget=11,contacts=2,roi=.5,solver="highs")
    assert len(prices)==1
    assert prices.protected_load.sum()+campaign.incremental_trips.sum()<=10+1e-8
    assert campaign.cost.sum()<=11 and receipt["all_constraints_passed"]

def test_local_model_gate_and_mart_grains():
    path=ROOT/"outputs/quality_gate.json"
    if not path.exists():pytest.skip("Generate data first")
    assert json.loads(path.read_text())["passed"]
    customers=pd.read_csv(ROOT/"outputs/customer_360.csv")
    assert not customers.customer_id.duplicated().any()
    np.testing.assert_allclose(customers.points_balance,customers.points_earned+customers.points_awarded-customers.points_redeemed)
    offers=pd.read_csv(ROOT/"outputs/customer_offer.csv")
    assert not offers.duplicated(["customer_id","offer_id"]).any()

def test_production_refuses_anonymous_local_mode(monkeypatch):
    monkeypatch.setenv("CORRIDOR_ENV","production");monkeypatch.setenv("CORRIDOR_AUTH","local")
    from streamlit.testing.v1 import AppTest
    app=AppTest.from_file(str(ROOT/"app.py")).run()
    assert not app.exception and app.error
    assert not app.radio
