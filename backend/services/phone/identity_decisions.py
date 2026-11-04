"""Who is who: suggestions and the decisions that link phone identities to people (docs/cellebrite/02 sections 8.7,
8.8; 07 J-7).

A person is a dossier. Nothing links automatically: a suggestion proposes, a person decides, and every decision is
appended to the case decision ledger (``decisions.record``) with the corrections feed in the same transaction. The
current link of an identity is the replay of its decisions in ``subject_sequence`` order, materialised in
``phone_identity_links`` (and rejected pairs in ``phone_identity_rejections``); those tables are rebuilt from the
ledger and are never its source.

Suggestions (8.7) never rest on names alone: R5 ``name_support`` only adds to another reason. Weights: R1
``same_card`` 0.6 on one phone, 0.8 on two or more; R2 ``owner_accounts`` 0.7; R3 ``dossier_contact`` 0.9; R5 adds
0.1; R4 ``financial_identifier`` 0.8 (a reviewed account identifier of kind ``phone_number`` or ``email``, 02-U11,
whose account's holder is linked to a dossier). Score = 1 - product(1 - w).

Every suggestion is listed, whatever its score (Neil 2026-11-04: "We don't want to miss things based on an arbitrary
cutoff."), with a strength on the app's one scale (services.match_strength) by a stated rule (:func:`strength`):
strong at 0.8 or more with two or more independent sources, moderate at ``THRESHOLD`` (0.5) or more, weak at 0.2 or
more, faint below. A name seen on both sides with nothing else is listed as a faint ``name_only`` suggestion
(weight 0.1): names alone never make it more than faint, and its reasons say so. Strongest first, then by score, ties
by identity key. A pair with a recorded rejection is not suggested again; a WhatsApp group is never a person.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from collections import defaultdict

from sqlalchemy import text

from services.phone import fold as F
from services.phone import identifiers

SUGGESTION_NS = uuid.UUID("2f7a9c41-0d6b-4e3a-9a52-8c1e7b3d5f60")
WEIGHTS = {"same_card": (0.6, 0.8), "owner_accounts": 0.7, "dossier_contact": 0.9, "financial_identifier": 0.8,
           "name_support": 0.1, "name_only": 0.1}
#: The boundary between a moderate and a weak suggestion (never a cutoff: every suggestion is listed).
THRESHOLD = 0.5
STRONG_AT, WEAK_AT = 0.8, 0.2
CHANGED = ("Someone else changed this person while you were reviewing. Their change is shown below. Your choice was "
           "not saved. Choose again.")
TYPED_REQUIRED = ("unlink_phone_identity", "split")


class IdentityDecisionError(ValueError):
    status = 422


class StaleRevision(IdentityDecisionError):
    status = 409


# ---- current state from the ledger -----------------------------------------------------------------------------

def links_revision(conn, identity_ids) -> str:
    """sha256 over the current link rows of these identities (8.8): a mismatch means someone decided meanwhile."""
    rows = conn.execute(text(
        "SELECT identity_id::text, dossier_id::text, decision_id::text FROM phone_identity_links WHERE "
        "identity_id = ANY(CAST(:i AS uuid[])) ORDER BY 1"), {"i": [str(i) for i in identity_ids]}).fetchall()
    return hashlib.sha256(json.dumps([list(r) for r in rows]).encode()).hexdigest()


def case_links_revision(conn, case_id) -> str:
    """``links_revision`` of the whole case, which spec 05 includes in its input revision (8.8)."""
    rows = conn.execute(text("SELECT identity_id::text, dossier_id::text, decision_id::text FROM phone_identity_links "
                             "WHERE case_id = :c ORDER BY 1"), {"c": case_id}).fetchall()
    return hashlib.sha256(json.dumps([list(r) for r in rows]).encode()).hexdigest()


def rebuild(conn, case_id, identity_ids):
    """Replay the ledger for these identities into ``phone_identity_links`` and ``phone_identity_rejections``."""
    ids = [str(i) for i in identity_ids]
    conn.execute(text("DELETE FROM phone_identity_links WHERE identity_id = ANY(CAST(:i AS uuid[]))"), {"i": ids})
    conn.execute(text("DELETE FROM phone_identity_rejections WHERE identity_id = ANY(CAST(:i AS uuid[]))"), {"i": ids})
    link, rejected = {}, {}
    for subject, decision, after, did in conn.execute(text(
            "SELECT subject_id, decision, after, id FROM adjudications WHERE subject_type = 'phone_identity' AND "
            "subject_id = ANY(CAST(:i AS uuid[])) ORDER BY subject_id, subject_sequence"), {"i": ids}):
        s = str(subject)
        if decision == "link_phone_identity":
            link[s] = ((after or {}).get("dossier_id"), did)
        elif decision == "unlink_phone_identity":
            link.pop(s, None)
        elif decision in ("reject_phone_identity_link", "restore_phone_identity_link"):
            for k, v in (after or {}).items():
                if k.startswith("rejected:"):
                    if v:
                        rejected[(s, k[len("rejected:"):])] = did
                    else:
                        rejected.pop((s, k[len("rejected:"):]), None)
    for s, (dossier, did) in link.items():
        if dossier:
            conn.execute(text("INSERT INTO phone_identity_links (case_id, identity_id, dossier_id, decision_id) VALUES "
                              "(:c, :i, :d, :did)"), {"c": case_id, "i": s, "d": dossier, "did": did})
    for (s, target), did in rejected.items():
        conn.execute(text("INSERT INTO phone_identity_rejections (case_id, identity_id, target, decision_id) VALUES "
                          "(:c, :i, :t, :did)"), {"c": case_id, "i": s, "t": target, "did": did})


# ---- suggestions -----------------------------------------------------------------------------------------------

def _score(reasons):
    p = 1.0
    for r in reasons:
        w = r["weight"]
        p *= (1 - w)
    return round(1 - p, 2)


def financial_identifier_dossiers(session, case_id) -> list:
    """``[(identity_key, dossier_id, account_id)]`` for every reviewed account identifier of kind ``phone_number`` or
    ``email`` whose account has a holder party with a reviewed entity link to a dossier's canonical entity (8.9)."""
    from services.financial.account_identity import CONTACT_KINDS, identity_state, normalised_contact
    state = identity_state(session, case_id)
    dossiers = defaultdict(set)
    from sqlalchemy import select
    from postgres.models.case_profile import CaseProfile
    for d, key in session.execute(select(CaseProfile.id, CaseProfile.canonical_entity_key).where(
            CaseProfile.case_id == case_id, CaseProfile.canonical_entity_key.is_not(None),
            CaseProfile.archived_at.is_(None))):
        dossiers[key].add(str(d))
    out = set()
    for account in state["accounts"]:
        review = account.get("identity_review") or {}
        holders = {r["party"]["id"] for r in account.get("relationships") or [] if r.get("role") == "holder"}
        targets = {d for link in review.get("entity_links") or [] if link.get("party_id") in holders
                   for d in dossiers.get(link.get("entity_key"), ())}
        if not targets:
            continue
        for ident in review.get("identifiers") or []:
            if ident.get("kind") not in CONTACT_KINDS:
                continue
            v = normalised_contact(ident["kind"], ident.get("value"))
            if v is None:
                continue
            key = ("phone:" if ident["kind"] == "phone_number" else "email:") + v
            out.update((key, d, account["id"]) for d in targets)
    return sorted(out)


