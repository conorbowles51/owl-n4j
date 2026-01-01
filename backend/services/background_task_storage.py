"""
Background Task Storage

Stores background task information so the frontend can monitor progress.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import List, Optional, Dict
from datetime import datetime
from enum import Enum

from config import BASE_DIR


TASK_DIR = BASE_DIR / "data"
TASK_FILE = TASK_DIR / "background_tasks.json"

# Maximum number of task entries to retain (oldest are dropped)
MAX_TASK_ENTRIES = 500


class TaskStatus(str, Enum):
    """Task status enumeration."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


def _ensure_dir() -> None:
    TASK_DIR.mkdir(parents=True, exist_ok=True)


def _load_tasks() -> List[Dict]:
    _ensure_dir()
    if not TASK_FILE.exists():
        return []
    try:
        with open(TASK_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
            return []
    except (json.JSONDecodeError, OSError):
        return []


def _save_tasks(tasks: List[Dict]) -> None:
    _ensure_dir()
    tmp = TASK_FILE.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(tasks, f, indent=2, ensure_ascii=False)
    tmp.replace(TASK_FILE)


class BackgroundTaskStorage:
    """Simple JSON-file backed storage for background tasks."""

    def __init__(self) -> None:
        self._tasks: List[Dict] = _load_tasks()

    def reload(self) -> None:
        """Reload tasks from disk."""
        self._tasks = _load_tasks()

    def _persist(self) -> None:
        _save_tasks(self._tasks)

    def create_task(
        self,
        *,
        task_type: str,
        task_name: str,
        owner: Optional[str] = None,
        case_id: Optional[str] = None,
        metadata: Optional[Dict] = None,
    ) -> Dict:
        """
        Create a new background task.

        Args:
            task_type: Type of task (e.g., "evidence_processing")
            task_name: Human-readable task name
            owner: Optional owner username
            case_id: Optional associated case ID
            metadata: Optional additional metadata

        Returns:
            Task dict with id, status, etc.
        """
        task_id = str(uuid.uuid4())
        timestamp = datetime.now().isoformat()
        
        task = {
            "id": task_id,
            "task_type": task_type,
            "task_name": task_name,
            "owner": owner,
            "case_id": case_id,
            "status": TaskStatus.PENDING.value,
            "created_at": timestamp,
            "updated_at": timestamp,
            "started_at": None,
            "completed_at": None,
            "progress": {
                "total": 0,
                "completed": 0,
                "failed": 0,
            },
            "files": [],  # List of file processing statuses
            "error": None,
            "metadata": metadata or {},
        }

        self._tasks.append(task)

        # Trim to last MAX_TASK_ENTRIES
        if len(self._tasks) > MAX_TASK_ENTRIES:
            self._tasks = self._tasks[-MAX_TASK_ENTRIES :]

        self._persist()
        return task

    def get_task(self, task_id: str) -> Optional[Dict]:
        """Get a task by ID."""
        for task in self._tasks:
            if task.get("id") == task_id:
                return task
        return None

    def update_task(
        self,
        task_id: str,
        *,
        status: Optional[str] = None,
        progress_total: Optional[int] = None,
        progress_completed: Optional[int] = None,
        progress_failed: Optional[int] = None,
        file_status: Optional[Dict] = None,
        error: Optional[str] = None,
        started_at: Optional[str] = None,
        completed_at: Optional[str] = None,
    ) -> Optional[Dict]:
        """
        Update a task's status and progress.

        Args:
            task_id: Task ID
            status: New status
            progress_total: Total items to process
            progress_completed: Number completed
            progress_failed: Number failed
            file_status: Dict with file_id, filename, status, error for file-by-file updates
            error: Error message if task failed
            started_at: When task started (ISO timestamp)
            completed_at: When task completed (ISO timestamp)

        Returns:
            Updated task dict or None if not found
        """
        task = self.get_task(task_id)
        if not task:
            return None

        updated = False

        if status is not None:
            task["status"] = status
            updated = True

        if progress_total is not None:
            task["progress"]["total"] = progress_total
            updated = True

        if progress_completed is not None:
            task["progress"]["completed"] = progress_completed
            updated = True

        if progress_failed is not None:
            task["progress"]["failed"] = progress_failed
            updated = True

        if file_status is not None:
            # Update or add file status
            file_id = file_status.get("file_id")
            if file_id:
                existing_file = next(
                    (f for f in task["files"] if f.get("file_id") == file_id),
                    None,
                )
                if existing_file:
                    existing_file.update(file_status)
                else:
                    task["files"].append(file_status)
                updated = True

        if error is not None:
            task["error"] = error
            updated = True

        if started_at is not None:
            task["started_at"] = started_at
            updated = True

        if completed_at is not None:
            task["completed_at"] = completed_at
            updated = True

        if updated:
            task["updated_at"] = datetime.now().isoformat()
            self._persist()

        return task

    def list_tasks(
        self,
        *,
        owner: Optional[str] = None,
        case_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict]:
        """
        List tasks, optionally filtered.

        Args:
            owner: Filter by owner
            case_id: Filter by case_id
            status: Filter by status
            limit: Max number of tasks to return (most recent first)

        Returns:
            List of task dicts
        """
        tasks = self._tasks

        if owner:
            tasks = [t for t in tasks if t.get("owner") == owner]

        if case_id:
            tasks = [t for t in tasks if t.get("case_id") == case_id]

        if status:
            tasks = [t for t in tasks if t.get("status") == status]

        # Return most recent first, up to limit
        tasks = sorted(tasks, key=lambda t: t.get("created_at", ""), reverse=True)
        return tasks[:limit]

    def delete_task(self, task_id: str) -> bool:
        """
        Delete a task.

        Args:
            task_id: Task ID

        Returns:
            True if deleted, False if not found
        """
        task = self.get_task(task_id)
        if not task:
            return False

        self._tasks.remove(task)
        self._persist()
        return True


# Singleton instance
background_task_storage = BackgroundTaskStorage()





