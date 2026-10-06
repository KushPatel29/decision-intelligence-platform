"""Decision API: serve the verified October plan and bounded scenario solves over HTTP.

Run: uvicorn decision_platform.api:app --host 127.0.0.1 --port 8600

Reads the same hash-verified serving snapshot as the app; never touches
simulator truth. Authentication is an API key in `X-API-Key` checked against
`CORRIDOR_API_KEYS` (comma-separated). Without configured keys the service
only runs in local mode; production refuses to start unauthenticated.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import time
from contextlib import asynccontextmanager
from pathlib import Path

import pandas as pd
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field

from . import __version__
from .config import ROOT
from .experiments import sample_size
from .optimization import solve
from .planning import with_reserve

DEFAULT_SERVING = Path(os.environ.get("CORRIDOR_SERVING", ROOT / "outputs" / "serving"))


class Snapshot:
    """Verified, read-only serving data loaded once per process."""

    def __init__(self, folder: Path):
        manifest = json.loads((folder / "manifest.json").read_text())
        for name, digest in manifest["files"].items():
            if hashlib.sha256((folder / name).read_bytes()).hexdigest() != digest:
                raise ValueError(f"Serving snapshot integrity check failed for {name}")
        self.folder = folder
        self.manifest = manifest
        self.release_id = manifest["release_id"]
        self.customers = pd.read_parquet(folder / "customers.parquet").set_index("customer_id")
        self.candidates = pd.read_parquet(folder / "candidates.parquet")
        self.decisions = pd.read_parquet(folder / "decisions.parquet")
        self.capacity = pd.read_parquet(folder / "capacity.parquet")
        self.summary = json.loads((folder / "summary.json").read_text())
        self.optimization = json.loads((folder / "optimization.json").read_text())


class ScenarioRequest(BaseModel):
    budget: float = Field(10000.0, ge=0, le=500000)
    contacts: int = Field(5000, ge=0, le=50000)
    min_roi: float = Field(0.15, ge=0, le=5)
    points: int = Field(2_500_000, ge=0, le=50_000_000)
    reserve: float = Field(0.20, ge=0, le=0.5)
    risk_aversion: float = Field(0.0, ge=0, le=3)
    relief_value: float = Field(0.5, ge=0, le=10)
    solver: str = Field("auto", pattern="^(auto|highs)$")
    include_allocation: bool = False


class SampleSizeRequest(BaseModel):
    baseline: float = Field(0.35, gt=0, lt=1)
    mde: float = Field(0.05, gt=0, lt=1)
    alpha: float = Field(0.05, gt=0, lt=1)
    power: float = Field(0.8, gt=0, lt=1)
    comparisons: int = Field(1, ge=1, le=50)


def _keys():
    return {key.strip() for key in os.environ.get("CORRIDOR_API_KEYS", "").split(",") if key.strip()}


def require_key(x_api_key: str | None = Header(default=None)):
    keys = _keys()
    production = os.environ.get("CORRIDOR_ENV", "local") == "production"
    if not keys:
        if production:
            raise HTTPException(503, "API keys are not configured")
        return "local"
    if not x_api_key or not any(secrets.compare_digest(x_api_key, key) for key in keys):
        raise HTTPException(401, "Missing or invalid API key")
    return hashlib.sha256(x_api_key.encode()).hexdigest()[:12]


def create_app(serving: Path | None = None) -> FastAPI:
    folder = Path(serving or DEFAULT_SERVING)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        try:
            app.state.snapshot = Snapshot(folder)
            app.state.error = None
        except (OSError, ValueError, KeyError) as exc:
            app.state.snapshot, app.state.error = None, str(exc)
        yield

    app = FastAPI(
        title="Corridor decision API",
        version=__version__,
        description="Next-best-offer lookups, the verified October plan and bounded scenario solves. Synthetic data.",
        lifespan=lifespan,
    )

    def snapshot(request: Request) -> Snapshot:
        value = request.app.state.snapshot
        if value is None:
            raise HTTPException(503, f"Serving snapshot unavailable: {request.app.state.error}")
        return value

    @app.get("/health", tags=["operations"])
    def health():
        return {"status": "ok"}

    @app.get("/ready", tags=["operations"])
    def ready(request: Request):
        data = snapshot(request)
        return {
            "status": "ready",
            "release_id": data.release_id,
            "decision_date": data.manifest["decision_date"],
        }

    @app.get("/v1/plan/summary", tags=["plan"])
    def plan_summary(data: Snapshot = Depends(snapshot), _: str = Depends(require_key)):
        combined = data.optimization["combined"]
        return {
            "release_id": data.release_id,
            "decision_date": data.manifest["decision_date"],
            "plan": combined,
            "solver": data.optimization["joint"]["solver"],
            "proven_optimal": bool(data.optimization["certification"].get("proven_optimal")),
            "binding_guardrails": data.optimization["lp_relaxation"]["shadow_prices"],
        }

    @app.get("/v1/plan", tags=["plan"])
    def plan(
        data: Snapshot = Depends(snapshot),
        _: str = Depends(require_key),
        offer_id: str | None = None,
        zone_id: int | None = Query(None, ge=0, le=5),
        limit: int = Query(100, ge=1, le=1000),
        offset: int = Query(0, ge=0),
    ):
        rows = data.decisions
        if offer_id:
            rows = rows[rows.offer_id.eq(offer_id)]
        if zone_id is not None:
            rows = rows[rows.zone_id.eq(zone_id)]
        page = rows.sort_values("objective_value", ascending=False).iloc[offset : offset + limit]
        columns = [
            "customer_id",
            "offer_id",
            "zone_id",
            "cost",
            "objective_value",
            "incremental_trips",
            "value_uplift_sd",
        ]
        return {
            "total": len(rows),
            "offset": offset,
            "items": json.loads(page[columns].to_json(orient="records")),
        }

    @app.get("/v1/customers/{customer_id}", tags=["customers"])
    def customer(customer_id: str, data: Snapshot = Depends(snapshot), _: str = Depends(require_key)):
        if customer_id not in data.customers.index:
            raise HTTPException(404, "Unknown customer")
        row = data.customers.loc[customer_id]
        offers = data.candidates[data.candidates.customer_id.eq(customer_id)].sort_values(
            "objective_value", ascending=False
        )
        fields = [
            "rfm_segment",
            "tier",
            "eligible",
            "trips_90d",
            "propensity_probability",
            "churn_probability",
            "clv_12m",
            "plan_offer_id",
            "plan_value",
        ]
        profile = json.loads(row[fields].to_json())
        return {
            "customer_id": customer_id,
            "profile": profile,
            "offers": json.loads(
                offers[
                    [
                        "offer_id",
                        "objective_value",
                        "value_uplift",
                        "later_value_uplift",
                        "cost",
                        "value_uplift_sd",
                    ]
                ].to_json(orient="records")
            ),
        }

    @app.post("/v1/scenarios/solve", tags=["scenarios"])
    def scenario(
        body: ScenarioRequest, data: Snapshot = Depends(snapshot), owner: str = Depends(require_key)
    ):
        candidates = data.candidates.copy()
        candidates["net_contribution"] = (
            candidates.value_uplift - body.risk_aversion * candidates.value_uplift_sd
        )
        candidates["relief_value"] = body.relief_value * candidates.trips_peak
        candidates["objective_value"] = (
            candidates.net_contribution + candidates.later_value_uplift + candidates.relief_value
        )
        keep = (candidates.objective_value > 0) | (candidates.trips_peak < 0)
        candidates = candidates[keep].reset_index(drop=True)
        started = time.perf_counter()
        try:
            allocation = solve(
                candidates,
                with_reserve(data.capacity, body.reserve),
                body.budget,
                body.contacts,
                body.min_roi,
                body.solver,
                body.points,
            )
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(503, str(exc)) from exc
        diagnostics = {k: v for k, v in allocation.diagnostics.items() if k != "certificate"}
        result = {
            "release_id": data.release_id,
            "solver": allocation.solver,
            "status": allocation.status,
            "objective": allocation.objective,
            "diagnostics": diagnostics,
            "offer_mix": allocation.selected.offer_id.value_counts().to_dict(),
            "seconds": round(time.perf_counter() - started, 2),
        }
        if body.include_allocation:
            result["allocation"] = json.loads(
                allocation.selected[["customer_id", "offer_id", "cost", "objective_value"]].to_json(
                    orient="records"
                )
            )
        return result

    @app.post("/v1/experiments/sample-size", tags=["experiments"])
    def experiment_size(body: SampleSizeRequest, _: str = Depends(require_key)):
        try:
            n = sample_size(body.baseline, body.mde, body.alpha, body.power, body.comparisons)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        return {"customers_per_arm": n, **body.model_dump()}

    return app


app = create_app()
