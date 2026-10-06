"""Synthetic account, trip, digital, loyalty and pricing ecosystem.

The generator draws hidden traits from `simulation.py`, then writes only what a
toll operator could observe: accounts, trips, app/web/email events, points and
randomised price tests. Hidden traits, planted anomalies and planted data
defects go to `data/simulation_audit/`, which no model or feature may read.

Bronze keeps the raw feed exactly as ingested, defects included (a late batch, a
re-sent duplicate batch, a unit error and impossible charges). Silver is the
conformed layer: duplicates removed on the natural key and invalid rows moved to
`quarantine_trip` with a reason code.
"""

from __future__ import annotations

import hashlib

import numpy as np
import pandas as pd

from .config import write_json
from .simulation import (
    OFFER_CATALOG,
    PERIODS,
    TRIP_CHARGE,
    WINDOW_START,
    ZONES,
    daily_rate,
    draw_population,
    peak_probability,
    rate_per_km,
)

DIGITAL_EVENTS = [
    "app_login",
    "web_login",
    "notification_open",
    "email_open",
    "email_click",
    "offer_view",
    "offer_click",
    "offer_enroll",
    "pricing_page_view",
    "trip_history_view",
    "loyalty_page_view",
]

# Planted data defects: (ingestion date, kind). Ground truth for the data-quality monitor.
DATA_DEFECTS = [
    ("2025-07-23", "late_partial_batch"),
    ("2025-07-24", "late_partial_batch"),
    ("2025-08-21", "distance_unit_error"),
    ("2025-09-10", "duplicate_batch"),
]


def _ids(seed, n):
    return [hashlib.sha256(f"synthetic-{seed}-{i}".encode()).hexdigest()[:16] for i in range(n)]


def _customers(rng, n, seed):
    customer_type = rng.choice(["Personal", "Business"], n, p=[0.84, 0.16])
    created_at = pd.Timestamp("2019-01-01") + pd.to_timedelta(rng.integers(0, 2190, n), unit="D")
    frame = pd.DataFrame(
        {
            "customer_id": _ids(seed, n),
            "account_id": [f"A{i:06}" for i in range(n)],
            "customer_type": customer_type,
            "account_status": rng.choice(["Active", "Suspended"], n, p=[0.97, 0.03]),
            "marketing_consent": rng.random(n) < 0.83,
            "has_my_account": rng.random(n) < 0.91,
            "past_due": rng.random(n) < 0.07,
            "autopay": rng.random(n) < 0.67,
            "transponder_flag": rng.random(n) < 0.86,
            "vehicle_class": np.where(
                rng.random(n) < np.where(customer_type == "Business", 0.20, 0.04), "Heavy", "Light"
            ),
            "created_at": created_at,
        }
    )
    frame["eligible"] = (
        frame.marketing_consent & frame.has_my_account & ~frame.past_due & frame.account_status.eq("Active")
    )
    return frame


def _trip_hours(rng, period):
    m = len(period)
    peak_hour = np.where(rng.random(m) < 0.5, rng.choice([7, 8, 9], m), rng.choice([16, 17, 18], m))
    off_hour = np.where(
        rng.random(m) < 0.03,
        rng.choice([22, 23, 0, 1, 2, 3, 4, 5], m),
        rng.choice([10, 11, 12, 13, 14, 15, 19, 20, 21], m),
    )
    weekend_hour = rng.integers(9, 21, m)
    return np.select([period == "Peak", period == "Off-peak"], [peak_hour, off_hour], weekend_hour)


