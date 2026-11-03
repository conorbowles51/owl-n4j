"""agent-proposals B, C: the case agent's Workspace drafts wait pending review and only a person accepts them.

Accepted work carries the model origin (actor_origin) so it always shows a model drafted it; what the person opened
first is recorded; a lead card names the institution and a four-digit ending, cites each alert and never totals.
"""
from __future__ import annotations

import json
import uuid
from datetime import date

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from postgres.base import Base
from postgres.models.agent_proposals import AgentProposalSourceOpen
from postgres.models.case import Case
from postgres.models.case_context import CaseContext, CaseMandateVersion
from postgres.models.evidence import EvidenceFile
from postgres.models.financial_judgements import FinancialJudgement
from postgres.models.user import User
from postgres.models.case_deadline import CaseDeadline
from postgres.models.work import CaseTask, CaseTaskLink
from postgres.models.workspace_ai import WorkspaceAIOutput
from postgres.models.workspace_entry import (WorkspaceEntry, WorkspaceEntryEvent, WorkspaceEntryLink,
                                             WorkspaceEntryRevision, WorkspaceLegacyMapping)
from services.agent import proposals, workspace_proposals as W

TABLES = [User.__table__, Case.__table__, CaseMandateVersion.__table__, CaseContext.__table__, EvidenceFile.__table__,
          WorkspaceEntry.__table__, WorkspaceEntryRevision.__table__, WorkspaceEntryLink.__table__,
          WorkspaceEntryEvent.__table__, WorkspaceAIOutput.__table__, AgentProposalSourceOpen.__table__,
          FinancialJudgement.__table__, CaseTask.__table__, CaseTaskLink.__table__, CaseDeadline.__table__,
          WorkspaceLegacyMapping.__table__]


@pytest.fixture()
def db(tmp_path):
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine, tables=TABLES)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        owner = User(email="alex@example.test", name="Alex", password_hash="x")
        session.add(owner)
        session.flush()
        case = Case(title="Case without a mandate", created_by_user_id=owner.id, owner_user_id=owner.id)
        other = Case(title="Other", created_by_user_id=owner.id, owner_user_id=owner.id)
        session.add_all([case, other])
        session.flush()
        statement = EvidenceFile(case_id=case.id, original_filename="statement-march.pdf",
                                 stored_path=str(tmp_path / "s.pdf"), size=1, sha256="a" * 64, status="processed",
                                 created_by_id=owner.id)
        foreign = EvidenceFile(case_id=other.id, original_filename="elsewhere.pdf", stored_path=str(tmp_path / "e.pdf"),
                               size=1, sha256="b" * 64, status="processed", created_by_id=owner.id)
        session.add_all([statement, foreign])
        session.commit()
        session.info.update(owner=owner, case=case, other=other, statement=statement, foreign=foreign)
        yield session
    engine.dispose()


def _origin():
    return proposals.agent_origin(for_name="Alex", model="DeepSeek V4 Pro", model_id="deepseek-v4-pro",
                                  run_id=uuid.uuid4())


def _draft(db, citations=None):
    case, statement = db.info["case"], db.info["statement"]
    return W.propose_entry(db, case_id=case.id, entry_type="finding", title="Cash out after each deposit",
                           body="Each deposit is followed by a cash withdrawal within two days.",
                           citations=citations or [f"doc://{statement.id}/3"], origin=_origin())


def test_a_draft_waits_and_changes_nothing_until_a_person_accepts(db):
    item = _draft(db)
    assert (item["review_status"], item["target_type"], item["output_type"]) == ("pending_review", "case",
                                                                                  "entry_draft")
    assert item["mandate_version_id"] is None  # a case with no mandate can still hold a proposal
    assert item["proposal"]["model"] == "DeepSeek V4 Pro"
    assert db.scalars(select(WorkspaceEntry)).all() == []
    listed = W.list_proposals(db, case_id=db.info["case"].id)
    assert (listed["total"], listed["returned"]) == (1, 1)


def test_a_citation_from_another_case_refuses_the_draft(db):
    with pytest.raises(proposals.ProposalError, match="Not in this case"):
        _draft(db, citations=[f"doc://{db.info['foreign'].id}/1"])
    assert db.scalars(select(WorkspaceAIOutput)).all() == []


