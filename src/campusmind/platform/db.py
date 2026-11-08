from __future__ import annotations

import uuid
from datetime import datetime, timezone
from sqlalchemy import DateTime, Uuid
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from collections.abc import Generator
from functools import lru_cache
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker
from campusmind.config import get_settings
from sqlalchemy.types import UserDefinedType
from decimal import Decimal
from sqlalchemy import Boolean, ForeignKey, JSON, Numeric, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column
from datetime import date
from sqlalchemy import Boolean, Date, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, Uuid
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, Numeric, String, Text, Uuid
from datetime import date, datetime
from sqlalchemy import Date, DateTime, ForeignKey, Integer, JSON, String, Text, Uuid, UniqueConstraint

"""CampusMind db domain."""

# ---- app/db/base.py ----
class Base(DeclarativeBase):
    """Shared SQLAlchemy declarative base for the CampusMind modular monolith."""


class UUIDPrimaryKeyMixin:
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

# ---- app/db/session.py ----
@lru_cache
def get_engine() -> Engine:
    settings = get_settings()
    return create_engine(
        settings.sqlalchemy_database_url,
        pool_pre_ping=True,
        pool_size=settings.postgres_pool_size,
        max_overflow=settings.postgres_max_overflow,
        pool_timeout=settings.postgres_pool_timeout,
    )


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), class_=Session, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    db = get_session_factory()()
    try:
        yield db
    finally:
        db.close()

# ---- app/db/types.py ----
class Vector(UserDefinedType):
    """Minimal PostgreSQL pgvector type.

    Keeping the type in-project avoids coupling the baseline database schema definition to a
    specific Python pgvector adapter. The database extension is still pgvector.
    A richer adapter can be introduced when the embedding pipeline is added.
    """

    cache_ok = True

    def __init__(self, dimensions: int | None = None) -> None:
        self.dimensions = dimensions

    def get_col_spec(self, **_: object) -> str:
        return f"vector({self.dimensions})" if self.dimensions else "vector"

# ---- app/db/models/evaluation.py ----
class EvaluationDataset(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "evaluation_datasets"
    name: Mapped[str] = mapped_column(String(128), index=True)
    version: Mapped[str] = mapped_column(String(64), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)


class EvaluationCase(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "evaluation_cases"
    dataset_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("evaluation_datasets.id", ondelete="CASCADE"), index=True)
    category: Mapped[str] = mapped_column(String(64), index=True)
    question: Mapped[str] = mapped_column(Text)
    expected_answer: Mapped[str | None] = mapped_column(Text)
    expected_evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)


class EvaluationResult(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "evaluation_results"
    dataset_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("evaluation_datasets.id", ondelete="CASCADE"), index=True)
    case_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("evaluation_cases.id", ondelete="CASCADE"), index=True)
    agent_run_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("agent_runs.id", ondelete="SET NULL"), index=True)
    score: Mapped[Decimal | None] = mapped_column(Numeric(6, 4))
    passed: Mapped[bool | None] = mapped_column(Boolean)
    metrics_json: Mapped[dict] = mapped_column(JSON, default=dict)

# ---- app/db/models/identity.py ----
class Role(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "roles"
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str | None] = mapped_column(Text)


class Permission(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "permissions"
    code: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str | None] = mapped_column(Text)


class RolePermission(Base):
    __tablename__ = "role_permissions"
    role_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True)
    permission_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True)


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    email: Mapped[str | None] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str | None] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False)


class UserRole(Base):
    __tablename__ = "user_roles"
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    role_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True)


class AuthSession(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "auth_sessions"
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    token_hash: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        index=True,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        index=True,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )


class College(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "colleges"
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128), unique=True)


class Department(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "departments"
    college_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("colleges.id", ondelete="RESTRICT"), index=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))


class Major(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "majors"
    college_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("colleges.id", ondelete="RESTRICT"), index=True)
    department_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("departments.id", ondelete="SET NULL"), index=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    degree_type: Mapped[str] = mapped_column(String(32), default="bachelor")
    graduation_credits: Mapped[int] = mapped_column(Integer, default=160)


class Student(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "students"
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True)
    student_no: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    major_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("majors.id", ondelete="RESTRICT"), index=True)
    enrollment_year: Mapped[int] = mapped_column(Integer)
    grade_level: Mapped[int] = mapped_column(Integer, default=1)
    total_credits: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=0)
    expected_graduation_date: Mapped[date | None] = mapped_column(Date)


class Teacher(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "teachers"
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True)
    employee_no: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    department_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("departments.id", ondelete="RESTRICT"), index=True)
    title: Mapped[str | None] = mapped_column(String(64))
    bio: Mapped[str | None] = mapped_column(Text)


class Course(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "courses"
    department_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("departments.id", ondelete="RESTRICT"), index=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128), index=True)
    credits: Mapped[Decimal] = mapped_column(Numeric(4, 1))
    course_type: Mapped[str] = mapped_column(String(32), default="required")
    description: Mapped[str | None] = mapped_column(Text)


class CoursePrerequisite(Base):
    __tablename__ = "course_prerequisites"
    __table_args__ = (UniqueConstraint("course_id", "prerequisite_course_id", name="uq_course_prerequisite"),)
    course_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), primary_key=True)
    prerequisite_course_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), primary_key=True)
    relation_type: Mapped[str] = mapped_column(String(32), default="prerequisite")


