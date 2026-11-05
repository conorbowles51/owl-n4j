"""The case graph's phone layer: a projection of Postgres, never its record (02 section 9; plan decision 6).

``plan(conn, case_id)`` builds the desired graph from the current generation of the case's active phones;
``apply(graph_session, plan)`` writes it in one Neo4j transaction under a per-case marker and removes what the
plan no longer holds, so the graph can be dropped and rebuilt from Postgres at any time.

What is projected (9.3): one node per phone; the identities that took part in a communication on any phone, the
phones' owners, and identities linked to a person (address-book-only identities stay in Postgres); group chats.
Messages, calls, events, places and texts are never nodes, and no projected property carries a name the case
Timeline or Map would read as a date or a place (9.2, ``FORBIDDEN_PROPERTIES``).

Membership (9.4): an identity has ``APPEARS_ON`` for every phone it is seen on. When a phone leaves the case, the
plan loses that phone's node and edges, and an identity still seen on another phone keeps its node and that
phone's edges. Every node and relationship matched here is matched with its ``case_id``.

``COMMUNICATED`` holds what Conversations shows for Between A and B, direct, one copy of each message: the counts come
from ``link_edges.every_pair``, the bulk form of the one edge implementation (03 R-1, 02 C11), so a stored count
always equals the pair edge. An event with exactly two identities that Between does not show, because its direction is
not known, keeps its pair on the graph and counts in ``undirected``, never in a direction. Messages in a group
conversation count on ``POSTED_IN``. A node an investigator wrote notes on is kept, marked ``phone_projection_orphaned``, when the
plan no longer holds it, because notes are investigator content (9.5 step 5).
"""
from __future__ import annotations

import hashlib
import json
import logging
from collections import defaultdict

from sqlalchemy import text

log = logging.getLogger(__name__)

GRAPH_TRANSACTION_TIMEOUT = 120
BATCH = 500  # the engine's write convention (02 section 9.5)
FORBIDDEN_PROPERTIES = frozenset(("date", "time", "timestamp", "start_time", "capture_time", "creation_time",
                                  "date_time", "datetime", "latitude", "longitude"))
MANAGED = {"phone_projection_managed": True, "layer": "phone"}
FROM_ROLES = {"sender", "caller", "from"}
TO_ROLES = {"recipient", "callee", "to"}
KIND_PREFIX = {"message": "messages", "call": "calls", "email": "emails"}
NODE_LABELS = ("PhoneExtraction", "PhoneIdentity", "PhoneGroup")
# (from label, to label) of each relationship; every match names its labels so it uses the (case_id, key) index
REL_ENDS = {"APPEARS_ON": ("PhoneIdentity", "PhoneExtraction"), "OWNS_PHONE": ("PhoneIdentity", "PhoneExtraction"),
            "COMMUNICATED": ("PhoneIdentity", "PhoneIdentity"), "POSTED_IN": ("PhoneIdentity", "PhoneGroup"),
            "MEMBER_OF_GROUP": ("PhoneIdentity", "PhoneGroup"), "REVIEWED_SAME_IDENTITY": ("PhoneIdentity", None)}


def _iso(v):
    return v.isoformat() if v is not None and hasattr(v, "isoformat") else v


def _span(cur, instant):
    if instant is None:
        return cur
    a, b = cur
    return (instant if a is None or instant < a else a, instant if b is None or instant > b else b)


def _active(conn, case_id):
    return [r for r in conn.execute(text(
        "SELECT e.id, e.report_version, e.producer_version, e.record_count FROM phone_extractions e JOIN "
        "phone_interpretation_state s ON s.extraction_id = e.id WHERE e.case_id = :c AND e.standing = 'active' AND "
        "s.generation > 0 ORDER BY e.created_at, e.id"), {"c": case_id})]


