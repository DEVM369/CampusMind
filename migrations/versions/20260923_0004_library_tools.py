"""CampusMind library tools and inventory.

Revision ID: 20260923_0004
Revises: 20260923_0003
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260923_0004"
down_revision = "20260923_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "library_books",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("book_code", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("author", sa.String(length=200), nullable=False),
        sa.Column("isbn", sa.String(length=40), nullable=True),
        sa.Column("subject", sa.String(length=160), nullable=True),
        sa.Column("location", sa.String(length=160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("book_code", name="uq_library_books_book_code"),
    )
    op.create_index("ix_library_books_book_code", "library_books", ["book_code"])
    op.create_index("ix_library_books_title", "library_books", ["title"])
    op.create_index("ix_library_books_subject", "library_books", ["subject"])

    op.create_table(
        "library_inventory",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("book_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("total_copies", sa.Integer(), nullable=False),
        sa.Column("available_copies", sa.Integer(), nullable=False),
        sa.Column("reserved_copies", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("total_copies >= 0", name="ck_library_inventory_total_nonnegative"),
        sa.CheckConstraint("available_copies >= 0", name="ck_library_inventory_available_nonnegative"),
        sa.CheckConstraint("reserved_copies >= 0", name="ck_library_inventory_reserved_nonnegative"),
        sa.ForeignKeyConstraint(["book_id"], ["library_books.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("book_id", name="uq_library_inventory_book"),
    )
    op.create_index("ix_library_inventory_book_id", "library_inventory", ["book_id"])

    op.create_table(
        "library_reservations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("action_request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("book_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("book_code", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("pickup_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["action_request_id"], ["campus_action_requests.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["book_id"], ["library_books.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("action_request_id", name="uq_library_reservations_action_request"),
    )
    op.create_index("ix_library_reservations_actor_user_id", "library_reservations", ["actor_user_id"])
    op.create_index("ix_library_reservations_book_id", "library_reservations", ["book_id"])

    op.create_table(
        "library_loans",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("book_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("borrowed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("returned_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["book_id"], ["library_books.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_library_loans_actor_user_id", "library_loans", ["actor_user_id"])
    op.create_index("ix_library_loans_book_id", "library_loans", ["book_id"])


def downgrade() -> None:
    op.drop_index("ix_library_loans_book_id", table_name="library_loans")
    op.drop_index("ix_library_loans_actor_user_id", table_name="library_loans")
    op.drop_table("library_loans")
    op.drop_index("ix_library_reservations_book_id", table_name="library_reservations")
    op.drop_index("ix_library_reservations_actor_user_id", table_name="library_reservations")
    op.drop_table("library_reservations")
    op.drop_index("ix_library_inventory_book_id", table_name="library_inventory")
    op.drop_table("library_inventory")
    op.drop_index("ix_library_books_subject", table_name="library_books")
    op.drop_index("ix_library_books_title", table_name="library_books")
    op.drop_index("ix_library_books_book_code", table_name="library_books")
    op.drop_table("library_books")
