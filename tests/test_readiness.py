from fastapi.testclient import TestClient

from campusmind.api.schemas import DatabaseSchemaStatus, SystemHealthResponse
from campusmind.main import app
from campusmind.platform.health import DatabaseSchemaService, SystemHealthService


def test_readiness_requires_current_database_schema(monkeypatch):
    async def healthy_infrastructure(self):
        return SystemHealthResponse(status="healthy", components={})

    monkeypatch.setattr(SystemHealthService, "check_all", healthy_infrastructure)
    monkeypatch.setattr(
        DatabaseSchemaService,
        "status",
        lambda self: DatabaseSchemaStatus(
            status="incomplete",
            revision="20260924_0010",
            table_count=1,
            expected_table_count=2,
            missing_tables=["auth_sessions"],
        ),
    )
    with TestClient(app) as client:
        response = client.get("/api/v1/system/readiness")
    assert response.status_code == 503
    assert response.json()["detail"]["missing_tables"] == ["auth_sessions"]


def test_readiness_accepts_current_database_schema(monkeypatch):
    async def healthy_infrastructure(self):
        return SystemHealthResponse(status="healthy", components={})

    monkeypatch.setattr(SystemHealthService, "check_all", healthy_infrastructure)
    monkeypatch.setattr(
        DatabaseSchemaService,
        "status",
        lambda self: DatabaseSchemaStatus(
            status="ready", revision="20260926_0011", table_count=2, expected_table_count=2
        ),
    )
    with TestClient(app) as client:
        response = client.get("/api/v1/system/readiness")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_readiness_fails_closed_when_schema_check_errors(monkeypatch):
    async def healthy_infrastructure(self):
        return SystemHealthResponse(status="healthy", components={})

    def failing_schema(self):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(SystemHealthService, "check_all", healthy_infrastructure)
    monkeypatch.setattr(DatabaseSchemaService, "status", failing_schema)
    with TestClient(app) as client:
        response = client.get("/api/v1/system/readiness")
    assert response.status_code == 503
    assert response.json()["detail"] == "Database schema check unavailable"