def compute_suggestions(conn, case_id) -> dict:
    """Recompute the open suggestions of a case from the current sightings, links and dossier contacts."""
    rows = candidate_rows(conn, case_id)
    conn.execute(text("DELETE FROM phone_identity_suggestions WHERE case_id = :c AND state = 'open'"), {"c": case_id})
    return _store(conn, case_id, rows)


def candidate_rows(conn, case_id) -> list:
    """Every suggestion of the case, strongest first (reads only; ``compute_suggestions`` stores them)."""
    from sqlalchemy.orm import Session
    from services.dossier_service import contacts_for_suggestions
    from services.phone.readings import phone_labels
    labels = phone_labels(conn, case_id)
    ident = {str(r.id): r for r in conn.execute(text(
        "SELECT id, identity_key, kind, subkind, value_normalised FROM phone_identities WHERE case_id = :c AND "
        "sighting_count > 0"), {"c": case_id})}
    persons = {k: v for k, v in ident.items() if not (v.kind == "other" and v.subkind == "group")}
    linked = {str(r[0]): str(r[1]) for r in conn.execute(text(
        "SELECT identity_id, dossier_id FROM phone_identity_links WHERE case_id = :c"), {"c": case_id})}
    rejected = {(str(r[0]), r[1]) for r in conn.execute(text(
        "SELECT identity_id, target FROM phone_identity_rejections WHERE case_id = :c"), {"c": case_id})}
    names = defaultdict(set)
    for i, name in conn.execute(text("SELECT identity_id, name FROM pv_identity_name WHERE case_id = :c"), {"c": case_id}):
        names[str(i)].add(F.fold(name))
    seen_names = defaultdict(set)  # identity -> {(card record or None, folded name)}
    for i, card, name in conn.execute(text(
            "SELECT identity_id, card_record_uid, name_alongside FROM pv_identity_sighting WHERE case_id = :c AND "
            "name_alongside IS NOT NULL"), {"c": case_id}):
        seen_names[str(i)].add((str(card) if card else None, F.fold(name)))
    found = defaultdict(list)  # (tuple(identity ids), dossier id or None) -> reasons

    # R1: two identities on one card
    cards = defaultdict(lambda: {"ids": set(), "phones": set(), "records": set()})
    for card, i, ext in conn.execute(text(
            "SELECT card_record_uid, identity_id, extraction_id FROM pv_identity_sighting WHERE case_id = :c AND "
            "context = 'listed_on_card' AND card_type IN ('Contact', 'UserAccount', 'ContactEntry')"), {"c": case_id}):
        cards[card]["ids"].add(str(i))
        cards[card]["phones"].add(str(ext))
    pairs = defaultdict(lambda: {"phones": set(), "records": set()})
    for card, v in cards.items():
        ids = sorted(x for x in v["ids"] if x in persons)
        for a in range(len(ids)):
            for b in range(a + 1, len(ids)):
                pairs[(ids[a], ids[b])]["phones"] |= v["phones"]
                pairs[(ids[a], ids[b])]["records"].add(str(card))
    for (a, b), v in pairs.items():
        if linked.get(a) and linked.get(a) == linked.get(b):
            continue
        if (a, "identity:" + b) in rejected or (b, "identity:" + a) in rejected:
            continue
        w = WEIGHTS["same_card"][1 if len(v["phones"]) > 1 else 0]
        found[((a, b), None)].append({"reason": "same_card", "weight": w, "records": sorted(v["records"])[:3],
                                      "record_count": len(v["records"]),
                                      "phones": sorted(labels.get(p, p) for p in v["phones"])})

    # R2: the phone's own accounts when its owner identity is linked to a dossier
    for ext, owner_key in conn.execute(text(
            "SELECT o.extraction_id, o.identity_key FROM pv_owner_candidate o WHERE o.case_id = :c AND "
            "o.candidate_kind = 'number' AND o.tier IN (1, 2)"), {"c": case_id}):
        owner_id = next((k for k, v in ident.items() if v.identity_key == owner_key), None)
        dossier = linked.get(owner_id) if owner_id else None
        if not dossier:
            continue
        for i, cnt in conn.execute(text(
                "SELECT identity_id, occurrences FROM pv_owner_candidate WHERE extraction_id = :e AND "
                "candidate_kind = 'account'"), {"e": ext}):
            i = str(i)
            if i in persons and linked.get(i) != dossier and (i, dossier) not in rejected:
                found[((i,), dossier)].append({"reason": "owner_accounts", "weight": WEIGHTS["owner_accounts"],
                                               "records": [], "record_count": int(cnt),
                                               "phones": [labels.get(str(ext), str(ext))]})

    # R3: a dossier contact of kind phone or email with the same normalised value
    session = Session(bind=conn)
    try:
        contacts = contacts_for_suggestions(session, case_id)
    finally:
        session.close()
    by_value = {}
    for k, v in persons.items():
        by_value.setdefault(v.identity_key, k)
    dossier_names = {}
    for c in contacts:
        if c.get("kind") not in ("phone", "email") or not c.get("value"):
            continue
        idf = identifiers.classify(c["value"], region="US")
        if idf is None or idf.kind not in ("phone", "email"):
            continue
        i = by_value.get(idf.identity_key)
        d = c["dossier_id"]
        if i and linked.get(i) != d and (i, d) not in rejected:
            found[((i,), d)].append({"reason": "dossier_contact", "weight": WEIGHTS["dossier_contact"], "records": [],
                                     "record_count": 1, "phones": []})

    # R4: a reviewed financial identifier of kind phone_number or email (02-U11), on an account whose holder party
    # is linked to a dossier (8.9: the account's reviewed entity link names the dossier's canonical entity)
    session = Session(bind=conn)
    try:
        held = financial_identifier_dossiers(session, case_id)
    finally:
        session.close()
    for key, d, account_id in held:
        i = by_value.get(key)
        if i and linked.get(i) != d and (i, d) not in rejected:
            found[((i,), d)].append({"reason": "financial_identifier", "weight": WEIGHTS["financial_identifier"],
                                     "records": [], "record_count": 1, "phones": [], "account_id": account_id})
    if found:
        for d, name in conn.execute(text("SELECT id::text, display_name FROM case_profiles WHERE case_id = :c"),
                                    {"c": case_id}):
            dossier_names[d] = F.fold(name)

    # R5: name support, only beside another reason
    rows = []
    for (ids, dossier), reasons in found.items():
        support = False
        if dossier and dossier_names.get(dossier):
            support = any(dossier_names[dossier] in names.get(i, ()) for i in ids)
        elif len(ids) == 2:
            # names seen away from the cards that gave R1: the card's own name on both numbers is that card's
            # evidence again, not support for it
            shared = set(pairs.get(tuple(ids), {}).get("records", ()))
            a, b = ({n for card, n in seen_names.get(i, ()) if card not in shared} for i in ids)
            support = bool(a & b)
        if support:
            reasons = reasons + [{"reason": "name_support", "weight": WEIGHTS["name_support"], "records": [],
                                  "record_count": 0, "phones": []}]
        rows.append({"ids": list(ids), "dossier": dossier, "reasons": reasons, "score": _score(reasons)})

    # A name on both sides and nothing else: listed as faint, never more (R5 never makes a suggestion stronger alone)
    if not dossier_names:
        for d, name in conn.execute(text("SELECT id::text, display_name FROM case_profiles WHERE case_id = :c"),
                                    {"c": case_id}):
            dossier_names[d] = F.fold(name)
    rows.extend(name_only_rows(persons, names, found, linked, rejected, dossier_names))
    rows.sort(key=lambda r: (_rank(r["score"], r["reasons"]), -r["score"], min(ident[i].identity_key for i in r["ids"])))
    return rows


