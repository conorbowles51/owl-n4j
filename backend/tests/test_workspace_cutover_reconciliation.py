from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

from services import workspace_cutover_reconciliation_service as reconciliation


def _entry_report():
    return {
        "summary": {"source_records": 0},
        "duplicate_sources": [],
        "missing_mappings": [],
        "missing_targets": [],
        "inconsistent_targets": [],
        "mappings_without_target_identity": [],
        "unrepointed_profile_links": [],
        "unresolved_links": [],
        "needs_migration_review": [],
    }


def _dossier_report():
    return {
        "summary": {"unrepointed_witness_links": 0},
        "invalid_profile_mappings": [],
        "missing_witness_mappings": [],
        "duplicate_active_entity_claims": [],
        "integrity_errors": [],
        "multiple_cover_errors": [],
    }


def _preflight():
    return {
        "counts": {},
        "malformed_identifiers": [],
        "orphaned_links": [],
        "duplicate_pins": [],
        "duplicate_profile_entity_associations": [],
        "conflicting_deadline_sources": [],
    }


def test_review_items_require_exact_explicit_acceptance():
    case_id = uuid4()
    db = MagicMock()
    db.scalars.return_value.all.return_value = [case_id]
    review = {
        "key": "dossier-linkage:dossier-1",
        "category": "dossier-linkage",
        "detail": {"reason": "graph identity needs investigator review"},
    }
    patches = (
        patch.object(reconciliation, "build_workspace_entry_reconciliation_report", return_value=_entry_report()),
        patch.object(reconciliation, "build_dossier_reconciliation_report", return_value=_dossier_report()),
        patch.object(reconciliation, "build_workspace_preflight_report", return_value=_preflight()),
        patch.object(reconciliation, "_work_reconciliation", return_value=({}, [], [])),
        patch.object(reconciliation, "_context_reconciliation", return_value=({}, [], [])),
        patch.object(reconciliation, "_canonical_integrity_errors", return_value=[]),
        patch.object(reconciliation, "_canonical_counts", return_value={}),
        patch.object(reconciliation, "_dossier_review_items", return_value=[review]),
        patch.object(
            reconciliation,
            "_legacy_evidence_dossier_reconciliation",
            return_value=({}, [], []),
        ),
    )
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patches[7], patches[8]:
        unaccepted = reconciliation.build_workspace_cutover_reconciliation_report(db)
        accepted = reconciliation.build_workspace_cutover_reconciliation_report(
            db, accepted_review_keys={review["key"]}
        )
        unknown = reconciliation.build_workspace_cutover_reconciliation_report(
            db, accepted_review_keys={review["key"], "unknown:key"}
        )

    assert unaccepted["passed"] is False
    assert unaccepted["summary"]["unaccepted_review_items"] == 1
    assert accepted["passed"] is True
    assert accepted["summary"]["accepted_review_items"] == 1
    assert unknown["passed"] is False
    assert unknown["unknown_acceptance_keys"] == ["unknown:key"]
