"""What the Corridor report contains: eight pages, and every visual on them.

Each page answers one question a planning team would ask about the October plan,
from the same verified outputs the app serves.

Fields are written ``table[column]`` for a column and ``[Measure]`` for a measure.
"""

from __future__ import annotations

from decision_platform.bi.report_chrome import add_chrome

CARD_Y, CARD_H = 20, 118
ROW1_Y, ROW2_Y = 152, 442
CARDS = ((20, 300), (330, 296), (634, 300), (942, 318))
CARDS_3 = ((20, 404), (438, 404), (856, 404))
SLICER = (1068, 192, 76)


def cards(*specs: dict) -> list[dict]:
    slots = CARDS if len(specs) == 4 else CARDS_3
    return [
        {"type": "card", "pos": (x, CARD_Y, width, CARD_H), **spec} for (x, width), spec in zip(slots, specs)
    ]


def tile(
    field: str, alt: str, *, subtitle: str | None = None, label: str | None = None, rail: bool = True
) -> dict:
    spec: dict[str, object] = {"field": field, "alt": alt}
    if subtitle:
        spec["subtitle"] = subtitle
    if label:
        spec["label"] = label
    if not rail:
        spec["rail"] = False
    return spec


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

PAGES: list[dict] = [
    {
        "name": "p1_plan",
        "display": "October plan",
        "visuals": [
            *cards(
                tile(
                    "[Expected value]",
                    "Card. Expected value of the October plan.",
                    subtitle="[Value caption]",
                ),
                tile(
                    "[Incentive spend]",
                    "Card. Incentive spend against the budget.",
                    subtitle="[Spend caption]",
                ),
                tile("[Contacts]", "Card. Customers contacted.", subtitle="[Contacts caption]"),
                tile("[Net ROI]", "Card. 30-day net ROI of the plan.", subtitle="[ROI caption]", rail=False),
            ),
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
            *cards(
                tile(
                    "[Extra trips]",
                    "Card. Extra trips the plan is expected to create.",
                    subtitle="[Peak caption]",
                ),
                tile("[Points awarded]", "Card. Loyalty points the plan awards."),
                tile("[Mean uncertainty]", "Card. Mean bootstrap standard deviation per contact."),
                tile("[Budget used]", "Card. Share of the budget used.", subtitle="[Spend caption]"),
            ),
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
            *cards(
                tile("[Customers]", "Card. Customers in the October snapshot."),
                tile("[Mean travel propensity]", "Card. Mean probability of travelling in the next 30 days."),
                tile(
                    "[Mean inactivity risk]", "Card. Mean 90-day inactivity risk.", subtitle="[Risk caption]"
                ),
                tile("[Share in plan]", "Card. Share of customers in the plan."),
            ),
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
            {
                "type": "table",
                "columns": [
                    "customer_segments[rfm_segment]",
                    "[Customers]",
                    "[Mean travel propensity]",
                    "[Mean inactivity risk]",
                    "[Mean projected value]",
                    "[Mean best-offer value]",
                    "[Share in plan]",
                ],
                "sort": ("customer_segments[rfm_segment]", "Ascending"),
                "title": "Segments: risk, value and what the plan does with them",
                "pos": (20, ROW2_Y, 1044, 258),
                "alt": "Table titled Segments. Lists segment, Customers, Mean travel propensity, Mean inactivity "
                "risk, Mean projected value, Mean best-offer value and Share in plan.",
            },
            *slicers(ZONE, ("customer_segments[tier]", "Loyalty tier")),
        ],
    },
    {
        "name": "p4_capacity",
        "display": "Transportation and capacity",
        "visuals": [
            *cards(
                tile("[Forecast trips]", "Card. 30-day baseline demand forecast."),
                tile("[Campaign trips]", "Card. Signed trips the campaign adds.", subtitle="[Peak caption]"),
                tile(
                    "[Load]", "Card. Forecast plus campaign trips over capacity.", subtitle="[Load caption]"
                ),
                tile("[Planning capacity]", "Card. Planning capacity over the window."),
            ),
            {
                "type": "matrix",
                "rows": "dim_zone[zone_name]",
                "columns_by": "dim_period[period]",
                "values": ["[Load]"],
                "totals": False,
                "title": "Load by zone and travel period, with the campaign",
                "pos": (20, ROW1_Y, 620, 272),
                "alt": "Matrix titled Load by zone and travel period. Shows Load by zone name and period.",
            },
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
            *cards(
                tile(
                    "[Elasticity]",
                    "Card. Mean price elasticity.",
                    subtitle="[Elasticity caption]",
                    rail=False,
                ),
                tile("[Price contribution change]", "Card. Contribution change from the optimized prices."),
                tile("[Cells repriced]", "Card. Zone-period cells whose optimal price changes."),
            ),
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
            *cards(
                tile("[Customers per arm]", "Card. Customers per trial arm.", subtitle="[Trial caption]"),
                tile("[CUPED variance removed]", "Card. Variance removed by CUPED."),
                tile(
                    "[Learner rank correlation]",
                    "Card. Mean rank correlation of causal learners with the truth.",
                    rail=False,
                ),
            ),
            {
                "type": "bar",
                "x": "dim_offer[offer_name]",
                "y": ["[Trial value effect]"],
                "color": "[Effect colour]",
                "sort": ("[Trial value effect]", "Descending"),
                "title": "30-day net contribution per randomised customer (CUPED; red: loses money)",
                "pos": (20, ROW1_Y, 620, 272),
                "alt": "Bar chart titled 30-day net contribution per randomised customer. Plots Trial value effect by "
                "offer; negative effects are red.",
            },
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
            *cards(
                tile(
                    "[Optimized true value]",
                    "Card. True value of the optimized plan.",
                    subtitle="[Truth caption]",
                    label="Optimized plan · true value",
                ),
                tile(
                    "[Value ceiling]",
                    "Card. Value of the plan with perfect knowledge.",
                    label="Ceiling · perfect knowledge",
                ),
                tile(
                    "[Propensity true value]",
                    "Card. True value of propensity targeting.",
                    subtitle="[Propensity caption]",
                    label="Propensity targeting · true value",
                ),
            ),
            {
                "type": "bar",
                "x": "policy_comparison[policy]",
                "y": ["[Predicted value]", "[True value]"],
                "sort": ("policy_comparison[policy]", "Ascending"),
                "title": "Predicted against true value, by approach",
                "pos": (20, ROW1_Y, 760, 272),
                "alt": "Bar chart titled Predicted against true value. Plots Predicted value and True value by approach.",
            },
            {
                "type": "table",
                "columns": ["guardrails[constraint_label]", "guardrails[limit]", "[Shadow price]"],
                "totals": False,
                "sort": ("[Shadow price]", "Descending"),
                "title": "Binding guardrails: value of one more unit",
                "pos": (794, ROW1_Y, 466, 272),
                "alt": "Table titled Binding guardrails. Lists guardrail, limit and Shadow price.",
            },
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
            *cards(
                tile(
                    "[Checks passed]",
                    "Card. Release acceptance checks passed.",
                    subtitle="[Gate caption]",
                    rail=False,
                ),
                tile("[Model AUC]", "Card. Mean held-out AUC of the customer models.", rail=False),
                tile("[Flagged days]", "Card. Feed ingestion days flagged.", subtitle="[Feed caption]"),
                tile(
                    "[Features to review]",
                    "Card. Features above the drift threshold.",
                    subtitle="[Drift caption]",
                ),
            ),
            {
                "type": "line",
                "x": "feed_quality[day]",
                "y": ["[Feed rows]", "[Expected feed rows]"],
                "sort": ("feed_quality[day]", "Ascending"),
                "title": "Bronze trip feed: rows ingested against the same-weekday expectation",
                "pos": (20, ROW1_Y, 760, 272),
                "alt": "Line chart titled Bronze trip feed. Plots Feed rows and Expected feed rows by day.",
            },
            {
                "type": "table",
                "columns": ["quality_gate[check_name]", "quality_gate[passed]", "quality_gate[criteria]"],
                "totals": False,
                "title": "Release acceptance gate",
                "pos": (794, ROW1_Y, 466, 272),
                "alt": "Table titled Release acceptance gate. Lists check, passed and criteria.",
            },
            {
                "type": "bar",
                "x": "feature_drift[feature]",
                "y": ["[Mean PSI]"],
                "sort": ("[Mean PSI]", "Descending"),
                "title": "Feature drift (PSI), January to October 2025",
                "pos": (20, ROW2_Y, 620, 258),
                "alt": "Bar chart titled Feature drift. Plots Mean PSI by feature.",
            },
            {
                "type": "table",
                "columns": [
                    "model_quality[model]",
                    "model_quality[champion]",
                    "model_quality[auc]",
                    "model_quality[brier]",
                    "model_quality[ece]",
                ],
                "totals": False,
                "title": "Customer models on the July 2025 test fold",
                "pos": (654, ROW2_Y, 410, 258),
                "alt": "Table titled Customer models. Lists model, champion, AUC, Brier and ECE.",
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
}

PAGES = add_chrome(PAGES)
