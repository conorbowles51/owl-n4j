"""
Testing feedback storage — JSON file on disk.

Backs the QA testing hub: testers leave a status (pass/fail/blocked) and a
note per checklist item. Stored centrally so devs read everyone's feedback in
one place (no per-browser export needed).

Feedback is keyed by **item id → tester** so each tester's own status/note is
preserved and attributable (two testers don't overwrite each other).

Shape on disk (data/testing-feedback.json):
    {
      "items": {
        "<item_id>": {
          "<tester_name>": {
            "status": "pass" | "fail" | "blocked" | "",
            "note": "...",
            "updated_at": "2026-06-09T12:00:00Z"
          },
          ...
        },
        ...
      },
      "assignments":   { "<item_id>": "<username>" },          # who's on it ("" = anyone)
      "item_comments": { "<item_id>": [ {author, text, created_at}, ... ] }
    }

Single small file under an exclusive lock + atomic replace — same pattern as
snapshot_storage. This is an internal QA tool, not user data, so a flat file
is the right weight.
"""

from pathlib import Path
from typing import Any, Dict, Optional
import json

from services._json_file_lock import save_json_atomic
from services._timeutil import utcnow_iso

BASE_DIR = Path(__file__).resolve().parent.parent.parent
STORAGE_DIR = BASE_DIR / "data"
STORAGE_FILE = STORAGE_DIR / "testing-feedback.json"

VALID_STATUSES = {"", "pass", "fail", "blocked"}


def _load() -> Dict[str, Any]:
    if not STORAGE_FILE.exists():
        return {"items": {}, "assignments": {}, "item_comments": {}}
    try:
        with open(STORAGE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {"items": {}, "assignments": {}, "item_comments": {}}
        data.setdefault("items", {})
        if not isinstance(data["items"], dict):
            data["items"] = {}
        for key in ("assignments", "item_comments"):
            if not isinstance(data.get(key), dict):
                data[key] = {}
        return data
    except (json.JSONDecodeError, IOError):
        return {"items": {}, "assignments": {}, "item_comments": {}}


def get_all() -> Dict[str, Any]:
    """Return all feedback ({"items": {item_id: {tester: {...}}}})."""
    return _load()


def upsert_feedback(
    item_id: str,
    status: Optional[str] = None,
    note: Optional[str] = None,
    tester: Optional[str] = None,
) -> Dict[str, Any]:
    """Create or update one (item, tester) feedback record. Returns it.

    Only the provided fields are changed; omitted fields keep their prior
    value. `status` is validated (unknown coerced to ""). `tester` is required
    so feedback is always attributable.
    """
    if not item_id:
        raise ValueError("item_id is required")
    who = (tester or "").strip() or "unknown"

    data = _load()
    items = data["items"]
    by_tester = items.get(item_id)
    if not isinstance(by_tester, dict):
        by_tester = {}
    rec = by_tester.get(who)
    if not isinstance(rec, dict):
        rec = {}

    if status is not None:
        rec["status"] = status if status in VALID_STATUSES else ""
    if note is not None:
        rec["note"] = str(note)[:5000]
    rec["updated_at"] = utcnow_iso()

    by_tester[who] = rec
    items[item_id] = by_tester
    data["items"] = items
    save_json_atomic(STORAGE_FILE, data)
    return rec


def set_assignment(item_id: str, assignee: str) -> Dict[str, str]:
    """Assign a checklist item to a tester ("" clears it back to 'anyone').
    Returns the full assignments map."""
    if not item_id:
        raise ValueError("item_id is required")
    data = _load()
    assignments = data.get("assignments")
    if not isinstance(assignments, dict):
        assignments = {}
    who = (assignee or "").strip().lower()
    if who:
        assignments[item_id] = who
    else:
        assignments.pop(item_id, None)
    data["assignments"] = assignments
    save_json_atomic(STORAGE_FILE, data)
    return assignments


def add_item_comment(item_id: str, author: str, text: str) -> Dict[str, Any]:
    """Append a comment to a checklist item's thread. Returns the comment."""
    if not item_id:
        raise ValueError("item_id is required")
    text = (text or "").strip()
    if not text:
        raise ValueError("comment text is required")
    data = _load()
    comments = data.get("item_comments")
    if not isinstance(comments, dict):
        comments = {}
    thread = comments.get(item_id)
    if not isinstance(thread, list):
        thread = []
    comment = {"author": (author or "").strip() or "unknown",
               "text": text[:5000], "created_at": utcnow_iso()}
    thread.append(comment)
    comments[item_id] = thread
    data["item_comments"] = comments
    save_json_atomic(STORAGE_FILE, data)
    return comment


def clear_all() -> None:
    """Wipe all stored feedback (back to empty)."""
    save_json_atomic(STORAGE_FILE, {"items": {}})