def test_accepting_creates_the_entry_with_the_model_origin_and_records_the_open(db):
    item = _draft(db)
    owner = db.info["owner"]
    cite = f"doc://{db.info['statement'].id}/3"
    proposals.record_open(db, case_id=db.info["case"].id, proposal_type="workspace_ai", proposal_id=item["id"],
                          citation=cite, user=owner)
    done = W.accept(db, case_id=db.info["case"].id, output_id=item["id"], reviewer=owner, via="ui")
    assert done["review_status"] == "accepted"
    assert done["proposal"]["review"]["source_opened"] is True
    assert done["proposal"]["review"]["opened"] == [cite]
    entry = db.get(WorkspaceEntry, uuid.UUID(done["accepted_targets"][0]["target_id"]))
    assert (entry.entry_type, entry.author_name, entry.title) == ("finding", "Alex", "Cash out after each deposit")
    origin = entry.migration_metadata["actor_origin"]
    assert origin["origin"]["model"] == "DeepSeek V4 Pro"
    assert origin["accepted_by"]["name"] == "Alex"
    with pytest.raises(proposals.ProposalError, match="already accepted"):
        W.accept(db, case_id=db.info["case"].id, output_id=item["id"], reviewer=owner)


def test_accepting_without_opening_is_recorded_as_such(db):
    item = _draft(db)
    done = W.accept(db, case_id=db.info["case"].id, output_id=item["id"], reviewer=db.info["owner"])
    assert (done["proposal"]["review"]["source_opened"], done["proposal"]["review"]["via"]) == (False, "api")
    stats = proposals.precision(db, db.info["case"].id)
    assert stats["confirmations"] == dict(total=1, with_source_opened=0, without_source_opened=1)
    assert next(k for k in stats["kinds"] if k["kind"] == "entry_draft")["accepted"] == 1


def test_only_a_person_accepts_and_a_rejection_needs_a_reason(db):
    from services.financial.model_work import model_actor
    item = _draft(db)
    owner = db.info["owner"]
    claude = model_actor(for_name="Alex", for_email=owner.email, for_user_id=owner.id)
    with pytest.raises(proposals.ProposalError, match="A person accepts"):
        W.accept(db, case_id=db.info["case"].id, output_id=item["id"], reviewer=claude)
    with pytest.raises(proposals.ProposalError, match="Say why"):
        W.reject(db, case_id=db.info["case"].id, output_id=item["id"], reviewer=owner, reason=" ")
    done = W.reject(db, case_id=db.info["case"].id, output_id=item["id"], reviewer=owner,
                    reason="The withdrawals are a payroll pattern.")
    assert (done["review_status"], done["rejection_reason"]) == ("rejected", "The withdrawals are a payroll pattern.")
    assert db.scalars(select(WorkspaceEntry)).all() == []


def test_the_generic_workspace_ai_accept_refuses_an_agent_proposal(db):
    from services.workspace_ai_service import WorkspaceAIConflict, accept_output
    item = _draft(db)
    with pytest.raises(WorkspaceAIConflict, match="case agent"):
        accept_output(db, case_id=db.info["case"].id, output_id=uuid.UUID(item["id"]), reviewer=db.info["owner"])


def test_another_case_cannot_see_or_accept_the_proposal(db):
    item = _draft(db)
    assert W.list_proposals(db, case_id=db.info["other"].id)["total"] == 0
    with pytest.raises(proposals.ProposalError, match="not found"):
        W.accept(db, case_id=db.info["other"].id, output_id=item["id"], reviewer=db.info["owner"])


# -- lead cards ---------------------------------------------------------------------------------------------------

LEAD = dict(id=str(uuid.uuid4()), kind="account_lead", measures=dict(
    institution=dict(id="bbva-mx", name="BBVA México"), account_ref="ending 4821", status="no_statement_found",
    counts=dict(transactional=3, account=1), sentence="This phone holds 3 alerts from BBVA México for an account "
                                                     "ending 4821. No statement for an account ending 4821 at BBVA "
                                                     "México is among the financial records in this case."))


