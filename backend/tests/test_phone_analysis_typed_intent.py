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
    assert T.VERSION == "7.3" and I.VERSION == "9.3"


# ---- 05 10.3 step 1, the rest of the vocabulary: case entities, ledger amounts, places (cb-vocab) -------------------

def test_nothing_is_left_out_of_the_vocabulary():
    """With case entities, ledger amounts and places read, no kind of 10.3 step 1 is missing; each new kind has its
    plain words for the screens."""
    assert V.NOT_INCLUDED == ()
    for k in ("case_entity", "ledger_amount", "place"):
        assert k in V.KINDS and V.KIND_WORDS[k]
    assert V.not_included({"not_included": []}) == [] and V.vocabulary_partial_detail({}) is None


def test_amount_forms():
    """19.S10-e: the dot and comma conventions, grouped and plain; a whole amount also without decimals only when
    grouped; at least 4 digits; a currency without minor units has no decimals."""
    f = V.amount_forms(123456, "USD")
    assert f == {"dot": {"1234.56", "1,234.56"}, "comma": {"1234,56", "1.234,56"}}
    assert V.amount_forms(150000, "EUR") == {"dot": {"1500.00", "1,500.00", "1,500"},
                                             "comma": {"1500,00", "1.500,00", "1.500"}}
    assert V.amount_forms(-150000, "EUR") == V.amount_forms(150000, "EUR")
    assert V.amount_forms(1500, "JPY") == {"dot": {"1,500"}, "comma": {"1.500"}}
    assert V.amount_forms(999, "USD") == {"dot": set(), "comma": set()}  # 9.99: 3 digits
    assert "1500" not in V.amount_forms(150000, "USD")["dot"]  # the plain whole form matched years and page numbers


def test_amounts_match_as_a_whole_number():
    vocab = dict(VOCAB, amount_forms=V.amount_forms(123456, "USD")["dot"])
    assert V.matches("sent 1,234.56 today", vocab) == [("ledger_amount", "1 234 56")]
    assert V.matches("$1234.56.", vocab) == [("ledger_amount", "1234 56")]
    for other in ("11234.56", "1,234.567", "123456", "1234,56", "1.234,56", "21,234.56"):
        assert V.matches(other, vocab) == [], other
    assert V.matches("1234,56", dict(VOCAB, amount_forms=V.amount_forms(123456, "USD")["comma"])) == [
        ("ledger_amount", "1234 56")]


