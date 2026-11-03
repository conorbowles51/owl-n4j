"""05-S0: the shared analysis framework (05 section 3) and sensitive values (3.8). Invented data only.

A test approach is registered under one of 3.3's codes; it reads the case's message records and gives one result
per message, so the framework's behaviour is tested apart from any real approach.
"""
from __future__ import annotations

import types
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from services.financial.decisions import Actor
from services.phone_analysis import framework as F
from tests.phone_pg import fresh_engine, make_case, needs_template

pytestmark = needs_template
OWNER, ANA = "phone:+12025550100", "phone:+12025550143"


def _approach(fail=False):
    m = types.ModuleType("test_approach")
    m.CODE, m.VERSION = "common_contacts", "test-1"
    m.PARAMETERS = {"window_days": {"default": 7, "min": 1, "max": 30}, "mode": {"default": "a", "choices": ["a", "b"]}}
    m.KINDS = ("message_seen",)

    def run(conn, case_id, params, ctx):
        if fail:
            raise RuntimeError("synthetic failure")
        rows = conn.execute(text("SELECT extraction_id, record_uid, sort_instant FROM pv_comm_event WHERE case_id = :c "
                                 "ORDER BY record_uid"), {"c": case_id}).fetchall()
        out = []
        for i, r in enumerate(rows):
            ctx.progress(i + 1, len(rows))
            out.append({"kind": "message_seen", "strength": "plain", "measures": {"n": 1, "window": params["window_days"]},
                        "directions": {"supports": [{"code": "seen", "detail": "", "locators": []}],
                                       "undercuts": [{"code": "synced_attribution", "detail": "", "locators": []}]},
                        "period_start": r.sort_instant, "period_end": r.sort_instant,
                        "records": [{"extraction_id": str(r.extraction_id), "record_uid": str(r.record_uid),
                                     "field_path": "Body", "role": "evidence"}]})
        return out

    def coverage(conn, case_id):
        phones = {}
        from services.phone.readings import phone_labels
        for e, label in phone_labels(conn, case_id).items():
            n = conn.execute(text("SELECT count(*) FROM pv_comm_event WHERE extraction_id = :e"), {"e": e}).scalar()
            phones[str(e)] = {"label": label, "signals": {"messages": {"carries_signal": n > 0, "records": n}}}
        return {"phones": phones, "signals": [{"code": "messages", "label": "Messages"}]}

    m.run, m.coverage = run, coverage
    return m


def _m(instant, sender, recips, body):
    parties = [(sender, "sender", sender == OWNER, None, None)] + [(r, "recipient", r == OWNER, None, None)
                                                                    for r in recips]
    return dict(kind="message", instant=instant, body=body, thread="t", parties=parties, app="WhatsApp",
                direction="outgoing" if sender == OWNER else "incoming")


def _case(engine, label="C1", empty=False):
    from tests.phone_streams_fixture import at, phone
    with engine.begin() as c:
        case = make_case(c)
        phone(c, case, label=label, events=[] if empty else [_m(at(2023, 3, 2, 9), ANA, [OWNER], "one"),
                                                             _m(at(2023, 3, 3, 9), OWNER, [ANA], "two")])
        uid, email = c.execute(text("SELECT u.id, u.email FROM users u JOIN cases k ON k.owner_user_id = u.id WHERE "
                                    "k.id = :c"), {"c": case}).one()
    return str(case), Actor(name="Synthetic Reviewer", email=email, user_id=uid)


@pytest.fixture(autouse=True)
def registered():
    saved = dict(F.APPROACHES)
    F.register(_approach())
    yield
    F.APPROACHES.clear()
    F.APPROACHES.update(saved)


