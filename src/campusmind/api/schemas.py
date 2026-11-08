from __future__ import annotations

from uuid import UUID
from pydantic import BaseModel, Field
from datetime import date
from typing import Any
from campusmind.knowledge.graph import EntityType, RelationType
import uuid
from datetime import date, datetime
from datetime import datetime, timezone
from typing import Any, Literal

# ---- rag.py ----
class Citation(BaseModel):
    chunk_id: UUID
    document_id: UUID
    title: str
    page: int | None = None
    section: str | None = None
    chapter: str | None = None
    object_key: str
    quote: str


class RetrievalHitResponse(BaseModel):
    chunk_id: UUID
    content: str
    score: float
    vector_score: float | None = None
    keyword_score: float | None = None
    rrf_score: float
    ranks: dict[str, int]
    citation: Citation


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=20)


class SearchResponse(BaseModel):
    query: str
    rewritten_query: str
    vector_count: int
    keyword_count: int
    elapsed_ms: float
    hits: list[RetrievalHitResponse]


class ChatRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    top_k: int = Field(default=5, ge=1, le=20)


class ChatResponse(BaseModel):
    trace_id: str
    answer: str
    citations: list[Citation]
    retrieval: SearchResponse


class RagStatusResponse(BaseModel):
    embedding_provider: str
    embedding_model: str
    embedding_dimensions: int
    llm_provider: str
    llm_model: str


class ModelComponentCheck(BaseModel):
    ok: bool
    provider: str
    model: str
    latency_ms: float
    detail: str
    dimensions: int | None = None


class ModelCheckResponse(BaseModel):
    status: str
    embedding: ModelComponentCheck
    llm: ModelComponentCheck

# ---- graph.py ----
class GraphEvidenceModel(BaseModel):
    source_document_id: str = Field(min_length=1)
    source_chunk_id: str = Field(min_length=1)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    effective_from: date | None = None
    effective_to: date | None = None


class GraphEntityUpsertRequest(BaseModel):
    entity_id: str = Field(min_length=1, max_length=200)
    entity_type: EntityType
    name: str = Field(min_length=1, max_length=500)
    aliases: list[str] = Field(default_factory=list)
    description: str | None = None
    properties: dict[str, Any] = Field(default_factory=dict)
    evidence: GraphEvidenceModel | None = None


class GraphRelationUpsertRequest(BaseModel):
    relation_id: str = Field(min_length=1, max_length=240)
    relation_type: RelationType
    source_id: str = Field(min_length=1, max_length=200)
    source_type: EntityType
    target_id: str = Field(min_length=1, max_length=200)
    target_type: EntityType
    properties: dict[str, Any] = Field(default_factory=dict)
    evidence: GraphEvidenceModel


class GraphMutationResponse(BaseModel):
    status: str = "ok"
    data: dict[str, Any]


class GraphOntologyResponse(BaseModel):
    entity_count: int
    relation_count: int
    entities: list[dict[str, Any]]
    relations: list[dict[str, Any]]


class GraphStatsResponse(BaseModel):
    node_count: int
    relation_count: int
    nodes_by_type: dict[str, int]
    relations_by_type: dict[str, int]


class GraphBootstrapResponse(BaseModel):
    status: str = "ok"
    constraints: int
    indexes: int

# ---- graph_rag.py ----
class GraphRagRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    max_paths: int = Field(default=12, ge=1, le=30)


class LinkedEntityResponse(BaseModel):
    query_name: str
    entity_id: str
    entity_type: str
    name: str
    aliases: list[str] = Field(default_factory=list)
    confidence: float


class GraphPathResponse(BaseModel):
    source_id: str
    source_name: str
    source_type: str
    relation_type: str
    target_id: str
    target_name: str
    target_type: str
    relation_id: str | None = None
    source_document_id: str | None = None
    source_chunk_id: str | None = None
    confidence: float | None = None
    path_id: str | None = None
    hop_index: int = 1
    text: str


