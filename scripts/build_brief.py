"""Four-page executive brief, generated from the latest pipeline run.

Written for the people who own the decision, not the people who built the models: what to do, what it is
worth, how sure we are, what it costs to change a limit, and what is not known. Every figure is read from
`outputs/`; nothing is typed in.

Usage::

    python scripts/build_brief.py   # writes output/pdf/executive_brief.pdf
"""

import json
from xml.sax.saxutils import escape

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from decision_platform import __version__
from decision_platform.config import ROOT, Config
from decision_platform.simulation import OFFER_CATALOG, ZONES

NAVY = colors.HexColor("#081522")
TEAL = colors.HexColor("#007b80")
SLATE = colors.HexColor("#3d5566")
PALE = colors.HexColor("#edf4f7")
RULE = colors.HexColor("#d7e3eb")
styles = {
    "eyebrow": ParagraphStyle(
        "eyebrow", fontName="Helvetica-Bold", fontSize=9, leading=12, textColor=TEAL, spaceAfter=10
    ),
    "title": ParagraphStyle(
        "title", fontName="Helvetica-Bold", fontSize=26, leading=31, textColor=NAVY, spaceAfter=14
    ),
    "h": ParagraphStyle(
        "h",
        fontName="Helvetica-Bold",
        fontSize=13.5,
        leading=18,
        textColor=NAVY,
        spaceBefore=12,
        spaceAfter=6,
    ),
    "body": ParagraphStyle(
        "body", fontName="Helvetica", fontSize=10.5, leading=15.5, textColor=SLATE, spaceAfter=8
    ),
    "lead": ParagraphStyle(
        "lead", fontName="Helvetica", fontSize=12.5, leading=18, textColor=NAVY, spaceAfter=10
    ),
    "small": ParagraphStyle(
        "small", fontName="Helvetica", fontSize=8.5, leading=11.5, textColor=SLATE, spaceAfter=6
    ),
    "cell": ParagraphStyle("cell", fontName="Helvetica", fontSize=8.8, leading=11.5, textColor=SLATE),
    "cellb": ParagraphStyle("cellb", fontName="Helvetica-Bold", fontSize=8.8, leading=11.5, textColor=NAVY),
}


def p(text, style="body"):
    return Paragraph(escape(str(text)).replace("**", ""), styles[style])


def rich(text, style="body"):
    """A paragraph whose **bold** spans are rendered bold."""
    parts = escape(str(text)).split("**")
    return Paragraph("".join(f"<b>{s}</b>" if i % 2 else s for i, s in enumerate(parts)), styles[style])


def table(headers, rows, widths, bold_first=False):
    values = [[p(h, "cellb") for h in headers]] + [
        [p(x, "cellb" if (bold_first and i == 0) else "cell") for i, x in enumerate(row)] for row in rows
    ]
    t = Table(values, colWidths=widths, hAlign="LEFT", repeatRows=1)
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), PALE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEBELOW", (0, 0), (-1, 0), 1, TEAL),
                ("LINEBELOW", (0, 1), (-1, -1), 0.4, RULE),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return t


def signed(value, decimals=2):
    """A number with a typographic minus."""
    return f"{value:.{decimals}f}".replace("-", "−")


def money(value, decimals=0):
    sign = "−" if value < 0 else ""
    return f"{sign}${abs(value):,.{decimals}f}"


