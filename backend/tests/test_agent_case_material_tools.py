"""The agent's readers for the case material it had no tool for (lx-agentlive G/H): evidence files and their
processing state, interviews and transcripts, the dossier list, one theory with its additions and narratives, the
Significant layer, saved reports, every decision of the case, and casework by tag.

Each test runs the tool layer the model calls (make_agent_tools with the run's case) on the financial suite's SQLite
harness, with a second case beside it, so a leak from one case to the other has somewhere to go. The last tests run
the agent runner itself with a scripted model that calls each type's tool, and check the registry the agent's help
is built from. Every test fails on code without these tools.
"""
from __future__ import annotations

import json
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest import mock

from postgres.base import Base
from postgres.models.case_deadline import CaseDeadline
from postgres.models.case_profile import CaseProfile
from postgres.models.case_selection import CaseSelection
from postgres.models.collection_membership import CollectionMembership
from postgres.models.dossier import (DossierAssessment, DossierAssessmentLink, DossierInterview,
                                     DossierInterviewEvidenceLink, DossierLink, DossierMedia, DossierRole)
from postgres.models.enums import AdjudicationDecision, AdjudicationSubject
from postgres.models.evidence import EvidenceFile
from postgres.models.significant import SignificantEntity
from postgres.models.theory_narrative import TheoryNarrative
from postgres.models.transcript import TranscriptRevision, TranscriptSource, TranscriptState
from postgres.models.work import CaseTask
from postgres.models.workspace_entry import (WorkspaceEntry, WorkspaceEntryEvent, WorkspaceEntryLink,
                                             WorkspaceEntryRevision, WorkspaceLegacyMapping)
from services import case_selections
from services.workspace_entry_service import create_entry
from tests.test_financial_duplicates import DuplicateTestCase

EXTRA = [CaseProfile, CaseDeadline, CaseTask, WorkspaceEntry, WorkspaceEntryRevision, WorkspaceEntryLink,
         WorkspaceEntryEvent, WorkspaceLegacyMapping, CaseSelection, CollectionMembership, TheoryNarrative,
         SignificantEntity, DossierRole, DossierLink, DossierAssessment, DossierAssessmentLink, DossierMedia,
         DossierInterview, DossierInterviewEvidenceLink, TranscriptSource, TranscriptRevision, TranscriptState]


