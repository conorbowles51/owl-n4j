"""Who overlaps with whom (lx-overlapviews-a A-D): every pair of people in the case against every kind of overlap.

``build(store)`` reads the case once through the Corroborate store (the same records, the same copy folding and the
same "together" rule as the engine) and returns, for each pair of people:

- ``contact``: messages, calls and e-mails with both on them, a copy held on both phones counted once;
- ``through_others``: numbers and people each of them is in contact with (go-betweens), with the contacts to each end;
- ``groups``: group chats both are members of;
- ``shared``: the same uncommon words on both people's phones (lx-overlapviews-b ``shared_words``), when available;
- ``place``: days their phones were together by the engine's rule (``signals.together_rows``); photo places are not
  positions and never count;
- ``access``: days both are named in dated rows of the same document (badge logs, reports);
- ``money``: payments and payment alerts between them, a ledger row and its alert counted once;
- ``documents``: documents a model read as naming both, each with its page. A model reading until a person checks it.

Nothing here sets a level. The level of a pair is the level of a saved lead (``services.leads``, the Corroborate
engine's level) naming both people; a pair with records and no lead is "not weighed yet".
"""
from __future__ import annotations

import re
import threading
import time
from collections import Counter, defaultdict
from datetime import date, datetime, time as dtime, timedelta, timezone
from itertools import combinations
from typing import Any

from sqlalchemy import text

from services.corroborate import model as M
from services.corroborate import signals as S

SCHEMA = "loupe.overlaps/1"
KINDS = ("contact", "through_others", "groups", "shared", "place", "access", "money", "documents")
KIND_WORDS = {
    "contact": "Contact",
    "through_others": "Through others",
    "groups": "Groups",
    "shared": "Same words and files",
    "place": "Place",
    "access": "Access logs and dated papers",
    "money": "Money",
    "documents": "Documents naming both",
}
SEARCHED = {
    "contact": "calls, messages and e-mails between them on every phone in the case, a copy on both phones counted once",
    "through_others": "every number or person in contact with both of them",
    "groups": "group chats on every phone with both of them as members",
    "shared": "the same uncommon words on both people's phones, stock phrases set aside",
    "place": "their phones within each other's accuracy plus 50 m inside 15 minutes; photo places are not positions",
    "access": "dated rows of the case's documents naming both of them on the same day",
    "money": "payments and payment alerts between them, a ledger row and its alert counted once",
    "documents": "names a model read from each document, with the page, and full names in each document's text",
}
# Places read from photos are where a photo was taken, not where the phone was (followups owns the store fix).
PHOTO_PLACE = re.compile(r"photo|media|exif", re.I)
MAX_PEOPLE = 16          # people in the grid, most records first; the rest are counted and named, never dropped silently
MAX_LISTED = 40          # records listed per kind in a pair's detail; the count is always the full count
CACHE_SECONDS = 600
LEVEL_ORDER = ("strong", "probable", "possible", "cant_tell", "coincidence", "no_link_found")  # the Leads list's order


def _short(label: str) -> str:
    return label.split(" (")[0]


def is_photo_place(rec: dict) -> bool:
    return rec.get("kind") == "media_position" or bool(PHOTO_PLACE.search(str((rec.get("place") or {}).get("source") or "")))


def _ends(rec: dict) -> set[str]:
    return ({rec.get("owner")} | set(rec.get("parties") or ())) - {None}


def _brief(rec: dict, labels: dict[str, str]) -> dict:
    return {"ref": rec["ref"], "kind": rec["kind"], "at": M.iso(rec.get("at")), "day_only": bool(rec.get("day_only")),
            "phone": rec.get("phone"),
            # who wrote it: only a message, call or e-mail has a writer; a payment alert is the bank's text
            "from": labels.get(rec.get("sender") or rec.get("owner") or "", None) if rec["kind"] in M.CONTACT_KINDS else None,
            "body": (rec.get("body") or "")[:200] or None, "copies": len(rec.get("copies") or [rec["ref"]]),
            "deleted": bool(rec.get("deleted")), "amount_minor": rec.get("amount_minor"), "app": rec.get("app")}


# ---- reading the case ------------------------------------------------------------------------------------------------

def _all_records(store) -> tuple[list[dict], int]:
    everyone = store.people()
    lo = datetime(1990, 1, 1, tzinfo=timezone.utc)
    hi = datetime.now(timezone.utc) + timedelta(days=366)
    raw = store.records(everyone, [(lo, hi)], everyone)
    return M.dedupe(raw)