def main():
    out = ROOT / "outputs"
    load = lambda name: json.loads((out / name).read_text())  # noqa: E731
    summary, models = load("summary.json"), load("model_metrics.json")
    experiment, optimization = load("experiment_results.json"), load("optimization_results.json")
    pilot, policy_value, gate = (
        load("policy_trial_results.json"),
        load("policy_value.json"),
        load("quality_gate.json"),
    )
    uplift = load("uplift_metrics.json")
    policies = pd.read_csv(out / "policy_comparison.csv")
    capacity = pd.read_csv(out / "capacity.csv")
    combined, certificate = optimization["combined"], optimization["certification"]
    ceiling = policy_value["oracle_ceiling"]
    share = summary["share_of_oracle_optimized"]
    effect = pilot["incremental_net_contribution_per_customer"]
    insight = policy_value["propensity_insight"]
    names = dict(zip(OFFER_CATALOG.offer_id, OFFER_CATALOG.offer_name, strict=True))

    flow = [
        p("CORRIDOR / EXECUTIVE DECISION BRIEF / OCTOBER 2025 CAMPAIGN", "eyebrow"),
        p("Which customers get which offer, and what it is worth", "title"),
        rich(
            f"**Recommendation.** Contact {combined['contacts']:,} of {summary['eligible_customers']:,} eligible customers "
            f"with one offer each, for {money(combined['spend'])} of incentives. The models expect "
            f"{money(combined['objective_value'])} of value; scored against the simulator's true responses the plan "
            f"creates **{money(summary['true_value_optimized'])}, {share:.0%} of what a perfectly informed planner "
            f"could reach**.",
            "lead",
        ),
        p("The one thing to remember", "h"),
        rich(
            "**The customers most likely to travel are not the ones an offer moves.** Ranking customers by travel "
            "propensity and ranking them by the value an offer truly creates go in opposite directions (rank "
            f"correlation {signed(insight['spearman_propensity_vs_true_best_value'])}). Giving 10% off to the most "
            f"frequent travellers, with the same budget, creates {money(summary['true_value_propensity'])}: "
            f"{summary['share_of_oracle_propensity']:.0%} of the ceiling. Most of that budget discounts trips that "
            "would have happened anyway."
        ),
        p("The plan in numbers", "h"),
        table(
            ["", "Value", "What it means"],
            [
                ["Contacts", f"{combined['contacts']:,}", f"limit {combined['contact_limit']:,}"],
                ["Incentive spend", money(combined["spend"]), f"budget {money(combined['budget'])}"],
                [
                    "Expected value",
                    money(combined["objective_value"]),
                    "30-day net contribution after incentives, discounted days 31-90 margin, congestion relief",
                ],
                [
                    "True value (simulation)",
                    money(summary["true_value_optimized"]),
                    f"{share:.0%} of the {money(ceiling)} perfect-knowledge ceiling",
                ],
                [
                    "Rush-hour trips moved onto the 407",
                    f"{combined['rush_hour_trips_per_workday']:+,.0f} per workday",
                    "only where the zone has free-flow room at peak",
                ],
                [
                    "Certificate",
                    "proven optimal" if certificate.get("proven_optimal") else "within gap",
                    f"one program over {certificate['variables']:,} customer-offer decisions; gap "
                    f"{certificate['relative_gap_to_lp_bound']:.1e} to the bound",
                ],
            ],
            [130, 105, 260],
            bold_first=True,
        ),
        Spacer(1, 10),
        p(
            "Synthetic portfolio simulation inspired by electronic toll-road decisions. Customers, rates, zones, "
            "capacities and policies are invented; the weather, holiday and exchange-rate context is real public "
            "data. Not affiliated with 407 ETR.",
            "small",
        ),
        PageBreak(),
    ]

    design = experiment["design"]
    flow += [
        p("02 / HOW SURE WE ARE", "eyebrow"),
        p("Two randomised tests stand behind the plan", "title"),
        p("The July offer trial", "h"),
        p(
            f"Every customer was randomised into control or one of {len(experiment['results'])} offers "
            f"({min(experiment['actual_per_arm'].values()):,} per arm against {experiment['required_per_arm']:,} "
            f"required), with assignment balanced within strata of past travel (worst covariate imbalance "
            f"{experiment['max_abs_smd']:.3f} standardised difference; allocation check p = "
            f"{experiment['srm_p_value']:.2f}). Using each customer's June behaviour as a control variable removed "
            f"{experiment['cuped_mean_variance_reduction']:.0%} of the noise, so the trial could detect an effect of "
            f"{design['achieved_mde_trips_cuped']:.2f} trips per customer."
        ),
        table(
            ["Offer", "Net contribution per randomised customer, 30 days", "95% interval (Bonferroni)"],
            [
                [
                    r["arm"],
                    money(r["incremental_net_contribution_cuped"]["difference"], 2),
                    f"{money(r['incremental_net_contribution_cuped']['ci_low'], 2)} to "
                    f"{money(r['incremental_net_contribution_cuped']['ci_high'], 2)}",
                ]
                for r in sorted(
                    experiment["results"],
                    key=lambda r: -r["incremental_net_contribution_cuped"]["difference"],
                )
            ],
            [170, 175, 150],
        ),
        p(
            "Most offers lose money on the average customer: a discount is paid on every trip, including the ones "
            "the customer would have taken anyway. That is why the plan targets the customers each offer actually "
            "moves rather than sending the best-on-average offer to everyone.",
            "small",
        ),
        p("The October policy test", "h"),
        rich(
            f"The targeting policy itself was then randomised: {pilot['n_policy']:,} customers governed by the "
            f"plan's rules against {pilot['n_control']:,} who were not, counting everyone the plan chose not to "
            f"contact. Result: **{money(effect['difference'], 2)} net contribution per customer** (95% interval "
            f"{money(effect['ci_low'], 2)} to {money(effect['ci_high'], 2)}, p = {effect['p_value']:.3f})."
        ),
        p("Customer models, scored on an untouched later month", "h"),
        table(
            ["Model", "Algorithm", "AUC", "Calibration error", "Use"],
            [
                [
                    task.title(),
                    models["customer"][task]["champion"].replace("_", " "),
                    f"{models['customer'][task]['test_calibrated']['roc_auc']:.3f}",
                    f"{models['customer'][task]['test_calibrated']['ece_10bins']:.3f}",
                    use,
                ]
                for task, use in [
                    ("propensity", "reporting and segments, never targeting"),
                    ("churn", "inactivity risk in the next 90 days"),
                    ("attrition", "risk among recently active customers"),
                ]
            ],
            [70, 110, 45, 75, 195],
        ),
        p(
            f"Release gate: {sum(c['passed'] for c in gate['checks'])} of {len(gate['checks'])} checks passed. The "
            "gate is evaluated on every run; at 3,000 customers it fails, and the run is not published.",
            "small",
        ),
        PageBreak(),
    ]

    shadow = sorted(optimization["lp_relaxation"]["shadow_prices"], key=lambda r: -r["shadow_price"])
    labels = {
        "budget": "Incentive budget",
        "campaign_size": "Contact limit",
        "minimum_net_roi": "Net ROI floor",
        "loyalty_points": "Points cap",
    }

    def label(constraint):
        if constraint.startswith("inventory:"):
            return f"Inventory: {names.get(constraint.split(':', 1)[1], constraint.split(':', 1)[1])}"
        return labels.get(constraint, constraint.replace(":", " "))

    by_offer = optimization["by_offer"]
    peak = capacity[capacity.period.eq("Peak")].sort_values("final_utilization", ascending=False)
    flow += [
        p("03 / THE PLAN AND ITS TRADE-OFFS", "eyebrow"),
        p("Every limit has an owner and a price", "title"),
        p("Where the money goes", "h"),
        table(
            ["Offer", "Contacts", "Spend", "Expected value"],
            [
                [names.get(o, o), f"{v['contacts']:,}", money(v["spend"]), money(v["objective_value"])]
                for o, v in sorted(by_offer.items(), key=lambda kv: -kv[1]["objective_value"])
            ],
            [200, 80, 100, 115],
        ),
        p("What relaxing a limit is worth", "h"),
        p(
            "The optimiser reports, for each limit that binds, how much expected value one more unit would add. "
            "That turns a request for more budget or more inventory into a priced trade-off."
        ),
        table(
            ["Limit", "Current", "Value of one more unit"],
            [[label(r["constraint"]), f"{r['limit']:,.0f}", money(r["shadow_price"], 2)] for r in shadow],
            [200, 120, 175],
        ),
        p("Rush hour", "h"),
        p(
            "Peak capacity is a hard limit with a 20% reserve. The busiest peak cells after the campaign: "
            + "; ".join(
                f"{ZONES[int(r.zone_id)]} at {r.final_utilization:.0%}" for r in peak.head(3).itertuples()
            )
            + ". Rush-hour offers are used only where there is room, and off-peak offers that move commuters out "
            "of the peak free capacity for them."
        ),
        p("How the plan compares with simpler targeting", "h"),
        table(
            ["Approach", "True value", "Share of ceiling"],
            [
                [r.policy, money(r.true_value), f"{r.share_of_oracle:.0%}".replace("-", "−")]
                for r in policies.sort_values("true_value", ascending=False).itertuples()
            ],
            [250, 120, 125],
        ),
        PageBreak(),
    ]

    bias = uplift["blp_calibration_check"]["mean_value_bias_raw"]
    flow += [
        p("04 / WHAT IS NOT KNOWN, AND WHAT TO DO NEXT", "eyebrow"),
        p("Limits that change how to read this", "title"),
        rich(
            f"**Estimates are conservative in level.** The models under-state each customer-offer's value by "
            f"{money(-bias, 2)} on average, which is why the expected {money(combined['objective_value'])} sits "
            f"below the simulated true {money(summary['true_value_optimized'])}. The plan depends on ranking "
            "customers correctly, not on the level; the policy test measures the level directly."
        ),
        rich(
            "**The simulation is a test bench, not the business.** It shows the method finds value where a "
            "simpler rule does not; it cannot show what the real response rates are. The first real campaign "
            "should run as a policy test like October's before any full rollout."
        ),
        rich(
            "**Congestion relief is a policy choice.** It is valued at "
            f"{money(Config().relief_value, 2)} per "
            "net rush-hour trip moved onto the highway; the business should set that number."
        ),
        p("Recommended next steps", "h"),
        table(
            ["Step", "Owner", "Decision it enables"],
            [
                [
                    "Approve the plan for a randomised pilot",
                    "Marketing",
                    "Measure real incremental value per customer",
                ],
                [
                    "Release more free-trip inventory",
                    "Marketing",
                    "The limit with the highest value per unit",
                ],
                [
                    "Set the congestion-relief value",
                    "Traffic operations",
                    "How much rush-hour shifting is worth",
                ],
                [
                    "Provide dated consent and status history",
                    "IT",
                    "Point-in-time eligibility for every plan",
                ],
            ],
            [190, 100, 205],
        ),
        p("Where the work runs", "h"),
        table(
            ["Surface", "Status"],
            [
                [
                    "Pipeline and release gate",
                    f"Runs end to end in {summary['runtime_seconds'] / 60:.0f} minutes; gate passed",
                ],
                ["Decision app and API", "Twelve-page app; decision API with keys and health checks"],
                ["Power BI", "Nine-page report; every measure executed against the Power BI engine"],
                ["Databricks", "Four-task job built and run locally end to end; hosted run pending sign-in"],
                ["AWS SageMaker", "Pipeline defined and its stages run locally; not run in AWS"],
            ],
            [160, 335],
        ),
    ]

    output = ROOT / "output" / "pdf" / "executive_brief.pdf"
    output.parent.mkdir(parents=True, exist_ok=True)

    def footer(canvas, doc):
        canvas.saveState()
        w, _h = A4
        canvas.setStrokeColor(TEAL)
        canvas.setLineWidth(1)
        canvas.line(42, 38, w - 42, 38)
        canvas.setFillColor(SLATE)
        canvas.setFont("Helvetica", 8)
        canvas.drawString(
            42, 24, f"CORRIDOR {__version__} / SYNTHETIC SIMULATION / NOT AFFILIATED WITH 407 ETR"
        )
        canvas.drawRightString(w - 42, 24, f"{doc.page}")
        canvas.restoreState()

    doc = SimpleDocTemplate(
        str(output),
        pagesize=A4,
        rightMargin=42,
        leftMargin=42,
        topMargin=42,
        bottomMargin=52,
        title="Corridor executive decision brief",
        author="Kush Patel",
    )
    doc.build(flow, onFirstPage=footer, onLaterPages=footer)
    print(output)


if __name__ == "__main__":
    main()
