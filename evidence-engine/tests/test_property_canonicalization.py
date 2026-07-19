from app.pipeline.property_canonicalization import (
    LOCATION_SPECIFICITY_LEVELS,
    canonicalize_properties,
    normalize_location_specificity,
    promote_location_specificity,
)
from app.ontology.loader import load_ontology
from app.ontology.prompt_builder import build_entity_extraction_prompt


def test_media_datetime_range_is_split_into_canonical_date_time_fields() -> None:
    props = canonicalize_properties(
        "Media",
        {"date": "2025-04-12 06:21:47-06:23:45"},
    )

    assert props["date"] == "2025-04-12"
    assert props["time"] == "06:21"
    assert props["end_time"] == "06:23"


def test_timestamp_alias_preserves_raw_value_and_adds_canonical_fields() -> None:
    props = canonicalize_properties(
        "Communication",
        {"timestamp": "2025-04-12T06:21:47-04:00"},
    )

    assert props["date"] == "2025-04-12"
    assert props["time"] == "06:21"
    assert props["timestamp_raw"] == "2025-04-12T06:21:47-04:00"
    assert "end_time" not in props


def test_space_timestamp_with_timezone_is_not_treated_as_a_time_range() -> None:
    props = canonicalize_properties(
        "Media",
        {"timestamp": "2025-04-12 06:21:47-04:00"},
    )

    assert props["date"] == "2025-04-12"
    assert props["time"] == "06:21"
    assert "end_time" not in props


def test_missing_time_can_be_recovered_from_supporting_text_when_date_matches() -> None:
    props = canonicalize_properties(
        "Media",
        {"date": "2025-04-12"},
        evidence_texts=[
            "Cellebrite image set 2025-04-12 06:21:47-06:23:45 includes 5289672309.jpg"
        ],
    )

    assert props["date"] == "2025-04-12"
    assert props["time"] == "06:21"
    assert props["end_time"] == "06:23"


def test_transaction_aliases_feed_financial_views_and_party_linking() -> None:
    props = canonicalize_properties(
        "Transaction",
        {
            "transaction_amount": "$1,250.00",
            "payer": "Timothy Valentin",
            "payee": "Cobalt Pier LLC",
        },
    )

    assert props["amount"] == "$1,250.00"
    assert props["sender"] == "Timothy Valentin"
    assert props["receiver"] == "Cobalt Pier LLC"


def test_geo_aliases_are_normalized_when_coordinates_are_valid() -> None:
    props = canonicalize_properties(
        "Location",
        {
            "place": "Camden Logistics Yard",
            "lat": "39.945",
            "lng": "-75.165",
        },
    )

    assert props["location_raw"] == "Camden Logistics Yard"
    assert props["latitude"] == 39.945
    assert props["longitude"] == -75.165


def test_location_specificity_vocabulary_is_ordered_from_unknown_to_exact() -> None:
    assert LOCATION_SPECIFICITY_LEVELS == (
        "unknown",
        "continent",
        "country",
        "region",
        "city",
        "district",
        "street",
        "exact_address",
    )
    assert normalize_location_specificity("neighbourhood") == "district"
    assert normalize_location_specificity("building") == "exact_address"
    assert normalize_location_specificity("not-a-real-level") is None


def test_structured_geo_fields_determine_specificity_conservatively() -> None:
    country = canonicalize_properties(
        "Location",
        {"location_raw": "Ireland", "country": "Ireland", "location_specificity": "exact"},
    )
    street = canonicalize_properties("Location", {"address": "Fleet Street"})
    numbered_street_name = canonicalize_properties("Location", {"address": "5th Avenue"})
    exact = canonicalize_properties("Location", {"address": "12 Fleet Street"})
    district = canonicalize_properties(
        "Location",
        {
            "location_raw": "Temple Bar",
            "city": "Dublin",
            "location_specificity": "district",
        },
    )

    assert country["location_specificity"] == "country"
    assert street["location_specificity"] == "street"
    assert numbered_street_name["location_specificity"] == "street"
    assert exact["location_specificity"] == "exact_address"
    assert district["location_specificity"] == "district"


def test_raw_location_defaults_to_unknown_and_accepts_model_granularity() -> None:
    vague = canonicalize_properties("Location", {"location_raw": "overseas"})
    continent = canonicalize_properties(
        "Location",
        {"location_raw": "Europe", "location_specificity": "continent"},
    )

    assert vague["location_specificity"] == "unknown"
    assert continent["location_specificity"] == "continent"


def test_source_coordinates_are_exact_but_geocoded_centroids_are_not_reclassified() -> None:
    extracted = canonicalize_properties(
        "Location",
        {"location_raw": "GPS fix", "latitude": 53.34, "longitude": -6.26},
    )
    geocoded_country = canonicalize_properties(
        "Location",
        {
            "location_raw": "Ireland",
            "country": "Ireland",
            "latitude": 53.4,
            "longitude": -8.0,
            "geocoding_status": "success",
        },
    )

    assert extracted["location_specificity"] == "exact_address"
    assert geocoded_country["location_specificity"] == "country"


def test_location_specificity_is_promoted_when_entities_merge() -> None:
    properties = {"location_specificity": "country"}

    promote_location_specificity(
        properties,
        {"location_specificity": "city"},
        {"location_specificity": "street"},
    )

    assert properties["location_specificity"] == "street"


def test_extraction_prompt_requires_specificity_without_suppressing_vague_locations() -> None:
    prompt = build_entity_extraction_prompt(
        "The subject travelled from Europe to 12 Fleet Street, London.",
        "report.txt",
        "Location review",
    )
    ontology = load_ontology()

    assert "Never omit a location solely because it is less specific than a city" in prompt
    assert (
        "unknown, continent, country, region, city, district, street, exact_address"
        in prompt
    )
    assert "LOCATION EXCEPTION: retain every source-supported geographic reference" in prompt
    assert all(
        any(
            prop.name == "location_specificity"
            for prop in ontology.get_category(category).properties
        )
        for category in ontology.geocodable_categories
    )


def test_string_aliases_become_a_list_not_characters() -> None:
    props = canonicalize_properties(
        "Person",
        {"aliases": "Tim, Timothy V.; TV"},
    )

    assert props["aliases"] == ["Tim", "Timothy V.", "TV"]
