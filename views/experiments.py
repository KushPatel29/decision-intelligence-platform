"""Experiments: the July nine-arm trial, CUPED effects, sequential monitoring and causal-learner evidence."""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from decision_platform.ui import NEUTRAL, SERIES, callout, chart, money, page_header, pct, tiles
from decision_platform.webapp import doc, download, offer_names, offer_order, table

page_header(
    "Experiments",
    "The July trial randomised every customer into control or one of eight offers. Effects are measured with "
    "CUPED variance reduction, monitored with group-sequential boundaries and corrected for multiple comparisons.",
    eyebrow="Prove",
)
e = doc("experiment")
design = e["design"]
names, order = offer_names(), offer_order()
results = pd.DataFrame(
    [
        {
            "offer_id": r["offer_id"],
            "arm": r["arm"],
            "n": r["n"],
            "response_diff": r["difference"],
            "trips": r["incremental_trips_cuped"]["difference"],
            "trips_low": r["incremental_trips_cuped"]["ci_low"],
            "trips_high": r["incremental_trips_cuped"]["ci_high"],
            "trips_raw_low": r["incremental_trips_per_customer"]["ci_low"],
            "trips_raw_high": r["incremental_trips_per_customer"]["ci_high"],
            "value": r["incremental_net_contribution_cuped"]["difference"],
            "value_low": r["incremental_net_contribution_cuped"]["ci_low"],
            "value_high": r["incremental_net_contribution_cuped"]["ci_high"],
            "value_p_adjusted": r["incremental_net_contribution_cuped"]["p_adjusted"],
            "variance_reduction": r["incremental_trips_cuped"]["variance_reduction"],
            "enrollment_rate": r["enrollment_rate"],
            "stopped_at_day": r["sequential"]["stopped_at_day"],
        }
        for r in e["results"]
    ]
)
tiles(
    [
        ("Customers per arm", f"{min(e['actual_per_arm'].values()):,}", f"Planned ≥ {e['required_per_arm']:,} for a 5-pt lift", True),
        ("Sample-ratio check", f"p = {e['srm_p_value']:.2f}", "Allocation matches the design"),
        ("Worst covariate imbalance", f"{e.get('max_abs_smd', 0):.3f} SMD", "Blocked randomisation; |SMD| < 0.1 is balanced"),
        ("CUPED variance removed", pct(e["cuped_mean_variance_reduction"]), "Pre-period trips as covariate"),
        (
            "Detectable effect, trips",
            f"{design['achieved_mde_trips_cuped']:.2f}",
            f"per customer with CUPED (raw {design['achieved_mde_trips_raw']:.2f})",
        ),
    ]
)

tab_effects, tab_sequential, tab_learners, tab_subgroups = st.tabs(
    ["Offer effects", "Sequential monitoring", "Causal learners", "Subgroups"]
)
with tab_effects:
    st.subheader("Incremental net contribution per customer, 30 days")
    ranked = results.sort_values("value")
    fig = go.Figure(
        go.Scatter(
            x=ranked.value,
            y=ranked.arm,
            mode="markers",
            marker=dict(size=11, color=[SERIES[order.index(o)] for o in ranked.offer_id]),
            error_x=dict(
                type="data",
                symmetric=False,
                array=ranked.value_high - ranked.value,
                arrayminus=ranked.value - ranked.value_low,
                color="#8faebf",
                thickness=1.5,
            ),
            customdata=ranked[["value_low", "value_high", "value_p_adjusted"]].to_numpy(),
            hovertemplate="%{y}<br>%{x:$,.2f} per customer<br>95% CI %{customdata[0]:$,.2f} to "
            "%{customdata[1]:$,.2f}<br>Bonferroni p %{customdata[2]:.4f}<extra></extra>",
        )
    )
    fig.add_vline(x=0, line_dash="dot", line_color=NEUTRAL)
    fig.update_xaxes(title="CAD per randomised customer (CUPED-adjusted, Bonferroni 95% intervals)")
    chart(fig, 360, legend=False)
    best = results.sort_values("value").iloc[-1]
    worst = results.sort_values("value").iloc[0]
    callout(
        f"On average, <b>{best.arm}</b> earns the most per randomised customer ({money(best.value, 2)}) and "
        f"<b>{worst.arm}</b> loses the most ({money(worst.value, 2)}). Averages hide who responds: the plan targets "
        "the customers each offer actually moves, which is why an offer that loses money on average can still "
        "belong in it."
    )
    st.subheader("Incremental trips per customer: CUPED vs unadjusted")
    fig = go.Figure()
    for label, low, high, color in [
        ("Unadjusted", "trips_raw_low", "trips_raw_high", NEUTRAL),
        ("CUPED", "trips_low", "trips_high", SERIES[0]),
    ]:
        fig.add_trace(
            go.Scatter(
                x=results.trips,
                y=results.arm + ("  " if label == "CUPED" else ""),
                mode="markers",
                name=label,
                marker=dict(size=9, color=color),
                error_x=dict(
                    type="data",
                    symmetric=False,
                    array=results[high] - results.trips,
                    arrayminus=results.trips - results[low],
                    color=color,
                    thickness=1.5,
                ),
                hovertemplate="%{y}<br>%{x:.2f} trips<extra>" + label + "</extra>",
            )
        )
    fig.add_vline(x=0, line_dash="dot", line_color=NEUTRAL)
    fig.update_xaxes(title="Incremental trips per customer over 30 days")
    chart(fig, 520)
    st.dataframe(
        results.drop(columns=["trips_raw_low", "trips_raw_high"]),
        hide_index=True,
        width="stretch",
        column_config={
            "response_diff": st.column_config.NumberColumn("Travelled, diff", format="%+.3f"),
            "trips": st.column_config.NumberColumn("Trips", format="%+.2f"),
            "value": st.column_config.NumberColumn("Net CAD", format="$%+.2f"),
            "value_p_adjusted": st.column_config.NumberColumn("p (Bonferroni)", format="%.4f"),
            "variance_reduction": st.column_config.NumberColumn("CUPED variance removed", format="percent"),
            "enrollment_rate": st.column_config.NumberColumn("Enrolled", format="percent"),
        },
    )
    download(results, "experiment_results.csv")

