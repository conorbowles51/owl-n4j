"""
Chat Router - endpoints for AI question answering.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from models.llm_models import get_model_by_id
from postgres.models.user import User
from postgres.session import get_db
from routers.users import get_current_db_user
from services.chat_db_service import (
    append_conversation_turn,
    build_cost_payload,
    conversation_prompt_history,
    create_case_revision,
    create_conversation,
    get_conversation_for_user,
    get_latest_case_revision,
    require_case_access,
    summarize_title,
)
from services.cost_tracking_service import CostJobType, record_cost
from services.rag_service import rag_service
from services.system_log_service import LogOrigin, LogType, system_log_service
from utils.prompt_trace import log_section, start_trace

backend_dir = Path(__file__).parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))


router = APIRouter(prefix="/api/chat", tags=["chat"])


class ChatRequest(BaseModel):
    question: str
    case_id: UUID
    conversation_id: Optional[UUID] = None
    scope: Literal["case_overview", "selection"] = "case_overview"
    selected_entity_keys: Optional[List[str]] = None
    provider: str = "openai"
    model: str = "gpt-4o"
    confidence_threshold: Optional[float] = None
    persist: bool = False


class ChatSource(BaseModel):
    filename: str
    excerpt: Optional[str] = None
    page: Optional[int] = None


class ChatCost(BaseModel):
    usd: float
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    cost_record_id: Optional[str] = None


class ChatModelInfo(BaseModel):
    provider: str
    model_id: str
    model_name: str
    server: str


class ChatProvenance(BaseModel):
    case_id: str
    case_revision_id: Optional[str] = None
    snapshot_id: Optional[str] = None


class ChatSuggestion(BaseModel):
    question: str


class ChatResponse(BaseModel):
    conversation_id: Optional[str] = None
    message_id: str
    answer: str
    sources: List[ChatSource] = Field(default_factory=list)
    cost: Optional[ChatCost] = None
    model_info: ChatModelInfo
    result_graph: Optional[Dict[str, Any]] = None
    provenance: ChatProvenance
    suggestions: List[ChatSuggestion] = Field(default_factory=list)
    context_mode: str
    context_description: str
    cypher_used: bool
    debug_log: Optional[Dict[str, Any]] = None
    used_node_keys: Optional[List[str]] = None
    document_summary: Optional[str] = None


class SuggestionsRequest(BaseModel):
    case_id: UUID
    selected_entity_keys: Optional[List[str]] = None


class SuggestionsResponse(BaseModel):
    suggestions: List[ChatSuggestion]


class ExtractNodesRequest(BaseModel):
    answer: str


class ExtractNodesResponse(BaseModel):
    node_keys: List[str]


@router.post("", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    if not request.question or not request.question.strip():
        raise HTTPException(status_code=400, detail="Question is required")

    require_case_access(db, current_user, request.case_id)

    question = request.question.strip()
    selected_entity_keys = list(dict.fromkeys(request.selected_entity_keys or []))
    if request.scope == "selection" and not selected_entity_keys:
        selected_entity_keys = []

    conversation = None
    conversation_history: list[dict[str, str]] = []
    if request.conversation_id:
        conversation = get_conversation_for_user(
            db=db,
            conversation_id=request.conversation_id,
            user=current_user,
            case_id=request.case_id,
        )
        conversation_history = conversation_prompt_history(conversation)
    elif request.persist:
        conversation = create_conversation(
            db=db,
            user=current_user,
            case_id=request.case_id,
            title=summarize_title(question),
        )

    provider = request.provider.lower()
    model_id = request.model
    model = get_model_by_id(model_id)
    if not model:
        raise HTTPException(status_code=400, detail=f"Invalid model: {model_id}")

    llm = rag_service.llm.create_context(provider=provider, model_id=model_id)

    trace_cm = start_trace(
        meta={
            "endpoint": "/api/chat",
            "user": current_user.email,
            "provider": llm.provider,
            "model": llm.model_id,
            "question": question,
            "case_id": str(request.case_id),
            "scope": request.scope,
            "conversation_id": str(conversation.id) if conversation else None,
        }
    )
    trace_cm.__enter__()

    assistant_message_id = str(uuid.uuid4())
    persisted_revision = get_latest_case_revision(db, request.case_id)

    try:
        log_section(
            source_file=__file__,
            source_func="chat",
            title="Incoming request",
            content={
                "question": question,
                "scope": request.scope,
                "selected_entity_keys": selected_entity_keys,
                "provider": llm.provider,
                "model": llm.model_id,
                "persist": request.persist,
                "conversation_id": str(conversation.id) if conversation else None,
            },
            as_json=True,
        )

        system_log_service.log(
            log_type=LogType.AI_ASSISTANT,
            origin=LogOrigin.FRONTEND,
            action=f"AI Assistant Query: {question[:100]}",
            details={
                "question": question,
                "scope": request.scope,
                "selected_entity_keys": selected_entity_keys,
                "case_id": str(request.case_id),
            },
            user=current_user.email,
            success=True,
        )

        result = rag_service.answer_question(
            question=question,
            selected_keys=selected_entity_keys or None,
            confidence_threshold=request.confidence_threshold,
            case_id=str(request.case_id),
            conversation_history=conversation_history or None,
            llm_context=llm,
        )

        cost_record = None
        if llm.provider == "openai" and llm.last_usage:
            cost_record = record_cost(
                job_type=CostJobType.AI_ASSISTANT,
                provider=llm.provider,
                model_id=llm.model_id,
                prompt_tokens=llm.last_usage.get("prompt_tokens"),
                completion_tokens=llm.last_usage.get("completion_tokens"),
                total_tokens=llm.last_usage.get("total_tokens"),
                case_id=request.case_id,
                user_id=current_user.id,
                description=f"AI Assistant Query: {question[:100]}",
                extra_metadata={
                    "question": question,
                    "scope": request.scope,
                    "selected_entity_keys": selected_entity_keys,
                    "conversation_id": str(conversation.id) if conversation else None,
                },
                db=db,
            )

        if request.persist and conversation is not None:
            persisted_revision = create_case_revision(
                db=db,
                case_id=request.case_id,
                user_id=current_user.id,
                extra_metadata={
                    "scope": request.scope,
                    "selected_entity_keys": selected_entity_keys,
                    "conversation_id": str(conversation.id),
                },
            )
            _, assistant_message = append_conversation_turn(
                db=db,
                conversation=conversation,
                revision=persisted_revision,
                user_question=question,
                assistant_answer=result["answer"],
                context_scope=request.scope,
                selected_entity_keys=selected_entity_keys,
                sources=result.get("sources"),
                provider=llm.provider,
                model_id=llm.model_id,
                result_graph=result.get("result_graph"),
                cost_record=cost_record,
            )
            assistant_message_id = str(assistant_message.id)
            db.commit()
            db.refresh(conversation)
        else:
            db.commit()

        server = "Ollama (local)" if llm.provider == "ollama" else "OpenAI (remote)"
        model_info = ChatModelInfo(
            provider=llm.provider,
            model_id=llm.model_id,
            model_name=model.name,
            server=server,
        )
        suggestions = [
            ChatSuggestion(question=question_text)
            for question_text in rag_service.get_suggested_questions(
                str(request.case_id),
                selected_entity_keys or None,
            )
        ]

        system_log_service.log(
            log_type=LogType.AI_ASSISTANT,
            origin=LogOrigin.BACKEND,
            action="AI Assistant Response",
            details={
                "question": question,
                "context_mode": result.get("context_mode"),
                "context_description": result.get("context_description"),
                "cypher_used": result.get("cypher_used"),
                "answer_length": len(result.get("answer", "")),
                "sources_count": len(result.get("sources", [])),
                "conversation_id": str(conversation.id) if conversation else None,
            },
            user=current_user.email,
            success=True,
        )

        return ChatResponse(
            conversation_id=str(conversation.id) if conversation else None,
            message_id=assistant_message_id,
            answer=result["answer"],
            sources=[ChatSource(**source) for source in result.get("sources", [])],
            cost=ChatCost(**build_cost_payload(cost_record)) if cost_record else None,
            model_info=model_info,
            result_graph=result.get("result_graph"),
            provenance=ChatProvenance(
                case_id=str(request.case_id),
                case_revision_id=str(persisted_revision.id) if persisted_revision else None,
                snapshot_id=None,
            ),
            suggestions=suggestions,
            context_mode=result.get("context_mode", request.scope),
            context_description=result.get("context_description", ""),
            cypher_used=bool(result.get("cypher_used")),
            debug_log=result.get("debug_log"),
            used_node_keys=result.get("used_node_keys"),
            document_summary=result.get("document_summary"),
        )
    except Exception as exc:
        db.rollback()
        system_log_service.log(
            log_type=LogType.AI_ASSISTANT,
            origin=LogOrigin.BACKEND,
            action=f"AI Assistant Query Failed: {question[:100]}",
            details={"question": question, "error": str(exc)},
            user=current_user.email,
            success=False,
            error=str(exc),
        )
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        try:
            trace_cm.__exit__(None, None, None)
        except Exception:
            pass


@router.post("/suggestions", response_model=SuggestionsResponse)
async def get_suggestions(
    request: SuggestionsRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_db_user),
):
    require_case_access(db, current_user, request.case_id)
    suggestions = rag_service.get_suggested_questions(
        str(request.case_id),
        request.selected_entity_keys,
    )
    return SuggestionsResponse(
        suggestions=[ChatSuggestion(question=question) for question in suggestions]
    )


@router.post("/extract-nodes", response_model=ExtractNodesResponse)
async def extract_nodes_from_answer(
    request: ExtractNodesRequest,
    current_user: User = Depends(get_current_db_user),
):
    if not request.answer or not request.answer.strip():
        raise HTTPException(status_code=400, detail="Answer is required")

    try:
        node_keys = rag_service.extract_nodes_from_answer(request.answer.strip())
        return ExtractNodesResponse(node_keys=node_keys)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
