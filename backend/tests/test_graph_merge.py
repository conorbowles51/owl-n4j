import unittest
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from fastapi import HTTPException

from routers import graph
from services.case_service import CaseAccessDenied


class _ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar(self):
        return self.value


class _ScalarOneOrNoneResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class _FakeDb:
    def __init__(self, lock_results=None, job=None):
        self.lock_results = list(lock_results or [])
        self.job = job
        self.lock_ids = []

    def execute(self, statement, params=None):
        if params and "lock_id" in params:
            self.lock_ids.append(params["lock_id"])
            return _ScalarResult(self.lock_results.pop(0))
        return _ScalarOneOrNoneResult(self.job)


class GraphMergeTests(unittest.IsolatedAsyncioTestCase):
    def test_merge_advisory_lock_id_is_stable_and_distinct(self):
        first = graph._merge_advisory_lock_id("case-1", "entity-a")
        second = graph._merge_advisory_lock_id("case-1", "entity-a")
        other = graph._merge_advisory_lock_id("case-1", "entity-b")

        self.assertEqual(first, second)
        self.assertNotEqual(first, other)
        self.assertGreaterEqual(first, -(2**63))
        self.assertLess(first, 2**63)

    def test_acquire_merge_locks_uses_sorted_keys(self):
        db = _FakeDb(lock_results=[True, True])

        graph._acquire_merge_entity_locks(db, "case-1", ["entity-b", "entity-a"])

        self.assertEqual(
            db.lock_ids,
            [
                graph._merge_advisory_lock_id("case-1", "entity-a"),
                graph._merge_advisory_lock_id("case-1", "entity-b"),
            ],
        )

    def test_acquire_merge_locks_returns_conflict_on_lock_failure(self):
        db = _FakeDb(lock_results=[False])

        with self.assertRaises(HTTPException) as ctx:
            graph._acquire_merge_entity_locks(db, "case-1", ["entity-a"])

        self.assertEqual(ctx.exception.status_code, 409)

    def test_relationship_merge_payload_strips_identity_and_keeps_provenance(self):
        payload = graph._relationship_merge_payload(
            {
                "relationship": "OWNS",
                "direction": "outgoing",
                "key": "target-1",
                "rel_properties": {
                    "source_id": "old-source",
                    "target_id": "old-target",
                    "case_id": "case-1",
                    "source_files": ["file-a.pdf"],
                    "source_quotes": ["quote a"],
                    "confidence": 0.8,
                    "detail": "beneficial owner",
                    "nested": {"ignored": True},
                },
            }
        )

        self.assertEqual(payload["target_key"], "target-1")
        self.assertEqual(payload["source_files"], ["file-a.pdf"])
        self.assertEqual(payload["source_quotes"], ["quote a"])
        self.assertEqual(
            payload["properties"],
            {"confidence": 0.8, "detail": "beneficial owner"},
        )

    async def test_get_merge_job_checks_case_access_before_returning_status(self):
        case_id = uuid4()
        job = SimpleNamespace(
            id=uuid4(),
            case_id=case_id,
            status="completed",
            merged_entity_key="merged-1",
            recycled_source_keys=["source-1"],
            source_entity_keys=["source-1", "source-2"],
            error_message=None,
        )
        db = _FakeDb(job=job)
        current_user = SimpleNamespace(id=uuid4())

        with patch("routers.graph.check_case_access") as check_case_access:
            result = await graph.get_merge_job(
                str(job.id),
                current_user=current_user,
                db=db,
            )

        check_case_access.assert_called_once_with(
            db,
            case_id,
            current_user,
            required_permission=("case", "view"),
        )
        self.assertEqual(result["id"], str(job.id))
        self.assertEqual(result["status"], "completed")

    async def test_get_merge_job_returns_403_without_case_access(self):
        job = SimpleNamespace(
            id=uuid4(),
            case_id=uuid4(),
            status="processing",
            merged_entity_key=None,
            recycled_source_keys=None,
            source_entity_keys=["source-1"],
            error_message=None,
        )
        db = _FakeDb(job=job)

        with patch("routers.graph.check_case_access") as check_case_access:
            check_case_access.side_effect = CaseAccessDenied("denied")
            with self.assertRaises(HTTPException) as ctx:
                await graph.get_merge_job(
                    str(job.id),
                    current_user=SimpleNamespace(id=uuid4()),
                    db=db,
                )

        self.assertEqual(ctx.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()