def group_threads(store) -> list[dict]:
    """Group chats on the phones: title, app, members (people keys or raw identifiers), records."""
    everyone = store.people()
    out = []
    for ext, key, app, title, n, parties in store.q(
            "SELECT t.extraction_id, t.thread_key, t.app, t.title_in_record, t.event_count, t.party_identity_keys "
            "FROM phone_threads t JOIN phone_extractions e ON e.id = t.extraction_id AND e.standing = 'active' "
            "WHERE t.case_id = :c AND t.chat_type = 'Group'"):
        owner = next((p["key"] for p in everyone if str(ext) in p["phones"]), None)
        members = {owner} - {None}
        for raw in parties or []:
            value = str(raw).split(":")[-1]
            members.add(M.person_for_value(everyone, value) or value)
        out.append({"thread": key, "phone": str(ext), "app": app, "title": title or "an untitled group",
                    "records": n or 0, "members": sorted(members)})
    return out


def documents_naming(store) -> list[dict]:
    """Each document whose people a model read (entity readings), with the people of the case it names and the
    page each was read on. Model readings: nothing here is confirmed by a person."""
    everyone = store.people()
    named: dict[str, dict] = {}
    for fid, fname, obj, quote, loc in store.q(
            "SELECT c.evidence_file_id, f.original_filename, c.object_value, c.quote, c.source_location FROM evidence_claims c "
            "JOIN evidence_files f ON f.id = c.evidence_file_id AND f.deleted_at IS NULL WHERE c.case_id = :c AND "
            "c.claim_type IN ('entity_mention', 'entity_fact') AND COALESCE(c.status, '') <> 'rejected'"):
        doc = named.setdefault(str(fid), {"file_id": str(fid), "file": fname, "people": {}})
        obj = obj or {}
        if str(obj.get("category") or "").casefold() != "person":
            continue
        name = str(obj.get("name") or "")
        aliases = [str(a) for a in ((obj.get("properties") or {}).get("aliases") or []) if a]
        hits = [p["key"] for p in everyone if any(M.names_match(n, t) for n in p["names"] if n for t in [name] + aliases)]
        if len(hits) != 1:
            continue
        page = (loc or {}).get("page_start")
        entry = doc["people"].setdefault(hits[0], {"key": hits[0], "read_as": name, "pages": set(), "quote": quote})
        if page is not None:
            entry["pages"].add(int(page))
    # a full name in the document's text (Loupe's name rule, either order) names a person the model did not read
    for fid, fname, content in store.q(
            "SELECT f.id, f.original_filename, t.content FROM evidence_document_texts t JOIN evidence_files f ON "
            "f.id = t.evidence_file_id WHERE f.case_id = :c AND f.deleted_at IS NULL"):
        doc = named.get(str(fid))
        if doc is None:   # only documents a model read (statements, papers); phone reports list every contact name
            continue
        for p in everyone:
            if p["key"] in doc["people"]:
                continue
            if any(M.names_match(n, content or "") for n in p["names"] if n):
                doc["people"][p["key"]] = {"key": p["key"], "read_as": None, "pages": set(), "quote": None,
                                           "by": "name in the text"}
    out = []
    for doc in named.values():
        people = [{"by": "model", **v, "pages": sorted(v["pages"])} for v in doc["people"].values()]
        out.append({"file_id": doc["file_id"], "file": doc["file"], "people": people})
    return sorted(out, key=lambda d: d["file"] or "")


def _place_days(store, recs: list[dict], keys: list[str], everyone: dict) -> tuple[dict, int]:
    """{(a, b): [(day, refs)]} by the engine's together rule, one instance per local day; photo places excluded."""
    zone = store.zone()
    tzz = M.tz(zone)
    pos = [r for r in recs if r["kind"] == "position" and r.get("place") and not is_photo_place(r)]
    photo = sum(1 for r in recs if r["kind"] in ("position", "media_position") and is_photo_place(r))
    days = sorted({r["at"].astimezone(tzz).date() for r in pos})
    if not days:
        return {}, photo
    instances = [M.make_instance(d, dtime(0, 0), timedelta(hours=24), tzz, "incident", zone) for d in days]
    with_pos = sorted({r["owner"] for r in pos if r.get("owner")})
    people = {k: everyone[k] for k in keys if k in with_pos}
    out: dict[tuple[str, str], list] = {}
    if len(people) < 2:
        return out, photo
    for row in S.together_rows(people, pos, instances, {}):
        a, b = row["people"]
        hits = [(i["day"], row["records"].get(i["id"], [])) for i in instances if row["cells"].get(i["id"]) == "present"]
        if hits:
            out[M.pair_key(a, b)] = hits
    return out, photo


