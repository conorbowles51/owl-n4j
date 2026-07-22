import json

from app.api.routes.merge import MergeEntityPayload
from app.pipeline.merge_relationships import (
    aggregate_relationships_for_merge,
    build_merge_result_state,
    merge_entity_evidence,
    relationship_write_properties,
)


def test_merge_request_model_retains_node_claims_and_locations() -> None:
    payload = MergeEntityPayload(
        key="person-1",
        name="Victoria Blackwood",
        source_claim_ids=["claim-1"],
        source_locations=[{"file_name": "registry.pdf", "page_start": 2}],
    ).model_dump()

    assert payload["source_claim_ids"] == ["claim-1"]
    assert payload["source_locations"] == [
        {"file_name": "registry.pdf", "page_start": 2}
    ]


def test_aggregate_relationships_preserves_provenance_and_strips_identity_fields() -> None:
    entities = [
        {
            "key": "source-1",
            "name": "Source One",
            "relationships": [
                {
                    "type": "OWNS",
                    "direction": "outgoing",
                    "target_key": "target-1",
                    "source_files": ["file-a.pdf"],
                    "source_quotes": ["quote a"],
                    "source_claim_ids": ["claim-a"],
                    "source_locations": [{"file_name": "file-a.pdf", "page_start": 2}],
                    "properties": {
                        "source_id": "source-1",
                        "target_id": "target-1",
                        "case_id": "case-1",
                        "source_files": ["file-b.pdf"],
                        "source_quotes": ["quote b"],
                        "source_claim_ids": ["claim-b"],
                        "source_locations": '[{"file_name":"file-b.pdf","page_start":4}]',
                        "detail": "beneficial ownership",
                        "confidence": 0.82,
                    },
                }
            ],
        },
        {
            "key": "source-2",
            "name": "Source Two",
            "relationships": [
                {
                    "type": "OWNS",
                    "direction": "outgoing",
                    "target_key": "target-1",
                    "source_files": ["file-a.pdf", "file-c.pdf"],
                    "source_quotes": ["quote a", "quote c"],
                    "source_claim_ids": ["claim-c"],
                    "source_locations": [{"file_name": "file-c.pdf", "page_start": 6}],
                    "properties": {
                        "source_id": "source-2",
                        "target_id": "target-1",
                        "detail": "ignored because first non-empty wins",
                    },
                },
                {
                    "type": "OWNS",
                    "direction": "incoming",
                    "target_key": "source-1",
                    "properties": {"detail": "relationship between merged sources"},
                },
            ],
        },
    ]

    aggregated, source_names = aggregate_relationships_for_merge(entities, "case-1")

    key = ("OWNS", "outgoing", "target-1")
    assert set(aggregated) == {key}
    assert source_names[key] == "Source One"
    relationship = aggregated[key]
    assert relationship == {
        "case_id": "case-1",
        "source_files": ["file-a.pdf", "file-b.pdf", "file-c.pdf"],
        "source_quotes": ["quote a", "quote b", "quote c"],
        "source_claim_ids": ["claim-a", "claim-b", "claim-c"],
        "source_locations": relationship["source_locations"],
        "detail": "beneficial ownership",
        "confidence": 0.82,
    }
    assert json.loads(relationship["source_locations"]) == [
        {"file_name": "file-a.pdf", "page_start": 2},
        {"file_name": "file-b.pdf", "page_start": 4},
        {"file_name": "file-c.pdf", "page_start": 6},
    ]


def test_merge_entity_evidence_preserves_node_evidence_instead_of_ai_rewriting_it() -> None:
    original_fact = {
        "text": "Victoria Blackwood is named as a director.",
        "quote": "Victoria Blackwood — Director",
        "source_doc": "registry.pdf",
        "page": 2,
        "verification_status": "verified",
        "verification_reason": "Directly stated",
        "source_location": {"file_name": "registry.pdf", "page_start": 2},
    }
    original_insight = {
        "text": "The record identifies a corporate role.",
        "confidence": "high",
        "reasoning": "The title appears in the source.",
        "source_doc": "registry.pdf",
    }
    entities = [
        {
            "key": "source-1",
            "name": "Victoria Blackwood",
            "category": "Person",
            "verified_facts": [original_fact],
            "ai_insights": [original_insight],
            "source_files": ["registry.pdf"],
            "source_quotes": ["Victoria Blackwood — Director"],
            "source_claim_ids": ["claim-1"],
            "source_locations": [{"file_name": "registry.pdf", "page_start": 2}],
            "relationships": [],
        },
        {
            "key": "source-2",
            "name": "V. Blackwood",
            "category": "Person",
            "verified_facts": [],
            "ai_insights": [],
            "source_files": ["report.pdf"],
            "source_quotes": ["V. Blackwood"],
            "source_claim_ids": ["claim-2"],
            "source_locations": [{"file_name": "report.pdf", "page_start": 9}],
            "relationships": [],
        },
    ]
    ai_result = {
        "name": "Victoria Blackwood",
        "description": "Merged description",
        "summary": "Merged summary",
        "specific_type": "Director",
        "verified_facts": [{"text": "AI rewrote and stripped the fact"}],
        "ai_insights": [],
        "merged_properties": {},
    }
    evidence = merge_entity_evidence(ai_result, entities)

    assert evidence["verified_facts"] == [original_fact]
    assert evidence["ai_insights"] == [original_insight]
    assert evidence["source_claim_ids"] == ["claim-1", "claim-2"]
    assert evidence["source_locations"] == [
        {"file_name": "registry.pdf", "page_start": 2},
        {"file_name": "report.pdf", "page_start": 9},
    ]


def test_merge_result_is_persisted_in_the_job_state_for_terminal_recovery() -> None:
    state = build_merge_result_state(
        {"ai_runtime": {"provider": "openai"}},
        merged_entity_key="merged-1",
        relationship_count=12,
    )

    assert state == {
        "ai_runtime": {"provider": "openai"},
        "merge_result": {
            "merged_entity_key": "merged-1",
            "entity_count": 1,
            "relationship_count": 12,
        },
    }


def test_relationship_write_properties_replace_stale_endpoint_ids() -> None:
    original = {"case_id": "case-1", "detail": "Named director"}

    assert relationship_write_properties(
        original,
        merged_entity_key="merged-1",
        target_key="company-1",
        direction="outgoing",
    ) == {
        "case_id": "case-1",
        "detail": "Named director",
        "source_id": "merged-1",
        "target_id": "company-1",
    }
    assert relationship_write_properties(
        original,
        merged_entity_key="merged-1",
        target_key="person-2",
        direction="incoming",
    )["source_id"] == "person-2"
