"""Ledger to graph follow-up: invoked after admission, idempotent, isolated, bounded.

No Neo4j is used.  ``tests.financial_fake_graph`` stands in for the session and
keeps transaction semantics, so rollback and partial failure are observable.
"""
import asyncio
import io
import json
import os
import threading
import time
from pathlib import Path
from unittest import TestCase
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from sqlalchemy import select

from postgres.base import Base
from postgres.models.evidence import IngestionLog
from postgres.models.financial import FinancialTransaction
from postgres.models.financial_import_batches import FinancialImportBatch as Batch, FinancialImportBatchItem as Item
from services.financial import graph_followup, import_batches
from services.financial.projection import LABEL_ACCOUNT, LABEL_DOCUMENT, LABEL_TRANSACTION, REL_TRANSFERRED_TO
from tests.financial_fake_graph import FakeGraph
from tests import test_financial_statement_import as statement_fixture


class _Clock:
    def __init__(self):
        self.now = time.monotonic() + 10_000

    def __call__(self):
        return self.now


class GraphFollowUpTestCase(TestCase):
    def setUp(self):
        graph_followup._reset_for_tests()
        self.env = patch.dict(os.environ, {graph_followup.ENABLED_ENV: "1"})
        self.env.start()
        self.f = statement_fixture.StatementImportTests('test_existing_import_and_same_request_keep_the_saved_account_for_navigation')
        self.f.setUp()
        self.f.file.status = "processed"
        Base.metadata.create_all(self.f.db.connection(), tables=[Batch.__table__, Item.__table__, IngestionLog.__table__])
        self.f.db.commit()
        self.graph = FakeGraph()
        self.clock = _Clock()
        self.case = str(self.f.case.id)

    def tearDown(self):
        self.env.stop()
        self.f.tearDown()
        graph_followup._reset_for_tests()

    def run_due(self, **kwargs):
        return graph_followup.run_due(self.f.SessionLocal, self.graph.session, clock=self.clock, **kwargs)

    def project(self, **kwargs):
        return graph_followup.project_case_graph(self.f.case.id, session_factory=self.f.SessionLocal,
                                                 graph_session_factory=self.graph.session, **kwargs)

    def ledger_count(self):
        with self.f.SessionLocal() as db:
            return len(list(db.scalars(select(FinancialTransaction).where(
                FinancialTransaction.case_id == self.f.case.id, FinancialTransaction.ledger_status == 'admitted'))))

    def status(self):
        with self.f.SessionLocal() as db:
            return graph_followup.follow_up_status(db, self.f.case.id, graph_session_factory=self.graph.session)


