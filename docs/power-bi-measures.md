# Power BI measures

Generated from `src/decision_platform/bi/model_spec.py` by `python -m decision_platform.bi.build_pbip`; do not edit by hand.
91 business measures in 10 display folders. The report's own SVG tile, header and button measures live in the *Report UI* folder and are not listed.


## 01 Plan

| Measure | Definition | Format | DAX |
|---|---|---|---|
| Contacts | Customers the October plan contacts (one offer each). | `#,0` | `COUNTROWS(plan_contacts)` |
| Incentive spend | Expected incentive cost: discounts on every eligible trip, threshold rewards, points liability and contact cost. | `\$#,0` | `SUM(plan_contacts[cost])` |
| Expected value | Model-estimated 30-day net contribution after incentives plus discounted days 31-90 margin. | `\$#,0` | `SUM(plan_contacts[expected_value])` |
| Expected 30-day net | Model-estimated incremental 30-day net contribution after incentive costs. | `\$#,0` | `SUM(plan_contacts[value_30d])` |
| Expected later value | Model-estimated incremental margin on days 31-90, discounted. | `\$#,0` | `SUM(plan_contacts[later_value])` |
| Net ROI | 30-day net contribution / incentive spend. The plan holds it above a 15% floor. | `0%` | `DIVIDE([Expected 30-day net], [Incentive spend])` |
| Value per incentive dollar | Expected value created per dollar of incentive. | `0.00"x"` | `DIVIDE([Expected value], [Incentive spend])` |
| Extra trips | Model-estimated incremental trips. | `#,0` | `SUM(plan_contacts[incremental_trips])` |
| Extra peak trips | Incremental peak trips; negative where off-peak offers move commuters out of the peak. | `#,0` | `SUM(plan_contacts[trips_peak])` |
| Extra off-peak trips | Incremental off-peak trips. | `#,0` | `SUM(plan_contacts[trips_offpeak])` |
| Extra weekend trips | Incremental weekend trips. | `#,0` | `SUM(plan_contacts[trips_weekend])` |
| Points awarded | Loyalty points the plan awards. | `#,0` | `SUM(plan_contacts[points])` |
| Mean uncertainty | Mean bootstrap standard deviation of the 30-day value estimate per contact. | `\$#,0.00` | `AVERAGE(plan_contacts[value_sd])` |
| Budget | The incentive budget the plan was solved under. | `\$#,0` | `MAX(plan_summary[budget])` |
| Contact limit | Maximum contacts. | `#,0` | `MAX(plan_summary[contact_limit])` |
| Eligible customers | Customers with consent, My Account, no past-due balance and an active account. | `#,0` | `MAX(plan_summary[eligible_customers])` |
| Budget used | Incentive spend / budget. | `0%` | `DIVIDE([Incentive spend], [Budget])` |

## 02 Customers

| Measure | Definition | Format | DAX |
|---|---|---|---|
| Customers | Customers in the October snapshot. | `#,0` | `SUM(customer_segments[customers])` |
| Customers in plan | Customers the plan contacts. | `#,0` | `SUM(customer_segments[planned_customers])` |
| Share in plan | Customers in the plan / all customers. | `0.0%` | `DIVIDE([Customers in plan], [Customers])` |
| Mean travel propensity | Mean calibrated probability of travelling in the next 30 days. | `0.0%` | `DIVIDE(SUM(customer_segments[sum_propensity]), [Customers])` |
| Mean inactivity risk | Mean 90-day inactivity probability among historically active customers. | `0.0%` | `DIVIDE(SUM(customer_segments[sum_churn]), SUM(customer_segments[active_customers]))` |
| High-risk customers | Historically active customers with inactivity probability above 50%. | `#,0` | `SUM(customer_segments[high_risk_customers])` |
| Mean projected value | Mean heuristic 12-month projected contribution. | `\$#,0` | `DIVIDE(SUM(customer_segments[sum_clv]), [Customers])` |
| Mean best-offer value | Mean modelled value of each customer's best offer. | `\$#,0.00` | `DIVIDE(SUM(customer_segments[sum_best_value]), [Customers])` |

