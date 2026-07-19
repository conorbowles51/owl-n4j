import json
import unittest
import uuid
from datetime import datetime, timezone
from unittest.mock import Mock, patch

from postgres.models.graph_recycle_bin import GraphRecycleBinItem
from routers import graph
from services.neo4j.graph_edit_service import GraphEditService
from services.neo4j.timeline_service import TimelineService


class _FakeResult:
    def __init__(self, record=None):
        self._record = record or {
            "labels": ["Communication"],
            "properties": {
                "key": "event-1",
                "case_id": "case-1",
                "date": "2024-01-02",
                "manual_fields": ["category", "date"],
            },
        }

    def single(self):
        return self._record


class _FakeSession:
    def __init__(self, captured, record=None):
        self._captured = captured
        self._record = record

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def run(self, query, **params):
        self._captured["query"] = query
        self._captured["params"] = params
        return _FakeResult(self._record)


class _FakeQuery:
    def __init__(self, item):
        self._item = item

    def filter(self, *args):
        return self

    def order_by(self, *args):
        return self

    def with_for_update(self):
        return self

    def first(self):
        return self._item


class _FakeDB:
    def __init__(self, item=None):
        self.items = []
        self.item = item
        self.commits = 0
        self.rollbacks = 0

    def add(self, item):
        self.items.append(item)
        self.item = item

    def commit(self):
        self.commits += 1

    def refresh(self, item):
        return None

    def rollback(self):
        self.rollbacks += 1

    def query(self, model):
        return _FakeQuery(self.item)


