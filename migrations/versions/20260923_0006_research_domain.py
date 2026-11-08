"""CampusMind structured research domain.

Revision ID: 20260923_0006
Revises: 20260923_0005
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260923_0006"
down_revision = "20260923_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "research_teacher_profiles",
        sa.Column("teacher_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("display_name", sa.String(length=160), nullable=False),
        sa.Column("title", sa.String(length=80), nullable=True),
        sa.Column("bio", sa.Text(), nullable=True),
        sa.Column("homepage_url", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["teacher_id"], ["teachers.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_research_teacher_profiles_name", "research_teacher_profiles", ["display_name"])

    op.create_table(
        "research_areas",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("code", name="uq_research_areas_code"),
        sa.UniqueConstraint("name", name="uq_research_areas_name"),
    )
    op.create_index("ix_research_areas_name", "research_areas", ["name"])

    op.create_table(
        "teacher_research_areas",
        sa.Column("teacher_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("research_area_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["teacher_id"], ["teachers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["research_area_id"], ["research_areas.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("teacher_id", "research_area_id", name="pk_teacher_research_areas"),
    )
    op.create_index("ix_teacher_research_areas_area", "teacher_research_areas", ["research_area_id"])

    op.create_table(
        "research_labs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("website_url", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("code", name="uq_research_labs_code"),
    )
    op.create_index("ix_research_labs_name", "research_labs", ["name"])

    op.create_table(
        "research_lab_memberships",
        sa.Column("lab_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("teacher_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(length=80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["lab_id"], ["research_labs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["teacher_id"], ["teachers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("lab_id", "teacher_id", name="pk_research_lab_memberships"),
    )
    op.create_index("ix_research_lab_memberships_teacher", "research_lab_memberships", ["teacher_id"])

    op.create_table(
        "research_projects",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(length=60), nullable=False),
        sa.Column("name", sa.String(length=240), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("funding_source", sa.String(length=160), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("code", name="uq_research_projects_code"),
    )
    op.create_index("ix_research_projects_name", "research_projects", ["name"])
    op.create_index("ix_research_projects_status", "research_projects", ["status"])

    op.create_table(
        "research_project_members",
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("teacher_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(length=80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["research_projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["teacher_id"], ["teachers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("project_id", "teacher_id", name="pk_research_project_members"),
    )
    op.create_index("ix_research_project_members_teacher", "research_project_members", ["teacher_id"])

    op.create_table(
        "research_papers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("abstract", sa.Text(), nullable=True),
        sa.Column("venue", sa.String(length=240), nullable=True),
        sa.Column("published_year", sa.Integer(), nullable=True),
        sa.Column("doi", sa.String(length=200), nullable=True),
        sa.Column("url", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("title", name="uq_research_papers_title"),
    )
    op.create_index("ix_research_papers_title", "research_papers", ["title"])
    op.create_index("ix_research_papers_year", "research_papers", ["published_year"])

    op.create_table(
        "research_paper_authors",
        sa.Column("paper_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("teacher_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("author_order", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("author_order >= 1", name="ck_research_paper_authors_order"),
        sa.ForeignKeyConstraint(["paper_id"], ["research_papers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["teacher_id"], ["teachers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("paper_id", "teacher_id", name="pk_research_paper_authors"),
    )
    op.create_index("ix_research_paper_authors_teacher", "research_paper_authors", ["teacher_id"])


def downgrade() -> None:
    op.drop_index("ix_research_paper_authors_teacher", table_name="research_paper_authors")
    op.drop_table("research_paper_authors")
    op.drop_index("ix_research_papers_year", table_name="research_papers")
    op.drop_index("ix_research_papers_title", table_name="research_papers")
    op.drop_table("research_papers")
    op.drop_index("ix_research_project_members_teacher", table_name="research_project_members")
    op.drop_table("research_project_members")
    op.drop_index("ix_research_projects_status", table_name="research_projects")
    op.drop_index("ix_research_projects_name", table_name="research_projects")
    op.drop_table("research_projects")
    op.drop_index("ix_research_lab_memberships_teacher", table_name="research_lab_memberships")
    op.drop_table("research_lab_memberships")
    op.drop_index("ix_research_labs_name", table_name="research_labs")
    op.drop_table("research_labs")
    op.drop_index("ix_teacher_research_areas_area", table_name="teacher_research_areas")
    op.drop_table("teacher_research_areas")
    op.drop_index("ix_research_areas_name", table_name="research_areas")
    op.drop_table("research_areas")
    op.drop_index("ix_research_teacher_profiles_name", table_name="research_teacher_profiles")
    op.drop_table("research_teacher_profiles")
