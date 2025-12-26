"""
Chat History Router

Handles saving and retrieving chat histories.
"""

from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from services.chat_history_storage import chat_history_storage
from .auth import get_current_user

router = APIRouter(prefix="/api/chat-history", tags=["chat-history"])


class ChatHistoryCreate(BaseModel):
    """Request model for creating a chat history."""
    name: Optional[str] = None
    messages: List[dict]
    snapshot_id: Optional[str] = None
    case_id: Optional[str] = None
    case_version: Optional[int] = None


class ChatHistoryResponse(BaseModel):
    """Response model for a chat history."""
    id: str
    name: str
    messages: List[dict]
    timestamp: str
    created_at: str
    owner: str
    snapshot_id: Optional[str] = None
    case_id: Optional[str] = None
    case_version: Optional[int] = None
    message_count: int


@router.post("", response_model=ChatHistoryResponse)
async def create_chat_history(chat: ChatHistoryCreate, user: dict = Depends(get_current_user)):
    """Create a new chat history."""
    chat_id = f"chat_{datetime.now().isoformat().replace(':', '-').replace('.', '-')}"
    timestamp = datetime.now().isoformat()
    
    # Generate a name if not provided
    name = chat.name or f"Chat {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    
    # Store the chat history data
    chat_data = {
        "id": chat_id,
        "name": name,
        "messages": chat.messages,
        "timestamp": timestamp,
        "created_at": timestamp,
        "owner": user["username"],
        "snapshot_id": chat.snapshot_id,
        "case_id": chat.case_id,
        "case_version": chat.case_version,
    }
    
    # Save to persistent storage
    chat_history_storage.save(chat_id, chat_data)
    
    return ChatHistoryResponse(
        id=chat_id,
        name=name,
        messages=chat.messages,
        timestamp=timestamp,
        created_at=timestamp,
        owner=user["username"],
        snapshot_id=chat.snapshot_id,
        case_id=chat.case_id,
        case_version=chat.case_version,
        message_count=len(chat.messages),
    )


@router.get("", response_model=List[ChatHistoryResponse])
async def list_chat_histories(user: dict = Depends(get_current_user)):
    """List all chat histories for the current user."""
    chats = chat_history_storage.list_by_user(user["username"])
    
    # Convert to response format
    result = []
    for chat in chats:
        result.append(ChatHistoryResponse(
            id=chat["id"],
            name=chat["name"],
            messages=chat["messages"],
            timestamp=chat["timestamp"],
            created_at=chat["created_at"],
            owner=chat["owner"],
            snapshot_id=chat.get("snapshot_id"),
            case_id=chat.get("case_id"),
            case_version=chat.get("case_version"),
            message_count=len(chat.get("messages", [])),
        ))
    
    # Sort by created_at descending (newest first)
    result.sort(key=lambda x: x.created_at, reverse=True)
    return result


@router.get("/{chat_id}", response_model=ChatHistoryResponse)
async def get_chat_history(chat_id: str, user: dict = Depends(get_current_user)):
    """Get a specific chat history by ID."""
    chat = chat_history_storage.get(chat_id)
    
    if chat is None:
        raise HTTPException(status_code=404, detail="Chat history not found")
    if chat.get("owner") != user["username"]:
        raise HTTPException(status_code=404, detail="Chat history not found")
    
    return ChatHistoryResponse(
        id=chat["id"],
        name=chat["name"],
        messages=chat["messages"],
        timestamp=chat["timestamp"],
        created_at=chat["created_at"],
        owner=chat["owner"],
        snapshot_id=chat.get("snapshot_id"),
        case_id=chat.get("case_id"),
        case_version=chat.get("case_version"),
        message_count=len(chat.get("messages", [])),
    )


@router.delete("/{chat_id}")
async def delete_chat_history(chat_id: str, user: dict = Depends(get_current_user)):
    """Delete a chat history."""
    chat = chat_history_storage.get(chat_id)
    if chat is None or chat.get("owner") != user["username"]:
        raise HTTPException(status_code=404, detail="Chat history not found")
    
    if not chat_history_storage.delete(chat_id):
        raise HTTPException(status_code=404, detail="Chat history not found")
    
    return {"status": "deleted", "id": chat_id}


@router.get("/by-snapshot/{snapshot_id}", response_model=List[ChatHistoryResponse])
async def get_chat_histories_by_snapshot(snapshot_id: str, user: dict = Depends(get_current_user)):
    """Get all chat histories associated with a snapshot."""
    chats = chat_history_storage.list_by_snapshot(snapshot_id)
    
    # Filter by owner
    user_chats = [chat for chat in chats if chat.get("owner") == user["username"]]
    
    result = []
    for chat in user_chats:
        result.append(ChatHistoryResponse(
            id=chat["id"],
            name=chat["name"],
            messages=chat["messages"],
            timestamp=chat["timestamp"],
            created_at=chat["created_at"],
            owner=chat["owner"],
            snapshot_id=chat.get("snapshot_id"),
            case_id=chat.get("case_id"),
            case_version=chat.get("case_version"),
            message_count=len(chat.get("messages", [])),
        ))
    
    # Sort by created_at descending (newest first)
    result.sort(key=lambda x: x.created_at, reverse=True)
    return result

