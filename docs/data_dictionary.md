# Data dictionary
Actual generated silver schema. Types come from the current Parquet output. Every customer-level field is synthetic. Monetary fields use CAD.

## customer_preferences
Grain: one static customer preference record. Rows: 25,000.
| Field | Type | Nullable in run | Classification |
|---|---|---|---|
| customer_id | str | False | synthetic non-PII |
| marketing_consent | bool | False | synthetic non-PII |
| autopay | bool | False | synthetic non-PII |
| has_my_account | bool | False | synthetic non-PII |

## customer_status_history
Grain: customer × effective_from state/consent transition; intervals end at the next transition. Rows: 27,000.
| Field | Type | Nullable in run | Classification |
|---|---|---|---|
| customer_id | str | False | synthetic non-PII |
| account_status | str | False | synthetic non-PII |
| marketing_consent | bool | False | synthetic non-PII |
| effective_from | datetime64[us] | False | synthetic non-PII |
| effective_to | datetime64[us] | True | synthetic non-PII |

## dim_account
Grain: one account. Rows: 25,000.
| Field | Type | Nullable in run | Classification |
|---|---|---|---|
| account_id | str | False | synthetic non-PII |
| customer_id | str | False | synthetic non-PII |
| account_status | str | False | synthetic non-PII |
| autopay | bool | False | synthetic non-PII |
| past_due | bool | False | synthetic non-PII |
| created_at | datetime64[us] | False | synthetic non-PII |

## dim_customer
Grain: one synthetic customer. Rows: 25,000.
| Field | Type | Nullable in run | Classification |
|---|---|---|---|
| customer_id | str | False | synthetic non-PII |
| account_id | str | False | synthetic non-PII |
| customer_type | str | False | synthetic non-PII |
| account_status | str | False | synthetic non-PII |
| marketing_consent | bool | False | synthetic non-PII |
| has_my_account | bool | False | synthetic non-PII |
| past_due | bool | False | synthetic non-PII |
| autopay | bool | False | synthetic non-PII |
| transponder_flag | bool | False | synthetic non-PII |
| vehicle_class | str | False | synthetic non-PII |
| created_at | datetime64[us] | False | synthetic non-PII |
| eligible | bool | False | synthetic non-PII |
| home_zone | int64 | False | synthetic non-PII |

## dim_entry_point
Grain: one invented entry point per zone. Rows: 6.
| Field | Type | Nullable in run | Classification |
|---|---|---|---|
| zone_id | int64 | False | synthetic non-PII |
| zone_name | str | False | synthetic non-PII |
| entry_point_id | str | False | synthetic non-PII |

## dim_exit_point
Grain: one invented exit point per zone. Rows: 6.
| Field | Type | Nullable in run | Classification |
|---|---|---|---|
| zone_id | int64 | False | synthetic non-PII |
| zone_name | str | False | synthetic non-PII |
| exit_point_id | str | False | synthetic non-PII |

## dim_offer
Grain: one offer template. Rows: 9.
| Field | Type | Nullable in run | Classification |
|---|---|---|---|
| offer_id | str | False | synthetic non-PII |
| offer_name | str | False | synthetic non-PII |
| offer_type | str | False | synthetic non-PII |
| period | str | False | synthetic non-PII |
| discount_pct | float64 | False | synthetic non-PII |
| reward_value | float64 | False | synthetic non-PII |
| points | int64 | False | synthetic non-PII |
| inventory | int64 | False | synthetic non-PII |

## dim_rate
Grain: zone × period × vehicle class, illustrative 2025 tariff. Rows: 36.
| Field | Type | Nullable in run | Classification |
|---|---|---|---|
| zone_id | int64 | False | synthetic non-PII |
| period | str | False | synthetic non-PII |
| vehicle_class | str | False | synthetic non-PII |
| rate_per_km | float64 | False | synthetic non-PII |
| trip_charge | float64 | False | synthetic non-PII |

## dim_reward
Grain: one reward template. Rows: 2.
| Field | Type | Nullable in run | Classification |
|---|---|---|---|
| reward_id | str | False | synthetic non-PII |
| reward_name | str | False | synthetic non-PII |
| points_cost | int64 | False | synthetic non-PII |
| max_value_cad | float64 | False | synthetic non-PII |

