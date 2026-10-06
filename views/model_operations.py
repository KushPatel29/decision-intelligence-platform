"""Model operations: held-out quality, calibration, explanations, drift and the acceptance gate."""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from decision_platform.ui import NEUTRAL, SERIES, badges, chart, page_header, tiles
from decision_platform.webapp import doc, download, table

page_header(
    "Model operations",
    "How each model was chosen and how it performs on data it never saw: purged chronological folds, "
    "validation-only selection, a separate calibration fold and a predeclared acceptance gate.",
    eyebrow="Prove",
)
metrics = doc("metrics")
gate = doc("quality_gate")
badges(
    [
        (f"{c['model']}: {'passed' if c['passed'] else 'review'}", "good" if c["passed"] else "warning")
        for c in gate["checks"]
    ]
)

customer = metrics["customer"]
rows = []
for name in ["propensity", "churn", "attrition"]:
    m = customer[name]
    rows.append({"model": name, "champion": m["champion"], **m["test_calibrated"]})
quality = pd.DataFrame(rows)
tiles(
    [
        (
            f"{row.model.capitalize()} AUC",
            f"{row.roc_auc:.3f}",
            f"{row.champion.replace('_', ' ')} · ECE {row.ece_10bins:.3f}",
            i == 0,
        )
        for i, row in enumerate(quality.itertuples())
    ]
    + [
        (
            "Demand 30-day MAE",
            f"{metrics['demand']['test']['mae']:.1f}",
            metrics["demand"]["champion"].replace("_", " "),
        ),
    ]
)

tab_quality, tab_calibration, tab_explain, tab_drift = st.tabs(
    ["Leaderboards", "Calibration", "Explanations", "Drift"]
)
with tab_quality:
    st.subheader("Validation leaderboard (uncalibrated), then the held-out test of the champion")
    for name in ["propensity", "churn", "attrition"]:
        board = pd.DataFrame(customer[name]["validation_uncalibrated"]).T.reset_index(names="algorithm")
        board["champion"] = board.algorithm.eq(customer[name]["champion"])
        st.markdown(f"**{name.capitalize()}** · {customer[name]['population']}")
        st.dataframe(
            board[["algorithm", "champion", "roc_auc", "pr_auc", "brier", "ece_10bins", "lift_at_10"]],
            hide_index=True,
            width="stretch",
            column_config={
                "roc_auc": st.column_config.NumberColumn("ROC-AUC", format="%.3f"),
                "pr_auc": st.column_config.NumberColumn("PR-AUC", format="%.3f"),
                "brier": st.column_config.NumberColumn("Brier", format="%.4f"),
                "ece_10bins": st.column_config.NumberColumn("ECE", format="%.4f"),
                "lift_at_10": st.column_config.NumberColumn("Lift @10%", format="%.2f"),
            },
        )
    st.caption(
        "Champion = lowest validation Brier score, because decisions consume probabilities, not ranks. "
        "Folds: train July 2024-January 2025, validation April 2025, test July 2025; 90-day labels never cross a boundary."
    )
    st.subheader("Acceptance gate")
    st.dataframe(pd.DataFrame(gate["checks"]), hide_index=True, width="stretch")
    st.caption(gate["scope"])

with tab_calibration:
    name = (
        st.segmented_control("Model", ["propensity", "churn", "attrition"], default="propensity")
        or "propensity"
    )
    performance = table(f"performance_{name}")
    performance["bin"] = pd.cut(
        performance.predicted_probability, bins=[i / 10 for i in range(11)], include_lowest=True
    )
    curve = (
        performance.groupby("bin", observed=True)
        .agg(
            predicted=("predicted_probability", "mean"),
            observed=("target", "mean"),
            customers=("target", "size"),
        )
        .reset_index()
    )
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=curve.predicted,
            y=curve.observed,
            mode="lines+markers",
            name="July 2025 test",
            marker=dict(size=9, color=SERIES[0]),
            line=dict(color=SERIES[0], width=2),
            text=curve.customers,
            hovertemplate="Predicted %{x:.1%}<br>Observed %{y:.1%}<br>%{text:,} customers<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=[0, 1], y=[0, 1], mode="lines", name="Perfect calibration", line=dict(color=NEUTRAL, dash="dot")
        )
    )
    fig.update_xaxes(title="Predicted probability", tickformat=".0%")
    fig.update_yaxes(title="Observed rate", tickformat=".0%")
    chart(fig, 380)

with tab_explain:
    shap = table("shap_global").head(15).sort_values("mean_absolute_shap")
    fig = go.Figure(
        go.Bar(
            x=shap.mean_absolute_shap,
            y=shap.feature,
            orientation="h",
            marker_color=SERIES[0],
            hovertemplate="%{y}<br>%{x:.3f}<extra></extra>",
        )
    )
    fig.update_xaxes(title="Mean |SHAP| on the travel model's log-odds")
    chart(fig, 460, legend=False)
    st.caption(
        "Predictive explanations of travel propensity on 300 sampled customers. They explain the score, not causes."
    )
    clv = doc("probabilistic_clv")
    st.subheader("Probabilistic value benchmark (BG/NBD + Gamma-Gamma)")
    st.write(clv["method"])
    st.json(clv["validation_90d_customer_days"], expanded=False)
    st.caption(clv["limitations"])

with tab_drift:
    drift = table("feature_drift").sort_values("psi", ascending=False)
    fig = go.Figure(
        go.Bar(
            x=drift.feature,
            y=drift.psi,
            marker_color=[SERIES[1] if p > 0.2 else SERIES[0] for p in drift.psi],
            hovertemplate="%{x}<br>PSI %{y:.3f}<extra></extra>",
        )
    )
    fig.add_hline(y=0.2, line_dash="dot", line_color="#fab219", annotation_text="Review threshold 0.2")
    fig.update_yaxes(title="Population stability index, Jan → Oct 2025")
    chart(fig, 360, legend=False)
    monitoring = doc("monitoring")
    st.caption(monitoring["interpretation"])
    st.dataframe(pd.DataFrame(monitoring.get("prediction_drift", [])), hide_index=True, width="stretch")
    download(drift, "feature_drift.csv")
