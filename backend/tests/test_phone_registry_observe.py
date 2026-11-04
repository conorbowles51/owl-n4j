"""02-U3: observation pass and review queue (02 sections 3.3 and 3.4)."""
from __future__ import annotations

import json
import threading

import pytest
from sqlalchemy import text

from services.phone import registry
from tests.phone_pg import (corpus_connection, fld, fresh_engine, make_case, make_extraction, model, needs_corpus,
                            needs_template, refs)


def _known_records(extra_call_fields=(), call_attrs=None, extra_children=(), extra_records=()):
    call = model("Call", [fld("Direction", ("ModelDirections", "Incoming")),
                          fld("TimeStamp", ("TimeStamp", "2023-03-14T15:07:12-04:00")),
                          fld("Duration", ("TimeSpan", "00:01:05")),
                          *extra_call_fields,
                          refs("Parties", 1, *[o for o, _ in extra_children])], **(call_attrs or {}))
    party = model("Party", [fld("Identifier", ("String", "synthetic-1"))])
    rows = [(0, None, 0, call), (1, 0, 0, party)]
    rows += [(o, 0, 0, b) for o, b in extra_children]
    rows += list(extra_records)
    return rows


def _flags(c, ids):
    return sorted(r[0] for r in c.execute(text("SELECT flag_kind FROM phone_schema_flags WHERE id = ANY(:i)"),
                                          {"i": ids}))


@needs_template
def test_known_structure_raises_nothing_and_six_novelties_raise_exactly_six():
    with fresh_engine() as engine, engine.begin() as c:
        registry.apply_seed(c)
        case = make_case(c)
        known = make_extraction(c, case, _known_records())
        assert registry.observe_extraction(c, known)["flags_raised"] == 0
        novel = make_extraction(c, case, _known_records(
            extra_call_fields=[fld("ZzzNewField", ("String", "x")), fld("Direction", ("ModelDirections", "Sideways")),
                               fld("Duration", ("Int32", "65"))],
            call_attrs={"zzz_attribute": "1"},
            extra_children=[(2, model("Coordinate", [fld("Latitude", ("Double", "1.5"))]))],
            extra_records=[(3, None, 3, model("ZzzNewType", []))]))
        out = registry.observe_extraction(c, novel)
        assert out["flags_raised"] == 6
        assert _flags(c, out["flag_ids"]) == sorted(["new_type", "new_field", "new_set_value", "new_nesting",
                                                     "new_attribute", "new_value_type"])
        drift = c.execute(text("SELECT detail FROM phone_schema_flags WHERE flag_kind = 'new_value_type' AND state = 'open'")).scalar()
        assert drift["previous"] == ["TimeSpan"] and drift["now"] == "Int32"
        # observing either again raises nothing and keeps the totals
        before = c.execute(text("SELECT id, observed_value_count FROM phone_schema_fields ORDER BY id")).fetchall()
        assert registry.observe_extraction(c, novel)["flags_raised"] == 0
        assert registry.observe_extraction(c, known)["flags_raised"] == 0
        after = c.execute(text("SELECT id, observed_value_count FROM phone_schema_fields ORDER BY id")).fetchall()
        assert before == after
        new_row = c.execute(text(
            "SELECT origin, first_seen_extraction_id, first_seen_report_version, observed_extraction_count FROM "
            "phone_schema_fields WHERE field_name = 'ZzzNewField'")).one()
        assert new_row[0] == "observed" and new_row[1] == novel and new_row[2] == "7.70" and new_row[3] == 1


@needs_template
def test_fields_of_a_new_type_are_recorded_under_the_type_flag():
    with fresh_engine() as engine, engine.begin() as c:
        registry.apply_seed(c)
        case = make_case(c)
        ext = make_extraction(c, case, [(0, None, 0, model("ZzzUnknown", [fld("When", ("TimeStamp", "x")),
                                                                         fld("Note", ("String", "y"))]))])
        out = registry.observe_extraction(c, ext)
        assert _flags(c, out["flag_ids"]) == ["new_type"]
        assert c.execute(text("SELECT count(*) FROM phone_schema_fields WHERE type_name = 'ZzzUnknown'")).scalar() == 2


@needs_template
def test_a_plain_field_with_two_values_records_the_maximum_and_flags_it():
    with fresh_engine() as engine, engine.begin() as c:
        registry.apply_seed(c)
        case = make_case(c)
        label = model("QuotedMessageData", [fld("Label", ("Label", "Reply"), ("Label", "Edited"))])
        ext = make_extraction(c, case, [(0, None, 0, label)])
        out = registry.observe_extraction(c, ext)
        assert _flags(c, out["flag_ids"]) == ["multi_value_field"]
        assert c.execute(text("SELECT max_values_in_one_field FROM phone_schema_fields WHERE type_name = "
                              "'QuotedMessageData' AND field_name = 'Label' AND value_type = 'Label'")).scalar() == 2


