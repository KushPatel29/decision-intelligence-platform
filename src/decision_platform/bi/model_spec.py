"""What the Corridor Power BI semantic model contains: tables, relationships and measures.

Every table is a CSV the pipeline writes to `powerbi/data/` from the same verified
outputs the app serves. Measures only sum, count or divide those columns; the
analysis itself (models, optimizer, truth-based evaluation) happens once, in Python,
and is tested there.
"""

from __future__ import annotations

TABLES: dict[str, dict] = {
    "dim_zone": {"kind": "dimension"},
    "dim_offer": {"kind": "dimension"},
    "dim_period": {"kind": "dimension"},
    "plan_summary": {"kind": "snapshot"},
    "plan_contacts": {"kind": "fact"},
    "customer_segments": {"kind": "fact"},
    "zone_capacity": {"kind": "fact"},
    "monthly_trips": {"kind": "fact"},
    "policy_comparison": {"kind": "snapshot"},
    "budget_frontier": {"kind": "snapshot"},
    "guardrails": {"kind": "snapshot"},
    "experiment_effects": {"kind": "fact"},
    "sequential_looks": {"kind": "fact"},
    "learner_comparison": {"kind": "fact"},
    "elasticity": {"kind": "fact"},
    "price_scenarios": {"kind": "fact"},
    "price_plan": {"kind": "fact"},
    "hourly_forecast": {"kind": "fact"},
    "demand_backtest": {"kind": "fact"},
    "feed_quality": {"kind": "fact"},
    "feature_drift": {"kind": "snapshot"},
    "model_quality": {"kind": "snapshot"},
    "quality_gate": {"kind": "snapshot"},
}

SORT_BY: dict[str, dict[str, str]] = {
    "dim_zone": {"zone_name": "zone_order"},
    "dim_offer": {"offer_name": "offer_order"},
    "dim_period": {"period": "period_order"},
    "monthly_trips": {"month_label": "month_index"},
    "policy_comparison": {"policy": "policy_order"},
    "customer_segments": {"rfm_segment": "segment_order"},
}

DATE_COLUMNS = {"day", "date"}

ROW_RATIOS = {
    "share_of_oracle",
    "load",
    "variance_reduction",
    "enrollment_rate",
    "value_spearman",
    "trips_spearman",
    "psi",
    "auc",
    "pr_auc",
    "brier",
    "ece",
    "elasticity",
    "ci_low",
    "ci_high",
    "ols_elasticity",
    "demand_index",
    "revenue_index",
    "price_change",
    "p_adjusted",
    "z",
    "boundary",
    "volume_z",
    "shadow_price",
    "marginal_value_per_dollar",
}

RELATIONSHIPS: list[tuple[str, str, str, str]] = [
    ("plan_contacts", "offer_id", "dim_offer", "offer_id"),
    ("plan_contacts", "zone_id", "dim_zone", "zone_id"),
    ("customer_segments", "zone_id", "dim_zone", "zone_id"),
    ("zone_capacity", "zone_id", "dim_zone", "zone_id"),
    ("zone_capacity", "period", "dim_period", "period"),
    ("elasticity", "zone_id", "dim_zone", "zone_id"),
    ("elasticity", "period", "dim_period", "period"),
    ("price_scenarios", "zone_id", "dim_zone", "zone_id"),
    ("price_scenarios", "period", "dim_period", "period"),
    ("price_plan", "zone_id", "dim_zone", "zone_id"),
    ("price_plan", "period", "dim_period", "period"),
    ("hourly_forecast", "zone_id", "dim_zone", "zone_id"),
    ("hourly_forecast", "period", "dim_period", "period"),
    ("demand_backtest", "period", "dim_period", "period"),
    ("experiment_effects", "offer_id", "dim_offer", "offer_id"),
    ("learner_comparison", "offer_id", "dim_offer", "offer_id"),
]

UNRELATED: dict[str, str] = {
    "plan_summary": "One row: the plan's guardrails and certificate.",
    "monthly_trips": "Network history by month, before the decision date.",
    "policy_comparison": "One row per targeting approach, scored against the simulator's truth.",
    "budget_frontier": "One row per budget level the optimizer was re-solved at.",
    "guardrails": "One row per constraint with its LP shadow price.",
    "sequential_looks": "One row per arm and interim look.",
    "feed_quality": "One row per ingestion day of the bronze trip feed.",
    "feature_drift": "One row per model feature.",
    "model_quality": "One row per customer model.",
    "quality_gate": "One row per release acceptance check.",
}