class InvokedAfterAdmissionTests(GraphFollowUpTestCase):
    def test_worker_import_requests_follow_up_and_worker_round_draws_the_payments(self):
        batch = self._worker_import()
        self.assertEqual(self.ledger_count(), 12)
        # The worker turn only recorded a request; nothing touched the graph.
        self.assertTrue(graph_followup.pending_state(self.case)['requested'])
        self.assertEqual(self.graph.writes, 0)
        self.assertEqual(self.status()['status'], 'pending')

        results = self.run_due()
        self.assertEqual([r['outcome'] for r in results], ['projected'])
        self.assertEqual(self.graph.count(LABEL_TRANSACTION, self.case), 12)
        self.assertGreaterEqual(self.graph.count(LABEL_ACCOUNT, self.case), 1)
        self.assertEqual(self.graph.count(LABEL_DOCUMENT, self.case), 1)
        self.assertEqual(self.graph.edge_count(REL_TRANSFERRED_TO), 12)
        self.assertIsNone(graph_followup.pending_state(self.case))
        state = self.status()
        self.assertEqual(state['status'], 'current')
        self.assertEqual(state['projected_transactions'], 12)
        # The batch result is unaffected by the graph follow-up.
        with self.f.SessionLocal() as db:
            shown = import_batches.batch_status(db, case_id=self.f.case.id, batch_id=batch)
        self.assertEqual(shown['counts']['imported'], 1)

    def test_direct_confirmation_also_requests_follow_up(self):
        self.f.confirm()
        self.assertTrue(graph_followup.pending_state(self.case)['requested'])

    def test_request_waits_for_a_quiet_interval_but_not_beyond_the_maximum_deferral(self):
        start = self.clock.now
        graph_followup.request_follow_up(self.case, now=start)
        self.clock.now = start + 1
        self.assertEqual(graph_followup.run_due(self.f.SessionLocal, self.graph.session, clock=self.clock), [])
        # Continuous requests keep resetting the quiet interval ...
        for step in range(1, graph_followup.MAX_DEFER_SECONDS, 10):
            graph_followup.request_follow_up(self.case, now=start + step)
        self.clock.now = start + graph_followup.MAX_DEFER_SECONDS - 5
        self.assertEqual(self.run_due(), [])
        # ... but the maximum deferral still bounds the wait.
        self.clock.now = start + graph_followup.MAX_DEFER_SECONDS
        self.assertEqual([r['outcome'] for r in self.run_due()], ['projected'])

    def test_worker_loop_round_runs_projection_off_the_event_loop(self):
        self.f.confirm()
        graph_followup.request_follow_up(self.case, immediate=True)
        results = asyncio.run(graph_followup.follow_up_round(self.f.SessionLocal, self.graph.session))
        self.assertEqual([r['outcome'] for r in results], ['projected'])
        self.assertEqual(self.graph.count(LABEL_TRANSACTION, self.case), 12)

    def test_disabled_switch_projects_nothing(self):
        self.f.confirm()
        graph_followup.request_follow_up(self.case, immediate=True)
        with patch.dict(os.environ, {graph_followup.ENABLED_ENV: "0"}):
            self.assertEqual(self.run_due(), [])
        self.assertEqual(self.graph.writes, 0)

    def test_duplicate_ignored_receipt_does_not_request_follow_up(self):
        from services.financial import statement_import
        with patch.object(statement_import, '_write_statement_import', return_value=dict(outcome='duplicate_ignored')):
            statement_import.confirm_statement_import(session_factory=self.f.SessionLocal, case_id=self.f.case.id,
                evidence_file_id=uuid4(), request={}, actor=None, resolve_path=None)
        self.assertIsNone(graph_followup.pending_state(self.case))

    def _worker_import(self):
        f = self.f
        with f.SessionLocal() as db:
            batch = import_batches.create_batch(db, case_id=f.case.id, request_id=uuid4(),
                file_ids=[f.file.id], folder_ids=[], actor=f.actor)
        self._advance(batch)
        with f.SessionLocal() as db:
            revision = import_batches.batch_status(db, case_id=f.case.id, batch_id=batch)['ready_revision']
            import_batches.queue_import(db, case_id=f.case.id, batch_id=batch, expected_revision=revision, actor=f.actor)
        self._advance(batch)
        return batch

    def _advance(self, batch):
        process = AsyncMock(side_effect=AssertionError('Existing geometry must be reused'))
        asyncio.run(import_batches.advance_batch(self.f.SessionLocal, batch, Path, process))


class IdempotencyTests(GraphFollowUpTestCase):
    def test_rerunning_the_same_ledger_creates_no_duplicates(self):
        self.f.confirm()
        first = self.project()
        nodes, edges = dict(self.graph.nodes), dict(self.graph.edges)
        second = self.project()
        self.assertEqual(first['outcome'], 'projected')
        self.assertEqual(second['outcome'], 'unchanged')
        self.assertEqual(second['statements_run'], 0)
        self.assertEqual(first['digest'], second['digest'])
        self.assertEqual(self.graph.nodes, nodes)
        self.assertEqual(self.graph.edges, edges)
        forced = self.project(force=True)
        self.assertEqual(forced['outcome'], 'projected')
        self.assertEqual(self.graph.nodes, nodes)
        self.assertEqual(self.graph.edges, edges)
        self.assertEqual(self.graph.count(LABEL_TRANSACTION), 12)

    def test_retraction_follows_the_ledger(self):
        self.f.confirm()
        self.project()
        with self.f.SessionLocal() as db:
            row = db.scalars(select(FinancialTransaction).where(FinancialTransaction.case_id == self.f.case.id)
                             .order_by(FinancialTransaction.ref_id)).first()
            gone = row.ref_id
            row.ledger_status = 'quarantined'
            row.quarantine_reason = 'unreadable_row'
            db.commit()
        report = self.project()
        self.assertEqual(report['transaction_count'], 11)
        self.assertEqual(self.graph.count(LABEL_TRANSACTION), 11)
        self.assertNotIn((LABEL_TRANSACTION, self.case, gone), self.graph.nodes)
        self.assertEqual(report['refusal_count'], 1)

    def test_indexes_are_ensured_once_and_are_idempotent(self):
        self.f.confirm()
        self.project()
        self.assertTrue(set(s.split(' ')[2] for s in graph_followup.GRAPH_INDEXES) <= self.graph.schema)
        with self.graph.session() as graph:
            self.assertEqual(graph_followup.missing_graph_indexes(graph), [])