def test_a_run_is_idempotent_and_parameters_are_checked():
    with fresh_engine() as engine:
        case, actor = _case(engine)
        with engine.begin() as c:
            run, created = F.request_run(c, case, "common_contacts", {"window_days": 3}, actor.email)
            again, created2 = F.request_run(c, case, "common_contacts", {"window_days": 3}, actor.email)
            assert created and not created2 and again["id"] == run["id"]
            assert run["parameters"] == {"window_days": 3, "mode": "a"}  # every threshold used, by name
            other, created3 = F.request_run(c, case, "common_contacts", {"window_days": 4}, actor.email)
            assert created3 and other["id"] != run["id"]
            for bad in ({"nope": 1}, {"window_days": 99}, {"mode": "z"}, {"window_days": "7"}):
                with pytest.raises(F.AnalysisError) as e:
                    F.request_run(c, case, "common_contacts", bad, actor.email)
                assert e.value.status == 422
            with pytest.raises(F.AnalysisError):
                F.request_run(c, case, "not_an_approach", None, actor.email)


def test_results_carry_both_directions_the_full_total_and_the_records_behind_them():
    with fresh_engine() as engine:
        case, actor = _case(engine)
        with engine.begin() as c:
            run, _ = F.request_run(c, case, "common_contacts", None, actor.email)
        assert F.execute(engine, run["id"])["status"] == "completed"
        with engine.connect() as c:
            done = F.get_run(c, case, run["id"])
            assert done["status"] == "completed" and done["counts"]["results"] == 2
            assert done["coverage"]["sentence"] == "Messages exist on all 1 phones."
            page = F.results(c, case, run["id"], limit=1)
            assert page["total"] == 2 and len(page["items"]) == 1  # the total is never the page
            item = page["items"][0]
            assert item["label"] == "Lead for enquiry"
            assert item["directions"]["undercuts"][0]["code"] == "synced_attribution"
            detail = F.result_detail(c, case, item["id"])
            assert detail["records"][0]["link"].startswith("rec://") and detail["records"][0]["role"] == "evidence"
            assert F.results(c, case, run["id"], kind="other")["total"] == 0
            assert F.results(c, case, run["id"], start="2023-03-03T00:00:00Z")["total"] == 1


def test_another_case_never_sees_a_run_or_result():
    with fresh_engine() as engine:
        case, actor = _case(engine)
        other, _ = _case(engine, label="C2")
        with engine.begin() as c:
            run, _ = F.request_run(c, case, "common_contacts", None, actor.email)
        F.execute(engine, run["id"])
        with engine.connect() as c:
            rid = F.results(c, case, run["id"])["items"][0]["id"]
            for call in (lambda: F.get_run(c, other, run["id"]), lambda: F.results(c, other, run["id"]),
                         lambda: F.result_detail(c, other, rid)):
                with pytest.raises(F.NotFound):
                    call()


def test_a_failure_is_named_and_a_cancelled_queue_entry_never_runs():
    with fresh_engine() as engine:
        case, actor = _case(engine)
        F.register(_approach(fail=True))
        with engine.begin() as c:
            run, _ = F.request_run(c, case, "common_contacts", None, actor.email)
        F.execute(engine, run["id"])
        with engine.connect() as c:
            failed = F.get_run(c, case, run["id"])
        assert failed["status"] == "failed" and "synthetic failure" in failed["error"]
        F.register(_approach())
        with engine.begin() as c:
            again, created = F.request_run(c, case, "common_contacts", None, actor.email)
            assert created and again["id"] == run["id"] and again["status"] == "queued"
            assert F.cancel(c, case, run["id"])["status"] == "cancelled"
        assert F.execute(engine, run["id"])["status"] == "not_queued"


