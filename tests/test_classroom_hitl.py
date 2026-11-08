from __future__ import annotations

from datetime import datetime, timezone

from campusmind.knowledge.adaptive import AdaptiveRagResult, RetrievalRoute, RouteDecision
from campusmind.agent.runtime import AnswerCritic
from campusmind.agent.runtime import CampusPlanner
from campusmind.agent.runtime import RetrievalValidator
from campusmind.tools.actions import ClassroomIntentParser


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


def test_classroom_parser_resolves_tomorrow_afternoon_and_capacity():
    parser = ClassroomIntentParser()
    value = parser.parse(
        "帮我预约明天下午可以坐30人的自习室。",
        now=datetime(2026, 9, 23, 8, 0, tzinfo=timezone.utc),
    )
    assert value.reservation_date.isoformat() == "2026-09-24"
    assert value.start_time.isoformat() == "13:30:00"
    assert value.end_time.isoformat() == "17:30:00"
    assert value.capacity == 30
    assert value.daypart == "afternoon"


def test_classroom_parser_accepts_explicit_verification_date():
    parser = ClassroomIntentParser()
    value = parser.parse(
        "预约2099-12-31下午40人的教室",
        now=datetime(2026, 9, 23, 8, 0, tzinfo=timezone.utc),
    )
    assert value.reservation_date.isoformat() == "2099-12-31"
    assert value.capacity == 40


def test_tool_planner_requires_human_approval_and_candidate_search():
    plan = CampusPlanner().plan("帮我预约明天下午30人的自习室", _tool_decision())
    assert plan.pending_approval is True
    assert plan.risk_level == "medium"
    assert plan.retrieval_strategy == "campus_action_tool_hitl"
    assert "search_available_rooms" in plan.steps
    assert "human_approval_pause" in plan.steps


def test_validator_and_critic_accept_safe_prepared_action_without_execution():
    result = AdaptiveRagResult(
        trace_id="tool-test",
        query="帮我预约明天下午30人的自习室",
        answer="找到候选教室，确认后才会执行预约。",
        decision=_tool_decision(),
        executed_route=None,
        evidence_hits=[],
        graph_paths=[],
        text_retrieval=None,
        elapsed_ms=1.0,
        deferred_capability="tool_approval",
        structured_data={
            "capability": "classroom_reservation",
            "phase": "awaiting_approval",
            "approval_id": "00000000-0000-0000-0000-000000000016",
            "candidates": [
                {
                    "room_id": "CM-A101",
                    "room_name": "A101",
                    "building": "计算机学院A楼",
                    "capacity": 40,
                    "floor": 1,
                }
            ],
        },
    )
    validation = RetrievalValidator().validate(_tool_decision(), result)
    assert validation.passed is True
    assert validation.score == 1.0

    critic = AnswerCritic().evaluate(
        query=result.query,
        answer=result.answer,
        result=result,
        sub_queries=[result.query],
    )
    assert critic.passed is True
    assert critic.score == 1.0
    assert any("approval_id" in item for item in critic.checks)


def test_v11_classroom_confirmation_faq_does_not_trigger_action():
    from campusmind.tools.actions import (
        ClassroomActionService,
    )

    query = "系统找到符合容量的空闲教室后会直接替我预约吗？"

    assert (
        ClassroomActionService.supports(query)
        is False
    )

    query = "找到空闲教室后是不是还需要我确认才会预约？"

    assert (
        ClassroomActionService.supports(query)
        is False
    )


def test_v11_real_classroom_action_request_still_supported():
    from campusmind.tools.actions import (
        ClassroomActionService,
    )

    query = "帮我预约明天下午能坐30人的教室"

    assert (
        ClassroomActionService.supports(query)
        is True
    )

    query = "请帮我找明天下午的空闲教室"

    assert (
        ClassroomActionService.supports(query)
        is True
    )

