"""02-U10 (U-backend for 07 J-7): suggestions and identity decisions (02 sections 8.7, 8.8). Synthetic phones only."""
from __future__ import annotations

import os
import subprocess
import sys

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from postgres.models.enums import AdjudicationDecision, AdjudicationSubject
from postgres.models.financial import _ADJUDICATION_DECISIONS, _ADJUDICATION_SUBJECTS
from services import manual_changes
from services.financial.decisions import Actor
from services.phone import identities, identity_decisions as idd, readings, registry, sweep
from tests.phone_pg import fresh_engine, make_case, needs_template
from tests.test_phone_identities import _call, _contact, _phone
from tests.test_phone_mappings import CALL, hooks, write  # noqa: F401 (fixture)

A, B, C = "phone:+12025550143", "phone:+12025550144", "phone:+12025550145"


@pytest.fixture
def people(hooks, tmp_path, monkeypatch):
    write(str(hooks), CALL)
    identities.install()
    readings.install()
    monkeypatch.setattr(manual_changes, "INBOX", tmp_path / "inbox.jsonl")
    return hooks


def _card(top, name, *numbers):
    from tests.phone_pg import fld, model, refs
    card = model("Contact", [fld("Name", ("String", name)), refs("Entries", *[top + 1 + i for i in range(len(numbers))])])
    recs = [(top, None, top, card)]
    for i, n in enumerate(numbers):
        recs.append((top + 1 + i, top, top, model("PhoneNumber", [fld("Value", ("String", n))])))
    return recs, []


def _setup(engine, parts_a, parts_b=None):
    with engine.begin() as c:
        registry.apply_seed(c)
        case = make_case(c)
        exts = [_phone(c, case, parts_a)]
        if parts_b:
            exts.append(_phone(c, case, parts_b))
        uid, email = c.execute(text("SELECT u.id, u.email FROM users u JOIN cases k ON k.owner_user_id = u.id WHERE "
                                    "k.id = :c"), {"c": case}).one()
    for e in exts:
        assert sweep.interpret_one(engine, e)["status"] == "done"
    return case, exts, Actor(name="Synthetic Reviewer", email=email, user_id=uid), uid


def _user(db, uid):
    from postgres.models.user import User
    return db.get(User, uid)


@needs_template
def test_no_suggestion_from_names_alone_and_one_from_a_shared_card(people):
    with fresh_engine() as engine:
        # the same saved name for two different numbers on two phones: names alone, no suggestion
        case, _, _, _ = _setup(engine, [_contact(0, "Same Name", "+12025550143")],
                               [_contact(0, "Same Name", "+12025550144")])
        with engine.begin() as c:
            idd.compute_suggestions(c, case)
            assert idd.suggestions(c, case) == []
    with fresh_engine() as engine:
        case, _, _, _ = _setup(engine, [_card(0, "Synthetic Two", "+12025550143", "+12025550144")])
        with engine.begin() as c:
            idd.compute_suggestions(c, case)
            s = idd.suggestions(c, case)
        assert len(s) == 1 and [i["identity_key"] for i in s[0]["identities"]] == [A, B]
        assert [r["reason"] for r in s[0]["reasons"]] == ["same_card"] and s[0]["score"] == 0.6


@needs_template
def test_name_support_needs_a_name_seen_away_from_the_shared_card(people):
    with fresh_engine() as engine:
        # the shared card's own name on both numbers is not support; the same name on two other cards is
        case, _, _, _ = _setup(engine, [_card(0, "Synthetic Two", "+12025550143", "+12025550144"),
                                        _contact(10, "Synthetic Pat", "+12025550143"),
                                        _contact(12, "Synthetic Pat", "+12025550144")])
        with engine.begin() as c:
            idd.compute_suggestions(c, case)
            s = idd.suggestions(c, case)
        assert [r["reason"] for r in s[0]["reasons"]] == ["same_card", "name_support"] and s[0]["score"] == 0.64


@needs_template
def test_link_then_unlink_restores_and_both_decisions_are_in_order(people):
    with fresh_engine() as engine:
        case, _, actor, uid = _setup(engine, [_card(0, "Synthetic Two", "+12025550143", "+12025550144")])
        with Session(engine) as db:
            rev = idd.links_revision(db.connection(), [db.connection().execute(text(
                "SELECT id FROM phone_identities WHERE identity_key = :k AND case_id = :c"), {"k": A, "c": case}).scalar()])
            out = idd.decide(db, case_id=case, decision="link_phone_identity", identity_keys=[A], actor=actor,
                             user=_user(db, uid), new_person_name="Synthetic Person",
                             reasons_shown=[{"reason": "same_card"}], expected_revision=rev)
            db.commit()
        with Session(engine) as db:
            with pytest.raises(idd.IdentityDecisionError, match="reason in your own words"):
                idd.decide(db, case_id=case, decision="unlink_phone_identity", identity_keys=[A], actor=actor,
                           user=_user(db, uid))
            db.rollback()
            idd.decide(db, case_id=case, decision="unlink_phone_identity", identity_keys=[A], actor=actor,
                       user=_user(db, uid), reason="linked to the wrong person")
            db.commit()
        with engine.connect() as c:
            hist = c.execute(text(
                "SELECT a.decision, a.reason_kind, a.actor_name, a.subject_sequence, a.reason FROM adjudications a JOIN "
                "phone_identities i ON i.id = a.subject_id WHERE i.identity_key = :k AND i.case_id = :c ORDER BY "
                "a.subject_sequence"), {"k": A, "c": case}).fetchall()
            assert [(h[0], h[1], h[2], h[3]) for h in hist] == [
                ("link_phone_identity", "standard", "Synthetic Reviewer", 1),
                ("unlink_phone_identity", "typed", "Synthetic Reviewer", 2)]
            assert hist[0][4] == "Linked on the review screen after seeing: listed together on one contact card"
            assert c.execute(text("SELECT count(*) FROM phone_identity_links WHERE case_id = :c"), {"c": case}).scalar() == 0
            assert c.execute(text("SELECT count(*) FROM case_profiles WHERE id = :d"), {"d": out["dossier_id"]}).scalar() == 1
            feed = c.execute(text("SELECT kind FROM manual_changes WHERE case_id = :c"), {"c": case}).fetchall()
            assert feed == [("phone_identity",), ("phone_identity",)]  # one feed line per action


