"""Sharing a phone review across people and knowing what is left (07 J-13 steps 1, 5 and 6; failure state).

- **Split for review** (step 1): the threads under the current Conversations filter go into Workspace tasks
  (``case_tasks``), one per chosen member, either thread by thread or person by person (every one-to-one thread with
  the same person goes to the same reviewer; a group thread is its own unit). Each task links its threads with
  ``case_task_links`` rows of target type ``phone_thread`` whose anchor carries ``review_split``. The marks stay
  where ``review_marks`` keeps them, so a reviewer's mark on a thread in their task counts in the one coverage and
  the task's progress is read from the marks, never stored twice.
- **Second pass** (step 5): a random sample (10% by default, the seed recorded) of fully reviewed threads, each
  first reviewed by someone other than the second reviewer, in one task assigned to that person. The second
  reviewer's result (agrees, or disagrees with a note) is stored on the sample's link beside a copy of the first
  mark; the first mark is never touched.
- **"[name] is also reviewing this thread."**: presence rows in the existing ``presence_sessions`` table, one per
  person and open thread, refreshed by a heartbeat every ``HEARTBEAT_SECONDS`` and expired after
  ``PRESENCE_TTL_SECONDS``.
- **Coverage summary** (step 6): searches run and terms used (``phone_search_runs``, and the case's keyword lists
  when that table exists), who reviewed what, what was not reviewed, the splits and the second-pass results. Its
  thread counts are the marks' counts (``streams.thread_list``), so the summary always equals the marks.
"""
from __future__ import annotations

import hashlib
import json
import math
import random
import secrets
import uuid
from datetime import datetime, timezone

from sqlalchemy import text

SPLIT_BY = ("thread", "person")
SECOND_PASS_PERCENT = 10
HEARTBEAT_SECONDS = 45  # under 1 request per 30 s per open thread (brief C): 1.33 a minute
PRESENCE_TTL_SECONDS = 100  # two missed beats and the person is gone
PRESENCE_PREFIX = "pt_"
PRESENCE_DEVICE = "phone_thread:"


class ReviewShareError(ValueError):
    pass


class SplitChanged(ReviewShareError):
    """The threads under the filter changed between the counts shown and the split being made."""


def _n(v) -> str:
    return "{:,}".format(int(v))


def _plural(n, one, many):
    return "%s %s" % (_n(n), one if n == 1 else many)


# ---- split for review -----------------------------------------------------------------------------------------------

def _members(conn, case_id, user_ids) -> list:
    """The chosen people, in the order given, each an active owner or member of the case."""
    out = []
    for uid in user_ids:
        row = conn.execute(text(
            "SELECT u.id, coalesce(u.name, u.email) AS name FROM users u JOIN cases c ON c.id = :c WHERE u.id = :u "
            "AND u.is_active AND (c.owner_user_id = u.id OR EXISTS (SELECT 1 FROM case_memberships m WHERE "
            "m.case_id = c.id AND m.user_id = u.id))"), {"c": str(case_id), "u": str(uid)}).first()
        if row is None:
            raise ReviewShareError("Each reviewer must be an active member of this case.")
        if any(m["user_id"] == str(row.id) for m in out):
            raise ReviewShareError("Each reviewer can be chosen once.")
        out.append({"user_id": str(row.id), "name": row.name})
    if not out:
        raise ReviewShareError("Choose at least one person to review.")
    return out


def _person_of(thread) -> str | None:
    others = [p.get("identity_key") for p in thread.get("participants") or [] if not p.get("is_owner")]
    others = [k for k in others if k]
    if thread.get("thread_kind") == "none" or len(set(others)) != 1 or (thread.get("participant_count") or 0) > 2:
        return None
    return others[0]


def _person_name(thread) -> str | None:
    for p in thread.get("participants") or []:
        if not p.get("is_owner"):
            return p.get("name") or ((p.get("identifier") or {}).get("display"))
    return None


