SELECT zone_id, period, elasticity, mae,
       row_number() OVER (PARTITION BY period ORDER BY elasticity) AS sensitivity_rank
FROM gold.pricing_elasticity;
