from app.pipeline.property_canonicalization import canonicalize_properties


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


def test_string_aliases_become_a_list_not_characters() -> None:
    props = canonicalize_properties(
        "Person",
        {"aliases": "Tim, Timothy V.; TV"},
    )

    assert props["aliases"] == ["Tim", "Timothy V.", "TV"]