def plan_split(conn, f, *, by: str, reviewers: list, only_not_reviewed: bool = True) -> dict:
    """The split the counts dialog shows, and exactly what ``create_split`` makes: the threads under ``f`` (all of
    them, or only those not yet fully reviewed), kept together by thread or by person, shared among the reviewers
    so their message counts are as even as whole units allow (largest unit first to the least loaded)."""
    from services.phone import streams
    if by not in SPLIT_BY:
        raise ReviewShareError("Split by thread or by person.")
    people = _members(conn, f.case_id, reviewers)
    listed = streams.thread_list(conn, f, sort="name")["items"]
    reviewed = [t for t in listed if t["review"] and not t["review"]["added_since"]]
    threads = [t for t in listed if not (only_not_reviewed and t["review"] and not t["review"]["added_since"])]
    units: dict = {}
    for t in threads:
        person = _person_of(t) if by == "person" else None
        key = ("person", person) if person else ("thread", t["thread_key"])
        units.setdefault(key, []).append(t)
    ordered = sorted(units.items(), key=lambda kv: (-sum(x["event_count_total"] for x in kv[1]), kv[0][1]))
    parts = [{"reviewer": p, "threads": [], "messages": 0, "people": set()} for p in people]
    for (kind, ident), ts in ordered:
        part = min(parts, key=lambda p: (p["messages"], len(p["threads"]), parts.index(p)))
        part["threads"] += ts
        part["messages"] += sum(x["event_count_total"] for x in ts)
        if kind == "person":
            part["people"].add(ident)
    out_parts = []
    for i, p in enumerate(parts, 1):
        out_parts.append({
            "part": i, "reviewer": p["reviewer"], "threads": len(p["threads"]), "messages": p["messages"],
            "people": len(p["people"]), "thread_keys": [t["thread_key"] for t in p["threads"]],
            "words": "%s: %s, %s%s" % (p["reviewer"]["name"], _plural(len(p["threads"]), "thread", "threads"),
                                       _plural(p["messages"], "message", "messages"),
                                       (", " + _plural(len(p["people"]), "person", "people")) if by == "person"
                                       else "")})
    skipped = len(reviewed) if only_not_reviewed else 0
    total_msgs = sum(t["event_count_total"] for t in threads)
    words = "%s into %s, by %s" % (_plural(len(threads), "thread", "threads"),
                                   _plural(len(parts), "task", "tasks"), by)
    if skipped:
        words += "; %s already reviewed %s left out" % (_plural(skipped, "thread", "threads"),
                                                         "is" if skipped == 1 else "are")
    empty = [p for p in out_parts if not p["threads"]]
    return {"by": by, "only_not_reviewed": only_not_reviewed, "threads_in_filter": len(listed),
            "threads": len(threads), "messages": total_msgs, "already_reviewed_left_out": skipped,
            "parts": out_parts, "words": words + ".",
            "warning": ("%s would get no threads: there are fewer units than reviewers." %
                        _plural(len(empty), "person", "people")) if empty else None,
            "_threads": {t["thread_key"]: t for t in threads}}


def create_split(db, f, *, by: str, reviewers: list, user, expect_threads: int, only_not_reviewed: bool = True,
                 scope_words: str | None = None) -> dict:
    """Make the tasks of ``plan_split`` in one transaction. ``expect_threads`` is the count the person saw; if the
    threads changed since, nothing is made (``SplitChanged``) and the dialog shows the new counts."""
    from services.system_log_service import LogOrigin, LogType, system_log_service
    conn = db.connection()
    plan = plan_split(conn, f, by=by, reviewers=reviewers, only_not_reviewed=only_not_reviewed)
    if plan["threads"] != int(expect_threads):
        raise SplitChanged("The threads changed since the counts were shown: %s now. Check the split again."
                           % _n(plan["threads"]))
    if not plan["threads"]:
        raise ReviewShareError("There are no threads to split under this filter.")
    split_id = str(uuid.uuid4())
    made_at = datetime.now(timezone.utc).isoformat()
    n_parts = len([p for p in plan["parts"] if p["threads"]])
    tasks, i = [], 0
    for part in plan["parts"]:
        if not part["threads"]:
            continue
        i += 1
        tid = uuid.uuid4()
        title = "Review phone conversations, part %d of %d (by %s)" % (i, n_parts, by)
        desc = ("Split for review by %s on %s: %s. Mark each thread reviewed in Conversations (m); the marks count "
                "in the case's review coverage." % (user.name or user.email, made_at[:10], part["words"]))
        if scope_words:
            desc += " Filter: %s." % scope_words
        conn.execute(text(
            "INSERT INTO case_tasks (id, case_id, title, description, status, priority, assignee_user_id, "
            "created_by_user_id, updated_by_user_id, created_at, updated_at) VALUES (:i, :c, :t, :d, 'todo', "
            "'standard', :a, :u, :u, now(), now())"),
            {"i": tid, "c": f.case_id, "t": title, "d": desc, "a": part["reviewer"]["user_id"], "u": user.id})
        rows = []
        for key in part["thread_keys"]:
            t = plan["_threads"][key]
            anchor = {"review_split": split_id, "by": by, "part": i, "parts": n_parts,
                      "assigned_to": part["reviewer"]["user_id"], "assigned_to_name": part["reviewer"]["name"],
                      "record_count": int(t["event_count_total"]), "extraction_id": t["phone"]["extraction_id"],
                      "person_key": _person_of(t) if by == "person" else None, "split_at": made_at}
            rows.append({"i": uuid.uuid4(), "t": tid, "c": f.case_id, "k": key, "l": (t["title"] or "")[:512],
                         "a": json.dumps(anchor), "u": user.id})
        conn.execute(text(
            "INSERT INTO case_task_links (id, task_id, case_id, target_type, target_id, label, source_anchor, "
            "created_by_user_id, created_at, updated_at) VALUES (:i, :t, :c, 'phone_thread', :k, :l, "
            "CAST(:a AS jsonb), :u, now(), now())"), rows)
        tasks.append({"task_id": str(tid), "title": title, "reviewer": part["reviewer"], "threads": part["threads"],
                      "messages": part["messages"], "people": part["people"]})
    system_log_service.log(log_type=LogType.CASE_OPERATION, origin=LogOrigin.BACKEND,
                           action="Split phone conversations for review",
                           details={"case_id": str(f.case_id), "split_id": split_id, "by": by,
                                    "tasks": len(tasks), "threads": plan["threads"]},
                           user=user.email, success=True, db=db)
    db.commit()
    return {"split_id": split_id, "by": by, "tasks": tasks, "threads": plan["threads"],
            "messages": plan["messages"],
            "words": "Made %s for %s." % (_plural(len(tasks), "review task", "review tasks"),
                                         _plural(plan["threads"], "thread", "threads"))}


