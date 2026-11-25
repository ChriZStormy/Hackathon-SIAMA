"""Pruebas del esqueleto FastAPI (/health y /status/data)."""

from fastapi.testclient import TestClient

from src.api.main import app

client = TestClient(app)


def test_health_endpoint() -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["service"] == "SIAMA-Impute"


def test_data_status_endpoint() -> None:
    resp = client.get("/status/data")
    assert resp.status_code == 200
    body = resp.json()
    assert body["project"] == "SIAMA-Impute"
    assert "files" in body
    assert "estaciones" in body["files"]