class GraphEditServiceTests(unittest.TestCase):
    def test_rejects_system_property_edits(self):
        service = GraphEditService()
        service._fetch_node = Mock(
            return_value={
                "labels": ["Person"],
                "category": "Person",
                "properties": {"key": "person-1", "case_id": "case-1"},
            }
        )

        with self.assertRaisesRegex(ValueError, "system field"):
            service.update_node(
                "person-1",
                case_id="case-1",
                properties={"job_id": "job-123"},
            )

    def test_rejects_generic_location_property_edits(self):
        service = GraphEditService()
        service._fetch_node = Mock(
            return_value={
                "labels": ["Location"],
                "category": "Location",
                "properties": {"key": "loc-1", "case_id": "case-1"},
            }
        )

        with self.assertRaisesRegex(ValueError, "geocode flow"):
            service.update_node(
                "loc-1",
                case_id="case-1",
                properties={"latitude": 51.5},
            )

    def test_relabels_ontology_category_and_marks_manual_fields(self):
        service = GraphEditService()
        service._fetch_node = Mock(
            return_value={
                "labels": ["Event"],
                "category": "Event",
                "properties": {"key": "event-1", "case_id": "case-1", "date": "2024-01-01"},
            }
        )
        captured = {}

        with patch(
            "services.neo4j.graph_edit_service.driver.session",
            return_value=_FakeSession(captured),
        ):
            result = service.update_node(
                "event-1",
                case_id="case-1",
                category="Communication",
                properties={"date": "2024-01-02"},
                edited_by="investigator",
                source_view="timeline",
            )

        self.assertTrue(result["success"])
        self.assertIn("REMOVE n:`Event`", captured["query"])
        self.assertIn("SET n:`Communication`", captured["query"])
        self.assertEqual(
            captured["params"]["manual_fields"],
            ["date", "category"],
        )

    def test_apply_geocoded_location_records_manual_snapshot(self):
        service = GraphEditService()
        case_id = str(uuid.uuid4())
        service._fetch_node = Mock(
            return_value={
                "labels": ["Location"],
                "category": "Location",
                "properties": {
                    "key": "loc-1",
                    "case_id": case_id,
                    "name": "Old Place",
                    "latitude": 1.0,
                    "longitude": 2.0,
                    "location_formatted": "Old Place",
                    "geocoding_confidence": "low",
                    "manual_fields": [],
                },
            }
        )
        captured = {}
        db = _FakeDB()
        record = {
            "labels": ["Location"],
            "properties": {
                "key": "loc-1",
                "latitude": 51.5,
                "longitude": -0.12,
                "location_formatted": "London, UK",
                "geocoding_confidence": "manual",
            },
        }

        with patch(
            "services.neo4j.graph_edit_service.driver.session",
            return_value=_FakeSession(captured, record),
        ):
            result = service.apply_geocoded_location(
                "loc-1",
                case_id=case_id,
                address="London",
                latitude=51.5,
                longitude=-0.12,
                formatted_address="London, UK",
                geocoder_confidence="high",
                edited_by="investigator",
                source_view="map_popup",
                db=db,
            )

        self.assertEqual(result["confidence"], "manual")
        self.assertEqual(db.items[0].item_type, "location_relocation")
        self.assertEqual(db.items[0].status, "active")
        self.assertEqual(db.items[0].snapshot["before_location"]["latitude"], 1.0)
        self.assertEqual(db.items[0].snapshot["after_location"]["geocoding_confidence"], "manual")
        self.assertEqual(db.items[0].snapshot["after_location"]["location_source"], "manual")
        self.assertEqual(captured["params"]["updates"]["geocoding_confidence"], "manual")
        self.assertEqual(captured["params"]["updates"]["location_source"], "manual")
        self.assertIn("geocoding_confidence", captured["params"]["manual_fields"])

    def test_undo_last_location_relocation_restores_previous_location(self):
        service = GraphEditService()
        case_id = str(uuid.uuid4())
        item = GraphRecycleBinItem(
            case_id=uuid.UUID(case_id),
            recycle_key="location_relocation_loc-1",
            item_type="location_relocation",
            original_key="loc-1",
            original_name="London",
            original_type="Location",
            reason="location_relocation",
            deleted_by="investigator",
            deleted_at=datetime.now(timezone.utc),
            relationship_count=0,
            status="active",
            snapshot={
                "before_location": {
                    "latitude": 1.0,
                    "longitude": 2.0,
                    "location_raw": "Old",
                    "location_formatted": "Old",
                    "location_name": "Old",
                    "geocoding_status": "success",
                    "geocoding_confidence": "low",
                },
                "before_manual_fields": ["name"],
            },
        )
        db = _FakeDB(item)
        captured = {}
        record = {
            "labels": ["Location"],
            "properties": {
                "key": "loc-1",
                "latitude": 1.0,
                "longitude": 2.0,
                "location_formatted": "Old",
                "geocoding_confidence": "low",
            },
        }

        with patch(
            "services.neo4j.graph_edit_service.driver.session",
            return_value=_FakeSession(captured, record),
        ):
            result = service.undo_last_location_relocation(
                "loc-1",
                case_id=case_id,
                edited_by="investigator",
                source_view="map_popup",
                db=db,
            )

        self.assertTrue(result["undone"])
        self.assertEqual(item.status, "restored")
        self.assertEqual(captured["params"]["restore_updates"]["latitude"], 1.0)
        self.assertEqual(captured["params"]["manual_fields"], ["name"])

    def test_geocoded_location_appends_manual_correction_history(self):
        service = GraphEditService()
        service._fetch_node = Mock(
            return_value={
                "labels": ["Location"],
                "category": "Location",
                "properties": {
                    "key": "loc-1",
                    "case_id": "case-1",
                    "latitude": 51.5,
                    "longitude": -0.12,
                    "manual_correction_history": json.dumps(
                        [{"moved_by": "analyst", "moved_at": "2026-07-17T12:00:00+00:00"}]
                    ),
                },
            }
        )
        captured = {}

        with patch(
            "services.neo4j.graph_edit_service.driver.session",
            return_value=_FakeSession(captured),
        ):
            result = service.update_geocoded_location(
                "loc-1",
                case_id="case-1",
                query="London",
                latitude=51.501,
                longitude=-0.141,
                formatted_address="London, UK",
                confidence="high",
                provider="nominatim",
                location_granularity="city",
                edited_by="investigator",
                edited_by_name="Investigator One",
            )

        history = json.loads(captured["params"]["updates"]["manual_correction_history"])
        self.assertTrue(result["success"])
        self.assertEqual(len(history), 2)
        self.assertEqual(history[-1]["moved_by"], "investigator")
        self.assertEqual(history[-1]["moved_by_name"], "Investigator One")
        self.assertEqual(history[-1]["from_latitude"], 51.5)
        self.assertEqual(history[-1]["from_longitude"], -0.12)
        self.assertEqual(history[-1]["to_latitude"], 51.501)
        self.assertEqual(history[-1]["to_longitude"], -0.141)
        self.assertEqual(captured["params"]["updates"]["geocoding_provider"], "nominatim")

    def test_apply_geocoded_location_appends_manual_correction_history(self):
        service = GraphEditService()
        case_id = str(uuid.uuid4())
        service._fetch_node = Mock(
            return_value={
                "labels": ["Location"],
                "category": "Location",
                "properties": {
                    "key": "loc-1",
                    "case_id": case_id,
                    "latitude": 51.5,
                    "longitude": -0.12,
                    "manual_correction_history": json.dumps(
                        [{"moved_by": "analyst", "moved_at": "2026-07-17T12:00:00+00:00"}]
                    ),
                },
            }
        )
        captured = {}
        db = _FakeDB()
        record = {
            "labels": ["Location"],
            "properties": {"key": "loc-1", "latitude": 51.501, "longitude": -0.141},
        }

        with patch(
            "services.neo4j.graph_edit_service.driver.session",
            return_value=_FakeSession(captured, record),
        ):
            service.apply_geocoded_location(
                "loc-1",
                case_id=case_id,
                address="London",
                latitude=51.501,
                longitude=-0.141,
                formatted_address="London, UK",
                geocoder_confidence="high",
                provider="nominatim",
                location_granularity="city",
                edited_by="investigator",
                edited_by_name="Investigator One",
                db=db,
            )

        history = json.loads(captured["params"]["updates"]["manual_correction_history"])
        self.assertEqual(len(history), 2)
        self.assertEqual(history[-1]["moved_by"], "investigator")
        self.assertEqual(history[-1]["moved_by_name"], "Investigator One")
        self.assertEqual(history[-1]["from_latitude"], 51.5)
        self.assertEqual(history[-1]["to_latitude"], 51.501)
        self.assertEqual(captured["params"]["updates"]["geocoding_provider"], "nominatim")
        self.assertEqual(captured["params"]["updates"]["location_granularity"], "city")