def _identity_labels(conn, case_id):
    """{identity_key: label} from the latest ``set_phone_identity_label`` decision on each identity."""
    out = {}
    for key, after in conn.execute(text(
            "SELECT i.identity_key, a.after FROM adjudications a JOIN phone_identities i ON i.id = a.subject_id WHERE "
            "a.case_id = :c AND a.subject_type = 'phone_identity' AND a.decision = 'set_phone_identity_label' "
            "ORDER BY a.subject_sequence"), {"c": case_id}):
        label = (after or {}).get("label")
        if label:
            out[key] = label
        else:
            out.pop(key, None)
    return out


def plan(conn, case_id) -> dict:
    """The desired phone layer of one case, as rows, with a revision over all of it."""
    from services.phone import identities as I
    from services.phone import link_edges
    from services.phone.readings import phone_labels
    case = str(case_id)
    labels = phone_labels(conn, case_id)
    exts = _active(conn, case_id)
    ext_ids = [str(e.id) for e in exts]
    owners = {}
    ext_nodes = []
    for e in exts:
        o = I.owner(conn, e.id)
        owner_key = (o.get("owner_identity_keys") or [None])[0]
        decided = o.get("decided") or {}
        basis = "manual" if decided else {1: "extracted", 2: "inferred"}.get(o["computed"].get("tier"))
        owners[str(e.id)] = (owner_key, basis, decided.get("decision_id"))
        head = I.header_items(conn, e.id)
        device = " ".join(x for x in ((head.get("DeviceInfoSelectedManufacturer") or [None])[0],
                                      (head.get("DeviceInfoSelectedDeviceName") or [None])[0]) if x)
        label = labels.get(str(e.id))
        ext_nodes.append({"key": "phone-extraction:%s" % e.id, "name": " · ".join(x for x in (label, device) if x),
                          "extraction_id": str(e.id), "phone_label": label, "report_version": e.report_version,
                          "producer_version": e.producer_version, "owner_identity_key": owner_key,
                          "owner_basis": basis,
                          "summary": "%s records" % format(e.record_count or 0, ",")})

    # communications, with the owner side mapped to the phone's owner identity
    groups_threads = {r[0]: r for r in conn.execute(text(
        "SELECT thread_key, extraction_id, record_uid, title_in_record, chat_type, party_identity_keys FROM pv_thread "
        "WHERE case_id = :c AND (chat_type ILIKE '%group%' OR thread_kind = 'sms_group' OR (thread_kind = 'chat' AND "
        "coalesce(cardinality(party_identity_keys), 0) > 2))"), {"c": case_id})}  # chat_type is often absent
    events = defaultdict(lambda: {"kind": None, "ext": None, "thread": None, "at": None, "parties": [], "group": None})
    communicating = set()
    for ev, ext, kind, thread, at, dup, key, role, implied, is_owner in conn.execute(text(
            "SELECT e.event_uid, e.extraction_id, e.kind, e.thread_key, e.sort_instant, e.dup_group_uid, p.identity_key, "
            "p.role, p.implied_role, p.is_phone_owner FROM pv_comm_event e JOIN pv_comm_party p ON p.event_uid = e.event_uid "
            "AND p.extraction_id = e.extraction_id WHERE e.case_id = :c"), {"c": case_id}):
        if role == "owner_implicit":
            key, role = owners.get(str(ext), (None,))[0], implied
        elif not key and is_owner:
            # the phone's own side written with the owner flag and no identifier (C6: 74,147 of 341,053 parties)
            key = owners.get(str(ext), (None,))[0]
        if not key:
            continue
        d = events[ev]
        d["kind"], d["ext"], d["thread"], d["at"] = kind, str(ext), thread, at
        d["group"] = link_edges.copy_group(ext, dup, ev)
        d["parties"].append((key, role))
        communicating.add(key)

    owner_keys = {v[0] for v in owners.values() if v[0]}
    linked = {r[0]: (str(r[1]), r[2], r[3]) for r in conn.execute(text(
        "SELECT i.identity_key, l.dossier_id, p.display_name, p.canonical_entity_key FROM phone_identity_links l JOIN "
        "phone_identities i ON i.id = l.identity_id LEFT JOIN case_profiles p ON p.id = l.dossier_id WHERE "
        "l.case_id = :c"), {"c": case_id})}
    idents = {r.identity_key: r for r in conn.execute(text(
        "SELECT id, identity_key, kind, subkind, value_display FROM phone_identities WHERE case_id = :c AND "
        "sighting_count > 0"), {"c": case_id})}
    group_keys = {k for k, r in idents.items() if r.kind == "other" and r.subkind == "group"}
    wanted = {k for k in (communicating | owner_keys | set(linked)) if k in idents and k not in group_keys}

    names = defaultdict(list)
    for key, ext, name, basis, occ, is_phone in conn.execute(text(
            "SELECT identity_key, extraction_id, name, basis, occurrences, is_phone_name FROM pv_identity_name WHERE "
            "case_id = :c ORDER BY occurrences DESC, name"), {"c": case_id}):
        if key in wanted:
            names[key].append((str(ext), name, basis, occ, is_phone))
    decided = _identity_labels(conn, case_id)
    seen = {}
    for key, ext, n, roles, a, b in conn.execute(text(
            "SELECT identity_key, extraction_id, count(*), array_agg(DISTINCT context), min(instant), max(instant) "
            "FROM pv_identity_sighting WHERE case_id = :c GROUP BY identity_key, extraction_id"), {"c": case_id}):
        if key in wanted:
            seen[(key, str(ext))] = (n, sorted(x for x in roles if x), a, b)

    id_nodes, appears, owns, reviewed = [], [], [], []
    for key in sorted(wanted):
        r = idents[key]
        ns = names.get(key, [])
        top = max(ns, key=lambda x: (x[3], x[1]))[1] if ns else None
        person = linked.get(key)
        shown = decided.get(key) or (person[1] if person else None) or top
        id_nodes.append({"key": "phone-identity:%s" % key, "identity_key": key, "kind": r.kind,
                         "value_display": r.value_display,
                         "name": "%s (%s)" % (shown, r.value_display) if shown else r.value_display,
                         "phone_names_json": json.dumps([{"phone": labels.get(e), "name": n, "basis": b}
                                                         for e, n, b, _, _ in ns], sort_keys=True),
                         "person_id": person[0] if person else None,
                         "owner_of": sorted(labels.get(e, e) for e, v in owners.items() if v[0] == key)})
        for ext in ext_ids:
            s = seen.get((key, ext))
            if s is None:
                continue
            phone_name = next((n for e, n, _, _, isp in ns if e == ext and isp), None)
            basis = next((b for e, n, b, _, isp in ns if e == ext and isp), None)
            appears.append({"key": "appears:%s:%s" % (key, ext), "source": "phone-identity:%s" % key,
                            "target": "phone-extraction:%s" % ext, "phone_name": phone_name, "name_basis": basis,
                            "records": s[0], "roles": s[1], "first_instant": _iso(s[2]), "last_instant": _iso(s[3])})
        if person and person[2]:
            reviewed.append({"key": "reviewed-same:%s" % key, "source": "phone-identity:%s" % key,
                             "target": person[2], "decision_id": None})
    for ext, (key, basis, decision_id) in owners.items():
        if key and key in wanted:
            owns.append({"key": "owns:%s:%s" % (key, ext), "source": "phone-identity:%s" % key,
                         "target": "phone-extraction:%s" % ext,
                         "basis": basis,
                         "decision_id": str(decision_id) if decision_id else None})

    # COMMUNICATED and POSTED_IN
    both = link_edges.every_pair(conn, case_id, {e: [v[0]] for e, v in owners.items() if v[0]})
    pairs = {}
    for (a, b), v in both.items():
        if a in wanted and b in wanted:
            pairs[(a, b)] = {"counts": v["counts"], "span": (v["first"], v["last"]),
                             "phones": {labels.get(p, p) for p in v["phones"]}, "groups": v["groups"]}
    posted = {}
    undirected_events = 0
    unshown = set()  # one copy of an event Between does not show counts once
    for d in events.values():
        keys = sorted({k for k, _ in d["parties"] if k in wanted})
        thread = groups_threads.get(d["thread"])
        if thread is not None:
            gkey = _group_key(thread, group_keys)
            for k, role in d["parties"]:
                if role in FROM_ROLES and k in wanted:
                    p = posted.setdefault((k, gkey), {"messages": 0, "span": (None, None)})
                    p["messages"] += 1
                    p["span"] = _span(p["span"], d["at"])
            continue
        if len(keys) != 2 or d["kind"] not in KIND_PREFIX:
            continue
        a, b = keys
        if d["group"] in both.get((a, b), {}).get("groups", ()) or ((a, b), d["group"]) in unshown:
            continue
        unshown.add(((a, b), d["group"]))
        pr = pairs.setdefault((a, b), {"counts": defaultdict(int), "span": (None, None), "phones": set(), "groups": set()})
        pr["counts"]["undirected"] += 1
        undirected_events += 1
        pr["span"] = _span(pr["span"], d["at"])
        pr["phones"].add(labels.get(d["ext"], d["ext"]))
    communicated = []
    for (a, b), v in sorted(pairs.items()):
        row = {"key": "communicated:%s|%s" % (a, b), "source": "phone-identity:%s" % a,
               "target": "phone-identity:%s" % b, "first_instant": _iso(v["span"][0]),
               "last_instant": _iso(v["span"][1]), "phones": sorted(v["phones"]), "undirected": v["counts"]["undirected"]}
        for p in KIND_PREFIX.values():
            row[p + "_ab"], row[p + "_ba"] = v["counts"][p + "_ab"], v["counts"][p + "_ba"]
        communicated.append(row)

    group_nodes, members, posted_in = {}, [], []
    for tk, t in sorted(groups_threads.items()):
        gkey = _group_key(t, group_keys)
        g = group_nodes.setdefault(gkey, {"key": gkey, "name": t.title_in_record, "chat_type": t.chat_type,
                                          "phones": set()})
        g["name"] = g["name"] or t.title_in_record
        g["phones"].add(labels.get(str(t.extraction_id), str(t.extraction_id)))
        for k in t.party_identity_keys or ():
            if k in wanted:
                members.append((k, gkey, labels.get(str(t.extraction_id), str(t.extraction_id))))
    member_rows = defaultdict(set)
    for k, gkey, phone in members:
        member_rows[(k, gkey)].add(phone)
    member_of = [{"key": "member:%s:%s" % (k, g), "source": "phone-identity:%s" % k, "target": g,
                  "phones": sorted(p)} for (k, g), p in sorted(member_rows.items())]
    for (k, g), v in sorted(posted.items()):
        posted_in.append({"key": "posted:%s:%s" % (k, g), "source": "phone-identity:%s" % k, "target": g,
                          "messages": v["messages"], "first_instant": _iso(v["span"][0]),
                          "last_instant": _iso(v["span"][1])})
    groups = [dict(g, phones=sorted(g["phones"])) for _, g in sorted(group_nodes.items())]

    out = {"case_id": case, "nodes": {"PhoneExtraction": ext_nodes, "PhoneIdentity": id_nodes, "PhoneGroup": groups},
           "rels": {"APPEARS_ON": appears, "OWNS_PHONE": owns, "COMMUNICATED": communicated,
                    "POSTED_IN": posted_in, "MEMBER_OF_GROUP": member_of, "REVIEWED_SAME_IDENTITY": reviewed},
           "counts": {"phones": len(ext_nodes), "identities": len(id_nodes), "groups": len(groups),
                      "pair_edges": len(communicated), "undirected_events": undirected_events}}
    check_properties(out)
    out["revision"] = hashlib.sha256(json.dumps({"n": out["nodes"], "r": out["rels"]}, sort_keys=True,
                                                default=str).encode()).hexdigest()
    return out


