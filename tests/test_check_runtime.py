import json

import pytest

from scripts.check_runtime import REQUIRED_ASSETS, run_checks, validate_origin


def responses():
    health = {"status": "healthy", "components": {
        name: {"status": "healthy"} for name in ("postgres", "neo4j", "redis", "rustfs")
    }}
    data = {
        "/health": {"status": "ok"},
        "/api/v1/system/health": health,
        "/api/v1/system/readiness": health,
        "/api/v1/system/database": {
            "status": "ready", "revision": "20260926_0011", "missing_tables": [],
        },
    }
    result = {path: (200, "application/json", json.dumps(body).encode())
              for path, body in data.items()}
    html = ('<div id="app"></div><link rel="stylesheet" href="./styles.css">'
            '<script src="./vendor/vue.global.prod.js"></script>'
            '<script type="module" src="./src/main.js"></script>')
    result["/ui/"] = (200, "text/html", html.encode())
    result.update({path: (200, "application/javascript", b"/* asset */")
                   for path in REQUIRED_ASSETS.values()})
    return result


def test_healthy_runtime_and_limited_mode():
    data = responses()
    assert all(item["passed"] for item in run_checks(data.__getitem__))
    limited = run_checks(data.__getitem__, liveness_only=True)
    assert all(item["passed"] for item in limited)
    assert not any("/system/" in item["path"] for item in limited)


@pytest.mark.parametrize("path,body", [
    ("/api/v1/system/readiness", {"status": "degraded", "components": {}}),
    ("/api/v1/system/health", {"status": "healthy", "components": {}}),
    ("/api/v1/system/health", {"status": "healthy", "components": {"postgres": None}}),
    ("/api/v1/system/database", {
        "status": "ready", "revision": "20260924_0010", "missing_tables": [],
    }),
    ("/api/v1/system/database", {
        "status": "ready", "revision": "20260926_0011", "missing_tables": ["auth_sessions"],
    }),
])
def test_http_200_cannot_hide_unhealthy_runtime(path, body):
    data = responses()
    data[path] = (200, "application/json", json.dumps(body).encode())
    assert not next(item for item in run_checks(data.__getitem__) if item["path"] == path)["passed"]


@pytest.mark.parametrize("status,content_type,body", [
    (404, "application/javascript", b"missing"),
    (200, "text/html", b"<div id=app></div>"),
    (200, "application/javascript", b"<!doctype html><html>fallback"),
    (200, "application/javascript", b""),
])
def test_missing_or_html_fallback_asset_fails(status, content_type, body):
    data = responses()
    data["/ui/src/main.js"] = (status, content_type, body)
    assert not all(item["passed"] for item in run_checks(data.__getitem__))


def test_missing_ui_references_fails():
    data = responses()
    data["/ui/"] = (200, "text/html", b'<div id="app"></div>')
    assert not all(item["passed"] for item in run_checks(data.__getitem__))


def test_response_and_exception_details_are_redacted():
    def fail(path):
        raise RuntimeError("credential-sentinel")

    output = run_checks(fail)
    assert not any(item["passed"] for item in output)
    assert "credential-sentinel" not in json.dumps(output)


@pytest.mark.parametrize("origin", [
    "http://operator:secret@localhost", "file:///tmp", "http://localhost/path",
    "http://localhost?secret=value", "http://localhost#token", "http://localhost:invalid",
    "http://localhost:0", "http://local host",
])
def test_origin_rejects_credentials_and_non_origins(origin):
    with pytest.raises(ValueError):
        validate_origin(origin)
