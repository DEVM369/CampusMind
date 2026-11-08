from __future__ import annotations

import warnings
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from campusmind.platform.auth import hash_password, verify_password
from campusmind.platform.db import AuthSession, Base, Role, User, UserRole
from scripts import reset_demo_passwords


def test_read_new_password_uses_two_hidden_prompts(monkeypatch):
    prompts: list[str] = []
    values = iter(("a-secure-demo-password", "a-secure-demo-password"))

    def fake_getpass(prompt: str) -> str:
        prompts.append(prompt)
        return next(values)

    monkeypatch.setattr(reset_demo_passwords, "getpass", fake_getpass)

    assert reset_demo_passwords._read_new_password("student001") == "a-secure-demo-password"
    assert len(prompts) == 2
    assert all("password" in prompt.lower() for prompt in prompts)


@pytest.mark.parametrize("password", ["short", "x" * 257])
def test_invalid_length_never_opens_database(monkeypatch, capsys, password):
    monkeypatch.setattr(reset_demo_passwords, "getpass", lambda _: password)
    monkeypatch.setattr(
        reset_demo_passwords,
        "get_session_factory",
        lambda: pytest.fail("Invalid password must not open the database"),
    )
    assert reset_demo_passwords.main(["student001"]) == 2
    assert password not in capsys.readouterr().err


def test_mismatch_never_changes_password(monkeypatch):
    values = iter(("a-secure-demo-password", "a-different-password"))
    monkeypatch.setattr(reset_demo_passwords, "getpass", lambda _: next(values))
    with pytest.raises(ValueError, match="do not match"):
        reset_demo_passwords._read_new_password("student001")


def test_getpass_visible_fallback_is_blocked(monkeypatch, capsys):
    def unsupported_terminal(_):
        warnings.warn("Cannot disable echo", reset_demo_passwords.GetPassWarning)
        pytest.fail("Visible input fallback must never run")

    monkeypatch.setattr(reset_demo_passwords, "getpass", unsupported_terminal)
    assert reset_demo_passwords.main(["student001"]) == 2
    assert "Hidden input is unavailable" in capsys.readouterr().err


@pytest.mark.parametrize("username", ["student001", "admin"])
def test_reset_password_updates_hash_and_revokes_active_sessions(monkeypatch, username):
    user_id = uuid4()
    engine = create_engine(
        "sqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine, tables=[User.__table__, AuthSession.__table__])
    now = datetime.now(UTC)
    with Session(engine) as db:
        user = User(
            id=user_id,
            username=username,
            full_name="Student",
            password_hash=hash_password("old-password"),
        )
        other_user = User(username="other", full_name="Other")
        db.add_all([user, other_user])
        db.flush()
        other_user_id = other_user.id
        db.add_all(
            [
                AuthSession(
                    user_id=user_id,
                    token_hash="a" * 64,
                    expires_at=now + timedelta(days=1),
                ),
                AuthSession(
                    user_id=user_id,
                    token_hash="b" * 64,
                    expires_at=now - timedelta(days=1),
                ),
                AuthSession(
                    user_id=other_user.id,
                    token_hash="c" * 64,
                    expires_at=now + timedelta(days=1),
                ),
            ]
        )
        db.commit()

    monkeypatch.setattr(
        reset_demo_passwords,
        "get_session_factory",
        lambda: sessionmaker(bind=engine, expire_on_commit=False),
    )

    revoked = reset_demo_passwords.reset_password(username, "a-secure-demo-password")

    assert revoked == 2
    with Session(engine) as db:
        updated_user = db.scalar(select(User).where(User.username == username))
        sessions = db.scalars(
            select(AuthSession).where(AuthSession.user_id == user_id)
        ).all()
        other_session = db.scalar(
            select(AuthSession).where(AuthSession.user_id == other_user_id)
        )
    assert updated_user is not None
    assert verify_password("a-secure-demo-password", updated_user.password_hash)
    assert not verify_password("old-password", updated_user.password_hash)
    assert len(sessions) == 2
    assert all(row.revoked_at is not None for row in sessions)
    assert other_session.revoked_at is None
    engine.dispose()


def test_failed_password_update_rolls_back_session_revocation(monkeypatch):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=[User.__table__, AuthSession.__table__])
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    old_hash = hash_password("old-password")
    with factory.begin() as db:
        user = User(username="student001", full_name="Student", password_hash=old_hash)
        db.add(user)
        db.flush()
        db.add(AuthSession(user_id=user.id, token_hash="d" * 64,
                           expires_at=datetime.now(UTC) + timedelta(days=1)))
    monkeypatch.setattr(reset_demo_passwords, "get_session_factory", lambda: factory)

    def fail_update(_connection, _cursor, statement, *_):
        if statement.startswith("UPDATE users"):
            raise SQLAlchemyError("injected failure after session revocation")

    event.listen(engine, "before_cursor_execute", fail_update)
    with pytest.raises(SQLAlchemyError):
        reset_demo_passwords.reset_password("student001", "a-secure-demo-password")
    with factory() as db:
        assert db.scalar(select(User.password_hash)) == old_hash
        assert db.scalar(select(AuthSession.revoked_at)) is None
    engine.dispose()


