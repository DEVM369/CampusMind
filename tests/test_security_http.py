"""HTTP security tests with real sessions, SQL RBAC, and isolated SQL storage.

Only the database provider is replaced. No configured database is initialized.
"""
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from campusmind.main import create_app
from campusmind.platform.auth import hash_password, session_token_hash
from campusmind.platform.db import (
    AgentRun,
    AuthSession,
    Base,
    Conversation,
    Document,
    DocumentChunk,
    DocumentPermission,
    DocumentVersion,
    EvaluationCase,
    EvaluationDataset,
    KnowledgeBase,
    Permission,
    Role,
    RolePermission,
    User,
    UserRole,
    get_db,
)
from campusmind.tools.actions import (
    action_requests,
    classroom_reservations,
    library_books,
    library_inventory,
    library_metadata,
    library_reservations,
)
from campusmind.tools.actions import (
    metadata as action_metadata,
)


@pytest.fixture
def security_app():
    engine = create_engine("sqlite://", poolclass=StaticPool,
                           connect_args={"check_same_thread": False})
    # The real Agent initializes course/student tools during route selection.
    # Install only in this new, process-local SQLite database.
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        # Existing schedule table is defined only in migration 0005, outside ORM metadata.
        connection.exec_driver_sql(
            "CREATE TABLE course_schedules (id CHAR(32) PRIMARY KEY, course_id CHAR(32) NOT NULL, "
            "academic_year VARCHAR(20) NOT NULL, semester VARCHAR(40) NOT NULL, "
            "weekday SMALLINT NOT NULL, start_time TIME NOT NULL, end_time TIME NOT NULL, "
            "classroom VARCHAR(120) NOT NULL, campus VARCHAR(120), "
            "created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL)"
        )
    action_metadata.create_all(engine)
    library_metadata.create_all(engine)
    with Session(engine) as db:
        role = Role(code="student", name="Student")
        users = [User(username=name, full_name=name, status="active",
                      password_hash=hash_password("test-password-123"))
                 for name in ("alice", "bob")]
        db.add_all([role, *users])
        db.flush()
        ids = [u.id for u in users]
        db.add_all([UserRole(user_id=u.id, role_id=role.id) for u in users])
        db.commit()
    app = create_app()

    def database():
        with Session(engine, expire_on_commit=False) as db:
            yield db

    app.dependency_overrides[get_db] = database
    with TestClient(app) as client:
        yield client, engine, ids
    engine.dispose()


def login(client, username="alice"):
    response = client.post("/api/v1/auth/login", json={
        "username": username, "password": "test-password-123",
    })
    assert response.status_code == 200, response.text


@pytest.mark.parametrize("method,path,body", [
    ("post", "/agent/chat", {"query": "hello"}),
    ("post", "/agent/resume", {}),
    ("post", "/tools/student/query", {}),
    ("post", "/tools/classroom/prepare", {}),
    ("get", "/tools/classroom/reservations", None),
    ("post", "/documents/upload", {}),
    ("get", f"/documents/{uuid4()}", None),
    ("get", f"/documents/{uuid4()}/chunks", None),
    ("get", f"/documents/{uuid4()}/download-url", None),
    ("post", f"/graph/ingest/documents/{uuid4()}", {}),
    ("post", "/graph/bootstrap", {}),
    ("post", "/multi-agent/chat", {"query": "hello"}),
    ("post", "/adaptive-rag/chat", {"query": "hello"}),
    ("post", "/chat", {"query": "hello"}),
    ("get", "/admin/dashboard", None),
    ("get", "/conversations", None),
])
def test_sec01_anonymous(security_app, method, path, body):
    client, _, _ = security_app
    response = client.request(method, "/api/v1" + path, json=body)
    assert response.status_code == 401, response.text


@pytest.mark.parametrize("path", ["/agent/chat", "/adaptive-rag/chat", "/chat",
                                  "/multi-agent/chat", "/tools/classroom/prepare"])
