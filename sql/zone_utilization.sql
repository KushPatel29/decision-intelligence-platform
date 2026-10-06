SELECT zone_id, period, baseline_forecast, allocated_trips, capacity_trips,
       (baseline_forecast + allocated_trips) / nullif(capacity_trips,0) AS utilization,
       remaining_with_reserve,
       row_number() OVER (PARTITION BY period ORDER BY remaining_with_reserve DESC) AS headroom_rank
FROM gold.zone_capacity;
