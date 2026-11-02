"""Identities, sightings, each phone's names and the owner of each phone (docs/cellebrite/02 sections 8.5, 8.6).

Runs in the sweep's transaction after the mappings (an applier hook, 6.7), on generation n+1:

1. **Sightings.** Every identifier seen on the phone, with its context: a Party (``party``, or ``owner_party`` when
   its ``IsPhoneOwner`` is True; the identity key was set as the participation was written, 8.2), an entry
   listed on a card (``listed_on_card``: the ``Value`` of a nested PhoneNumber, UserID or EmailAddress, with the
   card's name alongside), an ``Account`` field of a top-level record (``account_field``), and the report header
   (``header``: metadata item ``MSISDN``; a SIMData record whose Category is ``SIM/USIM MSISDN``).
2. **Identities.** One row per (case, identity key), id uuid5 of both, never deleted: counts are recomputed over
   the current generation of the case's active phones, so a key no longer seen keeps its row at 0.
3. **Each phone's names** (8.5): contact names of the cards listing the identity (``contact``, ``contact_entry``)
   with their latest TimeModified, and the Party names (``name_in_record``), with counts. A name that is the
   identifier echoed back (equal to it, of phone shape or of JID shape) is not a name (NM-4). The phone's name is
   the most frequent contact name, ties by latest TimeModified then lowest record id; else the most frequent
   name in records under the same rule; else none.
4. **Owner candidates** (8.6): tier 1 header numbers, tier 2 numbers counted over ``Account`` fields and owner
   parties; owner names (owner parties' names and UserAccount names, NM-4 filtered); the owner's other
   identities (``account``), listed for suggestions and never merged. The computed owner is tier 1's top, else
   tier 2's (count, then the lower E.164 string), else none; a ``set_phone_owner`` decision overrides it
   (``register_owner_decision``) and the candidates stay visible.
"""
from __future__ import annotations

import json
import re
import uuid
from collections import defaultdict

from sqlalchemy import text

from services.phone import generic, identifiers

IDENTITY_NS = uuid.UUID("5c1f0a7e-3d2b-4b8e-9f61-2a7d4c8e0b13")
SIGHTING_NS = uuid.UUID("9a4e2c61-7b3f-4d0a-8e15-6c2b9f1d3a70")
CARD_ENTRY_TYPES = ("PhoneNumber", "UserID", "EmailAddress")
CARD_NAME_BASIS = {"Contact": "contact", "ContactEntry": "contact_entry"}
SIM_MSISDN = "SIM/USIM MSISDN"
SIGHTING_COLUMNS = ("sighting_uid", "case_id", "extraction_id", "identity_id", "identity_key", "record_uid",
                    "root_record_uid", "card_record_uid", "card_type", "field_path", "identifier_raw", "context",
                    "name_alongside", "region_basis", "instant", "generation")
NAME_COLUMNS = ("case_id", "extraction_id", "identity_id", "name", "basis", "occurrences", "latest_modified",
                "first_record_uid", "is_phone_name", "generation")
OWNER_COLUMNS = ("case_id", "extraction_id", "candidate_kind", "identity_id", "identity_key", "name", "tier",
                 "occurrences", "basis", "basis_detail", "generation")
_hooks = {"owner_decision": None}


def identity_id(case_id, key):
    return uuid.uuid5(IDENTITY_NS, "%s|%s" % (case_id, key))


def register_owner_decision(fn):
    """``fn(conn, extraction_id) -> {"identity_keys": [...], "decision_id": ..., "by": ..., "at": ...} or None``:
    the current ``set_phone_owner`` decision (8.8)."""
    _hooks["owner_decision"] = fn


def is_echo(name, raw=None):
    """NM-4: a value that is the identifier echoed back is not a name."""
    s = (name or "").strip()
    if not s:
        return True
    if raw is not None and s == str(raw).strip():
        return True
    if identifiers.JID_USER.match(s) or identifiers.JID_GROUP.match(s):
        return True
    if not any(c.isalpha() for c in s) and identifiers.NUMBER_SHAPE.match(s):
        return 7 <= len(re.sub(r"\D", "", s)) <= 17
    return False


# ---- the pass ------------------------------------------------------------------------------------------------------

