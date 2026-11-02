"""Email threading by header where headers exist (02 decision 45; brief 07 additions). Synthetic phones only."""
from __future__ import annotations

import pytest
from sqlalchemy import text

from services.phone import registry, sweep
from services.phone.comms import header_thread_root
from tests.phone_pg import fld, fresh_engine, make_case, make_extraction, model, needs_template
from tests.test_phone_mappings import _shipped, hooks, stamp  # noqa: F401 (fixture)


def test_the_root_is_the_first_reference_then_the_reply_then_the_email_itself():
    assert header_thread_root({"MessageId": "<A@x.test>"}) == "a@x.test"
    assert header_thread_root({"MessageId": "<b@x.test>", "InReplyTo": "<A@x.test>"}) == "a@x.test"
    assert header_thread_root({"MessageId": "<c@x.test>", "InReplyTo": "<b@x.test>",
                               "References": "<a@x.test>\n <b@x.test>"}) == "a@x.test"
    assert header_thread_root({"MessageId": "  ", "References": None}) is None
    assert header_thread_root({}) is None


def _email(subject, when, **headers):
    fields = [fld("TimeStamp", ("TimeStamp", when)), fld("Subject", ("String", subject)),
              fld("Folder", ("String", "Inbox"))]
    fields += [fld(k, ("String", v)) for k, v in headers.items()]
    return model("Email", fields)


@needs_template
def test_a_conversation_threads_by_its_headers_and_a_same_subject_stranger_does_not_join_it(hooks):
    _shipped(hooks, ["type"])
    with fresh_engine() as engine:
        with engine.begin() as c:
            registry.apply_seed(c)
            case = make_case(c)
            recs = [
                _email("Synthetic plan", "2023-03-14T15:00:00Z", MessageId="<a@x.test>"),
                _email("Re: Synthetic plan", "2023-03-14T16:00:00Z", MessageId="<b@x.test>", InReplyTo="<a@x.test>"),
                _email("Synthetic plan, changed", "2023-03-14T17:00:00Z", MessageId="<c@x.test>",
                       InReplyTo="<b@x.test>", References="<a@x.test> <b@x.test>"),
                _email("Synthetic plan", "2023-03-15T09:00:00Z", MessageId="<z@x.test>"),  # same subject, own thread
                _email("No headers here", "2023-03-15T10:00:00Z"),
            ]
            ext = make_extraction(c, case, [(i, None, i, r) for i, r in enumerate(recs)],
                                  timestamps=[stamp(i, "0.0", "TimeStamp", "Email") for i in range(len(recs))])
        assert sweep.interpret_one(engine, ext)["status"] == "done"
        with engine.connect() as c:
            keys = [r[0] for r in c.execute(text(
                "SELECT thread_key FROM phone_comm_events WHERE extraction_id = :e ORDER BY sort_instant, document_index, "
                "ordinal"), {"e": ext})]  # every email shares one instant here: report order breaks the tie
        assert len(keys) == 5
        assert keys[0] == keys[1] == keys[2] and keys[0].startswith("hdr:")
        assert keys[3] != keys[0] and keys[3].startswith("hdr:")
        assert keys[4].startswith("email:")
