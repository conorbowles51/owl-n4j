from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from postgres.base import Base
from postgres.models.case import Case
from postgres.models.case_context import CaseContext, CaseMandateVersion
from postgres.models.case_profile import CaseProfile
from postgres.models.dossier import (
    DossierAssessment,
    DossierAssessmentLink,
    DossierInterview,
    DossierInterviewEvidenceLink,
)
from postgres.models.evidence import EvidenceDocumentText, EvidenceFile
from postgres.models.user import User
from postgres.models.workspace_ai import WorkspaceAIOutput
from postgres.models.workspace_entry import (
    WorkspaceEntry,
    WorkspaceEntryEvent,
    WorkspaceEntryLink,
    WorkspaceEntryRevision,
)
from services import workspace_ai_service


TABLES = [
    User.__table__,
    Case.__table__,
    CaseMandateVersion.__table__,
    CaseContext.__table__,
    EvidenceFile.__table__,
    EvidenceDocumentText.__table__,
    WorkspaceEntry.__table__,
    WorkspaceEntryRevision.__table__,
    WorkspaceEntryLink.__table__,
    WorkspaceEntryEvent.__table__,
    CaseProfile.__table__,
    DossierInterview.__table__,
    DossierInterviewEvidenceLink.__table__,
    WorkspaceAIOutput.__table__,
    DossierAssessment.__table__,
    DossierAssessmentLink.__table__,
]


@pytest.fixture()
def ai_db(tmp_path):
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine, tables=TABLES)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        owner = User(email="owner@example.test", name="Owner", password_hash="x")
        reviewer = User(email="reviewer@example.test", name="Reviewer", password_hash="x")
        db.add_all([owner, reviewer])
        db.flush()
        case = Case(title="AI Case", created_by_user_id=owner.id, owner_user_id=owner.id)
        other_case = Case(title="Other", created_by_user_id=owner.id, owner_user_id=owner.id)
        db.add_all([case, other_case])
        db.flush()
        mandate = CaseMandateVersion(
            case_id=case.id,
            version_number=1,
            objective="Test the witness account without assuming it is accurate.",
            key_questions=["What changed?"],
            author_user_id=owner.id,
        )
        db.add(mandate)
        db.flush()
        db.add(
            CaseContext(
                case_id=case.id,
                active_template_key="generic",
                active_mandate_version_id=mandate.id,
                created_by_user_id=owner.id,
            )
        )
        dossier = CaseProfile(
            case_id=case.id,
            profile_type="person",
            display_name="Alex Witness",
            status="active",
            linkage_state="unlinked",
            created_by_user_id=owner.id,
            updated_by_user_id=owner.id,
        )
        theory = WorkspaceEntry(
            case_id=case.id,
            entry_type="theory",
            title="Vehicle left before midnight",
            body="The blue vehicle left the yard before midnight.",
            tags=[],
            lifecycle_state="investigating",
            confidence=50,
            review_state="accepted",
            author_user_id=owner.id,
            author_email=owner.email,
            author_name=owner.name,
            updated_by_user_id=owner.id,
            updated_by_email=owner.email,
            updated_by_name=owner.name,
        )
        db.add_all([dossier, theory])
        db.flush()

        pdf = EvidenceFile(
            case_id=case.id,
            original_filename="first-statement.pdf",
            stored_path=str(tmp_path / "first-statement.pdf"),
            size=100,
            sha256="a" * 64,
            status="processed",
            created_by_id=owner.id,
        )
        audio = EvidenceFile(
            case_id=case.id,
            original_filename="follow-up.mp3",
            stored_path=str(tmp_path / "follow-up.mp3"),
            size=200,
            sha256="b" * 64,
            status="processed",
            transcription="At first I said ten. It may have been after midnight.",
            transcription_segments=[
                {"id": "seg-1", "start": 12.5, "end": 18.0, "speaker": "Witness", "text": "At first I said ten."},
                {"id": "seg-2", "start": 18.0, "end": 25.0, "speaker": "Witness", "text": "It may have been after midnight."},
            ],
            created_by_id=owner.id,
        )
        support = EvidenceFile(
            case_id=case.id,
            original_filename="gate-log.txt",
            stored_path=str(tmp_path / "gate-log.txt"),
            size=80,
            sha256="c" * 64,
            status="processed",
            created_by_id=owner.id,
        )
        contradiction = EvidenceFile(
            case_id=case.id,
            original_filename="camera-note.txt",
            stored_path=str(tmp_path / "camera-note.txt"),
            size=90,
            sha256="d" * 64,
            status="processed",
            created_by_id=owner.id,
        )
        foreign = EvidenceFile(
            case_id=other_case.id,
            original_filename="foreign.txt",
            stored_path=str(tmp_path / "foreign.txt"),
            size=10,
            sha256="e" * 64,
            status="processed",
            created_by_id=owner.id,
        )
        db.add_all([pdf, audio, support, contradiction, foreign])
        db.flush()
        pdf_text = "The witness said the blue vehicle left at ten in the evening. A receipt was mentioned."
        support_text = "The gate log confirms the blue vehicle left the yard at 22:04 before midnight."
        contradiction_text = "The camera timestamp shows the blue vehicle in the yard at 00:12, which conflicts with an early departure."
        db.add_all(
            [
                EvidenceDocumentText(
                    evidence_file_id=pdf.id,
                    content=pdf_text,
                    content_sha256="1" * 64,
                    character_count=len(pdf_text),
                    source_locations=[{"start_char": 0, "end_char": len(pdf_text), "page_number": 3}],
                ),
                EvidenceDocumentText(
                    evidence_file_id=support.id,
                    content=support_text,
                    content_sha256="2" * 64,
                    character_count=len(support_text),
                    source_locations=[{"start_char": 0, "end_char": len(support_text), "page_number": 1}],
                ),
                EvidenceDocumentText(
                    evidence_file_id=contradiction.id,
                    content=contradiction_text,
                    content_sha256="3" * 64,
                    character_count=len(contradiction_text),
                    source_locations=[{"start_char": 0, "end_char": len(contradiction_text), "page_number": 1}],
                ),
            ]
        )
        first = DossierInterview(
            dossier_id=dossier.id,
            case_id=case.id,
            participants=["Alex Witness"],
            interviewer_user_ids=[str(owner.id)],
            status="completed",
            created_by_user_id=owner.id,
            updated_by_user_id=owner.id,
        )
        second = DossierInterview(
            dossier_id=dossier.id,
            case_id=case.id,
            participants=["Alex Witness"],
            interviewer_user_ids=[str(owner.id)],
            status="completed",
            created_by_user_id=owner.id,
            updated_by_user_id=owner.id,
        )
        db.add_all([first, second])
        db.flush()
        db.add_all(
            [
                DossierInterviewEvidenceLink(
                    interview_id=first.id,
                    case_id=case.id,
                    evidence_file_id=pdf.id,
                    source_anchor={"page": 3},
                ),
                DossierInterviewEvidenceLink(
                    interview_id=second.id,
                    case_id=case.id,
                    evidence_file_id=audio.id,
                    source_anchor={"start_seconds": 12.5, "end_seconds": 25.0},
                ),
            ]
        )
        db.commit()
        ids = {
            "owner": owner.id,
            "reviewer": reviewer.id,
            "case": case.id,
            "other_case": other_case.id,
            "mandate": mandate.id,
            "dossier": dossier.id,
            "theory": theory.id,
            "first": first.id,
            "second": second.id,
            "pdf": pdf.id,
            "audio": audio.id,
            "support": support.id,
            "contradiction": contradiction.id,
            "foreign": foreign.id,
        }
    yield factory, ids
    engine.dispose()


