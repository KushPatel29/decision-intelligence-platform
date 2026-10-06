"""Command line entry point: `decision-platform demo` runs the full local pipeline."""

import argparse
import json
import time
from pathlib import Path

from .config import Config, manifest, write_json

STEPS = 10


def _step(number, text):
    print(f"{number}/{STEPS} {text}", flush=True)


def _run(cfg, solver="auto", tracking=True):
    import pandas as pd

    from .advanced import explain, probabilistic_value, reward_ledger
    from .causal import fit_uplift
    from .data import generate
    from .evaluation import evaluate_policies
    from .experiments import analyze, simulate
    from .external import fetch
    from .features import build, connect, snapshot
    from .marts import build_marts
    from .models import fit_customer_models, fit_demand, fit_elasticity
    from .monitoring import data_quality_monitor, monitor
    from .optimization import allocate
    from .policy import heldout_offer_rule
    from .policy_trial import policy_trial
    from .pricing import build_pricing
    from .quality import evaluate_quality
    from .report import report

    started = time.perf_counter()
    timings = {}
    cfg.path("outputs").mkdir(parents=True, exist_ok=True)

    def mark(name):
        timings[name] = round(time.perf_counter() - started - sum(timings.values()), 2)

    _step(1, "Download or reuse cached public context (weather, holidays, CAD/USD)")
    context = fetch(cfg)
    _step(2, "Generate the synthetic ecosystem, conform bronze to silver, validate contracts")
    frames, hidden = generate(cfg, context)
    write_json(cfg.path("outputs", "manifest.json"), manifest(cfg, frames))
    print(
        f"  {len(frames['fact_trip']):,} trips, {len(frames['fact_digital_event']):,} digital events",
        flush=True,
    )
    mark("generate")
    db = connect(cfg, frames)
    try:
        _step(3, "Build point-in-time features and purged chronological folds")
        snapshots, current = build(db, cfg)
        mark("features")
        _step(4, "Train customer models, segments and anomaly review flags")
        scored, customer_metrics = fit_customer_models(cfg, snapshots, current, tracking)
        scored = probabilistic_value(cfg, frames["fact_trip"], scored)
        explain(cfg, scored)
        mark("customer_models")
        _step(5, "Simulate the July randomised trial and analyse it (CUPED, sequential, FDR)")
        trial_features = snapshot(db, cfg, "2025-07-01", labels=False)
        trial = simulate(cfg, trial_features, hidden, context, frames["dim_customer"])
        reward_ledger(cfg)
        for name in [
            "fact_campaign_result",
            "fact_offer_exposure",
            "fact_offer_enrollment",
            "fact_offer_redemption",
            "fact_loyalty_redemption",
            "fact_loyalty_award",
        ]:
            pd.read_parquet(cfg.path("data", "silver", name + ".parquet")).to_parquet(
                cfg.path("data", "bronze", name + ".parquet"), index=False
            )
        experiment = analyze(cfg, trial)
        mark("experiment")
        _step(6, "Estimate price elasticity and forecast 30-day demand by zone and period")
        elasticity, scenarios, elasticity_metrics = fit_elasticity(
            cfg, frames["fact_pricing_scenario"], tracking
        )
        capacity, demand_metrics = fit_demand(cfg, frames["fact_trip"], context, tracking)
        mark("pricing_demand")
        _step(7, "Learn incremental trips for all nine offers (S, T, X, DR learners) and cost them")
        totals = capacity.groupby("period").baseline_forecast.sum().to_dict()
        uplift, uplift_metrics = fit_uplift(cfg, trial, scored, totals, tracking)
        mark("causal")
        _step(8, "Optimize the October campaign over the full population; certify and stress-test it")
        decisions, capacity, optimization, frame, robust = allocate(
            cfg, scored, uplift, frames["dim_offer"], capacity, solver
        )
        policy_value, truth = evaluate_policies(
            cfg,
            scored,
            uplift,
            frames["dim_offer"],
            capacity,
            decisions,
            robust.selected,
            hidden,
            context,
            frames["dim_customer"],
        )
        heldout_offer_rule(cfg, pd.read_csv(cfg.path("outputs", "heldout_policy_scores.csv")))
        policy_trial(cfg, scored, truth, frame, capacity, solver)
        build_pricing(cfg, scenarios, capacity, frames["fact_trip"], solver)
        mark("decisions")
        _step(9, "Build marts and run monitoring (drift, matured performance, feed quality)")
        scored = build_marts(cfg, frames, scored, uplift, trial, elasticity, decisions)
        monitoring = monitor(cfg, snapshots, scored, frames, trial)
        monitoring["data_quality"] = data_quality_monitor(cfg, context)
        scored.to_parquet(cfg.path("data", "gold", "customer_360.parquet"), index=False)
        for name, table in {
            "customer_360": scored,
            "decision_table": decisions,
            "zone_capacity": capacity,
            "pricing_elasticity": elasticity,
            "campaign_performance": trial,
        }.items():
            db.register("incoming", table)
            db.execute(f"CREATE OR REPLACE TABLE gold.{name} AS SELECT * FROM incoming")
        metrics = {
            "customer": customer_metrics,
            "uplift": uplift_metrics,
            "demand": demand_metrics,
            "elasticity": elasticity_metrics,
            "policy": _policy_summary(policy_value),
        }
        write_json(cfg.path("outputs", "model_metrics.json"), metrics)
        write_json(cfg.path("outputs", "quality_gate.json"), evaluate_quality(metrics))
        mark("marts_monitoring")
        _step(10, "Export the serving snapshot, BI tables, executive findings and analyst cases")
        summary = report(
            cfg,
            frames,
            scored,
            decisions,
            capacity,
            scenarios,
            metrics,
            optimization,
            experiment,
            monitoring,
            policy_value,
            db,
        )
        mark("report")
        summary["runtime_seconds"] = round(time.perf_counter() - started, 1)
        summary["stage_seconds"] = timings
        write_json(cfg.path("outputs", "summary.json"), summary)
        print(json.dumps(summary, indent=2), flush=True)
    finally:
        db.close()


