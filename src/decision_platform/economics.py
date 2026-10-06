"""Offer terms: what each offer costs and earns, given baseline and incremental trips.

These are contract mechanics a toll operator knows exactly (a 15% off-peak
discount costs 15% of every off-peak trip taken during the offer, including
trips that would have happened anyway). Only the behavioural response is
uncertain, so models estimate trips and this module turns trips into money.
The simulator uses the same terms with true trips; the planner uses them with
estimated trips.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import poisson

PERIODS = ["Peak", "Off-peak", "Weekend"]
CONTACT_COST = 0.35
LOYALTY_LIABILITY = {"loyalty_500": 5.0, "loyalty_1500": 15.0}
PASS_CAP = 30.0
SPEND_REWARD = 10.0


def spend_threshold(expected_spend):
    """Personalised 'spend X, get $10' threshold: 1.3x expected 30-day spend, in $5 steps, at least $25."""
    return np.maximum(25.0, 5 * np.ceil(1.3 * np.asarray(expected_spend, float) / 5))


def at_least(k, mean):
    return poisson.sf(np.asarray(k) - 1, np.maximum(np.asarray(mean, float), 1e-12))


def expected_excess(cap, toll, mean):
    """E[max(0, toll * N - cap)] for N ~ Poisson(mean), computed exactly."""
    mean = np.maximum(np.asarray(mean, float), 1e-12)
    k = np.arange(0, 90)
    pmf = poisson.pmf(k[None, :], mean[:, None])
    spend = np.asarray(toll, float)[:, None] * k[None, :]
    return (np.maximum(spend - np.asarray(cap, float)[:, None], 0) * pmf).sum(axis=1)


def incentive_cost(offer_id, base, trips, tolls, threshold_spend=None):
    """Expected incentive cost of one offer per customer, contact cost included.

    `base`, `trips` and `tolls` are frames with one column per period: expected
    control trips, incremental trips and toll per trip.
    """
    base = base[PERIODS].to_numpy(float)
    trips = trips[PERIODS].to_numpy(float)
    tolls = tolls[PERIODS].to_numpy(float)
    treated = np.maximum(base + trips, 0)
    total = treated.sum(axis=1)
    mu = base.sum(axis=1)
    avg_toll = np.where(mu > 1e-9, (base * tolls).sum(axis=1) / np.maximum(mu, 1e-9), tolls[:, 1])
    if offer_id == "rush_hour_25":
        cost = 0.25 * tolls[:, 0] * treated[:, 0]
    elif offer_id == "offpeak_15":
        cost = 0.15 * tolls[:, 1] * treated[:, 1]
    elif offer_id == "pct_10":
        cost = 0.10 * (treated * tolls).sum(axis=1)
    elif offer_id == "weekend_20":
        cost = 0.20 * tolls[:, 2] * treated[:, 2]
    elif offer_id == "spend_10":
        spend = (base * tolls).sum(axis=1) if threshold_spend is None else np.asarray(threshold_spend, float)
        needed = np.ceil(spend_threshold(spend) / np.maximum(avg_toll, 0.5))
        cost = SPEND_REWARD * at_least(needed, total)
    elif offer_id == "free_trip":
        cost = avg_toll * at_least(5, total)
    elif offer_id == "offpeak_pass":
        cost = expected_excess(np.full(len(base), PASS_CAP), tolls[:, 1], treated[:, 1])
    elif offer_id in LOYALTY_LIABILITY:
        cost = np.full(len(base), LOYALTY_LIABILITY[offer_id])
    else:
        raise ValueError(f"Unknown offer {offer_id}")
    return np.asarray(cost, float) + CONTACT_COST


def window_value(offer_id, base, trips, tolls, margin, threshold_spend=None):
    """Expected 30-day incremental gross contribution, incentive cost and net contribution."""
    gross = margin * (trips[PERIODS].to_numpy(float) * tolls[PERIODS].to_numpy(float)).sum(axis=1)
    cost = incentive_cost(offer_id, base, trips, tolls, threshold_spend)
    return pd.DataFrame({"gross": gross, "cost": cost, "net": gross - cost})