def assignments(conn, case_id, marks: dict, totals: dict) -> list:
    """Every open split task with its reviewer and its progress read from the marks (a thread counts as reviewed
    only when its mark covers every message it holds now)."""
    rows = conn.execute(text(
        "SELECT t.id, t.title, t.status, t.assignee_user_id, coalesce(u.name, u.email) AS who, l.target_id, "
        "l.source_anchor->>'review_split' AS split FROM case_task_links l JOIN case_tasks t ON t.id = l.task_id "
        "LEFT JOIN users u ON u.id = t.assignee_user_id WHERE l.case_id = :c AND l.target_type = 'phone_thread' "
        "AND t.deleted_at IS NULL AND l.source_anchor ? 'review_split' ORDER BY t.created_at, t.title"),
        {"c": str(case_id)}).fetchall()
    out: dict = {}
    for r in rows:
        a = out.setdefault(str(r.id), {"task_id": str(r.id), "title": r.title, "status": r.status,
                                       "reviewer": r.who, "reviewer_id": str(r.assignee_user_id)
                                       if r.assignee_user_id else None, "split_id": r.split,
                                       "threads": 0, "reviewed": 0, "partly_reviewed": 0, "not_reviewed": 0,
                                       "not_in_case": 0})
        a["threads"] += 1
        m = marks.get(r.target_id)
        if r.target_id not in totals:
            a["not_in_case"] += 1  # a thread of a replaced report the marks could not carry
        elif m and int(totals[r.target_id]) <= int(m.get("record_count") or 0):
            a["reviewed"] += 1
        elif m:
            a["partly_reviewed"] += 1
        else:
            a["not_reviewed"] += 1
    for a in out.values():
        a["words"] = "%s (%s): %s of %s reviewed" % (a["title"], a["reviewer"] or "nobody assigned",
                                                       _n(a["reviewed"]), _plural(a["threads"], "thread", "threads"))
    return list(out.values())


def after_mark(conn, case_id, thread_key: str) -> None:
    """A mark moves the split tasks holding the thread on: 'todo' to 'in_progress', and to 'done' when every thread
    in the task is fully reviewed. A task a person closed or reopened by hand is left as they set it once done."""
    from services.phone import review_marks
    tasks = [r[0] for r in conn.execute(text(
        "SELECT DISTINCT l.task_id FROM case_task_links l JOIN case_tasks t ON t.id = l.task_id WHERE "
        "l.case_id = :c AND l.target_type = 'phone_thread' AND l.target_id = :k AND t.deleted_at IS NULL AND "
        "t.status <> 'done' AND l.source_anchor ? 'review_split'"), {"c": str(case_id), "k": thread_key})]
    if not tasks:
        return
    marks = review_marks.marks(conn, case_id)
    for tid in tasks:
        keys = [r[0] for r in conn.execute(text(
            "SELECT target_id FROM case_task_links WHERE task_id = :t AND target_type = 'phone_thread'"),
            {"t": tid})]
        totals = _totals(conn, case_id, keys)
        done = all(k in marks and int(totals.get(k, 0)) <= int(marks[k].get("record_count") or 0) for k in keys)
        conn.execute(text("UPDATE case_tasks SET status = CAST(:s AS varchar), completed_at = CASE WHEN CAST(:s AS varchar) = 'done' THEN now() ELSE "
                          "NULL END, updated_at = now() WHERE id = :t"),
                     {"s": "done" if done else "in_progress", "t": tid})


