import argparse
import json
import time
from pathlib import Path
from dataclasses import replace
from .config import Config, write_json, manifest

def _run(cfg,solver="auto",tracking=True):
    import pandas as pd
    from .external import fetch
    from .data import generate
    from .features import connect,build,snapshot
    from .models import fit_customer_models,fit_uplift,fit_elasticity,fit_demand
    from .experiments import simulate,analyze
    from .optimization import allocate
    from .monitoring import monitor
    from .report import report
    started=time.perf_counter()
    cfg.path("outputs").mkdir(parents=True,exist_ok=True)
    print("1/8 Download/cache public context",flush=True)
    context=fetch(cfg)
    print("2/8 Generate synthetic domains and validate",flush=True)
    frames,hidden=generate(cfg,context)
    write_json(cfg.path("outputs","manifest.json"),manifest(cfg,frames))
    print(f"  {len(frames['fact_trip']):,} trips, {len(frames['fact_digital_event']):,} digital events",flush=True)
    db=connect(cfg,frames)
    try:
        print("3/8 Build point-in-time SQL features",flush=True)
        snapshots,current=build(db,cfg)
        print("4/8 Train customer models and historical segmentation",flush=True)
        scored,customer_metrics=fit_customer_models(cfg,snapshots,current,tracking)
        from .advanced import explain,probabilistic_value,reward_ledger
        scored=probabilistic_value(cfg,frames["fact_trip"],scored)
        explain(cfg,scored)
        print("5/8 Simulate historical trial; evaluate causal models",flush=True)
        trial_features=snapshot(db,cfg,"2025-07-01",labels=False)
        trial=simulate(cfg,trial_features,hidden)
        reward_ledger(cfg)
        # Unified delivered bronze upload includes campaign facts generated later.
        for name in ["fact_campaign_result","fact_offer_exposure","fact_offer_enrollment","fact_offer_redemption","fact_loyalty_redemption","fact_loyalty_award"]:
            pd_frame=pd.read_parquet(cfg.path("data","silver",name+".parquet"))
            pd_frame.to_parquet(cfg.path("data","bronze",name+".parquet"),index=False)
        experiment=analyze(cfg,trial)
        uplift,uplift_metrics=fit_uplift(cfg,trial,scored,tracking)
        print("6/8 Estimate elasticity and forecast transportation demand",flush=True)
        elasticity,scenarios=fit_elasticity(cfg,frames["fact_pricing_scenario"],tracking)
        capacity,demand_metrics=fit_demand(cfg,frames["fact_trip"],context,tracking)
        print("7/8 Allocate promotion and loyalty budget",flush=True)
        decisions,capacity,optimization=allocate(cfg,scored,uplift,frames["dim_offer"],capacity,solver)
        from .marts import build_marts
        from .pricing import build_pricing
        from .policy_trial import policy_trial
        from .quality import evaluate_quality
        scored=build_marts(cfg,frames,scored,uplift,trial,elasticity)
        build_pricing(cfg,scenarios,capacity,frames["fact_trip"],solver)
        policy_trial(cfg,scored,hidden,capacity,solver)
        monitoring=monitor(cfg,snapshots,scored,frames,trial)
        scored.to_parquet(cfg.path("data","gold","customer_360.parquet"),index=False)
        scored.to_csv(cfg.path("outputs","customer_360.csv"),index=False)
        for name,frame in {"customer_360":scored,"decision_table":decisions,"zone_capacity":capacity,"pricing_elasticity":elasticity,"campaign_performance":trial}.items():
            db.register("incoming",frame)
            db.execute(f"CREATE OR REPLACE TABLE gold.{name} AS SELECT * FROM incoming")
        metrics={"customer":customer_metrics,"uplift":uplift_metrics,"demand":demand_metrics}
        write_json(cfg.path("outputs","model_metrics.json"),metrics)
        write_json(cfg.path("outputs","quality_gate.json"),evaluate_quality(metrics))
        print("8/8 Export dashboard, BI tables and executive findings",flush=True)
        summary=report(cfg,frames,scored,decisions,capacity,scenarios,metrics,optimization,experiment,monitoring,db)
        summary["runtime_seconds"]=time.perf_counter()-started
        write_json(cfg.path("outputs","summary.json"),summary)
        print(json.dumps(summary,indent=2),flush=True)
    finally:
        db.close()

def run(cfg,solver="auto",tracking=True):
    # Fix floating-point reduction order for deterministic model and cluster metrics.
    from threadpoolctl import threadpool_limits
    from .runtime import pipeline_run
    with pipeline_run(cfg),threadpool_limits(limits=1):
        return _run(cfg,solver,tracking)

def main():
    parser=argparse.ArgumentParser(description="Synthetic customer and transportation decision platform")
    sub=parser.add_subparsers(dest="command",required=True)
    demo=sub.add_parser("demo",help="Run the local end-to-end pipeline")
    demo.add_argument("--customers",type=int,default=8000)
    demo.add_argument("--seed",type=int,default=407)
    demo.add_argument("--solver",choices=["auto","gurobi","highs"],default="auto")
    demo.add_argument("--no-tracking",action="store_true")
    demo.add_argument("--root",type=Path,default=Config().root)
    fetch=sub.add_parser("fetch",help="Cache public external datasets")
    fetch.add_argument("--refresh",action="store_true")
    args=parser.parse_args()
    if args.command=="fetch":
        from .external import fetch as get
        print(get(Config(),args.refresh).shape)
    else:
        if args.customers<300:parser.error("At least 300 customers required for meaningful training/trial folds")
        run(Config(seed=args.seed,customers=args.customers,root=args.root),args.solver,not args.no_tracking)

if __name__=="__main__":main()
