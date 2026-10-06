"""Corridor's design system: tokens, page chrome, stat tiles and the chart theme.

Chart colours come from a categorical palette validated for colour-vision
deficiency on the app's navy surface (worst adjacent CVD delta-E 8.4, normal
vision 19.3, every slot >= 3:1 contrast). The teal brand accent is reserved for
interface chrome and is never a data series.
"""

from __future__ import annotations

import html
import math

import plotly.graph_objects as go
import streamlit as st

from .planning import zone_summary

# Categorical slots, fixed order: blue, orange, aqua, yellow, magenta, green, violet, red.
SERIES = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767"]
COLORS = SERIES  # Backwards-compatible name.
STATUS = {"good": "#0ca30c", "warning": "#fab219", "serious": "#ec835a", "critical": "#d03b3b"}
NEUTRAL = "#5b7486"
ACCENT = "#4bdcd5"
# Sequential blue on a dark surface: the step nearest the surface means "near zero".
SEQUENTIAL = [[0.0, "#0d366b"], [0.35, "#1c5cab"], [0.7, "#3987e5"], [1.0, "#86b6ef"]]
DIVERGING = [[0.0, "#e66767"], [0.5, "#383835"], [1.0, "#3987e5"]]
INK, PANEL, LINE, TEXT, TEXT_2, MUTED = "#081522", "#0d2030", "#263f52", "#eef8ff", "#b3c7d7", "#8faebf"

