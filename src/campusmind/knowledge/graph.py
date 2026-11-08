from __future__ import annotations

from neo4j import GraphDatabase
from neo4j import Driver
from campusmind.config import Settings, get_settings
from dataclasses import dataclass
from enum import StrEnum
from dataclasses import dataclass, field
from datetime import date
from typing import Any
from collections.abc import Iterable
from campusmind.config import get_settings
from typing import TYPE_CHECKING, Any

"""CampusMind graph domain."""

# ---- app/graph/connection.py ----
def create_neo4j_driver(settings: Settings | None = None) -> Driver:
    settings = settings or get_settings()
    return GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
        connection_timeout=settings.infra_connect_timeout,
    )

# ---- app/graph/ontology.py ----
class EntityType(StrEnum):
    STUDENT = "Student"
    TEACHER = "Teacher"
    COLLEGE = "College"
    DEPARTMENT = "Department"
    MAJOR = "Major"
    COURSE = "Course"
    KNOWLEDGE_POINT = "KnowledgePoint"
    POLICY = "Policy"
    PROCEDURE = "Procedure"
    REQUIREMENT = "Requirement"
    RESEARCH_AREA = "ResearchArea"
    PAPER = "Paper"
    PROJECT = "Project"
    LAB = "Lab"
    BOOK = "Book"
    LIBRARY_RESOURCE = "LibraryResource"
    BUILDING = "Building"
    CLASSROOM = "Classroom"
    ACTIVITY = "Activity"


class RelationType(StrEnum):
    ENROLLED_IN = "ENROLLED_IN"
    BELONGS_TO = "BELONGS_TO"
    REQUIRES = "REQUIRES"
    PREREQUISITE_OF = "PREREQUISITE_OF"
    TEACHES = "TEACHES"
    RESEARCHES = "RESEARCHES"
    AUTHORED = "AUTHORED"
    RELATED_TO = "RELATED_TO"
    USES = "USES"
    APPLIES_TO = "APPLIES_TO"
    HAS_REQUIREMENT = "HAS_REQUIREMENT"
    MEMBER_OF = "MEMBER_OF"
    LOCATED_IN = "LOCATED_IN"
    OFFERS = "OFFERS"
    HAS_KNOWLEDGE_POINT = "HAS_KNOWLEDGE_POINT"
    PARTICIPATES_IN = "PARTICIPATES_IN"
    WORKS_ON = "WORKS_ON"


@dataclass(frozen=True)
class RelationRule:
    relation_type: RelationType
    source_types: frozenset[EntityType]
    target_types: frozenset[EntityType]
    description: str


