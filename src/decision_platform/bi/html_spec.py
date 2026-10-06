"""HTML/CSS panels for the Power BI report, rendered by the HTML Content custom visual.

Each panel is a DAX measure that returns semantic HTML with class names. One shared
stylesheet (set on every HTML visual) does all of the styling, so a measure never
carries layout or colour decisions of its own beyond data-driven widths and fills.

Rules that keep the markup valid inside DAX and PBIR:
* HTML attributes use single quotes, so the DAX string literals never need escaping.
* The stylesheet contains no quotes at all: PBIR stores it as a single-quoted literal.
* Every number that drives a width is clamped to 0-100 before it reaches CSS.
"""

from __future__ import annotations

# AppSource "HTML Content" by Daniel Marsh-Patrick (github.com/dm-p/powerbi-visuals-html-content).
HTML_VISUAL = "htmlContent443BE3AD55E043BF878BED274D3A6855"

BLUE, ORANGE, AQUA, YELLOW = "#3987e5", "#d95926", "#199e70", "#c98500"
RED, GREY, TEAL = "#e66767", "#5b7486", "#4bdcd5"

CSS = " ".join(
    """
body{margin:0}
.w{font-family:Segoe UI,sans-serif;color:#eef8ff;font-size:12px;line-height:1.45}
.h{font-size:12px;color:#b3c7d7;margin:0 0 8px 0;font-weight:600;letter-spacing:.02em}
.eyebrow{color:#4bdcd5;font-size:10.5px;letter-spacing:.14em;text-transform:uppercase;font-weight:700}
.hero{display:flex;gap:18px;background:linear-gradient(135deg,#123349,#0b1c2a 70%);border:1px solid #2d4c61;border-radius:14px;padding:11px 18px}
.hero .left{flex:1.05}
.headline{font-size:21px;font-weight:600;margin:4px 0 4px 0;letter-spacing:-.01em}
.sub{color:#b3c7d7;font-size:11.5px}
.kpis{flex:1.6;display:grid;grid-template-columns:repeat(4,1fr);gap:10px}
.kpi{background:rgba(13,32,48,.85);border:1px solid #263f52;border-radius:10px;padding:9px 11px}
.kpi .l{color:#b3c7d7;font-size:10.5px}
.kpi .v{font-size:21px;font-weight:600;font-variant-numeric:tabular-nums;margin-top:2px}
.kpi .d{color:#8faebf;font-size:10px;margin-top:2px}
.kpi.accent{border-color:#2f6b70;background:linear-gradient(180deg,#0f2f3a,#0d2030)}
.kpi.accent .v{color:#7fe8e1}
.badge{display:inline-block;border-radius:999px;padding:2px 9px;font-size:10px;margin:6px 6px 0 0;border:1px solid #1f6b2a;color:#9be59b;background:#0b2016}
.badge.blue{border-color:#2d4c61;color:#b7d9e5;background:#0b1c2a}
.cards{display:grid;grid-template-columns:repeat(5,1fr);gap:6px}
.card{background:#102437;border:1px solid #263f52;border-radius:10px;padding:5px 10px 6px}
.card.idle{opacity:.55}
.top{display:flex;justify-content:space-between;align-items:flex-start;gap:6px}
.card .n{font-size:12px;font-weight:600;white-space:nowrap}
.card .t{color:#8faebf;font-size:10px}
.big{font-size:16px;font-weight:600;font-variant-numeric:tabular-nums;white-space:nowrap}
.r{display:flex;justify-content:space-between;font-size:11px;color:#d4e6f0;margin-top:2px}
.r b{font-variant-numeric:tabular-nums;font-weight:600}
.track{height:5px;background:#1d3448;border-radius:3px;margin-top:5px;overflow:hidden}
.fill{height:5px;border-radius:3px}
.dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:6px}
table.t{width:100%;border-collapse:collapse;font-size:11px}
table.t th{color:#8faebf;font-weight:600;text-align:left;padding:3px 6px;border-bottom:1px solid #263f52}
table.t td{padding:3px 6px;border-bottom:1px solid #18304a}
table.t td .track{margin-top:0}
table.t tr.hl td{background:#0f2b3d;color:#eef8ff;font-weight:600}
.num{text-align:right;font-variant-numeric:tabular-nums}
.lane{position:relative;height:14px;background:#0b1c2a;border-radius:4px}
.zero{position:absolute;top:0;bottom:0;width:1px;background:#5b7486}
.ci{position:absolute;top:6px;height:2px;background:#8faebf;border-radius:1px}
.pt{position:absolute;top:3px;width:8px;height:8px;border-radius:50%;margin-left:-4px}
.fr{display:grid;grid-template-columns:150px 1fr 64px;gap:8px;align-items:center;margin:2px 0}
.grid{display:grid;gap:4px;font-size:11px}
.gh{color:#8faebf;font-weight:600;text-align:center;padding:2px}
.gz{color:#d4e6f0;padding:0 2px;align-self:center}
.cell{border-radius:6px;padding:3px 4px;text-align:center;font-weight:600;font-variant-numeric:tabular-nums;line-height:1.25}
.cell small{font-weight:400;color:#d4e6f0;font-size:9.5px;margin-left:6px}
.ok{color:#9be59b;font-weight:700}
.no{color:#ff9c9c;font-weight:700}
.note{color:#8faebf;font-size:10px;margin-top:4px}
""".split()
)