def _trip_frame(rng, date, idx, period, hour, entry, exit_, heavy, customer_ids):
    m = len(idx)
    same = entry == exit_
    direction = np.where(
        exit_ > entry,
        "Eastbound",
        np.where(exit_ < entry, "Westbound", rng.choice(["Eastbound", "Westbound"], m)),
    )
    distance = 7.0 + 8.5 * np.abs(exit_ - entry) + rng.uniform(0, 5, m) - 3.0 * same
    toll = TRIP_CHARGE + distance * rate_per_km(entry, period, date.year) * np.where(heavy[idx], 1.65, 1.0)
    discount = toll * rng.choice([0.0, 0.10, 0.20], m, p=[0.86, 0.10, 0.04])
    timestamp = date + pd.to_timedelta(hour, unit="h") + pd.to_timedelta(rng.integers(0, 60, m), unit="m")
    return pd.DataFrame(
        {
            "customer_id": customer_ids[idx],
            "timestamp": timestamp,
            "zone_id": entry,
            "entry_zone": entry,
            "exit_zone": exit_,
            "direction": direction,
            "period": period,
            "distance_km": distance,
            "duration_min": distance / 1.45 + rng.uniform(1, 5, m),
            "toll": toll,
            "discount": discount,
            "final_charge": toll - discount,
        }
    )


def _daily_trips(rng, date, day, row, population, created_day, heavy, customer_ids):
    rate = daily_rate(population, day, row, created_day)
    counts = rng.poisson(np.clip(rate, 0, 6))
    idx = np.repeat(np.arange(len(population)), counts)
    m = len(idx)
    if not m:
        return None
    if row.weekend:
        period = np.full(m, "Weekend", dtype=object)
    else:
        period = np.where(rng.random(m) < peak_probability(population)[idx], "Peak", "Off-peak").astype(
            object
        )
    hour = _trip_hours(rng, period)
    home = population.col("latent_home_zone")[idx]
    work = population.col("latent_work_zone")[idx]
    morning = hour < 12
    peak = period == "Peak"
    entry = np.where(rng.random(m) < 0.7, home, rng.integers(0, len(ZONES), m))
    exit_ = np.where(rng.random(m) < 0.85, rng.integers(0, len(ZONES), m), entry)
    entry = np.where(peak, np.where(morning, home, work), entry)
    exit_ = np.where(peak, np.where(morning, work, home), exit_)
    return _trip_frame(rng, date, idx, period, hour, entry, exit_, heavy, customer_ids)


def _planted_customer_anomalies(rng, customers, population, heavy, customer_ids):
    """Cloned-transponder bursts and night trips far from home, in the 30 days before October."""
    stop = population.col("latent_stop_day")
    pool = np.flatnonzero(
        (customers.created_at < pd.Timestamp("2025-03-01")).to_numpy()
        & (stop > 700)
        & customers.transponder_flag.to_numpy()
    )
    chosen = rng.choice(pool, 30, replace=False)
    frames, labels = [], []
    for rank, i in enumerate(chosen):
        kind = "cloned_transponder" if rank < 20 else "night_far_zone"
        start = pd.Timestamp("2025-09-03") + pd.Timedelta(days=int(rng.integers(0, 19)))
        for offset in range(5 if kind == "cloned_transponder" else 6):
            date = start + pd.Timedelta(days=offset)
            count = int(rng.poisson(9 if kind == "cloned_transponder" else 3)) + 1
            idx = np.full(count, i)
            if kind == "cloned_transponder":
                hour = rng.integers(0, 24, count)
                entry = rng.integers(0, len(ZONES), count)
            else:
                hour = rng.integers(0, 5, count)
                home = population.col("latent_home_zone")[i]
                entry = np.full(count, 5 if home <= 2 else 0)
            exit_ = rng.integers(0, len(ZONES), count)
            weekend = date.dayofweek >= 5
            period = np.where(
                weekend, "Weekend", np.where(np.isin(hour, [7, 8, 9, 16, 17, 18]), "Peak", "Off-peak")
            )
            frames.append(
                _trip_frame(rng, date, idx, period.astype(object), hour, entry, exit_, heavy, customer_ids)
            )
        labels.append({"customer_id": customer_ids[i], "anomaly_type": kind, "window_start": start})
    return pd.concat(frames, ignore_index=True), pd.DataFrame(labels)


