"""Four-page executive PDF generated from verified simulation artifacts."""

import json
from xml.sax.saxutils import escape

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from decision_platform.config import ROOT

NAVY = colors.HexColor("#081522")
CYAN = colors.HexColor("#007b80")
SLATE = colors.HexColor("#445e70")
PALE = colors.HexColor("#edf4f7")
styles = {
    "eyebrow": ParagraphStyle(
        "eyebrow", fontName="Helvetica-Bold", fontSize=9, leading=12, textColor=CYAN, spaceAfter=12
    ),
    "title": ParagraphStyle(
        "title", fontName="Helvetica-Bold", fontSize=30, leading=35, textColor=NAVY, spaceAfter=20
    ),
    "h": ParagraphStyle(
        "h", fontName="Helvetica-Bold", fontSize=15, leading=19, textColor=NAVY, spaceBefore=16, spaceAfter=8
    ),
    "body": ParagraphStyle(
        "body", fontName="Helvetica", fontSize=10.5, leading=16, textColor=SLATE, spaceAfter=10
    ),
    "small": ParagraphStyle(
        "small", fontName="Helvetica", fontSize=8.5, leading=12, textColor=SLATE, spaceAfter=8
    ),
}


def p(text, style="body"):
    return Paragraph(escape(str(text)), styles[style])


def table(headers, rows, widths=None):
    values = [[p(x, "small") for x in row] for row in [headers] + rows]
    t = Table(values, colWidths=widths, hAlign="LEFT", repeatRows=1)
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), PALE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEBELOW", (0, 0), (-1, 0), 1, CYAN),
                ("LINEBELOW", (0, 1), (-1, -1), 0.4, colors.HexColor("#d7e3eb")),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 9),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return t


