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


def test_investigator_terms_match_whole_words_in_order():
    """19.S10-c: an investigator term matches its folded words as whole words, in order; nothing else changes."""
    vocab = dict(VOCAB, terms=["cash drop", "harbour"])
    assert V.matches("Cash-drop at 5", vocab) == [("investigator_term", "cash drop")]
    assert V.matches("cashew drop", vocab) == []
    assert V.matches("drop cash", vocab) == []
    assert V.matches("HARBOUR", vocab) == [("investigator_term", "harbour")]
    assert V.matches("Zorvath harbour", vocab) == [("contact_name", "zorvath"), ("investigator_term", "harbour")]
    # with no investigator terms the matches are what they were
    for value in ("Zorvath!", "acct 99994821", "5550147", "cash drop"):
        assert V.matches(value, dict(VOCAB, terms=[])) == V.matches(value, VOCAB)
    assert "investigator-added terms" not in V.NOT_INCLUDED and "investigator_term" in V.KINDS


@needs_template
def test_investigator_terms_from_case_terms_and_keyword_lists_reach_typed_words_and_intent(engine):
    """05 10.3 step 1 and 12.3 step 1: the case's case terms and keyword-list terms are vocabulary of kind
    investigator_term; a run with none gives the same hits as before, and adding one adds its hits and a new
    input revision (a kept result stays tied to the run it came from)."""
    from sqlalchemy.orm import Session

    from postgres.models.user import User
    from services.pattern_of_life import key_dates
    from services.phone_analysis import framework as FW
    from services.search import keyword_lists as K
    with engine.begin() as c:
        case = make_case(c)
        ext, _ = phone(c, case, contacts={"phone:+12025550199": "Velmora Ashgrove"},
                       events=[{"instant": at(2023, 1, 5, 10), "direction": "outgoing", "body": "see velmora soon"}])
        w = record(c, case, ext, 700, "DictionaryWord", texts=[("Word", "brimstead")])
        w2 = record(c, case, ext, 701, "DictionaryWord", texts=[("Word", "velmora")])
        s = record(c, case, ext, 702, "SearchedItem", texts=[("Value", "night ferry to brimstead")])
        for u in (w, w2):
            _sensitive(c, u)
    with engine.connect() as c:
        before_t, _ = T.analyse(c, case, {})
        before_i, _ = I.analyse(c, case, {})
        rev0 = FW.sha256(FW.input_manifest(c, case, T))
    assert {r["records"][0]["record_uid"] for r in before_t} == {w2}
    assert before_i == []
    with Session(engine) as db:
        uid, email = db.execute(text("SELECT u.id, u.email FROM cases k JOIN users u ON u.id = k.owner_user_id "
                                     "WHERE k.id = :c"), {"c": case}).one()
        user = User(id=uid, email=email, name="synthetic")
        key_dates.create(db, case, user, kind="term", label="Place", term="Brimstead")
        K.create(db, case, user, name="Travel", terms=["night ferry"])
    with engine.connect() as c:
        after_t, counts = T.analyse(c, case, {})
        after_i, _ = I.analyse(c, case, {})
        rev1 = FW.sha256(FW.input_manifest(c, case, T))
    by = {r["records"][0]["record_uid"]: r for r in after_t}
    assert set(by) == {w, w2}
    assert by[w]["measures"]["term_kinds"] == ["investigator_term"]
    assert by[w]["kind"] == "typed_and_present" and by[w]["measures"]["elsewhere_records"] == 1  # the search holds it
    assert "brimstead" not in json.dumps(after_t, default=str).lower()  # 10.8.3: no matched term in a result
    assert counts["vocabulary_terms"] == 2
    assert [r["records"][0]["record_uid"] for r in after_i] == [s]
    assert after_i[0]["measures"]["term_kinds"] == ["investigator_term"] and after_i[0]["measures"]["terms_matched"] == 2
    assert rev0 != rev1
    assert T.VERSION == "7.2" and I.VERSION == "9.2"
