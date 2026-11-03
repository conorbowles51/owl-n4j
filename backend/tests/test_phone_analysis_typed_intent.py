"""05-S10 approach 7 (typed words, 10.8) and 05-S12 approach 9 (intent, 12.8), with the case vocabulary they share.
Invented data only."""
from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy import text

from services.phone_analysis import intent as I
from services.phone_analysis import typed_words as T
from services.phone_analysis import vocabulary as V
from tests.phone_analysis_fixture import record
from tests.phone_pg import fresh_engine, make_case, needs_template
from tests.phone_streams_fixture import at, phone

VOCAB = {"names": {"zorvath": {"contact_name"}, "quillon": {"financial_name"}},
         "numbers": {"12025550147"}, "endings": {"4821"}}


@pytest.fixture
def engine():
    with fresh_engine() as e:
        yield e


def test_matching_rules():
    """19.S10-a: names by token, account endings by a run ending in them, phone numbers only on 7 or more digits."""
    assert V.matches("Zorvath!", VOCAB) == [("contact_name", "zorvath")]
    assert V.matches("zorvathx", VOCAB) == []
    assert V.matches("acct 99994821", VOCAB) == [("account_ending", "99994821")]
    assert V.matches("4821", VOCAB) == [("account_ending", "4821")]
    assert V.matches("5550147", VOCAB) == [("phone_number", "5550147")]
    assert V.matches("2025", VOCAB) == []  # a 4-digit run inside a number is not a phone-number hit
    assert V.matches("0147", VOCAB) == []


def test_url_words_are_the_path_only():
    assert I.url_words("https://zorvath.example/a/quillon-plans?q=zorvath") == " a quillon plans"


def _sensitive(c, uid):
    c.execute(text("UPDATE phone_texts SET is_sensitive = true WHERE record_uid = CAST(:u AS uuid)"), {"u": uid})


def _account(c, case, printed, holder):
    c.execute(text("INSERT INTO financial_accounts (id, case_id, identity_key, institution_name, identifier_as_printed, "
                   "holder_name, currency, created_at, updated_at) VALUES (:i, :c, :k, 'Synthetic Bank', :p, :h, 'USD', "
                   "now(), now())"), {"i": uuid.uuid4(), "c": case, "k": "synthetic-%s" % uuid.uuid4(), "p": printed,
                                       "h": holder})


@needs_template
def test_typed_words_masked_and_not_elsewhere(engine):
    """10.8 tests 1 to 3: a learned word equal to an account holder name that no message holds is
    typed_not_in_extraction, its value never in the result; a 4-digit learned word equal to an account ending is a
    hit of kind account_ending; a word that a message holds is typed_and_present with the message linked."""
    with engine.begin() as c:
        case = make_case(c)
        ext, evs = phone(c, case, contacts={"phone:+12025550199": "Velmora Ashgrove"},
                         events=[{"instant": at(2023, 1, 5, 10), "direction": "outgoing", "body": "see velmora soon"}])
        _account(c, case, "XX-XXXX-4821", "Quillon Darrowby")
        w1 = record(c, case, ext, 500, "DictionaryWord", texts=[("Word", "quillon")],
                    fields=[("Frequency", "Int32", "7")])
        w2 = record(c, case, ext, 501, "DictionaryWord", texts=[("Word", "4821")])
        w3 = record(c, case, ext, 502, "DictionaryWord", texts=[("Word", "velmora")])
        w4 = record(c, case, ext, 503, "DictionaryWord", texts=[("Word", "unrelated")])
        a1 = record(c, case, ext, 504, "Autofill", texts=[("Key", "name"), ("Value", "darrowby")],
                    fields=[("Key", "String", "name")], times=[("TimeStamp", at(2023, 1, 6, 9))])
        for u in (w1, w2, w3, w4):
            _sensitive(c, u)
        c.execute(text("UPDATE phone_texts SET is_sensitive = true WHERE record_uid = CAST(:u AS uuid) AND "
                       "field_path = 'Value'"), {"u": a1})
    with engine.connect() as c:
        res, counts = T.analyse(c, case, {})
    by = {r["records"][0]["record_uid"]: r for r in res}
    assert set(by) == {w1, w2, w3, a1}
    assert by[w1]["kind"] == "typed_not_in_extraction" and by[w1]["measures"]["term_kinds"] == ["financial_name"]
    assert by[w1]["sensitive"] is True and by[w1]["measures"]["value_masked"] == "••••"
    assert by[w2]["measures"]["term_kinds"] == ["account_ending"]
    assert by[w3]["kind"] == "typed_and_present" and by[w3]["measures"]["elsewhere_records"] == 1
    assert [x["record_uid"] for x in by[w3]["records"] if x["role"] == "elsewhere"] == [evs[0]["record_uid"]]
    assert by[a1]["period_start"] == at(2023, 1, 6, 9) and by[a1]["measures"]["autofill_key"] == "name"
    assert any(d["code"] == "no_time_recorded" for d in by[w1]["directions"]["undercuts"])
    blob = json.dumps(res, default=str)
    for word in ("quillon", "4821", "velmora", "darrowby"):
        assert word not in blob.lower()  # 10.8.3: no typed value or matched term in a result
    assert counts["typed_not_in_extraction"] == 3 and counts["typed_and_present"] == 1


@needs_template
def test_intent_times_and_common_terms(engine):
    """12.8 tests 1 and 2: a page's time is its last visit only (with the visit count); an undated search has no
    period; a term matching 3 or more records is a common term; an address-only match says so."""
    with engine.begin() as c:
        case = make_case(c)
        ext, _ = phone(c, case, contacts={"phone:+12025550199": "Velmora Ashgrove"}, events=[])
        p = record(c, case, ext, 600, "VisitedPage", texts=[("Title", "ashgrove ledger"), ("Url", "https://x.example/")],
                   fields=[("VisitCount", "Int32", "5")], times=[("LastVisited", at(2023, 2, 1, 12))])
        s = record(c, case, ext, 601, "SearchedItem", texts=[("Value", "where is ashgrove")])
        commons = [record(c, case, ext, 610 + i, "VisitedPage", texts=[("Title", "velmora shop %d" % i)])
                   for i in range(3)]
        a = record(c, case, ext, 620, "VisitedPage", texts=[("Title", "nothing here"),
                                                            ("Url", "https://x.example/people/ashgrove")])
    with engine.connect() as c:
        res, counts = I.analyse(c, case, {})
    by = {r["records"][0]["record_uid"]: r for r in res}
    assert set(by) == {p, s, a, *commons}
    page = by[p]
    assert page["measures"]["time_meaning"] == "last_visit_only" and page["measures"]["visit_count"] == "5"
    assert any(d["code"] == "last_visit_only" and "5 visits" in d["detail"] for d in page["directions"]["undercuts"])
    assert by[s]["period_start"] is None and by[s]["measures"]["time_meaning"] == "not_recorded"
    assert all(by[u]["strength"] == "common_term" for u in commons)
    assert by[p]["strength"] == "common_term"  # ashgrove: page, search and address, 3 records
    assert by[a]["measures"]["matched_in"] == ["address"]
    assert any(d["code"] == "address_only" for d in by[a]["directions"]["undercuts"])
    assert counts["distinct_terms"] == 2
