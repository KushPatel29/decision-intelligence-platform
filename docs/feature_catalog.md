# Feature catalog

Contract version 2.0. Refresh: monthly batch. Owner: project analytics. Privacy class: synthetic, non-PII. Model usage: customer prediction and causal outcome models unless a model card narrows it.

All windows are end-exclusive at the snapshot date; timestamps are Toronto wall-clock. Status and marketing consent resolve their effective-dated history. Other account attributes remain static synthetic flags.

| Feature | Business definition | Formula | Source | Nullable |
|---|---|---|---|---|
| tenure_days | Days since synthetic account creation | date_diff(created_at, as_of) | dim_customer | False |
| business_flag | Business account indicator | customer_type = Business | dim_customer | False |
| autopay | Automatic-payment indicator | cast(autopay as int) | dim_customer | False |
| transponder_flag | Vehicle uses transponder | cast(transponder_flag as int) | dim_customer | False |
| heavy_vehicle | Heavy-vehicle account | vehicle_class = Heavy | dim_customer | False |
| home_zone | Synthetic preferred zone | home_zone | dim_customer | False |
| trips_7d | Recent 7-day trip frequency | count trips in [as_of-7d, as_of) | fact_trip | False |
| trips_30d | Recent 30-day trip frequency | count trips in [as_of-30d, as_of) | fact_trip | False |
| trips_90d | Recent 90-day trip frequency | count trips in [as_of-90d, as_of) | fact_trip | False |
| trips_previous90d | Prior comparison-window frequency | count trips in [as_of-180d, as_of-90d) | fact_trip | False |
| spend_30d | 30-day billed amount CAD | sum(final_charge) over trailing 30d | fact_trip | False |
| spend_90d | 90-day billed amount CAD | sum(final_charge) over trailing 90d | fact_trip | False |
| spend_365d | Annual billed amount CAD | sum(final_charge) over trailing 365d | fact_trip | False |
| avg_toll | Mean pre-discount toll CAD | avg(toll) over trailing 90d | fact_trip | False |
| avg_distance_km | Mean trip distance | avg(distance_km) over trailing 90d | fact_trip | False |
| peak_share | Peak share of recent trips | avg(period = Peak) over trailing 90d | fact_trip | False |
| weekend_share | Weekend share of recent trips | avg(period = Weekend) over trailing 90d | fact_trip | False |
| night_share_30d | Share of recent trips before 06:00 | avg(hour < 6) over trailing 30d | fact_trip | False |
| zones_visited_30d | Distinct zones travelled recently | count distinct zone_id over trailing 30d | fact_trip | False |
| active_days_30d | Days with at least one trip | count distinct trip dates over trailing 30d | fact_trip | False |
| max_daily_trips_30d | Busiest recent day | max trips in one day over trailing 30d | fact_trip | False |
| discount_90d | Recent applied discounts CAD | sum(discount) over trailing 90d | fact_trip | False |
| recency_days | Days since latest prior trip | date_diff(max(timestamp), as_of); 730 if no history | fact_trip | False |
| digital_events_30d | Recent digital interaction count | count digital events over trailing 30d | fact_digital_event | False |
| app_logins_30d | Recent app logins | count event_type=app_login over trailing 30d | fact_digital_event | False |
| offer_views_30d | Recent offer views | count event_type=offer_view over trailing 30d | fact_digital_event | False |
| email_opens_30d | Recent email opens | count event_type=email_open over trailing 30d | fact_digital_event | False |
| sessions_30d | Days with a digital session | count distinct event dates over trailing 30d | fact_digital_event | False |
| offer_views_90d | Offer views | count event_type=offer_view over trailing 90d | fact_digital_event | False |
| offer_click_rate_90d | Smoothed offer click-through | (offer clicks + 0.5) / (offer views + 3) over trailing 90d | fact_digital_event | False |
| enroll_rate_90d | Smoothed enrolment after a click | (enrolments + 0.5) / (offer clicks + 2) over trailing 90d | fact_digital_event | False |
| email_click_rate_90d | Smoothed email click-through | (email clicks + 0.5) / (email opens + 3) over trailing 90d | fact_digital_event | False |
| pricing_views_90d | Pricing page views | count event_type=pricing_page_view over trailing 90d | fact_digital_event | False |
| loyalty_views_90d | Loyalty page views | count event_type=loyalty_page_view over trailing 90d | fact_digital_event | False |
| app_share_90d | Share of logins in the app | app logins / all logins over trailing 90d; 0 if none | fact_digital_event | False |
| days_since_last_login | Days since the last login | date_diff(max(login), as_of), capped at 365 | fact_digital_event | False |
| points_earned_to_date | Historical points earnings, not available balance | sum points_earned before as_of | fact_loyalty_points | False |
| frequency_trend | Smoothed relative usage change | (trips_90d+1)/(trips_previous90d+1) | customer_features | False |
| digital_engagement_score | Log digital engagement proxy | log1p(digital_events_30d) | customer_features | False |