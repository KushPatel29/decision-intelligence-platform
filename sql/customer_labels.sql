-- Labels intentionally separate from features. Forward windows, end-exclusive.
SELECT customer_id,
  count(*) FILTER (WHERE timestamp < $as_of + INTERVAL '30 days') AS future_trips_30d,
  count(*) AS future_trips_90d,
  sum(final_charge) * $margin AS future_margin_90d
FROM silver.fact_trip
WHERE timestamp >= $as_of AND timestamp < $as_of + INTERVAL '90 days'
GROUP BY customer_id;
