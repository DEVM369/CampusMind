from __future__ import annotations

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    Response,
    status,
)
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from campusmind.api.dependencies import (
    current_authenticated_user,
)
from campusmind.config import get_settings
from campusmind.platform.auth import (
    AuthService,
    AuthenticationError,
)
from campusmind.platform.db import (
    User,
    get_db,
)


router = APIRouter()


class AuthLoginRequest(BaseModel):
    username: str = Field(
        min_length=1,
        max_length=64,
    )

    password: str = Field(
        min_length=8,
        max_length=256,
    )


class AuthUserResponse(BaseModel):
    user_id: str
    username: str
    full_name: str
    status: str
    is_superuser: bool
    roles: list[str]


class AuthLoginResponse(BaseModel):
    status: str = "ok"
    user: AuthUserResponse


class AuthStatusResponse(BaseModel):
    status: str = "ok"


def _user_response(
    service: AuthService,
    user: User,
) -> AuthUserResponse:
    return AuthUserResponse(
        user_id=str(
            user.id
        ),
        username=user.username,
        full_name=user.full_name,
        status=user.status,
        is_superuser=bool(
            user.is_superuser
        ),
        roles=service.role_codes(
            user.id
        ),
    )


@router.post(
    "/login",
    response_model=AuthLoginResponse,
)
def login(
    payload: AuthLoginRequest,
    response: Response,
    db: Session = Depends(
        get_db
    ),
) -> AuthLoginResponse:
    service = AuthService(
        db
    )

    try:
        user = service.authenticate(
            payload.username,
            payload.password,
        )
    except AuthenticationError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=(
                "Invalid username or password"
            ),
        ) from None

    raw_token, session_row = (
        service.create_session(
            user.id
        )
    )

    settings = get_settings()

    response.set_cookie(
        key=settings.auth_cookie_name,
        value=raw_token,
        max_age=(
            settings.auth_session_ttl_hours
            * 3600
        ),
        path="/",
        secure=settings.auth_cookie_secure,
        httponly=True,
        samesite="strict",
    )

    return AuthLoginResponse(
        user=_user_response(
            service,
            user,
        )
    )


@router.get(
    "/me",
    response_model=AuthUserResponse,
)
def me(
    user: User = Depends(
        current_authenticated_user
    ),
    db: Session = Depends(
        get_db
    ),
) -> AuthUserResponse:
    return _user_response(
        AuthService(
            db
        ),
        user,
    )


@router.post(
    "/logout",
    response_model=AuthStatusResponse,
)
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(
        get_db
    ),
) -> AuthStatusResponse:
    settings = get_settings()

    raw_token = request.cookies.get(
        settings.auth_cookie_name
    )

    AuthService(
        db
    ).revoke_session(
        raw_token
    )

    response.delete_cookie(
        key=settings.auth_cookie_name,
        path="/",
        secure=settings.auth_cookie_secure,
        httponly=True,
        samesite="strict",
    )

    return AuthStatusResponse()
