"""Feasible targeting baselines and exploratory held-out policy evaluation."""
import numpy as np
import pandas as pd
from .optimization import constraint_matrix
from .config import write_json

def greedy(frame,capacity,budget,limit,roi,rank,points_budget=35000):
    """Every prefix is feasible; individual ROI filtering is deliberately conservative."""
    matrix,upper,_=constraint_matrix(frame,capacity,budget,limit,roi,points_budget)
    used=np.zeros(len(upper));chosen=[]
    for i in frame.sort_values(rank,ascending=False,kind="stable").index:
        row=frame.loc[i]
        if not row.eligible or row.net_contribution<roi*row.cost:continue
        cost=matrix[:,i].toarray().ravel()
        if np.all(used+cost<=upper+1e-6):
            chosen.append(i);used+=cost
    return frame.loc[chosen].copy()

def compare(cfg,frame,capacity,optimized):
    rows=[]
    for name,selected in [("Joint optimization",optimized),
        ("Propensity ranking",greedy(frame,capacity,cfg.budget,cfg.campaign_limit,cfg.min_roi,"propensity_probability")),
        ("Frequency rules",greedy(frame,capacity,cfg.budget,cfg.campaign_limit,cfg.min_roi,"trips_90d"))]:
        rows.append({"policy":name,"contacts":len(selected),"spend":float(selected.cost.sum()),
            "net_contribution":float(selected.net_contribution.sum()),"incremental_trips":float(selected.incremental_trips.sum()),
            "objective":float(selected.objective_value.sum())})
    pd.DataFrame(rows).to_csv(cfg.path("outputs","policy_comparison.csv"),index=False)
    test=pd.read_csv(cfg.path("outputs","heldout_policy_scores.csv"))
    offers=["offpeak_15","weekend_20","loyalty_500"]
    arms={"offpeak_15":"Off-peak 15%","weekend_20":"Weekend 20%","loyalty_500":"500 loyalty points"}
    values=test[[o+"_value" for o in offers]].to_numpy()
    recommended=np.array([arms[o] for o in offers])[values.argmax(axis=1)]
    recommended=np.where(values.max(axis=1)>0,recommended,"Control")
    # Assignment probability is exactly 1/4 by design, not inferred from test outcomes.
    weighted=np.where(test.arm.eq(recommended),test.net_contribution*4,0)
    control=np.where(test.arm.eq("Control"),test.net_contribution*4,0)
    delta=weighted-control;rng=np.random.default_rng(cfg.seed+73)
    bootstrap=np.array([rng.choice(delta,len(delta),replace=True).mean() for _ in range(500)])
    result={"n_test":len(test),"incremental_contribution_per_customer":float(delta.mean()),
        "ci_low":float(np.quantile(bootstrap,.025)),"ci_high":float(np.quantile(bootstrap,.975)),
        "bootstrap_replicates":500,"policy":"Choose positive highest modeled offer value; otherwise control",
        "interpretation":"Exploratory inverse-propensity-weighted estimate on untouched randomized customers. This unconstrained offer rule is distinct from the capacity-constrained optimized campaign. Wide intervals and model-selection uncertainty require a new randomized policy trial; simulation only."}
    write_json(cfg.path("outputs","policy_evaluation.json"),result)
    return rows,result