def _store(conn, case_id, rows) -> dict:
    decided = {(tuple(sorted(str(x) for x in r[0])), str(r[1]) if r[1] else None) for r in conn.execute(text(
        "SELECT identity_ids, dossier_id FROM phone_identity_suggestions WHERE case_id = :c"), {"c": case_id})}
    n = 0
    for r in rows:
        key = (tuple(sorted(r["ids"])), r["dossier"])
        if key in decided:
            continue
        conn.execute(text(
            "INSERT INTO phone_identity_suggestions (id, case_id, identity_ids, dossier_id, reasons, score, state) "
            "VALUES (:id, :c, CAST(:i AS uuid[]), :d, CAST(:r AS jsonb), :s, 'open')"),
            {"id": uuid.uuid5(SUGGESTION_NS, "%s|%s|%s" % (case_id, ",".join(key[0]), key[1])), "c": case_id,
             "i": list(key[0]), "d": r["dossier"], "r": json.dumps(r["reasons"]), "s": r["score"]})
        n += 1
    return {"suggestions": n}


def suggestions(conn, case_id) -> list:
    out = []
    for r in conn.execute(text(
            "SELECT s.id, s.identity_ids, s.dossier_id, s.reasons, s.score, s.state FROM phone_identity_suggestions s "
            "WHERE s.case_id = :c AND s.state = 'open' ORDER BY s.score DESC, s.id"), {"c": case_id}):
        idents = [dict(x._mapping) for x in conn.execute(text(
            "SELECT id::text, identity_key, kind, value_display FROM phone_identities WHERE id = ANY(:i) ORDER BY "
            "identity_key"), {"i": list(r.identity_ids)})]
        lv, words = strength(float(r.score), r.reasons or [])
        out.append({"id": str(r.id), "identities": idents, "dossier_id": str(r.dossier_id) if r.dossier_id else None,
                    "reasons": r.reasons, "score": float(r.score), "level": lv, "strength_reasons": words,
                    "expected_revision": links_revision(conn, r.identity_ids)})
    # 8.7: strongest first, then by score, ties by identity key
    out.sort(key=lambda x: (_rank(x["score"], x["reasons"]), -x["score"],
                            min((i["identity_key"] for i in x["identities"]), default="")))
    return out


