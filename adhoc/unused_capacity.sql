SELECT z.zone_name,
       round(c.baseline_forecast) AS forecast_trips,
       round(c.capacity_trips) AS capacity_trips,
       round(c.available_trips) AS free_before_campaign,
       round(c.allocated_trips, 1) AS campaign_trips,
       round(c.remaining_with_reserve) AS free_after_campaign,
       rank() OVER (ORDER BY c.remaining_with_reserve DESC) AS headroom_rank,
       round(100 * c.remaining_with_reserve / sum(c.remaining_with_reserve) OVER (), 1) AS share_of_free_pct
FROM gold.zone_capacity c JOIN silver.dim_zone z USING (zone_id)
WHERE c.period = 'Off-peak'
ORDER BY headroom_rank;