CSS = """<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Space+Grotesk:wght@500;600;700&display=swap');
:root{color-scheme:dark;--ink:#081522;--panel:#0d2030;--panel-2:#102437;--line:#263f52;--text:#eef8ff;--text-2:#b3c7d7;
--muted:#8faebf;--accent:#4bdcd5;--good:#0ca30c;--warning:#fab219;--serious:#ec835a;--critical:#d03b3b}
.stApp{background:var(--ink);color:var(--text);font-family:Inter,'Segoe UI',system-ui,sans-serif}
.block-container{padding:2.6rem 2.4rem 3rem;max-width:1560px}
header[data-testid=stHeader]{background:rgba(8,21,34,.94)}
section[data-testid=stSidebar]{background:var(--panel);border-right:1px solid var(--line)}
[data-testid=stSidebarNav] a{border-radius:7px}
[data-testid=stSidebarNav] a[aria-current=page]{background:#173749}
h1,h2,h3{font-family:'Space Grotesk',Inter,sans-serif!important;color:var(--text);letter-spacing:-.4px}
h1{font-weight:600!important;font-size:2.1rem!important;margin-bottom:0!important;padding-bottom:.35rem!important}
h2{font-size:1.5rem!important}h3{font-size:1.15rem!important;font-weight:600!important}
[data-testid=stMetric]{padding:14px 16px;border:1px solid var(--line);background:var(--panel);border-radius:10px}
[data-testid=stMetricLabel]{color:var(--text-2);font-size:.8rem}
[data-testid=stMetricValue]{font-variant-numeric:tabular-nums;font-weight:600;color:var(--text);font-size:1.6rem}
[data-testid=stCaptionContainer]{color:var(--text-2);line-height:1.6}
[data-testid=stForm]{border:1px solid var(--line);border-radius:12px;background:var(--panel);padding:22px}
button[kind=primary],button[kind=primaryFormSubmit]{background:var(--accent);color:var(--ink)!important;border:none;font-weight:650;min-height:42px}
button[kind=primary] p,button[kind=primaryFormSubmit] p{color:var(--ink)!important;font-weight:650}
button:focus-visible,a:focus-visible,[role=tab]:focus-visible,input:focus-visible{outline:3px solid #ffc773!important;outline-offset:3px}
[data-testid=stTabs] [role=tablist]{gap:26px;border-bottom:1px solid var(--line);margin-bottom:12px}
[data-testid=stTabs] [role=tab]{font-weight:600;padding:9px 0}
[data-testid=stDataFrame]{border:1px solid var(--line);border-radius:8px;overflow:hidden}
[data-testid=stAlert]{border-radius:8px}a{color:#7fe8e1}
.brand{display:flex;align-items:center;gap:10px;font-family:'Space Grotesk',sans-serif;font-size:27px;font-weight:600;color:var(--text);margin:2px 0 4px}
.brand svg{width:28px;height:32px;flex-shrink:0}
.brand-subtitle{color:var(--text-2);font-size:12px;line-height:1.5;margin:0 0 6px}
.sidebar-note{border-top:1px solid var(--line);margin-top:14px;padding-top:14px;color:var(--text-2);font-size:12px;line-height:1.65}
.sidebar-note strong{color:var(--text)}.sidebar-note small{display:block;margin-top:8px;font-size:11px;color:var(--muted)}
.masthead{display:flex;justify-content:space-between;align-items:center;gap:12px;border-bottom:1px solid var(--line);padding:0 0 10px;margin:0 0 16px;font-size:12px;color:var(--text-2)}
.masthead .status{display:inline-flex;align-items:center;gap:7px;color:#99ece4;white-space:nowrap}
.status-dot{width:7px;height:7px;border-radius:50%;background:var(--accent);display:inline-block}
.eyebrow{color:var(--accent);font-size:12px;font-weight:600;letter-spacing:.08em;text-transform:uppercase;margin:0 0 4px}
.page-description{color:var(--text-2);font-size:14.5px;line-height:1.6;max-width:820px;margin:2px 0 18px}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px;margin:4px 0 16px}
.tile{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:15px 17px 14px;min-height:108px}
.tile-label{color:var(--text-2);font-size:12.5px;display:block;margin-bottom:6px}
.tile-value{font-family:'Space Grotesk',sans-serif;font-size:28px;line-height:1.15;color:var(--text);font-variant-numeric:tabular-nums;white-space:nowrap}
.tile-detail{color:var(--muted);font-size:12px;display:block;margin-top:6px;line-height:1.45}
.tile.accent{border-color:#2f6b70;background:linear-gradient(180deg,#0f2b37,#0d2030)}.tile.accent .tile-value{color:#7fe8e1}
.callout{border-left:3px solid var(--accent);background:#0f2a36;border-radius:0 10px 10px 0;padding:13px 16px;margin:6px 0 16px;color:#d8ecf4;font-size:14px;line-height:1.6}
.callout b{color:var(--text)}.callout.warning{border-color:var(--warning);background:#2a2412}.callout.good{border-color:var(--good);background:#0f2a1a}
.callout.critical{border-color:var(--critical);background:#2c1418}
.badge{display:inline-flex;align-items:center;gap:6px;border:1px solid var(--line);border-radius:999px;padding:3px 10px;font-size:12px;color:var(--text-2);background:#0b1c2a;margin:0 6px 6px 0}
.badge.good{border-color:#1f6b2a;color:#9be59b}.badge.warning{border-color:#7a5a12;color:#ffd78a}.badge.critical{border-color:#7a2626;color:#ff9c9c}
.badge i{width:7px;height:7px;border-radius:50%;display:inline-block;background:currentColor}
.campaign-deck{border:1px solid #315267;border-radius:16px;background:#0e2435;overflow:hidden;margin:4px 0 10px}
.deck-heading{display:flex;align-items:flex-start;justify-content:space-between;padding:20px 24px 0;gap:18px}
.deck-heading h2{font-size:25px!important;font-weight:600;margin:0 0 4px;padding:0!important}
.deck-heading p{color:#b5ccdc;font-size:13px;margin:0;line-height:1.6;max-width:760px}
.network{padding:0 18px}.network svg{width:100%;height:auto;display:block;max-height:210px}
.network-note{display:flex;justify-content:space-between;gap:14px;flex-wrap:wrap;color:#a7c4d5;font-size:11.5px;padding:0 24px 14px}
.network-note b{color:#d8eaf3;font-weight:500}
.outcome-rail{display:grid;grid-template-columns:repeat(4,1fr);background:#0a1d2c;border-top:1px solid #2e4b60}
.outcome{padding:16px 22px;border-right:1px solid #294356}.outcome:last-child{border:0}
.outcome-label{color:var(--text-2);font-size:12px;display:block;margin-bottom:4px}
.outcome-value{font-family:'Space Grotesk',sans-serif;font-size:28px;line-height:1.2;color:var(--text);font-variant-numeric:tabular-nums;white-space:nowrap}
.outcome-value.accent{color:#7fe8e1}.outcome-detail{color:#a7c4d5;font-size:11.5px;display:block;margin-top:3px}
.resource-row{padding:12px 0;border-bottom:1px solid var(--line)}.resource-row:last-child{border-bottom:0}
.resource-label{display:flex;justify-content:space-between;gap:15px;font-size:13px;color:#d4e6f0;margin-bottom:7px}
.resource-label span:last-child{color:#b9cfdc;font-variant-numeric:tabular-nums}
.resource-track{height:6px;background:#233d50;border-radius:3px;overflow:hidden}.resource-fill{height:100%;background:var(--accent);border-radius:3px}
.resource-fill.caution{background:var(--warning)}.resource-note{font-size:11.5px;color:var(--text-2);margin-top:6px}
.offer-row{display:grid;grid-template-columns:1fr auto;gap:4px 18px;padding:12px 0;border-bottom:1px solid var(--line)}.offer-row:last-child{border-bottom:0}
.offer-title{color:var(--text);font-size:14px;font-weight:600}.offer-value{color:var(--text);font-size:15px;font-weight:600;font-variant-numeric:tabular-nums}
.offer-detail{font-size:12px;color:var(--text-2)}.offer-track{grid-column:1/-1;height:5px;background:#223e52;border-radius:3px;margin-top:4px}
.offer-track i{display:block;height:100%;border-radius:3px}
.profile{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px 18px;background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:16px 18px;margin-bottom:14px}
.profile div span{display:block;color:var(--muted);font-size:11.5px}.profile div b{color:var(--text);font-weight:600;font-size:14px;font-variant-numeric:tabular-nums}
.delivery{padding:16px 20px;border-left:3px solid var(--accent);border-radius:0 10px 10px 0;background:var(--panel);margin-bottom:10px}
.delivery.pending{border-color:var(--warning)}.delivery .delivery-status{color:#99e5df;font-size:12px}.delivery.pending .delivery-status{color:#ffd79b}
.delivery strong{color:var(--text);display:block;margin-top:4px}.delivery p{color:#b7cfde;margin:6px 0 0;font-size:14px;line-height:1.6}
.footer-note{color:var(--muted);font-size:12px;border-top:1px solid var(--line);padding-top:12px;margin-top:28px}
@media(max-width:1100px){.block-container{padding:2.6rem 1.4rem 3rem}.outcome{padding:14px}.outcome-value{font-size:24px}}
@media(max-width:850px){.block-container{padding:3.4rem 1rem 2rem}.deck-heading{padding:16px 16px 0;flex-wrap:wrap}.network{overflow-x:auto}
.network svg{min-width:620px;max-height:none}.outcome-rail{grid-template-columns:1fr 1fr}.outcome{border-bottom:1px solid #294356}
.masthead{flex-wrap:wrap}h1{font-size:1.8rem!important}.tile-value{font-size:24px}}
@media(prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
</style>"""