def build(conn, extraction_id, generation, the_plan=None) -> dict:
    """The sweep's applier hook: sightings, identities, names and owner candidates of generation ``generation``."""
    case_id = conn.execute(text("SELECT case_id FROM phone_extractions WHERE id = :e"), {"e": extraction_id}).scalar()
    region = (the_plan or {}).get("marks", {}).get("region")
    if not region:
        from services.phone.mappings import apply
        region = apply.default_region(conn, extraction_id)
    p = {"c": case_id, "e": extraction_id, "g": generation}
    stats = defaultdict(int)
    w = generic.Writer(conn, {"phone_identity_sightings": SIGHTING_COLUMNS, "phone_identity_names": NAME_COLUMNS,
                              "phone_owner_candidates": OWNER_COLUMNS})

    # identities of the parties: keys were set as the participations were written
    party_keys = conn.execute(text(
        "SELECT DISTINCT ON (identity_key) identity_key, identifier_raw, region_basis FROM phone_participations "
        "WHERE extraction_id = :e AND generation = :g AND identity_key IS NOT NULL ORDER BY identity_key, "
        "participation_uid"), p).fetchall()
    found = {}
    for key, raw, basis in party_keys:
        ident = identifiers.classify(raw, region=region[0], region_basis=region[1])
        found[key] = ident if ident is not None and ident.identity_key == key else None

    # cards, account fields and the header: classified here
    rows = []
    for t_uid, rec, root, path, raw, category, card, card_type, card_name, source in conn.execute(text(
            "SELECT t.text_uid, t.record_uid, t.root_record_uid, t.field_path, t.effective_value, cat.effective_value, "
            "s.parent_record_uid, ps.model_type, nm.effective_value, src.effective_value "
            "FROM phone_texts t JOIN phone_record_summaries s ON s.record_uid = t.record_uid AND s.generation = t.generation "
            "LEFT JOIN phone_record_summaries ps ON ps.record_uid = s.parent_record_uid AND ps.generation = t.generation "
            "LEFT JOIN phone_texts cat ON cat.record_uid = t.record_uid AND cat.generation = t.generation AND "
            "cat.field_name = 'Category' AND cat.value_index = 0 "
            "LEFT JOIN phone_texts nm ON nm.record_uid = s.parent_record_uid AND nm.generation = t.generation AND "
            "nm.field_name = 'Name' AND nm.value_index = 0 "
            "LEFT JOIN phone_texts src ON src.record_uid = t.root_record_uid AND src.generation = t.generation AND "
            "src.field_name = 'Source' AND src.value_index = 0 "
            "WHERE t.extraction_id = :e AND t.generation = :g AND t.model_type = ANY(CAST(:types AS text[])) AND "
            "t.field_name = 'Value' AND t.case_id = :c"), dict(p, types=list(CARD_ENTRY_TYPES))):
        rows.append(("listed_on_card", t_uid, rec, root, path, raw, {"app": source, "category": category},
                     card, card_type, None if is_echo(card_name, raw) else card_name))
    for t_uid, rec, path, raw, source, mt in conn.execute(text(
            "SELECT t.text_uid, t.record_uid, t.field_path, t.effective_value, src.effective_value, t.model_type "
            "FROM phone_texts t LEFT JOIN phone_texts src ON src.record_uid = t.record_uid AND src.generation = "
            "t.generation AND src.field_name = 'Source' AND src.value_index = 0 WHERE t.extraction_id = :e AND "
            "t.generation = :g AND t.case_id = :c AND t.field_name = 'Account' AND t.record_uid = t.root_record_uid"), p):
        rows.append(("account_field", t_uid, rec, rec, path, raw, {"app": source}, None, None, None))
    for t_uid, rec, root, raw in conn.execute(text(
            "SELECT v.text_uid, v.record_uid, v.root_record_uid, v.effective_value FROM phone_texts v JOIN phone_texts c "
            "ON c.record_uid = v.record_uid AND c.generation = v.generation AND c.field_name = 'Category' AND "
            "c.effective_value = :sim WHERE v.extraction_id = :e AND v.generation = :g AND v.case_id = :c AND "
            "v.model_type = 'SIMData' AND v.field_name = 'Value'"), dict(p, sim=SIM_MSISDN)):
        rows.append(("header", t_uid, rec, root, "SIMData.Value", raw, {}, None, None, None))
    for i, raw in enumerate(header_msisdns(conn, extraction_id)):
        rows.append(("header", uuid.uuid5(SIGHTING_NS, "%s|metadata|%d" % (extraction_id, i)), None, None,
                     "metadata:MSISDN", raw, {}, None, None, None))
    instants = _root_instants(conn, extraction_id, generation, {r[3] for r in rows if r[3]})
    pending = []
    for context, uid, rec, root, path, raw, ctx, card, card_type, name in rows:
        ident = identifiers.classify(raw, context=ctx, region=region[0], region_basis=region[1])
        if ident is None:
            stats["sightings_without_identity:" + context] += 1
            continue
        if found.get(ident.identity_key) is None:
            found[ident.identity_key] = ident
        pending.append({
            "sighting_uid": uuid.uuid5(SIGHTING_NS, "%s|%s" % (context, uid)), "case_id": case_id,
            "extraction_id": extraction_id, "identity_id": identity_id(case_id, ident.identity_key),
            "identity_key": ident.identity_key, "record_uid": rec, "root_record_uid": root, "card_record_uid": card,
            "card_type": card_type, "field_path": path, "identifier_raw": raw, "context": context,
            "name_alongside": name, "region_basis": ident.region_basis, "instant": instants.get(root),
            "generation": generation})
        stats["sightings:" + context] += 1

    _upsert_identities(conn, case_id, found, party_keys)  # before any sighting row (foreign key)
    for row in pending:
        w.add("phone_identity_sightings", row)
    w.flush()
    n = conn.execute(text(
        "INSERT INTO phone_identity_sightings (" + ", ".join(SIGHTING_COLUMNS) + ") "
        "SELECT p.participation_uid, p.case_id, p.extraction_id, i.id, p.identity_key, p.record_uid, p.root_record_uid, "
        "NULL, NULL, coalesce(p.container_field, ''), p.identifier_raw, "
        "CASE WHEN p.is_phone_owner THEN 'owner_party' ELSE 'party' END, "
        "CASE WHEN p.name_in_record IS NULL OR btrim(p.name_in_record) = '' OR p.name_in_record = p.identifier_raw "
        "THEN NULL ELSE p.name_in_record END, p.region_basis, coalesce(ev.sort_instant, rs.first_instant), p.generation "
        "FROM phone_participations p JOIN phone_identities i ON i.case_id = p.case_id AND i.identity_key = p.identity_key "
        "LEFT JOIN phone_comm_events ev ON ev.record_uid = p.root_record_uid AND ev.generation = p.generation "
        "LEFT JOIN phone_record_summaries rs ON rs.record_uid = p.root_record_uid AND rs.generation = p.generation "
        "WHERE p.case_id = :c AND p.extraction_id = :e AND p.generation = :g AND p.identity_key IS NOT NULL"), p).rowcount
    stats["sightings:party_and_owner_party"] = n
    stats["identities_on_phone"] = conn.execute(text(
        "SELECT count(DISTINCT identity_id) FROM phone_identity_sightings WHERE extraction_id = :e AND generation = :g"),
        p).scalar()
    stats["names"] = _names(conn, w, case_id, extraction_id, generation)
    owner = _owner_candidates(conn, w, case_id, extraction_id, generation)
    w.flush()
    stats["owner_candidates"] = owner
    _recount(conn, case_id, extraction_id, generation)
    return {"identities:" + k: v for k, v in stats.items()}