def test_sec02_forged_actor(security_app, path):
    client, _, ids = security_app
    login(client)
    response = client.post("/api/v1" + path,
                           json={"query": "hello", "actor_user_id": str(ids[1])})
    assert response.status_code == 403, response.text


def test_sec03_and_auth01_conversation_ownership(security_app):
    client, engine, ids = security_app
    login(client)
    response = client.post("/api/v1/conversations", json={"title": "private"})
    assert response.status_code == 201, response.text
    conversation_id = response.json()["id"]
    assert client.get(f"/api/v1/conversations/{conversation_id}").status_code == 200
    with Session(engine) as db:
        assert db.scalar(select(Conversation.user_id)) == ids[0]
    login(client, "bob")
    assert client.get(f"/api/v1/conversations/{conversation_id}").status_code == 404
    assert client.delete(f"/api/v1/conversations/{conversation_id}").status_code == 404


def test_sec05_graph_requires_management_permission(security_app):
    client, _, _ = security_app
    login(client)
    for path in ("/graph/bootstrap", "/graph/entities",
                 f"/graph/ingest/documents/{uuid4()}"):
        assert client.post("/api/v1" + path, json={}).status_code == 403


def test_session_expiry_revocation_and_disabled_user(security_app):
    client, engine, ids = security_app
    login(client)
    token = client.cookies.get("campusmind_session")
    with Session(engine) as db:
        row = db.scalar(select(AuthSession).where(
            AuthSession.token_hash == session_token_hash(token)))
        row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()
    assert client.get("/api/v1/conversations").status_code == 401

    login(client)
    assert client.post("/api/v1/auth/logout").status_code == 200
    assert client.get("/api/v1/conversations").status_code == 401
    login(client)
    with Session(engine) as db:
        db.get(User, ids[0]).status = "disabled"
        db.commit()
    assert client.get("/api/v1/conversations").status_code == 401


def test_password_recovery_invalidates_old_cookie_and_allows_new_login(security_app, monkeypatch):
    from sqlalchemy.orm import sessionmaker

    from scripts import reset_demo_passwords

    client, engine, ids = security_app
    with Session(engine) as db:
        db.get(User, ids[0]).username = "student001"
        db.commit()
    login(client, "student001")
    assert client.get("/api/v1/auth/me").status_code == 200
    monkeypatch.setattr(
        reset_demo_passwords, "get_session_factory",
        lambda: sessionmaker(bind=engine, expire_on_commit=False),
    )
    assert reset_demo_passwords.reset_password("student001", "new-test-password-123") == 1
    assert client.get("/api/v1/auth/me").status_code == 401
    assert client.post("/api/v1/auth/login", json={
        "username": "student001", "password": "test-password-123",
    }).status_code == 401
    assert client.post("/api/v1/auth/login", json={
        "username": "student001", "password": "new-test-password-123",
    }).status_code == 200
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 200
    assert response.json()["username"] == "student001"
    assert response.json()["roles"] == ["student"]


@pytest.mark.parametrize("username,role", [("student001", "student"), ("admin", "admin")])
def test_provisioned_demo_login_has_expected_http_identity(security_app, monkeypatch, username, role):
    from sqlalchemy.orm import sessionmaker

    from scripts import reset_demo_passwords

    client, engine, _ = security_app
    monkeypatch.setattr(
        reset_demo_passwords, "get_session_factory",
        lambda: sessionmaker(bind=engine, autoflush=False, expire_on_commit=False),
    )
    monkeypatch.setattr(reset_demo_passwords, "_check_creation_target", lambda *_: None)
    reset_demo_passwords.reset_password(
        username, "new-demo-password", create_missing_in_test_db="campusmind_test",
    )
    response = client.post("/api/v1/auth/login", json={
        "username": username, "password": "new-demo-password",
    })
    assert response.status_code == 200
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 200
    assert response.json()["username"] == username
    assert response.json()["roles"] == [role]
    assert response.json()["is_superuser"] is (username == "admin")


