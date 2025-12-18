"""
Evidence Log Storage

Stores ingestion log messages so the frontend can display a live-ish
log window while evidence files are being processed.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional, Dict
from datetime import datetime

from config import BASE_DIR


LOG_DIR = BASE_DIR / "data"
LOG_FILE = LOG_DIR / "evidence_logs.json"

# Maximum number of log entries to retain (oldest are dropped)
MAX_LOG_ENTRIES = 1000


def _ensure_dir() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def _load_logs() -> List[Dict]:
    _ensure_dir()
    if not LOG_FILE.exists():
        return []
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
            return []
    except (json.JSONDecodeError, OSError):
        return []


def _save_logs(logs: List[Dict]) -> None:
    _ensure_dir()
    tmp = LOG_FILE.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(logs, f, indent=2, ensure_ascii=False)
    tmp.replace(LOG_FILE)


class EvidenceLogStorage:
    """Simple JSON-file backed storage for evidence ingestion logs."""

    def __init__(self) -> None:
        self._logs: List[Dict] = _load_logs()

    def reload(self) -> None:
        """Reload logs from disk."""
        self._logs = _load_logs()

    def _persist(self) -> None:
        _save_logs(self._logs)

    def add_log(
        self,
        *,
        case_id: Optional[str],
        evidence_id: Optional[str],
        filename: Optional[str],
        level: str,
        message: str,
        progress_current: Optional[int] = None,
        progress_total: Optional[int] = None,
    ) -> Dict:
        """
        Append a log entry.

        Args:
            case_id: Optional case identifier
            evidence_id: Optional evidence record id
            filename: Optional original filename
            level: Log level ('info', 'debug', 'error', etc.)
            message: Log message (may contain newlines)
        """
        timestamp = datetime.now().isoformat()
        entry = {
            "id": f"log_{int(datetime.now().timestamp() * 1000)}_{len(self._logs)}",
            "case_id": case_id,
            "evidence_id": evidence_id,
            "filename": filename,
            "level": level,
            "message": message,
            "timestamp": timestamp,
        }

        if progress_current is not None and progress_total is not None:
            entry["progress_current"] = progress_current
            entry["progress_total"] = progress_total

        self._logs.append(entry)

        # Trim to last MAX_LOG_ENTRIES
        if len(self._logs) > MAX_LOG_ENTRIES:
            self._logs = self._logs[-MAX_LOG_ENTRIES :]

        self._persist()
        return entry

    def list_logs(
        self,
        *,
        case_id: Optional[str] = None,
        limit: int = 200,
    ) -> List[Dict]:
        """
        Get recent log entries, optionally filtered by case_id.

        Args:
            case_id: If provided, only return logs for this case.
            limit: Max number of entries to return (most recent first).
        """
        logs = self._logs
        if case_id:
            logs = [l for l in logs if l.get("case_id") == case_id]

        # Return most recent first, up to limit
        logs = sorted(logs, key=lambda l: l.get("timestamp", ""), reverse=True)
        return logs[:limit]


# Singleton instance
evidence_log_storage = EvidenceLogStorage()



