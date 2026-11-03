"""Copies applier (03 section 3.4, rule version 1): the group key is unchanged by the per-record rewrite, and its
cost grows with events plus participations, not their product (followups m1103004811638).

Invented data only. Needs the PostgreSQL phone template.
"""
from __future__ import annotations

import hashlib
import time
import unicodedata

from sqlalchemy import text

from services.phone import copies
from tests.phone_pg import fresh_engine, make_case, needs_template
from tests.phone_streams_fixture import GEN, at, phone

pytestmark = needs_template
OWNER, ANA = "phone:+12025550100", "phone:+12025550143"


def _m(instant, body, dup=None, sender=ANA):
    return dict(kind="message", instant=instant, body=body, thread="t", dup=dup, direction="incoming",
                parties=[(sender, "sender", False, None, None), (OWNER, "recipient", True, None, None)])


def test_the_group_key_is_the_rule_v1_text_so_existing_groups_and_decisions_keep_their_ids():
    t = at(2023, 3, 14, 15)
    with fresh_engine() as engine:
        with engine.begin() as c:
            case = make_case(c)
            ext, _ = phone(c, case, events=[_m(t, "same"), _m(t, "same"), _m(t, "other")])
            copies.assign(c, ext, GEN)
            groups = [r[0] for r in c.execute(text(
                "SELECT dup_group_uid FROM phone_comm_events WHERE extraction_id = :e ORDER BY ordinal"), {"e": ext})]
    body = hashlib.sha256(unicodedata.normalize("NFC", "same").encode()).hexdigest()
    key = "|".join(["message", "incoming", "2023-03-14T15:00:00.000000", ANA, OWNER, body])
    expected = hashlib.sha256(key.encode()).hexdigest()
    assert groups == [expected, expected, None]


def test_a_phone_with_many_events_and_parties_is_grouped_in_time_that_grows_with_its_size():
    n = 4000
    with fresh_engine() as engine:
        with engine.begin() as c:
            case = make_case(c)
            ext, _ = phone(c, case, events=[_m(at(2023, 1, 1, 0, 0, 0) + __import__("datetime").timedelta(minutes=i),
                                               "synthetic %d" % (i // 2)) for i in range(n)])
        with engine.begin() as c:
            started = time.monotonic()
            out = copies.assign(c, ext, GEN)
            took = time.monotonic() - started
    assert out == {"groups": 0, "records": 0}  # a minute apart: no copies
    # measured on the scratch server (EXPLAIN ANALYZE): 0.13 s for 4,000 events with this change (0.78 s for 16,000),
    # 8.9 s for 4,000 before it
    assert took < 5, took