def money(value, decimals=0):
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "–"
    sign = "-" if value < 0 else ""
    return f"{sign}${abs(value):,.{decimals}f}"


def pct(value, decimals=0):
    return "–" if value is None else f"{value:.{decimals}%}"


def page_header(title, description=None, eyebrow=None):
    if eyebrow:
        st.markdown(f'<p class="eyebrow">{html.escape(eyebrow)}</p>', unsafe_allow_html=True)
    st.title(title)
    if description:
        st.markdown(f'<p class="page-description">{html.escape(description)}</p>', unsafe_allow_html=True)


def tiles(items):
    """Stat tiles from (label, value, detail[, accent]) tuples; values are pre-formatted strings."""
    cells = []
    for item in items:
        label, value, detail = item[:3]
        accent = len(item) > 3 and item[3]
        cells.append(
            f'<div class="tile {"accent" if accent else ""}"><span class="tile-label">{html.escape(label)}</span>'
            f'<div class="tile-value">{html.escape(value)}</div>'
            f'<span class="tile-detail">{html.escape(detail or "")}</span></div>'
        )
    st.markdown('<div class="tiles">' + "".join(cells) + "</div>", unsafe_allow_html=True)


def callout(text, tone="info"):
    """A highlighted finding. `text` may carry <b> tags; callers escape any data they interpolate."""
    st.markdown(f'<div class="callout {tone}">{text}</div>', unsafe_allow_html=True)


