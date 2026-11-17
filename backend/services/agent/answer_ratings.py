"""A person rates an agent answer: "Missed something", "Not relevant" or "Too thin" (lx-agenttools D20, plan R8).

Each rating is stored with the answer's run, goes through the manual-change feed (``services.manual_changes``) so the
lessons job sees it, and can be exported as a relevance test case (``relevance_case``) for lx-relevancetest's gate.
Ratings are append-only: giving one and withdrawing it are each a row; the active ratings are the latest row per
(answer, person, kind) whose action is ``rate``.

"Missed something" may carry the record the person says should have been found (a ``rec://``, ``txn://`` or
``doc://`` link): the test case then expects that record in the answer's reading of the case.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone

from sqlalchemy import select

KINDS = {"missed_something": "Missed something", "not_relevant": "Not relevant", "too_thin": "Too thin"}
RECORD_LINK = re.compile(r"^(rec|txn|doc)://[^\s]{1,300}$")
CHANGE_KIND = "agent_answer_rating"
NOTE_MAX = 2000


class RatingError(ValueError):
    pass


def _answer(db, *, case_id, message_id, user):
    """The answer, its thread and the question before it; an answer is its owner's, as everywhere in the agent."""
    from postgres.models.agent import AgentMessage, AgentThread
    row = db.execute(select(AgentMessage, AgentThread.case_id, AgentThread.owner_user_id)
                     .join(AgentThread, AgentThread.id == AgentMessage.thread_id)
                     .where(AgentMessage.id == message_id)).first()
    if row is None or str(row[1]) != str(case_id) or str(row[2]) != str(getattr(user, "id", None)):
        raise LookupError("This answer is not in this case.")
    message = row[0]
    if message.role != "assistant":
        raise RatingError("Only an answer from the agent can be rated.")
    question = db.scalar(select(AgentMessage.content)
                         .where(AgentMessage.thread_id == message.thread_id, AgentMessage.role == "user",
                                AgentMessage.sequence_number < message.sequence_number)
                         .order_by(AgentMessage.sequence_number.desc()).limit(1)) or ""
    return message, question


def rate_answer(db, *, case_id, message_id, user, kind, note="", record_ref=None, withdraw=False) -> dict:
    """Record a rating (or its withdrawal). The caller commits."""
    from postgres.models.agent import AgentAnswerRating
    from services.manual_changes import record_change
    if kind not in KINDS:
        raise RatingError("The rating is one of: %s." % ", ".join(KINDS))
    note = (note or "").strip()
    if len(note) > NOTE_MAX:
        raise RatingError("The note is at most %d characters." % NOTE_MAX)
    record_ref = (record_ref or "").strip() or None
    if record_ref:
        if kind != "missed_something":
            raise RatingError("Only 'Missed something' names a record that should have been found.")
        if not RECORD_LINK.match(record_ref):
            raise RatingError("A record is a rec://, txn:// or doc:// link.")
    message, question = _answer(db, case_id=case_id, message_id=message_id, user=user)
    if withdraw and not any(r["kind"] == kind for r in active_for_message(db, message_id=message.id, user=user)):
        raise RatingError("There is no active '%s' rating on this answer to withdraw." % KINDS[kind])
    row = AgentAnswerRating(id=uuid.uuid4(), case_id=case_id, thread_id=message.thread_id, message_id=message.id,
                            run_id=message.run_id, user_id=user.id, kind=kind,
                            action="withdraw" if withdraw else "rate", note=note, record_ref=record_ref,
                            question=question, created_at=datetime.now(timezone.utc))
    db.add(row)
    db.flush()
    # The feed carries ids, the kind and the link; the question and the note stay in this table.
    # The feed line names this row (rating_id), so the two are joined without a second write to the row.
    record_change(
        db, CHANGE_KIND, case_id, ("agent_message", str(message.id)), None,
        {"rating": kind, "action": row.action, "run_id": str(message.run_id) if message.run_id else None,
         "record_ref": record_ref, "rating_id": str(row.id)},
        user, reason=note[:200], link="/cases/%s/agent?thread=%s" % (case_id, message.thread_id),
        change_type="set_aside", field=kind, producer=str(message.model_id or ""))
    return view(row)


def view(row) -> dict:
    return {"id": str(row.id), "message_id": str(row.message_id), "kind": row.kind, "label": KINDS.get(row.kind, row.kind),
            "action": row.action, "note": row.note, "record_ref": row.record_ref,
            "created_at": row.created_at.isoformat() if row.created_at else None}


def _latest(rows) -> list:
    """The latest row per (message, person, kind): the state of each rating."""
    latest: dict = {}
    for row in sorted(rows, key=lambda r: (r.created_at is None, r.created_at)):
        latest[(str(row.message_id), str(row.user_id), row.kind)] = row
    return list(latest.values())


def active_for_message(db, *, message_id, user) -> list[dict]:
    from postgres.models.agent import AgentAnswerRating as R
    rows = db.scalars(select(R).where(R.message_id == message_id, R.user_id == user.id)).all()
    return [view(r) for r in _latest(rows) if r.action == "rate"]


def active_for_thread(db, *, thread_id, user) -> dict[str, list[dict]]:
    """Active ratings the person gave in a thread, by answer id."""
    from postgres.models.agent import AgentAnswerRating as R
    rows = db.scalars(select(R).where(R.thread_id == thread_id, R.user_id == user.id)).all()
    out: dict[str, list[dict]] = {}
    for r in _latest(rows):
        if r.action == "rate":
            out.setdefault(str(r.message_id), []).append(view(r))
    return out


def relevance_case(row) -> dict:
    """One active rating as a relevance test item, in lx-relevancetest's query shape: the question as asked, the
    complaint, and, when the person picked a record, the record the answer must reach. A complaint with no record
    is a case to read (``relevant`` empty): it is kept so the question is run and the answer judged."""
    item = {"id": "rating-%s" % str(row.id)[:8], "kind": "rating", "complaint": row.kind, "question": row.question,
            "case_id": str(row.case_id), "answer_message_id": str(row.message_id),
            "run_id": str(row.run_id) if row.run_id else None, "relevant": [], "decoys": []}
    if row.record_ref:
        item["relevant"].append({"id": "picked", "any": [row.record_ref]})
    return item


def active_rows(db, *, case_id=None) -> list:
    """Every active rating (any person), for the export."""
    from postgres.models.agent import AgentAnswerRating as R
    query = select(R)
    if case_id:
        query = query.where(R.case_id == case_id)
    return [r for r in _latest(db.scalars(query).all()) if r.action == "rate"]
