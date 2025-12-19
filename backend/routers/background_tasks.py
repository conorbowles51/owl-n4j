"""
Background Tasks Router

API endpoints for managing and monitoring background tasks.
"""

from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from services.background_task_storage import background_task_storage, TaskStatus
from routers.auth import get_current_user


router = APIRouter(prefix="/api/background-tasks", tags=["background-tasks"])


class TaskResponse(BaseModel):
    """Task response model."""
    id: str
    task_type: str
    task_name: str
    owner: Optional[str] = None
    case_id: Optional[str] = None
    status: str
    created_at: str
    updated_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    progress: dict
    files: List[dict]
    error: Optional[str] = None
    metadata: dict


class TasksListResponse(BaseModel):
    """List of tasks response."""
    tasks: List[TaskResponse]


@router.get("", response_model=TasksListResponse)
async def list_tasks(
    owner: Optional[str] = None,
    case_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 100,
    user: dict = Depends(get_current_user),
):
    """
    List background tasks, optionally filtered.

    Args:
        owner: Filter by owner (defaults to current user if not provided)
        case_id: Filter by case_id
        status: Filter by status (pending, running, completed, failed, cancelled)
        limit: Max number of tasks to return

    Returns:
        List of tasks
    """
    # Default to current user's tasks if owner not specified
    filter_owner = owner if owner is not None else user["username"]

    tasks = background_task_storage.list_tasks(
        owner=filter_owner,
        case_id=case_id,
        status=status,
        limit=limit,
    )

    return TasksListResponse(
        tasks=[TaskResponse(**task) for task in tasks]
    )


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: str,
    user: dict = Depends(get_current_user),
):
    """
    Get a specific task by ID.

    Args:
        task_id: Task ID

    Returns:
        Task details
    """
    task = background_task_storage.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # Only allow owner to view their own tasks
    if task.get("owner") != user["username"]:
        raise HTTPException(status_code=403, detail="Access denied")

    return TaskResponse(**task)


@router.delete("/{task_id}")
async def delete_task(
    task_id: str,
    user: dict = Depends(get_current_user),
):
    """
    Delete a task.

    Args:
        task_id: Task ID

    Returns:
        Success message
    """
    task = background_task_storage.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # Only allow owner to delete their own tasks
    if task.get("owner") != user["username"]:
        raise HTTPException(status_code=403, detail="Access denied")

    deleted = background_task_storage.delete_task(task_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Task not found")

    return {"message": "Task deleted", "task_id": task_id}

