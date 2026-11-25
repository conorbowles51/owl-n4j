"""Ask the phones a question (lx-phoneask A-D): rules, not the model, decide what an answer shows.

A statement with no citation, a citation the model was not shown, or a quotation its records do not hold is not
shown, and the answer says how many were left out. A phone whose Outside services decision is "not allowed" is not
read and is named. Next steps come from the answer's own data. Earlier questions are kept, counted and paged."""
import json
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from postgres.base import Base
from postgres.models.phone_ask import PhoneAsk
from services.phone import ask as A
from services.phone import ask_runs as R

CASE = "11111111-2222-3333-4444-555555555555"
P1, P2, P3 = ("aaaaaaaa-0000-0000-0000-00000000000%d" % i for i in (1, 2, 3))
M1, M2, M3, M4 = ("bbbbbbbb-0000-0000-0000-00000000000%d" % i for i in (1, 2, 3, 4))
AT = datetime(2024, 3, 12, 10, 20, tzinfo=timezone.utc)

SOURCES = [
    {"title": "Phone 2 · SMS · Dorian", "kind": "search", "records": [M1, M2],
     "text": "12 Mar 2024 10:20 AM | Phone 2 | Marisol Teague -> Dorian | the checks are in the drawer [rec://%s]\n"
             "12 Mar 2024 10:21 AM | Phone 2 | Dorian -> Marisol Teague | got them [rec://%s]" % (M1, M2)},
    {"title": "Phone 3 · Email", "kind": "search", "records": [M3],
     "text": "22 Mar 2024 | Phone 3 | Dorian Pell -> Teague Practice Services | transfer confirmation [rec://%s]" % M3},
]
FACTS = {M1: {"extraction_id": P2, "model_type": "InstantMessage", "at": AT, "deleted": False, "parent": "c1", "title": ""},
         M2: {"extraction_id": P2, "model_type": "InstantMessage", "at": AT + timedelta(minutes=1), "deleted": False,
              "parent": "c1", "title": ""},
         M3: {"extraction_id": P3, "model_type": "Email", "at": AT + timedelta(days=10), "deleted": False,
              "parent": None, "title": ""}}
PHONES = [{"extraction_id": P1, "label": "Phone 1", "owner": "Priya Halloran", "allowed": None},
          {"extraction_id": P2, "label": "Phone 2", "owner": "Marisol Teague", "allowed": None},
          {"extraction_id": P3, "label": "Phone 3", "owner": "Dorian Pell", "allowed": None}]


class Conn:
    """Answers the one query next_steps makes (thread sizes)."""

    def __init__(self, sizes=None):
        self.sizes = sizes or {}

    def execute(self, *_a, **_k):
        return SimpleNamespace(fetchall=lambda: list(self.sizes.items()))


def _model(answer):
    def call(prompt):
        call.prompts.append(prompt)
        return json.dumps(answer)
    call.prompts, call.model, call.usage = [], "test/model", []
    return call


def test_a_statement_without_a_citation_is_not_shown_and_is_counted():
    parsed = {"statements": [
        {"text": "Marisol Teague told Dorian the checks were in the drawer.", "cites": ["rec://" + M1]},
        {"text": "Dorian Pell moved the money offshore.", "cites": []},
        {"text": "Dorian Pell banked it.", "cites": ["rec://cccccccc-0000-0000-0000-000000000009"]},
    ]}
    kept, dropped = A.check(parsed, SOURCES, FACTS)
    assert [k["text"] for k in kept] == ["Marisol Teague told Dorian the checks were in the drawer."]
    assert dropped == {"no_citation": 2}
    assert "2 statements cited no record" in A.dropped_sentence(dropped)


def test_a_quote_its_records_do_not_hold_is_not_shown():
    parsed = {"statements": [
        {"text": 'She wrote “the checks are in the drawer” and he replied "got them".', "cites": [M1, "rec://" + M2]},
        {"text": 'She wrote "the money is in the drawer".', "cites": ["rec://" + M1]},
    ]}
    kept, dropped = A.check(parsed, SOURCES, FACTS)
    assert len(kept) == 1 and kept[0]["cites"] == [M1, M2]
    assert dropped == {"quote_not_in_record": 1}


