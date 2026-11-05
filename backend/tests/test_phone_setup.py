"""The Needs a decision box's backend (02 sections 4.1, 4.2, 8.3, 8.8; 03 section 7.3): region, device zone and a zone
for times with no offset as decisions, read back through the production re-read. Synthetic phones only."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from services.financial.decisions import Actor
from services.phone import corrections, identities, numbers, phone_setup, readings, registry, significant, sweep
from tests.phone_pg import fld, fresh_engine, make_case, make_extraction, model, needs_template, refs
from tests.test_phone_mappings import _shipped, hooks, stamp  # noqa: F401 (fixture)

BARE_MX = "8112345678"  # no valid US number; valid in Mexico
WALL = "2023-03-14T15:07:12"


def _messages():
    m1 = model("InstantMessage", [fld("TimeStamp", ("TimeStamp", "2023-03-14T15:07:12-04:00")), fld("Body", ("String", "one")),
                                  fld("Source", ("String", "SyntheticApp")), refs("From", 1), refs("To", 2, kind="multiModelField")])
    me = model("Party", [fld("Identifier", ("String", "+12025550100")), fld("IsPhoneOwner", ("Boolean", "True"))])
    them = model("Party", [fld("Identifier", ("String", BARE_MX)), fld("IsPhoneOwner", ("Boolean", "False"))])
    m2 = model("InstantMessage", [fld("TimeStamp", ("TimeStamp", WALL)), fld("Body", ("String", "two")),
                                  fld("Source", ("String", "SyntheticApp")), refs("From", 4), refs("To", 5, kind="multiModelField")])
    me2 = model("Party", [fld("Identifier", ("String", "+12025550100")), fld("IsPhoneOwner", ("Boolean", "True"))])
    them2 = model("Party", [fld("Identifier", ("String", "2025550143")), fld("IsPhoneOwner", ("Boolean", "False"))])
    return [(0, None, 0, m1), (1, 0, 0, me), (2, 0, 0, them), (3, None, 0, m2), (4, 3, 0, me2), (5, 3, 0, them2)]


@pytest.fixture
def phone(hooks, monkeypatch, tmp_path):
    from services import manual_changes
    monkeypatch.setattr(manual_changes, "INBOX", tmp_path / "inbox.jsonl")
    _shipped(hooks, ["type"])
    readings.install()
    with fresh_engine() as engine:
        with engine.begin() as c:
            registry.apply_seed(c)
            case = make_case(c)
            first = stamp(0, "0.0", "TimeStamp", "InstantMessage")
            second = stamp(3, "0.0", "TimeStamp", "InstantMessage")
            second.update(i=None, os="absent", off=None, lw=datetime(2023, 3, 14, 15, 7, 12), ot=WALL)
            ext = make_extraction(c, case, _messages(), timestamps=[first, second], label="C1")
            uid, email = c.execute(text("SELECT u.id, u.email FROM users u JOIN cases k ON k.owner_user_id = u.id "
                                        "WHERE k.id = :c"), {"c": case}).one()
        assert sweep.interpret_one(engine, ext)["status"] == "done"
        yield engine, case, ext, Actor(name="Synthetic Reviewer", email=email, user_id=uid)


def _keys(c, ext):
    return {r[0] for r in c.execute(text(
        "SELECT p.identity_key FROM phone_participations p JOIN phone_interpretation_state s ON s.extraction_id = "
        "p.extraction_id AND s.generation = p.generation WHERE p.extraction_id = :e AND NOT p.is_phone_owner"), {"e": ext})}


def _row(c, ext):
    return c.execute(text("SELECT t.machine_instant, t.instant, t.instant_basis, t.original_text, t.local_wall_time FROM "
                          "pv_time t WHERE t.extraction_id = :e AND t.original_text = :w"), {"e": ext, "w": WALL}).one()


@needs_template
def test_the_preview_counts_numbers_as_the_box_does_and_an_undone_reading_leaves_no_identity(phone):
    engine, case, ext, actor = phone
    sweep._hooks["apply"].append(identities.build)  # the production chain's identity step; the fixture restores it
    with engine.connect() as c:
        identities.build(c, ext, phone_setup._generation(c, ext))
        c.execute(text("CREATE TEMP TABLE spelled AS SELECT * FROM phone_participations WHERE extraction_id = :e AND "
                       "identifier_raw = '2025550143'"), {"e": ext})
        c.execute(text("UPDATE spelled SET participation_uid = gen_random_uuid(), identifier_raw = '(202) 555-0143'"))
        c.execute(text("INSERT INTO phone_participations SELECT * FROM spelled"))
        c.commit()
        s = phone_setup.region_state(c, ext)
        d = phone_setup.describe_region(c, ext, "MX")
        assert d["numbers"] == s["numbers"] + s["unread"] == 2  # two spellings of one number count once
        total = significant.summary(c, case)["total"]
        assert total >= 3
        keys = {r[0] for r in c.execute(text("SELECT identity_key FROM pv_identity WHERE case_id = :c"), {"c": case})}
    with Session(engine) as db:
        corrections.set_default_region(db, case_id=case, extraction_id=ext, region="MX", reason="a Mexican phone", actor=actor)
        db.commit()
    assert sweep.interpret_one(engine, ext)["status"] == "done"
    with engine.connect() as c:
        s = phone_setup.region_state(c, ext)
        assert (s["numbers"], s["unread"]) == (d["read"], d["unread"])  # what the preview said is what was saved
    with Session(engine) as db:
        corrections.set_default_region(db, case_id=case, extraction_id=ext, region=None, reason="Undo of: a Mexican phone",
                                       actor=actor)
        db.commit()
    sweep.interpret_one(engine, ext)
    with engine.connect() as c:
        assert significant.summary(c, case)["total"] == total
        assert {r[0] for r in c.execute(text("SELECT identity_key FROM pv_identity WHERE case_id = :c"), {"c": case})} == keys
        assert c.execute(text("SELECT sighting_count FROM phone_identities WHERE case_id = :c AND identity_key = "
                              "'phone:+528112345678'"), {"c": case}).scalar() == 0  # the row stays; older sightings need it


@needs_template
def test_region_is_shown_assumed_then_a_decision_rereads_and_an_undo_goes_back(phone):
    engine, case, ext, actor = phone
    with engine.connect() as c:
        s = phone_setup.region_state(c, ext)
        assert (s["region"], s["basis"], s["assumed"]) == ("US", "assumed_default", True)
        assert s["numbers"] == 1 and s["unread"] == 1  # the US number read; the Mexican digits are no US number
        assert s["words"] == "1 number was read assuming United States"
        assert "phone:+528112345678" not in _keys(c, ext)
        d = phone_setup.describe_region(c, ext, "MX")
        assert d["numbers"] == 2 and d["changed"] >= 1 and "Mexico" in d["words"]
    with Session(engine) as db:
        with pytest.raises(corrections.CorrectionError, match="reason"):
            corrections.set_default_region(db, case_id=case, extraction_id=ext, region="MX", reason=" ", actor=actor)
        with pytest.raises(corrections.CorrectionError, match="country"):
            corrections.set_default_region(db, case_id=case, extraction_id=ext, region="ZZ", reason="x", actor=actor)
        corrections.set_default_region(db, case_id=case, extraction_id=ext, region="MX", reason="a Mexican phone", actor=actor)
        db.commit()
    assert sweep.interpret_one(engine, ext)["status"] == "done"
    with engine.connect() as c:
        assert "phone:+528112345678" in _keys(c, ext)
        s = phone_setup.region_state(c, ext)
        assert (s["region"], s["basis"], s["assumed"]) == ("MX", "decided", False)
        assert s["decision"]["by"] == "Synthetic Reviewer" and s["undo_to"] is None
        assert c.execute(text("SELECT count(*) FROM manual_changes WHERE case_id = :c AND kind = 'phone_default_region'"),
                         {"c": case}).scalar() == 1
    with Session(engine) as db:
        corrections.set_default_region(db, case_id=case, extraction_id=ext, region=None, reason="Undo of: a Mexican phone",
                                       actor=actor)
        db.commit()
    sweep.interpret_one(engine, ext)
    with engine.connect() as c:
        assert "phone:+528112345678" not in _keys(c, ext)
        assert phone_setup.region_state(c, ext)["basis"] == "assumed_default"


@needs_template
def test_a_decided_zone_reaches_the_view_and_the_report_zone_is_kept(phone):
    engine, case, ext, actor = phone
    with Session(engine) as db:
        with pytest.raises(corrections.CorrectionError, match="time zone"):
            corrections.set_device_zone(db, case_id=case, extraction_id=ext, zone="Mars/Olympus", reason="x", actor=actor)
        corrections.set_device_zone(db, case_id=case, extraction_id=ext, zone="America/Mexico_City", reason="seen on the phone",
                                    actor=actor)
        db.commit()
    assert sweep.interpret_one(engine, ext)["status"] == "done"
    with engine.connect() as c:
        z = phone_setup.zone_state(c, ext)
        assert (z["zone"], z["basis"], z["report_zone"]) == ("America/Mexico_City", "decided", None)
        assert c.execute(text("SELECT device_zone, device_zone_basis FROM pv_extraction WHERE extraction_id = :e"),
                         {"e": ext}).one() == ("America/Mexico_City", "decided")
    with Session(engine) as db:
        corrections.set_device_zone(db, case_id=case, extraction_id=ext, zone=None, reason="undo", actor=actor)
        db.commit()
    sweep.interpret_one(engine, ext)
    with engine.connect() as c:
        z = phone_setup.zone_state(c, ext)
        assert z["zone"] is None and z["basis"] == "not_in_report"


@needs_template
def test_a_zone_applied_to_a_time_with_no_offset_keeps_the_report_and_is_labelled(phone):
    engine, case, ext, actor = phone
    with engine.connect() as c:
        r = _row(c, ext)
        assert r.instant is None and r.machine_instant is None and r.instant_basis is None
        assert phone_setup.offsetless_state(c, ext)["times"] == 1
        d = phone_setup.describe_offsetless(c, ext, "America/New_York")
        assert d["times"] == 1 and d["undated_events"] == 1
    with Session(engine) as db:
        corrections.apply_zone_to_offsetless(db, case_id=case, extraction_id=ext, zone="America/New_York",
                                             reason="the examiner's notes say Eastern", actor=actor)
        db.commit()
    assert sweep.interpret_one(engine, ext)["status"] == "done"
    with engine.connect() as c:
        r = _row(c, ext)
        assert r.machine_instant is None and r.original_text == WALL and r.local_wall_time is not None  # original kept
        assert r.instant == datetime(2023, 3, 14, 19, 7, 12, tzinfo=timezone.utc) and r.instant_basis == "zone_decision"
        o = phone_setup.offsetless_state(c, ext)
        assert o["applied"] == 1 and o["zone"] == "America/New_York"
        uid = c.execute(text("SELECT record_uid FROM pv_time WHERE original_text = :w AND extraction_id = :e"),
                        {"w": WALL, "e": ext}).scalar()
        assert (str(uid), "TimeStamp") in phone_setup.zone_decided_times(c, case, [uid])
        assert phone_setup.zone_decided_files(c, case, ["00000000-0000-0000-0000-000000000001"]) == set()  # the query runs
    with Session(engine) as db:  # a clock offset moves it too, and both show in the basis
        corrections.set_clock_offset(db, case_id=case, extraction_id=ext, offset_seconds=60, reason="fast", actor=actor)
        db.commit()
    sweep.interpret_one(engine, ext)
    with engine.connect() as c:
        r = _row(c, ext)
        assert r.instant == datetime(2023, 3, 14, 19, 8, 12, tzinfo=timezone.utc) and r.instant_basis == "zone_and_clock"
    with Session(engine) as db:
        corrections.apply_zone_to_offsetless(db, case_id=case, extraction_id=ext, zone=None, reason="undo", actor=actor)
        db.commit()
    sweep.interpret_one(engine, ext)
    with engine.connect() as c:
        r = _row(c, ext)
        assert r.instant is None and r.instant_basis is None


@needs_template
def test_clock_offset_preview_counts_the_times_the_decision_moves(phone):
    engine, case, ext, actor = phone
    with engine.connect() as c:
        d = phone_setup.describe_clock(c, ext, -120, "2023-03-14T00:00:00Z", "2023-03-15T00:00:00Z")
        assert (d["times"], d["total"]) == (1, 1) and "2 minutes earlier" in d["words"]
        assert phone_setup.describe_clock(c, ext, 60, "2024-01-01T00:00:00Z", None)["times"] == 0
        with pytest.raises(corrections.CorrectionError):
            phone_setup.describe_clock(c, ext, 0, None, None)
    with Session(engine) as db:
        corrections.set_clock_offset(db, case_id=case, extraction_id=ext, offset_seconds=-120, reason="fast", actor=actor)
        db.commit()
    with engine.connect() as c:
        p = phone_setup.clock_state(c, ext)["periods"]
        assert len(p) == 1 and p[0]["offset_seconds"] == -120 and p[0]["times"] == 1 and p[0]["decision"]["reason"] == "fast"


def test_region_names_read_in_words():
    assert numbers.region_name("MX") == "Mexico" and numbers.region_name("US") == "United States"
    assert "MX" in numbers.regions() and "ZZ" not in numbers.regions()