def _totals(conn, case_id, keys) -> dict:
    """The message count each thread holds now (the active report's thread), the count a mark is compared with."""
    from services.phone.streams import NO_THREAD_PREFIX
    out = {r.thread_key: int(r.event_count or 0) for r in conn.execute(text(
        "SELECT thread_key, event_count FROM pv_thread WHERE case_id = :c AND thread_key = ANY(:k)"),
        {"c": str(case_id), "k": [k for k in keys if not k.startswith(NO_THREAD_PREFIX)]})}
    loose = [k[len(NO_THREAD_PREFIX):] for k in keys if k.startswith(NO_THREAD_PREFIX)]
    if loose:
        for ext, n in conn.execute(text(
                "SELECT ev.extraction_id::text, count(*) FROM phone_comm_events ev JOIN phone_interpretation_state st "
                "ON st.extraction_id = ev.extraction_id AND st.generation = ev.generation JOIN phone_extractions e ON "
                "e.id = ev.extraction_id AND e.standing = 'active' WHERE e.case_id = :c AND ev.thread_key IS NULL "
                "AND ev.extraction_id::text = ANY(:e) GROUP BY 1"), {"c": str(case_id), "e": loose}):
            out[NO_THREAD_PREFIX + ext] = int(n)
    return out


# ---- second pass ----------------------------------------------------------------------------------------------------

def start_second_pass(db, case_id, *, reviewer_id, user, percent: int = SECOND_PASS_PERCENT,
                      seed: int | None = None) -> dict:
    """Sample ``percent`` of the case's fully reviewed threads that ``reviewer_id`` did not review first, with a
    recorded seed (the same seed over the same threads draws the same sample), into one task for that person."""
    from services.phone import review_marks
    from services.phone.filters import StreamFilter
    from services.phone import streams
    from services.system_log_service import LogOrigin, LogType, system_log_service
    conn = db.connection()
    if not 1 <= int(percent) <= 100:
        raise ReviewShareError("The sample is between 1% and 100% of the reviewed threads.")
    person = _members(conn, case_id, [reviewer_id])[0]
    items = streams.thread_list(conn, StreamFilter(case_id=str(case_id)), sort="name")["items"]
    marks = review_marks.marks(conn, case_id)
    reviewed = [t for t in items if t["review"] and not t["review"]["added_since"]]
    eligible = sorted((t for t in reviewed if (marks.get(t["thread_key"]) or {}).get("reviewed_by")
                       != person["user_id"]), key=lambda t: t["thread_key"])
    if not eligible:
        raise ReviewShareError(
            "No fully reviewed thread was first reviewed by someone other than %s, so there is nothing to sample."
            % person["name"] if reviewed else "No thread is fully reviewed yet, so there is nothing to sample.")
    seed = int(seed) if seed is not None else secrets.randbits(31)
    k = max(1, math.ceil(len(eligible) * int(percent) / 100))
    sample = random.Random(seed).sample(eligible, k)
    pass_id = str(uuid.uuid4())
    made_at = datetime.now(timezone.utc).isoformat()
    tid = uuid.uuid4()
    title = "Second-pass review: %s of %s reviewed threads (%d%% sample)" % (_n(k), _n(len(eligible)), int(percent))
    desc = ("A random %d%% sample (seed %d) of the %s fully reviewed threads that %s did not review first, drawn by "
            "%s on %s. For each thread, record whether you agree with the first review; a disagreement needs a "
            "note. The first review is kept as it is.%s" % (
                int(percent), seed, _n(len(eligible)), person["name"], user.name or user.email, made_at[:10],
                (" %s reviewed by %s first %s left out." % (_plural(len(reviewed) - len(eligible), "thread",
                                                                     "threads"), person["name"],
                                                             "is" if len(reviewed) - len(eligible) == 1 else "are"))
                if len(reviewed) > len(eligible) else ""))
    conn.execute(text(
        "INSERT INTO case_tasks (id, case_id, title, description, status, priority, assignee_user_id, "
        "created_by_user_id, updated_by_user_id, created_at, updated_at) VALUES (:i, :c, :t, :d, 'todo', 'standard', "
        ":a, :u, :u, now(), now())"),
        {"i": tid, "c": str(case_id), "t": title, "d": desc, "a": person["user_id"], "u": user.id})
    rows = []
    for t in sample:
        m = marks[t["thread_key"]]
        anchor = {"second_pass": pass_id, "seed": seed, "percent": int(percent), "eligible": len(eligible),
                  "reviewed": len(reviewed), "assigned_to": person["user_id"], "assigned_to_name": person["name"],
                  "drawn_at": made_at,
                  "first_mark": {k2: m.get(k2) for k2 in ("reviewed_by", "reviewed_by_name", "reviewed_at",
                                                           "record_count")},
                  "result": None, "earlier_results": []}
        rows.append({"i": uuid.uuid4(), "t": tid, "c": str(case_id), "k": t["thread_key"],
                     "l": (t["title"] or "")[:512], "a": json.dumps(anchor), "u": user.id})
    conn.execute(text(
        "INSERT INTO case_task_links (id, task_id, case_id, target_type, target_id, label, source_anchor, "
        "created_by_user_id, created_at, updated_at) VALUES (:i, :t, :c, 'phone_thread', :k, :l, CAST(:a AS jsonb), "
        ":u, now(), now())"), rows)
    system_log_service.log(log_type=LogType.CASE_OPERATION, origin=LogOrigin.BACKEND,
                           action="Drew a second-pass review sample",
                           details={"case_id": str(case_id), "pass_id": pass_id, "seed": seed, "percent": int(percent),
                                    "sample": k, "eligible": len(eligible)},
                           user=user.email, success=True, db=db)
    db.commit()
    return {"pass_id": pass_id, "task_id": str(tid), "title": title, "seed": seed, "percent": int(percent),
            "sample": k, "eligible": len(eligible), "reviewed": len(reviewed), "reviewer": person,
            "thread_keys": [t["thread_key"] for t in sample],
            "words": "Drew %s of %s for %s (seed %d)." % (_n(k), _plural(len(eligible), "reviewed thread",
                                                                          "reviewed threads"), person["name"], seed)}