def test_a_citation_written_inside_the_text_counts_and_is_taken_out_of_the_text():
    parsed = {"statements": [{"text": "Dorian emailed a transfer confirmation [rec://%s]." % M3, "cites": []}]}
    kept, _ = A.check(parsed, SOURCES, FACTS)
    assert kept[0]["cites"] == [M3] and "rec://" not in kept[0]["text"]


def test_a_phone_not_allowed_outside_is_not_read_and_is_named():
    phones = [dict(PHONES[0], allowed=False), dict(PHONES[1]), dict(PHONES[2], allowed=True)]
    seen = {}

    def gather(conn, case_id, question, read, **_k):
        seen["read"] = [p["extraction_id"] for p in read]
        return {"sources": SOURCES, "facts": FACTS, "understood": {}, "notes": [], "found": 2, "more_found": 0,
                "more_in_time": 0, "ranking_model": None, "seconds": {}}
    model = _model({"statements": [{"text": "Dorian emailed a transfer confirmation.", "cites": [M3],
                                    "people": ["Dorian Pell"]}]})
    with mock.patch.object(A, "phones_in_scope", return_value=phones), \
            mock.patch.object(A, "searched_counts", return_value={"InstantMessage": 3}), \
            mock.patch.object(A, "gather", side_effect=gather):
        out = A.ask(Conn(), CASE, "Did anyone move the money?", model_call=model,
                    elsewhere=lambda *a: {"rows": [], "note": None})
    assert seen["read"] == [P2, P3]
    assert out["left_out"] == [P1]
    assert any("Phone 1 was left out" in n for n in out["notes"])
    assert any(s["kind"] == "permission" for s in out["steps"])
    assert "Priya Halloran" not in model.prompts[0]  # the phone left out is not named to the model either


def test_no_phone_allowed_asks_no_model():
    model = _model({})
    with mock.patch.object(A, "phones_in_scope", return_value=[dict(PHONES[0], allowed=False)]), \
            mock.patch.object(A, "searched_counts", return_value={}):
        out = A.ask(Conn(), CASE, "Anything?", model_call=model)
    assert model.prompts == [] and out["statements"] == [] and "may be read by AI" in out["error"]


def test_the_answer_cites_labels_used_records_and_not_found():
    model = _model({"statements": [{"text": 'Marisol Teague told Dorian "the checks are in the drawer".',
                                    "cites": [M1, M2], "people": ["Marisol Teague", "Dorian Pell"],
                                    "date_from": "2024-03-12"}],
                    "not_found": [{"asked": "check numbers", "text": "No message names a check number."}]})
    g = {"sources": SOURCES, "facts": FACTS, "understood": {}, "notes": [], "found": 2, "more_found": 0,
         "more_in_time": 0, "ranking_model": None, "seconds": {}}
    with mock.patch.object(A, "phones_in_scope", return_value=PHONES), \
            mock.patch.object(A, "searched_counts", return_value={"InstantMessage": 244, "Call": 31}), \
            mock.patch.object(A, "gather", return_value=g):
        out = A.ask(Conn({"c1": 14}), CASE, "Did anyone talk about the refund checks?", model_call=model,
                    elsewhere=lambda *a: {"rows": None, "note": "not checked"})
    st = out["statements"][0]
    assert [c["label"] for c in st["cite_labels"]] == ["Phone 2 · Message 12 Mar 2024 10:20 AM UTC",
                                                       "Phone 2 · Message 12 Mar 2024 10:21 AM UTC"]
    assert out["searched"] == "Searched 244 messages and 31 calls"
    assert [(r["record"], r["cited"]) for r in out["records_used"]] == [(M1, True), (M2, True), (M3, False)]
    assert out["not_found"] == [{"asked": "check numbers", "text": "No message names a check number."}]
    kinds = [s["kind"] for s in out["steps"]]
    # Phone 3 is Dorian Pell's and holds none of it; two people to test; the thread has 14 messages, 2 cited
    assert kinds[:4] == ["missing_on_phone", "corroborate", "thread", "not_found"]
    assert out["steps"][0]["action"]["extraction_id"] == P3
    assert "has 14" in out["steps"][2]["why"]
    assert out["label"].startswith("Written by AI")