def position_days(recs: list[dict]) -> dict[str, int]:
    """Days each person's phone holds a position (photo places excluded)."""
    days = defaultdict(set)
    for r in recs:
        if r["kind"] == "position" and r.get("owner") and not is_photo_place(r):
            days[r["owner"]].add(r["at"].date())
    return {k: len(v) for k, v in days.items()}


# ---- the grid ----------------------------------------------------------------------------------------------------

def build(store, shared: dict | None = None) -> dict[str, Any]:
    started = time.time()
    everyone = {p["key"]: p for p in store.people()}
    labels = {k: _short(p["label"]) for k, p in everyone.items()}
    recs, folded = _all_records(store)
    groups = group_threads(store)

    contact = defaultdict(list)
    money = defaultdict(list)
    access = defaultdict(lambda: defaultdict(set))   # (a,b) -> day -> refs
    doc_rows_by = defaultdict(list)
    reach = defaultdict(lambda: defaultdict(list))   # endpoint -> other endpoint -> records (for go-betweens)
    records_of = Counter()
    for r in recs:
        ends = _ends(r)
        if r["kind"] in M.CONTACT_KINDS:
            # the unresolved numbers on a record are endpoints too: a go-between need not be a person of the case
            loose = {f"number:{v}" for v in (r.get("counterpart_values") or ()) if v
                     and not M.person_for_value(list(everyone.values()), v)}
            pts = ends | loose
            for x in pts:
                records_of[x] += 1
                for y in pts - {x}:
                    reach[x][y].append(r)
            for a, b in combinations(sorted(ends), 2):
                contact[(a, b)].append(r)
        elif r["kind"] in M.MONEY_KINDS:
            for a, b in combinations(sorted(ends), 2):
                money[(a, b)].append(r)
            for x in ends:
                records_of[x] += 1
        elif r["kind"] == "doc_row":
            doc_rows_by[r.get("source")].append(r)
    for src, rows in doc_rows_by.items():
        by_day = defaultdict(lambda: defaultdict(list))
        for r in rows:
            for p in r.get("parties") or ():
                by_day[r["at"].date().isoformat()][p].append(r["ref"])
        for day, who in by_day.items():
            for a, b in combinations(sorted(who), 2):
                access[(a, b)][day].update(who[a] + who[b])

    # the people of the grid: the case's people with records, most first; the rest named, never silently dropped
    ranked = sorted(everyone, key=lambda k: (-records_of.get(k, 0), labels[k]))
    keys = ranked[:MAX_PEOPLE]
    left_out = [labels[k] for k in ranked[MAX_PEOPLE:]]
    place, photo_places = _place_days(store, recs, keys, everyone)
    docs = documents_naming(store)
    pos_days = position_days(recs)

    pairs = []
    for a, b in combinations(keys, 2):
        a, b = M.pair_key(a, b)
        pairs.append(_pair(a, b, everyone, labels, contact, money, access, place, docs, groups, reach, shared))
    owners = [k for k in keys if everyone[k]["phones"]]
    docs_two = [d for d in docs if len({p["key"] for p in d["people"]} & set(owners)) >= 2]
    reaches = _reaches(reach, everyone)
    zone = store.zone()
    people_out = [_person(everyone[k], labels, records_of, pos_days) for k in keys]
    return {
        "schema": SCHEMA,
        "zone": zone,
        "go_betweens": {k: go_between_panel(k, reach, labels, {x: everyone[x] for x in keys}, place, pos_days, zone)
                        for k in keys},
        "graph": graph(pairs, people_out, docs, reaches, labels, owners),
        "people": people_out,
        "left_out": left_out,
        "pairs": pairs,
        "kinds": [{"key": k, "name": KIND_WORDS[k], "searched": SEARCHED[k]} for k in KINDS],
        "worth_a_look": worth_a_look(pairs, labels, everyone, reaches, _theories(store)),
        "documents": {"read": len(docs), "naming_two_phone_owners": len(docs_two)},
        "notes": _notes(folded, photo_places, shared),
        "seconds": round(time.time() - started, 2),
    }


def _person(p: dict, labels, records_of, pos_days) -> dict:
    return {"key": p["key"], "label": labels[p["key"]], "full_label": p["label"], "dossier_id": p.get("dossier_id"),
            "phones": len(p["phones"]), "records": records_of.get(p["key"], 0), "position_days": pos_days.get(p["key"], 0),
            "identifiers": sorted(["+" + n for n in p["numbers"]] + sorted(p["handles"]))[:6]}