@needs_template
def test_an_extraction_that_is_not_captured_is_not_observed():
    with fresh_engine() as engine, engine.begin() as c:
        case = make_case(c)
        ext = make_extraction(c, case, _known_records(), capture_state="capturing")
        with pytest.raises(registry.NotCaptured):
            registry.observe_extraction(c, ext)


@needs_template
def test_two_concurrent_observations_of_one_new_field_raise_one_flag():
    with fresh_engine() as engine:
        with engine.begin() as c:
            registry.apply_seed(c)
            case = make_case(c)
            recs = lambda: _known_records(extra_call_fields=[fld("ZzzRace", ("String", "x"))])
            e1, e2 = make_extraction(c, case, recs()), make_extraction(c, case, recs())
        a, b = engine.connect(), engine.connect()
        ta, tb = a.begin(), b.begin()
        results = {}
        registry.observe_extraction(a, e1)  # holds the new row's unique key until it commits

        def second():
            results["b"] = registry.observe_extraction(b, e2)
            tb.commit()

        t = threading.Thread(target=second)
        t.start()
        t.join(1.0)
        assert t.is_alive()  # waiting on the first transaction's insert
        ta.commit()
        t.join(30)
        a.close()
        b.close()
        with engine.connect() as c:
            n = c.execute(text("SELECT count(*) FROM phone_schema_flags f JOIN phone_schema_fields s ON "
                               "s.id = f.registry_id WHERE f.registry_table = 'fields' AND s.field_name = 'ZzzRace'"))
            assert n.scalar() == 1
        assert results["b"]["flags_raised"] == 0


@needs_template
def test_transitions_write_the_event_first_and_follow_the_table():
    with fresh_engine() as engine, engine.begin() as c:
        registry.apply_seed(c)
        case = make_case(c)
        ext = make_extraction(c, case, [(0, None, 0, model("ZzzQueue", []))])
        fid = registry.observe_extraction(c, ext)["flag_ids"][0]
        with pytest.raises(registry.TransitionRefused):
            registry.transition_flag(c, fid, "acknowledged", "  ")
        with pytest.raises(registry.TransitionRefused):
            registry.transition_flag(c, fid, "mapped", "a person cannot", actor_name="A Person")
        registry.transition_flag(c, fid, "mapping_needed", "needs a mapping", actor_name="A Person",
                                 actor_email="a@x.test")
        registry.transition_flag(c, fid, "mapped", "mapping Call v2 loaded", automatic=True)
        registry.transition_flag(c, fid, "dismissed", "not wanted", actor_name="A Person")
        registry.transition_flag(c, fid, "open", "reopened", actor_name="A Person")
        ev = c.execute(text("SELECT from_state, to_state, actor_name FROM phone_schema_flag_events WHERE flag_id = :f "
                            "ORDER BY id"), {"f": fid}).fetchall()
        assert [tuple(e[:2]) for e in ev] == [("open", "mapping_needed"), ("mapping_needed", "mapped"),
                                              ("mapped", "dismissed"), ("dismissed", "open")]
        assert registry.list_flags(c, "open")[0]["id"] == fid


@needs_corpus
def test_the_captured_samples_raise_no_flag_after_the_seed():
    with corpus_connection() as c:
        registry.apply_seed(c)
        exts = [r[0] for r in c.execute(text(
            "SELECT id FROM phone_extractions WHERE capture_state IN ('captured', 'captured_incomplete') AND "
            "record_count > 10000 ORDER BY record_count"))]
        assert exts
        for e in exts:
            assert registry.observe_extraction(c, e)["flags_raised"] == 0


@needs_template
def test_flag_endpoints_are_admin_only_and_record_the_actor():
    import uuid as _uuid
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import sessionmaker

    from postgres.models.enums import GlobalRole
    from postgres.models.user import User
    from postgres.session import get_db
    from routers.phones import router
    from routers.users import get_current_db_user

    with fresh_engine() as engine:
        with engine.begin() as c:
            registry.apply_seed(c)
            case = make_case(c)
            ext = make_extraction(c, case, [(0, None, 0, model("ZzzEndpoint", []))])
            fid = registry.observe_extraction(c, ext)["flag_ids"][0]
        Session = sessionmaker(bind=engine)
        app = FastAPI()
        app.include_router(router)
        role = {"r": GlobalRole.user}

        def db():
            s = Session()
            try:
                yield s
            finally:
                s.close()

        app.dependency_overrides[get_db] = db
        app.dependency_overrides[get_current_db_user] = lambda: User(
            id=_uuid.uuid4(), email="admin@x.test", name="Admin Person", global_role=role["r"])
        with TestClient(app) as client:
            assert client.get("/api/phones/registry/flags?state=open").status_code == 403
            assert client.post("/api/phones/registry/flags/%d/transition" % fid,
                               json={"to": "acknowledged", "reason": "x"}).status_code == 403
            role["r"] = GlobalRole.admin
            listed = client.get("/api/phones/registry/flags?state=open").json()
            assert listed["total"] == 1 and listed["flags"][0]["flag_kind"] == "new_type"
            r = client.post("/api/phones/registry/flags/%d/transition" % fid,
                            json={"to": "acknowledged", "reason": "generic reading is enough"})
            assert r.status_code == 200, r.text
            assert client.post("/api/phones/registry/flags/%d/transition" % fid,
                               json={"to": "mapping_needed", "reason": "x"}).status_code == 409
            assert client.post("/api/phones/registry/flags/%d/transition" % fid,
                               json={"to": "mapped", "reason": "x"}).status_code == 422
        with engine.connect() as c:
            ev = c.execute(text("SELECT to_state, actor_name, actor_email FROM phone_schema_flag_events WHERE "
                                "flag_id = :f"), {"f": fid}).fetchall()
        assert [tuple(e) for e in ev] == [("acknowledged", "Admin Person", "admin@x.test")]


