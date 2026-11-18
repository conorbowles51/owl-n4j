"""What also appears elsewhere, for Conversations (lx-overlapviews-b B; design Conversations.dc.html, screen 4).

Read-only. One message held on two phones (the sender's and the receiver's copy) is one message: copies are folded by
the Corroborate rule (``model.dedupe``: the same words in the same minute), so "counted once" means once per message,
and the copies are still shown.

- **Also elsewhere.** The same words (a whole message of two words or more, compared without case, spacing or end
  punctuation) in two or more separate messages, on two or more phones, on few dates (at most ``RARE_DATES``), and not on every phone of the case.
- **Shown, but counted for nothing.** Words on every phone, or on more dates than that: stock phrases. Files with the
  same bytes on every phone: common files. Pictures that only look alike (the picture-hash pairs of the media spread):
  shown for a person to check, never counted as the same photo.
- **Deleted on one phone, kept on another.** A message whose copies are deleted on one phone and intact on another.
- **Saved names.** The name each phone saved for a number, and whether the number is a case phone's own number. A
  saved name is a label on one phone and counts for little; the screen says so.
- **Meanwhile, from the same number.** For a message in the open thread, what the same number sent or received on
  the other phones within ``MEANWHILE`` of it.

Nothing is clipped: every phrase, file and pair is returned with its count.
"""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import timedelta
from typing import Any

from services.corroborate import model as M

RARE_DATES = 10
MIN_WORDS = 2
MEANWHILE = timedelta(minutes=15)
_SPACE = re.compile(r"\s+")


def norm(body: str | None) -> str:
    """The words of a message as compared: lower case, single spaces, no end punctuation."""
    return _SPACE.sub(" ", (body or "").strip()).casefold().rstrip(".!?…, ")


def _labels(store) -> dict[str, str]:
    from services.phone.readings import phone_labels
    labels = phone_labels(store.db.connection(), store.case)
    for p in store.people():
        for e in p["phones"]:
            if p.get("dossier_id"):
                labels[e] = f"{p['label']}'s phone"
    return labels


def _active_phones(store) -> list[str]:
    return [str(e) for (e,) in store.q("SELECT id FROM phone_extractions WHERE case_id = :c AND standing = 'active'")]


def _copies(store, texts: list[str] | None = None) -> dict[str, list[dict]]:
    """Every message copy whose words are on two or more phones, by its compared words."""
    rows = store.q(
        "WITH m AS (SELECT c.record_uid, c.extraction_id, c.sort_instant, c.body, c.direction, c.deleted_state, "
        "c.thread_key, lower(rtrim(regexp_replace(btrim(c.body), '\\s+', ' ', 'g'), '.!?…, ')) AS w FROM "
        "phone_comm_events c JOIN phone_extractions e ON e.id = c.extraction_id AND e.standing = 'active' WHERE "
        "c.case_id = :c AND c.kind = 'message' AND c.body IS NOT NULL AND c.sort_instant IS NOT NULL) "
        "SELECT m.* FROM m WHERE m.w IN (SELECT w FROM m WHERE array_length(regexp_split_to_array(w, ' '), 1) >= :n "
        "GROUP BY w HAVING count(DISTINCT extraction_id) >= 2) AND (CAST(:t AS text[]) IS NULL OR m.w = ANY(CAST(:t AS text[])))",
        n=MIN_WORDS, t=texts).fetchall()
    out: dict[str, list[dict]] = defaultdict(list)
    for uid, ext, at, body, direction, deleted, thread, w in rows:
        out[w].append({"record_uid": str(uid), "phone": str(ext), "at": M.as_utc(at), "body": body,
                       "direction": direction, "thread": thread,
                       "deleted": bool(deleted and str(deleted).lower() != "intact")})
    return out


def _messages(copies: list[dict]) -> list[list[dict]]:
    """Copies folded into messages by the Corroborate rule: the same words in the same minute."""
    recs = [{"ref": c["record_uid"], "dup_key": ("msg", c["at"].replace(second=0, microsecond=0), norm(c["body"])), **c}
            for c in copies]
    kept, _ = M.dedupe(recs)
    by_ref = {c["record_uid"]: c for c in copies}
    return [[by_ref[r] for r in k["copies"]] for k in kept]