def header_items(conn, extraction_id) -> dict:
    """``{name: [values]}`` of every metadata ``item`` in the report header, values in document order."""
    out = {}
    for (skel,) in conn.execute(text("SELECT skeleton FROM phone_extraction_documents WHERE extraction_id = :e "
                                     "ORDER BY document_index"), {"e": extraction_id}):
        stack = [skel]
        while stack:
            el = stack.pop()
            if not isinstance(el, list) or not el or not isinstance(el[0], str) or el[0][:1] == "@":
                continue
            if el[0] == "item" and (el[1] or {}).get("name") and isinstance(el[2], str) and el[2].strip():
                out.setdefault(el[1]["name"], []).append(el[2])
            for c in reversed(el[3] or ()) if len(el) > 3 else ():
                stack.append(c)
    return out


def header_msisdns(conn, extraction_id):
    """Values of metadata items named ``MSISDN`` in the report header (8.6 tier 1), in document order."""
    return header_items(conn, extraction_id).get("MSISDN", [])


def _root_instants(conn, extraction_id, generation, roots):
    if not roots:
        return {}
    return {r[0]: r[1] for r in conn.execute(text(
        "SELECT rs.record_uid, coalesce(ev.sort_instant, rs.first_instant) FROM phone_record_summaries rs "
        "LEFT JOIN phone_comm_events ev ON ev.record_uid = rs.record_uid AND ev.generation = rs.generation "
        "WHERE rs.extraction_id = :e AND rs.generation = :g AND rs.record_uid = ANY(CAST(:r AS uuid[]))"),
        {"e": extraction_id, "g": generation, "r": [str(x) for x in roots]})}


