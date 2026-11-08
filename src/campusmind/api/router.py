from __future__ import annotations

from fastapi import APIRouter, Depends

from campusmind.api.dependencies import (
    authenticated_knowledge_scope, public_knowledge_scope, require_capability, trusted_actor,
)
from campusmind.api.routes import (
    auth,
    admin_dashboard,
    adaptive_rag,
    agent_runtime,
    execution_traces,
    evaluation_runner,
    classroom_tools,
    course_tools,
    conversations,
    documents,
    graph,
    graph_ingestion,
    graph_rag,
    hybrid_graphrag,
    library_tools,
    multi_agent,
    rag,
    research_tools,
    student_tools,
    system,
)
from campusmind.api.schemas import AdaptiveChatResponse, AdaptiveRagRequest
from campusmind.config import get_settings
from campusmind.knowledge.adaptive import AdaptiveRagService

from campusmind.api.routes import admin_agent_catalog

router = APIRouter()
router.include_router(
    conversations.router,
    prefix="/conversations",
    tags=["conversations"],
    dependencies=[Depends(authenticated_knowledge_scope)],
)
router.include_router(
    auth.router,
    prefix="/auth",
    tags=["auth"],
)
router.include_router(system.router, prefix="/system", tags=["system"])
router.include_router(admin_dashboard.router, prefix="/admin", tags=["admin-dashboard"], dependencies=[Depends(trusted_actor)])
router.include_router(admin_agent_catalog.router, prefix="/admin", tags=["admin-agent-catalog"], dependencies=[Depends(trusted_actor)])
router.include_router(evaluation_runner.router, prefix="/admin", tags=["evaluation-runner"], dependencies=[Depends(trusted_actor)])
router.include_router(rag.router, prefix="/rag", tags=["rag"], dependencies=[Depends(public_knowledge_scope)])
router.include_router(documents.router, prefix="/documents", tags=["documents"], dependencies=[Depends(authenticated_knowledge_scope)])
router.include_router(graph.router, prefix="/graph", tags=["graph"], dependencies=[Depends(require_capability("knowledge.manage")), Depends(authenticated_knowledge_scope)])
router.include_router(graph_ingestion.router, prefix="/graph", tags=["graph-ingestion"], dependencies=[Depends(require_capability("knowledge.manage")), Depends(authenticated_knowledge_scope)])
router.include_router(graph_rag.router, prefix="/graph-rag", tags=["graph-rag"], dependencies=[Depends(public_knowledge_scope)])
router.include_router(hybrid_graphrag.router, prefix="/hybrid-rag", tags=["hybrid-graphrag"], dependencies=[Depends(public_knowledge_scope)])
router.include_router(adaptive_rag.router, prefix="/adaptive-rag", tags=["adaptive-rag"], dependencies=[Depends(authenticated_knowledge_scope)])
router.include_router(agent_runtime.router, prefix="/agent", tags=["agent-runtime"], dependencies=[Depends(authenticated_knowledge_scope)])
router.include_router(execution_traces.router, prefix="/agent", tags=["agent-traces"], dependencies=[Depends(trusted_actor)])
router.include_router(multi_agent.router, prefix="/multi-agent", tags=["multi-agent"], dependencies=[Depends(authenticated_knowledge_scope)])
router.include_router(student_tools.router, prefix="/tools/student", tags=["student-tools"], dependencies=[Depends(trusted_actor)])
router.include_router(course_tools.router, prefix="/tools/course", tags=["course-tools"])
router.include_router(research_tools.router, prefix="/tools/research", tags=["research-tools"])
router.include_router(classroom_tools.router, prefix="/tools/classroom", tags=["classroom-tools"], dependencies=[Depends(trusted_actor)])
router.include_router(library_tools.router, prefix="/tools/library", tags=["library-tools"], dependencies=[Depends(trusted_actor)])

@router.post("/chat", response_model=AdaptiveChatResponse, tags=["adaptive-rag"], dependencies=[Depends(authenticated_knowledge_scope)])
def chat_alias(
    request: AdaptiveRagRequest,
    actor=Depends(trusted_actor),
    service: AdaptiveRagService = Depends(adaptive_rag.get_adaptive_rag_service),
) -> AdaptiveChatResponse:
    return adaptive_rag._chat_response(
        service.answer(
            request.query,
            top_k=request.top_k,
            max_paths=request.max_paths,
            actor_user_id=actor,
        )
    )

api_router = APIRouter()
api_router.include_router(router, prefix=get_settings().api_v1_prefix)