@pytest.fixture(autouse=True)
def dossier_permissions():
    with patch("services.dossier_service.check_case_access", return_value=(None, None)):
        yield


def test_statement_summary_is_cited_versioned_and_explicitly_accepted(ai_db):
    factory, ids = ai_db
    with factory() as db:
        owner = db.get(User, ids["owner"])
        queued = workspace_ai_service.create_output(
            db,
            case_id=ids["case"],
            target_type="dossier",
            target_id=ids["dossier"],
            output_type="statement_summary",
            requested_by=owner,
            interview_ids=[ids["first"]],
        )
        assert queued["job_status"] == "queued"
        assert queued["mandate_version_id"] == str(ids["mandate"])
        assert queued["source_set"][0]["source_anchor"]["page"] == 3
        assert "page=3" in queued["source_set"][0]["url"]

        completed = workspace_ai_service.run_output(
            db,
            output_id=uuid.UUID(queued["id"]),
            generator=lambda prompt, sources, output: {
                "headline": "First account",
                "claims": [
                    {
                        "text": "The witness placed the departure at ten in the evening.",
                        "citation_ids": [sources[0]["source_id"]],
                    }
                ],
                "limitations": ["Only one account was selected."],
            },
        )
        assert completed["job_status"] == "completed"
        assert completed["citation_status"] == "valid"
        assert completed["review_status"] == "pending_review"
        assert db.scalar(select(DossierAssessment)) is None

        reviewer = db.get(User, ids["reviewer"])
        accepted = workspace_ai_service.accept_output(
            db,
            case_id=ids["case"],
            output_id=uuid.UUID(queued["id"]),
            reviewer=reviewer,
        )
        assessment = db.scalar(select(DossierAssessment))
        assert accepted["review_status"] == "accepted"
        assert accepted["reviewed_by_user_id"] == str(reviewer.id)
        assert assessment is not None
        assert assessment.author_user_id == reviewer.id
        assert assessment.provenance_type == "ai_assisted"
        assert assessment.generated_output_id == uuid.UUID(queued["id"])
        accepted_anchor = db.scalar(select(DossierAssessmentLink)).source_anchor
        assert accepted_anchor["page"] == 3
        assert accepted_anchor["start_char"] == 0
        assert accepted_anchor["end_char"] > accepted_anchor["start_char"]