def _alerts():
    uid = lambda: str(uuid.uuid4())
    ext = str(uuid.uuid4())
    return [dict(record_uid=uid(), extraction_id=ext, **{"class": "transactional"}, instant="2024-03-02T10:00:00+00:00",
                 amount_minor=150000, currency="MXN", direction="debit"),
            dict(record_uid=uid(), extraction_id=ext, **{"class": "transactional"}, instant="2024-01-15T09:30:00+00:00",
                 amount_minor=250000, currency="MXN", direction="credit"),
            dict(record_uid=uid(), extraction_id=ext, **{"class": "transactional"}, instant="2024-02-20T18:45:00+00:00",
                 amount_minor=99900, currency="MXN", direction="debit"),
            dict(record_uid=uid(), extraction_id=ext, **{"class": "account"}, instant="2023-11-01T08:00:00+00:00",
                 amount_minor=None, currency=None, direction=None)], {ext: "Phone 1 (iPhone)"}


def test_the_lead_card_masks_the_ending_cites_each_alert_and_never_totals():
    alerts, phones = _alerts()
    card = W.lead_card_content(LEAD, alerts, phones)
    assert card["account_ending"] == "ending 4821"
    assert card["institution"] == "BBVA México"
    # The period a request would cover runs over the alerts with an amount, first to last
    assert card["request_period"] == dict(start="2024-01-15", end="2024-03-02")
    assert card["counts"] == dict(transactional=3, account=1)
    assert [a["cite"] for a in card["alerts"]] == [f"rec://{a['record_uid']}" for a in
                                                    sorted(alerts, key=lambda a: a["instant"])]
    assert card["totalled"] is False
    assert not any("total" in key for key in card if key not in ("totalled", "alerts_total"))
    assert card["alerts_total"] == card["alerts_shown"] == 4
    assert card["phones"] == ["Phone 1 (iPhone)"]
    assert W.mask_ending("4152 3134 9988 4821") == "ending 4821"


def test_accepting_a_lead_card_needs_a_deadline_and_makes_a_finding_and_a_task(db, monkeypatch):
    alerts, phones = _alerts()
    monkeypatch.setattr(proposals, "check_citations", lambda session, case_id, cites: [
        dict(citation=c, scheme="rec", status="valid", label="Phone alert") for c in cites])
    item = W.propose_lead_card(db, case_id=db.info["case"].id, lead_result_id=LEAD["id"], origin=_origin(),
                               _read=lambda s, c, l: (LEAD, alerts, phones))
    assert item["output_type"] == "lead_card"
    owner = db.info["owner"]
    with pytest.raises(proposals.ProposalError, match="deadline"):
        W.accept(db, case_id=db.info["case"].id, output_id=item["id"], reviewer=owner)
    done = W.accept(db, case_id=db.info["case"].id, output_id=item["id"], reviewer=owner, due_at=date(2026, 11, 10))
    kinds = {t["target_type"] for t in done["accepted_targets"]}
    assert kinds == {"workspace_entry", "case_task"}
    task = db.scalars(select(CaseTask)).one()
    assert task.title == "Statements for BBVA México ending 4821, 2024-01-15 to 2024-03-02"
    assert task.due_at.date() == date(2026, 11, 10)
    assert task.migration_metadata["actor_origin"]["origin"]["model"] == "DeepSeek V4 Pro"
    entry = db.scalars(select(WorkspaceEntry)).one()
    assert "lead" in entry.tags and "ending 4821" in entry.title
    assert "1,500.00" in entry.body and "4,000" not in entry.body  # each alert listed, never a sum
    link = db.scalars(select(CaseTaskLink)).one()
    assert (link.target_type, link.target_id) == ("entry", str(entry.id))


# -- red cell (D) -------------------------------------------------------------------------------------------------

