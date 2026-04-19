"""
Chat History Storage Service

Per-chat JSON files under data/chat_histories/ plus a lightweight _index.json of
summaries. Startup only loads the index, not the chat bodies, so memory stays
bounded regardless of total chat volume.
"""

import json
from pathlib import Path
from typing import Dict, List, Optional

BASE_DIR = Path(__file__).resolve().parent.parent.parent
STORAGE_DIR = BASE_DIR / "data" / "chat_histories"
INDEX_FILE = STORAGE_DIR / "_index.json"

SUMMARY_FIELDS = ("id", "name", "timestamp", "created_at", "owner",
                  "snapshot_id", "case_id", "case_version")


def _ensure_dir() -> None:
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)


def _safe_chat_id(chat_id: str) -> bool:
    return isinstance(chat_id, str) and chat_id and "/" not in chat_id and not chat_id.startswith(".") and chat_id != "_index"


def _chat_path(chat_id: str) -> Path:
    return STORAGE_DIR / f"{chat_id}.json"


def _atomic_write(path: Path, obj) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)
    tmp.replace(path)


def _summarize(chat_id: str, chat: Dict) -> Dict:
    msgs = chat.get("messages") or []
    summary = {k: chat.get(k) for k in SUMMARY_FIELDS}
    summary["id"] = chat.get("id") or chat_id
    summary["message_count"] = len(msgs) if isinstance(msgs, list) else 0
    return summary


def _load_index() -> Dict[str, Dict]:
    _ensure_dir()
    if not INDEX_FILE.exists():
        return {}
    try:
        with open(INDEX_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, IOError) as e:
        print(f"Error loading chat history index: {e}")
        return {}


class ChatHistoryStorage:
    """Per-file chat history storage with an in-memory summary index."""

    def __init__(self):
        self._index: Dict[str, Dict] = _load_index()

    def get(self, chat_id: str) -> Optional[Dict]:
        if not _safe_chat_id(chat_id):
            return None
        path = _chat_path(chat_id)
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"Error loading chat {chat_id}: {e}")
            return None

    def save(self, chat_id: str, chat_data: Dict) -> None:
        if not _safe_chat_id(chat_id):
            raise ValueError(f"unsafe chat_id: {chat_id!r}")
        _ensure_dir()
        _atomic_write(_chat_path(chat_id), chat_data)
        self._index[chat_id] = _summarize(chat_id, chat_data)
        _atomic_write(INDEX_FILE, self._index)

    def delete(self, chat_id: str) -> bool:
        if not _safe_chat_id(chat_id):
            return False
        path = _chat_path(chat_id)
        existed = path.exists() or chat_id in self._index
        if not existed:
            return False
        try:
            path.unlink(missing_ok=True)
        except OSError as e:
            print(f"Error deleting chat {chat_id}: {e}")
            return False
        self._index.pop(chat_id, None)
        _atomic_write(INDEX_FILE, self._index)
        return True

    def list_by_user(self, username: str) -> List[Dict]:
        """Return summary dicts (no messages) for a user's chats."""
        return [s for s in self._index.values() if s.get("owner") == username]

    def list_by_snapshot(self, snapshot_id: str) -> List[Dict]:
        """Return summary dicts (no messages) for a snapshot's chats."""
        return [s for s in self._index.values() if s.get("snapshot_id") == snapshot_id]

    def reload(self) -> None:
        self._index = _load_index()


chat_history_storage = ChatHistoryStorage()
