"""Policy value: every targeting approach scored against the simulator's true customer responses."""

import html

import plotly.graph_objects as go
import streamlit as st

from decision_platform.ui import NEUTRAL, SERIES, callout, chart, money, offer_marker, page_header, pct, tiles
from decision_platform.webapp import doc, download, offer_names, offer_order, table

page_header(
    "Policy value",
    "A real operator can only estimate what a campaign is worth. The simulation knows every customer's true "
    "response to every offer, so each targeting approach is scored here by the value it would actually create, "
    "under identical budget, contact, points, inventory and capacity guardrails.",
    eyebrow="Prove",
)
value = doc("policy_value")
comparison = table("policy_comparison")
rows = comparison.set_index("policy")
optimized = rows.loc["Optimized (MIP)"]
oracle = rows.loc["Oracle optimum (true effects)"]
propensity = rows.loc[[p for p in rows.index if p.startswith("Propensity")][0]]
insight = value["propensity_insight"]

tiles(
    [
        (
            "Optimized plan, true value",
            money(optimized.true_value),
            f"{pct(optimized.share_of_oracle)} of the ceiling",
            True,
        ),
        ("Ceiling (perfect knowledge)", money(oracle.true_value), "Same MIP on true effects"),
        (
            "Propensity targeting",
            money(propensity.true_value),
            f"{pct(propensity.share_of_oracle)} of the ceiling",
        ),
        (
            "Propensity vs true value",
            f"{insight['spearman_propensity_vs_true_best_value']:+.2f}",
            "Rank correlation across eligible customers",
        ),
    ]
)
callout(
    "<b>Finding.</b> The customers most likely to travel are not the customers an offer moves. Ranking by travel "
    f"propensity correlates {insight['spearman_propensity_vs_true_best_value']:+.2f} with the value an offer truly "
    f"creates, while the causal models correlate {insight['spearman_model_vs_true_best_value']:+.2f}. Under the same "
    f"guardrails, targeting by modelled incremental value creates {money(optimized.true_value - propensity.true_value)} "
    "more than giving 10% off to the most frequent travellers.",
    "good",
)

st.subheader("True value created, by targeting approach")
order = comparison.sort_values("true_value")
colors = [
    SERIES[0] if p == "Optimized (MIP)" else ("#86b6ef" if p.startswith("Oracle") else NEUTRAL)
    for p in order.policy
]
fig = go.Figure(
    go.Bar(
        y=order.policy,
        x=order.true_value,
        orientation="h",
        marker=dict(color=colors),
        text=[f"{money(v)} · {pct(s)}" for v, s in zip(order.true_value, order.share_of_oracle, strict=True)],
        textposition="outside",
        customdata=order[["contacts", "true_spend", "customers_losing_money"]].to_numpy(),
        hovertemplate="%{y}<br>True value %{x:$,.0f}<br>Contacts %{customdata[0]:,}<br>True spend %{customdata[1]:$,.0f}"
        "<br>Contacts losing money %{customdata[2]:,}<extra></extra>",
    )
)
fig.add_vline(x=0, line_color="#5b7486")
fig.update_xaxes(title="True expected value: 30-day net contribution + days 31-90 margin (CAD)")
fig.update_layout(margin=dict(r=120))
chart(fig, 360, legend=False)
st.caption(
    "Blue: the production plan. Light blue: the ceiling a perfectly informed planner could reach with the same "
    "guardrails. Grey: approaches that need no causal model, plus a greedy uplift heuristic."
)

left, right = st.columns(2)
with left:
    st.subheader("The winner's curse")
    st.caption(
        "Optimizers pick the customers whose value the model overestimates. The gap between predicted and true "
        "value is the price of estimation error; the risk-averse plan trades expected value for a smaller gap."
    )
    curse = comparison[
        comparison.policy.isin(
            ["Optimized (MIP)", "Optimized, risk-averse (MIP on LCB)", "Uplift ranking (greedy)"]
        )
    ]
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=curse.policy, y=curse.predicted_value, name="Predicted by the models", marker_color=SERIES[0]
        )
    )
    fig.add_trace(go.Bar(x=curse.policy, y=curse.true_value, name="True value", marker_color=SERIES[2]))
    fig.update_layout(barmode="group", hovermode="x unified")
    fig.update_yaxes(title="CAD")
    chart(fig, 330)
