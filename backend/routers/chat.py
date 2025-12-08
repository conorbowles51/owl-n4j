"""
Chat Router - endpoints for AI question answering.
"""

from typing import List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.rag_service import rag_service

router = APIRouter(prefix="/api/chat", tags=["chat"])


class ChatRequest(BaseModel):
    """Request model for chat endpoint."""

    question: str
    selected_keys: Optional[List[str]] = None


class ChatResponse(BaseModel):
    """Response model for chat endpoint."""

    answer: str
    context_mode: str
    context_description: str
    cypher_used: bool


class SuggestionsRequest(BaseModel):
    """Request model for suggestions endpoint."""

    selected_keys: Optional[List[str]] = None


@router.post("", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Ask a question about the investigation.

    The AI will use either:
    - Full graph context (if no nodes selected)
    - Focused context (if nodes are selected)

    Args:
        request: Chat request with question and optional selected nodes
    """
    if not request.question or not request.question.strip():
        raise HTTPException(status_code=400, detail="Question is required")

    try:
        result = rag_service.answer_question(
            question=request.question.strip(),
            selected_keys=request.selected_keys,
        )
        return ChatResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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