def _notes(folded: int, photo_places: int, shared: dict | None) -> list[str]:
    notes = [f"{folded:,} copies of a record held on two phones (or a payment as a ledger row and an alert) are counted once."]
    if photo_places:
        notes.append(f"{photo_places:,} places read from photos are where a photo was taken, not where a phone was; "
                     "they are never counted as a place two people shared.")
    if shared is None:
        notes.append("Same words and files are not searched yet in this release, so that kind shows no result.")
    return notes


def _gobetweens(a: str, b: str, reach, labels) -> list[dict]:
    out = []
    for x in set(reach[a]) & set(reach[b]):
        if x in (a, b):
            continue
        days_a = {r["at"].date() for r in reach[a][x]}
        days_b = {r["at"].date() for r in reach[b][x]}
        out.append({"key": x, "label": labels.get(x) or ("+" + x.split(":", 1)[1] if x.startswith("number:") else x),
                    "with_a": len({r["ref"] for r in reach[a][x]}), "with_b": len({r["ref"] for r in reach[b][x]}),
                    "route_days": sum(1 for d in days_a if any(abs((d - e).days) <= 1 for e in days_b))})
    return sorted(out, key=lambda g: -(g["with_a"] + g["with_b"]))


def _pair(a, b, everyone, labels, contact, money, access, place, docs, groups, reach, shared) -> dict:
    kinds: dict[str, dict] = {}
    c = sorted(contact.get((a, b), []), key=lambda r: r["at"])
    n_calls = sum(1 for r in c if r["kind"] == "call")
    n_mail = sum(1 for r in c if r["kind"] == "email")
    both = sum(1 for r in c if len(r.get("copies") or ()) > 1)
    words = (f"{len(c):,} record{'' if len(c) == 1 else 's'} on their phones: {len(c) - n_calls - n_mail:,} messages, "
             f"{n_calls:,} calls" + (f", {n_mail:,} e-mails" if n_mail else "") +
             (f"; {both:,} held on both phones, counted once" if both else "") + ".") if c else "No direct contact."
    kinds["contact"] = {"count": len(c), "words": words, "records": [_brief(r, labels) for r in c[:MAX_LISTED]],
                        "first": M.iso(c[0]["at"]) if c else None, "last": M.iso(c[-1]["at"]) if c else None,
                        "deleted": sum(1 for r in c if r.get("deleted"))}
    gb = _gobetweens(a, b, reach, labels)
    kinds["through_others"] = {"count": len(gb), "go_betweens": gb[:12], "words": (
        "; ".join(f"{g['label']}: {g['with_a']:,} with {labels[a]}, {g['with_b']:,} with {labels[b]}" for g in gb[:3])
        + (f"; {len(gb) - 3:,} more" if len(gb) > 3 else "") + ".") if gb else "No number or person in contact with both."}
    gs, seen = [], set()
    for g in groups:   # a group held on two members' phones is one group
        key = (g["title"], g["app"], tuple(g["members"]))
        if a in g["members"] and b in g["members"] and key not in seen:
            seen.add(key)
            gs.append(g)
    kinds["groups"] = {"count": len(gs), "groups": gs, "words": "; ".join(
        f"“{g['title']}” on {g['app'] or 'a messaging app'}, {g['records']:,} records, {len(g['members'])} members" for g in gs) + "."
        if gs else "No group chat with both of them."}
    kinds["shared"] = _shared_kind(a, b, everyone, shared)
    pl = place.get((a, b), [])
    kinds["place"] = {"count": len(pl), "days": [d for d, _ in pl][:MAX_LISTED],
                      "refs": [ref for _, refs in pl[:MAX_LISTED] for ref in refs[:4]],
                      "words": (f"Their phones together on {len(pl):,} day{'' if len(pl) == 1 else 's'}"
                                f" (first {pl[0][0]}, last {pl[-1][0]}).") if pl else "Their phones were never together by Loupe's rule."}
    ac = access.get((a, b), {})
    kinds["access"] = {"count": len(ac), "days": sorted(ac)[:MAX_LISTED],
                       "refs": [ref for d in sorted(ac)[:MAX_LISTED] for ref in sorted(ac[d])[:4]],
                       "words": f"Both named in dated document rows on {len(ac):,} day{'' if len(ac) == 1 else 's'}." if ac
                       else "No dated document row names both of them on the same day."}
    mo = sorted(money.get((a, b), []), key=lambda r: r["at"])
    total = sum(abs(r.get("amount_minor") or 0) for r in mo)
    kinds["money"] = {"count": len(mo), "total_minor": total, "records": [_brief(r, labels) for r in mo[:MAX_LISTED]],
                      "words": (f"{len(mo):,} payment{'' if len(mo) == 1 else 's'} between them, {M.fmt_money(total)} in all.")
                      if mo else "No payment between them."}
    ds = [d for d in docs if {a, b} <= {p["key"] for p in d["people"]}]
    kinds["documents"] = {"count": len(ds), "model_reading": True, "documents": [
        {"file_id": d["file_id"], "file": d["file"],
         "pages": {p["key"]: p["pages"] for p in d["people"] if p["key"] in (a, b)},
         "by": {p["key"]: p["by"] for p in d["people"] if p["key"] in (a, b)}} for d in ds[:MAX_LISTED]],
        "words": (f"{len(ds):,} document{'' if len(ds) == 1 else 's'} name both (names read by a model, or a full name "
                  "in the text); not checked by a person.")
        if ds else "No document names both."}
    found = [k for k in KINDS if kinds[k]["count"] and k != "through_others"]
    return {"a": a, "b": b, "label": f"{labels[a]} and {labels[b]}", "kinds": kinds, "kinds_found": found,
            "direct": bool(c) or bool(gs), "records": sum(kinds[k]["count"] for k in ("contact", "money")),
            "state": "not_weighed" if found else "nothing"}