def _digital_events(rng, date, day, population, created_day, customer_ids):
    from .simulation import activity

    a = population.col("latent_digital_affinity")
    s = population.col("latent_sensitivity")
    p = (0.006 + 0.07 * a) * (0.25 + 0.75 * (activity(population, day) > 0.2))
    session = (rng.random(len(population)) < p) & (day >= created_day)
    idx = np.flatnonzero(session)
    m = len(idx)
    if not m:
        return None
    channel = np.where(
        rng.random(m) < 0.35 + 0.4 * a[idx], "App", np.where(rng.random(m) < 0.25, "Email", "Web")
    ).astype(object)
    start = date + pd.to_timedelta(rng.integers(6, 24, m), unit="h")
    view = rng.random(m) < 0.35
    click = view & (rng.random(m) < 0.12 + 0.09 * s[idx])
    enroll = click & (rng.random(m) < 0.25 + 0.30 * a[idx])
    email_open = channel == "Email"
    events = {
        "app_login": channel == "App",
        "web_login": channel == "Web",
        "notification_open": (channel == "App") & (rng.random(m) < 0.30),
        "email_open": email_open,
        "email_click": email_open & (rng.random(m) < 0.22),
        "offer_view": view,
        "offer_click": click,
        "offer_enroll": enroll,
        "pricing_page_view": rng.random(m) < 0.06 + 0.06 * s[idx],
        "trip_history_view": rng.random(m) < 0.18,
        "loyalty_page_view": rng.random(m) < 0.06 + 0.14 * a[idx],
    }
    parts = []
    for order, name in enumerate(DIGITAL_EVENTS):
        mask = events[name]
        if mask.any():
            parts.append(
                pd.DataFrame(
                    {
                        "customer_id": customer_ids[idx[mask]],
                        "timestamp": start[mask] + pd.to_timedelta(order, unit="m"),
                        "event_type": name,
                        "channel": channel[mask],
                    }
                )
            )
    return pd.concat(parts, ignore_index=True)


def _price_tests(rng, context):
    """Daily randomised effective-price tests by zone, period and customer segment."""
    rows = []
    for _, row in context.iterrows():
        for zone in range(len(ZONES)):
            for period in PERIODS:
                for segment in ("Personal", "Business"):
                    multiplier = rng.choice([0.7, 0.8, 0.9, 1.0, 1.05, 1.1])
                    base = (
                        70
                        * (1 + 0.1 * zone)
                        * (0.7 if row.weekend else 1.0)
                        * (1.2 if period == "Peak" else 0.8)
                    )
                    base *= np.exp(-0.018 * row.precipitation_mm) * (1 + 0.14 * row.month_sin)
                    base *= 1.0 if segment == "Personal" else 0.25
                    beta = -(0.6 + 0.13 * zone + (0.4 if period == "Weekend" else 0.0))
                    beta *= 1.0 if segment == "Personal" else 0.55
                    rows.append(
                        {
                            "date": row.date,
                            "zone_id": zone,
                            "period": period,
                            "segment": segment,
                            "effective_price": 10 * multiplier,
                            "assigned_price_multiplier": multiplier,
                            "demand": rng.poisson(base * multiplier**beta),
                            "temperature_c": row.temperature_c,
                            "precipitation_mm": row.precipitation_mm,
                            "weekend": row.weekend,
                            "holiday": row.holiday,
                            "month_sin": row.month_sin,
                            "month_cos": row.month_cos,
                            "_true_elasticity": beta,
                        }
                    )
    frame = pd.DataFrame(rows)
    truth = frame.groupby(["zone_id", "period", "segment"])._true_elasticity.first().rename("true_elasticity")
    return frame.drop(columns="_true_elasticity"), truth.reset_index()