def test_database_error_is_redacted(monkeypatch, capsys):
    password = "a-secure-demo-password"
    monkeypatch.setattr(reset_demo_passwords, "getpass", lambda _: password)

    def fail_reset(*_):
        raise RuntimeError(f"sensitive-dsn:{password}")

    monkeypatch.setattr(reset_demo_passwords, "reset_password", fail_reset)
    assert reset_demo_passwords.main(["admin"]) == 1
    output = capsys.readouterr()
    assert password not in output.out + output.err
    assert "sensitive-dsn" not in output.out + output.err


@pytest.mark.parametrize("username", ["student001", "admin"])
def test_missing_account_is_reported_without_changing_other_users(monkeypatch, capsys, username):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=[User.__table__, AuthSession.__table__])
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    old_hash = hash_password("unchanged-password")
    with factory.begin() as db:
        other = User(username="other", full_name="Other", password_hash=old_hash)
        db.add(other)
        db.flush()
        db.add(AuthSession(user_id=other.id, token_hash="e" * 64,
                           expires_at=datetime.now(UTC) + timedelta(days=1)))
    monkeypatch.setattr(reset_demo_passwords, "get_session_factory", lambda: factory)
    monkeypatch.setattr(reset_demo_passwords, "getpass", lambda _: "a-secure-demo-password")
    assert reset_demo_passwords.main([username]) == 1
    output = capsys.readouterr()
    assert f"Account {username} was not found" in output.err
    assert "No password or sessions were changed" in output.err
    assert "a-secure-demo-password" not in output.out + output.err
    with factory() as db:
        assert db.scalar(select(User.password_hash)) == old_hash
        assert db.scalar(select(AuthSession.revoked_at)) is None
        assert len(db.scalars(select(User)).all()) == 1
    engine.dispose()


@pytest.fixture
def account_factory(monkeypatch):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(
        engine, tables=[User.__table__, Role.__table__, UserRole.__table__, AuthSession.__table__],
    )
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(reset_demo_passwords, "get_session_factory", lambda: factory)
    yield factory
    engine.dispose()


def target_connection(database="campusmind_test", revisions=("20260926_0011",), dialect="postgresql"):
    connection = Mock()
    connection.dialect.name = dialect
    connection.exec_driver_sql.side_effect = [
        Mock(scalar_one=lambda: database), Mock(scalars=lambda: iter(revisions)),
    ]
    return connection


@pytest.mark.parametrize(
    ("expected", "actual", "revisions", "dialect", "message"),
    [
        ("campusmind", "campusmind", ("20260926_0011",), "postgresql", "ending in _test"),
        ("campusmind_test", "campusmind", ("20260926_0011",), "postgresql", "does not match"),
        ("campusmind_test", "campusmind_test", ("20260924_0010",), "postgresql", "migration head"),
        ("campusmind_test", "campusmind_test", (), "postgresql", "migration head"),
        ("campusmind_test", "campusmind_test", ("20260926_0011",), "sqlite", "PostgreSQL"),
    ],
)
def test_account_creation_rejects_unsafe_targets(expected, actual, revisions, dialect, message):
    connection = target_connection(actual, revisions, dialect)
    with pytest.raises(reset_demo_passwords.AccountProvisioningError, match=message):
        reset_demo_passwords._check_creation_target(connection, expected)


def test_account_creation_target_checks_actual_database_and_migration():
    connection = target_connection()
    reset_demo_passwords._check_creation_target(connection, "campusmind_test")
    assert [call.args[0] for call in connection.exec_driver_sql.call_args_list] == [
        "SELECT current_database()", "SELECT version_num FROM public.alembic_version",
    ]


@pytest.mark.parametrize("username,role_code", [("student001", "student"), ("admin", "admin")])
@pytest.mark.parametrize("role_exists", [False, True])
def test_create_missing_login_preserves_existing_accounts(
    account_factory, monkeypatch, username, role_code, role_exists,
):
    factory = account_factory
    old_hash = hash_password("unchanged-password")
    with factory.begin() as db:
        other = User(username="other", full_name="Other", password_hash=old_hash)
        db.add(other)
        db.flush()
        db.add(AuthSession(user_id=other.id, token_hash="f" * 64,
                           expires_at=datetime.now(UTC) + timedelta(days=1)))
        if role_exists:
            db.add(Role(code=role_code, name="Existing role"))
    # SQLite exercises real ORM writes and rollback; PostgreSQL target checks
    # are exercised independently above, without claiming a live PG result.
    guard = Mock()
    monkeypatch.setattr(reset_demo_passwords, "_check_creation_target", guard)
    assert reset_demo_passwords.reset_password(
        username, "new-demo-password", create_missing_in_test_db="campusmind_test",
    ) == 0
    guard.assert_called_once()
    assert guard.call_args.args[1] == "campusmind_test"
    with factory() as db:
        user = db.scalar(select(User).where(User.username == username))
        assert user.status == "active"
        assert user.is_superuser is (username == "admin")
        assert verify_password("new-demo-password", user.password_hash)
        assigned_role = db.scalar(
            select(Role).join(UserRole, UserRole.role_id == Role.id)
            .where(UserRole.user_id == user.id)
        )
        assert assigned_role.code == role_code
        if role_exists:
            assert assigned_role.name == "Existing role"
        assert len(db.scalars(select(Role)).all()) == 1
        assert db.scalar(select(User.password_hash).where(User.username == "other")) == old_hash
        assert db.scalar(select(AuthSession.revoked_at)) is None


