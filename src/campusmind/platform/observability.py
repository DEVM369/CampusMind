from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from datetime import datetime, timezone
import uuid
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

"""CampusMind observability domain."""

# ---- app/observability/extraction.py ----
_SECRET_KEYS = {
    "api_key",
    "apikey",
    "authorization",
    "password",
    "secret",
    "token",
    "access_token",
    "refresh_token",
}


def _enum_value(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, Enum):
        return str(value.value)
    return str(getattr(value, "value", value))


def _get(value: Any, name: str, default=None):
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _first(value: Any, names: tuple[str, ...]):
    for name in names:
        item = _get(value, name, None)
        if item is not None:
            return item
    return None


def _answer_text(value: Any) -> str:
    """Extract only explicit CampusMind answer-bearing fields.

    Agent Runtime versions may expose the final answer at the top level or
    inside writer/finalize output. Arbitrary content is never promoted to an
    answer.
    """

    for name in (
        "answer",
        "final_answer",
        "draft_answer",
        "response_text",
        "final_response",
    ):
        item = _get(value, name, None)
        if isinstance(item, str) and item.strip():
            return item.strip()

    return ""


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return max(0.0, number)


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return max(0, number)


def sanitize_payload(value: Any, *, depth: int = 0) -> Any:
    """Return a JSON-friendly, shallowly bounded representation.

    Observability must never become a new secret-leak path. Known credential keys
    are redacted and arbitrary objects are represented conservatively.
    """

    if depth > 5:
        return "<max-depth>"
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        result = {}
        for raw_key, raw_value in list(value.items())[:100]:
            key = str(raw_key)
            if key.lower() in _SECRET_KEYS:
                result[key] = "<redacted>"
            else:
                result[key] = sanitize_payload(raw_value, depth=depth + 1)
        return result
    if isinstance(value, (list, tuple, set)):
        return [sanitize_payload(item, depth=depth + 1) for item in list(value)[:100]]
    if hasattr(value, "model_dump"):
        try:
            return sanitize_payload(value.model_dump(mode="json"), depth=depth + 1)
        except Exception:
            pass
    return str(value)


def _chunk_id(value: Any) -> str | None:
    for name in ("chunk_id", "source_chunk_id"):
        item = _get(value, name, None)
        if item is not None:
            return str(item)
    nested = _get(value, "chunk", None)
    if nested is not None and nested is not value:
        return _chunk_id(nested)
    return None


def _content(value: Any) -> str | None:
    item = _get(value, "content", None)
    if item:
        return str(item)
    nested = _get(value, "chunk", None)
    if nested is not None and nested is not value:
        return _content(nested)
    return None


def _graph_tokens(value: Any) -> list[str]:
    tokens: list[str] = []
    relation = _enum_value(_get(value, "relation_type", None))
    if relation:
        tokens.append(relation)
    for name in ("source_name", "target_name", "path_text"):
        item = _get(value, name, None)
        if item:
            tokens.append(str(item))
    return tokens


@dataclass(slots=True)
class TraceStepSnapshot:
    name: str
    component: str
    status: str = "completed"
    duration_ms: float | None = None
    input_json: dict[str, Any] = field(default_factory=dict)
    output_json: dict[str, Any] = field(default_factory=dict)
    metrics_json: dict[str, Any] = field(default_factory=dict)
    error_type: str | None = None
    error_message: str | None = None


@dataclass(slots=True)
class ResultSnapshot:
    answer: str = ""
    status: str = "completed"
    route: str | None = None
    latency_ms: float | None = None
    retries: int | None = None
    pending_approval: bool | None = None
    token_input: int | None = None
    token_output: int | None = None
    token_total: int | None = None
    token_cost: float | None = None
    evidence_ids: list[str] = field(default_factory=list)
    evidence_texts: list[str] = field(default_factory=list)
    graph_path_tokens: list[str] = field(default_factory=list)
    steps: list[TraceStepSnapshot] = field(default_factory=list)


def _component_for_step(name: str) -> str:
    lowered = name.lower()
    if "router" in lowered or "intent" in lowered or "complexity" in lowered:
        return "router"
    if "planner" in lowered or "decomposer" in lowered:
        return "planner"
    if "retriev" in lowered or "vector" in lowered or "keyword" in lowered or "rerank" in lowered:
        return "retrieval"
    if "graph" in lowered:
        return "graph"
    if "tool" in lowered or "approval" in lowered:
        return "tool"
    if "writer" in lowered or "rewrite" in lowered:
        return "writer"
    if "critic" in lowered or "validator" in lowered:
        return "validation"
    if "final" in lowered:
        return "finalize"
    return "agent"


