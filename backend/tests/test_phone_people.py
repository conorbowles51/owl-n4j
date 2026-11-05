"""People across phones (03 section 10, 07 J-3, XF-5, 4.5): the Phone identities list, a dossier's panel and scope
presets. Every count equals the Conversations count for the link it opens. Invented data only."""
from __future__ import annotations

import uuid
from urllib.parse import parse_qs, urlparse

import pytest
from sqlalchemy import text

from services.phone import crossings as X
from services.phone import people as P
from tests.phone_pg import fresh_engine, make_case, needs_template
from tests.phone_streams_fixture import at, ensure_identity, phone

pytestmark = needs_template
OWNER, OWNER2 = "phone:+12025550100", "phone:+12025550101"
ANA, ANA2, BEN = "phone:+12025550143", "email:ana@synthetic.test", "phone:+12025550188"


def msg(instant, sender, recips, me, kind="message", body="hello", **kw):
    parties = [(sender, "sender", sender == me, None, None)] + [(r, "recipient", r == me, None, None) for r in recips]
    return dict(kind=kind, instant=instant, body=body, parties=parties,
                direction="outgoing" if sender == me else "incoming", thread="t", **kw)


def dossier(c, case, name, kind="person"):
    d = uuid.uuid4()
    c.execute(text("INSERT INTO case_profiles (id, case_id, profile_type, display_name, contacts, linkage_state, status, "
                   "needs_link_review, graph_entity_deleted, created_at, updated_at) VALUES (:d, :c, :t, :n, '[]', "
                   "'unlinked', 'active', false, false, now(), now())"), {"d": d, "c": case, "n": name, "t": kind})
    return d


def link(c, case, d, key):
    c.execute(text("INSERT INTO phone_identity_links (case_id, identity_id, dossier_id, decision_id) VALUES (:c, :i, :d, "
                   ":x)"), {"c": case, "i": ensure_identity(c, case, key), "d": d, "x": uuid.uuid4()})


def sighting(c, case, ext, key):
    c.execute(text("INSERT INTO phone_identity_sightings (sighting_uid, case_id, extraction_id, identity_id, identity_key, "
                   "field_path, identifier_raw, context, generation) VALUES (:u, :c, :e, :i, :k, 'x', 'x', 'party', 1)"),
              {"u": uuid.uuid4(), "c": case, "e": ext, "i": ensure_identity(c, case, key), "k": key})


@pytest.fixture
def world():
    with fresh_engine() as engine:
        with engine.begin() as c:
            case = make_case(c)
            c1, _ = phone(c, case, label="C1", contacts={ANA: "Maria L"}, events=[
                msg(at(2023, 3, 13, 9), ANA, [OWNER], OWNER),
                msg(at(2023, 3, 14, 9), OWNER, [ANA], OWNER),
                msg(at(2023, 3, 14, 10), ANA2, [OWNER], OWNER),
                msg(at(2023, 3, 14, 11), BEN, [OWNER], OWNER),
                msg(None, ANA, [OWNER], OWNER, body="undated")])
            c2, _ = phone(c, case, label="C2", contacts={ANA: "Mom"}, events=[
                msg(at(2023, 3, 20, 9), ANA, [OWNER2], OWNER2),
                msg(at(2023, 3, 21, 9), OWNER2, [BEN], OWNER2)])
            for ext, keys in ((c1, (ANA, ANA2, BEN)), (c2, (ANA,))):
                for key in keys:
                    sighting(c, case, ext, key)
            ana = dossier(c, case, "Ana Synthetic")
            link(c, case, ana, ANA)
            link(c, case, ana, ANA2)
            unlinked = dossier(c, case, "Nobody Yet")
        with engine.connect() as conn:
            yield {"conn": conn, "case": case, "c1": str(c1), "c2": str(c2), "ana": ana, "unlinked": unlinked}


def conv_total(w, href):
    """What Conversations counts for a link: the filter the page builds from that URL."""
    q = parse_qs(urlparse(href).query)
    keys = q["people"][0].split(",")
    f = X.conversations_scope(w["case"], keys, phones=q["phones"][0].split(",") if "phones" in q else None)[0]
    return X.count(w["conn"], f)


def test_u1_each_phone_keeps_its_own_name_and_counts_add_up(world):
    out = P.registry(world["conn"], world["case"])
    assert out["total"] == out["in_case"]
    ana = next(i for i in out["items"] if i["identity_key"] == ANA)
    assert sorted((n["phone_label"], n["name"]) for n in ana["names"]) == [("C1", "Maria L"), ("C2", "Mom")]
    assert {p["phone_label"]: p["events"] for p in ana["phones"]} == {"C1": 3, "C2": 1}
    assert ana["event_count"] == 4 and ana["person"]["display_name"] == "Ana Synthetic"
    # undated events are counted and do not stand in as a first or last contact
    assert ana["first_contact"].startswith("2023-03-13") and ana["last_contact"].startswith("2023-03-20")
    for p in ana["phones"]:
        assert p["events"] == X.count(world["conn"], X.conversations_scope(world["case"], [ANA], phones=[p["extraction_id"]])[0])