def name_only_rows(persons, names, found, linked, rejected, dossier_names) -> list:
    """Suggestions resting on a name alone: two identities a phone saves under the same name, or an identity saved
    under a dossier's name, when no other reason pairs them. Weight 0.1, so always faint."""
    out = []
    taken = set(found)
    by_name = defaultdict(set)
    for i, ns in names.items():
        if i in persons:
            for n in ns:
                if n:
                    by_name[n].add(i)
    pairs = {}
    for n, ids in by_name.items():
        ids = sorted(ids)
        for a in range(len(ids)):
            for b in range(a + 1, len(ids)):
                x, y = ids[a], ids[b]
                if ((x, y), None) in taken or (linked.get(x) and linked.get(x) == linked.get(y)):
                    continue
                if (x, "identity:" + y) in rejected or (y, "identity:" + x) in rejected:
                    continue
                pairs.setdefault((x, y), set()).add(n)
    for (x, y), ns in pairs.items():
        out.append({"ids": [x, y], "dossier": None, "score": _score([{"weight": WEIGHTS["name_only"]}]),
                    "reasons": [{"reason": "name_only", "weight": WEIGHTS["name_only"], "records": [],
                                 "record_count": 0, "phones": [], "names": sorted(ns)[:3]}]})
    by_dossier = defaultdict(list)
    for d, n in dossier_names.items():
        if n:
            by_dossier[n].append(d)
    for n, ids in by_name.items():
        for d in by_dossier.get(n, ()):
            for i in sorted(ids):
                if ((i,), d) in taken or linked.get(i) == d or (i, d) in rejected:
                    continue
                out.append({"ids": [i], "dossier": d, "score": _score([{"weight": WEIGHTS["name_only"]}]),
                            "reasons": [{"reason": "name_only", "weight": WEIGHTS["name_only"], "records": [],
                                         "record_count": 0, "phones": [], "names": [n]}]})
    return out