def badge(label, tone="neutral"):
    return f'<span class="badge {tone}"><i></i>{html.escape(label)}</span>'


def badges(items):
    st.markdown("".join(badge(label, tone) for label, tone in items), unsafe_allow_html=True)


def chart(fig, height=330, legend=True):
    fig.update_layout(
        height=height,
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, Segoe UI, sans-serif", color="#c9dce8", size=12),
        margin=dict(l=6, r=14, t=36 if legend else 14, b=12),
        colorway=SERIES,
        showlegend=legend,
        legend=dict(
            orientation="h", y=1.14, x=0, font=dict(size=11), traceorder="normal", bgcolor="rgba(0,0,0,0)"
        ),
        hoverlabel=dict(bgcolor="#102b3d", bordercolor="#2d4c61", font=dict(color=TEXT, size=12.5)),
        hovermode=fig.layout.hovermode or "closest",
        bargap=0.3,
    )
    fig.update_xaxes(gridcolor="#1a2f42", zerolinecolor="#2d4c61", showgrid=False, linecolor=LINE)
    fig.update_yaxes(gridcolor="#1a2f42", zerolinecolor="#2d4c61", linecolor=LINE)
    st.plotly_chart(
        fig,
        width="stretch",
        config={
            "displaylogo": False,
            "scrollZoom": False,
            "modeBarButtonsToRemove": ["lasso2d", "select2d", "autoScale2d"],
            "toImageButtonOptions": {"scale": 2},
        },
    )


def line(frame, x, ys, height=330, fill=False, names=None, fmt=",.1f"):
    fig = go.Figure()
    for i, y in enumerate(ys):
        name = (names or {}).get(y, y.replace("_", " ").capitalize())
        fig.add_trace(
            go.Scatter(
                x=frame[x],
                y=frame[y],
                name=name,
                mode="lines",
                line=dict(width=2, color=SERIES[i % len(SERIES)]),
                fill="tozeroy" if fill and i == 0 else None,
                fillcolor="rgba(57,135,229,.10)",
                hovertemplate=f"%{{y:{fmt}}}<extra>{name}</extra>",
            )
        )
    fig.update_layout(hovermode="x unified")
    chart(fig, height, legend=len(ys) > 1)


def bars(frame, x, ys, height=330, stack=False, names=None, horizontal=False, fmt=",.1f"):
    fig = go.Figure()
    for i, y in enumerate(ys):
        name = (names or {}).get(y, y.replace("_", " ").capitalize())
        category, value = ("y", "x") if horizontal else ("x", "y")
        fig.add_trace(
            go.Bar(
                **{category: frame[x], value: frame[y]},
                orientation="h" if horizontal else "v",
                name=name,
                marker=dict(color=SERIES[i % len(SERIES)], line=dict(width=0)),
                hovertemplate=f"%{{{category}}}<br>%{{{value}:{fmt}}}<extra>{name}</extra>",
            )
        )
    fig.update_layout(barmode="stack" if stack else "group")
    if not horizontal:
        fig.update_xaxes(type="category")
    chart(fig, height, legend=len(ys) > 1)


