"""
Evidence Log Storage

Stores ingestion log messages so the frontend can display a live-ish
log window while evidence files are being processed.
"""

from __future__ import annotations

import fcntl
import json
import os
from contextlib import contextmanager
from pathlib import Path
from typing import List, Optional, Dict
from datetime import datetime
from threading import RLock

from config import BASE_DIR
from services._timeutil import utcnow_iso


LOG_DIR = BASE_DIR / "data"
LOG_FILE = LOG_DIR / "evidence_logs.json"
LOCK_FILE = LOG_DIR / "evidence_logs.json.lock"

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
    """JSON-file backed storage for evidence ingestion logs.

    Multi-process safe: every mutation reloads under an fcntl LOCK_EX,
    appends, atomically saves, and releases — same shape as
    EvidenceStorage / BackgroundTaskStorage. Without this, the bare
    atomic-write pattern in `_save_logs` (open `.tmp` → rename) raced
    across uvicorn workers writing concurrent log entries during a
    Cellebrite ingest: worker A opens `.tmp`, worker B opens the
    SAME path with `O_TRUNC`, B's `tmp.replace(LOG_FILE)` runs first
    and consumes the file, A's `replace` then fails with `ENOENT`.
    Observed killing C5 ingest task c7dfd4a5 on 2026-05-23 at the
    5,000-of-19,056 model mark — the writer's per-batch logging hit
    the race within ~20 minutes of every ingest start.
    """

    def __init__(self) -> None:
        self._logs: List[Dict] = _load_logs()
        self._lock = RLock()  # in-process reentrant lock
        try:
            self._mtime: float = LOG_FILE.stat().st_mtime
        except OSError:
            self._mtime = 0.0

    def _refresh_if_stale(self) -> None:
        """Reload from disk if another worker has mutated it."""
        try:
            current_mtime = LOG_FILE.stat().st_mtime
        except OSError:
            return
        if current_mtime > self._mtime:
            with self._lock:
                try:
                    current_mtime = LOG_FILE.stat().st_mtime
                except OSError:
                    return
                if current_mtime > self._mtime:
                    self._logs = _load_logs()
                    self._mtime = current_mtime

    @contextmanager
    def _file_locked(self):
        """Yield a freshly-loaded logs list under an exclusive file
        lock; persist on exit. Serialises writes across all uvicorn
        workers via fcntl on a sidecar lock file.
        """
        with self._lock:
            _ensure_dir()
            with open(LOCK_FILE, "a") as lf:
                # See evidence_storage._file_locked — defends against a sudo'd
                # script re-creating the lock with restrictive root ownership.
                try:
                    os.chmod(LOCK_FILE, 0o666)
                except OSError:
                    pass
                fcntl.flock(lf.fileno(), fcntl.LOCK_EX)
                try:
                    fresh = _load_logs()
                    yield fresh
                    _save_logs(fresh)
                    self._logs = fresh
                    try:
                        self._mtime = LOG_FILE.stat().st_mtime
                    except OSError:
                        pass
                finally:
                    fcntl.flock(lf.fileno(), fcntl.LOCK_UN)

    def reload(self) -> None:
        """Reload logs from disk."""
        with self._lock:
            self._logs = _load_logs()
            try:
                self._mtime = LOG_FILE.stat().st_mtime
            except OSError:
                self._mtime = 0.0

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
        timestamp = utcnow_iso()
        entry = {
            "id": f"log_{int(datetime.now().timestamp() * 1000)}",
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

        with self._file_locked() as fresh:
            # `entry["id"]` had a `_{len(self._logs)}` suffix before,
            # but that uses stale per-worker length — with the file
            # lock we now have the authoritative current length.
            entry["id"] = f"{entry['id']}_{len(fresh)}"
            fresh.append(entry)
            # Trim to last MAX_LOG_ENTRIES
            if len(fresh) > MAX_LOG_ENTRIES:
                del fresh[: len(fresh) - MAX_LOG_ENTRIES]
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
        self._refresh_if_stale()
        with self._lock:
            logs = self._logs.copy()  # Copy to avoid modification during iteration

            if case_id:
                logs = [l for l in logs if l.get("case_id") == case_id]

            # Return most recent first, up to limit
            logs = sorted(logs, key=lambda l: l.get("timestamp", ""), reverse=True)
            return logs[:limit]


# Singleton instance
evidence_log_storage = EvidenceLogStorage()



