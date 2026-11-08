from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from campusmind.config import get_settings
from campusmind.platform.auth import AuthService
from campusmind.platform.db import User, get_db
from campusmind.platform.security import (
    AuthorizationDenied,
    AuthorizationService,
    KnowledgeAclService,
    bind_acl_context,
)


async def public_knowledge_scope() -> AsyncGenerator[None, None]:
    """Force legacy raw retrieval HTTP endpoints to anonymous/public scope."""

    with bind_acl_context(
        permission_levels=["public"],
        actor_user_id=None,
    ):
        yield


def current_authenticated_user(
    request: Request,
    db: Session = Depends(
        get_db
    ),
) -> User:
    settings = get_settings()

    token = request.cookies.get(
        settings.auth_cookie_name
    )

    user = AuthService(
        db
    ).resolve_session(
        token
    )

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    return user


async def trusted_actor(
    request: Request,
    user: User = Depends(current_authenticated_user),
) -> UUID:
    """Validate legacy actor assertions against the authenticated session."""
    assertions = request.query_params.getlist("actor_user_id")
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if (not content_type and request.method in {"POST", "PUT", "PATCH"}) or (
        content_type == "application/json"
        or (content_type.startswith("application/") and content_type.endswith("+json"))
    ):
        try:
            body = await request.body()
            payload = json.loads(body) if body else {}
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise HTTPException(status_code=422, detail="Invalid JSON body") from None
        if isinstance(payload, dict) and payload.get("actor_user_id") is not None:
            assertions.append(payload["actor_user_id"])
    elif content_type in {"multipart/form-data", "application/x-www-form-urlencoded"}:
        form = await request.form()
        assertions.extend(form.getlist("actor_user_id"))
    for value in assertions:
        try:
            asserted = UUID(str(value))
        except (ValueError, TypeError, AttributeError):
            raise HTTPException(status_code=422, detail="Invalid actor_user_id") from None
        if asserted != user.id:
            raise HTTPException(status_code=403, detail="actor_user_id does not match session")
    return user.id


async def authenticated_knowledge_scope(
    actor: UUID = Depends(trusted_actor),
    db: Session = Depends(get_db),
) -> AsyncGenerator[None, None]:
    acl = KnowledgeAclService(db)
    with acl.bind_context(actor):
        # Authentication has already opened the shared request transaction.
        if db.get_bind().dialect.name == "postgresql":
            acl.apply_to_session(actor)
        yield


def require_capability(capability: str):
    def dependency(
        actor: UUID = Depends(trusted_actor),
        db: Session = Depends(get_db),
    ) -> UUID:
        try:
            AuthorizationService(db).require(capability, actor)
        except AuthorizationDenied as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        return actor

    return dependency