def test_filters_by_phone_link_and_text_keep_an_exact_total(world):
    w = world
    assert {i["identity_key"] for i in P.registry(w["conn"], w["case"], linked=True)["items"]} == {ANA, ANA2}
    unlinked = P.registry(w["conn"], w["case"], linked=False)
    assert ANA not in {i["identity_key"] for i in unlinked["items"]} and unlinked["linked_in_case"] == 2
    assert [i["identity_key"] for i in P.registry(w["conn"], w["case"], phone=w["c2"])["items"]] == [ANA]
    assert [i["identity_key"] for i in P.registry(w["conn"], w["case"], q="mom")["items"]] == [ANA]
    first = P.registry(w["conn"], w["case"], limit=2)
    second = P.registry(w["conn"], w["case"], limit=2, cursor=first["next_cursor"])
    assert not {i["identity_key"] for i in first["items"]} & {i["identity_key"] for i in second["items"]}
    assert first["total"] == second["total"]


def test_u4_panel_counts_equal_conversations_for_every_link(world):
    out = P.dossier_phones(world["conn"], world["case"], world["ana"])
    assert out["dossier"]["name"] == "Ana Synthetic"
    assert out["total"] == conv_total(world, out["conversations_href"]) == 5
    assert out["total"] == X.person_activity(world["conn"], world["case"], dossier_id=world["ana"])["total"]
    assert sum(p["total"] for p in out["phones"]) == out["total"]
    for p in out["phones"]:
        assert p["total"] == conv_total(world, p["conversations_href"])
        assert sum(d["events"] for k in p["kinds"] for d in k["directions"]) == p["total"]
    for i in out["identities"]:
        assert i["events"] == conv_total(world, i["conversations_href"])
    c1 = next(p for p in out["phones"] if p["label"] == "C1")
    assert {n["name"] for n in c1["names"]} == {"Maria L"}
    assert c1["kinds"] == [{"kind": "message", "directions": [{"direction": "incoming", "events": 3},
                                                              {"direction": "outgoing", "events": 1}]}]


def test_a_dossier_with_no_link_says_so_and_another_case_is_refused(world):
    out = P.dossier_phones(world["conn"], world["case"], world["unlinked"])
    assert out["identities"] == [] and out["total"] == 0 and out["conversations_href"] is None
    with pytest.raises(P.NotInCase):
        P.dossier_phones(world["conn"], world["case"], uuid.uuid4())


def test_a_suggestion_is_stated_apart_and_never_counted(world):
    w = world
    w["conn"].execute(text("INSERT INTO phone_identity_suggestions (id, case_id, identity_ids, dossier_id, reasons, "
                           "score, state) VALUES (:i, :c, CAST(:k AS uuid[]), :d, '[]', 0.5, 'open')"),
                      {"i": uuid.uuid4(), "c": w["case"], "k": [ensure_identity(w["conn"], w["case"], BEN)], "d": w["ana"]})
    out = P.dossier_phones(w["conn"], w["case"], w["ana"])
    assert out["suggested_identities"] == 1 and BEN not in {i["identity_key"] for i in out["identities"]}
    assert out["total"] == 5


def test_presets_name_owned_phones_and_phones_they_appear_on(world):
    w = world
    link(w["conn"], w["case"], w["unlinked"], OWNER)
    out = {p["name"]: p for p in P.scope_presets(w["conn"], w["case"])["people"]}
    assert out["Ana Synthetic"]["appears_on"] == sorted([w["c1"], w["c2"]])
    assert out["Ana Synthetic"]["owned_phones"] == []
    assert w["c1"] in out["Nobody Yet"]["owned_phones"] and w["c1"] in out["Nobody Yet"]["appears_on"]


def test_a_scope_counts_the_identities_its_phones_hold(world):
    w = world
    assert P.scope_identities(w["conn"], w["case"], [w["c2"]]) == 1
    assert P.scope_identities(w["conn"], w["case"], [w["c1"], w["c2"]]) == P.scope_identities(w["conn"], w["case"]) == 3


def test_u2_linking_then_unlinking_keeps_counts_and_both_decisions_show_with_the_actor(world):
    from sqlalchemy.orm import Session

    from services.financial.decisions import Actor
    from services.phone import identity_decisions as D
    w = world
    with Session(bind=w["conn"]) as db:
        actor = Actor(name="Jane Reviewer", email="jane@synthetic.test")
        before = X.count(w["conn"], X.conversations_scope(w["case"], [BEN])[0])
        D.decide(db, case_id=w["case"], decision="link_phone_identity", identity_keys=[BEN], actor=actor, user=None,
                 dossier_id=w["unlinked"])
        linked = P.dossier_phones(w["conn"], w["case"], w["unlinked"])
        assert linked["total"] == before and [i["identity_key"] for i in linked["identities"]] == [BEN]
        D.decide(db, case_id=w["case"], decision="unlink_phone_identity", identity_keys=[BEN], actor=actor, user=None,
                 reason="Not the same person after all")
        out = P.dossier_phones(w["conn"], w["case"], w["unlinked"])
    assert out["identities"] == [] and X.count(w["conn"], X.conversations_scope(w["case"], [BEN])[0]) == before
    assert [h["decision"] for h in out["history"]] == ["unlink_phone_identity", "link_phone_identity"]
    assert {h["actor"] for h in out["history"]} == {"Jane Reviewer"} and out["history_total"] == 2


def test_a_count_with_its_channel_and_direction_equals_conversations(world):
    w = world
    out = P.dossier_phones(w["conn"], w["case"], w["ana"])
    c1 = next(p for p in out["phones"] if p["label"] == "C1")
    keys = [i["identity_key"] for i in out["identities"]]
    for kind in c1["kinds"]:
        for d in kind["directions"]:
            f = X.conversations_scope(w["case"], keys, phones=[w["c1"]])[0]
            f.update({"kinds": [kind["kind"]], "directions": [d["direction"]]})
            assert X.count(w["conn"], f) == d["events"]
