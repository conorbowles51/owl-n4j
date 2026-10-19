import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4
from fastapi import HTTPException
from routers import financial_adjudication as write, financial_ledger as read
from services.financial.candidate_materialization import CandidateFinalizationRequest
from services.financial.candidate_store import CandidateStoreError

class FinalizationRouterTests(unittest.IsolatedAsyncioTestCase):
    async def test_preview_is_case_scoped_and_always_releases_locks(self):
        case, file = uuid4(),uuid4()
        db=Mock()
        with patch.object(read,"preview_candidate_finalization",return_value={"applied":False}) as call:
            self.assertFalse((await read.get_candidate_finalization_preview(file,case,db))["applied"])
        call.assert_called_once_with(db,case_id=case,evidence_file_id=file,resolve_path=read._resolve_stored_path)
        db.rollback.assert_called_once()
        self.assertEqual(read._ledger_case_permission(None,{}),("case","view"))

    async def test_preview_stale_errors_preserve_status_and_release_locks(self):
        db=Mock()
        with patch.object(read,"preview_candidate_finalization",side_effect=CandidateStoreError("Reload",409)):
            with self.assertRaises(HTTPException) as error:
                await read.get_candidate_finalization_preview(uuid4(),uuid4(),db)
        self.assertEqual(error.exception.status_code,409)
        db.rollback.assert_called_once()

    async def test_writer_receives_authenticated_actor_and_trusted_resolver(self):
        case,file=uuid4(),uuid4()
        user=SimpleNamespace(id=uuid4(),name="Synthetic",email="synthetic@example.test")
        db=Mock()
        body=CandidateFinalizationRequest(expected_revision="a"*64, documentary_financial_rows=True,
            accept_incomplete_coverage=True,reason="Reviewed source")
        with patch.object(write,"finalize_candidates",return_value={"applied":True}) as call:
            self.assertTrue((await write.record_candidate_finalization(file,body,case,user,db))["applied"])
        args=call.call_args.kwargs
        self.assertEqual(args["case_id"],case);self.assertEqual(args["evidence_file_id"],file)
        self.assertEqual(args["actor"].user_id,user.id)
        self.assertIs(args["resolve_path"],write._resolve_stored_path)

    async def test_unexpected_failure_does_not_leak_storage_details(self):
        db=Mock()
        with patch.object(read,"preview_candidate_finalization",side_effect=RuntimeError("private path")):
            with self.assertRaises(HTTPException) as error:
                await read.get_candidate_finalization_preview(uuid4(),uuid4(),db)
        self.assertEqual(error.exception.status_code,500)
        self.assertNotIn("private",error.exception.detail)