def _group_key(thread, group_keys):
    jid = next((k for k in (thread.party_identity_keys or ()) if k in group_keys), None)
    if jid:
        return "phone-group:%s" % jid
    return "phone-group:%s:%s" % (thread.extraction_id, thread.record_uid)


def check_properties(p):
    """9.2: no projected property may carry a name the Timeline or Map reads as a date or a place."""
    for rows in list(p["nodes"].values()) + list(p["rels"].values()):
        for row in rows:
            bad = FORBIDDEN_PROPERTIES & set(row)
            if bad:
                raise ValueError("A phone projection property would be read as a date or a place: %s" % sorted(bad))


def _props(row, drop=("source", "target")):
    return {k: v for k, v in row.items() if k not in drop}


def apply(graph_session, p) -> dict:
    """Write the plan for one case. Returns what was written, or ``{"unchanged": True}``."""
    from neo4j import Query
    case = p["case_id"]
    graph_session.run(Query("CREATE CONSTRAINT phone_projection_sync_case IF NOT EXISTS FOR (m:PhoneProjectionSync) "
                            "REQUIRE m.case_id IS UNIQUE", timeout=GRAPH_TRANSACTION_TIMEOUT)).consume()
    for label in NODE_LABELS:
        graph_session.run(Query("CREATE INDEX phone_%s_case_key IF NOT EXISTS FOR (n:%s) ON (n.case_id, n.key)"
                                % (label.lower(), label), timeout=GRAPH_TRANSACTION_TIMEOUT)).consume()
    with graph_session.begin_transaction(timeout=GRAPH_TRANSACTION_TIMEOUT) as tx:
        marker = tx.run("MERGE (m:PhoneProjectionSync {case_id:$case}) SET m.system_node = true, "
                        "m.projection_lock = coalesce(m.projection_lock, 0) + 1 RETURN m.revision AS revision",
                        case=case).single()
        if marker and marker["revision"] == p["revision"]:
            tx.run("MATCH (m:PhoneProjectionSync {case_id:$case}) SET m.input_signature = $sig", case=case,
                   sig=p.get("input_signature")).consume()
            tx.commit()
            return {"unchanged": True}
        written = defaultdict(int)
        for label, rows in p["nodes"].items():  # labels and types come from this module, never user text
            for i in range(0, len(rows), BATCH):
                batch = [_props(r) for r in rows[i:i + BATCH]]
                tx.run("UNWIND $rows AS row MERGE (n:%s {case_id:$case, key:row.key}) SET n += row, "
                       "n.phone_projection_managed = true, n.layer = 'phone', n.case_id = $case "
                       "REMOVE n.phone_projection_orphaned" % label, rows=batch, case=case).consume()
                written[label] += len(batch)
        for kind, rows in p["rels"].items():
            for i in range(0, len(rows), BATCH):
                batch = [{"source": r["source"], "target": r["target"], "props": _props(r)} for r in rows[i:i + BATCH]]
                src, dst = REL_ENDS[kind]
                if dst is None:  # a dossier's case entity: any label, still matched within the case
                    match = "MATCH (a:%s {case_id:$case, key:row.source}), (b {case_id:$case, key:row.target})" % src
                else:
                    match = "MATCH (a:%s {case_id:$case, key:row.source}), (b:%s {case_id:$case, key:row.target})" % (
                        src, dst)
                res = tx.run("UNWIND $rows AS row %s MERGE (a)-[r:%s {phone_projection_key:row.props.key}]->(b) "
                             "SET r += row.props, r.phone_projection_managed = true, r.layer = 'phone', "
                             "r.case_id = $case RETURN count(r) AS n" % (match, kind), rows=batch, case=case).single()
                written[kind] += res["n"] if res else 0
        rel_keys = sorted(r["key"] for rows in p["rels"].values() for r in rows)
        dropped_rels = tx.run(  # every phone relationship starts at a PhoneIdentity
            "MATCH (a:PhoneIdentity {case_id:$case})-[r]->() WHERE r.phone_projection_managed = true AND "
            "NOT r.phone_projection_key IN $keys DELETE r RETURN count(r) AS n", case=case, keys=rel_keys).single()["n"]
        node_keys = sorted(r["key"] for rows in p["nodes"].values() for r in rows)
        kept = dropped = 0
        for label in NODE_LABELS:
            # an investigator's notes (and, off the phone node, a summary) are kept on a node the plan dropped
            own = "n.notes IS NOT NULL" + ("" if label == "PhoneExtraction" else " OR n.summary IS NOT NULL")
            kept += tx.run(
                "MATCH (n:%s {case_id:$case}) WHERE n.phone_projection_managed = true AND NOT n.key IN $keys AND "
                "(%s) SET n.phone_projection_orphaned = true RETURN count(n) AS n" % (label, own),
                case=case, keys=node_keys).single()["n"]
            dropped += tx.run(
                "MATCH (n:%s {case_id:$case}) WHERE n.phone_projection_managed = true AND NOT n.key IN $keys AND "
                "n.phone_projection_orphaned IS NULL DETACH DELETE n RETURN count(n) AS n" % label,
                case=case, keys=node_keys).single()["n"]
        tx.run("MATCH (m:PhoneProjectionSync {case_id:$case}) SET m.revision = $rev, m.completed_at = datetime(), "
               "m.status = 'current', m.counts_json = $counts, m.input_signature = $sig", case=case, rev=p["revision"],
               counts=json.dumps(p["counts"], sort_keys=True), sig=p.get("input_signature")).consume()
        tx.commit()
    return dict(written, nodes_removed=dropped, relationships_removed=dropped_rels, nodes_kept_for_notes=kept)


