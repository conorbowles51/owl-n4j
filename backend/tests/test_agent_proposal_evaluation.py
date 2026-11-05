"""Agent evaluation set, proposals (agent-proposals G): questions with known outcomes, measured through the agent's
own proposal tools (the StructuredTool layer the model calls, with the run's case and proposer).

Each question is a tool call the model would make when a person asks it to propose work, and its known outcome is
written by hand: recorded as a proposal waiting for a person, or refused in the stated words with nothing recorded.
Throughout, nothing in the Workspace or the calculation changes until a person accepts. Set LOUPE_AGENT_EVAL_OUT to a
file path to write one JSON line per question. Synthetic data only (SQLite).
"""
from __future__ import annotations

import json
import os
import uuid
from contextlib import contextmanager

import pytest
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import sessionmaker

from postgres.base import Base
from postgres.models.agent_evidence import CaseGlossaryTerm
from postgres.models.agent_proposals import AgentProposalSourceOpen, ProceedsCalculation
from postgres.models.case import Case
from postgres.models.case_context import CaseContext, CaseMandateVersion
from postgres.models.evidence import EvidenceFile
from postgres.models.financial_judgements import FinancialJudgement
from postgres.models.user import User
from postgres.models.workspace_ai import WorkspaceAIOutput
from postgres.models.workspace_entry import (WorkspaceEntry, WorkspaceEntryEvent, WorkspaceEntryLink,
                                             WorkspaceEntryRevision, WorkspaceLegacyMapping)
from services.agent import proposal_tools
from services.agent.tools import AgentToolContext

TABLES = [User.__table__, Case.__table__, CaseMandateVersion.__table__, CaseContext.__table__, EvidenceFile.__table__,
          WorkspaceEntry.__table__, WorkspaceEntryRevision.__table__, WorkspaceEntryLink.__table__,
          WorkspaceEntryEvent.__table__, WorkspaceAIOutput.__table__, AgentProposalSourceOpen.__table__,
          FinancialJudgement.__table__, ProceedsCalculation.__table__, WorkspaceLegacyMapping.__table__,
          CaseGlossaryTerm.__table__]
NOT_IN_CASE = "Not in this case."


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("eval")
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine, tables=TABLES)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as s:
        owner = User(email="eval@example.test", name="Eval Person", password_hash="x")
        s.add(owner)
        s.flush()
        case = Case(title="Eval case", created_by_user_id=owner.id, owner_user_id=owner.id)
        other = Case(title="Other case", created_by_user_id=owner.id, owner_user_id=owner.id)
        s.add_all([case, other])
        s.flush()
        doc = EvidenceFile(case_id=case.id, original_filename="march.pdf", stored_path=str(tmp / "m.pdf"), size=1,
                           sha256="a" * 64, status="processed", created_by_id=owner.id)
        foreign = EvidenceFile(case_id=other.id, original_filename="elsewhere.pdf", stored_path=str(tmp / "e.pdf"),
                               size=1, sha256="b" * 64, status="processed", created_by_id=owner.id)
        s.add_all([doc, foreign])
        s.flush()
        entry = WorkspaceEntry(case_id=case.id, entry_type="theory", title="Cash moves after deposits", body="x",
                               tags=[], lifecycle_state="proposed", review_state="accepted", author_user_id=owner.id, author_email=owner.email, author_name=owner.name, updated_by_user_id=owner.id, updated_by_email=owner.email)
        foreign_entry = WorkspaceEntry(case_id=other.id, entry_type="theory", title="Elsewhere", body="y",
                                       tags=[], lifecycle_state="proposed", review_state="accepted", author_user_id=owner.id, author_email=owner.email, author_name=owner.name, updated_by_user_id=owner.id, updated_by_email=owner.email)
        calc = ProceedsCalculation(id=uuid.uuid4(), case_id=case.id, title="Line A", currency="MXN",
                                   deposit_categories=[], created_by="Eval Person")
        foreign_calc = ProceedsCalculation(id=uuid.uuid4(), case_id=other.id, title="Line B", currency="MXN",
                                           deposit_categories=[], created_by="Eval Person")
        s.add_all([entry, foreign_entry, calc, foreign_calc])
        s.execute(text("CREATE TABLE pv_record (case_id TEXT, record_uid TEXT)"))
        rec, foreign_rec = uuid.uuid4(), uuid.uuid4()
        s.execute(text("INSERT INTO pv_record VALUES (:c, :u), (:o, :f)"),
                  dict(c=str(case.id), u=str(rec), o=str(other.id), f=str(foreign_rec)))
        s.commit()
        ids = dict(case=case.id, other=other.id, owner=owner.id, doc=doc.id, foreign=foreign.id, entry=entry.id,
                   foreign_entry=foreign_entry.id, calc=calc.id, foreign_calc=foreign_calc.id, rec=rec,
                   foreign_rec=foreign_rec)
    yield dict(factory=factory, ids=ids)
    engine.dispose()


