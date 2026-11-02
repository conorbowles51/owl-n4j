"""02-U5 review (RQ-2 to RQ-8, one feed line per review action): confirming and correcting the system's readings
(02 sections 6.8, 6.10, 8.8; 07 J-8). Synthetic phones only."""
from __future__ import annotations

import json
import re

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from services import manual_changes
from services.financial.decisions import Actor
from services.phone import readings, registry, sweep
from tests.phone_pg import fresh_engine, make_case, needs_template
from tests.test_phone_mappings import CALL, call_extraction, hooks, write  # noqa: F401 (fixture)


@pytest.fixture
def review(hooks, tmp_path, monkeypatch):
    write(str(hooks), CALL)
    readings.install()
    monkeypatch.setattr(manual_changes, "INBOX", tmp_path / "inbox.jsonl")
    return hooks


def _actor(c, case):
    uid, email = c.execute(text("SELECT u.id, u.email FROM users u JOIN cases k ON k.owner_user_id = u.id WHERE "
                                "k.id = :c"), {"c": case}).one()
    return Actor(name="Synthetic Reviewer", email=email, user_id=uid)


def _call_id(c, ext, rule):
    return c.execute(text("SELECT j.id FROM phone_mapping_judgements j JOIN phone_interpretation_state s ON "
                          "s.extraction_id = j.extraction_id AND s.generation = j.generation WHERE j.extraction_id = :e "
                          "AND j.rule_id = :r"), {"e": ext, "r": rule}).scalar()


def _feed(c, case):
    return c.execute(text("SELECT kind, change_type FROM manual_changes WHERE case_id = :c ORDER BY created_at"),
                     {"c": case}).fetchall()


def _setup(engine):
    with engine.begin() as c:
        registry.apply_seed(c)
        case = make_case(c)
        ext = call_extraction(c, case, label="C1")
        actor = _actor(c, case)
    assert sweep.interpret_one(engine, ext)["status"] == "done"
    return case, ext, actor


def test_a_phone_is_named_by_the_token_in_its_report_name():
    assert readings.label_from_name("/x/C6_synthetic_Report.xml") == "C6"
    assert readings.label_from_name("Report C12 synthetic.xml") == "C12"
    assert readings.label_from_name("C3.xml") == "C3"
    assert readings.label_from_name("CASE3_Report.xml") is None and readings.label_from_name("AC6_x.xml") is None
    assert readings.label_from_name(None) is None


@needs_template
def test_labels_fall_back_in_capture_order_and_shared_ones_say_which_report(review):
    from tests.phone_pg import make_extraction
    with fresh_engine() as engine:
        with engine.begin() as c:
            case = make_case(c)
            a = make_extraction(c, case, [], label="C1")
            b = make_extraction(c, case, [], label="C1")
            d = make_extraction(c, case, [], label="unlabelled")
            c.execute(text("UPDATE phone_extractions SET created_at = created_at + make_interval(secs => :s) WHERE "
                           "id = :e"), [{"s": 1, "e": b}, {"s": 2, "e": d}])
            assert readings.phone_labels(c, case) == {str(a): "C1 (report 1 of 2)", str(b): "C1 (report 2 of 2)",
                                                      str(d): "Phone 1"}


@needs_template
def test_the_queue_is_plain_sentences_most_records_first_with_no_field_names(review):
    with fresh_engine() as engine:
        case, ext, _ = _setup(engine)
        with engine.connect() as c:
            q = readings.queue(c, case)
        assert q["open"] == q["total"] > 0
        counts = [i["records"] for i in q["items"]]
        assert counts == sorted(counts, reverse=True)
        for i in q["items"]:
            assert re.match(r"^On C\d+, .+: .+\. Affects [\d,]+ \w", i["sentence"]), i["sentence"]
            # RQ-1: no field or rule names in the copy: no CamelCase token, no dotted id
            assert not re.search(r"[a-z][A-Z]|\w\.\w", i["sentence"]), i["sentence"]
            assert i["origin"] == "Mapped by the system, not yet confirmed"
        role = [i for i in q["items"] if i["rule_id"] == "Call.role.From"][0]
        assert {c["label"] for c in role["choices"]} == {"The caller is the other party",
                                                       "Which side this party is on is not known"}


