import contextlib
import json
import unittest
from unittest.mock import patch

from routers import timeline
from services.neo4j import graph_response_cache


class TimelineRouterTests(unittest.IsolatedAsyncioTestCase):
    async def test_get_timeline_uses_neo4j_facade(self):
        page = {"events": [], "count": 0, "total": 0, "next_cursor": None}

        graph_response_cache.graph_responses.clear()
        with (
            patch.object(graph_response_cache.driver, "session", return_value=contextlib.nullcontext(object())),
            patch("services.neo4j.graph_read_cache.graph_bookmark", return_value=("bookmark-1",)),
            patch.object(timeline, "get_case_if_allowed") as check_access,
            patch.object(timeline.neo4j_service, "get_timeline_page", return_value=page) as get_page,
        ):
            result = timeline.get_timeline(
                types=None,
                start_date=None,
                end_date=None,
                case_id="case-1",
                limit=25,
                cursor=None,
                scope="all",
                db=object(),
                current_user=object(),
            )

        self.assertEqual(json.loads(result.body), page)
        check_access.assert_called_once()
        get_page.assert_called_once_with(
            event_types=None,
            start_date=None,
            end_date=None,
            case_id="case-1",
            limit=25,
            cursor=None,
        )

    async def test_whole_timeline_uses_the_whole_read_and_too_large_is_413(self):
        from fastapi import HTTPException
        from services.neo4j.timeline_service import TimelineTooLarge
        whole = {"events": [], "count": 0, "total": 0, "next_cursor": None}
        graph_response_cache.graph_responses.clear()
        common = dict(types=None, start_date=None, end_date=None, case_id="case-1", limit=25, cursor="ignored",
                      scope="all", db=object(), current_user=object())
        with (
            patch.object(graph_response_cache.driver, "session", side_effect=lambda: contextlib.nullcontext(object())),
            patch("services.neo4j.graph_read_cache.graph_bookmark", return_value=("bookmark-1",)),
            patch.object(timeline, "get_case_if_allowed"),
            patch.object(timeline.neo4j_service, "get_timeline_page", side_effect=AssertionError("paged")),
            patch.object(timeline.neo4j_service, "get_timeline_whole", return_value=whole) as get_whole,
        ):
            result = timeline.get_timeline(whole=True, **common)
            self.assertEqual(json.loads(result.body), whole)
            get_whole.assert_called_once_with(event_types=None, start_date=None, end_date=None, case_id="case-1")
            get_whole.side_effect = TimelineTooLarge("too many")
            graph_response_cache.graph_responses.clear()
            with self.assertRaises(HTTPException) as refused:
                timeline.get_timeline(whole=True, **common)
            self.assertEqual(refused.exception.status_code, 413)

if __name__ == "__main__":
    unittest.main()
