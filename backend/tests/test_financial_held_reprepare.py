"""Held statements prepared by an earlier backend reader are prepared again, by themselves, after a deploy.

A synthetic replay: a file is prepared by an "old reader" that misses one
printed payment but keeps the review revision (a backend fix the revision does
not see, so ``reader_release`` records it 'unchanged'). Its statement waits.
The deployed reader reads it fully. The batch loop's held_reprepare sweep judges
the file (read only), marks it pending (the queue says it is being rechecked),
hands it back to the batch's own preparation, and it becomes ready, with no
click and nothing else changed.
"""
import asyncio
import importlib.util
from copy import deepcopy
from pathlib import Path
from unittest import TestCase
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from postgres.models.evidence import EvidenceFile
from postgres.models.financial_import_batches import FinancialImportBatch as Batch, FinancialImportBatchItem as Item
from services.financial import held_reprepare as held
from services.financial import import_batches as batches
from services.financial import queue_save, reader_release, recovery_readers
from services.financial.review_queue import case_review_queue
from services.financial.statement_import import read_statement_import as current_reader
from tests import test_financial_statement_overlap as overlap_fixture

OLD = 'old-preparation-stamp'


def old_reader(*args, **kwargs):
    """An earlier backend reader: one printed payment missed, the review revision unchanged."""
    proposal = current_reader(*args, **kwargs)
    if kwargs.get('statement_id') is None and proposal.get('statement_choices'):
        return proposal
    proposal = deepcopy(proposal)
    rows = [row for row in proposal['rows'] if row['kind'] == 'transaction' and not row['excluded']]
    proposal['rows'] = [row for row in proposal['rows'] if row['id'] != rows[-1]['id']]
    return proposal