with tab_sequential:
    st.subheader("Would we have stopped early?")
    st.caption(
        "Cumulative CUPED z-statistics for trips per customer at days 10, 20 and 30 against two-sided O'Brien-"
        "Fleming boundaries, calibrated by simulation to the Bonferroni alpha. Crossing early saves exposure; "
        "the boundary is strict early so the overall false-positive rate is preserved."
    )
    fig = go.Figure()
    boundaries = e["sequential_boundaries"]
    days = [10, 20, 30]
    fig.add_trace(
        go.Scatter(x=days, y=boundaries, mode="lines", name="Efficacy boundary", line=dict(color="#ec835a", width=2, dash="dash"))
    )
    for i, r in enumerate(e["results"]):
        looks = r["sequential"]["looks"]
        fig.add_trace(
            go.Scatter(
                x=[look["day"] for look in looks],
                y=[look["z"] for look in looks],
                mode="lines+markers",
                name=r["arm"],
                line=dict(width=2, color=SERIES[i % len(SERIES)]),
                marker=dict(size=8),
                hovertemplate="Day %{x}<br>z = %{y:.2f}<extra>" + r["arm"] + "</extra>",
            )
        )
    fig.update_xaxes(title="Day of the 30-day window", tickvals=days)
    fig.update_yaxes(title="CUPED z-statistic")
    chart(fig, 440)
    stops = results[["arm", "stopped_at_day"]].fillna({"stopped_at_day": "Not stopped"})
    st.dataframe(stops, hide_index=True, width="stretch")

with tab_learners:
    learners = table("uplift_learners")
    metrics = doc("uplift_metrics")
    st.subheader("Which causal learner to trust, per offer")
    st.caption(
        "Each offer's production learner is the one with the lowest doubly robust loss on the validation fold, "
        "a criterion computable from trial data alone. The rank correlation with the simulator's true value "
        "shows whether that observable rule picks well."
    )
    summary = pd.DataFrame(metrics["learner_summary"]).T.reset_index(names="learner")
    tiles(
        [
            ("Selected learners vs truth", f"{metrics.get('selected_value_spearman', float('nan')):.2f}", "Mean rank correlation with true value", True),
        ]
        + [
            (row.learner.replace("_", "-").upper().replace("-LEARNER", " learner"), f"{row.mean_value_spearman:.2f}", f"chosen for {int(row.times_selected)} offers")
            for row in summary.itertuples()
        ]
    )
    value_cols = [c for c in learners if c.endswith("_value_spearman")]
    grid = learners.set_index("offer_id")[value_cols].rename(columns=lambda c: c.replace("_value_spearman", ""))
    grid.index = [names[o] for o in grid.index]
    fig = go.Figure(
        go.Heatmap(
            z=grid.to_numpy(),
            x=grid.columns,
            y=grid.index,
            colorscale=[[0, "#0d366b"], [0.5, "#3987e5"], [1, "#86b6ef"]],
            zmin=0,
            zmax=1,
            text=np.round(grid.to_numpy(), 2),
            texttemplate="%{text}",
            hovertemplate="%{y} · %{x}<br>rank correlation %{z:.2f}<extra></extra>",
            colorbar=dict(title="ρ", thickness=10),
        )
    )
    chart(fig, 360, legend=False)
    st.dataframe(learners, hide_index=True, width="stretch")
    persistence = metrics["persistence"]
    st.caption(
        "Carry-over into days 31-90 per dollar of in-window gross contribution, regression-adjusted on pre-period "
        "behaviour: discounts "
        f"{persistence['discount']['point_estimate']:.2f} (90% CI {persistence['discount']['ci_low']:.2f}-"
        f"{persistence['discount']['ci_high']:.2f}), loyalty {persistence['loyalty']['point_estimate']:.2f} "
        f"(90% CI {persistence['loyalty']['ci_low']:.2f}-{persistence['loyalty']['ci_high']:.2f}). Planning uses the "
        "conservative 20th percentile."
    )

with tab_subgroups:
    subgroups = table("experiment_subgroups")
    dimension = st.selectbox("Pre-treatment dimension", subgroups.dimension.unique())
    view = subgroups[subgroups.dimension.eq(dimension)]
    pivot = view.pivot(index="group", columns="arm", values="difference")
    fig = go.Figure(
        go.Heatmap(
            z=pivot.to_numpy(),
            x=pivot.columns,
            y=pivot.index,
            colorscale=[[0, "#e66767"], [0.5, "#383835"], [1, "#3987e5"]],
            zmid=0,
            text=np.round(pivot.to_numpy(), 1),
            texttemplate="%{text}",
            hovertemplate="%{y} · %{x}<br>%{z:$,.2f} per customer<extra></extra>",
            colorbar=dict(title="CAD", thickness=10),
        )
    )
    chart(fig, 320, legend=False)
    st.dataframe(
        view,
        hide_index=True,
        width="stretch",
        column_config={
            "difference": st.column_config.NumberColumn("Effect", format="$%+.2f"),
            "q_value": st.column_config.NumberColumn("BH q-value", format="%.3f"),
            "p_value": st.column_config.NumberColumn("p", format="%.4f"),
        },
    )
    st.caption(e["subgroup_scope"])
    download(view, "experiment_subgroups.csv")
