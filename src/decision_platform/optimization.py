"""Binary campaign allocation with identical constraints in Gurobi and HiGHS."""
from dataclasses import dataclass
import numpy as np
import pandas as pd
from scipy.optimize import milp, Bounds, LinearConstraint
from scipy.sparse import csr_matrix
from .config import write_json
from .runtime import bounded_operation

@dataclass
class Allocation:
    selected: pd.DataFrame
    solver: str
    status: str
    objective: float
    gap: float | None
    diagnostics: dict

def candidates(cfg,current,uplift,offers,kind="promotion"):
    frame=uplift.merge(current[["customer_id","eligible","home_zone","avg_toll","clv_12m","rfm_segment","propensity_probability","trips_90d"]],on="customer_id",validate="many_to_one")
    frame=frame.merge(offers,on="offer_id",validate="many_to_one")
    # Declared 25% planning shrinkage, not a statistical lower confidence bound.
    frame["incremental_trips"]=np.maximum(frame.incremental_trips_raw,0)*.75
    reward=frame.offer_id.eq("loyalty_500")
    frame["cost"]=np.where(reward,5.35,np.maximum(frame.predicted_treated_trips,0)*frame.avg_toll.clip(lower=8)*frame.discount_pct+.35)
    frame["points"]=np.where(reward,500,0)
    if kind=="promotion":frame=frame[~reward].copy()
    elif kind=="loyalty":frame=frame[reward].copy()
    frame["zone_id"]=frame.home_zone.astype(int)
    frame["incremental_gross_contribution"]=frame.incremental_trips*frame.avg_toll.clip(lower=8)*cfg.contribution_margin
    frame["net_contribution"]=frame.incremental_gross_contribution-frame.cost
    frame["network_value"]=.25*frame.incremental_trips
    frame["incremental_value_days31_90"]=frame.get("incremental_value_days31_90",0.)
    frame["incremental_retention_90d"]=frame.get("incremental_retention_90d",0.)
    # Retention KPI is separate: monetizing it again would double count later margin.
    frame["objective_value"]=frame.net_contribution+frame.network_value+frame.incremental_value_days31_90
    # Bounded demonstration size supports the restricted Gurobi license.
    best=frame[frame.eligible].groupby("customer_id").objective_value.max().nlargest(600).index
    frame=frame[frame.customer_id.isin(best)].reset_index(drop=True)
    frame["candidate_id"]=np.arange(len(frame))
    return frame

def constraint_matrix(frame,capacity,budget,campaign_limit,min_roi,points_budget=None):
    n=len(frame);rows=[];upper=[];names=[]
    def add(values,bound,name):
        rows.append(np.asarray(values,dtype=float));upper.append(float(bound));names.append(name)
    add(frame.cost,budget,"budget")
    add(np.ones(n),campaign_limit,"campaign_size")
    # Net ROI >= threshold is linear because total cost is nonnegative.
    add(min_roi*frame.cost-frame.net_contribution,0,"minimum_net_roi")
    for customer,positions in frame.groupby("customer_id").indices.items():
        row=np.zeros(n);row[positions]=1;add(row,1,f"contact:{customer}")
    for _,cell in capacity.iterrows():
        mask=frame.zone_id.eq(cell.zone_id)&frame.period.eq(cell.period)
        add(np.where(mask,frame.incremental_trips,0),cell.available_trips,f"capacity:{cell.zone_id}:{cell.period}")
    for offer,group in frame.groupby("offer_id"):
        add(frame.offer_id.eq(offer),group.inventory.iloc[0],f"inventory:{offer}")
    if points_budget is not None:
        add(frame.points,points_budget,"loyalty_points")
    return csr_matrix(np.asarray(rows)),np.asarray(upper),names

