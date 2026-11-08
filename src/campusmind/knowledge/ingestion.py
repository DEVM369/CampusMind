from __future__ import annotations

import uuid
from sqlalchemy import select
from sqlalchemy.orm import Session
from campusmind.platform.db import Document, DocumentChunk, DocumentVersion, KnowledgeBase
from dataclasses import dataclass, field
from uuid import UUID
import re
import unicodedata
from datetime import date
from abc import ABC, abstractmethod
from io import BytesIO
from docx import Document as DocxDocument
from pathlib import Path
from openpyxl import load_workbook
from pypdf import PdfReader
import hashlib
from datetime import date, datetime, timezone
from campusmind.config import Settings, get_settings
from campusmind.platform.db import Document, DocumentChunk, DocumentVersion
from campusmind.platform.infrastructure import RustFSObjectStorage
from campusmind.knowledge.rag import EmbeddingProvider, get_embedding_provider

"""CampusMind ingestion domain."""

# ---- app/ingestion/repository.py ----
class IngestionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def knowledge_base_by_code(self, code: str) -> KnowledgeBase:
        kb = self.session.scalar(select(KnowledgeBase).where(KnowledgeBase.code == code))
        if kb is None:
            raise ValueError(f"Unknown knowledge base: {code}")
        return kb

    def document_by_id(self, document_id: uuid.UUID) -> Document:
        document = self.session.get(Document, document_id)
        if document is None:
            raise ValueError(f"Document not found: {document_id}")
        return document

    def version_exists(self, document_id: uuid.UUID, version: str) -> bool:
        return self.session.scalar(
            select(DocumentVersion.id).where(
                DocumentVersion.document_id == document_id,
                DocumentVersion.version == version,
            )
        ) is not None

    def deactivate_versions(self, document_id: uuid.UUID) -> None:
        for version in self.session.scalars(
            select(DocumentVersion).where(
                DocumentVersion.document_id == document_id,
                DocumentVersion.status == "active",
            )
        ):
            version.status = "superseded"

# ---- app/ingestion/types.py ----
@dataclass(slots=True)
class ParsedBlock:
    text: str
    page: int | None = None
    chapter: str | None = None
    section: str | None = None
    paragraph_index: int | None = None
    metadata: dict = field(default_factory=dict)


@dataclass(slots=True)
class ParsedDocument:
    blocks: list[ParsedBlock]
    parser_name: str
    metadata: dict = field(default_factory=dict)


@dataclass(slots=True)
class ChunkDraft:
    index: int
    content: str
    token_count: int
    page: int | None = None
    chapter: str | None = None
    section: str | None = None
    metadata: dict = field(default_factory=dict)


@dataclass(slots=True)
class IngestionResult:
    document_id: UUID
    document_version_id: UUID
    object_key: str
    parser_name: str
    chunk_count: int
    embedding_model: str
    embedding_dimensions: int
    status: str = "parsed"

# ---- app/ingestion/chunker.py ----
def _token_estimate(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]", text))