## 03 Capacity

| Measure | Definition | Format | DAX |
|---|---|---|---|
| Forecast trips | 30-day baseline demand forecast. | `#,0` | `SUM(zone_capacity[baseline_forecast])` |
| Campaign trips | Signed trips the plan adds. | `#,0` | `SUM(zone_capacity[campaign_trips])` |
| Safety reserve | Trips held back as a 20% demand reserve. | `#,0` | `SUM(zone_capacity[reserve_trips])` |
| Planning capacity | Planning capacity over the period's operating days. | `#,0` | `SUM(zone_capacity[capacity_trips])` |
| Load | Forecast plus campaign trips / capacity. | `0.0%` | `DIVIDE([Forecast trips] + [Campaign trips], [Planning capacity])` |
| Free after campaign | Trips of capacity left after the reserve and the campaign. | `#,0` | `SUM(zone_capacity[free_after_campaign])` |
| Monthly trips | Trips per month before the decision date. | `#,0` | `SUM(monthly_trips[trips])` |
| Monthly revenue | Toll revenue per month. | `\$#,0` | `SUM(monthly_trips[revenue])` |
| Hourly forecast trips | October forecast disaggregated by hour and direction. | `#,0` | `SUM(hourly_forecast[forecast_trips])` |
| Backtest actual | Actual trips on held-out days. | `#,0` | `SUM(demand_backtest[actual])` |
| Backtest forecast | Forecast made 1-30 days ahead for the same days. | `#,0` | `SUM(demand_backtest[forecast])` |

## 04 Policy value

| Measure | Definition | Format | DAX |
|---|---|---|---|
| True value | Simulator-true expected value of the approach's chosen customer-offer pairs. | `\$#,0` | `SUM(policy_comparison[true_value])` |
| Predicted value | What the models predicted the same pairs were worth. | `\$#,0` | `SUM(policy_comparison[predicted_value])` |
| Winner's curse | Predicted minus true: how much the selected customers' value was overestimated. | `\$#,0` | `[Predicted value] - [True value]` |
| Value ceiling | True value of the same MIP solved on the true effects: the achievable ceiling. | `\$#,0` | `CALCULATE([True value], REMOVEFILTERS(policy_comparison), policy_comparison[policy] = "Oracle optimum (true effects)")` |
| Share of ceiling | True value / ceiling. | `0%` | `DIVIDE([True value], [Value ceiling])` |
| Optimized true value | True value of the production plan. | `\$#,0` | `CALCULATE([True value], REMOVEFILTERS(policy_comparison), policy_comparison[policy] = "Optimized (MIP)")` |
| Propensity true value | True value of giving 10% off to the highest-propensity travellers. | `\$#,0` | `CALCULATE([True value], REMOVEFILTERS(policy_comparison), LEFT(policy_comparison[policy], 10) = "Propensity")` |
| Contacts losing money | Contacts whose offer truly destroys value. | `#,0` | `SUM(policy_comparison[customers_losing_money])` |
| Frontier value | Optimal expected value at each budget level. | `\$#,0` | `SUM(budget_frontier[expected_value])` |
| Frontier marginal value | Extra expected value per extra budget dollar between budget levels. | `0.00"x"` | `AVERAGE(budget_frontier[marginal_value_per_dollar])` |
| Shadow price | LP dual: value of relaxing a guardrail by one unit. | `\$#,0.00` | `SUM(guardrails[shadow_price])` |

## 05 Experiments