def validate_inputs(frame,capacity,budget,campaign_limit,min_roi,solver,points_budget):
    if solver not in {"auto","gurobi","highs"}:raise ValueError("Unknown solver")
    limits=[budget,campaign_limit,min_roi]+([] if points_budget is None else [points_budget])
    if not all(np.isfinite(v) and v>=0 for v in limits):raise ValueError("Limits must be finite and nonnegative")
    if int(campaign_limit)!=campaign_limit or points_budget is not None and int(points_budget)!=points_budget:raise ValueError("Contacts and points must be integers")
    required={"customer_id","offer_id","eligible","zone_id","period","cost","net_contribution","incremental_trips","objective_value","inventory","points"}
    if not required.issubset(frame):raise ValueError("Candidate schema is incomplete")
    if frame[list(required)].isna().any().any():raise ValueError("Missing candidate values")
    numeric=["cost","net_contribution","incremental_trips","objective_value","inventory","points"]
    if not np.isfinite(frame[numeric].to_numpy(dtype=float)).all():raise ValueError("Nonfinite candidate values")
    if (frame[["cost","incremental_trips","inventory","points"]]<0).any().any():raise ValueError("Negative candidate resources")
    if not frame.eligible.isin([True,False]).all():raise ValueError("Eligibility must be boolean")
    if frame.duplicated(["customer_id","offer_id"]).any():raise ValueError("Duplicate customer/offer candidates")
    if (frame.groupby("offer_id").inventory.nunique()>1).any():raise ValueError("Inconsistent offer inventory")
    if not {"zone_id","period","available_trips","baseline_over_capacity"}.issubset(capacity):raise ValueError("Capacity schema is incomplete")
    if capacity.duplicated(["zone_id","period"]).any():raise ValueError("Duplicate capacity cells")
    if capacity.isna().any().any() or not np.isfinite(capacity.available_trips).all() or (capacity.available_trips<0).any():raise ValueError("Invalid capacity values")
    cells=set(zip(capacity.zone_id,capacity.period))
    if any(pair not in cells for pair in zip(frame.zone_id,frame.period)):raise ValueError("Candidate has no matching capacity cell")

@bounded_operation
def solve(frame,capacity,budget=1600,campaign_limit=180,min_roi=.15,solver="auto",points_budget=None):
    validate_inputs(frame,capacity,budget,campaign_limit,min_roi,solver,points_budget)
    if capacity.baseline_over_capacity.any():
        raise ValueError("Baseline plus safety reserve exceeds capacity before campaign allocation")
    frame=frame.reset_index(drop=True)
    if frame.empty:
        return Allocation(frame,"none","empty",0.,0.,{"reason":"no candidates","candidate_count":0,"customer_count":0,"budget":budget,"spend":0.,"net_contribution":0.,"incremental_trips":0.,"net_roi":None,"all_constraints_passed":True,"min_roi":min_roi,"binding_constraints":[]})
    matrix,upper,names=constraint_matrix(frame,capacity,budget,campaign_limit,min_roi,points_budget)
    fallback=None;selection=None;gap=None;status="unknown"
    if solver in ("auto","gurobi"):
        try:
            import gurobipy as gp
            with gp.Env(empty=True) as env:
                env.setParam("OutputFlag",0);env.start()
                with gp.Model("decision_allocation",env=env) as model:
                    x=model.addMVar(len(frame),vtype=gp.GRB.BINARY,ub=frame.eligible.astype(float).to_numpy(),name="allocate")
                    model.setObjective(frame.objective_value.to_numpy()@x,gp.GRB.MAXIMIZE)
                    model.addMConstr(matrix,x,"<",upper,name="policy")
                    model.Params.TimeLimit=30;model.Params.MIPGap=.001;model.Params.Seed=407
                    model.optimize()
                    if model.SolCount<1:
                        raise RuntimeError(f"Gurobi returned no feasible incumbent, status {model.Status}")
                    selection=x.X>.5;gap=float(model.MIPGap)
                    status="optimal" if model.Status==gp.GRB.OPTIMAL else "feasible_time_limit"
                    actual="Gurobi"
        except (ImportError, ModuleNotFoundError) as exc:
            if solver=="gurobi": raise
            fallback=str(exc)
        except Exception as exc:
            # Only a Gurobi-specific availability/license failure may trigger fallback.
            if solver=="gurobi" or exc.__class__.__name__!="GurobiError": raise
            fallback=str(exc)
    if selection is None:
        solution=milp(-frame.objective_value.to_numpy(),integrality=np.ones(len(frame)),
            bounds=Bounds(np.zeros(len(frame)),frame.eligible.astype(float).to_numpy()),
            constraints=LinearConstraint(matrix,np.full(len(upper),-np.inf),upper),
            options={"time_limit":30,"mip_rel_gap":.001})
        if solution.x is None:
            raise RuntimeError(f"HiGHS did not return an incumbent: {solution.message}")
        selection=solution.x>.5;actual="HiGHS (SciPy)"
        status="optimal" if solution.success else "feasible_time_limit";gap=float(solution.mip_gap)
    lhs=matrix@selection.astype(float)
    violated=[names[i] for i in np.flatnonzero(lhs>upper+1e-6)]
    if violated:
        raise RuntimeError(f"Solver result violates policy: {violated}")
    chosen=frame[selection].copy()
    if chosen.customer_id.duplicated().any() or not chosen.eligible.all():
        raise RuntimeError("Customer contact/eligibility violation")
    diagnostics={"candidate_count":len(frame),"customer_count":frame.customer_id.nunique(),"constraint_count":len(names),
        "budget":budget,"spend":float(chosen.cost.sum()),"net_contribution":float(chosen.net_contribution.sum()),
        "incremental_trips":float(chosen.incremental_trips.sum()),"net_roi":float(chosen.net_contribution.sum()/chosen.cost.sum()) if chosen.cost.sum() else None,
        "all_constraints_passed":True,"fallback_reason":fallback,"min_roi":min_roi,
        "binding_constraints":[names[i] for i in np.flatnonzero(abs(lhs-upper)<1e-5)]}
    return Allocation(chosen,actual,status,float(chosen.objective_value.sum()),gap,diagnostics)

