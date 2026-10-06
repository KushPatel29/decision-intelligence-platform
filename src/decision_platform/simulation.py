"""Ground truth for the synthetic toll-road population.

The simulator owns every hidden customer trait and the *true* response of each
customer to each offer. Nothing in this module may feed a model, a feature, the
optimizer or the app's decisions: models only ever see observed tables. The
evaluation code (`evaluation.py`) is the one consumer allowed to call the truth,
so that every targeting policy can be scored against the value it would really
have produced.

All rates, zones, offers and behaviours are invented. This is not 407 ETR's
network, tariff, offer logic or customer behaviour.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

ZONES = ["West", "Northwest", "Central", "Northeast", "East", "Outer east"]
PERIODS = ["Peak", "Off-peak", "Weekend"]
WINDOW_START = pd.Timestamp("2024-01-01")

from .economics import CONTACT_COST, spend_threshold, window_value  # noqa: E402, F401

TRIP_CHARGE = 1.00  # Fixed per-trip charge, never discounted.
POINT_VALUE = 0.01  # CAD liability per loyalty point.


def rate_per_km(zone, period, year=2025):
    """Invented distance rate: peak premium plus a mild west-to-east gradient."""
    zone = np.asarray(zone, dtype=float)
    peak = np.asarray(period) == "Peak"
    base = 0.26 + 0.08 * peak + 0.012 * zone
    return base * np.where(np.asarray(year) >= 2025, 1.035, 1.0)


# Offer catalogue. `period` is the travel period an offer is designed to fill;
# offers marked "Mixed" add trips in proportion to the customer's own travel mix.
OFFER_CATALOG = pd.DataFrame(
    [
        ("offpeak_15", "Off-peak 15% off", "Off-peak discount", "Off-peak", 0.15, 0.0, 0, 9000),
        ("pct_10", "10% off every trip", "Percentage discount", "Mixed", 0.10, 0.0, 0, 9000),
        ("weekend_20", "Weekend 20% off", "Weekend incentive", "Weekend", 0.20, 0.0, 0, 9000),
        ("spend_10", "Spend & get $10", "Spend threshold reward", "Mixed", 0.0, 10.0, 0, 9000),
        ("free_trip", "Fifth trip free", "Free-trip reward", "Mixed", 0.0, 0.0, 0, 3000),
        ("offpeak_pass", "Off-peak pass ($30 cap)", "Driving pass", "Off-peak", 0.0, 30.0, 0, 9000),
        ("loyalty_500", "500 bonus points", "Loyalty reward", "Mixed", 0.0, 5.0, 500, 9000),
        ("loyalty_1500", "1,500 bonus points", "Loyalty reward", "Mixed", 0.0, 15.0, 1500, 1200),
    ],
    columns=[
        "offer_id",
        "offer_name",
        "offer_type",
        "period",
        "discount_pct",
        "reward_value",
        "points",
        "inventory",
    ],
)
OFFERS = OFFER_CATALOG.offer_id.tolist()
ARMS = ["Control"] + OFFER_CATALOG.offer_name.tolist()
OFFER_ARMS = dict(zip(OFFER_CATALOG.offer_id, OFFER_CATALOG.offer_name, strict=True))
LOYALTY_OFFERS = {"loyalty_500", "loyalty_1500"}


@dataclass(frozen=True)
class Population:
    """Hidden traits, one row per customer, aligned with `dim_customer`."""

    frame: pd.DataFrame

    def __len__(self):
        return len(self.frame)

    def col(self, name):
        return self.frame[name].to_numpy()


def draw_population(rng, n, customer_type):
    business = np.asarray(customer_type) == "Business"
    frequency = np.exp(rng.normal(-1.95, 1.0, n)) * np.where(business, 1.6, 1.0)
    sensitivity = rng.uniform(0.35, 2.0, n) * np.where(business, 0.6, 1.0)
    churner = rng.random(n) < 0.30
    home = rng.integers(0, len(ZONES), n)
    shift = rng.choice([-3, -2, -1, 1, 2, 3], n)
    work = np.where(rng.random(n) < 0.85, np.clip(home + shift, 0, len(ZONES) - 1), home)
    return Population(
        pd.DataFrame(
            {
                "latent_frequency": frequency,
                "latent_sensitivity": sensitivity,
                "latent_digital_affinity": rng.beta(2, 2, n),
                "latent_commuter": rng.beta(2, 2.2, n),
                "latent_weekend_affinity": rng.beta(2, 3, n),
                "latent_stop_day": np.where(churner, rng.integers(300, 700, n), 100_000),
                "latent_home_zone": home,
                "latent_work_zone": work,
            }
        )
    )


def activity(population, day_index):
    """Multiplicative churn drift on a given day (1 = fully active)."""
    stop = population.col("latent_stop_day")
    return np.exp(-np.maximum(day_index - stop, 0) / 22.0)


def calendar_effect(population, weekend, holiday):
    if holiday:
        return np.full(len(population), 0.6)
    if weekend:
        return 0.35 + 1.1 * population.col("latent_weekend_affinity")
    return np.ones(len(population))


def peak_probability(population):
    return 0.15 + 0.70 * population.col("latent_commuter")


def daily_rate(population, day_index, row, created_day):
    seasonal = 1 + 0.16 * np.sin(2 * np.pi * day_index / 365.25)
    weather = np.exp(-0.018 * row.precipitation_mm)
    rate = (
        population.col("latent_frequency")
        * activity(population, day_index)
        * seasonal
        * weather
        * calendar_effect(population, bool(row.weekend), bool(row.holiday))
    )
    return np.where(day_index >= created_day, rate, 0.0)


def commute_distance(population):
    gap = np.abs(population.col("latent_work_zone") - population.col("latent_home_zone"))
    return 7.0 + 8.5 * gap + 2.5


LEISURE_DISTANCE = 7.0 + 8.5 * 1.6 + 2.5


def expected_tolls(population, vehicle_class, year=2025):
    """Expected toll per trip in each period for every customer."""
    heavy = np.where(np.asarray(vehicle_class) == "Heavy", 1.65, 1.0)
    zone = population.col("latent_home_zone")
    peak = TRIP_CHARGE + commute_distance(population) * rate_per_km(zone, "Peak", year) * heavy
    off = TRIP_CHARGE + LEISURE_DISTANCE * rate_per_km(zone, "Off-peak", year) * heavy
    return pd.DataFrame({"Peak": peak, "Off-peak": off, "Weekend": off})


def expected_window_trips(population, context, start, days, created_day):
    """Expected control trips per period over [start, start+days) from the true rate."""
    start = pd.Timestamp(start)
    window = context[(context.date >= start) & (context.date < start + pd.Timedelta(days=days))]
    if len(window) != days:
        raise ValueError("Context does not cover the requested window")
    p_peak = peak_probability(population)
    totals = {period: np.zeros(len(population)) for period in PERIODS}
    for _, row in window.iterrows():
        day = (row.date - WINDOW_START).days
        rate = daily_rate(population, day, row, created_day)
        if row.weekend:
            totals["Weekend"] += rate
        else:
            totals["Peak"] += rate * p_peak
            totals["Off-peak"] += rate * (1 - p_peak)
    return pd.DataFrame(totals)


def _split(total, base):
    """Distribute incremental trips in proportion to the customer's own mix."""
    values = base.to_numpy(float)
    totals = values.sum(axis=1, keepdims=True)
    mix = np.where(totals > 1e-9, values / np.maximum(totals, 1e-9), 1 / 3)
    return pd.DataFrame(mix * np.asarray(total)[:, None], columns=base.columns, index=base.index)