def _open_samples(conn, case_id, thread_key=None):
    q = ("SELECT l.id, l.task_id, l.target_id, l.source_anchor, t.title FROM case_task_links l JOIN case_tasks t ON "
         "t.id = l.task_id WHERE l.case_id = :c AND l.target_type = 'phone_thread' AND t.deleted_at IS NULL AND "
         "l.source_anchor ? 'second_pass'")
    p = {"c": str(case_id)}
    if thread_key is not None:
        q += " AND l.target_id = :k"
        p["k"] = thread_key
    return conn.execute(text(q + " ORDER BY l.created_at"), p).fetchall()


def record_second_pass(db, case_id, *, task_id, thread_key: str, user, agrees: bool, note: str | None) -> dict:
    """The second reviewer's result on one sampled thread, kept beside the first mark (which is not changed). A
    result recorded again keeps the earlier one in ``earlier_results``."""
    from services.system_log_service import LogOrigin, LogType, system_log_service
    conn = db.connection()
    row = conn.execute(text(
        "SELECT l.id, l.source_anchor FROM case_task_links l JOIN case_tasks t ON t.id = l.task_id WHERE "
        "l.task_id = :t AND l.case_id = :c AND l.target_type = 'phone_thread' AND l.target_id = :k AND "
        "t.deleted_at IS NULL AND l.source_anchor ? 'second_pass'"),
        {"t": str(task_id), "c": str(case_id), "k": thread_key}).first()
    if row is None:
        raise LookupError("This thread is not in that second-pass sample.")
    anchor = dict(row.source_anchor or {})
    first = anchor.get("first_mark") or {}
    if first.get("reviewed_by") == str(user.id):
        raise ReviewShareError("A second pass is made by someone other than the first reviewer (%s)."
                               % (first.get("reviewed_by_name") or "a person"))
    note = (note or "").strip() or None
    if not agrees and not note:
        raise ReviewShareError("Say why you disagree with the first review.")
    earlier = list(anchor.get("earlier_results") or [])
    if anchor.get("result"):
        earlier.append(anchor["result"])
    anchor["result"] = {"agrees": bool(agrees), "note": note, "by": str(user.id), "by_name": user.name or user.email,
                        "at": datetime.now(timezone.utc).isoformat()}
    anchor["earlier_results"] = earlier
    conn.execute(text("UPDATE case_task_links SET source_anchor = CAST(:a AS jsonb), updated_at = now() WHERE id = :i"),
                 {"a": json.dumps(anchor), "i": row.id})
    left = conn.execute(text(
        "SELECT count(*) FROM case_task_links WHERE task_id = :t AND target_type = 'phone_thread' AND id <> :i AND "
        "(source_anchor->'result' IS NULL OR source_anchor->'result' = 'null'::jsonb)"),
        {"t": str(task_id), "i": row.id}).scalar()
    conn.execute(text("UPDATE case_tasks SET status = CAST(:s AS varchar), completed_at = CASE WHEN CAST(:s AS varchar) = 'done' THEN now() ELSE NULL "
                      "END, updated_at = now() WHERE id = :t AND status <> 'done'"),
                 {"s": "done" if not left else "in_progress", "t": str(task_id)})
    system_log_service.log(log_type=LogType.CASE_OPERATION, origin=LogOrigin.BACKEND,
                           action="Recorded a second-pass review result",
                           details={"case_id": str(case_id), "task_id": str(task_id), "thread_key": thread_key,
                                    "agrees": bool(agrees)}, user=user.email, success=True, db=db)
    db.commit()
    return second_pass_words(anchor)


