"""Fixed-origin monthly seasonal forecasts and pre-cutoff hour/direction allocation."""

import numpy as np
import pandas as pd

from .config import write_json


def horizon_validation(cfg, frame):
    rows = []
    for origin in ["2025-04-01", "2025-05-01", "2025-06-01", "2025-07-01", "2025-08-01", "2025-09-01"]:
        start = pd.Timestamp(origin)
        history = frame[(frame.date < start) & (frame.date >= start - pd.Timedelta(days=28))]
        means = history.groupby(["zone_id", "period", "dow"]).trips.mean().rename("prediction").reset_index()
        actual = frame[(frame.date >= start) & (frame.date < start + pd.Timedelta(days=30))]
        evaluated = actual[["date", "zone_id", "period", "dow", "trips"]].merge(
            means, on=["zone_id", "period", "dow"], validate="many_to_one"
        )
        evaluated["origin"] = origin
        evaluated["split"] = "validation" if start < pd.Timestamp("2025-07-01") else "test"
        rows.append(evaluated)
    result = pd.concat(rows, ignore_index=True)
    calibration = result[result.split.eq("validation")]
    radius = float(np.quantile(abs(calibration.trips - calibration.prediction), 0.90, method="higher"))
    result["lower_90"] = np.maximum(result.prediction - radius, 0)
    result["upper_90"] = result.prediction + radius
    result.to_csv(cfg.path("outputs", "demand_horizon_backtest.csv"), index=False)
    test = result[result.split.eq("test")]
    report = {
        "horizon_days": 30,
        "method": "Same weekday mean from previous 28 days, frozen at each origin",
        "test_origins": 3,
        "test_mae": float(abs(test.trips - test.prediction).mean()),
        "validation_interval_radius": radius,
        "test_interval_coverage": float(
            ((test.trips >= test.lower_90) & (test.trips <= test.upper_90)).mean()
        ),
        "nominal_coverage": 0.90,
        "n_test": len(test),
        "limitations": "Marginal validation-residual intervals; dependent cells and overlapping origins, no simultaneous or hourly coverage guarantee",
    }
    write_json(cfg.path("outputs", "demand_horizon_metrics.json"), report)
    return report


def hourly_forecast(cfg, trips, daily_forecast):
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
    future.to_parquet(cfg.path("data", "gold", "zone_hour.parquet"), index=False)
    return future
