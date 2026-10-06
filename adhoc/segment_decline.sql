SELECT rfm_segment, avg(frequency_trend) AS frequency_ratio, count(*) AS customers FROM gold.customer_360 GROUP BY 1 ORDER BY 2;
