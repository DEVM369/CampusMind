"""Read-only HTTP acceptance checks; no login, model calls, or business writes."""

from __future__ import annotations

import argparse
import json
from html.parser import HTMLParser
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

REQUIRED_ASSETS = {
    "./vendor/vue.global.prod.js": "/ui/vendor/vue.global.prod.js",
    "./src/main.js": "/ui/src/main.js",
    "./styles.css": "/ui/styles.css",
}


def validate_origin(value: str) -> str:
    try:
        parts = urlsplit(value)
        valid = (
            parts.scheme in {"http", "https"} and parts.hostname and parts.port != 0
            and parts.username is None and parts.password is None
            and parts.path in {"", "/"} and not parts.query and not parts.fragment
            and not any(char.isspace() for char in value)
        )
    except ValueError:
        valid = False
    if not valid:
        raise ValueError("base URL must be an HTTP(S) origin without credentials")
    return value.rstrip("/")


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class FrontendParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.has_app = False
        self.assets: set[str] = set()

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self.has_app |= tag == "div" and attrs.get("id") == "app"
        if tag == "script" and attrs.get("src"):
            self.assets.add(attrs["src"])
        if tag == "link" and attrs.get("rel") == "stylesheet" and attrs.get("href"):
            self.assets.add(attrs["href"])


def http_fetch(origin: str, *, timeout: float = 15):
    origin = validate_origin(origin)
    opener = build_opener(ProxyHandler({}), NoRedirect())

    def fetch(path: str):
        request = Request(origin + path, headers={"User-Agent": "CampusMind-runtime-check"})
        try:
            response = opener.open(request, timeout=timeout)
        except HTTPError as exc:
            response = exc
        with response:
            body = response.read(4 * 1024 * 1024 + 1)
            if len(body) > 4 * 1024 * 1024:
                raise ValueError("response exceeds check size limit")
            return response.status, response.headers.get("Content-Type", ""), body

    return fetch


def healthy(payload):
    return (
        isinstance(payload, dict) and payload.get("status") == "healthy"
        and isinstance(payload.get("components"), dict)
        and all(isinstance(payload["components"].get(name), dict)
                and payload["components"][name].get("status") == "healthy"
                for name in ("postgres", "neo4j", "redis", "rustfs"))
    )


def run_checks(fetch, *, liveness_only: bool = False) -> list[dict]:
    results = []

    def check(path, predicate, *, as_json=True):
        status = None
        try:
            status, content_type, body = fetch(path)
            payload = json.loads(body) if as_json else (content_type, body)
            passed = status == 200 and bool(predicate(payload))
        except (OSError, ValueError, TypeError, KeyError, RuntimeError):
            # Response bodies and exception messages can contain infrastructure credentials.
            passed = False
        results.append({"path": path, "http_status": status, "passed": passed})

    check("/health", lambda data: isinstance(data, dict) and data.get("status") == "ok")
    if not liveness_only:
        check("/api/v1/system/health", healthy)
        check("/api/v1/system/readiness", healthy)
        check("/api/v1/system/database", lambda data: (
            isinstance(data, dict) and data.get("status") == "ready"
            and data.get("revision") == "20260926_0011"
            and data.get("missing_tables") == []
        ))

    def valid_frontend(payload):
        content_type, body = payload
        parser = FrontendParser()
        parser.feed(body.decode("utf-8"))
        return ("text/html" in content_type.lower() and parser.has_app
                and REQUIRED_ASSETS.keys() <= parser.assets)

    check("/ui/", valid_frontend, as_json=False)
    for path in REQUIRED_ASSETS.values():
        check(path, lambda payload: (
            bool(payload[1].strip()) and "text/html" not in payload[0].lower()
            and not payload[1].lstrip().lower().startswith((b"<!doctype html", b"<html"))
        ), as_json=False)
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--liveness-only", action="store_true",
                        help="limited image smoke: skip dependencies and schema")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        fetch = http_fetch(args.base_url)
    except ValueError:
        parser.error("base URL must be an HTTP(S) origin without credentials")
    checks = run_checks(fetch, liveness_only=args.liveness_only)
    passed = all(item["passed"] for item in checks)
    mode = "liveness_only" if args.liveness_only else "deployment"
    if args.json:
        print(json.dumps({"mode": mode, "passed": passed, "checks": checks}, indent=2))
    else:
        print(f"Runtime check mode: {mode}")
        for item in checks:
            print(f"{'PASS' if item['passed'] else 'FAIL'}: {item['path']} "
                  f"(HTTP {item['http_status']})")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