INVENTED_SKELETON = ["project", {"reportVersion": "7.70"}, None, [
    ["caseInformation", None, None, [["field", {"name": "Notes"}, registry.INVENTED_REPORT_MARK, None]]],
    ["decodedData", None, None, [["@r", 0, 1]]]]]


def _direction(value):
    return [(0, None, 0, model("Call", [fld("Direction", ("ModelDirections", value))]))]


@needs_template
def test_an_invented_report_adds_no_vocabulary_and_a_known_value_is_still_counted():
    with fresh_engine() as engine, engine.begin() as c:
        registry.apply_seed(c)
        case = make_case(c)
        ext = make_extraction(c, case, _direction("Sideways"), skeleton=INVENTED_SKELETON)
        out = registry.observe_extraction(c, ext)
        assert out["invented_values_skipped"] == 1 and out["flags_raised"] == 0
        assert c.execute(text("SELECT count(*) FROM phone_schema_set_values WHERE value = 'Sideways'")).scalar() == 0
        known = make_extraction(c, case, _direction("Incoming"), skeleton=INVENTED_SKELETON)
        assert registry.observe_extraction(c, known)["invented_values_skipped"] == 0
        assert c.execute(text("SELECT observed_count FROM phone_schema_set_values WHERE set_name = 'ModelDirections' "
                              "AND value = 'Incoming'")).scalar() == 1


@needs_template
def test_forgetting_invented_values_keeps_real_ones_and_the_record_of_the_flag():
    with fresh_engine() as engine, engine.begin() as c:
        registry.apply_seed(c)
        case = make_case(c)
        junk = make_extraction(c, case, _direction("Junk"), label="J")
        shared = make_extraction(c, case, _direction("Shared"), label="S")
        real = make_extraction(c, case, _direction("Real"), label="R")
        also_real = make_extraction(c, case, _direction("Shared"), label="T")
        for e in (junk, shared, real, also_real):
            registry.observe_extraction(c, e)
        # each report was marked only after it was observed, as on live
        for e in (junk, shared):
            c.execute(text("UPDATE phone_extraction_documents SET skeleton = CAST(:s AS jsonb) WHERE extraction_id = :e"),
                      {"s": json.dumps(INVENTED_SKELETON), "e": e})
        over = c.execute(text("SELECT min(id) FROM phone_schema_set_values WHERE set_name = 'ModelDirections'")).scalar()
        c.execute(text("INSERT INTO phone_schema_flags (flag_kind, registry_table, registry_id, "
                       "raised_by_extraction_id, severity, state, detail) VALUES ('set_overflow', 'set_values', :r, "
                       ":e, 'info', 'open', '{}'::jsonb)"), {"r": over, "e": junk})
        dry = registry.forget_invented_values(c, dry_run=True)
        assert (dry["values"], dry["flags"]) == (1, 2)
        assert c.execute(text("SELECT count(*) FROM phone_schema_set_values WHERE value = 'Junk'")).scalar() == 1
        seed_before = c.execute(text("SELECT count(*) FROM phone_schema_set_values WHERE origin = 'seed'")).scalar()

        assert registry.forget_invented_values(c)["values"] == 1
        values = {r[0] for r in c.execute(text("SELECT value FROM phone_schema_set_values WHERE origin = 'observed'"))}
        assert values == {"Shared", "Real"}
        assert c.execute(text("SELECT count(*) FROM phone_schema_set_values WHERE origin = 'seed'")).scalar() == seed_before
        page = registry.list_flags_page(c, "dismissed")
        assert page["total"] == 2
        kept = [f for f in page["flags"] if f["flag_kind"] == "new_set_value"][0]
        assert kept["subject"]["value"] == "Junk"
        assert kept["last_event"]["by"] == registry.INVENTED_ACTOR and "invented" in kept["last_event"]["reason"]
        assert registry.forget_invented_values(c)["values"] == 0
        assert registry.list_flags_page(c, "dismissed")["total"] == 2