def offer_truth(population, base, tolls, offer_id, margin, later_discount=1.10**0.25):
    """True expected 30-day effects of one offer for every customer.

    `base` holds expected control trips by period over the offer window and
    `tolls` the expected toll per trip by period. The behavioural response
    (incremental trips by period, persistence, retention) is the simulator's
    hidden truth; the money follows from the offer terms in `economics.py`.
    """
    s = population.col("latent_sensitivity")
    a = population.col("latent_digital_affinity")
    c = population.col("latent_commuter")
    w = population.col("latent_weekend_affinity")
    mu = base.sum(axis=1).to_numpy()
    avg_toll = (base * tolls).sum(axis=1).to_numpy() / np.maximum(mu, 1e-9)
    avg_toll = np.where(mu > 1e-9, avg_toll, tolls["Off-peak"].to_numpy())
    zero = np.zeros(len(population))
    trips = pd.DataFrame({p: zero.copy() for p in PERIODS})
    persistence, retention = 0.25, 0.01 + 0.025 * s / 2

    if offer_id == "offpeak_15":
        off = (0.08 + 0.20 * s) * (1.25 - c) * (base["Off-peak"].to_numpy() + 0.6)
        trips["Off-peak"] = off
        trips["Peak"] = -np.minimum(0.15 * off * c, base["Peak"].to_numpy())  # Flexible commuters shift.
    elif offer_id == "pct_10":
        trips = base.mul(0.05 + 0.12 * s, axis=0)
    elif offer_id == "weekend_20":
        trips["Weekend"] = (0.10 + 0.24 * s) * (0.5 + 1.2 * w) * (base["Weekend"].to_numpy() + 0.5)
    elif offer_id == "spend_10":
        spend = mu * avg_toll
        threshold = spend_threshold(spend)
        gradient = np.exp(-((((spend / threshold) - 0.8) / 0.3) ** 2))
        trips = _split((0.3 + 0.8 * s) * gradient * (0.8 + 0.3 * a), base)
    elif offer_id == "free_trip":
        trips = _split((0.5 + 1.3 * s) * np.exp(-mu / 7.0) * (0.7 + 0.6 * a), base)
    elif offer_id == "offpeak_pass":
        off_spend = base["Off-peak"].to_numpy() * tolls["Off-peak"].to_numpy()
        trips["Off-peak"] = (0.3 + 0.9 * s) * (1 / (1 + np.exp(-(off_spend - 20) / 6))) * (1.2 - c)
    elif offer_id in LOYALTY_OFFERS:
        total = (0.25 + 1.3 * a) * (0.4 + 0.4 * s) * (1 - np.exp(-(mu + 1) / 5))
        scale = 1.65 if offer_id == "loyalty_1500" else 1.0
        trips = _split(total * scale, base)
        persistence = 0.40
        retention = (0.02 + 0.06 * a) * (1.5 if offer_id == "loyalty_1500" else 1.0)
    else:
        raise ValueError(f"Unknown offer {offer_id}")

    money = window_value(offer_id, base, trips, tolls, margin)
    incremental = trips.sum(axis=1).to_numpy()
    later = persistence * 2 * incremental * avg_toll * margin / later_discount
    return pd.DataFrame(
        {
            "true_trips_peak": trips["Peak"].to_numpy(),
            "true_trips_offpeak": trips["Off-peak"].to_numpy(),
            "true_trips_weekend": trips["Weekend"].to_numpy(),
            "true_incremental_trips": incremental,
            "true_cost": money.cost.to_numpy(),
            "true_net_contribution": money.net.to_numpy(),
            "true_later_margin": later,
            "true_retention_effect": retention,
            "true_response_effect": np.exp(-mu) - np.exp(-(mu + incremental)),
            "true_value": money.net.to_numpy() + later,
        }
    )


def truth_table(population, base, tolls, margin):
    """True effects of every offer for every customer, long format."""
    frames = []
    for offer_id in OFFERS:
        frame = offer_truth(population, base, tolls, offer_id, margin)
        frame.insert(0, "offer_id", offer_id)
        frame.insert(0, "row", np.arange(len(population)))
        frames.append(frame)
    return pd.concat(frames, ignore_index=True)
