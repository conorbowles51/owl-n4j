from services.location_validation import (
    GEOCODING_STATUS_MAPPED,
    GEOCODING_STATUS_REJECTED,
    GEOCODING_STATUS_UNMAPPED_RETRIABLE,
    GeocodeProvenance,
    LocationRejectionReason,
    validate_location,
)


def test_accepts_valid_coordinate_for_allowed_entity_type():
    result = validate_location(
        latitude="51.5",
        longitude="-0.12",
        entity_type="Location",
        provenance=GeocodeProvenance(geocoder="nominatim", query="London"),
    )

    assert result.status == GEOCODING_STATUS_MAPPED
    assert result.latitude == 51.5
    assert result.longitude == -0.12


def test_rejects_non_numeric_coordinate():
    result = validate_location(latitude="north", longitude="-0.12", entity_type="Location")

    assert result.status == GEOCODING_STATUS_REJECTED
    assert result.rejection_reason == LocationRejectionReason.NON_NUMERIC


def test_rejects_out_of_range_latitude():
    result = validate_location(latitude=91, longitude=0.1, entity_type="Location")

    assert result.status == GEOCODING_STATUS_REJECTED
    assert result.rejection_reason == LocationRejectionReason.OUT_OF_RANGE_LATITUDE


def test_rejects_out_of_range_longitude():
    result = validate_location(latitude=45, longitude=-181, entity_type="Location")

    assert result.status == GEOCODING_STATUS_REJECTED
    assert result.rejection_reason == LocationRejectionReason.OUT_OF_RANGE_LONGITUDE


def test_rejects_null_island():
    result = validate_location(latitude=0, longitude=0, entity_type="Location")

    assert result.status == GEOCODING_STATUS_REJECTED
    assert result.rejection_reason == LocationRejectionReason.NULL_ISLAND


def test_rejects_disallowed_entity_type():
    result = validate_location(latitude=45, longitude=1, entity_type="Document")

    assert result.status == GEOCODING_STATUS_REJECTED
    assert result.rejection_reason == LocationRejectionReason.DISALLOWED_ENTITY_TYPE


def test_provider_failure_returns_retriable_unmapped_state():
    result = validate_location(
        latitude=None,
        longitude=None,
        entity_type="Location",
        provenance=GeocodeProvenance(
            provider_status=GEOCODING_STATUS_UNMAPPED_RETRIABLE,
            failure_reason="timeout",
        ),
    )

    assert result.status == GEOCODING_STATUS_UNMAPPED_RETRIABLE
    assert result.rejection_reason == LocationRejectionReason.PROVIDER_FAILURE
