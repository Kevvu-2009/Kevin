"""HTTP-level tests for the webhook: auth, allowlist, and the ordering of checks.

These run the real FastAPI app through its lifespan. In DRY_RUN mode the app
wires itself to ``PaperExchange``, so no credentials or network are involved.
"""

from __future__ import annotations

import dataclasses
import time

import pytest
from fastapi.testclient import TestClient

from app.main import create_app

from .conftest import ENTRY, SECRET, STOP, TARGET


def _body(**overrides) -> dict:
    now_ms = int(time.time() * 1000)
    payload = {
        "secret": SECRET,
        "signal_id": f"BTCUSDT.P-60-{now_ms}",
        "action": "entry",
        "side": "long",
        "symbol": "BTCUSDT.P",
        "entry": ENTRY,
        "stop": STOP,
        "target": TARGET,
        "timeframe": "60",
        "bar_time": now_ms - 3_600_000 - 2_000,
        "bar_close_time": now_ms - 2_000,
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def test_valid_signal_is_accepted(client):
    response = client.post("/webhook", json=_body())
    assert response.status_code == 200
    assert response.json()["status"] == "accepted"


def test_wrong_secret_is_unauthorized(client):
    response = client.post("/webhook", json=_body(secret="wrong-secret-value-here"))
    assert response.status_code == 401
    assert response.json()["status"] == "unauthorized"


def test_missing_secret_is_rejected_by_the_schema(client):
    body = _body()
    del body["secret"]
    response = client.post("/webhook", json=body)
    assert response.status_code == 422


def test_duplicate_delivery_returns_200_without_re_executing(client):
    body = _body()
    first = client.post("/webhook", json=body)
    second = client.post("/webhook", json=body)

    assert first.json()["status"] == "accepted"
    assert second.status_code == 200
    assert second.json()["status"] == "duplicate"


def test_malformed_json_is_rejected(client):
    response = client.post(
        "/webhook", content=b"{not json", headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 400


def test_schema_violation_is_rejected(client):
    response = client.post("/webhook", json=_body(side="sideways"))
    assert response.status_code == 422


def test_inconsistent_geometry_is_rejected_before_any_trading(client):
    response = client.post("/webhook", json=_body(stop=ENTRY + 500))
    assert response.status_code == 422


def test_unknown_field_is_rejected(client):
    response = client.post("/webhook", json=_body(qty=99.0))
    assert response.status_code == 422


def test_ip_allowlist_blocks_unlisted_callers(settings):
    locked = dataclasses.replace(
        settings, ip_allowlist_enabled=True, ip_allowlist=("203.0.113.7",)
    )
    with TestClient(create_app(locked)) as client:
        response = client.post("/webhook", json=_body())
        assert response.status_code == 403
        assert response.json()["status"] == "forbidden"


def test_ip_allowlist_admits_listed_callers(settings):
    # TestClient presents itself as "testclient".
    allowed = dataclasses.replace(
        settings, ip_allowlist_enabled=True, ip_allowlist=("testclient",)
    )
    with TestClient(create_app(allowed)) as client:
        response = client.post("/webhook", json=_body())
        assert response.status_code == 200


def test_forwarded_header_is_ignored_unless_proxy_is_trusted(settings):
    """An attacker must not be able to spoof their way past the allowlist."""
    locked = dataclasses.replace(
        settings,
        ip_allowlist_enabled=True,
        ip_allowlist=("203.0.113.7",),
        trust_proxy_headers=False,
    )
    with TestClient(create_app(locked)) as client:
        response = client.post(
            "/webhook", json=_body(), headers={"X-Forwarded-For": "203.0.113.7"}
        )
        assert response.status_code == 403


def test_forwarded_header_is_honoured_when_proxy_is_trusted(settings):
    trusted = dataclasses.replace(
        settings,
        ip_allowlist_enabled=True,
        ip_allowlist=("203.0.113.7",),
        trust_proxy_headers=True,
    )
    with TestClient(create_app(trusted)) as client:
        response = client.post(
            "/webhook", json=_body(), headers={"X-Forwarded-For": "203.0.113.7, 10.0.0.1"}
        )
        assert response.status_code == 200


def test_stale_signal_is_rejected_synchronously(client):
    """The response must not claim "accepted" for a signal that will be dropped."""
    now_ms = int(time.time() * 1000)
    stale_close = now_ms - 600_000  # bar closed 10 minutes ago
    response = client.post(
        "/webhook",
        json=_body(
            signal_id="BTCUSDT.P-60-stale",
            bar_time=stale_close - 3_600_000,
            bar_close_time=stale_close,
        ),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "rejected"
    assert body["code"] == "stale_signal"


def test_stale_signal_leaves_no_position(client):
    now_ms = int(time.time() * 1000)
    stale_close = now_ms - 600_000
    client.post(
        "/webhook",
        json=_body(
            signal_id="BTCUSDT.P-60-stale-2",
            bar_time=stale_close - 3_600_000,
            bar_close_time=stale_close,
        ),
    )
    status_body = client.get("/status").json()
    assert status_body["positions"] == []


def test_healthz_reports_reconciled_state(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["mode"] == "DRY_RUN"


def test_status_endpoint_exposes_risk_snapshot(client):
    response = client.get("/status")
    assert response.status_code == 200
    body = response.json()
    assert body["reconciled"] is True
    assert body["risk"]["max_positions_total"] == 2
    assert body["risk"]["halted"] is False