def _f(expression: str, fmt: str) -> str:
    """FORMAT that never prints blank: a missing value reads as an em dash."""
    return f'IF(ISBLANK({expression}), "—", FORMAT({expression}, "{fmt}"))'


def _kpi(label: str, value: str, detail: str, accent: bool = False) -> str:
    klass = "kpi accent" if accent else "kpi"
    return (
        f"\"<div class='{klass}'><div class='l'>{label}</div><div class='v'>\" & {value} & "
        f'"</div><div class=\'d\'>" & {detail} & "</div></div>"'
    )


def _pct_width(expression: str) -> str:
    """A 0-100 integer for a CSS width, clamped."""
    return f'FORMAT(MAX(0, MIN(100, ({expression}) * 100)), "0")'


HERO = "\n".join(
    [
        "VAR vShare = DIVIDE([Optimized true value], [Value ceiling])",
        "VAR vCertified = SELECTEDVALUE(plan_summary[proven_optimal])",
        "RETURN",
        "\"<div class='w'><div class='hero'><div class='left'>\"",
        "    & \"<div class='eyebrow'>October 2025 · campaign plan</div>\"",
        '    & "<div class=\'headline\'>" & FORMAT([Contacts], "#,0") & " customers · " '
        '& FORMAT([Incentive spend], "$#,0") & " of incentives</div>"',
        '    & "<div class=\'sub\'>One mixed-integer plan across " & FORMAT([Decision variables], "#,0") '
        '& " customer-offer decisions, inside budget, contact, ROI, points, inventory and 407 free-flow capacity '
        'guardrails.</div>"',
        '    & "<span class=\'badge\'>" & IF(vCertified, "✓ Proven optimal", "Within solver gap") & "</span>"',
        "    & \"<span class='badge blue'>10-arm blocked trial</span><span class='badge blue'>Synthetic data</span>\"",
        "    & \"</div><div class='kpis'>\"",
        "    & "
        + _kpi(
            "Expected value",
            _f("[Expected value]", "$#,0"),
            'FORMAT([Value per incentive dollar], "0.0") & "x the incentive spend"',
            True,
        ),
        "    & "
        + _kpi(
            "True value · simulation",
            _f("[Optimized true value]", "$#,0"),
            'FORMAT(vShare, "0%") & " of the perfect-knowledge ceiling"',
        ),
        "    & " + _kpi("Net ROI · 30 days", _f("[Net ROI]", "0%"), '"floor 15%"'),
        "    & "
        + _kpi(
            "Rush-hour trips / workday",
            _f("[Rush-hour trips per workday]", "+#,0;-#,0"),
            '"moved onto the 407"',
        ),
        '    & "</div></div></div>"',
    ]
)

