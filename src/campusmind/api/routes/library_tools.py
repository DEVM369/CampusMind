from __future__ import annotations

from collections.abc import Generator
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from campusmind.tools.actions import (
    ClassroomActionConflict,
    ClassroomActionError,
    ClassroomActionExpired,
    ClassroomActionNotFound,
    ClassroomActionOwnershipError,
)
from campusmind.tools.actions import LibraryActionService
from campusmind.platform.db import get_db
from campusmind.platform.security import AuthorizationDenied, AuthorizationService
from campusmind.api.schemas import (
    LibraryActionResponse,
    LibraryBorrowedListResponse,
    LibraryPrepareRequest,
    LibraryPrepareResponse,
    LibraryReservationListResponse,
    LibraryResumeRequest,
    LibrarySearchRequest,
    LibrarySearchResponse,
)


router = APIRouter()


def get_library_service(db: Session = Depends(get_db)) -> Generator[LibraryActionService, None, None]:
    yield LibraryActionService(db)


def get_authorization_service(db: Session = Depends(get_db)) -> AuthorizationService:
    return AuthorizationService(db)


def _authorize(authorization: AuthorizationService, capability: str, actor_user_id) -> None:
    try:
        authorization.require(capability, actor_user_id)
    except AuthorizationDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


def _error(exc: ClassroomActionError) -> None:
    if isinstance(exc, ClassroomActionNotFound):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, ClassroomActionOwnershipError):
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if isinstance(exc, (ClassroomActionConflict, ClassroomActionExpired)):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/search", response_model=LibrarySearchResponse)
def search(
    request: LibrarySearchRequest,
    service: LibraryActionService = Depends(get_library_service),
) -> LibrarySearchResponse:
    try:
        books = service.search_book(
            request.query,
            available_only=request.available_only,
            limit=request.limit,
        )
    except ClassroomActionError as exc:
        _error(exc)
    return LibrarySearchResponse(books=books)


@router.get("/inventory/{book_id}")
def inventory(
    book_id: uuid.UUID,
    service: LibraryActionService = Depends(get_library_service),
) -> dict:
    try:
        return service.check_book_inventory(book_id)
    except ClassroomActionError as exc:
        _error(exc)


@router.get("/recommend", response_model=LibrarySearchResponse)
def recommend(
    query: str,
    limit: int = 5,
    service: LibraryActionService = Depends(get_library_service),
) -> LibrarySearchResponse:
    try:
        books = service.recommend_books(query, limit=max(1, min(limit, 20)))
    except ClassroomActionError as exc:
        _error(exc)
    return LibrarySearchResponse(books=books)


@router.get("/borrowed", response_model=LibraryBorrowedListResponse)
def borrowed(
    actor_user_id: uuid.UUID,
    service: LibraryActionService = Depends(get_library_service),
    authorization: AuthorizationService = Depends(get_authorization_service),
) -> LibraryBorrowedListResponse:
    _authorize(authorization, "library.self.read", actor_user_id)
    try:
        values = service.get_borrowed_books(actor_user_id)
    except ClassroomActionError as exc:
        _error(exc)
    return LibraryBorrowedListResponse(actor_user_id=str(actor_user_id), borrowed_books=values)


@router.post("/prepare", response_model=LibraryPrepareResponse)
def prepare(
    request: LibraryPrepareRequest,
    service: LibraryActionService = Depends(get_library_service),
    authorization: AuthorizationService = Depends(get_authorization_service),
) -> LibraryPrepareResponse:
    _authorize(authorization, "library.reserve", request.actor_user_id)
    try:
        result = service.prepare_reservation(
            request.query,
            request.actor_user_id,
            trace_id=request.trace_id,
        )
    except ClassroomActionError as exc:
        _error(exc)
    return LibraryPrepareResponse(
        approval_id=result.approval_id,
        trace_id=result.trace_id,
        actor_user_id=result.actor_user_id,
        status=result.status.value,
        answer=result.answer,
        requested=result.requested.model_dump(mode="json"),
        candidates=[item.model_dump(mode="json") for item in result.candidates],
        expires_at=result.expires_at,
        audit=result.audit,
    )


@router.post("/resume", response_model=LibraryActionResponse)
def resume(
    request: LibraryResumeRequest,
    service: LibraryActionService = Depends(get_library_service),
    authorization: AuthorizationService = Depends(get_authorization_service),
) -> LibraryActionResponse:
    _authorize(authorization, "library.reserve", request.actor_user_id)
    try:
        result = service.resume_reservation(
            request.approval_id,
            request.actor_user_id,
            approved=request.approved,
            book_id=request.book_id,
        )
    except ClassroomActionError as exc:
        _error(exc)
    return LibraryActionResponse(
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


@router.get("/reservations", response_model=LibraryReservationListResponse)
def reservations(
    actor_user_id: uuid.UUID,
    service: LibraryActionService = Depends(get_library_service),
    authorization: AuthorizationService = Depends(get_authorization_service),
) -> LibraryReservationListResponse:
    _authorize(authorization, "library.self.read", actor_user_id)
    try:
        values = service.list_reservations(actor_user_id)
    except ClassroomActionError as exc:
        _error(exc)
    return LibraryReservationListResponse(actor_user_id=str(actor_user_id), reservations=values)