RELATION_RULES: dict[RelationType, RelationRule] = {
    RelationType.ENROLLED_IN: RelationRule(
        RelationType.ENROLLED_IN,
        frozenset({EntityType.STUDENT}),
        frozenset({EntityType.MAJOR}),
        "Student enrolled in a Major.",
    ),
    RelationType.BELONGS_TO: RelationRule(
        RelationType.BELONGS_TO,
        frozenset(
            {
                EntityType.MAJOR,
                EntityType.DEPARTMENT,
                EntityType.TEACHER,
                EntityType.LAB,
                EntityType.COURSE,
            }
        ),
        frozenset({EntityType.COLLEGE, EntityType.DEPARTMENT}),
        "Organizational membership or ownership.",
    ),
    RelationType.REQUIRES: RelationRule(
        RelationType.REQUIRES,
        frozenset({EntityType.MAJOR, EntityType.PROCEDURE}),
        frozenset({EntityType.COURSE, EntityType.REQUIREMENT}),
        "A major/procedure requires a course or requirement.",
    ),
    RelationType.PREREQUISITE_OF: RelationRule(
        RelationType.PREREQUISITE_OF,
        frozenset({EntityType.COURSE, EntityType.KNOWLEDGE_POINT}),
        frozenset({EntityType.COURSE, EntityType.KNOWLEDGE_POINT}),
        "Prerequisite relation between courses or knowledge points.",
    ),
    RelationType.TEACHES: RelationRule(
        RelationType.TEACHES,
        frozenset({EntityType.TEACHER}),
        frozenset({EntityType.COURSE}),
        "Teacher teaches a course.",
    ),
    RelationType.RESEARCHES: RelationRule(
        RelationType.RESEARCHES,
        frozenset({EntityType.TEACHER, EntityType.LAB}),
        frozenset({EntityType.RESEARCH_AREA}),
        "Teacher or lab researches an area.",
    ),
    RelationType.AUTHORED: RelationRule(
        RelationType.AUTHORED,
        frozenset({EntityType.TEACHER}),
        frozenset({EntityType.PAPER}),
        "Teacher authored a paper.",
    ),
    RelationType.RELATED_TO: RelationRule(
        RelationType.RELATED_TO,
        frozenset(
            {
                EntityType.PAPER,
                EntityType.COURSE,
                EntityType.BOOK,
                EntityType.KNOWLEDGE_POINT,
                EntityType.RESEARCH_AREA,
            }
        ),
        frozenset({EntityType.RESEARCH_AREA, EntityType.KNOWLEDGE_POINT}),
        "Semantic relation to a research area or knowledge point.",
    ),
    RelationType.USES: RelationRule(
        RelationType.USES,
        frozenset({EntityType.COURSE}),
        frozenset({EntityType.BOOK, EntityType.LIBRARY_RESOURCE}),
        "Course uses a book or library resource.",
    ),
    RelationType.APPLIES_TO: RelationRule(
        RelationType.APPLIES_TO,
        frozenset({EntityType.POLICY}),
        frozenset({EntityType.COLLEGE, EntityType.DEPARTMENT, EntityType.MAJOR}),
        "Policy applies to an organizational/academic scope.",
    ),
    RelationType.HAS_REQUIREMENT: RelationRule(
        RelationType.HAS_REQUIREMENT,
        frozenset({EntityType.POLICY, EntityType.PROCEDURE, EntityType.MAJOR}),
        frozenset({EntityType.REQUIREMENT}),
        "Policy/procedure/major has a requirement.",
    ),
    RelationType.MEMBER_OF: RelationRule(
        RelationType.MEMBER_OF,
        frozenset({EntityType.TEACHER, EntityType.STUDENT}),
        frozenset({EntityType.LAB, EntityType.PROJECT}),
        "Person is a member of a lab or project.",
    ),
    RelationType.LOCATED_IN: RelationRule(
        RelationType.LOCATED_IN,
        frozenset({EntityType.CLASSROOM, EntityType.LAB, EntityType.LIBRARY_RESOURCE}),
        frozenset({EntityType.BUILDING}),
        "Physical location relation.",
    ),
    RelationType.OFFERS: RelationRule(
        RelationType.OFFERS,
        frozenset({EntityType.COLLEGE, EntityType.DEPARTMENT}),
        frozenset({EntityType.MAJOR, EntityType.COURSE}),
        "College/department offers a major or course.",
    ),
    RelationType.HAS_KNOWLEDGE_POINT: RelationRule(
        RelationType.HAS_KNOWLEDGE_POINT,
        frozenset({EntityType.COURSE}),
        frozenset({EntityType.KNOWLEDGE_POINT}),
        "Course contains a knowledge point.",
    ),
    RelationType.PARTICIPATES_IN: RelationRule(
        RelationType.PARTICIPATES_IN,
        frozenset({EntityType.STUDENT, EntityType.TEACHER}),
        frozenset({EntityType.ACTIVITY, EntityType.PROJECT}),
        "Person participates in an activity/project.",
    ),
    RelationType.WORKS_ON: RelationRule(
        RelationType.WORKS_ON,
        frozenset({EntityType.TEACHER, EntityType.STUDENT, EntityType.LAB}),
        frozenset({EntityType.PROJECT}),
        "Person/lab works on a project.",
    ),
}


ENTITY_DESCRIPTIONS: dict[EntityType, str] = {
    EntityType.STUDENT: "Campus student.",
    EntityType.TEACHER: "Campus teacher or researcher.",
    EntityType.COLLEGE: "College/school within the university.",
    EntityType.DEPARTMENT: "Academic or administrative department.",
    EntityType.MAJOR: "Academic major/program.",
    EntityType.COURSE: "Course offered by the university.",
    EntityType.KNOWLEDGE_POINT: "Knowledge point taught or researched.",
    EntityType.POLICY: "Campus policy/regulation.",
    EntityType.PROCEDURE: "Campus business procedure/workflow.",
    EntityType.REQUIREMENT: "Explicit policy/program requirement.",
    EntityType.RESEARCH_AREA: "Research domain/topic.",
    EntityType.PAPER: "Academic paper/publication.",
    EntityType.PROJECT: "Research/teaching/campus project.",
    EntityType.LAB: "Laboratory or research group.",
    EntityType.BOOK: "Book or textbook.",
    EntityType.LIBRARY_RESOURCE: "Library-held resource or collection item.",
    EntityType.BUILDING: "Campus building.",
    EntityType.CLASSROOM: "Classroom or reservable room.",
    EntityType.ACTIVITY: "Campus activity/event.",
}


