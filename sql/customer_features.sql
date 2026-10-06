-- DuckDB dialect. $as_of is bound by Python. Every window is end-exclusive:
-- nothing at or after the snapshot cutoff can enter a feature.
WITH trips AS (
  SELECT * FROM silver.fact_trip WHERE timestamp < $as_of
), trip_features AS (
  SELECT customer_id,
    count(*) FILTER (WHERE timestamp >= $as_of - INTERVAL '7 days') AS trips_7d,
    count(*) FILTER (WHERE timestamp >= $as_of - INTERVAL '30 days') AS trips_30d,
    count(*) FILTER (WHERE timestamp >= $as_of - INTERVAL '90 days') AS trips_90d,
    count(*) FILTER (WHERE timestamp >= $as_of - INTERVAL '180 days' AND timestamp < $as_of - INTERVAL '90 days') AS trips_previous90d,
    coalesce(sum(final_charge) FILTER (WHERE timestamp >= $as_of - INTERVAL '30 days'), 0) AS spend_30d,
    coalesce(sum(final_charge) FILTER (WHERE timestamp >= $as_of - INTERVAL '90 days'), 0) AS spend_90d,
    coalesce(sum(final_charge) FILTER (WHERE timestamp >= $as_of - INTERVAL '365 days'), 0) AS spend_365d,
    coalesce(avg(toll) FILTER (WHERE timestamp >= $as_of - INTERVAL '90 days'), 0) AS avg_toll,
    coalesce(avg(toll) FILTER (WHERE period = 'Peak' AND timestamp >= $as_of - INTERVAL '90 days'), 0) AS avg_toll_peak,
    coalesce(avg(toll) FILTER (WHERE period = 'Off-peak' AND timestamp >= $as_of - INTERVAL '90 days'), 0) AS avg_toll_offpeak,
    coalesce(avg(toll) FILTER (WHERE period = 'Weekend' AND timestamp >= $as_of - INTERVAL '90 days'), 0) AS avg_toll_weekend,
    coalesce(avg(distance_km) FILTER (WHERE timestamp >= $as_of - INTERVAL '90 days'), 0) AS avg_distance_km,
    coalesce(avg(CASE WHEN period = 'Peak' THEN 1.0 ELSE 0.0 END) FILTER (WHERE timestamp >= $as_of - INTERVAL '90 days'), 0) AS peak_share,
    coalesce(avg(CASE WHEN period = 'Weekend' THEN 1.0 ELSE 0.0 END) FILTER (WHERE timestamp >= $as_of - INTERVAL '90 days'), 0) AS weekend_share,
    coalesce(avg(CASE WHEN hour(timestamp) < 6 THEN 1.0 ELSE 0.0 END) FILTER (WHERE timestamp >= $as_of - INTERVAL '30 days'), 0) AS night_share_30d,
    count(DISTINCT zone_id) FILTER (WHERE timestamp >= $as_of - INTERVAL '30 days') AS zones_visited_30d,
    count(DISTINCT CAST(timestamp AS DATE)) FILTER (WHERE timestamp >= $as_of - INTERVAL '30 days') AS active_days_30d,
    coalesce(sum(discount) FILTER (WHERE timestamp >= $as_of - INTERVAL '90 days'), 0) AS discount_90d,
    date_diff('day', max(timestamp), $as_of) AS recency_days,
    max(timestamp) AS feature_max_timestamp
  FROM trips GROUP BY customer_id
), busiest_day AS (
  SELECT customer_id, max(day_trips) AS max_daily_trips_30d
  FROM (
    SELECT customer_id, CAST(timestamp AS DATE) AS day, count(*) AS day_trips
    FROM trips WHERE timestamp >= $as_of - INTERVAL '30 days'
    GROUP BY customer_id, day
  ) GROUP BY customer_id
), events AS (
  SELECT * FROM silver.fact_digital_event
  WHERE timestamp >= $as_of - INTERVAL '90 days' AND timestamp < $as_of
), digital AS (
  SELECT customer_id,
    count(*) FILTER (WHERE timestamp >= $as_of - INTERVAL '30 days') AS digital_events_30d,
    count(*) FILTER (WHERE event_type = 'app_login' AND timestamp >= $as_of - INTERVAL '30 days') AS app_logins_30d,
    count(*) FILTER (WHERE event_type = 'offer_view' AND timestamp >= $as_of - INTERVAL '30 days') AS offer_views_30d,
    count(*) FILTER (WHERE event_type = 'email_open' AND timestamp >= $as_of - INTERVAL '30 days') AS email_opens_30d,
    count(DISTINCT CAST(timestamp AS DATE)) FILTER (WHERE timestamp >= $as_of - INTERVAL '30 days') AS sessions_30d,
    count(*) FILTER (WHERE event_type = 'offer_view') AS offer_views_90d,
    count(*) FILTER (WHERE event_type = 'offer_click') AS offer_clicks_90d,
    count(*) FILTER (WHERE event_type = 'offer_enroll') AS offer_enrolls_90d,
    count(*) FILTER (WHERE event_type = 'email_open') AS email_opens_90d,
    count(*) FILTER (WHERE event_type = 'email_click') AS email_clicks_90d,
    count(*) FILTER (WHERE event_type = 'pricing_page_view') AS pricing_views_90d,
    count(*) FILTER (WHERE event_type = 'loyalty_page_view') AS loyalty_views_90d,
    count(*) FILTER (WHERE event_type = 'app_login') AS app_logins_90d,
    count(*) FILTER (WHERE event_type IN ('app_login', 'web_login')) AS logins_90d
  FROM events GROUP BY customer_id
), last_login AS (
  SELECT customer_id, date_diff('day', max(timestamp), $as_of) AS days_since_last_login
  FROM silver.fact_digital_event
  WHERE timestamp < $as_of AND event_type IN ('app_login', 'web_login')
  GROUP BY customer_id
), loyalty AS (
  SELECT customer_id, sum(points_earned) AS points_earned_to_date
  FROM silver.fact_loyalty_points WHERE timestamp < $as_of GROUP BY customer_id
)
SELECT c.customer_id, $as_of::TIMESTAMP AS as_of,
  date_diff('day', c.created_at, $as_of) AS tenure_days,
  CAST(c.customer_type = 'Business' AS INTEGER) AS business_flag,
  CAST(c.autopay AS INTEGER) AS autopay,
  CAST(c.transponder_flag AS INTEGER) AS transponder_flag,
  CAST(c.vehicle_class = 'Heavy' AS INTEGER) AS heavy_vehicle,
  c.home_zone, c.eligible, c.account_status,
  coalesce(t.trips_7d, 0) AS trips_7d, coalesce(t.trips_30d, 0) AS trips_30d,
  coalesce(t.trips_90d, 0) AS trips_90d, coalesce(t.trips_previous90d, 0) AS trips_previous90d,
  coalesce(t.spend_30d, 0) AS spend_30d, coalesce(t.spend_90d, 0) AS spend_90d,
  coalesce(t.spend_365d, 0) AS spend_365d, coalesce(t.avg_toll, 0) AS avg_toll,
  -- Economics inputs for offer costing; deliberately not in the model allowlist.
  coalesce(t.avg_toll_peak, 0) AS avg_toll_peak, coalesce(t.avg_toll_offpeak, 0) AS avg_toll_offpeak,
  coalesce(t.avg_toll_weekend, 0) AS avg_toll_weekend,
  coalesce(t.avg_distance_km, 0) AS avg_distance_km, coalesce(t.peak_share, 0) AS peak_share,
  coalesce(t.weekend_share, 0) AS weekend_share, coalesce(t.night_share_30d, 0) AS night_share_30d,
  coalesce(t.zones_visited_30d, 0) AS zones_visited_30d, coalesce(t.active_days_30d, 0) AS active_days_30d,
  coalesce(b.max_daily_trips_30d, 0) AS max_daily_trips_30d,
  coalesce(t.discount_90d, 0) AS discount_90d,
  coalesce(t.recency_days, 730) AS recency_days,
  coalesce(d.digital_events_30d, 0) AS digital_events_30d, coalesce(d.app_logins_30d, 0) AS app_logins_30d,
  coalesce(d.offer_views_30d, 0) AS offer_views_30d, coalesce(d.email_opens_30d, 0) AS email_opens_30d,
  coalesce(d.sessions_30d, 0) AS sessions_30d,
  coalesce(d.offer_views_90d, 0) AS offer_views_90d,
  (coalesce(d.offer_clicks_90d, 0) + 0.5) / (coalesce(d.offer_views_90d, 0) + 3.0) AS offer_click_rate_90d,
  (coalesce(d.offer_enrolls_90d, 0) + 0.5) / (coalesce(d.offer_clicks_90d, 0) + 2.0) AS enroll_rate_90d,
  (coalesce(d.email_clicks_90d, 0) + 0.5) / (coalesce(d.email_opens_90d, 0) + 3.0) AS email_click_rate_90d,
  coalesce(d.pricing_views_90d, 0) AS pricing_views_90d,
  coalesce(d.loyalty_views_90d, 0) AS loyalty_views_90d,
  CASE WHEN coalesce(d.logins_90d, 0) = 0 THEN 0.0 ELSE d.app_logins_90d / d.logins_90d END AS app_share_90d,
  least(coalesce(ll.days_since_last_login, 365), 365) AS days_since_last_login,
  coalesce(l.points_earned_to_date, 0) AS points_earned_to_date,
  t.feature_max_timestamp
FROM silver.dim_customer c
LEFT JOIN trip_features t USING (customer_id)
LEFT JOIN busiest_day b USING (customer_id)
LEFT JOIN digital d USING (customer_id)
LEFT JOIN last_login ll USING (customer_id)
LEFT JOIN loyalty l USING (customer_id)
WHERE c.created_at < $as_of
ORDER BY c.customer_id;