class GraphPlanResponse(BaseModel):
    entities: list[dict]
    relation_types: list[str]
    direction: str
    traversal_steps: list[dict] = Field(default_factory=list)
    max_hops: int


class GraphRagSearchResponse(BaseModel):
    query: str
    plan: GraphPlanResponse
    linked_entities: list[LinkedEntityResponse]
    paths: list[GraphPathResponse]
    citations: list[Citation]
    elapsed_ms: float
    raw_path_count: int = 0
    recovered_evidence_count: int = 0
    diagnostics: list[str] = Field(default_factory=list)


class GraphRagChatResponse(GraphRagSearchResponse):
    trace_id: str
    answer: str

# ---- hybrid_graphrag.py ----
class HybridGraphRagRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    top_k: int = Field(default=6, ge=1, le=20)
    max_paths: int = Field(default=12, ge=1, le=30)


class HybridEvidenceResponse(BaseModel):
    citation: Citation
    sources: list[str]
    graph_score: float
    text_score: float
    rrf_score: float
    lexical_score: float
    fusion_score: float
    graph_path_ids: list[str]


class HybridGraphRagSearchResponse(BaseModel):
    query: str
    rewritten_query: str | None = None
    vector_count: int = 0
    keyword_count: int = 0
    graph_plan: GraphPlanResponse | None = None
    linked_entities: list[LinkedEntityResponse] = Field(default_factory=list)
    graph_paths: list[GraphPathResponse] = Field(default_factory=list)
    evidence: list[HybridEvidenceResponse] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    graph_error: str | None = None
    text_error: str | None = None
    elapsed_ms: float


class HybridGraphRagChatResponse(HybridGraphRagSearchResponse):
    trace_id: str
    answer: str

# ---- adaptive_rag.py ----
class AdaptiveRagRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    top_k: int = Field(default=6, ge=1, le=20)
    max_paths: int = Field(default=12, ge=1, le=30)
    actor_user_id: uuid.UUID | None = None


class AdaptiveRouteDecisionResponse(BaseModel):
    route: str
    intent: str
    complexity: str
    confidence: float
    reasons: list[str]
    executable: bool
    requires_agent: bool
    source: str


class AdaptiveRouteResponse(BaseModel):
    query: str
    decision: AdaptiveRouteDecisionResponse


class AdaptiveEvidenceResponse(BaseModel):
    citation: Citation
    sources: list[str]
    score: float
    graph_path_ids: list[str] = Field(default_factory=list)


class AdaptiveChatResponse(BaseModel):
    trace_id: str
    query: str
    answer: str
    decision: AdaptiveRouteDecisionResponse
    planned_route: str
    executed_route: str | None = None
    citations: list[Citation] = Field(default_factory=list)
    evidence: list[AdaptiveEvidenceResponse] = Field(default_factory=list)
    graph_paths: list[GraphPathResponse] = Field(default_factory=list)
    retrieval: SearchResponse | None = None
    fallback_reason: str | None = None
    deferred_capability: str | None = None
    structured_data: dict | None = None
    elapsed_ms: float

# ---- agent_runtime.py ----
class AgentRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    actor_user_id: uuid.UUID | None = None
    top_k: int = Field(default=6, ge=1, le=20)
    max_paths: int = Field(default=12, ge=1, le=30)
    max_retries: int = Field(default=1, ge=0, le=2)
    max_answer_rewrites: int = Field(default=1, ge=0, le=2)
    persist_trace: bool = True


class AgentPlanResponse(BaseModel):
    route: str
    intent: str
    complexity: str
    risk_level: str
    retrieval_strategy: str
    sub_queries: list[str]
    steps: list[str]
    pending_approval: bool


class AgentValidationResponse(BaseModel):
    passed: bool
    score: float
    reasons: list[str]


class AgentCriticResponse(BaseModel):
    passed: bool
    score: float
    feedback: str
    checks: list[str]


