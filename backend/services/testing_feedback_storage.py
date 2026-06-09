"""
Testing feedback storage — JSON file on disk.

Backs the QA testing hub: testers leave a status (pass/fail/blocked) and a
note per checklist item, keyed by the stable item id. Stored centrally so
devs can read everyone's feedback in one place (no per-browser export needed).

Shape on disk (data/testing-feedback.json):
    {
      "items": {
        "<item_id>": {
          "status": "pass" | "fail" | "blocked" | "",
          "note": "...",
          "tester": "Neil",
          "updated_at": "2026-06-09T12:00:00Z"
        },
        ...
      }
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
        return {"items": {}}
    try:
        with open(STORAGE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {"items": {}}
        data.setdefault("items", {})
        if not isinstance(data["items"], dict):
            data["items"] = {}
        return data
    except (json.JSONDecodeError, IOError):
        return {"items": {}}


def get_all() -> Dict[str, Any]:
    """Return all feedback ({"items": {item_id: {...}}})."""
    return _load()


def upsert_feedback(
    item_id: str,
    status: Optional[str] = None,
    note: Optional[str] = None,
    tester: Optional[str] = None,
) -> Dict[str, Any]:
    """Create or update one item's feedback. Returns the stored record.

    Only the provided fields are changed; omitted fields keep their prior
    value. `status` is validated against VALID_STATUSES (an unknown value
    is coerced to "").
    """
    if not item_id:
        raise ValueError("item_id is required")

    data = _load()
    items = data["items"]
    rec = items.get(item_id, {}) if isinstance(items.get(item_id), dict) else {}

    if status is not None:
        rec["status"] = status if status in VALID_STATUSES else ""
    if note is not None:
        rec["note"] = str(note)[:5000]
    if tester is not None:
        rec["tester"] = str(tester)[:120]
    rec["updated_at"] = utcnow_iso()

    items[item_id] = rec
    data["items"] = items
    save_json_atomic(STORAGE_FILE, data)
    return rec


def clear_all() -> None:
    """Wipe all stored feedback (back to empty)."""
    save_json_atomic(STORAGE_FILE, {"items": {}})