def _upsert_identities(conn, case_id, found, party_keys):
    rows = []
    kinds = {}
    for key, raw, basis in party_keys:
        kinds[key] = raw
    for key, ident in found.items():
        if ident is None:  # a participation key the classifier no longer gives: keep the key, show it as captured
            kind = key.split(":", 1)[0]
            kind = {"app": "app_user"}.get(kind, kind)
            value = key.split(":", 1)[1] if ":" in key else key
            rows.append({"id": identity_id(case_id, key), "c": case_id, "k": key,
                         "kind": kind if kind in ("phone", "app_user", "email", "other") else "other", "sub": None,
                         "vn": value, "vd": kinds.get(key) or value})
        else:
            rows.append({"id": identity_id(case_id, key), "c": case_id, "k": key, "kind": ident.kind,
                         "sub": ident.subkind, "vn": ident.value_normalised, "vd": ident.value_display})
    for i in range(0, len(rows), 1000):
        conn.execute(text(
            "INSERT INTO phone_identities (id, case_id, identity_key, kind, subkind, value_normalised, value_display) "
            "VALUES (:id, :c, :k, :kind, :sub, :vn, :vd) ON CONFLICT (case_id, identity_key) DO NOTHING"),
            rows[i:i + 1000])


def _pick(cands):
    """The most frequent; ties by latest TimeModified, then lowest record id (8.5 rule 3)."""
    return sorted(cands, key=lambda c: (-c["occurrences"], -(c["latest_modified"].timestamp()
                                                              if c["latest_modified"] else float("-inf")),
                                         str(c["first_record_uid"] or "~")))[0]


def _names(conn, w, case_id, extraction_id, generation):
    p = {"e": extraction_id, "g": generation}
    by_identity = defaultdict(list)
    for ident, card_type, name, n, modified, first in conn.execute(text(
            "SELECT x.identity_id, x.card_type, x.name_alongside, count(*), max(tv.effective_instant), "
            "min(x.card_record_uid::text) FROM phone_identity_sightings x LEFT JOIN phone_time_values tv ON "
            "tv.record_uid = x.card_record_uid AND tv.generation = x.generation AND tv.field_name = 'TimeModified' "
            "WHERE x.extraction_id = :e AND x.generation = :g AND x.context = 'listed_on_card' AND "
            "x.card_type = ANY(CAST(:ct AS text[])) AND x.name_alongside IS NOT NULL GROUP BY 1, 2, 3"),
            dict(p, ct=list(CARD_NAME_BASIS))):
        if not is_echo(name):
            by_identity[ident].append({"name": name, "basis": CARD_NAME_BASIS[card_type], "occurrences": int(n),
                                       "latest_modified": modified, "first_record_uid": first})
    for ident, name, n, first in conn.execute(text(
            "SELECT identity_id, name_alongside, count(*), min(record_uid::text) FROM phone_identity_sightings "
            "WHERE extraction_id = :e AND generation = :g AND context IN ('party', 'owner_party') AND "
            "name_alongside IS NOT NULL GROUP BY 1, 2"), p):
        if not is_echo(name):
            by_identity[ident].append({"name": name, "basis": "name_in_record", "occurrences": int(n),
                                       "latest_modified": None, "first_record_uid": first})
    count = 0
    for ident, cands in by_identity.items():
        contact = [c for c in cands if c["basis"] in ("contact", "contact_entry")]
        chosen = _pick(contact) if contact else _pick(cands)
        for c in cands:
            w.add("phone_identity_names", dict(c, case_id=case_id, extraction_id=extraction_id, identity_id=ident,
                                               is_phone_name=c is chosen, generation=generation))
            count += 1
    return count


