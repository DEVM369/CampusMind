from __future__ import annotations

from campusmind.knowledge.adaptive import AdaptiveRagService
from campusmind.knowledge.adaptive import AdaptiveRagResult, RetrievalRoute, RouteDecision
from campusmind.agent.runtime import AnswerCritic
from campusmind.agent.runtime import CampusPlanner
from campusmind.agent.runtime import RetrievalValidator
from campusmind.tools.course import CourseCapability, CourseIntentParser, CourseToolService


class _FallbackAnalyzer:
    def analyze(self, query: str) -> RouteDecision:
        return RouteDecision(
            route=RetrievalRoute.RAG,
            intent="fallback",
            complexity="simple",
            confidence=0.5,
            reasons=["fallback"],
            executable=True,
            requires_agent=False,
            source="rules",
        )


def _course_decision() -> RouteDecision:
    return RouteDecision(
        route=RetrievalRoute.TOOL,
        intent="course_lookup",
        complexity="structured",
        confidence=0.99,
        reasons=["test"],
        executable=True,
        requires_agent=True,
        source="rules",
    )


def test_course_parser_recognizes_supported_capabilities():
    assert CourseIntentParser.parse("机器学习有哪些先修课程？").capability is CourseCapability.PREREQUISITES
    assert CourseIntentParser.parse("机器学习课程表是什么？").capability is CourseCapability.SCHEDULE
    assert CourseIntentParser.parse("谁教机器学习？").capability is CourseCapability.TEACHERS
    assert CourseIntentParser.parse("搜索课程 人工智能").capability is CourseCapability.SEARCH


def test_course_support_detection_does_not_hijack_graphrag_relation_query():
    assert CourseToolService.supports("机器学习有哪些先修课程？")
    assert CourseToolService.supports("机器学习课程表是什么？")
    assert CourseToolService.supports("谁教机器学习？")
    assert not CourseToolService.supports("研究知识图谱的老师教授哪些课程？")
    assert not CourseToolService.supports("软件工程专业有哪些课程需要先学高等数学？")


def test_adaptive_route_promotes_explicit_course_structured_query_to_tool():
    service = AdaptiveRagService(None, analyzer=_FallbackAnalyzer(), rag_service=object())
    decision = service.route("机器学习有哪些先修课程？")
    assert decision.route is RetrievalRoute.TOOL
    assert decision.intent == "course_lookup"
    assert decision.complexity == "structured"


def test_planner_marks_course_tool_as_read_only_without_human_approval():
    plan = CampusPlanner().plan("机器学习有哪些先修课程？", _course_decision())
    assert plan.risk_level == "low"
    assert plan.pending_approval is False
    assert plan.retrieval_strategy == "postgresql_course_tool"
    assert "execute_course_tool" in plan.steps
    assert "require_human_approval" not in plan.steps


def test_read_only_course_tool_passes_validator_and_critic_without_citations():
    result = AdaptiveRagResult(
        trace_id="course-test",
        query="机器学习有哪些先修课程？",
        answer="机器学习的结构化先修课程为：线性代数、Python程序设计。",
        decision=_course_decision(),
        executed_route=RetrievalRoute.TOOL,
        evidence_hits=[],
        graph_paths=[],
        text_retrieval=None,
        elapsed_ms=1.0,
        structured_data={
            "capability": "course_prerequisites",
            "source": "postgresql",
            "read_only": True,
            "data": {
                "course": {"course_name": "机器学习"},
                "prerequisites": [{"prerequisite_course_name": "线性代数"}],
                "count": 1,
            },
        },
    )
    validation = RetrievalValidator().validate(_course_decision(), result)
    assert validation.passed is True
    critic = AnswerCritic().evaluate(
        query=result.query,
        answer=result.answer,
        result=result,
        sub_queries=[result.query],
    )
    assert critic.passed is True

class _MentionRepository:
    def __init__(self, rows):
        self.rows = rows

    def find_courses_mentioned_in_text(self, query):
        return list(self.rows)


def _guarded_course_service(rows):
    service = object.__new__(CourseToolService)
    service.parser = CourseIntentParser()
    service.repository = _MentionRepository(rows)
    return service


def test_course_guard_rejects_graph_schema_and_student_readiness_queries():
    service = _guarded_course_service([
        {"course_id": "c1", "course_code": "AI301", "course_name": "机器学习"}
    ])
    assert service.can_answer("当前知识图谱中，课程机器学习的最短 prerequisite path 是多少？") is False
    assert service.can_answer("只看一跳 prerequisite，Course 数据给出的先修课集合是什么？") is False
    assert service.can_answer("把张同学已修课程和机器学习先修课连接起来，他是否满足要求？") is False


def test_course_guard_accepts_one_resolved_structured_course_target():
    service = _guarded_course_service([
        {"course_id": "c1", "course_code": "AI301", "course_name": "机器学习"}
    ])
    assert service.can_answer("课程 AI301 机器学习当前有哪些直接先修课程？") is True



def test_prerequisite_requirement_synonym_routes_to_course_tool():
    query = "机器学习课程有哪些先修要求？"
    assert CourseToolService.supports(query) is True
    intent = CourseIntentParser.parse(query)
    assert intent.capability.value == "course_prerequisites"
