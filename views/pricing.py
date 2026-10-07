"""Pricing studio: elasticity by zone, period and segment; price scenarios; joint price and campaign optimization."""

import plotly.graph_objects as go
import streamlit as st

from decision_platform.runtime import audit_event
from decision_platform.ui import NEUTRAL, SERIES, callout, chart, money, page_header, tiles
from decision_platform.webapp import (
    ROOT,
    SOLVE_SECONDS,
    context,
    doc,
    download,
    solver_slot,
    table,
    zone_names,
)

page_header(
    "Pricing studio",
    "How demand responds to the effective price in each zone, travel period and customer segment, what a price "
    "change would do to trips and revenue, and the best discrete price per cell when prices and the campaign "
    "share the same road capacity. Illustrative effective prices only: this does not model 407 ETR's tariff.",
    eyebrow="Decide",
)
ctx = context()
zones = zone_names()
elasticity = table("elasticity")
scenarios = table("scenarios")
metrics = doc("elasticity_metrics")
recovery = metrics["elasticity_rmse_vs_truth"]
tiles(
    [
        ("Method", "Empirical Bayes", "Cell OLS shrunk toward period x segment mean", True),
        (
            "Error vs true elasticity",
            f"{recovery.get('elasticity', float('nan')):.3f}",
            "RMSE across 36 cells (simulation check)",
        ),
        (
            "Pooled model error",
            f"{recovery.get('pooled_elasticity', float('nan')):.3f}",
            "Ignores zone differences",
        ),
        (
            "Boosting error",
            f"{recovery.get('boosting_elasticity', float('nan')):.3f}",
            "Monotone gradient boosting",
        ),
        (
            "95% interval coverage",
            f"{recovery.get('ci_coverage', float('nan')):.0%}",
            "Cells whose interval holds the truth",
        ),
    ]
)
callout(
    "Randomised daily price tests identify elasticity cleanly. Gradient boosting predicts demand about as well as "
    "the log-log model, yet recovers the price response far worse: a model can fit well and still answer the "
    "pricing question badly."
)

tab_elasticity, tab_scenarios, tab_optimize = st.tabs(
    ["Elasticity", "Price scenarios", "Optimize prices with the campaign"]
)
with tab_elasticity:
    segment = st.segmented_control("Segment", ["Personal", "Business"], default="Personal")
    view = elasticity[elasticity.segment.eq(segment or "Personal")].copy()
    view["cell"] = view.zone_id.map(zones) + " · " + view.period
    view = view.sort_values("elasticity")
    fig = go.Figure(
        go.Scatter(
            x=view.elasticity,
            y=view.cell,
            mode="markers",
            marker=dict(size=10, color=SERIES[0]),
            error_x=dict(
                type="data",
                symmetric=False,
                array=view.ci_high - view.elasticity,
                arrayminus=view.elasticity - view.ci_low,
                color="#8faebf",
                thickness=1.4,
            ),
            name="Empirical Bayes",
            hovertemplate="%{y}<br>Elasticity %{x:.2f}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=view.ols_elasticity,
            y=view.cell,
            mode="markers",
            marker=dict(size=7, color=NEUTRAL, symbol="diamond"),
            name="Cell OLS",
            hovertemplate="%{y}<br>OLS %{x:.2f}<extra></extra>",
        )
    )
    fig.add_vline(x=-1, line_dash="dot", line_color="#ec835a", annotation_text="Unit elastic")
    fig.update_xaxes(title="Price elasticity of demand (95% interval)")
    chart(fig, 560)
    st.caption(
        "Below −1, a price cut raises revenue; above −1 it lowers revenue. Business travel is less price sensitive."
    )
    download(elasticity, "elasticity.csv")

