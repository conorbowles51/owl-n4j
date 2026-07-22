from app.pipeline.extract_entities import RawEntity, RawRelationship
from app.services.claim_ledger import (
    attach_claim_ids,
    compile_grounded_claims,
    rebuild_observations_from_claims,
)


def test_grounded_claim_compilation_is_deterministic_and_atomic() -> None:
    location = {
        "source_document_id": "evidence-1",
        "revision_id": "revision-1",
        "source_file": "Report.pdf",
        "chunk_index": 2,
        "page_start": 3,
        "page_end": 3,
        "quote_start_char": 100,
        "quote_end_char": 120,
        "coordinate_space": "document_text",
    }
    entity = RawEntity(
        "E1",
        "Person",
        "Person",
        "Marcus Chen",
        source_quote="Marcus Chen approved",
        source_file="Report.pdf",
        source_location=location,
        confidence=0.9,
        verified_facts=[
            {
                "text": "Marcus Chen approved the payment.",
                "quote": "Marcus Chen approved",
                "page": 3,
                "source_doc": "Report.pdf",
                "source_location": location,
            }
        ],
    )
    relationship = RawRelationship(
        "E1",
        "E2",
        "APPROVED",
        detail="Approved the payment",
        source_quote="Marcus Chen approved",
        source_file="Report.pdf",
        source_location=location,
        confidence=0.8,
    )

    first = compile_grounded_claims(
        entities=[entity],
        relationships=[relationship],
        case_id="case-1",
        evidence_file_id="evidence-1",
        revision_id="revision-1",
        engine_job_id="job-1",
    )
    second = compile_grounded_claims(
        entities=[entity],
        relationships=[relationship],
        case_id="case-1",
        evidence_file_id="evidence-1",
        revision_id="revision-1",
        engine_job_id="job-2",
    )

    assert [claim.id for claim in first] == [claim.id for claim in second]
    assert [claim.claim_type for claim in first] == [
        "entity_mention",
        "entity_fact",
        "relationship",
    ]
    assert all(claim.source_location == location for claim in first)
    assert all(claim.status == "grounded" for claim in first)

    attach_claim_ids([entity], [relationship], first)

    assert entity.source_claim_ids == [first[0].id, first[1].id]
    assert relationship.source_claim_ids == [first[2].id]

    rebuilt_entities, rebuilt_relationships = rebuild_observations_from_claims(first)

    assert len(rebuilt_entities) == 1
    assert rebuilt_entities[0].name == "Marcus Chen"
    assert rebuilt_entities[0].verified_facts[0]["text"] == "Marcus Chen approved the payment."
    assert rebuilt_entities[0].source_claim_ids == [first[0].id, first[1].id]
    assert len(rebuilt_relationships) == 1
    assert rebuilt_relationships[0].source_claim_ids == [first[2].id]


def test_unreviewed_claims_are_retained_but_not_rebuilt_for_projection() -> None:
    location = {"source_document_id": "evidence-1", "source_file": "Report.pdf"}
    entity = RawEntity(
        "E1",
        "Person",
        "Person",
        "Alex Smith",
        verified_facts=[
            {
                "text": "Alex Smith approved the payment.",
                "quote": "Alex Smith approved",
                "source_location": location,
                "verification_status": "unreviewed",
            }
        ],
    )
    claims = compile_grounded_claims(
        entities=[entity],
        relationships=[],
        case_id="case-1",
        evidence_file_id="evidence-1",
        revision_id="revision-1",
        engine_job_id="job-1",
    )

    assert claims[0].status == "unreviewed"
    rebuilt_entities, rebuilt_relationships = rebuild_observations_from_claims(claims)
    assert rebuilt_entities == []
    assert rebuilt_relationships == []
