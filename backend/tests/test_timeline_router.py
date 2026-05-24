import unittest
from unittest.mock import patch

from routers import timeline


class TimelineRouterTests(unittest.IsolatedAsyncioTestCase):
    async def test_get_timeline_uses_neo4j_facade(self):
        page = {"events": [], "count": 0, "total": 0, "next_cursor": None}

        with patch.object(timeline.neo4j_service, "get_timeline_page", return_value=page) as get_page:
            result = await timeline.get_timeline(
                types=None,
                start_date=None,
                end_date=None,
                case_id="case-1",
                limit=25,
                cursor=None,
            )

        self.assertEqual(result, page)
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
