"""CampusMind runtime DB role for enforceable PostgreSQL RLS.

Revision ID: 20260923_0008
Revises: 20260923_0007
"""

from alembic import op


revision = "20260923_0008"
down_revision = "20260923_0007"
branch_labels = None
depends_on = None


RUNTIME_ROLE = "campusmind_runtime"


def upgrade() -> None:
    # The Docker POSTGRES_USER login is intentionally retained as the
    # administrative/migration identity. PostgreSQL superusers bypass RLS even
    # when FORCE ROW LEVEL SECURITY is enabled, so normal ORM transactions must
    # SET ROLE to a non-superuser/non-BYPASSRLS runtime role.
    op.execute(
        r"""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_roles WHERE rolname = 'campusmind_runtime'
            ) THEN
                CREATE ROLE campusmind_runtime
                    NOLOGIN
                    NOSUPERUSER
                    NOCREATEDB
                    NOCREATEROLE
                    NOREPLICATION
                    NOBYPASSRLS;
            ELSE
                ALTER ROLE campusmind_runtime
                    NOLOGIN
                    NOSUPERUSER
                    NOCREATEDB
                    NOCREATEROLE
                    NOREPLICATION
                    NOBYPASSRLS;
            END IF;
        END
        $$
        """
    )

    # Allow the existing administrative login to SET ROLE without introducing a
    # second password/connection string.
    op.execute(
        r"""
        DO $$
        BEGIN
            EXECUTE format('GRANT campusmind_runtime TO %I', current_user);
        END
        $$
        """
    )

    op.execute("GRANT USAGE ON SCHEMA public TO campusmind_runtime")
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public "
        "TO campusmind_runtime"
    )
    op.execute(
        "GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public "
        "TO campusmind_runtime"
    )

    # RLS helper functions are deliberately explicit rather than granting every
    # function in the schema.
    op.execute("GRANT EXECUTE ON FUNCTION campusmind_acl_levels() TO campusmind_runtime")
    op.execute(
        "GRANT EXECUTE ON FUNCTION campusmind_normalize_permission_level(text) "
        "TO campusmind_runtime"
    )
    op.execute(
        "GRANT EXECUTE ON FUNCTION campusmind_prompt_injection_suspect(text) "
        "TO campusmind_runtime"
    )

    # Future application tables/sequences created by the administrative role are
    # automatically usable by the runtime role. Alembic itself still runs as the
    # administrative login and therefore keeps DDL ownership.
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO campusmind_runtime"
    )
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        "GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO campusmind_runtime"
    )


def downgrade() -> None:
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        "REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLES FROM campusmind_runtime"
    )
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        "REVOKE USAGE, SELECT, UPDATE ON SEQUENCES FROM campusmind_runtime"
    )
    op.execute(
        "REVOKE SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public "
        "FROM campusmind_runtime"
    )
    op.execute(
        "REVOKE USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public "
        "FROM campusmind_runtime"
    )
    op.execute("REVOKE USAGE ON SCHEMA public FROM campusmind_runtime")
    op.execute(
        r"""
        DO $$
        BEGIN
            EXECUTE format('REVOKE campusmind_runtime FROM %I', current_user);
        END
        $$
        """
    )
    op.execute("DROP ROLE IF EXISTS campusmind_runtime")
