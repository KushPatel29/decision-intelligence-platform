"""Publish the serving snapshot, Power BI tables, executive brief and analyst cases.

The app reads only `outputs/serving/`: compact Parquet tables plus JSON
documents, all covered by the release manifest's hashes. Nothing in the
snapshot is simulator truth except the clearly labelled policy evaluation.
"""

from __future__ import annotations

import hashlib
import json

import pandas as pd

from .config import write_json
from .palette import OFFER_COLORS, offer_fill
from .simulation import OFFER_CATALOG

CUSTOMER_COLUMNS = [
    "customer_id",
    "customer_type",
    "home_zone",
    "tier",
    "eligible",
    "marketing_consent",
    "account_status",
    "rfm_segment",
    "cluster",
    "gmm_cluster",
    "tenure_days",
    "trips_30d",
    "trips_90d",
    "trips_previous90d",
    "spend_90d",
    "avg_toll",
    "peak_share",
    "weekend_share",
    "recency_days",
    "frequency_trend",
    "digital_events_30d",
    "sessions_30d",
    "offer_click_rate_90d",
    "days_since_last_login",
    "app_share_90d",
    "propensity_probability",
    "churn_probability",
    "attrition_probability",
    "expected_margin_90d",
    "clv_12m",
    "probabilistic_clv_12m",
    "probability_alive",
    "anomaly_score",
    "anomaly_flag",
    "points_balance",
    "points_earned",
    "points_awarded",
    "points_redeemed",
    "campaign_exposures",
    "campaign_enrollments",
    "campaign_redemptions",
    "home_zone_elasticity",
    "loyalty_500_redemption_probability",
    "best_offer_id",
    "best_offer_value",
    "best_offer_sd",
    "plan_offer_id",
    "plan_value",
    "plan_cost",
    "in_plan",
]

DECISION_COLUMNS = [
    "candidate_id",
    "customer_id",
    "offer_id",
    "offer_name",
    "offer_type",
    "zone_id",
    "rfm_segment",
    "eligible",
    "propensity_probability",
    "churn_probability",
    "clv_12m",
    "cost",
    "value_uplift",
    "value_uplift_sd",
    "value_lcb",
    "later_value_uplift",
    "net_contribution",
    "relief_value",
    "objective_value",
    "incremental_gross_contribution",
    "trips_peak",
    "trips_offpeak",
    "trips_weekend",
    "incremental_trips",
    "incremental_response",
    "enrollment_probability",
    "points",
    "inventory",
    "period",
]


def records(frame):
    return json.loads(frame.to_json(orient="records", date_format="iso"))


def _parquet(frame, path):
    frame = frame.copy()
    for column in frame.columns:
        if frame[column].dtype == object:
            frame[column] = frame[column].astype("string")
    frame.to_parquet(path, index=False)


