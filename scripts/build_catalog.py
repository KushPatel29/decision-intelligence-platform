"""Generate governance documentation from actual data and model outputs."""

import json

import pandas as pd

from decision_platform.config import ROOT
from decision_platform.features import FEATURES

DEFINITIONS = {
    "tenure_days": ("Days since synthetic account creation", "date_diff(created_at, as_of)", "dim_customer"),
    "business_flag": ("Business account indicator", "customer_type = Business", "dim_customer"),
    "autopay": ("Automatic-payment indicator", "cast(autopay as int)", "dim_customer"),
    "transponder_flag": ("Vehicle uses transponder", "cast(transponder_flag as int)", "dim_customer"),
    "home_zone": ("Synthetic preferred zone", "home_zone", "dim_customer"),
    "trips_7d": ("Recent 7-day trip frequency", "count trips in [as_of-7d, as_of)", "fact_trip"),
    "trips_30d": ("Recent 30-day trip frequency", "count trips in [as_of-30d, as_of)", "fact_trip"),
    "trips_90d": ("Recent 90-day trip frequency", "count trips in [as_of-90d, as_of)", "fact_trip"),
    "trips_previous90d": (
        "Prior comparison-window frequency",
        "count trips in [as_of-180d, as_of-90d)",
        "fact_trip",
    ),
    "spend_30d": ("30-day billed amount CAD", "sum(final_charge) over trailing 30d", "fact_trip"),
    "spend_90d": ("90-day billed amount CAD", "sum(final_charge) over trailing 90d", "fact_trip"),
    "spend_365d": ("Annual billed amount CAD", "sum(final_charge) over trailing 365d", "fact_trip"),
    "avg_toll": ("Mean pre-discount toll CAD", "avg(toll) over trailing 90d", "fact_trip"),
    "avg_distance_km": ("Mean trip distance", "avg(distance_km) over trailing 90d", "fact_trip"),
    "peak_share": ("Peak share of recent trips", "avg(period = Peak) over trailing 90d", "fact_trip"),
    "weekend_share": (
        "Weekend share of recent trips",
        "avg(period = Weekend) over trailing 90d",
        "fact_trip",
    ),
    "discount_90d": ("Recent applied discounts CAD", "sum(discount) over trailing 90d", "fact_trip"),
    "recency_days": (
        "Days since latest prior trip",
        "date_diff(max(timestamp), as_of); 730 if no history",
        "fact_trip",
    ),
    "digital_events_30d": (
        "Recent digital interaction count",
        "count digital events over trailing 30d",
        "fact_digital_event",
    ),
    "app_logins_30d": (
        "Recent app logins",
        "count event_type=app_login over trailing 30d",
        "fact_digital_event",
    ),
    "offer_views_30d": (
        "Recent offer views",
        "count event_type=offer_view over trailing 30d",
        "fact_digital_event",
    ),
    "email_opens_30d": (
        "Recent email opens",
        "count event_type=email_open over trailing 30d",
        "fact_digital_event",
    ),
    "points_earned_to_date": (
        "Historical points earnings, not available balance",
        "sum points_earned before as_of",
        "fact_loyalty_points",
    ),
    "frequency_trend": (
        "Smoothed relative usage change",
        "(trips_90d+1)/(trips_previous90d+1)",
        "customer_features",
    ),
    "digital_engagement_score": (
        "Log digital engagement proxy",
        "log1p(digital_events_30d)",
        "customer_features",
    ),
}