def test_a_model_failure_shows_no_answer_and_says_so():
    def broken(prompt):
        raise TimeoutError("slow")
    broken.usage = []
    g = {"sources": SOURCES, "facts": FACTS, "understood": {}, "notes": [], "found": 2, "more_found": 0,
         "more_in_time": 0, "ranking_model": None, "seconds": {}}
    with mock.patch.object(A, "phones_in_scope", return_value=PHONES), \
            mock.patch.object(A, "searched_counts", return_value={}), \
            mock.patch.object(A, "gather", return_value=g):
        out = A.ask(Conn(), CASE, "Anything?", model_call=broken)
    assert out["statements"] == [] and "did not answer (TimeoutError)" in out["error"]


def test_the_prompt_carries_the_writing_standard():
    from services import writing_standard
    p = A.build_prompt("Q?", PHONES, SOURCES)
    assert writing_standard.MARKER in p and "rec://" + M1 in p


# ---- earlier questions -------------------------------------------------------------------------------------------
@pytest.fixture()
def db():
    with tempfile.TemporaryDirectory() as d:
        engine = create_engine(f"sqlite+pysqlite:///{Path(d) / 'a.db'}", future=True)
        Base.metadata.create_all(engine, tables=[PhoneAsk.__table__])
        with Session(engine) as s:
            yield s
        engine.dispose()


USER = SimpleNamespace(id=uuid.UUID("22222222-0000-0000-0000-000000000001"), name="Test Person", email="t@example.com")


def test_questions_are_kept_listed_newest_first_and_paged(db):
    case = uuid.UUID(CASE)
    for i in range(3):
        a = R.start(db, case_id=case, question="Question %d" % i, phones=None, user=None, run=False)
        row = db.get(PhoneAsk, uuid.UUID(a["id"]))
        row.created_at = datetime.now(timezone.utc) - timedelta(minutes=10 - i)
        row.status = "done"
        row.answer = {"statements": [{"text": "x"}] * i}
    db.commit()
    page = R.earlier(db, case, limit=2)
    assert page["total"] == 3 and page["shown"] == 2 and page["next_offset"] == 2
    assert [x["question"] for x in page["items"]] == ["Question 2", "Question 1"]
    assert page["items"][0]["statements"] == 2
    assert [x["question"] for x in R.earlier(db, case, offset=2)["items"]] == ["Question 0"]
    assert R.earlier(db, uuid.uuid4())["total"] == 0


def test_one_running_question_per_person_and_a_stopped_one_says_why(db):
    case = uuid.UUID(CASE)
    a = R.start(db, case_id=case, question="First", phones=None, user=USER, run=False)
    with pytest.raises(R.AskError) as e:
        R.start(db, case_id=case, question="Second", phones=None, user=USER, run=False)
    assert e.value.status == 409
    row = db.get(PhoneAsk, uuid.UUID(a["id"]))
    row.created_at = datetime.now(timezone.utc) - timedelta(seconds=R.STALE_S + 5)
    db.commit()
    v = R.read(db, case, a["id"] if isinstance(a["id"], uuid.UUID) else uuid.UUID(a["id"]))
    assert v["status"] == "failed" and "stopped" in v["error"]
    R.start(db, case_id=case, question="Second", phones=None, user=USER, run=False)  # a stopped one does not block
    assert R.read(db, uuid.uuid4(), uuid.UUID(a["id"])) is None  # another case's id reads nothing


def test_an_empty_or_long_question_is_refused(db):
    with pytest.raises(R.AskError):
        R.start(db, case_id=uuid.UUID(CASE), question="  ", phones=None, user=None, run=False)
    with pytest.raises(R.AskError):
        R.start(db, case_id=uuid.UUID(CASE), question="x" * (R.MAX_QUESTION + 1), phones=None, user=None, run=False)


