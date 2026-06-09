"""
Testing hub router.

Serves the QA testing hub — a standalone page (`/testing`) listing every
behaviour shipped in the Cellebrite work, where testers record a status
(pass/fail/blocked) and notes per item. Feedback is persisted centrally to a
JSON file on disk so devs read everyone's input in one place (not trapped in
each tester's browser).

Endpoints:
    GET  /testing                     → the standalone hub page (HTML)
    GET  /api/testing/checklist       → the checklist catalogue (sections+items)
    GET  /api/testing/feedback        → all stored feedback (devs read results)
    POST /api/testing/feedback        → upsert one item's status/note/tester
    DELETE /api/testing/feedback      → wipe all feedback (reset)

The page itself contains no case data, so it's served openly; the feedback
API requires the normal app auth (testers are logged-in internal users), so
results can't be read or written anonymously.
"""

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from routers.users import get_current_db_user
from postgres.models.user import User
from services import testing_checklist
from services import testing_feedback_storage as fb

router = APIRouter(tags=["testing"])

_PAGE = Path(__file__).resolve().parent.parent / "static" / "testing-hub.html"


# ---- the page ----

@router.get("/testing", include_in_schema=False)
def testing_hub_page():
    """Serve the standalone QA testing hub page."""
    if not _PAGE.exists():
        raise HTTPException(status_code=404, detail="testing hub page not found")
    return FileResponse(str(_PAGE), media_type="text/html")


# ---- the catalogue ----

@router.get("/api/testing/checklist")
def get_checklist():
    """The checklist catalogue: sections + items. Public (no case data)."""
    return {
        "sections": testing_checklist.CHECKLIST,
        "item_count": testing_checklist.item_count(),
    }


# ---- feedback ----

class FeedbackIn(BaseModel):
    item_id: str
    status: Optional[str] = None   # "", "pass", "fail", "blocked"
    note: Optional[str] = None
    tester: Optional[str] = None


@router.get("/api/testing/feedback")
def get_feedback(current_user: User = Depends(get_current_db_user)):
    """Return all stored tester feedback so devs can read the results."""
    return fb.get_all()


@router.post("/api/testing/feedback")
def post_feedback(
    body: FeedbackIn,
    current_user: User = Depends(get_current_db_user),
):
    """Create or update one checklist item's feedback."""
    if not body.item_id:
        raise HTTPException(status_code=400, detail="item_id is required")
    # Default the tester to the logged-in user when not supplied.
    tester = body.tester
    if tester is None:
        tester = getattr(current_user, "name", None) or getattr(current_user, "email", None)
    rec = fb.upsert_feedback(
        body.item_id,
        status=body.status,
        note=body.note,
        tester=tester,
    )
    return {"item_id": body.item_id, "record": rec}


@router.delete("/api/testing/feedback")
def clear_feedback(current_user: User = Depends(get_current_db_user)):
    """Wipe all stored feedback (reset the board)."""
    fb.clear_all()
    return {"status": "cleared"}