def _owner_candidates(conn, w, case_id, extraction_id, generation):
    p = {"e": extraction_id, "g": generation}
    n = 0
    numbers = defaultdict(lambda: defaultdict(int))
    accounts = defaultdict(lambda: defaultdict(int))
    for ident, key, kind, context, cnt in conn.execute(text(
            "SELECT x.identity_id, x.identity_key, i.kind, x.context, count(*) FROM phone_identity_sightings x "
            "JOIN phone_identities i ON i.id = x.identity_id WHERE x.extraction_id = :e AND x.generation = :g AND "
            "x.context IN ('header', 'account_field', 'owner_party') GROUP BY 1, 2, 3, 4"), p):
        if kind == "phone":
            numbers[(ident, key)][context] += int(cnt)
        if context != "header":
            accounts[(ident, key)][context] += int(cnt)
    tier1 = {k: v["header"] for k, v in numbers.items() if v.get("header")}
    tier2 = {k: v.get("account_field", 0) + v.get("owner_party", 0) for k, v in numbers.items()
             if v.get("account_field", 0) + v.get("owner_party", 0)}
    for tier, cands, basis in ((1, tier1, "extracted"), (2, tier2, "inferred")):
        for (ident, key), cnt in sorted(cands.items(), key=lambda kv: (-kv[1], kv[0][1])):
            w.add("phone_owner_candidates", {
                "case_id": case_id, "extraction_id": extraction_id, "candidate_kind": "number", "identity_id": ident,
                "identity_key": key, "name": None, "tier": tier, "occurrences": cnt, "basis": basis,
                "basis_detail": json.dumps(dict(numbers[(ident, key)])), "generation": generation})
            n += 1
    computed = _top(tier1) or _top(tier2)
    for (ident, key), by_ctx in sorted(accounts.items(), key=lambda kv: kv[0][1]):
        if computed and key == computed[1]:
            continue
        w.add("phone_owner_candidates", {
            "case_id": case_id, "extraction_id": extraction_id, "candidate_kind": "account", "identity_id": ident,
            "identity_key": key, "name": None, "tier": None, "occurrences": sum(by_ctx.values()), "basis": "account",
            "basis_detail": json.dumps(dict(by_ctx)), "generation": generation})
        n += 1
    names = defaultdict(lambda: defaultdict(int))
    for name, cnt in conn.execute(text(
            "SELECT name_alongside, count(*) FROM phone_identity_sightings WHERE extraction_id = :e AND generation = :g "
            "AND context = 'owner_party' AND name_alongside IS NOT NULL GROUP BY 1"), p):
        names[name]["owner_party"] += int(cnt)
    for name, cnt in conn.execute(text(
            "SELECT effective_value, count(*) FROM phone_texts WHERE extraction_id = :e AND generation = :g AND "
            "model_type = 'UserAccount' AND field_name = 'Name' AND record_uid = root_record_uid GROUP BY 1"), p):
        names[name]["user_account"] += int(cnt)
    for name, by_src in sorted(names.items(), key=lambda kv: (-sum(kv[1].values()), kv[0])):
        if is_echo(name):
            continue
        w.add("phone_owner_candidates", {
            "case_id": case_id, "extraction_id": extraction_id, "candidate_kind": "name", "identity_id": None,
            "identity_key": None, "name": name, "tier": None, "occurrences": sum(by_src.values()), "basis": "name",
            "basis_detail": json.dumps(dict(by_src)), "generation": generation})
        n += 1
    return n


def _top(cands):
    if not cands:
        return None
    return sorted(cands.items(), key=lambda kv: (-kv[1], kv[0][1]))[0][0]


