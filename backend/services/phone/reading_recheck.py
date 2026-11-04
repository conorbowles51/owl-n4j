"""A second person re-checks a sample of the confirmations of readings (07 J-8 quality measure, UXD-59).

The sample is drawn as the thread second pass draws (``review_share``, UXD-53): ``random.Random(seed)`` over the
confirmations in id order, the seed kept, 5% rounded up and at least 1. Only confirmations a person made are in it,
never one by the second person, and never one already sampled, so each confirmation counts once in the rate.

The sample is one Workspace task assigned to the second person, with one ``phone_extraction`` link per phone whose
anchor holds that phone's sampled confirmations. A confirmation is the ``adjudications`` row: the judgement row is
rewritten by each re-derive, the decision is not. The result sits beside a copy of the first confirmation, which is
never changed: a disagreement is reported and the reading stays as it is until a person corrects it.
"""
from __future__ import annotations

import json
import math
import random
import secrets
import uuid
from datetime import datetime, timezone

from sqlalchemy import text

from services.phone import readings
from services.phone.review_share import ReviewShareError, _members, _n, _plural

RECHECK_PERCENT = 5
MIN_BASE_FOR_RATE = 20  # below this many checked, the true counts are shown and no percentage (UXD-59)


def _confirmations(conn, case_id) -> list:
    """The standing confirmations by a person on the case's active phones, one row each."""
    labels = readings.phone_labels(conn, case_id)
    rows = conn.execute(text(
        "SELECT j.id AS reading_id, j.extraction_id, j.rule_id, j.mapping_version_id, j.rule_part, j.type_name, "
        "j.summary, j.records_touched, a.id AS confirmation_id, a.actor_user_id, a.actor_name, a.actor_email, "
        "a.created_at, a.reason FROM phone_mapping_judgements j JOIN phone_interpretation_state s ON "
        "s.extraction_id = j.extraction_id AND s.generation = j.generation JOIN phone_extractions e ON "
        "e.id = j.extraction_id AND e.standing = 'active' JOIN adjudications a ON a.id = j.adjudication_id WHERE "
        "j.case_id = :c AND j.status = 'confirmed' AND j.records_touched > 0 AND a.decision = 'confirm_phone_reading' "
        "AND a.actor_user_id IS NOT NULL"), {"c": str(case_id)}).fetchall()
    return [{"confirmation_id": str(r.confirmation_id), "reading_id": str(r.reading_id),
             "extraction_id": str(r.extraction_id), "rule_id": r.rule_id,
             "mapping_version_id": str(r.mapping_version_id), "part": r.rule_part,
             "phone": labels.get(str(r.extraction_id), "Phone"),
             "sentence": readings.sentence(labels.get(str(r.extraction_id), "Phone"), r.type_name, r.summary,
                                           int(r.records_touched)),
             "first": {"by_id": str(r.actor_user_id), "by_name": r.actor_name, "by_email": r.actor_email,
                       "at": r.created_at.isoformat(), "reason": r.reason}} for r in rows]


def _links(conn, case_id, *, lock_task=None) -> list:
    q = ("SELECT l.id, l.task_id, l.target_id, l.source_anchor, t.title, t.status, t.assignee_user_id FROM "
         "case_task_links l JOIN case_tasks t ON t.id = l.task_id WHERE l.case_id = :c AND t.deleted_at IS NULL AND "
         "l.target_type = 'phone_extraction' AND l.source_anchor ? 'reading_recheck'")
    p = {"c": str(case_id)}
    if lock_task is not None:
        q += " AND l.task_id = :t ORDER BY l.id FOR UPDATE OF l"
        p["t"] = str(lock_task)
    else:
        q += " ORDER BY l.created_at, l.id"
    return conn.execute(text(q), p).fetchall()