class GraphGeocodeRouteTests(unittest.IsolatedAsyncioTestCase):
    async def test_geocode_preview_does_not_persist(self):
        with patch(
            "services.geo_rescan_service.geocode_with_cache",
            return_value={
                "latitude": 51.5,
                "longitude": -0.12,
                "formatted_address": "London, UK",
                "confidence": "high",
            },
        ), patch.object(graph.neo4j_service, "update_graph_node") as update:
            result = await graph.geocode_node(
                "loc-1",
                graph.GeocodeNodeRequest(case_id="case-1", address="London"),
                apply=False,
                user={"username": "investigator"},
            )

        update.assert_not_called()
        self.assertEqual(result["latitude"], 51.5)
        self.assertFalse(result["applied"])

    async def test_geocode_apply_uses_location_correction_service(self):
        db = Mock()
        with patch(
            "services.geo_rescan_service.geocode_with_cache",
            return_value={
                "latitude": 51.5,
                "longitude": -0.12,
                "formatted_address": "London, UK",
                "confidence": "high",
            },
        ), patch.object(
            graph.neo4j_service,
            "apply_geocoded_location",
            return_value={
                "success": True,
                "latitude": 51.5,
                "longitude": -0.12,
                "formatted_address": "London, UK",
                "confidence": "manual",
                "geocoder_confidence": "high",
                "applied": True,
                "undo_key": "location_relocation_loc-1",
            },
        ) as apply_correction, patch.object(graph.system_log_service, "log"):
            result = await graph.geocode_node(
                "loc-1",
                graph.GeocodeNodeRequest(
                    case_id="case-1",
                    address="London",
                    source_view="evidence_panel",
                ),
                apply=True,
                user={"username": "investigator"},
                db=db,
            )

        apply_correction.assert_called_once()
        self.assertEqual(apply_correction.call_args.kwargs["source_view"], "evidence_panel")
        self.assertEqual(apply_correction.call_args.kwargs["db"], db)
        self.assertEqual(result["confidence"], "manual")
        self.assertEqual(result["geocoder_confidence"], "high")

    async def test_geocode_apply_persists_provenance_and_correction(self):
        db = Mock()
        with patch(
            "services.geo_rescan_service.geocode_with_cache",
            return_value={
                "provider": "nominatim",
                "query": "London",
                "latitude": 51.5,
                "longitude": -0.12,
                "formatted_address": "London, UK",
                "confidence": "high",
                "location_granularity": "city",
            },
        ), patch.object(
            graph.neo4j_service,
            "apply_geocoded_location",
            return_value={
                "success": True,
                "confidence": "manual",
                "undo_key": "location_relocation_loc-1",
            },
        ) as apply_correction, patch.object(graph.system_log_service, "log"):
            result = await graph.geocode_node(
                "loc-1",
                graph.GeocodeNodeRequest(case_id="case-1", address="London"),
                apply=True,
                user={"username": "investigator", "name": "Investigator One"},
                db=db,
            )

        apply_correction.assert_called_once_with(
            "loc-1",
            case_id="case-1",
            address="London",
            latitude=51.5,
            longitude=-0.12,
            formatted_address="London, UK",
            geocoder_confidence="high",
            provider="nominatim",
            location_granularity="city",
            edited_by="investigator",
            edited_by_name="Investigator One",
            source_view="map",
            db=db,
        )
        self.assertTrue(result["applied"])
        self.assertEqual(result["provider"], "nominatim")
        self.assertEqual(result["location_granularity"], "city")


class TimelineNormalisationTests(unittest.TestCase):
    def test_iso_datetime_is_split_into_date_and_time(self):
        date_value, time_value = TimelineService._normalise_date_time(
            "2024-05-01T13:45:20",
            None,
        )

        self.assertEqual(date_value, "2024-05-01")
        self.assertEqual(time_value, "13:45")


if __name__ == "__main__":
    unittest.main()
