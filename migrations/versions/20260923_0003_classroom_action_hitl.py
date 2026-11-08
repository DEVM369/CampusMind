"""CampusMind classroom action requests and reservations.

Revision ID: 20260923_0003
Revises: 20260923_0002
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260923_0003"
down_revision = "20260923_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "campus_action_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("trace_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action_type", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("request_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("candidates_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("selected_resource_id", sa.String(length=120), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_campus_action_requests_trace_id", "campus_action_requests", ["trace_id"])
    op.create_index("ix_campus_action_requests_actor_user_id", "campus_action_requests", ["actor_user_id"])
    op.create_index("ix_campus_action_requests_status", "campus_action_requests", ["status"])

    op.create_table(
        "classroom_reservations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("action_request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("room_id", sa.String(length=80), nullable=False),
        sa.Column("room_name", sa.String(length=80), nullable=False),
        sa.Column("building", sa.String(length=160), nullable=False),
        sa.Column("reservation_date", sa.Date(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column("party_size", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["action_request_id"], ["campus_action_requests.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("action_request_id", name="uq_classroom_reservations_action_request"),
    )
    op.create_index("ix_classroom_reservations_actor_user_id", "classroom_reservations", ["actor_user_id"])
    op.create_index("ix_classroom_reservations_room_date", "classroom_reservations", ["room_id", "reservation_date"])


def downgrade() -> None:
    op.drop_index("ix_classroom_reservations_room_date", table_name="classroom_reservations")
    op.drop_index("ix_classroom_reservations_actor_user_id", table_name="classroom_reservations")
    op.drop_table("classroom_reservations")
    op.drop_index("ix_campus_action_requests_status", table_name="campus_action_requests")
    op.drop_index("ix_campus_action_requests_actor_user_id", table_name="campus_action_requests")
    op.drop_index("ix_campus_action_requests_trace_id", table_name="campus_action_requests")
    op.drop_table("campus_action_requests")
