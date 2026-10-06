"""Corridor's visual language and data-backed planning displays."""

import html
import math

import plotly.graph_objects as go
import streamlit as st

from .planning import zone_summary

COLORS = ["#4bdcd5", "#61a9ec", "#ffc773", "#a1a7ff", "#e493bc", "#a4d7b2"]
CSS = """<style>
:root{color-scheme:dark;--ink:#081522;--panel:#0d2030;--line:#263f52;--muted:#b3c7d7;--signal:#4bdcd5}
.stApp{background:var(--ink);color:#eef8ff;font-family:'Segoe UI',sans-serif}
.block-container{padding:3.4rem 2.4rem 3rem;max-width:1560px}
header[data-testid=stHeader]{background:rgba(8,21,34,.96)}
section[data-testid=stSidebar]{background:#0d2030;border-right:1px solid #263f52;min-width:252px!important;max-width:252px!important;width:252px!important}
section[data-testid=stSidebar] .block-container{padding-top:1.8rem}
section[data-testid=stSidebar] [data-testid=stRadio] label{padding:7px 9px;border-radius:7px;min-height:37px;width:100%;border:1px solid transparent}
section[data-testid=stSidebar] [data-testid=stRadio] label:has(input:checked){background:#173749;border-color:#2a5769}
section[data-testid=stSidebar] [data-testid=stRadio] label:hover{background:#122c3d}
section[data-testid=stSidebar] [data-testid=stRadio] p{font-size:13px}
h1,h2,h3{font-family:Bahnschrift,'Segoe UI',sans-serif!important;color:#eef8ff;letter-spacing:-.6px}
h1{font-weight:600!important;font-size:2.25rem!important;letter-spacing:-1.1px;margin-bottom:0!important;padding-bottom:.5rem!important}
h2{font-size:1.7rem!important}h3{font-size:1.3rem!important;font-weight:600!important}
[data-testid=stMetric]{padding:16px 18px;border-left:2px solid #34566b;background:#0d2030;min-height:105px;border-radius:0 8px 8px 0}
[data-testid=stMetricLabel]{color:#b8ccda;font-size:.82rem}
[data-testid=stMetricValue]{font-variant-numeric:tabular-nums;font-weight:600;color:#eef8ff;letter-spacing:-.8px;font-size:1.85rem}
[data-testid=stCaptionContainer]{color:#b3c7d7;line-height:1.6}
[data-testid=stForm]{border:1px solid #2b4b60;border-radius:12px;background:#0d2030;padding:24px}
button[kind=primary],button[kind=primaryFormSubmit]{background:#4bdcd5;color:#081522!important;border:none;font-weight:650;min-height:42px}
button[kind=primary] p,button[kind=primaryFormSubmit] p{color:#081522!important;font-weight:650}
button:focus-visible,a:focus-visible,[role=tab]:focus-visible,input:focus-visible{outline:3px solid #ffc773!important;outline-offset:3px}
.brand{display:flex;align-items:center;gap:10px;font-family:Bahnschrift,'Segoe UI',sans-serif;font-size:29px;font-weight:600;letter-spacing:-.8px;color:#eef8ff;margin-bottom:8px}
.brand svg{width:30px;height:34px;flex-shrink:0}.brand-subtitle{color:#b3c7d7;font-size:12px;line-height:1.5;margin:0 0 25px}
.sidebar-note{border-top:1px solid #294253;margin-top:22px;padding-top:20px;color:#b3c7d7;font-size:12px;line-height:1.7}
.sidebar-note strong{color:#edf6fc;font-weight:600}.sidebar-note small{display:block;margin-top:12px;font-size:11px;color:#9cb8cd}
.masthead{display:flex;justify-content:space-between;align-items:center;gap:12px;border-bottom:1px solid #263f52;padding:0 0 12px;margin:0 0 14px;font-size:12px;color:#b3c7d7}
.masthead .location{color:#d5e5ef}.masthead .version{color:#8faebf;margin-left:10px}
.status{display:inline-flex;align-items:center;gap:7px;color:#99ece4;font-size:12px;white-space:nowrap}
.status-dot{width:6px;height:6px;border-radius:50%;background:#4bdcd5;display:inline-block}
.page-description{color:#b3c7d7;font-size:14px;line-height:1.6;max-width:780px;margin:0 0 20px}
.campaign-deck{border:1px solid #315267;border-radius:16px;background:#0e2435;overflow:hidden;margin:4px 0 8px}
.deck-heading{display:flex;align-items:flex-start;justify-content:space-between;padding:22px 26px 0;gap:18px}
.deck-heading h2{font-size:27px!important;font-weight:600;margin:0 0 5px;padding:0!important;letter-spacing:-.6px}
.deck-heading p{color:#b5ccdc;font-size:13px;margin:0;line-height:1.6}.plan-tag{border:1px solid #355668;border-radius:6px;padding:7px 11px;color:#b7d9e5;font-size:11px;white-space:nowrap}
.network{padding:0 20px}.network svg{width:100%;height:auto;display:block;max-height:210px}
.network-hint{display:none}
.network-note{display:flex;justify-content:space-between;gap:14px;flex-wrap:wrap;color:#a7c4d5;font-size:11px;padding:0 26px 16px}
.network-note b{color:#d8eaf3;font-weight:500}.outcome-rail{display:grid;grid-template-columns:1fr 1.16fr 1.16fr .9fr;background:#0a1d2c;border-top:1px solid #2e4b60}
.outcome{padding:18px 24px;border-right:1px solid #294356}.outcome:last-child{border:0}.outcome-label{color:#b3c7d7;font-size:12px;display:block;margin-bottom:5px}
.outcome-value{font-family:Bahnschrift,'Segoe UI',sans-serif;font-size:30px;line-height:1.25;color:#eef8ff;letter-spacing:-.5px;font-variant-numeric:tabular-nums;white-space:nowrap}.outcome-value.accent{color:#7fe8e1}
.outcome-detail{color:#a7c4d5;font-size:11px;display:block;margin-top:4px}
.resource-ledger{padding:4px 0 10px}.resource-row{padding:14px 0;border-bottom:1px solid #263f52}.resource-row:last-child{border-bottom:0}
.resource-label{display:flex;justify-content:space-between;gap:15px;font-size:13px;color:#d4e6f0;margin-bottom:8px}.resource-label span:last-child{color:#b9cfdc;font-variant-numeric:tabular-nums}
.resource-track{height:5px;background:#233d50;border-radius:3px;overflow:hidden}.resource-fill{height:100%;background:#4bdcd5;border-radius:3px}.resource-fill.caution{background:#ffc773}
.resource-note{font-size:11px;color:#b3c7d7;margin-top:7px}.check-note{background:#12333d;border-left:2px solid #4bdcd5;padding:11px 14px;font-size:12px;color:#cce5ec;margin-top:10px;line-height:1.6}
.offer-row{display:grid;grid-template-columns:1fr auto;gap:6px 18px;padding:14px 0;border-bottom:1px solid #263f52}.offer-row:last-child{border-bottom:0}.offer-title{color:#edf6fc;font-size:14px;font-weight:600}.offer-value{color:#7fe8e1;font-size:17px;font-weight:600;font-variant-numeric:tabular-nums}.offer-detail{font-size:12px;color:#b3c7d7}.offer-track{grid-column:1/-1;height:4px;background:#223e52;border-radius:3px;margin-top:5px}.offer-track i{display:block;height:100%;border-radius:3px}
.delivery{padding:20px 22px;border-left:3px solid #4bdcd5;border-radius:0 10px 10px 0;background:#0d2030;margin-bottom:12px}.delivery.pending{border-color:#ffc773}.delivery .delivery-status{color:#99e5df;font-size:12px}.delivery.pending .delivery-status{color:#ffd79b}.delivery strong{color:#eef8ff;display:block;margin-top:5px}.delivery p{color:#b7cfde;margin:8px 0 0;font-size:14px;line-height:1.65}
[data-testid=stTabs] [role=tablist]{gap:28px;border-bottom:1px solid #294356;margin-bottom:14px}[data-testid=stTabs] [role=tab]{font-weight:600;padding:9px 0}
[data-testid=stDataFrame]{border:1px solid #263f52;border-radius:8px;overflow:hidden}[data-testid=stAlert]{border-radius:8px}a{color:#7fe8e1}
@media(max-width:1100px){.block-container{padding:3.4rem 1.7rem 3rem}.outcome{padding:16px}.outcome-value{font-size:26px}.network{padding:0 10px}}
@media(max-width:850px){.block-container{padding:3.7rem 1rem 2rem}.deck-heading{padding:18px 18px 0;flex-wrap:wrap;gap:8px}.deck-heading h2{font-size:24px!important}.network{padding:0 10px;overflow-x:auto}.network svg{min-width:620px;max-height:none}.network-note{padding:4px 18px 14px}.outcome-rail{grid-template-columns:1fr 1fr}.outcome{padding:15px 18px;border-bottom:1px solid #294356}.outcome:nth-child(2){border-right:0}.masthead{flex-wrap:wrap}.masthead .version{display:none}h1{font-size:1.95rem!important}[data-testid=stTabs] [role=tablist]{gap:20px}}
@media(max-width:430px){.outcome-value{font-size:23px}.outcome-label{font-size:11px}.outcome-detail{font-size:10px}.deck-heading p{font-size:12px}.network-note{font-size:11px}.plan-tag{padding:5px 8px}[data-testid=stForm]{padding:18px}}
@media(max-width:850px){.network-hint{display:block;color:#b3c7d7;font-size:11px;padding:0 18px 10px}}
@media(prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
</style>"""


