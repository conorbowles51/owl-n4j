"""Saving a group to look into, starting its analysis, and reading it back (lx-overlaps D).

``save_group`` stores a ``relation_query`` group in ``case_selections`` (members checked against the case). A group is
never rewritten: adding items to a running query saves a new group that holds the old members plus the new ones and
says in ``how.extends`` which group it grew from. ``start`` queues a run and works on it in a background thread that
writes its step and true counts to the row, so the page says what it is doing within two seconds and the run goes on
if the page is closed.
"""
from __future__ import annotations

import logging
import threading
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from postgres.models.relation_run import RelationRun
from services import case_selections
from services.relations import engine
from services.relations.sources import DbSources

log = logging.getLogger(__name__)
WORDS = "Look into how these relate"


def normalise(db, case_id, members: list[dict]) -> list[dict]:
    """A marked passage becomes its document with the quote, as written from the stored text now (a passage that cannot
    be read is refused with the reason, never dropped)."""
    out = []
    for m in members:
        if m.get("type") != "evidence_passage":
            out.append(m)
            continue
        from services.evidence_page_text import PassageError, passage_anchor
        try:
            label, anchor = passage_anchor(db, case_id, str(m["id"]))
        except PassageError as exc:
            raise case_selections.SelectionError(str(exc)) from exc
        out.append({"type": "evidence", "id": str(m["id"]).split(":")[0], "label": label,
                    "quote": str((anchor or {}).get("quote") or "")})
    return out


def save_group(db, *, case_id, members: list[dict], user=None, extends: str | None = None, surface: str = "relation") -> dict:
    """Save the group. ``extends`` is a group of this case whose members are kept and added to."""
    held: list[dict] = []
    if extends:
        base = case_selections.describe(db, case_id, extends, member_limit=10**9)
        if base is None or base["group_type"] != "relation_query":
            raise case_selections.SelectionError("The query to add to is not in this case.")
        held = [{k: v for k, v in m.items() if k in ("type", "id", "label", "quote")} for m in base["members"]]
    return case_selections.freeze(db, case_id=case_id, group_type="relation_query", members=held + normalise(db, case_id, list(members)),
                                  how={"surface": surface, **({"extends": extends} if extends else {})},
                                  words=WORDS, user=user)


def start(db, *, case_id, selection_id, user=None, session_factory=None, inline: bool = False) -> dict:
    sel = case_selections.describe(db, case_id, selection_id, member_limit=10**9)
    if sel is None or sel["group_type"] != "relation_query":
        raise case_selections.SelectionError("That query is not in this case.")
    row = RelationRun(id=uuid.uuid4(), case_id=uuid.UUID(str(case_id)), selection_id=uuid.UUID(str(selection_id)),
                      status="queued", step="Waiting to start", progress={"items": sel["member_count"]},
                      requested_by=getattr(user, "id", None))
    db.add(row)
    db.commit()
    run_id = str(row.id)
    if inline:
        work(run_id, str(case_id), session_factory=lambda: db)
    else:
        if session_factory is None:
            from postgres.session import _get_background_session_local
            session_factory = _get_background_session_local()
        threading.Thread(target=work, args=(run_id, str(case_id)), kwargs={"session_factory": session_factory},
                         daemon=True, name=f"relations-{run_id[:8]}").start()
    return view(db, case_id, run_id)


def work(run_id: str, case_id: str, *, session_factory) -> None:
    session = session_factory()
    own = session is not None and session_factory is not None
    try:
        row = session.get(RelationRun, uuid.UUID(run_id))
        sel = case_selections.describe(session, case_id, str(row.selection_id), member_limit=10**9)
        members = [{k: v for k, v in m.items() if k in ("type", "id", "label", "quote")} for m in sel["members"]]
        row.status = "running"
        row.step = f"Reading {len(members):,} items"
        session.commit()

        def progress(step, done, total):
            row.step = f"{step} ({done:,} of {total:,})"
            session.commit()
        result = engine.run(DbSources(session, case_id), members, progress)
        row.result, row.status, row.step = result, "done", "Done"
        row.progress = {"items": result["counts"]["items"], "candidates": result["counts"]["candidates"],
                        "no_links": result["counts"]["no_links"]}
        row.finished_at = datetime.now(timezone.utc)
        session.commit()
    except Exception as exc:  # noqa: BLE001 - the run fails visibly, with the reason
        log.exception("relation run %s failed", run_id)
        session.rollback()
        row = session.get(RelationRun, uuid.UUID(run_id))
        if row is not None:
            row.status, row.error, row.step = "failed", f"{type(exc).__name__}: {exc}"[:2000], "Stopped"
            row.finished_at = datetime.now(timezone.utc)
            session.commit()
    finally:
        if own and getattr(session, "bind", None) is not None and session_factory.__name__ != "<lambda>":
            session.close()


def view(db, case_id, run_id, *, with_result: bool = True) -> dict[str, Any]:
    row = db.get(RelationRun, uuid.UUID(str(run_id)))
    if row is None or str(row.case_id) != str(case_id):
        raise LookupError("That run is not in this case.")
    out = {"id": str(row.id), "selection_id": str(row.selection_id), "status": row.status, "step": row.step,
           "progress": row.progress or {}, "error": row.error, "hypotheses": row.hypotheses,
           "created_at": row.created_at.isoformat() if row.created_at else None,
           "finished_at": row.finished_at.isoformat() if row.finished_at else None}
    if with_result:
        out["result"] = row.result
    return out


def latest_for(db, case_id, selection_id) -> str | None:
    return db.scalar(select(RelationRun.id).where(RelationRun.case_id == uuid.UUID(str(case_id)),
                                                  RelationRun.selection_id == uuid.UUID(str(selection_id)))
                     .order_by(RelationRun.created_at.desc()).limit(1))
