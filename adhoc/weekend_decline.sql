WITH weekend AS (
  SELECT date_trunc('month', t.timestamp) AS month,
         count(*) AS trips,
         count(DISTINCT CAST(t.timestamp AS DATE)) AS weekend_days,
         avg(c.precipitation_mm) AS mean_rain_mm
  FROM silver.fact_trip t
  JOIN silver.external_context c ON c.date = CAST(t.timestamp AS DATE)
  WHERE t.period = 'Weekend' AND t.timestamp >= '2025-04-01' AND t.timestamp < '2025-10-01'
  GROUP BY 1
)
SELECT strftime(month, '%Y-%m') AS month,
       trips,
       weekend_days,
       round(trips / weekend_days, 1) AS trips_per_weekend_day,
       round(100 * (trips / weekend_days) / lag(trips / weekend_days) OVER (ORDER BY month) - 100, 1) AS change_pct,
       round(mean_rain_mm, 2) AS mean_rain_mm
FROM weekend ORDER BY month;
