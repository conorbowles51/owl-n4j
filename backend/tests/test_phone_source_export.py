"""07 J-14b: exporting the records behind an analysis result, a statement check or an incident window
(services.phone.source_export). Invented data only."""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from services.phone import source_export as S
from services.phone.exports import jobs
from tests.phone_analysis_fixture import record
from tests.phone_pg import fresh_engine, make_case, needs_template
from tests.phone_streams_fixture import at, phone

OWNER, ANA = "phone:+12025550100", "phone:+12025550111"


def msg(t, sender, to, body):
    return dict(kind="message", instant=t, body=body, thread="t",
                parties=[(sender, "sender", sender == OWNER, None, None)] +
                        [(x, "recipient", x == OWNER, None, None) for x in to])


@pytest.fixture
def world():
    with fresh_engine() as engine:
        with engine.begin() as c:
            case, other = make_case(c), make_case(c)
            ext, evs = phone(c, case, events=[msg(at(2023, 3, 15, 10), ANA, [OWNER], "first synthetic"),
                                              msg(at(2023, 3, 15, 11), OWNER, [ANA], "second synthetic"),
                                              msg(at(2023, 3, 20, 9), ANA, [OWNER], "later synthetic")])
            word = record(c, case, ext, 700, "DictionaryWord", texts=[("Word", "synthetic")])
            user = c.execute(text("SELECT owner_user_id FROM cases WHERE id = :c"), {"c": case}).scalar()
        yield {"engine": engine, "case": case, "other": other, "ext": ext, "evs": evs, "word": word, "user": user}


class _U:
    def __init__(self, uid):
        self.id = uid


def _result(c, case, ext, uids):
    run, res = uuid.uuid4(), uuid.uuid4()
    c.execute(text(
        "INSERT INTO phone_analysis_runs (id, case_id, approach, approach_version, parameters, parameters_sha256, "
        "input_manifest, input_revision, status, requested_by) VALUES (:r, :c, 'typed_words', '7.1', '{}', :h, '{}', "
        ":h, 'completed', 'synthetic')"), {"r": run, "c": case, "h": "0" * 64})
    c.execute(text(
        "INSERT INTO phone_analysis_results (id, run_id, case_id, result_key, kind, strength, measures, directions) "
        "VALUES (:i, :r, :c, :k, 'typed_and_present', 'elsewhere', '{}', '{}')"),
        {"i": res, "r": run, "c": case, "k": "1" * 64})
    for u in uids:
        c.execute(text("INSERT INTO phone_analysis_result_records (id, result_id, extraction_id, record_uid, role) "
                       "VALUES (:i, :r, :e, :u, 'evidence')"), {"i": uuid.uuid4(), "r": res, "e": ext, "u": u})
    return str(res)


@needs_template
def test_analysis_result_exports_its_messages_and_says_what_is_not_in_it(world):
    w = world
    with w["engine"].begin() as c:
        rid = _result(c, w["case"], w["ext"], [w["evs"][0]["record_uid"], w["evs"][1]["record_uid"], w["word"]])
    with Session(w["engine"]) as db:
        out = S.freeze_source(db, w["case"], "analysis_result", {"result_id": rid}, _U(w["user"]))
    assert out["collected"] == 2
    assert out["sentence"] == ("1 record behind it is not a message or call and is not in the export; open them on "
                               "the screen.")
    assert "Typed words" in out["words"]
    with w["engine"].begin() as c:
        facts = jobs.describe(c, w["case"], out["filter"])
        made = jobs.create(c, case_id=w["case"], user_id=w["user"], fmt="pdf", source="analysis_result",
                           filter_body=out["filter"], options={})
    assert facts["total"] == 2 and made["export_id"]
    with Session(w["engine"]) as db, pytest.raises(LookupError):
        S.freeze_source(db, w["other"], "analysis_result", {"result_id": rid}, _U(w["user"]))


@needs_template
def test_a_result_with_no_message_behind_it_is_refused_with_the_reason(world):
    w = world
    with w["engine"].begin() as c:
        rid = _result(c, w["case"], w["ext"], [w["word"]])
    with Session(w["engine"]) as db, pytest.raises(S.SourceExportError, match="1 record behind it"):
        S.freeze_source(db, w["case"], "analysis_result", {"result_id": rid}, _U(w["user"]))


@needs_template
def test_incident_window_exports_every_message_in_the_window(world):
    w = world
    with Session(w["engine"]) as db:
        out = S.freeze_source(db, w["case"], "incident_window",
                              {"start": "2023-03-15T09:00:00Z", "end": "2023-03-15T12:00:00Z"}, _U(w["user"]))
    assert out["collected"] == 2 and out["sentence"] is None
    with Session(w["engine"]) as db, pytest.raises(S.SourceExportError, match="at most 7 days"):
        S.freeze_source(db, w["case"], "incident_window",
                        {"start": "2023-03-01T00:00:00Z", "end": "2023-03-20T00:00:00Z"}, _U(w["user"]))


@needs_template
def test_a_selection_source_needs_its_selection(world):
    w = world
    with w["engine"].begin() as c, pytest.raises(jobs.ExportError, match="statement check is exported through"):
        jobs.create(c, case_id=w["case"], user_id=w["user"], fmt="pdf", source="statement_check", filter_body={},
                    options={})


@needs_template
def test_a_kept_result_is_listed_and_exports_its_records_as_frozen(world):
    import json

    from services.phone_analysis import keep
    w = world
    recs = [w["evs"][0]["record_uid"], w["word"]]
    with w["engine"].begin() as c:
        c.execute(text(
            "INSERT INTO pol_analysis_snapshot (id, case_id, kind, label, snapshot, record_count) VALUES ('pa_synthetic', "
            ":c, 'analysis_result', 'Typed words: typed and present (Lead for enquiry)', CAST(:s AS jsonb), 2)"),
            {"c": w["case"], "s": json.dumps({"subject": {"approach": "typed_words"}, "record_ids": recs})})
    with w["engine"].connect() as c:
        listed = keep.list_kept(c, w["case"])
        assert listed["total"] == 1 and listed["items"][0]["approach"] == "typed_words"
        assert keep.list_kept(c, w["other"])["total"] == 0
    with Session(w["engine"]) as db:
        out = S.freeze_source(db, w["case"], "analysis_result", {"kept_id": "pa_synthetic"}, _U(w["user"]))
    assert out["collected"] == 1 and out["sentence"].startswith("1 record behind it")
    assert "kept result" in out["words"]
    with Session(w["engine"]) as db, pytest.raises(LookupError):
        S.freeze_source(db, w["other"], "analysis_result", {"kept_id": "pa_synthetic"}, _U(w["user"]))