MONEY = "\\$#,0"
MONEY_2 = "\\$#,0.00"
COUNT = "#,0"
DEC_1 = "#,0.0"
DEC_2 = "#,0.00"
PCT = "0.0%"
PCT_0 = "0%"
RATIO = '0.00"x"'

P, S, C = "plan_contacts", "customer_segments", "zone_capacity"
ORACLE = "Oracle optimum (true effects)"
OPTIMIZED = "Optimized (MIP)"

MEASURES: list[tuple[str, str, str, str, str]] = [
    # --- Plan -------------------------------------------------------------------------------
    (
        "Contacts",
        f"COUNTROWS({P})",
        COUNT,
        "01 Plan",
        "Customers the October plan contacts (one offer each).",
    ),
    (
        "Incentive spend",
        f"SUM({P}[cost])",
        MONEY,
        "01 Plan",
        "Expected incentive cost: discounts on every eligible trip, threshold rewards, points liability and contact cost.",
    ),
    (
        "Expected value",
        f"SUM({P}[expected_value])",
        MONEY,
        "01 Plan",
        "Model-estimated 30-day net contribution after incentives plus discounted days 31-90 margin.",
    ),
    (
        "Expected 30-day net",
        f"SUM({P}[value_30d])",
        MONEY,
        "01 Plan",
        "Model-estimated incremental 30-day net contribution after incentive costs.",
    ),
    (
        "Expected later value",
        f"SUM({P}[later_value])",
        MONEY,
        "01 Plan",
        "Model-estimated incremental margin on days 31-90, discounted.",
    ),
    (
        "Net ROI",
        "DIVIDE([Expected 30-day net], [Incentive spend])",
        PCT_0,
        "01 Plan",
        "30-day net contribution / incentive spend. The plan holds it above a 15% floor.",
    ),
    (
        "Value per incentive dollar",
        "DIVIDE([Expected value], [Incentive spend])",
        RATIO,
        "01 Plan",
        "Expected value created per dollar of incentive.",
    ),
    ("Extra trips", f"SUM({P}[incremental_trips])", COUNT, "01 Plan", "Model-estimated incremental trips."),
    (
        "Extra peak trips",
        f"SUM({P}[trips_peak])",
        COUNT,
        "01 Plan",
        "Incremental peak trips; negative where off-peak offers move commuters out of the peak.",
    ),
    ("Extra off-peak trips", f"SUM({P}[trips_offpeak])", COUNT, "01 Plan", "Incremental off-peak trips."),
    ("Extra weekend trips", f"SUM({P}[trips_weekend])", COUNT, "01 Plan", "Incremental weekend trips."),
    ("Points awarded", f"SUM({P}[points])", COUNT, "01 Plan", "Loyalty points the plan awards."),
    (
        "Mean uncertainty",
        f"AVERAGE({P}[value_sd])",
        MONEY_2,
        "01 Plan",
        "Mean bootstrap standard deviation of the 30-day value estimate per contact.",
    ),
    (
        "Budget",
        "MAX(plan_summary[budget])",
        MONEY,
        "01 Plan",
        "The incentive budget the plan was solved under.",
    ),
    ("Contact limit", "MAX(plan_summary[contact_limit])", COUNT, "01 Plan", "Maximum contacts."),
    (
        "Eligible customers",
        "MAX(plan_summary[eligible_customers])",
        COUNT,
        "01 Plan",
        "Customers with consent, My Account, no past-due balance and an active account.",
    ),
    ("Budget used", "DIVIDE([Incentive spend], [Budget])", PCT_0, "01 Plan", "Incentive spend / budget."),
    (
        "Decision variables",
        "MAX(plan_summary[decision_variables])",
        COUNT,
        "01 Plan",
        "Customer-offer binaries in the mixed-integer program the plan solves.",
    ),
    (
        "Relief value",
        f"SUM({P}[relief_value])",
        MONEY,
        "01 Plan",
        "Congestion-relief value of the net rush-hour trips the plan moves onto the 407 (included in Expected value).",
    ),
    (
        "Rush-hour trips per workday",
        "DIVIDE([Extra peak trips], 22)",
        DEC_1,
        "01 Plan",
        "Net incremental peak trips per workday over a 22-workday month; negative where off-peak offers move "
        "commuters out of the peak.",
    ),
    # --- Customers ----------------------------------------------------------------------------
    ("Customers", f"SUM({S}[customers])", COUNT, "02 Customers", "Customers in the October snapshot."),
    (
        "Customers in plan",
        f"SUM({S}[planned_customers])",
        COUNT,
        "02 Customers",
        "Customers the plan contacts.",
    ),
    (
        "Share in plan",
        "DIVIDE([Customers in plan], [Customers])",
        PCT,
        "02 Customers",
        "Customers in the plan / all customers.",
    ),
    (
        "Mean travel propensity",
        f"DIVIDE(SUM({S}[sum_propensity]), [Customers])",
        PCT,
        "02 Customers",
        "Mean calibrated probability of travelling in the next 30 days.",
    ),
    (
        "Mean inactivity risk",
        f"DIVIDE(SUM({S}[sum_churn]), SUM({S}[active_customers]))",
        PCT,
        "02 Customers",
        "Mean 90-day inactivity probability among historically active customers.",
    ),
    (
        "High-risk customers",
        f"SUM({S}[high_risk_customers])",
        COUNT,
        "02 Customers",
        "Historically active customers with inactivity probability above 50%.",
    ),
    (
        "Mean projected value",
        f"DIVIDE(SUM({S}[sum_clv]), [Customers])",
        MONEY,
        "02 Customers",
        "Mean heuristic 12-month projected contribution.",
    ),
    (
        "Mean best-offer value",
        f"DIVIDE(SUM({S}[sum_best_value]), [Customers])",
        MONEY_2,
        "02 Customers",
        "Mean modelled value of each customer's best offer.",
    ),
    # --- Capacity -----------------------------------------------------------------------------
    (
        "Forecast trips",
        f"SUM({C}[baseline_forecast])",
        COUNT,
        "03 Capacity",
        "30-day baseline demand forecast.",
    ),
    ("Campaign trips", f"SUM({C}[campaign_trips])", COUNT, "03 Capacity", "Signed trips the plan adds."),
    (
        "Safety reserve",
        f"SUM({C}[reserve_trips])",
        COUNT,
        "03 Capacity",
        "Trips held back as a 20% demand reserve.",
    ),
    (
        "Planning capacity",
        f"SUM({C}[capacity_trips])",
        COUNT,
        "03 Capacity",
        "Planning capacity over the period's operating days.",
    ),
    (
        "Load",
        "DIVIDE([Forecast trips] + [Campaign trips], [Planning capacity])",
        PCT,
        "03 Capacity",
        "Forecast plus campaign trips / capacity.",
    ),
    (
        "Free after campaign",
        f"SUM({C}[free_after_campaign])",
        COUNT,
        "03 Capacity",
        "Trips of capacity left after the reserve and the campaign.",
    ),
    (
        "Monthly trips",
        "SUM(monthly_trips[trips])",
        COUNT,
        "03 Capacity",
        "Trips per month before the decision date.",
    ),
    ("Monthly revenue", "SUM(monthly_trips[revenue])", MONEY, "03 Capacity", "Toll revenue per month."),
    (
        "Hourly forecast trips",
        "SUM(hourly_forecast[forecast_trips])",
        COUNT,
        "03 Capacity",
        "October forecast disaggregated by hour and direction.",
    ),
    (
        "Backtest actual",
        "SUM(demand_backtest[actual])",
        COUNT,
        "03 Capacity",
        "Actual trips on held-out days.",
    ),
    (
        "Backtest forecast",
        "SUM(demand_backtest[forecast])",
        COUNT,
        "03 Capacity",
        "Forecast made 1-30 days ahead for the same days.",
    ),
    # --- Policy value -------------------------------------------------------------------------
    (
        "True value",
        "SUM(policy_comparison[true_value])",
        MONEY,
        "04 Policy value",
        "Simulator-true expected value of the approach's chosen customer-offer pairs.",
    ),
    (
        "Predicted value",
        "SUM(policy_comparison[predicted_value])",
        MONEY,
        "04 Policy value",
        "What the models predicted the same pairs were worth.",
    ),
    (
        "Winner's curse",
        "[Predicted value] - [True value]",
        MONEY,
        "04 Policy value",
        "Predicted minus true: how much the selected customers' value was overestimated.",
    ),
    (
        "Value ceiling",
        f'CALCULATE([True value], REMOVEFILTERS(policy_comparison), policy_comparison[policy] = "{ORACLE}")',
        MONEY,
        "04 Policy value",
        "True value of the same MIP solved on the true effects: the achievable ceiling.",
    ),
    (
        "Share of ceiling",
        "DIVIDE([True value], [Value ceiling])",
        PCT_0,
        "04 Policy value",
        "True value / ceiling.",
    ),
    (
        "Optimized true value",
        f'CALCULATE([True value], REMOVEFILTERS(policy_comparison), policy_comparison[policy] = "{OPTIMIZED}")',
        MONEY,
        "04 Policy value",
        "True value of the production plan.",
    ),
    (
        "Propensity true value",
        'CALCULATE([True value], REMOVEFILTERS(policy_comparison), LEFT(policy_comparison[policy], 10) = "Propensity")',
        MONEY,
        "04 Policy value",
        "True value of giving 10% off to the highest-propensity travellers.",
    ),
    (
        "Contacts losing money",
        "SUM(policy_comparison[customers_losing_money])",
        COUNT,
        "04 Policy value",
        "Contacts whose offer truly destroys value.",
    ),
    (
        "Frontier value",
        "SUM(budget_frontier[expected_value])",
        MONEY,
        "04 Policy value",
        "Optimal expected value at each budget level.",
    ),
    (
        "Frontier marginal value",
        "AVERAGE(budget_frontier[marginal_value_per_dollar])",
        RATIO,
        "04 Policy value",
        "Extra expected value per extra budget dollar between budget levels.",
    ),
    (
        "Shadow price",
        "SUM(guardrails[shadow_price])",
        MONEY_2,
        "04 Policy value",
        "LP dual: value of relaxing a guardrail by one unit.",
    ),
    # --- Experiments --------------------------------------------------------------------------
    (
        "Trial value effect",
        "SUM(experiment_effects[value_effect])",
        MONEY_2,
        "05 Experiments",
        "CUPED-adjusted 30-day net contribution per randomised customer, arm vs control.",
    ),
    (
        "Trial value low",
        "SUM(experiment_effects[value_low])",
        MONEY_2,
        "05 Experiments",
        "Bonferroni 95% lower bound.",
    ),
    (
        "Trial value high",
        "SUM(experiment_effects[value_high])",
        MONEY_2,
        "05 Experiments",
        "Bonferroni 95% upper bound.",
    ),
    (
        "Trial trips effect",
        "SUM(experiment_effects[trips_effect])",
        DEC_2,
        "05 Experiments",
        "CUPED-adjusted incremental trips per randomised customer.",
    ),
    (
        "CUPED variance removed",
        "AVERAGE(experiment_effects[variance_reduction])",
        PCT_0,
        "05 Experiments",
        "Share of outcome variance removed by the pre-period covariate.",
    ),
    ("Customers per arm", "MIN(experiment_effects[n])", COUNT, "05 Experiments", "Smallest arm size."),
    ("Sequential z", "SUM(sequential_looks[z])", DEC_2, "05 Experiments", "Cumulative CUPED z-statistic."),
    (
        "Efficacy boundary",
        "AVERAGE(sequential_looks[boundary])",
        DEC_2,
        "05 Experiments",
        "O'Brien-Fleming boundary at the look.",
    ),
    (
        "Learner rank correlation",
        "AVERAGE(learner_comparison[value_spearman])",
        "0.00",
        "05 Experiments",
        "Rank correlation between a learner's value estimates and the true values (simulation check).",
    ),
    (
        "Learner Qini",
        "AVERAGE(learner_comparison[qini])",
        "0.00",
        "05 Experiments",
        "Held-out Qini on observed outcomes.",
    ),
    # --- Pricing ------------------------------------------------------------------------------
    (
        "Elasticity",
        "AVERAGE(elasticity[elasticity])",
        "0.00",
        "06 Pricing",
        "Empirical-Bayes price elasticity of demand.",
    ),
    ("Elasticity low", "AVERAGE(elasticity[ci_low])", "0.00", "06 Pricing", "95% interval, lower."),
    ("Elasticity high", "AVERAGE(elasticity[ci_high])", "0.00", "06 Pricing", "95% interval, upper."),
    (
        "Demand index",
        "AVERAGE(price_scenarios[demand_index])",
        DEC_1,
        "06 Pricing",
        "Demand at the price change, baseline = 100.",
    ),
    (
        "Revenue index",
        "AVERAGE(price_scenarios[revenue_index])",
        DEC_1,
        "06 Pricing",
        "Revenue at the price change, baseline = 100.",
    ),
    (
        "Price contribution change",
        "SUM(price_plan[contribution_change])",
        MONEY,
        "06 Pricing",
        "Contribution change from the jointly optimized prices.",
    ),
    (
        "Cells repriced",
        "COUNTROWS(FILTER(price_plan, price_plan[price_change] <> 0))",
        COUNT,
        "06 Pricing",
        "Zone-period cells whose optimal price differs from baseline.",
    ),
    # --- Operations ---------------------------------------------------------------------------
    ("Feed rows", "SUM(feed_quality[rows])", COUNT, "07 Operations", "Bronze trip rows ingested per day."),
    (
        "Expected feed rows",
        "SUM(feed_quality[expected_rows])",
        COUNT,
        "07 Operations",
        "Median of the same weekday over the previous four weeks.",
    ),
    (
        "Flagged days",
        "COUNTROWS(FILTER(feed_quality, feed_quality[flagged]))",
        COUNT,
        "07 Operations",
        "Ingestion days the monitor flagged.",
    ),
    ("Mean PSI", "AVERAGE(feature_drift[psi])", "0.000", "07 Operations", "Mean population stability index."),
    (
        "Features to review",
        "COUNTROWS(FILTER(feature_drift, feature_drift[psi] > 0.2))",
        COUNT,
        "07 Operations",
        "Features with PSI above 0.2.",
    ),
    ("Model AUC", "AVERAGE(model_quality[auc])", "0.000", "07 Operations", "Held-out ROC-AUC."),
    (
        "Checks passed",
        "COUNTROWS(FILTER(quality_gate, quality_gate[passed]))",
        COUNT,
        "07 Operations",
        "Release acceptance checks passed.",
    ),
    ("Checks total", "COUNTROWS(quality_gate)", COUNT, "07 Operations", "Release acceptance checks."),
]

