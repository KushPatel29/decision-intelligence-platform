"""Download and cache three real public datasets. Failure is explicit, never replaced with fiction."""

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd

from .config import PARQUET, write_json

SOURCES = {
    "weather": "https://archive-api.open-meteo.com/v1/archive?latitude=43.65&longitude=-79.38&start_date=2024-01-01&end_date=2025-12-31&daily=temperature_2m_mean,precipitation_sum,sunrise,sunset&timezone=America%2FToronto",
    "economy": "https://www.bankofcanada.ca/valet/observations/FXCADUSD/json?start_date=2024-01-01&end_date=2025-12-31",
    "holidays_2024": "https://date.nager.at/api/v3/PublicHolidays/2024/CA",
    "holidays_2025": "https://date.nager.at/api/v3/PublicHolidays/2025/CA",
}


def fetch(cfg, refresh=False):
    folder = cfg.path("data", "external")
    folder.mkdir(parents=True, exist_ok=True)

    def get(item):
        name, url = item
        target = folder / f"{name}.json"
        metadata = folder / f"{name}.provenance.json"
        if refresh or not target.exists():
            request = Request(url, headers={"User-Agent": "DecisionSciencePortfolio/0.1 (educational)"})
            with urlopen(request, timeout=45) as response:
                payload = response.read()
            json.loads(payload)  # Validate before saving.
            target.write_bytes(payload)
            write_json(
                metadata,
                {
                    "source_url": url,
                    "retrieved_at_utc": datetime.now(UTC).isoformat(),
                    "sha256": hashlib.sha256(payload).hexdigest(),
                    "status": "downloaded",
                },
            )
        return name, json.loads(target.read_text(encoding="utf-8"))

    with ThreadPoolExecutor(max_workers=4) as pool:
        raw = dict(pool.map(get, SOURCES.items()))
    weather = pd.DataFrame(raw["weather"]["daily"]).rename(
        columns={
            "time": "date",
            "temperature_2m_mean": "temperature_c",
            "precipitation_sum": "precipitation_mm",
        }
    )
    weather["date"] = pd.to_datetime(weather.date)
    weather["daylight_hours"] = (
        pd.to_datetime(weather.sunset) - pd.to_datetime(weather.sunrise)
    ).dt.total_seconds() / 3600
    economy = pd.DataFrame(
        [
            {"date": r["d"], "cad_usd": float(r["FXCADUSD"]["v"])}
            for r in raw["economy"]["observations"]
            if "FXCADUSD" in r
        ]
    )
    economy["date"] = pd.to_datetime(economy.date)
    holiday_rows = []
    for year in (2024, 2025):
        for r in raw[f"holidays_{year}"]:
            if r["global"] or "CA-ON" in (r.get("counties") or []):
                holiday_rows.append({"date": pd.Timestamp(r["date"]), "holiday_name": r["name"]})
    holidays = (
        pd.DataFrame(holiday_rows)
        .groupby("date", as_index=False)
        .agg(holiday_name=("holiday_name", lambda v: "; ".join(sorted(set(v)))))
    )
    dates = pd.DataFrame({"date": pd.date_range(cfg.start, cfg.end)})
    result = dates.merge(weather.drop(columns=["sunrise", "sunset"]), on="date", how="left")
    # Only forward fill macro data. Initial gap is missing, NOT filled from future observations.
    result = pd.merge_asof(
        result.sort_values("date"), economy.sort_values("date"), on="date", direction="backward"
    )
    result = result.merge(holidays, on="date", how="left")
    result["holiday"] = result.holiday_name.notna().astype(int)
    result["weekend"] = (result.date.dt.dayofweek >= 5).astype(int)
    result["month_sin"] = np.sin(2 * np.pi * result.date.dt.dayofyear / 365.25)
    result["month_cos"] = np.cos(2 * np.pi * result.date.dt.dayofyear / 365.25)
    if result[["temperature_c", "precipitation_mm", "daylight_hours"]].isna().any().any():
        raise ValueError("Weather feed has gaps. Inspect source; synthetic replacement is prohibited.")
    result.to_parquet(folder / "daily_context.parquet", index=False, **PARQUET)
    return result