## dim_time
Grain: one calendar day. Rows: 731.
| Field | Type | Nullable in run | Classification |
|---|---|---|---|
| date | datetime64[us] | False | synthetic non-PII |
| weekend | int64 | False | synthetic non-PII |
| holiday | int64 | False | synthetic non-PII |
| day_of_week | int32 | False | synthetic non-PII |
| month | int32 | False | synthetic non-PII |
| year | int32 | False | synthetic non-PII |

## dim_transponder
Grain: one synthetic equipped account. Rows: 21,513.
| Field | Type | Nullable in run | Classification |
|---|---|---|---|
| customer_id | str | False | synthetic non-PII |
| account_id | str | False | synthetic non-PII |
| transponder_id | str | False | synthetic non-PII |

## dim_vehicle
Grain: one vehicle. Rows: 25,000.
| Field | Type | Nullable in run | Classification |
|---|---|---|---|
| vehicle_id | str | False | synthetic non-PII |
| customer_id | str | False | synthetic non-PII |
| vehicle_class | str | False | synthetic non-PII |
| transponder_flag | bool | False | synthetic non-PII |

## dim_zone
Grain: one invented zone. Rows: 6.
| Field | Type | Nullable in run | Classification |
|---|---|---|---|
| zone_id | int64 | False | synthetic non-PII |
| zone_name | str | False | synthetic non-PII |
| is_synthetic | bool | False | synthetic non-PII |

## external_context
Grain: one Toronto/Ontario context day. Rows: 731.
| Field | Type | Nullable in run | Classification |
|---|---|---|---|
| date | datetime64[us] | False | public context |
| temperature_c | float64 | False | public context |
| precipitation_mm | float64 | False | public context |
| daylight_hours | float64 | False | public context |
| cad_usd | float64 | True | public context |
| holiday_name | str | True | public context |
| holiday | int64 | False | public context |
| weekend | int64 | False | public context |
| month_sin | float64 | False | public context |
| month_cos | float64 | False | public context |

## fact_campaign_result
Grain: one randomized customer trial outcome. Rows: 25,000.
| Field | Type | Nullable in run | Classification |
|---|---|---|---|
| customer_id | str | False | synthetic non-PII |
| as_of | datetime64[us] | False | synthetic non-PII |
| tenure_days | int64 | False | synthetic non-PII |
| business_flag | int32 | False | synthetic non-PII |
| autopay | int32 | False | synthetic non-PII |
| transponder_flag | int32 | False | synthetic non-PII |
| heavy_vehicle | int32 | False | synthetic non-PII |
| home_zone | int64 | False | synthetic non-PII |
| trips_7d | int64 | False | synthetic non-PII |
| trips_30d | int64 | False | synthetic non-PII |
| trips_90d | int64 | False | synthetic non-PII |
| trips_previous90d | int64 | False | synthetic non-PII |
| spend_30d | float64 | False | synthetic non-PII |
| spend_90d | float64 | False | synthetic non-PII |
| spend_365d | float64 | False | synthetic non-PII |
| avg_toll | float64 | False | synthetic non-PII |
| avg_toll_peak | float64 | False | synthetic non-PII |
| avg_toll_offpeak | float64 | False | synthetic non-PII |
| avg_toll_weekend | float64 | False | synthetic non-PII |
| avg_distance_km | float64 | False | synthetic non-PII |
| peak_share | float64 | False | synthetic non-PII |
| weekend_share | float64 | False | synthetic non-PII |
| night_share_30d | float64 | False | synthetic non-PII |
| zones_visited_30d | int64 | False | synthetic non-PII |
| active_days_30d | int64 | False | synthetic non-PII |
| max_daily_trips_30d | int64 | False | synthetic non-PII |
| discount_90d | float64 | False | synthetic non-PII |
| recency_days | int64 | False | synthetic non-PII |
| digital_events_30d | int64 | False | synthetic non-PII |
| app_logins_30d | int64 | False | synthetic non-PII |
| offer_views_30d | int64 | False | synthetic non-PII |
| email_opens_30d | int64 | False | synthetic non-PII |
| sessions_30d | int64 | False | synthetic non-PII |
| offer_views_90d | int64 | False | synthetic non-PII |
| offer_click_rate_90d | float64 | False | synthetic non-PII |
| enroll_rate_90d | float64 | False | synthetic non-PII |
| email_click_rate_90d | float64 | False | synthetic non-PII |
| pricing_views_90d | int64 | False | synthetic non-PII |
| loyalty_views_90d | int64 | False | synthetic non-PII |
| app_share_90d | float64 | False | synthetic non-PII |
| days_since_last_login | int64 | False | synthetic non-PII |
| points_earned_to_date | float64 | False | synthetic non-PII |
| feature_max_timestamp | datetime64[us] | True | synthetic non-PII |
| account_status | str | False | synthetic non-PII |
| marketing_consent | bool | False | synthetic non-PII |
| has_my_account | bool | False | synthetic non-PII |
| past_due | bool | False | synthetic non-PII |
| eligible | bool | False | synthetic non-PII |
| frequency_trend | float64 | False | synthetic non-PII |
| digital_engagement_score | float64 | False | synthetic non-PII |
| stratum | int64 | False | synthetic non-PII |
| arm | str | False | synthetic non-PII |
| treated | int64 | False | synthetic non-PII |
| offer_id | str | True | synthetic non-PII |
| trips_by_day10 | int64 | False | synthetic non-PII |
| trips_by_day20 | int64 | False | synthetic non-PII |
| trips_by_day30 | int64 | False | synthetic non-PII |
| trips_peak | int64 | False | synthetic non-PII |
| trips_offpeak | int64 | False | synthetic non-PII |
| trips_weekend | int64 | False | synthetic non-PII |
| trip_count | int64 | False | synthetic non-PII |
| incentive_cost | float64 | False | synthetic non-PII |
| gross_contribution | float64 | False | synthetic non-PII |
| net_contribution | float64 | False | synthetic non-PII |
| response | int64 | False | synthetic non-PII |
| enrolled | int64 | False | synthetic non-PII |
| redeemed | int64 | False | synthetic non-PII |
| retained_90d | int64 | False | synthetic non-PII |
| trips_days31_90 | int64 | False | synthetic non-PII |
| margin_days31_90 | float64 | False | synthetic non-PII |
| pre_trips_30d | int64 | False | synthetic non-PII |
| pre_spend_30d | float64 | False | synthetic non-PII |
| split | str | False | synthetic non-PII |
| spend_threshold | float64 | True | synthetic non-PII |