def report(
    cfg,
    frames,
    customers,
    decisions,
    capacity,
    scenarios,
    metrics,
    optimization,
    experiment,
    monitoring,
    policy,
    db,
):
    out = cfg.path("outputs")
    serving = out / "serving"
    serving.mkdir(parents=True, exist_ok=True)
    trips = frames["fact_trip"]
    history = trips[trips.timestamp < pd.Timestamp(cfg.decision_date)]
    monthly = (
        history.assign(month=history.timestamp.dt.strftime("%Y-%m"))
        .groupby("month")
        .agg(
            trips=("trip_id", "count"),
            revenue=("final_charge", "sum"),
            savings=("discount", "sum"),
            customers=("customer_id", "nunique"),
            peak_trips=("period", lambda p: int((p == "Peak").sum())),
        )
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
            in_plan=("in_plan", "mean"),
            best_offer_value=("best_offer_value", "mean"),
        )
        .reset_index()
    )
    combined = optimization["combined"]
    production = next(p for p in policy["policies"] if p["policy"] == "Optimized (MIP)")
    propensity = next(p for p in policy["policies"] if p["policy"].startswith("Propensity"))
    summary = {
        "status": "local simulation complete",
        "data_kind": "synthetic customers/trips plus three real public context datasets",
        "decision_date": cfg.decision_date,
        "customers": len(customers),
        "eligible_customers": int(customers.eligible.sum()),
        "trips": len(trips),
        "digital_events": len(frames["fact_digital_event"]),
        "quarantined_trips": len(frames["quarantine_trip"]),
        "simulated_revenue": float(trips.final_charge.sum()),
        "selected_contacts": len(decisions),
        "campaign_spend": combined["spend"],
        "budget": cfg.budget,
        "expected_net_contribution": combined["net_contribution"],
        "expected_total_value": combined["objective_value"],
        "expected_incremental_trips": combined["incremental_trips"],
        "solver": optimization["joint"]["solver"],
        "optimality_certified": bool(optimization["certification"].get("proven_optimal", False)),
        "constraints_passed": combined["all_constraints_passed"],
        "true_value_optimized": production["true_value"],
        "share_of_oracle_optimized": production["share_of_oracle"],
        "true_value_propensity": propensity["true_value"],
        "share_of_oracle_propensity": propensity["share_of_oracle"],
        "oracle_ceiling": policy["oracle_ceiling"],
    }
    customer_view = customers[[c for c in CUSTOMER_COLUMNS if c in customers]]
    tables = {
        "customers": customer_view,
        "decisions": decisions[[c for c in DECISION_COLUMNS if c in decisions]],
        "candidates": pd.read_csv(out / "joint_candidates.csv")[DECISION_COLUMNS],
        "robust_decisions": pd.read_csv(out / "robust_decision_table.csv")[DECISION_COLUMNS],
        "capacity": capacity,
        "monthly": monthly,
        "segments": segments,
        "scenarios": scenarios,
        "elasticity": pd.read_csv(out / "elasticity.csv"),
        "price_options": pd.read_csv(out / "price_options.csv"),
        "price_allocation": pd.read_csv(out / "price_allocation.csv"),
        "policy_comparison": pd.read_csv(out / "policy_comparison.csv"),
        "policy_offer_mix": pd.read_csv(out / "policy_offer_mix.csv"),
        "value_calibration": pd.read_csv(out / "value_calibration.csv"),
        "budget_frontier": pd.read_csv(out / "budget_frontier.csv"),
        "shadow_prices": pd.read_csv(out / "shadow_prices.csv"),
        "uplift_learners": pd.read_csv(out / "uplift_learner_comparison.csv"),
        "experiment_subgroups": pd.read_csv(out / "experiment_subgroups.csv"),
        "demand_backtest": pd.read_csv(out / "demand_horizon_backtest.csv"),
        "decision_forecast": pd.read_csv(out / "decision_forecast.csv")[
            ["date", "zone_id", "period", "baseline_forecast", "forecast_low", "forecast_high"]
        ],
        "zone_hour_forecast": pd.read_csv(out / "zone_hour_forecast.csv")
        .groupby(["zone_id", "period", "direction", "hour"], as_index=False)
        .forecast_trips.sum(),
        "data_quality_daily": pd.read_csv(out / "data_quality_daily.csv"),
        "loyalty_ledger": pd.read_csv(out / "loyalty_ledger.csv"),
        "shap_global": pd.read_csv(out / "shap_global.csv"),
        "feature_drift": pd.DataFrame(monitoring["features"]),
        "offers": OFFER_CATALOG,
        "zones": frames["dim_zone"],
    }
    for name in ["propensity", "churn", "attrition"]:
        tables[f"performance_{name}"] = pd.read_csv(out / "performance" / f"{name}_predictions.csv")
    for name, frame in tables.items():
        _parquet(frame, serving / f"{name}.parquet")
    documents = {
        "summary": summary,
        "metrics": metrics,
        "optimization": optimization,
        "experiment": experiment,
        "monitoring": monitoring,
        "policy_value": policy,
        "policy_evaluation": json.loads((out / "policy_evaluation.json").read_text()),
        "policy_trial": json.loads((out / "policy_trial_results.json").read_text()),
        "price_optimization": json.loads((out / "price_optimization.json").read_text()),
        "loyalty_accounting": json.loads((out / "loyalty_accounting.json").read_text()),
        "data_quality": json.loads((out / "data_quality.json").read_text()),
        "probabilistic_clv": json.loads((out / "probabilistic_clv_metrics.json").read_text()),
        "quality_gate": json.loads((out / "quality_gate.json").read_text()),
        "uplift_metrics": json.loads((out / "uplift_metrics.json").read_text()),
        "elasticity_metrics": json.loads((out / "elasticity_metrics.json").read_text()),
        "data_quality_monitor": json.loads((out / "data_quality_monitor.json").read_text()),
    }
    for name, value in documents.items():
        write_json(serving / f"{name}.json", value)
    from .adhoc import run_adhoc

    cases = run_adhoc(cfg, db)
    for name in cases:
        _parquet(pd.read_csv(out / "adhoc" / f"{name}.csv"), serving / f"adhoc_{name}.parquet")
    write_json(serving / "adhoc.json", cases)
    write_serving_manifest(serving, cfg)
    write_json(
        out / "dashboard_data.json",
        {"summary": summary, "zones": records(frames["dim_zone"]), "serving": "outputs/serving"},
    )
    _powerbi(cfg, tables, metrics, experiment, monitoring, policy, optimization)
    _brief(cfg, summary, metrics, experiment, optimization, policy)
    return summary


