from __future__ import annotations

from collections.abc import Generator

from fastapi import APIRouter, Depends, HTTPException

from campusmind.knowledge.graph import CampusGraphService
from campusmind.knowledge.graph import GraphEntity, GraphEvidence, GraphRelation
from campusmind.api.schemas import (
    GraphBootstrapResponse,
    GraphEntityUpsertRequest,
    GraphMutationResponse,
    GraphOntologyResponse,
    GraphRelationUpsertRequest,
    GraphStatsResponse,
)

router = APIRouter()


def get_graph_service() -> Generator[CampusGraphService, None, None]:
    service = CampusGraphService()
    try:
        yield service
    finally:
        service.close()


def _evidence(model):
    if model is None:
        return None
    return GraphEvidence(
        source_document_id=model.source_document_id,
        source_chunk_id=model.source_chunk_id,
        confidence=model.confidence,
        effective_from=model.effective_from,
        effective_to=model.effective_to,
    )


@router.get("/ontology", response_model=GraphOntologyResponse)
def ontology(service: CampusGraphService = Depends(get_graph_service)) -> GraphOntologyResponse:
    return GraphOntologyResponse.model_validate(service.ontology())


@router.post("/bootstrap", response_model=GraphBootstrapResponse)
def bootstrap(service: CampusGraphService = Depends(get_graph_service)) -> GraphBootstrapResponse:
    result = service.bootstrap()
    return GraphBootstrapResponse(**result)


@router.get("/stats", response_model=GraphStatsResponse)
def stats(service: CampusGraphService = Depends(get_graph_service)) -> GraphStatsResponse:
    return GraphStatsResponse.model_validate(service.stats())


@router.post("/entities", response_model=GraphMutationResponse)
def upsert_entity(
    request: GraphEntityUpsertRequest,
    service: CampusGraphService = Depends(get_graph_service),
) -> GraphMutationResponse:
    entity = GraphEntity(
        entity_id=request.entity_id,
        entity_type=request.entity_type,
        name=request.name,
        aliases=tuple(request.aliases),
        description=request.description,
        properties=request.properties,
        evidence=_evidence(request.evidence),
    )
    try:
        result = service.upsert_entity(entity)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return GraphMutationResponse(data=result)


@router.post("/relations", response_model=GraphMutationResponse)
def upsert_relation(
    request: GraphRelationUpsertRequest,
    service: CampusGraphService = Depends(get_graph_service),
) -> GraphMutationResponse:
    relation = GraphRelation(
        relation_id=request.relation_id,
        relation_type=request.relation_type,
        source_id=request.source_id,
        source_type=request.source_type,
        target_id=request.target_id,
        target_type=request.target_type,
        properties=request.properties,
        evidence=_evidence(request.evidence),
    )
    try:
        result = service.upsert_relation(relation)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return GraphMutationResponse(data=result)