OFFER_CARDS = "\n".join(
    [
        "VAR vMax = MAXX(ALL(dim_offer), [Expected value])",
        "RETURN",
        "\"<div class='w'><div class='h'>Offers in the plan · contacts, expected value and spend</div><div class='cards'>\"",
        "    & CONCATENATEX(",
        "        ALL(dim_offer),",
        '        "<div class=\'card" & IF(COALESCE([Contacts], 0) = 0, " idle", "") & "\'><div class=\'top\'><div>'
        "<div class='n'><span class='dot' style='background:\" & dim_offer[offer_fill] "
        '& "\'></span>" & dim_offer[offer_name] & "</div>"',
        '            & "<div class=\'t\'>" & dim_offer[offer_type] & " · " & IF(dim_offer[period] = "Mixed", "any period", "fills " & dim_offer[period]) & "</div></div>"',
        '            & "<div class=\'big\'>" & FORMAT(COALESCE([Expected value], 0), "$#,0") & "</div></div>"',
        '            & "<div class=\'t\'>" & FORMAT(COALESCE([Contacts], 0), "#,0") & " contacts · " '
        '& FORMAT(COALESCE([Incentive spend], 0), "$#,0") & " spend" & IF(COALESCE([Contacts], 0) = 0, '
        '" · not worth a contact under these limits", "") & "</div>"',
        "            & \"<div class='track'><div class='fill' style='width:\" & "
        + _pct_width("DIVIDE(COALESCE([Expected value], 0), vMax)")
        + ' & "%;background:" & dim_offer[offer_fill] & "\'></div></div></div>",',
        '        "", dim_offer[offer_order], ASC)',
        '    & "</div></div>"',
    ]
)

GUARDRAILS = "\n".join(
    [
        "VAR vTop = TOPN(1, guardrails, guardrails[shadow_price], DESC)",
        "RETURN",
        "\"<div class='w'><div class='h'>Binding guardrails · what one more unit is worth (LP duals)</div>\"",
        "    & \"<table class='t'><tr><th>Guardrail</th><th class='num'>Limit</th><th class='num'>Value of +1</th></tr>\"",
        "    & CONCATENATEX(",
        "        guardrails,",
        '        "<tr><td>" & guardrails[constraint_label] & "</td><td class=\'num\'>" & FORMAT(guardrails[limit], "#,0") '
        '& "</td><td class=\'num\'>" & FORMAT(guardrails[shadow_price], "$#,0.00") & "</td></tr>",',
        '        "", guardrails[shadow_price], DESC)',
        '    & "</table><div class=\'note\'>Relax first: <b>" & MAXX(vTop, guardrails[constraint_label]) & "</b>, worth " '
        '& FORMAT(MAXX(vTop, guardrails[shadow_price]), "$#,0.00") & " per extra unit. Guardrails that do not bind '
        'are worth nothing at the margin and are not listed.</div></div>"',
    ]
)

LEADERBOARD = "\n".join(
    [
        "VAR vCeiling = [Value ceiling]",
        "RETURN",
        "\"<div class='w'><div class='h'>Targeting approaches scored against the simulator's truth</div>\"",
        "    & \"<table class='t'><tr><th>Approach</th><th class='num'>True value</th><th></th>"
        "<th class='num'>Ceiling</th></tr>\"",
        "    & CONCATENATEX(",
        "        ALL(policy_comparison),",
        '        "<tr" & IF(policy_comparison[policy] = "Optimized (MIP)", " class=\'hl\'", "") & "><td>" '
        '& policy_comparison[policy] & "</td><td class=\'num\'>" & FORMAT(policy_comparison[true_value], "$#,0") '
        "& \"</td><td style='width:34%'><div class='track'><div class='fill' style='width:\" & "
        + _pct_width("DIVIDE(policy_comparison[true_value], vCeiling)")
        + ' & "%;background:" & SWITCH(TRUE(), policy_comparison[policy] = "Optimized (MIP)", "'
        + BLUE
        + '", LEFT(policy_comparison[policy], 6) = "Oracle", "#86b6ef", "'
        + GREY
        + '") & "\'></div></div></td><td class=\'num\'>" & FORMAT(DIVIDE(policy_comparison[true_value], vCeiling), "0%") '
        '& "</td></tr>",',
        '        "", policy_comparison[true_value], DESC)',
        '    & "</table></div>"',
    ]
)

