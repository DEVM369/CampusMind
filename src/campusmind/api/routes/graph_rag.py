from __future__ import annotations

from collections.abc import Generator

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from campusmind.platform.db import get_db
from campusmind.knowledge.graph_rag import GraphRagService
from campusmind.knowledge.graph_rag import GraphRagSearchResult
from campusmind.api.schemas import (
    GraphPathResponse,
    GraphPlanResponse,
    GraphRagChatResponse,
    GraphRagRequest,
    GraphRagSearchResponse,
    LinkedEntityResponse,
)
from campusmind.api.schemas import Citation


router = APIRouter()


def get_graph_rag_service(
    db: Session = Depends(get_db),
) -> Generator[GraphRagService, None, None]:
    service = GraphRagService(db)
    try:
        yield service
    finally:
        service.close()


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


def _search_response(result: GraphRagSearchResult) -> GraphRagSearchResponse:
    plan = GraphPlanResponse(
        entities=[
            {
                "name": item.name,
                "entity_type": item.entity_type.value if item.entity_type else None,
                "confidence": item.confidence,
            }
            for item in result.plan.entities
        ],
        relation_types=[item.value for item in result.plan.relation_types],
        direction=result.plan.direction,
        traversal_steps=[
            {
                "relation_type": step.relation_type.value,
                "direction": step.direction,
            }
            for step in result.plan.traversal_steps
        ],
        max_hops=result.plan.max_hops,
    )
    linked = [
        LinkedEntityResponse(
            query_name=item.query_name,
            entity_id=item.entity_id,
            entity_type=item.entity_type.value,
            name=item.name,
            aliases=list(item.aliases),
            confidence=item.confidence,
        )
        for item in result.linked_entities
    ]
    paths = [
        GraphPathResponse(
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
        for item in result.paths
    ]
    return GraphRagSearchResponse(
        query=result.query,
        plan=plan,
        linked_entities=linked,
        paths=paths,
        citations=[_citation(hit) for hit in result.evidence_hits],
        elapsed_ms=result.elapsed_ms,
        raw_path_count=result.raw_path_count,
        recovered_evidence_count=result.recovered_evidence_count,
        diagnostics=list(result.diagnostics),
    )


@router.post("/search", response_model=GraphRagSearchResponse)
def search(
    request: GraphRagRequest,
    service: GraphRagService = Depends(get_graph_rag_service),
) -> GraphRagSearchResponse:
    return _search_response(
        service.search(request.query, max_paths=request.max_paths)
    )


@router.post("/chat", response_model=GraphRagChatResponse)
def chat(
    request: GraphRagRequest,
    service: GraphRagService = Depends(get_graph_rag_service),
) -> GraphRagChatResponse:
    result = service.answer(request.query, max_paths=request.max_paths)
    base = _search_response(result.search)
    return GraphRagChatResponse(
        **base.model_dump(),
        trace_id=result.trace_id,
        answer=result.answer,
    )