def test_decisions_carry_over_by_result_key_and_never_change_a_computed_field():
    with fresh_engine() as engine:
        case, actor = _case(engine)
        with engine.begin() as c:
            run, _ = F.request_run(c, case, "common_contacts", None, actor.email)
        F.execute(engine, run["id"])
        with engine.connect() as c:
            first = F.results(c, case, run["id"])["items"][0]
        with Session(engine) as db:
            with pytest.raises(F.AnalysisError):
                F.decide(db, case, first["id"], "rejected", "  ", actor)  # a reject without a reason is refused
            out = F.decide(db, case, first["id"], "confirmed", "Read the message myself", actor)
            db.commit()
        assert out["decision"] == "confirmed" and out["strength"] == first["strength"]
        assert out["measures"] == first["measures"]
        # changed inputs (an identity decision lands): a new run; the old one is superseded and stays readable
        with engine.begin() as c:
            c.execute(text("INSERT INTO adjudications (id, case_id, subject_type, subject_id, subject_sequence, decision, "
                           "reason, actor_name, actor_email, created_at, before, after) SELECT gen_random_uuid(), :c, "
                           "'phone_identity', gen_random_uuid(), 1, 'set_phone_identity_label', 'synthetic', 'x', "
                           "'x@x.test', now(), '{}', '{}'"), {"c": case})
            rerun, created = F.request_run(c, case, "common_contacts", None, actor.email)
        assert created and rerun["id"] != run["id"]
        F.execute(engine, rerun["id"])
        with engine.connect() as c:
            assert F.get_run(c, case, run["id"])["status"] == "superseded"
            same = [i for i in F.results(c, case, rerun["id"])["items"] if i["result_key"] == first["result_key"]][0]
            assert same["decision"] == "confirmed" and same["decisions"][0]["reason"] == "Read the message myself"
        with Session(engine) as db:
            with pytest.raises(F.Conflict):
                F.decide(db, case, first["id"], "rejected", "changed my mind", actor)


def test_a_lead_can_be_marked_not_pursued_with_a_reason_and_it_stays_in_its_decision_history():
    """07 section 14: a decision not to act is logged ("Not pursued: reason") in the case decision ledger under the
    person's name, kept in the result's history with the confirm and reject decisions, and changes no computed
    field."""
    with fresh_engine() as engine:
        case, actor = _case(engine)
        with engine.begin() as c:
            run, _ = F.request_run(c, case, "common_contacts", None, actor.email)
        F.execute(engine, run["id"])
        with engine.connect() as c:
            first = F.results(c, case, run["id"])["items"][0]
        with Session(engine) as db:
            with pytest.raises(F.AnalysisError):
                F.decide(db, case, first["id"], "not_pursued", " ", actor)  # no reason, no decision
            with pytest.raises(F.AnalysisError):
                F.decide(db, case, first["id"], "ignored", "a reason", actor)
            out = F.decide(db, case, first["id"], "not_pursued", "Both numbers belong to the same family", actor)
            db.commit()
        assert out["decision"] == "not_pursued"
        assert out["strength"] == first["strength"] and out["measures"] == first["measures"]
        assert [(d["decision"], d["reason"], d["by"]) for d in out["decisions"]] == [
            ("not_pursued", "Both numbers belong to the same family", actor.name)]
        with Session(engine) as db:
            later = F.decide(db, case, first["id"], "confirmed", "Followed up after the interview", actor)
            db.commit()
        assert [d["decision"] for d in later["decisions"]] == ["not_pursued", "confirmed"]
        assert later["decision"] == "confirmed"
        with engine.connect() as c:
            rows = c.execute(text("SELECT decision, reason, actor_name FROM adjudications WHERE case_id = :c AND "
                                  "subject_type = 'phone_analysis_result' ORDER BY subject_sequence"),
                             {"c": case}).all()
        assert [r.decision for r in rows] == ["not_pursue_phone_result", "confirm_phone_result"]
        assert rows[0].reason == "Both numbers belong to the same family" and rows[0].actor_name == actor.name


def test_the_decision_body_accepts_not_pursued():
    from routers.phone_analysis import DecisionBody
    body = DecisionBody(case_id=uuid.uuid4(), decision="not_pursued", reason="Out of scope for this enquiry")
    assert body.decision == "not_pursued"
    assert set(F.DECISIONS) == {"confirmed", "rejected", "not_pursued"}


def test_the_coverage_sentence_names_the_phones_that_carry_the_signal():
    cov = {"phones": {"a": {"label": "B-C1", "signals": {"n": {"carries_signal": True}}},
                      "b": {"label": "B-C2", "signals": {"n": {"carries_signal": True}}},
                      "c": {"label": "A-C3", "signals": {"n": {"carries_signal": False}}}},
           "signals": [{"code": "n", "label": "Notifications"}]}
    s = F.coverage_sentence(cov)
    assert s == "Notifications exist on 2 of 3 phones (B-C1, B-C2). Results below cover those phones only."
    assert "—" not in s


