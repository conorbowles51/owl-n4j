"""
Chat History Router

Postgres-backed saved conversations.
"""

from __future__ import annotations

from typing import Any, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, joinedload

from postgres.models.chat import ChatConversation, ChatMessage
from postgres.models.user import User
from postgres.session import get_db
from routers.users import get_current_db_user
from services.chat_db_service import (
    build_conversation_payload,
    build_conversation_summary_payload,
    create_case_revision,
    create_conversation,
    delete_conversation,
    get_conversation_for_user,
    list_conversations_for_user,
    rename_conversation,
    replace_conversation_messages,
    require_case_access,
)
from services.case_service import CaseAccessDenied, CaseNotFound

router = APIRouter(prefix="/api/chat-history", tags=["chat-history"])


class ChatHistoryCreate(BaseModel):
    name: Optional[str] = None
    messages: List[dict[str, Any]] = Field(default_factory=list)
    snapshot_id: Optional[str] = None
    case_id: UUID


class ChatHistoryUpdate(BaseModel):
    name: Optional[str] = None
    messages: Optional[List[dict[str, Any]]] = None


class ChatHistoryResponse(BaseModel):
    id: str
    name: str
    messages: List[dict[str, Any]]
    timestamp: str
    created_at: str
    updated_at: str
    last_message_at: str
    owner: Optional[str] = None
    owner_user_id: str
    snapshot_id: Optional[str] = None
    case_id: str
    case_revision_id: Optional[str] = None
    message_count: int


class ChatHistorySummary(BaseModel):
    id: str
    name: str
    timestamp: str
    created_at: str
    updated_at: str
    last_message_at: str
    owner_user_id: str
    case_id: str
    message_count: int


def _to_response(conversation: ChatConversation) -> ChatHistoryResponse:
    return ChatHistoryResponse(**build_conversation_payload(conversation))


def _to_summary(conversation: ChatConversation) -> ChatHistorySummary:
    return ChatHistorySummary(**build_conversation_summary_payload(conversation))


@router.post("", response_model=ChatHistoryResponse)
async def create_chat_history(
    chat: ChatHistoryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    require_case_access(db, current_user, chat.case_id)

    conversation = create_conversation(
        db=db,
        user=current_user,
        case_id=chat.case_id,
        title=chat.name or "New conversation",
    )
    if chat.messages:
        revision = create_case_revision(
            db=db,
            case_id=chat.case_id,
            user_id=current_user.id,
            extra_metadata={"source": "chat_history_import"},
            source="chat_history_import",
        )
        replace_conversation_messages(db, conversation, chat.messages, revision=revision)

    db.commit()
    db.refresh(conversation)
    conversation = get_conversation_for_user(db, conversation.id, current_user, case_id=chat.case_id)
    return _to_response(conversation)


@router.get("", response_model=List[ChatHistorySummary])
async def list_chat_histories(
    case_id: Optional[UUID] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    conversations = list_conversations_for_user(db, current_user, case_id=case_id)
    return [_to_summary(conversation) for conversation in conversations]


@router.get("/by-snapshot/{snapshot_id}", response_model=List[ChatHistoryResponse])
async def get_chat_histories_by_snapshot(
    snapshot_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    conversations = (
        db.query(ChatConversation)
        .join(ChatMessage, ChatMessage.conversation_id == ChatConversation.id)
        .options(
            joinedload(ChatConversation.messages).joinedload(ChatMessage.cost_record),
            joinedload(ChatConversation.messages).joinedload(ChatMessage.case_revision),
        )
        .filter(
            ChatConversation.owner_user_id == current_user.id,
            ChatMessage.snapshot_id == snapshot_id,
        )
        .order_by(ChatConversation.last_message_at.desc())
        .all()
    )

    visible: list[ChatConversation] = []
    for conversation in conversations:
        try:
            require_case_access(db, current_user, conversation.case_id)
        except (CaseAccessDenied, CaseNotFound):
            continue
        visible.append(conversation)

    return [_to_response(conversation) for conversation in visible]


@router.get("/{chat_id}", response_model=ChatHistoryResponse)
async def get_chat_history(
    chat_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    try:
        conversation = get_conversation_for_user(db, chat_id, current_user)
    except (CaseNotFound, CaseAccessDenied) as exc:
        raise HTTPException(status_code=404, detail="Chat history not found") from exc
    return _to_response(conversation)


@router.put("/{chat_id}", response_model=ChatHistoryResponse)
async def update_chat_history(
    chat_id: UUID,
    update: ChatHistoryUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    try:
        conversation = get_conversation_for_user(db, chat_id, current_user)
    except (CaseNotFound, CaseAccessDenied) as exc:
        raise HTTPException(status_code=404, detail="Chat history not found") from exc

    if update.name is not None:
        rename_conversation(db, conversation, update.name)

    if update.messages is not None:
        revision = create_case_revision(
            db=db,
            case_id=conversation.case_id,
            user_id=current_user.id,
            extra_metadata={"source": "chat_history_replace"},
            source="chat_history_replace",
        )
        replace_conversation_messages(db, conversation, update.messages, revision=revision)

    db.commit()
    conversation = get_conversation_for_user(db, chat_id, current_user)
    return _to_response(conversation)


@router.delete("/{chat_id}")
async def delete_chat_history(
    chat_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    try:
        conversation = get_conversation_for_user(db, chat_id, current_user)
    except (CaseNotFound, CaseAccessDenied) as exc:
        raise HTTPException(status_code=404, detail="Chat history not found") from exc

    delete_conversation(db, conversation)
    db.commit()
    return {"status": "deleted", "id": str(chat_id)}
