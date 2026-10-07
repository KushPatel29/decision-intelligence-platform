"""Transportation: demand forecasts with intervals, protected capacity and where the campaign lands."""

import plotly.graph_objects as go
import streamlit as st

from decision_platform.ui import SERIES, chart, page_header, pct, tiles
from decision_platform.webapp import doc, download, table, zone_names

page_header(
    "Transportation",
    "Thirty-day demand forecasts by zone and travel period, the capacity each cell has left after a safety "
    "reserve, and where the October campaign adds — or removes — trips.",
    eyebrow="Understand",
)
zones = zone_names()
capacity = table("capacity")
capacity["zone"] = capacity.zone_id.map(zones)
demand = doc("metrics")["demand"]
test = demand["test"]
tiles(
    [
        (
            "Forecast model",
            demand["champion"].replace("_", " ").capitalize(),
            demand["selection"].get("promotion_gate", ""),
            True,
        ),
        (
            "30-day MAE, trips per cell-day",
            f"{test['mae']:.1f}",
            f"Same-weekday baseline {test['same_weekday_mean_mae']:.1f}",
        ),
        (
            "90% interval coverage",
            pct(test["interval_coverage_90"]),
            f"{test['test_origins']} held-out forecast origins",
        ),
        (
            "Campaign peak trips",
            f"{capacity[capacity.period.eq('Peak')].allocated_trips.sum():+,.0f}",
            "Negative = commuters moved off the peak",
        ),
    ]
)

period = st.segmented_control("Travel period", ["All", "Peak", "Off-peak", "Weekend"], default="All")
view = capacity if period in (None, "All") else capacity[capacity.period.eq(period)]
tab_capacity, tab_forecast, tab_hourly = st.tabs(["Capacity", "Forecast accuracy", "Hourly profile"])
with tab_capacity:
    totals = (
        view.groupby("zone")[["baseline_forecast", "allocated_trips", "reserve_trips", "capacity_trips"]]
        .sum()
        .reindex(list(zones.values()))
        .reset_index()
    )
    fig = go.Figure()
    for label, key, color in [
        ("Baseline forecast", "baseline_forecast", SERIES[0]),
        ("Campaign trips", "allocated_trips", SERIES[1]),
        ("Safety reserve", "reserve_trips", SERIES[3]),
    ]:
        fig.add_trace(
            go.Bar(
                x=totals.zone,
                y=totals[key],
                name=label,
                marker=dict(color=color, line=dict(width=1, color="#081522")),
                hovertemplate="%{x}<br>%{y:,.0f} trips<extra>" + label + "</extra>",
            )
        )
    fig.add_trace(
        go.Scatter(
            x=totals.zone,
            y=totals.capacity_trips,
            name="Planning capacity",
            mode="markers",
            marker=dict(symbol="line-ew", size=30, line=dict(width=3, color="#eef8ff")),
            hovertemplate="%{x}<br>%{y:,.0f} trips capacity<extra></extra>",
        )
    )
    fig.update_layout(barmode="relative", hovermode="x unified")
    fig.update_yaxes(title="Trips over the 30-day window")
    chart(fig, 400)
    st.caption(
        "White ticks mark planning capacity. Campaign trips can be negative where off-peak offers move commuters out of the peak."
    )
    st.dataframe(
        view[
            [
                "zone",
                "period",
                "baseline_forecast",
                "forecast_high",
                "allocated_trips",
                "reserve_trips",
                "capacity_trips",
                "final_utilization",
                "remaining_with_reserve",
            ]
        ],
        hide_index=True,
        width="stretch",
        column_config={
            "baseline_forecast": st.column_config.NumberColumn("Forecast", format="%,.0f"),
            "forecast_high": st.column_config.NumberColumn("Forecast, 90% high", format="%,.0f"),
            "allocated_trips": st.column_config.NumberColumn("Campaign", format="%+.0f"),
            "reserve_trips": st.column_config.NumberColumn("Reserve", format="%,.0f"),
            "capacity_trips": st.column_config.NumberColumn("Capacity", format="%,.0f"),
            "final_utilization": st.column_config.ProgressColumn(
                "Load", min_value=0, max_value=1, format="percent"
            ),
            "remaining_with_reserve": st.column_config.NumberColumn("Free after reserve", format="%,.0f"),
        },
    )
    download(view, "capacity.csv")

with tab_forecast:
    backtest = table("demand_backtest")
    cells = backtest[["zone_id", "period"]].drop_duplicates().sort_values(["zone_id", "period"])
    labels = {f"{zones[z]} · {p}": (z, p) for z, p in cells.itertuples(index=False)}
    choice = st.selectbox(
        "Zone and period",
        list(labels),
        index=list(labels).index(f"{zones[2]} · Peak") if f"{zones[2]} · Peak" in labels else 0,
    )
    zone_id, cell_period = labels[choice]
    series = backtest[(backtest.zone_id == zone_id) & (backtest.period == cell_period)].sort_values("date")
    origin = series.origin.max()
    series = series[series.origin.eq(origin)]
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=series.date,
            y=series.upper_90,
            mode="lines",
            line=dict(width=0),
            showlegend=False,
            hoverinfo="skip",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=series.date,
            y=series.lower_90,
            mode="lines",
            fill="tonexty",
            fillcolor="rgba(57,135,229,.18)",
            line=dict(width=0),
            name="90% interval",
            hoverinfo="skip",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=series.date,
            y=series.prediction,
            mode="lines",
            name="Forecast",
            line=dict(color=SERIES[0], width=2),
        )
    )
    fig.add_trace(
        go.Scatter(
            x=series.date, y=series.trips, mode="markers", name="Actual", marker=dict(color="#eef8ff", size=6)
        )
    )
    fig.update_layout(hovermode="x unified")
    fig.update_yaxes(title="Trips per day")
    chart(fig, 380)
    st.caption(
        f"Latest held-out origin ({str(origin)[:10]}); the forecast is frozen at the origin for 30 days. {demand['decision_forecast']}"
    )
    errors = (
        backtest.assign(abs_error=(backtest.trips - backtest.prediction).abs())
        .groupby("period")
        .abs_error.mean()
    )
    st.dataframe(errors.rename("MAE").reset_index(), hide_index=True)

with tab_hourly:
    hourly = table("zone_hour_forecast")
    profile = hourly if period in (None, "All") else hourly[hourly.period.eq(period)]
    grouped = profile.groupby(["hour", "direction"]).forecast_trips.sum().unstack(fill_value=0)
    fig = go.Figure()
    for i, direction in enumerate(grouped.columns):
        fig.add_trace(
            go.Scatter(
                x=grouped.index,
                y=grouped[direction],
                name=direction,
                mode="lines",
                line=dict(width=2, color=SERIES[i]),
            )
        )
    fig.update_layout(hovermode="x unified")
    fig.update_xaxes(title="Hour of day", dtick=2)
    fig.update_yaxes(title="Forecast trips, October")
    chart(fig, 340)
    st.caption(
        "Daily forecasts disaggregated with pre-cutoff hour and direction shares; not separately validated hourly models."
    )