def seed_document(engine, owner, *, security=True, level="personal", grant=None):
    with Session(engine) as db:
        kb = KnowledgeBase(code="kb-" + uuid4().hex, name="Test knowledge", domain="test")
        db.add(kb)
        db.flush()
        document = Document(knowledge_base_id=kb.id, title="Private document",
                            object_key="documents/" + uuid4().hex,
                            mime_type="text/plain", document_type="test", status="parsed")
        db.add(document)
        db.flush()
        manifest = {"security": {"permission_level": level, "owner_user_id": str(owner)}}
        version = DocumentVersion(document_id=document.id, version="1", status="active",
                                  object_key=document.object_key,
                                  metadata_json=manifest if security else {})
        db.add(version)
        db.flush()
        db.add(DocumentChunk(document_id=document.id, document_version_id=version.id,
                             knowledge_base_id=kb.id, chunk_index=0, content="Private evidence",
                             permission_level=level, metadata_json={"owner_user_id": str(owner)}))
        if grant:
            db.add(DocumentPermission(document_id=document.id, subject_type="user",
                                      subject_id=grant, permission_level="read"))
        db.commit()
        return document.id


def test_sec04_document_ownership_and_real_signing(security_app, monkeypatch):
    from campusmind.api.routes import documents
    from campusmind.config import Settings

    client, engine, ids = security_app
    document_id = seed_document(engine, ids[0])
    settings = Settings(_env_file=None, rustfs_endpoint="http://storage.test:9000",
                        rustfs_access_key="offline-test", rustfs_secret_key="offline-test-secret")
    monkeypatch.setattr(documents, "get_settings", lambda: settings)
    login(client)
    for suffix in ("", "/chunks", "/download-url"):
        response = client.get(f"/api/v1/documents/{document_id}{suffix}")
        assert response.status_code == 200, response.text
        if suffix == "/download-url":
            assert "X-Amz-Signature=" in response.json()["url"]
    login(client, "bob")
    for suffix in ("", "/chunks", "/download-url"):
        response = client.get(f"/api/v1/documents/{document_id}{suffix}")
        assert response.status_code == 403, response.text
        assert "url" not in response.json()


def test_legacy_document_requires_explicit_grant(security_app):
    client, engine, ids = security_app
    unclassified = seed_document(engine, ids[0], security=False, level="campus")
    granted = seed_document(engine, ids[0], security=False, level="campus", grant=ids[0])
    login(client)
    assert client.get(f"/api/v1/documents/{unclassified}").status_code == 403
    assert client.get(f"/api/v1/documents/{granted}").status_code == 200
    login(client, "bob")
    assert client.get(f"/api/v1/documents/{granted}").status_code == 403


def test_upload_denied_before_storage_or_ingestion(security_app):
    client, engine, _ = security_app
    login(client)
    response = client.post("/api/v1/documents/upload",
                           files={"file": ("test.txt", b"content", "text/plain")},
                           data={"knowledge_base_code": "test", "document_type": "test"})
    assert response.status_code == 403, response.text
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(Document)) == 0


def prepare_classroom(client, actor, **extra):
    response = client.post("/api/v1/tools/classroom/prepare", json={
        "query": "\u5e2e\u6211\u9884\u7ea62099-12-31\u4e0b\u534830\u4eba\u7684\u6559\u5ba4",
        "actor_user_id": str(actor), **extra,
    })
    assert response.status_code == 200, response.text
    return response.json()["approval_id"]


def test_sec06_foreign_approval_cannot_resume_through_either_route(security_app):
    client, engine, ids = security_app
    login(client, "bob")
    approval = prepare_classroom(client, ids[1])
    login(client)
    for path in ("/tools/classroom/resume", "/agent/resume"):
        response = client.post("/api/v1" + path, json={
            "approval_id": approval, "actor_user_id": str(ids[0]), "approved": True,
        })
        assert response.status_code == 403, response.text
    with Session(engine) as db:
        assert db.scalar(select(action_requests.c.status)) == "awaiting_approval"
        assert db.scalar(select(func.count()).select_from(classroom_reservations)) == 0


