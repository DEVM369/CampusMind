from __future__ import annotations

from collections.abc import Generator

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from campusmind.api.dependencies import trusted_actor

from campusmind.knowledge.adaptive import AdaptiveRagService
from campusmind.knowledge.adaptive import AdaptiveRagResult, RouteDecision
from campusmind.platform.db import get_db
from campusmind.api.schemas import (
    AdaptiveChatResponse,
    AdaptiveEvidenceResponse,
    AdaptiveRagRequest,
    AdaptiveRouteDecisionResponse,
    AdaptiveRouteResponse,
)
from campusmind.api.schemas import GraphPathResponse
from campusmind.api.schemas import Citation


router = APIRouter()


def get_adaptive_rag_service(
    db: Session = Depends(get_db),
) -> Generator[AdaptiveRagService, None, None]:
    service = AdaptiveRagService(db)
    try:
        yield service
    finally:
        service.close()


def _decision(decision: RouteDecision) -> AdaptiveRouteDecisionResponse:
    return AdaptiveRouteDecisionResponse(
        route=decision.route.value,
        intent=decision.intent,
        complexity=decision.complexity,
        confidence=decision.confidence,
        reasons=list(decision.reasons),
        executable=decision.executable,
        requires_agent=decision.requires_agent,
        source=decision.source,
    )


def _citation(hit) -> Citation:
    return Citation(
        chunk_id=hit.chunk_id,
        document_id=hit.document_id,
        title=hit.title,
        page=hit.page,
        section=hit.section,
        chapter=hit.chapter,
        object_key=hit.object_key,
        quote=hit.content,
    )


def _graph_path(item) -> GraphPathResponse:
    return GraphPathResponse(
        source_id=item.source_id,
        source_name=item.source_name,
        source_type=item.source_type.value,
        relation_type=item.relation_type.value,
        target_id=item.target_id,
        target_name=item.target_name,
        target_type=item.target_type.value,
        relation_id=item.relation_id,
        source_document_id=item.source_document_id,
        source_chunk_id=item.source_chunk_id,
        confidence=item.confidence,
        path_id=item.path_id,
        hop_index=item.hop_index,
        text=item.path_text,
    )


def _chat_response(result: AdaptiveRagResult) -> AdaptiveChatResponse:
    evidence = [
        AdaptiveEvidenceResponse(
            citation=_citation(item.chunk),
            sources=list(item.sources),
            score=item.score,
            graph_path_ids=list(item.graph_path_ids),
        )
        for item in result.evidence_hits
    ]

    retrieval = None
    if result.text_retrieval is not None:
        # Import lazily to avoid endpoint module import cycles.
        from campusmind.api.routes.rag import _search_response

        retrieval = _search_response(result.text_retrieval)

    return AdaptiveChatResponse(
        trace_id=result.trace_id,
        query=result.query,
        answer=result.answer,
        decision=_decision(result.decision),
        planned_route=result.decision.route.value,
        executed_route=(result.executed_route.value if result.executed_route else None),
        citations=[item.citation for item in evidence],
        evidence=evidence,
        graph_paths=[_graph_path(item) for item in result.graph_paths],
        retrieval=retrieval,
        fallback_reason=result.fallback_reason,
        deferred_capability=result.deferred_capability,
        structured_data=result.structured_data,
        elapsed_ms=result.elapsed_ms,
    )


@router.post("/route", response_model=AdaptiveRouteResponse)
def route_query(
    request: AdaptiveRagRequest,
    service: AdaptiveRagService = Depends(get_adaptive_rag_service),
) -> AdaptiveRouteResponse:
    decision = service.route(request.query)
    return AdaptiveRouteResponse(
        query=request.query,
        decision=_decision(decision),
    )


@router.post("/chat", response_model=AdaptiveChatResponse)
def chat(
    request: AdaptiveRagRequest,
    actor=Depends(trusted_actor),
    service: AdaptiveRagService = Depends(get_adaptive_rag_service),
) -> AdaptiveChatResponse:
    return _chat_response(
        service.answer(
            request.query,
            top_k=request.top_k,
            max_paths=request.max_paths,
            actor_user_id=actor,
        )
    )
