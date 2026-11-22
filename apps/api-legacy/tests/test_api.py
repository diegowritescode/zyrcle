"""Smoke tests for the hackathon API. They pin the fixes made during the monorepo import."""

import pytest
from fastapi.testclient import TestClient

from services import iot_service


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(iot_service, "DATA_FILE", str(tmp_path / "containers.json"))
    from main import app

    return TestClient(app)


def test_status(client):
    assert client.get("/api/status").status_code == 200


def test_cors_allows_configured_origin_only(client):
    preflight = {"Access-Control-Request-Method": "GET"}
    ok = client.options("/api/status", headers={"Origin": "http://localhost:8080", **preflight})
    assert ok.status_code == 200
    bad = client.options("/api/status", headers={"Origin": "https://evil.example", **preflight})
    assert bad.status_code == 400


def test_validate_code_returns_container_id(client):
    r = client.post("/api/contenedor/validar-codigo", json={"codigo": "654321"})
    assert r.status_code == 200
    assert r.json() == {"message": "Acceso permitido", "container_id": 2}


@pytest.mark.parametrize(("codigo", "status"), [("000000", 400), ("12ab56", 422)])
def test_validate_code_rejects_unknown_or_malformed(client, codigo, status):
    r = client.post("/api/contenedor/validar-codigo", json={"codigo": codigo})
    assert r.status_code == status


def test_finish_returns_weight_in_grams(client):
    r = client.post(
        "/api/contenedor/finalizar", json={"codigo": "123456", "tiempoTranscurrido": 42}
    )
    assert r.status_code == 200
    assert r.json()["weight_grams"] == 5000
    assert r.json()["container_id"] == 1


def test_finish_rejects_negative_time(client):
    r = client.post(
        "/api/contenedor/finalizar", json={"codigo": "123456", "tiempoTranscurrido": -1}
    )
    assert r.status_code == 422


CONTAINER = {
    "id": "c1",
    "location": {"lat": 6.2, "lon": -75.5},
    "weight": 10,
    "volume": 20,
    "materials": ["plastico"],
    "name": "PET",
}


def test_iot_ingest_disabled_without_token(client, monkeypatch):
    monkeypatch.delenv("IOT_INGEST_TOKEN", raising=False)
    assert client.post("/api/iot/contenedores", json=[CONTAINER]).status_code == 503


def test_iot_ingest_requires_matching_token(client, monkeypatch):
    monkeypatch.setenv("IOT_INGEST_TOKEN", "s3cret")
    url = "/api/iot/contenedores"
    assert client.post(url, json=[CONTAINER], headers={"X-Device-Token": "nope"}).status_code == 401
    ok = client.post(url, json=[CONTAINER], headers={"X-Device-Token": "s3cret"})
    assert ok.status_code == 200


def test_iot_ingest_rejects_negative_weight(client, monkeypatch):
    monkeypatch.setenv("IOT_INGEST_TOKEN", "s3cret")
    bad = {**CONTAINER, "weight": -99999}
    r = client.post("/api/iot/contenedores", json=[bad], headers={"X-Device-Token": "s3cret"})
    assert r.status_code == 422


def test_evidence_upload_disabled_without_credential(client, monkeypatch):
    monkeypatch.delenv("PINATA_JWT", raising=False)
    files = {"file": ("a.png", b"\x89PNG", "image/png")}
    assert client.post("/api/evidence", files=files).status_code == 503


def test_route_optimization_reports_missing_key(client, monkeypatch):
    import services.gemini as gemini

    monkeypatch.setattr(gemini, "GEMINI_API_KEY", "")
    r = client.post("/api/rutas/optimizar", json={"latitude": 6.2, "longitude": -75.5})
    assert r.status_code == 503
