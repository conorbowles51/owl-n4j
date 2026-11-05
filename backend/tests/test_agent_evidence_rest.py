"""agent-evidence-rest A, C, D, F, G: what the report promised and only prompt wording held. No PostgreSQL needed.

Invented data only. Every test fails on the code before this job: the kinds, tools and functions did not exist, leads
had no draft schedule, and the waiting list was newest first whatever people had decided.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from postgres.base import Base
from postgres.models.agent_evidence import CaseGlossaryTerm
from postgres.models.agent_proposals import AgentProposalSourceOpen
from postgres.models.case import Case
from postgres.models.case_context import CaseContext, CaseMandateVersion
from postgres.models.evidence import EvidenceFile
from postgres.models.financial_judgements import FinancialJudgement
from postgres.models.user import User
from postgres.models.workspace_ai import WorkspaceAIOutput
from services.agent import glossary, proposal_feedback as PF, proposals, workspace_proposals as W
from services.financial.model_work import model_origin

TABLES = [User.__table__, Case.__table__, CaseMandateVersion.__table__, CaseContext.__table__, EvidenceFile.__table__,
          WorkspaceAIOutput.__table__, AgentProposalSourceOpen.__table__, FinancialJudgement.__table__,
          CaseGlossaryTerm.__table__]


@pytest.fixture()
def db(tmp_path):
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine, tables=TABLES)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        owner = User(email="alex@example.test", name="Alex", password_hash="x")
        session.add(owner)
        session.flush()
        case = Case(title="Case", created_by_user_id=owner.id, owner_user_id=owner.id)
        other = Case(title="Other", created_by_user_id=owner.id, owner_user_id=owner.id)
        session.add_all([case, other])
        session.flush()
        page = EvidenceFile(case_id=case.id, original_filename="timeline.pdf", stored_path=str(tmp_path / "t.pdf"),
                            size=1, sha256="a" * 64, status="processed", created_by_id=owner.id)
        session.add(page)
        session.commit()
        session.info.update(owner=owner, case=case, other=other, page=page)
        yield session
    engine.dispose()


def _origin():
    return model_origin(for_name="Alex", model="DeepSeek V4 Pro", model_id="deepseek-v4-pro", how="case agent proposal")


def _cite(db):
    return [f"doc://{db.info['page'].id}"]


# ---- A: the draft schedule on a lead card ------------------------------------------------------------------------

LEAD = dict(id=str(uuid.uuid4()), measures=dict(institution=dict(name="Synthetic Bank"), account_ref="ending 4821",
                                                status="no_statement_found", sentence="s", counts=dict(transactional=2)))
ALERTS = [dict(record_uid=str(uuid.uuid4()), extraction_id="e", **{"class": "transactional"}, amount_minor=100,
               currency="USD", direction="debit", instant=f"2024-0{m}-05T10:00:00+00:00") for m in (1, 3)]


def test_the_lead_card_holds_an_editable_schedule_labelled_model_drafted():
    card = W.lead_card_content(LEAD, ALERTS, {"e": "Phone 1"})
    assert "Institution: Synthetic Bank" in card["schedule"] and "ending 4821" in card["schedule"]
    assert "2024-01-05 to 2024-03-05" in card["schedule"]
    assert "Drafted by the case agent, not confirmed" in card["schedule_label"]
    assert "Phone 1" in card["schedule"]
    # a schedule never adds alerts up (p4)
    assert "100" not in card["schedule"]


def test_a_lead_with_no_dated_alert_says_a_person_sets_the_period():
    card = W.lead_card_content(LEAD, [dict(ALERTS[0], instant=None)], {"e": "Phone 1"})
    assert card["request_period"] is None and "a person sets it" in card["schedule"]


# ---- G: past decisions order later proposals ---------------------------------------------------------------------

def _entry(db, title):
    return W.propose_entry(db, case_id=db.info["case"].id, entry_type="note", title=title, body="b",
                           citations=_cite(db), origin=_origin())


def _rejected_entries_and_term(db):
    for i in range(3):
        out = _entry(db, f"old {i}")
        W.reject(db, case_id=db.info["case"].id, output_id=out["id"], reviewer=db.info["owner"], reason=f"not so {i}")
    return W.propose_term(db, case_id=db.info["case"].id, term="breakfast", meaning="a cash payment",
                          citations=_cite(db), origin=_origin())


def test_a_kind_people_rejected_goes_below_one_nobody_decided_and_the_reason_is_given(db):
    term = _rejected_entries_and_term(db)
    newest = _entry(db, "newest draft")
    page = W.list_proposals(db, case_id=db.info["case"].id)
    assert [i["id"] for i in page["items"]] == [term["id"], newest["id"]]
    assert "rejected of 3 decided" in page["items"][1]["order_reason"]
    assert page["items"][0]["order_reason"] == "Code-word meaning: none decided yet."
    assert page["order_rule"] == PF.RULE


def test_reordering_never_hides_a_proposal(db):
    _rejected_entries_and_term(db)
    made = [_entry(db, f"draft {i}")["id"] for i in range(4)]
    page = W.list_proposals(db, case_id=db.info["case"].id)
    assert page["total"] == 5 and page["returned"] == 5 and set(made) <= {i["id"] for i in page["items"]}


def test_the_feedback_states_the_counts_rule_and_lessons_and_is_not_shown_before_any_decision(db):
    case = db.info["case"].id
    assert PF.block(PF.read(db, case)) == ""
    _rejected_entries_and_term(db)
    feedback = PF.read(db, case)
    assert feedback["decided"] == 3 and feedback["rule"] == PF.RULE
    assert [k["kind"] for k in feedback["kinds"]] == ["glossary_term", "entry_draft"]
    row = feedback["kinds"][1]
    assert (row["rejected"], row["score"]) == (3, 0.2) and len(row["lessons"]) == PF.MAX_REASONS
    words = PF.block(feedback)
    assert "3 rejected of 3 decided" in words and 'A person said: "not so' in words


def test_outcomes_of_another_case_do_not_order_this_one(db):
    other = db.info["other"].id
    doc = EvidenceFile(case_id=other, original_filename="o.pdf", stored_path="/nowhere/o", size=1, sha256="b" * 64,
                       status="processed", created_by_id=db.info["owner"].id)
    db.add(doc)
    db.commit()
    out = W.propose_entry(db, case_id=other, entry_type="note", title="t", body="b", citations=[f"doc://{doc.id}"],
                          origin=_origin())
    W.reject(db, case_id=other, output_id=out["id"], reviewer=db.info["owner"], reason="no")
    assert PF.read(db, db.info["case"].id)["kinds"] == []


# ---- D: an entity, through the graph's own path ----------------------------------------------------------------

def test_an_entity_waits_and_only_an_accept_writes_it_with_the_model_shown(db, monkeypatch):
    from services import graph_entities
    written = []
    monkeypatch.setattr(graph_entities, "same_name", lambda c, n: [])
    monkeypatch.setattr(graph_entities, "create_case_entity", lambda **kw: written.append(kw) or ("key", "cypher"))
    item = W.propose_entity(db, case_id=db.info["case"].id, name="Pickup 7741", entity_type="Document",
                            summary="A pickup code in the schedule.", citations=_cite(db), origin=_origin())
    assert item["review_status"] == "pending_review" and not written
    done = W.accept(db, case_id=db.info["case"].id, output_id=item["id"], reviewer=db.info["owner"])
    assert done["accepted_targets"] == [dict(target_type="graph_entity", target_id="key")]
    kw = written[0]
    assert kw["name"] == "Pickup 7741" and kw["properties"]["citations"] == _cite(db)
    assert kw["properties"]["proposed_by_model"] == "DeepSeek V4 Pro" and kw["properties"]["accepted_by"] == "Alex"
    assert "accepted by Alex" in kw["notes"] and kw["key_suffix"]


def test_an_entity_the_graph_already_holds_is_refused_so_nothing_is_overwritten(db, monkeypatch):
    from services import graph_entities
    monkeypatch.setattr(graph_entities, "same_name", lambda c, n: [dict(key="k", name=n)])
    with pytest.raises(proposals.ProposalError, match="already holds"):
        W.propose_entity(db, case_id=db.info["case"].id, name="Acme", entity_type="Company", summary="s",
                         citations=_cite(db), origin=_origin())
    assert db.scalars(select(WorkspaceAIOutput)).all() == []


def test_the_key_of_a_proposed_entity_cannot_meet_another_entitys():
    from services.graph_entities import entity_key
    assert entity_key("Acme Ltd") == "acme-ltd"
    assert entity_key("Acme Ltd", key_suffix="ab12cd34") == "acme-ltd-ab12cd34"


def test_an_entity_or_claim_with_no_citation_is_refused(db):
    with pytest.raises(proposals.ProposalError, match="cites"):
        W.propose_entity(db, case_id=db.info["case"].id, name="A", entity_type="Company", summary="s", citations=[],
                         origin=_origin(), _same=lambda c, n: [])


# ---- F: a code word stays a model reading until a person confirms it ------------------------------------------------

def test_a_person_confirms_a_term_in_their_own_words_and_the_model_reading_stays_visible(db, monkeypatch):
    monkeypatch.setattr(glossary, "_save_keyword_list", lambda *a: None)
    item = W.propose_term(db, case_id=db.info["case"].id, term="breakfast", meaning="a bribe", speaker="Sam",
                          citations=_cite(db), origin=_origin())
    assert db.scalars(select(CaseGlossaryTerm)).all() == []
    W.accept(db, case_id=db.info["case"].id, output_id=item["id"], reviewer=db.info["owner"],
             edits=dict(meaning="a cash payment to the official"))
    row = db.scalars(select(CaseGlossaryTerm)).one()
    out = glossary.term_out(row)
    assert out["meaning"] == "a cash payment to the official" and out["model_meaning"] == "a bribe"
    assert out["meaning_changed"] is True and out["confirmed_by"] == "Alex"
    assert out["reading_words"].startswith("A person's reading: confirmed by Alex")
    assert row.origin["origin"]["model"] == "DeepSeek V4 Pro"


def test_only_a_person_confirms_a_term_and_a_second_proposal_for_it_is_refused(db, monkeypatch):
    monkeypatch.setattr(glossary, "_save_keyword_list", lambda *a: None)
    item = W.propose_term(db, case_id=db.info["case"].id, term="Breakfast", meaning="m", citations=_cite(db),
                          origin=_origin())
    with pytest.raises(proposals.ProposalError) as refused:
        W.accept(db, case_id=db.info["case"].id, output_id=item["id"], reviewer=model_origin(
            for_name="Alex", model="m", model_id="m", how="x"))
    assert refused.value.status_code == 403
    W.accept(db, case_id=db.info["case"].id, output_id=item["id"], reviewer=db.info["owner"])
    with pytest.raises(proposals.ProposalError, match="already confirmed"):
        W.propose_term(db, case_id=db.info["case"].id, term="breakfast", meaning="m", citations=_cite(db),
                       origin=_origin())


def test_a_withdrawn_term_stays_listed_with_who_and_why(db, monkeypatch):
    monkeypatch.setattr(glossary, "_save_keyword_list", lambda *a: None)
    item = W.propose_term(db, case_id=db.info["case"].id, term="lunch", meaning="m", citations=_cite(db),
                          origin=_origin())
    W.accept(db, case_id=db.info["case"].id, output_id=item["id"], reviewer=db.info["owner"])
    row = db.scalars(select(CaseGlossaryTerm)).one()
    with pytest.raises(glossary.GlossaryError):
        glossary.withdraw(db, case_id=db.info["case"].id, term_id=row.id, reviewer=db.info["owner"], reason=" ")
    out = glossary.withdraw(db, case_id=db.info["case"].id, term_id=row.id, reviewer=db.info["owner"], reason="wrong")
    assert (out["status"], out["withdrawn_by"], out["withdrawn_reason"]) == ("withdrawn", "Alex", "wrong")
    assert glossary.read(None, db, db.info["case"].id, with_mentions=False)["total"] == 1


def test_a_refused_term_accept_goes_back_to_waiting(db, monkeypatch):
    item = W.propose_term(db, case_id=db.info["case"].id, term="dinner", meaning="m", citations=_cite(db),
                          origin=_origin())
    db.add(CaseGlossaryTerm(id=uuid.uuid4(), case_id=db.info["case"].id, term="dinner", meaning="x",
                            confirmed_by_name="Bo", confirmed_at=datetime.now(timezone.utc)))
    db.commit()
    with pytest.raises(proposals.ProposalError, match="already confirmed"):
        W.accept(db, case_id=db.info["case"].id, output_id=item["id"], reviewer=db.info["owner"])
    assert db.get(WorkspaceAIOutput, uuid.UUID(item["id"])).review_status == "pending_review"


def test_the_published_list_ships_with_the_code():
    from services.phone_analysis import monitoring_apps as MA
    doc = MA.load()
    assert len(doc["entries"]) >= 100 and doc["source"]["license"]


def test_no_list_is_stated_not_shown_as_a_clean_result(monkeypatch):
    from services.phone_analysis import monitoring_apps as MA
    monkeypatch.setattr(MA, "load", lambda data_dir=None: {"version": None, "source": None, "entries": []})
    monkeypatch.setattr(MA, "_edits", lambda s, c: [])
    monkeypatch.setattr(MA, "_installed", lambda c, i: ([], {"e": dict(phone="P", apps_read=3)}))
    monkeypatch.setattr(MA, "bank_control_events", lambda c, i: [])
    out = MA.indicators(None, None, uuid.uuid4())
    assert out["coverage"].startswith("No monitoring-app list is installed")


def test_a_draft_refuses_documents_and_interviews_together(db, monkeypatch):
    from types import SimpleNamespace as NS

    from services import workspace_ai_service as S
    from services.pattern_of_life import drafting
    case, owner = db.info["case"], db.info["owner"]
    monkeypatch.setattr(S, "_load_target", lambda *a, **k: NS(display_name="x"))
    monkeypatch.setattr(S.mandate_context_service, "active_version", lambda *a, **k: NS(id=uuid.uuid4()))
    monkeypatch.setattr(drafting, "check_subject", lambda *a: dict(subject={}))
    with pytest.raises(S.WorkspaceAIError, match="not both"):
        S.create_output(db, case_id=case.id, target_type="dossier", target_id=uuid.uuid4(), output_type="statement_claims",
                        requested_by=owner, interview_ids=[uuid.uuid4()], document_ids=[uuid.uuid4()], subject={})