def corridor(capacity, zone_names):
    """Six-zone corridor schematic: rings show capacity-weighted forecast load."""
    cells = zone_summary(capacity)
    nodes, coords = [], []
    radius = 23
    circumference = 2 * math.pi * radius
    for i, (zone, row) in enumerate(cells.iterrows()):
        x = 66 + i * 154
        y = 104 if i % 2 == 0 else 78
        coords.append((x, y))
        color = STATUS["warning"] if row.utilization >= 0.75 else ACCENT
        name = html.escape(zone_names[zone])
        label = f"{row.utilization:.0%}"
        arc = max(0, min(1, row.utilization)) * circumference
        nodes.append(
            f"<g><title>{name}: {label} forecast load; {row.remaining_with_reserve:,.0f} trips free after reserve"
            f'</title><circle cx="{x}" cy="{y}" r="31" fill="#0e2435"/>'
            f'<circle cx="{x}" cy="{y}" r="{radius}" fill="#102b3d" stroke="#2d4c61" stroke-width="3"/>'
            f'<circle cx="{x}" cy="{y}" r="{radius}" fill="none" stroke="{color}" stroke-width="3" '
            f'stroke-linecap="round" stroke-dasharray="{arc:.2f} {circumference:.2f}" transform="rotate(-90 {x} {y})"/>'
            f'<text x="{x}" y="{y + 5}" fill="#eef8ff" font-size="14" font-weight="600" text-anchor="middle">{label}</text>'
            f'<text x="{x}" y="{y + 49}" fill="#eef8ff" font-size="16" font-weight="500" text-anchor="middle">{name}</text>'
            f'<text x="{x}" y="{y + 69}" fill="#b3cddd" font-size="12" text-anchor="middle">'
            f"{row.remaining_with_reserve:,.0f} trips free</text></g>"
        )
    path = "M" + " L".join(f"{x} {y}" for x, y in coords)
    return (
        '<svg viewBox="0 0 902 194" role="img" aria-label="Six simulated zones with capacity-weighted forecast '
        'load and remaining trips after the safety reserve"><defs><pattern id="corridor-grid" width="28" '
        'height="28" patternUnits="userSpaceOnUse"><path d="M28 0H0V28" fill="none" stroke="#294c61" '
        'stroke-width=".5"/></pattern></defs><rect x="0" y="18" width="902" height="160" fill="url(#corridor-grid)" '
        f'opacity=".35"/><path d="{path}" fill="none" stroke="#1e3e53" stroke-width="22" stroke-linejoin="round"/>'
        f'<path d="{path}" fill="none" stroke="#456980" stroke-width="1" stroke-dasharray="4 7"/>'
        f'<path d="{path}" fill="none" stroke="{ACCENT}" stroke-width="2" opacity=".75"/>'
        + "".join(nodes)
        + "</svg>"
    )