class FailureIsolationTests(GraphFollowUpTestCase):
    def test_ledger_survives_projection_failure_and_failure_is_retried_with_backoff(self):
        self.f.confirm()
        self.assertEqual(self.ledger_count(), 12)
        graph_followup.request_follow_up(self.case, immediate=True)
        # Fail part-way through the plan: after nodes are merged, on the edges.
        self.graph.fail_on_statement = lambda cypher: 'MERGE (a)-[r:' in cypher
        first = self.run_due()
        self.assertEqual(first[0]['outcome'], 'failed')
        self.assertEqual(first[0]['attempts'], 1)
        self.assertEqual(first[0]['retry_in'], graph_followup.RETRY_BASE_SECONDS)
        # Nothing half-applied: the whole plan was one transaction.
        self.assertEqual(self.graph.count(LABEL_TRANSACTION), 0)
        # The ledger is exactly as committed.
        self.assertEqual(self.ledger_count(), 12)
        # Visible status, with the reason, recorded in process and on the marker.
        state = self.status()
        self.assertEqual(state['status'], 'retrying')
        self.assertIn('graph write failed', state['last_error'])
        self.assertEqual(self.graph.markers[self.case]['status'], 'retrying')
        # Not due again until the backoff has elapsed: no hot loop.
        self.assertEqual(self.run_due(), [])
        self.clock.now += graph_followup.RETRY_BASE_SECONDS
        second = self.run_due()
        self.assertEqual((second[0]['outcome'], second[0]['attempts'], second[0]['retry_in']),
                         ('failed', 2, graph_followup.RETRY_BASE_SECONDS * 2))
        # Recovery clears the failure.
        self.graph.fail_on_statement = None
        self.clock.now += graph_followup.RETRY_BASE_SECONDS * 2
        self.assertEqual(self.run_due()[0]['outcome'], 'projected')
        self.assertEqual(self.status()['status'], 'current')
        self.assertIsNone(graph_followup.pending_state(self.case))

    def test_backoff_is_capped(self):
        self.assertEqual(graph_followup.retry_delay(1), graph_followup.RETRY_BASE_SECONDS)
        self.assertEqual(graph_followup.retry_delay(50), graph_followup.RETRY_CAP_SECONDS)

    def test_unavailable_graph_never_fails_the_import_and_status_says_so(self):
        self.graph.unavailable = True
        receipt = self.f.confirm()
        self.assertEqual(receipt['transaction_count'], 12)
        graph_followup.request_follow_up(self.case, immediate=True)
        result = self.run_due()
        self.assertEqual(result[0]['outcome'], 'failed')
        self.assertEqual(self.ledger_count(), 12)
        self.assertEqual(self.status()['status'], 'unavailable')

    def test_a_broken_request_cannot_reach_the_import(self):
        class Broken(dict):
            def setdefault(self, *args):
                raise RuntimeError('broken registry')
        with patch.object(graph_followup, '_states', Broken()):
            receipt = self.f.confirm()
        self.assertEqual(receipt['transaction_count'], 12)
        self.assertEqual(self.ledger_count(), 12)

    def test_ledger_change_under_the_lock_is_stale_not_a_failure(self):
        self.f.confirm()
        graph_followup.request_follow_up(self.case, immediate=True)
        with patch.object(graph_followup, 'ledger_fingerprint', side_effect=['before', 'after', 'after']):
            result = self.run_due()
        self.assertEqual(result, [dict(case_id=self.case, outcome='stale')])
        self.assertEqual(self.graph.count(LABEL_TRANSACTION), 0)
        self.assertEqual(graph_followup.pending_state(self.case)['attempts'], 0)
        self.clock.now += graph_followup.STALE_RETRY_SECONDS
        self.assertEqual(self.run_due()[0]['outcome'], 'projected')

    def test_refuses_a_plan_that_would_erase_an_admitted_ledger(self):
        from services.financial import projection
        self.f.confirm()
        self.project()
        empty = projection.project_case(self.f.case.id, accounts=[], documents=[])
        with self.f.SessionLocal() as db:
            snapshot = graph_followup.snapshot_case(db, self.f.case.id)
        hollow = graph_followup.CaseSnapshot(snapshot.case_id, snapshot.fingerprint, snapshot.admitted_count, empty)
        with self.graph.session() as graph, self.assertRaises(graph_followup.UnexpectedEmptyProjection):
            graph_followup.apply_snapshot(graph, hollow)
        self.assertEqual(self.graph.count(LABEL_TRANSACTION), 12)

    def test_stop_between_statements_rolls_back(self):
        self.f.confirm()
        stop = threading.Event()
        def stop_after_first_node_merge(cypher):
            if cypher.startswith('UNWIND $rows AS row\nMERGE (n:'):
                stop.set()
        self.graph.on_statement = stop_after_first_node_merge
        with self.assertRaises(graph_followup.ProjectionStopped):
            self.project(stop=stop)
        self.assertEqual(self.graph.count(LABEL_TRANSACTION), 0)
        self.assertEqual(self.graph.count(LABEL_ACCOUNT), 0)

    def test_drift_on_a_projected_case_is_detected_and_redrawn(self):
        self.f.confirm()
        self.project()
        # The import's own request finds the graph already current.
        self.assertEqual([r['outcome'] for r in self.run_due()], ['unchanged'])
        self.assertEqual(self.run_due(), [])
        with self.f.SessionLocal() as db:
            row = db.scalars(select(FinancialTransaction).where(FinancialTransaction.case_id == self.f.case.id)).first()
            row.ledger_status = 'quarantined'
            row.quarantine_reason = 'unreadable_row'
            db.commit()
        self.assertEqual(self.status()['status'], 'pending')
        self.clock.now += graph_followup.DRIFT_SCAN_SECONDS
        results = self.run_due()
        self.assertEqual([r['outcome'] for r in results], ['projected'])
        self.assertEqual(self.graph.count(LABEL_TRANSACTION), 11)

    def test_never_projected_case_is_not_backfilled_by_the_drift_check(self):
        self.f.confirm()
        graph_followup._reset_for_tests()   # the in-process request is gone, e.g. after a restart
        self.assertEqual(self.run_due(), [])
        self.assertEqual(self.graph.count(LABEL_TRANSACTION), 0)
        self.assertEqual(self.status()['status'], 'not_projected')


