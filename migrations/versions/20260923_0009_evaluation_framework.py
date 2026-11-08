"""CampusMind evaluation benchmark runs and case measurements.

Revision ID: 20260923_0009
Revises: 20260923_0008
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260923_0009"
down_revision = "20260923_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "evaluation_benchmark_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("suite_key", sa.String(length=120), nullable=False),
        sa.Column("suite_version", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("case_count", sa.Integer(), nullable=False),
        sa.Column("passed_count", sa.Integer(), nullable=False),
        sa.Column("metrics_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("metadata_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_evaluation_benchmark_runs_suite", "evaluation_benchmark_runs", ["suite_key", "suite_version"])
    op.create_index("ix_evaluation_benchmark_runs_started", "evaluation_benchmark_runs", ["started_at"])

    op.create_table(
        "evaluation_case_measurements",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("case_key", sa.String(length=120), nullable=False),
        sa.Column("category", sa.String(length=80), nullable=False),
        sa.Column("system_variant", sa.String(length=80), nullable=False),
        sa.Column("expected_route", sa.String(length=32), nullable=True),
        sa.Column("actual_route", sa.String(length=32), nullable=True),
        sa.Column("expected_tool", sa.String(length=80), nullable=True),
        sa.Column("actual_tool", sa.String(length=80), nullable=True),
        sa.Column("task_success", sa.Boolean(), nullable=True),
        sa.Column("approval_expected", sa.Boolean(), nullable=True),
        sa.Column("approval_actual", sa.Boolean(), nullable=True),
        sa.Column("latency_ms", sa.Float(), nullable=True),
        sa.Column("metrics_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("observation_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["evaluation_benchmark_runs.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("run_id", "case_key", "system_variant", name="uq_evaluation_case_measurement"),
    )
    op.create_index("ix_evaluation_case_measurements_run", "evaluation_case_measurements", ["run_id"])
    op.create_index("ix_evaluation_case_measurements_category", "evaluation_case_measurements", ["category"])


def downgrade() -> None:
    op.drop_index("ix_evaluation_case_measurements_category", table_name="evaluation_case_measurements")
    op.drop_index("ix_evaluation_case_measurements_run", table_name="evaluation_case_measurements")
    op.drop_table("evaluation_case_measurements")
    op.drop_index("ix_evaluation_benchmark_runs_started", table_name="evaluation_benchmark_runs")
    op.drop_index("ix_evaluation_benchmark_runs_suite", table_name="evaluation_benchmark_runs")
    op.drop_table("evaluation_benchmark_runs")
