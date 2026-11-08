"""CampusMind classroom and library actions with human approval."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from enum import Enum

from pydantic import BaseModel, Field
from sqlalchemy import (
    JSON,
    Column,
    Date,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    Time,
    Uuid,
    case,
    insert,
    or_,
    select,
    text,
    update,
)
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from campusmind.platform.db import AgentRun, User
from campusmind.platform.security import AuthorizationService


# ---- app/campus_tools/types.py ----
class ClassroomActionStatus(str, Enum):
    AWAITING_APPROVAL = "awaiting_approval"
    EXECUTED = "executed"
    REJECTED = "rejected"
    EXPIRED = "expired"


class ClassroomIntent(BaseModel):
    reservation_date: date
    start_time: time
    end_time: time
    capacity: int = Field(ge=1, le=500)
    daypart: str


class ClassroomCandidate(BaseModel):
    room_id: str
    room_name: str
    building: str
    capacity: int
    floor: int


class ClassroomPrepareResult(BaseModel):
    capability: str = "classroom_reservation"
    approval_id: str
    trace_id: str | None = None
    actor_user_id: str
    status: ClassroomActionStatus = ClassroomActionStatus.AWAITING_APPROVAL
    answer: str
    requested: ClassroomIntent
    candidates: list[ClassroomCandidate] = Field(default_factory=list)
    expires_at: str
    audit: dict = Field(default_factory=dict)


class ClassroomResumeResult(BaseModel):
    capability: str = "classroom_reservation"
    approval_id: str
    trace_id: str | None = None
    actor_user_id: str
    status: ClassroomActionStatus
    answer: str
    reservation: dict | None = None
    state_changed: bool = True
    idempotent: bool = False
    audit: dict = Field(default_factory=dict)


class LibraryIntent(BaseModel):
    query: str
    title_hint: str | None = None
    keywords: list[str] = Field(default_factory=list)


class LibraryBookCandidate(BaseModel):
    book_id: str
    book_code: str
    title: str
    author: str
    isbn: str | None = None
    subject: str | None = None
    location: str
    total_copies: int = 0
    available_copies: int = 0


class LibraryPrepareResult(BaseModel):
    capability: str = "library_book_reservation"
    approval_id: str
    trace_id: str | None = None
    actor_user_id: str
    status: ClassroomActionStatus = ClassroomActionStatus.AWAITING_APPROVAL
    answer: str
    requested: LibraryIntent
    candidates: list[LibraryBookCandidate] = Field(default_factory=list)
    expires_at: str
    audit: dict = Field(default_factory=dict)


class LibraryResumeResult(BaseModel):
    capability: str = "library_book_reservation"
    approval_id: str
    trace_id: str | None = None
    actor_user_id: str
    status: ClassroomActionStatus
    answer: str
    reservation: dict | None = None
    state_changed: bool = True
    idempotent: bool = False
    audit: dict = Field(default_factory=dict)

# ---- app/campus_tools/classroom.py ----
class ClassroomActionError(RuntimeError):
    pass


class ClassroomActionNotFound(ClassroomActionError):
    pass


class ClassroomActionOwnershipError(ClassroomActionError):
    pass


class ClassroomActionConflict(ClassroomActionError):
    pass


class ClassroomActionExpired(ClassroomActionError):
    pass


def _require_trace_owner(session: Session, trace_id, actor) -> None:
    if trace_id is None:
        return
    run = session.get(AgentRun, uuid.UUID(str(trace_id)))
    if run is not None and run.user_id != actor:
        raise ClassroomActionOwnershipError("trace does not belong to actor_user_id")


@dataclass(frozen=True, slots=True)
class _Room:
    room_id: str
    room_name: str
    building: str
    capacity: int
    floor: int
    priority: int


ROOMS: tuple[_Room, ...] = (
    _Room("CM-A101", "A101", "计算机学院A楼", 40, 1, 1),
    _Room("CM-A103", "A103", "计算机学院A楼", 48, 1, 2),
    _Room("TEACH-C305", "C305", "第三教学楼", 32, 3, 3),
    _Room("LIB-B202", "B202", "主图书馆B区", 60, 2, 4),
    _Room("TEACH-D401", "D401", "第四教学楼", 90, 4, 5),
)


metadata = MetaData()

action_requests = Table(
    "campus_action_requests",
    metadata,
    # Deliberately no FK to agent_runs: the AgentRun is persisted after the
    # graph returns its awaiting-approval state.
    # UUID columns use SQLAlchemy's backend-portable Uuid type.
    Column("id", Uuid(as_uuid=True), primary_key=True),
    Column("trace_id", Uuid(as_uuid=True), nullable=True, index=True),
    Column("actor_user_id", Uuid(as_uuid=True), nullable=False, index=True),
    Column("action_type", String(80), nullable=False),
    Column("status", String(32), nullable=False),
    Column("request_json", JSON, nullable=False),
    Column("candidates_json", JSON, nullable=False),
    Column("selected_resource_id", String(120), nullable=True),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

classroom_reservations = Table(
    "classroom_reservations",
    metadata,
    Column("id", Uuid(as_uuid=True), primary_key=True),
    Column("action_request_id", Uuid(as_uuid=True), nullable=False, unique=True),
    Column("actor_user_id", Uuid(as_uuid=True), nullable=False, index=True),
    Column("room_id", String(80), nullable=False, index=True),
    Column("room_name", String(80), nullable=False),
    Column("building", String(160), nullable=False),
    Column("reservation_date", Date, nullable=False, index=True),
    Column("start_time", Time, nullable=False),
    Column("end_time", Time, nullable=False),
    Column("party_size", Integer, nullable=False),
    Column("status", String(32), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)


class ClassroomIntentParser:
    """Narrow deterministic parser for governed classroom actions."""

    _CAPACITY_RE = re.compile(r"(?:(?:能坐|容纳|至少|大约|约)\s*)?(\d{1,3})\s*人")
    _ISO_DATE_RE = re.compile(r"(20\d{2})[-/](\d{1,2})[-/](\d{1,2})")
    _CN_DATE_RE = re.compile(r"(\d{1,2})月(\d{1,2})日")

    def parse(self, query: str, *, now: datetime | None = None) -> ClassroomIntent:
        now = now or datetime.now().astimezone()
        q = "".join((query or "").split())

        match = self._CAPACITY_RE.search(q)
        capacity = int(match.group(1)) if match else 1

        iso = self._ISO_DATE_RE.search(q)
        cn = self._CN_DATE_RE.search(q)
        if iso:
            target = date(int(iso.group(1)), int(iso.group(2)), int(iso.group(3)))
        elif cn:
            target = date(now.year, int(cn.group(1)), int(cn.group(2)))
            if target < now.date():
                target = date(now.year + 1, target.month, target.day)
        elif "后天" in q:
            target = now.date() + timedelta(days=2)
        elif "今天" in q or "今日" in q:
            target = now.date()
        else:
            # Classroom action requests without an explicit date are intentionally
            # biased to tomorrow rather than silently booking today.
            target = now.date() + timedelta(days=1)

        if "上午" in q or "早上" in q:
            start, end, daypart = time(8, 30), time(12, 0), "morning"
        elif "晚上" in q or "晚间" in q:
            start, end, daypart = time(18, 30), time(21, 30), "evening"
        else:
            start, end, daypart = time(13, 30), time(17, 30), "afternoon"

        return ClassroomIntent(
            reservation_date=target,
            start_time=start,
            end_time=end,
            capacity=capacity,
            daypart=daypart,
        )


class LegacyAuditMirror:
    """Mirror classroom HITL events into the existing tool_calls/audit_logs tables.

    The baseline schema intentionally keeps those tables generic. To remain compatible with
    the existing schema without replacing its ORM model file, this writer uses
    SQLAlchemy reflection and a conservative alias map. Inserts are isolated in
    SAVEPOINTs so a legacy-schema mismatch never corrupts the action transaction.
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    def _reflect(self, name: str) -> Table | None:
        try:
            return Table(name, MetaData(), autoload_with=self.session.connection())
        except SQLAlchemyError:
            return None

    @staticmethod
    def _uuid(value) -> uuid.UUID | None:
        if not value:
            return None
        try:
            return uuid.UUID(str(value))
        except (TypeError, ValueError):
            return None

    def _agent_run_exists(self, trace_id) -> bool:
        trace = self._uuid(trace_id)
        if trace is None:
            return False
        table = self._reflect("agent_runs")
        if table is None or "id" not in table.c:
            return False
        return self.session.execute(select(table.c.id).where(table.c.id == trace)).first() is not None

    def _payload(
        self,
        table: Table,
        *,
        kind: str,
        actor_user_id,
        trace_id,
        tool_name,
        action,
        arguments,
        result,
        status,
        requires_approval,
        resource_type: str = "classroom",
        resource_id: str | None = None,
    ) -> dict:
        now = datetime.now(UTC)
        actor = self._uuid(actor_user_id)
        trace = self._uuid(trace_id)
        trace_exists = self._agent_run_exists(trace)
        details = {
            "tool_name": tool_name,
            "action": action,
            "arguments": arguments,
            "result": result,
            "requires_approval": requires_approval,
            "resource_type": resource_type,
            "resource_id": resource_id,
        }

        values: dict = {}
        aliases = {
            "id": uuid.uuid4(),
            "user_id": actor,
            "actor_user_id": actor,
            "actor_id": actor,
            "agent_run_id": trace if trace_exists else None,
            "tool_name": tool_name,
            "tool": tool_name,
            "name": tool_name if kind == "tool" else action,
            "action": action,
            "operation": action,
            "event_type": action,
            "resource_type": resource_type,
            "resource_id": resource_id or str(
                result.get("room_id")
                or result.get("book_id")
                or arguments.get("room_id")
                or arguments.get("book_id")
                or arguments.get("resource_id")
                or ""
            ) or None,
            "arguments_json": arguments,
            "arguments": arguments,
            "input_json": arguments,
            "input": arguments,
            "request_json": arguments,
            "request": arguments,
            "params_json": arguments,
            "params": arguments,
            "result_json": result,
            "result": result,
            "output_json": result,
            "output": result,
            "response_json": result,
            "response": result,
            "details_json": details,
            "details": details,
            "detail_json": details,
            "metadata_json": details,
            "metadata": details,
            "status": status,
            "requires_approval": requires_approval,
            "pending_approval": requires_approval and status == "pending",
            "approved": status in {"approved", "succeeded", "executed"},
            "approved_at": now if status in {"approved", "succeeded", "executed"} else None,
            "executed_at": now if status in {"succeeded", "executed"} else None,
            "started_at": now,
            "finished_at": now,
            "success": status in {"approved", "succeeded", "executed"},
            "created_at": now,
            "updated_at": now,
            "latency_ms": 0,
        }
        for column in table.c:
            if column.name in aliases and aliases[column.name] is not None:
                values[column.name] = aliases[column.name]

        # Fill only unavoidable scalar NOT NULL fields that do not have a DB/default.
        for column in table.c:
            if column.name in values or column.primary_key:
                continue
            if column.nullable or column.default is not None or column.server_default is not None:
                continue
            if column.foreign_keys:
                continue
            pytype = None
            try:
                pytype = column.type.python_type
            except (AttributeError, NotImplementedError):
                pass
            if pytype is str:
                values[column.name] = action
            elif pytype is bool:
                values[column.name] = False
            elif pytype is int:
                values[column.name] = 0
            elif pytype is dict:
                values[column.name] = details
            elif pytype is datetime:
                values[column.name] = now
            elif pytype is uuid.UUID:
                values[column.name] = uuid.uuid4()

        return values

    def _insert(self, table_name: str, **context) -> tuple[bool, str | None]:
        table = self._reflect(table_name)
        if table is None:
            return False, f"{table_name} table is unavailable"
        try:
            with self.session.begin_nested():
                self.session.execute(insert(table).values(**self._payload(table, **context)))
            return True, None
        except Exception as exc:  # noqa: BLE001 - mirror failures must not abort the action
            return False, f"{type(exc).__name__}: {exc}"

    def record(
        self,
        *,
        actor_user_id,
        trace_id,
        tool_name: str,
        action: str,
        arguments: dict,
        result: dict,
        status: str,
        requires_approval: bool,
        resource_type: str = "classroom",
        resource_id: str | None = None,
    ) -> dict:
        # Agent actions are prepared before the AgentRun row is persisted. If a
        # trace_id was supplied, defer both legacy mirrors until that row exists;
        # AgentRuntimeService retries immediately after persisting the paused run.
        if trace_id and not self._agent_run_exists(trace_id):
            reason = "agent_run is not persisted yet; mirror will retry after trace persistence"
            return {
                "tool_call_persisted": False,
                "audit_log_persisted": False,
                "tool_call_error": reason,
                "audit_log_error": reason,
            }

        common = {
            "actor_user_id": actor_user_id,
            "trace_id": trace_id,
            "tool_name": tool_name,
            "action": action,
            "arguments": arguments,
            "result": result,
            "status": status,
            "requires_approval": requires_approval,
            "resource_type": resource_type,
            "resource_id": resource_id,
        }
        tool_ok, tool_error = self._insert("tool_calls", kind="tool", **common)
        audit_ok, audit_error = self._insert("audit_logs", kind="audit", **common)
        return {
            "tool_call_persisted": tool_ok,
            "audit_log_persisted": audit_ok,
            "tool_call_error": tool_error,
            "audit_log_error": audit_error,
        }


class ClassroomActionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    @staticmethod
    def _as_uuid(value) -> uuid.UUID:
        return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))

    def ensure_actor(self, actor_user_id) -> uuid.UUID:
        actor = self._as_uuid(actor_user_id)
        if self.session.scalar(select(User.id).where(User.id == actor, User.status == "active")) is None:
            raise ClassroomActionOwnershipError(f"unknown actor_user_id={actor}")
        return actor

    def occupied_room_ids(self, intent: ClassroomIntent) -> set[str]:
        stmt = select(classroom_reservations.c.room_id).where(
            classroom_reservations.c.reservation_date == intent.reservation_date,
            classroom_reservations.c.status == "confirmed",
            classroom_reservations.c.start_time < intent.end_time,
            classroom_reservations.c.end_time > intent.start_time,
        )
        return set(self.session.scalars(stmt).all())

    def lock_room_slot(self, room_id: str, reservation_date: date) -> None:
        # PostgreSQL transaction-scoped advisory lock closes the race between
        # availability re-check and INSERT without requiring a heavyweight room table.
        key = f"campusmind:classroom:{room_id}:{reservation_date.isoformat()}"
        self.session.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
            {"lock_key": key},
        )

    def create_request(self, *, actor_user_id: uuid.UUID, trace_id, intent: ClassroomIntent, candidates: list[ClassroomCandidate], expires_at: datetime) -> uuid.UUID:
        approval_id = uuid.uuid4()
        trace_uuid = self._as_uuid(trace_id) if trace_id else None
        now = datetime.now(UTC)
        self.session.execute(
            insert(action_requests).values(
                id=approval_id,
                trace_id=trace_uuid,
                actor_user_id=actor_user_id,
                action_type="reserve_classroom",
                status=(
                    ClassroomActionStatus.AWAITING_APPROVAL.value
                    if candidates
                    else ClassroomActionStatus.REJECTED.value
                ),
                request_json={
                    "reservation_date": intent.reservation_date.isoformat(),
                    "start_time": intent.start_time.isoformat(),
                    "end_time": intent.end_time.isoformat(),
                    "capacity": intent.capacity,
                    "daypart": intent.daypart,
                },
                candidates_json=[item.model_dump() for item in candidates],
                expires_at=expires_at,
                created_at=now,
                updated_at=now,
            )
        )
        return approval_id

    # latest_valid_classroom_pending_v131
    def latest_valid_pending_request_id(
        self,
        actor_user_id,
    ):
        actor = self.ensure_actor(actor_user_id)

        stmt = (
            select(action_requests.c.id)
            .where(
                action_requests.c.actor_user_id == actor,
                action_requests.c.action_type
                == "reserve_classroom",
                action_requests.c.status
                == ClassroomActionStatus.AWAITING_APPROVAL.value,
                text(
                    "jsonb_array_length("
                    "COALESCE("
                    "campus_action_requests."
                    "candidates_json::jsonb, "
                    "'[]'::jsonb"
                    ")"
                    ") > 0"
                ),
            )
            .order_by(
                action_requests.c.created_at.desc()
            )
            .limit(1)
        )

        return self.session.scalar(stmt)


    def get_request_for_update(self, approval_id) -> dict:
        approval = self._as_uuid(approval_id)
        row = self.session.execute(
            select(action_requests).where(action_requests.c.id == approval).with_for_update()
        ).mappings().one_or_none()
        if row is None:
            raise ClassroomActionNotFound(f"approval_id={approval} was not found")
        return dict(row)

    def existing_reservation(self, approval_id) -> dict | None:
        approval = self._as_uuid(approval_id)
        row = self.session.execute(
            select(classroom_reservations).where(classroom_reservations.c.action_request_id == approval)
        ).mappings().one_or_none()
        return dict(row) if row else None

    def insert_reservation(self, *, approval_id, actor_user_id, room: ClassroomCandidate, intent: ClassroomIntent) -> dict:
        reservation_id = uuid.uuid4()
        now = datetime.now(UTC)
        self.session.execute(
            insert(classroom_reservations).values(
                id=reservation_id,
                action_request_id=self._as_uuid(approval_id),
                actor_user_id=self._as_uuid(actor_user_id),
                room_id=room.room_id,
                room_name=room.room_name,
                building=room.building,
                reservation_date=intent.reservation_date,
                start_time=intent.start_time,
                end_time=intent.end_time,
                party_size=intent.capacity,
                status="confirmed",
                created_at=now,
            )
        )
        return {
            "reservation_id": str(reservation_id),
            "room_id": room.room_id,
            "room_name": room.room_name,
            "building": room.building,
            "reservation_date": intent.reservation_date.isoformat(),
            "start_time": intent.start_time.isoformat(),
            "end_time": intent.end_time.isoformat(),
            "party_size": intent.capacity,
            "status": "confirmed",
        }

    def set_request_status(self, approval_id, *, status: ClassroomActionStatus, selected_resource_id: str | None = None) -> None:
        self.session.execute(
            update(action_requests)
            .where(action_requests.c.id == self._as_uuid(approval_id))
            .values(
                status=status.value,
                selected_resource_id=selected_resource_id,
                updated_at=datetime.now(UTC),
            )
        )

    def list_actor_reservations(self, actor_user_id) -> list[dict]:
        actor = self.ensure_actor(actor_user_id)
        rows = self.session.execute(
            select(classroom_reservations)
            .where(classroom_reservations.c.actor_user_id == actor)
            .order_by(classroom_reservations.c.reservation_date.asc(), classroom_reservations.c.start_time.asc())
        ).mappings().all()
        return [dict(row) for row in rows]


    # latest_pending_classroom_approval_v127
    def latest_pending_request_id(
        self,
        actor_user_id,
    ):
        actor = self.ensure_actor(actor_user_id)

        return self.session.scalar(
            select(action_requests.c.id)
            .where(
                action_requests.c.actor_user_id == actor,
                action_requests.c.action_type
                == "reserve_classroom",
                action_requests.c.status
                == ClassroomActionStatus.AWAITING_APPROVAL.value,
            )
            .order_by(
                action_requests.c.created_at.desc()
            )
            .limit(1)
        )


