"""Decision API contract tests against a tiny, hermetic serving snapshot."""

import json

import pandas as pd
import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from decision_platform.api import create_app  # noqa: E402
from decision_platform.config import Config  # noqa: E402
from decision_platform.report import write_serving_manifest  # noqa: E402


def candidate_rows():
    rows = []
    for i, customer in enumerate(["C1", "C2", "C3"]):
        for offer, cost, value in [("pct_10", 4.0, 6.0 - i), ("loyalty_500", 5.35, 3.0 + i)]:
            rows.append(
                {
                    "candidate_id": len(rows),
                    "customer_id": customer,
                    "offer_id": offer,
                    "offer_name": offer,
                    "eligible": True,
                    "zone_id": 0,
                    "period": "Mixed",
                    "cost": cost,
                    "value_uplift": value,
                    "value_uplift_sd": 1.0,
                    "later_value_uplift": 1.0,
                    "net_contribution": value,
                    "objective_value": value + 1.0,
                    "trips_peak": 0.1,
                    "trips_offpeak": 0.5,
                    "trips_weekend": 0.2,
                    "incremental_trips": 0.8,
                    "points": 500 if offer == "loyalty_500" else 0,
                    "inventory": 10,
                }
            )
    return pd.DataFrame(rows)


@pytest.fixture
def client(tmp_path):
    serving = tmp_path / "serving"
    serving.mkdir()
    candidates = candidate_rows()
    candidates.to_parquet(serving / "candidates.parquet", index=False)
    candidates.iloc[[0, 3]].to_parquet(serving / "decisions.parquet", index=False)
    pd.DataFrame(
        {
            "customer_id": ["C1", "C2", "C3"],
            "rfm_segment": ["Loyal", "New", "Dormant"],
            "tier": ["Gold", "Silver", "Silver"],
            "eligible": [True, True, True],
            "trips_90d": [20, 3, 0],
            "propensity_probability": [0.9, 0.4, 0.1],
            "churn_probability": [0.1, 0.3, None],
            "clv_12m": [300.0, 80.0, 5.0],
            "plan_offer_id": ["pct_10", "loyalty_500", None],
            "plan_value": [7.0, 5.0, None],
        }
    ).to_parquet(serving / "customers.parquet", index=False)
    pd.DataFrame(
        {
            "zone_id": [0, 0, 0],
            "period": ["Peak", "Off-peak", "Weekend"],
            "baseline_forecast": [100.0, 100.0, 50.0],
            "capacity_trips": [200.0, 300.0, 150.0],
            "reserve_trips": [20.0, 20.0, 10.0],
            "available_trips": [80.0, 180.0, 90.0],
            "baseline_over_capacity": [False, False, False],
        }
    ).to_parquet(serving / "capacity.parquet", index=False)
    (serving / "summary.json").write_text(json.dumps({"customers": 3}))
    (serving / "optimization.json").write_text(
        json.dumps(
            {
                "combined": {"contacts": 2},
                "joint": {"solver": "Gurobi"},
                "certification": {"proven_optimal": True},
                "lp_relaxation": {"shadow_prices": []},
            }
        )
    )
    write_serving_manifest(serving, Config())
    with TestClient(create_app(serving)) as test_client:
        yield test_client, serving


def test_health_and_readiness_report_the_release(client):
    test_client, _ = client
    assert test_client.get("/health").json() == {"status": "ok"}
    ready = test_client.get("/ready").json()
    assert ready["status"] == "ready" and len(ready["release_id"]) == 64


def test_customer_lookup_ranks_offers_and_rejects_unknown_ids(client):
    test_client, _ = client
    body = test_client.get("/v1/customers/C1").json()
    values = [offer["objective_value"] for offer in body["offers"]]
    assert values == sorted(values, reverse=True)
    assert body["profile"]["plan_offer_id"] == "pct_10"
    assert test_client.get("/v1/customers/NOPE").status_code == 404


def test_scenario_solve_respects_budget_and_contacts(client):
    test_client, _ = client
    response = test_client.post(
        "/v1/scenarios/solve", json={"budget": 9.0, "contacts": 2, "points": 0, "include_allocation": True}
    )
    body = response.json()
    assert response.status_code == 200
    assert body["diagnostics"]["spend"] <= 9.0 + 1e-9
    assert len(body["allocation"]) <= 2
    assert all(row["offer_id"] != "loyalty_500" for row in body["allocation"])


def test_invalid_scenario_inputs_are_rejected(client):
    test_client, _ = client
    assert test_client.post("/v1/scenarios/solve", json={"budget": -1}).status_code == 422
    assert test_client.post("/v1/scenarios/solve", json={"solver": "imaginary"}).status_code == 422


def test_api_key_is_enforced_when_configured(client, monkeypatch):
    test_client, _ = client
    monkeypatch.setenv("CORRIDOR_API_KEYS", "alpha-key")
    assert test_client.get("/v1/plan/summary").status_code == 401
    assert test_client.get("/v1/plan/summary", headers={"X-API-Key": "wrong"}).status_code == 401
    ok = test_client.get("/v1/plan/summary", headers={"X-API-Key": "alpha-key"})
    assert ok.status_code == 200 and ok.json()["proven_optimal"]


def test_production_refuses_to_serve_without_keys(client, monkeypatch):
    test_client, _ = client
    monkeypatch.setenv("CORRIDOR_ENV", "production")
    monkeypatch.delenv("CORRIDOR_API_KEYS", raising=False)
    assert test_client.get("/v1/plan/summary").status_code == 503


def test_tampered_snapshot_is_never_served(tmp_path, client):
    _, serving = client
    frame = pd.read_parquet(serving / "decisions.parquet")
    frame.loc[0, "cost"] = 0.0
    frame.to_parquet(serving / "decisions.parquet", index=False)
    with TestClient(create_app(serving)) as fresh:
        assert fresh.get("/ready").status_code == 503
        assert fresh.get("/health").status_code == 200


def test_sample_size_endpoint_matches_library(client):
    test_client, _ = client
    body = test_client.post(
        "/v1/experiments/sample-size", json={"baseline": 0.35, "mde": 0.05, "comparisons": 2}
    ).json()
    from decision_platform.experiments import sample_size

    assert body["customers_per_arm"] == sample_size(0.35, 0.05, comparisons=2)