def allocate(cfg,current,uplift,offers,capacity,solver="auto"):
    frame=candidates(cfg,current,uplift,offers,kind="joint")
    joint=solve(frame,capacity,cfg.budget,cfg.campaign_limit,cfg.min_roi,solver,points_budget=35000)
    all_selected=joint.selected
    frame.to_csv(cfg.path("outputs","joint_candidates.csv"),index=False)
    frame[~frame.offer_id.eq("loyalty_500")].to_csv(cfg.path("outputs","promotion_candidates.csv"),index=False)
    promo=all_selected[~all_selected.offer_id.eq("loyalty_500")];loyalty=all_selected[all_selected.offer_id.eq("loyalty_500")]
    promo.to_csv(cfg.path("outputs","promotion_allocation.csv"),index=False)
    loyalty.to_csv(cfg.path("outputs","loyalty_allocation.csv"),index=False)
    from .policy import compare
    compare(cfg,frame,capacity,all_selected)
    sensitivity=[]
    for budget in [400,800,1200,1600,2000,2400]:
        scenario=solve(frame,capacity,budget,cfg.campaign_limit,cfg.min_roi,solver,points_budget=35000)
        sensitivity.append({"budget":budget,"contacts":len(scenario.selected),"spend":scenario.diagnostics["spend"],"net_contribution":scenario.diagnostics["net_contribution"],"objective_value":scenario.objective,"incremental_value_days31_90":float(scenario.selected.incremental_value_days31_90.sum()),"incremental_trips":scenario.diagnostics["incremental_trips"]})
    pd.DataFrame(sensitivity).to_csv(cfg.path("outputs","budget_frontier.csv"),index=False)
    combined=all_selected.groupby(["zone_id","period"]).incremental_trips.sum().rename("allocated_trips").reset_index()
    capacity=capacity.merge(combined,on=["zone_id","period"],how="left").fillna({"allocated_trips":0})
    capacity["final_utilization"]=(capacity.baseline_forecast+capacity.allocated_trips)/capacity.capacity_trips
    capacity["remaining_with_reserve"]=capacity.available_trips-capacity.allocated_trips
    if (capacity.remaining_with_reserve < -1e-6).any():raise RuntimeError("Combined capacity violated")
    capacity.to_csv(cfg.path("outputs","capacity.csv"),index=False)
    all_selected.to_csv(cfg.path("outputs","decision_table.csv"),index=False)
    def subtotal(selected):
        return {"solver":joint.solver,"status":joint.status,"gap":joint.gap,"spend":float(selected.cost.sum()),"net_contribution":float(selected.net_contribution.sum()),"incremental_trips":float(selected.incremental_trips.sum()),"all_constraints_passed":True}
    result={"promotion":subtotal(promo),"loyalty":subtotal(loyalty),"joint":{"solver":joint.solver,"status":joint.status,"gap":joint.gap,**joint.diagnostics},
        "combined":{"contacts":len(all_selected),"budget":cfg.budget,"spend":float(all_selected.cost.sum()),"net_contribution":float(all_selected.net_contribution.sum()),"incremental_trips":float(all_selected.incremental_trips.sum()),"points_awarded":int(all_selected.points.sum()),"all_constraints_passed":True},
        "scope":"One joint promotion/reward solve with shared budget, contacts, capacity, inventory, ROI and 35,000-point liability cap. At most 600 shortlisted customers × three offers; optimality applies to this shortlist, not all 8,000 customers.",
        "economics":"Expected synthetic 30-day contribution plus separately estimated discounted margin on days 31–90 and network value. Retention effect is reported separately to avoid double counting. No claimed incremental 12-month CLV. Dedicated randomized loyalty arm; full $5 liability plus $0.35 contact cost reserved. Effects shrunk by 25%; no measured real-world impact."}
    write_json(cfg.path("outputs","optimization_results.json"),result)
    return all_selected,capacity,result