@needs_template
def test_looks_right_needs_every_kind_viewed_and_stores_a_standard_reason_and_one_feed_line(review):
    with fresh_engine() as engine:
        case, ext, actor = _setup(engine)
        with engine.connect() as c:
            jid = _call_id(c, ext, "Call.event_time")
            ex = readings.examples(c, case, jid)
        kinds = [k["id"] for k in ex["kinds"]]
        assert kinds == ["direction:outgoing", "one_to_one"]  # the synthetic calls are all outgoing, one to one
        assert all(k["example"]["record_uid"] == k["record_uid"] for k in ex["kinds"])
        with Session(engine) as db:  # RQ-2: refused until every kind was viewed
            with pytest.raises(readings.ReadingError, match="Open every kind of example first"):
                readings.confirm(db, case, jid, viewed=kinds[:1], actor=actor)
            db.rollback()
            out = readings.confirm(db, case, jid, viewed=kinds, opened=kinds[:1], actor=actor, note="looked at both")
            db.commit()
        assert out["reason"] == "Confirmed on the review screen after viewing 2 examples across 2 kinds"
        with engine.connect() as c:
            a = c.execute(text("SELECT decision, reason, reason_kind, actor_name, after FROM adjudications WHERE "
                               "id = :d"), {"d": out["decision_id"]}).one()
            assert (a.decision, a.reason_kind, a.actor_name) == ("confirm_phone_reading", "standard", "Synthetic Reviewer")
            assert a.reason == out["reason"] and a.after["note"] == "looked at both"
            # RQ-8: whether each example was opened is recorded with the decision
            assert [(e["kind"], e["opened"]) for e in a.after["examples"]] == [("direction:outgoing", True),
                                                                             ("one_to_one", False)]
            assert _feed(c, case) == [("phone_reading", "confirm")]  # RQ-5: one feed line
            lv = c.execute(text("SELECT DISTINCT interpretation_level FROM phone_time_values WHERE extraction_id = :e "
                                "AND mapping_row_id = 'Call.event_time'"), {"e": ext}).fetchall()
            assert lv == [("reviewed",)]
            q = {i["rule_id"]: i for i in readings.queue(c, case)["items"]}
            assert q["Call.event_time"]["status"] == "confirmed" and q["Call.event_time"]["reason_kind"] == "standard"
            assert q["Call.event_time"]["resolved_by"] == "Synthetic Reviewer"
            assert [p["state"] for p in readings.progress(c, case)] == ["waiting"]
        out2 = sweep.interpret_one(engine, ext)  # the new decision re-derives the phone; the level stays
        assert out2["status"] == "done"
        with engine.connect() as c:
            lv = c.execute(text("SELECT DISTINCT t.interpretation_level FROM phone_time_values t JOIN "
                                "phone_interpretation_state s ON s.extraction_id = t.extraction_id AND s.generation = "
                                "t.generation WHERE t.extraction_id = :e AND t.mapping_row_id = 'Call.event_time'"),
                           {"e": ext}).fetchall()
            assert lv == [("reviewed",)]
            assert {i["rule_id"]: i["status"] for i in readings.queue(c, case)["items"]}["Call.event_time"] == "confirmed"
            assert [p["state"] for p in readings.progress(c, case)] == ["done"]
        with Session(engine) as db:  # RQ-6: a second decision on the same reading is refused with the wording
            with pytest.raises(readings.Conflict, match=r"^Synthetic Reviewer confirmed this (just now|\d+ minutes? "
                                                        r"ago)\. Your view is updated\.$"):
                readings.confirm(db, case, _call_id(db.connection(), ext, "Call.event_time"), viewed=kinds,
                                 actor=actor)


