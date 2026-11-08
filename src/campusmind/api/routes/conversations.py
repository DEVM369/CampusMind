from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID
from typing import Any, Literal

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Response,
    status,
)
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from campusmind.api.dependencies import (
    current_authenticated_user,
)
from campusmind.api.routes import adaptive_rag
from campusmind.api.schemas import (
    AdaptiveChatResponse,
)
from campusmind.knowledge.adaptive import (
    AdaptiveRagService,
)
from campusmind.platform.db import (
    Conversation,
    Message,
    User,
    get_db,
)


router = APIRouter()


class ConversationCreateRequest(BaseModel):
    title: str | None = Field(
        default=None,
        max_length=255,
    )


class ConversationChatRequest(BaseModel):
    query: str = Field(
        min_length=1,
        max_length=4000,
    )

    top_k: int = Field(
        default=5,
        ge=1,
        le=20,
    )

    max_paths: int = Field(
        default=5,
        ge=1,
        le=20,
    )


class ConversationSummaryResponse(BaseModel):
    id: UUID
    title: str | None
    status: str
    created_at: datetime
    updated_at: datetime


class ConversationMessageResponse(BaseModel):
    id: UUID
    role: str
    content: str
    citations: list
    metadata_json: dict
    created_at: datetime


class ConversationDetailResponse(
    ConversationSummaryResponse
):
    messages: list[
        ConversationMessageResponse
    ]