def _shared_kind(a, b, everyone, shared) -> dict:
    """lx-overlapviews-b's shared content between two people: uncommon words on both people's phones (stock phrases
    already set aside there), a message deleted on one person's phone and kept on the other's, the same file on both."""
    if shared is None:
        return {"count": 0, "searched": False, "words": "Not searched yet."}
    pa, pb = set(everyone[a]["phones"]), set(everyone[b]["phones"])
    # shared_words names phones by its own labels ("<name>'s phone"); read them back to the phones
    by_label = shared.get("phone_of_label") or {}
    la = {lab for lab, e in by_label.items() if e in pa} | set((everyone[a].get("phone_labels") or {}).values())
    lb = {lab for lab, e in by_label.items() if e in pb} | set((everyone[b].get("phone_labels") or {}).values())
    phrases = [x for x in shared.get("also", []) if pa & set(x.get("phones") or ()) and pb & set(x.get("phones") or ())]
    deleted = [d for d in shared.get("deletions", []) if (set(d["deleted_on"]) & la and set(d["kept_on"]) & lb)
               or (set(d["deleted_on"]) & lb and set(d["kept_on"]) & la)]
    files = [f for f in shared.get("files_shared", []) if set(f["phones"]) & la and set(f["phones"]) & lb]
    bits = []
    if phrases:
        bits.append("; ".join(f"“{x['text']}” ({x['messages']:,} message{'' if x['messages'] == 1 else 's'} on "
                              f"{len(x['dates'])} date{'' if len(x['dates']) == 1 else 's'})" for x in phrases[:3])
                    + (f" and {len(phrases) - 3} more" if len(phrases) > 3 else "") + " on both people's phones")
    for d in deleted[:2]:
        bits.append(f"“{d['text']}” deleted on {', '.join(d['deleted_on'])}, kept on {', '.join(d['kept_on'])}")
    if files:
        bits.append(f"{len(files):,} file{'' if len(files) == 1 else 's'} on both people's phones")
    return {"count": len(phrases) + len(deleted) + len(files), "searched": True, "phrases": phrases[:12],
            "deletions": deleted[:12], "files": files[:12],
            "words": ("; ".join(bits) + ".") if bits else "No uncommon words or files on both people's phones."}


NARROW_REACH = 3      # a go-between that reaches at most this many people of the case is a narrow route, not a hub
ROUTE_DAYS = 2        # ... and contacts both ends within a day of each other on at least this many days
BESIDE_DAYS = 3       # a phone with no owner name beside a person's phone on at least this many days
_PHONE_WORD = re.compile(r"\bphone\b", re.I)


def _reaches(reach, everyone) -> dict[str, int]:
    return {x: sum(1 for y in ys if y in everyone) for x, ys in reach.items()}


def _theories(store) -> list[dict]:
    try:
        return [dict(r) for r in store.q(
            "SELECT id, entry_type, title, body FROM workspace_entries WHERE case_id = :c AND deleted_at IS NULL "
            "AND entry_type IN ('theory', 'finding') ORDER BY created_at").mappings()]
    except Exception:  # noqa: BLE001 - a case without the workspace tables reads as having no theories
        store.db.rollback()
        return []


