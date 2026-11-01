from __future__ import annotations

from collections import Counter
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from postgres import link_types
from postgres.models.case_profile import CaseProfile
from postgres.models.dossier import (
    DossierInterview, DossierInterviewEvidenceLink, DossierLegacyMapping,
    DossierLink, DossierMedia,
)
from postgres.models.evidence import EvidenceFile
from postgres.models.workspace import WorkspaceWitness
from postgres.models.workspace_entry import WorkspaceEntryLink


def build_dossier_reconciliation_report(
    db: Session,
    *,
    case_id: UUID | None = None,
) -> dict[str, Any]:
    profile_query = select(CaseProfile)
    mapping_query = select(DossierLegacyMapping)
    witness_query = select(WorkspaceWitness)
    if case_id is not None:
        profile_query = profile_query.where(CaseProfile.case_id == case_id)
        mapping_query = mapping_query.where(DossierLegacyMapping.case_id == case_id)
        witness_query = witness_query.where(WorkspaceWitness.case_id == case_id)
    profiles = db.scalars(profile_query).all()
    mappings = db.scalars(mapping_query).all()
    mapping_keys = {(row.case_id, row.source_type, row.source_id) for row in mappings}
    active_claims = Counter(
        (row.case_id, row.canonical_entity_key)
        for row in profiles
        if row.archived_at is None and row.canonical_entity_key
    )
    duplicate_active = [
        {"case_id": str(case_id), "entity_key": key, "count": count}
        for (case_id, key), count in active_claims.items() if count > 1
    ]
    profile_by_id = {row.id: row for row in profiles}
    invalid_profile_mappings = [
        {
            "case_id": str(row.case_id),
            "source_id": row.source_id,
            "dossier_id": str(row.dossier_id),
        }
        for row in mappings
        if row.source_type == "case_profile"
        and (
            row.dossier_id not in profile_by_id
            or row.source_id != str(row.dossier_id)
        )
    ]
    witnesses = db.scalars(witness_query).all()
    missing_witness_mappings = [
        {"case_id": str(row.case_id), "witness_id": row.witness_id}
        for row in witnesses
        if (row.case_id, "workspace_witness", row.witness_id) not in mapping_keys
    ]
    unrepointed_query = (
        select(func.count())
        .select_from(WorkspaceEntryLink)
        .where(WorkspaceEntryLink.target_type == "witness")
    )
    if case_id is not None:
        unrepointed_query = unrepointed_query.where(
            WorkspaceEntryLink.case_id == case_id
        )
    unrepointed_witness_links = db.scalar(unrepointed_query) or 0

    errors: list[dict[str, Any]] = []
    media_query = select(DossierMedia, EvidenceFile).join(
        EvidenceFile, EvidenceFile.id == DossierMedia.evidence_file_id
    )
    link_query = select(DossierLink).where(DossierLink.target_type == "evidence")
    interview_evidence_query = (
        select(DossierInterviewEvidenceLink, DossierInterview, EvidenceFile)
        .join(DossierInterview, DossierInterview.id == DossierInterviewEvidenceLink.interview_id)
        # Outer join: interview evidence can be a phone record, analysis or statement check with no evidence file.
        .outerjoin(EvidenceFile, EvidenceFile.id == DossierInterviewEvidenceLink.evidence_file_id)
    )
    covers_query = select(DossierMedia.dossier_id, func.count()).where(
        DossierMedia.is_cover.is_(True)
    )
    if case_id is not None:
        media_query = media_query.where(DossierMedia.case_id == case_id)
        link_query = link_query.where(DossierLink.case_id == case_id)
        interview_evidence_query = interview_evidence_query.where(
            DossierInterviewEvidenceLink.case_id == case_id
        )
        covers_query = covers_query.where(DossierMedia.case_id == case_id)

    for media, evidence in db.execute(media_query):
        if media.case_id != evidence.case_id:
            errors.append({"kind": "cross_case_media", "id": str(media.id)})
    for link in db.scalars(link_query):
        try:
            evidence = db.get(EvidenceFile, UUID(link.target_id))
        except (TypeError, ValueError):
            evidence = None
        if evidence is None or evidence.case_id != link.case_id:
            errors.append({"kind": "invalid_evidence_link", "id": str(link.id)})
    interview_evidence_targets: list[dict[str, Any]] = []
    for link, interview, evidence in db.execute(interview_evidence_query):
        if link.evidence_file_id is not None:
            if evidence is None or link.case_id != interview.case_id or link.case_id != evidence.case_id:
                errors.append({"kind": "cross_case_interview_evidence", "id": str(link.id)})
            continue
        # A target row (phone record, phone analysis, statement check) is reported by type and id and checked
        # against the case where its type can be checked here; one that cannot is reported as unchecked.
        target = {"id": str(link.id), "target_type": link.target_type, "target_id": link.target_id,
                  "checked": False}
        interview_evidence_targets.append(target)
        if link.case_id != interview.case_id:
            errors.append({"kind": "cross_case_interview_evidence", "id": str(link.id)})
            continue
        if not link.target_type or not link.target_id:
            errors.append({"kind": "invalid_interview_evidence_target", "id": str(link.id)})
            continue
        if not link_types.has_phone_resolver(link.target_type):
            continue
        try:
            link_types.resolve_phone_target(db, link.case_id, link.target_type, link.target_id)
        except link_types.PhoneLinkUnavailable:
            continue
        except link_types.LinkTargetError:
            errors.append({"kind": "invalid_interview_evidence_target", "id": str(link.id)})
        target["checked"] = True
    multiple_covers = [
        {"dossier_id": str(dossier_id), "count": count}
        for dossier_id, count in db.execute(
            covers_query.group_by(DossierMedia.dossier_id).having(func.count() > 1)
        )
    ]
    summary = {
        "dossiers": len(profiles),
        "linked": sum(row.linkage_state == "linked" for row in profiles),
        "unlinked": sum(row.linkage_state == "unlinked" for row in profiles),
        "deleted_graph_entity": sum(row.linkage_state == "deleted" for row in profiles),
        "needs_link_review": sum(bool(row.needs_link_review) for row in profiles),
        "legacy_mappings": len(mappings),
        "invalid_profile_mappings": len(invalid_profile_mappings),
        "missing_witness_mappings": len(missing_witness_mappings),
        "unrepointed_witness_links": unrepointed_witness_links,
        "duplicate_active_entity_claims": len(duplicate_active),
        "integrity_errors": len(errors),
        "multiple_cover_errors": len(multiple_covers),
        "interview_evidence_targets": dict(sorted(Counter(
            str(row["target_type"]) for row in interview_evidence_targets).items())),
        "interview_evidence_targets_unchecked": sum(not row["checked"] for row in interview_evidence_targets),
    }
    return {
        "scope": {"case_id": str(case_id) if case_id else None},
        "summary": summary,
        "duplicate_active_entity_claims": duplicate_active,
        "invalid_profile_mappings": invalid_profile_mappings,
        "missing_witness_mappings": missing_witness_mappings,
        "integrity_errors": errors,
        "multiple_cover_errors": multiple_covers,
        "interview_evidence_targets": interview_evidence_targets,
        "passed": all(summary[key] == 0 for key in (
            "invalid_profile_mappings", "missing_witness_mappings", "unrepointed_witness_links",
            "duplicate_active_entity_claims", "integrity_errors", "multiple_cover_errors",
        )),
    }
