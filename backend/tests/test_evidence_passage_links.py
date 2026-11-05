"""A quote (evidence_passage link): several from one document, written by the server, kept as taken (lx-textbench C)."""
from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from postgres import link_types
from postgres.base import Base
from postgres.models.case import Case
from postgres.models.case_profile import CaseProfile
from postgres.models.collection_membership import CollectionMembership
from postgres.models.dossier import DossierLink
from postgres.models.activity_event import ActivityEvent
from postgres.models.evidence import EvidenceDocumentText, EvidenceFile
from postgres.models.user import User
from postgres.models.workspace_entry import WorkspaceEntry
from services import dossier_service, evidence_page_text as P, workspace_entry_service as W
from tests.test_dossier_service import TABLES as DOSSIER_TABLES
from tests.test_workspace_entry_service import ENTRY_TABLES

TABLES = list(dict.fromkeys(DOSSIER_TABLES + ENTRY_TABLES + [ActivityEvent.__table__, CollectionMembership.__table__,
                                                             EvidenceFile.__table__, EvidenceDocumentText.__table__]))
TEXT = "Paid to ACME Ltd\n\nWire to Globex"
VERSION = "b" * 64
LOCATIONS = [dict(kind="page", label="Page 1", page_number=1, start_char=0, end_char=16, extraction_method="native",
                  text_origin="digital_text_layer"),
             dict(kind="page", label="Page 2", page_number=2, start_char=18, end_char=32, ocr_status="success",
                  extraction_method="tesseract_ocr", text_origin="recognised_glyphs", ocr_confidence=88.0)]


class World:
    pass


@pytest.fixture()
def world():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True, connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine, tables=TABLES)
    w = World()
    w.factory = sessionmaker(bind=engine, expire_on_commit=False)
    w.owner, w.case_id, w.dossier_id, w.entry_id, w.file_id = (uuid.uuid4() for _ in range(5))
    with w.factory() as db:
        db.add(User(id=w.owner, email="owner@example.test", name="Owner", password_hash="x"))
        db.flush()
        db.add(Case(id=w.case_id, title="Case", created_by_user_id=w.owner, owner_user_id=w.owner))
        db.flush()
        db.add(CaseProfile(id=w.dossier_id, case_id=w.case_id, display_name="Subject", profile_type="person",
                           created_by_user_id=w.owner, updated_by_user_id=w.owner))
        db.add(WorkspaceEntry(id=w.entry_id, case_id=w.case_id, entry_type="note", body="synthetic",
                              author_user_id=w.owner))
        db.add(EvidenceFile(id=w.file_id, case_id=w.case_id, original_filename="s.pdf", stored_path="/tmp/s.pdf", size=1,
                            sha256="a" * 64, status="processed"))
        db.add(EvidenceDocumentText(evidence_file_id=w.file_id, content=TEXT, content_sha256=VERSION,
                                    character_count=len(TEXT), source_locations=LOCATIONS))
        db.commit()
    with patch.object(dossier_service, "check_case_access", return_value=(None, None)), \
            patch.object(dossier_service, "get_case_if_allowed", return_value=None):
        yield w
    engine.dispose()


def _link(w, start, end, **extra):
    return {"target_type": "evidence_passage", "target_id": P.passage_id(w.file_id, VERSION, start, end), **extra}


def _reread(db, w):
    text = db.get(EvidenceDocumentText, w.file_id)
    text.content, text.content_sha256, text.character_count = "new reading", "c" * 64, 11
    text.source_locations = []
    db.commit()


def test_the_type_is_in_the_registry_for_findings_notes_and_dossiers():
    assert "evidence_passage" in link_types.WORKSPACE_TYPES
    assert "evidence_passage" in link_types.DOSSIER_TYPES
    assert "evidence_passage" in link_types.NOTEBOOK_TYPES
    assert "evidence_passage" not in link_types.TASK_TYPES


def test_a_finding_holds_two_quotes_of_one_document(world):
    with world.factory() as db:
        user = db.get(User, world.owner)
        out = W.batch_add_entry_links(db, case_id=world.case_id, entry_id=world.entry_id, current_user=user,
                                      links=[_link(world, 0, 4), _link(world, 18, 22)], rationale="Added from text")
        assert out["added"] == 2
        links = {link.source_anchor["quote"]: link for link in db.get(WorkspaceEntry, world.entry_id).links}
    assert set(links) == {"Paid", "Wire"}
    assert links["Wire"].source_anchor["reader"]["kind"] == "ocr"


def test_a_quote_added_to_a_finding_keeps_the_ocr_label_and_ignores_what_the_client_sent(world):
    forged = _link(world, 18, 22, target_label="A person's reading", source_anchor={"quote": "Forged", "reader": None})
    with world.factory() as db:
        W.batch_add_entry_links(db, case_id=world.case_id, entry_id=world.entry_id, current_user=db.get(User, world.owner),
                                links=[forged], rationale="x")
        link = db.get(WorkspaceEntry, world.entry_id).links[0]
    assert link.source_anchor["quote"] == "Wire"
    assert link.source_anchor["reader"]["machine_read"] is True
    assert "OCR" in link.target_label and "A person" not in link.target_label


def test_a_refused_quote_reaches_the_person_in_words(world):
    with world.factory() as db, pytest.raises(W.WorkspaceEntryValidationError, match="one page"):
        W.batch_add_entry_links(db, case_id=world.case_id, entry_id=world.entry_id, current_user=db.get(User, world.owner),
                                links=[_link(world, 10, 22)], rationale="x")


