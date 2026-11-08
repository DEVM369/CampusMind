from __future__ import annotations

from collections.abc import Generator

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from campusmind.platform.db import get_db
from campusmind.knowledge.hybrid import HybridGraphRagService
from campusmind.knowledge.hybrid import HybridGraphRagSearchResult
from campusmind.api.schemas import GraphPathResponse, GraphPlanResponse, LinkedEntityResponse
from campusmind.api.schemas import (
    HybridEvidenceResponse,
    HybridGraphRagChatResponse,
    HybridGraphRagRequest,
    HybridGraphRagSearchResponse,
)
from campusmind.api.schemas import Citation


router = APIRouter()


def get_hybrid_graph_rag_service(
    db: Session = Depends(get_db),
) -> Generator[HybridGraphRagService, None, None]:
    service = HybridGraphRagService(db)
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


def _graph_parts(result: HybridGraphRagSearchResult):
    graph = result.graph_search
    if graph is None:
        return None, [], []

    plan = GraphPlanResponse(
        entities=[
            {
                "name": item.name,
                "entity_type": item.entity_type.value if item.entity_type else None,
                "confidence": item.confidence,
            }
            for item in graph.plan.entities
        ],
        relation_types=[item.value for item in graph.plan.relation_types],
        direction=graph.plan.direction,
        traversal_steps=[
            {
                "relation_type": step.relation_type.value,
                "direction": step.direction,
            }
            for step in graph.plan.traversal_steps
        ],
        max_hops=graph.plan.max_hops,
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
        for item in graph.linked_entities
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
        for item in graph.paths
    ]
    return plan, linked, paths


def _search_response(result: HybridGraphRagSearchResult) -> HybridGraphRagSearchResponse:
    plan, linked, paths = _graph_parts(result)
    text = result.text_retrieval
    evidence = [
        HybridEvidenceResponse(
            citation=_citation(item.chunk),
            sources=list(item.sources),
            graph_score=item.graph_score,
            text_score=item.text_score,
            rrf_score=item.rrf_score,
            lexical_score=item.lexical_score,
            fusion_score=item.fusion_score,
            graph_path_ids=list(item.graph_path_ids),
        )
        for item in result.hits
    ]
    return HybridGraphRagSearchResponse(
        query=result.query,
        rewritten_query=(text.rewritten_query if text is not None else None),
        vector_count=(text.vector_count if text is not None else 0),
        keyword_count=(text.keyword_count if text is not None else 0),
        graph_plan=plan,
        linked_entities=linked,
        graph_paths=paths,
        evidence=evidence,
        citations=[item.citation for item in evidence],
        graph_error=result.graph_error,
        text_error=result.text_error,
        elapsed_ms=result.elapsed_ms,
    )


@router.post("/search", response_model=HybridGraphRagSearchResponse)
def search(
    request: HybridGraphRagRequest,
    service: HybridGraphRagService = Depends(get_hybrid_graph_rag_service),
) -> HybridGraphRagSearchResponse:
    return _search_response(
        service.search(
            request.query,
            top_k=request.top_k,
            max_paths=request.max_paths,
        )
    )


@router.post("/chat", response_model=HybridGraphRagChatResponse)
def chat(
    request: HybridGraphRagRequest,
    service: HybridGraphRagService = Depends(get_hybrid_graph_rag_service),
) -> HybridGraphRagChatResponse:
    result = service.answer(
        request.query,
        top_k=request.top_k,
        max_paths=request.max_paths,
    )
    base = _search_response(result.search)
    return HybridGraphRagChatResponse(
        **base.model_dump(),
        trace_id=result.trace_id,
        answer=result.answer,
    )
