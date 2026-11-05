"""People across phones (03 section 10; 07 J-3, J-16, XF-5, 4.5): the Phone identities list, a dossier's "On the phones"
panel and the scope presets built from identity links.

Every count here is the count Conversations shows for the link it opens. They read the stream module's own tables and
party rule (``streams.Query``, ``PARTY_KEY_SQL``) and count copies as it does: one per copy group, a group being per
phone (03 3.4), so counts per phone add up to the total. Nothing here writes; a link is a person's decision and goes
through ``identity_decisions.decide``. A suggestion is reported as a suggestion and never counted as linked.
"""
from __future__ import annotations

from sqlalchemy import text

from services.phone import crossings, readings, streams
from services.phone import fold as phone_fold
from services.phone import time_display as T
from services.phone.filters import StreamFilter

HISTORY_LIMIT = 50
GROUP_SQL = "coalesce(ev.dup_group_uid, ev.event_uid::text)"


class NotInCase(LookupError):
    pass


def event_counts(conn, case_id, keys=None) -> dict:
    """``{identity_key: {extraction_id: (events, first, last)}}``: events an identity takes part in on each phone,
    equal to Conversations for that identity and phone (one query, however many identities)."""
    q, _ = streams._query(conn, StreamFilter(case_id=str(case_id)))
    params, where = dict(q.params), q.where_sql()
    if keys is not None:
        params["keys"] = sorted(keys)
        where += " AND %s = ANY(CAST(:keys AS text[]))" % streams.PARTY_KEY_SQL
    out: dict = {}
    for r in conn.execute(text(
            "SELECT %s AS k, ev.extraction_id::text AS e, count(DISTINCT %s) AS n, min(ev.sort_instant) AS f, "
            "max(ev.sort_instant) AS l FROM %s JOIN phone_participations p ON p.record_uid = ev.record_uid AND "
            "p.generation = ev.generation WHERE %s AND %s IS NOT NULL GROUP BY 1, 2"
            % (streams.PARTY_KEY_SQL, GROUP_SQL, q.FROM, where, streams.PARTY_KEY_SQL)), params):
        out.setdefault(r.k, {})[r.e] = (int(r.n), r.f, r.l)
    return out