def test_comparison_rejects_unresolved_citations_and_retry_preserves_prior_version(ai_db):
    factory, ids = ai_db
    with factory() as db:
        owner = db.get(User, ids["owner"])
        queued = workspace_ai_service.create_output(
            db,
            case_id=ids["case"],
            target_type="dossier",
            target_id=ids["dossier"],
            output_type="statement_comparison",
            requested_by=owner,
            interview_ids=[ids["first"], ids["second"]],
        )
        failed = workspace_ai_service.run_output(
            db,
            output_id=uuid.UUID(queued["id"]),
            generator=lambda *_: {
                "headline": "Comparison",
                "consistencies": [],
                "contradictions": [{"text": "The time changed.", "citation_ids": ["S999"]}],
                "omissions": [],
                "material_changes": [],
                "limitations": [],
            },
        )
        assert failed["job_status"] == "failed"
        assert failed["citation_status"] == "invalid"
        with pytest.raises(workspace_ai_service.WorkspaceAIConflict, match="valid citations"):
            workspace_ai_service.accept_output(
                db,
                case_id=ids["case"],
                output_id=uuid.UUID(queued["id"]),
                reviewer=owner,
            )

        retry = workspace_ai_service.retry_output(
            db,
            case_id=ids["case"],
            output_id=uuid.UUID(queued["id"]),
            requested_by=owner,
        )
        assert retry["version"] == 2
        assert retry["parent_output_id"] == queued["id"]
        assert retry["source_set"] == queued["source_set"]
        completed = workspace_ai_service.run_output(
            db,
            output_id=uuid.UUID(retry["id"]),
            generator=lambda _prompt, sources, _output: {
                "headline": "Comparison",
                "consistencies": [],
                "contradictions": [
                    {
                        "text": "The first account says ten while the follow-up allows after midnight.",
                        "citation_ids": [sources[0]["source_id"], sources[-1]["source_id"]],
                    }
                ],
                "omissions": [],
                "material_changes": [],
                "limitations": [],
            },
        )
        rejected = workspace_ai_service.reject_output(
            db,
            case_id=ids["case"],
            output_id=uuid.UUID(retry["id"]),
            reviewer=owner,
            reason="Needs another interview",
        )
        assert completed["job_status"] == "completed"
        assert rejected["review_status"] == "rejected"
        assert rejected["rejection_reason"] == "Needs another interview"
        assert db.get(WorkspaceAIOutput, uuid.UUID(queued["id"])).job_status == "failed"


def test_theory_analysis_searches_both_sides_and_accepts_links_atomically(ai_db):
    factory, ids = ai_db
    with factory() as db:
        owner = db.get(User, ids["owner"])
        queued = workspace_ai_service.create_output(
            db,
            case_id=ids["case"],
            target_type="theory",
            target_id=ids["theory"],
            output_type="theory_analysis",
            requested_by=owner,
        )
        evidence_ids = {item["evidence_file_id"] for item in queued["source_set"]}
        assert str(ids["support"]) in evidence_ids
        assert str(ids["contradiction"]) in evidence_ids
        by_evidence = {item["evidence_file_id"]: item for item in queued["source_set"]}
        completed = workspace_ai_service.run_output(
            db,
            output_id=uuid.UUID(queued["id"]),
            generator=lambda *_: {
                "headline": "Departure timing",
                "supporting": [
                    {
                        "text": "The gate log records a 22:04 departure.",
                        "citation_ids": [by_evidence[str(ids["support"])]["source_id"]],
                    }
                ],
                "contradicting": [
                    {
                        "text": "A camera record places the vehicle there at 00:12.",
                        "citation_ids": [by_evidence[str(ids["contradiction"])]["source_id"]],
                    }
                ],
                "supporting_not_found_reason": None,
                "contradicting_not_found_reason": None,
                "limitations": ["Timestamp calibration was not independently checked."],
            },
        )
        assert {item["relationship"] for item in completed["proposed_actions"]} == {"supports", "contradicts"}
        before = db.get(WorkspaceEntry, ids["theory"]).version
        accepted = workspace_ai_service.accept_output(
            db,
            case_id=ids["case"],
            output_id=uuid.UUID(queued["id"]),
            reviewer=owner,
        )
        links = db.scalars(select(WorkspaceEntryLink).where(WorkspaceEntryLink.entry_id == ids["theory"])).all()
        assert accepted["review_status"] == "accepted"
        assert {link.relationship_type for link in links} == {"supports", "contradicts"}
        assert db.get(WorkspaceEntry, ids["theory"]).version == before + 1
        assert all(link.link_metadata["workspace_ai_output_id"] == queued["id"] for link in links)