def drop(graph_session, case_id) -> int:
    """Delete every managed phone node of a case (``--drop-first``), to show a rebuild needs nothing from the graph."""
    n = 0
    for label in NODE_LABELS:
        rec = graph_session.run("MATCH (n:%s {case_id:$case}) WHERE n.phone_projection_managed = true DETACH DELETE n "
                                "RETURN count(n) AS n" % label, case=str(case_id)).single()
        n += rec["n"] if rec else 0
    graph_session.run("MATCH (m:PhoneProjectionSync {case_id:$case}) DETACH DELETE m", case=str(case_id)).consume()
    return n


def project_case(engine, case_id, graph_session=None, signature=None) -> dict:
    """Build the plan in one short read transaction, then write it."""
    with engine.connect() as conn:
        with conn.begin():
            conn.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
            p = plan(conn, case_id)
            if signature is None:
                signature = signatures(conn).get(str(case_id)) or "no phones"
    p["input_signature"] = signature
    if graph_session is not None:
        out = apply(graph_session, p)
    else:
        from services.neo4j_service import neo4j_service
        with neo4j_service.session() as s:
            out = apply(s, p)
    with engine.begin() as conn:
        conn.execute(text("UPDATE phone_interpretation_state SET projected_at = now() WHERE extraction_id IN "
                          "(SELECT id FROM phone_extractions WHERE case_id = :c)"), {"c": case_id})
    return dict(out, counts=p["counts"])


