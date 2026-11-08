import ast
import json

import pytest

from scripts import accept_restart


def probe():
    return {
        "test_database_matches": True, "expected_revision": True,
        "deterministic_embedding": True, "student_login_identity": True,
        "admin_login_identity": True, "student_profile_count": 0,
    }


def test_embedded_read_only_probe_is_valid_python():
    ast.parse(accept_restart.TARGET_PROBE)


@pytest.mark.parametrize("field", [
    "test_database_matches", "expected_revision", "deterministic_embedding",
    "student_login_identity", "admin_login_identity",
])
def test_failed_preflight_never_restarts(monkeypatch, field):
    calls = []
    target = probe()
    target[field] = False

    def docker(*args, **kwargs):
        calls.append(args)
        return json.dumps(target)

    monkeypatch.setattr(accept_restart, "docker", docker)
    assert accept_restart.main([
        "--container", "campusmind-api", "--test-database", "campusmind_p0_test", "--restart",
    ]) == 1
    assert len(calls) == 1
    assert calls[0][0] == "exec"


@pytest.mark.parametrize("restart", [False, True])
def test_restart_is_explicit_and_recovery_is_verified(monkeypatch, restart):
    calls = []

    def docker(*args, source=None, **kwargs):
        calls.append(args)
        if args[0] == "inspect":
            return "host|unless-stopped"
        if args[0] == "restart":
            return "campusmind-api"
        if source == accept_restart.TARGET_PROBE:
            return json.dumps(probe())
        return json.dumps({"passed": True, "mode": "deployment"})

    monkeypatch.setattr(accept_restart, "docker", docker)
    arguments = ["--container", "campusmind-api", "--test-database", "campusmind_p0_test"]
    assert accept_restart.main(arguments + (["--restart"] if restart else [])) == 0
    assert sum(call[0] == "restart" for call in calls) == int(restart)
    assert sum(call[0] == "exec" for call in calls) == (4 if restart else 2)


def test_wrong_container_policy_never_restarts(monkeypatch):
    calls = []

    def docker(*args, **kwargs):
        calls.append(args)
        return "bridge|no" if args[0] == "inspect" else json.dumps(probe())

    monkeypatch.setattr(accept_restart, "docker", docker)
    assert accept_restart.main([
        "--container", "campusmind-api", "--test-database", "campusmind_p0_test", "--restart",
    ]) == 1
    assert not any(call[0] == "restart" for call in calls)
