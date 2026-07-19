"""
Regression fixtures for coordinate validation and geocoding provenance on
the Cellebrite ingestion path.

Device telemetry (GPS fixes, cell-tower registrations) is where garbage
coordinates are most likely to appear — 0,0 cold starts, out-of-range
carves — so this suite pins down that invalid values never reach the graph
as pins, that every written location carries provenance, and that a
reverse-geocoder failure never fabricates or drops a device pin.
"""

import pytest

from app.pipeline.cellebrite import neo4j_writer as writer_module
from app.pipeline.cellebrite.models import CellebriteReport, ParsedModel
from app.pipeline.cellebrite.neo4j_writer import CellebriteNeo4jWriter
from app.services.location_validation import ALLOWED_COORDINATE_ENTITY_TYPES


class FakeDb:
    def __init__(self) -> None:
        self.calls = []

    def run_query(self, query, **params):
        self.calls.append({"query": query, "params": params})


def make_writer(db: FakeDb) -> CellebriteNeo4jWriter:
    return CellebriteNeo4jWriter(
        db,
        case_id="case-1",
        report_key="report-1",
        report=CellebriteReport(),
    )


def location_model(lat, lon, *, fields=None, model_id="abcdef1234567890") -> ParsedModel:
    position = ParsedModel(
        model_type="Coordinate",
        fields={"Latitude": lat, "Longitude": lon},
    )
    return ParsedModel(
        model_type="Location",
        model_id=model_id,
        fields={"Source": "Native GPS", **(fields or {})},
        model_fields={"Position": position},
    )


def cell_tower_model(lat, lon, *, fields=None, model_id="fedcba0987654321") -> ParsedModel:
    return ParsedModel(
        model_type="CellTower",
        model_id=model_id,
        fields={"CellId": "31026", "Latitude": lat, "Longitude": lon, **(fields or {})},
    )


def written_props(db: FakeDb) -> dict:
    assert db.calls, "expected a node write"
    return db.calls[0]["params"]["props"]


def test_valid_gps_location_writes_coordinates_with_provenance(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(writer_module, "_geocode_lat_lon", lambda lat, lon: None)
    db = FakeDb()
    make_writer(db)._write_location(location_model("51.5074", "-0.1278", fields={"Confidence": "High"}))

    props = written_props(db)
    assert props["latitude"] == pytest.approx(51.5074)
    assert props["longitude"] == pytest.approx(-0.1278)
    assert props["geocoding_status"] == "mapped"
    assert props["geocoding_provider"] == "cellebrite"
    assert props["geocoding_precision"] == "gps"
    assert props["geocoding_confidence"] == "high"


def test_null_island_location_is_rejected_and_never_becomes_a_pin(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(lat, lon):
        raise AssertionError("invalid coordinates must not be reverse-geocoded")

    monkeypatch.setattr(writer_module, "_geocode_lat_lon", fail)
    db = FakeDb()
    make_writer(db)._write_location(location_model("0", "0"))

    props = written_props(db)
    assert "latitude" not in props
    assert "longitude" not in props
    assert props["geocoding_status"] == "rejected"
    assert props["geocoding_rejection_reason"] == "null_island"


def test_out_of_range_location_is_rejected_with_reason(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(writer_module, "_geocode_lat_lon", lambda lat, lon: None)
    db = FakeDb()
    make_writer(db)._write_location(location_model("91.2", "10.0"))

    props = written_props(db)
    assert "latitude" not in props
    assert "longitude" not in props
    assert props["geocoding_status"] == "rejected"
    assert props["geocoding_rejection_reason"] == "out_of_range_latitude"


def test_non_numeric_coordinates_never_write_a_location() -> None:
    db = FakeDb()
    make_writer(db)._write_location(location_model("fifty-one", "north"))

    assert db.calls == []


def test_device_provided_address_is_exposed_as_formatted_address() -> None:
    model = location_model("48.8566", "2.3522")
    model.model_fields["PositionAddress"] = ParsedModel(
        model_type="Address",
        fields={"Street": "Rue de Rivoli", "City": "Paris", "Country": "France"},
    )
    db = FakeDb()
    make_writer(db)._write_location(model)

    props = written_props(db)
    assert props["location_formatted"] == "Rue de Rivoli, Paris, France"
    assert props["geocode_source"] == "cellebrite"
    assert props["geocoding_provider"] == "cellebrite"


def test_reverse_geocoded_address_records_provider_and_query(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        writer_module,
        "_geocode_lat_lon",
        lambda lat, lon: {
            "address": "10 Downing Street, London",
            "place_name": "London",
            "country": "United Kingdom",
            "geocode_source": "nominatim",
            "geocode_accuracy": "building",
        },
    )
    db = FakeDb()
    make_writer(db)._write_location(location_model("51.5034", "-0.1276"))

    props = written_props(db)
    assert props["geocode_source"] == "nominatim"
    assert props["geocoding_query"] == "reverse:51.5034,-0.1276"
    assert props["location_formatted"] == "10 Downing Street, London"


def test_reverse_geocoder_failure_keeps_device_pin_without_fabricating_address(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def explode(lat, lon):
        raise RuntimeError("no network")

    monkeypatch.setattr(writer_module, "_geocode_lat_lon", explode)
    db = FakeDb()
    make_writer(db)._write_location(location_model("51.5074", "-0.1278"))

    props = written_props(db)
    assert props["latitude"] == pytest.approx(51.5074)
    assert props["longitude"] == pytest.approx(-0.1278)
    assert props["geocoding_status"] == "mapped"
    assert "address" not in props
    assert "location_formatted" not in props
    assert "geocoding_query" not in props


def test_cell_tower_is_an_allowed_coordinate_entity_type() -> None:
    assert "CellTower" in ALLOWED_COORDINATE_ENTITY_TYPES


def test_valid_cell_tower_writes_coordinates_with_provenance() -> None:
    db = FakeDb()
    make_writer(db)._write_cell_tower(cell_tower_model("53.3498", "-6.2603", fields={"Confidence": "0.9"}))

    props = written_props(db)
    assert props["latitude"] == pytest.approx(53.3498)
    assert props["longitude"] == pytest.approx(-6.2603)
    assert props["geocoding_status"] == "mapped"
    assert props["geocoding_provider"] == "cellebrite"
    assert props["geocoding_precision"] == "cell_tower"
    assert props["geocoding_confidence"] == "high"


def test_null_island_cell_tower_keeps_radio_evidence_but_never_a_pin() -> None:
    db = FakeDb()
    make_writer(db)._write_cell_tower(cell_tower_model("0", "0"))

    props = written_props(db)
    assert props["cell_id"] == "31026"
    assert "latitude" not in props
    assert "longitude" not in props
    assert props["geocoding_status"] == "rejected"
    assert props["geocoding_rejection_reason"] == "null_island"


def test_out_of_range_cell_tower_coordinates_are_rejected() -> None:
    db = FakeDb()
    make_writer(db)._write_cell_tower(cell_tower_model("53.3498", "-200.5"))

    props = written_props(db)
    assert "latitude" not in props
    assert "longitude" not in props
    assert props["geocoding_status"] == "rejected"
    assert props["geocoding_rejection_reason"] == "out_of_range_longitude"
