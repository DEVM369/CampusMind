"""Reset a synthetic CampusMind user's password without exposing the secret.

This is an operator-only maintenance command. It deliberately accepts the
username as a positional value and reads the new password with ``getpass`` so
the password never appears in shell history, process arguments, or output.
"""

from __future__ import annotations

import argparse
import sys
import warnings
from datetime import UTC, datetime
from getpass import GetPassWarning, getpass

import httpx
from sqlalchemy import select, update
from sqlalchemy.exc import SQLAlchemyError

from campusmind.platform.auth import hash_password
from campusmind.platform.db import AuthSession, Role, User, UserRole, get_session_factory

SUPPORTED_USERNAMES = ("student001", "admin")
MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 256
EXPECTED_MIGRATION_HEAD = "20260926_0011"


class AccountNotFoundError(RuntimeError):
    """The selected account is absent from the configured database."""


class AccountProvisioningError(RuntimeError):
    """A guarded synthetic-account creation requirement was not met."""


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Reset a CampusMind synthetic user's password interactively."
    )
    parser.add_argument(
        "username",
        choices=SUPPORTED_USERNAMES,
        help="the synthetic account whose password should be reset",
    )
    parser.add_argument(
        "--verify-login",
        action="store_true",
        help="verify login and /auth/me against the local API on port 8000",
    )
    parser.add_argument(
        "--create-missing-in-test-db",
        metavar="DATABASE",
        help="create the selected missing synthetic login only in this named *_test database",
    )
    return parser.parse_args(argv)


def _validate_password(password: str) -> None:
    if not MIN_PASSWORD_LENGTH <= len(password) <= MAX_PASSWORD_LENGTH:
        raise ValueError("Password must contain between 12 and 256 characters.")


def _read_new_password(username: str) -> str:
    # getpass otherwise falls back to visible stdin on unsupported terminals.
    with warnings.catch_warnings():
        warnings.simplefilter("error", GetPassWarning)
        password = getpass(f"New password for {username} (12-256 characters): ")
        _validate_password(password)
        confirmation = getpass("Repeat the new password: ")
    if password != confirmation:
        raise ValueError("The two password entries do not match.")

    return password


def _check_creation_target(connection, expected_database: str) -> None:
    if not expected_database.endswith("_test"):
        raise AccountProvisioningError("Account creation requires a database name ending in _test.")
    if connection.dialect.name != "postgresql":
        raise AccountProvisioningError("Account creation requires PostgreSQL.")
    actual_database = connection.exec_driver_sql("SELECT current_database()").scalar_one()
    if actual_database != expected_database:
        raise AccountProvisioningError("The connected database does not match the named test database.")
    revisions = set(
        connection.exec_driver_sql("SELECT version_num FROM public.alembic_version").scalars()
    )
    if revisions != {EXPECTED_MIGRATION_HEAD}:
        raise AccountProvisioningError("The test database is not at migration head 20260926_0011.")


def reset_password(
    username: str,
    password: str,
    *,
    create_missing_in_test_db: str | None = None,
) -> int:
    """Reset an existing login, or explicitly provision one in a checked test DB."""

    if username not in SUPPORTED_USERNAMES:
        raise ValueError("Only student001 and admin are supported.")
    _validate_password(password)
    password_hash = hash_password(password)
    now = datetime.now(UTC)

    with get_session_factory().begin() as session:
        if create_missing_in_test_db is not None:
            _check_creation_target(session.connection(), create_missing_in_test_db)
        user = session.scalar(
            select(User)
            .where(User.username == username)
            .with_for_update()
        )
        if user is None:
            if create_missing_in_test_db is None:
                raise AccountNotFoundError(
                    "The selected account is absent from the configured database."
                )
            role_code = "student" if username == "student001" else "admin"
            role = session.scalar(select(Role).where(Role.code == role_code))
            if role is None:
                role = Role(code=role_code, name=role_code, description="Synthetic demo login role")
                session.add(role)
            user = User(
                username=username,
                full_name=f"CampusMind synthetic {role_code}",
                status="active",
                is_superuser=username == "admin",
                password_hash=password_hash,
            )
            session.add(user)
            session.flush()
            session.add(UserRole(user_id=user.id, role_id=role.id))
        elif create_missing_in_test_db is not None:
            raise AccountProvisioningError(
                "The account already exists. Run the ordinary reset command without the creation option."
            )

        user.password_hash = password_hash
        result = session.execute(
            update(AuthSession)
            .where(
                AuthSession.user_id == user.id,
                AuthSession.revoked_at.is_(None),
            )
            .values(revoked_at=now)
        )

    return int(result.rowcount or 0)


def verify_local_login(username: str, password: str) -> list[str]:
    expected_role = "student" if username == "student001" else "admin"
    with httpx.Client(
        base_url="http://127.0.0.1:8000",
        timeout=10,
        trust_env=False,
        follow_redirects=False,
    ) as client:
        logged_in = False
        try:
            response = client.post(
                "/api/v1/auth/login",
                json={"username": username, "password": password},
            )
            response.raise_for_status()
            logged_in = True
            login_user = response.json()["user"]
            response = client.get("/api/v1/auth/me")
            response.raise_for_status()
            user = response.json()
            if (
                login_user["user_id"] != user["user_id"]
                or login_user["username"] != username
                or user["username"] != username
                or user["status"] != "active"
                or expected_role not in user["roles"]
                or user["is_superuser"] != (username == "admin")
            ):
                raise RuntimeError("Local API returned an unexpected user or role.")
            return user["roles"]
        finally:
            if logged_in:
                client.post("/api/v1/auth/logout").raise_for_status()


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        password = _read_new_password(args.username)
    except (EOFError, KeyboardInterrupt):
        print("Password input cancelled.", file=sys.stderr)
        return 1
    except GetPassWarning:
        print("Hidden input is unavailable. Use an interactive terminal.", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    try:
        if args.create_missing_in_test_db is None:
            revoked_sessions = reset_password(args.username, password)
            print(
                f"Password reset for {args.username}; "
                f"revoked {revoked_sessions} old session(s)."
            )
        else:
            reset_password(
                args.username, password,
                create_missing_in_test_db=args.create_missing_in_test_db,
            )
            print(f"Created synthetic login {args.username} in the named test database.")
            if args.username == "student001":
                print("Student academic records have not been created or reassigned.")
        if args.verify_login:
            try:
                roles = verify_local_login(args.username, password)
            except (httpx.HTTPError, RuntimeError, ValueError, KeyError, TypeError):
                print(
                    "Password reset succeeded, but local HTTP verification failed. "
                    "Check the API and try browser login.",
                    file=sys.stderr,
                )
                return 1
            print(f"PASS: /auth/login and /auth/me; roles={','.join(roles)}; logged out.")
    except AccountNotFoundError:
        print(
            f"Account {args.username} was not found in the configured database. "
            "No password or sessions were changed. Check the database target "
            "and account provisioning before retrying; do not rerun seed blindly.",
            file=sys.stderr,
        )
        return 1
    except AccountProvisioningError as exc:
        print(f"Account creation stopped: {exc}", file=sys.stderr)
        return 1
    except (SQLAlchemyError, RuntimeError) as exc:
        # Do not echo driver messages: a connection error can contain a DSN
        # or other deployment detail. The operator can inspect server logs.
        print(
            f"Password reset failed ({type(exc).__name__}). "
            "Check the database configuration and try again.",
            file=sys.stderr,
        )
        return 1
    finally:
        # Drop the local reference as soon as the transaction has completed.
        password = ""

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