class ClassroomActionService:
    """classroom HITL workflow two-phase classroom tool: prepare -> approve/resume -> execute."""

    def __init__(self, session: Session, *, parser=None, approval_ttl_minutes: int = 30) -> None:
        self.session = session
        self.parser = parser or ClassroomIntentParser()
        self.repository = ClassroomActionRepository(session)
        self.audit = LegacyAuditMirror(session)
        self.approval_ttl_minutes = approval_ttl_minutes

    @staticmethod
    def supports(query: str) -> bool:
        q = "".join(
            (query or "").lower().split()
        )

        if not q:
            return False

        # approval_control_is_not_prepare_v131
        control_markers = (
            "\u786e\u8ba4\u6267\u884c",
            "\u786e\u8ba4\u9884\u7ea6",
            "\u53d6\u6d88",
            "\u62d2\u7edd",
            "\u4e0d\u540c\u610f",
            "\u540c\u610f\u6267\u884c",
            "\u6279\u51c6\u6267\u884c",
            "approval_id",
        )

        if any(
            token in q
            for token in control_markers
        ):
            return False

        has_resource = any(
            token in q
            for token in (
                "教室",
                "自习室",
                "研讨室",
                "场地",
            )
        )

        if not has_resource:
            return False

        # Questions about approval or automatic execution are read-only FAQ questions,
        # not action requests.
        faq_markers = (
            "会直接",
            "会自动",
            "自动预约",
            "是否直接",
            "是否自动",
            "会不会直接",
            "会不会自动",
            "需要确认",
            "是否需要确认",
            "还需要我确认",
            "需要我确认",
            "确认才会",
            "确认后才会",
            "先确认",
            "人工确认",
            "人工审批",
            "审批后",
        )

        if any(
            marker in q
            for marker in faq_markers
        ):
            return False

        return any(
            token in q
            for token in (
                "预约",
                "预订",
                "申请",
                "找",
                "空闲",
            )
        )

    def _search(self, intent: ClassroomIntent) -> list[ClassroomCandidate]:
        occupied = self.repository.occupied_room_ids(intent)
        rooms = [
            room
            for room in ROOMS
            if room.capacity >= intent.capacity and room.room_id not in occupied
        ]
        rooms.sort(key=lambda room: (room.priority, room.capacity - intent.capacity, room.room_id))
        return [
            ClassroomCandidate(
                room_id=room.room_id,
                room_name=room.room_name,
                building=room.building,
                capacity=room.capacity,
                floor=room.floor,
            )
            for room in rooms[:4]
        ]

    def prepare_reservation(self, query: str, actor_user_id, *, trace_id=None) -> ClassroomPrepareResult:
        if not self.supports(query):
            raise ClassroomActionError("classroom HITL workflow currently supports classroom reservation actions only")
        actor = self.repository.ensure_actor(actor_user_id)
        AuthorizationService(self.session).require("classroom.reserve", actor)
        _require_trace_owner(self.session, trace_id, actor)
        intent = self.parser.parse(query)
        candidates = self._search(intent)
        expires_at = datetime.now(UTC) + timedelta(minutes=self.approval_ttl_minutes)
        approval_id = self.repository.create_request(
            actor_user_id=actor,
            trace_id=trace_id,
            intent=intent,
            candidates=candidates,
            expires_at=expires_at,
        )

        if candidates:
            first = candidates[0]
            lines = [
                f"找到 {len(candidates)} 个满足容量要求的空闲教室；当前还没有执行预约。",
                *[
                    f"{idx}. {item.building} {item.room_name}（容量 {item.capacity} 人，room_id={item.room_id}）"
                    for idx, item in enumerate(candidates, start=1)
                ],
                f"推荐 {first.building} {first.room_name}。确认后才会执行 reserve_room()。",
                f"approval_id={approval_id}",
            ]
        else:
            lines = [
                "当前时间段没有找到满足容量要求的空闲教室，因此不会创建预约。",
                f"approval_id={approval_id}",
            ]

        audit = self.audit.record(
            actor_user_id=actor,
            trace_id=trace_id,
            tool_name="classroom.search_available_rooms",
            action="prepare_reservation",
            arguments={"query": query, **intent.model_dump(mode="json")},
            result={"approval_id": str(approval_id), "candidate_count": len(candidates)},
            status="pending",
            requires_approval=True,
        )
        self.session.commit()

        return ClassroomPrepareResult(
            approval_id=str(approval_id),
            trace_id=str(trace_id) if trace_id else None,
            actor_user_id=str(actor),
            answer="\n".join(lines),
            requested=intent,
            candidates=candidates,
            expires_at=expires_at.isoformat(),
            audit=audit,
        )

    @staticmethod
    def _intent_from_row(row: dict) -> ClassroomIntent:
        request = row["request_json"]
        return ClassroomIntent(
            reservation_date=date.fromisoformat(request["reservation_date"]),
            start_time=time.fromisoformat(request["start_time"]),
            end_time=time.fromisoformat(request["end_time"]),
            capacity=int(request["capacity"]),
            daypart=request.get("daypart", "custom"),
        )

    @staticmethod
    def _candidate_from_row(row: dict, room_id: str | None) -> ClassroomCandidate:
        candidates = [ClassroomCandidate(**item) for item in row.get("candidates_json") or []]
        if not candidates:
            raise ClassroomActionConflict("the approval request has no reservable classroom candidates")
        if room_id is None:
            return candidates[0]
        for item in candidates:
            if item.room_id == room_id:
                return item
        raise ClassroomActionConflict("selected room_id is not part of the approved candidate set")

    @staticmethod
    def _reservation_json(row: dict) -> dict:
        return {
            "reservation_id": str(row["id"]),
            "room_id": row["room_id"],
            "room_name": row["room_name"],
            "building": row["building"],
            "reservation_date": row["reservation_date"].isoformat(),
            "start_time": row["start_time"].isoformat(),
            "end_time": row["end_time"].isoformat(),
            "party_size": int(row["party_size"]),
            "status": row["status"],
        }

    def resume_reservation(self, approval_id, actor_user_id, *, approved: bool, room_id: str | None = None) -> ClassroomResumeResult:
        actor = self.repository.ensure_actor(actor_user_id)
        AuthorizationService(self.session).require("classroom.reserve", actor)
        row = self.repository.get_request_for_update(approval_id)
        if row["actor_user_id"] != actor:
            self.session.rollback()
            raise ClassroomActionOwnershipError("approval request does not belong to actor_user_id")

        if row["action_type"] != "reserve_classroom":
            raise ClassroomActionConflict("approval action type does not match classroom reservation")
        _require_trace_owner(self.session, row.get("trace_id"), actor)

        trace_id = str(row["trace_id"]) if row.get("trace_id") else None
        status = row["status"]
        existing = self.repository.existing_reservation(approval_id)
        if status == ClassroomActionStatus.EXECUTED.value and existing:
            self.session.rollback()
            reservation = self._reservation_json(existing)
            return ClassroomResumeResult(
                approval_id=str(approval_id),
                trace_id=trace_id,
                actor_user_id=str(actor),
                status=ClassroomActionStatus.EXECUTED,
                answer=(
                    f"该审批已执行过：{reservation['building']} {reservation['room_name']} "
                    f"已预约，无需重复提交。"
                ),
                reservation=reservation,
                state_changed=False,
                idempotent=True,
            )
        if status == ClassroomActionStatus.REJECTED.value:
            self.session.rollback()
            return ClassroomResumeResult(
                approval_id=str(approval_id),
                trace_id=trace_id,
                actor_user_id=str(actor),
                status=ClassroomActionStatus.REJECTED,
                answer="该审批已经取消，不会执行预约。",
                state_changed=False,
                idempotent=True,
            )

        now = datetime.now(UTC)
        expires_at = row["expires_at"]
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at <= now:
            self.repository.set_request_status(approval_id, status=ClassroomActionStatus.EXPIRED)
            self.session.commit()
            raise ClassroomActionExpired("approval request has expired; create a new classroom search")

        if not approved:
            self.repository.set_request_status(approval_id, status=ClassroomActionStatus.REJECTED)
            audit = self.audit.record(
                actor_user_id=actor,
                trace_id=trace_id,
                tool_name="classroom.reserve_room",
                action="human_rejected",
                arguments={"approval_id": str(approval_id)},
                result={"executed": False},
                status="rejected",
                requires_approval=True,
            )
            self.session.commit()
            return ClassroomResumeResult(
                approval_id=str(approval_id),
                trace_id=trace_id,
                actor_user_id=str(actor),
                status=ClassroomActionStatus.REJECTED,
                answer="已取消这次教室预约，reserve_room() 未执行。",
                audit=audit,
            )

        if status != ClassroomActionStatus.AWAITING_APPROVAL.value:
            raise ClassroomActionConflict("approval request is not awaiting approval")
        AuthorizationService(self.session).require("classroom.reserve", actor)
        intent = self._intent_from_row(row)
        room = self._candidate_from_row(row, room_id)
        self.repository.lock_room_slot(room.room_id, intent.reservation_date)
        occupied = self.repository.occupied_room_ids(intent)
        if room.room_id in occupied:
            self.session.rollback()
            raise ClassroomActionConflict(
                f"{room.room_name} 在审批期间已被占用；请重新搜索候选教室"
            )

        reservation = self.repository.insert_reservation(
            approval_id=approval_id,
            actor_user_id=actor,
            room=room,
            intent=intent,
        )
        self.repository.set_request_status(
            approval_id,
            status=ClassroomActionStatus.EXECUTED,
            selected_resource_id=room.room_id,
        )
        audit = self.audit.record(
            actor_user_id=actor,
            trace_id=trace_id,
            tool_name="classroom.reserve_room",
            action="execute_reservation",
            arguments={"approval_id": str(approval_id), "room_id": room.room_id},
            result=reservation,
            status="executed",
            requires_approval=True,
        )
        self.session.commit()
        return ClassroomResumeResult(
            approval_id=str(approval_id),
            trace_id=trace_id,
            actor_user_id=str(actor),
            status=ClassroomActionStatus.EXECUTED,
            answer=(
                f"预约成功：{room.building} {room.room_name}，"
                f"{intent.reservation_date.isoformat()} "
                f"{intent.start_time.strftime('%H:%M')}-{intent.end_time.strftime('%H:%M')}，"
                f"人数 {intent.capacity}。"
            ),
            reservation=reservation,
            audit=audit,
        )

    def retry_prepare_audit(self, approval_id, actor_user_id, *, trace_id) -> dict:
        actor = self.repository.ensure_actor(actor_user_id)
        AuthorizationService(self.session).require("classroom.reserve", actor)
        _require_trace_owner(self.session, trace_id, actor)
        row = self.repository.get_request_for_update(approval_id)
        if row["actor_user_id"] != actor:
            self.session.rollback()
            raise ClassroomActionOwnershipError("approval request does not belong to actor_user_id")
        request = dict(row["request_json"] or {})
        candidates = list(row["candidates_json"] or [])
        audit = self.audit.record(
            actor_user_id=actor,
            trace_id=trace_id,
            tool_name="classroom.search_available_rooms",
            action="prepare_reservation",
            arguments=request,
            result={"approval_id": str(approval_id), "candidate_count": len(candidates)},
            status="pending",
            requires_approval=True,
        )
        self.session.commit()
        return audit

    def list_reservations(self, actor_user_id) -> list[dict]:
        AuthorizationService(self.session).require("classroom.reserve", actor_user_id)
        rows = self.repository.list_actor_reservations(actor_user_id)
        return [self._reservation_json(row) for row in rows]

