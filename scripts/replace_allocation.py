from pathlib import Path

p = Path(__file__).resolve().parents[1] / "src" / "decision_platform" / "optimization.py"
s = p.read_text()
s = (
    s[: s.index("def allocate(")]
    + """def allocate(cfg,current,uplift,offers,capacity,solver="auto"):
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
        sensitivity.append({"budget":budget,"contacts":len(scenario.selected),"spend":scenario.diagnostics["spend"],"net_contribution":scenario.diagnostics["net_contribution"],"incremental_trips":scenario.diagnostics["incremental_trips"]})
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
        "economics":"Expected synthetic 30-day outcomes. Dedicated randomized loyalty arm; full $5 reward liability plus $0.35 contact cost is reserved. Promotion costs include subsidies on baseline trips. Effects use a declared 25% planning shrinkage; no measured real-world impact."}
    write_json(cfg.path("outputs","optimization_results.json"),result)
    return all_selected,capacity,result
"""
)
p.write_text(s, encoding="utf-8")
