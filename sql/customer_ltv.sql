SELECT rfm_segment, count(*) AS customers, avg(clv_12m) AS average_value,
       percentile_cont(.5) WITHIN GROUP (ORDER BY clv_12m) AS median_value,
       sum(clv_12m) AS segment_projected_value
FROM gold.customer_360 GROUP BY rfm_segment;