def test_a_long_conversation_reaches_the_model_whole_and_a_unit_over_budget_is_counted():
    """Halloran case, 25 Nov: "delete the Quarrow emails" sat at character 2,600 of its conversation, and a cut at
    2,400 characters hid it, so the answer said nobody asked for emails to be deleted."""
    from services.case_search import service as S, units
    filler = "".join("1 Jan 2024 | Phone 3 | ok [rec://%s]\n" % ("dddddddd-0000-0000-0000-%012d" % i) for i in range(70))
    long_text = filler + "26 Apr 2024 | Phone 3 | delete the Quarrow emails [rec://%s]" % M4
    cands = [{"area": "phone_text", "title": "Phone 3 · WhatsApp", "text": long_text, "grade": "strong"},
             {"area": "phone_text", "title": "Phone 2", "text": SOURCES[0]["text"], "grade": "weak"}]
    ranked = {"understood": {"terms": [], "expansions": [], "windows": []}, "candidates": cands, "notes": [],
              "ranking": {}, "seconds": {}}

    def facts(conn, case_id, uids):
        return {u: {"extraction_id": P3, "model_type": "InstantMessage", "at": AT, "deleted": False, "parent": None,
                    "title": ""} for u in uids}
    with mock.patch.object(S, "ranked", return_value=ranked), \
            mock.patch.object(units, "build", side_effect=lambda conn, case_id, c, terms: c), \
            mock.patch.object(A, "record_facts", side_effect=facts):
        got = A.gather(Conn(), CASE, "Did anyone ask for emails to be deleted?", PHONES)
        assert len(got["sources"][0]["text"]) > 2400
        assert "delete the Quarrow emails" in got["sources"][0]["text"] and M4 in got["sources"][0]["records"]
        with mock.patch.object(A, "PROMPT_CHARS", len(long_text) + 10):
            small = A.gather(Conn(), CASE, "Did anyone ask for emails to be deleted?", PHONES)
    assert len(small["sources"]) == 1 and small["more_found"] == 1  # left out whole, and counted


def test_what_the_rest_of_the_case_says_comes_from_the_elsewhere_service_with_its_relations():
    from services.elsewhere import service as ES, subject as SU
    got = {"parts": [
        {"source": "financial", "label": "Financial", "state": "done", "searched": "statement rows 1 to 30 Mar",
         "items": [{"relation": "agrees", "relation_label": "Agrees", "text": "Check 2204 arrives", "reason": "same amount",
                    "citation": {"kind": "transaction", "id": "t1", "href": "txn://t1", "label": "pell-2024-03.pdf p.1"}}]},
        {"source": "phones", "label": "Phones", "state": "done", "searched": "other phones",
         "items": [{"relation": "missing_here", "relation_label": "Missing here", "text": "Phone 1 was recording",
                    "reason": "", "citation": {"kind": "phone_record", "id": M4, "href": "rec://" + M4, "phone": "Phone 1",
                                               "label": "Phone 1 · Message"}}]},
        {"source": "timeline", "label": "Timeline", "state": "failed", "searched": "", "items": []}],
        "counts": {"agrees": 1}}
    seen = {}

    def subject(conn, case_id, payload):
        seen.update(payload)
        return object()
    st = {"text": "Dorian banked the checks.", "cites": [M1], "people": ["Dorian Pell"], "date_from": "2024-03-12",
          "date_to": "2024-03-12"}
    with mock.patch.object(SU, "from_statement", side_effect=subject), mock.patch.object(ES, "run", return_value=got):
        out = A.elsewhere_rows(Conn(), CASE, st, PHONES, FACTS)
    assert seen["record_uids"] == [M1] and seen["people"] == [{"name": "Dorian Pell"}]
    assert seen["period"] == {"start": "2024-03-12", "end": "2024-03-12"}
    assert [(r["source"], r["relation"], r["cite"]) for r in out["rows"]] == [
        ("Financial", "agrees", "txn://t1"), ("Phone 1", "missing_here", "rec://" + M4)]
    assert "Timeline" in out["note"]  # a failed part is said, never left out silently
    with mock.patch.object(SU, "from_statement", side_effect=SU.BadSubject("x")):
        bad = A.elsewhere_rows(Conn(), CASE, st, PHONES, FACTS)
    assert bad["rows"] is None and "could not be checked" in bad["note"]
