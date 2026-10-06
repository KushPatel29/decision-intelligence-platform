"""Customer intelligence: segments, risk, value, anomalies and a filterable Customer 360."""

import plotly.graph_objects as go
import streamlit as st

from decision_platform.ui import SERIES, callout, chart, page_header, pct, tiles
from decision_platform.webapp import doc, download, table

page_header(
    "Customer intelligence",
    "Who the customers are, how likely they are to travel or lapse, what they are worth and which accounts "
    "look anomalous. Scores are calibrated on a separate fold and judged on an untouched later month.",
    eyebrow="Understand",
)
customers = table("customers")
metrics = doc("metrics")["customer"]
segments = table("segments")
active = customers[customers.churn_probability.notna()]
tiles(
    [
        ("Customers", f"{len(customers):,}", f"{customers.eligible.mean():.0%} eligible for offers", True),
        (
            "Travel propensity AUC",
            f"{metrics['propensity']['test_calibrated']['roc_auc']:.3f}",
            metrics["propensity"]["champion"].replace("_", " "),
        ),
        (
            "Inactivity risk AUC",
            f"{metrics['churn']['test_calibrated']['roc_auc']:.3f}",
            "Historically active customers",
        ),
        ("At high inactivity risk", f"{(active.churn_probability > 0.5).sum():,}", "Probability above 50%"),
        ("Anomaly review queue", f"{int(customers.anomaly_flag.sum()):,}", "Top 0.5% by isolation score"),
    ]
)

tab_segments, tab_risk, tab_anomaly, tab_360 = st.tabs(
    ["Segments", "Risk and value", "Anomaly review", "Customer 360"]
)
with tab_segments:
    left, right = st.columns([1, 1.15])
    with left:
        st.subheader("Business segments (RFM rules)")
        ranked = segments.sort_values("customers")
        fig = go.Figure(
            go.Bar(
                x=ranked.customers,
                y=ranked.rfm_segment,
                orientation="h",
                marker_color=SERIES[0],
                text=[f"{c:,}" for c in ranked.customers],
                textposition="outside",
                hovertemplate="%{y}<br>%{x:,} customers<extra></extra>",
            )
        )
        fig.update_xaxes(title="Customers", range=[0, ranked.customers.max() * 1.2])
        chart(fig, 320, legend=False)
    with right:
        st.subheader("What each segment is worth to the plan")
        st.dataframe(
            segments,
            hide_index=True,
            width="stretch",
            column_config={
                "rfm_segment": "Segment",
                "customers": st.column_config.NumberColumn("Customers", format="localized"),
                "clv": st.column_config.NumberColumn("Projected 12-month value", format="$%.0f"),
                "propensity": st.column_config.ProgressColumn(
                    "Travel propensity", min_value=0, max_value=1, format="percent"
                ),
                "churn": st.column_config.ProgressColumn(
                    "Inactivity risk", min_value=0, max_value=1, format="percent"
                ),
                "digital": st.column_config.NumberColumn("Digital events, 30 days", format="%.1f"),
                "in_plan": st.column_config.ProgressColumn(
                    "Share in October plan", min_value=0, max_value=1, format="percent"
                ),
                "best_offer_value": st.column_config.NumberColumn("Mean best-offer value", format="$%.2f"),
            },
        )
    seg = metrics["segmentation"]
    callout(
        f"Behavioural clustering: K-Means (5 clusters, silhouette {seg['kmeans']['silhouette']:.2f}) and a Gaussian "
        f"mixture whose size was chosen by BIC ({seg['gmm']['clusters']} components, silhouette "
        f"{seg['gmm']['silhouette']:.2f}). They agree with each other at ARI {seg['agreement']['kmeans_vs_gmm_ari']:.2f} "
        f"and with the RFM rules at ARI {seg['agreement']['kmeans_vs_rfm_ari']:.2f}: rules and clusters describe "
        "different things, so the plan uses neither to target."
    )
    cluster = (
        customers.groupby("cluster")
        .agg(
            customers=("customer_id", "size"),
            trips_90d=("trips_90d", "mean"),
            spend_90d=("spend_90d", "mean"),
            peak_share=("peak_share", "mean"),
            weekend_share=("weekend_share", "mean"),
            recency_days=("recency_days", "median"),
            in_plan=("in_plan", "mean"),
        )
        .reset_index()
    )
    st.dataframe(
        cluster,
        hide_index=True,
        width="stretch",
        column_config={
            "trips_90d": st.column_config.NumberColumn("Trips, 90 days", format="%.1f"),
            "spend_90d": st.column_config.NumberColumn("Spend, 90 days", format="$%.0f"),
            "peak_share": st.column_config.NumberColumn("Peak share", format="percent"),
            "weekend_share": st.column_config.NumberColumn("Weekend share", format="percent"),
            "in_plan": st.column_config.NumberColumn("In plan", format="percent"),
        },
    )

