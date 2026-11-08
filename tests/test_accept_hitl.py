from datetime import date
from threading import Event, Lock
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Uuid, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from campusmind.platform.db import AuditLog, Base
from campusmind.tools.actions import (
    ClassroomActionRepository,
    LegacyAuditMirror,
    LibraryActionRepository,
    library_books,
    library_inventory,
)
from scripts import accept_hitl as acceptance
from tests.test_security_http import login
from tests.test_security_http import security_app as security_app  # noqa: PLC0414


def successful_body(*, replay=False, reservation_id="synthetic-reservation"):
    return {"status": "executed", "idempotent": replay, "state_changed": not replay,
            "reservation": {"reservation_id": reservation_id}}


def test_legacy_audit_mirror_populates_required_detail_json(security_app):
    _, engine, actors = security_app
    with Session(engine) as session:
        mirror = LegacyAuditMirror(session)
        table = mirror._reflect("audit_logs")
        payload = mirror._payload(
            table,
            kind="audit",
            actor_user_id=actors[0],
            trace_id=None,
            tool_name="synthetic.probe",
            action="prepare_reservation",
            arguments={"synthetic": True},
            result={"synthetic": True},
            status="pending",
            requires_approval=True,
            resource_type="diagnostic",
        )
        assert payload["detail_json"]["action"] == "prepare_reservation"
        session.execute(AuditLog.__table__.insert().values(payload))
        session.rollback()


def test_same_approval_and_last_resource_positive_controls():
    results = [(200, successful_body()), (200, successful_body(replay=True))]
    assert acceptance.same_approval_result(results) == "synthetic-reservation"
    assert acceptance.single_winner_result([(409, None), (200, successful_body())]) == 1


@pytest.mark.parametrize("results", [
    [(200, successful_body()), (200, successful_body())],
    [(200, successful_body()), (200, successful_body(replay=True, reservation_id="different"))],
    [(200, {**successful_body(), "idempotent": True}),
     (200, {**successful_body(replay=True), "idempotent": False})],
    [(200, successful_body()), (409, None)],
])
def test_same_approval_checker_rejects_duplicate_effects_or_inconsistent_replays(results):
    with pytest.raises(acceptance.security.AcceptanceError):
        acceptance.same_approval_result(results)


@pytest.mark.parametrize("results", [
    [(200, successful_body()), (200, successful_body())],
    [(409, None), (409, None)],
    [(200, successful_body(replay=True)), (409, None)],
])
def test_last_resource_checker_requires_one_new_success_and_one_conflict(results):
    with pytest.raises(acceptance.security.AcceptanceError):
        acceptance.single_winner_result(results)


def test_book_setup_refuses_sqlite_and_leaves_existing_inventory(security_app):
    _, engine, _ = security_app
    with pytest.raises(acceptance.security.AcceptanceError, match="PostgreSQL"):
        acceptance.create_books(engine, "campusmind_p0_test", uuid4().hex)
    with engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(library_books)) == 0


def test_each_run_uses_new_book_ids_without_resetting_prior_inventory(security_app, monkeypatch):
    _, engine, _ = security_app
    monkeypatch.setattr(acceptance.security, "check_target", lambda *_: None)
    first = acceptance.create_books(engine, "isolated_test", uuid4().hex)
    with engine.begin() as connection:
        connection.execute(library_inventory.update().where(
            library_inventory.c.book_id == first["replay"]["id"]
        ).values(available_copies=0, reserved_copies=1))
    second = acceptance.create_books(engine, "isolated_test", uuid4().hex)
    assert {book["id"] for book in first.values()}.isdisjoint(book["id"] for book in second.values())
    with engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(library_books)) == 6
        assert connection.scalar(select(library_inventory.c.available_copies).where(
            library_inventory.c.book_id == first["replay"]["id"]
        )) == 0
    assert all(len(book["code"]) <= 40 for book in (*first.values(), *second.values()))


def test_partial_book_setup_rolls_back_atomically(security_app, monkeypatch):
    _, engine, _ = security_app
    monkeypatch.setattr(acceptance.security, "check_target", lambda *_: None)
    first_id, inventory_id = uuid4(), uuid4()
    values = iter([first_id, inventory_id, first_id])
    monkeypatch.setattr(acceptance, "uuid4", lambda: next(values))
    with pytest.raises(IntegrityError):
        acceptance.create_books(engine, "isolated_test", "a" * 32)
    with engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(library_books)) == 0
        assert connection.scalar(select(func.count()).select_from(library_inventory)) == 0


def test_classroom_date_selection_skips_all_existing_approvals(security_app):
    client, engine, actors = security_app
    run_id = "0" * 32
    login(client)
    client.post("/api/v1/tools/classroom/prepare", json={
        "actor_user_id": str(actors[0]),
        "query": "\u5e2e\u6211\u9884\u7ea62090-01-01\u4e0b\u534830\u4eba\u7684\u6559\u5ba4",
    }).raise_for_status()
    dates = acceptance.unused_classroom_dates(engine, run_id)
    assert dates == [date(2090, 1, 2), date(2090, 1, 3), date(2090, 1, 4)]