class CaseMaterialToolTests(DuplicateTestCase):
    def setUp(self):
        super().setUp()
        Base.metadata.create_all(self.engine, tables=[m.__table__ for m in EXTRA])
        self.graph = {str(self.case.id): {"person:ann", "company:acme"}, str(self.other_case.id): {"person:zed"}}
        patcher = mock.patch.object(case_selections, "graph_keys_in_case",
                                    side_effect=lambda case_id, keys: {k for k in keys
                                                                       if k in self.graph.get(case_id, set())})
        patcher.start()
        self.addCleanup(patcher.stop)
        names = mock.patch("services.agent.tools._lookup_entity_names_and_kinds",
                           side_effect=lambda case_id, keys: {k: {"name": k.split(":")[1].title(),
                                                                 "type": "Person" if k.startswith("person") else "Company"}
                                                             for k in keys if k in self.graph.get(case_id, set())})
        names.start()
        self.addCleanup(names.stop)

    # -- helpers ---------------------------------------------------------------------------------------------------

    def session(self):
        @contextmanager
        def factory():
            with self.SessionLocal() as s:
                yield s
        return factory

    def tools(self, case_id=None, allowed=None):
        from services.agent.tools import AgentToolContext, make_agent_tools
        ctx = AgentToolContext(case_id=str(case_id or self.case.id), ledger_session_factory=self.session(),
                               allowed_entity_keys=allowed)
        return {t.name: t for t in make_agent_tools(ctx)}

    def call(self, tool_name, case_id=None, allowed=None, **args):
        if tool_name == "get_casework":  # its phone link states are read with PostgreSQL arrays; none here
            with mock.patch("services.phone.link_states.entry_links", return_value=[]), \
                    mock.patch("services.phone.link_states.for_readers", return_value={}):
                return self.tools(case_id, allowed)[tool_name].invoke(args)
        return self.tools(case_id, allowed)[tool_name].invoke(args)

    def file(self, name, *, status="processed", case=None, error=None, source_type=None, transcription=None):
        f = EvidenceFile(id=uuid.uuid4(), case_id=(case or self.case).id, original_filename=name,
                         stored_path="/x/%s" % name, size=10, sha256=uuid.uuid4().hex * 2, status=status,
                         last_error=error, source_type=source_type, transcription=transcription)
        self.db.add(f)
        self.db.commit()
        return f

    def dossier(self, name, case=None):
        d = CaseProfile(id=uuid.uuid4(), case_id=(case or self.case).id, profile_type="person", display_name=name)
        self.db.add(d)
        self.db.commit()
        return d

    # -- evidence files ----------------------------------------------------------------------------------------------

    def test_evidence_files_counts_every_state_lists_failed_first_and_keeps_to_the_case(self):
        before = self.call("get_evidence_files")["data"]["counts_by_state"]
        self.file("a.pdf")
        self.file("b.pdf", status="unprocessed")
        self.file("c.pdf", status="failed", error="OCR failed on PDF page 3: Tesseract process timeout")
        self.file("thread.txt", source_type="phone_text")
        self.file("other.pdf", status="failed", case=self.other_case)
        out = self.call("get_evidence_files", limit=2)
        data = out["data"]
        counts = data["counts_by_state"]
        self.assertEqual(counts["failed"] - before["failed"], 1)
        self.assertEqual(counts["unprocessed"] - before["unprocessed"], 1)
        self.assertEqual(data["files_in_all"] - data["files_on_evidence_page"], 1)  # the phone conversation document
        self.assertIn("phone conversations", data["coverage"])
        first = data["items"][0]
        self.assertEqual((first["filename"], first["state"]), ("c.pdf", "failed"))
        self.assertIn("scanned page took too long", first["failure"])
        self.assertTrue(first["doc"].startswith("doc://"))
        self.assertEqual(data["returned"], 2)
        self.assertTrue(data["has_more"])
        self.assertEqual(data["next_offset"], 2)
        self.assertIn("read on with offset 2", data["limitation"])
        self.assertNotIn("other.pdf", [i["filename"] for i in data["items"]])
        named = self.call("get_evidence_files", name="b.pd")["data"]
        self.assertEqual([i["filename"] for i in named["items"]], ["b.pdf"])
        self.assertEqual(named["total_matching"], 1)
        self.assertIn("result_id", out)

    def test_evidence_files_are_refused_inside_the_significant_layer(self):
        out = self.call("get_evidence_files", allowed={"person:ann"})
        self.assertEqual(out["status"], "error")
        self.assertIn("Significant layer", out["summary"])

    # -- interviews and transcripts ----------------------------------------------------------------------------------

    def test_interviews_list_participants_notes_and_attached_files_and_transcripts(self):
        d = self.dossier("Jane Roe")
        f = self.file("notes.txt")
        interview = DossierInterview(id=uuid.uuid4(), dossier_id=d.id, case_id=self.case.id, status="completed",
                                     participants=["Jane Roe", {"name": "Our investigator", "role": "interviewed_by"}],
                                     working_notes="line one\nline two", date_value="2026-11-01")
        self.db.add(interview)
        self.db.flush()
        self.db.add(DossierInterviewEvidenceLink(id=uuid.uuid4(), interview_id=interview.id, case_id=self.case.id,
                                                 evidence_file_id=f.id))
        other = self.dossier("Zed", case=self.other_case)
        self.db.add(DossierInterview(id=uuid.uuid4(), dossier_id=other.id, case_id=self.other_case.id))
        self.db.commit()
        self.file("call.mp3", transcription="Hello, this is the call.")
        data = self.call("get_interviews")["data"]
        self.assertEqual(data["total_matching"], 1)
        item = data["items"][0]
        self.assertEqual((item["dossier"], item["status"], item["date"]), ("Jane Roe", "completed", "2026-11-01"))
        self.assertEqual(item["attached_files"][0]["doc"], "doc://%s" % f.id)
        self.assertIn("/dossiers?dossier=%s" % d.id, item["dossier_href"])
        self.assertEqual(data["transcripts"]["total"], 1)
        self.assertEqual(data["transcripts"]["items"][0]["review"], "machine transcript, not yet reviewed by a person")
        none = self.call("get_interviews", dossier="Nobody")["data"]
        self.assertFalse(none["available"])
        self.assertIn("Not in this case.", none["reason"])

    def test_transcript_reads_the_saved_revision_with_its_review_state_and_refuses_another_cases_file(self):
        f = self.file("call.mp3")
        src = TranscriptSource(id=uuid.uuid4(), evidence_file_id=f.id, case_id=self.case.id, engine_job_id="j1",
                               source_sha256="0" * 64, text="machine words", segments=[], metadata_={})
        self.db.add(src)
        self.db.flush()
        rev = TranscriptRevision(id=uuid.uuid4(), evidence_file_id=f.id, case_id=self.case.id, source_id=src.id,
                                 payload={"body_text": "corrected words " * 1000}, digest="d")
        self.db.add(rev)
        self.db.flush()
        self.db.add(TranscriptState(evidence_file_id=f.id, case_id=self.case.id, source_id=src.id,
                                    working_revision_id=rev.id, reviewed_revision_id=rev.id))
        self.db.commit()
        data = self.call("get_transcript", evidence=str(f.id))["data"]
        self.assertEqual(data["review"], "reviewed by a person")
        self.assertTrue(data["text"].startswith("corrected words"))
        self.assertEqual(data["characters"], len("corrected words " * 1000))
        self.assertTrue(data["has_more"])
        self.assertIn("read on with offset 12000", data["limitation"])
        rest = self.call("get_transcript", evidence=str(f.id), offset=12000)["data"]
        self.assertFalse(rest["has_more"])
        other = self.file("other.mp3", case=self.other_case, transcription="secret")
        refused = self.call("get_transcript", evidence=str(other.id))["data"]
        self.assertFalse(refused["available"])
        self.assertIn("Not in this case.", refused["reason"])

    # -- dossiers ----------------------------------------------------------------------------------------------------

    def test_list_dossiers_counts_what_each_holds(self):
        d = self.dossier("Jane Roe")
        self.dossier("Zed", case=self.other_case)
        self.db.add(DossierLink(id=uuid.uuid4(), dossier_id=d.id, case_id=self.case.id, target_type="evidence",
                                target_id=str(uuid.uuid4())))
        self.db.add(DossierInterview(id=uuid.uuid4(), dossier_id=d.id, case_id=self.case.id))
        self.db.commit()
        data = self.call("list_dossiers")["data"]
        self.assertEqual(data["total_matching"], 1)
        self.assertEqual({k: data["items"][0][k] for k in ("name", "links", "assessments", "interviews")},
                         {"name": "Jane Roe", "links": 1, "assessments": 0, "interviews": 1})

    # -- theories ----------------------------------------------------------------------------------------------------

    def test_theory_reads_every_addition_with_members_and_labels_a_models_narrative(self):
        from services import theory_additions as T
        theory = create_entry(self.db, case_id=self.case.id, current_user=self.user, entry_type="theory",
                              title="Acme pays Ann", body="Acme routes money to Ann")
        T.add(self.db, case_id=self.case.id, entry_id=theory["id"], user=self.user, surface="graph",
              why="the hub", items=[{"target_type": "graph_entity", "target_id": "person:ann", "target_label": "Ann"}])
        T.add(self.db, case_id=self.case.id, entry_id=theory["id"], user=self.user, surface="graph",
              group={"group_type": "graph_selection", "how": {"selection": "lasso"}, "words": "both",
                     "members": [{"type": "graph_entity", "id": "person:ann", "label": "Ann"},
                                 {"type": "graph_entity", "id": "company:acme", "label": "Acme"}]})
        self.db.add(TheoryNarrative(id=uuid.uuid4(), case_id=self.case.id, entry_id=uuid.UUID(theory["id"]),
                                    text="It fits.", origin="agent", model="stub-model", citations=[], basis={}))
        self.db.commit()
        create_entry(self.db, case_id=self.other_case.id, current_user=self.user, entry_type="theory",
                     title="Acme pays Zed", body="other matter")
        data = self.call("get_theory", theory="Acme pays")["data"]
        self.assertTrue(data["available"])
        item = data["items"][0]
        self.assertEqual(item["title"], "Acme pays Ann")
        self.assertEqual(len(item["additions"]), 2)
        self.assertEqual(item["additions"][0]["why"], "the hub")
        group = item["additions"][1]
        self.assertEqual((group["member_count"], group["members_shown"]), (2, 2))
        self.assertEqual(sorted(m["label"] for m in group["members"]), ["Acme", "Ann"])
        self.assertIn("Model reading", item["fit"]["words"])
        self.assertIn("not confirmed", item["fit"]["words"])
        self.assertIn("2 additions", data["coverage"])
        self.assertIn("/workspace?view=casework&kind=theory&entry=", item["href"])
        other = self.call("get_theory", theory="Acme pays Zed")["data"]
        self.assertFalse(other["available"])
        self.assertIn("Not in this case.", other["reason"])

    # -- significant layer -------------------------------------------------------------------------------------------

    def test_significant_layer_names_each_item_and_says_how_it_was_added(self):
        now = datetime(2026, 11, 8, tzinfo=timezone.utc)
        self.db.add_all([
            SignificantEntity(case_id=self.case.id, entity_key="person:ann", added_by_user_id=self.user.id,
                              addition_source="manual", context={}, created_at=now),
            SignificantEntity(case_id=self.case.id, entity_key="company:acme", addition_source="merge", context={},
                              created_at=now, removed_at=now),
            SignificantEntity(case_id=self.other_case.id, entity_key="person:zed", addition_source="manual",
                              context={}, created_at=now)])
        self.db.commit()
        for allowed in (None, {"person:ann"}):  # also inside the Significant layer itself
            data = self.call("get_significant_layer", allowed=allowed)["data"]
            self.assertEqual(data["total_matching"], 1)
            item = data["items"][0]
            self.assertEqual((item["name"], item["kind"], item["how_added"]), ("Ann", "Person", "added by a person"))
            self.assertEqual(item["added_by"], self.user.name)
            self.assertEqual(data["counts_by_kind"], {"Person": 1})

    def test_significant_layer_gives_the_keys_and_says_so_when_the_graph_cannot_be_read(self):
        self.db.add(SignificantEntity(case_id=self.case.id, entity_key="person:ann", addition_source="manual",
                                      context={}))
        self.db.commit()
        with mock.patch("services.agent.tools._lookup_entity_names_and_kinds", side_effect=RuntimeError("down")):
            data = self.call("get_significant_layer")["data"]
        self.assertEqual(data["items"][0]["entity_key"], "person:ann")
        self.assertIn("could not be read", data["names_note"])

    # -- reports, casework by tag ------------------------------------------------------------------------------------

    def test_reports_lists_saved_financial_reports_and_the_casework_report_sections(self):
        create_entry(self.db, case_id=self.case.id, current_user=self.user, entry_type="note", title="Q3 report",
                     body="Saved report text", tags=["financial-report"])
        create_entry(self.db, case_id=self.case.id, current_user=self.user, entry_type="note", title="plain",
                     body="a note")
        create_entry(self.db, case_id=self.other_case.id, current_user=self.user, entry_type="note",
                     title="other report", body="x", tags=["financial-report"])
        data = self.call("get_reports")["data"]
        self.assertEqual([i["title"] for i in data["items"]], ["Q3 report"])
        sections = {s["section"]: s["entries"] for s in data["casework_report"]["sections"]}
        self.assertEqual(sections, {"Findings": 0, "Theories": 0, "Notes": 2})
        tagged = self.call("get_casework", tag="financial-report")["data"]
        self.assertEqual([i["title"] for i in tagged["items"]], ["Q3 report"])
        self.assertIn("tagged financial-report", tagged["coverage"])
        self.assertIn("/workspace?view=casework&kind=note&entry=", tagged["items"][0]["href"])

    # -- decisions across the case ----------------------------------------------------------------------------------

    def test_decisions_without_a_subject_count_every_decision_by_who_and_by_model(self):
        from services.financial.decisions import Actor, record
        from services.financial.model_work import model_origin
        doc = self.make_document()
        period = self.make_period(doc)
        rows = [self.add_row(period, doc, amount=a) for a in (100_00, 200_00)]
        drafted = Actor(name=self.actor.name, email=self.actor.email, user_id=self.actor.user_id,
                        origin=model_origin(for_name=self.actor.name, model="Claude"))
        for row, actor in ((rows[0], self.actor), (rows[1], drafted)):
            record(self.db, case_id=self.case.id, subject=row, subject_type=AdjudicationSubject.transaction,
                   decision=AdjudicationDecision.set_counterparty_party, reason="linked", actor=actor,
                   before={"party": None}, after={"party": {"id": "p", "name": "P"}})
        self.db.commit()
        data = self.call("get_decisions")["data"]
        self.assertEqual(data["scope"], "whole case")
        self.assertEqual((data["total"], data["model_drafted"], data["person_decided"]), (2, 1, 1))
        self.assertEqual(data["counts_by_decision"], {"set_counterparty_party": 2})
        self.assertEqual(sorted(w["kind"] for w in data["counts_by_who"]), ["model", "person"])
        self.assertTrue(all(i["subject"].startswith("payment:") for i in data["items"]))
        other = self.call("get_decisions", case_id=self.other_case.id)["data"]
        self.assertEqual(other["total"], 0)

    # -- the runner, with a scripted model, reaches each type's tool --------------------------------------------------

    def test_a_scripted_run_reaches_each_new_types_tool_and_records_what_it_returned(self):
        from langchain_core.messages import AIMessage, HumanMessage
        from services.agent import capabilities as CAP, graph
        self.file("a.pdf")
        self.dossier("Jane Roe")
        create_entry(self.db, case_id=self.case.id, current_user=self.user, entry_type="theory", title="T one",
                     body="b")
        create_entry(self.db, case_id=self.case.id, current_user=self.user, entry_type="finding", title="F one",
                     body="b")
        self.db.add(SignificantEntity(case_id=self.case.id, entity_key="person:ann", addition_source="manual",
                                      context={}))
        self.db.commit()
        calls = {"evidence_files": ("get_evidence_files", {}), "interviews": ("get_interviews", {}),
                 "dossiers": ("list_dossiers", {}), "theories": ("get_theory", {"theory": "T one"}),
                 "significant": ("get_significant_layer", {}), "reports": ("get_reports", {}),
                 "findings": ("get_casework", {"kinds": ["finding"]}), "decisions": ("get_decisions", {})}
        for type_id, (tool, args) in calls.items():
            self.assertIn(tool, CAP.tools_for_type(type_id))

            class Model:
                step = 0

                def bind_tools(self, tools):
                    owner = self

                    class Bound:
                        def invoke(self, messages):
                            owner.step += 1
                            if owner.step == 1:
                                return AIMessage(content="", tool_calls=[{"id": "c1", "name": tool, "args": args}])
                            return AIMessage(content="answered")
                    return Bound()

                def invoke(self, messages):
                    return AIMessage(content="answered")

            runner = object.__new__(graph.AgentGraphRunner)
            runner.base_model, runner.model_id = Model(), "deepseek-v4-pro"
            with mock.patch("services.agent.tools._financial_session", self.session()), \
                    mock.patch("services.phone.link_states.entry_links", return_value=[]), \
                    mock.patch("services.phone.link_states.for_readers", return_value={}):
                out = runner.invoke(case_id=str(self.case.id), messages=[HumanMessage(content="q")])
            trace = out["tool_trace"]
            self.assertEqual([t["name"] for t in trace], [tool], type_id)
            self.assertEqual(trace[0]["status"], "success", (type_id, trace[0]))
            tool_message = [m for m in out["messages"] if getattr(m, "type", "") == "tool"][0]
            self.assertIs(json.loads(tool_message.content)["data"]["available"], True, type_id)

    def test_call_facts_records_totals_and_items_of_the_new_tools(self):
        from services.agent.run_record import call_facts
        self.file("a.pdf")
        self.file("b.pdf")
        out = self.call("get_evidence_files", limit=1)
        facts = call_facts("get_evidence_files", {"limit": 1}, out, None)
        self.assertEqual((facts["total"], facts["returned"]), (out["data"]["total_matching"], 1))
        self.assertEqual(facts["category"], "evidence")
        self.assertEqual(facts["next_page"]["tool"]["offset"], 1)
        self.assertEqual(facts["items"][0]["kind"], "document")
        self.assertEqual(facts["result_id"], out["result_id"])