def _policy_summary(policy_value):
    rows = {p["policy"]: p for p in policy_value["policies"]}
    optimized = rows["Optimized (MIP)"]
    naive = [
        p
        for name, p in rows.items()
        if name in ("Random targeting", "RFM segment playbook") or name.startswith("Propensity")
    ]
    return {
        "share_of_oracle": optimized["share_of_oracle"],
        "beats_naive": all(optimized["true_value"] > p["true_value"] for p in naive),
        "true_value": optimized["true_value"],
    }


def run(cfg, solver="auto", tracking=True):
    # Single-threaded BLAS keeps floating-point reductions, and so every metric, reproducible.
    from threadpoolctl import threadpool_limits

    from .runtime import pipeline_run

    with pipeline_run(cfg), threadpool_limits(limits=1):
        return _run(cfg, solver, tracking)


def main():
    parser = argparse.ArgumentParser(
        description="Synthetic customer, pricing and transportation decision platform"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    demo = sub.add_parser("demo", help="Run the local end-to-end pipeline")
    demo.add_argument("--customers", type=int, default=Config().customers)
    demo.add_argument("--seed", type=int, default=407)
    demo.add_argument("--solver", choices=["auto", "gurobi", "highs"], default="auto")
    demo.add_argument("--no-tracking", action="store_true")
    demo.add_argument("--root", type=Path, default=Config().root)
    fetch = sub.add_parser("fetch", help="Cache public external datasets")
    fetch.add_argument("--refresh", action="store_true")
    sub.add_parser("export-bi", help="Rebuild powerbi/data from the serving snapshot")
    args = parser.parse_args()
    if args.command == "export-bi":
        from .report import export_bi

        for name in export_bi(Config()):
            print(name)
    elif args.command == "fetch":
        from .external import fetch as get

        print(get(Config(), args.refresh).shape)
    else:
        if args.customers < 3000:
            parser.error("At least 3,000 customers are needed for a ten-arm trial and stable folds")
        scale = args.customers / Config().customers
        cfg = Config(
            seed=args.seed,
            customers=args.customers,
            root=args.root,
            budget=Config().budget * scale,
            campaign_limit=int(Config().campaign_limit * scale),
            points_budget=int(Config().points_budget * scale),
        )
        run(cfg, args.solver, not args.no_tracking)


if __name__ == "__main__":
    main()