FOREST = "\n".join(
    [
        "VAR vLow = MINX(ALL(experiment_effects), experiment_effects[value_low])",
        "VAR vHigh = MAXX(ALL(experiment_effects), experiment_effects[value_high])",
        "VAR vSpan = MAX(vHigh - vLow, 0.01)",
        "VAR vZero = " + _pct_width("DIVIDE(0 - vLow, vSpan)"),
        "RETURN",
        "\"<div class='w'><div class='h'>30-day net contribution per randomised customer · CUPED, Bonferroni 95%</div>\"",
        "    & CONCATENATEX(",
        "        ALL(experiment_effects),",
        "        \"<div class='fr'><span>\" & RELATED(dim_offer[offer_name]) & \"</span><div class='lane'>\"",
        "            & \"<div class='zero' style='left:\" & vZero & \"%'></div>\"",
        "            & \"<div class='ci' style='left:\" & "
        + _pct_width("DIVIDE(experiment_effects[value_low] - vLow, vSpan)")
        + ' & "%;width:" & '
        + _pct_width("DIVIDE(experiment_effects[value_high] - experiment_effects[value_low], vSpan)")
        + ' & "%\'></div>"',
        "            & \"<div class='pt' style='left:\" & "
        + _pct_width("DIVIDE(experiment_effects[value_effect] - vLow, vSpan)")
        + ' & "%;background:" & IF(experiment_effects[value_effect] < 0, "'
        + RED
        + '", "'
        + BLUE
        + '") & "\'></div></div><span class=\'num\'>" & FORMAT(experiment_effects[value_effect], "+$0.00;-$0.00") '
        '& "</span></div>",',
        '        "", experiment_effects[value_effect], DESC)',
        "    & \"<div class='note'>Red: loses money on the average randomised customer. The plan still uses an offer "
        'where the models find customers it moves.</div></div>"',
    ]
)

CAPACITY = "\n".join(
    [
        "VAR vColumns = COUNTROWS(VALUES(dim_period[period]))",
        "RETURN",
        "\"<div class='w'><div class='h'>Load by zone and period, with the campaign (share of free-flow capacity)</div>"
        "<div class='grid' style='grid-template-columns:96px repeat(\" & vColumns & \",1fr)'><div></div>\"",
        '    & CONCATENATEX(VALUES(dim_period[period]), "<div class=\'gh\'>" & dim_period[period] & "</div>", "", '
        "CALCULATE(MAX(dim_period[period_order])), ASC)",
        "    & CONCATENATEX(",
        "        VALUES(dim_zone[zone_name]),",
        '        "<div class=\'gz\'>" & dim_zone[zone_name] & "</div>" & CONCATENATEX(',
        "            VALUES(dim_period[period]),",
        "            VAR vLoad = CALCULATE([Load])",
        '            VAR vTone = IF(vLoad >= 0.8, "201,133,0", "57,135,229")',
        '            RETURN "<div class=\'cell\' style=\'background:rgba(" & vTone & "," '
        '& FORMAT(MAX(0.12, MIN(0.95, vLoad)), "0.00") & ")\'>" & FORMAT(vLoad, "0%") & "<small>" '
        '& FORMAT(CALCULATE([Free after campaign]), "#,0") & " free</small></div>",',
        '            "", CALCULATE(MAX(dim_period[period_order])), ASC),',
        '        "", CALCULATE(MAX(dim_zone[zone_order])), ASC)',
        "    & \"</div><div class='note'>Amber: 80% of capacity or more, where rush-hour offers are held back.</div></div>\"",
    ]
)