@pytest.mark.parametrize("domain", ["library", "classroom"])
@pytest.mark.parametrize("corrupt_audit", [False, True])
def test_real_http_approval_denial_rejection_execution_and_replay(security_app, monkeypatch, domain, corrupt_audit):
    owner, engine, actors = security_app
    monkeypatch.setattr(acceptance.security, "check_target", lambda *_: None)
    # SQLite verifies HTTP/business state only; PostgreSQL locks are checked live.
    monkeypatch.setattr(ClassroomActionRepository, "lock_room_slot", lambda *_: None)

    def local_inventory(self, book_id):
        return dict(self.session.execute(select(library_inventory).where(
            library_inventory.c.book_id == self._as_uuid(book_id)
        )).mappings().one())

    monkeypatch.setattr(LibraryActionRepository, "lock_inventory", local_inventory)
    reflect = LegacyAuditMirror._reflect

    def portable_uuid_reflection(self, name):
        table = reflect(self, name)
        if table is not None:
            original = Base.metadata.tables[name]
            # SQLite reflects UUIDs as CHAR and loses the UUID bind adapter.
            for column in table.c:
                if isinstance(original.c[column.name].type, Uuid):
                    column.type = Uuid(as_uuid=True)
        return table

    monkeypatch.setattr(LegacyAuditMirror, "_reflect", portable_uuid_reflection)
    books = acceptance.create_books(engine, "isolated_test", uuid4().hex)
    login(owner)
    with TestClient(owner.app) as other, TestClient(owner.app) as anonymous:
        login(other, "bob")
        action = acceptance.prepare(owner, engine, "isolated_test", uuid4().hex, actors[0],
                                    book=books["cancel"] if domain == "library" else None,
                                    target=date(2098, 1, 1) if domain == "classroom" else None)
        acceptance.action_state(engine, action, "awaiting_approval", 0)
        assert acceptance.negative_checks(engine, owner, other, anonymous, action, actors[1]) == [401, 403, 403, 404, 422, 409, 409]
        acceptance.reject_and_replay(engine, owner, action)
        if domain == "library":
            acceptance.require_library_state(engine, books["cancel"], 0)
        executed = acceptance.prepare(owner, engine, "isolated_test", uuid4().hex, actors[0],
                                      book=books["replay"] if domain == "library" else None,
                                      target=date(2098, 1, 2) if domain == "classroom" else None)
        result = acceptance.resume(owner, executed)
        result.raise_for_status()
        reservation_id = result.json()["reservation"]["reservation_id"]
        acceptance.check_replay(owner, executed, reservation_id)
        acceptance.action_state(engine, executed, "executed", 1)
        if domain == "library":
            acceptance.require_library_state(engine, books["replay"], 1)
        if corrupt_audit:
            execution_action = "execute_book_reservation" if domain == "library" else "execute_reservation"
            with engine.begin() as connection:
                connection.execute(AuditLog.__table__.insert().values(
                    actor_user_id=actors[0], action=execution_action, resource_type=domain,
                    detail_json={"arguments": {"approval_id": str(executed["approval"])}},
                ))
            with pytest.raises(acceptance.security.AcceptanceError, match="execution audit count"):
                acceptance.action_state(engine, executed, "executed", 1)


@pytest.mark.parametrize("observe_two", [True, False])
def test_race_releases_controller_lock_before_workers_finish(monkeypatch, observe_two):
    released = Event()
    worker_started = Event()
    counter_lock = Lock()
    counter = [0]
    transaction = Mock()
    transaction.rollback.side_effect = released.set
    blocker = Mock()
    blocker.begin.return_value = transaction
    blocker.exec_driver_sql.return_value.scalar_one.return_value = 42
    engine = Mock()
    engine.connect.return_value.__enter__ = Mock(return_value=blocker)
    engine.connect.return_value.__exit__ = Mock(return_value=False)
    monkeypatch.setattr(acceptance.security, "check_target", lambda *_: None)

    def operation(request, start):
        start.wait(timeout=2)
        with counter_lock:
            counter[0] += 1
            if counter[0] == 2:
                worker_started.set()
        assert released.wait(timeout=3), "Controller must release before joining workers"
        return (200, successful_body())

    def observed(*args):
        assert worker_started.wait(timeout=2)
        return 2 if observe_two else 1

    clock_values = iter([0, 0, 20])
    monkeypatch.setattr(acceptance.time, "monotonic", lambda: next(clock_values))
    monkeypatch.setattr(acceptance.time, "sleep", lambda _: None)
    monkeypatch.setattr(acceptance, "post_operation", operation)
    monkeypatch.setattr(acceptance, "blocked_count", observed)
    if observe_two:
        results, waiters = acceptance.run_race(engine, "isolated_test", "new-fixture-lock", [None, None])
        assert len(results) == 2 and waiters == 2
    else:
        with pytest.raises(acceptance.security.AcceptanceError, match="observed waiting"):
            acceptance.run_race(engine, "isolated_test", "new-fixture-lock", [None, None])
    assert released.is_set()
    transaction.rollback.assert_called_once()


def test_parallel_http_cookies_never_enter_worker_result(monkeypatch):
    cookie = "cookie-sentinel"
    transport = httpx.MockTransport(lambda request: httpx.Response(409, text="private-error-sentinel"))
    original_client = httpx.Client
    monkeypatch.setattr(acceptance.httpx, "Client", lambda **kwargs: original_client(transport=transport, **kwargs))
    original = SimpleNamespace(cookies={"session": cookie})
    result = acceptance.post_operation((original, "/api/v1/tools/library/resume", {}), SimpleNamespace(wait=lambda **_: None))
    assert result == (409, None)
    assert "sentinel" not in repr(result)