# ---- sensitive values (3.8) --------------------------------------------------------------------------------------

def _password_phone(engine):
    from services.phone import identities, readings, registry, sweep
    from tests.phone_pg import fld, make_extraction, model
    with engine.begin() as c:
        registry.apply_seed(c)
        case = make_case(c)
        ext = make_extraction(c, case, [
            (0, None, 0, model("Password", [fld("Service", ("String", "synthetic-bank.test")),
                                            fld("Data", ("String", "hunter2-synthetic"))])),
            (1, None, 1, model("CreditCard", [fld("CreditCardNumber", ("String", "4111 1111 1111 1234"))]))])
        uid, email = c.execute(text("SELECT u.id, u.email FROM users u JOIN cases k ON k.owner_user_id = u.id WHERE "
                                    "k.id = :c"), {"c": case}).one()
    assert sweep.interpret_one(engine, ext)["status"] == "done"
    return str(case), ext, Actor(name="Synthetic Reviewer", email=email, user_id=uid)


def test_sensitive_values_are_masked_until_revealed_and_each_reveal_is_logged(hooks):
    from services.phone import records, sensitive
    from services.search import search
    with fresh_engine() as engine:
        case, ext, actor = _password_phone(engine)
        with engine.connect() as c:
            uids = {r.model_type: str(r.record_uid) for r in c.execute(text(
                "SELECT model_type, record_uid FROM phone_record_summaries WHERE extraction_id = :e"), {"e": ext})}
            pw = records.record_detail(c, case, uids["Password"])
            data = [f for f in pw["fields"] if f["name"] == "Data"][0]
            assert data["sensitive"] and data["values"][0]["text"] == "••••" and data["values"][0]["masked"]
            assert "hunter2" not in records.record_text(pw)
            assert [f for f in pw["fields"] if f["name"] == "Service"][0]["values"][0]["text"] == "synthetic-bank.test"
            card = records.record_detail(c, case, uids["CreditCard"])
            assert card["fields"][0]["values"][0]["text"] == "••••1234"
            # never searched
            hits = search.search(c, case, "hunter2")
            assert all(g["total"] == 0 for g in hits["groups"].values()) if isinstance(hits["groups"], dict) else \
                all(g["total"] == 0 for g in hits["groups"])
        with Session(engine) as db:
            with pytest.raises(sensitive.RevealError):
                sensitive.reveal(db, case, uids["Password"], "Service", 0, actor)
            with pytest.raises(LookupError):
                sensitive.reveal(db, str(uuid.uuid4()), uids["Password"], "Data", 0, actor)
            out = sensitive.reveal(db, case, uids["Password"], "Data", 0, actor)
            db.commit()
        assert out["value"] == "hunter2-synthetic"
        with engine.connect() as c:
            log = sensitive.reveals(c, case)
        assert [(r["record_uid"], r["field_path"], r["by"]) for r in log] == [(uids["Password"], "Data", actor.name)]
        with pytest.raises(Exception):
            with engine.begin() as c:
                c.execute(text("UPDATE phone_sensitive_reveals SET actor_name = 'someone else'"))


@pytest.fixture
def hooks(tmp_path):
    """The sweep's hooks are process-wide: install the identity and reading passes for one test, restore after (a
    later test file's sweep must not run them)."""
    import copy
    from services.phone import identities, readings, sweep
    saved = copy.copy(sweep._hooks), {k: list(v) for k, v in sweep._hooks.items() if isinstance(v, list)}
    identities.install()
    readings.install()
    yield tmp_path
    sweep._hooks.clear()
    sweep._hooks.update(saved[0])
    sweep._hooks.update(saved[1])


# ---- review of the framework (05-S0): each case below failed on the first version ----------------------------------