def registry(conn, case_id, *, q="", phone=None, linked=None, cursor=0, limit=50) -> dict:
    """The Phone identities list and the identity picker (03 10.2, 10.4; 4.4): one row per identity with each phone's
    name for it, events per phone, first and last contact and its linked person, searched as Search folds (11.3).
    ``total`` is exact; the busiest come first."""
    text_q = q.strip()
    folded = phone_fold.fold(text_q) if text_q else ""
    digits = "".join(ch for ch in q if ch.isdigit())
    idents = conn.execute(text(
        "SELECT i.identity_id, i.identity_key, i.kind, i.subkind, i.value_display, i.value_normalised, i.person_id, "
        "p.display_name AS person_name FROM pv_identity i LEFT JOIN case_profiles p ON p.id = i.person_id "
        "WHERE i.case_id = :c"), {"c": case_id}).fetchall()
    names: dict = {}
    for n in conn.execute(text("SELECT identity_id, extraction_id, name, basis, is_phone_name FROM pv_identity_name "
                               "WHERE case_id = :c ORDER BY extraction_id"), {"c": case_id}):
        names.setdefault(n.identity_id, []).append(n)
    on_phone = None
    if phone:
        on_phone = {r[0] for r in conn.execute(text(
            "SELECT DISTINCT identity_id FROM pv_identity_sighting WHERE extraction_id = CAST(:e AS uuid)"),
            {"e": str(phone)})}

    def matches(r):
        # Folded as Search folds (11.3): "jose" finds "José"; three or more digits match the number's digits.
        if not text_q:
            return True
        if not folded:
            return False  # punctuation only: nothing to match
        hay = [r.value_display, r.identity_key] + [n.name for n in names.get(r.identity_id, [])]
        if any(folded in phone_fold.fold(h) for h in hay if h):
            return True
        return len(digits) >= 3 and digits in "".join(ch for ch in (r.value_normalised or "") if ch.isdigit())

    hits = [r for r in idents if matches(r) and (linked is None or bool(r.person_id) == linked)
            and (on_phone is None or r.identity_id in on_phone)]
    counts = event_counts(conn, case_id)

    def events(r):
        return sum(v[0] for v in counts.get(r.identity_key, {}).values())

    hits.sort(key=lambda r: (-events(r), r.value_display or "", r.identity_key))
    total = len(hits)
    labels = readings.phone_labels(conn, case_id)
    items = []
    for r in hits[cursor:cursor + limit]:
        per = counts.get(r.identity_key, {})
        firsts = [v[1] for v in per.values() if v[1]]
        lasts = [v[2] for v in per.values() if v[2]]
        items.append({
            "identity_key": r.identity_key, "kind": r.kind, "subkind": r.subkind, "value_display": r.value_display,
            "names": [{"phone_label": labels.get(str(n.extraction_id)), "extraction_id": str(n.extraction_id),
                       "name": n.name, "basis": n.basis} for n in names.get(r.identity_id, []) if n.is_phone_name],
            "person": {"id": str(r.person_id), "display_name": r.person_name} if r.person_id else None,
            "event_count": events(r),
            "phones": sorted(({"extraction_id": e, "phone_label": labels.get(e, "A phone"), "events": v[0]}
                              for e, v in per.items()), key=lambda x: (-x["events"], x["phone_label"])),
            "first_contact": T.iso(min(firsts)) if firsts else None,
            "last_contact": T.iso(max(lasts)) if lasts else None,
            "can_be_a_person": not (r.kind == "other" and r.subkind == "group")})
    nxt = cursor + len(items)
    linked_total = sum(1 for r in idents if r.person_id)
    return {"case_id": str(case_id), "items": items, "total": int(total), "next_cursor": nxt if nxt < total else None,
            "in_case": len(idents), "linked_in_case": linked_total}


def _dossier(conn, case_id, dossier_id):
    row = conn.execute(text("SELECT id::text AS id, display_name AS name, profile_type AS type FROM case_profiles "
                            "WHERE case_id = :c AND id = CAST(:d AS uuid)"),
                       {"c": str(case_id), "d": str(dossier_id)}).first()
    if row is None:
        raise NotInCase("That person is not in this case.")
    return row


def _contact_dates(conn, case_id, identity_ids) -> dict:
    """``{(extraction_id, identity_id): (created, modified)}`` from the contact cards listing an identity (03 10.2)."""
    out = {}
    if not identity_ids:
        return out
    for r in conn.execute(text(
            "SELECT x.extraction_id::text AS e, x.identity_id::text AS i, "
            "min(tv.effective_instant) FILTER (WHERE tv.field_name = 'TimeCreated') AS created, "
            "max(tv.effective_instant) FILTER (WHERE tv.field_name = 'TimeModified') AS modified "
            "FROM phone_identity_sightings x JOIN phone_interpretation_state st ON st.extraction_id = x.extraction_id "
            "AND st.generation = x.generation JOIN phone_extractions e ON e.id = x.extraction_id AND e.case_id = :c AND "
            "e.standing = 'active' LEFT JOIN phone_time_values tv ON tv.record_uid = x.card_record_uid AND "
            "tv.generation = x.generation AND tv.field_name IN ('TimeCreated', 'TimeModified') WHERE x.context = "
            "'listed_on_card' AND x.identity_id = ANY(CAST(:i AS uuid[])) GROUP BY 1, 2"),
            {"c": str(case_id), "i": [str(i) for i in identity_ids]}):
        out[(r.e, r.i)] = (r.created, r.modified)
    return out