class BackfillCommandTests(GraphFollowUpTestCase):
    def backfill(self, *args):
        from scripts.financial_graph_backfill import run
        out = io.StringIO()
        code = run(['--case', self.case, *args], session_factory=self.f.SessionLocal,
                   graph_session_factory=self.graph.session, out=out)
        return code, json.loads(out.getvalue())

    def test_dry_run_reports_and_writes_nothing(self):
        self.f.confirm()
        self.graph.amount_nodes = (5, 2)
        code, report = self.backfill()
        self.assertEqual(code, 0)
        self.assertTrue(report['dry_run'])
        self.assertEqual(report['admitted_transactions'], 12)
        self.assertEqual(report['transaction_count'], 12)
        self.assertEqual(report['nodes'][LABEL_TRANSACTION], 12)
        self.assertTrue(report['would_change_graph'])
        self.assertIsNone(report['marker'])
        self.assertEqual(report['legacy_untagged_amount_nodes'], 3)
        self.assertFalse(report['provenance_will_survive_read'])
        self.assertEqual(len(report['missing_graph_indexes']), len(graph_followup.GRAPH_INDEXES))
        self.assertEqual(self.graph.writes, 0)
        self.assertEqual(self.graph.nodes, {})
        self.assertEqual(self.graph.schema, set())

    def test_dry_run_without_graph_reads_only_the_ledger(self):
        self.f.confirm()
        self.graph.unavailable = True
        code, report = self.backfill('--no-graph')
        self.assertEqual(code, 0)
        self.assertEqual(report['transaction_count'], 12)
        self.assertNotIn('marker', report)

    def test_apply_projects_through_the_worker_path_and_is_repeatable(self):
        self.f.confirm()
        with patch.object(graph_followup, 'project_case_graph', wraps=graph_followup.project_case_graph) as path:
            code, report = self.backfill('--apply')
        path.assert_called_once()
        self.assertEqual(code, 0)
        self.assertEqual(report['outcome'], 'projected')
        self.assertEqual(self.graph.count(LABEL_TRANSACTION), 12)
        code, again = self.backfill('--apply')
        self.assertEqual(again['outcome'], 'unchanged')
        self.assertEqual(self.graph.count(LABEL_TRANSACTION), 12)
        code, dry = self.backfill()
        self.assertFalse(dry['would_change_graph'])
        self.assertEqual(self.status()['status'], 'current')

    def test_apply_failure_exits_nonzero_and_leaves_the_ledger(self):
        self.f.confirm()
        self.graph.fail_on_statement = lambda cypher: 'MERGE (n:FinancialTransaction' in cypher
        code, report = self.backfill('--apply')
        self.assertEqual(code, 1)
        self.assertEqual(report['outcome'], 'failed')
        self.assertEqual(self.graph.count(LABEL_TRANSACTION), 0)
        self.assertEqual(self.ledger_count(), 12)
