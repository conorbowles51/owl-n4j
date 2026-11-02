"""02-U14: the case graph's phone layer (02 section 9). Synthetic phones; a scratch Neo4j for the write tests
(``LOUPE_TEST_NEO4J_URI`` with ``_USER``/``_PASSWORD``); never the live graph."""
from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import text

from services.phone import graph_projection as G
from services.phone import identities, readings, registry, sweep
from tests.phone_pg import fresh_engine, make_case, needs_template
from tests.test_phone_identities import _call, _contact, _phone
from tests.test_phone_mappings import CALL, hooks, write  # noqa: F401 (fixture)

OWNER_1, OWNER_2 = "+12025550100", "+12025550101"
SHARED, ONLY_2, ONLY_1 = "+12025550143", "+12025550144", "+12025550145"
needs_neo4j = pytest.mark.skipif(not os.environ.get("LOUPE_TEST_NEO4J_URI"),
                                 reason="needs a scratch Neo4j (LOUPE_TEST_NEO4J_URI)")


@pytest.fixture
def two_phones(hooks):
    """One case, two phones: the shared number calls both owners, each phone has a number of its own; and a second
    case holding the same shared number, so case scoping is visible."""
    write(str(hooks), CALL)
    identities.install()
    readings.install()
    with fresh_engine() as engine:
        with engine.begin() as c:
            registry.apply_seed(c)
            case, other = make_case(c), make_case(c)
            p1 = _phone(c, case, [_call(0, [(OWNER_1, None, True), (SHARED, None, False)]),
                                  _call(3, [(OWNER_1, None, True), (ONLY_1, None, False)]),
                                  _contact(6, "Synthetic Shared", SHARED)], metadata={"MSISDN": OWNER_1})
            p2 = _phone(c, case, [_call(0, [(OWNER_2, None, True), (SHARED, None, False)], direction="Incoming"),
                                  _call(3, [(OWNER_2, None, True), (ONLY_2, None, False)])],
                        metadata={"MSISDN": OWNER_2})
            p3 = _phone(c, other, [_call(0, [(OWNER_1, None, True), (SHARED, None, False)])],
                        metadata={"MSISDN": OWNER_1})
        for e in (p1, p2, p3):
            assert sweep.interpret_one(engine, e)["status"] == "done"
        yield engine, case, other, p1, p2


def _keys(p, label):
    return sorted(n["key"] for n in p["nodes"][label])


def _rels(p, kind):
    return sorted((r["source"], r["target"]) for r in p["rels"][kind])


@needs_template
def test_the_plan_holds_phones_communicating_identities_and_their_membership(two_phones):
    engine, case, _, p1, p2 = two_phones
    with engine.connect() as c:
        p = G.plan(c, case)
    assert _keys(p, "PhoneExtraction") == sorted(["phone-extraction:%s" % p1, "phone-extraction:%s" % p2])
    ids = _keys(p, "PhoneIdentity")
    assert ids == sorted("phone-identity:phone:%s" % n for n in (OWNER_1, OWNER_2, SHARED, ONLY_1, ONLY_2))
    appears = _rels(p, "APPEARS_ON")
    assert ("phone-identity:phone:%s" % SHARED, "phone-extraction:%s" % p1) in appears
    assert ("phone-identity:phone:%s" % SHARED, "phone-extraction:%s" % p2) in appears
    owns = {(r["source"], r["target"]): r["basis"] for r in p["rels"]["OWNS_PHONE"]}
    assert owns[("phone-identity:phone:%s" % OWNER_1, "phone-extraction:%s" % p1)] == "extracted"
    pairs = {(r["source"], r["target"]): r for r in p["rels"]["COMMUNICATED"]}
    a, b = sorted(["phone-identity:phone:%s" % OWNER_1, "phone-identity:phone:%s" % SHARED])
    assert pairs[(a, b)]["calls_ab"] + pairs[(a, b)]["calls_ba"] + pairs[(a, b)]["undirected"] == 1
    shared = next(n for n in p["nodes"]["PhoneIdentity"] if n["identity_key"] == "phone:%s" % SHARED)
    assert shared["name"].startswith("Synthetic Shared (")