| Measure | Definition | Format | DAX |
|---|---|---|---|
| Trial value effect | CUPED-adjusted 30-day net contribution per randomised customer, arm vs control. | `\$#,0.00` | `SUM(experiment_effects[value_effect])` |
| Trial value low | Bonferroni 95% lower bound. | `\$#,0.00` | `SUM(experiment_effects[value_low])` |
| Trial value high | Bonferroni 95% upper bound. | `\$#,0.00` | `SUM(experiment_effects[value_high])` |
| Trial trips effect | CUPED-adjusted incremental trips per randomised customer. | `#,0.00` | `SUM(experiment_effects[trips_effect])` |
| CUPED variance removed | Share of outcome variance removed by the pre-period covariate. | `0%` | `AVERAGE(experiment_effects[variance_reduction])` |
| Customers per arm | Smallest arm size. | `#,0` | `MIN(experiment_effects[n])` |
| Sequential z | Cumulative CUPED z-statistic. | `#,0.00` | `SUM(sequential_looks[z])` |
| Efficacy boundary | O'Brien-Fleming boundary at the look. | `#,0.00` | `AVERAGE(sequential_looks[boundary])` |
| Learner rank correlation | Rank correlation between a learner's value estimates and the true values (simulation check). | `0.00` | `AVERAGE(learner_comparison[value_spearman])` |
| Learner Qini | Held-out Qini on observed outcomes. | `0.00` | `AVERAGE(learner_comparison[qini])` |

## 06 Pricing

| Measure | Definition | Format | DAX |
|---|---|---|---|
| Elasticity | Empirical-Bayes price elasticity of demand. | `0.00` | `AVERAGE(elasticity[elasticity])` |
| Elasticity low | 95% interval, lower. | `0.00` | `AVERAGE(elasticity[ci_low])` |
| Elasticity high | 95% interval, upper. | `0.00` | `AVERAGE(elasticity[ci_high])` |
| Demand index | Demand at the price change, baseline = 100. | `#,0.0` | `AVERAGE(price_scenarios[demand_index])` |
| Revenue index | Revenue at the price change, baseline = 100. | `#,0.0` | `AVERAGE(price_scenarios[revenue_index])` |
| Price contribution change | Contribution change from the jointly optimized prices. | `\$#,0` | `SUM(price_plan[contribution_change])` |
| Cells repriced | Zone-period cells whose optimal price differs from baseline. | `#,0` | `COUNTROWS(FILTER(price_plan, price_plan[price_change] <> 0))` |

## 07 Operations

| Measure | Definition | Format | DAX |
|---|---|---|---|
| Feed rows | Bronze trip rows ingested per day. | `#,0` | `SUM(feed_quality[rows])` |
| Expected feed rows | Median of the same weekday over the previous four weeks. | `#,0` | `SUM(feed_quality[expected_rows])` |
| Flagged days | Ingestion days the monitor flagged. | `#,0` | `COUNTROWS(FILTER(feed_quality, feed_quality[flagged]))` |
| Mean PSI | Mean population stability index. | `0.000` | `AVERAGE(feature_drift[psi])` |
| Features to review | Features with PSI above 0.2. | `#,0` | `COUNTROWS(FILTER(feature_drift, feature_drift[psi] > 0.2))` |
| Model AUC | Held-out ROC-AUC. | `0.000` | `AVERAGE(model_quality[auc])` |
| Checks passed | Release acceptance checks passed. | `#,0` | `COUNTROWS(FILTER(quality_gate, quality_gate[passed]))` |
| Checks total | Release acceptance checks. | `#,0` | `COUNTROWS(quality_gate)` |

## 09 Colours

| Measure | Definition | Format | DAX |
|---|---|---|---|
| Approach colour | Blue for the production plan, light blue for the ceiling, grey otherwise. | `text` | `SWITCH(SELECTEDVALUE(policy_comparison[policy]), "Optimized (MIP)", "#3987e5", "Oracle optimum (true effects)", "#86b6ef", "#5b7486")` |
| Effect colour | Red where an offer loses money on the average randomised customer. | `text` | `IF([Trial value effect] < 0, "#e66767", "#3987e5")` |
| Load colour | Amber where a cell runs at 80% of capacity or more. | `text` | `IF([Load] >= 0.8, "#c98500", "#3987e5")` |
| Check colour | Red if any acceptance check fails. | `text` | `IF([Checks passed] < [Checks total], "#e66767", "#3987e5")` |

