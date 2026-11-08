from __future__ import annotations

import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from campusmind.platform.db import (
    AgentRun,
    AuditLog,
    Document,
    EvaluationCase,
    EvaluationDataset,
    EvaluationResult,
    KnowledgeBase,
    Role,
    ToolCall,
    User,
    UserRole,
    get_db,
)
from campusmind.platform.security import (
    AuthorizationDenied,
    AuthorizationService,
)


from campusmind.knowledge.graph import CampusGraphService
from campusmind.platform.db import DocumentChunk, DocumentVersion

router = APIRouter()


def get_authorization_service(
    db: Session = Depends(get_db),
) -> AuthorizationService:
    return AuthorizationService(db)


def _authorize_admin(
    authorization: AuthorizationService,
    actor_user_id: uuid.UUID,
):
    try:
        return authorization.require(
            "admin.dashboard.read",
            actor_user_id,
        )
    except AuthorizationDenied as exc:
        raise HTTPException(
            status_code=403,
            detail=str(exc),
        ) from exc


def _count(
    db: Session,
    model,
    *conditions,
) -> int:
    stmt = (
        select(func.count())
        .select_from(model)
    )

    if conditions:
        stmt = stmt.where(*conditions)

    return int(db.scalar(stmt) or 0)


def _decimal(
    value: Decimal | float | None,
) -> float | None:
    if value is None:
        return None

    return float(value)


@router.get("/dashboard")
def dashboard(
    actor_user_id: uuid.UUID,
    recent_limit: int = Query(
        default=8,
        ge=1,
        le=25,
    ),
    db: Session = Depends(get_db),
    authorization: AuthorizationService = Depends(
        get_authorization_service
    ),
) -> dict:
    decision = _authorize_admin(
        authorization,
        actor_user_id,
    )

    total_evaluations = _count(
        db,
        EvaluationResult,
    )

    passed_evaluations = _count(
        db,
        EvaluationResult,
        EvaluationResult.passed.is_(True),
    )

    counts = {
        "users": _count(db, User),
        "active_users": _count(
            db,
            User,
            User.status == "active",
        ),
        "roles": _count(db, Role),
        "knowledge_bases": _count(
            db,
            KnowledgeBase,
        ),
        "active_knowledge_bases": _count(
            db,
            KnowledgeBase,
            KnowledgeBase.status == "active",
        ),
        "documents": _count(
            db,
            Document,
        ),
        "agent_runs": _count(
            db,
            AgentRun,
        ),
        "completed_agent_runs": _count(
            db,
            AgentRun,
            AgentRun.status == "completed",
        ),
        "tool_calls": _count(
            db,
            ToolCall,
        ),
        "hitl_tool_calls": _count(
            db,
            ToolCall,
            ToolCall.requires_approval.is_(True),
        ),
        "audit_logs": _count(
            db,
            AuditLog,
        ),
        "evaluation_results": total_evaluations,
        "passed_evaluations": passed_evaluations,
    }

    recent_runs = list(
        db.scalars(
            select(AgentRun)
            .order_by(
                AgentRun.started_at.desc()
            )
            .limit(recent_limit)
        ).all()
    )

    recent_audits = list(
        db.scalars(
            select(AuditLog)
            .order_by(
                AuditLog.created_at.desc()
            )
            .limit(recent_limit)
        ).all()
    )

    return {
        "actor_user_id": str(actor_user_id),
        "capability": "admin.dashboard.read",
        "role_codes": list(
            decision.role_codes
        ),
        "role_families": list(
            decision.role_families
        ),
        "counts": counts,
        "evaluation_pass_rate": (
            round(
                passed_evaluations
                / total_evaluations,
                4,
            )
            if total_evaluations
            else None
        ),
        "recent_runs": [
            {
                "trace_id": str(item.id),
                "query": item.query,
                "intent": item.intent,
                "complexity": item.complexity,
                "risk_level": item.risk_level,
                "retrieval_strategy": (
                    item.retrieval_strategy
                ),
                "status": item.status,
                "validation_score": _decimal(
                    item.validation_score
                ),
                "started_at": item.started_at,
                "latency_ms": item.latency_ms,
            }
            for item in recent_runs
        ],
        "recent_audits": [
            {
                "audit_id": str(item.id),
                "actor_user_id": (
                    str(item.actor_user_id)
                    if item.actor_user_id
                    else None
                ),
                "action": item.action,
                "resource_type": (
                    item.resource_type
                ),
                "resource_id": (
                    item.resource_id
                ),
                "request_id": (
                    item.request_id
                ),
                "created_at": (
                    item.created_at
                ),
            }
            for item in recent_audits
        ],
    }