def main():
    docs = ROOT / "docs"
    docs.mkdir(exist_ok=True)
    snapshot = pd.read_parquet(ROOT / "data" / "gold" / "customer_360.parquet")
    lines = [
        "# Feature catalog",
        "Version 1.0. Refresh: monthly batch. Owner: project analytics. Privacy class: synthetic, non-PII. Model usage: customer prediction and causal outcome models unless a model card narrows it.",
        "All windows are end-exclusive at the snapshot date; timestamps are Toronto wall-clock. Status and marketing consent resolve their effective-dated history. Other account attributes remain static synthetic flags.",
        "| Feature | Business definition | Formula | Source | Nullable |",
        "|---|---|---|---|---|",
    ]
    assert set(FEATURES) == set(DEFINITIONS)
    for feature in FEATURES:
        definition, formula, source = DEFINITIONS[feature]
        lines.append(
            f"| {feature} | {definition} | {formula} | {source} | {snapshot[feature].isna().any()} |"
        )
    (docs / "feature_catalog.md").write_text(
        "\n\n".join(lines[:3]) + "\n\n" + "\n".join(lines[3:]), encoding="utf-8"
    )
    dictionary = [
        "# Data dictionary",
        "Actual generated silver schema. Types come from the current Parquet output. Every customer-level field is synthetic. Monetary fields use CAD.",
    ]
    grains = {
        "dim_customer": "one synthetic customer",
        "dim_account": "one account",
        "dim_vehicle": "one vehicle",
        "dim_zone": "one invented zone",
        "dim_offer": "one offer template",
        "fact_trip": "one generated trip",
        "fact_digital_event": "one interaction event",
        "fact_loyalty_points": "one trip earning entry",
        "fact_pricing_scenario": "zone × period × day randomized price assignment",
        "fact_campaign_result": "one randomized customer trial outcome",
        "external_context": "one Toronto/Ontario context day",
    }
    grains.update(
        {
            "dim_transponder": "one synthetic equipped account",
            "customer_preferences": "one static customer preference record",
            "customer_status_history": "customer × effective_from state/consent transition; intervals end at the next transition",
            "dim_entry_point": "one invented entry point per zone",
            "dim_exit_point": "one invented exit point per zone",
            "dim_time": "one calendar day",
            "dim_rate": "zone × period × vehicle class, illustrative 2025 tariff",
            "fact_effective_price": "one realized price per synthetic trip",
            "dim_reward": "one reward template",
            "fact_loyalty_tier": "one customer tier at the decision date",
            "fact_offer_exposure": "one assigned treated customer exposure",
            "fact_offer_enrollment": "one treated customer enrollment",
            "fact_offer_redemption": "one treated customer redemption",
            "fact_loyalty_award": "one randomized loyalty-group customer award",
            "fact_loyalty_redemption": "one loyalty redemption event",
        }
    )
    registry = []
    for path in sorted((ROOT / "data" / "silver").glob("*.parquet")):
        frame = pd.read_parquet(path)
        grain = grains.get(path.stem, "one customer campaign event")
        dictionary.extend(
            [
                f"\n## {path.stem}",
                f"Grain: {grain}. Rows: {len(frame):,}.",
                "| Field | Type | Nullable in run | Classification |",
                "|---|---|---|---|",
            ]
        )
        for field in frame:
            classification = "public context" if path.stem == "external_context" else "synthetic non-PII"
            dictionary.append(
                f"| {field} | {frame[field].dtype} | {frame[field].isna().any()} | {classification} |"
            )
        registry.append(
            {
                "table": path.stem,
                "version": "2.0",
                "grain": grain,
                "columns": {field: str(frame[field].dtype) for field in frame},
            }
        )
    (docs / "data_dictionary.md").write_text("\n".join(dictionary), encoding="utf-8")
    (docs / "schema_registry.json").write_text(json.dumps(registry, indent=2), encoding="utf-8")
    (docs / "schema_registry.md").write_text(
        "# Schema registry\n\nMachine-readable schema: `schema_registry.json`. Version 1.0. Table names and keys are recorded in the data dictionary. Breaking changes require a version increment and regeneration of features/models. Customer and event primary keys must be unique; trip/customer and trip/zone foreign keys must be valid. Date/event cutoffs must follow the feature contract.\n",
        encoding="utf-8",
    )
    metrics = json.loads((ROOT / "outputs" / "model_metrics.json").read_text())
    targets = {
        "propensity": "At least one trip in following 30 days",
        "churn": "No trips in following 90 days, among customers with >=3 trips in prior 90 days",
        "attrition": "Future 90-day trips <50% of prior 90-day trips, among historically active customers",
    }
    cards = docs / "model_cards"
    cards.mkdir(exist_ok=True)
    for name, target in targets.items():
        info = metrics["customer"][name]
        card = f"""# {name.title()} model card

Purpose: support travel/retention planning. Target: {target}.

Training population: synthetic customer-month snapshots July 2024–January 2025. Validation/calibration: April 2025. Held-out test: July 2025. Label overlap is purged. The same customer may recur across time.

Features: the version 1.0 allowlist in `feature_catalog.md`; no targets, future events or latent simulator parameters. Algorithm selected by validation Brier score: {info["champion"]}. Separate validation-fold logistic calibration is used before test/current scoring.

Measured synthetic held-out metrics:

```json
{json.dumps(info["test_calibrated"], indent=2)}
```

Deployment: local batch scoring and saved joblib artifacts with local MLflow run lineage. SageMaker execution is pending. Churn/attrition scores are blank outside their historically active population.

Limitations and bias: designed synthetic behaviour; no real-world performance or fairness validation. Static account flags and overlapping customer identities limit population generalization. No protected attributes are used, but geographic and behavioural proxies would require review in a real system.

Monitoring: feature PSI/KS review, delayed-label discrimination and calibration once labels mature. Retraining trigger: validated decline relative to the champion plus confirmed data quality; PSI alone does not automatically retrain or approve a model.
"""
        (cards / f"{name}.md").write_text(card, encoding="utf-8")
    others = {
        "clv": (
            "Future contribution and projected customer value",
            metrics["customer"]["clv"],
            "Historical-margin and learned forecasts compete only on validation. The retained baseline matches the held-out reference. Quarterly survival decay is heuristic. BG/NBD plus constrained Gamma-Gamma is evaluated on 90-day purchase-days, not 12-month value. Frequency/monetary correlation challenges its independence assumption.",
        ),
        "uplift": (
            "Incremental response, trips, 90-day retention and days31-90 margin",
            metrics["uplift"],
            "Four-arm July randomized simulation with held-out identities. T/S/X comparisons are exploratory; negative Qini is retained. Signed later margin uses 25% planning shrinkage, not an individual confidence bound. Retention is not monetized twice. A fresh October constrained-policy trial reports ITT uncertainty separately; its wide interval does not prove benefit.",
        ),
        "demand": (
            "Daily zone-period trip demand",
            metrics["demand"],
            "Validation-selected learned candidate failed the untouched promotion gate; the seasonal baseline remains the serving model. Six fixed-origin 30-day backtests report marginal interval coverage from validation residuals. Origins overlap and cells are dependent. Hour/direction values disaggregate daily forecasts and have no independent hourly validation.",
        ),
        "segmentation": (
            "Behavioural customer clustering",
            metrics["customer"]["segmentation"],
            "Fitted on the January 2025 training snapshot, with three bootstrap adjusted-Rand comparisons. Bootstrap stability does not establish temporal stability or business actionability.",
        ),
        "anomaly": (
            "Customer behavioural review",
            metrics["customer"]["anomaly"],
            "Unsupervised historical baseline. No labelled fraud evaluation; flags never automatically disqualify customers.",
        ),
        "elasticity": (
            "Demand response to price",
            pd.read_csv(ROOT / "outputs" / "elasticity.csv").to_dict(orient="records"),
            "Log-log OLS using independent randomized synthetic prices; coefficients are not observational estimates of actual company demand.",
        ),
    }
    for name, (purpose, evidence, limits) in others.items():
        card = f"# {name.title()} model card\n\nPurpose: {purpose}.\n\nEvidence from actual local run:\n\n```json\n{json.dumps(evidence, indent=2)}\n```\n\nLimitations: {limits}\n\nTraining/inference: local synthetic data, explicit feature cutoffs and model-specific folds. Artifacts are local; hosted deployment is pending. Monitor input distributions, realized outcomes when available, and business validity before promotion. Retrain only after data QA and a validated evaluation against the existing candidate. Synthetic data cannot establish real-world bias or fairness.\n"
        (cards / f"{name}.md").write_text(card, encoding="utf-8")
    print("Generated data dictionary, schema registry, feature catalog and nine model cards")


if __name__ == "__main__":
    main()