def _channel_counts(conn, case_id, keys) -> dict:
    """``{extraction_id: {"total", "first", "last", "kinds": {kind: {direction: n}}}}`` under the filter Conversations
    uses for this person (one identity list, Involving), so the panel adds up to its total."""
    f = StreamFilter.model_validate(crossings.conversations_scope(case_id, keys)[0])
    q, _ = streams._query(conn, f)
    out: dict = {}
    for r in conn.execute(text(
            "WITH m AS (%s) SELECT extraction_id::text AS e, kind, direction, count(*) FILTER (WHERE %s) AS n, "
            "min(sort_instant) AS f, max(sort_instant) AS l FROM m GROUP BY 1, 2, 3"
            % (q.matched_sql(), streams._shown(f))), q.params):
        if not r.n:
            continue
        d = out.setdefault(r.e, {"total": 0, "first": None, "last": None, "kinds": {}})
        d["total"] += int(r.n)
        d["kinds"].setdefault(r.kind, {})[r.direction or "unknown"] = int(r.n)
        d["first"] = min((x for x in (d["first"], r.f) if x), default=None)
        d["last"] = max((x for x in (d["last"], r.l) if x), default=None)
    return out


def _history(conn, case_id, dossier_id) -> tuple[list, int]:
    """Every link decision naming this person, newest first (03 10.3: reversible from the dossier)."""
    d = str(dossier_id)
    where = ("a.case_id = :c AND a.subject_type = 'phone_identity' AND (a.after ->> 'dossier_id' = :d OR a.before ->> "
             "'dossier_id' = :d OR jsonb_exists(a.after, :r) OR jsonb_exists(a.before, :r))")
    p = {"c": str(case_id), "d": d, "r": "rejected:" + d}
    total = conn.execute(text("SELECT count(*) FROM adjudications a WHERE " + where), p).scalar()
    rows = conn.execute(text(
        "SELECT a.id::text AS id, a.decision, a.reason, a.reason_kind, a.actor_name, a.actor_email, a.created_at, "
        "i.identity_key, i.value_display FROM adjudications a JOIN phone_identities i ON i.id = a.subject_id WHERE "
        + where + " ORDER BY a.created_at DESC, a.subject_sequence DESC LIMIT :n"), dict(p, n=HISTORY_LIMIT)).fetchall()
    return [{"id": r.id, "decision": str(r.decision), "reason": r.reason, "reason_kind": r.reason_kind,
             "actor": r.actor_name or r.actor_email, "at": T.iso(r.created_at), "identity_key": r.identity_key,
             "value_display": r.value_display} for r in rows], int(total)


