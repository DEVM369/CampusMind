from __future__ import annotations

from campusmind.knowledge.adaptive import AdaptiveRagService
from campusmind.knowledge.adaptive import AdaptiveRagResult, RetrievalRoute, RouteDecision
from campusmind.agent.runtime import AnswerCritic
from campusmind.agent.runtime import CampusPlanner
from campusmind.agent.runtime import RetrievalValidator
from campusmind.tools.research import ResearchCapability, ResearchIntentParser, ResearchToolService


class _FallbackAnalyzer:
    def analyze(self, query: str) -> RouteDecision:
        # Preserve the GraphRAG boundary used by the GraphRAG routing contract.
        route = RetrievalRoute.GRAPH if "哪些老师研究" in query else RetrievalRoute.RAG
        return RouteDecision(
            route=route,
            intent="fallback",
            complexity="relational" if route is RetrievalRoute.GRAPH else "simple",
            confidence=0.9,
            reasons=["fallback"],
            executable=True,
            requires_agent=route is RetrievalRoute.GRAPH,
            source="rules",
        )


def _research_decision() -> RouteDecision:
    return RouteDecision(
        route=RetrievalRoute.TOOL,
        intent="research_lookup",
        complexity="structured",
        confidence=0.99,
        reasons=["test"],
        executable=True,
        requires_agent=True,
        source="rules",
    )


def test_research_parser_recognizes_five_capabilities():
    assert ResearchIntentParser.parse("搜索科研教师 知识图谱").capability is ResearchCapability.TEACHERS
    assert ResearchIntentParser.parse("搜索论文 GraphRAG").capability is ResearchCapability.PAPERS
    assert ResearchIntentParser.parse("搜索研究方向 大语言模型").capability is ResearchCapability.AREAS
    assert ResearchIntentParser.parse("搜索实验室 RAG").capability is ResearchCapability.LABS
    assert ResearchIntentParser.parse("搜索科研项目 Agentic").capability is ResearchCapability.PROJECTS


def test_research_support_detection_does_not_hijack_graphrag_relation_query():
    assert ResearchToolService.supports("搜索科研教师 知识图谱")
    assert ResearchToolService.supports("搜索论文 GraphRAG")
    assert not ResearchToolService.supports("哪些老师研究知识图谱？")
    assert not ResearchToolService.supports("研究知识图谱的老师教授哪些课程？")


def test_adaptive_route_promotes_explicit_research_structured_query_to_tool():
    service = AdaptiveRagService(None, analyzer=_FallbackAnalyzer(), rag_service=object())
    decision = service.route("搜索科研教师 知识图谱")
    assert decision.route is RetrievalRoute.TOOL
    assert decision.intent == "research_lookup"
    assert decision.complexity == "structured"
    boundary = service.route("哪些老师研究知识图谱？")
    assert boundary.route is RetrievalRoute.GRAPH


def test_planner_marks_research_tool_as_read_only_without_human_approval():
    plan = CampusPlanner().plan("搜索论文 GraphRAG", _research_decision())
    assert plan.risk_level == "low"
    assert plan.pending_approval is False
    assert plan.retrieval_strategy == "postgresql_research_tool"
    assert "execute_research_tool" in plan.steps
    assert "require_human_approval" not in plan.steps


def test_read_only_research_tool_passes_validator_and_critic_without_document_citations():
    result = AdaptiveRagResult(
        trace_id="research-test",
        query="搜索论文 GraphRAG",
        answer="科研论文查询结果：GraphRAG for Campus Knowledge Services。",
        decision=_research_decision(),
        executed_route=RetrievalRoute.TOOL,
        evidence_hits=[],
        graph_paths=[],
        text_retrieval=None,
        elapsed_ms=1.0,
        structured_data={
            "capability": "research_paper_search",
            "source": "postgresql",
            "read_only": True,
            "data": {"papers": [{"title": "GraphRAG for Campus Knowledge Services"}], "count": 1},
        },
    )
    validation = RetrievalValidator().validate(_research_decision(), result)
    assert validation.passed is True
    critic = AnswerCritic().evaluate(
        query=result.query,
        answer=result.answer,
        result=result,
        sub_queries=[result.query],
    )
    assert critic.passed is True
