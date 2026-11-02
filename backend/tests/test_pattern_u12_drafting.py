"""04-U12 (cb-pol item L): model drafting of statement claims.

Synthetic interview and phone only; the model is a stub. Opt-in PostgreSQL through
``LOUPE_TEST_PHONE_PG_TEMPLATE_URL``.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from postgres.models.case_context import CaseContext, CaseMandateVersion
from postgres.models.case_profile import CaseProfile
from postgres.models.dossier import DossierInterview, DossierInterviewEvidenceLink
from postgres.models.evidence import EvidenceFile
from postgres.models.user import User
from services import ai_model_policy, workspace_ai_service
from services.pattern_of_life import claims, drafting
from services.phone import registry, sweep
from tests.phone_pg import fld, fresh_engine, make_case, make_extraction, model, needs_template, refs
from tests.test_phone_mappings import _shipped, hooks, stamp  # noqa: F401 (fixture)


@pytest.fixture(autouse=True)
def _feed_inbox(monkeypatch, tmp_path):
    from services import manual_changes
    monkeypatch.setattr(manual_changes, "INBOX", tmp_path / "inbox.jsonl")  # never the real feed inbox


def test_drafting_is_its_own_workload_and_defaults_to_deepseek():
    assert "statement_claim_drafting" in ai_model_policy.WORKLOADS
    assert ai_model_policy.DEFAULT_POLICY["statement_claim_drafting"]["provider"] == "deepseek"
    for profile in ai_model_policy.PROVIDER_DEFAULTS.values():
        assert "statement_claim_drafting" in profile


def test_an_uncited_claim_is_rejected_and_a_model_time_is_discarded():
    sources = [{"source_id": "S1", "evidence_file_id": None, "interview_id": None, "filename": "x",
                "source_anchor": {}, "content_hash": "0" * 64, "text": "synthetic words", "url": "/x"}]
    base = {"kind": "inactive", "window_text": "from about eleven", "quote": "I was asleep from about eleven"}
    with pytest.raises(workspace_ai_service.WorkspaceAIError):
        drafting.validate({"claims": [dict(base)], "limitations": []}, sources)
    with pytest.raises(workspace_ai_service.WorkspaceAIError):
        drafting.validate({"claims": [dict(base, citation_ids=["S9"])], "limitations": []}, sources)
    with pytest.raises(workspace_ai_service.WorkspaceAIError):
        drafting.validate({"claims": [dict(base, citation_ids=["S1"], kind="asleep")], "limitations": []}, sources)
    content, cites = drafting.validate({"claims": [dict(base, citation_ids=["S1"], window_start="2023-03-14T23:00:00Z",
                                                        window_end="2023-03-15T07:00:00Z")], "limitations": []},
                                       sources)
    assert "window_start" not in content["claims"][0] and content["discarded_fields"] == 2
    assert [c["source_id"] for c in cites] == ["S1"]


def _seed(c, case):
    """A mandate, a person, an interview with a synthetic transcript, and a phone conversation."""
    uid = c.execute(text("SELECT owner_user_id FROM cases WHERE id = :c"), {"c": case}).scalar_one()
    s = Session(bind=c)
    mandate = CaseMandateVersion(case_id=case, version_number=1, objective="Synthetic objective.",
                                 key_questions=["Synthetic?"], author_user_id=uid)
    s.add(mandate)
    s.flush()
    s.add(CaseContext(case_id=case, active_template_key="generic", active_mandate_version_id=mandate.id,
                      created_by_user_id=uid))
    dossier = CaseProfile(case_id=case, profile_type="person", display_name="Synthetic Person", status="active",
                          linkage_state="unlinked", created_by_user_id=uid, updated_by_user_id=uid)
    audio = EvidenceFile(case_id=case, original_filename="synthetic-interview.mp3", stored_path="/nowhere/x.mp3",
                         size=1, sha256="b" * 64, status="processed", created_by_id=uid,
                         transcription="I was asleep from about eleven.",
                         transcription_segments=[{"id": "seg-1", "start": 3.0, "end": 6.0, "speaker": "Witness",
                                                  "text": "I was asleep from about eleven."}])
    s.add_all([dossier, audio])
    s.flush()
    interview = DossierInterview(dossier_id=dossier.id, case_id=case, participants=["Synthetic Person"],
                                 interviewer_user_ids=[str(uid)], status="completed", created_by_user_id=uid,
                                 updated_by_user_id=uid)
    s.add(interview)
    s.flush()
    s.add(DossierInterviewEvidenceLink(interview_id=interview.id, case_id=case, evidence_file_id=audio.id,
                                       source_anchor={"start_seconds": 3.0, "end_seconds": 6.0}))
    s.flush()
    msg = model("InstantMessage", [fld("TimeStamp", ("TimeStamp", "2023-03-14T23:30:00-04:00")),
                                   fld("Body", ("String", "synthetic: are you up?")),
                                   fld("Source", ("String", "SyntheticApp")), refs("From", 1),
                                   refs("To", 2, kind="multiModelField")])
    me = model("Party", [fld("Identifier", ("String", "+12025550100")), fld("IsPhoneOwner", ("Boolean", "True"))])
    them = model("Party", [fld("Identifier", ("String", "+12025550143")), fld("IsPhoneOwner", ("Boolean", "False"))])
    ext = make_extraction(c, case, [(0, None, 0, msg), (1, 0, 0, me), (2, 0, 0, them)],
                          timestamps=[stamp(0, "0.0", "TimeStamp", "InstantMessage")], label="C1")
    return uid, dossier.id, interview.id, ext


def _stub(claims_out):
    return lambda prompt, sources, output: ({"headline": "Drafted", "claims": claims_out(sources), "limitations": []},
                                            {"provider": "deepseek", "model_id": "deepseek-v4-pro"})


@needs_template
def test_drafts_from_an_interview_become_cited_unconfirmed_claims_with_no_time(hooks):
    _shipped(hooks, ["type"])
    with fresh_engine() as engine:
        with engine.begin() as c:
            registry.apply_seed(c)
            case = make_case(c)
            uid, dossier, interview, ext = _seed(c, case)
        assert sweep.interpret_one(engine, ext)["status"] == "done"
        subject = {"kind": "extraction", "extraction_id": str(ext)}
        with Session(engine) as db:
            user = db.get(User, uid)
            q = workspace_ai_service.create_output(db, case_id=case, target_type="dossier", target_id=dossier,
                                                   output_type="statement_claims", requested_by=user,
                                                   interview_ids=[interview], subject=subject)
            assert q["source_set"][0]["source_anchor"]["start_seconds"] == 3.0
            bad = workspace_ai_service.run_output(db, output_id=uuid.UUID(q["id"]), generator=_stub(lambda s: [
                {"kind": "inactive", "window_text": "from about eleven", "quote": "asleep from about eleven"}]))
            assert bad["job_status"] == "failed" and bad["citation_status"] == "invalid"  # uncited: rejected
            q = workspace_ai_service.create_output(db, case_id=case, target_type="dossier", target_id=dossier,
                                                   output_type="statement_claims", requested_by=user,
                                                   interview_ids=[interview], subject=subject)
            seen = {}

            def gen(prompt, sources, output):
                seen["prompt"] = prompt
                return ({"headline": "Drafted", "limitations": [], "claims": [
                    {"kind": "inactive", "window_text": "from about eleven", "quote": "asleep from about eleven",
                     "citation_ids": [sources[0]["source_id"]], "window_start": "2023-03-15T03:00:00Z"}]},
                        {"provider": "deepseek", "model_id": "deepseek-v4-pro"})
            done = workspace_ai_service.run_output(db, output_id=uuid.UUID(q["id"]), generator=gen)
            assert done["job_status"] == "completed" and done["content"]["discarded_fields"] == 1
            assert "Never convert a time" in seen["prompt"]
            acc = workspace_ai_service.accept_output(db, case_id=case, output_id=uuid.UUID(q["id"]), reviewer=user)
            assert [t["target_type"] for t in acc["accepted_targets"]] == ["pol_claim"]
            got = claims.get(db.connection(), case, acc["accepted_targets"][0]["target_id"])
            assert got["origin"] == "ai_draft" and got["status"] == "draft" and got["window_start"] is None
            assert got["status_words"] == "Drafted by deepseek-v4-pro, not confirmed"
            assert got["source_anchor"]["citations"][0]["start_seconds"] == 3.0
            assert got["source_anchor"]["quote"] == "asleep from about eleven"


@needs_template
def test_drafting_reads_a_conversation_of_the_case_in_full_and_refuses_one_from_elsewhere(hooks):
    from tests.pattern_pg import api_client
    _shipped(hooks, ["type"])
    with fresh_engine() as engine:
        with engine.begin() as c:
            registry.apply_seed(c)
            case = make_case(c)
            uid, dossier, interview, ext = _seed(c, case)
        assert sweep.interpret_one(engine, ext)["status"] == "done"
        with engine.connect() as c:
            thread = c.execute(text("SELECT thread_key FROM pv_comm_event WHERE extraction_id = :e"),
                               {"e": ext}).scalar_one()
        # no external-processing decision on the phone: drafting still reads it (full phone visibility)
        with engine.connect() as c:
            assert not c.execute(text("SELECT count(*) FROM adjudications WHERE decision = "
                                      "'allow_phone_external_processing'")).scalar()
        subject = {"kind": "extraction", "extraction_id": str(ext)}
        with Session(engine) as db:
            user = db.get(User, uid)
            q = workspace_ai_service.create_output(db, case_id=case, target_type="dossier", target_id=dossier,
                                                   output_type="statement_claims", requested_by=user,
                                                   subject=subject, conversation=thread)
            src = q["source_set"]
            assert len(src) == 1 and src[0]["source_anchor"]["thread_key"] == thread
            assert "are you up" in src[0]["excerpt"]
            with pytest.raises(workspace_ai_service.WorkspaceAIError):
                workspace_ai_service.create_output(db, case_id=case, target_type="dossier", target_id=dossier,
                                                   output_type="statement_claims", requested_by=user,
                                                   subject=subject, conversation="not-a-thread-of-this-case")
        with api_client(engine, case) as client:
            r = client.post("/api/pattern/%s/claim-drafts" % case, json={
                "dossier_id": str(dossier), "subject": {"kind": "extraction", "extraction_id": str(uuid.uuid4())},
                "conversation_locator": thread})
            assert r.status_code == 404  # an extraction not in the case