def test_every_bound_tool_has_a_type_or_is_a_support_tool_and_every_type_tool_is_bound():
    from services.agent import capabilities as CAP
    from services.agent.tools import AgentToolContext, make_agent_tools
    bound = {t.name for t in make_agent_tools(AgentToolContext(case_id=str(uuid.uuid4()), all_cases=True))}
    typed = {name for t in CAP.DATA_TYPES for name in t["tools"]}
    assert sorted(bound - typed - set(CAP.SUPPORT_TOOLS)) == []
    assert sorted(typed - bound) == []
    assert sorted(set(CAP.SUPPORT_TOOLS) - bound) == []
    assert not typed & set(CAP.SUPPORT_TOOLS)
    for t in CAP.DATA_TYPES:
        assert t["tools"] and len(t["examples"]) >= 3, t["id"]


def test_the_help_names_every_type_in_plain_words_and_no_tool():
    import re
    from services.agent import capabilities as CAP
    help_ = CAP.capabilities()
    assert [t["id"] for t in help_["types"]] == [t["id"] for t in CAP.DATA_TYPES]
    words = " ".join(" ".join([t["label"], t["description"], *t["examples"]]) for t in help_["types"])
    every_tool = {n for t in CAP.DATA_TYPES for n in t["tools"]} | set(CAP.SUPPORT_TOOLS)
    assert not [n for n in every_tool if n in words]
    assert not re.search(r"\b\w+_\w+\b", words)  # no snake_case words on screen
    assert "—" not in words
    for t in help_["types"]:
        assert set(t) == {"id", "label", "description", "examples"}
    assert [t["id"] for t in CAP.capabilities(["get_timeline_events"])["types"]] == ["timeline"]