def test_the_red_cell_leaves_out_the_framing_and_records_alternatives_as_proposals(db, monkeypatch):
    from services.agent import red_cell
    case, owner, statement = db.info["case"], db.info["owner"], db.info["statement"]
    theory = WorkspaceEntry(case_id=case.id, entry_type="theory", title="Maria Lopez laundered the cash",
                            body="Maria Lopez moved the deposits to Juan Ortega.", tags=[], lifecycle_state="proposed",
                            review_state="accepted", author_user_id=owner.id, author_email=owner.email,
                            author_name=owner.name, updated_by_user_id=owner.id, updated_by_email=owner.email,
                            updated_by_name=owner.name)
    db.add(theory)
    db.commit()
    facts = [dict(cite=f"doc://{statement.id}/2", text="Maria Lopez deposited 9,500 in cash on 3 March."),
             dict(cite=f"doc://{statement.id}/3", text="A transfer of 9,000 went to Juan Ortega on 4 March.")]
    monkeypatch.setattr(red_cell, "_facts", lambda s, c, t: [dict(f, fact_id=f"F{i}") for i, f in
                                                              enumerate(facts, 1)])
    seen = {}

    def reader(prompt):
        seen["prompt"] = prompt
        return json.dumps({"alternatives": [
            {"title": "Repayment of a family loan", "explanation": "The transfer repays a loan.", "facts": ["F2"],
             "would_tell_apart": "A loan agreement or earlier transfers the other way."},
            {"title": "Business takings banked", "explanation": "Cash from a market stall.", "facts": ["F1"]},
            {"title": "No facts cited", "explanation": "x", "facts": ["F9"]}]})
    out = red_cell.sweep(db, case_id=case.id, theory_id=theory.id, requested_by=owner, reader=reader,
                         model=("anthropic", "claude-opus-4-8"), agent_model=("deepseek", "deepseek-v4-pro"))
    prompt = seen["prompt"]
    assert "laundered" not in prompt and "Maria Lopez" not in prompt and "Juan Ortega" not in prompt
    assert "Person A" in prompt and "Person B" in prompt
    assert (out["returned"], out["recorded"], len(out["refused"])) == (3, 2, 1)
    item = out["proposals"][0]
    assert (item["output_type"], item["review_status"]) == ("alternative_explanation", "pending_review")
    origin = db.get(WorkspaceAIOutput, uuid.UUID(item["id"])).model_metadata["origin"]["red_cell"]
    assert origin["framing_removed"] is True and origin["agent_model_id"] == "deepseek-v4-pro"
    done = W.accept(db, case_id=case.id, output_id=item["id"], reviewer=owner)
    entry = db.get(WorkspaceEntry, uuid.UUID(done["accepted_targets"][0]["target_id"]))
    assert (entry.entry_type, entry.lifecycle_state, "red-cell" in entry.tags) == ("theory", "proposed", True)
    kinds = {k["kind"]: k for k in proposals.precision(db, case.id)["kinds"]}
    assert (kinds["alternative_explanation"]["accepted"], kinds["alternative_explanation"]["open"]) == (1, 1)


def test_the_red_cell_never_runs_on_the_agents_own_model():
    from services.agent.red_cell import choose_model
    assert choose_model("deepseek", "deepseek-v4-pro", lambda p: p == "deepseek") == ("deepseek", "deepseek-v4-flash",
                                                                                     True)
    assert choose_model("deepseek", "deepseek-v4-pro", lambda p: p in ("deepseek", "openai"))[:2] == ("openai",
                                                                                                    "gpt-5.6-sol")
    assert choose_model("openai", "gpt-5.6-sol", lambda p: p == "openai") is None


def test_a_phone_record_citation_is_checked_against_the_case(db):
    """rec:// is checked locally against the case's phone records, so lead cards can cite their alerts."""
    from sqlalchemy import text
    case = db.info["case"]
    mine, theirs = uuid.uuid4(), uuid.uuid4()
    db.execute(text("CREATE TABLE IF NOT EXISTS pv_record (case_id TEXT, record_uid TEXT)"))
    db.execute(text("INSERT INTO pv_record VALUES (:c, :u)"), dict(c=str(case.id), u=str(mine)))
    db.execute(text("INSERT INTO pv_record VALUES (:c, :u)"), dict(c=str(uuid.uuid4()), u=str(theirs)))
    out = proposals.check_citations(db, case.id, [f"rec://{mine}", f"rec://{mine}#body", f"rec://{theirs}",
                                                  "rec://not-a-uid"])
    assert [o["status"] for o in out] == ["valid", "valid", "not_in_case", "not_in_case"]
    assert out[2]["label"] == out[3]["label"] == "Not in this case."


def _pv(db, uids, case_id=None):
    from sqlalchemy import text
    db.execute(text("CREATE TABLE IF NOT EXISTS pv_record (case_id TEXT, record_uid TEXT)"))
    for u in uids:
        db.execute(text("INSERT INTO pv_record VALUES (:c, :u)"), dict(c=str(case_id or db.info["case"].id), u=str(u)))


