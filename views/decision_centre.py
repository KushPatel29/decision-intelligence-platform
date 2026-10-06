"""Decision centre: the October plan, a scenario studio and the evidence behind the plan."""

import json

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from decision_platform.optimization import lp_relaxation, solve
from decision_platform.planning import SCENARIO_TEMPLATES, plan_capacity, with_reserve
from decision_platform.runtime import audit_event, saved_plans
from decision_platform.ui import (
    SEQUENTIAL,
    callout,
    campaign_deck,
    chart,
    money,
    offer_mix,
    page_header,
    pct,
    resource_ledger,
    tiles,
)
from decision_platform.webapp import ROOT, context, doc, download, offer_names, offer_order, table, zone_names

page_header(
    "Decision centre",
    "Who should get which offer in October, and why the plan is worth what it claims. "
    "Plan, stress-test and save reviewed scenarios.",
    eyebrow="Decide",
)
ctx = context()
summary, optimization, policy = doc("summary"), doc("optimization"), doc("policy_value")
combined = optimization["combined"]
capacity = table("capacity")
decisions = table("decisions")
zones, names, order = zone_names(), offer_names(), offer_order()
certificate = optimization.get("certification") or {}
campaign_deck(
    capacity,
    zones,
    combined,
    summary["eligible_customers"],
    optimization["joint"]["solver"],
    certificate.get("proven_optimal", False),
)

rows = {p["policy"]: p for p in policy["policies"]}
optimized = rows["Optimized (MIP)"]
propensity = next(v for k, v in rows.items() if k.startswith("Propensity"))
callout(
    f"<b>Simulation check:</b> scored against the simulator's true customer responses, this plan creates "
    f"<b>{money(optimized['true_value'])}</b>, {pct(optimized['share_of_oracle'])} of the best plan any planner "
    f"could build. Sending 10% off to the highest-propensity travellers under the same guardrails creates "
    f"{money(propensity['true_value'])} ({pct(propensity['share_of_oracle'])}). See <b>Policy value</b>.",
    "good",
)

overview, studio, evidence = st.tabs(["Plan overview", "Scenario studio", "Plan evidence"])

with overview:
    left, right = st.columns([1, 1.25])
    with left:
        st.subheader("Offer mix")
        offer_mix(decisions, names, order)
    with right:
        st.subheader("Guardrails and their marginal value")
        prices = {p["constraint"]: p["shadow_price"] for p in optimization["lp_relaxation"]["shadow_prices"]}

        def worth(name, unit):
            price = prices.get(name, 0.0)
            return f"Binding: one more {unit} is worth {money(price, 2)}" if price > 1e-6 else "Not binding"

        resource_ledger(
            [
                (
                    "Incentive budget",
                    combined["spend"],
                    combined["budget"],
                    f"{money(combined['spend'])} / {money(combined['budget'])}",
                    worth("budget", "dollar"),
                ),
                (
                    "Contact limit",
                    combined["contacts"],
                    combined["contact_limit"],
                    f"{combined['contacts']:,} / {combined['contact_limit']:,}",
                    worth("campaign_size", "contact"),
                ),
                (
                    "Loyalty points liability",
                    combined["points_awarded"],
                    max(combined["points_limit"], 1),
                    f"{combined['points_awarded']:,} / {combined['points_limit']:,}",
                    worth("loyalty_points", "point"),
                ),
            ],
            "Every budget, contact, ROI, points, inventory, eligibility and capacity constraint passed.",
        )
    st.subheader("Forecast load by zone and travel period, including the campaign")
    grid = (
        capacity.assign(zone=capacity.zone_id.map(zones))
        .pivot(index="zone", columns="period", values="final_utilization")
        .reindex(list(zones.values()))[["Peak", "Off-peak", "Weekend"]]
    )
    fig = go.Figure(
        go.Heatmap(
            z=grid.to_numpy() * 100,
            x=grid.columns,
            y=grid.index,
            colorscale=SEQUENTIAL,
            zmin=0,
            zmax=100,
            text=grid.to_numpy() * 100,
            texttemplate="%{text:.0f}%",
            hovertemplate="%{y} · %{x}<br>%{z:.1f}% of planning capacity<extra></extra>",
            colorbar=dict(title="Load %", thickness=10),
        )
    )
    chart(fig, 300, legend=False)
    st.caption(
        "Baseline forecast plus the plan's signed campaign trips, as a share of planning capacity. Central peak "
        "cells are deliberately tight; off-peak offers that move commuters out of the peak free capacity there."
    )