def _recount(conn, case_id, extraction_id, generation):
    """Counts per identity over the case's active phones: this extraction's new generation, the others' current."""
    conn.execute(text(
        "WITH cur AS (SELECT x.identity_id, x.extraction_id, x.instant FROM phone_identity_sightings x "
        "JOIN phone_extractions e ON e.id = x.extraction_id AND e.standing = 'active' "
        "LEFT JOIN phone_interpretation_state s ON s.extraction_id = x.extraction_id "
        "WHERE x.case_id = :c AND ((x.extraction_id = :e AND x.generation = :g) OR "
        "(x.extraction_id <> :e AND x.generation = s.generation))), "
        "agg AS (SELECT identity_id, count(*) n, count(DISTINCT extraction_id) phones, min(instant) f, max(instant) l "
        "FROM cur GROUP BY 1) "
        "UPDATE phone_identities i SET sighting_count = coalesce(agg.n, 0), phone_count = coalesce(agg.phones, 0), "
        "first_instant = agg.f, last_instant = agg.l, updated_at = now() FROM phone_identities i2 "
        "LEFT JOIN agg ON agg.identity_id = i2.id WHERE i.id = i2.id AND i2.case_id = :c AND "
        "(i.sighting_count, i.phone_count, i.first_instant, i.last_instant) IS DISTINCT FROM "
        "(coalesce(agg.n, 0), coalesce(agg.phones, 0), agg.f, agg.l)"),
        {"c": case_id, "e": extraction_id, "g": generation})


def recount_case(conn, case_id):
    """Counts per identity over the current generation of the case's active phones (9.4): run when a phone is
    deleted or superseded, so an identity seen only there drops to zero and one seen elsewhere keeps its count."""
    conn.execute(text(
        "WITH cur AS (SELECT x.identity_id, x.extraction_id, x.instant FROM phone_identity_sightings x "
        "JOIN phone_extractions e ON e.id = x.extraction_id AND e.standing = 'active' "
        "JOIN phone_interpretation_state s ON s.extraction_id = x.extraction_id AND x.generation = s.generation "
        "WHERE x.case_id = :c), "
        "agg AS (SELECT identity_id, count(*) n, count(DISTINCT extraction_id) phones, min(instant) f, max(instant) l "
        "FROM cur GROUP BY 1) "
        "UPDATE phone_identities i SET sighting_count = coalesce(agg.n, 0), phone_count = coalesce(agg.phones, 0), "
        "first_instant = agg.f, last_instant = agg.l, updated_at = now() FROM phone_identities i2 "
        "LEFT JOIN agg ON agg.identity_id = i2.id WHERE i.id = i2.id AND i2.case_id = :c AND "
        "(i.sighting_count, i.phone_count, i.first_instant, i.last_instant) IS DISTINCT FROM "
        "(coalesce(agg.n, 0), coalesce(agg.phones, 0), agg.f, agg.l)"), {"c": case_id})


# ---- reading -------------------------------------------------------------------------------------------------------

def owner(conn, extraction_id) -> dict:
    """The owner of one phone: computed (tier 1, else tier 2's top, else none), a decision when one is recorded,
    and every candidate with its tier, count and basis (8.6)."""
    cands = [dict(r._mapping) for r in conn.execute(text(
        "SELECT candidate_kind, identity_id, identity_key, name, tier, occurrences, basis, basis_detail FROM "
        "pv_owner_candidate WHERE extraction_id = :e ORDER BY candidate_kind, tier NULLS LAST, occurrences DESC, "
        "identity_key, name"), {"e": extraction_id})]
    numbers = [c for c in cands if c["candidate_kind"] == "number"]
    top = None
    for tier in (1, 2):
        tiered = sorted((c for c in numbers if c["tier"] == tier), key=lambda c: (-c["occurrences"], c["identity_key"]))
        if tiered:
            top = tiered[0]
            break
    out = {"computed": {"identity_key": top["identity_key"], "tier": top["tier"], "basis": top["basis"]} if top else
           {"identity_key": None, "tier": None, "basis": "unidentified"},
           "decided": None, "candidates": cands}
    fn = _hooks["owner_decision"]
    d = fn(conn, extraction_id) if fn else None
    if d:
        out["decided"] = d
        out["owner_identity_keys"], out["owner_basis"] = list(d["identity_keys"]), "manual"
    else:
        out["owner_identity_keys"] = [top["identity_key"]] if top else []
        out["owner_basis"] = out["computed"]["basis"]
    return out


def install():
    from services.phone import sweep
    sweep.register_applier(build)