def worth_a_look(pairs: list[dict], labels: dict, everyone: dict, reaches: dict, theories: list[dict]) -> list[dict]:
    """Pairs with no direct contact (no call, message, e-mail or shared group) that are linked another way:

    - money between them;
    - a narrow go-between (reaching at most NARROW_REACH people) in contact with each of them within a day of each
      other on ROUTE_DAYS days or more;
    - a phone with no owner name whose positions are beside a person's phone on BESIDE_DAYS days or more;
    - a theory or finding of the case that names the person and speaks of a phone, when the case holds exactly one
      phone with no owner name (so "the phone" can only be that one), with what the records hold between them.
    Each line says which of these it is; none of them sets a level."""
    unnamed = [k for k, p in everyone.items() if p["key"].startswith("phone:")]
    by_pair = {(p["a"], p["b"]): p for p in pairs}
    out: dict[tuple, dict] = {}

    def add(p, words, why):
        item = out.setdefault((p["a"], p["b"]), {"a": p["a"], "b": p["b"], "label": p["label"], "reasons": [], "words": []})
        item["reasons"].append(why)
        item["words"].append(words)

    for p in pairs:
        if p["direct"]:
            continue
        a, b = labels[p["a"]], labels[p["b"]]
        mo = p["kinds"]["money"]
        if mo["count"]:
            add(p, f"{a} and {b} never message or call each other, yet {mo['count']:,} payment"
                   f"{'' if mo['count'] == 1 else 's'} pass between them, {M.fmt_money(mo['total_minor'])} in all.", "money")
        narrow = [g for g in p["kinds"]["through_others"]["go_betweens"]
                  if reaches.get(g["key"], 99) <= NARROW_REACH and g.get("route_days", 0) >= ROUTE_DAYS]
        if narrow:
            g = narrow[0]
            add(p, f"{a} and {b} never contact each other, but {g['label']} contacts both within a day of each other "
                   f"on {g['route_days']:,} days ({g['with_a']:,} records with {a}, {g['with_b']:,} with {b}).", "go_between")
        place = p["kinds"]["place"]["count"]
        if (p["a"] in unnamed or p["b"] in unnamed) and place >= BESIDE_DAYS:
            add(p, f"{a} and {b} never contact each other, yet their phones are together on {place:,} days: "
                   "one phone may be the other person's.", "beside")
    if len(unnamed) == 1:
        phone = unnamed[0]
        for t in theories:
            words = f"{t.get('title') or ''}. {t.get('body') or ''}"
            if not _PHONE_WORD.search(words):
                continue
            for k, person in everyone.items():
                if k == phone or not any(M.names_match(n, words) for n in person["names"] if n):
                    continue
                p = by_pair.get(M.pair_key(k, phone))
                if not p or p["direct"]:
                    continue
                found = [KIND_WORDS[x].lower() for x in p["kinds_found"]]
                held = ("the records hold only " + ", ".join(found)) if found else \
                    "the records hold no contact, no shared place and nothing else between them"
                add(p, f"The {t['entry_type']} “{(t.get('title') or '')[:80]}” names {labels[k]} and speaks of a phone; "
                       f"{labels[phone]} is the only phone with no owner name, and {held}.", "theory")
    return list(out.values())


# ---- go-betweens and the graph -------------------------------------------------------------------------------------

