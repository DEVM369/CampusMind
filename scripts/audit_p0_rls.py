"""Read-only audit of the configured PostgreSQL identity and ORM RLS context."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from campusmind.config import get_settings
from campusmind.platform.security import AuthorizationBackendError, bind_acl_context


def audit() -> int:
    settings = get_settings()
    engine = create_engine(settings.sqlalchemy_database_url,
                           connect_args={"connect_timeout": 4})
    result = {}
    try:
        with engine.connect() as connection:
            connection.exec_driver_sql("SET TRANSACTION READ ONLY")
            result["login"] = dict(connection.execute(text(
                "SELECT session_user, current_user, rolsuper, rolbypassrls "
                "FROM pg_roles WHERE rolname = session_user"
            )).mappings().one())
            result["policies"] = [dict(row) for row in connection.execute(text(
                "SELECT schemaname, tablename, policyname, permissive, roles, cmd, "
                "qual, with_check FROM pg_policies WHERE schemaname = 'public' "
                "AND tablename IN ('documents', 'document_versions', 'document_chunks', "
                "'campus_action_requests', 'classroom_reservations', 'library_reservations')"
            )).mappings()]
            connection.rollback()
        # Exercise the actual Session.after_begin hook twice, including after
        # transaction boundaries. All transactions are explicitly read-only.
        for label, levels, actor in [("public", ["public"], None),
                                     ("personal", ["public", "personal"], uuid4())]:
            with engine.connect() as connection:
                connection.exec_driver_sql("SET TRANSACTION READ ONLY")
                with bind_acl_context(permission_levels=levels, actor_user_id=actor):
                    with Session(bind=connection) as session:
                        row = session.execute(text(
                            "SELECT session_user, current_user, rolsuper, rolbypassrls, "
                            "current_setting('row_security') AS row_security, "
                            "current_setting('campusmind.permission_levels', true) AS levels, "
                            "current_setting('campusmind.actor_user_id', true) AS actor "
                            "FROM pg_roles WHERE rolname = current_user"
                        )).mappings().one()
                        result[label] = dict(row)
                        assert row["current_user"] == "campusmind_runtime"
                        assert not row["rolsuper"] and not row["rolbypassrls"]
                        assert row["levels"] == ",".join(levels)
                        assert row["actor"] == (str(actor) if actor else "")
                connection.rollback()
        result["verified"] = True
    except (SQLAlchemyError, AuthorizationBackendError) as exc:
        # Connection errors may include infrastructure details; never print DSNs.
        result["verified"] = False
        result["error_type"] = type(exc).__name__
    finally:
        engine.dispose()
    print(json.dumps(result, indent=2, default=str))
    return 0 if result.get("verified") else 1


if __name__ == "__main__":
    raise SystemExit(audit())