class AgentSubQueryExecutionResponse(BaseModel):
    query: str
    planned_route: str
    executed_route: str | None = None
    evidence_count: int
    graph_path_count: int
    deferred_capability: str | None = None
    structured_data: dict | None = None
    fallback_reason: str | None = None


class AgentStepResponse(BaseModel):
    sequence_no: int
    step_name: str
    step_type: str
    status: str
    latency_ms: float
    input: dict
    output: dict


class AgentPlanOnlyResponse(BaseModel):
    query: str
    planned_route: str
    route_confidence: float
    route_source: str
    plan: AgentPlanResponse


class AgentChatResponse(BaseModel):
    trace_id: str
    query: str
    status: str
    answer: str
    planned_route: str
    active_route: str
    executed_route: str | None = None
    retry_count: int
    answer_rewrite_count: int
    pending_approval: bool
    plan: AgentPlanResponse
    sub_queries: list[str] = Field(default_factory=list)
    subquery_executions: list[AgentSubQueryExecutionResponse] = Field(default_factory=list)
    validation: AgentValidationResponse
    critic: AgentCriticResponse
    citations: list[Citation] = Field(default_factory=list)
    graph_paths: list[GraphPathResponse] = Field(default_factory=list)
    deferred_capability: str | None = None
    structured_data: dict | None = None
    fallback_reason: str | None = None
    steps: list[AgentStepResponse] = Field(default_factory=list)
    elapsed_ms: float
    trace_persisted: bool
    trace_persist_error: str | None = None


class AgentResumeRequest(BaseModel):
    approval_id: uuid.UUID
    actor_user_id: uuid.UUID
    approved: bool
    # Backward-compatible resource selectors. classroom HITL workflow clients can keep room_id;
    # library tools adds book_id and generic resource_id for future Campus Tools.
    room_id: str | None = Field(default=None, max_length=120)
    book_id: str | None = Field(default=None, max_length=120)
    resource_id: str | None = Field(default=None, max_length=120)


class AgentResumeResponse(BaseModel):
    trace_id: str | None = None
    approval_id: str
    actor_user_id: str
    status: str
    answer: str
    structured_data: dict | None = None
    state_changed: bool
    idempotent: bool
    trace_updated: bool
    trace_update_error: str | None = None

# ---- classroom_tools.py ----
class ClassroomPrepareRequest(BaseModel):
    actor_user_id: uuid.UUID
    query: str = Field(min_length=1, max_length=1000)
    trace_id: uuid.UUID | None = None


class ClassroomResumeRequest(BaseModel):
    actor_user_id: uuid.UUID
    approval_id: uuid.UUID
    approved: bool
    room_id: str | None = Field(default=None, max_length=120)


class ClassroomActionResponse(BaseModel):
    approval_id: str
    trace_id: str | None = None
    actor_user_id: str
    status: str
    answer: str
    requested: dict | None = None
    candidates: list[dict] = Field(default_factory=list)
    reservation: dict | None = None
    expires_at: str | None = None
    state_changed: bool = True
    idempotent: bool = False
    audit: dict = Field(default_factory=dict)


class ClassroomReservationListResponse(BaseModel):
    actor_user_id: str
    reservations: list[dict] = Field(default_factory=list)

# ---- course_tools.py ----
class CourseSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    limit: int = Field(default=10, ge=1, le=30)


class CourseSearchResponse(BaseModel):
    courses: list[dict] = Field(default_factory=list)


class CourseQueryRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)


class CourseQueryResponse(BaseModel):
    capability: str
    answer: str
    data: dict
    source: str = "postgresql"
    read_only: bool = True


class CourseScheduleResponse(BaseModel):
    course: dict
    schedules: list[dict] = Field(default_factory=list)
    count: int


class CoursePrerequisiteResponse(BaseModel):
    course: dict
    prerequisites: list[dict] = Field(default_factory=list)
    count: int


class CourseTeacherResponse(BaseModel):
    course: dict
    teachers: list[dict] = Field(default_factory=list)
    count: int