@router.get("/users")
def users_and_roles(
    actor_user_id: uuid.UUID,
    limit: int = Query(
        default=200,
        ge=1,
        le=500,
    ),
    db: Session = Depends(get_db),
    authorization: AuthorizationService = Depends(
        get_authorization_service
    ),
) -> dict:
    _authorize_admin(
        authorization,
        actor_user_id,
    )

    users = list(
        db.scalars(
            select(User)
            .order_by(
                User.username.asc()
            )
            .limit(limit)
        ).all()
    )

    user_ids = [
        item.id
        for item in users
    ]

    role_map: dict[
        uuid.UUID,
        list[dict],
    ] = {
        item.id: []
        for item in users
    }

    if user_ids:
        rows = db.execute(
            select(
                UserRole.user_id,
                Role.id,
                Role.code,
                Role.name,
            )
            .join(
                Role,
                Role.id
                == UserRole.role_id,
            )
            .where(
                UserRole.user_id.in_(
                    user_ids
                )
            )
            .order_by(
                Role.code.asc()
            )
        ).all()

        for (
            user_id,
            role_id,
            code,
            name,
        ) in rows:
            role_map.setdefault(
                user_id,
                [],
            ).append(
                {
                    "role_id": str(
                        role_id
                    ),
                    "code": code,
                    "name": name,
                }
            )

    role_counts = dict(
        db.execute(
            select(
                UserRole.role_id,
                func.count(
                    UserRole.user_id
                ),
            )
            .group_by(
                UserRole.role_id
            )
        ).all()
    )

    roles = list(
        db.scalars(
            select(Role)
            .order_by(
                Role.code.asc()
            )
        ).all()
    )

    return {
        "actor_user_id": str(
            actor_user_id
        ),
        "total": _count(
            db,
            User,
        ),
        "users": [
            {
                "user_id": str(item.id),
                "username": item.username,
                "full_name": item.full_name,
                "email": item.email,
                "status": item.status,
                "is_superuser": (
                    item.is_superuser
                ),
                "roles": role_map.get(
                    item.id,
                    [],
                ),
                "created_at": getattr(
                    item,
                    "created_at",
                    None,
                ),
            }
            for item in users
        ],
        "roles": [
            {
                "role_id": str(item.id),
                "code": item.code,
                "name": item.name,
                "description": (
                    item.description
                ),
                "user_count": int(
                    role_counts.get(
                        item.id,
                        0,
                    )
                ),
            }
            for item in roles
        ],
    }


@router.get("/knowledge")
def knowledge_inventory(
    actor_user_id: uuid.UUID,
    document_limit: int = Query(
        default=50,
        ge=1,
        le=200,
    ),
    db: Session = Depends(get_db),
    authorization: AuthorizationService = Depends(
        get_authorization_service
    ),
) -> dict:
    _authorize_admin(
        authorization,
        actor_user_id,
    )

    knowledge_bases = list(
        db.scalars(
            select(KnowledgeBase)
            .order_by(
                KnowledgeBase.name.asc()
            )
        ).all()
    )

    document_counts = dict(
        db.execute(
            select(
                Document.knowledge_base_id,
                func.count(Document.id),
            )
            .group_by(
                Document.knowledge_base_id
            )
        ).all()
    )

    kb_names = {
        item.id: item.name
        for item in knowledge_bases
    }

    documents = list(
        db.scalars(
            select(Document)
            .order_by(
                Document.created_at.desc()
            )
            .limit(document_limit)
        ).all()
    )

    return {
        "actor_user_id": str(
            actor_user_id
        ),
        "knowledge_bases": [
            {
                "knowledge_base_id": str(
                    item.id
                ),
                "code": item.code,
                "name": item.name,
                "domain": item.domain,
                "description": (
                    item.description
                ),
                "visibility": (
                    item.visibility
                ),
                "status": item.status,
                "document_count": int(
                    document_counts.get(
                        item.id,
                        0,
                    )
                ),
                "created_at": getattr(
                    item,
                    "created_at",
                    None,
                ),
            }
            for item in knowledge_bases
        ],
        "total_documents": _count(
            db,
            Document,
        ),
        "documents": [
            {
                "document_id": str(
                    item.id
                ),
                "knowledge_base_id": str(
                    item.knowledge_base_id
                ),
                "knowledge_base_name": (
                    kb_names.get(
                        item.knowledge_base_id
                    )
                ),
                "title": item.title,
                "mime_type": (
                    item.mime_type
                ),
                "document_type": (
                    item.document_type
                ),
                "status": item.status,
                "created_at": getattr(
                    item,
                    "created_at",
                    None,
                ),
            }
            for item in documents
        ],
    }