@needs_template
def test_a_correction_re_derives_only_its_scope_and_leaves_other_cases_unchanged(review):
    with fresh_engine() as engine:
        case, ext, actor = _setup(engine)
        with engine.begin() as c:
            sibling = call_extraction(c, case, label="C2")  # same case, same report format
            other_case = make_case(c)
            elsewhere = call_extraction(c, other_case)  # another case
        sweep.interpret_one(engine, sibling)
        sweep.interpret_one(engine, elsewhere)
        with Session(engine) as db:
            with pytest.raises(readings.ReadingError, match="reason in your own words"):
                readings.correct(db, case, _call_id(db.connection(), ext, "Call.role.From"), choice_id="role:callee",
                                 reason=" ", actor=actor)
            db.rollback()
            out = readings.correct(db, case, _call_id(db.connection(), ext, "Call.role.From"), choice_id="role:callee",
                                   reason="the from side is the far end on this handset", actor=actor)
            db.commit()
        assert out["scope"] == ["C1"] and out["choice"] == "The caller is the other party"
        with engine.connect() as c:
            assert _feed(c, case) == [("phone_reading", "change")]
            prop = c.execute(text("SELECT origin, case_id, decision_id::text FROM phone_mapping_proposals")).one()
            assert tuple(prop) == ("case_correction", case, out["decision_id"])
            prog = {p["phone"]: p["state"] for p in readings.progress(c, case)}
            assert prog == {"C1": "waiting", "C2": "done"}
        assert sweep.interpret_one(engine, ext)["status"] == "done"

        def roles(e):
            with engine.connect() as c:
                return dict(c.execute(text(
                    "SELECT p.role_in_record || '>' || p.role, count(*) FROM phone_participations p JOIN "
                    "phone_interpretation_state s ON s.extraction_id = p.extraction_id AND s.generation = p.generation "
                    "WHERE p.extraction_id = :e AND p.role_basis = 'mapping' GROUP BY 1"), {"e": e}).fetchall())
        assert roles(ext) == {"From>callee": 3, "To>callee": 3}
        assert roles(sibling) == {"From>caller": 3, "To>callee": 3}     # RQ-4: only its scope
        assert roles(elsewhere) == {"From>caller": 3, "To>callee": 3}   # RQ-7: other cases unchanged
        with engine.connect() as c:
            j = c.execute(text("SELECT j.status, j.resolved_by, j.resolution_reason FROM phone_mapping_judgements j JOIN "
                               "phone_interpretation_state s ON s.extraction_id = j.extraction_id AND s.generation = "
                               "j.generation WHERE j.extraction_id = :e AND j.rule_id = 'Call.role.From'"), {"e": ext}).one()
            assert tuple(j) == ("corrected", "Synthetic Reviewer", "the from side is the far end on this handset")


@needs_template
def test_the_same_format_scope_lists_and_corrects_the_cases_matching_phones(review):
    with fresh_engine() as engine:
        case, ext, actor = _setup(engine)
        with engine.begin() as c:
            sibling = call_extraction(c, case, label="C2")
        sweep.interpret_one(engine, sibling)
        with Session(engine) as db:
            out = readings.correct(db, case, _call_id(db.connection(), ext, "Call.role.From"), choice_id="role:unknown",
                                   reason="cannot tell the side on these reports", actor=actor, scope="same_format")
            db.commit()
        assert out["scope"] == ["C1", "C2"]
        with engine.connect() as c:
            n = c.execute(text("SELECT count(*) FROM adjudications WHERE decision = 'correct_phone_reading'")).scalar()
            assert n == 2 and _feed(c, case) == [("phone_reading", "change")]  # one feed line for the one action
        for e in (ext, sibling):
            assert sweep.interpret_one(engine, e)["status"] == "done"
        with engine.connect() as c:
            assert c.execute(text(
                "SELECT count(*) FROM phone_participations p JOIN phone_interpretation_state s ON s.extraction_id = "
                "p.extraction_id AND s.generation = p.generation WHERE p.case_id = :c AND p.role_in_record = 'From' "
                "AND p.role = 'unknown'"), {"c": case}).scalar() == 6
        json.dumps(out)
