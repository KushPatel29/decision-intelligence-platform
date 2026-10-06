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
    "heavy_vehicle": ("Heavy-vehicle account", "vehicle_class = Heavy", "dim_customer"),
    "night_share_30d": ("Share of recent trips before 06:00", "avg(hour < 6) over trailing 30d", "fact_trip"),
    "zones_visited_30d": (
        "Distinct zones travelled recently",
        "count distinct zone_id over trailing 30d",
        "fact_trip",
    ),
    "active_days_30d": (
        "Days with at least one trip",
        "count distinct trip dates over trailing 30d",
        "fact_trip",
    ),
    "max_daily_trips_30d": ("Busiest recent day", "max trips in one day over trailing 30d", "fact_trip"),
    "sessions_30d": (
        "Days with a digital session",
        "count distinct event dates over trailing 30d",
        "fact_digital_event",
    ),
    "offer_views_90d": ("Offer views", "count event_type=offer_view over trailing 90d", "fact_digital_event"),
    "offer_click_rate_90d": (
        "Smoothed offer click-through",
        "(offer clicks + 0.5) / (offer views + 3) over trailing 90d",
        "fact_digital_event",
    ),
    "enroll_rate_90d": (
        "Smoothed enrolment after a click",
        "(enrolments + 0.5) / (offer clicks + 2) over trailing 90d",
        "fact_digital_event",
    ),
    "email_click_rate_90d": (
        "Smoothed email click-through",
        "(email clicks + 0.5) / (email opens + 3) over trailing 90d",
        "fact_digital_event",
    ),
    "pricing_views_90d": (
        "Pricing page views",
        "count event_type=pricing_page_view over trailing 90d",
        "fact_digital_event",
    ),
    "loyalty_views_90d": (
        "Loyalty page views",
        "count event_type=loyalty_page_view over trailing 90d",
        "fact_digital_event",
    ),
    "app_share_90d": (
        "Share of logins in the app",
        "app logins / all logins over trailing 90d; 0 if none",
        "fact_digital_event",
    ),
    "days_since_last_login": (
        "Days since the last login",
        "date_diff(max(login), as_of), capped at 365",
        "fact_digital_event",
    ),
}


def main():
    docs = ROOT / "docs"
    docs.mkdir(exist_ok=True)
    snapshot = pd.read_parquet(ROOT / "data" / "gold" / "customer_360.parquet")
    lines = [
        "# Feature catalog",
        "Contract version 2.0. Refresh: monthly batch. Owner: project analytics. Privacy class: synthetic, non-PII. Model usage: customer prediction and causal outcome models unless a model card narrows it.",
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
            "quarantine_trip": "one bronze trip rejected by the silver contract, with its reason",
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
    # Model cards are written by scripts/build_model_cards.py from the same run.
    print("Generated data dictionary, schema registry and feature catalog")


if __name__ == "__main__":
    main()
