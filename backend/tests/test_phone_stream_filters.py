"""Each Conversations filter (03 section 6.4), applied by the server with the true count, and the apps on offer.
Synthetic phones in a throwaway PostgreSQL database."""
from __future__ import annotations

import pytest
from sqlalchemy import text

from services.phone import streams as S
from services.phone.filters import Flags, StreamFilter, TextFilter, canonical_json
from tests.phone_pg import fresh_engine, make_case, needs_template
from tests.phone_streams_fixture import GEN, at, phone

OWNER, ANA = "phone:+12025550100", "phone:+12025550143"
pytestmark = needs_template


def msg(instant, sender, recips, body="hello", **kw):
    parties = [(sender, "sender", sender == OWNER, None, None)] + [(r, "recipient", r == OWNER, None, None)
                                                                    for r in recips]
    return dict(kind=kw.pop("kind", "message"), instant=instant, body=body, parties=parties,
                direction="outgoing" if sender == OWNER else "incoming", **kw)


@pytest.fixture
def scene():
    with fresh_engine() as engine:
        with engine.begin() as c:
            case = make_case(c)
            ext, evs = phone(c, case, events=[
                msg(at(2023, 3, 10), ANA, [OWNER], body="an apple", app="WhatsApp", thread="a"),
                msg(at(2023, 3, 11), OWNER, [ANA], body="a pear", app="WhatsApp", thread="a"),
                msg(at(2023, 3, 12), ANA, [OWNER], body="a plum", app="Signal", thread="b", deleted_state="Deleted"),
                msg(at(2023, 3, 13), ANA, [OWNER], body="a fig", app=None, thread="c", deleted_state="Trash"),
                msg(None, ANA, [OWNER], body="no time", app="WhatsApp", thread="a", deleted_state="Unknown"),
            ])
            yield c, case, ext, evs


def total(c, case, **kw):
    return S.index_comm_events(c, StreamFilter(case_id=str(case), **kw))["counts"]["events"]


def test_apps_include_those_with_no_app_recorded(scene):
    c, case, _, _ = scene
    assert total(c, case) == 5
    assert total(c, case, apps=["WhatsApp"]) == 3
    assert total(c, case, apps=[None]) == 1
    assert total(c, case, apps=["Signal", None]) == 2


def test_the_apps_on_offer_are_counted_under_the_other_filters_only(scene):
    c, case, _, _ = scene
    got = S.app_counts(c, StreamFilter(case_id=str(case), apps=["Signal"], directions=["incoming"]))
    assert got["items"] == [{"app": "WhatsApp", "count": 2}, {"app": "Signal", "count": 1}, {"app": None, "count": 1}]
    assert got["counts"] == {"apps": 2, "events": 4}


def test_direction(scene):
    c, case, _, _ = scene
    assert total(c, case, directions=["outgoing"]) == 1
    assert total(c, case, directions=["incoming"]) == 4


def test_date_range_keeps_undated_rows_unless_asked(scene):
    c, case, _, _ = scene
    span = dict(from_instant=at(2023, 3, 11, 0), to_instant=at(2023, 3, 12, 23, 59))
    assert total(c, case, **span) == 3, "two in the range and the undated one, which is counted and listed"
    assert total(c, case, include_no_time=False, **span) == 2


def test_deletion_state(scene):
    c, case, _, _ = scene
    assert total(c, case, deleted_states=["Deleted", "Trash"]) == 2
    assert total(c, case, deleted_states=["Deleted"]) == 1
    assert total(c, case, deleted_states=["Trash"]) == 1
    assert total(c, case, deleted_states=[None, "Intact", "Unknown"]) == 3


def test_text_in_the_body_with_true_count(scene):
    c, case, _, _ = scene
    assert total(c, case, text=TextFilter(query="PLUM")) == 1
    assert total(c, case, text=TextFilter(query="PLUM", exact_characters=True)) == 1
    assert total(c, case, text=TextFilter(query="nowhere")) == 0


def test_unreadable_and_has_attachment(scene):
    c, case, ext, evs = scene
    c.execute(text(
        "INSERT INTO phone_record_summaries (case_id, extraction_id, document_index, ordinal, record_uid, "
        "root_record_uid, parent_record_uid, locator, model_type, generation, is_top_level, title, has_time, has_point) "
        "VALUES (:c, :e, 0, 90, md5('child')::uuid, :p, :p, 'x', 'ScrambledMessageData', :g, false, 's', false, false)"),
        {"c": case, "e": ext, "p": evs[0]["record_uid"], "g": GEN})
    assert total(c, case, flags=Flags(unreadable=True)) == 1
    assert total(c, case, flags=Flags(unreadable=False)) == 4
    c.execute(text(
        "INSERT INTO phone_file_references (extraction_id, document_index, record_ordinal, body_path, mechanism, "
        "reference_text, resolution, ambiguous) VALUES (:e, 0, 1, 'jumptargets', 'jumptarget', 'x.jpg', 'unresolved', false)"),
        {"e": ext})
    assert total(c, case, flags=Flags(has_attachment=True)) == 1
    assert total(c, case, flags=Flags(has_attachment=False)) == 4


def test_filters_narrow_the_thread_list_with_the_true_total(scene):
    c, case, _, _ = scene
    got = S.thread_list(c, StreamFilter(case_id=str(case), apps=["Signal"]))
    assert got["counts"]["threads"] == 1 and got["counts"]["threads_total"] == 3


def test_a_filter_with_no_app_has_its_own_stable_snapshot():
    case = "00000000-0000-0000-0000-000000000001"
    a = canonical_json(StreamFilter(case_id=case, apps=[None, "Signal"]))
    assert a == canonical_json(StreamFilter(case_id=case, apps=["Signal", None]))
    assert a != canonical_json(StreamFilter(case_id=case, apps=["Signal"]))