def test_sec07_reservations_cannot_be_read_as_another_user(security_app):
    client, _, ids = security_app
    login(client)
    for domain in ("classroom", "library"):
        response = client.get(f"/api/v1/tools/{domain}/reservations",
                              params={"actor_user_id": str(ids[1])})
        assert response.status_code == 403, response.text
        response = client.get(f"/api/v1/tools/{domain}/reservations",
                              params={"actor_user_id": str(ids[0])})
        assert response.status_code == 200, response.text


def test_hitl01_rejection_and_later_confirmation_never_reserve(security_app):
    client, engine, ids = security_app
    login(client)
    approval = prepare_classroom(client, ids[0])
    for approved in (False, False, True):
        response = client.post("/api/v1/tools/classroom/resume", json={
            "approval_id": approval, "actor_user_id": str(ids[0]), "approved": approved,
        })
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "rejected"
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(classroom_reservations)) == 0
        assert db.scalar(select(action_requests.c.status)) == "rejected"


def seed_library(engine):
    now = datetime.now(timezone.utc)
    book_id = uuid4()
    with engine.begin() as connection:
        connection.execute(library_books.insert().values(
            id=book_id, book_code="TEST-01", title="Graph Representation Learning",
            author="Test Author", subject="Graphs", location="Test shelf",
            created_at=now, updated_at=now))
        connection.execute(library_inventory.insert().values(
            id=uuid4(), book_id=book_id, total_copies=2, available_copies=2,
            reserved_copies=0, updated_at=now))
    return book_id


def prepare_library(client, actor):
    response = client.post("/api/v1/tools/library/prepare", json={
        "query": "\u5e2e\u6211\u9884\u7ea6\u300aGraph Representation Learning\u300b\u8fd9\u672c\u4e66",
        "actor_user_id": str(actor),
    })
    assert response.status_code == 200, response.text
    assert response.json()["candidates"]
    return response.json()["approval_id"]


def test_hitl02_duplicate_confirmation_has_one_sql_side_effect(security_app):
    client, engine, ids = security_app
    book_id = seed_library(engine)
    login(client)
    approval = prepare_library(client, ids[0])
    # Model the committed result of a prior successful execution. SQLite cannot
    # validate PostgreSQL advisory locks; the HTTP replay path and SQL state are real.
    reservation_id = uuid4()
    now = datetime.now(timezone.utc)
    with engine.begin() as connection:
        connection.execute(action_requests.update().values(status="executed").where(
            action_requests.c.id == UUID(approval)))
        connection.execute(library_reservations.insert().values(
            id=reservation_id, action_request_id=UUID(approval),
            actor_user_id=ids[0], book_id=book_id, book_code="TEST-01",
            title="Graph Representation Learning", status="ready_for_pickup",
            pickup_expires_at=now + timedelta(days=3), created_at=now))
        connection.execute(library_inventory.update().values(available_copies=1, reserved_copies=1))
    results = []
    for _ in range(2):
        response = client.post("/api/v1/tools/library/resume", json={
            "approval_id": approval, "actor_user_id": str(ids[0]), "approved": True,
        })
        assert response.status_code == 200, response.text
        results.append(response.json())
    assert results[0]["state_changed"] is False
    assert results[0]["idempotent"] is True
    assert results[1]["idempotent"] is True
    assert results[1]["state_changed"] is False
    assert results[0]["reservation"]["reservation_id"] == results[1]["reservation"]["reservation_id"]
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(library_reservations)) == 1
        inventory = db.execute(select(library_inventory)).mappings().one()
        assert inventory["available_copies"] == 1
        assert inventory["reserved_copies"] == 1


