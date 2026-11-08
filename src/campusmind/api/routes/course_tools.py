from __future__ import annotations

from collections.abc import Generator
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from campusmind.tools.course import CourseToolError, CourseToolNotFound, CourseToolService
from campusmind.platform.db import get_db
from campusmind.api.schemas import (
    CoursePrerequisiteResponse,
    CourseQueryRequest,
    CourseQueryResponse,
    CourseScheduleResponse,
    CourseSearchRequest,
    CourseSearchResponse,
    CourseTeacherResponse,
)


router = APIRouter()


def get_course_service(db: Session = Depends(get_db)) -> Generator[CourseToolService, None, None]:
    yield CourseToolService(db)


def _error(exc: CourseToolError) -> None:
    if isinstance(exc, CourseToolNotFound):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/search", response_model=CourseSearchResponse)
def search(
    request: CourseSearchRequest,
    service: CourseToolService = Depends(get_course_service),
) -> CourseSearchResponse:
    try:
        values = service.search_courses(request.query, limit=request.limit)
    except CourseToolError as exc:
        _error(exc)
    return CourseSearchResponse(courses=values)


@router.post("/query", response_model=CourseQueryResponse)
def natural_query(
    request: CourseQueryRequest,
    service: CourseToolService = Depends(get_course_service),
) -> CourseQueryResponse:
    try:
        result = service.answer(request.query)
    except CourseToolError as exc:
        _error(exc)
    return CourseQueryResponse(
        capability=result.capability.value,
        answer=result.answer,
        data=result.data,
        source=result.source,
        read_only=result.read_only,
    )


@router.get("/{course_id}/schedule", response_model=CourseScheduleResponse)
def schedule(
    course_id: uuid.UUID,
    academic_year: str | None = None,
    semester: str | None = None,
    service: CourseToolService = Depends(get_course_service),
) -> CourseScheduleResponse:
    try:
        data = service.get_course_schedule(
            course_id,
            academic_year=academic_year,
            semester=semester,
        )
    except CourseToolError as exc:
        _error(exc)
    return CourseScheduleResponse(**data)


@router.get("/{course_id}/prerequisites", response_model=CoursePrerequisiteResponse)
def prerequisites(
    course_id: uuid.UUID,
    service: CourseToolService = Depends(get_course_service),
) -> CoursePrerequisiteResponse:
    try:
        data = service.get_course_prerequisites(course_id)
    except CourseToolError as exc:
        _error(exc)
    return CoursePrerequisiteResponse(**data)


@router.get("/{course_id}/teachers", response_model=CourseTeacherResponse)
def teachers(
    course_id: uuid.UUID,
    service: CourseToolService = Depends(get_course_service),
) -> CourseTeacherResponse:
    try:
        data = service.get_course_teacher(course_id)
    except CourseToolError as exc:
        _error(exc)
    return CourseTeacherResponse(**data)
