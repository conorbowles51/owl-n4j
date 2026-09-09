"""Seed deterministic, case-isolated Phase 7 browser verification records.

The base Workspace fixture owns the cases and users.  This script only adds
records below the fixture's small case, records their exact identifiers in the
same manifest, and relies on the base fixture's case-cascade cleanup.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = BACKEND_ROOT.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from postgres.models.case_context import CaseContext, CaseMandateVersion
from postgres.backfills.workspace_cutover import backfill_missing_entry_history
from postgres.models.case_profile import CaseProfile
from postgres.models.dossier import DossierInterview, DossierInterviewEvidenceLink
from postgres.models.evidence import EvidenceDocumentText, EvidenceFile
from postgres.models.user import User
from postgres.models.workspace_ai import WorkspaceAIOutput
from postgres.models.workspace_entry import WorkspaceEntry
from postgres.session import get_background_session
from services import workspace_ai_service


PREFIX = "[workspace-verification]"
DEFAULT_MANIFEST = (
    REPOSITORY_ROOT / "output" / "workspace-redesign" / "browser-fixtures.json"
)


SOURCE_DEFINITIONS = (
    {
        "key": "marcus_interview",
        "filename": f"{PREFIX} interview-marcus-chen.pdf",
        "path": REPOSITORY_ROOT
        / "tmp"
        / "pdfs"
        / "case-audit"
        / "59144480-bee5-4cd0-a7ea-461d0eb73b1a"
        / "06_interview_marcus_chen.pdf",
        "content": (
            "Marcus Chen said Nexus provided strategic consulting and executive-level market analysis. "
            "When asked about more than one million pounds in 2023 payments, he said he believed the "
            "payments went through proper channels. The interviewer stated there was no board approval, "
            "no tender process, and no evidence of services rendered. Marcus then asked to speak with a lawyer."
        ),
    },
    {
        "key": "david_interview",
        "filename": f"{PREFIX} interview-david-okonkwo.pdf",
        "path": REPOSITORY_ROOT
        / "tmp"
        / "pdfs"
        / "case-audit"
        / "c88f3315-2c39-431d-a47f-8a20e390941a"
        / "07_interview_david_okonkwo.pdf",
        "content": (
            "David Okonkwo said his normal payment process required an approved invoice, purchase order, "
            "and manager sign-off. For Nexus payments, Marcus Chen told him normal procedures did not apply "
            "because the work was confidential. David admitted he knew something was wrong and said Marcus "
            "offered a promotion or bonus if he helped. David denied receiving a payment and agreed to cooperate."
        ),
    },
    {
        "key": "whistleblower_report",
        "filename": f"{PREFIX} whistleblower-report.pdf",
        "path": REPOSITORY_ROOT
        / "tmp"
        / "pdfs"
        / "case-audit"
        / "3132d8d6-adec-4fc8-8b3c-13644d5abaa9"
        / "01_whistleblower_report.pdf",
        "content": (
            "The whistleblower alleged a systematic procurement fraud scheme. The report identifies Marcus "
            "Chen as the manager overseeing vendor relationships and David Okonkwo as the supervisor who "
            "approved payments without proper documentation. It records suspicious payments to Nexus Trading "
            "between March and December 2023 and requests an immediate investigation."
        ),
    },
)


def _file_metadata(path: Path) -> tuple[str, int]:
    if not path.is_file():
        raise RuntimeError(f"Phase 7 source PDF is missing: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest(), path.stat().st_size


def _ensure_mandate(db, *, case_id: UUID, owner_id: UUID) -> CaseMandateVersion:
    context = db.query(CaseContext).filter(CaseContext.case_id == case_id).one_or_none()
    if context and context.active_mandate_version_id:
        mandate = db.get(CaseMandateVersion, context.active_mandate_version_id)
        if mandate:
            return mandate
    latest = (
        db.query(CaseMandateVersion)
        .filter(CaseMandateVersion.case_id == case_id)
        .order_by(CaseMandateVersion.version_number.desc())
        .first()
    )
    mandate = CaseMandateVersion(
        case_id=case_id,
        version_number=(latest.version_number + 1) if latest else 1,
        objective="Test whether procurement payments were coordinated without presuming wrongdoing.",
        key_questions=[
            "Which accounts are mutually consistent?",
            "What evidence supports or contradicts coordination?",
        ],
        in_scope="Interview records, payment-process evidence, and source-supported inconsistencies.",
        out_of_scope="Uncited speculation about motive or criminal liability.",
        perspective="Independent internal investigation.",
        success_criteria="A balanced, cited account that investigators can accept or reject.",
        constraints="Every factual claim must resolve to the supplied evidence.",
        author_user_id=owner_id,
    )
    db.add(mandate)
    db.flush()
    if context is None:
        context = CaseContext(
            case_id=case_id,
            case_summary="Representative procurement investigation used for Workspace verification.",
            background="Conflicting accounts concern payments made outside normal controls.",
            investigation_type="Internal corporate investigation",
            jurisdiction="Cross-border corporate operations",
            active_template_key="generic",
            created_by_user_id=owner_id,
            updated_by_user_id=owner_id,
        )
        db.add(context)
    context.active_mandate_version_id = mandate.id
    context.updated_by_user_id = owner_id
    db.flush()
    return mandate


def _ensure_evidence(db, *, case_id: UUID, owner: User, fixture_id: str) -> dict[str, EvidenceFile]:
    result: dict[str, EvidenceFile] = {}
    for source in SOURCE_DEFINITIONS:
        sha256, size = _file_metadata(source["path"])
        item = (
            db.query(EvidenceFile)
            .filter(
                EvidenceFile.case_id == case_id,
                EvidenceFile.original_filename == source["filename"],
            )
            .one_or_none()
        )
        if item is None:
            item = EvidenceFile(
                case_id=case_id,
                original_filename=source["filename"],
                stored_path=str(source["path"].resolve()),
                size=size,
                sha256=sha256,
                status="processed",
                owner=owner.email,
                created_by_id=owner.id,
                metadata_={"fixture_id": fixture_id, "purpose": "phase7-cited-ai"},
            )
            db.add(item)
            db.flush()
        content = source["content"]
        document = db.get(EvidenceDocumentText, item.id)
        if document is None:
            document = EvidenceDocumentText(
                evidence_file_id=item.id,
                content=content,
                content_sha256=hashlib.sha256(content.encode("utf-8")).hexdigest(),
                character_count=len(content),
                source_locations=[
                    {"page_number": 1, "start_char": 0, "end_char": len(content)}
                ],
            )
            db.add(document)
        result[source["key"]] = item
    db.flush()
    return result


def _ensure_dossier(db, *, case_id: UUID, owner_id: UUID) -> CaseProfile:
    dossier = (
        db.query(CaseProfile)
        .filter(
            CaseProfile.case_id == case_id,
            CaseProfile.legacy_source == "workspace_phase7_verification",
        )
        .one_or_none()
    )
    if dossier is None:
        dossier = CaseProfile(
            case_id=case_id,
            profile_type="person",
            display_name=f"{PREFIX} Marcus Chen",
            summary="Investigator-curated subject view for cited statement analysis.",
            importance="Central procurement decision-maker whose account conflicts with payment-control evidence.",
            linkage_state="unlinked",
            status="active",
            legacy_source="workspace_phase7_verification",
            created_by_user_id=owner_id,
            updated_by_user_id=owner_id,
        )
        db.add(dossier)
        db.flush()
    return dossier


def _ensure_interview(
    db,
    *,
    dossier: CaseProfile,
    owner_id: UUID,
    label: str,
    evidence: EvidenceFile,
) -> DossierInterview:
    marker = f"workspace-phase7:{label}"
    participant = "Marcus Chen" if label == "marcus" else "David Okonkwo"
    interview = next(
        (
            item
            for item in db.query(DossierInterview)
            .filter(DossierInterview.dossier_id == dossier.id)
            .all()
            if marker == item.working_notes or participant in (item.participants or [])
        ),
        None,
    )
    if interview is None:
        interview = DossierInterview(
            dossier_id=dossier.id,
            case_id=dossier.case_id,
            interview_date=datetime(2024, 3, 5, 10 if label == "marcus" else 14, tzinfo=timezone.utc),
            participants=[participant],
            interviewer_user_ids=[str(owner_id)],
            status="completed",
            working_notes="Source-linked interview used to compare the procurement-payment accounts.",
            created_by_user_id=owner_id,
            updated_by_user_id=owner_id,
        )
        db.add(interview)
        db.flush()
    else:
        interview.working_notes = (
            "Source-linked interview used to compare the procurement-payment accounts."
        )
    link = (
        db.query(DossierInterviewEvidenceLink)
        .filter(
            DossierInterviewEvidenceLink.interview_id == interview.id,
            DossierInterviewEvidenceLink.evidence_file_id == evidence.id,
        )
        .one_or_none()
    )
    if link is None:
        db.add(
            DossierInterviewEvidenceLink(
                interview_id=interview.id,
                case_id=dossier.case_id,
                evidence_file_id=evidence.id,
                source_anchor={"page": 1},
            )
        )
    db.flush()
    return interview


def _ensure_theory(db, *, case_id: UUID, owner: User) -> WorkspaceEntry:
    title = f"{PREFIX} Marcus and David coordinated Nexus payments"
    theory = (
        db.query(WorkspaceEntry)
        .filter(
            WorkspaceEntry.case_id == case_id,
            WorkspaceEntry.entry_type == "theory",
            WorkspaceEntry.title == title,
        )
        .one_or_none()
    )
    if theory is None:
        theory = WorkspaceEntry(
            case_id=case_id,
            entry_type="theory",
            title=title,
            body=(
                "Marcus Chen and David Okonkwo may have coordinated Nexus payments outside normal "
                "procurement procedures, but their accounts and the documentary evidence must be tested both ways."
            ),
            tags=["phase7", "payments"],
            lifecycle_state="investigating",
            confidence=55,
            review_state="accepted",
            version=1,
            author_user_id=owner.id,
            author_email=owner.email,
            author_name=owner.name,
            updated_by_user_id=owner.id,
            updated_by_email=owner.email,
            updated_by_name=owner.name,
        )
        db.add(theory)
        db.flush()
    return theory


def _source_id(sources: list[dict], filename_fragment: str) -> str:
    for source in sources:
        if filename_fragment in str(source.get("filename", "")):
            return str(source["source_id"])
    raise RuntimeError(f"Expected source containing {filename_fragment!r}")


def _generate(_prompt: str, sources: list[dict], output: WorkspaceAIOutput):
    marcus = _source_id(sources, "marcus-chen")
    if output.output_type == "statement_summary":
        return {
            "headline": "Marcus Chen statement summary",
            "claims": [
                {
                    "text": "Marcus said Nexus provided strategic consulting and that he believed the payments followed proper channels.",
                    "citation_ids": [marcus],
                },
                {
                    "text": "The interviewer put to Marcus that the payments lacked board approval, a tender process, and evidence of services.",
                    "citation_ids": [marcus],
                },
            ],
            "limitations": ["This summary is limited to the selected interview record."],
        }
    david = _source_id(sources, "david-okonkwo")
    if output.output_type == "statement_comparison":
        return {
            "headline": "Comparison of procurement-payment accounts",
            "consistencies": [
                {
                    "text": "Both accounts identify Marcus as involved in the Nexus payment process.",
                    "citation_ids": [marcus, david],
                }
            ],
            "contradictions": [
                {
                    "text": "Marcus said he believed proper channels were followed, while David said Marcus told him normal procedures did not apply.",
                    "citation_ids": [marcus, david],
                }
            ],
            "omissions": [
                {
                    "text": "Marcus did not identify the board approval or tender documentation requested by the interviewer.",
                    "citation_ids": [marcus],
                }
            ],
            "material_changes": [],
            "limitations": ["The records are separate interviews rather than successive accounts by one witness."],
        }
    return {
        "headline": "Balanced test of the coordination theory",
        "supporting": [
            {
                "text": "David said Marcus told him normal procedures did not apply and offered a promotion or bonus if he helped.",
                "citation_ids": [david],
            }
        ],
        "contradicting": [
            {
                "text": "Marcus stated that he believed the payments had gone through proper channels.",
                "citation_ids": [marcus],
            }
        ],
        "supporting_not_found_reason": None,
        "contradicting_not_found_reason": None,
        "limitations": ["The bounded source set does not independently establish intent."],
    }


def _new_completed(
    db,
    *,
    case_id: UUID,
    target_type: str,
    target_id: UUID,
    output_type: str,
    owner: User,
    interview_ids: list[UUID] | None = None,
) -> dict:
    queued = workspace_ai_service.create_output(
        db,
        case_id=case_id,
        target_type=target_type,
        target_id=target_id,
        output_type=output_type,
        requested_by=owner,
        interview_ids=interview_ids,
    )
    return workspace_ai_service.run_output(
        db,
        output_id=UUID(queued["id"]),
        generator=_generate,
    )


def _ensure_output_states(
    db,
    *,
    case_id: UUID,
    dossier: CaseProfile,
    theory: WorkspaceEntry,
    interviews: list[DossierInterview],
    owner: User,
) -> dict[str, str]:
    result: dict[str, str] = {}

    def find(target_type: str, target_id: UUID, output_type: str, review_status: str, job_status: str = "completed"):
        return (
            db.query(WorkspaceAIOutput)
            .filter(
                WorkspaceAIOutput.case_id == case_id,
                WorkspaceAIOutput.target_type == target_type,
                WorkspaceAIOutput.target_id == target_id,
                WorkspaceAIOutput.output_type == output_type,
                WorkspaceAIOutput.review_status == review_status,
                WorkspaceAIOutput.job_status == job_status,
            )
            .order_by(WorkspaceAIOutput.version.desc())
            .first()
        )

    accepted = find("dossier", dossier.id, "statement_summary", "accepted")
    if accepted is None:
        completed = _new_completed(
            db,
            case_id=case_id,
            target_type="dossier",
            target_id=dossier.id,
            output_type="statement_summary",
            owner=owner,
            interview_ids=[interviews[0].id],
        )
        workspace_ai_service.accept_output(
            db, case_id=case_id, output_id=UUID(completed["id"]), reviewer=owner
        )
        accepted = db.get(WorkspaceAIOutput, UUID(completed["id"]))
    result["accepted_summary"] = str(accepted.id)

    rejected = find("dossier", dossier.id, "statement_summary", "rejected")
    if rejected is None:
        completed = _new_completed(
            db,
            case_id=case_id,
            target_type="dossier",
            target_id=dossier.id,
            output_type="statement_summary",
            owner=owner,
            interview_ids=[interviews[0].id],
        )
        workspace_ai_service.reject_output(
            db,
            case_id=case_id,
            output_id=UUID(completed["id"]),
            reviewer=owner,
            reason="Fixture rejection preserves the generated version for review-state verification.",
        )
        rejected = db.get(WorkspaceAIOutput, UUID(completed["id"]))
    result["rejected_summary"] = str(rejected.id)

    pending = find("dossier", dossier.id, "statement_summary", "pending_review")
    if pending is None:
        completed = _new_completed(
            db,
            case_id=case_id,
            target_type="dossier",
            target_id=dossier.id,
            output_type="statement_summary",
            owner=owner,
            interview_ids=[interviews[0].id],
        )
        pending = db.get(WorkspaceAIOutput, UUID(completed["id"]))
    result["pending_summary"] = str(pending.id)

    pending_comparison = find("dossier", dossier.id, "statement_comparison", "pending_review")
    if pending_comparison is None:
        completed = _new_completed(
            db,
            case_id=case_id,
            target_type="dossier",
            target_id=dossier.id,
            output_type="statement_comparison",
            owner=owner,
            interview_ids=[item.id for item in interviews],
        )
        pending_comparison = db.get(WorkspaceAIOutput, UUID(completed["id"]))
    result["pending_comparison"] = str(pending_comparison.id)

    running = find("dossier", dossier.id, "statement_comparison", "pending_review", "running")
    if running is None:
        queued = workspace_ai_service.create_output(
            db,
            case_id=case_id,
            target_type="dossier",
            target_id=dossier.id,
            output_type="statement_comparison",
            requested_by=owner,
            interview_ids=[item.id for item in interviews],
        )
        running = db.get(WorkspaceAIOutput, UUID(queued["id"]))
        running.job_status = "running"
        running.progress = 47
        running.started_at = datetime.now(timezone.utc)
        db.commit()
    result["running_comparison"] = str(running.id)

    accepted_theory = find("theory", theory.id, "theory_analysis", "accepted")
    if accepted_theory is None:
        completed = _new_completed(
            db,
            case_id=case_id,
            target_type="theory",
            target_id=theory.id,
            output_type="theory_analysis",
            owner=owner,
        )
        workspace_ai_service.accept_output(
            db, case_id=case_id, output_id=UUID(completed["id"]), reviewer=owner
        )
        accepted_theory = db.get(WorkspaceAIOutput, UUID(completed["id"]))
    result["accepted_theory"] = str(accepted_theory.id)

    pending_theory = find("theory", theory.id, "theory_analysis", "pending_review")
    if pending_theory is None:
        completed = _new_completed(
            db,
            case_id=case_id,
            target_type="theory",
            target_id=theory.id,
            output_type="theory_analysis",
            owner=owner,
        )
        pending_theory = db.get(WorkspaceAIOutput, UUID(completed["id"]))
    result["pending_theory"] = str(pending_theory.id)
    return result


def seed(manifest_path: Path) -> dict:
    if not manifest_path.is_file():
        raise RuntimeError("Create the base Workspace browser fixtures before Phase 7 fixtures")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    case_id = UUID(manifest["case_ids"]["small"])
    owner_id = UUID(manifest["users"]["owner"]["id"])
    fixture_id = str(manifest["fixture_id"])
    with get_background_session() as db:
        owner = db.get(User, owner_id)
        if owner is None:
            raise RuntimeError("Workspace fixture owner no longer exists")
        mandate = _ensure_mandate(db, case_id=case_id, owner_id=owner_id)
        evidence = _ensure_evidence(
            db, case_id=case_id, owner=owner, fixture_id=fixture_id
        )
        dossier = _ensure_dossier(db, case_id=case_id, owner_id=owner_id)
        interviews = [
            _ensure_interview(
                db,
                dossier=dossier,
                owner_id=owner_id,
                label="marcus",
                evidence=evidence["marcus_interview"],
            ),
            _ensure_interview(
                db,
                dossier=dossier,
                owner_id=owner_id,
                label="david",
                evidence=evidence["david_interview"],
            ),
        ]
        theory = _ensure_theory(db, case_id=case_id, owner=owner)
        db.commit()
        entry_history = backfill_missing_entry_history(
            db.connection(), case_ids=[case_id]
        )
        outputs = _ensure_output_states(
            db,
            case_id=case_id,
            dossier=dossier,
            theory=theory,
            interviews=interviews,
            owner=owner,
        )
        phase7 = {
            "mandate_version_id": str(mandate.id),
            "dossier_id": str(dossier.id),
            "interview_ids": [str(item.id) for item in interviews],
            "theory_id": str(theory.id),
            "evidence_ids": {key: str(value.id) for key, value in evidence.items()},
            "output_ids": outputs,
            "entry_history": entry_history,
        }
    manifest["phase7"] = phase7
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return phase7


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest")
    args = parser.parse_args()
    path = Path(args.manifest).resolve() if args.manifest else DEFAULT_MANIFEST
    print(json.dumps(seed(path), indent=2))


if __name__ == "__main__":
    main()
