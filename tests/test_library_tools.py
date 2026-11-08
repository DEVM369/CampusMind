from __future__ import annotations

import uuid

from campusmind.knowledge.adaptive import AdaptiveRagResult, RetrievalRoute, RouteDecision
from campusmind.agent.runtime import AnswerCritic
from campusmind.agent.runtime import CampusPlanner
from campusmind.agent.runtime import RetrievalValidator
from campusmind.tools.actions import LibraryActionService, LibraryIntentParser
from campusmind.api.schemas import AgentResumeRequest


def _tool_decision() -> RouteDecision:
    return RouteDecision(
        route=RetrievalRoute.TOOL,
        intent="campus_action",
        complexity="action",
        confidence=0.99,
        reasons=["test"],
        executable=False,
        requires_agent=True,
        source="rules",
    )


def test_library_parser_extracts_book_title():
    value = LibraryIntentParser().parse("帮我预约《Graph Representation Learning》这本书")
    assert value.title_hint == "Graph Representation Learning"
    assert value.title_hint in value.keywords


def test_library_action_support_detection_is_narrow():
    assert LibraryActionService.supports("帮我预约《Graph Representation Learning》这本书")
    assert LibraryActionService.supports("图书馆有没有《Deep Learning》？")
    assert not LibraryActionService.supports("帮我预约明天下午30人的自习室")


def test_planner_uses_library_read_before_write_steps():
    plan = CampusPlanner().plan("帮我预约《Graph Representation Learning》这本书", _tool_decision())
    assert plan.pending_approval is True
    assert "search_book" in plan.steps
    assert "check_book_inventory" in plan.steps
    assert "require_human_approval" in plan.steps
    assert "human_approval_pause" in plan.steps
    assert "search_available_rooms" not in plan.steps


def test_library_prepared_action_passes_generic_hitl_validator_and_critic():
    result = AdaptiveRagResult(
        trace_id="library-test",
        query="帮我预约《Graph Representation Learning》这本书",
        answer="已找到馆藏，确认后才会执行 reserve_book()。",
        decision=_tool_decision(),
        executed_route=None,
        evidence_hits=[],
        graph_paths=[],
        text_retrieval=None,
        elapsed_ms=1.0,
        deferred_capability="tool_approval",
        structured_data={
            "capability": "library_book_reservation",
            "phase": "awaiting_approval",
            "approval_id": "00000000-0000-0000-0000-000000000017",
            "candidates": [
                {
                    "book_id": "00000000-0000-0000-0000-000000001701",
                    "book_code": "LIB-GRL-001",
                    "title": "Graph Representation Learning",
                    "author": "William L. Hamilton",
                    "location": "主图书馆三层 A-03",
                    "total_copies": 3,
                    "available_copies": 2,
                }
            ],
        },
    )
    validation = RetrievalValidator().validate(_tool_decision(), result)
    assert validation.passed is True
    critic = AnswerCritic().evaluate(
        query=result.query,
        answer=result.answer,
        result=result,
        sub_queries=[result.query],
    )
    assert critic.passed is True
    assert any("approval_id" in item for item in critic.checks)


def test_agent_resume_request_keeps_room_and_generic_resource_selectors():
    approval = uuid.UUID("00000000-0000-0000-0000-000000000017")
    actor = uuid.UUID("00000000-0000-0000-0000-000000000001")
    old = AgentResumeRequest(
        approval_id=approval,
        actor_user_id=actor,
        approved=True,
        room_id="CM-A101",
    )
    assert old.room_id == "CM-A101"
    new = AgentResumeRequest(
        approval_id=approval,
        actor_user_id=actor,
        approved=True,
        book_id="00000000-0000-0000-0000-000000001701",
        resource_id="00000000-0000-0000-0000-000000001701",
    )
    assert new.book_id == new.resource_id
