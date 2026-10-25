from fastapi.testclient import TestClient
from app.api import app


def test_operational_health_and_database_readiness(sessions, monkeypatch):
    monkeypatch.setattr("app.api.SessionLocal", sessions)
    client = TestClient(app)
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/ready").status_code == 200
    assert client.get("/users").status_code == 404
    assert client.get("/docs").status_code == 404


def test_readiness_database_failure_is_503_and_redacts_details(monkeypatch):
    def broken():
        raise RuntimeError("secret-database-password")
    monkeypatch.setattr("app.api.SessionLocal", broken)
    response = TestClient(app).get("/ready")
    assert response.status_code == 503
    assert "secret" not in response.text