def _tools(world, monkeypatch, *, can_propose=True, proposer=True):
    @contextmanager
    def session():
        with world["factory"]() as s:
            yield s
    monkeypatch.setattr(proposal_tools, "_write_session", session)
    who = dict(for_name="Eval Person", for_user_id=str(world["ids"]["owner"]), model="DeepSeek V4 Pro",
               model_id="deepseek-v4-pro", run_id=str(uuid.uuid4()), can_propose=can_propose)
    context = AgentToolContext(case_id=str(world["ids"]["case"]), proposer=who if proposer else None)
    return {t.name: t for t in proposal_tools.make_proposal_tools(context)}


def _count(world, model):
    with world["factory"]() as s:
        return s.scalar(select(func.count()).select_from(model))


# (id, question, tool, args(ids) -> dict, setting, expected: 'recorded' | refusal text)
QUESTIONS = [
    ("P1", "Draft a finding about the March statement, citing page 3.", "propose_workspace_entry",
     lambda i: dict(entry_type="finding", title="Cash out after each deposit", body="Each deposit is followed by a "
                    "cash withdrawal.", citations=[f"doc://{i['doc']}/3"]), "edit", "recorded"),
    ("P2", "Draft a note citing a file that belongs to another case.", "propose_workspace_entry",
     lambda i: dict(entry_type="note", title="Elsewhere", body="From another case.",
                    citations=[f"doc://{i['foreign']}/1"]), "edit", NOT_IN_CASE),
    ("P3", "Draft a note citing a phone record of this case.", "propose_workspace_entry",
     lambda i: dict(entry_type="note", title="The alert", body="The bank alert of 2 March.",
                    citations=[f"rec://{i['rec']}"]), "edit", "recorded"),
    ("P4", "Draft a note citing a phone record of another case.", "propose_workspace_entry",
     lambda i: dict(entry_type="note", title="Their alert", body="Another case's alert.",
                    citations=[f"rec://{i['foreign_rec']}"]), "edit", NOT_IN_CASE),
    ("P5", "Propose linking the March statement to the theory as supporting.", "propose_link",
     lambda i: dict(entry_id=str(i["entry"]), target_type="evidence", target_id=str(i["doc"]),
                    relationship="supports", why="Page 3 shows the withdrawals.",
                    citations=[f"doc://{i['doc']}/3"]), "edit", "recorded"),
    ("P6", "Propose a link on another case's theory.", "propose_link",
     lambda i: dict(entry_id=str(i["foreign_entry"]), target_type="evidence", target_id=str(i["doc"]),
                    relationship="context", why="x", citations=[f"doc://{i['doc']}/3"]), "edit", NOT_IN_CASE),
    ("P7", "Propose a price per deal for the proceeds calculation.", "propose_assumption",
     lambda i: dict(calculation_id=str(i["calc"]), key="price_per_deal", low="300", high="500",
                    source=f"doc://{i['doc']}/3", why="The price list on page 3."), "edit", "recorded"),
    ("P8", "Propose an assumption on another case's calculation.", "propose_assumption",
     lambda i: dict(calculation_id=str(i["foreign_calc"]), key="messages", low="10", high="20", source="x",
                    why="x"), "edit", NOT_IN_CASE),
    ("P9", "Draft a finding for a person who can only view the case.", "propose_workspace_entry",
     lambda i: dict(entry_type="finding", title="View only", body="x", citations=[f"doc://{i['doc']}/3"]),
     "view", "can view this case but not change it"),
    ("P10", "Draft a finding in a run that cannot propose.", "propose_workspace_entry",
     lambda i: dict(entry_type="finding", title="No proposer", body="x", citations=[f"doc://{i['doc']}/3"]),
     "none", "This run cannot record proposals."),
    # agent-evidence-rest D, F (the claim tool is measured on PostgreSQL: tests/test_agent_evidence_phone.py)
    ("P11", "Propose the pickup code in the schedule as an entity.", "propose_entity",
     lambda i: dict(name="Pickup 7741", entity_type="Document", summary="A pickup code on page 3.",
                    citations=[f"doc://{i['doc']}/3"]), "edit", "recorded"),
    ("P12", "Propose an entity citing another case's file.", "propose_entity",
     lambda i: dict(name="Elsewhere Ltd", entity_type="Company", summary="From another case.",
                    citations=[f"doc://{i['foreign']}/1"]), "edit", NOT_IN_CASE),
    ("P13", "Propose an entity the graph already holds.", "propose_entity",
     lambda i: dict(name="Already There", entity_type="Company", summary="x", citations=[f"doc://{i['doc']}/3"]),
     "edit", "already holds"),
    ("P14", "Propose what \"breakfast\" means in these messages.", "propose_glossary_term",
     lambda i: dict(term="breakfast", meaning="A cash payment.", citations=[f"rec://{i['rec']}"]), "edit", "recorded"),
    ("P15", "Propose a code word from another case's message.", "propose_glossary_term",
     lambda i: dict(term="lunch", meaning="x", citations=[f"rec://{i['foreign_rec']}"]), "edit", NOT_IN_CASE),
    ("P16", "Propose a code word for a person who can only view the case.", "propose_glossary_term",
     lambda i: dict(term="dinner", meaning="x", citations=[f"rec://{i['rec']}"]), "view",
     "can view this case but not change it"),
]
_ROWS = []