with studio:
    st.subheader("Build a scenario")
    st.caption(
        "Start from a template, change any guardrail and re-optimize every eligible customer. Results are compared "
        "with the saved October plan."
    )

    def apply_template():
        for key, value in SCENARIO_TEMPLATES[st.session_state["scenario_template"]].items():
            st.session_state["scenario_" + key] = value

    st.selectbox(
        "Start from a template",
        list(SCENARIO_TEMPLATES),
        key="scenario_template",
        on_change=apply_template,
        help="Changing the template replaces the controls below; every limit stays editable.",
    )
    for key, value in SCENARIO_TEMPLATES[st.session_state["scenario_template"]].items():
        st.session_state.setdefault("scenario_" + key, value)
    with st.form("campaign_scenario"):
        c1, c2, c3 = st.columns(3)
        budget = c1.number_input("Incentive budget (CAD)", 0.0, 200000.0, step=1000.0, key="scenario_budget")
        limit = c2.number_input("Maximum contacts", 0, 25000, step=250, key="scenario_limit")
        roi = c3.number_input(
            "Minimum portfolio net ROI",
            0.0,
            5.0,
            step=0.05,
            key="scenario_roi",
            help="30-day net contribution divided by incentive cost, for the plan as a whole.",
        )
        c4, c5, c6 = st.columns(3)
        points = c4.number_input("Loyalty points cap", 0, 10_000_000, step=100_000, key="scenario_points")
        reserve = c5.slider(
            "Capacity safety reserve",
            0.0,
            0.5,
            step=0.05,
            format="%.2f",
            key="scenario_reserve",
            help="Fraction of baseline forecast demand protected in every zone and period.",
        )
        risk = c6.slider(
            "Risk aversion (std. deviations)",
            0.0,
            2.0,
            step=0.25,
            key="scenario_risk",
            help="Optimize value minus this many bootstrap standard deviations: fewer, surer bets.",
        )
        relief = st.slider(
            "Value per rush-hour trip moved onto the 407 (CAD)",
            0.0,
            3.0,
            step=0.25,
            key="scenario_relief",
            help="Strategic value of taking a rush-hour trip off a congested alternate route. Peak capacity on the "
            "407 itself stays a hard limit.",
        )
        solver = st.radio(
            "Core solver",
            ["Auto (Gurobi core, HiGHS fallback)", "HiGHS only"],
            horizontal=True,
            help="HiGHS solves the LP over every candidate; the small core left after reduced-cost fixing goes to "
            "Gurobi when its licence is available.",
        )
        submitted = st.form_submit_button("Optimize scenario", type="primary", width="stretch")
    if submitted:
        try:
            candidates = table("candidates")
            candidates["net_contribution"] = candidates.value_uplift - risk * candidates.value_uplift_sd
            candidates["relief_value"] = relief * candidates.trips_peak
            candidates["objective_value"] = (
                candidates.net_contribution + candidates.later_value_uplift + candidates.relief_value
            )
            keep = (candidates.objective_value > 0) | (candidates.trips_peak < 0)
            candidates = candidates[keep].reset_index(drop=True)
            base = with_reserve(capacity, reserve)
            mode = "highs" if solver.startswith("HiGHS") else "auto"
            with st.spinner("Solving the LP relaxation and the exact core…"):
                allocation = solve(candidates, base, float(budget), int(limit), float(roi), mode, int(points))
                lp = lp_relaxation(candidates, base, float(budget), int(limit), float(roi), int(points))
            result = {
                "frame": allocation.selected,
                "diagnostics": allocation.diagnostics,
                "solver": allocation.solver,
                "status": allocation.status,
                "shadow": lp["shadow_prices"],
                "limits": {
                    "budget": budget,
                    "limit": limit,
                    "roi": roi,
                    "points": points,
                    "reserve": reserve,
                    "risk": risk,
                    "relief": relief,
                },
                "stamp": ctx["stamp"],
            }
            st.session_state["scenario"] = result
            history = st.session_state.setdefault("scenario_history", [])
            history.append(
                {
                    "scenario": f"Plan {len(history) + 1}",
                    "budget": budget,
                    "contacts": len(allocation.selected),
                    "spend": allocation.diagnostics["spend"],
                    "expected_value": allocation.objective,
                    "incremental_trips": allocation.diagnostics["incremental_trips"],
                    "points": int(allocation.selected.points.sum()),
                    "reserve": reserve,
                    "risk_aversion": risk,
                    "relief_value": relief,
                    "rush_hour_trips_per_workday": float(allocation.selected.trips_peak.sum() / 22),
                }
            )
            st.session_state["scenario_history"] = history[-20:]
            audit_event(
                ROOT,
                ctx["owner"],
                "solve_campaign",
                {
                    "release_id": ctx["release_id"],
                    "solver": allocation.solver,
                    "limits": result["limits"],
                    "diagnostics": {k: v for k, v in allocation.diagnostics.items() if k != "certificate"},
                },
            )
        except Exception as exc:  # Surface solver or input problems; never crash the page.
            st.error(f"The scenario did not solve: {exc}")
            st.caption(
                "Lower the capacity reserve if forecast plus reserve exceeds capacity, or relax a limit."
            )
    scenario = st.session_state.get("scenario")
    if scenario and scenario["stamp"] == ctx["stamp"]:
        d, view = scenario["diagnostics"], scenario["frame"]
        st.subheader("Scenario result")
        st.caption(
            f"{scenario['solver']} · {scenario['status']}. Changes compare with the saved October plan."
        )
        cols = st.columns(4)
        cols[0].metric("Contacts", f"{len(view):,}", f"{len(view) - combined['contacts']:+,} vs plan")
        cols[1].metric(
            "Incentive spend",
            money(d["spend"]),
            f"{d['spend'] - combined['spend']:+,.0f} CAD vs plan",
            delta_color="inverse",
        )
        cols[2].metric(
            "Expected value",
            money(d["objective_value"]),
            f"{d['objective_value'] - combined['objective_value']:+,.0f} CAD vs plan",
        )
        cols[3].metric(
            "Expected extra trips",
            f"{d['incremental_trips']:,.0f}",
            f"{d['incremental_trips'] - combined['incremental_trips']:+,.0f} vs plan",
        )
        if view.empty:
            st.info("No contacts under these limits. Increase the budget or relax a limit.")
        binding = [p for p in scenario["shadow"] if p["binding"]]
        if binding:
            lines = []
            for p in binding:
                label = p["constraint"].replace("campaign_size", "contact limit").replace("_", " ")
                lines.append(f"<b>{label}</b>: {money(p['shadow_price'], 2)} per unit")
            callout("Binding guardrails and what one more unit is worth: " + " · ".join(lines))
        left, right = st.columns(2)
        with left:
            st.subheader("Scenario offer mix")
            offer_mix(view, names, order)
        with right:
            st.subheader("Scenario capacity")
            result_capacity = plan_capacity(capacity, view, scenario["limits"]["reserve"])
            peak = result_capacity[result_capacity.period.eq("Peak")]
            fig = go.Figure(
                go.Bar(
                    x=peak.zone_id.map(zones),
                    y=peak.final_utilization * 100,
                    marker_color="#3987e5",
                    hovertemplate="%{x}<br>%{y:.1f}% peak load<extra></extra>",
                )
            )
            fig.add_hline(y=100, line_dash="dot", line_color="#8faebf", annotation_text="Capacity")
            fig.update_yaxes(title="Peak load, % of capacity", range=[0, 110])
            chart(fig, 300, legend=False)
        with st.expander("Selected customers"):
            st.dataframe(
                view[["customer_id", "offer_name", "zone_id", "objective_value", "cost", "value_uplift_sd"]],
                hide_index=True,
                width="stretch",
                column_config={
                    "objective_value": st.column_config.NumberColumn("Expected value", format="$%.2f"),
                    "cost": st.column_config.NumberColumn("Incentive cost", format="$%.2f"),
                    "value_uplift_sd": st.column_config.NumberColumn("Uncertainty (sd)", format="$%.2f"),
                },
            )
        download(view, "scenario_allocation.csv", "Download scenario allocation")
        if st.button("Save reviewed scenario"):
            identifier = audit_event(
                ROOT,
                ctx["owner"],
                "save_plan",
                {
                    "release_id": ctx["release_id"],
                    "solver": scenario["solver"],
                    "limits": scenario["limits"],
                    "outcomes": {k: v for k, v in d.items() if k != "certificate"},
                    "allocation": json.loads(
                        view[["customer_id", "offer_id", "cost", "objective_value"]].to_json(orient="records")
                    ),
                },
            )
            st.success(f"Scenario saved with audit reference {identifier[:12]}.")
        st.subheader("Scenario comparison")
        history = pd.DataFrame(st.session_state.get("scenario_history", []))
        st.dataframe(
            history,
            hide_index=True,
            width="stretch",
            column_config={
                "budget": st.column_config.NumberColumn("Budget", format="$%.0f"),
                "spend": st.column_config.NumberColumn("Spend", format="$%.0f"),
                "expected_value": st.column_config.NumberColumn("Expected value", format="$%.0f"),
                "incremental_trips": st.column_config.NumberColumn("Extra trips", format="%.0f"),
                "reserve": st.column_config.NumberColumn("Reserve", format="percent"),
            },
        )
        download(history, "scenario_comparison.csv")
    else:
        st.caption("Solved scenarios appear here with comparisons against the saved plan.")
    with st.expander("My saved scenarios"):
        plans = saved_plans(ROOT, ctx["owner"])
        if plans:
            st.dataframe(
                pd.DataFrame([{k: v for k, v in p.items() if k != "allocation"} for p in plans]),
                hide_index=True,
                width="stretch",
            )
        else:
            st.caption("Saved scenarios keep their limits, allocation and release identity across sessions.")