SEGMENTS = "\n".join(
    [
        "\"<div class='w'><div class='h'>Segments · risk, value and what the plan does with them</div>\"",
        "    & \"<table class='t'><tr><th>Segment</th><th class='num'>Customers</th><th class='num'>Propensity</th>"
        "<th class='num'>Inactivity</th><th class='num'>Best-offer value</th><th>In plan</th></tr>\"",
        "    & CONCATENATEX(",
        "        VALUES(customer_segments[rfm_segment]),",
        '        "<tr><td>" & customer_segments[rfm_segment] & "</td><td class=\'num\'>" & FORMAT([Customers], "#,0") '
        '& "</td><td class=\'num\'>" & FORMAT([Mean travel propensity], "0%") & "</td><td class=\'num\'>" '
        "& "
        + _f("[Mean inactivity risk]", "0%")
        + ' & "</td><td class=\'num\'>" & FORMAT([Mean best-offer value], "$0.00") '
        "& \"</td><td style='width:24%'><div class='track'><div class='fill' style='width:\" & "
        + _pct_width("[Share in plan]")
        + ' & "%;background:'
        + TEAL
        + "'></div></div></td></tr>\",",
        '        "", CALCULATE(MAX(customer_segments[segment_order])), ASC)',
        '    & "</table></div>"',
    ]
)

SCORECARD = "\n".join(
    [
        "\"<div class='w'><div class='h'>Release acceptance gate</div><table class='t'>\"",
        "    & CONCATENATEX(",
        "        quality_gate,",
        '        "<tr><td>" & IF(quality_gate[passed], "<span class=\'ok\'>✓</span>", "<span class=\'no\'>✕</span>") '
        '& " " & quality_gate[check_name] & "</td><td class=\'note\'>" & quality_gate[criteria] & "</td></tr>",',
        '        "")',
        "    & \"</table><div class='h' style='margin-top:10px'>Customer models · July 2025 test fold</div>"
        "<table class='t'><tr><th>Model</th><th>Champion</th><th class='num'>AUC</th><th class='num'>Brier</th>"
        "<th class='num'>ECE</th></tr>\"",
        "    & CONCATENATEX(",
        "        model_quality,",
        '        "<tr><td>" & model_quality[model] & "</td><td>" & model_quality[champion] & "</td><td class=\'num\'>" '
        '& FORMAT(model_quality[auc], "0.000") & "</td><td class=\'num\'>" & FORMAT(model_quality[brier], "0.000") '
        '& "</td><td class=\'num\'>" & FORMAT(model_quality[ece], "0.000") & "</td></tr>",',
        '        "")',
        '    & "</table></div>"',
    ]
)

NARRATIVE = (
    "\"<div class='w'><div class='eyebrow'>In plain language</div><div style='font-size:14px;line-height:1.55;margin-top:8px;"
    'color:#d8ecf4\'>" & [Executive summary] & "</div></div>"'
)

HTML_MEASURES: list[tuple[str, str, str, str, str]] = [
    ("HTML Hero", HERO, "", "11 HTML panels", "Command-centre banner with the plan's headline KPIs."),
    (
        "HTML Offer cards",
        OFFER_CARDS,
        "",
        "11 HTML panels",
        "One card per offer: contacts, expected value, spend.",
    ),
    ("HTML Guardrails", GUARDRAILS, "", "11 HTML panels", "Binding guardrails with their LP shadow prices."),
    (
        "HTML Policy leaderboard",
        LEADERBOARD,
        "",
        "11 HTML panels",
        "Targeting approaches ranked by true value.",
    ),
    ("HTML Experiment forest", FOREST, "", "11 HTML panels", "Trial effects with Bonferroni intervals."),
    ("HTML Capacity grid", CAPACITY, "", "11 HTML panels", "Zone x period load heat grid."),
    ("HTML Segments", SEGMENTS, "", "11 HTML panels", "Segment table with plan share bars."),
    ("HTML Scorecard", SCORECARD, "", "11 HTML panels", "Acceptance gate and model quality."),
    ("HTML Narrative", NARRATIVE, "", "11 HTML panels", "The executive summary as a styled paragraph."),
]
