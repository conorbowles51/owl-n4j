from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from postgres.models.case import Case
from postgres.models.chat import CaseRevision, ChatConversation, ChatMessage
from postgres.models.cost_record import CostRecord
from postgres.models.user import User
from models.llm_models import get_model_by_id
from services.case_service import CaseAccessDenied, CaseNotFound, check_case_access


DEFAULT_CONVERSATION_STATUS = "active"


def summarize_title(question: str) -> str:
    cleaned = " ".join((question or "").split())
    if not cleaned:
        return "New conversation"
    return cleaned[:80]


def _message_timestamp(message: dict[str, Any]) -> datetime | None:
    value = message.get("timestamp")
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed
    except ValueError:
        return None


def require_case_access(db: Session, user: User, case_id: UUID) -> Case:
    case, _ = check_case_access(db, case_id, user, required_permission=("case", "view"))
    return case


def create_case_revision(
    db: Session,
    case_id: UUID,
    user_id: UUID | None,
    extra_metadata: dict[str, Any] | None = None,
    source: str = "chat_turn",
) -> CaseRevision:
    current_max = (
        db.query(func.max(CaseRevision.revision_number))
        .filter(CaseRevision.case_id == case_id)
        .scalar()
    ) or 0

    revision = CaseRevision(
        case_id=case_id,
        revision_number=current_max + 1,
        source=source,
        extra_metadata=extra_metadata or {},
        created_by_user_id=user_id,
    )
    db.add(revision)
    db.flush()
    return revision


def get_latest_case_revision(db: Session, case_id: UUID) -> CaseRevision | None:
    return (
        db.query(CaseRevision)
        .filter(CaseRevision.case_id == case_id)
        .order_by(CaseRevision.revision_number.desc())
        .first()
    )


def list_conversations_for_user(
    db: Session,
    user: User,
    case_id: UUID | None = None,
) -> list[ChatConversation]:
    query = (
        db.query(ChatConversation)
        .options(joinedload(ChatConversation.messages), joinedload(ChatConversation.owner))
        .filter(ChatConversation.owner_user_id == user.id)
        .order_by(ChatConversation.last_message_at.desc(), ChatConversation.created_at.desc())
    )
    if case_id:
        require_case_access(db, user, case_id)
        query = query.filter(ChatConversation.case_id == case_id)
    return query.all()


def get_conversation_for_user(
    db: Session,
    conversation_id: UUID,
    user: User,
    case_id: UUID | None = None,
) -> ChatConversation:
    conversation = (
        db.query(ChatConversation)
        .options(
            joinedload(ChatConversation.owner),
            joinedload(ChatConversation.messages).joinedload(ChatMessage.cost_record),
            joinedload(ChatConversation.messages).joinedload(ChatMessage.case_revision),
        )
        .filter(
            ChatConversation.id == conversation_id,
            ChatConversation.owner_user_id == user.id,
        )
        .first()
    )
    if not conversation:
        raise CaseNotFound(f"Conversation {conversation_id} not found")

    require_case_access(db, user, conversation.case_id)

    if case_id and conversation.case_id != case_id:
        raise CaseAccessDenied(f"Conversation {conversation_id} does not belong to case {case_id}")

    return conversation


def create_conversation(
    db: Session,
    user: User,
    case_id: UUID,
    title: str,
) -> ChatConversation:
    require_case_access(db, user, case_id)
    conversation = ChatConversation(
        case_id=case_id,
        owner_user_id=user.id,
        title=title or "New conversation",
        status=DEFAULT_CONVERSATION_STATUS,
    )
    db.add(conversation)
    db.flush()
    return conversation


def rename_conversation(
    db: Session,
    conversation: ChatConversation,
    title: str,
) -> ChatConversation:
    conversation.title = title.strip() or conversation.title
    db.flush()
    return conversation


def conversation_prompt_history(
    conversation: ChatConversation,
    max_messages: int = 12,
) -> list[dict[str, str]]:
    history = [
        {"role": message.role, "content": message.content}
        for message in sorted(conversation.messages, key=lambda item: item.sequence_number)[-max_messages:]
    ]
    return history


def append_conversation_turn(
    db: Session,
    conversation: ChatConversation,
    revision: CaseRevision | None,
    user_question: str,
    assistant_answer: str,
    context_scope: str,
    selected_entity_keys: list[str] | None,
    sources: list[dict[str, Any]] | None,
    provider: str,
    model_id: str,
    result_graph: dict[str, Any] | None,
    cost_record: CostRecord | None,
    snapshot_id: str | None = None,
) -> tuple[ChatMessage, ChatMessage]:
    next_sequence = (
        db.query(func.max(ChatMessage.sequence_number))
        .filter(ChatMessage.conversation_id == conversation.id)
        .scalar()
    ) or 0

    revision_id = revision.id if revision else None
    selected_keys_payload = selected_entity_keys or None

    user_message = ChatMessage(
        conversation_id=conversation.id,
        sequence_number=next_sequence + 1,
        role="user",
        content=user_question,
        context_scope=context_scope,
        selected_entity_keys=selected_keys_payload,
        case_revision_id=revision_id,
        snapshot_id=snapshot_id,
    )
    assistant_message = ChatMessage(
        conversation_id=conversation.id,
        sequence_number=next_sequence + 2,
        role="assistant",
        content=assistant_answer,
        context_scope=context_scope,
        selected_entity_keys=selected_keys_payload,
        source_payload=sources or None,
        model_provider=provider,
        model_id=model_id,
        cost_record_id=cost_record.id if cost_record else None,
        result_graph_json=result_graph or None,
        case_revision_id=revision_id,
        snapshot_id=snapshot_id,
    )
    db.add(user_message)
    db.add(assistant_message)

    now = datetime.now(timezone.utc)
    conversation.last_message_at = now
    conversation.updated_at = now
    if not conversation.title or conversation.title == "New conversation":
        conversation.title = summarize_title(user_question)

    db.flush()
    return user_message, assistant_message


