"""CampusMind baseline schema.

Revision ID: 20260923_0001
Revises: None
Create Date: 2026-09-23
"""
from pathlib import Path

from alembic import op

revision = "20260923_0001"
down_revision = None
branch_labels = None
depends_on = None

_ROOT = Path(__file__).resolve().parents[2]


def _execute_sql_file(name: str) -> None:
    raw = (_ROOT / "infra" / "postgres" / name).read_text(encoding="utf-8")
    sql = "\n".join(line for line in raw.splitlines() if not line.lstrip().startswith("--"))
    connection = op.get_bind()
    # SQLAlchemy/psycopg can execute one DDL statement at a time reliably.
    for statement in sql.split(";"):
        statement = statement.strip()
        if statement and not statement.startswith("--"):
            connection.exec_driver_sql(statement)


def upgrade() -> None:
    _execute_sql_file("schema_v1.sql")


def downgrade() -> None:
    _execute_sql_file("drop_schema_v1.sql")
