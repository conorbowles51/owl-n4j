"""A person's decision survives a new version of the mapping (followups m110505261531507).

Unchanged content keeps the decision; changed content keeps it visible as needing review, with a correction still in
use until a person decides; a rule that is gone is listed. Rule 1: only the corrected value is used, and a catalogue
version must never put the catalogue's value back in silence."""
from __future__ import annotations

import copy
import json

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from services.phone import reading_recheck, readings, sweep  # noqa: F401
from services.phone.mappings import apply, loader
from tests.phone_pg import fresh_engine, needs_template
from tests.test_phone_mappings import CALL, hooks, write  # noqa: F401 (fixture)
from tests.test_phone_readings import _actor, _call_id, _setup, review  # noqa: F401 (fixture)

pytestmark = needs_template


def _version(dirpath, n, **body):
    v = copy.deepcopy(CALL)
    v["version"] = n
    v["body"].update(body)
    write(str(dirpath), v)
    loader.use_data_dir(str(dirpath))


def _state(engine, ext, rule):
    with engine.connect() as c:
        return c.execute(text(
            "SELECT j.status, j.resolved_by, j.adjudication_id, j.evidence FROM phone_mapping_judgements j JOIN "
            "phone_interpretation_state s ON s.extraction_id = j.extraction_id AND s.generation = j.generation WHERE "
            "j.extraction_id = :e AND j.rule_id = :r"), {"e": ext, "r": rule}).one()


def _roles(engine, ext):
    with engine.connect() as c:
        return dict(c.execute(text(
            "SELECT p.role_in_record || '>' || p.role, p.interpretation_level FROM phone_participations p JOIN "
            "phone_interpretation_state s ON s.extraction_id = p.extraction_id AND s.generation = p.generation WHERE "
            "p.extraction_id = :e AND p.role_basis = 'mapping'"), {"e": ext}).fetchall())


def _correct_from(engine, case, ext, actor):
    with Session(engine) as db:
        out = readings.correct(db, case, _call_id(db.connection(), ext, "Call.role.From"), choice_id="role:callee",
                               reason="the from side is the far end on this handset", actor=actor)
        db.commit()
    assert sweep.interpret_one(engine, ext)["status"] == "done"
    return out


def test_a_correction_on_an_unchanged_rule_applies_to_the_new_version(review):
    with fresh_engine() as engine:
        case, ext, actor = _setup(engine)
        out = _correct_from(engine, case, ext, actor)
        assert _roles(engine, ext)["From>callee"] == "reviewed"
        _version(review, 2, text_fields=["Account"])  # a rule of its own changes; Call.role.From does not
        assert sweep.interpret_one(engine, ext)["status"] == "done"
        assert _roles(engine, ext)["From>callee"] == "reviewed"  # on the old code: From>caller, unconfirmed
        st = _state(engine, ext, "Call.role.From")
        assert st.status == "corrected" and st.resolved_by == "Synthetic Reviewer"
        assert str(st.adjudication_id) == out["decision_id"]
        assert st.evidence["earlier_decision"]["version"] == 1
        assert st.evidence["earlier_decision"]["needs_review"] is False
        with engine.connect() as c:
            item = next(i for i in readings.queue(c, case)["items"] if i["rule_id"] == "Call.role.From")
        assert item["status"] == "corrected" and "has not changed since" in item["earlier_decision"]["words"]


def test_a_correction_on_a_changed_rule_stays_in_use_and_needs_review(review):
    with fresh_engine() as engine:
        case, ext, actor = _setup(engine)
        _correct_from(engine, case, ext, actor)
        _version(review, 2, participants=dict(CALL["body"]["participants"], role_map={"From": "author", "To": "callee"}))
        assert sweep.interpret_one(engine, ext)["status"] == "done"
        # the correction stays in use, and no person has checked the rule as it now stands
        assert _roles(engine, ext)["From>callee"] == "applied_unconfirmed"
        st = _state(engine, ext, "Call.role.From")
        assert st.status == "open" and st.resolved_by is None and st.adjudication_id is None
        with engine.connect() as c:
            item = next(i for i in readings.queue(c, case)["items"] if i["rule_id"] == "Call.role.From")
        e = item["earlier_decision"]
        assert e["needs_review"] and e["by"] == "Synthetic Reviewer" and "stays in use" in e["words"]


def test_a_confirmation_on_a_changed_rule_is_shown_and_settles_nothing(review):
    with fresh_engine() as engine:
        case, ext, actor = _setup(engine)
        with Session(engine) as db:
            call = _call_id(db.connection(), ext, "Call.role.From")
            kinds = [k["id"] for k in readings.examples(db.connection(), case, call)["kinds"]]
            readings.confirm(db, case, call, viewed=kinds, actor=actor)
            db.commit()
        assert sweep.interpret_one(engine, ext)["status"] == "done"
        _version(review, 2, participants=dict(CALL["body"]["participants"], role_map={"From": "author", "To": "callee"}))
        assert sweep.interpret_one(engine, ext)["status"] == "done"
        assert _state(engine, ext, "Call.role.From").status == "open"
        assert _roles(engine, ext)["From>author"] == "applied_unconfirmed"
        with engine.connect() as c:
            item = next(i for i in readings.queue(c, case)["items"] if i["rule_id"] == "Call.role.From")
        assert item["earlier_decision"]["needs_review"] and "needs a new look" in item["earlier_decision"]["words"]