def _bronze_feed(rng, trips):
    """Raw ingestion with metadata and four planted defects."""
    feed = trips.copy()
    day = feed.timestamp.dt.normalize()
    feed["ingested_at"] = day + pd.Timedelta(hours=23, minutes=30)
    late = day.eq("2025-07-23") & (rng.random(len(feed)) < 0.6)
    feed.loc[late, "ingested_at"] = pd.Timestamp("2025-07-24 23:30")
    unit = day.eq("2025-08-21") & (rng.random(len(feed)) < 0.35)
    feed.loc[unit, "distance_km"] *= 1000
    bad = rng.choice(len(feed), 120, replace=False)
    feed.loc[feed.index[bad[:60]], "final_charge"] = -feed.loc[feed.index[bad[:60]], "final_charge"]
    feed.loc[feed.index[bad[60:]], "toll"] *= 100
    feed.loc[feed.index[bad[60:]], "final_charge"] = (
        feed.loc[feed.index[bad[60:]], "toll"] - feed.loc[feed.index[bad[60:]], "discount"]
    )
    resent = feed[day.eq("2025-09-09")].sample(2500, random_state=int(rng.integers(1_000_000))).copy()
    resent["ingested_at"] = pd.Timestamp("2025-09-10 23:30")
    feed = pd.concat([feed, resent], ignore_index=True)
    feed["batch_id"] = "B" + feed.ingested_at.dt.strftime("%Y%m%d")
    feed["trip_id"] = [f"T{i:09}" for i in range(len(feed))]
    return feed


def conform_trips(feed):
    """Bronze -> silver: dedupe on the natural key, quarantine contract violations."""
    key = ["customer_id", "timestamp", "entry_zone", "exit_zone", "toll"]
    ordered = feed.sort_values(["ingested_at", "trip_id"], kind="stable")
    duplicate = ordered.duplicated(key, keep="first")
    reasons = pd.Series("", index=ordered.index)
    reasons[duplicate] = "duplicate_natural_key"
    reasons[(reasons == "") & ~ordered.distance_km.between(0.5, 120)] = "distance_out_of_range"
    reasons[(reasons == "") & ~ordered.toll.between(0, 150)] = "charge_out_of_range"
    reasons[(reasons == "") & ((ordered.final_charge < 0) | (ordered.discount > ordered.toll))] = (
        "charge_out_of_range"
    )
    quarantine = ordered[reasons != ""].assign(reason=reasons[reasons != ""])
    clean = (
        ordered[reasons == ""]
        .drop(columns=["ingested_at", "batch_id"])
        .sort_values("timestamp", kind="stable")
    )
    return clean.reset_index(drop=True), quarantine.reset_index(drop=True)