@router.get("/evaluations")
def evaluations(
    actor_user_id: uuid.UUID,
    result_limit: int = Query(
        default=40,
        ge=1,
        le=200,
    ),
    db: Session = Depends(get_db),
    authorization: AuthorizationService = Depends(
        get_authorization_service
    ),
) -> dict:
    _authorize_admin(
        authorization,
        actor_user_id,
    )

    datasets = list(
        db.scalars(
            select(EvaluationDataset)
            .order_by(
                EvaluationDataset.name.asc(),
                EvaluationDataset.version.asc(),
            )
        ).all()
    )

    case_counts = dict(
        db.execute(
            select(
                EvaluationCase.dataset_id,
                func.count(
                    EvaluationCase.id
                ),
            )
            .group_by(
                EvaluationCase.dataset_id
            )
        ).all()
    )

    result_counts = dict(
        db.execute(
            select(
                EvaluationResult.dataset_id,
                func.count(
                    EvaluationResult.id
                ),
            )
            .group_by(
                EvaluationResult.dataset_id
            )
        ).all()
    )

    passed_counts = dict(
        db.execute(
            select(
                EvaluationResult.dataset_id,
                func.count(
                    EvaluationResult.id
                ),
            )
            .where(
                EvaluationResult.passed
                .is_(True)
            )
            .group_by(
                EvaluationResult.dataset_id
            )
        ).all()
    )

    score_rows = db.execute(
        select(
            EvaluationResult.dataset_id,
            func.avg(
                EvaluationResult.score
            ),
        )
        .where(
            EvaluationResult.score
            .is_not(None)
        )
        .group_by(
            EvaluationResult.dataset_id
        )
    ).all()

    average_scores = {
        dataset_id: (
            float(score)
            if score is not None
            else None
        )
        for dataset_id, score
        in score_rows
    }

    dataset_names = {
        item.id: item.name
        for item in datasets
    }

    results = list(
        db.scalars(
            select(EvaluationResult)
            .order_by(
                EvaluationResult.created_at
                .desc()
            )
            .limit(result_limit)
        ).all()
    )

    return {
        "actor_user_id": str(
            actor_user_id
        ),
        "datasets": [
            {
                "dataset_id": str(
                    item.id
                ),
                "name": item.name,
                "version": item.version,
                "description": (
                    item.description
                ),
                "status": item.status,
                "case_count": int(
                    case_counts.get(
                        item.id,
                        0,
                    )
                ),
                "result_count": int(
                    result_counts.get(
                        item.id,
                        0,
                    )
                ),
                "passed_count": int(
                    passed_counts.get(
                        item.id,
                        0,
                    )
                ),
                "pass_rate": (
                    round(
                        passed_counts.get(
                            item.id,
                            0,
                        )
                        / result_counts.get(
                            item.id,
                            1,
                        ),
                        4,
                    )
                    if result_counts.get(
                        item.id,
                        0,
                    )
                    else None
                ),
                "average_score": (
                    average_scores.get(
                        item.id
                    )
                ),
            }
            for item in datasets
        ],
        "results": [
            {
                "result_id": str(
                    item.id
                ),
                "dataset_id": str(
                    item.dataset_id
                ),
                "dataset_name": (
                    dataset_names.get(
                        item.dataset_id
                    )
                ),
                "case_id": (
                    str(item.case_id)
                    if item.case_id
                    else None
                ),
                "agent_run_id": (
                    str(item.agent_run_id)
                    if item.agent_run_id
                    else None
                ),
                "score": _decimal(
                    item.score
                ),
                "passed": item.passed,
                "created_at": getattr(
                    item,
                    "created_at",
                    None,
                ),
            }
            for item in results
        ],
    }


@router.get("/audits")
def audit_logs(
    actor_user_id: uuid.UUID,
    limit: int = Query(
        default=50,
        ge=1,
        le=200,
    ),
    db: Session = Depends(get_db),
    authorization: AuthorizationService = Depends(
        get_authorization_service
    ),
) -> dict:
    _authorize_admin(
        authorization,
        actor_user_id,
    )

    logs = list(
        db.scalars(
            select(AuditLog)
            .order_by(
                AuditLog.created_at.desc()
            )
            .limit(limit)
        ).all()
    )

    actor_ids = {
        item.actor_user_id
        for item in logs
        if item.actor_user_id
        is not None
    }

    actors = {}

    if actor_ids:
        users = list(
            db.scalars(
                select(User)
                .where(
                    User.id.in_(
                        actor_ids
                    )
                )
            ).all()
        )

        actors = {
            item.id: {
                "username": item.username,
                "full_name": (
                    item.full_name
                ),
            }
            for item in users
        }

    return {
        "actor_user_id": str(
            actor_user_id
        ),
        "total": _count(
            db,
            AuditLog,
        ),
        "logs": [
            {
                "audit_id": str(item.id),
                "actor_user_id": (
                    str(item.actor_user_id)
                    if item.actor_user_id
                    else None
                ),
                "actor_username": (
                    actors.get(
                        item.actor_user_id,
                        {},
                    ).get("username")
                    if item.actor_user_id
                    else None
                ),
                "actor_full_name": (
                    actors.get(
                        item.actor_user_id,
                        {},
                    ).get("full_name")
                    if item.actor_user_id
                    else None
                ),
                "action": item.action,
                "resource_type": (
                    item.resource_type
                ),
                "resource_id": (
                    item.resource_id
                ),
                "request_id": (
                    item.request_id
                ),
                "created_at": (
                    item.created_at
                ),
            }
            for item in logs
        ],
    }

