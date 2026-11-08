from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from campusmind.platform.db import (
    AgentRun,
    AgentStep,
    ToolCall,
    get_db,
)

from campusmind.platform.security import (
    AuthorizationDenied,
    AuthorizationService,
)


router = APIRouter()


def get_authorization_service(
    db: Session = Depends(get_db),
) -> AuthorizationService:
    return AuthorizationService(db)


def _authorize_self(
    authorization: AuthorizationService,
    actor_user_id: uuid.UUID,
) -> None:
    try:
        authorization.require(
            "student.self.read",
            actor_user_id,
        )
    except AuthorizationDenied as exc:
        raise HTTPException(
            status_code=403,
            detail=str(exc),
        ) from exc


class TraceRunSummary(BaseModel):
    trace_id: str
    query: str
    intent: str | None = None
    complexity: str | None = None
    risk_level: str
    retrieval_strategy: str | None = None
    status: str
    validation_score: float | None = None
    final_answer: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    latency_ms: int | None = None
    step_count: int = 0
    tool_call_count: int = 0
    requires_approval: bool = False


class TraceStepItem(BaseModel):
    step_id: str
    sequence_no: int
    step_name: str
    step_type: str
    status: str
    input_json: dict = Field(default_factory=dict)
    output_json: dict = Field(default_factory=dict)
    latency_ms: int | None = None


class TraceToolCallItem(BaseModel):
    tool_call_id: str
    agent_step_id: str | None = None
    tool_name: str
    arguments_json: dict = Field(default_factory=dict)
    result_json: dict = Field(default_factory=dict)
    status: str
    requires_approval: bool
    approved_by_user_id: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


class TraceListResponse(BaseModel):
    actor_user_id: str
    traces: list[TraceRunSummary] = Field(
        default_factory=list
    )


class TraceDetailResponse(BaseModel):
    actor_user_id: str
    trace: TraceRunSummary
    steps: list[TraceStepItem] = Field(
        default_factory=list
    )
    tool_calls: list[TraceToolCallItem] = Field(
        default_factory=list
    )


def _score(
    value: Decimal | float | None,
) -> float | None:
    if value is None:
        return None
    return float(value)


def _summary(
    run: AgentRun,
    *,
    step_count: int = 0,
    tool_call_count: int = 0,
    requires_approval: bool = False,
) -> TraceRunSummary:
    return TraceRunSummary(
        trace_id=str(run.id),
        query=run.query,
        intent=run.intent,
        complexity=run.complexity,
        risk_level=run.risk_level,
        retrieval_strategy=run.retrieval_strategy,
        status=run.status,
        validation_score=_score(
            run.validation_score
        ),
        final_answer=run.final_answer,
        started_at=run.started_at,
        finished_at=run.finished_at,
        latency_ms=run.latency_ms,
        step_count=step_count,
        tool_call_count=tool_call_count,
        requires_approval=requires_approval,
    )


@router.get(
    "/traces",
    response_model=TraceListResponse,
)
def list_traces(
    actor_user_id: uuid.UUID,
    limit: int = Query(
        default=30,
        ge=1,
        le=100,
    ),
    db: Session = Depends(get_db),
    authorization: AuthorizationService = Depends(
        get_authorization_service
    ),
) -> TraceListResponse:
    _authorize_self(
        authorization,
        actor_user_id,
    )

    runs = list(
        db.scalars(
            select(AgentRun)
            .where(
                AgentRun.user_id
                == actor_user_id
            )
            .order_by(
                AgentRun.started_at.desc()
            )
            .limit(limit)
        ).all()
    )

    if not runs:
        return TraceListResponse(
            actor_user_id=str(
                actor_user_id
            ),
            traces=[],
        )

    run_ids = [
        item.id
        for item in runs
    ]

    steps = list(
        db.scalars(
            select(AgentStep)
            .where(
                AgentStep.agent_run_id.in_(
                    run_ids
                )
            )
        ).all()
    )

    calls = list(
        db.scalars(
            select(ToolCall)
            .where(
                ToolCall.agent_run_id.in_(
                    run_ids
                )
            )
        ).all()
    )

    step_counts: dict[
        uuid.UUID,
        int,
    ] = {}

    tool_counts: dict[
        uuid.UUID,
        int,
    ] = {}

    approval_flags: dict[
        uuid.UUID,
        bool,
    ] = {}

    for item in steps:
        step_counts[item.agent_run_id] = (
            step_counts.get(
                item.agent_run_id,
                0,
            )
            + 1
        )

    for item in calls:
        tool_counts[item.agent_run_id] = (
            tool_counts.get(
                item.agent_run_id,
                0,
            )
            + 1
        )

        if item.requires_approval:
            approval_flags[
                item.agent_run_id
            ] = True

    return TraceListResponse(
        actor_user_id=str(
            actor_user_id
        ),
        traces=[
            _summary(
                run,
                step_count=step_counts.get(
                    run.id,
                    0,
                ),
                tool_call_count=tool_counts.get(
                    run.id,
                    0,
                ),
                requires_approval=(
                    approval_flags.get(
                        run.id,
                        False,
                    )
                ),
            )
            for run in runs
        ],
    )


@router.get(
    "/traces/{trace_id}",
    response_model=TraceDetailResponse,
)
def trace_detail(
    trace_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    db: Session = Depends(get_db),
    authorization: AuthorizationService = Depends(
        get_authorization_service
    ),
) -> TraceDetailResponse:
    _authorize_self(
        authorization,
        actor_user_id,
    )

    run = db.scalar(
        select(AgentRun).where(
            AgentRun.id == trace_id,
            AgentRun.user_id
            == actor_user_id,
        )
    )

    if run is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "Trace not found for "
                "actor_user_id"
            ),
        )

    steps = list(
        db.scalars(
            select(AgentStep)
            .where(
                AgentStep.agent_run_id
                == trace_id
            )
            .order_by(
                AgentStep.sequence_no.asc()
            )
        ).all()
    )

    calls = list(
        db.scalars(
            select(ToolCall)
            .where(
                ToolCall.agent_run_id
                == trace_id
            )
            .order_by(
                ToolCall.created_at.asc()
            )
        ).all()
    )

    return TraceDetailResponse(
        actor_user_id=str(
            actor_user_id
        ),
        trace=_summary(
            run,
            step_count=len(steps),
            tool_call_count=len(calls),
            requires_approval=any(
                item.requires_approval
                for item in calls
            ),
        ),
        steps=[
            TraceStepItem(
                step_id=str(item.id),
                sequence_no=item.sequence_no,
                step_name=item.step_name,
                step_type=item.step_type,
                status=item.status,
                input_json=item.input_json
                or {},
                output_json=item.output_json
                or {},
                latency_ms=item.latency_ms,
            )
            for item in steps
        ],
        tool_calls=[
            TraceToolCallItem(
                tool_call_id=str(item.id),
                agent_step_id=(
                    str(item.agent_step_id)
                    if item.agent_step_id
                    else None
                ),
                tool_name=item.tool_name,
                arguments_json=(
                    item.arguments_json
                    or {}
                ),
                result_json=(
                    item.result_json
                    or {}
                ),
                status=item.status,
                requires_approval=(
                    item.requires_approval
                ),
                approved_by_user_id=(
                    str(
                        item.approved_by_user_id
                    )
                    if item.approved_by_user_id
                    else None
                ),
                started_at=item.started_at,
                finished_at=item.finished_at,
            )
            for item in calls
        ],
    )