def validate_relation(
    relation_type: RelationType,
    source_type: EntityType,
    target_type: EntityType,
) -> None:
    rule = RELATION_RULES[relation_type]
    if source_type not in rule.source_types or target_type not in rule.target_types:
        raise ValueError(
            f"Invalid ontology relation: {source_type.value} "
            f"-[{relation_type.value}]-> {target_type.value}"
        )


def ontology_summary() -> dict[str, object]:
    return {
        "entity_count": len(EntityType),
        "relation_count": len(RelationType),
        "entities": [
            {
                "type": entity_type.value,
                "description": ENTITY_DESCRIPTIONS[entity_type],
            }
            for entity_type in EntityType
        ],
        "relations": [
            {
                "type": relation_type.value,
                "source_types": sorted(item.value for item in rule.source_types),
                "target_types": sorted(item.value for item in rule.target_types),
                "description": rule.description,
            }
            for relation_type, rule in RELATION_RULES.items()
        ],
    }

# ---- app/graph/types.py ----
@dataclass(frozen=True)
class GraphEvidence:
    source_document_id: str
    source_chunk_id: str
    confidence: float = 1.0
    effective_from: date | None = None
    effective_to: date | None = None


@dataclass(frozen=True)
class GraphEntity:
    entity_id: str
    entity_type: EntityType
    name: str
    aliases: tuple[str, ...] = ()
    description: str | None = None
    properties: dict[str, Any] = field(default_factory=dict)
    evidence: GraphEvidence | None = None


@dataclass(frozen=True)
class GraphRelation:
    relation_id: str
    relation_type: RelationType
    source_id: str
    source_type: EntityType
    target_id: str
    target_type: EntityType
    properties: dict[str, Any] = field(default_factory=dict)
    evidence: GraphEvidence | None = None

# ---- app/graph/repository.py ----
def _serialize_value(value: Any) -> Any:
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, tuple):
        return list(value)
    return value


def _clean_properties(properties: dict[str, Any]) -> dict[str, Any]:
    return {
        key: _serialize_value(value)
        for key, value in properties.items()
        if value is not None
    }


