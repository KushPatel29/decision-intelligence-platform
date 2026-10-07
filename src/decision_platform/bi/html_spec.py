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
.strip{display:grid;gap:10px}
.kc{position:relative;background:linear-gradient(180deg,#112840,#0d2030);border:1px solid #263f52;border-radius:12px;padding:8px 12px 7px 15px;overflow:hidden;min-width:0}
.kc.accent{border-color:#2f6b70;background:linear-gradient(180deg,#0f2f3a,#0d2030)}
.rail{position:absolute;left:0;top:9px;bottom:9px;width:3px;border-radius:0 3px 3px 0;background:#2d4c61}
.kc.accent .rail{background:#4bdcd5}
.kc .l{display:flex;justify-content:space-between;align-items:center;gap:6px;color:#b3c7d7;font-size:10.5px;letter-spacing:.02em;white-space:nowrap}
.kc .v{font-size:24px;font-weight:600;font-variant-numeric:tabular-nums;letter-spacing:-.01em;line-height:1.2;margin-top:2px;white-space:nowrap}
.kc.accent .v{color:#7fe8e1}
.kc .d{color:#8faebf;font-size:10px;margin-top:4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.pill{font-size:9.5px;border-radius:999px;padding:1px 7px;font-weight:600;white-space:nowrap}
.pill.good{color:#9be59b;background:#0b2016;border:1px solid #1f6b2a}
.pill.warn{color:#ffd27a;background:#2a1f05;border:1px solid #6b5212}
.pill.info{color:#b7d9e5;background:#0b1c2a;border:1px solid #2d4c61}
.mv{position:relative;height:6px;background:#1d3448;border-radius:3px;margin-top:6px}
.mv i{position:absolute;left:0;top:0;bottom:0;border-radius:3px}
.mv b{position:absolute;top:-3px;bottom:-3px;width:2px;margin-left:-1px;background:#eef8ff;border-radius:1px}
.seg{display:flex;gap:2px;height:6px;border-radius:3px;overflow:hidden;margin-top:6px;background:#1d3448}
.seg i{height:6px}
.sp{display:flex;align-items:flex-end;gap:2px;height:20px;margin-top:3px}
.sp i{flex:1;background:#3987e5;border-radius:2px 2px 0 0;min-height:2px;opacity:.9}
.dots{display:flex;gap:4px;margin-top:6px;flex-wrap:wrap}
.dots i{width:9px;height:9px;border-radius:50%;background:#1d3448;border:1px solid #2d4c61}
.dots i.on{background:#3fb96b;border-color:#3fb96b}
.lg{margin-right:9px}
.lg i{display:inline-block;width:7px;height:7px;border-radius:2px;margin-right:4px}
""".split()
)


def _f(expression: str, fmt: str) -> str:
    """FORMAT that never prints blank: a missing value reads as an em dash."""
    return f'IF(ISBLANK({expression}), "—", FORMAT({expression}, "{fmt}"))'


def _kpi(label: str, value: str, detail: str, accent: bool = False, micro: str = '""') -> str:
    klass = "kpi accent" if accent else "kpi"
    return (
        f"\"<div class='{klass}'><div class='l'>{label}</div><div class='v'>\" & {value} & \"</div>\" & {micro} & "
        f'"<div class=\'d\'>" & {detail} & "</div></div>"'
    )


def _pct_width(expression: str) -> str:
    """A 0-100 integer for a CSS width, clamped."""
    return f'FORMAT(MAX(0, MIN(100, ({expression}) * 100)), "0")'


# --------------------------------------------------------------------------------------------
# KPI strips: one HTML visual per page replaces its row of image tiles. Each card is a label,
# a value, a status pill that says in words what its colour says, a micro-visual that puts the
# value against its limit, target, history or parts, and one line of context.
# --------------------------------------------------------------------------------------------

AMBER, GOOD = "#c98500", "#3fb96b"


def _q(text: str) -> str:
    """A DAX string literal (no double quotes are ever needed inside the markup)."""
    return '"' + text + '"'


def _pill(condition: str, good_text: str, bad_text: str) -> str:
    return (
        f"IF({condition}, \"<span class='pill good'>{good_text}</span>\", "
        f"\"<span class='pill warn'>{bad_text}</span>\")"
    )


def _info_pill(text_expr: str) -> str:
    return f'"<span class=\'pill info\'>" & {text_expr} & "</span>"'


def _progress(ratio: str, warn_at: float | None = None, marker: float | None = None) -> str:
    """A bar filled to `ratio` of its track; amber at or above `warn_at`; a tick at `marker`."""
    colour = f'IF(({ratio}) >= {warn_at}, "{AMBER}", "{BLUE}")' if warn_at is not None else f'"{BLUE}"'
    tick = f"<b style='left:{marker * 100:.0f}%'></b>" if marker is not None else ""
    return f'"<div class=\'mv\'><i style=\'width:" & {_pct_width(ratio)} & "%;background:" & {colour} & "\'></i>{tick}</div>"'


def _bullet(value: str, target: str, above_is_good: bool = True) -> str:
    """Value against a target on one scale: the bar is the value, the tick is the target."""
    scale = f"MAX({value}, {target}) * 1.12"
    ok = f"({value}) >= ({target})" if above_is_good else f"({value}) <= ({target})"
    return (
        f'"<div class=\'mv\'><i style=\'width:" & {_pct_width(f"DIVIDE({value}, {scale})")} & "%;background:" & '
        f'IF({ok}, "{BLUE}", "{AMBER}") & "\'></i><b style=\'left:" & '
        f'{_pct_width(f"DIVIDE({target}, {scale})")} & "%\'></b></div>"'
    )


def _parts(parts: list[tuple[str, str]]) -> str:
    """A stacked bar of non-negative parts, each in its own validated slot colour."""
    total = " + ".join(f"MAX(0, {expr})" for expr, _ in parts)
    segments = " & ".join(
        f'"<i style=\'width:" & {_pct_width(f"DIVIDE(MAX(0, {expr}), {total})")} & "%;background:{colour}\'></i>"'
        for expr, colour in parts
    )
    return f'"<div class=\'seg\'>" & {segments} & "</div>"'


def _key(parts: list[tuple[str, str, str]]) -> str:
    """Detail line that keys a stacked bar: a colour chip, a label and a formatted value per part."""
    return " & ".join(
        f"\"<span class='lg'><i style='background:{colour}'></i>{label} \" & {value}" + ' & "</span>"'
        for label, value, colour in parts
    )


def _columns(table: str, order: str, value: str, label: str) -> str:
    """Mini column chart: one bar per member of `order`, height relative to the tallest."""
    return (
        f"\"<div class='sp'>\" & CONCATENATEX(VALUES({order}), "
        f"VAR vMax = MAXX(ALL({order}), CALCULATE({value})) "
        f'RETURN "<i title=\'" & CALCULATE(MAX({label})) & "\' style=\'height:" & '
        f'{_pct_width(f"DIVIDE(CALCULATE({value}), vMax)")} & "%\'></i>", "", {order}, ASC) & "</div>"'
    )


def _range(low: str, point: str, high: str, lo: str, hi: str) -> str:
    """An interval [low, high] with its point estimate, on the scale [lo, hi]."""
    span = f"(({hi}) - ({lo}))"
    return (
        f'"<div class=\'mv\'><i style=\'left:" & {_pct_width(f"DIVIDE(({low}) - ({lo}), {span})")} & "%;width:" & '
        f"{_pct_width(f'DIVIDE(({high}) - ({low}), {span})')} & \"%;background:#2f5f8f'></i><b style='left:\" & "
        f'{_pct_width(f"DIVIDE(({point}) - ({lo}), {span})")} & "%\'></b></div>"'
    )


def _dots(on: str, total: str) -> str:
    return (
        f"\"<div class='dots'>\" & CONCATENATEX(GENERATESERIES(1, MAX(1, {total})), "
        f'IF([Value] <= {on}, "<i class=\'on\'></i>", "<i></i>"), "", [Value], ASC) & "</div>"'
    )


def _card(
    label: str, value: str, detail: str, micro: str = '""', pill: str = '""', accent: bool = False
) -> str:
    klass = "kc accent" if accent else "kc"
    return (
        f"\"<div class='{klass}'><span class='rail'></span><div class='l'><span>{label}</span>\" & {pill} & "
        f'"</div><div class=\'v\'>" & {value} & "</div>" & {micro} & "<div class=\'d\'>" & {detail} & '
        '"</div></div>"'
    )


def _strip(cards: list[str]) -> str:
    head = f"\"<div class='w'><div class='strip' style='grid-template-columns:repeat({len(cards)},1fr)'>\""
    return "\n    & ".join([head, *cards, '"</div></div>"'])


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
            _parts(
                [
                    ("[Expected 30-day net]", BLUE),
                    ("[Expected later value]", AQUA),
                    ("[Relief value]", YELLOW),
                ]
            ),
        ),
        "    & "
        + _kpi(
            "True value · simulation",
            _f("[Optimized true value]", "$#,0"),
            'FORMAT(vShare, "0%") & " of the perfect-knowledge ceiling"',
            micro=_progress("vShare"),
        ),
        "    & "
        + _kpi(
            "Net ROI · 30 days",
            _f("[Net ROI]", "0%"),
            '"floor " & FORMAT([ROI floor], "0%")',
            micro=_bullet("[Net ROI]", "[ROI floor]"),
        ),
        "    & "
        + _kpi(
            "Rush-hour trips / workday",
            _f("[Rush-hour trips per workday]", "+#,0;-#,0"),
            '"moved onto the 407, worth " & FORMAT([Relief value], "$#,0")',
            micro=_progress("DIVIDE([Relief value], [Expected value])"),
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

KPI_STRIPS: dict[str, tuple[str, list[str]]] = {
    "p1_plan": (
        "Plan KPIs: expected value with its parts, spend against budget, contacts against the limit, and net "
        "ROI against its floor.",
        [
            _card(
                "Expected value",
                _f("[Expected value]", "$#,0"),
                _key(
                    [
                        ("30-day", 'FORMAT([Expected 30-day net], "$#,0")', BLUE),
                        ("days 31-90", 'FORMAT([Expected later value], "$#,0")', AQUA),
                        ("relief", 'FORMAT([Relief value], "$#,0")', YELLOW),
                    ]
                ),
                _parts(
                    [
                        ("[Expected 30-day net]", BLUE),
                        ("[Expected later value]", AQUA),
                        ("[Relief value]", YELLOW),
                    ]
                ),
                _info_pill('FORMAT([Value per incentive dollar], "0.0") & "x spend"'),
                accent=True,
            ),
            _card(
                "Incentive spend",
                _f("[Incentive spend]", "$#,0"),
                '"of the " & FORMAT([Budget], "$#,0") & " budget"',
                _progress("DIVIDE([Incentive spend], [Budget])"),
                _info_pill('FORMAT([Budget used], "0%") & " used"'),
            ),
            _card(
                "Contacts",
                _f("[Contacts]", "#,0"),
                'FORMAT(DIVIDE([Contacts], [Eligible customers]), "0%") & " of " & FORMAT([Eligible customers], "#,0") '
                '& " eligible customers"',
                _progress("DIVIDE([Contacts], [Contact limit])"),
                _info_pill('"limit " & FORMAT([Contact limit], "#,0")'),
            ),
            _card(
                "Net ROI · 30 days",
                _f("[Net ROI]", "0%"),
                '"30-day net " & FORMAT([Expected 30-day net], "$#,0") & " on " & FORMAT([Incentive spend], "$#,0")',
                _bullet("[Net ROI]", "[ROI floor]"),
                _pill("[Net ROI] >= [ROI floor]", "✓ above floor", "✕ below floor"),
            ),
        ],
    ),
    "p2_contacts": (
        "Contact KPIs: extra trips by travel period, points against the cap, estimate uncertainty and "
        "congestion relief.",
        [
            _card(
                "Extra trips",
                _f("[Extra trips]", "#,0"),
                _key(
                    [
                        ("peak", 'FORMAT([Extra peak trips], "+#,0;-#,0")', BLUE),
                        ("off-peak", 'FORMAT([Extra off-peak trips], "+#,0;-#,0")', ORANGE),
                        ("weekend", 'FORMAT([Extra weekend trips], "+#,0;-#,0")', AQUA),
                    ]
                ),
                _parts(
                    [
                        ("[Extra peak trips]", BLUE),
                        ("[Extra off-peak trips]", ORANGE),
                        ("[Extra weekend trips]", AQUA),
                    ]
                ),
                accent=True,
            ),
            _card(
                "Offers in use",
                'FORMAT([Offers in plan], "0") & " of " & FORMAT(COUNTROWS(ALL(dim_offer)), "0")',
                'IF([Points awarded] = 0, "no loyalty points: not worth a contact under these limits", '
                'FORMAT([Points awarded], "#,0") & " points of the " & FORMAT([Points cap], "#,0") & " cap")',
                _dots("[Offers in plan]", "COUNTROWS(ALL(dim_offer))"),
            ),
            _card(
                "Uncertainty per contact",
                _f("[Mean uncertainty]", "$#,0.00"),
                '"bootstrap sd against " & FORMAT(DIVIDE([Expected value], [Contacts]), "$#,0.00") & " value per contact"',
                _progress("DIVIDE([Mean uncertainty], DIVIDE([Expected value], [Contacts]))", warn_at=1.0),
            ),
            _card(
                "Congestion relief",
                _f("[Relief value]", "$#,0"),
                'FORMAT([Rush-hour trips per workday], "+#,0;-#,0") & " rush-hour trips a workday onto the 407"',
                _progress("DIVIDE([Relief value], [Expected value])"),
                _info_pill('FORMAT(DIVIDE([Relief value], [Expected value]), "0.0%") & " of value"'),
            ),
        ],
    ),
    "p3_customers": (
        "Customer KPIs: customers by segment, travel propensity, inactivity risk and the share the plan contacts.",
        [
            _card(
                "Customers",
                _f("[Customers]", "#,0"),
                '"by segment, Champions to Dormant"',
                _columns(
                    "customer_segments",
                    "customer_segments[segment_order]",
                    "[Customers]",
                    "customer_segments[rfm_segment]",
                ),
                accent=True,
            ),
            _card(
                "Travel propensity",
                _f("[Mean travel propensity]", "0%"),
                '"mean calibrated chance of a trip in 30 days"',
                _progress("[Mean travel propensity]"),
            ),
            _card(
                "Inactivity risk",
                _f("[Mean inactivity risk]", "0.0%"),
                'FORMAT([High-risk customers], "#,0") & " customers above 50% risk"',
                _progress("[Mean inactivity risk]", warn_at=0.25),
                _pill("[Mean inactivity risk] < 0.25", "✓ low", "▲ elevated"),
            ),
            _card(
                "In the plan",
                _f("[Share in plan]", "0.0%"),
                'FORMAT([Customers in plan], "#,0") & " of " & FORMAT([Customers], "#,0") & " customers"',
                _progress("[Share in plan]"),
            ),
        ],
    ),
    "p4_capacity": (
        "Capacity KPIs: the October forecast with monthly history, campaign trips, load against the 80% "
        "threshold and capacity used with the reserve.",
        [
            _card(
                "Forecast trips · 30 days",
                _f("[Forecast trips]", "#,0"),
                '"monthly trips to September 2025"',
                _columns(
                    "monthly_trips",
                    "monthly_trips[month_index]",
                    "[Monthly trips]",
                    "monthly_trips[month_label]",
                ),
                accent=True,
            ),
            _card(
                "Campaign trips",
                _f("[Campaign trips]", "+#,0;-#,0"),
                'FORMAT(DIVIDE([Campaign trips], [Forecast trips]), "0.0%") & " on top of the forecast"',
                _parts([("[Forecast trips]", GREY), ("[Campaign trips]", BLUE)]),
            ),
            _card(
                "Load with the campaign",
                _f("[Load]", "0%"),
                "[Load caption]",
                _progress("[Load]", warn_at=0.8, marker=0.8),
                _pill("[Load] < 0.8", "✓ under 80%", "▲ 80% or more"),
            ),
            _card(
                "Capacity committed",
                _f(
                    "DIVIDE([Forecast trips] + [Campaign trips] + [Safety reserve], [Planning capacity])",
                    "0%",
                ),
                '"forecast, campaign and 20% reserve of " & FORMAT([Planning capacity], "#,0")',
                _progress(
                    "DIVIDE([Forecast trips] + [Campaign trips] + [Safety reserve], [Planning capacity])",
                    warn_at=0.95,
                ),
            ),
        ],
    ),
    "p5_pricing": (
        "Pricing KPIs: mean elasticity with its interval, contribution from the optimized prices, and the "
        "cells repriced.",
        [
            _card(
                "Price elasticity",
                _f("[Elasticity]", "0.00"),
                "[Elasticity caption]",
                _range("[Elasticity low]", "[Elasticity]", "[Elasticity high]", "-2.5", "0"),
                _info_pill('IF([Elasticity] > -1, "inelastic", "elastic")'),
                accent=True,
            ),
            _card(
                "Contribution from prices",
                _f("[Price contribution change]", "+$#,0;-$#,0"),
                '"jointly optimized with the campaign"',
                pill=_pill("[Price contribution change] >= 0", "✓ gain", "✕ loss"),
            ),
            _card(
                "Cells repriced",
                _f("[Cells repriced]", "0"),
                '"of " & FORMAT([Price cells], "0") & " zone × period cells"',
                _dots("[Cells repriced]", "[Price cells]"),
            ),
        ],
    ),
    "p6_experiments": (
        "Experiment KPIs: customers per arm against the power requirement, variance removed by CUPED, and how "
        "well the causal learners rank customers.",
        [
            _card(
                "Customers per arm",
                _f("[Customers per arm]", "#,0"),
                '"10 arms · power calculation needs " & FORMAT([Required per arm], "#,0")',
                _bullet("[Customers per arm]", "[Required per arm]"),
                _pill("[Customers per arm] >= [Required per arm]", "✓ powered", "✕ under-powered"),
                accent=True,
            ),
            _card(
                "CUPED variance removed",
                _f("[CUPED variance removed]", "0%"),
                '"June trips as the pre-period covariate"',
                _progress("[CUPED variance removed]"),
            ),
            _card(
                "Learner rank correlation",
                _f("[Learner rank correlation]", "0.00"),
                '"mean ρ with the true value, all learners (simulation check)"',
                _progress("[Learner rank correlation]"),
            ),
        ],
    ),
    "p7_policy": (
        "Policy KPIs: the optimized plan's true value against the perfect-knowledge ceiling, the ceiling, and "
        "propensity targeting against the same ceiling.",
        [
            _card(
                "Optimized plan · true value",
                _f("[Optimized true value]", "$#,0"),
                "[Truth caption]",
                _progress("DIVIDE([Optimized true value], [Value ceiling])"),
                _info_pill('FORMAT(DIVIDE([Optimized true value], [Value ceiling]), "0%") & " of ceiling"'),
                accent=True,
            ),
            _card(
                "Ceiling · perfect knowledge",
                _f("[Value ceiling]", "$#,0"),
                '"the same MIP solved on the true effects"',
            ),
            _card(
                "Propensity targeting · true value",
                _f("[Propensity true value]", "$#,0"),
                "[Propensity caption]",
                _progress("DIVIDE([Propensity true value], [Value ceiling])"),
                _info_pill('FORMAT(DIVIDE([Propensity true value], [Value ceiling]), "0%") & " of ceiling"'),
            ),
        ],
    ),
    "p8_operations": (
        "Operations KPIs: release checks passed, held-out model AUC against the 0.70 gate, flagged feed days "
        "and features above the drift threshold.",
        [
            _card(
                "Release gate",
                'FORMAT([Checks passed], "0") & " / " & FORMAT([Checks total], "0")',
                "[Gate caption]",
                _dots("[Checks passed]", "[Checks total]"),
                _pill("[Checks passed] = [Checks total]", "✓ passed", "✕ review"),
                accent=True,
            ),
            _card(
                "Model AUC",
                _f("[Model AUC]", "0.000"),
                '"mean of three classifiers on the July 2025 test fold · gate 0.70"',
                _progress("[Model AUC]", marker=0.7),
            ),
            _card(
                "Flagged feed days",
                _f("[Flagged days]", "0"),
                '"of " & FORMAT([Feed days], "#,0") & " ingestion days, against the same-weekday median"',
                pill=_info_pill('FORMAT(DIVIDE([Flagged days], [Feed days]), "0.0%") & " of days"'),
            ),
            _card(
                "Features drifting",
                _f("[Features to review]", "0"),
                '"of " & FORMAT([Features monitored], "0") & " features above PSI 0.2"',
                _progress("DIVIDE([Features to review], [Features monitored])", warn_at=0.25),
                _pill("[Features to review] = 0", "✓ stable", "▲ review"),
            ),
        ],
    ),
}

HTML_MEASURES: list[tuple[str, str, str, str, str]] = [
    *[
        (f"HTML KPIs {page}", _strip(cards), "", "11 HTML panels", description)
        for page, (description, cards) in KPI_STRIPS.items()
    ],
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
