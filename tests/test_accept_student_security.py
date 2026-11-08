import warnings
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from campusmind.main import create_app
from campusmind.platform.auth import hash_password
from campusmind.platform.db import (
    AuthSession,
    Base,
    College,
    Course,
    DocumentChunk,
    Major,
    Role,
    Student,
    StudentCourse,
    User,
    UserRole,
    get_db,
)
from scripts import accept_student_security as acceptance

PASSWORD = "synthetic-acceptance-password"


@pytest.fixture
def fixture_database():
    engine = create_engine("sqlite://", poolclass=StaticPool,
                           connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, record):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    password_hash = hash_password(PASSWORD)
    with Session(engine) as session, session.begin():
        users = [User(username=name, full_name=f"Synthetic {name}", status="active",
                      is_superuser=name == "admin", password_hash=password_hash)
                 for name in ("student001", "admin")]
        roles = [Role(code=code, name=code) for code in ("student", "admin")]
        session.add_all([*users, *roles])
        session.flush()
        identities = {user.username: user.id for user in users}
        session.add_all(UserRole(user_id=user.id, role_id=role.id)
                        for user, role in zip(users, roles, strict=True))
        session.add(AuthSession(user_id=users[0].id, token_hash="a" * 64,
                                expires_at=datetime.now(UTC) + timedelta(days=1)))
    yield engine, identities, password_hash
    engine.dispose()


def provision(engine, identities):
    with Session(engine) as session, session.begin():
        return acceptance.ensure_fixtures(session, identities, provision=True)


def count(session, model):
    return session.scalar(select(func.count()).select_from(model))


def test_provision_is_repeatable_and_preserves_credentials_and_sessions(fixture_database):
    engine, identities, password_hash = fixture_database
    assert provision(engine, identities) == acceptance.fixture_id("student")
    assert provision(engine, identities) == acceptance.fixture_id("student")
    with Session(engine) as session:
        assert count(session, Student) == 2
        assert count(session, Course) == 2
        assert count(session, StudentCourse) == 2
        assert count(session, DocumentChunk) == 5
        assert session.get(User, identities["student001"]).password_hash == password_hash
        assert session.get(User, identities["admin"]).password_hash == password_hash
        assert session.scalar(select(AuthSession)).revoked_at is None
        peer = session.get(User, acceptance.fixture_id("peer-user"))
        assert peer.password_hash is None and peer.status == "inactive" and not peer.is_superuser
    acceptance.check_student_repository(engine, identities)


def test_fixture_setup_refuses_sqlite_without_creating_academic_records(fixture_database):
    engine, _, _ = fixture_database
    with pytest.raises(acceptance.AcceptanceError, match="PostgreSQL"):
        acceptance.setup_database(engine, "campusmind_p0_test", provision=True)
    with Session(engine) as session:
        assert count(session, College) == 0
        assert count(session, Student) == 0


def test_missing_fixture_requires_explicit_provision_option(fixture_database):
    engine, identities, _ = fixture_database
    with Session(engine) as session, session.begin(), pytest.raises(acceptance.AcceptanceError, match="missing"):
        acceptance.ensure_fixtures(session, identities, provision=False)
    with Session(engine) as session:
        assert count(session, College) == 0


@pytest.mark.parametrize("foreign_owner", [True, False])
def test_existing_profile_is_never_reassigned_and_partial_setup_rolls_back(fixture_database, foreign_owner):
    engine, identities, _ = fixture_database
    with Session(engine) as session, session.begin():
        college = College(code="EXISTING", name="Existing college")
        session.add(college)
        session.flush()
        major = Major(code="EXISTING", name="Existing major", college_id=college.id)
        session.add(major)
        session.flush()
        owner = identities["admin"] if foreign_owner else identities["student001"]
        profile = Student(student_no=acceptance.STUDENT_NO if foreign_owner else "EXISTING-001",
                          user_id=owner, major_id=major.id, enrollment_year=2024)
        session.add(profile)
        session.flush()
        profile_id = profile.id
    with pytest.raises(acceptance.AcceptanceError):
        provision(engine, identities)
    with Session(engine) as session:
        assert count(session, College) == 1
        assert count(session, Major) == 1
        assert count(session, Student) == 1
        assert count(session, Course) == 0
        assert session.get(Student, profile_id).user_id == owner


def test_reserved_code_collision_is_not_adopted(fixture_database):
    engine, identities, _ = fixture_database
    with Session(engine) as session, session.begin():
        session.add(College(code="CM-ACCEPT-COLLEGE", name="Someone else's college"))
    with pytest.raises(acceptance.AcceptanceError, match="conflicts"):
        provision(engine, identities)
    with Session(engine) as session:
        assert count(session, Student) == 0
        assert count(session, Course) == 0


def test_unexpected_course_record_stops_fixture_reuse(fixture_database):
    engine, identities, _ = fixture_database
    provision(engine, identities)
    with Session(engine) as session, session.begin():
        session.add(StudentCourse(student_id=acceptance.fixture_id("student"),
                                  course_id=acceptance.fixture_id("math"), semester="other",
                                  status="completed", score=75, credits_earned=3))
    with pytest.raises(acceptance.AcceptanceError, match="unexpected course"):
        provision(engine, identities)
    with Session(engine) as session:
        assert count(session, StudentCourse) == 3


