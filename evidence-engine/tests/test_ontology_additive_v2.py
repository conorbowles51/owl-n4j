from app.ontology.loader import load_ontology


LEGACY_CATEGORIES = {
    "Person",
    "Organization",
    "Group",
    "Location",
    "Event",
    "Transaction",
    "Account",
    "FinancialInstrument",
    "Communication",
    "Document",
    "Media",
    "Vehicle",
    "Weapon",
    "Drug",
    "Device",
    "PhysicalEvidence",
    "CyberIdentity",
    "LegalAction",
    "Intelligence",
    "Other",
}

NEW_CATEGORIES = {
    "Company",
    "Bank",
    "DigitalAccount",
    "PhoneNumber",
    "NetworkIdentifier",
}

LEGACY_RELATIONSHIPS = {
    "KNOWN_ASSOCIATE_OF",
    "ALLEGED_ASSOCIATE_OF",
    "PHONE_ACTIVITY_OBSERVED_AT",
}

NEW_RELATIONSHIPS = {
    "DIRECTOR_OF",
    "SHAREHOLDER_OF",
    "HELD_AT",
    "SIGNATORY_ON",
    "RESULTED_IN",
}


def _property_names(category_name: str) -> set[str]:
    ontology = load_ontology()
    return {prop.name for prop in ontology.get_category(category_name).properties}


def test_new_categories_are_additive() -> None:
    ontology = load_ontology()

    assert LEGACY_CATEGORIES <= set(ontology.categories)
    assert NEW_CATEGORIES <= set(ontology.categories)
    assert ontology.version == "1.0"


def test_migration_sensitive_properties_and_enum_values_are_retained() -> None:
    ontology = load_ontology()

    assert {"institution", "holder"} <= _property_names("Account")
    assert {"sender", "receiver", "time"} <= _property_names("Transaction")
    assert {"participants", "time", "end_time"} <= _property_names("Communication")
    assert {"source_reliability", "information_credibility"} <= _property_names("Intelligence")
    assert {"other_type", "proposed_category"} <= _property_names("Other")

    financial_instrument = ontology.get_category("FinancialInstrument")
    instrument_type = next(
        prop for prop in financial_instrument.properties if prop.name == "instrument_type"
    )
    assert {"crypto_wallet", "wire_transfer"} <= set(instrument_type.enum)


def test_new_relationships_do_not_replace_evidentiary_relationships() -> None:
    ontology = load_ontology()
    relationship_types = set(ontology.relationship_types)

    assert LEGACY_RELATIONSHIPS <= relationship_types
    assert NEW_RELATIONSHIPS <= relationship_types

    phone_activity = ontology.get_relationship("PHONE_ACTIVITY_OBSERVED_AT")
    assert "PhoneNumber" in phone_activity.typical_source
    assert phone_activity.typical_target == ("Location",)


def test_new_categories_are_wired_into_existing_relationships_and_views() -> None:
    ontology = load_ontology()

    assert {"Company", "Bank", "Organization"} <= set(
        ontology.get_relationship("WORKS_FOR").typical_target
    )
    assert {"DigitalAccount", "PhoneNumber", "CyberIdentity"} <= set(
        ontology.get_relationship("COMMUNICATED_WITH").typical_source
    )
    assert {"Company", "Bank"} <= set(ontology.geocodable_categories)
