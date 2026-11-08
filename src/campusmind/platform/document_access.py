from __future__ import annotations

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from campusmind.platform.db import (
    Document,
    DocumentChunk,
    DocumentPermission,
    DocumentVersion,
    UserRole,
)
from campusmind.platform.security import AuthorizationService, KnowledgeAclService


class DocumentAccessService:
    """Authorize complete versions before exposing metadata or signing raw files."""

    def __init__(self, session: Session, actor) -> None:
        self.session = session
        self.actor = actor
        self.authorization = AuthorizationService(session)
        self.scope = KnowledgeAclService(session).scope(actor)

    def _explicit_access(self, document_id, *, write=False) -> bool | None:
        grants = list(self.session.scalars(select(DocumentPermission).where(
            DocumentPermission.document_id == document_id)))
        if not grants:
            return None
        roles = set(self.session.scalars(select(UserRole.role_id).where(
            UserRole.user_id == self.actor)))
        levels = {"write", "admin", "owner"} if write else {"read", "write", "admin", "owner"}
        return any(
            row.permission_level in levels
            and ((row.subject_type == "user" and row.subject_id == self.actor)
                 or (row.subject_type == "role" and row.subject_id in roles))
            for row in grants
        )

    def can_read_version(self, version: DocumentVersion) -> bool:
        explicit = self._explicit_access(version.document_id)
        if explicit is False:
            return False
        security = (version.metadata_json or {}).get("security") or {}
        level = security.get("permission_level")
        if level == "personal" and security.get("owner_user_id") != str(self.actor):
            return False
        if level == "department" and explicit is not True:
            # A role family alone cannot establish membership of a specific department.
            return security.get("owner_user_id") == str(self.actor) or self.authorization.authorize(
                "knowledge.manage", self.actor).allowed
        if level:
            return level in self.scope.permission_levels
        # Chunk RLS cannot prove permission to an entire legacy object: hidden
        # chunks would make a partial scan look like complete authorization.
        return explicit is True or self.authorization.authorize(
            "knowledge.manage", self.actor).allowed

    def require_document(self, document_id) -> tuple[Document, list[DocumentVersion]]:
        document = self.session.get(Document, document_id)
        if document is None:
            raise LookupError("Document not found")
        versions = list(self.session.scalars(select(DocumentVersion).where(
            DocumentVersion.document_id == document_id).order_by(
                DocumentVersion.created_at.desc())))
        current = [v for v in versions if v.status == "active"
                   and v.object_key == document.object_key]
        if not current or not all(self.can_read_version(v) for v in current):
            raise PermissionError("Document access denied")
        return document, [v for v in versions if self.can_read_version(v)]

    def require_write(self, document_id) -> None:
        document, versions = self.require_document(document_id)
        explicit = self._explicit_access(document_id, write=True)
        if explicit is True:
            return
        if explicit is None:
            current = [v for v in versions if v.object_key == document.object_key]
            if all((v.metadata_json or {}).get("security", {}).get("owner_user_id")
                   == str(self.actor) for v in current):
                return
            if self.authorization.authorize("knowledge.manage", self.actor).allowed:
                return
        raise PermissionError("Document write access denied")

    def chunk_predicate(self):
        owner = func.coalesce(
            DocumentChunk.metadata_json["owner_user_id"].as_string(),
            DocumentChunk.metadata_json["actor_user_id"].as_string(), "")
        level = func.lower(DocumentChunk.permission_level)
        return and_(
            level.in_(self.scope.permission_levels),
            or_(level != "personal", owner == str(self.actor)),
        )

    def require_chunk(self, chunk_id) -> DocumentChunk:
        chunk = self.session.scalar(select(DocumentChunk).where(
            DocumentChunk.id == chunk_id, self.chunk_predicate()))
        if chunk is None:
            raise LookupError("Document chunk not found")
        _, versions = self.require_document(chunk.document_id)
        if chunk.document_version_id not in {v.id for v in versions}:
            raise PermissionError("Document version access denied")
        return chunk
