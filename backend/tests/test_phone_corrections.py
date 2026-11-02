"""02-U15: corrections on phone data (02 section 10). Synthetic phones only."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from services.financial.decisions import Actor
from services.phone import corrections, readings, registry, sweep, thread_text
from tests.phone_pg import fld, fresh_engine, make_case, make_extraction, model, needs_template, refs
from tests.test_phone_mappings import _shipped, hooks, stamp  # noqa: F401 (fixture)

T0 = "2023-03-14T15:07:12-04:00"


def _message(body, when=T0):
    msg = model("InstantMessage", [fld("TimeStamp", ("TimeStamp", when)), fld("Body", ("String", body)),
                                   fld("Source", ("String", "SyntheticApp")),
                                   refs("From", 1), refs("To", 2, kind="multiModelField")])
    me = model("Party", [fld("Identifier", ("String", "+12025550100")), fld("IsPhoneOwner", ("Boolean", "True"))])
    them = model("Party", [fld("Identifier", ("String", "+12025550143")), fld("IsPhoneOwner", ("Boolean", "False"))])
    return msg, me, them


@pytest.fixture
def phone(hooks):
    _shipped(hooks, ["type"])
    readings.install()
    with fresh_engine() as engine:
        with engine.begin() as c:
            registry.apply_seed(c)
            case = make_case(c)
            msg, me, them = _message("synthetic original words")
            ext = make_extraction(c, case, [(0, None, 0, msg), (1, 0, 0, me), (2, 0, 0, them)],
                                  timestamps=[stamp(0, "0.0", "TimeStamp", "InstantMessage")], label="C1")
            uid, email = c.execute(text("SELECT u.id, u.email FROM users u JOIN cases k ON k.owner_user_id = u.id "
                                        "WHERE k.id = :c"), {"c": case}).one()
        assert sweep.interpret_one(engine, ext)["status"] == "done"
        yield engine, case, ext, Actor(name="Synthetic Reviewer", email=email, user_id=uid)


def _uid(c, ext):
    return c.execute(text("SELECT record_uid FROM pv_record WHERE extraction_id = :e AND model_type = 'InstantMessage'"),
                     {"e": ext}).scalar()


@needs_template
def test_a_corrected_body_is_the_one_searched_and_threaded_and_the_original_stays(phone):
    engine, case, ext, actor = phone
    with engine.connect() as c:
        uid = _uid(c, ext)
        captured = c.execute(text("SELECT count(*) FROM phone_records WHERE extraction_id = :e"), {"e": ext}).scalar()
    with Session(engine) as db:
        with pytest.raises(corrections.CorrectionError, match="reason in your own words"):
            corrections.correct_value(db, case_id=case, record_uid=uid, field_path="Body", corrected_text="x",
                                      reason=" ", actor=actor)
        db.rollback()
        out = corrections.correct_value(db, case_id=case, record_uid=uid, field_path="Body",
                                        corrected_text="synthetic corrected words", reason="the report misread it",
                                        actor=actor)
        db.commit()
    assert out["machine_text"] == "synthetic original words"
    assert sweep.interpret_one(engine, ext)["status"] == "done"  # the decision re-derives the phone, no re-capture
    with engine.begin() as c:
        assert c.execute(text("SELECT count(*) FROM phone_records WHERE extraction_id = :e"), {"e": ext}).scalar() \
            == captured
        row = c.execute(text("SELECT machine_value, value, value_folded FROM pv_text WHERE record_uid = :r AND "
                             "field_path = 'Body'"), {"r": uid}).one()
        assert row[0] == "synthetic original words" and row[1] == "synthetic corrected words"
        assert "corrected" in row[2] and "original" not in row[2]
        body = c.execute(text("SELECT body FROM pv_comm_event WHERE record_uid = :r"), {"r": uid}).scalar()
        assert body == "synthetic corrected words"
        thread_text.build_extraction(c, ext)
        doc = c.execute(text("SELECT t.content, t.source_locations FROM evidence_document_texts t JOIN evidence_files f "
                             "ON f.id = t.evidence_file_id WHERE f.source_type = 'phone_text' AND f.case_id = :c"),
                        {"c": case}).one()
        assert "synthetic corrected words" in doc[0] and "synthetic original words" not in doc[0]
        assert doc[1][0]["record_uid"] == str(uid) and doc[1][0]["kind"] == "phone_record"
    with Session(engine) as db:
        rev = corrections.revision(db.connection(), uid, "Body", 0)
        corrections.correct_value(db, case_id=case, record_uid=uid, field_path="Body",
                                  corrected_text="synthetic original words", reason="undo: it was right",
                                  actor=actor, expected_revision=rev)
        db.commit()
        with pytest.raises(corrections.StaleCorrection):
            corrections.correct_value(db, case_id=case, record_uid=uid, field_path="Body", corrected_text="y",
                                      reason="late", actor=actor, expected_revision=rev)
        db.rollback()
        ch = corrections.chain(db.connection(), uid)
    assert [(x["corrected_text"], x["current"], x["is_undo"]) for x in ch] == [
        ("synthetic corrected words", False, False), ("synthetic original words", True, True)]
    sweep.interpret_one(engine, ext)
    with engine.connect() as c:
        assert c.execute(text("SELECT value FROM pv_text WHERE record_uid = :r AND field_path = 'Body'"),
                         {"r": uid}).scalar() == "synthetic original words"


@needs_template
def test_a_corrected_time_needs_its_offset_and_moves_the_event_while_the_machine_time_stays(phone):
    engine, case, ext, actor = phone
    with engine.connect() as c:
        uid = _uid(c, ext)
    with Session(engine) as db:
        with pytest.raises(corrections.CorrectionError, match="offset"):
            corrections.correct_value(db, case_id=case, record_uid=uid, field_path="TimeStamp",
                                      corrected_text="2023-03-14T16:07:12", reason="clock", actor=actor)
        db.rollback()
        corrections.correct_value(db, case_id=case, record_uid=uid, field_path="TimeStamp",
                                  corrected_text="2023-03-14T16:07:12-04:00", reason="the phone's clock was an hour slow",
                                  actor=actor)
        db.commit()
    sweep.interpret_one(engine, ext)
    with engine.connect() as c:
        r = c.execute(text("SELECT machine_instant, instant, instant_basis FROM pv_time WHERE record_uid = :r "
                           "AND field_path = 'TimeStamp'"), {"r": uid}).one()
        assert r[0] == datetime(2023, 3, 14, 19, 7, 12, tzinfo=timezone.utc)
        assert r[1] == r[0] + timedelta(hours=1) and r[2] == "corrected"
        assert c.execute(text("SELECT sort_instant FROM pv_comm_event WHERE record_uid = :r"), {"r": uid}).scalar() == r[1]


@needs_template
def test_a_clock_offset_moves_only_the_times_in_its_period(phone):
    engine, case, ext, actor = phone
    with engine.connect() as c:
        uid = _uid(c, ext)
    with Session(engine) as db:
        with pytest.raises(corrections.CorrectionError, match="end after it starts"):
            corrections.set_clock_offset(db, case_id=case, extraction_id=ext, offset_seconds=60,
                                         start="2023-03-15T00:00:00Z", end="2023-03-14T00:00:00Z", reason="x",
                                         actor=actor)
        corrections.set_clock_offset(db, case_id=case, extraction_id=ext, offset_seconds=-120,
                                     start="2023-03-14T00:00:00Z", end="2023-03-15T00:00:00Z",
                                     reason="the device clock ran two minutes fast that day", actor=actor)
        db.commit()
    sweep.interpret_one(engine, ext)
    with engine.connect() as c:
        r = c.execute(text("SELECT machine_instant, instant, instant_basis FROM pv_time WHERE record_uid = :r "
                           "AND field_path = 'TimeStamp'"), {"r": uid}).one()
        assert r[1] == r[0] - timedelta(minutes=2) and r[2] == "clock_offset"
    with Session(engine) as db:
        corrections.set_clock_offset(db, case_id=case, extraction_id=ext, offset_seconds=-120,
                                     start="2023-03-16T00:00:00Z", end=None, reason="a later period only", actor=actor)
        corrections.set_clock_offset(db, case_id=case, extraction_id=ext, offset_seconds=0,
                                     start="2023-03-14T00:00:00Z", end="2023-03-15T00:00:00Z",
                                     reason="ends the first period", actor=actor)
        db.commit()
    sweep.interpret_one(engine, ext)
    with engine.connect() as c:
        r = c.execute(text("SELECT machine_instant, instant, instant_basis FROM pv_time WHERE record_uid = :r "
                           "AND field_path = 'TimeStamp'"), {"r": uid}).one()
        assert r[1] == r[0] and r[2] == "report"


def test_parse_instant_reads_z_and_offsets_and_refuses_a_bare_time():
    assert corrections.parse_instant("2023-03-14T19:07:12Z") == datetime(2023, 3, 14, 19, 7, 12, tzinfo=timezone.utc)
    assert corrections.parse_instant("2023-03-14T15:07:12-04:00").hour == 19
    with pytest.raises(corrections.CorrectionError):
        corrections.parse_instant("2023-03-14 15:07")