def chart(fig, height=330):
    fig.update_layout(
        height=height,
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Segoe UI", color="#c9dce8", size=12),
        margin=dict(l=5, r=12, t=30, b=15),
        colorway=COLORS,
        legend=dict(orientation="h", y=1.14, x=0, font=dict(size=11), traceorder="normal"),
        hoverlabel=dict(bgcolor="#102b3d", font=dict(color="#eef8ff", size=13)),
        hovermode=fig.layout.hovermode or "x unified",
    )
    fig.update_xaxes(gridcolor="#1c3245", zerolinecolor="#294356", showgrid=False)
    fig.update_yaxes(gridcolor="#1c3245", zerolinecolor="#294356")
    st.plotly_chart(
        fig,
        width="stretch",
        config={
            "displaylogo": False,
            "scrollZoom": False,
            "modeBarButtonsToRemove": ["lasso2d", "select2d"],
            "toImageButtonOptions": {"scale": 2},
        },
    )


def line(frame, x, ys, height=330, fill=False):
    fig = go.Figure()
    for i, y in enumerate(ys):
        fig.add_trace(
            go.Scatter(
                x=frame[x],
                y=frame[y],
                name=y.replace("_", " ").title(),
                mode="lines+markers",
                line=dict(width=2.5, color=COLORS[i % len(COLORS)]),
                marker=dict(size=4),
                fill="tozeroy" if fill and i == 0 else None,
                fillcolor="rgba(75,220,213,.08)",
                hovertemplate="%{y:,.2f}<extra>%{fullData.name}</extra>",
            )
        )
    chart(fig, height)


