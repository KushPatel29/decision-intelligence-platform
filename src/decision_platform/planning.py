"""Display calculations and editable scenario starting points."""

SCENARIO_TEMPLATES = {
    "Balanced": dict(budget=1600.0, limit=180, roi=0.15, points=35000, reserve=0.20),
    "Lean budget": dict(budget=800.0, limit=100, roi=0.25, points=15000, reserve=0.20),
    "More capacity reserve": dict(budget=1600.0, limit=180, roi=0.15, points=35000, reserve=0.35),
    "No reward points": dict(budget=1600.0, limit=180, roi=0.15, points=0, reserve=0.20),
}


def zone_summary(capacity):
    """Capacity cells differ in size: aggregate amounts before computing load."""
    grouped = capacity.groupby("zone_id", sort=True)[
        ["baseline_forecast", "allocated_trips", "reserve_trips", "capacity_trips", "remaining_with_reserve"]
    ].sum()
    grouped["utilization"] = (grouped.baseline_forecast + grouped.allocated_trips) / grouped.capacity_trips
    return grouped


def plan_capacity(capacity, selected, reserve):
    """Replace saved allocations with this plan and its chosen baseline reserve."""
    view = capacity.drop(columns=["allocated_trips"], errors="ignore").copy()
    additions = selected.groupby(["zone_id", "period"]).incremental_trips.sum().rename("allocated_trips")
    view = view.merge(additions.reset_index(), on=["zone_id", "period"], how="left", validate="one_to_one")
    view["allocated_trips"] = view.allocated_trips.fillna(0.0)
    view["reserve_trips"] = reserve * view.baseline_forecast
    view["available_trips"] = (view.capacity_trips - view.baseline_forecast - view.reserve_trips).clip(
        lower=0
    )
    view["baseline_over_capacity"] = view.baseline_forecast + view.reserve_trips > view.capacity_trips
    view["final_utilization"] = (view.baseline_forecast + view.allocated_trips) / view.capacity_trips
    view["remaining_with_reserve"] = view.available_trips - view.allocated_trips
    return view
