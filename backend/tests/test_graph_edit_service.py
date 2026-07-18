import unittest
from unittest.mock import Mock, patch

from routers import graph
from services.neo4j.graph_edit_service import GraphEditService
from services.neo4j.timeline_service import TimelineService


class _FakeResult:
    def single(self):
        return {
            "labels": ["Communication"],
            "properties": {
                "key": "event-1",
                "case_id": "case-1",
                "date": "2024-01-02",
                "manual_fields": ["category", "date"],
            },
        }


class _FakeSession:
    def __init__(self, captured):
        self._captured = captured

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def run(self, query, **params):
        self._captured["query"] = query
        self._captured["params"] = params
        return _FakeResult()


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

    def test_update_node_rejects_document_coordinates_before_write(self):
        service = GraphEditService()
        service._fetch_node = Mock(
            return_value={
                "labels": ["Document"],
                "category": "Document",
                "properties": {"key": "doc-1", "case_id": "case-1", "name": "Source document"},
            }
        )

        with patch("services.neo4j.graph_edit_service.driver.session") as session:
            with self.assertRaisesRegex(ValueError, "disallowed_entity_type"):
                service.update_node(
                    "doc-1",
                    case_id="case-1",
                    properties={
                        "latitude": 0,
                        "longitude": 0,
                        "location_name": "Null Island",
                    },
                )

        session.assert_not_called()

    def test_update_node_rejects_null_island_before_write(self):
        service = GraphEditService()
        service._fetch_node = Mock(
            return_value={
                "labels": ["Location"],
                "category": "Location",
                "properties": {"key": "loc-1", "case_id": "case-1", "name": "Bad pin"},
            }
        )

        with patch("services.neo4j.graph_edit_service.driver.session") as session:
            with self.assertRaisesRegex(ValueError, "null_island"):
                service.update_node(
                    "loc-1",
                    case_id="case-1",
                    properties={
                        "latitude": 0,
                        "longitude": 0,
                        "location_name": "Null Island",
                    },
                )

        session.assert_not_called()

    def test_update_location_rejects_document_before_write(self):
        service = GraphEditService()
        service._fetch_node = Mock(
            return_value={
                "labels": ["Document"],
                "category": "Document",
                "properties": {"key": "doc-1", "case_id": "case-1", "name": "Source document"},
            }
        )

        with patch("services.neo4j.graph_edit_service.driver.session") as session:
            with self.assertRaisesRegex(ValueError, "disallowed_entity_type"):
                service.update_location(
                    "doc-1",
                    case_id="case-1",
                    location_name="Null Island",
                    latitude=0,
                    longitude=0,
                )

        session.assert_not_called()

    def test_update_node_writes_manual_location_provenance(self):
        service = GraphEditService()
        service._fetch_node = Mock(
            return_value={
                "labels": ["Location"],
                "category": "Location",
                "properties": {"key": "loc-1", "case_id": "case-1", "name": "London"},
            }
        )
        captured = {}

        with patch(
            "services.neo4j.graph_edit_service.driver.session",
            return_value=_FakeSession(captured),
        ):
            service.update_node(
                "loc-1",
                case_id="case-1",
                properties={
                    "latitude": "51.5",
                    "longitude": "-0.12",
                    "location_raw": "London",
                    "location_name": "London, UK",
                },
            )

        updates = captured["params"]["updates"]
        self.assertEqual(updates["latitude"], 51.5)
        self.assertEqual(updates["longitude"], -0.12)
        self.assertEqual(updates["geocoding_provider"], "manual")
        self.assertEqual(updates["geocoding_query"], "London")
        self.assertEqual(updates["location_formatted"], "London, UK")
        self.assertEqual(updates["geocoding_precision"], "manual")
        self.assertEqual(updates["geocoding_confidence"], "high")
        self.assertEqual(updates["geocoding_status"], "mapped")


class GraphGeocodeRouteTests(unittest.IsolatedAsyncioTestCase):
    async def test_geocode_preview_does_not_persist(self):
        with patch(
            "services.geo_rescan_service.geocode_with_cache",
            return_value={
                "status": "mapped",
                "latitude": 51.5,
                "longitude": -0.12,
                "geocoder": "nominatim",
                "query": "London",
                "formatted_address": "London, UK",
                "precision": "city",
                "confidence": "high",
                "candidates": [],
            },
        ), patch.object(graph.neo4j_service, "update_entity_location_full") as update:
            result = await graph.geocode_node(
                "loc-1",
                graph.GeocodeNodeRequest(case_id="case-1", address="London"),
                apply=False,
                user={"username": "investigator"},
            )

        update.assert_not_called()
        self.assertEqual(result["latitude"], 51.5)
        self.assertEqual(result["geocoder"], "nominatim")
        self.assertEqual(result["precision"], "city")
        self.assertFalse(result["applied"])

    async def test_geocode_apply_rejects_disallowed_entity_type(self):
        with patch(
            "services.geo_rescan_service.geocode_with_cache",
            return_value={
                "status": "mapped",
                "latitude": 51.5,
                "longitude": -0.12,
                "geocoder": "nominatim",
                "query": "London",
                "formatted_address": "London, UK",
                "precision": "city",
                "confidence": "high",
                "candidates": [],
            },
        ), patch.object(
            graph.neo4j_service,
            "update_entity_location_full",
            return_value={
                "geocoding_status": "rejected",
                "geocoding_rejection_reason": "disallowed_entity_type",
            },
        ):
            result = await graph.geocode_node(
                "doc-1",
                graph.GeocodeNodeRequest(case_id="case-1", address="London"),
                apply=True,
                user={"username": "investigator"},
            )

        self.assertFalse(result["success"])
        self.assertEqual(result["rejection_reason"], "disallowed_entity_type")


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