# ---- database.py ----
class DatabaseSchemaStatus(BaseModel):
    status: str
    revision: str | None = None
    table_count: int = Field(ge=0)
    expected_table_count: int = Field(ge=0)
    missing_tables: list[str] = Field(default_factory=list)
    seed_counts: dict[str, int] = Field(default_factory=dict)

# ---- documents.py ----
class DocumentUploadResponse(BaseModel):
    document_id: UUID
    document_version_id: UUID
    status: str
    object_key: str
    parser: str
    chunk_count: int
    embedding_model: str
    embedding_dimensions: int


class DocumentVersionItem(BaseModel):
    id: UUID
    version: str
    status: str
    object_key: str
    effective_from: date | None = None
    effective_to: date | None = None
    published_at: datetime | None = None
    department: str | None = None
    metadata: dict = Field(default_factory=dict)


class DocumentDetailResponse(BaseModel):
    id: UUID
    knowledge_base_id: UUID
    title: str
    object_key: str
    mime_type: str
    checksum_sha256: str | None = None
    document_type: str
    status: str
    versions: list[DocumentVersionItem] = Field(default_factory=list)


class DocumentChunkItem(BaseModel):
    id: UUID
    document_version_id: UUID
    chunk_index: int
    content: str
    token_count: int | None = None
    page: int | None = None
    chapter: str | None = None
    section: str | None = None
    embedding_model: str | None = None
    embedding_dimensions: int | None = None
    metadata: dict = Field(default_factory=dict)


class DocumentChunksResponse(BaseModel):
    document_id: UUID
    total: int
    chunks: list[DocumentChunkItem]


class DocumentDownloadUrlResponse(BaseModel):
    document_id: UUID
    object_key: str
    url: str
    expires_seconds: int

# ---- graph_ingestion.py ----
class ChunkGraphIngestionResponse(BaseModel):
    chunk_id: UUID
    document_id: UUID
    entities_extracted: int = Field(ge=0)
    entities_written: int = Field(ge=0)
    relations_extracted: int = Field(ge=0)
    relations_written: int = Field(ge=0)
    skipped_relations: int = Field(ge=0)
    reused_entities: int = Field(ge=0)
    created_entities: int = Field(ge=0)


class DocumentGraphIngestionResponse(BaseModel):
    document_id: UUID
    chunk_count: int = Field(ge=0)
    entities_extracted: int = Field(ge=0)
    entities_written: int = Field(ge=0)
    relations_extracted: int = Field(ge=0)
    relations_written: int = Field(ge=0)
    skipped_relations: int = Field(ge=0)
    reused_entities: int = Field(ge=0)
    created_entities: int = Field(ge=0)
    chunks: list[ChunkGraphIngestionResponse]


class SourceGraphRelation(BaseModel):
    source_id: str
    source_name: str
    source_type: str
    relation_type: str
    target_id: str
    target_name: str
    target_type: str
    relation_id: str
    source_document_id: str | None = None
    source_chunk_id: str | None = None
    confidence: float | None = None
    created_at: str | None = None


class SourceChunkGraphResponse(BaseModel):
    relation_count: int = Field(ge=0)
    relations: list[SourceGraphRelation]
    evidence_gaps: list[str]

# ---- library_tools.py ----
class LibrarySearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    available_only: bool = False
    limit: int = Field(default=8, ge=1, le=20)


class LibraryPrepareRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    actor_user_id: uuid.UUID
    trace_id: uuid.UUID | None = None


class LibraryResumeRequest(BaseModel):
    approval_id: uuid.UUID
    actor_user_id: uuid.UUID
    approved: bool
    book_id: str | None = Field(default=None, max_length=120)


class LibraryBookResponse(BaseModel):
    book_id: str
    book_code: str
    title: str
    author: str
    isbn: str | None = None
    subject: str | None = None
    location: str
    total_copies: int
    available_copies: int


class LibrarySearchResponse(BaseModel):
    books: list[LibraryBookResponse] = Field(default_factory=list)


