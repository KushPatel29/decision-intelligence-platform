-- Quartile ranks are descriptive current-customer business segmentation inputs.
SELECT customer_id, recency_days, trips_90d, spend_90d,
       ntile(4) OVER (ORDER BY recency_days DESC) AS recency_quartile,
       ntile(4) OVER (ORDER BY trips_90d) AS frequency_quartile,
       ntile(4) OVER (ORDER BY spend_90d) AS monetary_quartile
FROM gold.customer_360;
