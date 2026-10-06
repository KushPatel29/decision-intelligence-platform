WITH control AS (
  SELECT avg(trip_count) AS base_trips FROM gold.campaign_performance WHERE arm = 'Control'
)
SELECT p.arm,
       count(*) AS customers,
       round(avg(p.trip_count), 2) AS trips_per_customer,
       round(avg(p.trip_count) - c.base_trips, 2) AS incremental_trips,
       round(avg(p.incentive_cost), 2) AS incentive_per_customer,
       round(1 - (avg(p.trip_count) - c.base_trips) / nullif(avg(p.trip_count), 0), 3) AS subsidy_share,
       round(avg(p.net_contribution), 2) AS net_contribution_per_customer
FROM gold.campaign_performance p CROSS JOIN control c
WHERE p.arm <> 'Control'
GROUP BY p.arm, c.base_trips ORDER BY subsidy_share DESC;