# Colours returned by a measure; bound through a wildcard data-point selector.
HIGHLIGHT, MUTED_BAR, ALERT = "#3987e5", "#5b7486", "#e66767"
MEASURES += [
    (
        "Approach colour",
        f'SWITCH(SELECTEDVALUE(policy_comparison[policy]), "{OPTIMIZED}", "{HIGHLIGHT}", "{ORACLE}", "#86b6ef", '
        f'"{MUTED_BAR}")',
        "",
        "09 Colours",
        "Blue for the production plan, light blue for the ceiling, grey otherwise.",
    ),
    (
        "Effect colour",
        f'IF([Trial value effect] < 0, "{ALERT}", "{HIGHLIGHT}")',
        "",
        "09 Colours",
        "Red where an offer loses money on the average randomised customer.",
    ),
    (
        "Load colour",
        f'IF([Load] >= 0.8, "#c98500", "{HIGHLIGHT}")',
        "",
        "09 Colours",
        "Amber where a cell runs at 80% of capacity or more.",
    ),
    (
        "Check colour",
        f'IF([Checks passed] < [Checks total], "{ALERT}", "{HIGHLIGHT}")',
        "",
        "09 Colours",
        "Red if any acceptance check fails.",
    ),
]

# Tile captions: a sentence about the figure, built from measures.
MEASURES += [
    (
        "Spend caption",
        'FORMAT([Budget used], "0%") & " of the " & FORMAT([Budget], "$#,0") & " budget"',
        "",
        "08 Captions",
        "Tile caption: budget used.",
    ),
    (
        "Contacts caption",
        'FORMAT(DIVIDE([Contacts], [Eligible customers]), "0%") & " of " & FORMAT([Eligible customers], "#,0") '
        '& " eligible customers"',
        "",
        "08 Captions",
        "Tile caption: contacts against eligible customers.",
    ),
    (
        "Value caption",
        'FORMAT([Value per incentive dollar], "0.0") & "x the incentive spend"',
        "",
        "08 Captions",
        "Tile caption: value per incentive dollar.",
    ),
    (
        "ROI caption",
        '"30-day net " & FORMAT([Expected 30-day net], "$#,0") & " · floor 15%"',
        "",
        "08 Captions",
        "Tile caption: 30-day net contribution.",
    ),
    (
        "Truth caption",
        'FORMAT(DIVIDE([Optimized true value], [Value ceiling]), "0%") & " of the " & FORMAT([Value ceiling], "$#,0") '
        '& " ceiling"',
        "",
        "08 Captions",
        "Tile caption: share of the ceiling.",
    ),
    (
        "Propensity caption",
        'FORMAT(DIVIDE([Propensity true value], [Value ceiling]), "0%") & " of the ceiling"',
        "",
        "08 Captions",
        "Tile caption: propensity targeting against the ceiling.",
    ),
    (
        "Load caption",
        'FORMAT([Free after campaign], "#,0") & " trips free after the reserve"',
        "",
        "08 Captions",
        "Tile caption: capacity left.",
    ),
    (
        "Peak caption",
        'FORMAT([Extra off-peak trips], "#,0") & " off-peak and " & FORMAT([Extra weekend trips], "#,0") '
        '& " weekend"',
        "",
        "08 Captions",
        "Tile caption: where the extra trips land.",
    ),
    (
        "Risk caption",
        'FORMAT([High-risk customers], "#,0") & " above 50% inactivity risk"',
        "",
        "08 Captions",
        "Tile caption: high-risk customers.",
    ),
    (
        "Gate caption",
        'FORMAT([Checks passed], "0") & " of " & FORMAT([Checks total], "0") & " checks passed"',
        "",
        "08 Captions",
        "Tile caption: acceptance checks.",
    ),
    (
        "Drift caption",
        'FORMAT([Features to review], "0") & " features above PSI 0.2"',
        "",
        "08 Captions",
        "Tile caption: drift review count.",
    ),
    (
        "Feed caption",
        'FORMAT([Flagged days], "0") & " ingestion days flagged"',
        "",
        "08 Captions",
        "Tile caption: feed anomalies.",
    ),
    (
        "Elasticity caption",
        '"95% interval " & FORMAT([Elasticity low], "0.00") & " to " & FORMAT([Elasticity high], "0.00")',
        "",
        "08 Captions",
        "Tile caption: elasticity interval.",
    ),
    (
        "Trial caption",
        'FORMAT([Customers per arm], "#,0") & " customers per arm, 10 arms"',
        "",
        "08 Captions",
        "Tile caption: trial size.",
    ),
]

