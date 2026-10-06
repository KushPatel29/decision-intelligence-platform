"""Explicit-grain reporting marts; outcome fields never join predictor allowlists."""

import pandas as pd

from .config import write_json


def build_marts(cfg, frames, customers, uplift, trial, elasticity, decisions):
    cutoff = pd.Timestamp(cfg.decision_date)
    ledger = pd.read_csv(cfg.path("outputs", "loyalty_ledger.csv"))
    result = customers.merge(ledger, on="customer_id", how="left", validate="one_to_one")
    for col in ["points_earned", "points_awarded", "points_redeemed", "points_balance"]:
        result[col] = result[col].fillna(0).astype(int)
    tiers = frames["fact_loyalty_tier"][["customer_id", "tier"]]
    result = result.merge(tiers, on="customer_id", how="left", validate="one_to_one")
    attributes = frames["dim_customer"][
        ["customer_id"]
        + [c for c in ["marketing_consent", "has_my_account", "past_due", "customer_type"] if c not in result]
    ]
    result = result.merge(attributes, on="customer_id", validate="one_to_one")
    campaign = trial.groupby("customer_id").agg(
        campaign_exposures=("treated", "sum"),
        campaign_enrollments=("enrolled", "sum"),
        campaign_redemptions=("redeemed", "sum"),
    )
    result = result.merge(campaign, on="customer_id", how="left", validate="one_to_one")
    campaign_cols = ["campaign_exposures", "campaign_enrollments", "campaign_redemptions"]
    result[campaign_cols] = result[campaign_cols].fillna(0).astype(int)
    events = frames["fact_digital_event"]
    recent = events[(events.timestamp < cutoff) & (events.timestamp >= cutoff - pd.Timedelta(days=30))].copy()
    recent["session_day"] = recent.timestamp.dt.normalize()
    channels = (
        recent.groupby(["customer_id", "channel"])
        .size()
        .unstack(fill_value=0)
        .add_prefix("channel_30d_")
        .reset_index()
    )
    sessions = recent.groupby("customer_id").session_day.nunique().rename("engaged_days_30d").reset_index()
    result = result.merge(channels, on="customer_id", how="left", validate="one_to_one").merge(
        sessions, on="customer_id", how="left", validate="one_to_one"
    )
    digital_cols = [c for c in result if c.startswith("channel_30d_")] + ["engaged_days_30d"]
    result[digital_cols] = result[digital_cols].fillna(0).astype(int)
    zone_elasticity = (
        elasticity.groupby("zone_id").elasticity.mean().rename("home_zone_elasticity").reset_index()
    )
    result = result.merge(
        zone_elasticity, left_on="home_zone", right_on="zone_id", how="left", validate="many_to_one"
    ).drop(columns="zone_id")
    loyalty = uplift[uplift.offer_id.eq("loyalty_500")][["customer_id", "redemption_probability"]].rename(
        columns={"redemption_probability": "loyalty_500_redemption_probability"}
    )
    result = result.merge(loyalty, on="customer_id", validate="one_to_one")
    # Next-best offer by model value, and the offer the optimized plan actually assigns.
    value = uplift.assign(total_value=uplift.value_uplift + uplift.later_value_uplift)
    best = value.loc[value.groupby("customer_id").total_value.idxmax()]
    best = best[["customer_id", "offer_id", "total_value", "value_uplift_sd"]].rename(
        columns={
            "offer_id": "best_offer_id",
            "total_value": "best_offer_value",
            "value_uplift_sd": "best_offer_sd",
        }
    )
    result = result.merge(best, on="customer_id", validate="one_to_one")
    plan = decisions[["customer_id", "offer_id", "objective_value", "cost"]].rename(
        columns={"offer_id": "plan_offer_id", "objective_value": "plan_value", "cost": "plan_cost"}
    )
    result = result.merge(plan, on="customer_id", how="left", validate="one_to_one")
    result["in_plan"] = result.plan_offer_id.notna()
    offer = uplift.merge(
        result[["customer_id", "rfm_segment", "home_zone", "eligible", "tier", "points_balance"]],
        on="customer_id",
        validate="many_to_one",
    )
    performance = (
        trial.groupby("arm")
        .agg(
            customers=("customer_id", "size"),
            responses=("response", "sum"),
            enrollments=("enrolled", "sum"),
            redemptions=("redeemed", "sum"),
            trips=("trip_count", "sum"),
            incentive_cost=("incentive_cost", "sum"),
            net_contribution=("net_contribution", "sum"),
        )
        .reset_index()
    )
    loyalty_perf = ledger.assign(point_liability=ledger.points_balance * 0.01)
    history = frames["fact_trip"]
    history = history[history.timestamp < cutoff].copy()
    history["month"] = history.timestamp.dt.strftime("%Y-%m")
    month = (
        history.groupby(["customer_id", "month"])
        .agg(trips=("trip_id", "size"), spend=("final_charge", "sum"), discount=("discount", "sum"))
        .reset_index()
    )
    marts = {
        "customer_360": result,
        "customer_offer": offer,
        "customer_activity_month": month,
        "campaign_performance": performance,
        "pricing_elasticity": elasticity,
        "loyalty_performance": loyalty_perf,
    }
    catalog = []
    grains = {
        "customer_360": ["customer_id"],
        "customer_offer": ["customer_id", "offer_id"],
        "customer_activity_month": ["customer_id", "month"],
        "campaign_performance": ["arm"],
        "pricing_elasticity": ["zone_id", "period", "segment"],
        "loyalty_performance": ["customer_id"],
    }
    for name, frame in marts.items():
        if frame.duplicated(grains[name]).any():
            raise ValueError(f"Duplicate mart grain: {name}")
        frame.to_parquet(cfg.path("data", "gold", name + ".parquet"), index=False)
        frame.to_csv(cfg.path("outputs", name + ".csv"), index=False)
        catalog.append({"table": name, "grain": grains[name], "rows": len(frame), "as_of": cfg.decision_date})
    write_json(cfg.path("outputs", "mart_catalog.json"), catalog)
    return result