def bars(frame, x, ys, height=330, stack=False):
    fig = go.Figure()
    for i, y in enumerate(ys):
        fig.add_trace(
            go.Bar(
                x=frame[x],
                y=frame[y],
                name=y.replace("_", " ").title(),
                marker_color=COLORS[i % len(COLORS)],
                marker_line_width=0,
                hovertemplate="%{x}<br>%{y:,.1f}<extra>%{fullData.name}</extra>",
            )
        )
    fig.update_layout(barmode="stack" if stack else "group", bargap=0.35)
    fig.update_xaxes(type="category")
    chart(fig, height)


def corridor(capacity, zone_names):
    cells = zone_summary(capacity)
    nodes = []
    radius = 23
    circumference = 2 * math.pi * radius
    coords = []
    for i, (zone, row) in enumerate(cells.iterrows()):
        x = 66 + i * 154
        y = 104 if i % 2 == 0 else 78
        coords.append((x, y))
        color = "#ffc773" if row.utilization >= 0.75 else "#4bdcd5"
        name = html.escape(zone_names[zone])
        label = f"{row.utilization:.0%}"
        arc = max(0, min(1, row.utilization)) * circumference
        nodes.append(
            f'<g><title>{name}: {label} forecast load; {row.remaining_with_reserve:,.0f} trips available after reserve</title><circle cx="{x}" cy="{y}" r="31" fill="#0e2435"/><circle cx="{x}" cy="{y}" r="{radius}" fill="#102b3d" stroke="#2d4c61" stroke-width="3"/><circle cx="{x}" cy="{y}" r="{radius}" fill="none" stroke="{color}" stroke-width="3" stroke-linecap="round" stroke-dasharray="{arc:.2f} {circumference:.2f}" transform="rotate(-90 {x} {y})"/><text x="{x}" y="{y + 5}" fill="#eef8ff" font-size="14" font-weight="600" text-anchor="middle">{label}</text><text x="{x}" y="{y + 49}" fill="#eef8ff" font-size="16" font-weight="500" text-anchor="middle">{name}</text><text x="{x}" y="{y + 69}" fill="#b3cddd" font-size="12" text-anchor="middle">{row.remaining_with_reserve:,.0f} trips free</text></g>'
        )
    path = "M" + " L".join(f"{x} {y}" for x, y in coords)
    return (
        '<svg viewBox="0 0 902 194" role="img" aria-label="Six simulated zones with capacity-weighted forecast load and remaining trips after safety reserve"><defs><pattern id="corridor-grid" width="28" height="28" patternUnits="userSpaceOnUse"><path d="M28 0H0V28" fill="none" stroke="#294c61" stroke-width=".5"/></pattern></defs><rect x="0" y="18" width="902" height="160" fill="url(#corridor-grid)" opacity=".35"/><path d="'
        + path
        + '" fill="none" stroke="#1e3e53" stroke-width="22" stroke-linejoin="round"/><path d="'
        + path
        + '" fill="none" stroke="#456980" stroke-width="1" stroke-dasharray="4 7"/><path d="'
        + path
        + '" fill="none" stroke="#4bdcd5" stroke-width="2" opacity=".75"/>'
        + "".join(nodes)
        + "</svg>"
    )