# ---- app/campus_tools/library.py ----
library_metadata = MetaData()

library_books = Table(
    "library_books",
    library_metadata,
    Column("id", Uuid(as_uuid=True), primary_key=True),
    Column("book_code", String(40), nullable=False, unique=True, index=True),
    Column("title", String(300), nullable=False, index=True),
    Column("author", String(200), nullable=False),
    Column("isbn", String(40), nullable=True),
    Column("subject", String(160), nullable=True, index=True),
    Column("location", String(160), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

library_inventory = Table(
    "library_inventory",
    library_metadata,
    Column("id", Uuid(as_uuid=True), primary_key=True),
    Column("book_id", Uuid(as_uuid=True), nullable=False, unique=True, index=True),
    Column("total_copies", Integer, nullable=False),
    Column("available_copies", Integer, nullable=False),
    Column("reserved_copies", Integer, nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

library_reservations = Table(
    "library_reservations",
    library_metadata,
    Column("id", Uuid(as_uuid=True), primary_key=True),
    Column("action_request_id", Uuid(as_uuid=True), nullable=False, unique=True),
    Column("actor_user_id", Uuid(as_uuid=True), nullable=False, index=True),
    Column("book_id", Uuid(as_uuid=True), nullable=False, index=True),
    Column("book_code", String(40), nullable=False),
    Column("title", String(300), nullable=False),
    Column("status", String(32), nullable=False),
    Column("pickup_expires_at", DateTime(timezone=True), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

library_loans = Table(
    "library_loans",
    library_metadata,
    Column("id", Uuid(as_uuid=True), primary_key=True),
    Column("actor_user_id", Uuid(as_uuid=True), nullable=False, index=True),
    Column("book_id", Uuid(as_uuid=True), nullable=False, index=True),
    Column("status", String(32), nullable=False),
    Column("borrowed_at", DateTime(timezone=True), nullable=False),
    Column("due_at", DateTime(timezone=True), nullable=False),
    Column("returned_at", DateTime(timezone=True), nullable=True),
)


class LibraryIntentParser:
    _CN_TITLE_RE = re.compile(r"《([^》]{1,300})》")
    _QUOTE_RE = re.compile(r'["“]([^"”]{2,300})["”]')
    _STOP = (
        "帮我",
        "这本书",
        "图书馆",
        "图书",
        "书籍",
        "有没有",
        "查找",
        "搜索",
        "查询",
        "预约",
        "预订",
        "借阅",
        "库存",
        "馆藏",
        "一下",
        "请",
        "本书",
        "找",
        "借",
        "书",
    )


    def parse(self, query: str) -> LibraryIntent:
        raw = (query or "").strip()
        match = self._CN_TITLE_RE.search(raw) or self._QUOTE_RE.search(raw)
        title_hint = match.group(1).strip() if match else None

        normalized = raw
        if title_hint:
            normalized = normalized.replace(f"《{title_hint}》", " ")
            normalized = normalized.replace(f'"{title_hint}"', " ")
            normalized = normalized.replace(f'“{title_hint}”', " ")
        for token in self._STOP:
            normalized = normalized.replace(token, " ")
        normalized = re.sub(r"[，。！？、,:：;；()（）]", " ", normalized)
        keywords = [item for item in normalized.split() if len(item) >= 2]
        if title_hint and title_hint not in keywords:
            keywords.insert(0, title_hint)
        return LibraryIntent(query=raw, title_hint=title_hint, keywords=keywords[:8])


class LibraryActionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    @staticmethod
    def _as_uuid(value) -> uuid.UUID:
        return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))

    def ensure_actor(self, actor_user_id) -> uuid.UUID:
        actor = self._as_uuid(actor_user_id)
        if self.session.scalar(select(User.id).where(User.id == actor, User.status == "active")) is None:
            raise ClassroomActionOwnershipError(f"unknown actor_user_id={actor}")
        return actor

    def search_books(self, intent: LibraryIntent, *, limit: int = 8, available_only: bool = False) -> list[dict]:
        stmt = (
            select(
                library_books.c.id,
                library_books.c.book_code,
                library_books.c.title,
                library_books.c.author,
                library_books.c.isbn,
                library_books.c.subject,
                library_books.c.location,
                library_inventory.c.total_copies,
                library_inventory.c.available_copies,
                library_inventory.c.reserved_copies,
            )
            .join(library_inventory, library_inventory.c.book_id == library_books.c.id)
        )
        if available_only:
            stmt = stmt.where(library_inventory.c.available_copies > 0)

        clauses = []
        search_text = (intent.title_hint or intent.query).strip()
        whole_title_match = library_books.c.title.ilike(f"%{search_text}%") if search_text else None
        if whole_title_match is not None:
            clauses.append(whole_title_match)
        for keyword in intent.keywords:
            like = f"%{keyword}%"
            clauses.extend(
                [
                    library_books.c.title.ilike(like),
                    library_books.c.author.ilike(like),
                    library_books.c.subject.ilike(like),
                ]
            )
        if clauses:
            stmt = stmt.where(or_(*clauses))

        if whole_title_match is not None:
            stmt = stmt.order_by(
                case((whole_title_match, 0), else_=1),
                library_inventory.c.available_copies.desc(),
                library_books.c.title.asc(),
            )
        else:
            stmt = stmt.order_by(
                library_inventory.c.available_copies.desc(),
                library_books.c.title.asc(),
            )
        stmt = stmt.limit(limit)
        return [dict(row) for row in self.session.execute(stmt).mappings().all()]

    def inventory(self, book_id) -> dict | None:
        book_uuid = self._as_uuid(book_id)
        row = self.session.execute(
            select(
                library_books.c.id,
                library_books.c.book_code,
                library_books.c.title,
                library_books.c.author,
                library_books.c.isbn,
                library_books.c.subject,
                library_books.c.location,
                library_inventory.c.total_copies,
                library_inventory.c.available_copies,
                library_inventory.c.reserved_copies,
            )
            .join(library_inventory, library_inventory.c.book_id == library_books.c.id)
            .where(library_books.c.id == book_uuid)
        ).mappings().one_or_none()
        return dict(row) if row else None

    def create_request(
        self,
        *,
        actor_user_id: uuid.UUID,
        trace_id,
        intent: LibraryIntent,
        candidates: list[LibraryBookCandidate],
        expires_at: datetime,
    ) -> uuid.UUID:
        approval_id = uuid.uuid4()
        trace_uuid = self._as_uuid(trace_id) if trace_id else None
        now = datetime.now(UTC)
        self.session.execute(
            insert(action_requests).values(
                id=approval_id,
                trace_id=trace_uuid,
                actor_user_id=actor_user_id,
                action_type="reserve_library_book",
                status=(
                    ClassroomActionStatus.AWAITING_APPROVAL.value
                    if candidates
                    else ClassroomActionStatus.REJECTED.value
                ),
                request_json=intent.model_dump(mode="json"),
                candidates_json=[item.model_dump(mode="json") for item in candidates],
                expires_at=expires_at,
                created_at=now,
                updated_at=now,
            )
        )
        return approval_id

    # latest_pending_library_approval_v129
    def latest_pending_request_id(
        self,
        actor_user_id,
    ):
        actor = self.ensure_actor(actor_user_id)

        return self.session.scalar(
            select(action_requests.c.id)
            .where(
                action_requests.c.actor_user_id == actor,
                action_requests.c.action_type
                == "reserve_library_book",
                action_requests.c.status
                == ClassroomActionStatus.AWAITING_APPROVAL.value,
            )
            .order_by(
                action_requests.c.created_at.desc()
            )
            .limit(1)
        )


    # latest_valid_library_pending_v131
    def latest_valid_pending_request_id(
        self,
        actor_user_id,
    ):
        actor = self.ensure_actor(actor_user_id)

        stmt = (
            select(action_requests.c.id)
            .where(
                action_requests.c.actor_user_id == actor,
                action_requests.c.action_type
                == "reserve_library_book",
                action_requests.c.status
                == ClassroomActionStatus.AWAITING_APPROVAL.value,
                text(
                    "jsonb_array_length("
                    "COALESCE("
                    "campus_action_requests."
                    "candidates_json::jsonb, "
                    "'[]'::jsonb"
                    ")"
                    ") > 0"
                ),
            )
            .order_by(
                action_requests.c.created_at.desc()
            )
            .limit(1)
        )

        return self.session.scalar(stmt)


    def get_request_for_update(self, approval_id) -> dict:
        approval = self._as_uuid(approval_id)
        row = self.session.execute(
            select(action_requests).where(action_requests.c.id == approval).with_for_update()
        ).mappings().one_or_none()
        if row is None:
            raise ClassroomActionNotFound(f"approval_id={approval} was not found")
        value = dict(row)
        if value.get("action_type") != "reserve_library_book":
            raise ClassroomActionConflict("approval request is not a library-book reservation")
        return value

    def set_request_status(
        self,
        approval_id,
        *,
        status: ClassroomActionStatus,
        selected_resource_id: str | None = None,
    ) -> None:
        self.session.execute(
            update(action_requests)
            .where(action_requests.c.id == self._as_uuid(approval_id))
            .values(
                status=status.value,
                selected_resource_id=selected_resource_id,
                updated_at=datetime.now(UTC),
            )
        )

    def existing_reservation(self, approval_id) -> dict | None:
        row = self.session.execute(
            select(library_reservations).where(
                library_reservations.c.action_request_id == self._as_uuid(approval_id)
            )
        ).mappings().one_or_none()
        return dict(row) if row else None

    def lock_inventory(self, book_id) -> dict:
        book_uuid = self._as_uuid(book_id)
        self.session.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
            {"lock_key": f"campusmind:library:{book_uuid}"},
        )
        row = self.session.execute(
            select(library_inventory)
            .where(library_inventory.c.book_id == book_uuid)
            .with_for_update()
        ).mappings().one_or_none()
        if row is None:
            raise ClassroomActionConflict("library inventory row is missing")
        return dict(row)

    def insert_reservation(
        self,
        *,
        approval_id,
        actor_user_id,
        candidate: LibraryBookCandidate,
        pickup_ttl_days: int,
    ) -> dict:
        reservation_id = uuid.uuid4()
        now = datetime.now(UTC)
        pickup_expires_at = now + timedelta(days=pickup_ttl_days)
        self.session.execute(
            insert(library_reservations).values(
                id=reservation_id,
                action_request_id=self._as_uuid(approval_id),
                actor_user_id=self._as_uuid(actor_user_id),
                book_id=self._as_uuid(candidate.book_id),
                book_code=candidate.book_code,
                title=candidate.title,
                status="ready_for_pickup",
                pickup_expires_at=pickup_expires_at,
                created_at=now,
            )
        )
        self.session.execute(
            update(library_inventory)
            .where(library_inventory.c.book_id == self._as_uuid(candidate.book_id))
            .values(
                available_copies=library_inventory.c.available_copies - 1,
                reserved_copies=library_inventory.c.reserved_copies + 1,
                updated_at=now,
            )
        )
        return {
            "reservation_id": str(reservation_id),
            "book_id": candidate.book_id,
            "book_code": candidate.book_code,
            "title": candidate.title,
            "author": candidate.author,
            "location": candidate.location,
            "status": "ready_for_pickup",
            "pickup_expires_at": pickup_expires_at.isoformat(),
        }

    def list_actor_reservations(self, actor_user_id) -> list[dict]:
        actor = self.ensure_actor(actor_user_id)
        rows = self.session.execute(
            select(library_reservations)
            .where(library_reservations.c.actor_user_id == actor)
            .order_by(library_reservations.c.created_at.desc())
        ).mappings().all()
        return [dict(row) for row in rows]

    def list_active_loans(self, actor_user_id) -> list[dict]:
        actor = self.ensure_actor(actor_user_id)
        rows = self.session.execute(
            select(
                library_loans.c.id,
                library_loans.c.book_id,
                library_loans.c.status,
                library_loans.c.borrowed_at,
                library_loans.c.due_at,
                library_books.c.book_code,
                library_books.c.title,
                library_books.c.author,
                library_books.c.location,
            )
            .join(library_books, library_books.c.id == library_loans.c.book_id)
            .where(
                library_loans.c.actor_user_id == actor,
                library_loans.c.status == "borrowed",
            )
            .order_by(library_loans.c.due_at.asc())
        ).mappings().all()
        return [dict(row) for row in rows]


class LibraryActionService:
    """library tools PostgreSQL Library Tool with the classroom HITL workflow HITL action protocol."""

    def __init__(
        self,
        session: Session,
        *,
        parser=None,
        approval_ttl_minutes: int = 30,
        pickup_ttl_days: int = 3,
    ) -> None:
        self.session = session
        self.parser = parser or LibraryIntentParser()
        self.repository = LibraryActionRepository(session)
        self.audit = LegacyAuditMirror(session)
        self.approval_ttl_minutes = approval_ttl_minutes
        self.pickup_ttl_days = pickup_ttl_days

    @staticmethod
    def supports(query: str) -> bool:
        q = "".join((query or "").lower().split())

        # approval_control_is_not_prepare_v131
        control_markers = (
            "\u786e\u8ba4\u6267\u884c",
            "\u786e\u8ba4\u9884\u7ea6",
            "\u53d6\u6d88",
            "\u62d2\u7edd",
            "\u4e0d\u540c\u610f",
            "\u540c\u610f\u6267\u884c",
            "\u6279\u51c6\u6267\u884c",
            "approval_id",
        )

        if any(
            token in q
            for token in control_markers
        ):
            return False
        library_tokens = ("图书", "图书馆", "书籍", "这本书", "本书", "馆藏", "库存")
        action_tokens = ("预约", "预订", "借", "借阅", "找", "搜索", "查询", "有没有")
        return any(token in q for token in library_tokens) and any(token in q for token in action_tokens)

    @staticmethod
    def _candidate(row: dict) -> LibraryBookCandidate:
        return LibraryBookCandidate(
            book_id=str(row["id"]),
            book_code=row["book_code"],
            title=row["title"],
            author=row["author"],
            isbn=row.get("isbn"),
            subject=row.get("subject"),
            location=row["location"],
            total_copies=int(row["total_copies"]),
            available_copies=int(row["available_copies"]),
        )

    def search_book(self, query: str, *, available_only: bool = False, limit: int = 8) -> list[dict]:
        intent = self.parser.parse(query)
        return [
            self._candidate(row).model_dump(mode="json")
            for row in self.repository.search_books(intent, limit=limit, available_only=available_only)
        ]

    def check_book_inventory(self, book_id) -> dict:
        row = self.repository.inventory(book_id)
        if row is None:
            raise ClassroomActionNotFound(f"book_id={book_id} was not found")
        result = self._candidate(row).model_dump(mode="json")
        result["reserved_copies"] = int(row["reserved_copies"])
        return result

    def recommend_books(self, query: str, *, limit: int = 5) -> list[dict]:
        intent = self.parser.parse(query)
        rows = self.repository.search_books(intent, limit=limit, available_only=False)
        return [self._candidate(row).model_dump(mode="json") for row in rows]

    def get_borrowed_books(self, actor_user_id) -> list[dict]:
        rows = self.repository.list_active_loans(actor_user_id)
        result: list[dict] = []
        for row in rows:
            result.append(
                {
                    "loan_id": str(row["id"]),
                    "book_id": str(row["book_id"]),
                    "book_code": row["book_code"],
                    "title": row["title"],
                    "author": row["author"],
                    "location": row["location"],
                    "status": row["status"],
                    "borrowed_at": row["borrowed_at"].isoformat(),
                    "due_at": row["due_at"].isoformat(),
                }
            )
        return result

    def prepare_reservation(self, query: str, actor_user_id, *, trace_id=None) -> LibraryPrepareResult:
        if not self.supports(query):
            raise ClassroomActionError("library tools Library Tool does not recognize this request")
        actor = self.repository.ensure_actor(actor_user_id)
        AuthorizationService(self.session).require("library.reserve", actor)
        _require_trace_owner(self.session, trace_id, actor)
        intent = self.parser.parse(query)
        candidates = [
            self._candidate(row)
            for row in self.repository.search_books(intent, limit=5, available_only=True)
        ]
        expires_at = datetime.now(UTC) + timedelta(minutes=self.approval_ttl_minutes)
        approval_id = self.repository.create_request(
            actor_user_id=actor,
            trace_id=trace_id,
            intent=intent,
            candidates=candidates,
            expires_at=expires_at,
        )

        if candidates:
            first = candidates[0]
            lines = [
                f"找到 {len(candidates)} 本有可预约库存的候选图书；当前还没有执行预约。",
                *[
                    f"{idx}. 《{item.title}》 / {item.author}（可用 {item.available_copies}/{item.total_copies}，book_id={item.book_id}）"
                    for idx, item in enumerate(candidates, start=1)
                ],
                f"推荐《{first.title}》。确认后才会执行 reserve_book()。",
                f"approval_id={approval_id}",
            ]
        else:
            lines = [
                "没有找到当前可预约库存的匹配图书，因此不会执行预约。",
                f"approval_id={approval_id}",
            ]

        audit = self.audit.record(
            actor_user_id=actor,
            trace_id=trace_id,
            tool_name="library.search_book",
            action="prepare_book_reservation",
            arguments=intent.model_dump(mode="json"),
            result={"approval_id": str(approval_id), "candidate_count": len(candidates)},
            status="pending",
            requires_approval=True,
            resource_type="library_book",
        )
        self.session.commit()
        return LibraryPrepareResult(
            approval_id=str(approval_id),
            trace_id=str(trace_id) if trace_id else None,
            actor_user_id=str(actor),
            answer="\n".join(lines),
            requested=intent,
            candidates=candidates,
            expires_at=expires_at.isoformat(),
            audit=audit,
        )

    @staticmethod
    def _candidate_from_row(row: dict, book_id: str | None) -> LibraryBookCandidate:
        candidates = [LibraryBookCandidate(**item) for item in row.get("candidates_json") or []]
        if not candidates:
            raise ClassroomActionConflict("approval request has no reservable book candidates")
        if book_id is None:
            return candidates[0]
        for item in candidates:
            if item.book_id == str(book_id) or item.book_code == str(book_id):
                return item
        raise ClassroomActionConflict("selected book_id is not part of the approved candidate set")

    @staticmethod
    def _reservation_json(row: dict) -> dict:
        return {
            "reservation_id": str(row["id"]),
            "book_id": str(row["book_id"]),
            "book_code": row["book_code"],
            "title": row["title"],
            "status": row["status"],
            "pickup_expires_at": row["pickup_expires_at"].isoformat(),
        }

    def resume_reservation(
        self,
        approval_id,
        actor_user_id,
        *,
        approved: bool,
        book_id: str | None = None,
    ) -> LibraryResumeResult:
        actor = self.repository.ensure_actor(actor_user_id)
        AuthorizationService(self.session).require("library.reserve", actor)
        row = self.repository.get_request_for_update(approval_id)
        if row["actor_user_id"] != actor:
            self.session.rollback()
            raise ClassroomActionOwnershipError("approval request does not belong to actor_user_id")

        if row["action_type"] != "reserve_library_book":
            raise ClassroomActionConflict("approval action type does not match library reservation")
        _require_trace_owner(self.session, row.get("trace_id"), actor)

        trace_id = str(row["trace_id"]) if row.get("trace_id") else None
        status = row["status"]
        existing = self.repository.existing_reservation(approval_id)
        if status == ClassroomActionStatus.EXECUTED.value and existing:
            self.session.rollback()
            reservation = self._reservation_json(existing)
            return LibraryResumeResult(
                approval_id=str(approval_id),
                trace_id=trace_id,
                actor_user_id=str(actor),
                status=ClassroomActionStatus.EXECUTED,
                answer=f"该审批已执行过：《{reservation['title']}》已经预约，无需重复提交。",
                reservation=reservation,
                state_changed=False,
                idempotent=True,
            )
        if status == ClassroomActionStatus.REJECTED.value:
            self.session.rollback()
            return LibraryResumeResult(
                approval_id=str(approval_id),
                trace_id=trace_id,
                actor_user_id=str(actor),
                status=ClassroomActionStatus.REJECTED,
                answer="该审批已经取消，不会执行图书预约。",
                state_changed=False,
                idempotent=True,
            )

        now = datetime.now(UTC)
        expires_at = row["expires_at"]
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at <= now:
            self.repository.set_request_status(approval_id, status=ClassroomActionStatus.EXPIRED)
            self.session.commit()
            raise ClassroomActionExpired("approval request has expired; create a new library search")

        if not approved:
            self.repository.set_request_status(approval_id, status=ClassroomActionStatus.REJECTED)
            audit = self.audit.record(
                actor_user_id=actor,
                trace_id=trace_id,
                tool_name="library.reserve_book",
                action="human_rejected",
                arguments={"approval_id": str(approval_id)},
                result={"executed": False},
                status="rejected",
                requires_approval=True,
                resource_type="library_book",
            )
            self.session.commit()
            return LibraryResumeResult(
                approval_id=str(approval_id),
                trace_id=trace_id,
                actor_user_id=str(actor),
                status=ClassroomActionStatus.REJECTED,
                answer="已取消这次图书预约，reserve_book() 未执行。",
                audit=audit,
            )

        if status != ClassroomActionStatus.AWAITING_APPROVAL.value:
            raise ClassroomActionConflict("approval request is not awaiting approval")
        AuthorizationService(self.session).require("library.reserve", actor)
        candidate = self._candidate_from_row(row, book_id)
        inventory = self.repository.lock_inventory(candidate.book_id)
        if int(inventory["available_copies"]) <= 0:
            self.session.rollback()
            raise ClassroomActionConflict(
                f"《{candidate.title}》在审批期间已无可用库存；请重新搜索图书"
            )

        reservation = self.repository.insert_reservation(
            approval_id=approval_id,
            actor_user_id=actor,
            candidate=candidate,
            pickup_ttl_days=self.pickup_ttl_days,
        )
        self.repository.set_request_status(
            approval_id,
            status=ClassroomActionStatus.EXECUTED,
            selected_resource_id=candidate.book_id,
        )
        audit = self.audit.record(
            actor_user_id=actor,
            trace_id=trace_id,
            tool_name="library.reserve_book",
            action="execute_book_reservation",
            arguments={"approval_id": str(approval_id), "book_id": candidate.book_id},
            result=reservation,
            status="executed",
            requires_approval=True,
            resource_type="library_book",
            resource_id=candidate.book_id,
        )
        self.session.commit()
        return LibraryResumeResult(
            approval_id=str(approval_id),
            trace_id=trace_id,
            actor_user_id=str(actor),
            status=ClassroomActionStatus.EXECUTED,
            answer=(
                f"预约成功：《{candidate.title}》 / {candidate.author}。"
                f"取书地点：{candidate.location}；请在预约保留期内取书。"
            ),
            reservation=reservation,
            audit=audit,
        )

    def retry_prepare_audit(self, approval_id, actor_user_id, *, trace_id) -> dict:
        actor = self.repository.ensure_actor(actor_user_id)
        AuthorizationService(self.session).require("library.reserve", actor)
        _require_trace_owner(self.session, trace_id, actor)
        row = self.repository.get_request_for_update(approval_id)
        if row["actor_user_id"] != actor:
            self.session.rollback()
            raise ClassroomActionOwnershipError("approval request does not belong to actor_user_id")
        request = dict(row["request_json"] or {})
        candidates = list(row["candidates_json"] or [])
        audit = self.audit.record(
            actor_user_id=actor,
            trace_id=trace_id,
            tool_name="library.search_book",
            action="prepare_book_reservation",
            arguments=request,
            result={"approval_id": str(approval_id), "candidate_count": len(candidates)},
            status="pending",
            requires_approval=True,
            resource_type="library_book",
        )
        self.session.commit()
        return audit

    def list_reservations(self, actor_user_id) -> list[dict]:
        rows = self.repository.list_actor_reservations(actor_user_id)
        return [self._reservation_json(row) for row in rows]
