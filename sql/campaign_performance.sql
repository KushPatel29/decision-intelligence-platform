SELECT arm, count(*) AS randomized_customers, avg(response) AS response_rate,
       avg(enrolled) AS enrollment_rate, avg(trip_count) AS mean_trips,
       avg(incentive_cost) AS mean_incentive_cost, avg(net_contribution) AS mean_net_contribution
FROM gold.campaign_performance GROUP BY arm;