## fact_digital_event
Grain: one interaction event. Rows: 1,412,304.
| Field | Type | Nullable in run | Classification |
|---|---|---|---|
| event_id | str | False | synthetic non-PII |
| customer_id | str | False | synthetic non-PII |
| timestamp | datetime64[us] | False | synthetic non-PII |
| event_type | str | False | synthetic non-PII |
| channel | str | False | synthetic non-PII |

## fact_effective_price
Grain: one realized price per synthetic trip. Rows: 3,680,249.
| Field | Type | Nullable in run | Classification |
|---|---|---|---|
| trip_id | str | False | synthetic non-PII |
| customer_id | str | False | synthetic non-PII |
| timestamp | datetime64[us] | False | synthetic non-PII |
| zone_id | int64 | False | synthetic non-PII |
| period | str | False | synthetic non-PII |
| distance_km | float64 | False | synthetic non-PII |
| toll | float64 | False | synthetic non-PII |
| discount | float64 | False | synthetic non-PII |
| final_charge | float64 | False | synthetic non-PII |
| effective_price_per_km | float64 | False | synthetic non-PII |

## fact_loyalty_award
Grain: one randomized loyalty-group customer award. Rows: 5,000.
| Field | Type | Nullable in run | Classification |
|---|---|---|---|
| customer_id | str | False | synthetic non-PII |
| offer_id | str | False | synthetic non-PII |
| points_awarded | int64 | False | synthetic non-PII |
| awarded_at | datetime64[us] | False | synthetic non-PII |
| award_id | str | False | synthetic non-PII |

## fact_loyalty_points
Grain: one trip earning entry. Rows: 3,680,249.
| Field | Type | Nullable in run | Classification |
|---|---|---|---|
| trip_id | str | False | synthetic non-PII |
| customer_id | str | False | synthetic non-PII |
| timestamp | datetime64[us] | False | synthetic non-PII |
| points_earned | int64 | False | synthetic non-PII |

## fact_loyalty_redemption
Grain: one loyalty redemption event. Rows: 1,639.
| Field | Type | Nullable in run | Classification |
|---|---|---|---|
| customer_id | str | False | synthetic non-PII |
| reward_id | str | False | synthetic non-PII |
| points_redeemed | int64 | False | synthetic non-PII |
| reward_cost | float64 | False | synthetic non-PII |
| redeemed_at | datetime64[us] | False | synthetic non-PII |