def signatures(conn) -> dict:
    """``{case_id: signature}`` of every case with phones: what the plan reads, cheaply (the phones with their
    generation and standing, the latest phone decision, the latest Dossier change)."""
    return {str(r[0]): r[1] for r in conn.execute(text(
        "SELECT e.case_id, md5(string_agg(e.id::text || ':' || coalesce(s.generation, 0) || ':' || e.standing, ',' "
        "ORDER BY e.id) || '|' || coalesce((SELECT max(a.created_at)::text FROM adjudications a WHERE a.case_id = "
        "e.case_id AND a.subject_type IN ('phone_identity', 'phone_extraction')), '') || '|' || coalesce((SELECT "
        "max(p.updated_at)::text FROM case_profiles p WHERE p.case_id = e.case_id), '')) FROM phone_extractions e "
        "LEFT JOIN phone_interpretation_state s ON s.extraction_id = e.id GROUP BY e.case_id"))}


def _markers(graph_session) -> dict:
    return {r["case"]: r["input"] for r in graph_session.run(
        "MATCH (m:PhoneProjectionSync) RETURN m.case_id AS case, m.input_signature AS input").data()}


def project_stale(engine, graph_session=None) -> dict:
    """The worker's after-pass step: project every case whose inputs changed since its last projection, including
    a case whose phones were all deleted (its marker is still in the graph), one case at a time."""
    from contextlib import nullcontext
    with engine.connect() as conn:
        sigs = signatures(conn)
        # A case in Deleted items is skipped: its projection is neither rebuilt nor removed until it is restored or
        # purged (left out of the signatures alone it would read as "no phones" and lose its projection).
        deleted = {str(r[0]) for r in conn.execute(text("SELECT id FROM cases WHERE deleted_at IS NOT NULL"))}
    if graph_session is None:
        from services.neo4j_service import neo4j_service
        ctx = neo4j_service.session()
    else:
        ctx = nullcontext(graph_session)
    done = {}
    with ctx as gs:
        marks = _markers(gs)
        for case in sorted((set(sigs) | set(marks)) - deleted):
            if sigs.get(case) is not None and marks.get(case) == sigs.get(case):
                continue
            if sigs.get(case) is not None:
                from services.phone import identities
                with engine.begin() as conn:  # a phone deleted or superseded changes its identities' counts first
                    identities.recount_case(conn, case)
            done[case] = project_case(engine, case, gs, signature=sigs.get(case) or "no phones")
    return done


