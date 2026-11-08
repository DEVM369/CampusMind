from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from campusmind.config import MAIN_MODEL_NAME, resolved_llm_provider
from campusmind.platform.db import get_db
from campusmind.knowledge.rag import get_embedding_provider
from campusmind.knowledge.rag import ModelCheckService
from campusmind.knowledge.rag import BasicRagService, HybridRetrievalService, RetrievalResult
from campusmind.knowledge.rag import RetrievedChunk
from campusmind.api.schemas import (
    ChatRequest,
    ChatResponse,
    Citation,
    RagStatusResponse,
    ModelCheckResponse,
    RetrievalHitResponse,
    SearchRequest,
    SearchResponse,
)

router = APIRouter()


def _citation(hit: RetrievedChunk) -> Citation:
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


def _search_response(result: RetrievalResult) -> SearchResponse:
    hits = [
        RetrievalHitResponse(
            chunk_id=hit.chunk_id,
            content=hit.content,
            score=hit.final_score,
            vector_score=hit.vector_score,
            keyword_score=hit.keyword_score,
            rrf_score=hit.rrf_score,
            ranks=hit.ranks,
            citation=_citation(hit),
        )
        for hit in result.hits
    ]
    return SearchResponse(
        query=result.original_query,
        rewritten_query=result.rewritten_query,
        vector_count=result.vector_count,
        keyword_count=result.keyword_count,
        elapsed_ms=result.elapsed_ms,
        hits=hits,
    )


@router.get("/status", response_model=RagStatusResponse)
def rag_status() -> RagStatusResponse:
    provider = get_embedding_provider()

    return RagStatusResponse(
        embedding_provider=provider.name,
        embedding_model=provider.model,
        embedding_dimensions=provider.dimensions,
        llm_provider=resolved_llm_provider(),
        llm_model=MAIN_MODEL_NAME,
    )


@router.post("/model-check", response_model=ModelCheckResponse)
def model_check() -> ModelCheckResponse:
    """Actively call the configured embedding and LLM APIs. This may consume provider quota."""
    return ModelCheckService().check()


@router.post("/search", response_model=SearchResponse)
def search(request: SearchRequest, db: Session = Depends(get_db)) -> SearchResponse:
    result = HybridRetrievalService(db).search(request.query, top_k=request.top_k)
    return _search_response(result)


@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest, db: Session = Depends(get_db)) -> ChatResponse:
    result = BasicRagService(db).answer(request.query, top_k=request.top_k)
    retrieval = _search_response(result.retrieval)
    citations = [_citation(hit) for hit in result.evidence_hits]
    return ChatResponse(
        trace_id=result.trace_id,
        answer=result.answer,
        citations=citations,
        retrieval=retrieval,
    )