@pytest.mark.parametrize("database,dialect,actual,revisions,provider", [
    ("campusmind", "postgresql", "campusmind", {"20260926_0011"}, "deterministic"),
    ("campusmind_p0_test", "sqlite", "campusmind_p0_test", {"20260926_0011"}, "deterministic"),
    ("campusmind_p0_test", "postgresql", "other_test", {"20260926_0011"}, "deterministic"),
    ("campusmind_p0_test", "postgresql", "campusmind_p0_test", {"20260924_0010"}, "deterministic"),
    ("campusmind_p0_test", "postgresql", "campusmind_p0_test", {"20260926_0011"}, "auto"),
])
def test_target_guard_fails_closed(monkeypatch, database, dialect, actual, revisions, provider):
    connection = Mock(dialect=SimpleNamespace(name=dialect))

    def execute(sql):
        return Mock(scalar_one=lambda: actual, scalars=lambda: revisions)

    connection.exec_driver_sql.side_effect = execute
    monkeypatch.setattr(acceptance, "get_settings", lambda: SimpleNamespace(rag_embedding_provider=provider))
    with pytest.raises(acceptance.AcceptanceError):
        acceptance.check_target(connection, database)


def test_hidden_password_input_rejects_visible_fallback(monkeypatch):
    def unsupported(prompt):
        warnings.warn("No hidden terminal", acceptance.GetPassWarning)
        pytest.fail("Visible fallback must never run")

    monkeypatch.setattr(acceptance, "getpass", unsupported)
    with pytest.raises(acceptance.GetPassWarning):
        acceptance.verify_login(Mock(), "student001", uuid4())


@pytest.mark.parametrize("bad_evidence", [None, "missing_public", "peer", "quarantine"])
def test_http_checks_use_real_identity_and_document_authorization(fixture_database, monkeypatch, bad_evidence):
    engine, identities, _ = fixture_database
    provision(engine, identities)
    app = create_app()

    def database():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = database
    monkeypatch.setattr(acceptance, "getpass", lambda _: PASSWORD)
    from campusmind.knowledge.rag import HybridRetrievalService, RetrievalResult, RetrievedChunk

    def local_public_search(self, query, top_k):
        # SQLite does not enforce PostgreSQL RLS. This adapter only tests the HTTP checker.
        item = RetrievedChunk(chunk_id=acceptance.fixture_id("chunk-public"),
                              document_id=acceptance.fixture_id("doc-public"),
                              document_version_id=acceptance.fixture_id("version-public"),
                              knowledge_base_id=acceptance.fixture_id("knowledge-base"),
                              content="CMACCEPTPUBLIC synthetic public evidence.",
                              title="Synthetic public", object_key="synthetic.txt", rerank_score=1)
        hits = [item]
        if bad_evidence == "missing_public":
            hits = []
        elif bad_evidence is not None:
            from dataclasses import replace

            hits.append(replace(item, chunk_id=acceptance.fixture_id(f"chunk-{bad_evidence}")))
        return RetrievalResult(original_query=query, rewritten_query=query, hits=hits,
                               vector_count=0, keyword_count=1, elapsed_ms=0)

    monkeypatch.setattr(HybridRetrievalService, "search", local_public_search)
    with TestClient(app) as student, TestClient(app) as anonymous, TestClient(app) as admin:
        sessions = [student, admin]
        acceptance.verify_login(student, "student001", identities["student001"])
        acceptance.verify_login(admin, "admin", identities["admin"])
        if bad_evidence is None:
            acceptance.check_http(student, anonymous, identities)
        else:
            with pytest.raises(acceptance.AcceptanceError, match="public positive control or exposed"):
                acceptance.check_http(student, anonymous, identities)
        for http in (student, admin):
            acceptance.logout_session(http, sessions)
        assert not sessions
        assert student.get("/api/v1/auth/me").status_code == 401
    with Session(engine) as session:
        original = session.scalar(select(AuthSession).where(AuthSession.token_hash == "a" * 64))
        assert original.revoked_at is None


def test_login_failure_does_not_echo_password_or_response(monkeypatch, capsys):
    monkeypatch.setattr(acceptance, "getpass", lambda _: "password-sentinel")
    transport = httpx.MockTransport(lambda request: httpx.Response(401, text="private-response-sentinel"))
    with (
        httpx.Client(transport=transport, base_url=acceptance.BASE_URL) as http,
        pytest.raises(acceptance.AcceptanceError) as failure,
    ):
        acceptance.verify_login(http, "student001", uuid4())
    assert "sentinel" not in str(failure.value)
    assert "sentinel" not in str(capsys.readouterr())


def test_failed_logout_is_not_reported_as_success():
    transport = httpx.MockTransport(lambda request: httpx.Response(503))
    with httpx.Client(transport=transport, base_url=acceptance.BASE_URL) as http:
        sessions = [http]
        acceptance.logout_session(http, sessions)
        assert sessions == [http]