def go_between_panel(x: str, reach, labels: dict, everyone: dict, place: dict, pos_days: dict, zone: str) -> dict:
    """Who ``x`` reaches, its contacts with every person of the case (zero included), the days its phone is beside
    each person's phone, and the order its repeating messages follow (the same lines, in the same order, on several
    stretches of activity; a stretch ends after M.CLUSTER_GAP with nothing)."""
    tzz = M.tz(zone)
    people = [k for k in everyone if k != x]
    contacts = {k: len({r["ref"] for r in reach[x].get(k, [])}) for k in people}
    reached = [k for k in people if contacts[k]]
    mine = sorted({r["ref"]: r for k in reached for r in reach[x][k]}.values(), key=lambda r: r["at"])
    stretches: list[list[dict]] = []
    for r in mine:
        if stretches and r["at"] - stretches[-1][-1]["at"] <= M.CLUSTER_GAP:
            stretches[-1].append(r)
        else:
            stretches.append([r])

    def step(r):
        other = next((k for k in _ends(r) if k != x and k in everyone), None)
        sent = r.get("owner") == x and r.get("sender") in (None, x) or r.get("sender") == x
        return other, ("to" if sent else "from"), (r.get("body") or "").strip().casefold()

    # the lines it sends again and again (in two or more stretches), in the order of each stretch
    sent_in = defaultdict(set)
    for i, st in enumerate(stretches):
        for r in st:
            o, way, body = step(r)
            if way == "to" and body:
                sent_in[(o, body)].add(i)
    repeating = {k for k, v in sent_in.items() if len(v) >= 2}
    seqs = []
    for st in stretches:
        seq = []
        for r in st:
            o, way, body = step(r)
            if way == "to" and (o, body) in repeating and (o, body) not in seq:
                seq.append((o, body))
        seqs.append(seq)

    def contains(seq, sub):
        it = iter(seq)
        return all(any(s == x_ for s in it) for x_ in sub)
    pattern = None
    cands = Counter(tuple(q) for q in seqs if len(q) >= 2)
    if cands:
        best = max(cands, key=lambda c: (sum(1 for q in seqs if contains(q, c)), len(c)))
        hits = [i for i, q in enumerate(seqs) if contains(q, best)]
        if len(hits) >= 2:
            st = stretches[hits[0]]
            steps = []
            for o, body in best:
                r = next(r for r in st if step(r)[0] == o and step(r)[2] == body and step(r)[1] == "to")
                local = r["at"].astimezone(tzz)
                reply = next((y for y in st if y["at"] > r["at"] and step(y)[0] == o and step(y)[1] == "from"), None)
                steps.append({"at": M.iso(r["at"]), "local": local.strftime("%a %H:%M"), "with": labels.get(o) if o else None,
                              "body": r.get("body"), "ref": r["ref"],
                              "reply": {"local": reply["at"].astimezone(tzz).strftime("%H:%M"), "body": reply.get("body"),
                                        "ref": reply["ref"]} if reply and reply["at"] - r["at"] <= timedelta(hours=1) else None})
            pattern = {"times": len(hits), "of": len(stretches), "steps": steps, "zone": zone,
                       "days": [stretches[i][0]["at"].astimezone(tzz).date().isoformat() for i in hits]}
    return {"key": x, "label": labels.get(x, x), "reaches": [labels[k] for k in reached],
            "people": [{"key": k, "label": labels[k], "contacts": contacts[k],
                        "place_days": len(place.get(M.pair_key(k, x), [])), "position_days": pos_days.get(k, 0)}
                       for k in people],
            "records": len(mine), "position_days": pos_days.get(x, 0), "pattern": pattern}


def graph(pairs: list[dict], people: list[dict], docs: list[dict], reaches: dict, labels: dict, owners: list[str]) -> dict:
    """People, go-betweens and documents: a line per pair with direct contact (width = records between them), a
    dashed line where the only route is a narrow go-between, and a square per set of people named together."""
    lines, dashed = [], []
    for p in pairs:
        n = p["kinds"]["contact"]["count"]
        if n:
            lines.append({"a": p["a"], "b": p["b"], "records": n})
            continue
        via = [g for g in p["kinds"]["through_others"]["go_betweens"] if reaches.get(g["key"], 99) <= NARROW_REACH]
        money = p["kinds"]["money"]["count"]
        if via or money:   # no direct contact, yet a narrow go-between or money between them
            dashed.append({"a": p["a"], "b": p["b"], "via": via[0]["key"] if via else None,
                           "via_label": via[0]["label"] if via else None, "money": money})
    sets: dict[tuple, list[dict]] = defaultdict(list)
    for d in docs:
        who = tuple(sorted({x["key"] for x in d["people"]} & set(labels)))
        if len(who) >= 2:
            sets[who].append(d)
    squares = [{"people": list(k), "documents": [{"file_id": d["file_id"], "file": d["file"],
                                                  "people": [{"key": x["key"], "by": x["by"], "pages": x["pages"]}
                                                             for x in d["people"] if x["key"] in k]} for d in v]}
               for k, v in sorted(sets.items(), key=lambda kv: -len(kv[1]))]
    named_two = sum(1 for d in docs if len({x["key"] for x in d["people"]} & set(owners)) >= 2)
    return {"nodes": people, "lines": lines, "dashed": dashed, "squares": squares,
            "documents": {"read": len(docs), "naming_two_phone_owners": named_two}}


# ---- levels from leads ---------------------------------------------------------------------------------------------

