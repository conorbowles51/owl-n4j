import json

import pytest

from app.pipeline import verify_claims
from app.pipeline.extract_entities import RawEntity, RawRelationship


@pytest.mark.asyncio
async def test_bounded_verifier_quarantines_inference_and_uncertain_relationships(
    monkeypatch,
) -> None:
    async def fake_completion(**kwargs) -> str:
        candidates = json.loads(
            kwargs["messages"][1]["content"].split("CANDIDATES:\n", 1)[1]
        )
        decisions = []
        for candidate in candidates:
            statement = candidate["statement"]
            if "supervisory responsibilities" in statement:
                decision = "REJECTED"
            elif candidate["claim_type"] == "relationship":
                decision = "UNCERTAIN"
            else:
                decision = "SUPPORTED"
            decisions.append(
                {
                    "candidate_id": candidate["candidate_id"],
                    "decision": decision,
                    "reason": "Test decision",
                }
            )
        return json.dumps({"decisions": decisions})

    monkeypatch.setattr(verify_claims, "chat_completion", fake_completion)
    monkeypatch.setattr(verify_claims.settings, "claim_verification_max_claims", 20)
    location = {"source_document_id": "evidence-1", "quote_start_char": 10}
    entity = RawEntity(
        "E1",
        "Person",
        "Person",
        "Vanderhoff",
        source_quote="Vanderhoff — Field Training Officer/Supervisor",
        source_location=location,
        verified_facts=[
            {
                "text": "Vanderhoff had supervisory responsibilities for the unit.",
                "quote": "Vanderhoff — Field Training Officer/Supervisor",
                "source_location": location,
            },
            {
                "text": "Vanderhoff is listed as Field Training Officer/Supervisor.",
                "quote": "Vanderhoff — Field Training Officer/Supervisor",
                "source_location": location,
            },
        ],
    )
    relationship = RawRelationship(
        "E1",
        "E2",
        "SUPERVISES",
        detail="Supervises the unit",
        source_quote="Vanderhoff — Field Training Officer/Supervisor",
        source_location=location,
    )

    result = await verify_claims.verify_grounded_claims([entity], [relationship])
    projected_entities, projected_relationships = result.projection_inputs()

    assert [fact["verification_status"] for fact in entity.verified_facts] == [
        "rejected",
        "verified",
    ]
    assert relationship.verification_status == "uncertain"
    assert [fact["text"] for fact in projected_entities[0].verified_facts] == [
        "Vanderhoff is listed as Field Training Officer/Supervisor."
    ]
    assert projected_relationships == []


@pytest.mark.asyncio
async def test_unreviewed_claims_are_quarantined_when_budget_is_exhausted(
    monkeypatch,
) -> None:
    async def fake_completion(**kwargs) -> str:
        candidates = json.loads(
            kwargs["messages"][1]["content"].split("CANDIDATES:\n", 1)[1]
        )
        return json.dumps(
            {
                "decisions": [
                    {
                        "candidate_id": candidate["candidate_id"],
                        "decision": "SUPPORTED",
                        "reason": "Directly stated",
                    }
                    for candidate in candidates
                ]
            }
        )

    monkeypatch.setattr(verify_claims, "chat_completion", fake_completion)
    monkeypatch.setattr(verify_claims.settings, "claim_verification_max_claims", 1)
    location = {"source_document_id": "evidence-1", "quote_start_char": 0}
    entity = RawEntity(
        "E1",
        "Person",
        "Person",
        "Alex Smith",
        source_quote="Alex Smith",
        source_location=location,
        verified_facts=[
            {"text": "Alex Smith attended.", "quote": "Alex Smith attended.", "source_location": location},
            {"text": "Alex Smith approved.", "quote": "Alex Smith approved.", "source_location": location},
        ],
    )

    result = await verify_claims.verify_grounded_claims([entity], [])
    projected_entities, _ = result.projection_inputs()

    assert result.unreviewed_count == 1
    assert entity.verified_facts[0]["verification_status"] == "verified"
    assert entity.verified_facts[0]["verification_reason"] == "Directly stated"
    assert entity.verified_facts[1]["verification_status"] == "unreviewed"
    assert [fact["text"] for fact in projected_entities[0].verified_facts] == [
        "Alex Smith attended."
    ]