def install():
    """Called by the sweep worker (the graph is written from one process)."""
    from services.phone import sweep
    sweep.register_after_pass(project_stale)


def flow_partners(case_id, anchor: str, graph_session=None) -> dict:
    """Every identity with a stored COMMUNICATED edge to ``anchor``, busiest first, for the Graph flow view. Volume
    orders the list only: the counts a person reads come from ``pair_counts``' one implementation."""
    from contextlib import nullcontext

    from services.neo4j.driver import driver
    key = "phone-identity:%s" % anchor
    with (nullcontext(graph_session) if graph_session is not None else driver.session()) as session:
        rows = session.run(
            "MATCH (a:PhoneIdentity {case_id: $case, key: $key})-[r:COMMUNICATED]-(b:PhoneIdentity {case_id: $case}) "
            "RETURN b.key AS key, b.name AS name, coalesce(r.messages_ab, 0) + coalesce(r.messages_ba, 0) + "
            "coalesce(r.calls_ab, 0) + coalesce(r.calls_ba, 0) + coalesce(r.emails_ab, 0) + coalesce(r.emails_ba, 0) + "
            "coalesce(r.undirected, 0) AS volume ORDER BY volume DESC, key", case=str(case_id), key=key)
        partners = [{"key": r["key"].removeprefix("phone-identity:"), "name": r["name"], "volume": r["volume"]}
                    for r in rows]
    return {"case_id": str(case_id), "anchor": anchor, "partners": partners, "total": len(partners)}


def pair_counts(conn, case_id, a: str, b: str, from_instant=None, to_instant=None) -> dict:
    """03 R-3: a pair edge's counts for a time slice, read as Conversations reads Between A and B in that window
    (every copy, direct and group-free as the edge counts them), so the sliced edge equals the list it opens. Counted
    by the one edge implementation, ``link_edges.communication`` (02 section 11.1, C11)."""
    from services.phone import link_edges
    c = link_edges.communication(conn, case_id, [a], [b], from_instant=from_instant, to_instant=to_instant,
                                 group_scope="direct", collapse_copies=False)
    out = {prefix: link_edges.comm_total(c, prefix) for prefix in KIND_PREFIX.values()}
    out["total"] = sum(out.values())
    return out
