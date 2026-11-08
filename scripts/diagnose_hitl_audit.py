"""Safely diagnose the deployed audit_logs insert contract.

The probe performs one synthetic insert inside a transaction and always rolls it
back. It prints schema names and sanitized driver diagnostics only.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import MetaData, Table, insert, inspect, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from campusmind.platform.db import User, get_engine
from campusmind.tools.actions import LegacyAuditMirror


def safe_driver_error(exc: BaseException) -> dict[str, str]:
    original = getattr(exc, "orig", None)
    diagnostic = getattr(original, "diag", None)
    return {
        "type": type(exc).__name__,
        "driver_type": type(original).__name__ if original is not None else "none",
        "sqlstate": str(getattr(diagnostic, "sqlstate", None) or "none")[:16],
        "constraint": str(getattr(diagnostic, "constraint_name", None) or "none")[:96],
        "column": str(getattr(diagnostic, "column_name", None) or "none")[:96],
        "datatype": str(getattr(diagnostic, "datatype_name", None) or "none")[:96],
    }


def main() -> int:
    engine = get_engine()
    try:
        with engine.connect() as connection:
            database = connection.execute(text("SELECT current_database()")).scalar_one()
            inspector = inspect(connection)
            columns = [item["name"] for item in inspector.get_columns("audit_logs")]
            constraints = [
                item.get("name") or "unnamed"
                for item in inspector.get_check_constraints("audit_logs")
            ]
            foreign_keys = [
                item.get("name") or "unnamed"
                for item in inspector.get_foreign_keys("audit_logs")
            ]
            users = connection.execute(
                select(User.username).where(User.username.in_(["student001", "admin"]))
            ).scalars().all()

            metadata = MetaData()
            table = Table("audit_logs", metadata, autoload_with=connection)

            actor = connection.execute(
                select(User.id).where(User.username == "student001")
            ).scalar_one_or_none()
            values = {
                "id": uuid4(),
                "actor_user_id": actor,
                "action": "campusmind_synthetic_audit_probe",
                "resource_type": "diagnostic",
                "resource_id": None,
                "request_id": None,
                "ip_address": None,
                "detail_json": {"synthetic": True, "probe": True},
                "created_at": datetime.now(UTC),
            }
            connection.rollback()
            transaction = connection.begin()
            try:
                connection.execute(insert(table).values(values))
            except SQLAlchemyError as exc:
                transaction.rollback()
                print(json.dumps({
                    "database": database,
                    "audit_columns": columns,
                    "audit_check_constraints": sorted(constraints),
                    "audit_foreign_keys": sorted(foreign_keys),
                    "accounts_found": sorted(users),
                    "probe": "rolled_back",
                    "result": "FAIL",
                    "error": safe_driver_error(exc),
                }, ensure_ascii=False, indent=2))
                return 1
            transaction.rollback()
            with Session(engine) as session:
                session_actor = session.scalar(select(User.id).where(User.username == "student001"))
                mirror = LegacyAuditMirror(session)
                mirror_table = mirror._reflect("audit_logs")
                payload = mirror._payload(
                    mirror_table,
                    kind="audit",
                    actor_user_id=session_actor,
                    trace_id=None,
                    tool_name="campusmind.synthetic_probe",
                    action="prepare_reservation",
                    arguments={"synthetic": True},
                    result={"synthetic": True},
                    status="pending",
                    requires_approval=True,
                    resource_type="diagnostic",
                )
                try:
                    session.execute(insert(mirror_table).values(payload))
                    session.rollback()
                    mirror_result = {"result": "PASS", "payload_columns": sorted(payload)}
                except SQLAlchemyError as exc:
                    session.rollback()
                    mirror_result = {
                        "result": "FAIL",
                        "payload_columns": sorted(payload),
                        "error": safe_driver_error(exc),
                    }
            print(json.dumps({
                "database": database,
                "audit_columns": columns,
                "audit_check_constraints": sorted(constraints),
                "audit_foreign_keys": sorted(foreign_keys),
                "accounts_found": sorted(users),
                "probe": "rolled_back",
                "result": "PASS",
                "mirror_probe": mirror_result,
            }, ensure_ascii=False, indent=2))
            return 0
    except (SQLAlchemyError, OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"result": "FAIL", "error": safe_driver_error(exc)}, ensure_ascii=False))
        return 1
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
