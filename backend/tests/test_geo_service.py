import unittest
from unittest.mock import patch

from services.neo4j.geo_service import GeoService


class _FakeSession:
    def __init__(self, captured, records):
        self._captured = captured
        self._records = records

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def run(self, query, **params):
        self._captured["query"] = query
        self._captured["params"] = params
        return self._records


class GeoServiceReviewQueueTests(unittest.TestCase):
    def test_needs_review_query_includes_flagged_statuses_and_excludes_manual_locations(self):
        captured = {}
        records = [
            {
                "key": "loc-1",
                "name": "Unknown warehouse",
                "type": "Location",
                "location_raw": "warehouse",
                "geocoding_status": "ambiguous",
                "geocoding_confidence": None,
                "location_specificity": "unknown",
                "manual_fields": None,
            }
        ]

        with patch(
            "services.neo4j.geo_service.driver.session",
            return_value=_FakeSession(captured, records),
        ):
            result = GeoService().get_locations_needing_review("case-1")

        self.assertEqual(captured["params"], {"case_id": "case-1"})
        self.assertIn("['ambiguous', 'unverified', 'failed']", captured["query"])
        self.assertIn("coalesce(n.manual_fields, [])", captured["query"])
        self.assertIn("'latitude'", captured["query"])
        self.assertIn("'longitude'", captured["query"])
        self.assertEqual(
            result,
            [
                {
                    "key": "loc-1",
                    "name": "Unknown warehouse",
                    "type": "Location",
                    "location_raw": "warehouse",
                    "geocoding_status": "ambiguous",
                    "geocoding_confidence": None,
                    "location_specificity": "unknown",
                    "manual_fields": [],
                }
            ],
        )


if __name__ == "__main__":
    unittest.main()
