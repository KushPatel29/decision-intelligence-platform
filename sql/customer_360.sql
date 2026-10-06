-- Executed model scores live in gold.customer_360; no outcome columns exposed.
SELECT customer_id, tenure_days, trips_30d, trips_90d, recency_days, spend_90d,
       rfm_segment, cluster, propensity_probability, churn_probability,
       attrition_probability, clv_12m, digital_engagement_score,
       points_earned_to_date, eligible, anomaly_flag
FROM gold.customer_360;
