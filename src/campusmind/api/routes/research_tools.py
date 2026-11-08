from __future__ import annotations

from collections.abc import Generator

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from campusmind.tools.research import ResearchToolError, ResearchToolService
from campusmind.platform.db import get_db
from campusmind.api.schemas import ResearchListResponse, ResearchQueryRequest, ResearchQueryResponse, ResearchSearchRequest


router = APIRouter()


def get_research_service(db: Session = Depends(get_db)) -> Generator[ResearchToolService, None, None]:
    yield ResearchToolService(db)


def _run(callable_):
    try:
        return callable_()
    except ResearchToolError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/query", response_model=ResearchQueryResponse)
def natural_query(request: ResearchQueryRequest, service: ResearchToolService = Depends(get_research_service)) -> ResearchQueryResponse:
    result = _run(lambda: service.answer(request.query))
    return ResearchQueryResponse(capability=result.capability.value, answer=result.answer, data=result.data, source=result.source, read_only=result.read_only)


@router.post("/teachers", response_model=ResearchListResponse)
def teachers(request: ResearchSearchRequest, service: ResearchToolService = Depends(get_research_service)) -> ResearchListResponse:
    items = _run(lambda: service.search_teacher(request.query, limit=request.limit))
    return ResearchListResponse(items=items, count=len(items))


@router.post("/papers", response_model=ResearchListResponse)
def papers(request: ResearchSearchRequest, service: ResearchToolService = Depends(get_research_service)) -> ResearchListResponse:
    items = _run(lambda: service.search_papers(request.query, limit=request.limit))
    return ResearchListResponse(items=items, count=len(items))


@router.post("/areas", response_model=ResearchListResponse)
def areas(request: ResearchSearchRequest, service: ResearchToolService = Depends(get_research_service)) -> ResearchListResponse:
    items = _run(lambda: service.search_research_area(request.query, limit=request.limit))
    return ResearchListResponse(items=items, count=len(items))


@router.post("/labs", response_model=ResearchListResponse)
def labs(request: ResearchSearchRequest, service: ResearchToolService = Depends(get_research_service)) -> ResearchListResponse:
    items = _run(lambda: service.search_lab(request.query, limit=request.limit))
    return ResearchListResponse(items=items, count=len(items))


@router.post("/projects", response_model=ResearchListResponse)
def projects(request: ResearchSearchRequest, service: ResearchToolService = Depends(get_research_service)) -> ResearchListResponse:
    items = _run(lambda: service.search_projects(request.query, limit=request.limit))
    return ResearchListResponse(items=items, count=len(items))
