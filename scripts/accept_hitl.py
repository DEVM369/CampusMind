"""Isolated PostgreSQL/HTTP acceptance for approvals, replay and resource races.

Run beside accept_student_security.py inside the API container. Every run adds
new synthetic books/traces and uses unused far-future classroom dates. No prior
reservation, inventory, account, password or role is changed or deleted.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, contextmanager
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from threading import Barrier, BrokenBarrierError
from uuid import UUID, uuid4

import httpx
from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from campusmind.platform.db import AgentRun, AuditLog, ToolCall, get_engine
from campusmind.platform.security import AuthorizationBackendError
from campusmind.tools.actions import (
    ROOMS,
    action_requests,
    classroom_reservations,
    library_books,
    library_inventory,
    library_reservations,
)

if __package__:
    from . import accept_student_security as security
else:
    import accept_student_security as security

WAITERS_SQL = text("""
    WITH RECURSIVE blocked(pid) AS (
        SELECT pid FROM pg_stat_activity
        WHERE datname = current_database() AND :blocker = ANY(pg_blocking_pids(pid))
        UNION
        SELECT a.pid FROM pg_stat_activity a JOIN blocked b
            ON b.pid = ANY(pg_blocking_pids(a.pid))
        WHERE a.datname = current_database()
    )
    SELECT count(DISTINCT pid) FROM blocked