def classify(w: str, copies: list[dict], phones_in_case: int, zone) -> dict:
    msgs = _messages(copies)
    phones = sorted({c["phone"] for c in copies})
    dates = sorted({c["at"].astimezone(zone).date().isoformat() for c in copies})
    repeated = len(msgs) >= 2
    every = phones_in_case >= 3 and len(phones) >= phones_in_case
    stock = every or len(dates) > RARE_DATES
    why = (f"On all {phones_in_case} phones." if every else f"On {len(dates)} dates.") if stock else None
    return {"text": copies[0]["body"].strip(), "words": w, "copies": len(copies), "messages": len(msgs),
            "phones": phones, "dates": dates, "stock": stock, "why": why,
            "repeated": repeated, "records": [c["record_uid"] for c in copies]}


def shared_content(store) -> dict[str, Any]:
    zone = M.tz(store.zone())
    labels = _labels(store)
    active = _active_phones(store)
    groups = _copies(store)
    phrases = [classify(w, cs, len(active), zone) for w, cs in groups.items()]
    also = sorted((p for p in phrases if p["repeated"] and not p["stock"]), key=lambda p: (-len(p["phones"]), len(p["dates"]), p["words"]))
    stock = sorted((p for p in phrases if p["stock"]), key=lambda p: -p["copies"])
    deletions = []
    for w, cs in groups.items():
        for msg in _messages(cs):
            gone = [c for c in msg if c["deleted"]]
            kept = [c for c in msg if not c["deleted"]]
            if gone and kept and {c["phone"] for c in gone} != {c["phone"] for c in kept}:
                deletions.append({"text": msg[0]["body"].strip(), "at": M.iso(msg[0]["at"]),
                                  "deleted_on": sorted({labels.get(c["phone"], "a phone") for c in gone}),
                                  "kept_on": sorted({labels.get(c["phone"], "a phone") for c in kept}),
                                  "records": [c["record_uid"] for c in msg]})
    files_common, files_shared = [], []
    for md5, n_phones, phones, name in store.q(
            "SELECT f.md5, count(DISTINCT f.extraction_id), array_agg(DISTINCT f.extraction_id::text), "
            "min(f.local_path) FROM pv_file f JOIN phone_extractions e ON e.id = f.extraction_id AND e.standing = 'active' "
            "WHERE f.case_id = :c AND f.md5 IS NOT NULL AND f.md5 <> '' GROUP BY f.md5 HAVING count(DISTINCT f.extraction_id) >= 2"):
        item = {"md5": md5, "name": re.split(r"[\\/]", name or "")[-1], "phones": sorted(labels.get(p, "a phone") for p in phones)}
        (files_common if len(active) >= 3 and n_phones >= len(active) else files_shared).append(item)
    try:
        from services.phone.media_spread import perceptual_pairs_all
        pairs = perceptual_pairs_all(store.db.connection(), store.case)
        lookalikes = [{"a": {"name": it["a"]["filename"], "phone": labels.get(it["a"]["extraction_id"], "a phone"),
                             "file_uid": it["a"]["file_uid"]},
                       "b": {"name": it["b"]["filename"], "phone": labels.get(it["b"]["extraction_id"], "a phone"),
                             "file_uid": it["b"]["file_uid"]},
                       "bits_apart": it["distance"], "level": it["level"]} for it in pairs["items"]]
        lookalike_note = pairs.get("stopped_words")
    except Exception as exc:  # noqa: BLE001 - the pictures' hashes may not be read yet; said so, never hidden
        lookalikes, lookalike_note = [], f"The picture comparison could not be read: {exc.__class__.__name__}."
    for p in phrases:
        p["phone_labels"] = [labels.get(e, "a phone") for e in p["phones"]]
    return {"zone": store.zone(), "phones_in_case": len(active),
            "rule": (f"The same words (a whole message of {MIN_WORDS} words or more) on two or more phones, on at most "
                     f"{RARE_DATES} dates and not on every phone, in two or more separate messages. A message held on two "
                     "phones is counted once."),
            "also": also, "stock": stock, "deletions": sorted(deletions, key=lambda d: d["at"]),
            "files_common": files_common, "files_shared": files_shared,
            "lookalikes": lookalikes, "lookalike_note": lookalike_note}


def saved_names(store, values: list[str]) -> list[dict]:
    """For each number: the name every phone saved for it, and the case phone whose own number it is."""
    labels = _labels(store)
    owners: dict[str, str] = {}
    for p in store.people():
        for n in p["numbers"]:
            for e in p["phones"]:
                owners.setdefault(n, labels.get(e, p["label"]))
    out = []
    for v in values:
        n = M.norm_number(v)
        if not n:
            continue
        names = defaultdict(set)
        for ext, name in store.q(
                "SELECT n.extraction_id, n.name FROM pv_identity i JOIN pv_identity_name n ON n.identity_id = i.identity_id "
                "WHERE i.case_id = :c AND n.is_phone_name AND regexp_replace(i.value_normalised, '\\D', '', 'g') = :n",
                n=n):
            names[str(ext)].add(name)
        out.append({"number": "+" + n, "names": [{"phone": labels.get(e, "a phone"), "name": sorted(ns)[0]}
                                                 for e, ns in sorted(names.items())],
                    "own_number_of": owners.get(n),
                    "note": "A saved name is a label on one phone, so it counts for little."})
    return out


