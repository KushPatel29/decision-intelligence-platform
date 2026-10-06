"""Scenario starting points and capacity arithmetic shared by the app and tests."""

SCENARIO_TEMPLATES = {
    "October plan": dict(budget=10000.0, limit=5000, roi=0.15, points=2_500_000, reserve=0.20, risk=0.0),
    "Double the budget": dict(budget=20000.0, limit=5000, roi=0.15, points=2_500_000, reserve=0.20, risk=0.0),
    "Lean budget": dict(budget=6000.0, limit=3000, roi=0.25, points=1_000_000, reserve=0.20, risk=0.0),
    "Protect capacity": dict(budget=10000.0, limit=5000, roi=0.15, points=2_500_000, reserve=0.25, risk=0.0),
    "No loyalty points": dict(budget=10000.0, limit=5000, roi=0.15, points=0, reserve=0.20, risk=0.0),
    "Risk-averse": dict(budget=10000.0, limit=5000, roi=0.15, points=2_500_000, reserve=0.20, risk=1.0),
}


def zone_summary(capacity):
    """Capacity cells differ in size: aggregate amounts before computing load."""
    grouped = capacity.groupby("zone_id", sort=True)[
        ["baseline_forecast", "allocated_trips", "reserve_trips", "capacity_trips", "remaining_with_reserve"]
    ].sum()
    grouped["utilization"] = (grouped.baseline_forecast + grouped.allocated_trips) / grouped.capacity_trips
    return grouped


def with_reserve(capacity, reserve):
    """Recompute protected headroom for a different safety reserve, before any campaign trips."""
    view = capacity.drop(
        columns=["allocated_trips", "final_utilization", "remaining_with_reserve"], errors="ignore"
    )
    view = view.copy()
    view["reserve_trips"] = reserve * view.baseline_forecast
    view["available_trips"] = (view.capacity_trips - view.baseline_forecast - view.reserve_trips).clip(
        lower=0
    )
    view["baseline_over_capacity"] = view.baseline_forecast + view.reserve_trips > view.capacity_trips
    return view


def plan_capacity(capacity, selected, reserve):
    """Replace saved allocations with this plan's trips and its chosen baseline reserve.

    `selected` carries either signed per-period trip columns or (zone_id, period,
    incremental_trips) rows.
    """
    from .optimization import capacity_after

    view = with_reserve(capacity, reserve)
    if {"trips_peak", "trips_offpeak", "trips_weekend"}.issubset(selected.columns):
        return capacity_after(view, selected)
    additions = selected.groupby(["zone_id", "period"]).incremental_trips.sum().rename("allocated_trips")
    view = view.merge(additions.reset_index(), on=["zone_id", "period"], how="left", validate="one_to_one")
    view["allocated_trips"] = view.allocated_trips.fillna(0.0)
    view["final_utilization"] = (view.baseline_forecast + view.allocated_trips) / view.capacity_trips
    view["remaining_with_reserve"] = view.available_trips - view.allocated_trips
    return view