def attach_levels(db, case_id, grid: dict) -> dict:
    """Each pair's level from the saved leads naming both people (the Corroborate engine's level). Never computed here."""
    try:
        from services.leads.store import list_leads
    except ImportError:
        list_leads = None
    leads = []
    if list_leads is not None:
        try:
            leads = list_leads(db, case_id)
        except Exception:  # noqa: BLE001 - the grid stays readable when leads cannot be read; the note says so
            grid["notes"].append("Leads could not be read, so no pair shows a level.")
    if list_leads is None:
        grid["notes"].append("Levels come from the Leads list, which is not in this release yet.")
    def keys(lead):
        return {x.get("key") if isinstance(x, dict) else x for x in lead.get("people") or ()}
    def focal_ok(lead, p):
        # A no-link lead about one person names everyone it searched against, but it is a finding about that person
        # alone: it says nothing of two others it names. A lead with one person in focus speaks only for their pairs.
        focal = (lead.get("detail") or {}).get("person") or ((lead.get("question") or {}).get("chips") or {}).get("person")
        return not focal or focal in (p["a"], p["b"])
    for p in grid["pairs"]:
        # the Leads list's own order (strongest first); a lead set aside is listed but never gives the level
        mine = [l for l in leads if {p["a"], p["b"]} <= keys(l) and focal_ok(l, p)]
        mine.sort(key=lambda l: LEVEL_ORDER.index((l.get("level") or {}).get("key")) if (l.get("level") or {}).get("key")
                  in LEVEL_ORDER else len(LEVEL_ORDER))
        p["leads"] = [{"id": l["id"], "title": l.get("title"), "level": l.get("level"), "origin": l.get("origin"),
                       "state": l.get("state"), "searched": l.get("searched"), "raises": l.get("raises"),
                       "lowers": l.get("lowers")} for l in mine[:6]]
        # A lead naming a group can join two people who never met: the finder chains phones near each other (A near B,
        # B near C), so a pair whose own records hold nothing takes no level from it. Only a
        # search that found no link may label such a pair. The lead stays listed under the pair.
        weighable = mine if p["state"] != "nothing" else [
            l for l in mine if (l.get("level") or {}).get("key") == "no_link_found"]
        top = next((l for l in weighable if (l.get("level") or {}).get("key") in LEVEL_ORDER), None)
        if top:
            p["level"] = top.get("level")
            p["state"] = "no_link" if (top.get("level") or {}).get("key") == "no_link_found" else "weighed"
    return grid


# ---- cache ---------------------------------------------------------------------------------------------------------

# Measured 18 Nov on the server (load 16-52, nice 15): the demo case (2,126 records) reads in 4-9 s, Phone reference 2
# (7,417) in 15.6 s; Phone reference 1 (527,856) took 810 s for shared words alone and was still reading the grid at
# 2.5 GB after 25 minutes. A request never reads more than this.
MAX_RECORDS = 10_000


def case_size(db, case_id) -> int:
    from sqlalchemy import text as _text
    c = {"c": str(case_id)}
    n = db.execute(_text("SELECT count(*) FROM phone_comm_events WHERE case_id = :c"), c).scalar() or 0
    n += db.execute(_text("SELECT count(*) FROM pol_place_observation WHERE case_id = :c"), c).scalar() or 0
    return int(n)


_cache: dict[str, tuple[float, dict]] = {}
_lock = threading.Lock()


def cached_build(db, case_id, *, fresh: bool = False) -> dict:
    """The grid for a case, read at most every CACHE_SECONDS (its time is in ``read_at``); levels are always current."""
    from services.corroborate.store import CaseStore
    key = str(case_id)
    size = case_size(db, case_id)
    if size > MAX_RECORDS:
        return {"schema": SCHEMA, "refused": True, "records": size, "limit": MAX_RECORDS,
                "words": (f"This case holds {size:,} phone records and positions. Who overlaps with whom reads a whole case "
                          f"at once, and only up to {MAX_RECORDS:,}, so it is not shown here. Corroborate chosen people or "
                          "records instead: that reads only what they hold.")}
    with _lock:
        hit = _cache.get(key)
    if hit and not fresh and time.time() - hit[0] < CACHE_SECONDS:
        grid = hit[1]
    else:
        store = CaseStore(db, case_id)
        grid = build(store, shared_content(store))
        grid["read_at"] = datetime.now(timezone.utc).isoformat()
        with _lock:
            _cache[key] = (time.time(), grid)
    import copy
    return attach_levels(db, case_id, copy.deepcopy(grid))


def shared_content(store) -> dict | None:
    """lx-overlapviews-b's shared words, when that module is in this release; None says "not searched"."""
    try:
        from services.corroborate import shared_words
    except ImportError:
        return None
    out = shared_words.shared_content(store)
    # the same-bytes files are read apart from the words; every one is listed here, because each pair is counted
    files = shared_words.same_files(store, listed=None)
    out["files_common"], out["files_shared"] = files["files_common"], files["files_shared"]
    out["phone_of_label"] = {label: ext for ext, label in shared_words._labels(store).items()}
    return out
