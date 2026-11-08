from uuid import uuid4

from campusmind.knowledge.graph import EntityType, RelationType
from campusmind.knowledge.graph_ingestion import GraphIngestionService
from campusmind.knowledge.graph_ingestion import (
    ChunkGraphSource,
    ExtractedEntity,
    ExtractedRelation,
    GraphExtraction,
)


class FakeExtractor:
    def extract(self, source):
        return GraphExtraction(
            entities=[
                ExtractedEntity(ref="m", entity_type=EntityType.MAJOR, name="软件工程专业", confidence=0.99),
                ExtractedEntity(ref="c", entity_type=EntityType.COURSE, name="数据结构课程", confidence=0.99),
            ],
            relations=[
                ExtractedRelation(
                    relation_type=RelationType.REQUIRES,
                    source_ref="m", target_ref="c", confidence=0.98,
                )
            ],
        )


class FakeStore:
    def __init__(self):
        self.entities = []
        self.relations = []

    def find_entity(self, entity_type, canonical_name, aliases):
        return None

    def replace_chunk_graph(self, source_chunk_id, entities, relations):
        self.entities = entities
        self.relations = relations
        return {"entities_written": len(entities), "relations_written": len(relations), "relations_deleted": 0}

    def source_chunk_graph(self, source_chunk_id):
        return {"relation_count": len(self.relations), "relations": [], "evidence_gaps": []}

    def close(self):
        pass


def test_chunk_graph_ingestion_binds_source_evidence_and_validates_relation():
    store = FakeStore()
    service = GraphIngestionService(
        session=None,
        source_repository=object(),
        extractor=FakeExtractor(),
        store=store,
    )
    source = ChunkGraphSource(
        chunk_id=uuid4(), document_id=uuid4(), document_version_id=uuid4(),
        document_title="2026软件工程培养方案", document_version="2026",
        content="软件工程专业要求学习数据结构课程。",
        page=16, chapter="培养方案", section="课程要求", department="计算机学院",
        document_type="training_program", effective_from=None, effective_to=None,
    )
    result = service.ingest_source(source)
    assert result.entities_written == 2
    assert result.relations_written == 1
    relation = store.relations[0]
    assert relation.relation_type == RelationType.REQUIRES
    assert relation.evidence.source_document_id == str(source.document_id)
    assert relation.evidence.source_chunk_id == str(source.chunk_id)