@needs_template
def test_the_owner_side_flagged_without_a_number_is_the_phone_owner_in_a_pair(hooks):
    """A party with the owner flag and no identifier is the phone's own side; the pair with the other party counts."""
    write(str(hooks), CALL)
    identities.install()
    readings.install()
    with fresh_engine() as engine:
        with engine.begin() as c:
            registry.apply_seed(c)
            case = make_case(c)
            p1 = _phone(c, case, [_call(0, [(OWNER_1, None, True), (ONLY_1, None, False)]),
                                  _call(3, [(None, None, True), (SHARED, None, False)])], metadata={"MSISDN": OWNER_1})
        assert sweep.interpret_one(engine, p1)["status"] == "done"
        with engine.connect() as c:
            p = G.plan(c, case)
    pairs = {(r["source"], r["target"]) for r in p["rels"]["COMMUNICATED"]}
    assert tuple(sorted(["phone-identity:phone:%s" % OWNER_1, "phone-identity:phone:%s" % SHARED])) in pairs
    assert p["counts"]["pair_edges"] == 2


@needs_template
def test_no_projected_property_is_read_as_a_date_or_a_place(two_phones):
    engine, case, _, _, _ = two_phones
    with engine.connect() as c:
        p = G.plan(c, case)
    names = {k for rows in list(p["nodes"].values()) + list(p["rels"].values()) for r in rows for k in r}
    assert not names & G.FORBIDDEN_PROPERTIES
    bad = dict(p, nodes=dict(p["nodes"], PhoneGroup=[{"key": "phone-group:x", "latitude": 1}]))
    with pytest.raises(ValueError, match="date or a place"):
        G.check_properties(bad)


@needs_template
def test_removing_a_phone_keeps_identities_seen_elsewhere_and_drops_only_its_own(two_phones):
    engine, case, _, p1, p2 = two_phones
    with engine.begin() as c:
        c.execute(text("UPDATE phone_extractions SET standing = 'superseded', superseded_at = now() WHERE id = :e"),
                  {"e": p2})
        identities.recount_case(c, case)
        p = G.plan(c, case)
        assert _keys(p, "PhoneExtraction") == ["phone-extraction:%s" % p1]
        ids = _keys(p, "PhoneIdentity")
        assert "phone-identity:phone:%s" % SHARED in ids and "phone-identity:phone:%s" % ONLY_1 in ids
        assert "phone-identity:phone:%s" % ONLY_2 not in ids and "phone-identity:phone:%s" % OWNER_2 not in ids
        assert all(t == "phone-extraction:%s" % p1 for _, t in _rels(p, "APPEARS_ON"))
        assert c.execute(text("SELECT sighting_count FROM phone_identities WHERE case_id = :c AND identity_key = :k"),
                         {"c": case, "k": "phone:%s" % ONLY_2}).scalar() == 0


def _graph():
    from neo4j import GraphDatabase
    return GraphDatabase.driver(os.environ["LOUPE_TEST_NEO4J_URI"], auth=(
        os.environ.get("LOUPE_TEST_NEO4J_USER", "neo4j"), os.environ["LOUPE_TEST_NEO4J_PASSWORD"]))


def _graph_keys(s, case, label):
    return sorted(r["k"] for r in s.run("MATCH (n:%s {case_id:$c}) RETURN n.key AS k" % label, c=str(case)).data())


@needs_template
@needs_neo4j
def test_apply_writes_the_plan_and_a_removed_phone_takes_only_its_own_nodes_and_edges(two_phones):
    engine, case, other, p1, p2 = two_phones
    driver = _graph()
    try:
        with driver.session() as s:
            for k in (case, other):
                G.drop(s, k)
            G.project_case(engine, other, s)
            first = G.project_case(engine, case, s)
            assert first["PhoneIdentity"] == 5 and first["nodes_removed"] == 0
            assert G.project_case(engine, case, s) == {"unchanged": True, "counts": first["counts"]}
            # an investigator's note on the identity seen only on phone 2
            s.run("MATCH (n:PhoneIdentity {case_id:$c, key:$k}) SET n.notes = 'synthetic note'", c=str(case),
                  k="phone-identity:phone:%s" % ONLY_2).consume()
            with engine.begin() as c:
                c.execute(text("UPDATE phone_extractions SET standing = 'superseded', superseded_at = now() WHERE "
                               "id = :e"), {"e": p2})
            done = G.project_stale(engine, s)
            assert str(case) in done and str(other) not in done  # the other case's inputs did not change
            keys = _graph_keys(s, case, "PhoneIdentity")
            assert "phone-identity:phone:%s" % SHARED in keys and "phone-identity:phone:%s" % OWNER_2 not in keys
            kept = s.run("MATCH (n:PhoneIdentity {case_id:$c, key:$k}) RETURN n.phone_projection_orphaned AS o",
                         c=str(case), k="phone-identity:phone:%s" % ONLY_2).single()
            assert kept and kept["o"] is True  # kept for its note, marked as no longer in the plan
            targets = {r["t"] for r in s.run(
                "MATCH (a:PhoneIdentity {case_id:$c})-[r:APPEARS_ON]->(b) RETURN b.key AS t", c=str(case)).data()}
            assert targets == {"phone-extraction:%s" % p1}
            # the other case's node with the same key is untouched
            assert "phone-identity:phone:%s" % SHARED in _graph_keys(s, other, "PhoneIdentity")
            # a rebuild after dropping everything gives the same graph
            before = _graph_keys(s, case, "PhoneIdentity")
            G.drop(s, case)
            G.project_case(engine, case, s)
            after = _graph_keys(s, case, "PhoneIdentity")
            assert set(after) == set(before) - {"phone-identity:phone:%s" % ONLY_2}  # the note node went with drop
            for k in (case, other):
                G.drop(s, k)
    finally:
        driver.close()