def write_serving_manifest(serving, cfg):
    """Hash every serving file so the app can refuse a partial or edited snapshot."""
    files = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(serving.iterdir())
        if path.is_file() and path.name != "manifest.json"
    }
    release = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
    write_json(
        serving / "manifest.json",
        {"schema_version": 2, "decision_date": cfg.decision_date, "release_id": release, "files": files},
    )


def _round(frame, digits=4):
    out = frame.copy()
    for column in out.columns:
        if pd.api.types.is_float_dtype(out[column]):
            out[column] = out[column].round(digits)
    return out


def _powerbi(cfg, tables, metrics, experiment, monitoring, policy, optimization):
    """Compact single-grain import tables for the generated Power BI project (`powerbi/data/`)."""
    from .simulation import PERIODS

    folder = cfg.path("powerbi", "data")
    folder.mkdir(parents=True, exist_ok=True)
    offers = tables["offers"].reset_index(drop=True)
    zones = tables["zones"][["zone_id", "zone_name"]].assign(zone_order=lambda f: f.zone_id)
    customers = tables["customers"].copy()
    decisions = tables["decisions"]
    combined = optimization["combined"]
    segment_order = {"Champions": 1, "Loyal": 2, "Occasional": 3, "New": 4, "At risk": 5, "Dormant": 6}
    active = customers.churn_probability.notna()
    customers["active"] = active.astype(int)
    customers["high_risk"] = (customers.churn_probability > 0.5).astype(int)
    segments = (
        customers.assign(churn=customers.churn_probability.fillna(0))
        .groupby(["rfm_segment", "home_zone", "tier"])
        .agg(
            customers=("customer_id", "size"),
            eligible_customers=("eligible", "sum"),
            planned_customers=("in_plan", "sum"),
            sum_propensity=("propensity_probability", "sum"),
            sum_churn=("churn", "sum"),
            active_customers=("active", "sum"),
            high_risk_customers=("high_risk", "sum"),
            sum_clv=("clv_12m", "sum"),
            sum_best_value=("best_offer_value", "sum"),
        )
        .reset_index()
        .rename(columns={"home_zone": "zone_id"})
    )
    segments["segment_order"] = segments.rfm_segment.map(segment_order).fillna(9).astype(int)
    capacity = tables["capacity"]
    policy_rows = pd.DataFrame(policy["policies"])
    policy_rows["policy_order"] = range(1, len(policy_rows) + 1)
    names = {
        "budget": "Incentive budget ($)",
        "campaign_size": "Contact limit",
        "minimum_net_roi": "Net ROI floor",
        "loyalty_points": "Points cap",
    }
    guardrails = pd.DataFrame(optimization["lp_relaxation"]["shadow_prices"])
    if guardrails.empty:
        guardrails = pd.DataFrame(columns=["constraint", "shadow_price", "limit", "binding"])
    guardrails["constraint_label"] = [
        names.get(
            c, c.replace("capacity:", "Capacity ").replace("inventory:", "Inventory ").replace(":", " ")
        )
        for c in guardrails.constraint
    ]
    for zone_id, zone_name in zip(zones.zone_id, zones.zone_name, strict=True):
        guardrails["constraint_label"] = guardrails.constraint_label.str.replace(
            f"Capacity {zone_id} ", f"Capacity {zone_name} "
        )
    inventory = {
        f"Inventory {o}": f"Inventory: {n}" for o, n in zip(offers.offer_id, offers.offer_name, strict=True)
    }
    guardrails["constraint_label"] = guardrails.constraint_label.replace(inventory)
    effects, looks = [], []
    for row in experiment["results"]:
        cuped_value, cuped_trips = row["incremental_net_contribution_cuped"], row["incremental_trips_cuped"]
        effects.append(
            {
                "offer_id": row["offer_id"],
                "n": row["n"],
                "trips_effect": cuped_trips["difference"],
                "value_effect": cuped_value["difference"],
                "value_low": cuped_value["ci_low"],
                "value_high": cuped_value["ci_high"],
                "p_adjusted": cuped_value["p_adjusted"],
                "variance_reduction": cuped_trips["variance_reduction"],
                "enrollment_rate": row["enrollment_rate"],
            }
        )
        for look in row["sequential"]["looks"]:
            looks.append(
                {"arm": row["arm"], "day": look["day"], "z": look["z"], "boundary": look["boundary"]}
            )
    learners = tables["uplift_learners"]
    learner_rows = []
    for row in learners.itertuples():
        for learner in ["s_learner", "t_learner", "x_learner", "dr_learner"]:
            learner_rows.append(
                {
                    "offer_id": row.offer_id,
                    "learner": learner.replace("_learner", "").upper() + "-learner",
                    "value_spearman": getattr(row, f"{learner}_value_spearman", float("nan")),
                    "qini": getattr(row, f"{learner}_qini"),
                    "selected": row.selected == learner,
                }
            )
    backtest = tables["demand_backtest"]
    latest = backtest[backtest.origin.eq(backtest.origin.max())]
    backtest_rows = (
        latest.groupby(["date", "period"])
        .agg(actual=("trips", "sum"), forecast=("prediction", "sum"))
        .reset_index()
    )
    quality_gate = pd.DataFrame(
        [
            {"check_name": c["model"], "passed": c["passed"], "criteria": c["criteria"]}
            for c in monitoring_gate(cfg)
        ]
    )
    model_rows = pd.DataFrame(
        [
            {
                "model": task,
                "champion": metrics["customer"][task]["champion"].replace("_", " "),
                "auc": metrics["customer"][task]["test_calibrated"]["roc_auc"],
                "pr_auc": metrics["customer"][task]["test_calibrated"]["pr_auc"],
                "brier": metrics["customer"][task]["test_calibrated"]["brier"],
                "ece": metrics["customer"][task]["test_calibrated"]["ece_10bins"],
            }
            for task in ("propensity", "churn", "attrition")
        ]
    )
    feed = tables["data_quality_daily"]
    exports = {
        "dim_zone": zones,
        "dim_offer": offers[["offer_id", "offer_name", "offer_type", "period", "inventory"]].assign(
            offer_order=range(1, len(offers) + 1),
            offer_color=offers.offer_id.map(OFFER_COLORS),
            offer_fill=offers.offer_id.map(offer_fill),
        ),
        "dim_period": pd.DataFrame({"period": PERIODS, "period_order": [1, 2, 3]}),
        "plan_summary": pd.DataFrame(
            [
                {
                    "budget": combined["budget"],
                    "contact_limit": combined["contact_limit"],
                    "points_limit": combined["points_limit"],
                    "eligible_customers": int(customers.eligible.sum()),
                    "proven_optimal": bool(optimization["certification"].get("proven_optimal", False)),
                    "decision_variables": int(optimization["certification"].get("variables", 0)),
                    "free_variables": int(optimization["certification"].get("free_variables", 0)),
                    "relief_value_per_trip": cfg.relief_value,
                    "min_roi": cfg.min_roi,
                    "required_per_arm": int(experiment["required_per_arm"]),
                }
            ]
        ),
        "plan_contacts": decisions[
            [
                "customer_id",
                "offer_id",
                "zone_id",
                "rfm_segment",
                "cost",
                "objective_value",
                "value_uplift",
                "later_value_uplift",
                "value_uplift_sd",
                "incremental_trips",
                "trips_peak",
                "trips_offpeak",
                "trips_weekend",
                "points",
                "relief_value",
            ]
        ].rename(
            columns={
                "objective_value": "expected_value",
                "value_uplift": "value_30d",
                "later_value_uplift": "later_value",
                "value_uplift_sd": "value_sd",
            }
        ),
        "customer_segments": segments,
        "zone_capacity": capacity[
            [
                "zone_id",
                "period",
                "baseline_forecast",
                "allocated_trips",
                "reserve_trips",
                "capacity_trips",
                "remaining_with_reserve",
            ]
        ].rename(
            columns={"allocated_trips": "campaign_trips", "remaining_with_reserve": "free_after_campaign"}
        ),
        "monthly_trips": tables["monthly"].assign(
            month_label=lambda f: pd.to_datetime(f.month).dt.strftime("%b %Y"),
            month_index=lambda f: range(1, len(f) + 1),
        )[["month_label", "month_index", "trips", "revenue", "savings", "customers", "peak_trips"]],
        "policy_comparison": policy_rows[
            [
                "policy",
                "policy_order",
                "contacts",
                "predicted_value",
                "true_value",
                "true_spend",
                "share_of_oracle",
                "customers_losing_money",
            ]
        ],
        "budget_frontier": tables["budget_frontier"].rename(columns={"objective_value": "expected_value"})[
            [
                "budget",
                "spend",
                "contacts",
                "expected_value",
                "budget_shadow_price",
                "marginal_value_per_dollar",
            ]
        ],
        "guardrails": guardrails[["constraint_label", "shadow_price", "limit"]],
        "experiment_effects": pd.DataFrame(effects),
        "sequential_looks": pd.DataFrame(looks),
        "learner_comparison": pd.DataFrame(learner_rows),
        "elasticity": tables["elasticity"][
            ["zone_id", "period", "segment", "elasticity", "ci_low", "ci_high", "ols_elasticity"]
        ],
        "price_scenarios": tables["scenarios"][
            ["zone_id", "period", "price_change", "demand_index", "revenue_index"]
        ],
        "price_plan": tables["price_allocation"][
            ["zone_id", "period", "price_change", "forecast_trips", "campaign_trips"]
        ].assign(contribution_change=tables["price_allocation"].incremental_contribution),
        "hourly_forecast": tables["zone_hour_forecast"],
        "demand_backtest": backtest_rows,
        "feed_quality": feed[["day", "rows", "expected_rows", "volume_z", "flagged", "reason"]],
        "feature_drift": tables["feature_drift"][["feature", "psi", "status"]],
        "model_quality": model_rows,
        "quality_gate": quality_gate,
    }
    for name, frame in exports.items():
        _round(frame).to_csv(folder / f"{name}.csv", index=False, lineterminator="\n")