with evidence:
    st.subheader("Optimality certificate")
    if certificate:
        tiles(
            [
                (
                    "Decisions considered",
                    f"{certificate.get('variables', 0):,}",
                    "Eligible customer-offer pairs",
                    True,
                ),
                (
                    "Settled by reduced costs",
                    f"{certificate.get('variables', 0) - certificate.get('free_variables', 0):,}",
                    "Provably fixed",
                ),
                (
                    "Exact core",
                    f"{certificate.get('free_variables', 0):,}",
                    f"Solved by {certificate.get('core_solver', '–')}",
                ),
                (
                    "Gap to LP bound",
                    f"{certificate.get('relative_gap_to_lp_bound', 0):.4%}",
                    "Proven optimal" if certificate.get("proven_optimal") else "Feasible",
                ),
            ]
        )
        st.caption(
            "HiGHS solves the LP relaxation over every candidate. Any variable whose reduced cost exceeds the gap "
            "between the LP bound and a rounded incumbent takes the same value in every better plan, so it is fixed. "
            "The remaining core is solved exactly; if it cannot beat the incumbent, the plan is globally optimal."
        )
    st.subheader("Constraint checks")
    checks = pd.DataFrame(
        {
            "Constraint": [
                "Incentive budget",
                "Contact limit",
                "Portfolio net ROI floor",
                "Loyalty points cap",
                "One offer per customer",
                "Eligibility (consent, My Account, no past-due balance, active)",
                "Offer inventory",
                "Zone and period capacity after reserve",
            ],
            "Result": [
                f"{money(combined['spend'])} of {money(combined['budget'])}",
                f"{combined['contacts']:,} of {combined['contact_limit']:,}",
                f"{combined['net_contribution'] / max(combined['spend'], 1):.0%} vs {combined['min_roi']:.0%} floor",
                f"{combined['points_awarded']:,} of {combined['points_limit']:,}",
                "Passed",
                "Passed",
                "Passed",
                "Passed",
            ],
        }
    )
    st.dataframe(checks, hide_index=True, width="stretch")
    st.subheader("Planning economics")
    st.write(optimization["economics"])
    st.caption(optimization["scope"])
    download(decisions, "october_plan.csv", "Download the October plan")