def test_asking_again_for_a_superseded_run_runs_it_again_and_makes_it_current():
    with fresh_engine() as engine:
        case, actor = _case(engine)
        with engine.begin() as c:
            a, _ = F.request_run(c, case, "common_contacts", {"window_days": 3}, actor.email)
        F.execute(engine, a["id"])
        with engine.begin() as c:
            b, _ = F.request_run(c, case, "common_contacts", {"window_days": 4}, actor.email)
        F.execute(engine, b["id"])
        with engine.begin() as c:
            assert F.get_run(c, case, a["id"])["status"] == "superseded"
            again, created = F.request_run(c, case, "common_contacts", {"window_days": 3}, actor.email)
            assert created and again["id"] == a["id"] and again["status"] == "queued"
        assert F.execute(engine, a["id"])["status"] == "completed"
        with engine.connect() as c:
            assert F.get_run(c, case, b["id"])["status"] == "superseded"
            assert F.results(c, case, a["id"])["total"] == 2


def test_a_run_whose_inputs_changed_before_it_ran_is_closed_and_queued_on_the_new_inputs():
    with fresh_engine() as engine:
        case, actor = _case(engine)
        with engine.begin() as c:
            run, _ = F.request_run(c, case, "common_contacts", None, actor.email)
            c.execute(text("INSERT INTO adjudications (id, case_id, subject_type, subject_id, subject_sequence, decision, "
                           "reason, actor_name, actor_email, created_at, before, after) SELECT gen_random_uuid(), :c, "
                           "'phone_identity', gen_random_uuid(), 1, 'set_phone_identity_label', 'synthetic', 'x', "
                           "'x@x.test', now(), '{}', '{}'"), {"c": case})
        out = F.execute(engine, run["id"])
        assert out["status"] == "inputs_changed" and out["requeued"] != run["id"]
        with engine.connect() as c:
            old = F.get_run(c, case, run["id"])
            assert old["status"] == "failed" and "changed after this analysis was asked for" in old["error"]
            assert F.get_run(c, case, out["requeued"])["status"] == "queued"


def test_a_stopping_worker_puts_its_run_back_on_the_queue_and_a_new_worker_picks_up_strays():
    import threading
    with fresh_engine() as engine:
        case, actor = _case(engine)
        with engine.begin() as c:
            run, _ = F.request_run(c, case, "common_contacts", None, actor.email)
        stop = threading.Event()
        stop.set()
        assert F.execute(engine, run["id"], stop)["status"] == "requeued"
        with engine.begin() as c:
            assert F.get_run(c, case, run["id"])["status"] == "queued"
            c.execute(text("UPDATE phone_analysis_runs SET status = 'running', started_at = now() WHERE id = :i"),
                      {"i": run["id"]})
        assert F.requeue_interrupted(engine) == 1
        with engine.connect() as c:
            assert F.get_run(c, case, run["id"])["status"] == "queued"


def test_cancelling_a_run_the_worker_just_took_asks_it_to_stop_instead_of_mislabelling_it(monkeypatch):
    with fresh_engine() as engine:
        case, actor = _case(engine)
        with engine.begin() as c:
            run, _ = F.request_run(c, case, "common_contacts", None, actor.email)
            c.execute(text("UPDATE phone_analysis_runs SET status = 'running' WHERE id = :i"), {"i": run["id"]})
            real = F.get_run
            seen = iter([dict(run, status="queued")])  # what cancel read before the worker took it
            monkeypatch.setattr(F, "get_run", lambda conn, cid, rid: next(seen, None) or real(conn, cid, rid))
            out = F.cancel(c, case, run["id"])
            assert out["status"] == "running"
            assert c.execute(text("SELECT cancel_requested FROM phone_analysis_runs WHERE id = :i"),
                             {"i": run["id"]}).scalar() is True


def test_a_malformed_date_filter_is_refused_as_bad_input():
    with fresh_engine() as engine:
        case, actor = _case(engine)
        with engine.begin() as c:
            run, _ = F.request_run(c, case, "common_contacts", None, actor.email)
        F.execute(engine, run["id"])
        with engine.connect() as c:
            with pytest.raises(F.AnalysisError) as e:
                F.results(c, case, run["id"], start="last tuesday")
            assert e.value.status == 422


