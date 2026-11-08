from fastapi.testclient import TestClient

from campusmind.main import app

client = TestClient(app)


def test_root():
    response = client.get("/")
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "CampusMind"
    assert body["status"] == "running"
    assert body["docs"] == "/docs"


def test_liveness():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_openapi_exposes_system_endpoints():
    response = client.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/api/v1/system/health" in paths
    assert "/api/v1/system/readiness" in paths
    assert "/api/v1/system/database" in paths


def test_frontend_ui_is_served():
    response = client.get("/ui/")
    assert response.status_code == 200
    assert "CampusMind" in response.text
    assert "vue.global.prod.js" in response.text
    assert "src/main.js" in response.text
