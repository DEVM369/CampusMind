from uuid import uuid4

from campusmind.knowledge.hybrid import HybridGraphRagService
from campusmind.knowledge.rag import RetrievalResult
from campusmind.knowledge.rag import RetrievedChunk


class BrokenGraphService:
    def search(self, query, max_paths):
        raise RuntimeError("neo4j unavailable")


class TextService:
    def search(self, query, top_k):
        hit = RetrievedChunk(
            chunk_id=uuid4(),
            document_id=uuid4(),
            document_version_id=uuid4(),
            knowledge_base_id=uuid4(),
            content="人工智能导论课程主要介绍机器学习与知识表示。",
            title="课程简介",
            object_key="course.md",
            section="课程内容",
            rerank_score=0.9,
        )
        return RetrievalResult(
            original_query=query,
            rewritten_query=query,
            hits=[hit],
            vector_count=1,
            keyword_count=1,
            elapsed_ms=1.0,
        )


class AnswerGenerator:
    def generate(self, query, paths, evidence_hits):
        return "人工智能导论介绍机器学习与知识表示。[1]"


def test_hybrid_service_is_fail_soft_when_graph_branch_fails():
    service = HybridGraphRagService(
        object(),
        graph_service=BrokenGraphService(),
        text_service=TextService(),
        answer_generator=AnswerGenerator(),
    )

    result = service.answer("人工智能导论介绍什么？")

    assert result.search.graph_error is not None
    assert result.search.text_error is None
    assert result.search.hits
    assert result.search.hits[0].sources == ("text",)
    assert "机器学习" in result.answer