def second_pass_words(anchor: dict) -> dict:
    first = anchor.get("first_mark") or {}
    res = anchor.get("result")
    if not res:
        words = "In a second-pass sample for %s; no result yet." % (anchor.get("assigned_to_name") or "a person")
    elif res["agrees"]:
        words = "Second pass by %s: agrees with %s's review." % (res["by_name"], first.get("reviewed_by_name") or
                                                                  "the first")
    else:
        words = "Second pass by %s: disagrees with %s's review. Note: %s" % (
            res["by_name"], first.get("reviewed_by_name") or "the first", res["note"])
    return {"first": first, "result": res, "earlier_results": len(anchor.get("earlier_results") or []),
            "assigned_to": anchor.get("assigned_to"), "assigned_to_name": anchor.get("assigned_to_name"),
            "seed": anchor.get("seed"), "percent": anchor.get("percent"), "words": words}


def thread_review_state(conn, case_id, thread_key: str, user_id) -> dict:
    """For the open thread's header: its split task and its second-pass samples, each with its words."""
    tasks = [{"task_id": str(r.task_id), "title": r.title, "assigned_to_name": (r.source_anchor or {}).get(
        "assigned_to_name"), "mine": (r.source_anchor or {}).get("assigned_to") == str(user_id)}
        for r in conn.execute(text(
            "SELECT l.task_id, l.source_anchor, t.title FROM case_task_links l JOIN case_tasks t ON t.id = l.task_id "
            "WHERE l.case_id = :c AND l.target_type = 'phone_thread' AND l.target_id = :k AND t.deleted_at IS NULL "
            "AND l.source_anchor ? 'review_split' ORDER BY l.created_at"), {"c": str(case_id), "k": thread_key})]
    samples = []
    for r in _open_samples(conn, case_id, thread_key):
        w = second_pass_words(r.source_anchor or {})
        w.update({"task_id": str(r.task_id), "title": r.title,
                  "mine": (r.source_anchor or {}).get("assigned_to") == str(user_id)})
        samples.append(w)
    return {"thread_key": thread_key, "tasks": tasks, "second_pass": samples}


# ---- presence: "[name] is also reviewing this thread." --------------------------------------------------------------

def _session_id(case_id, user_id, thread_key) -> str:
    h = hashlib.sha256(("%s|%s|%s" % (case_id, user_id, thread_key)).encode()).hexdigest()
    return PRESENCE_PREFIX + h[:40]


def heartbeat(db, case_id, thread_key: str, user, *, leaving: bool = False) -> dict:
    """Say this person has the thread open (or has left it), and return who else has it open now."""
    conn = db.connection()
    sid = _session_id(case_id, user.id, thread_key)
    if leaving:
        conn.execute(text("DELETE FROM presence_sessions WHERE session_id = :s"), {"s": sid})
    else:
        conn.execute(text(
            "INSERT INTO presence_sessions (session_id, case_id, user_id, username, device_info, started_at, "
            "last_active, created_at, updated_at) VALUES (:s, :c, :u, :n, :d, now(), now(), now(), now()) "
            "ON CONFLICT (session_id) DO UPDATE SET last_active = now(), updated_at = now(), username = :n"),
            {"s": sid, "c": str(case_id), "u": str(user.id), "n": user.name or user.email,
             "d": PRESENCE_DEVICE + thread_key})
    conn.execute(text(
        "DELETE FROM presence_sessions WHERE case_id = :c AND session_id LIKE 'pt\\_%' AND last_active < now() - "
        "make_interval(secs => :ttl * 6)"), {"c": str(case_id), "ttl": PRESENCE_TTL_SECONDS})
    others = [r.username for r in conn.execute(text(
        "SELECT DISTINCT ON (user_id) user_id, username FROM presence_sessions WHERE case_id = :c AND device_info = :d "
        "AND user_id <> :u AND session_id LIKE 'pt\\_%' AND last_active >= now() - make_interval(secs => :ttl) "
        "ORDER BY user_id, last_active DESC"),
        {"c": str(case_id), "d": PRESENCE_DEVICE + thread_key, "u": str(user.id), "ttl": PRESENCE_TTL_SECONDS})]
    db.commit()
    others.sort()
    return {"thread_key": thread_key, "others": others, "words": also_reviewing_words(others),
            "next_in_seconds": HEARTBEAT_SECONDS}


def also_reviewing_words(names: list) -> str | None:
    if not names:
        return None
    if len(names) == 1:
        return "%s is also reviewing this thread." % names[0]
    return "%s and %s are also reviewing this thread." % (", ".join(names[:-1]), names[-1])


# ---- searches run ---------------------------------------------------------------------------------------------------

