from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from campusmind.api.dependencies import trusted_actor

from campusmind.platform.db import get_db
from campusmind.agent.multi import HierarchicalMultiAgentService
from campusmind.agent.multi import AgentEvidence, MultiAgentPlan, MultiAgentResult
from campusmind.api.schemas import (
    MultiAgentChatResponse,
    MultiAgentChildResponse,
    MultiAgentEvidenceResponse,
    MultiAgentPlanOnlyResponse,
    MultiAgentPlanResponse,
    MultiAgentRequest,
    MultiAgentTaskResponse,
)


router = APIRouter()


def get_multi_agent_service(db: Session = Depends(get_db)) -> HierarchicalMultiAgentService:
    return HierarchicalMultiAgentService(db)


def _plan(value: MultiAgentPlan) -> MultiAgentPlanResponse:
    return MultiAgentPlanResponse(
        tasks=[
            MultiAgentTaskResponse(
                task_id=item.task_id,
                domain=item.domain.value,
                query=item.query,
                reason=item.reason,
                requires_actor=item.requires_actor,
                write_intent=item.write_intent,
                depends_on=item.depends_on,
                context_keys=item.context_keys,
            )
            for item in value.tasks
        ],
        parallelizable=value.parallelizable,
        supervisor_reason=value.supervisor_reason,
    )


def _evidence(value: AgentEvidence) -> MultiAgentEvidenceResponse:
    return MultiAgentEvidenceResponse(
        evidence_id=value.evidence_id,
        task_id=value.task_id,
        domain=value.domain.value,
        source_kind=value.source_kind,
        source=value.source,
        summary=value.summary,
        payload=value.payload,
    )


def _response(value: MultiAgentResult) -> MultiAgentChatResponse:
    return MultiAgentChatResponse(
        trace_id=value.trace_id,
        actor_user_id=value.actor_user_id,
        query=value.query,
        status=value.status,
        pending_approval=value.pending_approval,
        answer=value.answer,
        plan=_plan(value.plan),
        child_results=[
            MultiAgentChildResponse(
                task_id=item.task_id,
                domain=item.domain.value,
                query=item.query,
                status=item.status,
                answer=item.answer,
                source=item.source,
                pending_approval=item.pending_approval,
                approval_id=item.approval_id,
                trace_id=item.trace_id,
                structured_data=item.structured_data,
                consumed_context=item.consumed_context,
                evidence=[_evidence(ev) for ev in item.evidence],
                error=item.error,
            )
            for item in value.child_results
        ],
        elapsed_ms=value.elapsed_ms,
        execution_order=value.execution_order,
        shared_context=value.shared_context,
        evidence=[_evidence(item) for item in value.evidence],
        evidence_merge_passed=value.evidence_merge_passed,
        trace_persisted=value.trace_persisted,
        trace_persist_error=value.trace_persist_error,
    )


@router.post("/plan", response_model=MultiAgentPlanOnlyResponse)
def plan(
    request: MultiAgentRequest,
    service: HierarchicalMultiAgentService = Depends(get_multi_agent_service),
) -> MultiAgentPlanOnlyResponse:
    return MultiAgentPlanOnlyResponse(query=request.query, plan=_plan(service.plan(request.query)))


@router.post("/chat", response_model=MultiAgentChatResponse)
def chat(
    request: MultiAgentRequest,
    actor=Depends(trusted_actor),
    service: HierarchicalMultiAgentService = Depends(get_multi_agent_service),
) -> MultiAgentChatResponse:
    return _response(
        service.answer(
            request.query,
            actor_user_id=actor,
            persist_trace=request.persist_trace,
        )
    )
