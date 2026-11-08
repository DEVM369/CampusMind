from __future__ import annotations

from collections.abc import Generator

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from campusmind.api.dependencies import trusted_actor

from campusmind.agent.runtime import AgentRuntimeService
from campusmind.tools.actions import (
    ClassroomActionConflict,
    ClassroomActionError,
    ClassroomActionExpired,
    ClassroomActionNotFound,
    ClassroomActionOwnershipError,
)
from campusmind.agent.runtime import AgentPlan, AgentRuntimeResult
from campusmind.platform.db import get_db
from campusmind.api.schemas import (
    AgentChatResponse,
    AgentCriticResponse,
    AgentPlanOnlyResponse,
    AgentPlanResponse,
    AgentRequest,
    AgentResumeRequest,
    AgentResumeResponse,
    AgentStepResponse,
    AgentSubQueryExecutionResponse,
    AgentValidationResponse,
)
from campusmind.api.schemas import GraphPathResponse
from campusmind.api.schemas import Citation


router = APIRouter()


def get_agent_runtime_service(
    db: Session = Depends(get_db),
) -> Generator[AgentRuntimeService, None, None]:
    service = AgentRuntimeService(db)
    try:
        yield service
    finally:
        service.close()


def _plan(plan: AgentPlan) -> AgentPlanResponse:
    return AgentPlanResponse(
        route=plan.route.value,
        intent=plan.intent,
        complexity=plan.complexity,
        risk_level=plan.risk_level,
        retrieval_strategy=plan.retrieval_strategy,
        sub_queries=list(plan.sub_queries),
        steps=list(plan.steps),
        pending_approval=plan.pending_approval,
    )


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


def _graph_path(item) -> GraphPathResponse:
    return GraphPathResponse(
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


def _response(result: AgentRuntimeResult) -> AgentChatResponse:
    retrieval = result.retrieval_result
    return AgentChatResponse(
        trace_id=result.trace_id,
        query=result.query,
        status=result.status,
        answer=result.final_answer,
        planned_route=result.planned_decision.route.value,
        active_route=result.active_decision.route.value,
        executed_route=(retrieval.executed_route.value if retrieval.executed_route else None),
        retry_count=result.retry_count,
        answer_rewrite_count=result.answer_rewrite_count,
        pending_approval=result.pending_approval,
        plan=_plan(result.plan),
        sub_queries=list(result.sub_queries),
        subquery_executions=[
            AgentSubQueryExecutionResponse(**item.model_dump())
            for item in result.subquery_executions
        ],
        validation=AgentValidationResponse(
            passed=result.validation.passed,
            score=result.validation.score,
            reasons=list(result.validation.reasons),
        ),
        critic=AgentCriticResponse(
            passed=result.critic.passed,
            score=result.critic.score,
            feedback=result.critic.feedback,
            checks=list(result.critic.checks),
        ),
        citations=[_citation(item.chunk) for item in retrieval.evidence_hits],
        graph_paths=[_graph_path(item) for item in retrieval.graph_paths],
        deferred_capability=retrieval.deferred_capability,
        structured_data=retrieval.structured_data,
        fallback_reason=retrieval.fallback_reason,
        steps=[AgentStepResponse(**item.model_dump()) for item in result.steps],
        elapsed_ms=result.elapsed_ms,
        trace_persisted=result.trace_persisted,
        trace_persist_error=result.trace_persist_error,
    )


@router.post("/plan", response_model=AgentPlanOnlyResponse)
def plan(
    request: AgentRequest,
    service: AgentRuntimeService = Depends(get_agent_runtime_service),
) -> AgentPlanOnlyResponse:
    decision, plan_value = service.plan(request.query)
    return AgentPlanOnlyResponse(
        query=request.query,
        planned_route=decision.route.value,
        route_confidence=decision.confidence,
        route_source=decision.source,
        plan=_plan(plan_value),
    )


@router.post("/chat", response_model=AgentChatResponse)
def chat(
    request: AgentRequest,
    actor=Depends(trusted_actor),
    service: AgentRuntimeService = Depends(get_agent_runtime_service),
) -> AgentChatResponse:
    return _response(
        service.answer(
            request.query,
            top_k=request.top_k,
            max_paths=request.max_paths,
            max_retries=request.max_retries,
            max_answer_rewrites=request.max_answer_rewrites,
            persist_trace=request.persist_trace,
            actor_user_id=actor,
        )
    )


@router.post("/resume", response_model=AgentResumeResponse)
def resume(
    request: AgentResumeRequest,
    actor=Depends(trusted_actor),
    service: AgentRuntimeService = Depends(get_agent_runtime_service),
) -> AgentResumeResponse:
    try:
        result = service.resume_action(
            request.approval_id,
            actor,
            approved=request.approved,
            room_id=request.room_id,
            book_id=request.book_id,
            resource_id=request.resource_id,
        )
    except ClassroomActionNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ClassroomActionOwnershipError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except (ClassroomActionConflict, ClassroomActionExpired) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ClassroomActionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return AgentResumeResponse(
        trace_id=result.trace_id,
        approval_id=result.approval_id,
        actor_user_id=result.actor_user_id,
        status=result.status,
        answer=result.final_answer,
        structured_data=result.structured_data,
        state_changed=result.state_changed,
        idempotent=result.idempotent,
        trace_updated=result.trace_updated,
        trace_update_error=result.trace_update_error,
    )