_MATCH_WORDS = {"same_card": "listed together on one contact card", "owner_accounts": "the phone's own account",
                "dossier_contact": "a contact detail on the person's dossier",
                "financial_identifier": "an account identifier on a reviewed statement",
                "name_support": "the same name, seen apart from the other reason",
                "name_only": "the same name only: nothing else links them"}


def strength(score, reasons):
    """``(level, {match, substantiation})`` by the stated rule (module docstring); never a model's call."""
    from services.match_strength import LEVELS
    kinds = sorted({r.get("reason") for r in reasons if r.get("reason")})
    phones = {p for r in reasons for p in (r.get("phones") or [])}
    records = sum(int(r.get("record_count") or 0) for r in reasons)
    sources = len([k for k in kinds if k not in ("name_support", "name_only")]) + (1 if len(phones) > 1 else 0)
    if score >= STRONG_AT and sources >= 2:
        lv = "strong"
    elif score >= THRESHOLD:
        lv = "moderate"
    elif score >= WEAK_AT:
        lv = "weak"
    else:
        lv = "faint"
    assert lv in LEVELS
    sub = []
    if phones:
        sub.append("seen on %d phone%s" % (len(phones), "" if len(phones) == 1 else "s"))
    if records:
        sub.append("%d record%s" % (records, "" if records == 1 else "s"))
    if not sources:
        sub.append("no source beyond a saved name")
    return lv, {"match": [_MATCH_WORDS.get(k, k) for k in kinds] + ["score %.2f" % score], "substantiation": sub}