def main():
    folder = ROOT / "outputs"
    summary = json.loads((folder / "summary.json").read_text())
    models = json.loads((folder / "model_metrics.json").read_text())
    experiment = json.loads((folder / "experiment_results.json").read_text())
    optimization = json.loads((folder / "optimization_results.json").read_text())
    policy = pd.read_csv(folder / "policy_comparison.csv")
    flow = []
    flow.extend(
        [
            p("CORRIDOR / EXECUTIVE DECISION BRIEF", "eyebrow"),
            p("Customer, pricing & transportation intelligence", "title"),
            p(
                "Decision window: 1-30 October 2025. Release 0.4. Built as a synthetic portfolio simulation inspired by electronic toll-road decisions."
            ),
            p("The business decision", "h"),
            p(
                "Choose customer incentives and effective price strategies under spending, contact, inventory, reward and roadway limits. Future contribution on days 31-90 is estimated separately; no incremental twelve-month value is claimed."
            ),
            p("Recommended simulation plan", "h"),
        ]
    )
    flow.append(
        table(
            ["Expected outcome", "Result"],
            [
                ["Additional trips", f"{summary['expected_incremental_trips']:,.1f}"],
                ["Net incremental contribution", f"CAD {summary['expected_net_contribution']:,.2f}"],
                ["Incentive costs / budget", f"CAD {summary['campaign_spend']:,.2f} / 1,600.00"],
                ["Customer contacts", f"{summary['selected_contacts']:,}"],
                ["Constraint validation", "All implemented shared constraints passed"],
            ],
            [260, 230],
        )
    )
    flow.extend(
        [
            Spacer(1, 14),
            p(
                "All outcome figures above are model-based planning estimates inside a simulation. They are not observed company results. Zones, rates, engineering capacities and business policies are invented. No affiliation with 407 ETR.",
                "small",
            ),
            PageBreak(),
        ]
    )
    flow.extend(
        [
            p("02 / EVIDENCE & EXPERIMENTATION", "eyebrow"),
            p("What supports the decision", "title"),
            p(
                f"The pipeline contains {summary['customers']:,} synthetic customers, {summary['trips']:,} trips and {summary['digital_events']:,} digital events. Public Toronto weather, Ontario holidays and Bank of Canada exchange rates provide contextual data."
            ),
            p("Prediction evidence", "h"),
        ]
    )
    rows = []
    for task in ["propensity", "churn", "attrition"]:
        m = models["customer"][task]["test_calibrated"]
        rows.append([task.title(), f"{m['roc_auc']:.3f}", f"{m['brier']:.3f}", f"{m['n']:,}"])
    flow.append(table(["Model", "Test AUC", "Brier score", "Test rows"], rows, [180, 105, 105, 100]))
    flow.extend(
        [
            p(
                "Train snapshots end January 2025; validation and calibration use April; the untouched prediction test uses July. Ninety-day label windows are purged. Repeated customers across time match a batch-rescoring use case. Designed synthetic data cannot establish real-world model quality.",
                "small",
            ),
            p("Randomized offer experiment", "h"),
            p(
                f"The four groups contain {min(experiment['actual_per_arm'].values()):,} customers each. The planned requirement was {experiment['required_per_arm']:,} per group for a 5-percentage-point primary response effect, 80% power and family alpha 5%. The planned target {'was met' if experiment['powered_for_planned_mde'] else 'was not met'}. Three treatment/control comparisons use Bonferroni adjustment."
            ),
        ]
    )
    flow.append(
        table(
            ["Offer", "Response difference", "Adjusted interval"],
            [
                [
                    r["arm"],
                    f"{r['difference'] * 100:+.1f} pp",
                    f"{r['ci_low'] * 100:+.1f} to {r['ci_high'] * 100:+.1f} pp",
                ]
                for r in experiment["results"]
            ],
            [195, 140, 155],
        )
    )
    pilot = json.loads((folder / "policy_trial_results.json").read_text())
    effect = pilot["incremental_net_contribution_per_customer"]
    flow.extend(
        [
            p(
                f"A fresh constrained-policy trial randomized {pilot['n_policy']:,} policy and {pilot['n_control']:,} control customers, independently of model training. Estimated incremental net contribution is CAD {effect['difference']:.2f} per randomized customer (95% interval {effect['ci_low']:.2f} to {effect['ci_high']:.2f}). It includes uncontacted customers; wide uncertainty remains visible.",
                "small",
            ),
            PageBreak(),
        ]
    )
    flow.extend(
        [
            p("03 / ALLOCATION & TRADEOFFS", "eyebrow"),
            p("A constrained, reviewable plan", "title"),
            p(
                "One Gurobi mixed-integer solve chooses promotions and loyalty awards together. The optimizer can assign at most one offer per customer, enforce eligibility and inventory, reserve full reward liability, meet portfolio ROI and respect cell-level headroom including a 20% forecast reserve."
            ),
            p("How targeting methods compare", "h"),
        ]
    )
    flow.append(
        table(
            ["Method", "Contacts", "Expected net CAD", "Expected trips"],
            [
                [r.policy, str(r.contacts), f"{r.net_contribution:,.2f}", f"{r.incremental_trips:,.1f}"]
                for r in policy.itertuples()
            ],
            [185, 65, 130, 110],
        )
    )
    horizon = models["demand"]["horizon_validation"]
    flow.extend(
        [
            p(
                "Methods use the same shortlist and constraints. Differences compare planning objectives; adding later contribution can trade immediate contribution against future value.",
                "small",
            ),
            p("Limits that affect interpretation", "h"),
            p(
                "Optimality covers 600 shortlisted customers and three offers. Trip and later-value effects use a declared 25% shrinkage, not a confidence bound. Retention is reported separately to avoid double counting."
            ),
            p(
                "Discount costs include baseline travel. A loyalty award reserves CAD 5 plus CAD 0.35 contact cost; balances reconcile earnings plus awards less redemptions. The joint pricing solver shares capacity with campaign contacts and assumes constant elasticity without fitted price/offer interactions."
            ),
            p(
                f"The serving demand baseline has next-day MAE {models['demand']['test']['mae']:.2f}; the learned candidate was rejected by its untouched acceptance test. Fixed-origin 30-day backtests have MAE {horizon['test_mae']:.2f} and {horizon['test_interval_coverage']:.1%} marginal interval coverage. Hour/direction forecasts disaggregate daily demand; hourly coverage is unvalidated."
            ),
            p("Recommended next decision", "h"),
            p(
                "Review scenario economics and the fresh policy experiment before operational adoption. Replace invented rules with approved business policies, enforce realized spending/traffic limits and validate performance on the actual deployment population."
            ),
            PageBreak(),
        ]
    )
    flow.extend(
        [
            p("04 / DELIVERY & NEXT MILESTONE", "eyebrow"),
            p("Execution evidence and boundaries", "title"),
            p(
                "Twelve app workspaces include saved scenario audit records, customer reward/consent profiles, price allocation, policy experiments, an operations review queue and visual SQL cases. Production mode requires approved OIDC identities, release integrity and model acceptance."
            ),
            p("Delivery status", "h"),
        ]
    )
    flow.append(
        table(
            ["Deliverable", "Actual status"],
            [
                [
                    "Local analytics and app",
                    "Acceptance checks passed; monthly demand backtests and shared constraint checks recorded.",
                ],
                [
                    "Model registry",
                    "Nine model families registered locally; loaded scoring roundtrips matched. Promotion remains reviewed.",
                ],
                [
                    "Native Power BI",
                    "Eight pages, 16 tables and 32 measures structurally validated. Revised Desktop refresh blocked by reload-dialog automation.",
                ],
                [
                    "AWS / Databricks",
                    "Six AWS contracts run locally; rejected candidates held. Full Databricks marts authored. No hosted execution claimed.",
                ],
                [
                    "Production deployment",
                    "Private auth, containers, CI and AWS storage/IAM template prepared. Runtime dependency audit and infrastructure validation passed; hosted acceptance pending.",
                ],
            ],
            [150, 340],
        )
    )
    flow.extend(
        [
            p("Source and privacy notes", "h"),
            p(
                "Public context uses Open-Meteo historical weather, Ontario holiday data from Nager.Date and Bank of Canada FXCADUSD. Customer IDs and all customer behaviour are synthetic; raw public responses and provenance remain local."
            ),
            p(
                "Hosted execution, provider sign-in, container builds, staging load/backup tests and GitHub publication need completed external receipts. No AWS resources or charges were created by this release.",
                "small",
            ),
        ]
    )
    output = ROOT / "output" / "pdf" / "executive_brief.pdf"
    output.parent.mkdir(parents=True, exist_ok=True)

    def footer(canvas, doc):
        canvas.saveState()
        w, h = A4
        canvas.setStrokeColor(CYAN)
        canvas.setLineWidth(1)
        canvas.line(42, 38, w - 42, 38)
        canvas.setFillColor(SLATE)
        canvas.setFont("Helvetica", 8)
        canvas.drawString(42, 24, "CORRIDOR / SYNTHETIC PORTFOLIO / RELEASE 0.4")
        canvas.drawRightString(w - 42, 24, f"{doc.page}")
        canvas.restoreState()

    doc = SimpleDocTemplate(
        str(output),
        pagesize=A4,
        rightMargin=42,
        leftMargin=42,
        topMargin=42,
        bottomMargin=52,
        title="Corridor Executive Decision Brief",
        author="Kush - Decision Intelligence Portfolio",
    )
    doc.build(flow, onFirstPage=footer, onLaterPages=footer)
    print(output)


if __name__ == "__main__":
    main()