def campaign_deck(capacity, zone_names, combined, eligible, solver, certified):
    spend, budget = combined["spend"], combined["budget"]
    roi = combined["net_contribution"] / spend if spend else None
    reserve = capacity.reserve_trips.sum() / capacity.baseline_forecast.sum()
    outcomes = [
        ("Expected value", money(combined["objective_value"]), "30-day net + days 31-90 margin", True),
        (
            "Incentive spend",
            money(spend),
            f"{spend / budget:.0%} of {money(budget)} budget" if budget else "",
            False,
        ),
        (
            "Net ROI, 30 days",
            pct(roi) if roi is not None else "–",
            f"Floor {combined.get('min_roi', 0.15):.0%}",
            False,
        ),
        ("Customers contacted", f"{combined['contacts']:,}", f"of {eligible:,} eligible", False),
    ]
    rail = "".join(
        f'<div class="outcome"><span class="outcome-label">{label}</span>'
        f'<div class="outcome-value {"accent" if accent else ""}">{value}</div>'
        f'<span class="outcome-detail">{html.escape(detail)}</span></div>'
        for label, value, detail, accent in outcomes
    )
    tag = f"{solver} · {'certified optimal' if certified else 'optimal within 0.01% gap'}"
    st.markdown(
        '<section class="campaign-deck" aria-label="October campaign plan"><div class="deck-heading"><div>'
        "<h2>October campaign plan</h2><p>One optimized allocation of eight offers across every eligible "
        "customer, within budget, contact, ROI, points, inventory and roadway-capacity guardrails.</p></div>"
        f"{badge(tag, 'good')}</div>"
        f'<div class="network">{corridor(capacity, zone_names)}</div>'
        '<div class="network-note"><span><b>Ring:</b> forecast load including the campaign, as a share of '
        f"capacity</span><span><b>Trips free:</b> headroom after the {reserve:.0%} demand reserve</span></div>"
        f'<div class="outcome-rail">{rail}</div></section>',
        unsafe_allow_html=True,
    )


def resource_ledger(items, note=None):
    rows = []
    for label, used, limit, value_label, detail in items:
        share = used / limit if limit else 0
        rows.append(
            f'<div class="resource-row"><div class="resource-label"><span>{html.escape(label)}</span>'
            f"<span>{html.escape(value_label)}</span></div>"
            f'<div class="resource-track" role="meter" aria-label="{html.escape(label)}" aria-valuenow="{used}" '
            f'aria-valuemin="0" aria-valuemax="{max(limit, 1)}"><div class="resource-fill '
            f'{"caution" if share >= 0.9 else ""}" style="width:{min(100, max(0, share * 100)):.1f}%"></div></div>'
            f'<div class="resource-note">{html.escape(detail)}</div></div>'
        )
    content = '<div class="resource-ledger">' + "".join(rows) + "</div>"
    if note:
        content += f'<div class="callout good">{html.escape(note)}</div>'
    st.markdown(content, unsafe_allow_html=True)


def offer_mix(frame, offer_names, offer_order):
    """One row per offer in catalogue order: contacts, value and a share bar in the offer's slot colour."""
    total = len(frame)
    grouped = frame.groupby("offer_id").agg(
        contacts=("customer_id", "size"), value=("objective_value", "sum"), spend=("cost", "sum")
    )
    rows = []
    for i, offer in enumerate(offer_order):
        if offer not in grouped.index:
            continue
        row = grouped.loc[offer]
        share = row.contacts / total if total else 0
        rows.append(
            f'<div class="offer-row"><span class="offer-title">{html.escape(offer_names[offer])}</span>'
            f'<span class="offer-value">{int(row.contacts):,} contacts</span>'
            f'<span class="offer-detail">{money(row.value)} expected value · {money(row.spend)} spend</span>'
            f'<span class="offer-detail">{share:.0%} of contacts</span>'
            f'<div class="offer-track"><i style="width:{share * 100:.1f}%;background:{SERIES[i % len(SERIES)]}">'
            "</i></div></div>"
        )
    if not rows:
        rows.append(
            '<p class="page-description">No contacts under these limits. Relax a guardrail and solve again.</p>'
        )
    st.markdown("".join(rows), unsafe_allow_html=True)


def profile_card(fields):
    cells = "".join(
        f"<div><span>{html.escape(k)}</span><b>{html.escape(str(v))}</b></div>" for k, v in fields
    )
    st.markdown(f'<div class="profile">{cells}</div>', unsafe_allow_html=True)


def footer():
    st.markdown(
        '<div class="footer-note">Synthetic portfolio system inspired by electronic toll-road decisions. No '
        "affiliation with 407 ETR. No real customer data, toll rates or campaign rules. Figures are simulation "
        "outputs.</div>",
        unsafe_allow_html=True,
    )