def _step_snapshot(value: Any) -> TraceStepSnapshot | None:
    name = _first(value, ("step_name", "name", "node", "stage"))
    if not name:
        return None
    name = str(name)
    status = str(_first(value, ("status", "state")) or "completed")
    duration = _float_or_none(_first(value, ("duration_ms", "elapsed_ms", "latency_ms")))
    error = _first(value, ("error", "error_message", "failure_reason"))
    error_type = _first(value, ("error_type", "exception_type"))
    if error and status == "completed":
        status = "failed"
    input_value = _first(value, ("input_json", "input", "inputs"))
    output_value = _first(value, ("output_json", "output", "result", "details", "metadata"))
    metrics = _first(value, ("metrics_json", "metrics"))
    return TraceStepSnapshot(
        name=name,
        component=_component_for_step(name),
        status=status,
        duration_ms=duration,
        input_json=sanitize_payload(input_value) if isinstance(sanitize_payload(input_value), dict) else {},
        output_json=sanitize_payload(output_value) if isinstance(sanitize_payload(output_value), dict) else {},
        metrics_json=sanitize_payload(metrics) if isinstance(sanitize_payload(metrics), dict) else {},
        error_type=str(error_type) if error_type else None,
        error_message=str(error) if error else None,
    )


def extract_result_snapshot(result: Any) -> ResultSnapshot:
    """Extract observable facts from existing CampusMind result objects.

    The extractor is intentionally tolerant across agent runtime-25 result shapes. It
    never invents latency, tokens, evidence or graph paths; missing values remain
    missing so benchmark/observability data stays auditable.
    """

    snapshot = ResultSnapshot()
    snapshot.answer = _answer_text(result)
    snapshot.status = str(_get(result, "status", "completed") or "completed")
    snapshot.latency_ms = _float_or_none(_first(result, ("elapsed_ms", "latency_ms", "duration_ms")))
    snapshot.retries = _int_or_none(_first(result, ("retry_count", "retries")))
    pending = _get(result, "pending_approval", None)
    snapshot.pending_approval = bool(pending) if pending is not None else None

    route = _first(result, ("executed_route", "active_route", "planned_route"))
    if route is None:
        decision = _get(result, "decision", None)
        route = _get(decision, "route", None) if decision is not None else None
    snapshot.route = _enum_value(route)

    snapshot.token_input = _int_or_none(_first(result, ("input_tokens", "prompt_tokens")))
    snapshot.token_output = _int_or_none(_first(result, ("output_tokens", "completion_tokens")))
    snapshot.token_total = _int_or_none(_first(result, ("total_tokens", "token_total")))
    snapshot.token_cost = _float_or_none(_first(result, ("token_cost", "cost", "cost_usd")))

    evidence_ids: list[str] = []
    evidence_texts: list[str] = []
    graph_tokens: list[str] = []
    steps: list[TraceStepSnapshot] = []
    seen_steps: set[tuple[str, float | None, str]] = set()

    containers = [result]
    for name in (
        "retrieval",
        "result",
        "adaptive_result",
        "retrieval_result",
        "evidence_hits",
        "citations",
        "graph_paths",
        "steps",
        "subquery_executions",
    ):
        value = _get(result, name, None)
        if value is not None:
            containers.append(value)

    visited: set[int] = set()

    def walk(value: Any, depth: int = 0) -> None:
        if value is None or depth > 6:
            return
        if isinstance(value, (str, int, float, bool, bytes, Enum)):
            return
        marker = id(value)
        if marker in visited:
            return
        visited.add(marker)

        if isinstance(value, dict):
            if not snapshot.answer:
                nested_answer = _answer_text(value)
                if nested_answer:
                    snapshot.answer = nested_answer

            if snapshot.route is None:
                nested_route = _first(
                    value,
                    (
                        "executed_route",
                        "active_route",
                        "planned_route",
                    ),
                )
                if nested_route is not None:
                    snapshot.route = _enum_value(
                        nested_route
                    )

            # IMPORTANT:
            # Agent step output is often serialized as dict.
            # Interpret the dict itself BEFORE walking scalar values,
            # otherwise chunk_id/path_text/relation_type are lost.
            cid = _chunk_id(value)
            if cid and cid not in evidence_ids:
                evidence_ids.append(cid)

            content = _content(value)
            if content and content not in evidence_texts:
                evidence_texts.append(content)

            for token in _graph_tokens(value):
                if token not in graph_tokens:
                    graph_tokens.append(token)

            step = _step_snapshot(value)
            if step is not None:
                key = (
                    step.name,
                    step.duration_ms,
                    step.status,
                )
                if key not in seen_steps:
                    seen_steps.add(key)
                    steps.append(step)

            for item in list(value.values())[:150]:
                walk(item, depth + 1)

            return
        if isinstance(value, (list, tuple, set)):
            for item in list(value)[:150]:
                walk(item, depth + 1)
            return

        # Agent writer/finalize may keep the final answer in a nested
        # result object instead of exposing result.answer.
        if not snapshot.answer:
            nested_answer = _answer_text(value)
            if nested_answer:
                snapshot.answer = nested_answer

        if snapshot.route is None:
            nested_route = _first(
                value,
                (
                    "executed_route",
                    "active_route",
                    "planned_route",
                ),
            )
            if nested_route is not None:
                snapshot.route = _enum_value(
                    nested_route
                )

        cid = _chunk_id(value)
        if cid and cid not in evidence_ids:
            evidence_ids.append(cid)
        content = _content(value)
        if content and content not in evidence_texts:
            evidence_texts.append(content)

        for token in _graph_tokens(value):
            if token not in graph_tokens:
                graph_tokens.append(token)

        step = _step_snapshot(value)
        if step is not None:
            key = (step.name, step.duration_ms, step.status)
            if key not in seen_steps:
                seen_steps.add(key)
                steps.append(step)

        # Traverse only known result-bearing attributes. This avoids accidentally
        # walking SQLAlchemy sessions, clients, locks or provider internals.
        for name in (
            "chunk",
            "evidence_hits",
            "citations",
            "graph_paths",
            "retrieval",
            "result",
            "adaptive_result",
            "retrieval_result",
            "output",
            "output_json",
            "details",
            "metadata",
            "subquery_executions",
            "steps",
            "state",
            "final_state",
            "response",
        ):
            nested = _get(value, name, None)
            if nested is not None and nested is not value:
                walk(nested, depth + 1)

    for container in containers:
        walk(container)

    snapshot.evidence_ids = evidence_ids
    snapshot.evidence_texts = evidence_texts
    snapshot.graph_path_tokens = graph_tokens
    snapshot.steps = steps
    return snapshot