class LibraryPrepareResponse(BaseModel):
    approval_id: str
    trace_id: str | None = None
    actor_user_id: str
    status: str
    answer: str
    requested: dict
    candidates: list[LibraryBookResponse] = Field(default_factory=list)
    expires_at: str
    audit: dict = Field(default_factory=dict)


class LibraryActionResponse(BaseModel):
    approval_id: str
    trace_id: str | None = None
    actor_user_id: str
    status: str
    answer: str
    reservation: dict | None = None
    state_changed: bool
    idempotent: bool
    audit: dict = Field(default_factory=dict)


class LibraryReservationListResponse(BaseModel):
    actor_user_id: str
    reservations: list[dict] = Field(default_factory=list)


class LibraryBorrowedListResponse(BaseModel):
    actor_user_id: str
    borrowed_books: list[dict] = Field(default_factory=list)

# ---- multi_agent.py ----
class MultiAgentRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    actor_user_id: uuid.UUID | None = None
    persist_trace: bool = True


class MultiAgentTaskResponse(BaseModel):
    task_id: str
    domain: str
    query: str
    reason: str
    requires_actor: bool
    write_intent: bool
    depends_on: list[str] = Field(default_factory=list)
    context_keys: list[str] = Field(default_factory=list)


class MultiAgentPlanResponse(BaseModel):
    tasks: list[MultiAgentTaskResponse]
    parallelizable: bool
    supervisor_reason: str


class MultiAgentEvidenceResponse(BaseModel):
    evidence_id: str
    task_id: str
    domain: str
    source_kind: str
    source: str
    summary: str
    payload: dict


class MultiAgentChildResponse(BaseModel):
    task_id: str
    domain: str
    query: str
    status: str
    answer: str
    source: str
    pending_approval: bool
    approval_id: str | None = None
    trace_id: str | None = None
    structured_data: dict | None = None
    consumed_context: dict = Field(default_factory=dict)
    evidence: list[MultiAgentEvidenceResponse] = Field(default_factory=list)
    error: str | None = None


class MultiAgentPlanOnlyResponse(BaseModel):
    query: str
    plan: MultiAgentPlanResponse


class MultiAgentChatResponse(BaseModel):
    trace_id: str
    actor_user_id: str | None = None
    query: str
    status: str
    pending_approval: bool
    answer: str
    plan: MultiAgentPlanResponse
    child_results: list[MultiAgentChildResponse]
    elapsed_ms: float
    execution_order: list[str] = Field(default_factory=list)
    shared_context: dict = Field(default_factory=dict)
    evidence: list[MultiAgentEvidenceResponse] = Field(default_factory=list)
    evidence_merge_passed: bool = False
    trace_persisted: bool
    trace_persist_error: str | None = None

# ---- research_tools.py ----
class ResearchSearchRequest(BaseModel):
    query: str = Field(default="", max_length=1000)
    limit: int = Field(default=10, ge=1, le=30)


class ResearchQueryRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)


class ResearchQueryResponse(BaseModel):
    capability: str
    answer: str
    data: dict
    source: str = "postgresql"
    read_only: bool = True


class ResearchListResponse(BaseModel):
    items: list[dict] = Field(default_factory=list)
    count: int

# ---- student_tools.py ----
class StudentToolQueryRequest(BaseModel):
    actor_user_id: uuid.UUID
    query: str = Field(min_length=1, max_length=1000)


class StudentToolResponse(BaseModel):
    capability: str
    actor_user_id: str
    answer: str
    data: dict = Field(default_factory=dict)
    source: str
    self_only: bool

# ---- system.py ----
class ComponentHealth(BaseModel):
    status: Literal["healthy", "unhealthy"]
    message: str
    latency_ms: float = Field(ge=0)
    details: dict[str, Any] = Field(default_factory=dict)


class SystemHealthResponse(BaseModel):
    service: str = "CampusMind"
    status: Literal["healthy", "degraded"]
    checked_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    components: dict[str, ComponentHealth]
