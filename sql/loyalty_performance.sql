SELECT customer_id, sum(points_earned) AS points_earned,
       sum(sum(points_earned)) OVER () AS total_points_earned,
       sum(points_earned) * 0.01 AS maximum_redemption_liability
FROM silver.fact_loyalty_points
WHERE timestamp < TIMESTAMP '2025-10-01'
GROUP BY customer_id;