def test_the_coverage_question_set_covers_every_type_three_times_per_case():
    """The repository holds the Verification case's questions; a real case's are case material and live outside
    it, and are checked the same way where they are present."""
    import json
    import os
    from pathlib import Path
    from services.agent import capabilities as CAP
    files = [Path(__file__).resolve().parents[2] / "scripts" / "agent_coverage_questions.json"]
    real = Path(os.environ.get("LOUPE_AGENT_COVERAGE_REAL", "/mnt/owl-data/agent-coverage/questions-real.json"))
    if real.exists():
        files.append(real)
    for f in files:
        data = json.loads(f.read_text())
        for case in data["cases"]:
            for t in CAP.DATA_TYPES:
                n = sum(1 for q in data["questions"] if q["case"] == case and q["type"] == t["id"])
                assert n >= 3, (f.name, case, t["id"], n)
        assert {q["type"] for q in data["questions"]} <= set(CAP.BY_ID)


def test_the_capabilities_endpoint_serves_the_registry():
    from routers.agent import list_agent_capabilities
    from services.agent import capabilities as CAP
    out = list_agent_capabilities(current_user=None)
    assert out["schema"] == CAP.SCHEMA
    assert [t["id"] for t in out["types"]] == [t["id"] for t in CAP.DATA_TYPES]