class HeldReprepareTests(TestCase):
    def setUp(self):
        self.fixture = overlap_fixture.StatementOverlapTests('test_reason_bound_to_coverage_stays_valid_when_peer_imports')
        self.fixture.setUp()
        self.f = self.fixture.f
        from postgres.models.financial_recovery import FinancialRecoveryItem, FinancialRecoveryRun
        bind = self.f.SessionLocal.kw['bind']
        FinancialRecoveryRun.__table__.create(bind, checkfirst=True)
        FinancialRecoveryItem.__table__.create(bind, checkfirst=True)
        self.patches = [patch.object(queue_save, 'AUTO_SAVE_READY', False), patch.object(held, 'ENABLED', True),
                        patch.object(recovery_readers, 'evidence_being_read', return_value=0)]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.fixture.tearDown()

    def turn(self, batch):
        process = AsyncMock(side_effect=AssertionError('Existing geometry must be reused'))
        asyncio.run(batches.advance_batch(self.f.SessionLocal, batch, Path, process))

    def drain(self, batch):
        for _ in range(20):
            self.turn(batch)
            with self.f.SessionLocal() as db:
                if batches.batch_for(db, self.f.case.id, batch).status != 'preparing':
                    return
        self.fail('batch did not finish')

    def prepare(self, reader=old_reader, file_ids=None):
        with self.f.SessionLocal() as db:
            batch = batches.create_batch(db, case_id=self.f.case.id, request_id=uuid4(),
                file_ids=file_ids or [self.f.file.id], folder_ids=[], actor=self.f.actor, start_new=True)
        with patch.object(batches, 'read_statement_import', reader), \
                patch.object(held, 'preparation_stamp', return_value=OLD):
            self.drain(batch)
        return batch

    def items(self, batch):
        with self.f.SessionLocal() as db:
            return list(db.scalars(select(Item).where(Item.batch_id == batch)))

    def files(self, batch):
        with self.f.SessionLocal() as db:
            return deepcopy(batches.batch_for(db, self.f.case.id, batch).files)

    def queue(self):
        with self.f.SessionLocal() as db:
            return case_review_queue(db, case_id=self.f.case.id, use_cache=False)['counts']

    def test_a_held_statement_the_revision_does_not_see_becomes_ready_after_the_deploy_with_no_click(self):
        batch = self.prepare()
        self.assertEqual([i.status for i in self.items(batch)], ['attention'])
        self.assertEqual(self.files(batch)[0][held.STAMP], OLD)
        # The release sweep compares only keys and revision: it leaves the file as it is.
        self.assertEqual(reader_release.sweep(self.f.SessionLocal)['rechecked'], 0)
        first = held.sweep(self.f.SessionLocal)
        self.assertEqual((first['verdicts'], first['handed']), ({'changed': 1}, 0))
        self.assertEqual(self.files(batch)[0][held.MARK]['state'], held.PENDING)
        counts = self.queue()
        self.assertEqual((counts['rechecking'], counts['waiting']), (1, 0))
        second = held.sweep(self.f.SessionLocal)
        self.assertEqual(second['handed'], 1)
        entry = self.files(batch)[0]
        self.assertEqual((entry['status'], entry['recheck']['reason'], entry[held.MARK]['state']),
                         ('processing', held.RECHECK_REASON, held.HANDED))
        with self.f.SessionLocal() as db:
            self.assertEqual(batches.batch_for(db, self.f.case.id, batch).status, 'preparing')
        self.assertEqual(self.queue()['rechecking'], 1)
        self.drain(batch)
        item, = self.items(batch)
        self.assertEqual(item.status, 'ready')
        self.assertTrue(item.summary['can_import'])
        entry = self.files(batch)[0]
        self.assertEqual((entry['status'], entry[held.STAMP], entry[held.MARK]['state']),
                         ('checked', held.preparation_stamp(), 'done'))
        # Nothing left: the next sweep reads nothing and hands nothing.
        self.assertEqual(held.sweep(self.f.SessionLocal), dict(handed=0, read=0, deferred=0, waiting=0,
                                                                left_at_hand_off=0, verdicts={}))

    def test_with_automatic_save_the_statement_is_saved_by_the_system(self):
        batch = self.prepare()
        held.sweep(self.f.SessionLocal)
        held.sweep(self.f.SessionLocal)
        with patch.object(queue_save, 'AUTO_SAVE_READY', True), \
                patch.object(queue_save, 'fully_reconciled', return_value=True):
            self.drain(batch)
        item, = self.items(batch)
        self.assertEqual(item.status, 'imported')
        self.assertEqual(item.summary['import_actor']['email'], queue_save.SYSTEM_ACTOR.email)

    def deployed(self, reader):
        return patch('services.financial.statement_import.read_statement_import', reader)

    def test_a_file_the_deployed_reader_prepares_the_same_way_is_left_unchanged(self):
        batch = self.prepare()
        item, = self.items(batch)
        before = (item.status, item.summary, item.updated_at)
        with self.deployed(old_reader):
            outcome = held.sweep(self.f.SessionLocal)
        self.assertEqual((outcome['verdicts'], outcome['read']), ({'unchanged': 1}, 1))
        after, = self.items(batch)
        self.assertEqual((after.status, after.summary, after.updated_at), before)
        mark = self.files(batch)[0][held.MARK]
        self.assertEqual((mark['state'], mark['reason'], mark['stamp']), (held.LEFT, 'unchanged', held.preparation_stamp()))
        self.assertEqual(held.sweep(self.f.SessionLocal)['read'], 0)

    def test_an_item_without_a_recorded_assessment_counts_as_stale_once(self):
        batch = self.prepare()
        with self.f.SessionLocal() as db:
            item = db.scalar(select(Item).where(Item.batch_id == batch))
            item.summary = {key: value for key, value in item.summary.items() if key != held.ASSESSED}
            batch_row = batches.batch_for(db, self.f.case.id, batch, True)
            files = deepcopy(batch_row.files)
            files[0].pop(held.STAMP)
            batch_row.files = files
            db.commit()
        with self.deployed(old_reader):
            self.assertEqual(held.sweep(self.f.SessionLocal)['verdicts'], {'changed': 1})
            held.sweep(self.f.SessionLocal)
        self.drain(batch)
        self.assertIn(held.ASSESSED, self.items(batch)[0].summary)
        self.assertEqual(held.sweep(self.f.SessionLocal)['read'], 0)

    def test_investigator_work_and_decisions_are_left_exactly_as_they_are(self):
        cases = {
            'investigator_edits': lambda db, item, file: setattr(item, 'review_request', batches.initial_request(
                current_reader(db, case_id=self.f.case.id, evidence_file_id=item.file_id))),
            'duplicate_decision': lambda db, item, file: setattr(file, 'metadata_', {**(file.metadata_ or {}),
                'financial_duplicate_dispositions': {item.statement_key or '': dict(status='ignored',
                    actor=dict(name='Investigator', user_id=str(uuid4())))}}),
            'removed': lambda db, item, file: setattr(file, 'metadata_', {**(file.metadata_ or {}),
                'financial_file_visibility': dict(removed=True)}),
        }
        for reason, change in cases.items():
            with self.subTest(reason=reason):
                batch = self.prepare()
                with self.f.SessionLocal() as db:
                    item = db.scalar(select(Item).where(Item.batch_id == batch))
                    change(db, item, db.get(EvidenceFile, item.file_id))
                    db.commit()
                    snapshot = (item.status, deepcopy(item.summary), deepcopy(item.review_request))
                outcome = held.sweep(self.f.SessionLocal)
                self.assertEqual(outcome['handed'], 0)
                self.assertEqual(outcome['verdicts'], {reason: 1})
                after, = self.items(batch)
                self.assertEqual((after.status, after.summary, after.review_request), snapshot)
                self.assertEqual(self.files(batch)[0]['status'], 'checked')
                with self.f.SessionLocal() as db:
                    db.execute(Batch.__table__.update().values(status='removed'))
                    file = db.get(EvidenceFile, item.file_id)
                    file.metadata_ = {k: v for k, v in (file.metadata_ or {}).items()
                                      if k not in ('financial_duplicate_dispositions', 'financial_file_visibility')}
                    db.commit()

    def test_protected_statuses_and_a_ready_sibling_protect_the_file(self):
        # (An imported sibling with no person's work on it is settled, as for the engine campaign: its own item and
        # saved records stay, and the new reading's twin of it meets the ordinary copy and already-saved gates.)
        for status, reason in (('pending_import', 'saved_import'), ('skipped', 'investigator_decision'),
                               ('duplicate_ignored', 'investigator_decision'), ('assigned', 'investigator_decision'),
                               ('ready', 'not_all_held')):
            with self.subTest(status=status):
                batch = self.prepare()
                with self.f.SessionLocal() as db:
                    item = db.scalar(select(Item).where(Item.batch_id == batch))
                    db.add(Item(id=uuid4(), batch_id=batch, file_id=item.file_id, statement_key='another-period',
                                status=status, summary={}))
                    db.commit()
                outcome = held.sweep(self.f.SessionLocal)
                self.assertEqual(outcome['handed'], 0)
                self.assertEqual(outcome['verdicts'], {reason: 1}, outcome)
                self.assertEqual(self.files(batch)[0]['status'], 'checked')
                with self.f.SessionLocal() as db:
                    db.execute(Batch.__table__.update().values(status='removed'))
                    db.commit()

    def test_a_copy_is_judged_on_the_current_reading(self):
        batch = self.prepare()
        seen = []

        def copy(session, case_id, source, items, cache=None):
            seen.extend((item.summary.get('period_start'), item.summary.get('transaction_count')) for item in items)
            return True
        with patch.object(recovery_readers, 'copy_of_saved', copy):
            outcome = held.sweep(self.f.SessionLocal)
        self.assertEqual(outcome['verdicts'], {'copy_of_saved': 1})
        stored, = self.items(batch)
        # The current reading (every printed payment), not the stored stale one.
        self.assertEqual(seen, [(stored.summary.get('period_start'), stored.summary['transaction_count'] + 1)])
        self.assertEqual(self.files(batch)[0][held.MARK]['reason'], 'copy_of_saved')

    def stale_key(self, batch):
        """The stored statement key is one the deployed reader no longer produces (an older reader's key)."""
        from uuid import uuid5
        with self.f.SessionLocal() as db:
            item = db.scalar(select(Item).where(Item.batch_id == batch))
            db.add(Item(id=uuid5(batch, f'{item.file_id}:older-reader-key'), batch_id=batch, file_id=item.file_id,
                        statement_key='older-reader-key', status=item.status, summary=deepcopy(item.summary)))
            db.delete(item)
            db.commit()

    def test_a_stale_keyed_exact_copy_is_prepared_again_with_the_current_key(self):
        batch = self.prepare()
        self.stale_key(batch)
        with patch.object(recovery_readers, 'copy_of_saved', return_value=True), \
                patch('services.financial.saved_copies.compare', return_value=dict(outcome='match')) as compare:
            outcome = held.sweep(self.f.SessionLocal)
        self.assertEqual(outcome['verdicts'], {'changed': 1})
        self.assertTrue(compare.called)
        self.assertEqual(self.files(batch)[0][held.MARK]['state'], held.PENDING)
        self.assertEqual(held.sweep(self.f.SessionLocal)['handed'], 1)
        self.drain(batch)
        # Prepared again: the statement now carries the deployed reader's key; the stale one is retired.
        keys = {(item.statement_key or '', item.status) for item in self.items(batch)}
        self.assertIn(('older-reader-key', 'superseded_reading'), keys)
        self.assertIn(('', 'ready'), keys)

    def test_a_copy_that_differs_or_keeps_its_key_or_the_switch_off_is_left(self):
        cases = dict(differs=(dict(outcome='differs'), True, '1'), current_key=(dict(outcome='match'), False, '1'),
                     switch_off=(dict(outcome='match'), True, '0'))
        for name, (result, stale, switch) in cases.items():
            with self.subTest(name):
                batch = self.prepare()
                if stale:
                    self.stale_key(batch)
                with patch.object(recovery_readers, 'copy_of_saved', return_value=True), \
                        patch('services.financial.saved_copies.compare', return_value=result), \
                        patch.dict('os.environ', {'LOUPE_FINANCIAL_AUTOFILL_REAPPLY': switch}):
                    outcome = held.sweep(self.f.SessionLocal)
                self.assertEqual(outcome['verdicts'], {'copy_of_saved': 1})
                self.assertEqual(self.files(batch)[0][held.MARK]['reason'], 'copy_of_saved')
                with self.f.SessionLocal() as db:
                    db.execute(Batch.__table__.update().values(status='removed'))
                    db.commit()

    def test_a_failed_comparison_leaves_the_copy(self):
        batch = self.prepare()
        self.stale_key(batch)
        with patch.object(recovery_readers, 'copy_of_saved', return_value=True), \
                patch('services.financial.saved_copies.compare', side_effect=RuntimeError('boom')):
            outcome = held.sweep(self.f.SessionLocal)
        self.assertEqual(outcome['verdicts'], {'copy_of_saved': 1})

    def test_work_saved_between_judging_and_hand_off_is_kept(self):
        batch = self.prepare()
        held.sweep(self.f.SessionLocal)
        with self.f.SessionLocal() as db:
            item = db.scalar(select(Item).where(Item.batch_id == batch))
            item.review_request = batches.initial_request(current_reader(db, case_id=self.f.case.id,
                                                                         evidence_file_id=item.file_id))
            db.commit()
        outcome = held.sweep(self.f.SessionLocal)
        self.assertEqual((outcome['handed'], outcome['left_at_hand_off']), (0, 1))
        entry = self.files(batch)[0]
        self.assertEqual((entry['status'], entry[held.MARK]['state'], entry[held.MARK]['reason']),
                         ('checked', held.LEFT, 'investigator_edits'))

    def test_an_original_in_two_batches_is_prepared_again_in_both_or_neither(self):
        first = self.prepare()
        second = self.prepare()
        held.sweep(self.f.SessionLocal)
        with self.f.SessionLocal() as db:
            batches.batch_for(db, self.f.case.id, first, True).status = 'paused'
            db.commit()
        self.assertEqual(held.sweep(self.f.SessionLocal)['handed'], 0)
        self.assertEqual([self.files(b)[0]['status'] for b in (first, second)], ['checked', 'checked'])
        with self.f.SessionLocal() as db:
            batches.batch_for(db, self.f.case.id, first, True).status = 'review'
            db.commit()
        self.assertEqual(held.sweep(self.f.SessionLocal)['handed'], 1)
        held_files = [self.files(b)[0] for b in (first, second)]
        handed = [entry['status'] for entry in held_files if entry[held.MARK]['state'] == held.HANDED]
        self.assertTrue(handed and set(handed) == {'processing'}, held_files)
        for batch in (second, first):
            self.drain(batch)
        self.assertNotIn('attention', [i.status for b in (first, second) for i in self.items(b)])

    def test_paced_switch_off_and_while_evidence_is_read(self):
        batch = self.prepare()
        with patch.object(held, 'ENABLED', False):
            self.assertEqual(held.sweep(self.f.SessionLocal)['verdicts'], {})
            self.assertNotIn(held.MARK, self.files(batch)[0])
        held.sweep(self.f.SessionLocal)
        with patch.object(held, 'ENABLED', False):
            self.assertEqual(self.queue()['rechecking'], 0)   # a pending mark is not shown when off
            self.assertEqual(held.sweep(self.f.SessionLocal)['handed'], 0)
        with patch.object(recovery_readers, 'evidence_being_read', return_value=1):
            self.assertEqual(held.sweep(self.f.SessionLocal)['handed'], 0)
        with patch.object(held, 'AT_ONCE', 1), patch.object(recovery_readers, 'in_flight', return_value=1):
            self.assertEqual(held.sweep(self.f.SessionLocal)['waiting'], 1)
        self.assertEqual(self.files(batch)[0]['status'], 'checked')
        with patch.object(held, 'FILES_PER_SWEEP', 0):
            self.assertEqual(held.sweep(self.f.SessionLocal)['handed'], 1)

    def test_pending_and_handed_files_never_defer_a_deploy(self):
        spec = importlib.util.spec_from_file_location(
            'ingestion_gate', Path(__file__).resolve().parents[2] / 'deploy/check_ingestion_idle.py')
        gate = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(gate)
        batch = self.prepare()
        held.sweep(self.f.SessionLocal)
        engine = self.f.SessionLocal.kw['bind']
        self.assertEqual(gate.active_work(engine), 0)          # pending
        held.sweep(self.f.SessionLocal)
        self.assertEqual(self.files(batch)[0]['status'], 'processing')
        self.assertEqual(gate.active_work(engine), 0)          # handed, between turns

    def test_the_selection_sql_compiles_for_postgres(self):
        case_id = uuid4()
        with self.f.SessionLocal() as db:
            statements = []
            original = db.execute

            def capture(statement, *args, **kwargs):
                statements.append(statement)
                return original(statement, *args, **kwargs)
            with patch.object(db, 'execute', capture):
                held._held_files(db, case_id)
        sql = str(statements[0].compile(dialect=postgresql.dialect()))
        self.assertIn('DISTINCT', sql)
        self.assertNotIn('CAST', sql)

    def test_the_stamp_covers_every_financial_module(self):
        held._stamp = None
        first = held.preparation_stamp()
        held._stamp = None
        with patch.object(Path, 'read_bytes', return_value=b'changed reader'):
            changed = held.preparation_stamp()
        held._stamp = None
        self.assertNotEqual(first, changed)
        self.assertEqual(held.preparation_stamp(), first)
        self.assertEqual(held.assessment_digest('attention', dict(a=1, readiness=dict(x=1))),
                         held.assessment_digest('attention', dict(a=1)))

    def test_the_dry_run_estimate_writes_nothing_and_counts_what_a_sweep_would_do(self):
        batch = self.prepare()
        before = self.files(batch)
        with self.f.SessionLocal() as db:
            result, changed = held.estimate(db, self.f.case.id)
            db.rollback()
        self.assertEqual(result, {'changed': dict(originals=1, batch_files=1, held_items=1)})
        self.assertEqual([(len(members), members[0][2], members[0][3]) for _, members in changed], [(1, 1, 1)])
        self.assertEqual(self.files(batch), before)
