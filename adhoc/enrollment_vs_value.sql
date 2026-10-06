WITH control AS (
  SELECT avg(net_contribution) AS base_value FROM gold.campaign_performance WHERE arm = 'Control'
)
SELECT p.arm,
       round(avg(p.enrolled), 3) AS enrollment_rate,
       round(avg(p.redeemed), 3) AS redemption_rate,
       round(avg(p.incentive_cost), 2) AS incentive_per_customer,
       round(avg(p.net_contribution) - c.base_value, 2) AS net_contribution_per_customer,
       round((avg(p.net_contribution) - c.base_value) / nullif(avg(p.incentive_cost), 0), 3) AS incremental_roi,
       row_number() OVER (ORDER BY avg(p.enrolled) DESC) AS enrollment_rank
FROM gold.campaign_performance p CROSS JOIN control c
WHERE p.arm <> 'Control'
GROUP BY p.arm, c.base_value ORDER BY enrollment_rank;
