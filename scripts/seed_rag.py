from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

from sqlalchemy import select

from campusmind.platform.db import Document, DocumentChunk, DocumentVersion, KnowledgeBase
from campusmind.platform.db import get_session_factory

ROOT = Path(__file__).resolve().parents[1]
DATA = json.loads((ROOT / "datasets" / "rag_seed.json").read_text(encoding="utf-8"))


def one(session, model, **where):
    return session.scalar(select(model).filter_by(**where))


def main() -> None:
    created_chunks = 0
    with get_session_factory().begin() as session:
        for spec in DATA["documents"]:
            kb = one(session, KnowledgeBase, code=spec["knowledge_base"])
            if kb is None:
                raise RuntimeError(f"Missing knowledge base: {spec['knowledge_base']}; run python -m scripts.seed_core first")

            document = one(session, Document, object_key=spec["object_key"])
            if document is None:
                document = Document(
                    knowledge_base_id=kb.id,
                    title=spec["title"],
                    object_key=spec["object_key"],
                    mime_type="text/markdown",
                    document_type=spec["document_type"],
                    status="parsed",
                )
                session.add(document)
                session.flush()

            version = one(session, DocumentVersion, document_id=document.id, version=spec["version"])
            if version is None:
                version = DocumentVersion(
                    document_id=document.id,
                    version=spec["version"],
                    object_key=document.object_key,
                    status="active",
                    effective_from=date(2026, 9, 1),
                    published_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
                    department=spec["department"],
                    metadata_json={"synthetic": True, "seed_profile": "rag"},
                )
                session.add(version)
                session.flush()

            for chunk_spec in spec["chunks"]:
                chunk = one(
                    session,
                    DocumentChunk,
                    document_version_id=version.id,
                    chunk_index=chunk_spec["index"],
                )
                if chunk is None:
                    session.add(
                        DocumentChunk(
                            document_id=document.id,
                            document_version_id=version.id,
                            knowledge_base_id=kb.id,
                            chunk_index=chunk_spec["index"],
                            content=chunk_spec["content"],
                            page=chunk_spec["page"],
                            chapter=chunk_spec["chapter"],
                            section=chunk_spec["section"],
                            department=spec["department"],
                            document_type=spec["document_type"],
                            effective_date=date(2026, 9, 1),
                            permission_level="campus",
                            metadata_json={"synthetic": True, "seed_profile": "rag"},
                            embedding=None,
                        )
                    )
                    created_chunks += 1

    print(f"CampusMind RAG layer synthetic RAG corpus is ready; newly created chunks={created_chunks}.")


if __name__ == "__main__":
    main()
