from __future__ import annotations

from collections.abc import Generator
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from campusmind.platform.db import get_db
from campusmind.api.dependencies import trusted_actor
from campusmind.platform.document_access import DocumentAccessService
from campusmind.knowledge.graph_ingestion import GraphIngestionService
from campusmind.api.schemas import (
    ChunkGraphIngestionResponse,
    DocumentGraphIngestionResponse,
    SourceChunkGraphResponse,
)


router = APIRouter()


def get_graph_ingestion_service(
    request: Request,
    db: Session = Depends(get_db),
    actor=Depends(trusted_actor),
) -> Generator[GraphIngestionService, None, None]:
    access = DocumentAccessService(db, actor)
    try:
        if "document_id" in request.path_params:
            access.require_document(UUID(str(request.path_params["document_id"])))
        if "chunk_id" in request.path_params:
            access.require_chunk(UUID(str(request.path_params["chunk_id"])))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    service = GraphIngestionService(db)
    try:
        yield service
    finally:
        service.close()


def _chunk_response(result) -> ChunkGraphIngestionResponse:
    return ChunkGraphIngestionResponse(
        chunk_id=result.chunk_id,
        document_id=result.document_id,
        entities_extracted=result.entities_extracted,
        entities_written=result.entities_written,
        relations_extracted=result.relations_extracted,
        relations_written=result.relations_written,
        skipped_relations=result.skipped_relations,
        reused_entities=result.reused_entities,
        created_entities=result.created_entities,
    )


@router.post(
    "/ingest/chunks/{chunk_id}",
    response_model=ChunkGraphIngestionResponse,
)
def ingest_chunk(
    chunk_id: UUID,
    service: GraphIngestionService = Depends(get_graph_ingestion_service),
) -> ChunkGraphIngestionResponse:
    try:
        return _chunk_response(service.ingest_chunk(chunk_id))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/ingest/documents/{document_id}",
    response_model=DocumentGraphIngestionResponse,
)
def ingest_document(
    document_id: UUID,
    service: GraphIngestionService = Depends(get_graph_ingestion_service),
) -> DocumentGraphIngestionResponse:
    try:
        result = service.ingest_document(document_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return DocumentGraphIngestionResponse(
        document_id=result.document_id,
        chunk_count=result.chunk_count,
        entities_extracted=result.entities_extracted,
        entities_written=result.entities_written,
        relations_extracted=result.relations_extracted,
        relations_written=result.relations_written,
        skipped_relations=result.skipped_relations,
        reused_entities=result.reused_entities,
        created_entities=result.created_entities,
        chunks=[_chunk_response(item) for item in result.chunks],
    )


@router.get(
    "/ingest/chunks/{chunk_id}",
    response_model=SourceChunkGraphResponse,
)
def source_chunk_graph(
    chunk_id: UUID,
    service: GraphIngestionService = Depends(get_graph_ingestion_service),
) -> SourceChunkGraphResponse:
    return SourceChunkGraphResponse.model_validate(service.source_chunk_stats(chunk_id))
