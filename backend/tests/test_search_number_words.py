"""A phone number typed any way finds it stored any way (03 section 11.3; lx-phonesearch A).

Invented data only: 555 numbers and made-up text.
"""
from __future__ import annotations

import pytest
from sqlalchemy import text

from services.phone import fold as F
from services.phone import streams
from services.phone.filters import StreamFilter
from services.search import number_words as N
from services.search import search as S
from tests.phone_pg import fresh_engine, make_case, needs_template
from tests.phone_streams_fixture import at, phone

OWNER, ANA = "phone:+12025550100", "phone:+12025550143"


@pytest.mark.parametrize("typed", ["2025550143", "(202) 555-0143", "202-555-0143", "202.555.0143", "+1 202 555 0143",
                                   "1-202-555-0143", "+12025550143"])
def test_every_way_of_writing_a_number_searches_the_same_digits(typed):
    assert N.number_digits(typed) == "2025550143"


@pytest.mark.parametrize("typed", ["Pell", "dorian pell", "2024", "555-01", "a/b+c 2025550143", "flat 12b", ""])
def test_words_short_numbers_and_mixed_text_are_not_number_queries(typed):
    assert N.number_digits(typed) is None


def test_a_trunk_zero_is_dropped_so_a_national_number_finds_the_international_one():
    assert N.number_digits("07700 900123") == "7700900123"
    assert N.number_digits("+44 7700 900123") == "7700900123"


def test_digits_join_across_spaces_but_never_across_a_word():
    assert N.joined(F.fold("(202) 555-0143")) == "2025550143"
    assert "2025550143" not in N.joined(F.fold("room 202 then 555 0143"))  # "then" splits them
    assert N.span("Call (202) 555-0143 now", "2025550143") == (6, 19)  # "202) 555-0143"
    assert N.span("room 202 then 555 0143", "2025550143") is None


@pytest.fixture
def world():
    with fresh_engine() as engine:
        with engine.begin() as c:
            case = make_case(c)
            ext, evs = phone(c, case, events=[
                dict(kind="message", instant=at(2023, 3, 14, 10), body="ring me on (202) 555-0143 after six",
                     thread="t", parties=[(ANA, "sender", False, None, None), (OWNER, "recipient", True, None, None)]),
                dict(kind="message", instant=at(2023, 3, 14, 11), body="or +12025550143", thread="t",
                     parties=[(ANA, "sender", False, None, None), (OWNER, "recipient", True, None, None)]),
                dict(kind="message", instant=at(2023, 3, 14, 12), body="room 202 then 555 0143", thread="t",
                     parties=[(ANA, "sender", False, None, None), (OWNER, "recipient", True, None, None)])])
        yield {"engine": engine, "case": case, "ext": str(ext), "evs": evs}


@pytest.mark.parametrize("typed", ["2025550143", "(202) 555-0143", "+1 202 555 0143", "202-555-0143"])
def test_a_number_typed_any_way_finds_both_messages_and_conversations_counts_the_same(world, typed):
    with world["engine"].connect() as c:
        g = {x["group"]: x for x in S.search(c, world["case"], typed, groups=("messages",))["groups"]}
        f = StreamFilter.model_validate({"case_id": str(world["case"]), "kinds": ["message", "chat_activity"],
                                         "text": {"query": typed}})
        assert g["messages"]["total"] == 2 == streams.shown_count(c, f)  # never the "room 202 then 555 0143" one
        matches = sorted(h["snippet"]["match"] for h in g["messages"]["items"])
    assert matches == ["202) 555-0143", "2025550143"]  # the original digits, first to last, are the highlight


def test_the_number_index_is_read_and_its_expression_is_the_search_expression(world):
    """The partial index built by the migration must be usable by the query the search writes."""
    with world["engine"].connect() as c:
        idx = c.execute(text("SELECT indexdef FROM pg_indexes WHERE indexname = 'ix_phone_texts_digits_joined'")).scalar()
        assert idx, "migration 20261125_phone_texts_digits_joined did not build the index"
        c.execute(text("SET enable_seqscan = off"))
        p = {}
        cond = N.sql("t.value_folded", "(202) 555-0143", lambda v: p.setdefault("d", v) and ":d")
        plan = "\n".join(r[0] for r in c.execute(text("EXPLAIN SELECT count(*) FROM phone_texts t WHERE " + cond), p))
    assert "ix_phone_texts_digits_joined" in plan
