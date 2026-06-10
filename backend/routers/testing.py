"""
Testing hub router.

Serves the QA testing hub — a standalone page (`/testing`) listing every
behaviour shipped in the Cellebrite work, where testers record a status
(pass/fail/blocked) and notes per item. Feedback is persisted centrally to a
JSON file on disk so devs read everyone's input in one place (not trapped in
each tester's browser).

Access: a small, self-contained login scoped ONLY to this hub (testers
neil / alex / conor / arturo — see services/testing_auth.py). The page shell is served
openly (it's just a login screen + JS), but the checklist data and ALL
feedback endpoints require a valid hub token, so nothing here is available to
the public, and every note is attributed to whoever was logged in.

Endpoints:
    GET    /testing                   → the hub page (login screen + app)
    POST   /api/testing/login         → exchange username/password for a token
    GET    /api/testing/me            → who am I (token check)
    GET    /api/testing/checklist     → the checklist catalogue (auth required)
    GET    /api/testing/feedback      → all stored feedback (auth required)
    POST   /api/testing/feedback      → upsert one item's status/note/repro (auth)
    DELETE /api/testing/feedback      → wipe all feedback (auth)
    POST   /api/testing/comment       → append a comment to an item's thread (auth)
    POST   /api/testing/item          → create a tester item (feature request / bug) (auth)
    DELETE /api/testing/item/{id}     → remove a tester-submitted item (auth)
"""

from pathlib import Path
from typing import Optional

import json

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from services import testing_checklist
from services import testing_feedback_storage as fb
from services import testing_auth

router = APIRouter(tags=["testing"])
_security = HTTPBearer(auto_error=False)


def _safe_json(payload):
    """JSON response that can't be killed by a stray non-ASCII / lone-surrogate
    character. ensure_ascii=True escapes every non-ASCII codepoint to \\uXXXX,
    so the output is pure ASCII and always UTF-8-encodable — testers paste
    fancy-font names / emoji into bug reports, and a checklist string once
    carried surrogate escapes; without this either could 500 the whole hub."""
    return Response(
        content=json.dumps(payload, ensure_ascii=True),
        media_type="application/json",
    )

_PAGE = Path(__file__).resolve().parent.parent / "static" / "testing-hub.html"


# ---- auth dependency (hub-scoped) ----

def require_tester(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_security),
) -> dict:
    """Resolve the current tester from a hub token (Bearer header or cookie).

    Returns {username, name}. Raises 401 if missing/invalid. Hub tokens are
    distinct from the main app's tokens (they carry a `hub` claim), so app
    accounts can't read/write the hub and vice-versa.
    """
    token = None
    if credentials and credentials.credentials:
        token = credentials.credentials
    elif request is not None:
        token = request.cookies.get("testing_token")
    tester = testing_auth.verify_token(token) if token else None
    if not tester:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sign in to the testing hub",
        )
    return tester


# ---- the page ----

def _serve_page():
    if not _PAGE.exists():
        raise HTTPException(status_code=404, detail="testing hub page not found")
    return FileResponse(str(_PAGE), media_type="text/html")


@router.get("/testing", include_in_schema=False)
def testing_hub_page():
    """Serve the hub page directly off the backend (e.g. :8000/testing)."""
    return _serve_page()


@router.get("/api/testing/hub", include_in_schema=False)
def testing_hub_page_via_api():
    """Same page, served under /api so it rides the existing /api proxy.

    In every environment the frontend already proxies /api → the backend
    (Vite dev proxy + nginx), so testers can open the hub at
    <app-origin>/api/testing/hub with NO extra reverse-proxy rule, and the
    page's /api/testing/* calls are same-origin from there.
    """
    return _serve_page()


# ---- login ----

class LoginIn(BaseModel):
    username: str
    password: str


@router.post("/api/testing/login")
def login(body: LoginIn):
    """Exchange a hub username/password for a hub-scoped token."""
    name = testing_auth.authenticate(body.username, body.password)
    if not name:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )
    token = testing_auth.make_token(body.username)
    return {"token": token, "name": name, "username": body.username.strip().lower()}


@router.get("/api/testing/me")
def me(tester: dict = Depends(require_tester)):
    """Return the signed-in tester (used by the page to validate a stored token)."""
    return tester


# ---- the catalogue ----

@router.get("/api/testing/checklist")
def get_checklist(tester: dict = Depends(require_tester)):
    """The checklist catalogue: sections + items."""
    return _safe_json({
        "sections": testing_checklist.CHECKLIST,
        "item_count": testing_checklist.item_count(),
    })


# ---- feedback ----

class FeedbackIn(BaseModel):
    item_id: str
    status: Optional[str] = None   # "", "pass", "fail", "blocked"
    note: Optional[str] = None
    repro: Optional[str] = None    # reproduction steps


@router.get("/api/testing/feedback")
def get_feedback(tester: dict = Depends(require_tester)):
    """Return all stored tester feedback so devs can read the results."""
    return _safe_json(fb.get_all())


@router.post("/api/testing/feedback")
def post_feedback(body: FeedbackIn, tester: dict = Depends(require_tester)):
    """Create or update one checklist item's feedback.

    The tester is taken from the verified token — it can't be spoofed by the
    client — so authorship of every note/status is reliable.
    """
    if not body.item_id:
        raise HTTPException(status_code=400, detail="item_id is required")
    rec = fb.upsert_feedback(
        body.item_id,
        status=body.status,
        note=body.note,
        repro=body.repro,
        tester=tester.get("name"),
    )
    return {"item_id": body.item_id, "record": rec}


@router.delete("/api/testing/feedback")
def clear_feedback(tester: dict = Depends(require_tester)):
    """Wipe all stored feedback (reset the board)."""
    fb.clear_all()
    return {"status": "cleared"}


# ---- discussion (per-item comment thread) ----

class CommentIn(BaseModel):
    item_id: str
    text: str


@router.post("/api/testing/comment")
def post_comment(body: CommentIn, tester: dict = Depends(require_tester)):
    """Append a comment to one item's discussion thread.

    The author is taken from the verified token (can't be spoofed), so the
    chat history is reliably attributed. Comments are append-only.
    """
    if not body.item_id:
        raise HTTPException(status_code=400, detail="item_id is required")
    if not (body.text or "").strip():
        raise HTTPException(status_code=400, detail="comment text is required")
    comment = fb.add_comment(body.item_id, author=tester.get("name"), text=body.text)
    return {"item_id": body.item_id, "comment": comment}


# ---- tester-submitted items (feature requests / bugs) ----

class ItemIn(BaseModel):
    kind: str            # "feature" | "bug"
    title: str
    body: Optional[str] = None


@router.post("/api/testing/item")
def create_item(body: ItemIn, tester: dict = Depends(require_tester)):
    """Create a tester-submitted feature request or bug.

    The author is taken from the verified token. The item then behaves like a
    catalogue item: testers can set status/note/repro and discuss it.
    """
    try:
        item = fb.add_user_item(
            kind=body.kind,
            title=body.title,
            body=body.body or "",
            author=tester.get("name"),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"item": item}


@router.delete("/api/testing/item/{item_id}")
def delete_item(item_id: str, tester: dict = Depends(require_tester)):
    """Remove a tester-submitted item (and its feedback/comments)."""
    removed = fb.delete_user_item(item_id)
    if not removed:
        raise HTTPException(status_code=404, detail="item not found")
    return {"status": "deleted", "item_id": item_id}