def _rank(score, reasons):
    from services.match_strength import rank
    return rank(strength(score, reasons)[0])


def decided_count(conn, case_id) -> int:
    """Suggestions a person decided (linked or marked not the same person) in this case."""
    return int(conn.execute(text("SELECT count(*) FROM phone_identity_suggestions WHERE case_id = :c AND state IN "
                                 "('accepted', 'rejected')"), {"c": case_id}).scalar() or 0)


# ---- deciding --------------------------------------------------------------------------------------------------

def decide(db, *, case_id, decision, identity_keys, actor, user, dossier_id=None, new_person_name=None, reason=None,
           note=None, reasons_shown=None, expected_revision=None, target_identity_key=None) -> dict:
    """``decision``: ``link_phone_identity``, ``unlink_phone_identity``, ``split`` (unlink each, one reason, one
    transaction), ``reject_phone_identity_link`` or ``restore_phone_identity_link`` (against ``dossier_id`` or
    ``target_identity_key``). Links take a standard reason built from the reasons shown; Unlink and Split need a
    typed reason (8.8)."""
    from postgres.models.enums import AdjudicationDecision, AdjudicationSubject
    from postgres.models.phone_identity import PhoneIdentity
    from services import manual_changes
    from services.financial import decisions
    conn = db.connection()
    keys = sorted(set(identity_keys or ()))
    if not keys:
        raise IdentityDecisionError("Choose at least one identity.")
    rows = db.query(PhoneIdentity).filter(PhoneIdentity.case_id == case_id, PhoneIdentity.identity_key.in_(keys)) \
        .order_by(PhoneIdentity.id).with_for_update().all()
    if len(rows) != len(keys):
        raise IdentityDecisionError("An identity is not in this case.")
    if any(r.kind == "other" and r.subkind == "group" for r in rows) and decision == "link_phone_identity":
        raise IdentityDecisionError("A group conversation is not a person and cannot be linked to one.")
    ids = [r.id for r in rows]
    if expected_revision is not None and expected_revision != links_revision(conn, ids):
        raise StaleRevision(CHANGED)
    current = {str(r[0]): str(r[1]) for r in conn.execute(text(
        "SELECT identity_id, dossier_id FROM phone_identity_links WHERE identity_id = ANY(CAST(:i AS uuid[]))"),
        {"i": [str(i) for i in ids]})}
    typed = (reason or "").strip()
    kind = "standard"
    if decision in TYPED_REQUIRED:
        if not typed:
            raise IdentityDecisionError("Unlink and Split need a reason in your own words.")
        kind = "typed"
    elif typed:
        kind = "typed"
    written, also = [], []
    if decision == "link_phone_identity":
        if new_person_name and new_person_name.strip():
            from services.dossier_service import create_dossier
            created = create_dossier(db, case_id=case_id, user=user, data={"display_name": new_person_name.strip()},
                                     commit=False)
            dossier_id = created["id"]
        if not dossier_id:
            raise IdentityDecisionError("Choose a person or name a new one.")
        exists = conn.execute(text("SELECT 1 FROM case_profiles WHERE id = :d AND case_id = :c"),
                              {"d": dossier_id, "c": case_id}).scalar()
        if not exists:
            raise IdentityDecisionError("That person is not in this case.")
        words = typed or standard_link_reason(reasons_shown or [])
        for r in rows:
            if current.get(str(r.id)) == str(dossier_id):
                continue
            written.append(decisions.record(
                db, case_id=case_id, subject=r, subject_type=AdjudicationSubject.phone_identity,
                decision=AdjudicationDecision.link_phone_identity, reason=words, actor=actor, reason_kind=kind,
                before={"dossier_id": current.get(str(r.id)), "note": None, "reasons_shown": None},
                after={"dossier_id": str(dossier_id), "note": note.strip() if note and note.strip() else None,
                       "reasons_shown": reasons_shown or None}))
        conn.execute(text("UPDATE phone_identity_suggestions SET state = 'accepted' WHERE case_id = :c AND state = "
                          "'open' AND identity_ids && CAST(:i AS uuid[]) AND (dossier_id = :d OR dossier_id IS NULL)"),
                     {"c": case_id, "i": [str(i) for i in ids], "d": dossier_id})
    elif decision in ("unlink_phone_identity", "split"):
        for r in rows:
            if str(r.id) not in current:
                continue
            written.append(decisions.record(
                db, case_id=case_id, subject=r, subject_type=AdjudicationSubject.phone_identity,
                decision=AdjudicationDecision.unlink_phone_identity, reason=typed, actor=actor, reason_kind="typed",
                before={"dossier_id": current[str(r.id)]}, after={"dossier_id": None}))
        if not written:
            raise IdentityDecisionError("None of these identities is linked to a person.")
    elif decision in ("reject_phone_identity_link", "restore_phone_identity_link"):
        if target_identity_key:
            other = db.query(PhoneIdentity).filter(PhoneIdentity.case_id == case_id,
                                                   PhoneIdentity.identity_key == target_identity_key).one_or_none()
            if other is None:
                raise IdentityDecisionError("The other identity is not in this case.")
            target = "identity:%s" % other.id
            also.append(other.id)
        elif dossier_id:
            target = str(dossier_id)
        else:
            raise IdentityDecisionError("Say what these identities are not.")
        flag = decision == "reject_phone_identity_link"
        words = typed or ("Marked as not the same person on the review screen" if flag else
                          "Restored as a possible match on the review screen")
        for r in rows:
            written.append(decisions.record(
                db, case_id=case_id, subject=r, subject_type=AdjudicationSubject.phone_identity,
                decision=AdjudicationDecision(decision), reason=words, actor=actor, reason_kind=kind,
                before={"rejected:" + target: not flag}, after={"rejected:" + target: flag}))
        if flag:
            # only the suggestion this rejection answers: these identities with that identity, or with that person
            if target_identity_key:
                conn.execute(text(
                    "UPDATE phone_identity_suggestions SET state = 'rejected' WHERE case_id = :c AND state = 'open' AND "
                    "dossier_id IS NULL AND identity_ids @> CAST(:i AS uuid[])"),
                    {"c": case_id, "i": [str(i) for i in list(ids) + [other.id]]})
            else:
                conn.execute(text(
                    "UPDATE phone_identity_suggestions SET state = 'rejected' WHERE case_id = :c AND state = 'open' AND "
                    "dossier_id = :d AND identity_ids && CAST(:i AS uuid[])"),
                    {"c": case_id, "d": dossier_id, "i": [str(i) for i in ids]})
    else:
        raise IdentityDecisionError("Unknown decision.")
    db.flush()
    rebuild(conn, case_id, ids + also)
    manual_changes.record_change(db, "phone_identity", case_id, {"type": "phone_identity", "id": ",".join(keys)},
                                 {"dossier": sorted(set(current.values()))},
                                 {"decision": decision, "dossier": str(dossier_id) if dossier_id else None},
                                 actor, written[0].reason if written else (typed or decision),
                                 link="/cases/%s/phone-review" % case_id,
                                 pattern_key=manual_changes.make_pattern_key("phone_identity", decision))
    compute_suggestions(conn, case_id)
    return {"decisions": [str(w.id) for w in written], "dossier_id": str(dossier_id) if dossier_id else None,
            "revision": links_revision(conn, ids)}


def standard_reason_kinds(reasons_shown):
    return sorted({r.get("reason") if isinstance(r, dict) else str(r) for r in reasons_shown or []})


READING = {"same_card": "listed together on one contact card", "owner_accounts": "the phone's own account",
           "dossier_contact": "a contact detail on this person's dossier", "name_support": "the same name",
           "financial_identifier": "an account identifier on a statement"}


def standard_link_reason(reasons_shown):
    kinds = [READING.get(k, k) for k in standard_reason_kinds(reasons_shown)]
    if not kinds:
        return "Linked on the review screen"
    return "Linked on the review screen after seeing: %s" % "; ".join(kinds)
