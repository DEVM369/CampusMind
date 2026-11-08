from __future__ import annotations

import json
import uuid
from datetime import date, datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from campusmind.config import get_settings
from campusmind.api.dependencies import require_capability, trusted_actor
from campusmind.platform.document_access import DocumentAccessService
from campusmind.platform.db import Document, DocumentChunk, DocumentVersion
from campusmind.platform.db import get_db
from campusmind.knowledge.ingestion import UnsupportedDocumentType
from campusmind.knowledge.ingestion import DocumentIngestionService
from campusmind.platform.infrastructure import RustFSObjectStorage
from campusmind.api.schemas import (
    DocumentChunkItem,
    DocumentChunksResponse,
    DocumentDetailResponse,
    DocumentDownloadUrlResponse,
    DocumentUploadResponse,
    DocumentVersionItem,
)

router = APIRouter()


def _accessible_document(db, actor, document_id, *, write=False):
    try:
        access = DocumentAccessService(db, actor)
        if write:
            access.require_write(document_id)
        return access.require_document(document_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


def _version_item(row: DocumentVersion) -> DocumentVersionItem:
    return DocumentVersionItem(
        id=row.id,
        version=row.version,
        status=row.status,
        object_key=row.object_key,
        effective_from=row.effective_from,
        effective_to=row.effective_to,
        published_at=row.published_at,
        department=row.department,
        metadata=row.metadata_json or {},
    )


@router.post("/upload", response_model=DocumentUploadResponse)
def upload_document(
    file: UploadFile = File(...),
    knowledge_base_code: str = Form(...),
    document_type: str = Form(...),
    version: str = Form("1.0"),
    title: str | None = Form(None),
    department: str | None = Form(None),
    effective_from: date | None = Form(None),
    effective_to: date | None = Form(None),
    published_at: datetime | None = Form(None),
    permission_level: str = Form("campus"),
    document_id: uuid.UUID | None = Form(None),
    db: Session = Depends(get_db),
    actor=Depends(require_capability("document.upload")),
) -> DocumentUploadResponse:
    if document_id is not None:
        _accessible_document(db, actor, document_id, write=True)
    if permission_level not in DocumentAccessService(db, actor).scope.permission_levels:
        raise HTTPException(status_code=403, detail="Document permission level is not allowed")
    try:
        content = file.file.read()
        result = DocumentIngestionService(db).ingest(
            filename=file.filename or "document",
            content=content,
            knowledge_base_code=knowledge_base_code,
            document_type=document_type,
            version=version,
            title=title,
            department=department,
            effective_from=effective_from,
            effective_to=effective_to,
            published_at=published_at,
            permission_level=permission_level,
            document_id=document_id,
            mime_type=file.content_type,
            owner_user_id=actor,
        )
        db.commit()
        return DocumentUploadResponse(
            document_id=result.document_id,
            document_version_id=result.document_version_id,
            status=result.status,
            object_key=result.object_key,
            parser=result.parser_name,
            chunk_count=result.chunk_count,
            embedding_model=result.embedding_model,
            embedding_dimensions=result.embedding_dimensions,
        )
    except (ValueError, UnsupportedDocumentType) as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        raise


@router.get("/{document_id}", response_model=DocumentDetailResponse)
def get_document(document_id: uuid.UUID, db: Session = Depends(get_db), actor=Depends(trusted_actor)) -> DocumentDetailResponse:
    document, versions = _accessible_document(db, actor, document_id)
    return DocumentDetailResponse(
        id=document.id,
        knowledge_base_id=document.knowledge_base_id,
        title=document.title,
        object_key=document.object_key,
        mime_type=document.mime_type,
        checksum_sha256=document.checksum_sha256,
        document_type=document.document_type,
        status=document.status,
        versions=[_version_item(row) for row in versions],
    )


@router.get("/{document_id}/chunks", response_model=DocumentChunksResponse)
def get_document_chunks(document_id: uuid.UUID, db: Session = Depends(get_db), actor=Depends(trusted_actor)) -> DocumentChunksResponse:
    _, versions = _accessible_document(db, actor, document_id)
    rows = list(db.scalars(
        select(DocumentChunk)
        .join(DocumentVersion, DocumentVersion.id == DocumentChunk.document_version_id)
        .where(
            DocumentChunk.document_id == document_id,
            DocumentVersion.status == "active",
            DocumentVersion.id.in_([v.id for v in versions]),
            DocumentAccessService(db, actor).chunk_predicate(),
        )
        .order_by(DocumentChunk.chunk_index)
    ))
    return DocumentChunksResponse(
        document_id=document_id,
        total=len(rows),
        chunks=[
            DocumentChunkItem(
                id=row.id,
                document_version_id=row.document_version_id,
                chunk_index=row.chunk_index,
                content=row.content,
                token_count=row.token_count,
                page=row.page,
                chapter=row.chapter,
                section=row.section,
                embedding_model=row.embedding_model,
                embedding_dimensions=row.embedding_dimensions,
                metadata=row.metadata_json or {},
            )
            for row in rows
        ],
    )


@router.get("/{document_id}/download-url", response_model=DocumentDownloadUrlResponse)
def get_document_download_url(document_id: uuid.UUID, db: Session = Depends(get_db), actor=Depends(trusted_actor)) -> DocumentDownloadUrlResponse:
    document, _ = _accessible_document(db, actor, document_id)
    settings = get_settings()
    storage = RustFSObjectStorage(settings)
    url = storage.presigned_get_url(
        document.object_key,
        expires_seconds=settings.ingestion_download_url_ttl_seconds,
    )
    return DocumentDownloadUrlResponse(
        document_id=document.id,
        object_key=document.object_key,
        url=url,
        expires_seconds=settings.ingestion_download_url_ttl_seconds,
    )
