from app.services.projection_reconciliation import reconcile_projection_snapshot


def test_projection_reconciliation_detects_orphans_missing_claims_and_drafts() -> None:
    report = reconcile_projection_snapshot(
        ledger_claim_ids={"claim-a", "claim-b"},
        graph_claim_ids={"claim-a", "claim-orphan"},
        chunk_metadatas=[
            {"revision_id": "rev-2", "ingestion_state": "active"},
            {"revision_id": "rev-1", "ingestion_state": "inactive"},
            {"revision_id": "rev-3", "ingestion_state": "draft"},
        ],
        pending_publications=1,
    )

    assert report["status"] == "degraded"
    assert report["claims"]["orphan_graph_claim_ids"] == ["claim-orphan"]
    assert report["claims"]["missing_graph_claim_ids"] == ["claim-b"]
    assert report["chunks"] == {
        "active": 1,
        "draft": 1,
        "inactive": 1,
        "legacy": 0,
        "active_revisions": ["rev-2"],
    }
    assert report["pending_publications"] == 1
