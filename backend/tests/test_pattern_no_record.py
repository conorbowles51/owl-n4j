"""agent-phones A: a statement check says ``no_record`` with its reason when the phone cannot hold the record the
statement needs, and keeps ``insufficient_data`` for a time the phone covers too thinly.

Synthetic phones only. Opt-in PostgreSQL through ``LOUPE_TEST_PHONE_PG_TEMPLATE_URL``. The first two tests fail on
the code before ``no_record`` (both answered ``insufficient_data``).
"""
from __future__ import annotations

from datetime import timedelta

import pytest

from services.pattern_of_life import evaluation
from services.phone import registry
from tests.phone_pg import fresh_engine, make_case, needs_template
from tests.test_pattern_u11_claims import confirmed, night_phone, person
from tests.test_pattern_u4_availability import DAY, setup
from tests.test_pattern_u5_places import LAT, LON, PlacePhone, build
from tests.test_phone_mappings import hooks  # noqa: F401 (fixture)

HOME = {"lat": LAT, "lon": LON, "radius_m": 50}


@pytest.fixture(autouse=True)
def _feed_inbox(monkeypatch, tmp_path):
    from services import manual_changes
    monkeypatch.setattr(manual_changes, "INBOX", tmp_path / "inbox.jsonl")


def _phone(engine, case_maker):
    with engine.begin() as c:
        registry.apply_seed(c)
        case = make_case(c)
        p = PlacePhone()
        case_maker(p)
        ext = p.make(c, case)
    build(engine, ext)
    return case, ext


@needs_template
def test_a_time_after_every_record_on_the_phone_is_no_record_outside_coverage(hooks):
    setup(hooks)
    with fresh_engine() as engine:
        case, ext = _phone(engine, lambda p: [p.location(DAY + timedelta(hours=20, minutes=m), accuracy=10)
                                               for m in range(0, 120, 10)])
        with engine.begin() as c:
            me = person(c, case)
            subj = {"kind": "extraction", "extraction_id": str(ext)}
            a, b = DAY + timedelta(days=3, hours=20), DAY + timedelta(days=3, hours=22)
            ev = evaluation.evaluate(c, case, confirmed(c, case, me, "at_place", subj, a, b, place=HOME)["id"], me.name)
            assert ev["outcome"] == "no_record"
            assert ev["summary"]["no_record_reason"] == "outside_coverage"
            assert "outside what the phone's extraction covers" in ev["outcome_basis"]
            assert ev["outcome_words"] == evaluation.OUTCOME_WORDS["no_record"]


@needs_template
def test_a_place_statement_on_a_phone_with_no_location_records_is_no_record_not_extracted(hooks):
    setup(hooks)
    with fresh_engine() as engine:
        with engine.begin() as c:
            registry.apply_seed(c)
            case = make_case(c)
            ext = night_phone().make(c, case)
        build(engine, ext)
        with engine.begin() as c:
            me = person(c, case)
            subj = {"kind": "extraction", "extraction_id": str(ext)}
            a, b = DAY + timedelta(hours=23, minutes=30), DAY + timedelta(hours=25)
            ev = evaluation.evaluate(c, case, confirmed(c, case, me, "at_place", subj, a, b, place=HOME)["id"], me.name)
            assert ev["outcome"] == "no_record", ev["outcome_basis"]
            assert ev["summary"]["no_record_reason"] == "not_extracted"
            assert ev["outcome_basis"] == "The extraction holds no location records at all."


@needs_template
def test_a_covered_time_with_too_few_positions_stays_insufficient_data(hooks):
    setup(hooks)
    with fresh_engine() as engine:
        def recs(p):
            p.location(DAY + timedelta(hours=10), accuracy=10)
            p.location(DAY + timedelta(days=5), accuracy=10)
        case, ext = _phone(engine, recs)
        with engine.begin() as c:
            me = person(c, case)
            subj = {"kind": "extraction", "extraction_id": str(ext)}
            a, b = DAY + timedelta(days=2, hours=20), DAY + timedelta(days=2, hours=22)
            ev = evaluation.evaluate(c, case, confirmed(c, case, me, "at_place", subj, a, b, place=HOME)["id"], me.name)
            assert ev["outcome"] == "insufficient_data"
            assert "no_record_reason" not in ev["summary"]