def thread_marks(store, extraction_id: str, thread_key: str) -> dict[str, Any]:
    """Marks for the open thread: shared words per message, the saved names of its numbers, and what the same
    numbers sent or received on other phones meanwhile."""
    zone = M.tz(store.zone())
    labels = _labels(store)
    active = _active_phones(store)
    msgs = store.q(
        "SELECT c.record_uid, c.sort_instant, c.body FROM phone_comm_events c WHERE c.case_id = :c AND "
        "c.extraction_id = :e AND c.thread_key = :t AND c.sort_instant IS NOT NULL", e=extraction_id, t=thread_key).fetchall()
    words = sorted({norm(b) for _, _, b in msgs if b and len(norm(b).split(" ")) >= MIN_WORDS})
    groups = _copies(store, words) if words else {}
    marks: dict[str, dict] = {}
    for uid, at, body in msgs:
        w = norm(body)
        if w in groups:
            c = classify(w, groups[w], len(active), zone)
            if not c["repeated"]:
                continue  # one message held on two phones: not words that also appear elsewhere
            others = sorted({labels.get(p, "a phone") for p in c["phones"] if p != extraction_id})
            marks[str(uid)] = {"shared": {"stock": c["stock"], "why": c["why"], "copies": c["copies"],
                                          "messages": c["messages"], "dates": len(c["dates"]), "phones": len(c["phones"]),
                                          "other_phones": others}}
    values = sorted({str(r) for (r,) in store.q(
        "SELECT DISTINCT p.identifier_raw FROM phone_participations p JOIN phone_comm_events c ON c.record_uid = "
        "p.record_uid AND c.case_id = p.case_id WHERE p.case_id = :c AND c.extraction_id = :e AND c.thread_key = :t "
        "AND NOT COALESCE(p.is_phone_owner, false) AND p.identifier_raw IS NOT NULL", e=extraction_id, t=thread_key)})
    numbers = [n for n in (M.norm_number(v) for v in values) if n]
    meanwhile: dict[str, list[dict]] = {}
    if numbers and msgs:
        lo = min(M.as_utc(a) for _, a, _ in msgs) - MEANWHILE
        hi = max(M.as_utc(a) for _, a, _ in msgs) + MEANWHILE
        other = store.q(
            "SELECT DISTINCT c.record_uid, c.extraction_id, c.sort_instant, c.body, c.direction, p.identifier_raw FROM "
            "phone_comm_events c JOIN phone_participations p ON p.record_uid = c.record_uid AND p.case_id = c.case_id "
            "JOIN phone_extractions e ON e.id = c.extraction_id AND e.standing = 'active' WHERE c.case_id = :c AND "
            "c.extraction_id <> :e AND c.sort_instant BETWEEN :lo AND :hi AND c.kind IN ('message', 'call') AND "
            "NOT COALESCE(p.is_phone_owner, false) AND regexp_replace(p.identifier_raw, '\\D', '', 'g') = ANY(CAST(:n AS text[]))",
            e=extraction_id, lo=lo, hi=hi, n=numbers).fetchall()
        here = {(M.as_utc(a).replace(second=0, microsecond=0), norm(b)) for _, a, b in msgs}
        ordered = sorted((M.as_utc(a), str(u)) for u, a, _ in msgs)
        for ouid, oext, oat, obody, odir, _raw in other:
            oat = M.as_utc(oat)
            if (oat.replace(second=0, microsecond=0), norm(obody)) in here:
                continue  # a copy of this thread's own message on the other phone: counted once, not "meanwhile"
            before = [u for a, u in ordered if a < oat <= a + MEANWHILE]
            if not before:
                continue
            meanwhile.setdefault(before[-1], []).append(
                {"record_uid": str(ouid), "at": M.iso(oat), "time": oat.astimezone(zone).strftime("%H:%M"),
                 "phone": labels.get(str(oext), "a phone"), "body": obody,
                 "direction": "from the number" if odir == "incoming" else "to the number"})
        for v in meanwhile.values():
            v.sort(key=lambda x: x["at"])
    return {"zone": store.zone(), "marks": marks, "meanwhile": meanwhile, "names": saved_names(store, values)}
