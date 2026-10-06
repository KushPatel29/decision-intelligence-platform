SELECT zone_id, available_trips, remaining_with_reserve FROM gold.zone_capacity WHERE period='Off-peak' ORDER BY available_trips DESC;