def generate(cfg, context):
    rng = np.random.default_rng(cfg.seed)
    n = cfg.customers
    customers = _customers(rng, n, cfg.seed)
    population = draw_population(rng, n, customers.customer_type)
    customers["home_zone"] = population.col("latent_home_zone")
    created_day = (customers.created_at - WINDOW_START).dt.days.to_numpy()
    heavy = customers.vehicle_class.eq("Heavy").to_numpy()
    customer_ids = customers.customer_id.to_numpy()

    trip_parts, event_parts = [], []
    for day, row in context.iterrows():
        trips = _daily_trips(rng, row.date, day, row, population, created_day, heavy, customer_ids)
        if trips is not None:
            trip_parts.append(trips)
        events = _digital_events(rng, row.date, day, population, created_day, customer_ids)
        if events is not None:
            event_parts.append(events)
    anomalous, anomaly_labels = _planted_customer_anomalies(rng, customers, population, heavy, customer_ids)
    trips = pd.concat([*trip_parts, anomalous], ignore_index=True).sort_values("timestamp", kind="stable")
    trips = trips.reset_index(drop=True)
    feed = _bronze_feed(rng, trips)
    trips, quarantine = conform_trips(feed)

    events = pd.concat(event_parts, ignore_index=True)
    events.insert(0, "event_id", [f"D{i:09}" for i in range(len(events))])

    accounts = customers[
        ["account_id", "customer_id", "account_status", "autopay", "past_due", "created_at"]
    ].copy()
    vehicles = customers[["customer_id", "vehicle_class", "transponder_flag"]].copy()
    vehicles.insert(0, "vehicle_id", [f"V{i:06}" for i in range(n)])
    zones = pd.DataFrame({"zone_id": range(len(ZONES)), "zone_name": ZONES, "is_synthetic": True})
    loyalty = trips[["trip_id", "customer_id", "timestamp", "final_charge"]].copy()
    loyalty["points_earned"] = np.floor(loyalty.final_charge * 2).astype(int)
    loyalty = loyalty.drop(columns="final_charge")
    pricing, elasticity_truth = _price_tests(rng, context)

    frames = {
        "dim_customer": customers,
        "dim_account": accounts,
        "dim_vehicle": vehicles,
        "dim_zone": zones,
        "dim_offer": OFFER_CATALOG.copy(),
        "fact_trip": trips,
        "fact_digital_event": events,
        "fact_loyalty_points": loyalty,
        "fact_pricing_scenario": pricing,
        "external_context": context,
        "quarantine_trip": quarantine,
    }
    frames["dim_transponder"] = customers.loc[
        customers.transponder_flag, ["customer_id", "account_id"]
    ].assign(transponder_id=lambda x: "T" + x.account_id.str[1:])
    frames["customer_preferences"] = customers[
        ["customer_id", "marketing_consent", "autopay", "has_my_account"]
    ].copy()
    frames["customer_status_history"] = _status_history(customers, cfg.seed)
    frames["dim_entry_point"] = zones[["zone_id", "zone_name"]].assign(
        entry_point_id=lambda x: "E" + x.zone_id.astype(str)
    )
    frames["dim_exit_point"] = zones[["zone_id", "zone_name"]].assign(
        exit_point_id=lambda x: "X" + x.zone_id.astype(str)
    )
    frames["dim_time"] = context[["date", "weekend", "holiday"]].assign(
        day_of_week=context.date.dt.dayofweek, month=context.date.dt.month, year=context.date.dt.year
    )
    rate = pd.MultiIndex.from_product(
        [range(len(ZONES)), PERIODS, ["Light", "Heavy"]], names=["zone_id", "period", "vehicle_class"]
    ).to_frame(index=False)
    rate["rate_per_km"] = rate_per_km(rate.zone_id, rate.period) * np.where(
        rate.vehicle_class.eq("Heavy"), 1.65, 1.0
    )
    rate["trip_charge"] = TRIP_CHARGE
    frames["dim_rate"] = rate
    frames["fact_effective_price"] = trips[
        [
            "trip_id",
            "customer_id",
            "timestamp",
            "zone_id",
            "period",
            "distance_km",
            "toll",
            "discount",
            "final_charge",
        ]
    ].assign(effective_price_per_km=lambda x: x.final_charge / x.distance_km)
    frames["dim_reward"] = pd.DataFrame(
        {
            "reward_id": ["loyalty_500", "loyalty_1500"],
            "reward_name": ["500-point travel reward", "1,500-point travel reward"],
            "points_cost": [500, 1500],
            "max_value_cad": [5.0, 15.0],
        }
    )
    balances = (
        loyalty[loyalty.timestamp < pd.Timestamp(cfg.decision_date)]
        .groupby("customer_id")
        .points_earned.sum()
        .reindex(customer_ids, fill_value=0)
        .to_numpy()
    )
    frames["fact_loyalty_tier"] = pd.DataFrame(
        {
            "customer_id": customer_ids,
            "as_of": cfg.decision_date,
            "tier": np.where(balances >= 3000, "Platinum", np.where(balances >= 1000, "Gold", "Silver")),
        }
    )

    bronze, silver = cfg.path("data", "bronze"), cfg.path("data", "silver")
    for folder in (bronze, silver):
        folder.mkdir(parents=True, exist_ok=True)
    for name, frame in frames.items():
        frame.to_parquet(silver / f"{name}.parquet", index=False)
        if name not in {"fact_trip", "quarantine_trip"}:
            frame.to_parquet(bronze / f"{name}.parquet", index=False)
    feed.to_parquet(bronze / "fact_trip.parquet", index=False)

    audit = cfg.path("data", "simulation_audit")
    audit.mkdir(parents=True, exist_ok=True)
    hidden = population.frame.copy()
    hidden.insert(0, "customer_id", customer_ids)
    hidden["created_day"] = created_day
    hidden.to_parquet(audit / "hidden_parameters.parquet", index=False)
    anomaly_labels.to_parquet(audit / "planted_anomalies.parquet", index=False)
    pd.DataFrame(DATA_DEFECTS, columns=["ingestion_date", "defect"]).to_parquet(
        audit / "planted_data_defects.parquet", index=False
    )
    elasticity_truth.to_parquet(audit / "true_elasticity.parquet", index=False)
    quality = validate(frames)
    quality["bronze_rows"] = len(feed)
    quality["quarantined"] = quarantine.reason.value_counts().to_dict()
    write_json(cfg.path("outputs", "data_quality.json"), quality)
    return frames, hidden


