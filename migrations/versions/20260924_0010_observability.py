"""CampusMind observability traces and spans.

Revision ID: 20260924_0010
Revises: 20260923_0009
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260924_0010"
down_revision = "20260923_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "observability_traces",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("request_type", sa.String(length=80), nullable=False),
        sa.Column("system_variant", sa.String(length=80), nullable=True),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("query", sa.Text(), nullable=True),
        sa.Column("route", sa.String(length=40), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("total_latency_ms", sa.Float(), nullable=True),
        sa.Column("retries", sa.Integer(), nullable=True),
        sa.Column("token_input", sa.Integer(), nullable=True),
        sa.Column("token_output", sa.Integer(), nullable=True),
        sa.Column("token_total", sa.Integer(), nullable=True),
        sa.Column("token_cost", sa.Float(), nullable=True),
        sa.Column("error_type", sa.String(length=160), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_observability_traces_started", "observability_traces", ["started_at"])
    op.create_index("ix_observability_traces_variant", "observability_traces", ["system_variant"])
    op.create_index("ix_observability_traces_actor", "observability_traces", ["actor_user_id"])

    op.create_table(
        "observability_spans",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("trace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("parent_span_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("span_name", sa.String(length=160), nullable=False),
        sa.Column("component", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("duration_ms", sa.Float(), nullable=True),
        sa.Column("input_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("output_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("metrics_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("error_type", sa.String(length=160), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["trace_id"], ["observability_traces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_span_id"], ["observability_spans.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_observability_spans_trace", "observability_spans", ["trace_id"])
    op.create_index("ix_observability_spans_component", "observability_spans", ["component"])

    # Runtime application sessions operate under campusmind_runtime since document security layer.
    # Alembic still connects as the admin role, so explicitly grant the new tables.
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE observability_traces TO campusmind_runtime")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE observability_spans TO campusmind_runtime")


def downgrade() -> None:
    op.drop_index("ix_observability_spans_component", table_name="observability_spans")
    op.drop_index("ix_observability_spans_trace", table_name="observability_spans")
    op.drop_table("observability_spans")
    op.drop_index("ix_observability_traces_actor", table_name="observability_traces")
    op.drop_index("ix_observability_traces_variant", table_name="observability_traces")
    op.drop_index("ix_observability_traces_started", table_name="observability_traces")
    op.drop_table("observability_traces")