def draw(db, case_id, *, reviewer_id, user, percent: int = RECHECK_PERCENT, seed: int | None = None) -> dict:
    """Sample ``percent`` of the confirmations ``reviewer_id`` did not make into one task for that person."""
    from postgres import link_types
    from services.system_log_service import LogOrigin, LogType, system_log_service
    conn = db.connection()
    person = _members(conn, case_id, [reviewer_id])[0]
    email = (conn.execute(text("SELECT email FROM users WHERE id = :u"), {"u": person["user_id"]}).scalar() or "").lower()
    confirmed = _confirmations(conn, case_id)
    seen = {i["confirmation_id"] for r in _links(conn, case_id) for i in (r.source_anchor or {}).get("items") or []}
    theirs = [c for c in confirmed if c["first"]["by_id"] == person["user_id"] or
              (c["first"]["by_email"] or "").lower() == email]
    fresh = [c for c in confirmed if c["confirmation_id"] not in seen]
    eligible = sorted((c for c in fresh if c not in theirs), key=lambda c: c["confirmation_id"])
    if not eligible:
        if not confirmed:
            raise ReviewShareError("No reading is confirmed yet, so there is nothing to sample.")
        raise ReviewShareError(
            "No confirmation is left to sample for %s: of %s, %s made by them and %s already sampled." % (
                person["name"], _plural(len(confirmed), "confirmation", "confirmations"), _n(len(theirs)),
                _n(len(confirmed) - len(fresh))))
    seed = int(seed) if seed is not None else secrets.randbits(31)
    k = max(1, math.ceil(len(eligible) * int(percent) / 100))
    sample = random.Random(seed).sample(eligible, k)
    pass_id, tid, made_at = str(uuid.uuid4()), uuid.uuid4(), datetime.now(timezone.utc).isoformat()
    title = "Re-check of confirmed readings: %s of %s (%d%% sample)" % (_n(k), _n(len(eligible)), int(percent))
    desc = ("A random %d%% sample (seed %d) of the %s confirmations that %s did not make, drawn by %s on %s. On Needs "
            "a decision, look at each reading's examples and record whether you agree with the confirmation; a "
            "disagreement needs a note. The confirmation is kept as it is." % (
                int(percent), seed, _n(len(eligible)), person["name"], user.name or user.email, made_at[:10]))
    conn.execute(text(
        "INSERT INTO case_tasks (id, case_id, title, description, status, priority, assignee_user_id, "
        "created_by_user_id, updated_by_user_id, created_at, updated_at) VALUES (:i, :c, :t, :d, 'todo', 'standard', "
        ":a, :u, :u, now(), now())"),
        {"i": tid, "c": str(case_id), "t": title, "d": desc, "a": person["user_id"], "u": user.id})
    by_phone: dict = {}
    for c in sample:
        by_phone.setdefault(c["extraction_id"], []).append(c)
    for ext, items in sorted(by_phone.items()):
        target = link_types.resolve_phone_target(db, case_id, "phone_extraction", ext)
        anchor = link_types.phone_anchor(target, {
            "reading_recheck": pass_id, "seed": seed, "percent": int(percent), "eligible": len(eligible),
            "confirmed": len(confirmed), "assigned_to": person["user_id"], "assigned_to_name": person["name"],
            "drawn_at": made_at,
            "items": [{"confirmation_id": c["confirmation_id"], "rule_id": c["rule_id"],
                       "mapping_version_id": c["mapping_version_id"], "part": c["part"], "phone": c["phone"],
                       "sentence": c["sentence"], "first": c["first"], "result": None, "earlier_results": []}
                      for c in items]})
        conn.execute(text(
            "INSERT INTO case_task_links (id, task_id, case_id, target_type, target_id, label, source_anchor, "
            "created_by_user_id, created_at, updated_at) VALUES (:i, :t, :c, 'phone_extraction', :k, :l, "
            "CAST(:a AS jsonb), :u, now(), now())"),
            {"i": uuid.uuid4(), "t": tid, "c": str(case_id), "k": ext, "l": items[0]["phone"],
             "a": json.dumps(anchor, default=str), "u": user.id})
    system_log_service.log(log_type=LogType.CASE_OPERATION, origin=LogOrigin.BACKEND,
                           action="Drew a re-check sample of confirmed readings",
                           details={"case_id": str(case_id), "pass_id": pass_id, "seed": seed, "percent": int(percent),
                                    "sample": k, "eligible": len(eligible)}, user=user.email, success=True, db=db)
    db.commit()
    return {"pass_id": pass_id, "task_id": str(tid), "title": title, "seed": seed, "percent": int(percent),
            "sample": k, "eligible": len(eligible), "confirmed": len(confirmed), "reviewer": person,
            "confirmation_ids": [c["confirmation_id"] for c in sample],
            "words": "Drew %s of %s for %s (seed %d)." % (_n(k), _plural(len(eligible), "confirmation", "confirmations"),
                                                         person["name"], seed)}


def record_result(db, case_id, *, task_id, confirmation_id: str, user, agrees: bool, note: str | None) -> dict:
    """The second person's result on one sampled confirmation. A person never re-checks their own confirmation, and
    the first confirmation is not touched. A result recorded again keeps the earlier one."""
    from services.system_log_service import LogOrigin, LogType, system_log_service
    conn = db.connection()
    links = _links(conn, case_id, lock_task=task_id)
    hit = next(((r, i) for r in links for i in (r.source_anchor or {}).get("items") or []
                if i["confirmation_id"] == confirmation_id), None)
    if hit is None:
        raise LookupError("This confirmation is not in that re-check sample.")
    row, _ = hit
    anchor = dict(row.source_anchor)
    item = next(i for i in anchor["items"] if i["confirmation_id"] == confirmation_id)
    first = item.get("first") or {}
    if first.get("by_id") == str(user.id) or (first.get("by_email") or "").lower() == (user.email or "").lower():
        raise ReviewShareError("A re-check is made by someone other than the person who confirmed it (%s)."
                               % (first.get("by_name") or "a person"))
    note = (note or "").strip() or None
    if not agrees and not note:
        raise ReviewShareError("Say why you disagree with the confirmation.")
    if item.get("result"):
        item["earlier_results"] = list(item.get("earlier_results") or []) + [item["result"]]
    item["result"] = {"agrees": bool(agrees), "note": note, "by": str(user.id), "by_name": user.name or user.email,
                      "at": datetime.now(timezone.utc).isoformat()}
    conn.execute(text("UPDATE case_task_links SET source_anchor = CAST(:a AS jsonb), updated_at = now() WHERE id = :i"),
                 {"a": json.dumps(anchor, default=str), "i": row.id})
    left = sum(1 for r in links for i in ((anchor if r.id == row.id else r.source_anchor) or {}).get("items") or []
               if not i.get("result"))
    conn.execute(text("UPDATE case_tasks SET status = CAST(:s AS varchar), completed_at = CASE WHEN CAST(:s AS varchar) "
                      "= 'done' THEN now() ELSE NULL END, updated_at = now() WHERE id = :t AND status <> 'done'"),
                 {"s": "in_progress" if left else "done", "t": str(task_id)})
    system_log_service.log(log_type=LogType.CASE_OPERATION, origin=LogOrigin.BACKEND,
                           action="Recorded a re-check of a confirmed reading",
                           details={"case_id": str(case_id), "task_id": str(task_id),
                                    "confirmation_id": confirmation_id, "agrees": bool(agrees)},
                           user=user.email, success=True, db=db)
    db.commit()
    return {"confirmation_id": confirmation_id, "result": item["result"], "left": left}