def test_theory_analysis_requires_both_sides_or_specific_not_found_reason(ai_db):
    factory, ids = ai_db
    with factory() as db:
        owner = db.get(User, ids["owner"])
        queued = workspace_ai_service.create_output(
            db,
            case_id=ids["case"],
            target_type="theory",
            target_id=ids["theory"],
            output_type="theory_analysis",
            requested_by=owner,
        )
        source_id = queued["source_set"][0]["source_id"]
        failed = workspace_ai_service.run_output(
            db,
            output_id=uuid.UUID(queued["id"]),
            generator=lambda *_: {
                "headline": "One-sided",
                "supporting": [{"text": "Some support.", "citation_ids": [source_id]}],
                "contradicting": [],
                "supporting_not_found_reason": None,
                "contradicting_not_found_reason": None,
                "limitations": [],
            },
        )
        assert failed["job_status"] == "failed"
        retry = workspace_ai_service.retry_output(
            db,
            case_id=ids["case"],
            output_id=uuid.UUID(queued["id"]),
            requested_by=owner,
        )
        completed = workspace_ai_service.run_output(
            db,
            output_id=uuid.UUID(retry["id"]),
            generator=lambda *_: {
                "headline": "Balanced search",
                "supporting": [{"text": "Some support.", "citation_ids": [source_id]}],
                "contradicting": [],
                "supporting_not_found_reason": None,
                "contradicting_not_found_reason": "No reliable contradictory excerpt was found in the bounded source set.",
                "limitations": [],
            },
        )
        assert completed["job_status"] == "completed"


def test_cancel_is_durable_and_prevents_result_publication(ai_db):
    factory, ids = ai_db
    with factory() as db:
        owner = db.get(User, ids["owner"])
        queued = workspace_ai_service.create_output(
            db,
            case_id=ids["case"],
            target_type="dossier",
            target_id=ids["dossier"],
            output_type="statement_summary",
            requested_by=owner,
            interview_ids=[ids["first"]],
        )

        def cancel_during_generation(_prompt, sources, _output):
            workspace_ai_service.cancel_output(
                db,
                case_id=ids["case"],
                output_id=uuid.UUID(queued["id"]),
            )
            return {
                "headline": "Should not publish",
                "claims": [{"text": "Claim", "citation_ids": [sources[0]["source_id"]]}],
                "limitations": [],
            }

        result = workspace_ai_service.run_output(
            db,
            output_id=uuid.UUID(queued["id"]),
            generator=cancel_during_generation,
        )
        assert result["job_status"] == "cancelled"
        assert result["content"] == {}
        assert result["review_status"] == "pending_review"


def test_case_mandate_selection_and_cross_case_targets_are_enforced(ai_db):
    factory, ids = ai_db
    with factory() as db:
        owner = db.get(User, ids["owner"])
        with pytest.raises(workspace_ai_service.WorkspaceAINotFound, match="not found in this case"):
            workspace_ai_service.create_output(
                db,
                case_id=ids["other_case"],
                target_type="dossier",
                target_id=ids["dossier"],
                output_type="statement_summary",
                requested_by=owner,
                interview_ids=[ids["first"]],
            )
        context = db.scalar(select(CaseContext).where(CaseContext.case_id == ids["case"]))
        context.active_mandate_version_id = None
        db.commit()
        with pytest.raises(workspace_ai_service.WorkspaceAIError, match="active case mandate"):
            workspace_ai_service.create_output(
                db,
                case_id=ids["case"],
                target_type="dossier",
                target_id=ids["dossier"],
                output_type="statement_summary",
                requested_by=owner,
                interview_ids=[ids["first"]],
            )