@pytest.mark.asyncio
async def test_relationship_verifier_uses_entity_names_in_statement(monkeypatch) -> None:
    captured = {}

    async def fake_completion(**kwargs) -> str:
        candidates = json.loads(
            kwargs["messages"][1]["content"].split("CANDIDATES:\n", 1)[1]
        )
        captured.update(candidates[0])
        return json.dumps(
            {
                "decisions": [
                    {
                        "candidate_id": candidates[0]["candidate_id"],
                        "decision": "SUPPORTED",
                        "reason": "Directly stated",
                    }
                ]
            }
        )

    monkeypatch.setattr(verify_claims, "chat_completion", fake_completion)
    monkeypatch.setattr(verify_claims.settings, "claim_verification_max_claims", 10)
    location = {"source_document_id": "evidence-1", "quote_start_char": 0}
    entities = [
        RawEntity("E1", "Person", "Person", "Marcus Chen"),
        RawEntity("E2", "Organization", "Vendor", "Nexus Trading Ltd"),
    ]
    relationship = RawRelationship(
        "E1",
        "E2",
        "ADDED_AS_VENDOR",
        detail="Marcus Chen added Nexus as a vendor.",
        source_quote="Marcus Chen added Nexus Trading Ltd as a vendor.",
        source_location=location,
    )

    await verify_claims.verify_grounded_claims(entities, [relationship])

    assert captured["source_entity"] == "Marcus Chen"
    assert captured["target_entity"] == "Nexus Trading Ltd"
    assert captured["statement"].startswith(
        "Marcus Chen ADDED_AS_VENDOR Nexus Trading Ltd"
    )


@pytest.mark.asyncio
async def test_verifier_uses_same_chunk_context_for_table_and_heading_entailment(
    monkeypatch,
) -> None:
    captured: dict = {}

    async def fake_completion(**kwargs) -> str:
        prompt = kwargs["messages"][1]["content"]
        captured["prompt"] = prompt
        candidates = json.loads(prompt.split("CANDIDATES:\n", 1)[1])
        captured.update(candidates[0])
        return json.dumps(
            {
                "decisions": [
                    {
                        "candidate_id": candidates[0]["candidate_id"],
                        "decision": "SUPPORTED",
                        "reason": "The table heading establishes the subject of the row.",
                    }
                ]
            }
        )

    monkeypatch.setattr(verify_claims, "chat_completion", fake_completion)
    monkeypatch.setattr(verify_claims.settings, "claim_verification_max_claims", 10)
    location = {"source_document_id": "evidence-1", "quote_start_char": 40}
    entity = RawEntity(
        "E1",
        "Organization",
        "Company",
        "Nexus Trading Ltd",
        verified_facts=[
            {
                "text": "Victoria Blackwood was appointed to Nexus Trading Ltd on 14 February 2022.",
                "quote": "Victoria Blackwood | Appointed: February 14, 2022",
                "source_location": location,
                "_verification_context": (
                    "NEXUS TRADING LTD — Officers\n"
                    "Name | Appointment date\n"
                    "Victoria Blackwood | Appointed: February 14, 2022"
                ),
            }
        ],
    )

    result = await verify_claims.verify_grounded_claims([entity], [])

    assert result.rejected_count == 0
    assert entity.verified_facts[0]["verification_status"] == "verified"
    assert captured["evidence_context"].startswith("NEXUS TRADING LTD")
    assert "headings, labels, and table structure" in captured["prompt"]
    assert "Natural paraphrase is allowed" in captured["prompt"]


@pytest.mark.asyncio
async def test_bounded_budget_prioritizes_relationships_over_low_importance_facts(
    monkeypatch,
) -> None:
    reviewed = []

    async def fake_completion(**kwargs) -> str:
        candidates = json.loads(
            kwargs["messages"][1]["content"].split("CANDIDATES:\n", 1)[1]
        )
        reviewed.extend(candidate["claim_type"] for candidate in candidates)
        return json.dumps(
            {
                "decisions": [
                    {
                        "candidate_id": candidate["candidate_id"],
                        "decision": "SUPPORTED",
                        "reason": "Directly stated",
                    }
                    for candidate in candidates
                ]
            }
        )

    monkeypatch.setattr(verify_claims, "chat_completion", fake_completion)
    monkeypatch.setattr(verify_claims.settings, "claim_verification_max_claims", 1)
    location = {"source_document_id": "evidence-1", "quote_start_char": 0}
    entities = [
        RawEntity(
            "E1",
            "Person",
            "Person",
            "Alex Smith",
            verified_facts=[
                {
                    "text": "Alex Smith attended.",
                    "quote": "Alex Smith attended.",
                    "source_location": location,
                    "importance": 1,
                }
            ],
        ),
        RawEntity("E2", "Organization", "Vendor", "Acme Ltd"),
    ]
    relationship = RawRelationship(
        "E1",
        "E2",
        "WORKS_FOR",
        source_quote="Alex Smith works for Acme Ltd.",
        source_location=location,
    )

    result = await verify_claims.verify_grounded_claims(entities, [relationship])

    assert reviewed == ["relationship"]
    assert relationship.verification_status == "verified"
    assert entities[0].verified_facts[0]["verification_status"] == "unreviewed"
    assert result.unreviewed_count == 1