class ConversationMessageWrite(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(
        min_length=1,
        max_length=20000,
    )
    citations: list[Any] = Field(
        default_factory=list
    )
    metadata_json: dict[str, Any] = Field(
        default_factory=dict
    )


class ConversationMessagesAppendRequest(BaseModel):
    messages: list[
        ConversationMessageWrite
    ] = Field(
        min_length=1,
        max_length=4,
    )


class ConversationAppendResponse(BaseModel):
    status: str = "ok"
    appended: int


def _owned_conversation(
    db: Session,
    user: User,
    conversation_id: UUID,
) -> Conversation:
    conversation = db.scalar(
        select(
            Conversation
        ).where(
            Conversation.id
            == conversation_id,
            Conversation.user_id
            == user.id,
        )
    )

    if conversation is None:
        # Deliberately return 404 rather than revealing
        # whether another user's conversation exists.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    return conversation


def _summary(
    row: Conversation,
) -> ConversationSummaryResponse:
    return ConversationSummaryResponse(
        id=row.id,
        title=row.title,
        status=row.status,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get(
    "",
    response_model=list[
        ConversationSummaryResponse
    ],
)
def list_conversations(
    user: User = Depends(
        current_authenticated_user
    ),
    db: Session = Depends(
        get_db
    ),
) -> list[
    ConversationSummaryResponse
]:
    rows = db.scalars(
        select(
            Conversation
        )
        .where(
            Conversation.user_id
            == user.id
        )
        .order_by(
            Conversation.updated_at.desc(),
            Conversation.created_at.desc(),
        )
    ).all()

    return [
        _summary(row)
        for row in rows
    ]


@router.post(
    "",
    response_model=ConversationSummaryResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_conversation(
    payload: ConversationCreateRequest,
    user: User = Depends(
        current_authenticated_user
    ),
    db: Session = Depends(
        get_db
    ),
) -> ConversationSummaryResponse:
    title = (
        payload.title.strip()
        if payload.title
        else None
    )

    row = Conversation(
        user_id=user.id,
        title=title or "\u65b0\u5bf9\u8bdd",
        status="active",
    )

    db.add(row)
    db.commit()
    db.refresh(row)

    return _summary(row)


@router.get(
    "/{conversation_id}",
    response_model=ConversationDetailResponse,
)
def get_conversation(
    conversation_id: UUID,
    user: User = Depends(
        current_authenticated_user
    ),
    db: Session = Depends(
        get_db
    ),
) -> ConversationDetailResponse:
    row = _owned_conversation(
        db,
        user,
        conversation_id,
    )

    messages = db.scalars(
        select(
            Message
        )
        .where(
            Message.conversation_id
            == row.id
        )
        .order_by(
            Message.created_at.asc(),
            Message.id.asc(),
        )
    ).all()

    return ConversationDetailResponse(
        **_summary(
            row
        ).model_dump(),
        messages=[
            ConversationMessageResponse(
                id=message.id,
                role=message.role,
                content=message.content,
                citations=(
                    message.citations
                    or []
                ),
                metadata_json=(
                    message.metadata_json
                    or {}
                ),
                created_at=(
                    message.created_at
                ),
            )
            for message in messages
        ],
    )


@router.post(
    "/{conversation_id}/messages",
    response_model=ConversationAppendResponse,
    status_code=status.HTTP_201_CREATED,
)
def append_conversation_messages(
    conversation_id: UUID,
    payload: ConversationMessagesAppendRequest,
    user: User = Depends(
        current_authenticated_user
    ),
    db: Session = Depends(
        get_db
    ),
) -> ConversationAppendResponse:
    conversation = _owned_conversation(
        db,
        user,
        conversation_id,
    )

    first_user_content = None

    for item in payload.messages:
        if (
            first_user_content is None
            and item.role == "user"
        ):
            first_user_content = (
                item.content
            )

        db.add(
            Message(
                conversation_id=conversation.id,
                role=item.role,
                content=item.content,
                citations=item.citations,
                metadata_json=(
                    item.metadata_json
                ),
            )
        )

    current_title = (
        conversation.title
        or ""
    ).strip()

    if (
        first_user_content
        and (
            not current_title
            or current_title
            in {
                "\u65b0\u5bf9\u8bdd",
                "\u65b0\u4f1a\u8bdd",
            }
        )
    ):
        normalized = " ".join(
            first_user_content.split()
        )

        conversation.title = (
            normalized[:80]
            or "\u65b0\u5bf9\u8bdd"
        )

    conversation.updated_at = (
        datetime.now(
            timezone.utc
        )
    )

    db.commit()

    return ConversationAppendResponse(
        appended=len(
            payload.messages
        )
    )


@router.delete(
    "/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_conversation(
    conversation_id: UUID,
    user: User = Depends(
        current_authenticated_user
    ),
    db: Session = Depends(
        get_db
    ),
) -> Response:
    row = _owned_conversation(
        db,
        user,
        conversation_id,
    )

    db.delete(row)
    db.commit()

    return Response(
        status_code=status.HTTP_204_NO_CONTENT
    )


@router.post(
    "/{conversation_id}/chat",
    response_model=AdaptiveChatResponse,
)
def conversation_chat(
    conversation_id: UUID,
    payload: ConversationChatRequest,
    user: User = Depends(
        current_authenticated_user
    ),
    db: Session = Depends(
        get_db
    ),
    service: AdaptiveRagService = Depends(
        adaptive_rag.get_adaptive_rag_service
    ),
) -> AdaptiveChatResponse:
    conversation = _owned_conversation(
        db,
        user,
        conversation_id,
    )

    # Identity is derived exclusively from the
    # authenticated server-side session.
    answer = adaptive_rag._chat_response(
        service.answer(
            payload.query,
            top_k=payload.top_k,
            max_paths=payload.max_paths,
            actor_user_id=user.id,
        )
    )

    user_message = Message(
        conversation_id=conversation.id,
        role="user",
        content=payload.query,
        citations=[],
        metadata_json={
            "mode": "smart",
        },
    )

    assistant_message = Message(
        conversation_id=conversation.id,
        role="assistant",
        content=answer.answer,
        citations=[
            item.model_dump(
                mode="json"
            )
            for item
            in answer.citations
        ],
        metadata_json={
            "trace_id":
                answer.trace_id,
            "mode":
                "smart",
            "result":
                answer.model_dump(
                    mode="json"
                ),
        },
    )

    now = datetime.now(
        timezone.utc
    )

    conversation.updated_at = now

    current_title = (
        conversation.title
        or ""
    ).strip()

    if (
        not current_title
        or current_title
        == "\u65b0\u5bf9\u8bdd"
    ):
        normalized = " ".join(
            payload.query.split()
        )

        conversation.title = (
            normalized[:80]
            or "\u65b0\u5bf9\u8bdd"
        )

    db.add(
        user_message
    )

    db.add(
        assistant_message
    )

    db.commit()

    return answer
