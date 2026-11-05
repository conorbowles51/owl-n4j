"""Coming back to a phone review, and passing it to a colleague (07 J-15, UXD-36, UXD-60).

- **Position.** For an assigned review the reading position is stored on the review task's link, so it survives the
  browser and passes with the task. Only the person the task is assigned to moves it: a colleague looking at the
  same thread does not. Casual reading stays in that person's browser, as record ids only.
- **Continue reading.** The threads a person opened and has not finished, each with its last position: the assigned
  ones from the server, the casual ones from the ids the browser sends. Titles come from the server, so the browser
  keeps no names.
- **Hand over.** Reassigns a review task and attaches a Workspace note, linked to the task both ways, that lists the
  positions and the open items at that moment. Positions stay on the links, so the colleague resumes there.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import text

from services.phone import time_display as T
from services.phone.review_share import ReviewShareError, _members, _n, _plural, _totals

REVIEW_ANCHORS = ("review_split", "second_pass", "reading_recheck")
_IS_REVIEW = "(" + " OR ".join("l.source_anchor ? '%s'" % k for k in REVIEW_ANCHORS) + ")"
_THREAD_ANCHORS = "(l.source_anchor ? 'review_split' OR l.source_anchor ? 'second_pass')"


def save_position(db, case_id, thread_key: str, user, position: dict) -> dict:
    """Store the position on this thread's links in the open review tasks assigned to ``user``. ``saved`` is 0 when
    there are none: the reading is casual and stays in the browser."""
    stamp = {"event_uid": position["event_uid"], "instant": position.get("instant"), "by": str(user.id),
             "by_name": user.name or user.email, "at": datetime.now(timezone.utc).isoformat()}
    conn = db.connection()
    saved = conn.execute(text(
        "UPDATE case_task_links l SET source_anchor = jsonb_set(l.source_anchor, '{position}', CAST(:p AS jsonb)), "
        "updated_at = now() FROM case_tasks t WHERE t.id = l.task_id AND l.case_id = :c AND l.target_type = "
        "'phone_thread' AND l.target_id = :k AND t.deleted_at IS NULL AND t.status <> 'done' AND "
        "t.assignee_user_id = :u AND " + _THREAD_ANCHORS),
        {"p": json.dumps(stamp), "c": str(case_id), "k": thread_key, "u": str(user.id)}).rowcount
    db.commit()
    return {"thread_key": thread_key, "saved": int(saved), "position": stamp if saved else None}


def _position_words(p: dict) -> str:
    when = None
    if p.get("instant"):
        try:
            when = T.format_full(datetime.fromisoformat(p["instant"]), "UTC")
        except (TypeError, ValueError):
            when = p["instant"]
    return "stopped at the message of %s" % when if when else "stopped at a saved message"


def _thread_phones(conn, case_id, keys) -> dict:
    return {r.thread_key: str(r.extraction_id) for r in conn.execute(text(
        "SELECT thread_key, extraction_id FROM pv_thread WHERE case_id = :c AND thread_key = ANY(:k)"),
        {"c": str(case_id), "k": list(keys)})}


def _task_links(conn, case_id, *, assignee=None, task_id=None) -> list:
    q = ("SELECT l.id, l.task_id, l.target_type, l.target_id, l.label, l.source_anchor, t.title, t.status, "
         "t.assignee_user_id FROM case_task_links l JOIN case_tasks t ON t.id = l.task_id WHERE l.case_id = :c AND "
         "t.deleted_at IS NULL AND " + _IS_REVIEW)
    p = {"c": str(case_id)}
    if assignee is not None:
        q += " AND t.assignee_user_id = :a AND t.status <> 'done'"
        p["a"] = str(assignee)
    if task_id is not None:
        q += " AND t.id = :t"
        p["t"] = str(task_id)
    return conn.execute(text(q + " ORDER BY t.created_at, l.created_at, l.id"), p).fetchall()


def _thread_state(conn, case_id, links) -> dict:
    """``{link id: open words or None}`` for thread links: a thread in a split is finished when its mark covers every
    message it holds now, and a thread in a second pass when its result is recorded."""
    from services.phone import review_marks
    keys = [r.target_id for r in links if r.target_type == "phone_thread"]
    marks = review_marks.marks(conn, case_id) if keys else {}
    totals = _totals(conn, case_id, keys) if keys else {}
    out = {}
    for r in links:
        if r.target_type != "phone_thread":
            continue
        a = r.source_anchor or {}
        if "second_pass" in a:
            out[r.id] = None if a.get("result") else "second pass not yet recorded"
            continue
        m = marks.get(r.target_id)
        n = int(totals.get(r.target_id, 0))
        if r.target_id not in totals:
            out[r.id] = "not in the case's current phones"
        elif m and n <= int(m.get("record_count") or 0):
            out[r.id] = None
        elif m:
            out[r.id] = "%s added since it was reviewed" % _plural(n - int(m.get("record_count") or 0), "message",
                                                                   "messages")
        else:
            out[r.id] = "not yet reviewed, %s" % _plural(n, "message", "messages")
    return out


def continue_work(conn, case_id, user, threads: list) -> dict:
    """The person's assigned reviews with their positions, then the casual threads the browser named that are still
    not finished. ``threads``: ``[{"thread": key, "record": event id or None}]``."""
    from services.phone import review_marks, streams
    links = _task_links(conn, case_id, assignee=user.id)
    state = _thread_state(conn, case_id, links)
    phones = _thread_phones(conn, case_id, [r.target_id for r in links if r.target_type == "phone_thread"])
    tasks: dict = {}
    for r in links:
        a = r.source_anchor or {}
        t = tasks.setdefault(str(r.task_id), {"task_id": str(r.task_id), "title": r.title, "total": 0, "open": 0,
                                              "kind": "readings" if "reading_recheck" in a else "threads",
                                              "phones": [], "items": [], "next": []})
        if r.target_type != "phone_thread":
            items = a.get("items") or []
            t["total"] += len(items)
            t["open"] += sum(1 for i in items if not i.get("result"))
            t["phones"].append(r.target_id)
            continue
        t["total"] += 1
        if state[r.id] is None:
            continue
        t["open"] += 1  # a thread gone with a replaced report stays open, as the hand-over note lists it
        ext = phones.get(r.target_id) or (r.target_id[len(streams.NO_THREAD_PREFIX):]
                                          if r.target_id.startswith(streams.NO_THREAD_PREFIX) else None)
        if ext is None:
            continue
        if ext not in t["phones"]:
            t["phones"].append(ext)
        row = {"thread_key": r.target_id, "title": r.label, "extraction_id": ext, "open": state[r.id],
               "position": a.get("position")}
        if a.get("position"):
            t["items"].append(row)
        elif not any(n["extraction_id"] == ext for n in t["next"]):
            t["next"].append(row)  # where to start, one per phone so each Phone summary can show its own
    mine = {i["thread_key"] for t in tasks.values() for i in t["items"] + t["next"]}
    wanted = {x["thread"]: x.get("record") for x in threads if x["thread"] not in mine}
    reading = []
    if wanted:
        titles = streams.thread_titles(conn, case_id, list(wanted))
        marks = review_marks.marks(conn, case_id)
        totals = _totals(conn, case_id, list(titles))
        for k, record in wanted.items():
            m = marks.get(k)
            if k not in titles or (m and int(totals.get(k, 0)) <= int(m.get("record_count") or 0)):
                continue  # not a current thread of the case, or fully reviewed: nothing to continue
            reading.append({"thread_key": k, **titles[k], "record": record})
    return {"assigned": list(tasks.values()), "reading": reading}


def _can_edit(db, case_id, user_id) -> bool:
    from postgres.models.case import Case
    from postgres.models.case_membership import CaseMembership
    from services.case_service import has_permission
    case = db.get(Case, uuid.UUID(str(case_id)))
    if case is not None and str(case.owner_user_id) == str(user_id):
        return True
    return has_permission(db.get(CaseMembership, (uuid.UUID(str(case_id)), uuid.UUID(str(user_id)))), "case", "edit")


def _safe(words) -> str:
    return (words or "(untitled)").replace("<", "&lt;")  # a note body refuses raw HTML; a thread title may hold "<"


def hand_over(db, case_id, task_id, *, to_user, user, note: str | None) -> dict:
    """Reassign a review task and attach a note listing the positions and the open items at this moment. The links
    keep their positions. Refused, with nothing changed, for someone who could not do the work: a person without
    edit access, or the first reviewer of anything in a second-person sample."""
    from services.system_log_service import LogOrigin, LogType, system_log_service
    from services.workspace_entry_service import WorkspaceEntryValidationError, create_entry
    conn = db.connection()
    task = conn.execute(text(
        "SELECT id, title, status, assignee_user_id FROM case_tasks WHERE id = :t AND case_id = :c AND deleted_at IS "
        "NULL FOR UPDATE"), {"t": str(task_id), "c": str(case_id)}).first()
    links = _task_links(conn, case_id, task_id=task_id) if task else []
    if not links:
        raise LookupError("This is not a review task in this case.")
    if task.status == "done":
        raise ReviewShareError("This review task is done, so there is nothing to hand over.")
    person = _members(conn, case_id, [to_user])[0]
    if str(task.assignee_user_id) == person["user_id"]:
        raise ReviewShareError("%s already has this review task." % person["name"])
    if not _can_edit(db, case_id, person["user_id"]):
        raise ReviewShareError("%s can only view this case, so they could not do this review." % person["name"])
    own = sum(1 for r in links if ((r.source_anchor or {}).get("first_mark") or {}).get("reviewed_by") ==
              person["user_id"])
    own += sum(1 for r in links for i in (r.source_anchor or {}).get("items") or []
               if (i.get("first") or {}).get("by_id") == person["user_id"])
    if own:
        raise ReviewShareError("%s made the first review of %s in this sample, and a person never re-checks their own."
                               % (person["name"], _plural(own, "item", "items")))
    state = _thread_state(conn, case_id, links)
    positions, opened, total = [], [], 0
    for r in links:
        a = r.source_anchor or {}
        if r.target_type == "phone_thread":
            total += 1
            if state[r.id] is not None:
                opened.append("%s: %s" % (_safe(r.label), state[r.id]))
            if a.get("position"):
                positions.append("%s: %s" % (_safe(r.label), _position_words(a["position"])))
        for i in a.get("items") or []:
            total += 1
            if not i.get("result"):
                opened.append("%s: not yet re-checked" % _safe(i.get("sentence")))
    me, day = user.name or user.email, datetime.now(timezone.utc).date().isoformat()
    lines = ["Handed over by %s to %s on %s. This list was made by Loupe at that moment." % (me, person["name"], day),
             "", "Task: %s. %s of %s still open." % (_safe(task.title), _n(len(opened)), _n(total)), "", "**Positions**"]
    lines += ["- %s" % p for p in positions] or ["No reading position was saved."]
    lines += ["", "**Open items**"] + (["- %s" % o for o in opened] or ["Nothing is open."])
    note = (note or "").strip()
    if note:
        lines += ["", "**Note from %s**" % me, _safe(note)]
    entry_id = uuid.uuid4()
    title = "Handover: %s" % task.title
    conn.execute(text(
        "UPDATE case_tasks SET assignee_user_id = :a, updated_by_user_id = :u, updated_at = now() WHERE id = :t"),
        {"a": person["user_id"], "u": user.id, "t": str(task_id)})
    conn.execute(text(
        "UPDATE case_task_links l SET source_anchor = l.source_anchor || CAST(:p AS jsonb), updated_at = now() WHERE "
        "l.task_id = :t AND " + _IS_REVIEW),
        {"p": json.dumps({"assigned_to": person["user_id"], "assigned_to_name": person["name"]}), "t": str(task_id)})
    conn.execute(text(
        "INSERT INTO case_task_links (id, task_id, case_id, target_type, target_id, label, source_anchor, "
        "created_by_user_id, created_at, updated_at) VALUES (:i, :t, :c, 'entry', :k, :l, CAST(:a AS jsonb), :u, now(), "
        "now())"),
        {"i": uuid.uuid4(), "t": str(task_id), "c": str(case_id), "k": str(entry_id), "l": title[:512],
         "a": json.dumps({"handover": True, "from": str(task.assignee_user_id) if task.assignee_user_id else None,
                          "to": person["user_id"]}), "u": user.id})
    system_log_service.log(log_type=LogType.CASE_OPERATION, origin=LogOrigin.BACKEND,
                           action="Handed over a phone review task",
                           details={"case_id": str(case_id), "task_id": str(task_id), "to": person["user_id"],
                                    "note_id": str(entry_id), "open_items": len(opened)},
                           user=user.email, success=True, db=db)
    try:
        create_entry(db, case_id=uuid.UUID(str(case_id)), current_user=user, entry_id=entry_id, entry_type="note",
                     title=title[:255], body="\n".join(lines), tags=["handover"],
                     links=[{"target_type": "task", "target_id": str(task_id)}])  # commits the whole hand-over
    except WorkspaceEntryValidationError as exc:
        raise ReviewShareError(str(exc)) from exc
    return {"task_id": str(task_id), "note_id": str(entry_id), "reviewer": person, "open_items": len(opened),
            "positions": len(positions),
            "words": "Handed over to %s, with a note listing %s and %s." % (
                person["name"], _plural(len(positions), "position", "positions"),
                _plural(len(opened), "open item", "open items"))}