def test_execute_reauthorizes_after_role_revocation(security_app):
    client, engine, ids = security_app
    seed_library(engine)
    login(client)
    approval = prepare_library(client, ids[0])
    with Session(engine) as db:
        db.query(UserRole).filter(UserRole.user_id == ids[0]).delete()
        db.commit()
    # The Agent resume path does not have the classroom/library route guard;
    # the real runtime and service must recheck SQL-backed permissions.
    response = client.post("/api/v1/agent/resume", json={
        "approval_id": approval, "actor_user_id": str(ids[0]), "approved": True,
    })
    assert response.status_code == 403, response.text
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(library_reservations)) == 0
        assert db.scalar(select(library_inventory.c.available_copies)) == 2


@pytest.mark.parametrize("content_type", [None, "application/vnd.campusmind+json"])
def test_forged_actor_cannot_bypass_with_alternate_json_headers(security_app, content_type):
    import json

    client, _, ids = security_app
    login(client)
    response = client.post("/api/v1/tools/classroom/prepare",
                           content=json.dumps({"query": "test", "actor_user_id": str(ids[1])}),
                           headers={"content-type": content_type} if content_type else {})
    assert response.status_code == 403, response.text


def test_forged_actor_in_query_or_form_is_denied(security_app):
    client, _, ids = security_app
    login(client)
    response = client.get("/api/v1/tools/student/profile", params={"actor_user_id": str(ids[1])})
    assert response.status_code == 403, response.text
    response = client.post("/api/v1/documents/upload",
                           files={"file": ("test.txt", b"test", "text/plain")},
                           data={"actor_user_id": str(ids[1]), "knowledge_base_code": "test",
                                 "document_type": "test"})
    assert response.status_code == 403, response.text


def test_agent_tools_inherit_session_actor_without_client_id(security_app):
    client, engine, ids = security_app
    login(client)
    response = client.post("/api/v1/agent/chat", json={
        "query": "\u5e2e\u6211\u9884\u7ea62099-12-31\u4e0b\u534830\u4eba\u7684\u6559\u5ba4",
        "persist_trace": False,
    })
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "awaiting_approval"
    with Session(engine) as db:
        assert db.scalar(select(action_requests.c.actor_user_id)) == ids[0]
        assert db.scalar(select(func.count()).select_from(classroom_reservations)) == 0


def test_prepare_cannot_attach_other_users_trace(security_app):
    client, engine, ids = security_app
    with Session(engine) as db:
        run = AgentRun(user_id=ids[1], query="private trace")
        db.add(run)
        db.commit()
        trace_id = run.id
    login(client)
    response = client.post("/api/v1/tools/classroom/prepare", json={
        "query": "\u5e2e\u6211\u9884\u7ea62099-12-31\u4e0b\u534830\u4eba\u7684\u6559\u5ba4",
        "actor_user_id": str(ids[0]), "trace_id": str(trace_id),
    })
    assert response.status_code == 403, response.text
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(action_requests)) == 0


def test_read_grant_does_not_authorize_uploading_new_version(security_app):
    client, engine, ids = security_app
    document_id = seed_document(engine, ids[1], security=False, level="campus", grant=ids[0])
    with Session(engine) as db:
        permission = Permission(code="document.upload", name="Upload")
        db.add(permission)
        db.flush()
        role_id = db.scalar(select(UserRole.role_id).where(UserRole.user_id == ids[0]))
        db.add(RolePermission(role_id=role_id, permission_id=permission.id))
        db.commit()
    login(client)
    assert client.get(f"/api/v1/documents/{document_id}").status_code == 200
    response = client.post("/api/v1/documents/upload",
                           files={"file": ("test.txt", b"replacement", "text/plain")},
                           data={"knowledge_base_code": "test", "document_type": "test",
                                 "document_id": str(document_id), "version": "2"})
    assert response.status_code == 403, response.text
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(DocumentVersion)) == 1


def test_role_names_cannot_accidentally_grant_admin(security_app):
    client, engine, ids = security_app
    with Session(engine) as db:
        role = Role(code="student_club_admin", name="Club administrator")
        db.add(role)
        db.flush()
        db.add(UserRole(user_id=ids[0], role_id=role.id))
        db.commit()
    login(client)
    assert client.post("/api/v1/graph/bootstrap").status_code == 403