def dossier_phones(conn, case_id, dossier_id) -> dict:
    """The dossier's "On the phones" panel (03 10.2, 07 XF-5): its linked identities, and for each phone the names that
    phone holds, the contact's dates, counts by channel and direction, first and last contact, each with the list it
    opens. Suggestions are stated apart and never counted."""
    from services.phone import identity_decisions
    person = _dossier(conn, case_id, dossier_id)
    linked = conn.execute(text(
        "SELECT identity_id, identity_key, kind, value_display FROM pv_identity WHERE case_id = :c AND person_id = "
        "CAST(:d AS uuid) ORDER BY identity_key"), {"c": str(case_id), "d": str(dossier_id)}).fetchall()
    keys = [r.identity_key for r in linked]
    labels = readings.phone_labels(conn, case_id)
    zone = streams.case_zone(conn, str(case_id))["name"]
    open_rows = conn.execute(text(
        "SELECT identity_ids FROM phone_identity_suggestions WHERE case_id = :c AND dossier_id = CAST(:d AS uuid) AND "
        "state = 'open'"), {"c": str(case_id), "d": str(dossier_id)}).fetchall()
    suggested = len({str(i) for r in open_rows for i in r.identity_ids})
    history, history_total = _history(conn, case_id, dossier_id)
    base = {"case_id": str(case_id), "dossier": {"id": person.id, "name": person.name, "type": person.type},
            "suggested_identities": suggested, "history": history, "history_total": history_total,
            "phones_in_case": len(labels), "review_href": "/cases/%s/phone-review" % case_id}
    if not keys:
        return dict(base, identities=[], phones=[], total=0, conversations_href=None,
                    expected_revision=None)
    per_identity = event_counts(conn, case_id, keys)
    channels = _channel_counts(conn, case_id, keys)
    names: dict = {}
    for n in conn.execute(text(
            "SELECT extraction_id::text AS e, identity_id::text AS i, identity_key, name, basis, occurrences, "
            "is_phone_name FROM pv_identity_name WHERE case_id = :c AND identity_id = ANY(CAST(:i AS uuid[])) ORDER BY "
            "is_phone_name DESC, occurrences DESC, name"),
            {"c": str(case_id), "i": [str(r.identity_id) for r in linked]}):
        names.setdefault(n.e, []).append(n)
    dates = _contact_dates(conn, case_id, [r.identity_id for r in linked])
    value_of = {str(r.identity_id): r.value_display for r in linked}

    def href(**kw):
        return crossings.conversations_scope(case_id, keys, zone=zone, **kw)[1]

    phones = []
    for e in sorted(set(channels) | set(names), key=lambda x: (-channels.get(x, {}).get("total", 0), labels.get(x, x))):
        c = channels.get(e, {"total": 0, "first": None, "last": None, "kinds": {}})
        rows = []
        for n in names.get(e, []):
            if not n.is_phone_name:
                continue
            created, modified = dates.get((e, n.i), (None, None))
            rows.append({"name": n.name, "value_display": value_of.get(n.i), "basis": n.basis,
                         "contact_created": T.iso(created) if created else None,
                         "contact_modified": T.iso(modified) if modified else None})
        phones.append({"extraction_id": e, "label": labels.get(e, "A phone"), "names": rows, "total": c["total"],
                       "first_contact": T.iso(c["first"]) if c["first"] else None,
                       "last_contact": T.iso(c["last"]) if c["last"] else None,
                       "kinds": [{"kind": k, "directions": [{"direction": d, "events": n} for d, n in sorted(v.items())]}
                                 for k, v in sorted(c["kinds"].items())],
                       "conversations_href": href(phones=[e])})
    identities = []
    for r in linked:
        per = per_identity.get(r.identity_key, {})
        identities.append({"identity_key": r.identity_key, "kind": r.kind, "value_display": r.value_display,
                           "events": sum(v[0] for v in per.values()), "phones": len(per),
                           "conversations_href": crossings.conversations_scope(case_id, [r.identity_key], zone=zone)[1]})
    total = sum(p["total"] for p in phones)
    return dict(base, identities=identities, phones=phones, total=total, conversations_href=href(),
                expected_revision=identity_decisions.links_revision(conn, [r.identity_id for r in linked]))


def scope_presets(conn, case_id) -> dict:
    """The people a scope can start from (07 4.5): for each person with linked identities, the phones they own and
    the phones they appear on. The owner of a phone is that phone's owner identity, linked to this person."""
    from services.phone import labels as L
    linked = conn.execute(text(
        "SELECT i.identity_key, i.person_id::text AS d, p.display_name AS name FROM pv_identity i JOIN case_profiles p "
        "ON p.id = i.person_id WHERE i.case_id = :c AND p.archived_at IS NULL"), {"c": str(case_id)}).fetchall()
    if not linked:
        return {"case_id": str(case_id), "people": []}
    keys = {r.identity_key for r in linked}
    appears = event_counts(conn, case_id, keys)
    owners = L.LabelContext(conn, str(case_id), "phone").owners
    people: dict = {}
    for r in linked:
        p = people.setdefault(r.d, {"dossier_id": r.d, "name": r.name, "identity_keys": [], "owned_phones": set(),
                                    "appears_on": set()})
        p["identity_keys"].append(r.identity_key)
        p["appears_on"] |= set(appears.get(r.identity_key, {}))
        p["owned_phones"] |= {e for e, o in owners.items() if r.identity_key in (o.get("keys") or ())}
    out = [dict(p, owned_phones=sorted(p["owned_phones"]), appears_on=sorted(p["appears_on"]),
                identity_keys=sorted(p["identity_keys"])) for p in people.values()]
    out.sort(key=lambda p: (p["name"] or "").casefold())
    return {"case_id": str(case_id), "people": out}
