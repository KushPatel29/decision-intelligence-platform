SELECT arm, avg(trip_count) AS mean_trips, avg(incentive_cost) AS mean_subsidy, avg(net_contribution) AS mean_net_contribution FROM gold.campaign_performance GROUP BY 1 ORDER BY 1;