# ---- app/observability/repository.py ----
metadata = sa.MetaData()

traces = sa.Table(
    "observability_traces",
    metadata,
    sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
    sa.Column("request_type", sa.String(80), nullable=False),
    sa.Column("system_variant", sa.String(80), nullable=True),
    sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
    sa.Column("query", sa.Text(), nullable=True),
    sa.Column("route", sa.String(40), nullable=True),
    sa.Column("status", sa.String(32), nullable=False),
    sa.Column("total_latency_ms", sa.Float(), nullable=True),
    sa.Column("retries", sa.Integer(), nullable=True),
    sa.Column("token_input", sa.Integer(), nullable=True),
    sa.Column("token_output", sa.Integer(), nullable=True),
    sa.Column("token_total", sa.Integer(), nullable=True),
    sa.Column("token_cost", sa.Float(), nullable=True),
    sa.Column("error_type", sa.String(160), nullable=True),
    sa.Column("error_message", sa.Text(), nullable=True),
    sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
)

spans = sa.Table(
    "observability_spans",
    metadata,
    sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
    sa.Column("trace_id", postgresql.UUID(as_uuid=True), nullable=False),
    sa.Column("parent_span_id", postgresql.UUID(as_uuid=True), nullable=True),
    sa.Column("span_name", sa.String(160), nullable=False),
    sa.Column("component", sa.String(80), nullable=False),
    sa.Column("status", sa.String(32), nullable=False),
    sa.Column("duration_ms", sa.Float(), nullable=True),
    sa.Column("input_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column("output_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column("metrics_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column("error_type", sa.String(160), nullable=True),
    sa.Column("error_message", sa.Text(), nullable=True),
    sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
)


def _uuid(value):
    if value is None or isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))


class ObservabilityRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_trace(
        self,
        *,
        request_type: str,
        system_variant: str | None = None,
        actor_user_id=None,
        query: str | None = None,
        metadata_json=None,
    ) -> uuid.UUID:
        trace_id = uuid.uuid4()
        self.session.execute(
            traces.insert().values(
                id=trace_id,
                request_type=request_type,
                system_variant=system_variant,
                actor_user_id=_uuid(actor_user_id),
                query=query,
                route=None,
                status="running",
                total_latency_ms=None,
                retries=None,
                token_input=None,
                token_output=None,
                token_total=None,
                token_cost=None,
                error_type=None,
                error_message=None,
                metadata_json=dict(metadata_json or {}),
                started_at=datetime.now(timezone.utc),
                completed_at=None,
            )
        )
        self.session.flush()
        return trace_id

    def add_span(
        self,
        *,
        trace_id,
        span_name: str,
        component: str,
        status: str = "completed",
        duration_ms: float | None = None,
        parent_span_id=None,
        input_json=None,
        output_json=None,
        metrics_json=None,
        error_type: str | None = None,
        error_message: str | None = None,
    ) -> uuid.UUID:
        span_id = uuid.uuid4()
        now = datetime.now(timezone.utc)
        self.session.execute(
            spans.insert().values(
                id=span_id,
                trace_id=_uuid(trace_id),
                parent_span_id=_uuid(parent_span_id),
                span_name=span_name,
                component=component,
                status=status,
                duration_ms=duration_ms,
                input_json=dict(input_json or {}),
                output_json=dict(output_json or {}),
                metrics_json=dict(metrics_json or {}),
                error_type=error_type,
                error_message=error_message,
                started_at=now,
                completed_at=now,
            )
        )
        self.session.flush()
        return span_id

    def finish_trace(
        self,
        trace_id,
        *,
        status: str,
        route: str | None = None,
        total_latency_ms: float | None = None,
        retries: int | None = None,
        token_input: int | None = None,
        token_output: int | None = None,
        token_total: int | None = None,
        token_cost: float | None = None,
        error_type: str | None = None,
        error_message: str | None = None,
        metadata_json=None,
    ) -> None:
        values = dict(
            status=status,
            route=route,
            total_latency_ms=total_latency_ms,
            retries=retries,
            token_input=token_input,
            token_output=token_output,
            token_total=token_total,
            token_cost=token_cost,
            error_type=error_type,
            error_message=error_message,
            completed_at=datetime.now(timezone.utc),
        )
        if metadata_json is not None:
            values["metadata_json"] = dict(metadata_json)
        self.session.execute(
            traces.update().where(traces.c.id == _uuid(trace_id)).values(**values)
        )
        self.session.flush()

    def get_trace(self, trace_id):
        row = self.session.execute(
            sa.select(traces).where(traces.c.id == _uuid(trace_id))
        ).mappings().one_or_none()
        return dict(row) if row else None

    def get_spans(self, trace_id):
        rows = self.session.execute(
            sa.select(spans)
            .where(spans.c.trace_id == _uuid(trace_id))
            .order_by(spans.c.started_at.asc(), spans.c.span_name.asc())
        ).mappings().all()
        return [dict(row) for row in rows]

# ---- app/observability/types.py ----
class TraceSpanRecord(BaseModel):
    span_id: str
    trace_id: str
    parent_span_id: str | None = None
    span_name: str
    component: str
    status: str = "completed"
    duration_ms: float | None = Field(default=None, ge=0.0)
    input_json: dict[str, Any] = Field(default_factory=dict)
    output_json: dict[str, Any] = Field(default_factory=dict)
    metrics_json: dict[str, Any] = Field(default_factory=dict)
    error_type: str | None = None
    error_message: str | None = None


class TraceRecord(BaseModel):
    trace_id: str
    request_type: str
    system_variant: str | None = None
    actor_user_id: str | None = None
    query: str | None = None
    route: str | None = None
    status: str = "completed"
    total_latency_ms: float | None = Field(default=None, ge=0.0)
    retries: int | None = Field(default=None, ge=0)
    token_input: int | None = Field(default=None, ge=0)
    token_output: int | None = Field(default=None, ge=0)
    token_total: int | None = Field(default=None, ge=0)
    token_cost: float | None = Field(default=None, ge=0.0)
    error_type: str | None = None
    error_message: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    spans: list[TraceSpanRecord] = Field(default_factory=list)

