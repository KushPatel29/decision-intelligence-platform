SELECT customer_id, as_of, trips_90d, recency_days,
       lag(trips_90d) OVER (PARTITION BY customer_id ORDER BY as_of) AS previous_snapshot_trips,
       lead(as_of) OVER (PARTITION BY customer_id ORDER BY as_of) AS next_snapshot,
       avg(trips_90d) OVER (PARTITION BY customer_id ORDER BY as_of ROWS BETWEEN 2 PRECEDING AND CURRENT ROW) AS trailing_three_snapshot_average
FROM gold.customer_month;
