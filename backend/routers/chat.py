"""
Chat Router - endpoints for AI question answering.
"""

from typing import List, Optional, Dict
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from services.rag_service import rag_service
from services.llm_service import llm_service
from services.system_log_service import system_log_service, LogType, LogOrigin
from routers.auth import get_current_user

import sys
from pathlib import Path
backend_dir = Path(__file__).parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from models.llm_models import get_model_by_id
from utils.prompt_trace import start_trace, log_section

router = APIRouter(prefix="/api/chat", tags=["chat"])


class ChatRequest(BaseModel):
    """Request model for chat endpoint."""

    question: str
    selected_keys: Optional[List[str]] = None
    provider: str
    model: str


class ChatResponse(BaseModel):
    """Response model for chat endpoint."""

    answer: str
    context_mode: str
    context_description: str
    cypher_used: bool
    debug_log: Optional[Dict] = None
    used_node_keys: Optional[List[str]] = None  # Node keys actually used to generate the answer
    model_info: Optional[Dict] = None  # Current model and server information


class SuggestionsRequest(BaseModel):
    """Request model for suggestions endpoint."""

    selected_keys: Optional[List[str]] = None


@router.post("", response_model=ChatResponse)
async def chat(request: ChatRequest, user: dict = Depends(get_current_user)):
    """
    Ask a question about the investigation.

    The AI will use either:
    - Full graph context (if no nodes selected)
    - Focused context (if nodes are selected)

    Args:
        request: Chat request with question and optional selected nodes
        user: Current authenticated user
    """
    if not request.question or not request.question.strip():
        raise HTTPException(status_code=400, detail="Question is required")

    question = request.question.strip()
    username = user.get("username", "unknown")
    
    try:
        trace_cm = start_trace(
            meta={
                "endpoint": "/api/chat",
                "user": username,
                "provider": request.provider,
                "model": request.model,
                "question": question,
                "selected_keys": request.selected_keys,
            }
        )
        trace_cm.__enter__()
        log_section(
            source_file=__file__,
            source_func="chat",
            title="Incoming request",
            content={
                "question": question,
                "selected_keys": request.selected_keys,
                "provider": request.provider,
                "model": request.model,
                "question_length": len(question),
            },
            as_json=True,
        )

        # Log the AI assistant query
        system_log_service.log(
            log_type=LogType.AI_ASSISTANT,
            origin=LogOrigin.FRONTEND,
            action=f"AI Assistant Query: {question[:100]}",
            details={
                "question": question,
                "selected_keys": request.selected_keys,
                "question_length": len(question),
            },
            user=username,
            success=True,
        )

        provider = request.provider
        model_id = request.model
        model = get_model_by_id(model_id)

        rag_service.llm.set_config(provider, model_id)
        
        result = rag_service.answer_question(
            question=question,
            selected_keys=request.selected_keys,
        )
        
        # Get current model info
        
        server = "Ollama (local)" if provider == "ollama" else "OpenAI (remote)"
        result["model_info"] = {
            "provider": provider,
            "model_id": model_id,
            "model_name": model.name if model else model_id,
            "server": server,
        }
        
        # Log the response
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
                "used_node_keys_count": len(result.get("used_node_keys", [])),
                "debug_log_available": result.get("debug_log") is not None,
            },
            user=username,
            success=True,
        )
        
        return ChatResponse(**result)
    except Exception as e:
        # Log the error
        system_log_service.log(
            log_type=LogType.AI_ASSISTANT,
            origin=LogOrigin.BACKEND,
            action=f"AI Assistant Query Failed: {question[:100]}",
            details={
                "question": question,
                "error": str(e),
            },
            user=username,
            success=False,
            error=str(e),
        )
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        try:
            trace_cm.__exit__(None, None, None)
        except Exception:
            # Tracing must never break the request.
            pass


@router.post("/suggestions")
async def get_suggestions(request: SuggestionsRequest):
    """
    Get suggested questions based on current context.

    Args:
        request: Request with optional selected node keys
    """
    try:
        suggestions = rag_service.get_suggested_questions(request.selected_keys)
        return {"suggestions": suggestions}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class ExtractNodesRequest(BaseModel):
    """Request model for extract nodes endpoint."""

    answer: str


@router.post("/extract-nodes")
async def extract_nodes_from_answer(request: ExtractNodesRequest):
    """
    Extract node keys mentioned in an AI answer.
    
    Uses the LLM to identify which nodes from the graph are discussed in the answer.
    Returns the node keys that can be used to create a subgraph.

    Args:
        request: Request with answer text
    """
    if not request.answer or not request.answer.strip():
        raise HTTPException(status_code=400, detail="Answer is required")

    try:
        node_keys = rag_service.extract_nodes_from_answer(request.answer.strip())
        return {"node_keys": node_keys}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
