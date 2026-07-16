import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import ANY, patch
from uuid import uuid4

from fastapi import HTTPException

from routers import evidence, financial, filesystem
from services.case_service import CaseAccessDenied


class ExportAuthorizationTests(unittest.IsolatedAsyncioTestCase):
    async def test_filesystem_list_denies_non_member_before_directory_access(self):
        case_id = uuid4()
        current_user = SimpleNamespace(id=uuid4(), email="outsider@example.com")

        with (
            patch("routers.filesystem.check_case_access", side_effect=CaseAccessDenied("denied")) as check_access,
            patch("pathlib.Path.resolve") as resolve_path,
            patch("pathlib.Path.exists") as path_exists,
            patch("pathlib.Path.iterdir") as iterdir,
        ):
            with self.assertRaises(HTTPException) as ctx:
                await filesystem.list_directory(
                    case_id=str(case_id),
                    path=None,
                    current_user=current_user,
                    db=object(),
                )

        self.assertEqual(ctx.exception.status_code, 403)
        check_access.assert_called_once_with(
            ANY,
            case_id,
            current_user,
            required_permission=("case", "view"),
        )
        resolve_path.assert_not_called()
        path_exists.assert_not_called()
        iterdir.assert_not_called()

    async def test_filesystem_read_denies_non_member_before_path_access(self):
        case_id = uuid4()
        current_user = SimpleNamespace(id=uuid4(), email="outsider@example.com")

        with (
            patch("routers.filesystem.check_case_access", side_effect=CaseAccessDenied("denied")) as check_access,
            patch("pathlib.Path.resolve") as resolve_path,
            patch("pathlib.Path.exists") as path_exists,
            patch("pathlib.Path.read_text") as read_text,
        ):
            with self.assertRaises(HTTPException) as ctx:
                await filesystem.read_file(
                    case_id=str(case_id),
                    path="notes.txt",
                    current_user=current_user,
                    db=object(),
                )

        self.assertEqual(ctx.exception.status_code, 403)
        check_access.assert_called_once_with(
            ANY,
            case_id,
            current_user,
            required_permission=("case", "view"),
        )
        resolve_path.assert_not_called()
        path_exists.assert_not_called()
        read_text.assert_not_called()

    async def test_evidence_file_denies_non_member_before_file_resolution(self):
        case_id = uuid4()
        record = SimpleNamespace(
            id=uuid4(),
            case_id=case_id,
            original_filename="evidence.pdf",
            stored_path="/tmp/evidence.pdf",
        )
        current_user = SimpleNamespace(id=uuid4(), email="outsider@example.com")

        with (
            patch.object(evidence.EvidenceDBStorage, "get", return_value=record),
            patch("routers.evidence.check_case_access", side_effect=CaseAccessDenied("denied")) as check_access,
            patch("routers.evidence._resolve_stored_path") as resolve_path,
            patch.object(evidence.system_log_service, "log"),
        ):
            with self.assertRaises(HTTPException) as ctx:
                await evidence.get_evidence_file(str(record.id), current_user=current_user, db=object())

        self.assertEqual(ctx.exception.status_code, 403)
        check_access.assert_called_once_with(
            ANY,
            case_id,
            current_user,
            required_permission=("case", "view"),
        )
        resolve_path.assert_not_called()

    async def test_evidence_file_uses_record_case_id_for_authorization(self):
        requested_case_id = uuid4()
        record_case_id = uuid4()
        record = SimpleNamespace(
            id=uuid4(),
            case_id=record_case_id,
            original_filename="evidence.txt",
            stored_path="",
        )
        current_user = SimpleNamespace(id=uuid4(), email="investigator@example.com")

        with TemporaryDirectory() as tmp:
            file_path = Path(tmp) / "evidence.txt"
            file_path.write_text("ok")
            record.stored_path = str(file_path)

            with (
                patch.object(evidence.EvidenceDBStorage, "get", return_value=record),
                patch("routers.evidence.check_case_access", return_value=(object(), None)) as check_access,
                patch.object(evidence.system_log_service, "log"),
            ):
                response = await evidence.get_evidence_file(
                    str(record.id),
                    current_user=current_user,
                    db=SimpleNamespace(case_id=requested_case_id),
                )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(check_access.call_args.args[1], record_case_id)
        self.assertNotEqual(check_access.call_args.args[1], requested_case_id)

    async def test_video_frames_deny_non_member_before_path_or_extraction(self):
        record = SimpleNamespace(
            id=uuid4(),
            case_id=uuid4(),
            original_filename="clip.mp4",
            stored_path="/tmp/clip.mp4",
        )
        current_user = SimpleNamespace(id=uuid4(), email="outsider@example.com")

        with (
            patch.object(evidence.EvidenceDBStorage, "get", return_value=record),
            patch("routers.evidence.check_case_access", side_effect=CaseAccessDenied("denied")),
            patch("routers.evidence._resolve_stored_path") as resolve_path,
            patch("routers.evidence.run_in_threadpool") as run_in_threadpool,
            patch.object(evidence.system_log_service, "log"),
        ):
            with self.assertRaises(HTTPException) as ctx:
                await evidence.get_video_frames(str(record.id), current_user=current_user, db=object())

        self.assertEqual(ctx.exception.status_code, 403)
        resolve_path.assert_not_called()
        run_in_threadpool.assert_not_called()

    async def test_video_frame_image_denies_non_member_before_cache_lookup(self):
        record = SimpleNamespace(
            id=uuid4(),
            case_id=uuid4(),
            original_filename="clip.mp4",
            stored_path="/tmp/clip.mp4",
        )
        current_user = SimpleNamespace(id=uuid4(), email="outsider@example.com")

        with (
            patch.object(evidence.EvidenceDBStorage, "get", return_value=record),
            patch("routers.evidence.check_case_access", side_effect=CaseAccessDenied("denied")),
            patch("pathlib.Path.exists") as path_exists,
            patch.object(evidence.system_log_service, "log"),
        ):
            with self.assertRaises(HTTPException) as ctx:
                await evidence.get_video_frame_image(
                    str(record.id),
                    "frame_0001.jpg",
                    current_user=current_user,
                    db=object(),
                )

        self.assertEqual(ctx.exception.status_code, 403)
        path_exists.assert_not_called()

    async def test_financial_export_denies_non_member_before_neo4j_fetch(self):
        case_id = uuid4()
        current_user = SimpleNamespace(id=uuid4(), email="outsider@example.com")

        with (
            patch("routers.financial.check_case_access", side_effect=CaseAccessDenied("denied")),
            patch.object(financial.neo4j_service, "get_financial_transactions") as get_transactions,
            patch.object(financial.system_log_service, "log"),
        ):
            with self.assertRaises(HTTPException) as ctx:
                await financial.export_financial_pdf(
                    case_id=str(case_id),
                    mode="transactions",
                    case_name="Case",
                    categories=None,
                    start_date=None,
                    end_date=None,
                    entity_key=None,
                    entity_name=None,
                    entity=None,
                    search=None,
                    search_header=None,
                    from_entities=None,
                    to_entities=None,
                    include_entity_notes=True,
                    current_user=current_user,
                    db=object(),
                )

        self.assertEqual(ctx.exception.status_code, 403)
        get_transactions.assert_not_called()

    async def test_financial_export_authorizes_then_filters_selected_scope(self):
        case_id = uuid4()
        current_user = SimpleNamespace(id=uuid4(), email="investigator@example.com")
        order = []

        def check_access(*args, **kwargs):
            order.append("auth")
            return SimpleNamespace(title="DB Case Name"), None

        def get_transactions(*args, **kwargs):
            order.append("neo4j")
            return {
                "transactions": [
                    {
                        "date": "2026-07-01",
                        "name": "Included transfer",
                        "amount": 25,
                        "category": "Travel",
                        "from_entity": {"key": "sender-1", "name": "Sender"},
                        "to_entity": {"key": "beneficiary-1", "name": "Beneficiary"},
                    },
                    {
                        "date": "2026-07-01",
                        "name": "Excluded transfer",
                        "amount": 25,
                        "category": "Other",
                        "from_entity": {"key": "sender-2", "name": "Other Sender"},
                        "to_entity": {"key": "beneficiary-1", "name": "Beneficiary"},
                    },
                ]
            }

        with (
            patch("routers.financial.check_case_access", side_effect=check_access) as check_access_mock,
            patch.object(financial.neo4j_service, "get_financial_transactions", side_effect=get_transactions) as get_transactions_mock,
            patch("routers.financial._collect_entity_notes", return_value=[]),
            patch("routers.financial.render_financial_export", return_value={
                "content": b"pdf",
                "media_type": "application/pdf",
                "extension": "pdf",
            }) as render_export,
            patch.object(financial.system_log_service, "log"),
        ):
            response = await financial.export_financial_pdf(
                case_id=str(case_id),
                mode="transactions",
                case_name="Caller Supplied Name",
                categories="Travel",
                start_date=None,
                end_date=None,
                entity_key=None,
                entity_name=None,
                entity=None,
                search=None,
                search_header=None,
                from_entities="sender-1",
                to_entities=None,
                include_entity_notes=True,
                current_user=current_user,
                db=object(),
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(order, ["auth", "neo4j"])
        check_access_mock.assert_called_once()
        get_transactions_mock.assert_called_once_with(case_id=str(case_id), mode="transactions")
        rendered_transactions = render_export.call_args.args[0]
        self.assertEqual([t["name"] for t in rendered_transactions], ["Included transfer"])
        self.assertEqual(render_export.call_args.args[1], "DB Case Name")

    async def test_evidence_by_filename_requires_case_view_before_lookup(self):
        case_id = uuid4()
        current_user = SimpleNamespace(id=uuid4(), email="outsider@example.com")

        with (
            patch("services.case_service.check_case_access", side_effect=CaseAccessDenied("denied")) as check_access,
            patch.object(evidence.EvidenceDBStorage, "find_by_filename") as find_by_filename,
        ):
            with self.assertRaises(HTTPException) as ctx:
                await evidence.get_evidence_by_filename(
                    "report.pdf",
                    case_id=str(case_id),
                    current_user=current_user,
                    db=object(),
                )

        self.assertEqual(ctx.exception.status_code, 403)
        check_access.assert_called_once_with(
            ANY,
            case_id,
            current_user,
            required_permission=("case", "view"),
        )
        find_by_filename.assert_not_called()

    async def test_evidence_by_filename_scopes_lookup_to_authorized_case(self):
        case_id = uuid4()
        record = SimpleNamespace(
            id=uuid4(),
            case_id=case_id,
            original_filename="report.pdf",
            stored_path="/tmp/report.pdf",
            summary="summary",
        )
        current_user = SimpleNamespace(id=uuid4(), email="investigator@example.com")

        with (
            patch("services.case_service.check_case_access", return_value=(object(), None)),
            patch.object(evidence.EvidenceDBStorage, "find_by_filename", return_value=record) as find_by_filename,
        ):
            response = await evidence.get_evidence_by_filename(
                "report.pdf",
                case_id=str(case_id),
                current_user=current_user,
                db=object(),
            )

        self.assertTrue(response["found"])
        self.assertEqual(find_by_filename.call_args.kwargs["case_id"], case_id)

    async def test_document_summary_requires_case_view_before_lookup(self):
        case_id = uuid4()
        current_user = SimpleNamespace(id=uuid4(), email="outsider@example.com")

        with (
            patch("services.case_service.check_case_access", side_effect=CaseAccessDenied("denied")),
            patch.object(evidence.EvidenceDBStorage, "find_by_filename") as find_by_filename,
        ):
            with self.assertRaises(HTTPException) as ctx:
                await evidence.get_document_summary(
                    "report.pdf",
                    case_id=str(case_id),
                    current_user=current_user,
                    db=object(),
                )

        self.assertEqual(ctx.exception.status_code, 403)
        find_by_filename.assert_not_called()

    async def test_folder_summary_requires_case_view_before_neo4j_lookup(self):
        case_id = uuid4()
        current_user = SimpleNamespace(id=uuid4(), email="outsider@example.com")

        with (
            patch("services.case_service.check_case_access", side_effect=CaseAccessDenied("denied")),
            patch.object(evidence.neo4j_service, "get_folder_summary") as get_folder_summary,
        ):
            with self.assertRaises(HTTPException) as ctx:
                await evidence.get_folder_summary(
                    "00000128",
                    case_id=str(case_id),
                    current_user=current_user,
                    db=object(),
                )

        self.assertEqual(ctx.exception.status_code, 403)
        get_folder_summary.assert_not_called()

    async def test_transcription_translation_requires_case_view_before_neo4j_lookup(self):
        case_id = uuid4()
        current_user = SimpleNamespace(id=uuid4(), email="outsider@example.com")

        with (
            patch("services.case_service.check_case_access", side_effect=CaseAccessDenied("denied")),
            patch.object(evidence.neo4j_service, "get_transcription_translation") as get_transcription_translation,
        ):
            with self.assertRaises(HTTPException) as ctx:
                await evidence.get_transcription_translation(
                    case_id=str(case_id),
                    folder_name="00000128",
                    current_user=current_user,
                    db=object(),
                )

        self.assertEqual(ctx.exception.status_code, 403)
        get_transcription_translation.assert_not_called()


if __name__ == "__main__":
    unittest.main()
