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
def hooks(tmp_path, monkeypatch):
    from services.phone import identities, readings
    from tests.test_phone_mappings import hooks as _h  # noqa: F401
    identities.install()
    readings.install()
    return tmp_path