def record_search(db, case_id, user, query: str, *, exact: bool, surface: str, hits: int | None) -> None:
    """One more run of a search on the case's phone records, by this person. Never fails the search itself."""
    q = (query or "").strip()
    if not q:
        return
    try:
        with db.begin_nested():
            db.connection().execute(text(
                "INSERT INTO phone_search_runs (id, case_id, user_id, query, query_hash, exact, surface, run_count, "
                "last_hits, first_run_at, last_run_at) VALUES (:i, :c, :u, :q, :h, :x, :s, 1, :n, now(), now()) "
                "ON CONFLICT (case_id, user_id, query_hash, exact, surface) DO UPDATE SET run_count = "
                "phone_search_runs.run_count + 1, last_hits = EXCLUDED.last_hits, last_run_at = now()"),
                {"i": uuid.uuid4(), "c": str(case_id), "u": str(user.id), "q": q[:2000],
                 "h": hashlib.sha256(q.encode()).hexdigest(), "x": bool(exact), "s": surface,
                 "n": None if hits is None else int(hits)})
        db.commit()
    except Exception:  # noqa: BLE001 - a search is never refused because its record could not be written
        db.rollback()


def searches(conn, case_id) -> list:
    rows = conn.execute(text(
        "SELECT r.query, r.exact, r.surface, sum(r.run_count) OVER w AS runs_all, r.run_count, r.last_hits, "
        "r.first_run_at, r.last_run_at, coalesce(u.name, u.email, 'a former member') AS who FROM phone_search_runs r "
        "LEFT JOIN users u ON u.id = r.user_id WHERE r.case_id = :c WINDOW w AS (PARTITION BY r.query_hash, r.exact) "
        "ORDER BY r.last_run_at DESC"), {"c": str(case_id)}).fetchall()
    out: dict = {}
    for r in rows:
        s = out.setdefault((r.query, r.exact), {"query": r.query, "exact": r.exact, "runs": 0, "people": [],
                                                "surfaces": [], "last_hits": r.last_hits,
                                                "first_run_at": r.first_run_at.isoformat(),
                                                "last_run_at": r.last_run_at.isoformat()})
        s["runs"] += int(r.run_count)
        if r.who not in s["people"]:
            s["people"].append(r.who)
        if r.surface not in s["surfaces"]:
            s["surfaces"].append(r.surface)
        s["first_run_at"] = min(s["first_run_at"], r.first_run_at.isoformat())
    return list(out.values())


def keyword_lists(conn, case_id) -> list:
    """The case's saved keyword lists and their terms (cb-keywords E): ``services.search.keyword_lists.for_coverage``
    when it is installed, else the table read directly; until either exists there are none."""
    try:
        from services.search.keyword_lists import for_coverage
    except ImportError:
        for_coverage = None
    if for_coverage is not None:
        out = []
        for kl in for_coverage(conn, case_id) or []:
            terms = [t if isinstance(t, str) else (t or {}).get("term") for t in kl.get("terms") or []]
            out.append({**kl, "name": kl.get("name"), "terms": [t for t in terms if t]})
        return out
    exists = conn.execute(text("SELECT to_regclass('public.phone_keyword_lists')")).scalar()
    if not exists:
        return []
    cols = {r[0] for r in conn.execute(text(
        "SELECT column_name FROM information_schema.columns WHERE table_name = 'phone_keyword_lists'"))}
    if not {"case_id", "name", "terms"} <= cols:
        return []
    deleted = " AND deleted_at IS NULL" if "deleted_at" in cols else ""
    out = []
    for r in conn.execute(text("SELECT name, terms FROM phone_keyword_lists WHERE case_id = :c%s ORDER BY name"
                               % deleted), {"c": str(case_id)}):
        terms = r.terms if isinstance(r.terms, list) else []
        out.append({"name": r.name, "terms": [t if isinstance(t, str) else (t or {}).get("term") for t in terms]})
    return out


# ---- coverage summary -----------------------------------------------------------------------------------------------

