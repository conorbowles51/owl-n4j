from app.pipeline.link_transaction_parties import link_transaction_parties
from app.pipeline.resolve_entities import ResolvedEntity, ResolvedRelationship
from app.pipeline.resolve_relationships import _canonicalize_semantics


def _entity(entity_id: str, category: str, name: str, **properties):
    return ResolvedEntity(
        id=entity_id,
        category=category,
        specific_type=category,
        name=name,
        properties=properties,
    )


def test_linked_receiver_points_from_party_to_transaction_and_inherits_provenance():
    receiver = _entity("org", "Organization", "Nexus Trading Ltd")
    transaction = _entity(
        "tx",
        "Transaction",
        "Payment 1",
        receiver="Nexus Trading Ltd",
    )
    transaction.source_files = ["bank.pdf"]
    transaction.source_quotes = ["Paid to Nexus Trading Ltd"]
    transaction.source_locations = [{"source_file": "bank.pdf", "page_start": 1}]
    transaction.source_claim_ids = ["claim-1"]

    relationships = link_transaction_parties([receiver, transaction], [])

    assert len(relationships) == 1
    relationship = relationships[0]
    assert relationship.source_entity_id == receiver.id
    assert relationship.target_entity_id == transaction.id
    assert relationship.type == "RECEIVED_PAYMENT"
    assert relationship.source_claim_ids == ["claim-1"]
    assert relationship.source_locations[0]["page_start"] == 1


def test_canonicalization_preserves_allegation_and_does_not_call_phone_activity_travel():
    person = _entity("person", "Person", "Marcus Chen")
    location = _entity("location", "Location", "London")
    other = _entity("other", "Person", "David Okonkwo")
    relationships = [
        ResolvedRelationship(
            source_entity_id=person.id,
            target_entity_id=location.id,
            type="TRAVELED_TO",
            detail="Phone connected to a cell tower in London",
            source_quotes=["the handset used a London cell tower"],
        ),
        ResolvedRelationship(
            source_entity_id=person.id,
            target_entity_id=other.id,
            type="KNOWN_ASSOCIATE_OF",
            detail="described as an alleged co-conspirator",
            source_quotes=["alleged co-conspirator"],
        ),
    ]

    result = _canonicalize_semantics(relationships, [person, location, other])

    assert result[0].type == "PHONE_ACTIVITY_OBSERVED_AT"
    assert result[1].type == "ALLEGED_ASSOCIATE_OF"
    assert result[1].properties["assertion_status"] == "alleged"