def test_a_lead_card_cites_every_alert_even_past_twenty(db):
    """The model's own citations stop at 20; a lead card cites every alert the code found (old code: refused)."""
    uids = [uuid.uuid4() for _ in range(25)]
    _pv(db, uids)
    alerts = [dict(record_uid=str(u), extraction_id="x", instant=f"2024-01-{i + 1:02d}T09:00:00+00:00",
                   amount_minor=100, currency="MXN", direction="debit", **{"class": "transactional"})
              for i, u in enumerate(uids)]
    item = W.propose_lead_card(db, case_id=db.info["case"].id, lead_result_id=LEAD["id"], origin=_origin(),
                               _read=lambda s, c, l: (LEAD, alerts, {}))
    assert len(item["content"]["citations"]) == 25


CLAIM = dict(claim="Maria Lopez had the means to operate the BBVA account ending 4821 from 2024-01-01 to 2024-03-31",
             established=True, coverage="Account to device: 1 codes, 1 alerts, 0 app or login records.",
             correlated_strands="Strands from one handset are not independent.",
             not_a_holder_finding="This is never a finding that the person is the account holder.",
             person={"name": "Maria Lopez"}, account={"ending": "4821"}, period={"start": "2024-01-01"},
             chain=[{"link": "account_to_device", "holds": True, "counts": {"code": 1, "alert": 1}},
                    {"link": "device_to_person", "holds": True}])


def test_a_control_claim_is_stored_from_the_phones_check_and_accepted_as_a_finding_never_a_holder(db):
    code, alert = uuid.uuid4(), uuid.uuid4()
    _pv(db, [code, alert])
    result = dict(CLAIM, items=[dict(link="account_to_device", kind="code", strength="supporting",
                                     words="one-time code from BBVA", rec=f"rec://{code}"),
                                dict(link="account_to_device", kind="alert", strength="supporting",
                                     words="alert for the account", rec=f"rec://{alert}")])
    item = W.propose_phone_draft(db, case_id=db.info["case"].id, kind="control_claim", args={}, origin=_origin(),
                                 _run=lambda: result)
    assert item["output_type"] == "control_claim" and item["review_status"] == "pending_review"
    assert sorted(item["content"]["citations"]) == sorted([f"rec://{code}", f"rec://{alert}"])
    assert db.scalars(select(WorkspaceEntry)).all() == []
    owner = db.info["owner"]
    proposals.record_open(db, case_id=db.info["case"].id, proposal_type="workspace_ai", proposal_id=item["id"],
                          citation=f"rec://{code}", user=owner)
    W.accept(db, case_id=db.info["case"].id, output_id=item["id"], reviewer=owner, via="ui")
    entry = db.scalars(select(WorkspaceEntry)).one()
    assert entry.entry_type == "finding" and "control-claim" in entry.tags
    assert "never a finding that the person is the account holder" in entry.body
    assert entry.migration_metadata["actor_origin"]["origin"]["model"] == "DeepSeek V4 Pro"


def test_a_control_claim_that_does_not_hold_is_not_proposed(db):
    result = dict(CLAIM, established=False, items=[], limitation="The chain does not hold: no reviewed link.")
    with pytest.raises(proposals.ProposalError, match="does not hold"):
        W.propose_phone_draft(db, case_id=db.info["case"].id, kind="control_claim", args={}, origin=_origin(),
                              _run=lambda: result)
    assert db.scalars(select(WorkspaceAIOutput)).all() == []


def test_a_payment_purpose_quoting_another_cases_record_is_refused(db):
    mine, theirs = uuid.uuid4(), uuid.uuid4()
    _pv(db, [mine])
    _pv(db, [theirs], case_id=db.info["other"].id)
    result = dict(items=[dict(payment=None, outcome="consistent", purpose_stated="rent",
                              quoted=[f"rec://{mine}", f"rec://{theirs}"])])
    with pytest.raises(proposals.ProposalError, match="Not in this case"):
        W.propose_phone_draft(db, case_id=db.info["case"].id, kind="payment_purpose", args={}, origin=_origin(),
                              _run=lambda: result)