with tab_risk:
    st.subheader("Value and retention landscape")
    sample = active.sample(min(4000, len(active)), random_state=7)
    fig = go.Figure()
    for i, (name, group) in enumerate(sample.groupby("rfm_segment")):
        fig.add_trace(
            go.Scattergl(
                x=group.churn_probability * 100,
                y=group.clv_12m,
                mode="markers",
                name=name,
                marker=dict(size=5, opacity=0.55, color=SERIES[i % len(SERIES)]),
                text=group.customer_id,
                hovertemplate="%{text}<br>Inactivity risk %{x:.1f}%<br>Projected value %{y:$,.0f}<extra>"
                + name
                + "</extra>",
            )
        )
    fig.update_xaxes(title="90-day inactivity risk (%)")
    fig.update_yaxes(title="Projected 12-month contribution (CAD)")
    chart(fig, 430)
    st.caption(
        "A 4,000-customer sample of historically active customers. Hover for IDs; look them up in Next best offer."
    )
    left, right = st.columns(2)
    with left:
        st.subheader("Inactivity risk distribution")
        fig = go.Figure(go.Histogram(x=active.churn_probability * 100, nbinsx=40, marker_color=SERIES[0]))
        fig.update_xaxes(title="Inactivity risk (%)")
        fig.update_yaxes(title="Customers")
        chart(fig, 280, legend=False)
    with right:
        st.subheader("Declining use (attrition) by segment")
        attrition = active.groupby("rfm_segment").attrition_probability.mean().sort_values()
        fig = go.Figure(
            go.Bar(x=attrition.values * 100, y=attrition.index, orientation="h", marker_color=SERIES[1])
        )
        fig.update_xaxes(title="Mean probability of halving trips (%)")
        chart(fig, 280, legend=False)

with tab_anomaly:
    anomaly = metrics["anomaly"]
    evaluation = anomaly.get("evaluation_against_planted", {})
    forest, robust = evaluation.get("isolation_forest", {}), evaluation.get("robust_z_score", {})
    if forest:
        tiles(
            [
                (
                    "Planted anomalies caught",
                    f"{forest['caught']} of {forest['planted']}",
                    f"Isolation Forest recall {pct(forest['recall'])}",
                    True,
                ),
                ("Review queue precision", pct(forest["precision"]), f"{forest['flagged']} accounts flagged"),
                ("PR-AUC", f"{forest['pr_auc']:.3f}", "Ranking quality on planted cases"),
                (
                    "Robust z-score baseline",
                    f"{robust.get('caught', 0)} of {robust.get('planted', 0)}",
                    f"PR-AUC {robust.get('pr_auc', 0):.3f}",
                ),
            ]
        )
    st.caption(anomaly["method"])
    queue = customers[customers.anomaly_flag].sort_values("anomaly_score", ascending=False)
    st.dataframe(
        queue[
            [
                "customer_id",
                "rfm_segment",
                "trips_30d",
                "trips_90d",
                "recency_days",
                "anomaly_score",
                "eligible",
            ]
        ],
        hide_index=True,
        width="stretch",
        column_config={
            "anomaly_score": st.column_config.ProgressColumn(
                "Isolation score",
                min_value=float(queue.anomaly_score.min()) if len(queue) else 0,
                max_value=float(queue.anomaly_score.max()) if len(queue) else 1,
                format="%.3f",
            )
        },
    )
    download(queue, "anomaly_review_queue.csv")

with tab_360:
    st.subheader("Customer 360 workbench")
    c1, c2, c3 = st.columns([1, 1, 1.2])
    segment = c1.selectbox("Segment", ["All", *sorted(customers.rfm_segment.unique())])
    plan_filter = c2.selectbox(
        "Plan status", ["All", "In the October plan", "Eligible, not contacted", "Not eligible"]
    )
    text = c3.text_input("Customer ID contains")
    view = customers if segment == "All" else customers[customers.rfm_segment.eq(segment)]
    if plan_filter == "In the October plan":
        view = view[view.in_plan]
    elif plan_filter == "Eligible, not contacted":
        view = view[view.eligible & ~view.in_plan]
    elif plan_filter == "Not eligible":
        view = view[~view.eligible]
    if text:
        view = view[view.customer_id.str.contains(text, case=False, regex=False)]
    columns = [
        "customer_id",
        "rfm_segment",
        "tier",
        "trips_90d",
        "recency_days",
        "propensity_probability",
        "churn_probability",
        "clv_12m",
        "best_offer_id",
        "best_offer_value",
        "plan_offer_id",
        "eligible",
    ]
    st.dataframe(
        view[columns],
        hide_index=True,
        width="stretch",
        column_config={
            "propensity_probability": st.column_config.ProgressColumn(
                "Travel propensity", min_value=0, max_value=1, format="percent"
            ),
            "churn_probability": st.column_config.ProgressColumn(
                "Inactivity risk", min_value=0, max_value=1, format="percent"
            ),
            "clv_12m": st.column_config.NumberColumn("Projected value", format="$%.0f"),
            "best_offer_value": st.column_config.NumberColumn("Best offer value", format="$%.2f"),
        },
    )
    st.caption(
        f"{len(view):,} customers. Inactivity and attrition scores apply to historically active customers "
        "(≥3 trips in 90 days). Projected value is a heuristic 12-month projection, not validated CLV."
    )
    download(view, "customer_360_filtered.csv")