def replace_conversation_messages(
    db: Session,
    conversation: ChatConversation,
    messages: Iterable[dict[str, Any]],
    revision: CaseRevision | None = None,
) -> ChatConversation:
    db.query(ChatMessage).filter(ChatMessage.conversation_id == conversation.id).delete()

    revision_id = revision.id if revision else None
    latest_seen = conversation.created_at
    for index, message in enumerate(messages, start=1):
        stored = ChatMessage(
            conversation_id=conversation.id,
            sequence_number=index,
            role=message.get("role", "assistant"),
            content=message.get("content", ""),
            context_scope=message.get("scope"),
            selected_entity_keys=message.get("selected_entity_keys"),
            source_payload=message.get("sources"),
            model_provider=(message.get("model_info") or {}).get("provider"),
            model_id=(message.get("model_info") or {}).get("model_id"),
            result_graph_json=message.get("resultGraph"),
            case_revision_id=revision_id,
            snapshot_id=(message.get("provenance") or {}).get("snapshot_id"),
            created_at=_message_timestamp(message) or datetime.now(timezone.utc),
        )
        latest_seen = max(latest_seen, stored.created_at)
        db.add(stored)

    conversation.last_message_at = latest_seen
    conversation.updated_at = datetime.now(timezone.utc)
    db.flush()
    return conversation


def delete_conversation(db: Session, conversation: ChatConversation) -> None:
    db.delete(conversation)
    db.flush()


def build_cost_payload(cost_record: CostRecord | None) -> dict[str, Any] | None:
    if not cost_record:
        return None
    return {
        "usd": float(cost_record.cost_usd or 0.0),
        "prompt_tokens": cost_record.prompt_tokens,
        "completion_tokens": cost_record.completion_tokens,
        "total_tokens": cost_record.total_tokens,
        "cost_record_id": str(cost_record.id),
    }


def build_message_payload(message: ChatMessage, case_id: UUID) -> dict[str, Any]:
    model = get_model_by_id(message.model_id) if message.model_id else None
    provenance = {
        "case_id": str(case_id),
        "case_revision_id": str(message.case_revision_id) if message.case_revision_id else None,
        "snapshot_id": message.snapshot_id,
    }
    return {
        "id": str(message.id),
        "role": message.role,
        "content": message.content,
        "scope": message.context_scope,
        "selected_entity_keys": message.selected_entity_keys or [],
        "sources": message.source_payload or [],
        "cost": build_cost_payload(message.cost_record),
        "timestamp": message.created_at.isoformat(),
        "model_info": (
            {
                "provider": message.model_provider,
                "model_id": message.model_id,
                "model_name": model.name if model else (message.model_id or ""),
                "server": "Ollama (local)" if message.model_provider == "ollama" else "OpenAI (remote)",
            }
            if message.model_provider or message.model_id
            else None
        ),
        "resultGraph": message.result_graph_json,
        "provenance": provenance,
    }


def build_conversation_payload(conversation: ChatConversation) -> dict[str, Any]:
    ordered_messages = sorted(conversation.messages, key=lambda item: item.sequence_number)
    latest_snapshot_id = next(
        (message.snapshot_id for message in reversed(ordered_messages) if message.snapshot_id),
        None,
    )
    latest_revision_id = next(
        (str(message.case_revision_id) for message in reversed(ordered_messages) if message.case_revision_id),
        None,
    )
    return {
        "id": str(conversation.id),
        "name": conversation.title,
        "messages": [build_message_payload(message, conversation.case_id) for message in ordered_messages],
        "timestamp": conversation.updated_at.isoformat(),
        "created_at": conversation.created_at.isoformat(),
        "updated_at": conversation.updated_at.isoformat(),
        "last_message_at": conversation.last_message_at.isoformat(),
        "owner": conversation.owner.email if conversation.owner else None,
        "owner_user_id": str(conversation.owner_user_id),
        "case_id": str(conversation.case_id),
        "snapshot_id": latest_snapshot_id,
        "case_revision_id": latest_revision_id,
        "message_count": len(ordered_messages),
    }


def build_conversation_summary_payload(conversation: ChatConversation) -> dict[str, Any]:
    return {
        "id": str(conversation.id),
        "name": conversation.title,
        "timestamp": conversation.updated_at.isoformat(),
        "created_at": conversation.created_at.isoformat(),
        "updated_at": conversation.updated_at.isoformat(),
        "last_message_at": conversation.last_message_at.isoformat(),
        "owner_user_id": str(conversation.owner_user_id),
        "case_id": str(conversation.case_id),
        "message_count": len(conversation.messages),
    }