def test_evaluation_cannot_impersonate_another_user(security_app):
    client, engine, ids = security_app
    with Session(engine) as db:
        admin = Role(code="system_admin", name="System administrator")
        dataset = EvaluationDataset(name="test", version="1", status="active")
        db.add_all([admin, dataset])
        db.flush()
        db.add(UserRole(user_id=ids[0], role_id=admin.id))
        db.add(EvaluationCase(dataset_id=dataset.id, category="SQL", question="test",
                              metadata_json={"synthetic": True,
                                             "evaluation_actor_user_id": str(ids[1])}))
        db.commit()
        dataset_id = dataset.id
    login(client)
    response = client.post(f"/api/v1/admin/evaluations/{dataset_id}/run",
                           params={"actor_user_id": str(ids[0])})
    assert response.status_code == 403, response.text


def test_document_chunks_enforce_owner_and_hide_older_private_version(security_app):
    client, engine, ids = security_app
    document_id = seed_document(engine, ids[0])
    with Session(engine) as db:
        current = db.scalar(select(DocumentVersion).where(DocumentVersion.document_id == document_id))
        db.add(DocumentChunk(document_id=document_id, document_version_id=current.id,
                             knowledge_base_id=db.get(Document, document_id).knowledge_base_id,
                             chunk_index=1, content="Other user's secret",
                             permission_level="personal", metadata_json={"owner_user_id": str(ids[1])}))
        db.add(DocumentVersion(document_id=document_id, version="old", status="inactive",
                                object_key="old-private-object",
                                metadata_json={"security": {"permission_level": "personal",
                                                            "owner_user_id": str(ids[1])}}))
        db.commit()
    login(client)
    response = client.get(f"/api/v1/documents/{document_id}/chunks")
    assert response.status_code == 200, response.text
    assert response.json()["total"] == 1
    assert "Other user's secret" not in response.text
    response = client.get(f"/api/v1/documents/{document_id}")
    assert response.status_code == 200
    assert len(response.json()["versions"]) == 1
    assert "old-private-object" not in response.text


def test_authorized_graph_manager_still_cannot_ingest_someone_elses_personal_document(security_app):
    client, engine, ids = security_app
    document_id = seed_document(engine, ids[1])
    with Session(engine) as db:
        role = Role(code="knowledge_admin", name="Knowledge administrator")
        db.add(role)
        db.flush()
        db.add(UserRole(user_id=ids[0], role_id=role.id))
        db.commit()
        chunk_id = db.scalar(select(DocumentChunk.id))
    login(client)
    for path in (f"/graph/ingest/documents/{document_id}", f"/graph/ingest/chunks/{chunk_id}"):
        response = client.post("/api/v1" + path)
        assert response.status_code in {403, 404}, response.text


def test_library_rejection_preserves_inventory(security_app):
    client, engine, ids = security_app
    seed_library(engine)
    login(client)
    approval = prepare_library(client, ids[0])
    for approved in (False, True):
        response = client.post("/api/v1/tools/library/resume", json={
            "approval_id": approval, "actor_user_id": str(ids[0]), "approved": approved,
        })
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "rejected"
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(library_reservations)) == 0
        assert db.scalar(select(library_inventory.c.available_copies)) == 2


def test_approval_cannot_be_used_for_wrong_action_type(security_app):
    client, engine, ids = security_app
    seed_library(engine)
    login(client)
    approval = prepare_library(client, ids[0])
    response = client.post("/api/v1/tools/classroom/resume", json={
        "approval_id": approval, "actor_user_id": str(ids[0]), "approved": True,
    })
    assert response.status_code == 409, response.text
    with Session(engine) as db:
        assert db.scalar(select(action_requests.c.status)) == "awaiting_approval"
        assert db.scalar(select(func.count()).select_from(classroom_reservations)) == 0
