"""Offers & loyalty: the offer catalogue, what the plan buys with each offer and the points ledger."""

import plotly.graph_objects as go
import streamlit as st

from decision_platform.ui import callout, chart, money, offer_marker, page_header, pct, tiles
from decision_platform.webapp import doc, download, offer_names, offer_order, table, zone_names

page_header(
    "Offers & loyalty",
    "Nine offers with different mechanics: a rush-hour discount that moves commuters off congested roads, "
    "percentage discounts, a weekend incentive, a spend-threshold credit, a free trip, an off-peak driving pass "
    "and two loyalty-point rewards. What each costs, who it moves "
    "and what the plan buys with it.",
    eyebrow="Understand",
)
offers = table("offers")
decisions = table("decisions")
names, order, zones = offer_names(), offer_order(), zone_names()
optimization = doc("optimization")
experiment = {r["offer_id"]: r for r in doc("experiment")["results"]}

catalogue = offers.copy()
catalogue["trial_value_per_customer"] = catalogue.offer_id.map(
    lambda o: experiment[o]["incremental_net_contribution_cuped"]["difference"]
)
catalogue["trial_trips_per_customer"] = catalogue.offer_id.map(
    lambda o: experiment[o]["incremental_trips_cuped"]["difference"]
)
catalogue["plan_contacts"] = catalogue.offer_id.map(decisions.offer_id.value_counts()).fillna(0).astype(int)
plan = decisions.groupby("offer_id").agg(value=("objective_value", "sum"), spend=("cost", "sum"))
catalogue["plan_value"] = catalogue.offer_id.map(plan.value).fillna(0)
catalogue["plan_spend"] = catalogue.offer_id.map(plan.spend).fillna(0)
st.subheader("Offer catalogue")
st.dataframe(
    catalogue[
        [
            "offer_name",
            "offer_type",
            "period",
            "inventory",
            "trial_trips_per_customer",
            "trial_value_per_customer",
            "plan_contacts",
            "plan_spend",
            "plan_value",
        ]
    ],
    hide_index=True,
    width="stretch",
    column_config={
        "offer_name": "Offer",
        "offer_type": "Mechanic",
        "period": "Designed to fill",
        "inventory": st.column_config.NumberColumn("Monthly inventory", format="localized"),
        "trial_trips_per_customer": st.column_config.NumberColumn("Trial: trips / customer", format="%+.2f"),
        "trial_value_per_customer": st.column_config.NumberColumn(
            "Trial: net CAD / customer", format="$%+.2f"
        ),
        "plan_contacts": st.column_config.NumberColumn("Plan contacts", format="localized"),
        "plan_spend": st.column_config.NumberColumn("Plan spend", format="$%,.0f"),
        "plan_value": st.column_config.NumberColumn("Plan expected value", format="$%,.0f"),
    },
)
callout(
    "Average trial results and the plan disagree on purpose. An offer that loses money on the average customer "
    "can still create value for the customers the models select, and an offer that wins on average can be "
    "crowded out by better uses of the same budget and contacts."
)

left, right = st.columns(2)
with left:
    st.subheader("Where the plan's value comes from")
    fig = go.Figure()
    present = [o for o in order if o in plan.index]
    fig.add_trace(
        go.Bar(
            x=[names[o] for o in present],
            y=[plan.loc[o, "value"] for o in present],
            marker=offer_marker(present),
            hovertemplate="%{x}<br>%{y:$,.0f} expected value<extra></extra>",
        )
    )
    fig.update_yaxes(title="Expected value (CAD)")
    chart(fig, 330, legend=False)
with right:
    st.subheader("Value per incentive dollar")
    efficiency = (plan.value / plan.spend).reindex(present)
    fig = go.Figure(
        go.Bar(
            x=[names[o] for o in present],
            y=efficiency.values,
            marker=offer_marker(present),
            hovertemplate="%{x}<br>%{y:.2f} CAD per CAD<extra></extra>",
        )
    )
    fig.update_yaxes(title="Expected value per dollar of incentive")
    chart(fig, 330, legend=False)

st.subheader("Plan contacts by offer and zone")
mix = decisions.assign(zone=decisions.zone_id.map(zones)).pivot_table(
    index="zone", columns="offer_id", values="customer_id", aggfunc="count", fill_value=0
)
fig = go.Figure()
for offer in [o for o in order if o in mix.columns]:
    fig.add_trace(
        go.Bar(
            x=mix.index,
            y=mix[offer],
            name=names[offer],
            marker=offer_marker([offer] * len(mix), line=dict(width=1, color="#081522")),
        )
    )
fig.update_layout(barmode="stack", hovermode="x unified")
fig.update_yaxes(title="Contacts")
chart(fig, 340)

st.subheader("Loyalty points")
accounting = doc("loyalty_accounting")
combined = optimization["combined"]
tiles(
    [
        ("Points earned to date", f"{accounting['points_earned']:,}", "2 points per dollar of tolls", True),
        ("Trial points awarded", f"{accounting['points_awarded']:,}", "July bonus-points arms"),
        ("Points redeemed", f"{accounting['points_redeemed']:,}", "Reconciles to balances"),
        (
            "Outstanding liability",
            money(accounting["points_balance"] * accounting["point_value_cad"]),
            f"at {money(accounting['point_value_cad'], 2)} per point",
        ),
        (
            "October plan points",
            f"{combined['points_awarded']:,}",
            f"cap {combined['points_limit']:,} · {pct(combined['points_awarded'] / max(combined['points_limit'], 1))} used",
        ),
    ]
)
ledger = table("loyalty_ledger")
st.caption(accounting["note"])
download(ledger, "loyalty_ledger.csv", "Download the reconciled points ledger")
