import unittest
from unittest.mock import patch

from services.neo4j.timeline_service import TimelineService


class _FakeResult:
    def __init__(self, rows=None, single=None):
        self._rows = rows or []
        self._single = single

    def __iter__(self):
        return iter(self._rows)

    def single(self):
        return self._single


class _FakeSession:
    def __init__(self, captured, rows=None, total=0):
        self._captured = captured
        self._rows = rows or []
        self._total = total

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def run(self, query, **params):
        self._captured.append({"query": query, "params": params})
        if "RETURN count(n) AS total" in query:
            return _FakeResult(single={"total": self._total})
        return _FakeResult(rows=self._rows)


class TimelineServiceTests(unittest.TestCase):
    def test_timeline_query_uses_normalized_date_time_for_filter_cursor_and_sort(self):
        captured = []
        cursor = TimelineService._encode_cursor(
            {"date": "2024-01-02", "time": "09:15", "key": "event-1"}
        )
        row = {
            "key": "event-2",
            "name": "Later event",
            "type": "Event",
            "date": "2024-01-02",
            "time": "10:00",
            "amount": None,
            "summary": None,
            "notes": None,
            "connections": [],
        }

        with patch(
            "services.neo4j.timeline_service.driver.session",
            return_value=_FakeSession(captured, rows=[row], total=1),
        ):
            TimelineService().get_timeline_page(
                start_date="2024-01-01",
                end_date="2024-01-31",
                case_id="case-1",
                cursor=cursor,
            )

        page_query = captured[0]["query"]
        page_params = captured[0]["params"]
        count_query = captured[1]["query"]

        self.assertIn("AS sort_date", page_query)
        self.assertIn("AS sort_time", page_query)
        self.assertIn("n.timestamp IS NOT NULL", page_query)
        self.assertIn("'time' IN coalesce(n.manual_fields, [])", page_query)
        self.assertIn("sort_date >= $start_date", page_query)
        self.assertIn("sort_date <= $end_date", page_query)
        self.assertIn("sort_date > $cursor_date", page_query)
        self.assertIn("coalesce(sort_time, '99:99') > $cursor_time", page_query)
        self.assertIn(
            "ORDER BY sort_date ASC, coalesce(sort_time, '99:99') ASC, n.key ASC",
            page_query,
        )
        self.assertNotIn("ORDER BY n.date ASC", page_query)
        self.assertNotIn("n.date >= $start_date", page_query)
        self.assertIn("sort_date >= $start_date", count_query)
        self.assertEqual(page_params["cursor_date"], "2024-01-02")
        self.assertEqual(page_params["cursor_time"], "09:15")
        self.assertEqual(page_params["cursor_key"], "event-1")

    def test_iso_datetime_records_are_returned_with_separate_date_and_time(self):
        captured = []
        row = {
            "key": "event-1",
            "name": "Timestamped event",
            "type": "Event",
            "date": "2024-02-03T19:47:00",
            "time": None,
            "amount": None,
            "summary": None,
            "notes": None,
            "connections": [],
        }

        with patch(
            "services.neo4j.timeline_service.driver.session",
            return_value=_FakeSession(captured, rows=[row], total=1),
        ):
            page = TimelineService().get_timeline_page(case_id="case-1")

        self.assertEqual(page["events"][0]["date"], "2024-02-03")
        self.assertEqual(page["events"][0]["time"], "19:47")

    def test_space_datetime_records_are_returned_with_separate_date_and_time(self):
        captured = []
        row = {
            "key": "event-1",
            "name": "Timestamped event",
            "type": "Media",
            "date": "2025-04-12 06:21:47-06:23:45",
            "time": None,
            "amount": None,
            "summary": None,
            "notes": None,
            "connections": [],
        }

        with patch(
            "services.neo4j.timeline_service.driver.session",
            return_value=_FakeSession(captured, rows=[row], total=1),
        ):
            page = TimelineService().get_timeline_page(case_id="case-1")

        self.assertEqual(page["events"][0]["date"], "2025-04-12")
        self.assertEqual(page["events"][0]["time"], "06:21")

    def test_fetch_timeline_events_by_keys_is_case_scoped_and_includes_export_fields(self):
        captured = []
        row = {
            "key": "event-1",
            "name": "Timestamped event",
            "type": "Event",
            "date": "2024-02-03",
            "time": "19:47",
            "amount": None,
            "summary": None,
            "notes": None,
            "connections": [],
            "location": "Port Newark",
            "location_raw": None,
            "location_formatted": None,
            "location_name": None,
            "latitude": None,
            "longitude": None,
            "source_files": ["report.pdf"],
            "source_quotes": [],
            "source_references": [],
            "source_pages": [],
        }

        with patch(
            "services.neo4j.timeline_service.driver.session",
            return_value=_FakeSession(captured, rows=[row], total=1),
        ):
            events = TimelineService().get_timeline_events_by_keys(
                case_id="case-1",
                event_keys=["event-1", "event-1"],
                include_export_fields=True,
            )

        query = captured[0]["query"]
        params = captured[0]["params"]
        self.assertIn("n.case_id = $case_id", query)
        self.assertIn("n.key IN $event_keys", query)
        self.assertIn("n.source_files AS source_files", query)
        self.assertIn("ORDER BY sort_date ASC, coalesce(sort_time, '99:99') ASC, n.key ASC", query)
        self.assertEqual(params["event_keys"], ["event-1"])
        self.assertEqual(events[0]["source_files"], ["report.pdf"])
        self.assertEqual(events[0]["location"], "Port Newark")

    @staticmethod
    def _row(key, date="2024-01-02"):
        return {
            "key": key, "name": key, "type": "Event", "date": date, "time": None,
            "amount": None, "summary": None, "notes": None, "connections": [],
        }

    def test_page_is_cut_before_connections_are_gathered(self):
        captured = []
        with patch(
            "services.neo4j.timeline_service.driver.session",
            return_value=_FakeSession(captured, rows=[], total=0),
        ):
            TimelineService().get_timeline_page(case_id="case-1", limit=2)

        page_query = captured[0]["query"]
        self.assertLess(page_query.index("LIMIT $limit"), page_query.index("OPTIONAL MATCH (n)-[r]-(connected)"))
        # rows leave the aggregation unordered, so the page is sorted again after it
        self.assertTrue(page_query.rstrip().endswith("ORDER BY sort_date ASC, coalesce(sort_time, '99:99') ASC, n.key ASC"))
        self.assertLess(page_query.index("n.case_id = $case_id"), page_query.index("AS sort_date"))
        self.assertNotIn("properties(", page_query)

    def test_total_is_counted_once_and_carried_by_the_cursor(self):
        first, later = [], []
        rows = [self._row("a"), self._row("b"), self._row("c")]
        with patch(
            "services.neo4j.timeline_service.driver.session",
            return_value=_FakeSession(first, rows=rows, total=5),
        ):
            page1 = TimelineService().get_timeline_page(case_id="case-1", limit=2, event_types=["Event"])
        with patch(
            "services.neo4j.timeline_service.driver.session",
            return_value=_FakeSession(later, rows=[self._row("c")], total=999),
        ):
            page2 = TimelineService().get_timeline_page(
                case_id="case-1", limit=2, event_types=["Event"], cursor=page1["next_cursor"],
            )

        self.assertEqual(sum("RETURN count(n) AS total" in c["query"] for c in first), 1)
        self.assertEqual(page1["total"], 5)
        self.assertEqual([c for c in later if "RETURN count(n) AS total" in c["query"]], [])
        self.assertEqual(page2["total"], 5)
        self.assertEqual(later[0]["params"]["cursor_key"], "b")

    def test_cursor_total_is_not_reused_for_other_filters_or_old_cursors(self):
        carried = TimelineService._encode_cursor(self._row("b"), total=5, filters=TimelineService._filter_tag({"case_id": "case-1"}))
        old_style = TimelineService._encode_cursor(self._row("b"))
        for cursor, kwargs in ((carried, {"case_id": "case-2"}), (carried, {"case_id": "case-1", "event_types": ["Event"]}), (old_style, {"case_id": "case-1"})):
            captured = []
            with patch(
                "services.neo4j.timeline_service.driver.session",
                return_value=_FakeSession(captured, rows=[], total=7),
            ):
                page = TimelineService().get_timeline_page(cursor=cursor, **kwargs)
            self.assertEqual(page["total"], 7)
            self.assertEqual(sum("RETURN count(n) AS total" in c["query"] for c in captured), 1)

    def test_full_fetch_returns_every_page(self):
        pages = iter([
            {"events": [{"key": "a"}], "count": 1, "total": 2, "next_cursor": "c1"},
            {"events": [{"key": "b"}], "count": 1, "total": 2, "next_cursor": None},
        ])
        with patch.object(TimelineService, "get_timeline_page", side_effect=lambda **kw: next(pages)) as paged:
            events = TimelineService().get_timeline_events(case_id="case-1")
        self.assertEqual([e["key"] for e in events], ["a", "b"])
        self.assertEqual(paged.call_args_list[1].kwargs["cursor"], "c1")

if __name__ == "__main__":
    unittest.main()
