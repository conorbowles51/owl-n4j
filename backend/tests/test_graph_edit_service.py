import json
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

    async def test_geocode_apply_persists_provenance_and_correction(self):
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
        ), patch.object(graph.neo4j_service, "update_geocoded_location") as update:
            result = await graph.geocode_node(
                "loc-1",
                graph.GeocodeNodeRequest(case_id="case-1", address="London"),
                apply=True,
                user={"username": "investigator", "name": "Investigator One"},
            )

        update.assert_called_once_with(
            "loc-1",
            case_id="case-1",
            query="London",
            latitude=51.5,
            longitude=-0.12,
            formatted_address="London, UK",
            confidence="high",
            provider="nominatim",
            location_granularity="city",
            edited_by="investigator",
            edited_by_name="Investigator One",
            source_view="map",
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
