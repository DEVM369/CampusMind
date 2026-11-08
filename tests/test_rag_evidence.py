from uuid import uuid4

from campusmind.knowledge.rag import EvidenceSelector
from campusmind.knowledge.rag import RetrievedChunk


def hit(score: float, text: str) -> RetrievedChunk:
    item = RetrievedChunk(
        chunk_id=uuid4(),
        document_id=uuid4(),
        document_version_id=uuid4(),
        knowledge_base_id=uuid4(),
        content=text,
        title='doc',
        object_key='doc.md',
    )
    item.rerank_score = score
    return item


def test_evidence_selector_filters_candidates_far_below_best():
    hits = [
        hit(0.8366, '160学分'),
        hit(0.6623, '转专业'),
        hit(0.6383, '深度学习'),
        hit(0.61, '图书馆'),
    ]
    selected = EvidenceSelector(relative_threshold=0.82, max_chunks=3).select(hits)
    assert [item.content for item in selected] == ['160学分']


def test_evidence_selector_can_keep_multiple_close_evidence_chunks():
    hits = [hit(0.90, 'A'), hit(0.86, 'B'), hit(0.55, 'C')]
    selected = EvidenceSelector(relative_threshold=0.82, max_chunks=3).select(hits)
    assert [item.content for item in selected] == ['A', 'B']


def test_evidence_selector_keeps_at_least_one_chunk():
    hits = [hit(0.0, 'A'), hit(0.0, 'B')]
    selected = EvidenceSelector(relative_threshold=0.82, max_chunks=3, min_chunks=1).select(hits)
    assert len(selected) >= 1
