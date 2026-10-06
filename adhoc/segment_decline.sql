SELECT rfm_segment,
       count(*) AS customers,
       round(avg(trips_90d), 1) AS trips_last_90d,
       round(avg(trips_previous90d), 1) AS trips_prior_90d,
       round(sum(trips_90d) / nullif(sum(trips_previous90d), 0), 3) AS volume_ratio,
       round(avg(CASE WHEN trips_90d < 0.5 * trips_previous90d THEN 1.0 ELSE 0.0 END), 3) AS share_declining,
       round(percentile_cont(0.5) WITHIN GROUP (ORDER BY frequency_trend), 3) AS median_trend
FROM gold.customer_360
WHERE trips_previous90d >= 3
GROUP BY 1 ORDER BY share_declining DESC;