def monitoring_gate(cfg):
    return json.loads(cfg.path("outputs", "quality_gate.json").read_text())["checks"]


def _money(value):
    return f"${value:,.0f}"


def _brief(cfg, summary, metrics, experiment, optimization, policy):
    rows = {p["policy"]: p for p in policy["policies"]}
    optimized, robust = rows["Optimized (MIP)"], rows["Optimized, risk-averse (MIP on LCB)"]
    propensity = next(p for name, p in rows.items() if name.startswith("Propensity"))
    best = max(
        (r for r in experiment["results"]),
        key=lambda r: r["incremental_net_contribution_cuped"]["difference"],
    )
    insight = policy["propensity_insight"]
    certification = optimization["certification"]
    if certification.get("proven_optimal") and certification.get("core_solver") == "Gurobi":
        certified = (
            f"The plan is proven optimal for all {summary['eligible_customers']:,} eligible customers: reduced-cost "
            f"fixing settled {certification['variables'] - certification['free_variables']:,} of "
            f"{certification['variables']:,} decisions and Gurobi solved the remaining "
            f"{certification['free_variables']:,} exactly."
        )
    elif certification.get("proven_optimal"):
        certified = "The plan is proven optimal for the full population."
    else:
        certified = (
            f"The plan is within {certification.get('relative_gap_to_lp_bound', 0):.3%} of the LP bound."
        )
    brief = f"""# Customer, pricing and transportation decision intelligence

Synthetic portfolio simulation. Decision date {cfg.decision_date}. No affiliation with 407 ETR; customers, rates,
zones and offers are invented.

## The problem
A discount that goes to someone who would have driven anyway is a cost with no return. The question is not who
travels most, but whom an offer actually moves, and whether that movement lands where the road has room.

## What we found
- Travel propensity is the wrong targeting signal. Rank correlation between a customer's travel propensity and
  the value an offer really creates for them is {insight["spearman_propensity_vs_true_best_value"]:.2f}. Giving
  10% off to the most frequent travellers would create {_money(propensity["true_value"])} of value
  ({propensity["share_of_oracle"]:.0%} of what is achievable) with {propensity["customers_losing_money"]:,} contacts
  losing money.
- The optimized plan contacts {summary["selected_contacts"]:,} customers for {_money(summary["campaign_spend"])} of
  incentives and creates {_money(optimized["true_value"])} of true value, {optimized["share_of_oracle"]:.0%} of the
  ceiling a perfectly informed planner could reach. {certified}
- The models are optimistic about the customers they pick (the winner's curse): the plan predicted
  {_money(optimized["predicted_value"])}. A risk-averse variant that optimizes a one-standard-deviation lower bound
  predicted {_money(robust["predicted_value"])} and delivered {_money(robust["true_value"])}.
- In the July trial, {best["arm"]} produced the largest net contribution per customer
  ({best["incremental_net_contribution_cuped"]["difference"]:+.2f} CAD, CUPED). CUPED removed
  {experiment["cuped_mean_variance_reduction"]:.0%} of the variance in trips per customer on average.

## Decision
Allocate the October budget by expected incremental value under the shared guardrails, not by propensity or
segment rules. Run the plan against a randomised holdout and track realised spend weekly.

## Model evidence
Travel propensity AUC {metrics["customer"]["propensity"]["test_calibrated"]["roc_auc"]:.3f}; 90-day inactivity
{metrics["customer"]["churn"]["test_calibrated"]["roc_auc"]:.3f}; declining use
{metrics["customer"]["attrition"]["test_calibrated"]["roc_auc"]:.3f}. Demand forecast serving model:
{metrics["demand"]["champion"]} (30-day MAE {metrics["demand"]["test"]["mae"]:.1f} trips vs
{metrics["demand"]["test"]["same_weekday_mean_mae"]:.1f} for the same-weekday baseline).

All values are expected synthetic outcomes, not observed business results.
"""
    cfg.path("outputs", "executive_brief.md").write_text(brief, encoding="utf-8")


def export_bi(cfg):
    """Rebuild `powerbi/data/` from the verified serving snapshot, without rerunning any model."""
    serving = cfg.path("outputs", "serving")
    names = [
        "offers",
        "zones",
        "customers",
        "decisions",
        "capacity",
        "monthly",
        "scenarios",
        "elasticity",
        "price_allocation",
        "budget_frontier",
        "uplift_learners",
        "demand_backtest",
        "zone_hour_forecast",
        "data_quality_daily",
        "feature_drift",
    ]
    tables = {name: pd.read_parquet(serving / f"{name}.parquet") for name in names}
    docs = {
        name: json.loads((serving / f"{name}.json").read_text())
        for name in ["metrics", "experiment", "monitoring", "policy_value", "optimization"]
    }
    _powerbi(
        cfg,
        tables,
        docs["metrics"],
        docs["experiment"],
        docs["monitoring"],
        docs["policy_value"],
        docs["optimization"],
    )
    return sorted(path.name for path in cfg.path("powerbi", "data").glob("*.csv"))
