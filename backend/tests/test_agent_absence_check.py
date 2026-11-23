"""An answer saying none of a kind was found, when a read in the same run returned that kind (absence_check)."""
from pathlib import Path

from services.agent import absence_check as A

EMAIL = "819b84ac-e4c7-54ce-b710-643bbb489dc7"
MSG = "8c8db0a6-9d3b-5e97-9297-bd63ba2f7f25"


def _read(kinds, items, name="phone_messages"):
    return {"name": name, "status": "success",
            "arguments": {"mode": "between", "kinds": kinds, "start": "2024-03-15", "end": "2024-06-07",
                          "people": ["email:penn.tools@example.com", "email:travis.kell@example.net"]},
            "result_preview": {"total_matching": len(items), "items": items}}


def _item(uid, kind, text):
    return {"record_uid": uid, "rec": "rec://" + uid, "kind": kind, "time": "Sat, May 4, 2024, 2:20:00 PM EDT",
            "from": "Travis Kell (travis.kell@example.net)", "to": ["Gary P (penn.tools@example.com)"], "subject": text}


# demo P4 run 4 (22 Nov 2026, followups m112223403612703): the read returned the price-list email, the answer said none
TRACE = [_read(["email"], [_item(EMAIL, "email", "price list")]),
         _read([], [_item(MSG, "message", "are we still on for later")])]
ANSWER = ("In the seven days before each check, the only recorded contact between Gary Penn and Travis Kell sits on "
          "Travis Kell's phone. No emails appear in those windows. Every record below is mapped automatically.\n\n"
          f"- [21 Mar 19:12, Travis to Gary](rec://{MSG})")


def test_an_answer_saying_no_emails_when_the_run_read_one_it_does_not_cite_is_caught_with_the_record():
    found = A.contradictions(ANSWER, TRACE)
    assert [(f["sentence"], f["kinds"], [r["record_uid"] for r in f["records"]]) for f in found] == [
        ("No emails appear in those windows.", ["email"], [EMAIL])]
    request = A.repair_request(found)
    assert f"rec://{EMAIL}" in request and '"price list"' in request and "Sat, May 4, 2024" in request
    assert A.check_lines(found) == [f'The answer says "No emails appear in those windows.", but this run read email '
                                    f'records it does not cite: rec://{EMAIL}.']


def test_a_cited_record_a_read_of_everything_and_a_part_of_a_record_are_not_contradictions():
    # the answer quotes the email: "no emails" is about something else
    assert A.contradictions(ANSWER + f"\n- [4 May, price list](rec://{EMAIL})", TRACE) == []
    # a read of every kind holds other people's records (demo: contact "Mateo" on a number not tied to Mateo Ruiz)
    assert A.contradictions("There is no call or message between Mateo Ruiz and Desmond Okafor.", TRACE) == []
    # a source check line quoting a sentence, and words that name part of a record
    for text in ("Sentence gives no message text, sender, or timestamp.", "So there is no message window to quote.",
                 "12 files have no text read yet.", "No message states the landlord's name.",
                 "No email-reconciliation was run.", "x.\n\n**Source check**: no emails appear in this check."):
        assert A.absences(text) == [], text
    assert [k for _, k in A.absences("There were no calls, emails or messages.")] == [{"call", "email", "message"}]


def test_a_rewrite_is_taken_only_when_it_keeps_the_citations():
    assert A.keeps_citations(ANSWER, ANSWER + f" [price list](rec://{EMAIL})")
    assert not A.keeps_citations(ANSWER, "No contact was found.")


def test_the_writer_runs_the_check_before_the_answer_is_shown():
    source = (Path(__file__).resolve().parents[1] / "services" / "agent" / "durable_execution.py").read_text()
    assert "absence_check.contradictions(answer, trace)" in source
    assert "absence_check.repair_request(contradicted)" in source
