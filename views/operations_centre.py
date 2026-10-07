"""Operations centre: release integrity, feed quality, alerts and deployment readiness."""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from decision_platform.ui import NEUTRAL, SERIES, STATUS, badges, chart, page_header, pct, tiles
from decision_platform.webapp import SERVING, context, doc, download, table

page_header(
    "Operations centre",
    "Is today's snapshot safe to decide on? Release integrity, data-feed quality with planted-defect checks, "
    "drift and campaign alerts, and what a hosted deployment still needs.",
    eyebrow="Operate",
)
ctx = context()
gate = doc("quality_gate")
monitoring = doc("monitoring")
quality = doc("data_quality")
monitor = doc("data_quality_monitor")
alerts = monitoring.get("alerts", [])
evaluation = monitor.get("evaluation_against_planted", {})
badges(
    [
        (f"Release {ctx['release_id'][:12]} verified", "good"),
        (
            "Model acceptance passed" if gate["passed"] else "Model acceptance: review",
            "good" if gate["passed"] else "warning",
        ),
        (f"{len(alerts)} review alerts", "warning" if alerts else "good"),
    ]
)
quarantined = quality.get("quarantined", {})
tiles(
    [
        ("Bronze trips ingested", f"{quality.get('bronze_rows', 0):,}", "Raw feed, defects included", True),
        (
            "Quarantined in silver",
            f"{sum(quarantined.values()):,}",
            ", ".join(f"{k.replace('_', ' ')}: {v:,}" for k, v in quarantined.items()),
        ),
        (
            "Feed defects caught",
            f"{evaluation.get('caught', 0)} of {evaluation.get('planted_defect_days', 0)}",
            f"precision {pct(evaluation.get('precision', 0))}",
        ),
        (
            "False-alarm days",
            f"{evaluation.get('false_alarm_days', 0)}",
            f"of {evaluation.get('monitored_days', 0)} monitored days",
        ),
        (
            "Data contracts",
            f"{sum(quality['checks'].values())}/{len(quality['checks'])}",
            "Silver layer checks passed",
        ),
    ]
)

tab_feed, tab_alerts, tab_release = st.tabs(["Feed quality", "Alert queue", "Release & readiness"])
with tab_feed:
    daily = table("data_quality_daily")
    daily["day"] = pd.to_datetime(daily["day"])
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=daily.day,
            y=daily.expected_rows,
            mode="lines",
            name="Expected (same weekday)",
            line=dict(color=NEUTRAL, dash="dot", width=2),
        )
    )
    fig.add_trace(
        go.Scatter(
            x=daily.day, y=daily.rows, mode="lines", name="Ingested rows", line=dict(color=SERIES[0], width=2)
        )
    )
    flagged = daily[daily.flagged]
    fig.add_trace(
        go.Scatter(
            x=flagged.day,
            y=flagged.rows,
            mode="markers",
            name="Flagged",
            marker=dict(
                size=12, color=STATUS["serious"], symbol="diamond", line=dict(width=2, color="#081522")
            ),
            text=flagged.reason,
            hovertemplate="%{x|%b %d}<br>%{y:,} rows<br>%{text}<extra></extra>",
        )
    )
    fig.update_layout(hovermode="x unified")
    fig.update_yaxes(title="Trip rows per ingestion day")
    chart(fig, 380)
    st.caption(monitor["method"])
    st.dataframe(
        flagged[
            ["day", "rows", "expected_rows", "volume_z", "duplicate_rate", "out_of_range_rate", "reason"]
        ],
        hide_index=True,
        width="stretch",
        column_config={
            "volume_z": st.column_config.NumberColumn("Volume z", format="%.1f"),
            "duplicate_rate": st.column_config.NumberColumn("Duplicates", format="percent"),
            "out_of_range_rate": st.column_config.NumberColumn("Out of range", format="percent"),
        },
    )

with tab_alerts:
    if alerts:
        frame = pd.DataFrame(alerts)
        st.dataframe(frame, hide_index=True, width="stretch")
        download(frame, "alert_queue.csv")
    else:
        st.success("No batch thresholds exceeded.")
    st.caption(
        "Workflow: triage → check calendar, upstream freshness and matured outcomes → approve retraining → "
        "validate on untouched outcomes → reviewed promotion. Alerts never retrain or deploy a model on their own."
    )
    with st.expander("Prediction, volume and campaign checks"):
        for key in ["prediction_drift", "campaign_checks"]:
            st.markdown(f"**{key.replace('_', ' ').capitalize()}**")
            st.dataframe(pd.DataFrame(monitoring.get(key, [])), hide_index=True, width="stretch")

with tab_release:
    manifest = pd.read_json(SERVING / "manifest.json", typ="series")
    st.markdown(
        f"**Serving snapshot** · release `{manifest['release_id'][:16]}` · decision date {manifest['decision_date']}"
    )
    files = pd.DataFrame(
        {"file": list(manifest["files"]), "sha256": [v[:16] + "…" for v in manifest["files"].values()]}
    )
    st.dataframe(files, hide_index=True, width="stretch")
    st.caption(
        "The app verifies every file's SHA-256 against this manifest before serving and refuses a partial, "
        "refreshing or edited snapshot. Production mode also refuses to serve if model acceptance fails."
    )
    st.subheader("Deployment readiness")
    readiness = [
        (
            "Container image",
            "Built from Dockerfile; read-only filesystem, non-root user, health check",
            "Ready",
        ),
        (
            "Identity",
            "OIDC sign-in with an explicit subject allowlist; anonymous mode refused in production",
            "Ready",
        ),
        (
            "Audit trail",
            "Owner-isolated SQLite WAL store of solves and saved plans with release identity",
            "Ready",
        ),
        ("Decision API", "FastAPI service with API-key auth, health and readiness probes", "Ready"),
        (
            "Cloud training",
            "SageMaker pipeline definitions compile; hosted execution needs an AWS account",
            "Pending account",
        ),
        (
            "Power BI",
            "Generated nine-page report; all 135 measures executed against Power BI's engine",
            "Ready",
        ),
        (
            "Databricks job",
            "Four tasks (pipeline with Gurobi, Delta with CHECK constraints and a PySpark parity gate, Unity Catalog "
            "registry, reconciled publish) ran on Databricks serverless and passed every check",
            "Ready",
        ),
    ]
    st.dataframe(
        pd.DataFrame(readiness, columns=["Component", "Evidence", "Status"]), hide_index=True, width="stretch"
    )
