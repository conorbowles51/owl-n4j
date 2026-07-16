import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

from fastapi import HTTPException
from starlette.requests import Request

from postgres.models.user import User
from routers import financial, filesystem, snapshots
from services.agent import storage as agent_storage
from services.case_service import CaseAccessDenied
from services.export_security import audit_export_event, deterministic_hash


def _request(headers: list[tuple[bytes, bytes]] | None = None) -> Request:
    return Request({"type": "http", "method": "GET", "path": "/", "headers": headers or []})


def _user(email: str = "investigator@example.com") -> User:
    return User(id=uuid4(), email=email, name="Investigator", password_hash="hash")


class ExportSecurityTests(unittest.IsolatedAsyncioTestCase):
    def test_audit_export_event_records_metadata_without_payload(self):
        db = MagicMock()
        user = _user()

        with patch("services.export_security.system_log_service.log") as log:
            audit_export_event(
                db=db,
                user=user,
                action="financial_pdf_export",
                case_id=uuid4(),
                export_type="financial.pdf",
                result="success",
                correlation_id="corr-1",
                scope={"search": "needle"},
                row_count=1,
                content_hash=deterministic_hash([{"id": "txn-1"}]),
                content_type="application/pdf",
            )

        kwargs = log.call_args.kwargs
        self.assertEqual(kwargs["user"], user.email)
        self.assertTrue(kwargs["success"])
        details = kwargs["details"]
        self.assertEqual(details["correlation_id"], "corr-1")
        self.assertEqual(details["row_count"], 1)
        self.assertNotIn("secret evidence body", str(details))
        self.assertNotIn("content", details)

    async def test_financial_export_denial_does_not_fetch_transactions(self):
        db = MagicMock()
        user = _user()
        case_id = str(uuid4())

        with patch.object(financial, "check_case_access", side_effect=CaseAccessDenied("denied")), patch.object(
            financial.neo4j_service,
            "get_financial_transactions",
        ) as get_transactions, patch.object(financial, "audit_export_event") as audit:
            with self.assertRaises(HTTPException) as raised:
                await financial.export_financial_pdf(
                    _request([(b"x-correlation-id", b"corr-deny")]),
                    case_id=case_id,
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
                    include_entity_notes=False,
                    current_user=user,
                    db=db,
                )

        self.assertEqual(raised.exception.status_code, 403)
        get_transactions.assert_not_called()
        audit.assert_called_once()
        self.assertEqual(audit.call_args.kwargs["result"], "denied")

    async def test_financial_export_audits_filtered_row_count_and_hash(self):
        db = MagicMock()
        user = _user()
        case_id = str(uuid4())
        rows = [
            {"key": "txn-1", "category": "Rent", "date": "2024-01-05", "name": "Office"},
            {"key": "txn-2", "category": "Travel", "date": "2024-01-06", "name": "Flight"},
        ]

        with patch.object(financial, "check_case_access", return_value=(object(), None)), patch.object(
            financial.neo4j_service,
            "get_financial_transactions",
            return_value={"transactions": rows},
        ) as get_transactions, patch.object(
            financial,
            "render_financial_export",
            return_value={"content": b"%PDF", "media_type": "application/pdf", "extension": "pdf"},
        ), patch.object(financial, "audit_export_event") as audit:
            response = await financial.export_financial_pdf(
                _request([(b"x-correlation-id", b"corr-ok")]),
                case_id=case_id,
                mode="transactions",
                case_name="Case",
                categories="Rent",
                start_date=None,
                end_date=None,
                entity_key=None,
                entity_name=None,
                entity=None,
                search=None,
                search_header=None,
                from_entities=None,
                to_entities=None,
                include_entity_notes=False,
                current_user=user,
                db=db,
            )

        get_transactions.assert_called_once_with(case_id=case_id, mode="transactions")
        self.assertEqual(response.headers["X-Correlation-ID"], "corr-ok")
        audit_kwargs = audit.call_args.kwargs
        self.assertEqual(audit_kwargs["result"], "success")
        self.assertEqual(audit_kwargs["row_count"], 1)
        self.assertEqual(audit_kwargs["content_hash"], deterministic_hash([rows[0]]))

    async def test_filesystem_denial_does_not_create_case_directory(self):
        db = MagicMock()
        user = _user()
        case_id = str(uuid4())

        with tempfile.TemporaryDirectory() as tmpdir, patch.object(filesystem, "FILESYSTEM_ROOT", Path(tmpdir)), patch.object(
            filesystem,
            "check_case_access",
            side_effect=CaseAccessDenied("denied"),
        ):
            with self.assertRaises(HTTPException) as raised:
                await filesystem.list_directory(case_id=case_id, current_user=user, db=db)

            self.assertEqual(raised.exception.status_code, 403)
            self.assertFalse((Path(tmpdir) / case_id).exists())

    def test_agent_artifact_export_authorizes_by_case_not_owner(self):
        db = MagicMock()
        user = _user()
        artifact_id = uuid4()
        case_id = uuid4()
        artifact = SimpleNamespace(
            id=artifact_id,
            run=SimpleNamespace(case_id=case_id),
            thread=SimpleNamespace(case_id=case_id),
        )
        db.query.return_value.filter.return_value.first.return_value = artifact

        with patch.object(agent_storage, "check_case_access") as check_access:
            resolved = agent_storage.get_artifact_for_export(db, artifact_id=artifact_id, user=user)

        self.assertIs(resolved, artifact)
        check_access.assert_called_once_with(db, case_id, user, required_permission=("case", "view"))

    async def test_snapshot_chunk_cache_isolated_by_owner_and_case(self):
        snapshots._chunk_upload_cache.clear()
        user_a = _user("a@example.com")
        user_b = _user("b@example.com")
        case_a = str(uuid4())
        case_b = str(uuid4())
        db = MagicMock()
        storage = MagicMock()
        storage.get.return_value = None

        with patch.object(snapshots, "check_case_access", return_value=(object(), None)), patch.object(
            snapshots,
            "snapshot_storage",
            storage,
        ):
            await snapshots.upload_snapshot_chunk(
                snapshots.SnapshotChunkCreate(
                    snapshot_id="shared",
                    case_id=case_a,
                    chunk_index=0,
                    chunk_data={"name": "A", "notes": "", "case_id": case_a, "subgraph": {"nodes": [{"id": "a"}]}},
                    is_last_chunk=False,
                ),
                current_user=user_a,
                db=db,
            )

            with self.assertRaises(HTTPException) as raised:
                await snapshots.upload_snapshot_chunk(
                    snapshots.SnapshotChunkCreate(
                        snapshot_id="shared",
                        case_id=case_b,
                        chunk_index=1,
                        chunk_data={"subgraph": {"nodes": [{"id": "b"}]}},
                        is_last_chunk=True,
                    ),
                    current_user=user_b,
                    db=db,
                )

        self.assertEqual(raised.exception.status_code, 409)
        storage.save.assert_not_called()
        self.assertIn((user_a.email, case_a, "shared"), snapshots._chunk_upload_cache)
        self.assertNotIn((user_b.email, case_b, "shared"), snapshots._chunk_upload_cache)


if __name__ == "__main__":
    unittest.main()