def test_a_dossier_holds_quotes_written_by_the_server(world):
    with world.factory() as db:
        user = db.get(User, world.owner)
        out = dossier_service.add_links(db, dossier_id=world.dossier_id, user=user, links=[
            _link(world, 0, 4, label="forged", source_anchor={"quote": "Forged"}), _link(world, 18, 22)])
        assert out["added"] == 2
        rows = db.scalars(select(DossierLink).where(DossierLink.dossier_id == world.dossier_id)).all()
    assert {row.source_anchor["quote"] for row in rows} == {"Paid", "Wire"}
    assert all("forged" not in (row.label or "") for row in rows)


def test_an_assessment_cannot_carry_a_forged_quote(world):
    from postgres.models.dossier import DossierAssessmentLink
    with world.factory() as db:
        user = db.get(User, world.owner)
        dossier_service.create_assessment(db, dossier_id=world.dossier_id, user=user, data={
            "category": "c", "content": "c", "supporting_links": [_link(world, 18, 22, label="A person's reading",
                                                                       source_anchor={"quote": "Forged"})]})
        row = db.scalars(select(DossierAssessmentLink)).one()
    assert row.source_anchor["quote"] == "Wire"
    assert "OCR" in row.label and "A person" not in row.label


def test_a_theory_with_a_quote_still_converts_after_the_document_was_read_again(world):
    with world.factory() as db:
        user = db.get(User, world.owner)
        theory = WorkspaceEntry(id=uuid.uuid4(), case_id=world.case_id, entry_type="theory", title="T", body="b",
                                lifecycle_state="proposed", author_user_id=world.owner)
        db.add(theory)
        db.commit()
        W.batch_add_entry_links(db, case_id=world.case_id, entry_id=theory.id, current_user=user,
                                links=[_link(world, 18, 22)], rationale="x")
        db.expire_all()
        entry = db.get(WorkspaceEntry, theory.id)
        taken = dict(entry.links[0].source_anchor)
        _reread(db, world)
        out = W.convert_theory_to_finding(db, case_id=world.case_id, theory_id=theory.id, current_user=user,
                                          expected_version=entry.version, title="F", significance="low")
        db.expire_all()
        finding = next(e for e in db.scalars(select(WorkspaceEntry).where(WorkspaceEntry.entry_type == "finding")))
        assert out and [link.source_anchor for link in finding.links] == [taken]


def test_a_kept_quote_survives_the_finding_being_saved_after_the_document_was_read_again(world):
    with world.factory() as db:
        user = db.get(User, world.owner)
        W.batch_add_entry_links(db, case_id=world.case_id, entry_id=world.entry_id, current_user=user,
                                links=[_link(world, 18, 22)], rationale="x")
        entry = db.get(WorkspaceEntry, world.entry_id)
        before = dict(entry.links[0].source_anchor)
        _reread(db, world)
        W._replace_links(db, entry, user, [{"target_type": "evidence_passage", "target_id": entry.links[0].target_id,
                                            "source_anchor": {}, "relationship": "supports"}])
        db.commit()
        link = db.get(WorkspaceEntry, world.entry_id).links[0]
    assert link.source_anchor == before
    assert link.relationship_type == "supports"


def test_a_kept_quote_survives_a_dossier_being_saved_after_the_document_was_read_again(world):
    with world.factory() as db:
        user = db.get(User, world.owner)
        dossier_service.add_links(db, dossier_id=world.dossier_id, user=user, links=[_link(world, 18, 22)])
        row = db.scalars(select(DossierLink)).one()
        before, label = dict(row.source_anchor), row.label
        _reread(db, world)
        dossier_service.replace_links(db, dossier_id=world.dossier_id, user=user, links=[
            {"target_type": "evidence_passage", "target_id": row.target_id, "source_anchor": {}, "label": "x"}])
        row = db.scalars(select(DossierLink)).one()
    assert row.source_anchor == before and row.label == label


def test_updating_a_link_cannot_rewrite_the_quote(world):
    with world.factory() as db:
        user = db.get(User, world.owner)
        W.batch_add_entry_links(db, case_id=world.case_id, entry_id=world.entry_id, current_user=user,
                                links=[_link(world, 18, 22)], rationale="x")
        entry = db.get(WorkspaceEntry, world.entry_id)
        link = entry.links[0]
        W.update_entry_link(db, case_id=world.case_id, entry_id=world.entry_id, link_id=link.id, current_user=user,
                            expected_version=entry.version, relationship="context", source_anchor={"quote": "Forged"})
        assert db.get(WorkspaceEntry, world.entry_id).links[0].source_anchor["quote"] == "Wire"


def test_the_kept_anchor_is_found_by_its_target_and_only_for_its_document(world):
    with world.factory() as db:
        W.batch_add_entry_links(db, case_id=world.case_id, entry_id=world.entry_id, current_user=db.get(User, world.owner),
                                links=[_link(world, 18, 22)], rationale="x")
        record = db.get(EvidenceFile, world.file_id)
        target = P.passage_id(world.file_id, VERSION, 18, 22)
        assert P.kept_passage_anchor(db, record, target)["quote"] == "Wire"
        assert P.kept_passage_anchor(db, record, P.passage_id(world.file_id, VERSION, 0, 4)) is None
        assert P.kept_passage_anchor(db, record, f"{uuid.uuid4()}:x:18:22") is None


def test_a_report_prints_the_whole_quote_with_what_read_it():
    from services.casework_report import _link_words
    quote = "word " * 60
    link = {"target_type": "evidence_passage", "target_label": "short…", "source_anchor": {
        "quote": quote, "document_name": "s.pdf", "page_label": "Page 2",
        "reader": {"words": "Read by OCR software"}}}
    assert _link_words(link) == f"“{quote}”, s.pdf, Page 2 · Read by OCR software"
    assert _link_words({"target_type": "evidence", "target_label": "s.pdf"}) == "s.pdf"
