"""Controlled Linux Docker restart acceptance for a named isolated test database."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

# Executed in the existing API image. Only safe booleans/counts leave the container.
TARGET_PROBE = """
import json, sys
from sqlalchemy import text
from campusmind.config import get_settings
from campusmind.platform.db import get_engine
try:
    with get_engine().connect() as conn:
        conn.exec_driver_sql("SET TRANSACTION READ ONLY")
        conn.exec_driver_sql("SET LOCAL statement_timeout = '5s'")
        actual = conn.execute(text("SELECT current_database()")).scalar_one()
        revisions = list(conn.execute(text("SELECT version_num FROM public.alembic_version")).scalars())
        accounts = conn.execute(text(
            "SELECT u.username, u.status, u.is_superuser, "
            "EXISTS (SELECT 1 FROM public.user_roles ur JOIN public.roles r ON r.id=ur.role_id "
            "WHERE ur.user_id=u.id AND r.code=:role) AS expected_role "
            "FROM public.users u WHERE u.username=:username"
        ), {"username": "student001", "role": "student"}).mappings().one_or_none()
        admin = conn.execute(text(
            "SELECT u.status, u.is_superuser, EXISTS (SELECT 1 FROM public.user_roles ur "
            "JOIN public.roles r ON r.id=ur.role_id WHERE ur.user_id=u.id AND r.code='admin') "
            "AS expected_role FROM public.users u WHERE u.username='admin'"
        )).mappings().one_or_none()
        profiles = conn.execute(text(
            "SELECT count(*) FROM public.students s JOIN public.users u ON s.user_id=u.id "
            "WHERE u.username='student001'"
        )).scalar_one()
        result = {
            "test_database_matches": actual == sys.argv[1] and actual.endswith('_test'),
            "expected_revision": revisions == ['20260926_0011'],
            "deterministic_embedding": get_settings().rag_embedding_provider == 'deterministic',
            "student_login_identity": bool(accounts and accounts['status'] == 'active'
                and not accounts['is_superuser'] and accounts['expected_role']),
            "admin_login_identity": bool(admin and admin['status'] == 'active'
                and admin['is_superuser'] and admin['expected_role']),
            "student_profile_count": profiles,
        }
    print(json.dumps(result))
except Exception:
    print(json.dumps({"probe_failed": True}))
    sys.exit(1)
"""


def docker(*arguments, source=None, timeout=30):
    result = subprocess.run(
        ["docker", *arguments], input=source, text=True, capture_output=True, timeout=timeout,
        check=False,
    )
    if result.returncode:
        raise RuntimeError("Docker operation failed; no private diagnostic output was printed")
    return result.stdout


def verify_probe(probe):
    required = ("test_database_matches", "expected_revision", "deterministic_embedding",
                "student_login_identity", "admin_login_identity")
    if not isinstance(probe, dict) or not all(probe.get(name) is True for name in required):
        raise RuntimeError("Test database, migration, embedding or account guard failed")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--container", required=True)
    parser.add_argument("--test-database", required=True)
    parser.add_argument("--restart", action="store_true", help="explicitly restart the checked API")
    args = parser.parse_args(argv)
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]*", args.container):
        parser.error("invalid container name")
    if not re.fullmatch(r"[a-zA-Z0-9_]+_test", args.test_database):
        parser.error("database must be an explicitly named isolated *_test database")
    checker_path = Path(__file__).with_name("check_runtime.py")
    phase = "target preflight"
    try:
        checker = checker_path.read_text(encoding="utf-8")
        probe = json.loads(docker("exec", "-i", args.container, "python", "-", args.test_database,
                                  source=TARGET_PROBE))
        verify_probe(probe)
        print("PASS: named test database, migration, deterministic embeddings and account roles")
        print(f"Student academic profile count: {probe['student_profile_count']}", flush=True)
        phase = "container policy"
        policy = docker("inspect", "--format",
                        "{{.HostConfig.NetworkMode}}|{{.HostConfig.RestartPolicy.Name}}",
                        args.container).strip()
        if policy != "host|unless-stopped":
            raise RuntimeError("Expected Linux host network and unless-stopped restart policy")
        print("PASS: host network and unless-stopped restart policy", flush=True)

        def runtime():
            report = json.loads(docker("exec", "-i", args.container, "python", "-", "--json",
                                      source=checker, timeout=90))
            return report.get("passed") is True and report.get("mode") == "deployment"

        phase = "runtime before restart"
        if not runtime():
            raise RuntimeError("Pre-restart runtime checks failed")
        print("PASS: runtime before restart", flush=True)
        if not args.restart:
            print("Restart not requested; recovery has not been tested")
            return 0
        phase = "restart and recovery"
        docker("restart", "--time", "20", args.container, timeout=60)
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            try:
                if runtime():
                    after = json.loads(docker("exec", "-i", args.container, "python", "-",
                                              args.test_database, source=TARGET_PROBE))
                    verify_probe(after)
                    print("CM_RESTART_ACCEPTANCE_PASSED")
                    print("Recheck both accounts in the browser; RLS/HITL concurrency is separate.")
                    return 0
            except (RuntimeError, ValueError, subprocess.TimeoutExpired):
                pass
            time.sleep(2)
        raise RuntimeError("API recovery did not pass within the acceptance window")
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.TimeoutExpired) as exc:
        print(f"FAIL: {phase} ({type(exc).__name__})", file=sys.stderr)
        print("No container, database, volume or test data was deleted.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
