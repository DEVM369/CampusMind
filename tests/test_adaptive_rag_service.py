from types import SimpleNamespace
from uuid import uuid4

from campusmind.knowledge.adaptive import AdaptiveRagService
from campusmind.knowledge.adaptive import RetrievalRoute, RouteDecision, RuleBasedRouteAnalyzer
from campusmind.knowledge.rag import RetrievedChunk


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


class FixedAnalyzer:
    def __init__(self, route):
        self.route = route

    def analyze(self, query):
        executable = self.route not in {RetrievalRoute.SQL, RetrievalRoute.TOOL}
        return RouteDecision(
            route=self.route,
            intent="test",
            complexity=("structured" if self.route is RetrievalRoute.SQL else "simple"),
            confidence=1.0,
            reasons=["test"],
            executable=executable,
            requires_agent=not executable,
            source="rules",
        )


class FakeRag:
    def answer(self, query, top_k=6):
        hit = _chunk()
        return SimpleNamespace(
            trace_id="rag-trace",
            answer="rag answer",
            evidence_hits=[hit],
            retrieval=SimpleNamespace(
                original_query=query,
                rewritten_query=query,
                hits=[hit],
                vector_count=1,
                keyword_count=1,
                elapsed_ms=1.0,
            ),
        )


class FakeGraph:
    def answer(self, query, max_paths=12):
        hit = _chunk()
        return SimpleNamespace(
            trace_id="graph-trace",
            answer="graph answer",
            search=SimpleNamespace(evidence_hits=[hit], paths=[SimpleNamespace(path_id="p1")]),
        )

    def close(self):
        pass


class FakeHybrid:
    def answer(self, query, top_k=6, max_paths=12):
        hit = _chunk()
        evidence = SimpleNamespace(
            chunk=hit,
            sources=("graph", "text"),
            fusion_score=0.88,
            graph_path_ids=("p1",),
        )
        return SimpleNamespace(
            trace_id="hybrid-trace",
            answer="hybrid answer",
            evidence_hits=[evidence],
            search=SimpleNamespace(
                graph_search=SimpleNamespace(paths=[]),
                text_retrieval=None,
            ),
        )

    def close(self):
        pass


def _service(route):
    return AdaptiveRagService(
        object(),
        analyzer=FixedAnalyzer(route),
        rag_service=FakeRag(),
        graph_service=FakeGraph(),
        hybrid_service=FakeHybrid(),
    )


def test_service_dispatches_plain_rag():
    result = _service(RetrievalRoute.RAG).answer("q")
    assert result.executed_route is RetrievalRoute.RAG
    assert result.answer == "rag answer"
    assert result.evidence_hits[0].sources == ("text",)


def test_service_dispatches_graph():
    result = _service(RetrievalRoute.GRAPH).answer("q")
    assert result.executed_route is RetrievalRoute.GRAPH
    assert result.answer == "graph answer"


def test_service_dispatches_hybrid():
    result = _service(RetrievalRoute.HYBRID).answer("q")
    assert result.executed_route is RetrievalRoute.HYBRID
    assert result.evidence_hits[0].sources == ("graph", "text")


def test_sql_is_deferred_instead_of_fabricated():
    result = _service(RetrievalRoute.SQL).answer("我有多少学分？")
    assert result.executed_route is None
    assert result.deferred_capability == "sql"
    assert result.evidence_hits == []


def test_explicit_prerequisite_edge_routes_one_hop_graph():
    decision = RuleBasedRouteAnalyzer().analyze(
        "当前知识图谱中，从课程「数据结构」沿 PREREQUISITE_OF 正向一跳会到达哪门课程？"
    )
    assert decision.route is RetrievalRoute.GRAPH
    assert decision.intent == "relationship_query"
    assert decision.complexity == "relational"


class FakeGraphMiss:
    def answer(self, query, max_paths=12):
        return SimpleNamespace(
            trace_id="graph-miss",
            answer="no graph evidence",
            search=SimpleNamespace(evidence_hits=[], paths=[]),
        )

    def close(self):
        pass


def test_graph_miss_falls_back_to_rag_instead_of_false_negative():
    service = AdaptiveRagService(
        object(),
        analyzer=FixedAnalyzer(RetrievalRoute.GRAPH),
        rag_service=FakeRag(),
        graph_service=FakeGraphMiss(),
        hybrid_service=FakeHybrid(),
        knowledge_acl_service=SimpleNamespace(apply_to_session=lambda actor: None),
        authorization_service=SimpleNamespace(),
    )
    result = service.answer("graph q")
    assert result.executed_route is RetrievalRoute.RAG
    assert result.answer == "rag answer"
    assert "no source-verified path" in result.fallback_reason


class FakeRagEmpty:
    def answer(self, query, top_k=6):
        return SimpleNamespace(
            trace_id="rag-empty",
            answer="no text evidence",
            evidence_hits=[],
            retrieval=SimpleNamespace(
                original_query=query,
                rewritten_query=query,
                hits=[],
                vector_count=0,
                keyword_count=0,
                elapsed_ms=1.0,
            ),
        )


class FakeGraphAclMiss:
    def answer(self, query, max_paths=12):
        return SimpleNamespace(
            trace_id="graph-acl",
            answer="no verified graph evidence",
            search=SimpleNamespace(
                evidence_hits=[],
                paths=[],
                raw_path_count=1,
                diagnostics=("graph_edges_failed_source_evidence_validation",),
            ),
        )

    def close(self):
        pass


def test_graph_candidate_without_public_evidence_explains_acl_scope():
    service = AdaptiveRagService(
        object(),
        analyzer=FixedAnalyzer(RetrievalRoute.GRAPH),
        rag_service=FakeRagEmpty(),
        graph_service=FakeGraphAclMiss(),
        hybrid_service=FakeHybrid(),
        knowledge_acl_service=SimpleNamespace(apply_to_session=lambda actor: None),
        authorization_service=SimpleNamespace(),
    )
    result = service.answer("graph q", actor_user_id=None)
    assert result.executed_route is RetrievalRoute.GRAPH
    assert "未设置用户 ID" in result.answer
    assert result.structured_data["access_scope"] == "public"
