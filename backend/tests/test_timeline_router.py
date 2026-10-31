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


if __name__ == "__main__":
    unittest.main()