def test_case_entities_and_places_from_the_graph(monkeypatch):
    """Case entity names and aliases by token, as contact names; graph places and entity addresses as phrases, whole
    and by comma-separated part; an unreadable graph is stated, never silent."""
    rows = [["Person", "Brannock Ostravel", ["Branny Ostravel"], []],
            ["Organization", "Quorvane Holdings", None, ["14 Tidewell Lane, Marrowfield"]],
            ["Location", "Kelderwick Quay", ["Old Kelderwick"], ["Kelderwick Quay, Port Ansel"]]]
    monkeypatch.setattr(V, "_graph_rows", lambda case_id: rows)
    got, note = V._read_graph("c1")
    assert got == rows and note is None
    places = {}
    for label, name, aliases, addresses in got:
        for v in ([name] + (aliases or []) if label in V.PLACE_LABELS else []) + addresses:
            V._add_place(places, v)
    vocab = dict(VOCAB, names={"brannock": {"case_entity"}, "branny": {"case_entity"}, "quorvane": {"case_entity"}},
                 places=places)
    assert V.matches("Branny", vocab) == [("case_entity", "branny")]
    assert V.matches("ferry to kelderwick quay at 5", vocab) == [("place", "kelderwick quay")]
    assert V.matches("kelderwick", vocab) == []  # a phrase matches whole, not by one of its words
    assert V.matches("Marrowfield", vocab) == [("place", "marrowfield")]  # a comma-separated part of an address
    assert V.matches("14 tidewell lane", vocab) == [("place", "14 tidewell lane")]
    monkeypatch.setattr(V, "_graph_rows", lambda case_id: (_ for _ in ()).throw(RuntimeError("down")))
    got, note = V._read_graph("c1")
    assert got == [] and "could not be read" in note
    monkeypatch.setattr(V, "_graph_rows", lambda case_id: rows * (V.GRAPH_LIMIT // 3 + 1))
    got, note = V._read_graph("c1")
    assert len(got) == V.GRAPH_LIMIT and "beyond the first" in note


def test_graph_query_is_one_bounded_case_scoped_read_of_active_entities():
    """One query per build, case-scoped on every label, limited, and only active nodes (not in the recycle bin, not
    system nodes): a renamed entity gives its current name and a merged one only the entity it was merged into."""
    q = V._graph_query()
    assert q.count("{case_id: $case_id}") == len(V.ENTITY_LABELS) and "LIMIT $limit" in q
    assert "RecycleBin" in q and "system_node" in q and "n.name" in q and "n.aliases" in q
    assert "Person" in V.ENTITY_LABELS and "Organization" in V.ENTITY_LABELS and "Location" in V.PLACE_LABELS
    assert not {"PhoneIdentity", "FinancialTransaction", "Document"} & set(V.ENTITY_LABELS)


def test_phone_convention():
    """The forms follow the phone's region; with none, the ledger's currencies; with neither, both."""
    class C:
        def __init__(self, keys):
            self.keys = keys

        def execute(self, *a, **k):
            return [(x,) for x in self.keys]
    import services.phone.mappings.apply as A
    orig = A.default_region
    try:
        A.default_region = lambda conn, e: ("US", "assumed_default")
        assert V.phone_convention(C(["phone:+34600000000"]), "e")[0] == ("comma",)
        assert V.phone_convention(C(["phone:+12025550147"]), "e")[0] == ("dot",)
        assert V.phone_convention(C([]), "e", ["MXN"])[0] == ("dot",)
        assert V.phone_convention(C([]), "e", ["EUR"])[0] == ("comma", "dot")
        assert V.phone_convention(C([]), "e")[0] == ("comma", "dot")
        A.default_region = lambda conn, e: ("DE", "decided")
        assert V.phone_convention(C(["phone:+12025550147"]), "e") == (("comma",), "region DE (decided)")
    finally:
        A.default_region = orig


@needs_template
def test_case_entities_amounts_and_places_reach_typed_words_and_intent(engine, monkeypatch):
    """A learned word equal to a case entity's alias, an autofill value equal to a ledger amount in the phone's forms
    and a search naming a case place are hits of kinds case_entity, ledger_amount and place; the old kinds' hits are
    unchanged; the values never appear in a result; nothing is said to be left out; a superseded ledger row's amount
    is not vocabulary (the corrected value is the one read)."""
    from tests.test_phone_analysis_money_signals import Ledger
    monkeypatch.setattr(V, "_graph_rows", lambda case_id: [
        ["Person", "Brannock Ostravel", ["Branny"], []], ["Location", "Kelderwick Quay", [], []]])
    with engine.begin() as c:
        case = make_case(c)
        ext, _ = phone(c, case, contacts={"phone:+12025550199": "Velmora Ashgrove"},
                       events=[{"instant": at(2023, 1, 5, 10), "direction": "outgoing", "body": "see velmora soon"}])
        led = Ledger(c, case)
        acct = led.account("Synthetic Bank", "XX-9917")
        led.txn(acct, 123456, at(2023, 1, 2, 0).date())
        old = led.txn(acct, 777700, at(2023, 1, 3, 0).date())
        new = led.txn(acct, 777800, at(2023, 1, 3, 0).date())
        led.supersede(old, new)
        w1 = record(c, case, ext, 800, "DictionaryWord", texts=[("Word", "branny")])
        w2 = record(c, case, ext, 801, "DictionaryWord", texts=[("Word", "velmora")])
        a1 = record(c, case, ext, 802, "Autofill", texts=[("Key", "amount"), ("Value", "1,234.56")],
                    fields=[("Key", "String", "amount")], times=[("TimeStamp", at(2023, 1, 6, 9))])
        a2 = record(c, case, ext, 803, "Autofill", texts=[("Key", "amount"), ("Value", "7,777.00")],
                    fields=[("Key", "String", "amount")])
        s = record(c, case, ext, 804, "SearchedItem", texts=[("Value", "ferry to Kelderwick Quay")])
        for u in (w1, w2):
            _sensitive(c, u)
        for u in (a1, a2):
            c.execute(text("UPDATE phone_texts SET is_sensitive = true WHERE record_uid = CAST(:u AS uuid) AND "
                           "field_path = 'Value'"), {"u": u})
    with engine.connect() as c:
        res, counts = T.analyse(c, case, {})
        ires, icounts = I.analyse(c, case, {})
    by = {r["records"][0]["record_uid"]: r for r in res}
    assert set(by) == {w1, w2, a1}  # a2: the superseded amount is not vocabulary
    assert by[w1]["measures"]["term_kinds"] == ["case_entity"] and by[w1]["kind"] == "typed_not_in_extraction"
    assert by[a1]["measures"]["term_kinds"] == ["ledger_amount"]
    assert any(d["code"] == "amount_form" for d in by[a1]["directions"]["undercuts"])
    assert by[w2]["measures"]["term_kinds"] == ["contact_name"]
    assert counts["hits_case_entity"] == 1 and counts["hits_ledger_amount"] == 1 and counts["hits_contact_name"] == 1
    assert counts["not_elsewhere_case_entity"] == 1 and counts["vocabulary_not_included"] == []
    assert not any(d["code"] == "vocabulary_partial" for r in res + ires for d in r["directions"]["undercuts"])
    assert [r["records"][0]["record_uid"] for r in ires] == [s]
    assert ires[0]["measures"]["term_kinds"] == ["place"] and icounts["hits_place"] == 1
    blob = json.dumps(res, default=str).lower()
    for word in ("branny", "1,234.56", "1 234 56", "velmora"):
        assert word not in blob  # 10.8.3
    monkeypatch.setattr(V, "_graph_rows", lambda case_id: (_ for _ in ()).throw(RuntimeError("down")))
    with engine.connect() as c:
        res2, counts2 = T.analyse(c, case, {})
    assert {r["records"][0]["record_uid"] for r in res2} == {w2, a1}
    assert counts2["vocabulary_not_included"] and all(
        any(d["code"] == "vocabulary_partial" and "could not be read" in d["detail"] for d in r["directions"]["undercuts"])
        for r in res2)