@needs_template
def test_a_rejected_pair_is_not_suggested_again(people):
    with fresh_engine() as engine:
        # A is on one card with B and on another with C: two suggestions; rejecting A-B leaves A-C open
        case, _, actor, uid = _setup(engine, [_card(0, "Synthetic Two", "+12025550143", "+12025550144"),
                                              _card(10, "Synthetic Other", "+12025550143", "+12025550145")])
        with engine.begin() as c:
            idd.compute_suggestions(c, case)
            assert len(idd.suggestions(c, case)) == 2
        with Session(engine) as db:
            idd.decide(db, case_id=case, decision="reject_phone_identity_link", identity_keys=[A], actor=actor,
                       user=_user(db, uid), target_identity_key=B)
            db.commit()
        with engine.begin() as c:
            idd.compute_suggestions(c, case)
            assert [[i["identity_key"] for i in s["identities"]] for s in idd.suggestions(c, case)] == [[A, C]]
            assert sorted(r[0] for r in c.execute(text(
                "SELECT state FROM phone_identity_suggestions WHERE case_id = :c"), {"c": case})) == ["open", "rejected"]


@needs_template
def test_split_writes_one_decision_per_identity_in_one_transaction_and_a_stale_revision_is_refused(people):
    with fresh_engine() as engine:
        case, _, actor, uid = _setup(engine, [_card(0, "Synthetic Three", "+12025550143", "+12025550144",
                                                    "+12025550145")])
        with Session(engine) as db:
            out = idd.decide(db, case_id=case, decision="link_phone_identity", identity_keys=[A, B, C], actor=actor,
                             user=_user(db, uid), new_person_name="Synthetic Person")
            db.commit()
        assert len(out["decisions"]) == 3
        with Session(engine) as db:
            stale = idd.links_revision(db.connection(), [])
            with pytest.raises(idd.StaleRevision, match="Someone else changed this person"):
                idd.decide(db, case_id=case, decision="split", identity_keys=[A, B], actor=actor, user=_user(db, uid),
                           reason="two people share this card", expected_revision=stale)
            db.rollback()
        with Session(engine) as db:
            ids = [r[0] for r in db.connection().execute(text(
                "SELECT id FROM phone_identities WHERE case_id = :c AND identity_key = ANY(:k) ORDER BY id"),
                {"c": case, "k": [A, B]})]
            out = idd.decide(db, case_id=case, decision="split", identity_keys=[A, B], actor=actor, user=_user(db, uid),
                             reason="two people share this card", expected_revision=idd.links_revision(db.connection(), ids))
            db.commit()
        with engine.connect() as c:
            rows = c.execute(text("SELECT decision, reason, xmin::text FROM adjudications WHERE id = ANY(CAST(:d AS uuid[]))"),
                             {"d": out["decisions"]}).fetchall()
            assert len(rows) == 2 and {r[0] for r in rows} == {"unlink_phone_identity"}
            assert len({r[2] for r in rows}) == 1  # written by one transaction
            assert {r[1] for r in rows} == {"two people share this card"}
            left = c.execute(text("SELECT i.identity_key FROM phone_identity_links l JOIN phone_identities i ON i.id = "
                                  "l.identity_id WHERE l.case_id = :c"), {"c": case}).fetchall()
            assert left == [(C,)]


def test_every_phone_decision_and_subject_is_in_the_constraint():
    for d in AdjudicationDecision:
        assert "'%s'" % d.value in _ADJUDICATION_DECISIONS, d
        assert len(d.value) <= 48
    for s in AdjudicationSubject:
        assert "'%s'" % s.value in _ADJUDICATION_SUBJECTS, s
        assert len(s.value) <= 24


@needs_template
def test_the_decisions_migration_round_trips():
    backend = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with fresh_engine() as engine:
        url = engine.url.set(drivername="postgresql+psycopg").render_as_string(hide_password=False)
        env = dict(os.environ, DATABASE_URL=url)
        alembic = [sys.executable, "-m", "alembic"]
        for step in (["downgrade", "20261102_phone_identities"], ["upgrade", "head"]):
            r = subprocess.run(alembic + step, cwd=backend, env=env, capture_output=True, text=True, timeout=300)
            assert r.returncode == 0, r.stderr[-2000:]
        with engine.connect() as c:
            assert c.execute(text("SELECT count(*) FROM information_schema.columns WHERE table_name = 'adjudications' "
                                  "AND column_name = 'reason_kind'")).scalar() == 1
