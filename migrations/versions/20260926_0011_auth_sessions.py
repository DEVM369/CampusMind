"""CampusMind server-side authentication sessions.

Revision ID: 20260926_0011
Revises: 20260924_0010
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260926_0011"
down_revision = "20260924_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "auth_sessions",
        sa.Column(
            "id",
            postgresql.UUID(
                as_uuid=True
            ),
            primary_key=True,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(
                as_uuid=True
            ),
            nullable=False,
        ),
        sa.Column(
            "token_hash",
            sa.String(
                length=64
            ),
            nullable=False,
        ),
        sa.Column(
            "expires_at",
            sa.DateTime(
                timezone=True
            ),
            nullable=False,
        ),
        sa.Column(
            "revoked_at",
            sa.DateTime(
                timezone=True
            ),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(
                timezone=True
            ),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(
                timezone=True
            ),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "token_hash",
            name=(
                "uq_auth_sessions_token_hash"
            ),
        ),
    )

    op.create_index(
        "ix_auth_sessions_user_id",
        "auth_sessions",
        ["user_id"],
    )

    op.create_index(
        "ix_auth_sessions_token_hash",
        "auth_sessions",
        ["token_hash"],
        unique=True,
    )

    op.create_index(
        "ix_auth_sessions_expires_at",
        "auth_sessions",
        ["expires_at"],
    )

    op.create_index(
        "ix_auth_sessions_revoked_at",
        "auth_sessions",
        ["revoked_at"],
    )

    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE "
        "ON TABLE auth_sessions "
        "TO campusmind_runtime"
    )


def downgrade() -> None:
    op.drop_index(
        "ix_auth_sessions_revoked_at",
        table_name="auth_sessions",
    )

    op.drop_index(
        "ix_auth_sessions_expires_at",
        table_name="auth_sessions",
    )

    op.drop_index(
        "ix_auth_sessions_token_hash",
        table_name="auth_sessions",
    )

    op.drop_index(
        "ix_auth_sessions_user_id",
        table_name="auth_sessions",
    )

    op.drop_table(
        "auth_sessions"
    )
