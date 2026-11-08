from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from campusmind.tools.actions import (
    ClassroomActionConflict,
    ClassroomActionError,
    ClassroomActionExpired,
    ClassroomActionNotFound,
    ClassroomActionOwnershipError,
    ClassroomActionService,
)
from campusmind.platform.db import get_db
from campusmind.platform.security import AuthorizationDenied, AuthorizationService
from campusmind.api.schemas import (
    ClassroomActionResponse,
    ClassroomPrepareRequest,
    ClassroomReservationListResponse,
    ClassroomResumeRequest,
)


router = APIRouter()


def get_classroom_service(db: Session = Depends(get_db)) -> ClassroomActionService:
    return ClassroomActionService(db)


def get_authorization_service(db: Session = Depends(get_db)) -> AuthorizationService:
    return AuthorizationService(db)


def _authorize(authorization: AuthorizationService, actor_user_id) -> None:
    try:
        authorization.require("classroom.reserve", actor_user_id)
    except AuthorizationDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


def _error(exc: Exception):
    if isinstance(exc, ClassroomActionNotFound):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, ClassroomActionOwnershipError):
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if isinstance(exc, (ClassroomActionConflict, ClassroomActionExpired)):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/prepare", response_model=ClassroomActionResponse)
def prepare(
    request: ClassroomPrepareRequest,
    service: ClassroomActionService = Depends(get_classroom_service),
    authorization: AuthorizationService = Depends(get_authorization_service),
) -> ClassroomActionResponse:
    _authorize(authorization, request.actor_user_id)
    try:
        result = service.prepare_reservation(
            request.query,
            request.actor_user_id,
            trace_id=request.trace_id,
        )
    except ClassroomActionError as exc:
        _error(exc)
    return ClassroomActionResponse(
        approval_id=result.approval_id,
        trace_id=result.trace_id,
        actor_user_id=result.actor_user_id,
        status=result.status.value,
        answer=result.answer,
        requested=result.requested.model_dump(mode="json"),
        candidates=[item.model_dump() for item in result.candidates],
        expires_at=result.expires_at,
        audit=result.audit,
    )


@router.post("/resume", response_model=ClassroomActionResponse)
def resume(
    request: ClassroomResumeRequest,
    service: ClassroomActionService = Depends(get_classroom_service),
    authorization: AuthorizationService = Depends(get_authorization_service),
) -> ClassroomActionResponse:
    _authorize(authorization, request.actor_user_id)
    try:
        result = service.resume_reservation(
            request.approval_id,
            request.actor_user_id,
            approved=request.approved,
            room_id=request.room_id,
        )
    except ClassroomActionError as exc:
        _error(exc)
    return ClassroomActionResponse(
        approval_id=result.approval_id,
        trace_id=result.trace_id,
        actor_user_id=result.actor_user_id,
        status=result.status.value,
        answer=result.answer,
        reservation=result.reservation,
        state_changed=result.state_changed,
        idempotent=result.idempotent,
        audit=result.audit,
    )


@router.get("/reservations", response_model=ClassroomReservationListResponse)
def reservations(
    actor_user_id: uuid.UUID,
    service: ClassroomActionService = Depends(get_classroom_service),
    authorization: AuthorizationService = Depends(get_authorization_service),
) -> ClassroomReservationListResponse:
    _authorize(authorization, actor_user_id)
    try:
        values = service.list_reservations(actor_user_id)
    except ClassroomActionError as exc:
        _error(exc)
    return ClassroomReservationListResponse(
        actor_user_id=str(actor_user_id),
        reservations=values,
    )
