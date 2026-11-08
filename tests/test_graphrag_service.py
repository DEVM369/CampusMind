from uuid import uuid4

from campusmind.knowledge.graph import EntityType, RelationType
from campusmind.knowledge.graph_rag import GraphRagService, _heuristic_plan
from campusmind.knowledge.graph_rag import (
    GraphEdge,
    GraphRagSourceRepository,
    GraphQueryPlan,
    LinkedEntity,
    QueryEntityHint,
)
from campusmind.knowledge.rag import RetrievedChunk


class FakeAnalyzer:
    def analyze(self, query):
        return GraphQueryPlan(
            entities=[
                QueryEntityHint(
                    name="李明",
                    entity_type=EntityType.TEACHER,
                )
            ],
            relation_types=[RelationType.RESEARCHES],
            direction="outgoing",
        )


class FakeGraphRepository:
    def link_entity(self, hint):
        return LinkedEntity(
            query_name=hint.name,
            entity_id="teacher:li-ming",
            entity_type=EntityType.TEACHER,
            name="李明",
        )

    def expand_one_hop(self, anchor_ids, relation_types, direction, limit):
        return [
            GraphEdge(
                anchor_id="teacher:li-ming",
                source_id="teacher:li-ming",
                source_name="李明",
                source_type=EntityType.TEACHER,
                relation_type=RelationType.RESEARCHES,
                target_id="research:kg",
                target_name="知识图谱",
                target_type=EntityType.RESEARCH_AREA,
                relation_id="active-rel",
                source_document_id="doc-active",
                source_chunk_id="11111111-1111-1111-1111-111111111111",
                confidence=0.98,
            ),
            GraphEdge(
                anchor_id="teacher:li-ming",
                source_id="teacher:li-ming",
                source_name="李明",
                source_type=EntityType.TEACHER,
                relation_type=RelationType.RESEARCHES,
                target_id="research:stale",
                target_name="过期方向",
                target_type=EntityType.RESEARCH_AREA,
                relation_id="stale-rel",
                source_document_id="doc-stale",
                source_chunk_id="22222222-2222-2222-2222-222222222222",
                confidence=0.99,
            ),
        ]


class FakeSourceRepository:
    def active_chunks(self, chunk_ids):
        chunk_id = uuid4()
        # Use the exact key expected by the graph edge while the dataclass itself
        # can use any UUID for this isolated unit test.
        hit = RetrievedChunk(
            chunk_id=chunk_id,
            document_id=uuid4(),
            document_version_id=uuid4(),
            knowledge_base_id=uuid4(),
            content="李明教授研究知识图谱。",
            title="教师科研简介",
            object_key="documents/test.md",
            section="研究方向",
        )
        return {
            "11111111-1111-1111-1111-111111111111": hit,
        }


class FakeAnswerGenerator:
    def generate(self, query, paths, evidence_hits):
        return "李明教授研究知识图谱。[1]"


def test_graph_rag_filters_relations_without_active_source_evidence():
    service = GraphRagService(
        object(),
        analyzer=FakeAnalyzer(),
        graph_repository=FakeGraphRepository(),
        source_repository=FakeSourceRepository(),
        answer_generator=FakeAnswerGenerator(),
    )

    result = service.search("李明教授研究什么？")

    assert len(result.linked_entities) == 1
    assert len(result.paths) == 1
    assert result.paths[0].target_name == "知识图谱"
    assert len(result.evidence_hits) == 1


def test_graph_rag_answer_uses_filtered_paths():
    service = GraphRagService(
        object(),
        analyzer=FakeAnalyzer(),
        graph_repository=FakeGraphRepository(),
        source_repository=FakeSourceRepository(),
        answer_generator=FakeAnswerGenerator(),
    )

    result = service.answer("李明教授研究什么？")

    assert "知识图谱" in result.answer
    assert len(result.search.paths) == 1


def test_explicit_prerequisite_edge_is_one_hop_outgoing():
    plan = _heuristic_plan(
        "当前知识图谱中，从课程「数据结构」沿 PREREQUISITE_OF 正向一跳会到达哪门课程？"
    )
    assert plan.max_hops == 1
    assert len(plan.entities) == 1
    assert plan.entities[0].name == "数据结构"
    assert plan.relation_types == [RelationType.PREREQUISITE_OF]
    assert plan.direction == "outgoing"


def test_explicit_prerequisite_edge_to_quoted_target_is_incoming():
    plan = _heuristic_plan(
        "哪些课程通过 PREREQUISITE_OF 指向课程「机器学习」？"
    )
    assert plan.max_hops == 1
    assert len(plan.entities) == 1
    assert plan.entities[0].name == "机器学习"
    assert plan.direction == "incoming"


class RecoveringSourceRepository:
    def resolve_paths(self, paths):
        hit = RetrievedChunk(
            chunk_id=uuid4(),
            document_id=uuid4(),
            document_version_id=uuid4(),
            knowledge_base_id=uuid4(),
            content="李明教授研究知识图谱。",
            title="教师科研简介",
            object_key="documents/recovered.md",
            section="研究方向",
        )
        repaired = []
        for edge in paths:
            if edge.target_name != "知识图谱":
                repaired.append(edge)
                continue
            from dataclasses import replace
            repaired.append(
                replace(
                    edge,
                    source_document_id=str(hit.document_id),
                    source_chunk_id=str(hit.chunk_id),
                )
            )
        return repaired, {str(hit.chunk_id): hit}, 1


def test_graph_rag_accepts_safely_recovered_active_evidence():
    service = GraphRagService(
        object(),
        analyzer=FakeAnalyzer(),
        graph_repository=FakeGraphRepository(),
        source_repository=RecoveringSourceRepository(),
        answer_generator=FakeAnswerGenerator(),
    )
    result = service.search("李明教授研究什么？")
    assert len(result.paths) == 1
    assert result.paths[0].target_name == "知识图谱"
    assert result.recovered_evidence_count == 1
    assert "recovered_stale_evidence=1" in result.diagnostics



def test_prerequisite_recovery_requires_relation_semantics():
    markers = GraphRagSourceRepository._relation_evidence_markers(
        RelationType.PREREQUISITE_OF
    )
    assert "先修" in markers
    assert "prerequisite" in markers


def test_unknown_relation_recovery_does_not_invent_semantic_markers():
    markers = GraphRagSourceRepository._relation_evidence_markers(
        RelationType.RELATED_TO
    )
    assert markers == ()