# ---- app/observability/service.py ----
class ObservabilityService:
    def __init__(self, session) -> None:
        self.repository = ObservabilityRepository(session)

    def persist_result_trace(
        self,
        *,
        result: Any,
        request_type: str,
        system_variant: str | None = None,
        actor_user_id=None,
        query: str | None = None,
        metadata: dict | None = None,
    ) -> TraceRecord:
        snapshot = extract_result_snapshot(result)
        trace_id = self.repository.create_trace(
            request_type=request_type,
            system_variant=system_variant,
            actor_user_id=actor_user_id,
            query=query,
            metadata_json=sanitize_payload(metadata or {}),
        )

        span_records: list[TraceSpanRecord] = []
        root_span_id = self.repository.add_span(
            trace_id=trace_id,
            span_name="request",
            component="runtime",
            status=snapshot.status,
            duration_ms=snapshot.latency_ms,
            input_json={"query": query} if query else {},
            output_json={
                "answer_present": bool(snapshot.answer),
                "evidence_count": len(snapshot.evidence_ids),
                "graph_path_token_count": len(snapshot.graph_path_tokens),
            },
            metrics_json={
                "retry_count": snapshot.retries,
                "token_total": snapshot.token_total,
                "token_cost": snapshot.token_cost,
            },
        )
        span_records.append(
            TraceSpanRecord(
                span_id=str(root_span_id),
                trace_id=str(trace_id),
                span_name="request",
                component="runtime",
                status=snapshot.status,
                duration_ms=snapshot.latency_ms,
                input_json={"query": query} if query else {},
                output_json={
                    "answer_present": bool(snapshot.answer),
                    "evidence_count": len(snapshot.evidence_ids),
                    "graph_path_token_count": len(snapshot.graph_path_tokens),
                },
                metrics_json={
                    "retry_count": snapshot.retries,
                    "token_total": snapshot.token_total,
                    "token_cost": snapshot.token_cost,
                },
            )
        )

        for step in snapshot.steps:
            span_id = self.repository.add_span(
                trace_id=trace_id,
                parent_span_id=root_span_id,
                span_name=step.name,
                component=step.component,
                status=step.status,
                duration_ms=step.duration_ms,
                input_json=step.input_json,
                output_json=step.output_json,
                metrics_json=step.metrics_json,
                error_type=step.error_type,
                error_message=step.error_message,
            )
            span_records.append(
                TraceSpanRecord(
                    span_id=str(span_id),
                    trace_id=str(trace_id),
                    parent_span_id=str(root_span_id),
                    span_name=step.name,
                    component=step.component,
                    status=step.status,
                    duration_ms=step.duration_ms,
                    input_json=step.input_json,
                    output_json=step.output_json,
                    metrics_json=step.metrics_json,
                    error_type=step.error_type,
                    error_message=step.error_message,
                )
            )

        self.repository.finish_trace(
            trace_id,
            status=snapshot.status,
            route=snapshot.route,
            total_latency_ms=snapshot.latency_ms,
            retries=snapshot.retries,
            token_input=snapshot.token_input,
            token_output=snapshot.token_output,
            token_total=snapshot.token_total,
            token_cost=snapshot.token_cost,
            metadata_json={
                **sanitize_payload(metadata or {}),
                "evidence_ids": snapshot.evidence_ids,
                "evidence_texts": snapshot.evidence_texts,
                "graph_path_tokens": snapshot.graph_path_tokens,
                "pending_approval": snapshot.pending_approval,
            },
        )

        return TraceRecord(
            trace_id=str(trace_id),
            request_type=request_type,
            system_variant=system_variant,
            actor_user_id=str(actor_user_id) if actor_user_id is not None else None,
            query=query,
            route=snapshot.route,
            status=snapshot.status,
            total_latency_ms=snapshot.latency_ms,
            retries=snapshot.retries,
            token_input=snapshot.token_input,
            token_output=snapshot.token_output,
            token_total=snapshot.token_total,
            token_cost=snapshot.token_cost,
            metadata_json={
                **sanitize_payload(metadata or {}),
                "evidence_ids": snapshot.evidence_ids,
                "evidence_texts": snapshot.evidence_texts,
                "graph_path_tokens": snapshot.graph_path_tokens,
                "pending_approval": snapshot.pending_approval,
            },
            spans=span_records,
        )
