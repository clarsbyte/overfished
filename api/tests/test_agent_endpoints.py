"""Wiring tests for /agent/{gfw,vessel,law,complete}.

Backend agent functions are monkey-patched, so these tests do NOT hit
Anthropic, GFW, or AISStream. They verify: route exists, request schema
validates, response has the expected shape, the right backend function
was called with the right args.

Run from repo root with the api venv active:
    pytest api/tests -v
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_REPO_ROOT = Path(__file__).resolve().parents[2]
_BACKEND_DIR = _REPO_ROOT / "backend"
_API_SRC = _REPO_ROOT / "api" / "src"
for p in (_API_SRC, _BACKEND_DIR):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

# Mount only the agent router so the suite doesn't require twilio /
# the full main.py dep tree to be installed.
from fastapi import FastAPI  # noqa: E402

from overfished_api.routers.agent import router as agent_router  # noqa: E402


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(agent_router)
    return TestClient(app)


@pytest.fixture
def stub_backend(monkeypatch: pytest.MonkeyPatch) -> dict[str, list]:
    """Replace each backend agent entrypoint with a recorder stub."""
    calls: dict[str, list] = {"gfw": [], "vessel": [], "law_point": [], "law_region": [], "pipeline": []}

    import gfw_agent
    import pipeline_agent
    import regional_agent
    import vessel_agent

    monkeypatch.setattr(
        gfw_agent,
        "classify_vessel",
        lambda q, d=365: (calls["gfw"].append((q, d)), f"VERDICT: LOW (stub {q}/{d})")[1],
    )
    monkeypatch.setattr(
        vessel_agent,
        "run_agent",
        lambda x, y, r=100.0: (calls["vessel"].append((x, y, r)), f"vessel stub {x},{y}/{r}")[1],
    )
    monkeypatch.setattr(
        regional_agent,
        "evaluate_point",
        lambda lat, lon, port=None, flag=None, gear=None, species=None: (
            calls["law_point"].append((lat, lon, port, flag, gear, species)),
            f"VERDICT: ALLOWED (stub {lat},{lon})",
        )[1],
    )
    monkeypatch.setattr(
        regional_agent,
        "evaluate_region",
        lambda rid: (calls["law_region"].append(rid), f"region {rid} stub")[1],
    )
    monkeypatch.setattr(
        pipeline_agent,
        "evaluate_incident",
        lambda lat, lon, r=50.0, port=None, mmsi=None: (
            calls["pipeline"].append((lat, lon, r, port, mmsi)),
            f"EVIDENCE stub {lat},{lon}",
        )[1],
    )
    return calls


def test_gfw_happy_path(client: TestClient, stub_backend: dict[str, list]) -> None:
    r = client.post("/agent/gfw", json={"query": "273435360", "days_back": 30})
    assert r.status_code == 200
    body = r.json()
    assert body["agent"] == "gfw"
    assert body["query"] == "273435360"
    assert body["days_back"] == 30
    assert "VERDICT" in body["output"]
    assert stub_backend["gfw"] == [("273435360", 30)]


def test_gfw_default_days_back(client: TestClient, stub_backend: dict[str, list]) -> None:
    r = client.post("/agent/gfw", json={"query": "TEST VESSEL"})
    assert r.status_code == 200
    assert stub_backend["gfw"][-1] == ("TEST VESSEL", 365)


def test_gfw_validation_rejects_empty_query(client: TestClient) -> None:
    r = client.post("/agent/gfw", json={"query": ""})
    assert r.status_code == 422


def test_vessel_happy_path(client: TestClient, stub_backend: dict[str, list]) -> None:
    r = client.post(
        "/agent/vessel",
        json={"latitude": -0.4, "longitude": -90.3, "radius_miles": 25},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["agent"] == "vessel"
    assert body["latitude"] == -0.4
    assert body["longitude"] == -90.3
    # vessel_agent.run_agent signature is (longitude, latitude, radius)
    assert stub_backend["vessel"] == [(-90.3, -0.4, 25.0)]


def test_vessel_validation_rejects_bad_latitude(client: TestClient) -> None:
    r = client.post("/agent/vessel", json={"latitude": 999, "longitude": 0})
    assert r.status_code == 422


def test_law_point(client: TestClient, stub_backend: dict[str, list]) -> None:
    r = client.post(
        "/agent/law",
        json={
            "latitude": -0.4,
            "longitude": -90.3,
            "port_country_code": "ECU",
            "vessel_flag": "CHN",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["agent"] == "law"
    assert "VERDICT" in body["output"]
    assert stub_backend["law_point"] == [(-0.4, -90.3, "ECU", "CHN", None, None)]
    assert stub_backend["law_region"] == []


def test_law_region(client: TestClient, stub_backend: dict[str, list]) -> None:
    r = client.post("/agent/law", json={"region_id": "galapagos-marine-reserve"})
    assert r.status_code == 200
    body = r.json()
    assert body["region_id"] == "galapagos-marine-reserve"
    assert "galapagos" in body["output"]
    assert stub_backend["law_region"] == ["galapagos-marine-reserve"]
    assert stub_backend["law_point"] == []


def test_law_requires_coords_or_region(client: TestClient) -> None:
    r = client.post("/agent/law", json={})
    assert r.status_code == 422


def test_complete_happy_path(client: TestClient, stub_backend: dict[str, list]) -> None:
    r = client.post(
        "/agent/complete",
        json={
            "latitude": -0.4,
            "longitude": -90.3,
            "radius_miles": 50,
            "port_country_code": "ECU",
            "mmsi": "412440493",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["agent"] == "complete"
    assert "EVIDENCE" in body["output"]
    assert stub_backend["pipeline"] == [(-0.4, -90.3, 50.0, "ECU", "412440493")]


def test_complete_minimal_body(client: TestClient, stub_backend: dict[str, list]) -> None:
    r = client.post("/agent/complete", json={"latitude": 0, "longitude": 0})
    assert r.status_code == 200
    assert stub_backend["pipeline"][-1] == (0.0, 0.0, 50.0, None, None)