class Neo4jGraphRepository:
    def __init__(
        self,
        driver: Driver | None = None,
        *,
        database: str | None = None,
    ) -> None:
        settings = get_settings()
        self.driver = driver or create_neo4j_driver(settings)
        self._owns_driver = driver is None
        self.database = database or settings.neo4j_database

    def close(self) -> None:
        if self._owns_driver:
            self.driver.close()

    def bootstrap_schema(self) -> dict[str, int]:
        statements = [
            (
                "CREATE CONSTRAINT campusmind_entity_id IF NOT EXISTS "
                "FOR (n:CampusEntity) REQUIRE n.entity_id IS UNIQUE"
            ),
            (
                "CREATE INDEX campusmind_entity_name IF NOT EXISTS "
                "FOR (n:CampusEntity) ON (n.name)"
            ),
            (
                "CREATE INDEX campusmind_entity_type IF NOT EXISTS "
                "FOR (n:CampusEntity) ON (n.entity_type)"
            ),
            (
                "CREATE INDEX campusmind_source_document IF NOT EXISTS "
                "FOR (n:CampusEntity) ON (n.source_document_id)"
            ),
        ]

        with self.driver.session(database=self.database) as session:
            for statement in statements:
                session.run(statement).consume()

        return {
            "constraints": 1,
            "indexes": 3,
        }

    def upsert_entity(self, entity: GraphEntity) -> dict[str, Any]:
        label = entity.entity_type.value
        properties = {
            "name": entity.name,
            "aliases": list(entity.aliases),
            "aliases_text": " ".join(entity.aliases),
            "description": entity.description,
            "entity_type": entity.entity_type.value,
            "campusmind_graph": True,
            **entity.properties,
        }
        if entity.evidence is not None:
            properties.update(
                {
                    "source_document_id": entity.evidence.source_document_id,
                    "source_chunk_id": entity.evidence.source_chunk_id,
                    "confidence": entity.evidence.confidence,
                    "effective_from": entity.evidence.effective_from,
                    "effective_to": entity.evidence.effective_to,
                }
            )
        properties = _clean_properties(properties)

        query = f"""
        MERGE (n:CampusEntity {{entity_id: $entity_id}})
        ON CREATE SET n.created_at = datetime()
        SET n:`{label}`,
            n += $properties,
            n.updated_at = datetime()
        RETURN n.entity_id AS entity_id,
               n.entity_type AS entity_type,
               n.name AS name,
               labels(n) AS labels
        """
        with self.driver.session(database=self.database) as session:
            record = session.run(
                query,
                entity_id=entity.entity_id,
                properties=properties,
            ).single(strict=True)
        return dict(record)

    def upsert_relation(self, relation: GraphRelation) -> dict[str, Any]:
        source_label = relation.source_type.value
        target_label = relation.target_type.value
        rel_type = relation.relation_type.value
        properties = {
            "relation_id": relation.relation_id,
            "campusmind_graph": True,
            **relation.properties,
        }
        if relation.evidence is not None:
            properties.update(
                {
                    "source_document_id": relation.evidence.source_document_id,
                    "source_chunk_id": relation.evidence.source_chunk_id,
                    "confidence": relation.evidence.confidence,
                    "effective_from": relation.evidence.effective_from,
                    "effective_to": relation.evidence.effective_to,
                }
            )
        properties = _clean_properties(properties)

        query = f"""
        MATCH (source:CampusEntity:`{source_label}` {{entity_id: $source_id}})
        MATCH (target:CampusEntity:`{target_label}` {{entity_id: $target_id}})
        MERGE (source)-[r:`{rel_type}` {{relation_id: $relation_id}}]->(target)
        ON CREATE SET r.created_at = datetime()
        SET r += $properties,
            r.updated_at = datetime()
        RETURN r.relation_id AS relation_id,
               type(r) AS relation_type,
               source.entity_id AS source_id,
               target.entity_id AS target_id
        """
        with self.driver.session(database=self.database) as session:
            record = session.run(
                query,
                source_id=relation.source_id,
                target_id=relation.target_id,
                relation_id=relation.relation_id,
                properties=properties,
            ).single()
        if record is None:
            raise ValueError(
                "Cannot create relation because source or target entity does not exist "
                "with the expected ontology label."
            )
        return dict(record)

    def stats(self) -> dict[str, Any]:
        with self.driver.session(database=self.database) as session:
            node_rows = list(
                session.run(
                    """
                    MATCH (n:CampusEntity)
                    RETURN n.entity_type AS type, count(*) AS count
                    ORDER BY type
                    """
                )
            )
            relation_rows = list(
                session.run(
                    """
                    MATCH (:CampusEntity)-[r]->(:CampusEntity)
                    WHERE coalesce(r.campusmind_graph, false) = true
                    RETURN type(r) AS type, count(*) AS count
                    ORDER BY type
                    """
                )
            )
        nodes_by_type = {row["type"]: row["count"] for row in node_rows}
        relations_by_type = {row["type"]: row["count"] for row in relation_rows}
        return {
            "node_count": sum(nodes_by_type.values()),
            "relation_count": sum(relations_by_type.values()),
            "nodes_by_type": nodes_by_type,
            "relations_by_type": relations_by_type,
        }

    def list_entities(
        self,
        *,
        entity_type: str | None = None,
        keyword: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> dict[str, Any]:
        """Read-only entity browser."""

        offset = max(
            0,
            int(offset),
        )

        limit = max(
            1,
            min(int(limit), 200),
        )

        keyword_value = (
            keyword or ""
        ).strip().lower()

        where = """
        ($entity_type IS NULL OR
         n.entity_type = $entity_type)
        AND
        (
          $keyword = '' OR
          toLower(coalesce(n.name, ''))
            CONTAINS $keyword OR
          toLower(coalesce(n.entity_id, ''))
            CONTAINS $keyword OR
          toLower(coalesce(n['description'], ''))
            CONTAINS $keyword OR
          toLower(coalesce(n.aliases_text, ''))
            CONTAINS $keyword
        )
        """

        with self.driver.session(
            database=self.database
        ) as session:
            total_record = session.run(
                f"""
                MATCH (n:CampusEntity)
                WHERE {where}
                RETURN count(n) AS total
                """,
                entity_type=entity_type,
                keyword=keyword_value,
            ).single(strict=True)

            rows = list(
                session.run(
                    f"""
                    MATCH (n:CampusEntity)
                    WHERE {where}
                    RETURN
                      n.entity_id AS entity_id,
                      n.entity_type AS entity_type,
                      n.name AS name,
                      coalesce(
                        n.aliases,
                        []
                      ) AS aliases,
                      n['description'] AS description,
                      n.source_document_id
                        AS source_document_id,
                      n.source_chunk_id
                        AS source_chunk_id,
                      n.confidence AS confidence,
                      toString(
                        n.created_at
                      ) AS created_at,
                      toString(
                        n.updated_at
                      ) AS updated_at
                    ORDER BY
                      n.entity_type,
                      n.name,
                      n.entity_id
                    SKIP $offset
                    LIMIT $limit
                    """,
                    entity_type=entity_type,
                    keyword=keyword_value,
                    offset=offset,
                    limit=limit,
                )
            )

        return {
            "total": int(
                total_record["total"]
            ),
            "offset": offset,
            "limit": limit,
            "entity_type": entity_type,
            "keyword": keyword or "",
            "entities": [
                dict(row)
                for row in rows
            ],
        }

    def list_relations(
        self,
        *,
        relation_type: str | None = None,
        keyword: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> dict[str, Any]:
        """Read-only CampusMind relation browser."""

        offset = max(
            0,
            int(offset),
        )

        limit = max(
            1,
            min(int(limit), 200),
        )

        keyword_value = (
            keyword or ""
        ).strip().lower()

        where = """
        coalesce(
          r.campusmind_graph,
          false
        ) = true
        AND
        (
          $relation_type IS NULL OR
          type(r) = $relation_type
        )
        AND
        (
          $keyword = '' OR
          toLower(
            coalesce(
              source.name,
              ''
            )
          ) CONTAINS $keyword OR
          toLower(
            coalesce(
              source.entity_id,
              ''
            )
          ) CONTAINS $keyword OR
          toLower(
            coalesce(
              target.name,
              ''
            )
          ) CONTAINS $keyword OR
          toLower(
            coalesce(
              target.entity_id,
              ''
            )
          ) CONTAINS $keyword OR
          toLower(
            coalesce(
              r.relation_id,
              ''
            )
          ) CONTAINS $keyword OR
          toLower(type(r))
            CONTAINS $keyword
        )
        """

        with self.driver.session(
            database=self.database
        ) as session:
            total_record = session.run(
                f"""
                MATCH
                  (source:CampusEntity)
                  -[r]->
                  (target:CampusEntity)
                WHERE {where}
                RETURN count(r) AS total
                """,
                relation_type=relation_type,
                keyword=keyword_value,
            ).single(strict=True)

            rows = list(
                session.run(
                    f"""
                    MATCH
                      (source:CampusEntity)
                      -[r]->
                      (target:CampusEntity)
                    WHERE {where}
                    RETURN
                      r.relation_id
                        AS relation_id,
                      type(r)
                        AS relation_type,
                      source.entity_id
                        AS source_id,
                      source.entity_type
                        AS source_type,
                      source.name
                        AS source_name,
                      target.entity_id
                        AS target_id,
                      target.entity_type
                        AS target_type,
                      target.name
                        AS target_name,
                      r.source_document_id
                        AS source_document_id,
                      r.source_chunk_id
                        AS source_chunk_id,
                      r.confidence
                        AS confidence,
                      toString(
                        r.created_at
                      ) AS created_at,
                      toString(
                        r.updated_at
                      ) AS updated_at
                    ORDER BY
                      type(r),
                      source.name,
                      target.name,
                      r.relation_id
                    SKIP $offset
                    LIMIT $limit
                    """,
                    relation_type=relation_type,
                    keyword=keyword_value,
                    offset=offset,
                    limit=limit,
                )
            )

        return {
            "total": int(
                total_record["total"]
            ),
            "offset": offset,
            "limit": limit,
            "relation_type": relation_type,
            "keyword": keyword or "",
            "relations": [
                dict(row)
                for row in rows
            ],
        }

    def entity_context(
        self,
        entity_id: str,
        *,
        limit: int = 100,
    ) -> dict[str, Any] | None:
        """Read-only entity detail with directly connected graph relations."""

        entity_id = str(
            entity_id
        ).strip()

        if not entity_id:
            return None

        limit = max(
            1,
            min(int(limit), 200),
        )

        with self.driver.session(
            database=self.database
        ) as session:
            entity_record = session.run(
                """
                MATCH (n:CampusEntity {
                  entity_id: $entity_id
                })
                RETURN
                  n.entity_id AS entity_id,
                  n.entity_type AS entity_type,
                  n.name AS name,
                  coalesce(
                    n.aliases,
                    []
                  ) AS aliases,
                  properties(n) AS raw_properties,
                  n.source_document_id
                    AS source_document_id,
                  n.source_chunk_id
                    AS source_chunk_id,
                  n.confidence AS confidence,
                  toString(
                    n.created_at
                  ) AS created_at,
                  toString(
                    n.updated_at
                  ) AS updated_at
                """,
                entity_id=entity_id,
            ).single()

            if entity_record is None:
                return None

            count_record = session.run(
                """
                MATCH
                  (source:CampusEntity)
                  -[r]->
                  (target:CampusEntity)
                WHERE
                  coalesce(
                    r.campusmind_graph,
                    false
                  ) = true
                  AND (
                    source.entity_id = $entity_id
                    OR
                    target.entity_id = $entity_id
                  )
                RETURN count(r) AS total
                """,
                entity_id=entity_id,
            ).single(strict=True)

            relation_rows = list(
                session.run(
                    """
                    MATCH
                      (source:CampusEntity)
                      -[r]->
                      (target:CampusEntity)
                    WHERE
                      coalesce(
                        r.campusmind_graph,
                        false
                      ) = true
                      AND (
                        source.entity_id = $entity_id
                        OR
                        target.entity_id = $entity_id
                      )
                    RETURN
                      CASE
                        WHEN source.entity_id
                             = $entity_id
                        THEN 'outgoing'
                        ELSE 'incoming'
                      END AS direction,
                      r.relation_id
                        AS relation_id,
                      type(r)
                        AS relation_type,
                      source.entity_id
                        AS source_id,
                      source.entity_type
                        AS source_type,
                      source.name
                        AS source_name,
                      target.entity_id
                        AS target_id,
                      target.entity_type
                        AS target_type,
                      target.name
                        AS target_name,
                      r.source_document_id
                        AS source_document_id,
                      r.source_chunk_id
                        AS source_chunk_id,
                      r.confidence
                        AS confidence,
                      toString(
                        r.created_at
                      ) AS created_at
                    ORDER BY
                      direction,
                      type(r),
                      source.name,
                      target.name,
                      r.relation_id
                    LIMIT $limit
                    """,
                    entity_id=entity_id,
                    limit=limit,
                )
            )

        entity = dict(
            entity_record
        )

        raw_properties = dict(
            entity.pop(
                "raw_properties",
                {},
            )
            or {}
        )

        reserved = {
            "entity_id",
            "entity_type",
            "name",
            "aliases",
            "aliases_text",
            "campusmind_graph",
            "source_document_id",
            "source_chunk_id",
            "confidence",
            "created_at",
            "updated_at",
        }

        entity["description"] = (
            raw_properties.get(
                "description"
            )
        )

        entity["properties"] = {
            key: value
            for key, value
            in raw_properties.items()
            if key not in reserved
            and key != "description"
        }

        return {
            "entity": entity,
            "relation_count": int(
                count_record["total"]
            ),
            "limit": limit,
            "relations": [
                dict(row)
                for row in relation_rows
            ],
        }

    def source_chunks_graph_status(
        self,
        source_chunk_ids,
    ) -> dict[str, dict[str, Any]]:
        """Read-only CampusMind graph status for source chunks."""

        chunk_ids = list(
            dict.fromkeys(
                str(item).strip()
                for item in source_chunk_ids
                if str(item).strip()
            )
        )

        statuses = {
            chunk_id: {
                "relation_count": 0,
                "evidence_gap_count": 0,
                "relation_types": [],
                "relation_type_counts": {},
                "extraction_methods": [],
                "extraction_method_counts": {},
            }
            for chunk_id in chunk_ids
        }

        if not chunk_ids:
            return statuses

        with self.driver.session(
            database=self.database
        ) as session:
            rows = list(
                session.run(
                    """
                    MATCH
                      (:CampusEntity)
                      -[r]->
                      (:CampusEntity)
                    WHERE
                      r.source_chunk_id IN $chunk_ids
                      AND coalesce(
                        r.campusmind_graph,
                        false
                      ) = true
                    RETURN
                      r.source_chunk_id
                        AS chunk_id,
                      type(r)
                        AS relation_type,
                      coalesce(
                        r.extraction_method,
                        '<unspecified>'
                      )
                        AS extraction_method,
                      count(r)
                        AS relation_count,
                      sum(
                        CASE
                          WHEN
                            r.source_document_id IS NULL
                            OR r.source_chunk_id IS NULL
                            OR r.confidence IS NULL
                            OR r.created_at IS NULL
                          THEN 1
                          ELSE 0
                        END
                      )
                        AS evidence_gap_count
                    ORDER BY
                      chunk_id,
                      relation_type,
                      extraction_method
                    """,
                    chunk_ids=chunk_ids,
                )
            )

        for row in rows:
            chunk_id = str(
                row["chunk_id"]
            )

            status = statuses[
                chunk_id
            ]

            count = int(
                row["relation_count"]
            )

            gap_count = int(
                row[
                    "evidence_gap_count"
                ]
            )

            relation_type = str(
                row["relation_type"]
            )

            extraction_method = str(
                row[
                    "extraction_method"
                ]
            )

            status[
                "relation_count"
            ] += count

            status[
                "evidence_gap_count"
            ] += gap_count

            status[
                "relation_type_counts"
            ][relation_type] = (
                status[
                    "relation_type_counts"
                ].get(
                    relation_type,
                    0,
                )
                + count
            )

            status[
                "extraction_method_counts"
            ][extraction_method] = (
                status[
                    "extraction_method_counts"
                ].get(
                    extraction_method,
                    0,
                )
                + count
            )

        for status in statuses.values():
            status[
                "relation_types"
            ] = sorted(
                status[
                    "relation_type_counts"
                ]
            )

            status[
                "extraction_methods"
            ] = sorted(
                status[
                    "extraction_method_counts"
                ]
            )

        return statuses

    def relation_evidence_gaps(self, relation_ids: Iterable[str]) -> list[str]:
        relation_ids = list(relation_ids)
        if not relation_ids:
            return []
        with self.driver.session(database=self.database) as session:
            rows = list(
                session.run(
                    """
                    MATCH ()-[r]->()
                    WHERE r.relation_id IN $relation_ids
                      AND (
                        r.source_document_id IS NULL OR
                        r.source_chunk_id IS NULL OR
                        r.confidence IS NULL OR
                        r.created_at IS NULL
                      )
                    RETURN r.relation_id AS relation_id
                    """,
                    relation_ids=relation_ids,
                )
            )
        return [row["relation_id"] for row in rows]

    def fetch_path(self, source_id: str, relation_type: RelationType, target_id: str) -> dict[str, Any] | None:
        rel_type = relation_type.value
        query = f"""
        MATCH (source:CampusEntity {{entity_id: $source_id}})
              -[r:`{rel_type}`]->
              (target:CampusEntity {{entity_id: $target_id}})
        RETURN source.entity_id AS source_id,
               source.name AS source_name,
               type(r) AS relation_type,
               target.entity_id AS target_id,
               target.name AS target_name,
               r.source_document_id AS source_document_id,
               r.source_chunk_id AS source_chunk_id,
               r.confidence AS confidence
        """
        with self.driver.session(database=self.database) as session:
            record = session.run(
                query,
                source_id=source_id,
                target_id=target_id,
            ).single()
        return dict(record) if record else None

# ---- app/graph/service.py ----
if TYPE_CHECKING:
    from campusmind.knowledge.graph import Neo4jGraphRepository


class CampusGraphService:
    def __init__(self, repository: "Neo4jGraphRepository | Any | None" = None) -> None:
        if repository is None:
            from campusmind.knowledge.graph import Neo4jGraphRepository

            repository = Neo4jGraphRepository()
            self._owns_repository = True
        else:
            self._owns_repository = False
        self.repository = repository

    def close(self) -> None:
        if self._owns_repository:
            self.repository.close()

    def ontology(self) -> dict[str, object]:
        return ontology_summary()

    def bootstrap(self) -> dict[str, int]:
        return self.repository.bootstrap_schema()

    def upsert_entity(self, entity: GraphEntity) -> dict[str, Any]:
        return self.repository.upsert_entity(entity)

    def upsert_relation(self, relation: GraphRelation) -> dict[str, Any]:
        validate_relation(
            relation.relation_type,
            relation.source_type,
            relation.target_type,
        )
        if relation.evidence is None:
            raise ValueError("Graph relations must carry source evidence.")
        return self.repository.upsert_relation(relation)

    def stats(self) -> dict[str, Any]:
        return self.repository.stats()


    def list_entities(
        self,
        *,
        entity_type: str | None = None,
        keyword: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> dict[str, Any]:
        return self.repository.list_entities(
            entity_type=entity_type,
            keyword=keyword,
            offset=offset,
            limit=limit,
        )

    def list_relations(
        self,
        *,
        relation_type: str | None = None,
        keyword: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> dict[str, Any]:
        return self.repository.list_relations(
            relation_type=relation_type,
            keyword=keyword,
            offset=offset,
            limit=limit,
        )


    def entity_context(
        self,
        entity_id: str,
        *,
        limit: int = 100,
    ) -> dict[str, Any] | None:
        return self.repository.entity_context(
            entity_id,
            limit=limit,
        )


    def source_chunks_graph_status(
        self,
        source_chunk_ids,
    ) -> dict[str, dict[str, Any]]:
        return (
            self.repository
            .source_chunks_graph_status(
                source_chunk_ids
            )
        )

# ---- app/graph/seed.py ----
DOC_TRAINING = "00000000-0000-0000-0000-000000000701"
DOC_TEACHER = "00000000-0000-0000-0000-000000000702"
DOC_COURSE = "00000000-0000-0000-0000-000000000703"
CHUNK_TRAINING = "00000000-0000-0000-0000-000000000711"
CHUNK_TEACHER = "00000000-0000-0000-0000-000000000712"
CHUNK_COURSE = "00000000-0000-0000-0000-000000000713"


def _evidence(document_id: str, chunk_id: str, confidence: float = 0.98) -> GraphEvidence:
    return GraphEvidence(
        source_document_id=document_id,
        source_chunk_id=chunk_id,
        confidence=confidence,
        effective_from=date(2026, 1, 1),
    )


def seed_campus_graph(service: CampusGraphService) -> dict[str, object]:
    training = _evidence(DOC_TRAINING, CHUNK_TRAINING)
    teacher = _evidence(DOC_TEACHER, CHUNK_TEACHER)
    course = _evidence(DOC_COURSE, CHUNK_COURSE)

    entities = [
        GraphEntity("college:computer-science", EntityType.COLLEGE, "计算机学院", evidence=training),
        GraphEntity("major:software-engineering", EntityType.MAJOR, "软件工程", evidence=training),
        GraphEntity("course:data-structures", EntityType.COURSE, "数据结构", evidence=training),
        GraphEntity("course:linear-algebra", EntityType.COURSE, "线性代数", evidence=course),
        GraphEntity("course:machine-learning", EntityType.COURSE, "机器学习", evidence=course),
        GraphEntity("course:deep-learning", EntityType.COURSE, "深度学习", evidence=course),
        GraphEntity("teacher:li-ming", EntityType.TEACHER, "李明", aliases=("李明教授",), evidence=teacher),
        GraphEntity("research:knowledge-graph", EntityType.RESEARCH_AREA, "知识图谱", evidence=teacher),
        GraphEntity("research:llm", EntityType.RESEARCH_AREA, "大语言模型", aliases=("LLM",), evidence=teacher),
        GraphEntity("lab:ai-knowledge", EntityType.LAB, "智能知识实验室", evidence=teacher),
        GraphEntity("requirement:software-engineering-credits", EntityType.REQUIREMENT, "软件工程毕业最低160学分", evidence=training),
        GraphEntity("policy:software-engineering-2026", EntityType.POLICY, "2026软件工程培养方案", evidence=training),
    ]

    relations = [
        GraphRelation("rel:major-belongs-college", RelationType.BELONGS_TO, "major:software-engineering", EntityType.MAJOR, "college:computer-science", EntityType.COLLEGE, evidence=training),
        GraphRelation("rel:major-requires-data-structures", RelationType.REQUIRES, "major:software-engineering", EntityType.MAJOR, "course:data-structures", EntityType.COURSE, evidence=training),
        GraphRelation("rel:major-has-credit-requirement", RelationType.HAS_REQUIREMENT, "major:software-engineering", EntityType.MAJOR, "requirement:software-engineering-credits", EntityType.REQUIREMENT, evidence=training),
        GraphRelation("rel:policy-applies-major", RelationType.APPLIES_TO, "policy:software-engineering-2026", EntityType.POLICY, "major:software-engineering", EntityType.MAJOR, evidence=training),
        GraphRelation("rel:policy-has-credit-requirement", RelationType.HAS_REQUIREMENT, "policy:software-engineering-2026", EntityType.POLICY, "requirement:software-engineering-credits", EntityType.REQUIREMENT, evidence=training),
        GraphRelation("rel:linear-algebra-prereq-ml", RelationType.PREREQUISITE_OF, "course:linear-algebra", EntityType.COURSE, "course:machine-learning", EntityType.COURSE, evidence=course),
        GraphRelation("rel:ml-prereq-deep-learning", RelationType.PREREQUISITE_OF, "course:machine-learning", EntityType.COURSE, "course:deep-learning", EntityType.COURSE, evidence=course),
        GraphRelation("rel:li-ming-researches-kg", RelationType.RESEARCHES, "teacher:li-ming", EntityType.TEACHER, "research:knowledge-graph", EntityType.RESEARCH_AREA, evidence=teacher),
        GraphRelation("rel:li-ming-researches-llm", RelationType.RESEARCHES, "teacher:li-ming", EntityType.TEACHER, "research:llm", EntityType.RESEARCH_AREA, evidence=teacher),
        GraphRelation("rel:li-ming-member-lab", RelationType.MEMBER_OF, "teacher:li-ming", EntityType.TEACHER, "lab:ai-knowledge", EntityType.LAB, evidence=teacher),
        GraphRelation("rel:li-ming-belongs-college", RelationType.BELONGS_TO, "teacher:li-ming", EntityType.TEACHER, "college:computer-science", EntityType.COLLEGE, evidence=teacher),
    ]

    for entity in entities:
        service.upsert_entity(entity)
    for relation in relations:
        service.upsert_relation(relation)

    return {
        "entity_ids": [item.entity_id for item in entities],
        "relation_ids": [item.relation_id for item in relations],
        "entity_count": len(entities),
        "relation_count": len(relations),
    }
