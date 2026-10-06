"""Repeat the complete seeded run and compare data and decision artifacts."""
import json,subprocess,sys,hashlib
import pandas as pd,numpy as np
from decision_platform.config import ROOT,write_json,frame_hash

def capture():
    raw={name:frame_hash(pd.read_parquet(ROOT/"data/silver"/(name+".parquet"))) for name in ["dim_customer","fact_trip","fact_digital_event"]}
    customers=pd.read_parquet(ROOT/"data/gold/customer_360.parquet").sort_values("customer_id").reset_index(drop=True)
    decisions=pd.read_csv(ROOT/"outputs/decision_table.csv").sort_values("customer_id").reset_index(drop=True)
    def clean(value):
        if isinstance(value,dict):return {k:clean(v) for k,v in value.items() if k not in ["training_seconds","runtime_seconds"]}
        if isinstance(value,list):return [clean(v) for v in value]
        return value
    core=clean(json.loads((ROOT/"outputs/model_metrics.json").read_text()))
    return raw,customers,decisions,core

def main():
    before,customers,decisions,core=capture()
    subprocess.run([sys.executable,"-m","decision_platform.cli","demo","--customers","8000","--solver","gurobi"],cwd=ROOT,check=True)
    after,new_customers,new_decisions,new_core=capture()
    assert before==after
    metric_differences=[]
    def compare(a,b,path="metrics"):
        if isinstance(a,dict):
            assert a.keys()==b.keys()
            for key in a:compare(a[key],b[key],path+"."+key)
        elif isinstance(a,list):
            assert len(a)==len(b)
            for i,(left,right) in enumerate(zip(a,b)):compare(left,right,path+f"[{i}]")
        elif isinstance(a,(int,float)) and not isinstance(a,bool):
            difference=abs(a-b);metric_differences.append(difference)
            assert difference<=1e-9,f"Held-out core model metrics changed at {path}: {a} versus {b}"
        else:assert a==b
    compare(core,new_core)
    assert customers.customer_id.equals(new_customers.customer_id)
    assert decisions.customer_id.equals(new_decisions.customer_id)
    assert decisions.offer_id.equals(new_decisions.offer_id)
    checked=["propensity_probability","churn_probability","attrition_probability","clv_12m","probabilistic_clv_12m"]
    errors={}
    for field in checked:
        np.testing.assert_allclose(customers[field],new_customers[field],rtol=0,atol=1e-9,equal_nan=True)
        errors[field]=float(np.nanmax(np.abs(customers[field]-new_customers[field])))
    np.testing.assert_allclose(decisions[["cost","incremental_trips","net_contribution"]],new_decisions[["cost","incremental_trips","net_contribution"]],rtol=0,atol=1e-9)
    manifest=json.loads((ROOT/"outputs/manifest.json").read_text())
    write_json(ROOT/"outputs/reproducibility.json",{"status":"passed","release":"0.4.0","git_sha":manifest["git_sha"],"seed":407,"customers":8000,"repeated_complete_pipeline":True,"core_metrics_reproduce":True,"core_metrics_max_absolute_difference":max(metric_differences),"raw_dataset_hashes_match":True,"raw_frame_hashes":after,"prediction_max_absolute_differences":errors,"allocation_customer_offer_pairs_match":True,"tolerance":1e-9})
    print("Seeded end-to-end repeat verified")

if __name__=="__main__":main()
