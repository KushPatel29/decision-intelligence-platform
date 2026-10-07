"""30-day fixed-origin demand forecasting by zone, period and day.

A planning forecast is made once, on the decision date, for the next 30 days.
So the training set is built the same way: weekly forecast origins, each with
the 30 target days that follow and only information available at the origin
(same-weekday means, recent level and trend, the calendar). The learned model
predicts a multiplicative correction to the same-weekday mean, which keeps it
anchored to the latest level when the population drifts.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import PARQUET
from .simulation import PERIODS, ZONES

HORIZON = 30


def daily_cells(cfg, trips, context):
    daily = (
        trips.assign(date=trips.timestamp.dt.normalize())
        .groupby(["date", "zone_id", "period"])
        .size()
        .rename("trips")
        .reset_index()
    )
    grid = pd.MultiIndex.from_product(
        [pd.date_range(cfg.start, cfg.end), range(len(ZONES)), PERIODS], names=["date", "zone_id", "period"]
    ).to_frame(index=False)
    frame = grid.merge(daily, on=["date", "zone_id", "period"], how="left").fillna({"trips": 0})
    frame = frame.merge(context, on="date", how="left", validate="many_to_one")
    frame["dow"] = frame.date.dt.dayofweek
    frame["period_code"] = frame.period.map({p: i for i, p in enumerate(PERIODS)})
    return frame.sort_values(["zone_id", "period", "date"]).reset_index(drop=True)


def horizon_dataset(frame, context, origins=None):
    """One row per (origin, cell, target day) with origin-time features only."""
    dates = pd.DatetimeIndex(sorted(frame.date.unique()))
    cells = frame[["zone_id", "period"]].drop_duplicates().reset_index(drop=True)
    wide = frame.pivot_table(index="date", columns=["zone_id", "period"], values="trips").reindex(
        columns=pd.MultiIndex.from_frame(cells)
    )
    values = wide.to_numpy(float)
    if origins is None:
        origins = pd.date_range(dates[0] + pd.Timedelta(days=56), "2025-09-01", freq="7D")
    position = {d: i for i, d in enumerate(dates)}
    holidays = context.set_index("date").holiday
    rows = []
    for origin in origins:
        o = position[pd.Timestamp(origin)]
        rolling = values[o - 28 : o].mean(axis=0)
        previous = values[o - 56 : o - 28].mean(axis=0)
        for h in range(HORIZON):
            t = o + h
            if t >= len(dates):
                break
            d1 = o - 7 + (h % 7)
            same = values[[d1, d1 - 7, d1 - 14, d1 - 21]]
            target = dates[t]
            day_of_year = target.dayofyear
            rows.append(
                pd.DataFrame(
                    {
                        "origin": dates[o],
                        "date": target,
                        "zone_id": cells.zone_id.to_numpy(),
                        "period": cells.period.to_numpy(),
                        "horizon": h,
                        "dow": target.dayofweek,
                        "holiday": int(holidays.get(target, 0)),
                        "month_sin": np.sin(2 * np.pi * day_of_year / 365.25),
                        "month_cos": np.cos(2 * np.pi * day_of_year / 365.25),
                        "sdw4": same.mean(axis=0),
                        "lag7": same[0],
                        "rolling28": rolling,
                        "trend": np.log((rolling + 1) / (previous + 1)),
                        "trips": values[t],
                    }
                )
            )
    data = pd.concat(rows, ignore_index=True)
    data["period_code"] = data.period.map({p: i for i, p in enumerate(PERIODS)})
    data["log_sdw4"] = np.log1p(data.sdw4)
    data["log_rolling28"] = np.log1p(data.rolling28)
    data["log_ratio"] = np.log1p(data.trips) - data.log_sdw4
    # Weekend cells are empty on weekdays and vice versa; skip structurally-zero rows.
    weekend = data.date.dt.dayofweek >= 5
    structural = (data.period.eq("Weekend") & ~weekend) | (~data.period.eq("Weekend") & weekend)
    return data[~structural].reset_index(drop=True)


def interval_radius(rows, prediction, level=0.90):
    """Split-conformal radius on the log scale, one per travel period."""
    residual = np.abs(np.log1p(rows.trips.to_numpy()) - np.log1p(np.maximum(prediction, 0)))
    frame = pd.DataFrame({"period": rows.period.to_numpy(), "residual": residual})
    return {
        period: float(np.quantile(group.residual, level, method="higher"))
        for period, group in frame.groupby("period")
    }


def bounds(prediction, periods, radius):
    r = pd.Series(periods).map(radius).to_numpy()
    base = np.log1p(np.maximum(prediction, 0))
    return np.maximum(np.expm1(base - r), 0), np.expm1(base + r)


def hourly_forecast(cfg, trips, daily_forecast):
    """Disaggregate the daily champion with pre-cutoff hour/direction shares."""
    cutoff = pd.Timestamp(cfg.decision_date)
    history = trips[(trips.timestamp < cutoff) & (trips.timestamp >= cutoff - pd.Timedelta(days=90))].copy()
    history["hour"] = history.timestamp.dt.hour
    profile = history.groupby(["zone_id", "period", "direction", "hour"]).size().rename("count").reset_index()
    profile["share"] = profile["count"] / profile.groupby(["zone_id", "period"])["count"].transform("sum")
    future = daily_forecast[["date", "zone_id", "period", "baseline_forecast"]].merge(
        profile, on=["zone_id", "period"], validate="many_to_many"
    )
    future["forecast_trips"] = future.baseline_forecast * future.share
    future["method"] = "Daily champion disaggregated with pre-cutoff hour/direction shares"
    future.to_csv(cfg.path("outputs", "zone_hour_forecast.csv"), index=False)
    future.to_parquet(cfg.path("data", "gold", "zone_hour.parquet"), index=False, **PARQUET)
    return future