def test_sensitive_values_are_never_corrected_shown_through_corrections_matched_or_revealed_off_case(hooks):
    from services.phone import corrections, records, sensitive
    with fresh_engine() as engine:
        case, ext, actor = _password_phone(engine)
        with engine.connect() as c:
            uid = str(c.execute(text("SELECT record_uid FROM phone_record_summaries WHERE extraction_id = :e AND "
                                     "model_type = 'Password'"), {"e": ext}).scalar())
        with Session(engine) as db:
            with pytest.raises(corrections.CorrectionError):
                corrections.correct_value(db, case_id=case, record_uid=uid, field_path="Data", corrected_text="x",
                                          reason="typo", actor=actor)
        # a correction made before the refusal existed is masked on both sides
        with engine.begin() as c:
            did = c.execute(text("INSERT INTO adjudications (id, case_id, subject_type, subject_id, subject_sequence, "
                                 "decision, reason, actor_name, actor_email, created_at, before, after) SELECT "
                                 "gen_random_uuid(), :c, 'phone_identity', gen_random_uuid(), 1, "
                                 "'set_phone_identity_label', 'synthetic', 'x', 'x@x.test', now(), '{}', '{}' RETURNING "
                                 "id"), {"c": case}).scalar()
            c.execute(text("INSERT INTO phone_value_corrections (id, case_id, extraction_id, record_uid, field_path, "
                           "value_index, value_type, machine_text, corrected_text, decision_id) VALUES "
                           "(gen_random_uuid(), :c, :e, :r, 'Data', 0, 'String', 'hunter2-synthetic', 'hunter3', :d)"),
                      {"c": case, "e": ext, "r": uid, "d": did})
        with engine.connect() as c:
            got = corrections.chain(c, uid)
            assert got and got[0]["masked"] and "hunter" not in str(got)
            assert "hunter" not in str(records.record_detail(c, case, uid)["corrections"])
        # a phone no longer active: nothing to reveal
        with engine.begin() as c:
            c.execute(text("UPDATE phone_extractions SET standing = 'superseded' WHERE id = :e"), {"e": ext})
        with Session(engine) as db:
            with pytest.raises(LookupError):
                sensitive.reveal(db, case, uid, "Data", 0, actor)


def test_the_timeline_text_filter_never_matches_a_sensitive_value(hooks):
    from datetime import datetime, timezone
    from services.phone import registry, sweep, timeline_lens as L
    from tests.phone_pg import fld, make_extraction, model
    when = datetime(2024, 3, 2, 15, tzinfo=timezone.utc)
    with fresh_engine() as engine:
        with engine.begin() as c:
            registry.apply_seed(c)
            case = make_case(c)
            ext = make_extraction(c, case, [(0, None, 0, model("Password", [
                fld("Service", ("String", "synthetic-bank.test")), fld("Data", ("String", "hunter2-synthetic")),
                fld("DateCreated", ("TimeStamp", when.isoformat()))]))], timestamps=[
                {"o": 0, "bp": "2.0", "mt": "Password", "fn": "DateCreated", "ot": when.isoformat(), "i": when,
                 "os": "explicit", "off": 0}])
        assert sweep.interpret_one(engine, ext)["status"] == "done"
        with engine.begin() as c:  # the filter is under test, not which times are events: make this one an event
            c.execute(text("UPDATE phone_time_values SET is_event_time = true WHERE extraction_id = :e"), {"e": ext})
        with engine.connect() as c:
            def hits(q):
                f = L.TimelineLensFilter(case_id=str(case), lens_kinds=["accounts"], text={"query": q})
                o = L._Other(c, f, ["accounts"])
                return c.execute(text("SELECT count(*) FROM pv_timeline_entry t WHERE " + o.where), o.p).scalar()
            assert hits("synthetic-bank") == 1
            assert hits("hunter2") == 0
