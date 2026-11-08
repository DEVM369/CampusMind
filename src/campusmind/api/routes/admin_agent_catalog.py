from __future__ import annotations

from collections import Counter
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
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

from campusmind.knowledge.graph import (
    CampusGraphService,
    EntityType,
    RelationType,
)


router = APIRouter()


def _authorize(
    db: Session,
    actor_user_id: UUID,
) -> None:
    authorization = AuthorizationService(
        db
    )

    try:
        authorization.require(
            "admin.dashboard.read",
            actor_user_id,
        )
    except AuthorizationDenied as exc:
        raise HTTPException(
            status_code=403,
            detail=str(exc),
        ) from exc


def _iso(
    value: datetime | None,
) -> str | None:
    if value is None:
        return None

    return value.isoformat()


@router.get("/agents")
def agents(
    actor_user_id: UUID,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """Read-only view of the current Agent architecture."""

    _authorize(
        db,
        actor_user_id,
    )

    runs = list(
        db.scalars(
            select(AgentRun)
            .order_by(
                AgentRun.created_at.desc()
            )
            .limit(200)
        ).all()
    )

    steps = list(
        db.scalars(
            select(AgentStep)
            .order_by(
                AgentStep.created_at.desc()
            )
            .limit(1000)
        ).all()
    )

    statuses = Counter(
        str(item.status or "unknown")
        for item in runs
    )

    intents = Counter(
        str(item.intent)
        for item in runs
        if item.intent
    )

    agents_catalog = [
        {
            "code": "core-runtime",
            "name": "Core Agent Runtime",
            "kind": "orchestrator",
            "module": (
                "campusmind.agent.runtime"
            ),
            "class_name": (
                "AgentRuntimeService"
            ),
            "status": "active",
            "management_mode": (
                "code-managed"
            ),
            "description": (
                "Query planning, retrieval routing, "
                "validation, critic, tool execution "
                "and trace persistence."
            ),
        },
        {
            "code": "academic",
            "name": "Academic Agent",
            "kind": "domain-agent",
            "module": (
                "campusmind.agent.multi"
            ),
            "class_name": "AcademicAgent",
            "status": "active",
            "management_mode": (
                "code-managed"
            ),
            "description": (
                "Academic and course-oriented "
                "domain agent."
            ),
        },
        {
            "code": "research",
            "name": "Research Agent",
            "kind": "domain-agent",
            "module": (
                "campusmind.agent.multi"
            ),
            "class_name": "ResearchAgent",
            "status": "active",
            "management_mode": (
                "code-managed"
            ),
            "description": (
                "Research information domain agent."
            ),
        },
        {
            "code": "library",
            "name": "Library Agent",
            "kind": "domain-agent",
            "module": (
                "campusmind.agent.multi"
            ),
            "class_name": "LibraryAgent",
            "status": "active",
            "management_mode": (
                "code-managed"
            ),
            "description": (
                "Library information and "
                "library-service domain agent."
            ),
        },
        {
            "code": "campus-service",
            "name": "Campus Service Agent",
            "kind": "domain-agent",
            "module": (
                "campusmind.agent.multi"
            ),
            "class_name": (
                "CampusServiceAgent"
            ),
            "status": "active",
            "management_mode": (
                "code-managed"
            ),
            "description": (
                "Campus service domain agent."
            ),
        },
        {
            "code": "general-knowledge",
            "name": "General Knowledge Agent",
            "kind": "domain-agent",
            "module": (
                "campusmind.agent.multi"
            ),
            "class_name": (
                "GeneralKnowledgeAgent"
            ),
            "status": "active",
            "management_mode": (
                "code-managed"
            ),
            "description": (
                "Fallback general knowledge agent."
            ),
        },
        {
            "code": "hierarchical-multi-agent",
            "name": (
                "Hierarchical Multi-Agent"
            ),
            "kind": "orchestrator",
            "module": (
                "campusmind.agent.multi"
            ),
            "class_name": (
                "HierarchicalMultiAgentService"
            ),
            "status": "active",
            "management_mode": (
                "code-managed"
            ),
            "description": (
                "Hierarchical multi-agent "
                "planning and coordination."
            ),
        },
    ]

    recent_runs = [
        {
            "run_id": str(item.id),
            "user_id": (
                str(item.user_id)
                if item.user_id
                else None
            ),
            "intent": item.intent,
            "complexity": item.complexity,
            "risk_level": item.risk_level,
            "retrieval_strategy": (
                item.retrieval_strategy
            ),
            "status": item.status,
            "validation_score": (
                float(item.validation_score)
                if item.validation_score
                is not None
                else None
            ),
            "latency_ms": item.latency_ms,
            "created_at": _iso(
                item.created_at
            ),
        }
        for item in runs[:12]
    ]

    return {
        "catalog_version": "1.0",
        "read_only": True,
        "agents": agents_catalog,
        "runtime": {
            "run_count": len(runs),
            "step_count": len(steps),
            "status_counts": dict(
                statuses
            ),
            "top_intents": [
                {
                    "intent": key,
                    "count": value,
                }
                for key, value
                in intents.most_common(10)
            ],
        },
        "recent_runs": recent_runs,
    }


@router.get("/tools")
def tools(
    actor_user_id: UUID,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """Read-only Tool registry and observed invocation statistics."""

    _authorize(
        db,
        actor_user_id,
    )

    calls = list(
        db.scalars(
            select(ToolCall)
            .order_by(
                ToolCall.created_at.desc()
            )
            .limit(1000)
        ).all()
    )

    by_name: dict[str, dict[str, object]] = {}

    for item in calls:
        name = str(
            item.tool_name
            or "unknown"
        )

        row = by_name.setdefault(
            name,
            {
                "tool_name": name,
                "call_count": 0,
                "completed_count": 0,
                "failed_count": 0,
                "approval_required_count": 0,
                "latest_call_at": None,
            },
        )

        row["call_count"] = int(
            row["call_count"]
        ) + 1

        status = str(
            item.status
            or ""
        ).lower()

        if status in {
            "completed",
            "success",
            "succeeded",
        }:
            row["completed_count"] = int(
                row["completed_count"]
            ) + 1

        if status in {
            "failed",
            "error",
            "rejected",
        }:
            row["failed_count"] = int(
                row["failed_count"]
            ) + 1

        if item.requires_approval:
            row[
                "approval_required_count"
            ] = int(
                row[
                    "approval_required_count"
                ]
            ) + 1

        current_latest = row[
            "latest_call_at"
        ]

        candidate = _iso(
            item.created_at
        )

        if (
            candidate
            and (
                current_latest is None
                or candidate
                > current_latest
            )
        ):
            row[
                "latest_call_at"
            ] = candidate

    observed = sorted(
        by_name.values(),
        key=lambda item: (
            -int(
                item["call_count"]
            ),
            str(
                item["tool_name"]
            ),
        ),
    )

    service_catalog = [
        {
            "code": "student-sql",
            "name": "Student SQL Tool",
            "module": (
                "campusmind.tools.student"
            ),
            "class_name": (
                "StudentSqlToolService"
            ),
            "risk": "read-only",
            "status": "active",
        },
        {
            "code": "course",
            "name": "Course Tool",
            "module": (
                "campusmind.tools.course"
            ),
            "class_name": (
                "CourseToolService"
            ),
            "risk": "mixed",
            "status": "active",
        },
        {
            "code": "research",
            "name": "Research Tool",
            "module": (
                "campusmind.tools.research"
            ),
            "class_name": (
                "ResearchToolService"
            ),
            "risk": "read-only",
            "status": "active",
        },
        {
            "code": "action-layer",
            "name": "Action / HITL Tool Layer",
            "module": (
                "campusmind.tools.actions"
            ),
            "class_name": None,
            "risk": "approval-gated",
            "status": "active",
        },
    ]

    return {
        "catalog_version": "1.0",
        "read_only": True,
        "service_catalog": (
            service_catalog
        ),
        "observed_tools": observed,
        "total_tool_calls": len(
            calls
        ),
        "approval_required_calls": sum(
            1
            for item in calls
            if item.requires_approval
        ),
    }


@router.get("/prompts")
def prompts(
    actor_user_id: UUID,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """Read-only inventory of code-managed prompts."""

    _authorize(
        db,
        actor_user_id,
    )

    prompt_catalog = [
        {
            "code": "rag-answer",
            "name": "RAG Answer Prompt",
            "module": (
                "campusmind.knowledge.rag"
            ),
            "purpose": (
                "Grounded text-RAG answer "
                "generation."
            ),
            "status": "active",
            "management_mode": (
                "code-managed-read-only"
            ),
            "raw_prompt_exposed": False,
        },
        {
            "code": "graph-query-analyzer",
            "name": (
                "Graph Query Analyzer Prompt"
            ),
            "module": (
                "campusmind.knowledge.graph_rag"
            ),
            "purpose": (
                "Convert natural-language "
                "questions into safe graph "
                "retrieval plans."
            ),
            "status": "active",
            "management_mode": (
                "code-managed-read-only"
            ),
            "raw_prompt_exposed": False,
        },
        {
            "code": "graph-answer",
            "name": "GraphRAG Answer Prompt",
            "module": (
                "campusmind.knowledge.graph_rag"
            ),
            "purpose": (
                "Generate answers from verified "
                "graph paths and evidence."
            ),
            "status": "active",
            "management_mode": (
                "code-managed-read-only"
            ),
            "raw_prompt_exposed": False,
        },
        {
            "code": "graph-ontology",
            "name": (
                "Graph Ontology Extraction Prompt"
            ),
            "module": (
                "campusmind.knowledge.graph_ingestion"
            ),
            "purpose": (
                "Ontology-constrained graph "
                "entity and relation extraction."
            ),
            "status": "active",
            "management_mode": (
                "code-managed-read-only"
            ),
            "raw_prompt_exposed": False,
        },
        {
            "code": "answer-critic",
            "name": "Answer Critic",
            "module": (
                "campusmind.agent.runtime"
            ),
            "purpose": (
                "Validate answer quality, "
                "evidence and route coverage."
            ),
            "status": "active",
            "management_mode": (
                "code-managed-read-only"
            ),
            "raw_prompt_exposed": False,
        },
    ]

    return {
        "catalog_version": "1.0",
        "read_only": True,
        "editable": False,
        "reason": (
            "Prompts are currently managed "
            "in source code rather than "
            "database configuration."
        ),
        "prompts": prompt_catalog,
    }

@router.get("/graph/entities")
def graph_entities(
    actor_user_id: UUID,
    entity_type: str | None = None,
    keyword: str | None = None,
    offset: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """Read-only entity browser for the admin console."""

    _authorize(
        db,
        actor_user_id,
    )

    if entity_type:
        valid_types = {
            item.value
            for item in EntityType
        }

        if entity_type not in valid_types:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Unknown graph entity type: "
                    + entity_type
                ),
            )

    service = CampusGraphService()

    try:
        result = service.list_entities(
            entity_type=entity_type,
            keyword=keyword,
            offset=offset,
            limit=limit,
        )
    finally:
        service.close()

    return {
        "read_only": True,
        **result,
    }


@router.get("/graph/relations")
def graph_relations(
    actor_user_id: UUID,
    relation_type: str | None = None,
    keyword: str | None = None,
    offset: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """Read-only relation browser for the admin console."""

    _authorize(
        db,
        actor_user_id,
    )

    if relation_type:
        valid_types = {
            item.value
            for item in RelationType
        }

        if relation_type not in valid_types:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Unknown graph relation type: "
                    + relation_type
                ),
            )

    service = CampusGraphService()

    try:
        result = service.list_relations(
            relation_type=relation_type,
            keyword=keyword,
            offset=offset,
            limit=limit,
        )
    finally:
        service.close()

    return {
        "read_only": True,
        **result,
    }

@router.get("/graph/entity-context")
def graph_entity_context(
    actor_user_id: UUID,
    entity_id: str,
    limit: int = 100,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """Read-only graph neighborhood for one entity."""

    _authorize(
        db,
        actor_user_id,
    )

    entity_id = entity_id.strip()

    if not entity_id:
        raise HTTPException(
            status_code=400,
            detail="entity_id is required",
        )

    service = CampusGraphService()

    try:
        result = service.entity_context(
            entity_id,
            limit=limit,
        )
    finally:
        service.close()

    if result is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "Graph entity not found: "
                + entity_id
            ),
        )

    return {
        "read_only": True,
        **result,
    }