class StudentCourse(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "student_courses"
    __table_args__ = (UniqueConstraint("student_id", "course_id", "semester", name="uq_student_course_semester"),)
    student_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("students.id", ondelete="CASCADE"), index=True)
    course_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("courses.id", ondelete="RESTRICT"), index=True)
    semester: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(32), default="completed")
    score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    credits_earned: Mapped[Decimal] = mapped_column(Numeric(4, 1), default=0)


class TeachingAssignment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "teaching_assignments"
    __table_args__ = (UniqueConstraint("teacher_id", "course_id", "semester", name="uq_teacher_course_semester"),)
    teacher_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("teachers.id", ondelete="CASCADE"), index=True)
    course_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    semester: Mapped[str] = mapped_column(String(32), index=True)

# ---- app/db/models/runtime.py ----
class Conversation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "conversations"
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)


class Message(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "messages"
    conversation_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(32), index=True)
    content: Mapped[str] = mapped_column(Text)
    citations: Mapped[list] = mapped_column(JSON, default=list)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)


class AgentRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "agent_runs"
    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True)
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("conversations.id", ondelete="SET NULL"), index=True)
    query: Mapped[str] = mapped_column(Text)
    intent: Mapped[str | None] = mapped_column(String(64), index=True)
    complexity: Mapped[str | None] = mapped_column(String(32), index=True)
    risk_level: Mapped[str] = mapped_column(String(32), default="low", index=True)
    retrieval_strategy: Mapped[str | None] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), default="running", index=True)
    validation_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    final_answer: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    latency_ms: Mapped[int | None] = mapped_column(Integer)


class AgentStep(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "agent_steps"
    agent_run_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("agent_runs.id", ondelete="CASCADE"), index=True)
    sequence_no: Mapped[int] = mapped_column(Integer)
    step_name: Mapped[str] = mapped_column(String(128), index=True)
    step_type: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), default="running", index=True)
    input_json: Mapped[dict] = mapped_column(JSON, default=dict)
    output_json: Mapped[dict] = mapped_column(JSON, default=dict)
    latency_ms: Mapped[int | None] = mapped_column(Integer)


class ToolCall(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "tool_calls"
    agent_run_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("agent_runs.id", ondelete="CASCADE"), index=True)
    agent_step_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("agent_steps.id", ondelete="SET NULL"), index=True)
    tool_name: Mapped[str] = mapped_column(String(128), index=True)
    arguments_json: Mapped[dict] = mapped_column(JSON, default=dict)
    result_json: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=False)
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditLog(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "audit_logs"
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True)
    action: Mapped[str] = mapped_column(String(128), index=True)
    resource_type: Mapped[str] = mapped_column(String(64), index=True)
    resource_id: Mapped[str | None] = mapped_column(String(128), index=True)
    request_id: Mapped[str | None] = mapped_column(String(128), index=True)
    ip_address: Mapped[str | None] = mapped_column(String(64))
    detail_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

# ---- app/db/models/knowledge.py ----
class KnowledgeBase(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "knowledge_bases"
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    domain: Mapped[str] = mapped_column(String(32), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    visibility: Mapped[str] = mapped_column(String(32), default="campus")
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)


class Document(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "documents"
    knowledge_base_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("knowledge_bases.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(255), index=True)
    object_key: Mapped[str] = mapped_column(String(512), unique=True)
    mime_type: Mapped[str] = mapped_column(String(128))
    checksum_sha256: Mapped[str | None] = mapped_column(String(64), index=True)
    document_type: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), default="uploaded", index=True)


class DocumentVersion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "document_versions"
    __table_args__ = (UniqueConstraint("document_id", "version", name="uq_document_version"),)
    document_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    version: Mapped[str] = mapped_column(String(64))
    object_key: Mapped[str] = mapped_column(String(512))
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    effective_from: Mapped[date | None] = mapped_column(Date, index=True)
    effective_to: Mapped[date | None] = mapped_column(Date, index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    department: Mapped[str | None] = mapped_column(String(128), index=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)


class DocumentPermission(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "document_permissions"
    __table_args__ = (UniqueConstraint("document_id", "subject_type", "subject_id", name="uq_document_permission_subject"),)
    document_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    subject_type: Mapped[str] = mapped_column(String(16), index=True)  # user | role
    subject_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    permission_level: Mapped[str] = mapped_column(String(32), default="read")


class DocumentChunk(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "document_chunks"
    __table_args__ = (UniqueConstraint("document_version_id", "chunk_index", name="uq_document_chunk_index"),)
    document_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    document_version_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("document_versions.id", ondelete="CASCADE"), index=True)
    knowledge_base_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("knowledge_bases.id", ondelete="CASCADE"), index=True)
    chunk_index: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    token_count: Mapped[int | None] = mapped_column(Integer)
    page: Mapped[int | None] = mapped_column(Integer, index=True)
    chapter: Mapped[str | None] = mapped_column(String(255))
    section: Mapped[str | None] = mapped_column(String(255), index=True)
    department: Mapped[str | None] = mapped_column(String(128), index=True)
    document_type: Mapped[str | None] = mapped_column(String(64), index=True)
    effective_date: Mapped[date | None] = mapped_column(Date, index=True)
    permission_level: Mapped[str] = mapped_column(String(32), default="campus", index=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    embedding: Mapped[object | None] = mapped_column(Vector(), nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(128), index=True)
    embedding_dimensions: Mapped[int | None] = mapped_column(Integer)
    embedded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
