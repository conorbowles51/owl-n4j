import unittest
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from fastapi import HTTPException
from routers import timeline
from services.case_service import CaseAccessDenied


class TimelineRouterTests(unittest.IsolatedAsyncioTestCase):
    async def test_get_timeline_uses_neo4j_facade(self):
        page = {"events": [], "count": 0, "total": 0, "next_cursor": None}

        with (
            patch.object(timeline, "get_case_if_allowed") as check_access,
            patch.object(timeline.neo4j_service, "get_timeline_page", return_value=page) as get_page,
        ):
            result = await timeline.get_timeline(
                types=None,
                start_date=None,
                end_date=None,
                case_id="case-1",
                limit=25,
                cursor=None,
                db=object(),
                current_user=object(),
            )

        self.assertEqual(result, page)
        check_access.assert_called_once()
        get_page.assert_called_once_with(
            event_types=None,
            start_date=None,
            end_date=None,
            case_id="case-1",
            limit=25,
            cursor=None,
        )

    async def test_export_case_timeline_sets_download_security_headers(self):
        case_id = uuid4()
        request = timeline.TimelineExportRequest(
            case_id=case_id,
            source="filtered",
            format="pdf",
        )
        exported = SimpleNamespace(
            content=b"%PDF",
            filename="Timeline Résumé.pdf",
            media_type="application/pdf",
        )

        with (
            patch.object(timeline, "get_case_if_allowed", return_value=SimpleNamespace(title="Case")) as check_access,
            patch.object(timeline, "export_timeline", return_value=exported) as export_timeline,
        ):
            response = timeline.export_case_timeline(
                request=request,
                db=object(),
                current_user=SimpleNamespace(name="Investigator", email="i@example.test"),
            )

        check_access.assert_called_once()
        export_timeline.assert_called_once()
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertEqual(response.headers["x-content-type-options"], "nosniff")
        self.assertIn("filename*=UTF-8''Timeline%20R%C3%A9sum%C3%A9.pdf", response.headers["content-disposition"])

    async def test_export_case_timeline_permission_denied_does_not_export(self):
        request = timeline.TimelineExportRequest(
            case_id=uuid4(),
            source="filtered",
            format="pdf",
        )

        with (
            patch.object(timeline, "get_case_if_allowed", side_effect=CaseAccessDenied("denied")),
            patch.object(timeline, "export_timeline") as export_timeline,
        ):
            with self.assertRaises(HTTPException) as caught:
                timeline.export_case_timeline(
                    request=request,
                    db=object(),
                    current_user=object(),
                )

        self.assertEqual(caught.exception.status_code, 403)
        export_timeline.assert_not_called()


if __name__ == "__main__":
    unittest.main()
