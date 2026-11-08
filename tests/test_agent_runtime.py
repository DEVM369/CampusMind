from uuid import uuid4

from campusmind.knowledge.adaptive import (
    AdaptiveEvidence,
    AdaptiveRagResult,
    RetrievalRoute,
    RouteDecision,
)
from campusmind.agent.runtime import AgentRuntimeService
from campusmind.agent.runtime import NullAgentTraceRepository
from campusmind.knowledge.graph import EntityType, RelationType
from campusmind.knowledge.graph_rag import GraphEdge
from campusmind.knowledge.rag import RetrievedChunk


def _decision(route: RetrievalRoute) -> RouteDecision:
    complexity = {
        RetrievalRoute.GRAPH: "multi_hop",
        RetrievalRoute.HYBRID: "mixed",
        RetrievalRoute.SQL: "structured",
        RetrievalRoute.TOOL: "action",
    }.get(route, "simple")
    return RouteDecision(
        route=route,
        intent="test",
        complexity=complexity,
        confidence=1.0,
        reasons=["test"],
        executable=route not in {RetrievalRoute.SQL, RetrievalRoute.TOOL},
        requires_agent=route in {RetrievalRoute.SQL, RetrievalRoute.TOOL},
        source="rules",
    )


def _chunk():
    return RetrievedChunk(
        chunk_id=uuid4(),
        document_id=uuid4(),
        document_version_id=uuid4(),
        knowledge_base_id=uuid4(),
        content="evidence",
        title="test",
        object_key="test.md",
        page=1,
        section="test",
        rerank_score=0.9,
    )


def _graph_edge(chunk_id=None):
    chunk_id = chunk_id or uuid4()

    return GraphEdge(
        anchor_id="teacher:test",
        source_id="teacher:test",
        source_name="Test Teacher",
        source_type=EntityType.TEACHER,
        relation_type=RelationType.RESEARCHES,
        target_id="research:test",
        target_name="Test Research",
        target_type=EntityType.RESEARCH_AREA,
        relation_id="relation:test",
        source_document_id=str(uuid4()),
        source_chunk_id=str(chunk_id),
        confidence=0.95,
        path_id="p-test",
        hop_index=1,
    )


class FakeAdaptive:
    def __init__(self, route: RetrievalRoute, *, fail_graph_once: bool = False):
        self.initial = route
        self.fail_graph_once = fail_graph_once
        self.calls = []

    def route(self, query):
        return _decision(self.initial)

    def answer_with_decision(self, query, decision, *, top_k=6, max_paths=12):
        self.calls.append(decision.route)
        if decision.route in {RetrievalRoute.SQL, RetrievalRoute.TOOL}:
            return AdaptiveRagResult(
                trace_id="deferred",
                query=query,
                answer="deferred safely",
                decision=decision,
                executed_route=None,
                evidence_hits=[],
                graph_paths=[],
                text_retrieval=None,
                elapsed_ms=1.0,
                deferred_capability=decision.route.value,
            )

        hit = _chunk()
        if decision.route is RetrievalRoute.GRAPH and self.fail_graph_once:
            self.fail_graph_once = False
            return AdaptiveRagResult(
                trace_id="fallback",
                query=query,
                answer="text fallback",
                decision=decision,
                executed_route=RetrievalRoute.RAG,
                evidence_hits=[AdaptiveEvidence(chunk=hit, sources=("text",), score=0.8)],
                graph_paths=[],
                text_retrieval=None,
                elapsed_ms=1.0,
                fallback_reason="graph unavailable",
            )

        graph_paths = []
        if decision.route in {
            RetrievalRoute.GRAPH,
            RetrievalRoute.HYBRID,
        }:
            graph_paths = [
                _graph_edge(hit.chunk_id)
            ]
        return AdaptiveRagResult(
            trace_id="ok",
            query=query,
            answer="verified answer [1]",
            decision=decision,
            executed_route=decision.route,
            evidence_hits=[AdaptiveEvidence(chunk=hit, sources=("text",), score=0.9)],
            graph_paths=graph_paths,
            text_retrieval=None,
            elapsed_ms=1.0,
        )

    def close(self):
        pass


def _runtime(fake):
    return AgentRuntimeService(
        object(),
        adaptive_service=fake,
        trace_repository=NullAgentTraceRepository(),
    )


def test_runtime_executes_state_machine_and_validates_rag():
    result = _runtime(FakeAdaptive(RetrievalRoute.RAG)).answer(
        "q", persist_trace=False
    )
    assert result.status == "completed"
    assert result.validation.passed is True
    assert [item.step_name for item in result.steps] == [
        "intent_and_complexity",
        "planner",
        "query_decomposer",
        "retrieval_coordinator",
        "validator",
        "writer",
        "critic",
        "finalize",
    ]


def test_runtime_retries_failed_graph_as_hybrid():
    fake = FakeAdaptive(RetrievalRoute.GRAPH, fail_graph_once=True)
    result = _runtime(fake).answer("q", max_retries=1, persist_trace=False)
    # self-correcting agent runtime+ may fan out a GRAPH attempt into multiple decomposed
    # sub-queries before the validator requests the HYBRID retry.
    #
    # The stable contract is:
    #   1. retrieval starts on GRAPH;
    #   2. validator fallback eventually retries as HYBRID;
    #   3. HYBRID is the final retry strategy.
    assert fake.calls
    assert fake.calls[0] is RetrievalRoute.GRAPH
    assert fake.calls[-1] is RetrievalRoute.HYBRID
    assert RetrievalRoute.HYBRID in fake.calls
    assert fake.calls.count(RetrievalRoute.HYBRID) == 1
    assert all(
        route in {RetrievalRoute.GRAPH, RetrievalRoute.HYBRID}
        for route in fake.calls
    )
    assert result.retry_count == 1
    assert result.active_decision.route is RetrievalRoute.HYBRID
    assert result.validation.passed is True
    step_names = [
        item.step_name
        for item in result.steps
    ]

    assert "rewrite_and_retry" in step_names

    assert step_names.count(
        "query_decomposer"
    ) == 2

    assert step_names.count(
        "retrieval_coordinator"
    ) == 2

    assert step_names.count(
        "validator"
    ) == 2

    assert step_names[-2:] == [
        "critic",
        "finalize",
    ]


def test_runtime_defers_tool_and_requires_approval():
    result = _runtime(FakeAdaptive(RetrievalRoute.TOOL)).answer(
        "帮我预约", persist_trace=False
    )
    assert result.status == "deferred"
    assert result.pending_approval is True
    assert result.retrieval_result.deferred_capability == "tool"
    assert result.retry_count == 0