MEASURES.append(
    (
        "Executive summary",
        (
            "VAR vValue = [Expected value]\n"
            "VAR vSpend = [Incentive spend]\n"
            "VAR vTrue = [Optimized true value]\n"
            "VAR vCeiling = [Value ceiling]\n"
            "VAR vPropensity = [Propensity true value]\n"
            "RETURN\n"
            '    "The October plan contacts " & FORMAT([Contacts], "#,0") & " of " & FORMAT([Eligible customers], "#,0")\n'
            '        & " eligible customers for " & FORMAT(vSpend, "$#,0") & " of incentives. The models expect "\n'
            '        & FORMAT(vValue, "$#,0") & "; scored against the simulator\'s true responses it creates "\n'
            '        & FORMAT(vTrue, "$#,0") & ", " & FORMAT(DIVIDE(vTrue, vCeiling), "0%")\n'
            '        & " of what a perfectly informed planner could reach. Giving 10% off to the most frequent travellers "\n'
            '        & "would create " & FORMAT(vPropensity, "$#,0") & ": the customers most likely to travel are not the "\n'
            '        & "ones an offer moves. The plan also moves a net " & FORMAT([Rush-hour trips per workday], "#,0")\n'
            '        & " rush-hour trips per workday onto the 407, worth " & FORMAT([Relief value], "$#,0")\n'
            '        & " in congestion relief at the planning rate."'
        ),
        "",
        "10 Narrative",
        "One-paragraph summary of the plan and its truth-based evaluation, built from the measures.",
    )
)


def measure_names() -> set[str]:
    return {name for name, *_ in MEASURES}
