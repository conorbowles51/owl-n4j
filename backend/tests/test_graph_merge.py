import unittest
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from fastapi import HTTPException

from routers import graph
from services.case_service import CaseAccessDenied
from services.job_status_subscriber import JobStatusSubscriber, _merged_entity_key


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
        self.commits = 0

    def execute(self, statement, params=None):
        if params and "lock_id" in params:
            self.lock_ids.append(params["lock_id"])
            return _ScalarResult(self.lock_results.pop(0))
        return _ScalarOneOrNoneResult(self.job)

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass


class GraphMergeTests(unittest.IsolatedAsyncioTestCase):
    def test_merge_completion_key_is_recovered_from_persisted_pipeline_state(self):
        self.assertEqual(
            _merged_entity_key(
                {
                    "pipeline_state": {
                        "merge_result": {"merged_entity_key": "merged-1"}
                    }
                }
            ),
            "merged-1",
        )

    def test_merge_completion_without_a_result_key_keeps_sources_active(self):
        merge_job = SimpleNamespace(
            engine_job_id="engine-1",
            case_id=uuid4(),
            source_entity_keys=["source-1", "source-2"],
            created_by="tester",
            merged_entity_key=None,
            recycled_source_keys=None,
            status="processing",
            error_message=None,
        )
        db = _FakeDb()

        with patch(
            "services.neo4j.neo4j_service.soft_delete_entity"
        ) as soft_delete:
            JobStatusSubscriber()._handle_merge_completion(
                db,
                merge_job,
                {"pipeline_state": {}},
                "completed",
                str(merge_job.case_id),
            )

        soft_delete.assert_not_called()
        self.assertEqual(merge_job.status, "failed")
        self.assertIn("result key", merge_job.error_message)

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

    def test_a_merged_away_entity_is_refused_as_already_merged_not_missing(self):
        # GR-02: the second merge named an entity the first merge had moved to the recycle bin and got a bare 404.
        db = _FakeDb(job=SimpleNamespace(merged_entity_key="merged-1"))
        error = graph._missing_merge_entity_error(db, "case-1", "entity-a")
        self.assertEqual(error.status_code, 409)
        self.assertIn("already merged", error.detail)
        self.assertIn("Scan again", error.detail)

    def test_an_entity_never_merged_is_still_not_found(self):
        error = graph._missing_merge_entity_error(_FakeDb(job=None), "case-1", "entity-a")
        self.assertEqual(error.status_code, 404)
        self.assertEqual(error.detail, "Entity not found: entity-a")

    def test_the_merged_away_lookup_is_scoped_to_the_case(self):
        captured = []

        class _Db(_FakeDb):
            def execute(self, statement, params=None):
                captured.append(str(statement.compile(compile_kwargs={})))
                return _ScalarOneOrNoneResult(None)

        graph._missing_merge_entity_error(_Db(), "case-1", "entity-a")
        self.assertIn("merge_jobs.case_id", captured[0])
        self.assertIn("recycled_source_keys", captured[0])

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
                    "source_claim_ids": ["claim-a"],
                    "source_locations": '[{"file_name":"file-a.pdf","page_start":7}]',
                    "confidence": 0.8,
                    "detail": "beneficial owner",
                    "nested": {"ignored": True},
                },
            }
        )

        self.assertEqual(payload["target_key"], "target-1")
        self.assertEqual(payload["source_files"], ["file-a.pdf"])
        self.assertEqual(payload["source_quotes"], ["quote a"])
        self.assertEqual(payload["source_claim_ids"], ["claim-a"])
        self.assertEqual(
            payload["source_locations"],
            [{"file_name": "file-a.pdf", "page_start": 7}],
        )
        self.assertEqual(
            payload["properties"],
            {"confidence": 0.8, "detail": "beneficial owner"},
        )

    def test_entity_merge_payload_promotes_all_node_provenance(self):
        payload = graph._entity_merge_payload(
            {
                "key": "person-1",
                "name": "Victoria Blackwood",
                "type": "Person",
                "summary": "Summary",
                "verified_facts": [
                    {
                        "text": "Named as director.",
                        "verification_status": "verified",
                        "verification_reason": "Directly stated",
                        "source_location": {"page_start": 2},
                    }
                ],
                "ai_insights": [],
                "properties": {
                    "source_files": ["registry.pdf"],
                    "source_quotes": ["Victoria Blackwood — Director"],
                    "source_claim_ids": ["claim-1"],
                    "source_locations": '[{"file_name":"registry.pdf","page_start":2}]',
                    "occupation": "Director",
                },
                "connections": [],
            }
        )

        self.assertEqual(payload["source_claim_ids"], ["claim-1"])
        self.assertEqual(
            payload["source_locations"],
            [{"file_name": "registry.pdf", "page_start": 2}],
        )
        self.assertEqual(payload["properties"], {"occupation": "Director"})
        self.assertEqual(
            payload["verified_facts"][0]["verification_status"], "verified"
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
            result = graph.get_merge_job(
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
                graph.get_merge_job(
                    str(job.id),
                    current_user=SimpleNamespace(id=uuid4()),
                    db=db,
                )

        self.assertEqual(ctx.exception.status_code, 403)

    async def test_get_merge_job_says_when_the_merged_record_is_not_searchable_yet(self):
        # A merge kept while the embedding service refused: the merged record waits for the gap backfill.
        job = SimpleNamespace(
            id=uuid4(), case_id=uuid4(), status="completed", merged_entity_key="merged-1",
            recycled_source_keys=["source-1", "source-2"], source_entity_keys=["source-1", "source-2"],
            error_message=None,
        )
        with patch("routers.graph.check_case_access"), \
                patch("routers.graph.entity_vectors.is_pending", return_value=True) as is_pending:
            result = graph.get_merge_job(str(job.id), current_user=SimpleNamespace(id=uuid4()), db=_FakeDb(job=job))
        is_pending.assert_called_once_with(str(job.case_id), "merged-1")
        self.assertIs(result["search_pending"], True)
        self.assertEqual(result["status"], "completed")

        with patch("routers.graph.check_case_access"), \
                patch("routers.graph.entity_vectors.is_pending", return_value=False):
            result = graph.get_merge_job(str(job.id), current_user=SimpleNamespace(id=uuid4()), db=_FakeDb(job=job))
        self.assertIs(result["search_pending"], False)

    async def test_get_merge_job_search_mark_unknown_when_the_graph_cannot_be_read(self):
        job = SimpleNamespace(
            id=uuid4(), case_id=uuid4(), status="completed", merged_entity_key="merged-1",
            recycled_source_keys=[], source_entity_keys=["a", "b"], error_message=None,
        )
        with patch("routers.graph.check_case_access"), \
                patch("routers.graph.entity_vectors.is_pending", side_effect=RuntimeError("graph down")):
            result = graph.get_merge_job(str(job.id), current_user=SimpleNamespace(id=uuid4()), db=_FakeDb(job=job))
        self.assertIsNone(result["search_pending"])
        self.assertEqual(result["status"], "completed")

    def test_is_pending_reads_the_engine_mark_on_the_merged_record(self):
        from services import entity_vectors
        calls = []

        class _Row(dict):
            pass

        class _Session:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def run(self, query, **params):
                calls.append((query, params))
                return SimpleNamespace(single=lambda: _Row(c=1))

        self.assertTrue(entity_vectors.is_pending("case-1", "merged-1", session_factory=_Session))
        self.assertIn("vector_pending = true", calls[0][0])
        self.assertEqual(calls[0][1], {"key": "merged-1", "case_id": "case-1"})


if __name__ == "__main__":
    unittest.main()