## 08 Captions

| Measure | Definition | Format | DAX |
|---|---|---|---|
| Spend caption | Tile caption: budget used. | `text` | `FORMAT([Budget used], "0%") & " of the " & FORMAT([Budget], "$#,0") & " budget"` |
| Contacts caption | Tile caption: contacts against eligible customers. | `text` | `FORMAT(DIVIDE([Contacts], [Eligible customers]), "0%") & " of " & FORMAT([Eligible customers], "#,0") & " eligible customers"` |
| Value caption | Tile caption: value per incentive dollar. | `text` | `FORMAT([Value per incentive dollar], "0.0") & "x the incentive spend"` |
| ROI caption | Tile caption: 30-day net contribution. | `text` | `"30-day net " & FORMAT([Expected 30-day net], "$#,0") & " · floor 15%"` |
| Truth caption | Tile caption: share of the ceiling. | `text` | `FORMAT(DIVIDE([Optimized true value], [Value ceiling]), "0%") & " of the " & FORMAT([Value ceiling], "$#,0") & " ceiling"` |
| Propensity caption | Tile caption: propensity targeting against the ceiling. | `text` | `FORMAT(DIVIDE([Propensity true value], [Value ceiling]), "0%") & " of the ceiling"` |
| Load caption | Tile caption: capacity left. | `text` | `FORMAT([Free after campaign], "#,0") & " trips free after the reserve"` |
| Peak caption | Tile caption: where the extra trips land. | `text` | `FORMAT([Extra off-peak trips], "#,0") & " off-peak and " & FORMAT([Extra weekend trips], "#,0") & " weekend"` |
| Risk caption | Tile caption: high-risk customers. | `text` | `FORMAT([High-risk customers], "#,0") & " above 50% inactivity risk"` |
| Gate caption | Tile caption: acceptance checks. | `text` | `FORMAT([Checks passed], "0") & " of " & FORMAT([Checks total], "0") & " checks passed"` |
| Drift caption | Tile caption: drift review count. | `text` | `FORMAT([Features to review], "0") & " features above PSI 0.2"` |
| Feed caption | Tile caption: feed anomalies. | `text` | `FORMAT([Flagged days], "0") & " ingestion days flagged"` |
| Elasticity caption | Tile caption: elasticity interval. | `text` | `"95% interval " & FORMAT([Elasticity low], "0.00") & " to " & FORMAT([Elasticity high], "0.00")` |
| Trial caption | Tile caption: trial size. | `text` | `FORMAT([Customers per arm], "#,0") & " customers per arm, 9 arms"` |

## 10 Narrative

| Measure | Definition | Format | DAX |
|---|---|---|---|
| Executive summary | One-paragraph summary of the plan and its truth-based evaluation, built from the measures. | `text` | `VAR vValue = [Expected value] VAR vSpend = [Incentive spend] VAR vTrue = [Optimized true value] VAR vCeiling = [Value ceiling] VAR vPropensity = [Propensity true value] RETURN "The October plan contacts " & FORMAT([Contacts], "#,0") & " of " & FORMAT([Eligible customers], "#,0") & " eligible customers for " & FORMAT(vSpend, "$#,0") & " of incentives. The models expect " & FORMAT(vValue, "$#,0") & "; scored against the simulator's true responses it creates " & FORMAT(vTrue, "$#,0") & ", " & FORMAT(DIVIDE(vTrue, vCeiling), "0%") & " of what a perfectly informed planner could reach. Giving 10% off to the most frequent travellers " & "would create " & FORMAT(vPropensity, "$#,0") & ": the customers most likely to travel are not the " & "ones an offer moves."` |
