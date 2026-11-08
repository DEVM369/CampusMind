from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from campusmind.tools.student import StudentContextNotFound
from campusmind.tools.student import StudentSqlToolService
from campusmind.platform.db import get_db
from campusmind.api.schemas import StudentToolQueryRequest, StudentToolResponse
from campusmind.platform.security import AuthorizationDenied, AuthorizationService


router = APIRouter()


def get_student_sql_service(db: Session = Depends(get_db)) -> StudentSqlToolService:
    return StudentSqlToolService(db)


def get_authorization_service(db: Session = Depends(get_db)) -> AuthorizationService:
    return AuthorizationService(db)


def _authorize_self(authorization: AuthorizationService, actor_user_id) -> None:
    try:
        authorization.require("student.self.read", actor_user_id)
    except AuthorizationDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


def _response(result) -> StudentToolResponse:
    return StudentToolResponse(
        capability=result.capability.value,
        actor_user_id=result.actor_user_id,
        answer=result.answer,
        data=result.data,
        source=result.source,
        self_only=result.self_only,
    )


def _run(callable_):
    try:
        return _response(callable_())
    except StudentContextNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/query", response_model=StudentToolResponse)
def query_student_data(
    request: StudentToolQueryRequest,
    service: StudentSqlToolService = Depends(get_student_sql_service),
    authorization: AuthorizationService = Depends(get_authorization_service),
) -> StudentToolResponse:
    _authorize_self(authorization, request.actor_user_id)
    return _run(lambda: service.answer(request.query, request.actor_user_id))


@router.get("/profile", response_model=StudentToolResponse)
def get_profile(
    actor_user_id: uuid.UUID,
    service: StudentSqlToolService = Depends(get_student_sql_service),
    authorization: AuthorizationService = Depends(get_authorization_service),
) -> StudentToolResponse:
    _authorize_self(authorization, actor_user_id)
    return _run(lambda: service.get_student_profile(actor_user_id))


@router.get("/credits", response_model=StudentToolResponse)
def get_credits(
    actor_user_id: uuid.UUID,
    service: StudentSqlToolService = Depends(get_student_sql_service),
    authorization: AuthorizationService = Depends(get_authorization_service),
) -> StudentToolResponse:
    _authorize_self(authorization, actor_user_id)
    return _run(lambda: service.get_student_credits(actor_user_id))


@router.get("/courses", response_model=StudentToolResponse)
def get_courses(
    actor_user_id: uuid.UUID,
    service: StudentSqlToolService = Depends(get_student_sql_service),
    authorization: AuthorizationService = Depends(get_authorization_service),
) -> StudentToolResponse:
    _authorize_self(authorization, actor_user_id)
    return _run(lambda: service.get_student_courses(actor_user_id))


@router.get("/grades", response_model=StudentToolResponse)
def get_grades(
    actor_user_id: uuid.UUID,
    service: StudentSqlToolService = Depends(get_student_sql_service),
    authorization: AuthorizationService = Depends(get_authorization_service),
) -> StudentToolResponse:
    _authorize_self(authorization, actor_user_id)
    return _run(lambda: service.get_student_grades(actor_user_id))


@router.get("/graduation-progress", response_model=StudentToolResponse)
def get_graduation_progress(
    actor_user_id: uuid.UUID,
    service: StudentSqlToolService = Depends(get_student_sql_service),
    authorization: AuthorizationService = Depends(get_authorization_service),
) -> StudentToolResponse:
    _authorize_self(authorization, actor_user_id)
    return _run(lambda: service.get_graduation_progress(actor_user_id))
