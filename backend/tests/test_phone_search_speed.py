"""Search every phone: the first results read the case once per source (lx-phonesearch E).

Phone reference 1 (14 phones, 3.2 million records) took 16 to 49 s for its first results on 26 Nov at load 30 to 40.
The causes, each pinned here so it cannot come back: every name folded through the Unicode steps, the people check
folding every identity name of the case, each kind's first page and count running the text match again, and the
message match testing every event of every phone. Invented data only.
"""
from __future__ import annotations

import random
import unicodedata

from sqlalchemy import event

from services.phone import fold as F
from services.phone import streams
from services.phone.filters import StreamFilter
from services.search import phone_search as P
from services.search import search as S
from tests.phone_pg import needs_template
from tests.test_phone_search import world  # noqa: F401  (the fixture)


def _steps(text, exact=False):
    """``fold``'s seven steps, written out, for comparison."""
    if exact:
        return F._strip_format(text).casefold()
    s = unicodedata.normalize("NFKC", text)
    s = "".join(F.STYLED.get(c, c) for c in s)
    s = F._confusables(s)
    s = F._strip_format(s)
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = unicodedata.normalize("NFC", s).casefold()
    s = "".join(c if (c.isalnum() or unicodedata.category(c).startswith("M")) else " " for c in s)
    return F._WS.sub(" ", s).strip()


def test_plain_ascii_folds_without_the_unicode_steps_and_to_the_same_result(monkeypatch):
    rng = random.Random(7)
    samples = ["Dorian (office)", "O'Brien-Smith", "+1 (240) 295-8796", "a\x01b\tc\r\nd", "  MIKE__the\x7fBIKE  ", ""]
    samples += ["".join(chr(rng.randrange(128)) for _ in range(rng.randrange(1, 24))) for _ in range(3000)]
    want = {(t, ex): _steps(t, ex) for t in samples for ex in (False, True)}

    class Refusing:  # fold.py's own unicodedata, with normalize refused; every other module keeps the real one
        def __getattr__(self, name):
            return getattr(unicodedata, name)

        @staticmethod
        def normalize(*a, **k):
            raise AssertionError("plain ASCII went through the Unicode steps")

    monkeypatch.setattr(F, "unicodedata", Refusing())
    for (t, ex), w in want.items():
        assert F.fold(t, exact=ex) == w, (t, ex)
    monkeypatch.undo()
    assert F.fold("José Ⓟell") == "jose pell"  # anything else still takes the steps


@needs_template
def test_the_people_check_folds_only_names_that_could_match(world, monkeypatch):  # noqa: F811
    folded = []
    real = F.fold

    def counting(text, exact=False):
        folded.append(text)
        return real(text, exact=exact)

    monkeypatch.setattr(F, "fold", counting)
    with world["engine"].connect() as c:
        n, hits = S._people(c, world["case"], "office", False, False, 0, 100)
    assert [h["identity_key"] for h in hits] == ["phone:+12025550177"]
    assert "Dorian (office)" in folded and "D Pell" in folded  # the hit's names, to title it
    shown = [t for t in folded if t and t.startswith("+1 ")]
    assert shown == ["+1 202-555-0177"], shown  # no other identity of the case is read and folded


@needs_template
def test_first_pages_come_from_the_counts_and_equal_each_kinds_own_first_page(world):  # noqa: F811
    matches = []

    def seen(conn, cursor, statement, params, context, executemany):
        if "value_folded LIKE" in statement:
            matches.append(statement)

    event.listen(world["engine"], "before_cursor_execute", seen)
    try:
        with world["engine"].connect() as c:
            out = P.phone_search(c, world["case"], "pell")
    finally:
        event.remove(world["engine"], "before_cursor_execute", seen)
    # messages, calls and emails in one statement, other records in one: not once more per kind and again to count
    assert len(matches) == 2, len(matches)
    with world["engine"].connect() as c:
        for g in out["groups"]:
            own = P.kind_page(c, world["case"], "pell", g["kind"], limit=P.FIRST)
            assert own["items"] == g["items"], g["kind"]


def test_the_message_match_starts_from_the_text_index():
    """Without the candidate set Postgres tested all 400,000 events of Phone reference 1 against the matching texts
    (38,000 pages read, 9.5 s for "dinner"); with it, it reads the matching events through ix_phone_comm_events_record
    (3.8 s cold, 1.5 s warm). The condition is only necessary: what matches is decided by the two tests beside it."""
    case = "00000000-0000-0000-0000-000000000001"
    sql = streams.Query(None, StreamFilter.model_validate({"case_id": case, "text": {"query": "dinner"}}), {}).matched_sql()
    assert "ev.record_uid IN (SELECT t.record_uid FROM phone_texts t WHERE t.case_id = CAST(:case AS uuid)" in sql
    exact = StreamFilter.model_validate({"case_id": case, "text": {"query": "dinner", "exact_characters": True}})
    assert "ev.record_uid IN (SELECT" not in streams.Query(None, exact, {}).matched_sql()  # no index for exact


@needs_template
def test_the_people_saved_differently_come_beside_the_first_results_and_the_same(world):  # noqa: F811
    with world["engine"].connect() as c:
        whole = P.phone_search(c, world["case"], "pell")
        first = P.phone_search(c, world["case"], "pell", people=False)
        later = P.people_step(c, world["case"], "pell")
    assert whole["saved_differently"] and whole["people_pending"] is False
    assert first["saved_differently"] == [] and first["people_pending"] is True
    assert [s for s in first["next_steps"] if s["id"] == "person"] == []
    assert later["saved_differently"] == whole["saved_differently"]
    person = [{k: v for k, v in s.items() if k != "rank"} for s in whole["next_steps"] if s["id"] == "person"]
    assert later["steps"] == person
    rest = lambda out: [(s["id"], s["title"]) for s in out["next_steps"] if s["id"] != "person"]  # noqa: E731
    assert rest(first) == rest(whole)
    with world["engine"].connect() as c:
        assert P.people_step(c, world["case"], "pe") == {"saved_differently": [], "steps": []}  # too short to fold