def rate_words(agrees: int, disagrees: int, pending: int) -> dict:
    """The disagreement rate with its base. Below ``MIN_BASE_FOR_RATE`` checked there is no percentage: the true
    counts are given and the sentence says the sample is too small."""
    checked = agrees + disagrees
    if not checked and not pending:
        return {"rate_percent": None, "too_few": False, "words": "No confirmation has been sampled for a re-check."}
    if not checked:
        return {"rate_percent": None, "too_few": True,
                "words": "%s sampled; none checked yet." % _plural(pending, "confirmation", "confirmations")}
    words = "%s of %s %s." % (_n(disagrees), _plural(checked, "checked confirmation", "checked confirmations"),
                              "disagrees" if checked == 1 else "disagree")
    rate = too_few = None
    if checked >= MIN_BASE_FOR_RATE:
        rate, too_few = round(100.0 * disagrees / checked, 1), False
        words = "Disagreement rate %s%%: %s" % (rate, words[0].lower() + words[1:])
    else:
        too_few = True
        words += " Too few for a rate (under %d checked)." % MIN_BASE_FOR_RATE
    if pending:
        words += " %s not yet checked." % _n(pending)
    return {"rate_percent": rate, "too_few": too_few, "words": words}


def counts(conn, case_id) -> dict:
    agrees = disagrees = pending = 0
    for r in _links(conn, case_id):
        for i in (r.source_anchor or {}).get("items") or []:
            res = i.get("result")
            if not res:
                pending += 1
            elif res.get("agrees"):
                agrees += 1
            else:
                disagrees += 1
    return {"sampled": agrees + disagrees + pending, "agrees": agrees, "disagrees": disagrees, "pending": pending,
            **rate_words(agrees, disagrees, pending)}


def summary(conn, case_id, user) -> dict:
    """The counts, each draw, and every sampled confirmation with the reading it is on now (``reading_id`` is None
    when the phone was replaced, or the rule no longer applies, so there is nothing current to look at)."""
    now = {(r.extraction_id, r.rule_id, r.mapping_version_id): r for r in conn.execute(text(
        "SELECT j.id, j.extraction_id::text AS extraction_id, j.rule_id, j.mapping_version_id::text AS "
        "mapping_version_id, j.status, j.resolved_by FROM phone_mapping_judgements j JOIN phone_interpretation_state "
        "s ON s.extraction_id = j.extraction_id AND s.generation = j.generation WHERE j.case_id = :c"),
        {"c": str(case_id)})}
    passes: dict = {}
    items = []
    for r in _links(conn, case_id):
        a = r.source_anchor or {}
        p = passes.setdefault(a.get("reading_recheck"), {
            "pass_id": a.get("reading_recheck"), "task_id": str(r.task_id), "title": r.title, "seed": a.get("seed"),
            "percent": a.get("percent"), "eligible": a.get("eligible"), "reviewer": a.get("assigned_to_name"),
            "sampled": 0})
        for i in a.get("items") or []:
            p["sampled"] += 1
            cur = now.get((r.target_id, i.get("rule_id"), i.get("mapping_version_id")))
            first = {k: v for k, v in (i.get("first") or {}).items() if k != "by_email"}
            items.append({"task_id": str(r.task_id), "confirmation_id": i["confirmation_id"], "phone": i.get("phone"),
                          "extraction_id": r.target_id, "sentence": i.get("sentence"), "first": first,
                          "result": i.get("result"), "earlier_results": len(i.get("earlier_results") or []),
                          "reading_id": str(cur.id) if cur else None, "status_now": cur.status if cur else None,
                          "mine": r.assignee_user_id == user.id,
                          "own_confirmation": first.get("by_id") == str(user.id)})
    return {**counts(conn, case_id), "min_base": MIN_BASE_FOR_RATE, "percent": RECHECK_PERCENT,
            "passes": list(passes.values()), "items": items}
