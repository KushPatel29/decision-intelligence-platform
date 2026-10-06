import json

import pandas as pd

from .config import write_json


def records(frame):
    return json.loads(frame.to_json(orient="records", date_format="iso"))


def report(
    cfg, frames, customers, decisions, capacity, scenarios, metrics, optimization, experiment, monitoring, db
):
    trips = frames["fact_trip"]
    history = trips[trips.timestamp < pd.Timestamp(cfg.decision_date)]
    monthly = (
        history.assign(month=history.timestamp.dt.strftime("%Y-%m"))
        .groupby("month")
        .agg(trips=("trip_id", "count"), revenue=("final_charge", "sum"), savings=("discount", "sum"))
        .reset_index()
    )
    segments = (
        customers.groupby("rfm_segment")
        .agg(
            customers=("customer_id", "count"),
            clv=("clv_12m", "mean"),
            propensity=("propensity_probability", "mean"),
            churn=("churn_probability", "mean"),
            digital=("digital_events_30d", "mean"),
        )
        .reset_index()
    )
    summary = {
        "status": "local simulation complete",
        "data_kind": "synthetic customers/trips plus three real public context datasets",
        "customers": len(customers),
        "trips": len(trips),
        "digital_events": len(frames["fact_digital_event"]),
        "simulated_revenue": float(trips.final_charge.sum()),
        "simulated_savings": float(trips.discount.sum()),
        "selected_contacts": len(decisions),
        "expected_incremental_trips": float(decisions.incremental_trips.sum()),
        "expected_net_contribution": float(decisions.net_contribution.sum()),
        "campaign_spend": float(decisions.cost.sum()),
        "solver": optimization["promotion"]["solver"],
        "constraints_passed": optimization["combined"]["all_constraints_passed"],
        "dashboard": str(cfg.path("outputs", "dashboard.html")),
        "decision_date": cfg.decision_date,
    }
    payload = {
        "summary": summary,
        "monthly": records(monthly),
        "segments": records(segments),
        "customers": records(customers),
        "decisions": records(decisions),
        "capacity": records(capacity),
        "scenarios": records(scenarios),
        "metrics": metrics,
        "optimization": optimization,
        "experiment": experiment,
        "monitoring": monitoring,
        "zones": records(frames["dim_zone"]),
    }
    write_json(cfg.path("outputs", "dashboard_data.json"), payload)
    template = cfg.path("web", "dashboard.html").read_text(encoding="utf-8")
    data = json.dumps(payload, allow_nan=False).replace("</", "<\\/")
    cfg.path("outputs", "dashboard.html").write_text(
        template.replace("__DASHBOARD_DATA__", data), encoding="utf-8"
    )
    # Power BI import tables have single, explicit grains and stable keys.
    bi = cfg.path("outputs", "powerbi")
    bi.mkdir(parents=True, exist_ok=True)
    for name, frame in {
        "customer_360": customers,
        "decision_table": decisions,
        "zone_capacity": capacity,
        "monthly_performance": monthly,
        "pricing_scenarios": scenarios,
        "dim_zone": frames["dim_zone"],
        "dim_offer": frames["dim_offer"],
        "campaign_result": pd.read_parquet(cfg.path("data", "silver", "fact_campaign_result.parquet")),
    }.items():
        frame.to_csv(bi / f"{name}.csv", index=False)
    rows = []
    for task in ("propensity", "churn", "attrition"):
        rows.append({"model": task, **metrics["customer"][task]["test_calibrated"]})
    pd.DataFrame(rows).to_csv(bi / "model_metrics.csv", index=False)
    pd.DataFrame(monitoring["features"]).to_csv(bi / "feature_drift.csv", index=False)
    pd.DataFrame(experiment["results"]).drop(
        columns=["incremental_trips_per_customer", "incremental_net_contribution_per_customer"]
    ).to_csv(bi / "experiment_results.csv", index=False)
    brief = f"""# Customer, pricing and transportation decision intelligence

Synthetic portfolio simulation. Decision date: {cfg.decision_date}. No affiliation with 407 ETR.

## Business problem
Discounting customers who would travel anyway spends money without creating additional value. The platform estimates which offers can change travel behaviour, then allocates a fixed budget while respecting customer eligibility, contact limits, offer availability and simulated roadway capacity.

## Working system
The build combines {len(customers):,} synthetic customers, {len(trips):,} trips and {len(frames["fact_digital_event"]):,} digital events with real public weather, holiday and exchange-rate data. Historical information predicts travel, inactivity, declining use and future customer contribution. A past randomized simulation estimates offer effects. The decision process uses those estimates rather than access to the simulator's hidden effects.

## Proposed simulated campaign
The {summary["solver"]} allocation selected {len(decisions):,} customer contacts, with ${summary["campaign_spend"]:,.2f} in expected incentive costs against a ${cfg.budget:,.2f} budget. It predicts {summary["expected_incremental_trips"]:,.1f} additional trips and ${summary["expected_net_contribution"]:,.2f} in net incremental contribution after incentive costs. These are planning estimates within a simulation, not observed business results. All implemented shared budget, customer-contact, eligibility, offer-inventory and capacity checks passed.

## Evidence and interpretation
The travel model's held-out accuracy score is {metrics["customer"]["propensity"]["test_calibrated"]["roc_auc"]:.3f}; inactivity is {metrics["customer"]["churn"]["test_calibrated"]["roc_auc"]:.3f} and declining use is {metrics["customer"]["attrition"]["test_calibrated"]["roc_auc"]:.3f}. These scores reflect a designed synthetic population. The experiment planned {experiment["required_per_arm"]:,} customers per group to detect a five-percentage-point change; it actually contains {min(experiment["actual_per_arm"].values()):,} per group. Its planned sample-size target {"was" if experiment["powered_for_planned_mde"] else "was not"} met. Treat segment findings as exploratory.

## Decision and next step
Review the recommendation table, feasible baselines and fresh constrained-policy experiment before operational adoption. Monthly fixed-origin demand backtests and interval coverage are exported. Signed later-margin effects and retention outcomes are separate from 30-day economics; incremental 12-month value remains unvalidated.

## Delivery boundary
Python, SQL, local model tracking, price/campaign optimization and twelve app workspaces run locally. Eight-page native BI source is structurally validated; the revised Desktop refresh is pending. Six SageMaker workflows and full Databricks marts are authored; hosted jobs, Docker/ECR, identity flow and staging acceptance require separate receipts. No actual toll rates, customer records or company campaign rules are used.
"""
    cfg.path("outputs", "executive_brief.md").write_text(brief, encoding="utf-8")
    from .adhoc import run_adhoc

    run_adhoc(cfg, db)
    return summary