def _split_long_text(text: str, max_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    sentences = re.split(r"(?<=[。！？!?；;])", text)
    result: list[str] = []
    current = ""
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        if len(sentence) > max_chars:
            if current:
                result.append(current)
                current = ""
            result.extend(sentence[i:i + max_chars] for i in range(0, len(sentence), max_chars))
            continue
        candidate = sentence if not current else current + sentence
        if len(candidate) > max_chars:
            result.append(current)
            current = sentence
        else:
            current = candidate
    if current:
        result.append(current)
    return result


class StructureAwareChunker:
    def __init__(self, *, max_chars: int = 1200, overlap_chars: int = 120) -> None:
        if max_chars < 200:
            raise ValueError("max_chars must be >= 200")
        self.max_chars = max_chars
        self.overlap_chars = max(0, min(overlap_chars, max_chars // 3))

    def chunk(self, document: ParsedDocument) -> list[ChunkDraft]:
        chunks: list[ChunkDraft] = []
        current_parts: list[str] = []
        current_meta: ParsedBlock | None = None

        def flush() -> None:
            nonlocal current_parts, current_meta
            if not current_parts or current_meta is None:
                return
            content = "\n".join(current_parts).strip()
            chunks.append(ChunkDraft(
                index=len(chunks),
                content=content,
                token_count=_token_estimate(content),
                page=current_meta.page,
                chapter=current_meta.chapter,
                section=current_meta.section,
                metadata=dict(current_meta.metadata),
            ))
            tail = content[-self.overlap_chars:].strip() if self.overlap_chars else ""
            current_parts = [tail] if tail else []

        for block in document.blocks:
            pieces = _split_long_text(block.text, self.max_chars)
            for piece in pieces:
                structure_changed = (
                    current_meta is not None
                    and (current_meta.page, current_meta.chapter, current_meta.section)
                    != (block.page, block.chapter, block.section)
                )
                if structure_changed:
                    flush()
                    current_parts = []
                current_meta = block
                candidate = piece if not current_parts else "\n".join([*current_parts, piece])
                if len(candidate) > self.max_chars and current_parts:
                    flush()
                current_parts.append(piece)
        flush()
        for index, chunk in enumerate(chunks):
            chunk.index = index
        return chunks

# ---- app/ingestion/cleaner.py ----
class DocumentCleaner:
    def clean_text(self, text: str) -> str:
        text = unicodedata.normalize("NFKC", text or "")
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        lines = []
        for line in text.split("\n"):
            line = re.sub(r"[ \t]+", " ", line).strip()
            if line:
                lines.append(line)
        return "\n".join(lines).strip()

    def clean(self, document: ParsedDocument) -> ParsedDocument:
        blocks: list[ParsedBlock] = []
        for block in document.blocks:
            text = self.clean_text(block.text)
            if not text:
                continue
            blocks.append(
                ParsedBlock(
                    text=text,
                    page=block.page,
                    chapter=block.chapter,
                    section=block.section,
                    paragraph_index=block.paragraph_index,
                    metadata=dict(block.metadata),
                )
            )
        return ParsedDocument(
            blocks=blocks,
            parser_name=document.parser_name,
            metadata=dict(document.metadata),
        )

# ---- app/ingestion/metadata.py ----
class MetadataExtractor:
    def enrich_chunk(
        self,
        chunk: ChunkDraft,
        *,
        document_type: str,
        department: str | None,
        effective_from: date | None,
        source_filename: str,
        parser_name: str,
    ) -> dict:
        metadata = dict(chunk.metadata)
        metadata.update({
            "source_filename": source_filename,
            "parser": parser_name,
            "document_type": document_type,
            "department": department,
            "effective_from": effective_from.isoformat() if effective_from else None,
            "page": chunk.page,
            "chapter": chunk.chapter,
            "section": chunk.section,
        })
        return {key: value for key, value in metadata.items() if value is not None}

# ---- app/ingestion/parsers/base.py ----
_HEADING_CHAPTER = re.compile(r"^(第[一二三四五六七八九十百0-9]+章|[一二三四五六七八九十]+、|\d+\s+\S+)")
_HEADING_SECTION = re.compile(r"^(第[一二三四五六七八九十百0-9]+节|\d+\.\d+(?:\.\d+)*\s*\S*)")


def infer_heading_level(line: str) -> int | None:
    value = line.strip()
    if not value or len(value) > 80:
        return None
    if _HEADING_SECTION.match(value):
        return 2
    if _HEADING_CHAPTER.match(value):
        return 1
    if value.endswith(("：", ":")) and len(value) <= 40:
        return 2
    return None


def lines_to_blocks(lines: list[str], *, page: int | None = None, metadata: dict | None = None) -> list[ParsedBlock]:
    chapter: str | None = None
    section: str | None = None
    blocks: list[ParsedBlock] = []
    paragraph_index = 0
    for raw in lines:
        text = (raw or "").strip()
        if not text:
            continue
        level = infer_heading_level(text)
        if level == 1:
            chapter = text
            section = None
            continue
        if level == 2:
            section = text.rstrip("：:")
            continue
        blocks.append(
            ParsedBlock(
                text=text,
                page=page,
                chapter=chapter,
                section=section,
                paragraph_index=paragraph_index,
                metadata=dict(metadata or {}),
            )
        )
        paragraph_index += 1
    return blocks


class DocumentParser(ABC):
    name: str

    @abstractmethod
    def parse(self, content: bytes, *, filename: str) -> ParsedDocument:
        raise NotImplementedError

# ---- app/ingestion/parsers/docx.py ----
class DocxParser(DocumentParser):
    name = "docx"

    def parse(self, content: bytes, *, filename: str) -> ParsedDocument:
        doc = DocxDocument(BytesIO(content))
        chapter: str | None = None
        section: str | None = None
        blocks: list[ParsedBlock] = []
        paragraph_index = 0
        for paragraph in doc.paragraphs:
            text = paragraph.text.strip()
            if not text:
                continue
            style = (paragraph.style.name or "").lower() if paragraph.style else ""
            if style.startswith("heading"):
                try:
                    level = int(style.split()[-1])
                except (ValueError, IndexError):
                    level = 2
                if level == 1:
                    chapter = text
                    section = None
                else:
                    section = text
                continue
            blocks.append(ParsedBlock(
                text=text,
                chapter=chapter,
                section=section,
                paragraph_index=paragraph_index,
            ))
            paragraph_index += 1

        for table_index, table in enumerate(doc.tables, start=1):
            for row_index, row in enumerate(table.rows, start=1):
                cells = [cell.text.strip() for cell in row.cells]
                text = " | ".join(value for value in cells if value)
                if text:
                    blocks.append(ParsedBlock(
                        text=text,
                        chapter=chapter,
                        section=section or f"Table {table_index}",
                        paragraph_index=paragraph_index,
                        metadata={"table": table_index, "row": row_index},
                    ))
                    paragraph_index += 1
        return ParsedDocument(
            blocks=blocks,
            parser_name=self.name,
            metadata={"filename": filename},
        )

# ---- app/ingestion/parsers/excel.py ----
class ExcelParser(DocumentParser):
    name = "excel"

    def parse(self, content: bytes, *, filename: str) -> ParsedDocument:
        suffix = Path(filename).suffix.lower()
        if suffix == ".xls":
            return self._parse_xls(content, filename)
        return self._parse_xlsx(content, filename)

    def _parse_xlsx(self, content: bytes, filename: str) -> ParsedDocument:
        workbook = load_workbook(BytesIO(content), read_only=True, data_only=True)
        blocks: list[ParsedBlock] = []
        paragraph_index = 0
        for sheet in workbook.worksheets:
            rows = list(sheet.iter_rows(values_only=True))
            if not rows:
                continue
            headers = [str(v).strip() if v is not None else "" for v in rows[0]]
            for row_number, row in enumerate(rows[1:], start=2):
                parts = []
                for col_index, value in enumerate(row):
                    if value is None or str(value).strip() == "":
                        continue
                    label = headers[col_index] if col_index < len(headers) and headers[col_index] else f"column_{col_index + 1}"
                    parts.append(f"{label}: {value}")
                if parts:
                    blocks.append(ParsedBlock(
                        text="; ".join(parts),
                        chapter=sheet.title,
                        section=f"row {row_number}",
                        paragraph_index=paragraph_index,
                        metadata={"sheet": sheet.title, "row": row_number},
                    ))
                    paragraph_index += 1
        return ParsedDocument(blocks=blocks, parser_name=self.name, metadata={"filename": filename})

    def _parse_xls(self, content: bytes, filename: str) -> ParsedDocument:
        import xlrd
        book = xlrd.open_workbook(file_contents=content)
        blocks: list[ParsedBlock] = []
        paragraph_index = 0
        for sheet in book.sheets():
            if sheet.nrows == 0:
                continue
            headers = [str(sheet.cell_value(0, col)).strip() for col in range(sheet.ncols)]
            for row_number in range(1, sheet.nrows):
                parts = []
                for col in range(sheet.ncols):
                    value = sheet.cell_value(row_number, col)
                    if value in (None, ""):
                        continue
                    label = headers[col] or f"column_{col + 1}"
                    parts.append(f"{label}: {value}")
                if parts:
                    blocks.append(ParsedBlock(
                        text="; ".join(parts),
                        chapter=sheet.name,
                        section=f"row {row_number + 1}",
                        paragraph_index=paragraph_index,
                        metadata={"sheet": sheet.name, "row": row_number + 1},
                    ))
                    paragraph_index += 1
        return ParsedDocument(blocks=blocks, parser_name=self.name, metadata={"filename": filename})

# ---- app/ingestion/parsers/pdf.py ----
class PdfParser(DocumentParser):
    name = "pdf"

    def parse(self, content: bytes, *, filename: str) -> ParsedDocument:
        reader = PdfReader(BytesIO(content))
        blocks = []
        for page_index, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            blocks.extend(lines_to_blocks(text.splitlines(), page=page_index))
        return ParsedDocument(
            blocks=blocks,
            parser_name=self.name,
            metadata={"filename": filename, "page_count": len(reader.pages)},
        )

# ---- app/ingestion/parsers/text.py ----
def _decode(content: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="replace")


class TextParser(DocumentParser):
    name = "text"

    def parse(self, content: bytes, *, filename: str) -> ParsedDocument:
        text = _decode(content)
        return ParsedDocument(
            blocks=lines_to_blocks(text.splitlines()),
            parser_name=self.name,
            metadata={"filename": filename},
        )

# ---- app/ingestion/parsers/markdown.py ----
class MarkdownParser(DocumentParser):
    name = "markdown"

    def parse(self, content: bytes, *, filename: str) -> ParsedDocument:
        text = _decode(content)
        chapter: str | None = None
        section: str | None = None
        paragraphs: list[str] = []
        blocks: list[ParsedBlock] = []
        paragraph_index = 0

        def flush() -> None:
            nonlocal paragraph_index
            if not paragraphs:
                return
            value = "\n".join(paragraphs).strip()
            paragraphs.clear()
            if value:
                blocks.append(ParsedBlock(
                    text=value,
                    chapter=chapter,
                    section=section,
                    paragraph_index=paragraph_index,
                ))
                paragraph_index += 1

        for raw in text.splitlines():
            match = re.match(r"^(#{1,6})\s+(.+?)\s*$", raw)
            if match:
                flush()
                level = len(match.group(1))
                heading = match.group(2).strip()
                if level == 1:
                    chapter = heading
                    section = None
                else:
                    section = heading
                continue
            if not raw.strip():
                flush()
            else:
                paragraphs.append(raw.strip())
        flush()
        return ParsedDocument(
            blocks=blocks,
            parser_name=self.name,
            metadata={"filename": filename},
        )

# ---- app/ingestion/parsers/registry.py ----
class UnsupportedDocumentType(ValueError):
    pass


class ParserRegistry:
    def __init__(self) -> None:
        text = TextParser()
        excel = ExcelParser()
        self._parsers: dict[str, DocumentParser] = {
            ".pdf": PdfParser(),
            ".docx": DocxParser(),
            ".txt": text,
            ".md": MarkdownParser(),
            ".markdown": MarkdownParser(),
            ".xlsx": excel,
            ".xlsm": excel,
            ".xls": excel,
        }

    @property
    def supported_extensions(self) -> tuple[str, ...]:
        return tuple(sorted(self._parsers))

    def get(self, filename: str) -> DocumentParser:
        suffix = Path(filename).suffix.lower()
        try:
            return self._parsers[suffix]
        except KeyError as exc:
            raise UnsupportedDocumentType(
                f"Unsupported file type {suffix!r}; supported: {', '.join(self.supported_extensions)}"
            ) from exc

# ---- app/ingestion/service.py ----
def _safe_component(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip())
    return value.strip("-.") or "document"


class DocumentIngestionService:
    def __init__(
        self,
        session: Session,
        *,
        settings: Settings | None = None,
        storage: RustFSObjectStorage | None = None,
        embedding_provider: EmbeddingProvider | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.repository = IngestionRepository(session)
        self.storage = storage or RustFSObjectStorage(self.settings)
        self.embedding = embedding_provider or get_embedding_provider()
        self.parsers = ParserRegistry()
        self.cleaner = DocumentCleaner()
        self.chunker = StructureAwareChunker(
            max_chars=self.settings.ingestion_chunk_max_chars,
            overlap_chars=self.settings.ingestion_chunk_overlap_chars,
        )
        self.metadata = MetadataExtractor()

    def ingest(
        self,
        *,
        filename: str,
        content: bytes,
        knowledge_base_code: str,
        document_type: str,
        version: str = "1.0",
        title: str | None = None,
        department: str | None = None,
        effective_from: date | None = None,
        effective_to: date | None = None,
        published_at: datetime | None = None,
        permission_level: str = "campus",
        document_id: uuid.UUID | None = None,
        mime_type: str | None = None,
        owner_user_id: uuid.UUID | None = None,
    ) -> IngestionResult:
        if not content:
            raise ValueError("Uploaded file is empty")
        if len(content) > self.settings.ingestion_max_file_mb * 1024 * 1024:
            raise ValueError(f"File exceeds {self.settings.ingestion_max_file_mb} MB limit")
        parser = self.parsers.get(filename)
        kb = self.repository.knowledge_base_by_code(knowledge_base_code)

        document_uuid = document_id or uuid.uuid4()
        version_uuid = uuid.uuid4()
        object_key = "/".join([
            "documents",
            _safe_component(kb.code),
            str(document_uuid),
            _safe_component(version),
            _safe_component(Path(filename).name),
        ])
        if document_id is not None:
            document = self.repository.document_by_id(document_id)
            if document.knowledge_base_id != kb.id:
                raise ValueError("Existing document belongs to another knowledge base")
            if self.repository.version_exists(document.id, version):
                raise ValueError(f"Document version already exists: {version}")
        else:
            document = Document(
                id=document_uuid,
                knowledge_base_id=kb.id,
                title=(title or Path(filename).stem).strip(),
                object_key=object_key,
                mime_type=mime_type or "application/octet-stream",
                checksum_sha256=None,
                document_type=document_type,
                status="processing",
            )
            self.session.add(document)

            # Persist the parent document before creating dependent
            # document_versions/document_chunks rows.
            #
            # flush() does NOT commit the transaction. It only guarantees
            # that the parent row exists for subsequent foreign keys.
            self.session.flush()

        checksum = hashlib.sha256(content).hexdigest()
        uploaded = False
        try:
            self.storage.put_bytes(
                object_key,
                content,
                content_type=mime_type or "application/octet-stream",
                metadata={"sha256": checksum, "document-id": str(document_uuid), "version": version},
            )
            uploaded = True

            parsed = self.cleaner.clean(parser.parse(content, filename=filename))
            if not parsed.blocks:
                raise ValueError("Parser produced no text blocks")
            drafts = self.chunker.chunk(parsed)
            if not drafts:
                raise ValueError("Chunker produced no chunks")
            vectors = self.embedding.embed_documents([draft.content for draft in drafts])
            if len(vectors) != len(drafts):
                raise RuntimeError("Embedding provider returned an unexpected number of vectors")

            self.repository.deactivate_versions(document_uuid)
            version_row = DocumentVersion(
                id=version_uuid,
                document_id=document_uuid,
                version=version,
                object_key=object_key,
                status="active",
                effective_from=effective_from,
                effective_to=effective_to,
                published_at=published_at,
                department=department,
                metadata_json={
                    **parsed.metadata,
                    "source_filename": filename,
                    "parser": parsed.parser_name,
                    "sha256": checksum,
                    "security": {
                        "permission_level": permission_level,
                        "owner_user_id": str(owner_user_id) if owner_user_id else None,
                    },
                },
            )
            self.session.add(version_row)

            # document_chunks.document_version_id is a real PostgreSQL
            # foreign key. Persist the version row before adding chunks.
            #
            # Do not rely on ORM flush ordering here because the models
            # use explicit UUID foreign-key values rather than an ORM
            # relationship dependency.
            self.session.flush()

            now = datetime.now(timezone.utc)
            for draft, vector in zip(drafts, vectors, strict=True):
                self.session.add(DocumentChunk(
                    document_id=document_uuid,
                    document_version_id=version_uuid,
                    knowledge_base_id=kb.id,
                    chunk_index=draft.index,
                    content=draft.content,
                    token_count=draft.token_count,
                    page=draft.page,
                    chapter=draft.chapter,
                    section=draft.section,
                    department=department,
                    document_type=document_type,
                    effective_date=effective_from,
                    permission_level=permission_level,
                    metadata_json={**self.metadata.enrich_chunk(
                        draft,
                        document_type=document_type,
                        department=department,
                        effective_from=effective_from,
                        source_filename=filename,
                        parser_name=parsed.parser_name,
                    ), "owner_user_id": str(owner_user_id) if owner_user_id else None},
                    embedding=vector,
                    embedding_model=self.embedding.model,
                    embedding_dimensions=len(vector),
                    embedded_at=now,
                ))

            document.title = (title or document.title or Path(filename).stem).strip()
            document.object_key = object_key
            document.mime_type = mime_type or document.mime_type or "application/octet-stream"
            document.checksum_sha256 = checksum
            document.document_type = document_type
            document.status = "parsed"
            self.session.flush()
            return IngestionResult(
                document_id=document_uuid,
                document_version_id=version_uuid,
                object_key=object_key,
                parser_name=parsed.parser_name,
                chunk_count=len(drafts),
                embedding_model=self.embedding.model,
                embedding_dimensions=self.embedding.dimensions,
            )
        except Exception:
            if uploaded:
                try:
                    self.storage.delete(object_key)
                except Exception:
                    pass
            raise
