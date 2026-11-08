"""CampusMind structured course schedules.

Revision ID: 20260923_0005
Revises: 20260923_0004
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260923_0005"
down_revision = "20260923_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "course_schedules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("course_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("academic_year", sa.String(length=20), nullable=False),
        sa.Column("semester", sa.String(length=40), nullable=False),
        sa.Column("weekday", sa.SmallInteger(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column("classroom", sa.String(length=120), nullable=False),
        sa.Column("campus", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("weekday >= 1 AND weekday <= 7", name="ck_course_schedules_weekday"),
        sa.CheckConstraint("end_time > start_time", name="ck_course_schedules_time_order"),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "course_id",
            "academic_year",
            "semester",
            "weekday",
            "start_time",
            name="uq_course_schedules_slot",
        ),
    )
    op.create_index("ix_course_schedules_course_id", "course_schedules", ["course_id"])
    op.create_index(
        "ix_course_schedules_term",
        "course_schedules",
        ["academic_year", "semester"],
    )


def downgrade() -> None:
    op.drop_index("ix_course_schedules_term", table_name="course_schedules")
    op.drop_index("ix_course_schedules_course_id", table_name="course_schedules")
    op.drop_table("course_schedules")
