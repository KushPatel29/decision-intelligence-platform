"""Next best offer: one customer's profile, every offer's expected value and the plan's choice."""

import html

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from decision_platform.ui import SERIES, callout, chart, money, page_header, pct, profile_card
from decision_platform.webapp import download, offer_names, offer_order, table, zone_names

page_header(
    "Next best offer",
    "Look up a customer to see how the models read them, what each offer is expected to earn after its cost, "
    "and which offer the optimized plan assigns.",
    eyebrow="Decide",
)
customers = table("customers")
candidates = table("candidates")
names, order, zones = offer_names(), offer_order(), zone_names()

left, right = st.columns([1.2, 1])
with left:
    mode = st.radio(
        "Find a customer",
        ["In the October plan", "Highest uncertainty", "Not contacted", "Search by ID"],
        horizontal=True,
    )
pool = customers
if mode == "In the October plan":
    pool = customers[customers.in_plan].sort_values("plan_value", ascending=False)
elif mode == "Highest uncertainty":
    pool = customers[customers.eligible].sort_values("best_offer_sd", ascending=False)
elif mode == "Not contacted":
    pool = customers[customers.eligible & ~customers.in_plan].sort_values("best_offer_value", ascending=False)
with right:
    if mode == "Search by ID":
        text = st.text_input("Customer ID contains", placeholder="e.g. 3f2a")
        pool = customers[customers.customer_id.str.contains(text, case=False, regex=False)] if text else customers
    customer_id = st.selectbox("Customer", pool.customer_id.head(300).tolist(), index=0 if len(pool) else None)

if not customer_id:
    st.info("No customer matches.")
    st.stop()
row = customers.set_index("customer_id").loc[customer_id]

profile_card(
    [
        ("Segment", row.rfm_segment),
        ("Type", row.customer_type),
        ("Home zone", zones.get(int(row.home_zone), row.home_zone)),
        ("Loyalty tier", row.tier),
        ("Trips, last 90 days", f"{int(row.trips_90d):,}"),
        ("Peak share", pct(row.peak_share)),
        ("Average toll", money(row.avg_toll, 2)),
        ("Days since last trip", f"{int(row.recency_days):,}"),
        ("Travel propensity, 30 days", pct(row.propensity_probability)),
        ("Inactivity risk, 90 days", "–" if pd.isna(row.churn_probability) else pct(row.churn_probability)),
        ("Projected 12-month value", money(row.clv_12m)),
        ("Points balance", f"{int(row.points_balance):,}"),
        ("Eligible for offers", "Yes" if row.eligible else "No"),
        ("Offer click rate, 90 days", pct(row.offer_click_rate_90d)),
    ]
)

if not row.eligible:
    callout(
        "This customer is <b>not eligible</b> for personalised offers (marketing consent, My Account, no past-due "
        "balance and an active account are all required), so the plan cannot contact them.",
        "warning",
    )

offers = candidates[candidates.customer_id.eq(customer_id)].copy()
if offers.empty:
    st.info(
        "No offer is expected to create value for this customer, so none is a candidate. Every offer's modelled "
        "value is at or below zero after incentive costs."
    )
else:
    offers["order"] = offers.offer_id.map({o: i for i, o in enumerate(order)})
    offers = offers.sort_values("objective_value", ascending=True)
    plan = row.plan_offer_id if isinstance(row.plan_offer_id, str) else None
    if plan:
        callout(
            f"The October plan assigns <b>{html.escape(names[plan])}</b>, expected to add "
            f"<b>{money(row.plan_value, 2)}</b> after an incentive cost of {money(row.plan_cost, 2)}.",
            "good",
        )
    else:
        best = offers.iloc[-1]
        callout(
            f"Not in the plan. The best candidate, <b>{html.escape(names[best.offer_id])}</b>, is worth "
            f"{money(best.objective_value, 2)}, but the budget, contact limit or capacity buys more value elsewhere.",
        )
    fig = go.Figure()
    colors = [SERIES[order.index(o) % len(SERIES)] for o in offers.offer_id]
    fig.add_trace(
        go.Bar(
            y=offers.offer_id.map(names),
            x=offers.objective_value,
            orientation="h",
            marker=dict(color=colors),
            error_x=dict(type="data", array=offers.value_uplift_sd, color="#8faebf", thickness=1.2),
            customdata=np.column_stack([offers.cost, offers.incremental_trips, offers.value_uplift_sd]),
            hovertemplate="%{y}<br>Expected value %{x:$,.2f}<br>Incentive cost %{customdata[0]:$,.2f}"
            "<br>Extra trips %{customdata[1]:.2f}<br>Uncertainty ±%{customdata[2]:$,.2f}<extra></extra>",
        )
    )
    fig.add_vline(x=0, line_color="#5b7486")
    fig.update_xaxes(title="Expected value: 30-day net contribution + days 31-90 margin (CAD)")
    chart(fig, 70 + 42 * len(offers), legend=False)
    st.caption("Bars show expected value; whiskers show one bootstrap standard deviation of the estimate.")
    table_view = offers.sort_values("objective_value", ascending=False)[
        [
            "offer_name",
            "objective_value",
            "value_uplift",
            "later_value_uplift",
            "cost",
            "trips_peak",
            "trips_offpeak",
            "trips_weekend",
            "value_uplift_sd",
        ]
    ]
    st.dataframe(
        table_view,
        hide_index=True,
        width="stretch",
        column_config={
            "offer_name": "Offer",
            "objective_value": st.column_config.NumberColumn("Expected value", format="$%.2f"),
            "value_uplift": st.column_config.NumberColumn("30-day net", format="$%.2f"),
            "later_value_uplift": st.column_config.NumberColumn("Days 31-90", format="$%.2f"),
            "cost": st.column_config.NumberColumn("Incentive cost", format="$%.2f"),
            "trips_peak": st.column_config.NumberColumn("Peak trips", format="%+.2f"),
            "trips_offpeak": st.column_config.NumberColumn("Off-peak trips", format="%+.2f"),
            "trips_weekend": st.column_config.NumberColumn("Weekend trips", format="%+.2f"),
            "value_uplift_sd": st.column_config.NumberColumn("± sd", format="$%.2f"),
        },
    )
    download(table_view, f"offers_{customer_id}.csv")

with st.expander("How these numbers are made"):
    st.markdown(
        "- **Extra trips** by period come from causal learners fitted on the July randomised trial; each offer uses "
        "the learner with the lowest doubly robust validation loss.\n"
        "- **Incentive cost** follows the offer's terms: discounts are paid on every eligible trip, including trips "
        "the customer would have taken anyway; threshold rewards are paid only if the threshold is reached.\n"
        "- **Days 31-90** applies the carry-over ratio measured in the trial.\n"
        "- Travel propensity and inactivity risk are separate calibrated classifiers and do not drive the plan."
    )
