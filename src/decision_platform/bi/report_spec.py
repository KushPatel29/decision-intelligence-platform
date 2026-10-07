"""What the Corridor report contains: nine pages, and every visual on them.

Each page answers one question a planning team would ask about the October plan,
from the same verified outputs the app serves.

Fields are written ``table[column]`` for a column and ``[Measure]`` for a measure.
"""

from __future__ import annotations

from decision_platform.bi.html_spec import HTML_VISUAL, KPI_STRIPS
from decision_platform.bi.report_chrome import add_chrome

# Pages were laid out with a 118-px row of KPI tiles at the top; the KPI strip takes that row.
# (The SVG "card" kind is still supported by the generator for reports that want image tiles.)
CARD_Y, CARD_H = 20, 118
ROW1_Y, ROW2_Y = 152, 442
SLICER = (1068, 192, 76)


def slicers(*fields: tuple[str, str]) -> list[dict]:
    x, width, height = SLICER
    return [
        {
            "type": "slicer",
            "field": field,
            "title": title,
            "pos": (x, ROW2_Y + i * 84, width, height),
            "alt": f"Slicer. Filters the page by {title.lower()}.",
        }
        for i, (field, title) in enumerate(fields)
    ]


OFFER = ("dim_offer[offer_name]", "Offer")
ZONE = ("dim_zone[zone_name]", "Zone")
PERIOD = ("dim_period[period]", "Travel period")


def kpis(page: str) -> dict:
    """The page's KPI strip: one HTML visual in place of a row of image tiles."""
    description, _cards = KPI_STRIPS[page]
    return {
        "type": "html",
        "measure": f"[HTML KPIs {page}]",
        "pos": (20, CARD_Y, 1240, CARD_H),
        "alt": f"KPI strip. {description}",
        "framed": False,
    }


def html(measure: str, pos: tuple[int, int, int, int], alt: str, *, framed: bool = True) -> dict:
    """A panel drawn by the HTML Content visual from one of html_spec's measures."""
    return {"type": "html", "measure": f"[{measure}]", "pos": pos, "alt": alt, "framed": framed}