with tab_scenarios:
    c1, c2 = st.columns(2)
    zone = c1.selectbox("Zone", list(zones), format_func=lambda z: zones[z])
    period = c2.selectbox("Travel period", ["Off-peak", "Weekend", "Peak"])
    current = scenarios[(scenarios.zone_id == zone) & (scenarios.period == period)].sort_values(
        "price_change"
    )
    change = st.select_slider(
        "Effective price change",
        options=current.price_change.tolist(),
        value=0.0,
        format_func=lambda v: f"{v:+.0%}" if v else "Baseline",
    )
    row = current[current.price_change == change].iloc[0]
    st.columns(3)[0].metric(
        "Elasticity", f"{row.elasticity:.2f}", f"± {1.96 * row.elasticity_se:.2f}", delta_color="off"
    )
    fig = go.Figure()
    x = current.price_change * 100
    fig.add_trace(
        go.Scatter(
            x=x,
            y=current.demand_index_high,
            mode="lines",
            line=dict(width=0),
            showlegend=False,
            hoverinfo="skip",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=x,
            y=current.demand_index_low,
            mode="lines",
            fill="tonexty",
            fillcolor="rgba(57,135,229,.18)",
            line=dict(width=0),
            name="Demand, 95% band",
            hoverinfo="skip",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=x,
            y=current.demand_index,
            name="Demand index",
            mode="lines+markers",
            line=dict(color=SERIES[0], width=2),
        )
    )
    fig.add_trace(
        go.Scatter(
            x=x,
            y=current.revenue_index,
            name="Revenue index",
            mode="lines+markers",
            line=dict(color=SERIES[1], width=2),
        )
    )
    fig.add_hline(y=100, line_dash="dot", line_color=NEUTRAL)
    fig.add_vline(x=change * 100, line_dash="dot", line_color="#fab219")
    fig.update_layout(hovermode="x unified")
    fig.update_xaxes(title="Effective price change (%)")
    fig.update_yaxes(title="Index (baseline = 100)")
    chart(fig, 380)
    st.caption(
        f"At {change:+.0%}: demand {row.demand_index - 100:+.1f}% and revenue {row.revenue_index - 100:+.1f}% versus "
        "baseline, assuming constant elasticity within the tested −30% to +10% range."
    )

with tab_optimize:
    receipt = doc("price_optimization")
    st.caption(
        "One price option per zone and period plus every campaign contact, in a single MIP sharing budget, "
        "contacts, ROI, points, inventory and capacity. The surplus weight trades contribution against an "
        "illustrative consumer-surplus measure."
    )
    with st.form("joint_price_plan"):
        surplus = st.slider("Consumer surplus weight", 0.0, 1.0, 0.0, 0.1)
        run = st.form_submit_button("Optimize prices and campaign", type="primary")
    if run:
        try:
            from decision_platform.pricing import optimize_prices

            with solver_slot() as free:
                if not free:
                    st.warning("Other scenarios are solving right now. Try again in a few seconds.")
                    st.stop()
                with st.spinner("Solving the joint price and campaign problem…"):
                    chosen, contacts, result = optimize_prices(
                        table("price_options"),
                        table("candidates"),
                        budget=doc("optimization")["combined"]["budget"],
                        contacts=doc("optimization")["combined"]["contact_limit"],
                        roi=doc("optimization")["combined"]["min_roi"],
                        points=doc("optimization")["combined"]["points_limit"],
                        solver="auto",
                        surplus_weight=surplus,
                        time_limit=SOLVE_SECONDS,
                    )
            st.session_state["price_plan"] = (ctx["stamp"], chosen, contacts, result)
            audit_event(ROOT, ctx["owner"], "solve_prices", {"release_id": ctx["release_id"], **result})
        except Exception as exc:
            st.error(f"Price optimization did not finish: {exc}")
    saved = st.session_state.get("price_plan")
    if saved and saved[0] == ctx["stamp"]:
        _, chosen, contacts, receipt = saved
    else:
        chosen = table("price_allocation")
    tiles(
        [
            (
                "Price contribution change",
                money(receipt["price_contribution"]),
                f"{receipt['price_changes']} of 18 cells change price",
                True,
            ),
            (
                "Campaign value alongside",
                money(receipt.get("campaign_objective", receipt["campaign_net_contribution"])),
                f"{receipt['contacts']:,} contacts",
            ),
            (
                "Consumer surplus change",
                money(receipt["consumer_surplus_change"]),
                f"Weight {receipt['surplus_weight']:.1f}",
            ),
            (
                "Solver",
                receipt["solver"],
                "All shared constraints passed" if receipt["all_constraints_passed"] else "Review",
            ),
        ]
    )
    shown = chosen.assign(zone=chosen.zone_id.map(zones))
    st.dataframe(
        shown[
            [
                "zone",
                "period",
                "price_change",
                "elasticity",
                "forecast_trips",
                "campaign_trips",
                "remaining_with_reserve",
                "incremental_contribution",
                "consumer_surplus_change",
            ]
        ],
        hide_index=True,
        width="stretch",
        column_config={
            "price_change": st.column_config.NumberColumn("Price change", format="percent"),
            "elasticity": st.column_config.NumberColumn("Elasticity", format="%.2f"),
            "forecast_trips": st.column_config.NumberColumn("Trips at chosen price", format="%.0f"),
            "campaign_trips": st.column_config.NumberColumn("Campaign trips", format="%+.0f"),
            "remaining_with_reserve": st.column_config.NumberColumn("Free after reserve", format="%.0f"),
            "incremental_contribution": st.column_config.NumberColumn("Contribution change", format="$%.0f"),
            "consumer_surplus_change": st.column_config.NumberColumn("Surplus change", format="$%.0f"),
        },
    )
    st.caption(receipt["assumptions"])
    download(chosen, "optimized_prices.csv")