def coverage(conn, case_id, *, phones=None, thread_keys=None) -> dict:
    """The review coverage summary (07 J-13 step 6): the marks' own counts over the case (or the given phones, or
    the given threads, as an export prints it), who reviewed what, every thread not yet reviewed, the splits, the
    second-pass results, the searches run and the terms used. Nothing is clipped: every list is whole."""
    from services.phone import review_marks, streams
    from services.phone.filters import StreamFilter
    tl = streams.thread_list(conn, StreamFilter(case_id=str(case_id), phones=[str(p) for p in phones or []]),
                             sort="name")
    items = tl["items"]
    if thread_keys is not None:
        wanted = set(thread_keys)
        items = [t for t in items if t["thread_key"] in wanted]
    marks = review_marks.marks(conn, case_id)
    reviewed = [t for t in items if t["review"] and not t["review"]["added_since"]]
    partly = [t for t in items if t["review"] and t["review"]["added_since"]]
    never = [t for t in items if not t["review"]]
    by_person: dict = {}
    for t in reviewed + partly:
        who = t["review"]["by"] or "a person"
        p = by_person.setdefault(who, {"name": who, "reviewed": 0, "partly_reviewed": 0, "messages_at_review": 0})
        p["reviewed" if not t["review"]["added_since"] else "partly_reviewed"] += 1
        p["messages_at_review"] += t["review"]["record_count"]
    totals = {t["thread_key"]: t["event_count_total"] for t in tl["items"]}
    shown = {t["thread_key"] for t in items}
    splits = [a for a in assignments(conn, case_id, marks, totals)]
    samples: dict = {}
    for r in _open_samples(conn, case_id):
        if r.target_id not in shown:
            continue
        a = r.source_anchor or {}
        s = samples.setdefault(a.get("second_pass"), {
            "pass_id": a.get("second_pass"), "task_id": str(r.task_id), "title": r.title, "seed": a.get("seed"),
            "percent": a.get("percent"), "eligible": a.get("eligible"), "reviewer": a.get("assigned_to_name"),
            "sampled": 0, "agrees": 0, "disagrees": 0, "pending": 0, "disagreements": []})
        s["sampled"] += 1
        res = a.get("result")
        if not res:
            s["pending"] += 1
        elif res.get("agrees"):
            s["agrees"] += 1
        else:
            s["disagrees"] += 1
            title = next((t["title"] for t in items if t["thread_key"] == r.target_id), r.target_id)
            s["disagreements"].append({"thread_key": r.target_id, "title": title, "by": res.get("by_name"),
                                       "first_by": (a.get("first_mark") or {}).get("reviewed_by_name"),
                                       "note": res.get("note")})
    runs = searches(conn, case_id)
    lists = keyword_lists(conn, case_id)
    terms = sorted({s["query"] for s in runs} | {t for kl in lists for t in kl["terms"] if t}, key=str.lower)
    counts = {"threads": len(items), "reviewed": len(reviewed), "partly_reviewed": len(partly),
              "not_reviewed": len(items) - len(reviewed), "never_reviewed": len(never)}

    def row(t):
        return {"thread_key": t["thread_key"], "title": t["title"], "phone": t["phone"]["label"],
                "messages": t["event_count_total"], "review": t["review"]["words"] if t["review"] else None,
                "added_since": t["review"]["added_since"] if t["review"] else None}

    return {"case_id": str(case_id), "counts": counts, "words": coverage_words(counts),
            "reviewers": sorted(by_person.values(), key=lambda p: (-p["reviewed"], p["name"])),
            "not_reviewed": [row(t) for t in never], "partly_reviewed": [row(t) for t in partly],
            "reviewed": [row(t) for t in reviewed],
            "splits": splits if thread_keys is None else [], "second_pass": list(samples.values()),
            "searches": runs, "keyword_lists": lists, "terms": terms, "limits": tl.get("limits") or []}


def coverage_words(c: dict) -> str:
    s = "Not yet reviewed: %s of %s." % (_n(c["not_reviewed"]), _plural(c["threads"], "thread", "threads"))
    s += " Reviewed: %s. Partly reviewed (messages added since): %s." % (_n(c["reviewed"]), _n(c["partly_reviewed"]))
    return s


def cover_lines(cov: dict) -> list:
    """The export cover's "Review coverage" sentences (07 J-13 step 6, J-14), from one coverage summary."""
    out = [cov["words"]]
    if cov["reviewers"]:
        out.append("Reviewed by: %s." % "; ".join(
            "%s, %s%s" % (p["name"], _plural(p["reviewed"], "thread", "threads"),
                          (" and %s partly" % _n(p["partly_reviewed"])) if p["partly_reviewed"] else "")
            for p in cov["reviewers"]))
    for s in cov["second_pass"]:
        out.append("Second pass (%s%% sample, seed %s, by %s): %s sampled here; %s agree, %s disagree, %s not yet "
                   "checked." % (s["percent"], s["seed"], s["reviewer"] or "a person", _n(s["sampled"]),
                                 _n(s["agrees"]), _n(s["disagrees"]), _n(s["pending"])))
        for d in s["disagreements"]:
            out.append("%s disagrees with %s's review of \"%s\": %s" % (d["by"], d["first_by"] or "the first",
                                                                      d["title"], d["note"]))
    if cov["searches"]:
        out.append("Searches run on the case's phone records: %s. Terms: %s." % (
            _n(len(cov["searches"])), "; ".join('"%s"%s' % (s["query"], " (exact characters)" if s["exact"] else "")
                                               for s in cov["searches"])))
    else:
        out.append("No search of the case's phone records is recorded.")
    for kl in cov["keyword_lists"]:
        out.append('Keyword list "%s": %s.%s' % (kl["name"], "; ".join('"%s"' % t for t in kl["terms"] if t),
                                                 (" " + kl["summary"]) if isinstance(kl.get("summary"), str) else ""))
    for lim in cov["limits"]:
        if lim.get("message"):
            out.append(lim["message"])
    return out