def _status_history(customers, seed):
    """Effective-dated account status and consent, with a March 2025 change for 8% of customers."""
    state = customers[["customer_id", "account_status", "marketing_consent", "created_at"]].copy()
    changed = state.sample(frac=0.08, random_state=seed + 71).customer_id
    initial = state.rename(columns={"created_at": "effective_from"}).copy()
    initial["effective_to"] = pd.NaT
    mask = initial.customer_id.isin(changed) & (initial.effective_from < pd.Timestamp("2025-03-01"))
    initial.loc[mask, "effective_to"] = pd.Timestamp("2025-03-01")
    initial.loc[mask, "account_status"] = np.where(
        initial.loc[mask, "account_status"].eq("Active"), "Suspended", "Active"
    )
    initial.loc[mask, "marketing_consent"] = ~initial.loc[mask, "marketing_consent"]
    later = state[state.customer_id.isin(initial.loc[mask, "customer_id"])].rename(
        columns={"created_at": "effective_from"}
    )
    later = later.assign(effective_from=pd.Timestamp("2025-03-01"), effective_to=pd.NaT)
    return pd.concat([initial, later], ignore_index=True)


def validate(frames):
    c, t, d = frames["dim_customer"], frames["fact_trip"], frames["fact_digital_event"]
    first_trip = t.groupby("customer_id").timestamp.min()
    created = c.set_index("customer_id").created_at
    checks = {
        "customer_key_unique": not c.customer_id.duplicated().any(),
        "trip_key_unique": not t.trip_id.duplicated().any(),
        "event_key_unique": not d.event_id.duplicated().any(),
        "customer_fk": set(t.customer_id).issubset(set(c.customer_id)),
        "digital_customer_fk": set(d.customer_id).issubset(set(c.customer_id)),
        "zone_fk": set(t.zone_id).issubset(set(frames["dim_zone"].zone_id)),
        "exit_zone_fk": set(t.exit_zone).issubset(set(frames["dim_zone"].zone_id)),
        "nonnegative_charge": bool((t.final_charge >= 0).all()),
        "discount_within_toll": bool(((t.discount >= 0) & (t.discount <= t.toll)).all()),
        "charge_reconciles": bool(np.allclose(t.toll - t.discount, t.final_charge)),
        "timestamps_present": bool(t.timestamp.notna().all()),
        "distance_in_range": bool(t.distance_km.between(0.5, 120).all()),
        "no_trip_before_account": bool(
            (first_trip >= created.reindex(first_trip.index).dt.normalize()).all()
        ),
        "natural_key_unique": not t.duplicated(
            ["customer_id", "timestamp", "entry_zone", "exit_zone", "toll"]
        ).any(),
    }
    if not all(checks.values()):
        raise ValueError(f"Data contract failed: {checks}")
    return {"status": "passed", "checks": checks, "rows": {k: len(v) for k, v in frames.items()}}