def test_creation_mode_never_resets_or_promotes_an_existing_account(account_factory, monkeypatch):
    factory = account_factory
    old_hash = hash_password("unchanged-password")
    with factory.begin() as db:
        db.add(User(username="admin", full_name="Existing", password_hash=old_hash,
                    is_superuser=False))
    monkeypatch.setattr(reset_demo_passwords, "_check_creation_target", Mock())
    with pytest.raises(reset_demo_passwords.AccountProvisioningError, match="already exists"):
        reset_demo_passwords.reset_password(
            "admin", "new-demo-password", create_missing_in_test_db="campusmind_test",
        )
    with factory() as db:
        user = db.scalar(select(User))
        assert user.password_hash == old_hash
        assert not user.is_superuser
        assert not db.scalars(select(UserRole)).all()


def test_creation_cli_sets_password_and_verifies_without_printing_secret(
    account_factory, monkeypatch, capsys,
):
    password = "twelve-chars"
    monkeypatch.setattr(reset_demo_passwords, "getpass", lambda _: password)
    monkeypatch.setattr(reset_demo_passwords, "_check_creation_target", Mock())
    verify = Mock(return_value=["student"])
    monkeypatch.setattr(reset_demo_passwords, "verify_local_login", verify)
    assert reset_demo_passwords.main([
        "student001", "--create-missing-in-test-db", "campusmind_test", "--verify-login",
    ]) == 0
    verify.assert_called_once_with("student001", password)
    output = capsys.readouterr()
    assert "Created synthetic login student001" in output.out
    assert "roles=student" in output.out
    assert password not in output.out + output.err
    with account_factory() as db:
        assert verify_password(password, db.scalar(select(User.password_hash)))


def test_creation_guard_failure_prevents_all_writes(account_factory, monkeypatch):
    guard = Mock(side_effect=reset_demo_passwords.AccountProvisioningError("target mismatch"))
    monkeypatch.setattr(reset_demo_passwords, "_check_creation_target", guard)
    with pytest.raises(reset_demo_passwords.AccountProvisioningError, match="target mismatch"):
        reset_demo_passwords.reset_password(
            "student001", "new-demo-password", create_missing_in_test_db="campusmind_test",
        )
    with account_factory() as db:
        assert not db.scalars(select(User)).all()
        assert not db.scalars(select(Role)).all()


def test_failed_role_assignment_rolls_back_new_login_and_role(account_factory, monkeypatch):
    monkeypatch.setattr(reset_demo_passwords, "_check_creation_target", Mock())

    def fail_role(_connection, _cursor, statement, *_):
        if statement.startswith("INSERT INTO user_roles"):
            raise SQLAlchemyError("injected failure")

    event.listen(account_factory.kw["bind"], "before_cursor_execute", fail_role)
    with pytest.raises(SQLAlchemyError):
        reset_demo_passwords.reset_password(
            "student001", "new-demo-password", create_missing_in_test_db="campusmind_test",
        )
    with account_factory() as db:
        assert not db.scalars(select(User)).all()
        assert not db.scalars(select(Role)).all()


@pytest.mark.parametrize("correct_role", [True, False])
def test_local_http_verification_checks_identity_and_logs_out(monkeypatch, correct_role):
    paths = []
    client_type = httpx.Client
    user = {
        "user_id": str(uuid4()), "username": "student001", "status": "active",
        "roles": ["student" if correct_role else "teacher"], "is_superuser": False,
    }

    def handle(request):
        paths.append(request.url.path)
        assert request.url.host == "127.0.0.1"
        if request.url.path.endswith("/login"):
            return httpx.Response(
                200, json={"user": user},
                headers={"set-cookie": "campusmind_session=offline-test; Path=/"},
            )
        assert "campusmind_session=offline-test" in request.headers["cookie"]
        return httpx.Response(200, json=user)

    monkeypatch.setattr(
        reset_demo_passwords.httpx, "Client",
        lambda **kwargs: client_type(transport=httpx.MockTransport(handle), **kwargs),
    )
    if correct_role:
        assert reset_demo_passwords.verify_local_login("student001", "test-password") == ["student"]
    else:
        with pytest.raises(RuntimeError, match="unexpected user or role"):
            reset_demo_passwords.verify_local_login("student001", "test-password")
    assert paths == ["/api/v1/auth/login", "/api/v1/auth/me", "/api/v1/auth/logout"]