@router.get(
    "/documents/{document_id}/graph-status"
)
def document_graph_status(
    document_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    db: Session = Depends(get_db),
    authorization: AuthorizationService = Depends(
        get_authorization_service
    ),
) -> dict:
    """Read-only relation-backed graph status for a document."""

    _authorize_admin(
        authorization,
        actor_user_id,
    )

    document = db.get(
        Document,
        document_id,
    )

    if document is None:
        raise HTTPException(
            status_code=404,
            detail="Document not found",
        )

    chunks = list(
        db.scalars(
            select(DocumentChunk)
            .join(
                DocumentVersion,
                DocumentVersion.id
                == DocumentChunk.document_version_id,
            )
            .where(
                DocumentChunk.document_id
                == document_id,
                DocumentVersion.status
                == "active",
            )
            .order_by(
                DocumentChunk.chunk_index.asc()
            )
        ).all()
    )

    service = CampusGraphService()

    try:
        status_map = (
            service.source_chunks_graph_status(
                str(item.id)
                for item in chunks
            )
        )
    finally:
        service.close()

    chunk_items = []

    relation_type_counts = {}
    provenance_method_counts = {}

    relation_count = 0
    evidence_gap_count = 0
    relation_backed_chunk_count = 0

    for chunk in chunks:
        chunk_id = str(
            chunk.id
        )

        status = status_map.get(
            chunk_id,
            {},
        )

        chunk_relation_count = int(
            status.get(
                "relation_count",
                0,
            )
        )

        chunk_gap_count = int(
            status.get(
                "evidence_gap_count",
                0,
            )
        )

        relation_types = list(
            status.get(
                "relation_types",
                [],
            )
            or []
        )

        extraction_methods = list(
            status.get(
                "extraction_methods",
                [],
            )
            or []
        )

        chunk_relation_type_counts = dict(
            status.get(
                "relation_type_counts",
                {},
            )
            or {}
        )

        chunk_method_counts = dict(
            status.get(
                "extraction_method_counts",
                {},
            )
            or {}
        )

        if chunk_relation_count > 0:
            relation_backed_chunk_count += 1

        relation_count += (
            chunk_relation_count
        )

        evidence_gap_count += (
            chunk_gap_count
        )

        for (
            relation_type,
            count,
        ) in chunk_relation_type_counts.items():
            relation_type_counts[
                relation_type
            ] = (
                relation_type_counts.get(
                    relation_type,
                    0,
                )
                + int(count)
            )

        for (
            method,
            count,
        ) in chunk_method_counts.items():
            provenance_method_counts[
                method
            ] = (
                provenance_method_counts.get(
                    method,
                    0,
                )
                + int(count)
            )

        chunk_items.append(
            {
                "chunk_id": chunk_id,
                "chunk_index": (
                    chunk.chunk_index
                ),
                "page": chunk.page,
                "section": chunk.section,
                "chapter": chunk.chapter,
                "relation_count": (
                    chunk_relation_count
                ),
                "evidence_gap_count": (
                    chunk_gap_count
                ),
                "relation_types": (
                    relation_types
                ),
                "relation_type_counts": (
                    chunk_relation_type_counts
                ),
                "extraction_methods": (
                    extraction_methods
                ),
                "extraction_method_counts": (
                    chunk_method_counts
                ),
                "has_relations": (
                    chunk_relation_count > 0
                ),
            }
        )

    chunk_count = len(
        chunks
    )

    return {
        "read_only": True,
        "document_id": str(
            document.id
        ),
        "title": document.title,
        "document_status": (
            document.status
        ),
        "status_basis": (
            "campusmind_relations_by_source_chunk"
        ),
        "chunk_count": chunk_count,
        "relation_backed_chunk_count": (
            relation_backed_chunk_count
        ),
        "chunks_without_relations": (
            chunk_count
            - relation_backed_chunk_count
        ),
        "relation_count": (
            relation_count
        ),
        "evidence_gap_count": (
            evidence_gap_count
        ),
        "relation_type_counts": (
            relation_type_counts
        ),
        "provenance_method_counts": (
            provenance_method_counts
        ),
        "chunks": chunk_items,
        "interpretation": (
            "Counts CampusMind graph relations matched "
            "by source_chunk_id. Missing extraction_method "
            "is reported as <unspecified>; provenance is "
            "not inferred as LLM, seeded, or structured."
        ),
    }