@needs_template
@needs_neo4j
def test_a_case_whose_phones_are_all_deleted_loses_its_phone_layer(two_phones):
    engine, case, other, p1, p2 = two_phones
    driver = _graph()
    try:
        with driver.session() as s:
            G.drop(s, other)
            G.project_case(engine, other, s)
            assert _graph_keys(s, other, "PhoneExtraction")
            with engine.begin() as c:
                c.execute(text("DELETE FROM phone_extractions WHERE case_id = :c"), {"c": other})
            G.project_stale(engine, s)
            assert _graph_keys(s, other, "PhoneExtraction") == [] and _graph_keys(s, other, "PhoneIdentity") == []
            G.drop(s, other)
            G.drop(s, case)
    finally:
        driver.close()


@needs_template
def test_r1_each_pair_edge_count_equals_the_conversations_total_between_the_pair(two_phones):
    """03 R-1 (A3): the graph's pair edge counts the same events Conversations shows for Between A and B."""
    from services.phone import streams
    from services.phone.filters import StreamFilter
    engine, case, _, p1, p2 = two_phones
    with engine.connect() as c:
        p = G.plan(c, case)
        assert p["rels"]["COMMUNICATED"]
        for r in p["rels"]["COMMUNICATED"]:
            a, b = r["source"].split(":", 1)[1], r["target"].split(":", 1)[1]
            edge = r["undirected"] + sum(r[k + "_ab"] + r[k + "_ba"] for k in G.KIND_PREFIX.values())
            f = StreamFilter.model_validate({"case_id": str(case), "participants": [a, b],
                                             "participant_mode": "between", "kinds": list(G.KIND_PREFIX),
                                             "collapse_copies": False})
            assert streams.shown_count(c, f) == edge, (a, b)


@needs_template
def test_r3_a_time_sliced_edge_count_equals_conversations_in_that_window(two_phones):
    from services.phone import streams
    from services.phone.filters import StreamFilter
    engine, case, _, p1, p2 = two_phones
    with engine.connect() as c:
        p = G.plan(c, case)
        r = p["rels"]["COMMUNICATED"][0]
        a, b = r["source"].split(":", 1)[1], r["target"].split(":", 1)[1]
        whole = G.pair_counts(c, case, a, b)
        assert whole["total"] == r["undirected"] + sum(r[k + "_ab"] + r[k + "_ba"] for k in G.KIND_PREFIX.values())
        first = r["first_instant"]
        sliced = G.pair_counts(c, case, a, b, from_instant=first, to_instant=first)
        f = StreamFilter.model_validate({"case_id": str(case), "participants": [a, b], "participant_mode": "between",
                                         "collapse_copies": False, "kinds": list(G.KIND_PREFIX),
                                         "from_instant": first, "to_instant": first, "include_no_time": False})
        assert sliced["total"] == streams.shown_count(c, f) >= 1


@needs_template
def test_d21_the_graph_page_caps_a_phone_case_at_2000_by_degree_and_a_case_without_phones_is_whole(two_phones):
    from sqlalchemy.orm import Session
    from routers.graph import phone_case_cap
    engine, case, _, p1, p2 = two_phones
    with Session(engine) as db:
        empty = make_case(db.connection())
        assert phone_case_cap(db, case, None, None) == (2000, "degree")
        assert phone_case_cap(db, empty, None, None) == (None, None)
        assert phone_case_cap(db, case, 50, "degree") == (50, "degree")
        assert phone_case_cap(db, "not-a-case", None, None) == (None, None)