""")


@contextmanager
def readonly(engine):
    with engine.connect() as connection:
        if connection.dialect.name == "postgresql":
            connection.exec_driver_sql("SET TRANSACTION READ ONLY")
            connection.exec_driver_sql("SET LOCAL statement_timeout = '10s'")
        yield connection


def create_books(engine, database, run_id):
    books = {}
    now = datetime.now(UTC)
    with engine.begin() as connection:
        security.check_target(connection, database)
        for label in ("cancel", "replay", "lastcopy"):
            book = {"id": uuid4(), "title": f"CMHITL {run_id} {label}",
                    "code": f"CMHITL-{run_id[:20]}-{label}"}
            connection.execute(library_books.insert().values(
                id=book["id"], book_code=book["code"], title=book["title"],
                author="CampusMind synthetic acceptance", subject="Synthetic HITL acceptance",
                location="Synthetic acceptance shelf", created_at=now, updated_at=now,
            ))
            connection.execute(library_inventory.insert().values(
                id=uuid4(), book_id=book["id"], total_copies=1, available_copies=1,
                reserved_copies=0, updated_at=now,
            ))
            books[label] = book
    return books


def unused_classroom_dates(engine, run_id, count=3):
    start = date(2090, 1, 1) + timedelta(days=int(run_id[:6], 16) % 2500)
    found = []
    with readonly(engine) as connection:
        for offset in range(366):
            target = start + timedelta(days=offset)
            requests = connection.scalar(select(func.count()).select_from(action_requests).where(
                action_requests.c.request_json["reservation_date"].as_string() == target.isoformat()
            ))
            reservations = connection.scalar(select(func.count()).select_from(classroom_reservations).where(
                classroom_reservations.c.reservation_date == target
            ))
            if requests == reservations == 0:
                found.append(target)
                if len(found) == count:
                    return found
    raise security.AcceptanceError("Could not find unused far-future synthetic classroom dates")


def new_trace(engine, database, actor, run_id):
    trace_id = uuid4()
    with engine.begin() as connection:
        security.check_target(connection, database)
        connection.execute(AgentRun.__table__.insert().values(
            id=trace_id, user_id=actor, query=f"Synthetic HITL acceptance {run_id}",
            intent="synthetic_acceptance", risk_level="medium", status="synthetic_fixture",
            retrieval_strategy="synthetic_http_hitl",
        ))
    return trace_id


def path(domain, command):
    security.require(domain in {"library", "classroom"}, "Unsupported acceptance tool")
    return f"/api/v1/tools/{domain}/{command}"


def prepare(http, engine, database, run_id, actor, *, book=None, target=None):
    domain = "library" if book is not None else "classroom"
    query = (f"\u5e2e\u6211\u9884\u7ea6\u300a{book['title']}\u300b\u8fd9\u672c\u4e66" if book is not None
             else f"\u5e2e\u6211\u9884\u7ea6{target.isoformat()}\u4e0b\u534830\u4eba\u7684\u6559\u5ba4")
    trace = new_trace(engine, database, actor, run_id)
    result = security.response_json(http.post(path(domain, "prepare"), json={
        "actor_user_id": str(actor), "trace_id": str(trace), "query": query,
    }), 200, f"{domain} prepare")
    security.require(result["status"] == "awaiting_approval" and result["actor_user_id"] == str(actor)
                     and result["trace_id"] == str(trace), "Prepare did not return an owned pending approval")
    audit = result["audit"]
    if audit.get("audit_log_persisted") is not True or audit.get("tool_call_persisted") is not True:
        def error_kind(value):
            if not value:
                return "none"
            return str(value).split(":", 1)[0][:64]

        def error_constraint(value):
            if not value:
                return "none"
            diagnostic = getattr(getattr(value, "orig", None), "diag", None)
            return str(getattr(diagnostic, "constraint_name", None) or "none")[:96]

        def error_sqlstate(value):
            if not value:
                return "none"
            diagnostic = getattr(getattr(value, "orig", None), "diag", None)
            return str(getattr(diagnostic, "sqlstate", None) or "none")[:16]

        raise security.AcceptanceError(
            "Prepare audit was not persisted; "
            f"tool_call_persisted={audit.get('tool_call_persisted')!r}, "
            f"audit_log_persisted={audit.get('audit_log_persisted')!r}, "
            f"tool_error_type={error_kind(audit.get('tool_call_error'))}, "
            f"audit_error_type={error_kind(audit.get('audit_log_error'))}, "
            f"audit_constraint={error_constraint(audit.get('audit_log_error'))}, "
            f"audit_sqlstate={error_sqlstate(audit.get('audit_log_error'))}"
        )
    if book is not None:
        security.require({item["book_id"] for item in result["candidates"]} == {str(book["id"])},
                         "Library prepare returned a resource outside the new synthetic book")
        resource = str(book["id"])
    else:
        security.require(result["requested"]["reservation_date"] == target.isoformat(),
                         "Classroom prepare changed the selected synthetic date")
        resource = result["candidates"][0]["room_id"]
        security.require(resource in {room.room_id for room in ROOMS}, "Unexpected synthetic classroom")
    return {"domain": domain, "actor": actor, "approval": UUID(result["approval_id"]),
            "trace": trace, "resource": resource, "query": query, "target": target}


def resume_body(action, *, approved=True):
    field = "book_id" if action["domain"] == "library" else "room_id"
    return {"actor_user_id": str(action["actor"]), "approval_id": str(action["approval"]),
            "approved": approved, field: action["resource"]}


def resume(http, action, *, approved=True):
    return http.post(path(action["domain"], "resume"), json=resume_body(action, approved=approved))


def library_state(engine, book):
    with readonly(engine) as connection:
        row = connection.execute(select(library_inventory).where(
            library_inventory.c.book_id == book["id"]
        )).mappings().one()
        count = connection.scalar(select(func.count()).select_from(library_reservations).where(
            library_reservations.c.book_id == book["id"]
        ))
    return {"total_copies": row["total_copies"], "available_copies": row["available_copies"],
            "reserved_copies": row["reserved_copies"], "reservation_count": count}


def require_library_state(engine, book, reservations):
    state = library_state(engine, book)
    security.require(state == {"total_copies": 1, "available_copies": 1 - reservations,
                               "reserved_copies": reservations, "reservation_count": reservations},
                     "Synthetic book inventory or reservation count is inconsistent")
    return state


def action_state(engine, action, expected_status, reservations):
    table = library_reservations if action["domain"] == "library" else classroom_reservations
    execution_action = "execute_book_reservation" if action["domain"] == "library" else "execute_reservation"
    with readonly(engine) as connection:
        row = connection.execute(select(action_requests).where(
            action_requests.c.id == action["approval"]
        )).mappings().one()
        rows = connection.execute(select(table).where(
            table.c.action_request_id == action["approval"]
        )).mappings().all()
        tools = connection.scalar(select(func.count()).select_from(ToolCall).where(
            ToolCall.agent_run_id == action["trace"], ToolCall.status == "executed",
        ))
        audits = connection.scalar(select(func.count()).select_from(AuditLog).where(
            AuditLog.action == execution_action,
            AuditLog.detail_json["arguments"]["approval_id"].as_string() == str(action["approval"]),
        ))
    security.require(row["status"] == expected_status and row["actor_user_id"] == action["actor"]
                     and row["trace_id"] == action["trace"], "Approval state, owner or trace changed unexpectedly")
    security.require(len(rows) == tools == audits == reservations,
                     "Reservation or execution audit count does not match the expected single effect")
    resource_field = "book_id" if action["domain"] == "library" else "room_id"
    security.require(all(row["actor_user_id"] == action["actor"]
                         and str(row[resource_field]) == action["resource"] for row in rows),
                     "The committed reservation has an unexpected owner or resource")
    if reservations:
        security.require(row["selected_resource_id"] == action["resource"], "An unselected resource was reserved")
    else:
        security.require(row["selected_resource_id"] is None, "An unexecuted action selected a resource")
    return {"reservation_count": len(rows), "execution_tool_calls": tools, "execution_audit_logs": audits,
            "reservation_id": str(rows[0]["id"]) if rows else None}


def negative_checks(engine, owner, other, anonymous, action, other_actor):
    domain = action["domain"]
    body = resume_body(action)
    cases = [
        (anonymous, path(domain, "resume"), body, 401, "anonymous approval"),
        (owner, path(domain, "resume"), {**body, "actor_user_id": str(other_actor)}, 403, "forged actor"),
        (other, path(domain, "resume"), {**body, "actor_user_id": str(other_actor)}, 403, "foreign approval"),
        (owner, path(domain, "resume"), {**body, "approval_id": str(uuid4())}, 404, "missing approval"),
        (owner, path(domain, "resume"), {key: value for key, value in body.items() if key != "approved"},
         422, "missing explicit decision"),
    ]
    field = "book_id" if domain == "library" else "room_id"
    cases.append((owner, path(domain, "resume"), {**body, field: str(uuid4())}, 409, "unselected resource"))
    wrong_domain = "classroom" if domain == "library" else "library"
    wrong = {key: value for key, value in body.items() if key != field}
    cases.append((owner, path(wrong_domain, "resume"), wrong, 409, "wrong tool"))
    statuses = []
    for http, endpoint, payload, status, label in cases:
        response = http.post(endpoint, json=payload)
        security.response_json(response, status, f"{domain} {label}")
        statuses.append(response.status_code)
        action_state(engine, action, "awaiting_approval", 0)
    return statuses


def reject_and_replay(engine, http, action):
    result = security.response_json(resume(http, action, approved=False), 200, "explicit rejection")
    security.require(result["status"] == "rejected" and result["reservation"] is None,
                     "Rejected approval created a reservation")
    replay = security.response_json(resume(http, action), 200, "confirmation after rejection")
    security.require(replay["status"] == "rejected" and replay["reservation"] is None
                     and replay["idempotent"] is True and replay["state_changed"] is False,
                     "A rejected approval was executed on replay")
    return action_state(engine, action, "rejected", 0)


def blocked_count(engine, blocker):
    with readonly(engine) as connection:
        return int(connection.execute(WAITERS_SQL, {"blocker": blocker}).scalar_one())


def post_operation(operation, start):
    original, endpoint, payload = operation
    with httpx.Client(base_url=security.BASE_URL, timeout=45, trust_env=False,
                      follow_redirects=False, cookies=dict(original.cookies)) as http:
        start.wait(timeout=10)
        response = http.post(endpoint, json=payload)
        return response.status_code, response.json() if response.status_code == 200 else None


def run_race(engine, database, lock_key, operations):
    """Hold only the synthetic resource lock until both requests are observed waiting."""
    security.require(len(operations) == 2, "A race requires exactly two requests")
    start = Barrier(3)
    observed = 0
    with ThreadPoolExecutor(max_workers=2) as pool, engine.connect() as blocker:
        transaction = blocker.begin()
        try:
            security.check_target(blocker, database)
            pid = blocker.exec_driver_sql("SELECT pg_backend_pid()").scalar_one()
            blocker.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": lock_key})
            futures = [pool.submit(post_operation, operation, start) for operation in operations]
            start.wait(timeout=10)
            deadline = time.monotonic() + 12
            while time.monotonic() < deadline:
                observed = max(observed, blocked_count(engine, pid))
                if observed == 2:
                    break
                time.sleep(0.1)
            security.require(observed == 2, "Both HTTP requests were not observed waiting on the test resource")
        finally:
            # Release before collecting futures or allowing the executor to join workers.
            start.abort()
            transaction.rollback()
        results = [future.result(timeout=50) for future in futures]
    return results, observed


def same_approval_result(results):
    security.require([status for status, _ in results] == [200, 200], "Duplicate confirmation did not return HTTP 200 twice")
    bodies = [body for _, body in results]
    security.require(all(body["status"] == "executed" for body in bodies)
                     and sorted((body["idempotent"], body["state_changed"]) for body in bodies)
                     == [(False, True), (True, False)]
                     and len({body["reservation"]["reservation_id"] for body in bodies}) == 1,
                     "Concurrent duplicate confirmations did not converge on one reservation")
    return bodies[0]["reservation"]["reservation_id"]


def single_winner_result(results):
    security.require(sorted(status for status, _ in results) == [200, 409],
                     "The last resource did not produce one success and one conflict")
    winner = next(index for index, (status, _) in enumerate(results) if status == 200)
    body = results[winner][1]
    security.require(body["status"] == "executed" and body["state_changed"] is True
                     and body["idempotent"] is False, "The winning request did not execute one new reservation")
    return winner


def check_replay(http, action, reservation_id):
    result = security.response_json(resume(http, action), 200, "executed approval replay")
    check_response_owner(result, action)
    security.require(result["status"] == "executed" and result["idempotent"] is True
                     and result["state_changed"] is False
                     and result["reservation"]["reservation_id"] == reservation_id,
                     "Replay changed the committed reservation")


def check_response_owner(result, action):
    resource_field = "book_id" if action["domain"] == "library" else "room_id"
    security.require(result["actor_user_id"] == str(action["actor"])
                     and result["approval_id"] == str(action["approval"])
                     and result["reservation"][resource_field] == action["resource"],
                     "The HTTP reservation has an unexpected owner, approval or resource")


def record(checks, name, **facts):
    checks.append({"name": name, "passed": True, **facts})
    print(f"PASS: {name}" + (f"; HTTP {facts['http_statuses']}; lock_waiters={facts['lock_waiters_observed']}"
                            if "http_statuses" in facts else ""), flush=True)


def check_actions(engine, database, run_id, clients, identities, anonymous, checks):
    owner, other = clients["student001"], clients["admin"]
    actor, other_actor = identities["student001"], identities["admin"]
    books = create_books(engine, database, run_id)
    dates = unused_classroom_dates(engine, run_id)
    for domain in ("library", "classroom"):
        action = prepare(owner, engine, database, run_id, actor,
                         book=books["cancel"] if domain == "library" else None,
                         target=dates[0] if domain == "classroom" else None)
        action_state(engine, action, "awaiting_approval", 0)
        if domain == "library":
            require_library_state(engine, books["cancel"], 0)
        negative_statuses = negative_checks(engine, owner, other, anonymous, action, other_actor)
        state = reject_and_replay(engine, owner, action)
        if domain == "library":
            state.update(require_library_state(engine, books["cancel"], 0))
        record(checks, f"{domain} prepare, authorization, rejection and rejected replay",
               negative_http_statuses=negative_statuses, **state)

    for domain in ("library", "classroom"):
        action = prepare(owner, engine, database, run_id, actor,
                         book=books["replay"] if domain == "library" else None,
                         target=dates[1] if domain == "classroom" else None)
        action_state(engine, action, "awaiting_approval", 0)
        key = (f"campusmind:library:{action['resource']}" if domain == "library" else
               f"campusmind:classroom:{action['resource']}:{dates[1].isoformat()}")
        operation = (owner, path(domain, "resume"), resume_body(action))
        results, waiters = run_race(engine, database, key, [operation, operation])
        for _, result in results:
            if result is not None:
                check_response_owner(result, action)
        reservation_id = same_approval_result(results)
        check_replay(owner, action, reservation_id)
        state = action_state(engine, action, "executed", 1)
        security.require(state["reservation_id"] == reservation_id, "HTTP and SQL reservation IDs do not match")
        if domain == "library":
            state.update(require_library_state(engine, books["replay"], 1))
        record(checks, f"{domain} concurrent same-approval confirmation and replay",
               http_statuses=[status for status, _ in results], lock_waiters_observed=waiters, **state)

    for domain in ("library", "classroom"):
        actions = [prepare(http, engine, database, run_id, user,
                           book=books["lastcopy"] if domain == "library" else None,
                           target=dates[2] if domain == "classroom" else None)
                   for http, user in ((owner, actor), (other, other_actor))]
        for action in actions:
            action_state(engine, action, "awaiting_approval", 0)
        security.require(actions[0]["resource"] == actions[1]["resource"], "The race does not target one shared test resource")
        key = (f"campusmind:library:{actions[0]['resource']}" if domain == "library" else
               f"campusmind:classroom:{actions[0]['resource']}:{dates[2].isoformat()}")
        operations = [(http, path(domain, "resume"), resume_body(action))
                      for http, action in zip((owner, other), actions, strict=True)]
        results, waiters = run_race(engine, database, key, operations)
        winner = single_winner_result(results)
        check_response_owner(results[winner][1], actions[winner])
        for index, action in enumerate(actions):
            state = action_state(engine, action, "executed" if index == winner else "awaiting_approval", int(index == winner))
            if index == winner:
                security.require(state["reservation_id"] == results[winner][1]["reservation"]["reservation_id"],
                                 "The winning HTTP and SQL reservation IDs do not match")
        state = require_library_state(engine, books["lastcopy"], 1) if domain == "library" else {"reservation_count": 1}
        if domain == "classroom":
            with readonly(engine) as connection:
                count = connection.scalar(select(func.count()).select_from(classroom_reservations).where(
                    classroom_reservations.c.reservation_date == dates[2],
                    classroom_reservations.c.room_id == actions[0]["resource"],
                ))
            security.require(count == 1, "The shared classroom slot has more than one reservation")
        record(checks, f"{domain} two-owner last-resource competition",
               http_statuses=sorted(status for status, _ in results), lock_waiters_observed=waiters, **state)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--test-database", required=True)
    parser.add_argument("--run-synthetic-actions", action="store_true",
                        help="execute synthetic prepare/reject/confirm requests in this named test DB")
    parser.add_argument("--report-dir", type=Path,
                        help="write a uniquely named sanitized JSON report without credentials or cookies")
    args = parser.parse_args(argv)
    run_id = uuid4().hex
    checks = []
    engine = None
    phase = "target preflight"
    logged_in = []
    passed = False
    try:
        engine = get_engine()
        with readonly(engine) as connection:
            security.check_target(connection, args.test_database)
        with Session(engine) as session:
            identities = security.existing_identities(session)
        if not args.run_synthetic_actions:
            print("PASS: database/account preflight; no synthetic actions requested")
            return 0
        with ExitStack() as stack:
            anonymous = stack.enter_context(security.client())
            status = security.response_json(anonymous.get("/api/v1/rag/status"), 200, "embedding provider")
            security.require(status["embedding_provider"] == "deterministic", "API must use deterministic embeddings")
            clients = {}
            for username in ("student001", "admin"):
                phase = f"existing {username} login"
                http = stack.enter_context(security.client())
                logged_in.append(http)
                stack.callback(security.logout_session, http, logged_in)
                security.verify_login(http, username, identities[username])
                clients[username] = http
                record(checks, f"existing {username} HTTP login and role")
            phase = "synthetic HTTP HITL actions and PostgreSQL contention"
            print(f"Synthetic acceptance run: {run_id}", flush=True)
            check_actions(engine, args.test_database, run_id, clients, identities, anonymous, checks)
        security.require(not logged_in, "A verification session could not be logged out")
        passed = True
    except security.AcceptanceError as exc:
        print(f"FAIL: {phase}: {exc}", file=sys.stderr)
    except security.GetPassWarning:
        print("FAIL: hidden password input unavailable; use an interactive terminal", file=sys.stderr)
    except (EOFError, KeyboardInterrupt):
        print("Acceptance cancelled", file=sys.stderr)
    except (SQLAlchemyError, AuthorizationBackendError, httpx.HTTPError, OSError, ValueError,
            KeyError, TypeError, IndexError, BrokenBarrierError, TimeoutError) as exc:
        print(f"FAIL: {phase} ({type(exc).__name__}); private diagnostics suppressed", file=sys.stderr)
    finally:
        if engine is not None:
            engine.dispose()
    report = {"scope": "isolated_postgresql_http_hitl", "run_id": run_id, "passed": passed, "checks": checks}
    if args.report_dir:
        try:
            args.report_dir.mkdir(parents=True, exist_ok=True)
            report_path = args.report_dir / f"hitl-{run_id}.json"
            with report_path.open("x", encoding="utf-8") as output:
                json.dump(report, output, indent=2)
                output.write("\n")
            print(f"Sanitized report: {report_path}", flush=True)
        except OSError:
            print("FAIL: could not write the sanitized acceptance report", file=sys.stderr)
            return 1
    if passed:
        print("CM_HITL_ACCEPTANCE_PASSED")
        print("Synthetic reservations/traces are retained. Model quality and new-image/CI checks are separate.")
        return 0
    print("Synthetic fixtures are retained; no prior data was deleted or inventory reset.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