def campaign_deck(capacity, zone_names, combined, shortlist, solver):
    spend = combined["spend"]
    budget = combined["budget"]
    roi = combined["net_contribution"] / spend if spend else None
    reserve = capacity.reserve_trips.sum() / capacity.baseline_forecast.sum()
    outcomes = [
        ("Additional trips", f"{combined['incremental_trips']:,.1f}", "Expected over 30 days", False),
        (
            "Net contribution",
            f"${combined['net_contribution']:,.2f}",
            f"{roi:.0%} net ROI" if roi is not None else "No incentive spend",
            True,
        ),
        (
            "Incentive costs",
            f"${spend:,.2f}",
            f"{spend / budget:.0%} of ${budget:,.0f} budget" if budget else "Zero spending budget",
            False,
        ),
        (
            "Selected contacts",
            f"{combined['contacts']:,}",
            f"{combined['contacts'] / shortlist:.0%} of {shortlist:,} shortlisted"
            if shortlist
            else "No candidates",
            False,
        ),
    ]
    rail = "".join(
        f'<div class="outcome"><span class="outcome-label">{label}</span><div class="outcome-value {"accent" if accent else ""}">{value}</div><span class="outcome-detail">{detail}</span></div>'
        for label, value, detail, accent in outcomes
    )
    st.markdown(
        '<section class="campaign-deck" aria-label="Saved October campaign"><div class="deck-heading"><div><h2>October campaign</h2><p>Promotion and loyalty allocation for six simulated corridor zones.</p></div><span class="plan-tag">Saved baseline / '
        + html.escape(solver)
        + '</span></div><div class="network">'
        + corridor(capacity, zone_names)
        + '</div><div class="network-hint">Scroll the corridor to inspect all six zones.</div><div class="network-note"><span><b>Ring:</b> forecast load as a share of capacity</span><span><b>Trips free:</b> headroom after '
        + f"{reserve:.0%}"
        + ' demand reserve</span></div><div class="outcome-rail">'
        + rail
        + "</div></section>",
        unsafe_allow_html=True,
    )


def resource_ledger(items, note=None):
    rows = []
    for label, used, limit, value_label, detail in items:
        share = used / limit if limit else 0
        rows.append(
            f'<div class="resource-row"><div class="resource-label"><span>{html.escape(label)}</span><span>{html.escape(value_label)}</span></div><div class="resource-track" role="meter" aria-label="{html.escape(label)}" aria-valuenow="{used}" aria-valuemin="0" aria-valuemax="{max(limit, 1)}"><div class="resource-fill {"caution" if share >= 0.9 else ""}" style="width:{min(100, max(0, share * 100)):.1f}%"></div></div><div class="resource-note">{html.escape(detail)}</div></div>'
        )
    content = '<div class="resource-ledger">' + "".join(rows) + "</div>"
    if note:
        content += '<div class="check-note">' + html.escape(note) + "</div>"
    st.markdown(content, unsafe_allow_html=True)


def offer_mix(frame):
    grouped = frame.groupby("offer_name", sort=False).agg(
        contacts=("customer_id", "size"), trips=("incremental_trips", "sum"), net=("net_contribution", "sum")
    )
    rows = []
    total = len(frame)
    for i, (name, row) in enumerate(grouped.iterrows()):
        share = row.contacts / total if total else 0
        rows.append(
            f'<div class="offer-row"><span class="offer-title">{html.escape(name)}</span><span class="offer-value">{int(row.contacts):,} contacts</span><span class="offer-detail">{row.trips:,.1f} expected additional trips</span><span class="offer-detail">${row.net:,.2f} net contribution</span><div class="offer-track"><i style="width:{share * 100:.1f}%;background:{COLORS[i % len(COLORS)]}"></i></div></div>'
        )
    if not rows:
        rows.append(
            '<p class="page-description">No contacts selected under these limits. Adjust the campaign controls to explore another plan.</p>'
        )
    st.markdown("".join(rows), unsafe_allow_html=True)