## fact_loyalty_tier
Grain: one customer tier at the decision date. Rows: 25,000.
| Field | Type | Nullable in run | Classification |
|---|---|---|---|
| customer_id | str | False | synthetic non-PII |
| as_of | str | False | synthetic non-PII |
| tier | str | False | synthetic non-PII |

## fact_offer_enrollment
Grain: one treated customer enrollment. Rows: 9,062.
| Field | Type | Nullable in run | Classification |
|---|---|---|---|
| customer_id | str | False | synthetic non-PII |
| arm | str | False | synthetic non-PII |
| offer_id | str | False | synthetic non-PII |
| enrolled_at | datetime64[us] | False | synthetic non-PII |
| campaign_id | str | False | synthetic non-PII |

## fact_offer_exposure
Grain: one assigned treated customer exposure. Rows: 22,500.
| Field | Type | Nullable in run | Classification |
|---|---|---|---|
| customer_id | str | False | synthetic non-PII |
| arm | str | False | synthetic non-PII |
| offer_id | str | False | synthetic non-PII |
| exposed_at | datetime64[us] | False | synthetic non-PII |
| campaign_id | str | False | synthetic non-PII |

## fact_offer_redemption
Grain: one treated customer redemption. Rows: 5,848.
| Field | Type | Nullable in run | Classification |
|---|---|---|---|
| customer_id | str | False | synthetic non-PII |
| arm | str | False | synthetic non-PII |
| offer_id | str | False | synthetic non-PII |
| incentive_cost | float64 | False | synthetic non-PII |
| redeemed_at | datetime64[us] | False | synthetic non-PII |
| campaign_id | str | False | synthetic non-PII |

## fact_pricing_scenario
Grain: zone × period × day randomized price assignment. Rows: 26,316.
| Field | Type | Nullable in run | Classification |
|---|---|---|---|
| date | datetime64[us] | False | synthetic non-PII |
| zone_id | int64 | False | synthetic non-PII |
| period | str | False | synthetic non-PII |
| segment | str | False | synthetic non-PII |
| effective_price | float64 | False | synthetic non-PII |
| assigned_price_multiplier | float64 | False | synthetic non-PII |
| demand | int64 | False | synthetic non-PII |
| temperature_c | float64 | False | synthetic non-PII |
| precipitation_mm | float64 | False | synthetic non-PII |
| weekend | int64 | False | synthetic non-PII |
| holiday | int64 | False | synthetic non-PII |
| month_sin | float64 | False | synthetic non-PII |
| month_cos | float64 | False | synthetic non-PII |

## fact_trip
Grain: one generated trip. Rows: 3,680,249.
| Field | Type | Nullable in run | Classification |
|---|---|---|---|
| customer_id | str | False | synthetic non-PII |
| timestamp | datetime64[us] | False | synthetic non-PII |
| zone_id | int64 | False | synthetic non-PII |
| entry_zone | int64 | False | synthetic non-PII |
| exit_zone | int64 | False | synthetic non-PII |
| direction | str | False | synthetic non-PII |
| period | str | False | synthetic non-PII |
| distance_km | float64 | False | synthetic non-PII |
| duration_min | float64 | False | synthetic non-PII |
| toll | float64 | False | synthetic non-PII |
| discount | float64 | False | synthetic non-PII |
| final_charge | float64 | False | synthetic non-PII |
| trip_id | str | False | synthetic non-PII |

## quarantine_trip
Grain: one bronze trip rejected by the silver contract, with its reason. Rows: 4,147.
| Field | Type | Nullable in run | Classification |
|---|---|---|---|
| customer_id | str | False | synthetic non-PII |
| timestamp | datetime64[us] | False | synthetic non-PII |
| zone_id | int64 | False | synthetic non-PII |
| entry_zone | int64 | False | synthetic non-PII |
| exit_zone | int64 | False | synthetic non-PII |
| direction | str | False | synthetic non-PII |
| period | str | False | synthetic non-PII |
| distance_km | float64 | False | synthetic non-PII |
| duration_min | float64 | False | synthetic non-PII |
| toll | float64 | False | synthetic non-PII |
| discount | float64 | False | synthetic non-PII |
| final_charge | float64 | False | synthetic non-PII |
| ingested_at | datetime64[us] | False | synthetic non-PII |
| batch_id | str | False | synthetic non-PII |
| trip_id | str | False | synthetic non-PII |
| reason | str | False | synthetic non-PII |