PAGES: list[dict] = [
    {
        # Written in body coordinates (88-704), so the chrome's vertical reflow is
        # the identity and every panel keeps the height its markup was sized for.
        "name": "p0_command",
        "display": "Command centre",
        "visuals": [
            html(
                "HTML Hero",
                (20, 88, 1240, 140),
                "Banner. The October plan's size and spend, its certificate, and four headline figures: expected "
                "value, true value against the ceiling, net ROI and rush-hour trips moved onto the 407.",
                framed=False,
            ),
            html(
                "HTML Offer cards",
                (20, 240, 1240, 212),
                "Nine offer cards in catalogue order. Each shows the offer's mechanic, the period it fills, its "
                "expected value, contacts and spend, and a bar scaled to the largest offer.",
            ),
            html(
                "HTML Policy leaderboard",
                (20, 464, 620, 240),
                "Leaderboard of targeting approaches ranked by simulator-true value, with each approach's share of "
                "the perfect-knowledge ceiling; the production plan is highlighted.",
            ),
            html(
                "HTML Narrative",
                (654, 464, 606, 240),
                "The executive summary paragraph, built from the measures.",
            ),
        ],
    },
    {
        "name": "p1_plan",
        "display": "October plan",
        "visuals": [
            kpis("p1_plan"),
            {
                "type": "narrative",
                "field": "[Executive summary]",
                "title": "The plan in one paragraph",
                "pos": (20, ROW1_Y, 380, 272),
                "alt": "Card titled The plan in one paragraph. Shows the executive summary.",
            },
            {
                "type": "bar",
                "x": "dim_offer[offer_name]",
                "y": ["[Expected value]"],
                "sort": ("[Expected value]", "Descending"),
                "title": "Expected value by offer",
                "pos": (414, ROW1_Y, 846, 272),
                "alt": "Bar chart titled Expected value by offer. Plots Expected value by offer name.",
            },
            {
                "type": "bar",
                "x": "policy_comparison[policy]",
                "y": ["[True value]"],
                "color": "[Approach colour]",
                "sort": ("policy_comparison[policy]", "Ascending"),
                "title": "True value by targeting approach (simulation truth)",
                "pos": (20, ROW2_Y, 620, 258),
                "alt": "Bar chart titled True value by targeting approach. Plots True value by approach; the "
                "production plan is blue.",
            },
            {
                "type": "line",
                "x": "budget_frontier[budget]",
                "y": ["[Frontier value]"],
                "sort": ("budget_frontier[budget]", "Ascending"),
                "title": "Optimal expected value as the budget changes",
                "pos": (654, ROW2_Y, 606, 258),
                "alt": "Line chart titled Optimal expected value as the budget changes. Plots Frontier value by budget.",
            },
        ],
    },
    {
        "name": "p2_contacts",
        "display": "Campaign contacts",
        "visuals": [
            kpis("p2_contacts"),
            {
                "type": "stacked_column",
                "x": "dim_zone[zone_name]",
                "y": ["[Contacts]"],
                "series": "dim_offer[offer_name]",
                "sort": ("dim_zone[zone_name]", "Ascending"),
                "title": "Contacts by home zone and offer",
                "pos": (20, ROW1_Y, 760, 272),
                "alt": "Stacked column chart titled Contacts by home zone and offer. Plots Contacts by zone name for "
                "each offer.",
            },
            {
                "type": "bar",
                "x": "dim_offer[offer_name]",
                "y": ["[Value per incentive dollar]"],
                "sort": ("[Value per incentive dollar]", "Descending"),
                "title": "Expected value per incentive dollar",
                "pos": (794, ROW1_Y, 466, 272),
                "alt": "Bar chart titled Expected value per incentive dollar. Plots Value per incentive dollar by offer.",
            },
            {
                "type": "table",
                "columns": [
                    "plan_contacts[customer_id]",
                    "dim_offer[offer_name]",
                    "dim_zone[zone_name]",
                    "plan_contacts[rfm_segment]",
                    "[Expected value]",
                    "[Incentive spend]",
                    "[Extra trips]",
                    "[Mean uncertainty]",
                ],
                "sort": ("[Expected value]", "Descending"),
                "title": "Every contact in the plan",
                "pos": (20, ROW2_Y, 1044, 258),
                "alt": "Table titled Every contact in the plan. Lists customer, offer, zone, segment, Expected value, "
                "Incentive spend, Extra trips and Mean uncertainty.",
            },
            *slicers(OFFER, ZONE, ("plan_contacts[rfm_segment]", "Segment")),
        ],
    },
    {
        "name": "p3_customers",
        "display": "Customers",
        "visuals": [
            kpis("p3_customers"),
            {
                "type": "bar",
                "x": "customer_segments[rfm_segment]",
                "y": ["[Customers]"],
                "sort": ("customer_segments[rfm_segment]", "Ascending"),
                "title": "Customers by segment",
                "pos": (20, ROW1_Y, 620, 272),
                "alt": "Bar chart titled Customers by segment. Plots Customers by segment.",
            },
            {
                "type": "column",
                "x": "customer_segments[rfm_segment]",
                "y": ["[Share in plan]"],
                "sort": ("customer_segments[rfm_segment]", "Ascending"),
                "title": "Share of each segment the plan contacts",
                "pos": (654, ROW1_Y, 606, 272),
                "alt": "Column chart titled Share of each segment the plan contacts. Plots Share in plan by segment.",
            },
            html(
                "HTML Segments",
                (20, ROW2_Y, 1044, 258),
                "Table of segments with customers, travel propensity, inactivity risk, best-offer value and a bar "
                "for the share of each segment the plan contacts. Responds to the zone and tier filters.",
            ),
            *slicers(ZONE, ("customer_segments[tier]", "Loyalty tier")),
        ],
    },
    {
        "name": "p4_capacity",
        "display": "Transportation and capacity",
        "visuals": [
            kpis("p4_capacity"),
            html(
                "HTML Capacity grid",
                (20, ROW1_Y, 620, 272),
                "Heat grid of load by zone and travel period with the campaign, as a share of free-flow capacity, "
                "with the trips left free in each cell; cells at 80% or more are amber.",
            ),
            {
                "type": "stacked_column",
                "x": "dim_zone[zone_name]",
                "y": ["[Forecast trips]", "[Campaign trips]", "[Safety reserve]"],
                "sort": ("dim_zone[zone_name]", "Ascending"),
                "title": "Forecast, campaign and reserve against capacity",
                "pos": (654, ROW1_Y, 606, 272),
                "alt": "Stacked column chart titled Forecast, campaign and reserve. Plots Forecast trips, Campaign "
                "trips and Safety reserve by zone.",
            },
            {
                "type": "line",
                "x": "hourly_forecast[hour]",
                "y": ["[Hourly forecast trips]"],
                "series": "hourly_forecast[direction]",
                "sort": ("hourly_forecast[hour]", "Ascending"),
                "title": "October forecast by hour and direction",
                "pos": (20, ROW2_Y, 620, 258),
                "alt": "Line chart titled October forecast by hour and direction. Plots Hourly forecast trips by hour "
                "for each direction.",
            },
            {
                "type": "line",
                "x": "demand_backtest[date]",
                "y": ["[Backtest actual]", "[Backtest forecast]"],
                "sort": ("demand_backtest[date]", "Ascending"),
                "title": "Held-out 30-day forecast against actual trips",
                "pos": (654, ROW2_Y, 410, 258),
                "alt": "Line chart titled Held-out 30-day forecast against actual trips. Plots Backtest actual and "
                "Backtest forecast by date.",
            },
            *slicers(PERIOD),
        ],
    },
    {
        "name": "p5_pricing",
        "display": "Pricing",
        "visuals": [
            kpis("p5_pricing"),
            {
                "type": "bar",
                "x": "dim_zone[zone_name]",
                "y": ["[Elasticity]"],
                "series": "dim_period[period]",
                "sort": ("dim_zone[zone_name]", "Ascending"),
                "title": "Price elasticity by zone and period (empirical Bayes)",
                "pos": (20, ROW1_Y, 620, 272),
                "alt": "Bar chart titled Price elasticity by zone and period. Plots Elasticity by zone for each period.",
            },
            {
                "type": "line",
                "x": "price_scenarios[price_change]",
                "y": ["[Demand index]", "[Revenue index]"],
                "sort": ("price_scenarios[price_change]", "Ascending"),
                "title": "Demand and revenue index by effective price change",
                "pos": (654, ROW1_Y, 606, 272),
                "alt": "Line chart titled Demand and revenue index by effective price change. Plots Demand index and "
                "Revenue index by price change.",
            },
            {
                "type": "table",
                "columns": [
                    "dim_zone[zone_name]",
                    "dim_period[period]",
                    "price_plan[price_change]",
                    "price_plan[forecast_trips]",
                    "price_plan[campaign_trips]",
                    "[Price contribution change]",
                ],
                "sort": ("[Price contribution change]", "Descending"),
                "title": "Jointly optimized price per cell, sharing capacity with the campaign",
                "pos": (20, ROW2_Y, 1044, 258),
                "alt": "Table titled Jointly optimized price per cell. Lists zone, period, price change, forecast "
                "trips, campaign trips and Price contribution change.",
            },
            *slicers(PERIOD, ZONE),
        ],
    },
    {
        "name": "p6_experiments",
        "display": "Experiments",
        "visuals": [
            kpis("p6_experiments"),
            html(
                "HTML Experiment forest",
                (20, ROW1_Y, 620, 272),
                "Forest plot of each offer's CUPED-adjusted 30-day net contribution per randomised customer with "
                "its Bonferroni 95% interval and a zero line; negative estimates are red.",
            ),
            {
                "type": "table",
                "columns": [
                    "dim_offer[offer_name]",
                    "[Trial value effect]",
                    "[Trial value low]",
                    "[Trial value high]",
                    "[Trial trips effect]",
                    "[CUPED variance removed]",
                ],
                "sort": ("[Trial value effect]", "Descending"),
                "title": "Effects with Bonferroni 95% intervals",
                "pos": (654, ROW1_Y, 606, 272),
                "alt": "Table titled Effects with Bonferroni 95% intervals. Lists offer, effect, interval bounds, "
                "trips effect and CUPED variance removed.",
            },
            {
                "type": "line",
                "x": "sequential_looks[day]",
                "y": ["[Sequential z]"],
                "series": "sequential_looks[arm]",
                "sort": ("sequential_looks[day]", "Ascending"),
                "title": "Sequential monitoring: cumulative z at days 10, 20 and 30",
                "pos": (20, ROW2_Y, 620, 258),
                "alt": "Line chart titled Sequential monitoring. Plots Sequential z by day for each arm.",
            },
            {
                "type": "matrix",
                "rows": "dim_offer[offer_name]",
                "columns_by": "learner_comparison[learner]",
                "values": ["[Learner rank correlation]"],
                "totals": False,
                "title": "Causal learners: rank correlation with true value",
                "pos": (654, ROW2_Y, 606, 258),
                "alt": "Matrix titled Causal learners. Shows Learner rank correlation by offer and learner.",
            },
        ],
    },
    {
        "name": "p7_policy",
        "display": "Policy value",
        "visuals": [
            kpis("p7_policy"),
            {
                "type": "bar",
                "x": "policy_comparison[policy]",
                "y": ["[Predicted value]", "[True value]"],
                "sort": ("policy_comparison[policy]", "Ascending"),
                "title": "Predicted against true value, by approach",
                "pos": (20, ROW1_Y, 760, 272),
                "alt": "Bar chart titled Predicted against true value. Plots Predicted value and True value by approach.",
            },
            html(
                "HTML Guardrails",
                (794, ROW1_Y, 466, 272),
                "Table of binding guardrails with their limits and LP shadow prices, and the one most worth relaxing.",
            ),
            {
                "type": "table",
                "columns": [
                    "policy_comparison[policy]",
                    "[True value]",
                    "[Predicted value]",
                    "[Share of ceiling]",
                    "[Contacts losing money]",
                ],
                "totals": False,
                "sort": ("policy_comparison[policy]", "Ascending"),
                "title": "Approaches scored against the truth",
                "pos": (20, ROW2_Y, 620, 258),
                "alt": "Table titled Approaches scored against the truth. Lists approach, True value, Predicted value, "
                "Share of ceiling and Contacts losing money.",
            },
            {
                "type": "column",
                "x": "budget_frontier[budget]",
                "y": ["[Frontier marginal value]"],
                "sort": ("budget_frontier[budget]", "Ascending"),
                "title": "Extra value per extra budget dollar",
                "pos": (654, ROW2_Y, 606, 258),
                "alt": "Column chart titled Extra value per extra budget dollar. Plots Frontier marginal value by budget.",
            },
        ],
    },
    {
        "name": "p8_operations",
        "display": "Operations",
        "visuals": [
            kpis("p8_operations"),
            {
                "type": "line",
                "x": "feed_quality[day]",
                "y": ["[Feed rows]", "[Expected feed rows]"],
                "sort": ("feed_quality[day]", "Ascending"),
                "title": "Bronze trip feed: rows ingested against the same-weekday expectation",
                "pos": (20, ROW1_Y, 760, 272),
                "alt": "Line chart titled Bronze trip feed. Plots Feed rows and Expected feed rows by day.",
            },
            html(
                "HTML Scorecard",
                (794, ROW1_Y, 466, 548),
                "Scorecard of the release acceptance gate, one line per check with its criterion and a pass or fail "
                "mark, then the customer models' champion, AUC, Brier score and calibration error on the test fold.",
            ),
            {
                "type": "bar",
                "x": "feature_drift[feature]",
                "y": ["[Mean PSI]"],
                "sort": ("[Mean PSI]", "Descending"),
                "title": "Feature drift (PSI), January to October 2025",
                "pos": (20, ROW2_Y, 760, 258),
                "alt": "Bar chart titled Feature drift. Plots Mean PSI by feature.",
            },
        ],
    },
]

VISUAL_TYPES: dict[str, str] = {
    "card": "card",
    "narrative": "card",
    "bar": "clusteredBarChart",
    "column": "clusteredColumnChart",
    "stacked_column": "columnChart",
    "line": "lineChart",
    "area": "areaChart",
    "scatter": "scatterChart",
    "donut": "donutChart",
    "treemap": "treemap",
    "waterfall": "waterfallChart",
    "funnel": "funnel",
    "table": "tableEx",
    "matrix": "pivotTable",
    "slicer": "slicer",
    "gauge": "gauge",
    "page_header": "image",
    "nav": "actionButton",
    "filters_button": "actionButton",
    "panel_close": "actionButton",
    "panel_clear": "actionButton",
    "panel_background": "shape",
    "panel_title": "textbox",
    "html": HTML_VISUAL,
}

PAGES = add_chrome(PAGES)