with right:
    st.subheader("Calibration of the plan's value estimates")
    calibration = table("value_calibration")
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=calibration.predicted,
            y=calibration.actual,
            mode="lines+markers",
            name="Plan deciles",
            marker=dict(size=9, color=SERIES[0]),
            line=dict(width=2, color=SERIES[0]),
            hovertemplate="Predicted %{x:$,.2f}<br>True %{y:$,.2f}<extra></extra>",
        )
    )
    low, high = (
        float(calibration[["predicted", "actual"]].min().min()),
        float(calibration[["predicted", "actual"]].max().max()),
    )
    fig.add_trace(
        go.Scatter(
            x=[low, high], y=[low, high], mode="lines", name="Perfect", line=dict(color=NEUTRAL, dash="dot")
        )
    )
    fig.update_xaxes(title="Predicted value per contact (CAD)")
    fig.update_yaxes(title="True value per contact (CAD)")
    chart(fig, 330)

st.subheader("Offer mix by approach")
mix = table("policy_offer_mix").set_index("offer_id").reindex(offer_order())
names = offer_names()
fig = go.Figure()
for offer in mix.index:
    fig.add_trace(
        go.Bar(
            x=mix.columns,
            y=mix.loc[offer],
            name=names[offer],
            marker=offer_marker([offer] * len(mix.columns), line=dict(width=1, color="#081522")),
            hovertemplate="%{x}<br>%{y:,} contacts<extra>" + html.escape(names[offer]) + "</extra>",
        )
    )
fig.update_layout(barmode="stack", hovermode="x unified")
fig.update_yaxes(title="Contacts")
chart(fig, 380)

st.subheader("Evidence a real team could compute")
evaluation, trial = doc("policy_evaluation"), doc("policy_trial")
effect = trial["incremental_net_contribution_per_customer"]
tiles(
    [
        (
            "Held-out offer rule (IPW)",
            money(evaluation["incremental_contribution_per_customer"], 2),
            f"per customer · 95% CI {evaluation['ci_low']:+.2f} to {evaluation['ci_high']:+.2f}",
        ),
        (
            "Fresh policy test, measured",
            money(effect["difference"], 2),
            f"per customer · 95% CI {effect['ci_low']:+.2f} to {effect['ci_high']:+.2f}",
        ),
        (
            "Fresh policy test, planned",
            money(trial["predicted_effect_per_customer"], 2),
            "per customer, from the models",
        ),
        (
            "Fresh policy test, truth",
            money(trial["true_effect_per_customer"], 2),
            "per customer, simulator truth",
        ),
    ]
)
st.caption(evaluation["interpretation"] + " " + trial["limitations"])
display = comparison.copy()
st.dataframe(
    display,
    hide_index=True,
    width="stretch",
    column_config={
        "predicted_value": st.column_config.NumberColumn("Predicted value", format="$%.0f"),
        "planned_spend": st.column_config.NumberColumn("Planned spend", format="$%.0f"),
        "true_value": st.column_config.NumberColumn("True value", format="$%.0f"),
        "true_net_contribution_30d": st.column_config.NumberColumn("True 30-day net", format="$%.0f"),
        "true_spend": st.column_config.NumberColumn("True spend", format="$%.0f"),
        "true_incremental_trips": st.column_config.NumberColumn("True extra trips", format="%.0f"),
        "true_peak_trips": st.column_config.NumberColumn("True peak trips", format="%+.0f"),
        "share_of_oracle": st.column_config.ProgressColumn(
            "Share of ceiling", min_value=0, max_value=1, format="percent"
        ),
        "winners_curse": st.column_config.NumberColumn("Predicted − true", format="$%.0f"),
    },
)
download(display, "policy_comparison.csv")
st.caption(value["scope"])
