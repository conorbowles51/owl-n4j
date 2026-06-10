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
            "repro": "...",
            "updated_at": "2026-06-09T12:00:00Z"
          },
          ...
        },
        ...
      },
      "comments": {
        "<item_id>": [
          {
            "id": "<unix_ms>-<n>",
            "author": "Neil",
            "text": "...",
            "created_at": "2026-06-09T12:00:00Z"
          },
          ...
        ],
        ...
      },
      "user_items": [
        {
          "id": "user-bug-1-<ts>",
          "kind": "feature" | "bug",
          "title": "...",
          "body": "...",
          "author": "Neil",
          "created_at": "2026-06-09T12:00:00Z"
        },
        ...
      ]
    }

`user_items` are tester-submitted feature requests / bugs (not part of the
shipped catalogue). They reuse the same id-keyed feedback + comment machinery.

Per-item discussion lives in a SEPARATE top-level `comments` map (not under
the tester-keyed `items` records) so a comment thread can never collide with a
tester's own status/note record.

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
VALID_KINDS = {"feature", "bug"}


def _empty() -> Dict[str, Any]:
    return {"items": {}, "comments": {}, "user_items": []}


def _load() -> Dict[str, Any]:
    if not STORAGE_FILE.exists():
        return _empty()
    try:
        with open(STORAGE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return _empty()
        data.setdefault("items", {})
        if not isinstance(data["items"], dict):
            data["items"] = {}
        data.setdefault("comments", {})
        if not isinstance(data["comments"], dict):
            data["comments"] = {}
        data.setdefault("user_items", [])
        if not isinstance(data["user_items"], list):
            data["user_items"] = []
        return data
    except (json.JSONDecodeError, IOError):
        return _empty()


def get_all() -> Dict[str, Any]:
    """Return all feedback ({"items": {item_id: {tester: {...}}}})."""
    return _load()


def upsert_feedback(
    item_id: str,
    status: Optional[str] = None,
    note: Optional[str] = None,
    repro: Optional[str] = None,
    tester: Optional[str] = None,
) -> Dict[str, Any]:
    """Create or update one (item, tester) feedback record. Returns it.

    Only the provided fields are changed; omitted fields keep their prior
    value. `status` is validated (unknown coerced to ""). `tester` is required
    so feedback is always attributable. `repro` holds reproduction steps.
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
    if repro is not None:
        rec["repro"] = str(repro)[:5000]
    rec["updated_at"] = utcnow_iso()

    by_tester[who] = rec
    items[item_id] = by_tester
    data["items"] = items
    save_json_atomic(STORAGE_FILE, data)
    return rec


def add_comment(item_id: str, author: str, text: str) -> Dict[str, Any]:
    """Append one comment to an item's discussion thread. Returns the comment.

    Comments are an append-only, chronological log shared by all testers — the
    "chat history" for a feature/bug. `author` comes from the verified token so
    it's reliably attributed; `created_at` stamps when it was posted.
    """
    if not item_id:
        raise ValueError("item_id is required")
    who = (author or "").strip() or "unknown"
    body = str(text or "").strip()[:5000]
    if not body:
        raise ValueError("comment text is required")

    data = _load()
    comments = data["comments"]
    thread = comments.get(item_id)
    if not isinstance(thread, list):
        thread = []
    now = utcnow_iso()
    comment = {
        # id only needs to be unique within the thread (frontend keying):
        # the post-count guarantees that even for same-second posts.
        "id": f"{len(thread) + 1}-{now}",
        "author": who,
        "text": body,
        "created_at": now,
    }
    thread.append(comment)
    comments[item_id] = thread
    data["comments"] = comments
    save_json_atomic(STORAGE_FILE, data)
    return comment


def add_user_item(kind: str, title: str, body: str, author: str) -> Dict[str, Any]:
    """Create a tester-submitted item (a feature request or a bug). Returns it.

    These live alongside the shipped checklist but are user-generated, so they
    carry their own author + created_at and a `kind`. They support the same
    status/note/repro/comment machinery as catalogue items (keyed by their id).
    """
    k = (kind or "").strip().lower()
    if k not in VALID_KINDS:
        raise ValueError("kind must be 'feature' or 'bug'")
    t = str(title or "").strip()[:300]
    if not t:
        raise ValueError("title is required")
    b = str(body or "").strip()[:5000]
    who = (author or "").strip() or "unknown"

    data = _load()
    items = data["user_items"]
    now = utcnow_iso()
    item = {
        "id": f"user-{k}-{len(items) + 1}-{now}",
        "kind": k,
        "title": t,
        "body": b,
        "author": who,
        "created_at": now,
    }
    items.append(item)
    data["user_items"] = items
    save_json_atomic(STORAGE_FILE, data)
    return item


def delete_user_item(item_id: str) -> bool:
    """Remove a tester-submitted item and its feedback/comments. Returns True if found."""
    data = _load()
    before = len(data["user_items"])
    data["user_items"] = [it for it in data["user_items"] if it.get("id") != item_id]
    removed = len(data["user_items"]) != before
    if removed:
        data["items"].pop(item_id, None)
        data["comments"].pop(item_id, None)
        save_json_atomic(STORAGE_FILE, data)
    return removed


def clear_all() -> None:
    """Wipe all stored feedback (back to empty)."""
    save_json_atomic(STORAGE_FILE, _empty())