@pytest.mark.parametrize("qid,question,tool,args,setting,expected", QUESTIONS, ids=[q[0] for q in QUESTIONS])
def test_proposal_question(world, monkeypatch, qid, question, tool, args, setting, expected):
    tools = _tools(world, monkeypatch, can_propose=setting == "edit", proposer=setting != "none")
    from services import graph_entities
    monkeypatch.setattr(graph_entities, "same_name", lambda case, name: (
        [dict(key="already", name=name)] if name == "Already There" else []))
    before = dict(outputs=_count(world, WorkspaceAIOutput), calls=_count(world, FinancialJudgement),
                  entries=_count(world, WorkspaceEntry), links=_count(world, WorkspaceEntryLink))
    out = tools[tool].invoke(args(world["ids"]))
    after = dict(outputs=_count(world, WorkspaceAIOutput), calls=_count(world, FinancialJudgement),
                 entries=_count(world, WorkspaceEntry), links=_count(world, WorkspaceEntryLink))
    recorded = out["status"] == "success" and (out.get("data") or {}).get("recorded") is True
    added = sum(after[k] - before[k] for k in ("outputs", "calls"))
    # The Workspace itself never changes on a proposal: no entry, no link, until a person accepts.
    unchanged = after["entries"] == before["entries"] and after["links"] == before["links"]
    if expected == "recorded":
        ok = recorded and added == 1 and unchanged
    else:
        ok = (not recorded) and added == 0 and unchanged and expected in json.dumps(out)
    _ROWS.append(dict(id=qid, question=question, tool=tool, setting=setting, expected=expected, recorded=recorded,
                      proposals_added=added, workspace_unchanged=unchanged, passed=ok))
    if tool == "propose_assumption" and recorded:
        data = out["data"]["proposal"]
        assert (data["status"], data["used_in_result"]) == ("open", False)
        with world["factory"]() as s:
            row = s.get(FinancialJudgement, uuid.UUID(data["id"]))
            assert (row.origin, row.strength) == ("agent", "inferred")
    assert ok, out


def test_write_the_measured_table():
    path = os.environ.get("LOUPE_AGENT_EVAL_OUT")
    if path and _ROWS:
        with open(path, "w", encoding="utf-8") as fh:
            for row in _ROWS:
                fh.write(json.dumps(row) + "\n")