def test_a_person_deciding_on_the_new_version_ends_the_earlier_decision(review):
    with fresh_engine() as engine:
        case, ext, actor = _setup(engine)
        _correct_from(engine, case, ext, actor)
        _version(review, 2, participants=dict(CALL["body"]["participants"], role_map={"From": "author", "To": "callee"}))
        assert sweep.interpret_one(engine, ext)["status"] == "done"
        with Session(engine) as db:
            call = _call_id(db.connection(), ext, "Call.role.From")
            kinds = [k["id"] for k in readings.examples(db.connection(), case, call)["kinds"]]
            readings.confirm(db, case, call, viewed=kinds, actor=actor)
            db.commit()
        assert sweep.interpret_one(engine, ext)["status"] == "done"
        assert _roles(engine, ext)["From>author"] == "reviewed"
        assert _state(engine, ext, "Call.role.From").status == "confirmed"


def test_a_rule_the_new_version_does_not_hold_is_listed(review):
    with fresh_engine() as engine:
        case, ext, actor = _setup(engine)
        _correct_from(engine, case, ext, actor)
        _version(review, 2, participants=dict(CALL["body"]["participants"], role_map={"To": "callee"}))
        assert sweep.interpret_one(engine, ext)["status"] == "done"
        with engine.connect() as c:
            q = readings.queue(c, case)
        assert [d["rule_id"] for d in q["detached"]] == ["Call.role.From"]
        assert q["detached"][0]["by"] == "Synthetic Reviewer" and "no longer has that rule" in q["detached"][0]["words"]


def test_a_decision_survives_two_versions_and_the_latest_counts(review):
    with fresh_engine() as engine:
        case, ext, actor = _setup(engine)
        _correct_from(engine, case, ext, actor)
        _version(review, 2, text_fields=["Account"])
        assert sweep.interpret_one(engine, ext)["status"] == "done"
        with Session(engine) as db:  # a second correction, on version 2, undoes the first
            readings.correct(db, case, _call_id(db.connection(), ext, "Call.role.From"), choice_id="role:unknown",
                             reason="cannot tell the side here", actor=actor, expected_status="corrected")
            db.commit()
        _version(review, 3, text_fields=["Direction"])
        assert sweep.interpret_one(engine, ext)["status"] == "done"
        assert "From>unknown" in _roles(engine, ext)
        with engine.connect() as c:
            d = apply.reading_decisions(c, ext)
            v3 = str(next(m.id for m in loader.loaded() if m.name == "Call"))
            assert d[("Call.role.From", v3)]["choice"] == "unknown"
            assert d[("Call.role.From", v3)]["carried_from_version"] == 2


ROW = {"row_id": "r1", "type": "Call", "field": "TimeStamp", "predicates": [], "context": [],
       "outputs": {"class": "interaction", "actor": "owner", "physical": True}, "basis": "field_name",
       "reasoning": "a call", "would_change": "nothing"}
CAT = {"kind": "activity_strength", "name": "catalogue", "version": 1, "status": "applied_unconfirmed",
       "origin": "ai_draft", "review": {"reviewed_by": None, "reviewed_on": None, "basis": "synthetic",
                                        "registry_requirements": []}, "body": {"rows": [ROW, dict(ROW, row_id="r2",
                                                                                                  field="Duration")]}}


def _fake_decisions(rule, mv):
    return lambda conn, ext: {(rule, mv): {"decision": "correct", "choice": {"class": "passive"}, "decision_id": "d",
                                           "by": "P", "by_email": "p@x", "at": None, "reason": "why"}}


def test_a_catalogue_row_unchanged_or_changed_across_versions(hooks):
    with fresh_engine() as engine:
        write(str(hooks), CAT)
        loader.use_data_dir(str(hooks))
        ms = loader.loaded()
        loader.ensure_recorded(engine)
        v1 = str(ms[0].id)
        apply._earlier_versions.clear()
        changed = dict(ROW, outputs=dict(ROW["outputs"], physical=False))
        write(str(hooks), dict(CAT, version=2, body={"rows": [dict(ROW, row_id="r2", field="Duration"), changed]}))
        loader.use_data_dir(str(hooks))
        ms2 = loader.loaded()
        v2 = str(ms2[0].id)
        with engine.connect() as c:
            for rid, needs in (("activity_strength/catalogue/r1", True), ("activity_strength/catalogue/r2", False)):
                apply.register_reading_decisions(_fake_decisions(rid, v1))
                d = apply.reading_decisions(c, "x", ms2)[(rid, v2)]
                assert d["needs_review"] is needs
                assert d["carried_from_version"] == 1
                # one row out of a version never touches the other rows' rule ids
                assert apply.decision_level(ms2[0], d) == ("applied_unconfirmed" if needs else "reviewed")
                assert apply.reading_status(ms2[0], d) == ("open" if needs else "corrected")


def test_earlier_decision_is_plain_json():
    d = {"decision": "correct", "choice": "x", "by": "P", "at": None, "reason": "r", "decision_id": None,
         "carried_from_version": 2, "needs_review": True}
    assert json.loads(json.dumps(apply.earlier_decision(d), default=str))["version"] == 2
    assert apply.earlier_decision({"decision": "confirm"}) is None


if __name__ == "__main__":
    pytest.main([__file__])
