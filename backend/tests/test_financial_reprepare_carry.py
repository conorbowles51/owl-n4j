"""held_reprepare carries an investigator's saved work onto the current reading (reprepare_carry).

A synthetic replay on the held_reprepare fixture: an "old reader" prepared the file with another review revision
(and, in some tests, one printed payment missed). The investigator saved work on that reading. After the deploy
the sweep judges the file, carries her work onto the current reading (her values win, every difference asked
about with both values), keeps her original records, and prepares it. Anything that cannot be carried one to one
leaves the file exactly as it was.
"""
import hashlib
from copy import deepcopy
from unittest import TestCase
from unittest.mock import patch
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from postgres.models.evidence import EvidenceFile
from postgres.models.financial_import_batches import FinancialImportBatchItem as Item
from services.financial import held_reprepare as held
from services.financial import import_batches as batches
from services.financial import queue_save, reprepare_carry as carry
from services.financial.review_carry import conflict_problems
from services.financial.statement_import import read_statement_import as current_reader
from tests import test_financial_held_reprepare as held_tests

HER = dict(user_id=str(uuid4()), name='Investigator')


def _older(proposal, drop_last):
    proposal = deepcopy(proposal)
    proposal['revision'] = hashlib.sha256(('old:' + proposal['revision']).encode()).hexdigest()
    rows = [row for row in proposal['rows'] if row['kind'] == 'transaction' and not row['excluded']]
    if drop_last:
        proposal['rows'] = [row for row in proposal['rows'] if row['id'] != rows[-1]['id']]
    else:
        last = next(row for row in proposal['rows'] if row['id'] == rows[-1]['id'])
        last['issues'] = ['Check this payment against the statement.']
    return proposal


def missing_reader(*args, **kwargs):
    """An earlier reader with another revision that misses the last printed payment."""
    proposal = current_reader(*args, **kwargs)
    if kwargs.get('statement_id') is None and proposal.get('statement_choices'):
        return proposal
    return _older(proposal, True)


def doubtful_reader(*args, **kwargs):
    """An earlier reader with another revision that reads every row but doubts the last payment."""
    proposal = current_reader(*args, **kwargs)
    if kwargs.get('statement_id') is None and proposal.get('statement_choices'):
        return proposal
    return _older(proposal, False)


class ReprepareCarryTests(TestCase):
    def setUp(self):
        self.h = held_tests.HeldReprepareTests('test_the_stamp_covers_every_financial_module')
        self.h.setUp()
        self.f = self.h.f
        self.patch = patch.object(held, 'CARRY_EDITS', True)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.h.tearDown()

    def her_work(self, batch, reader, change, progress=False):
        """Her draft (and optionally saved progress) on the earlier reading, changed by ``change``."""
        with self.f.SessionLocal() as db:
            item = db.scalar(select(Item).where(Item.batch_id == batch))
            with patch('services.financial.statement_import.read_statement_import', reader):
                old = reader(db, case_id=self.f.case.id, evidence_file_id=item.file_id,
                             statement_id=item.statement_key or None)
            request = batches.initial_request(old)
            change(request)
            item.review_request = deepcopy(request)
            item.summary = {**item.summary, 'review_saved_by': HER}
            if progress:
                file = db.get(EvidenceFile, item.file_id)
                file.metadata_ = {**(file.metadata_ or {}), 'financial_review_progress': {
                    item.statement_key or '': dict(request=deepcopy(request), review_revision='r1',
                                                   saved_at='2026-10-01T00:00:00+00:00', saved_by=HER)}}
            db.commit()
            return request, item.file_id

    def snapshot(self, batch):
        with self.f.SessionLocal() as db:
            item = db.scalar(select(Item).where(Item.batch_id == batch))
            file = db.get(EvidenceFile, item.file_id)
            return item.status, deepcopy(item.summary), deepcopy(item.review_request), deepcopy(file.metadata_)

    def test_her_values_win_and_every_difference_is_asked_with_both_values(self):
        batch = self.h.prepare(reader=missing_reader)
        rows = []

        def change(request):
            request['holder'] = 'Her Holder Name'
            request['details_reason'] = 'Checked against the paper copy.'
            first = next(row for row in request['rows'] if not row['excluded'])
            first['description'] = 'Her description'
            rows.append(first['id'])
        mine, file_id = self.her_work(batch, missing_reader, change, progress=True)
        first = held.sweep(self.f.SessionLocal)
        self.assertEqual(first['verdicts'], {'changed': 1})
        mark = self.h.files(batch)[0][held.MARK]
        self.assertEqual(mark['state'], held.PENDING)
        self.assertTrue(mark['carry_work'])
        self.assertEqual(held.sweep(self.f.SessionLocal)['handed'], 1)
        entry = self.h.files(batch)[0]
        self.assertEqual(entry['recheck']['carry_work'], mark['carry_work'])
        with patch.object(queue_save, 'AUTO_SAVE_READY', True):
            self.h.drain(batch)
        live = [item for item in self.h.items(batch) if item.status != 'superseded_reading']
        item, = live
        # Her values win on the current reading.
        with self.f.SessionLocal() as db:
            fresh = current_reader(db, case_id=self.f.case.id, evidence_file_id=file_id,
                                   statement_id=item.statement_key or None)
        request = item.review_request
        self.assertEqual(request['expected_revision'], fresh['revision'])
        self.assertEqual((request['holder'], request['details_reason']),
                         ('Her Holder Name', 'Checked against the paper copy.'))
        self.assertEqual(next(row for row in request['rows'] if row['id'] == rows[0])['description'], 'Her description')
        # Both values shown, nothing imported, nobody's work saved by the System.
        self.assertEqual(item.status, 'attention')
        self.assertFalse(item.summary['can_import'])
        asked = {(p['field'], p['row_id'] is not None) for p in item.summary['problems'] if p.get('kind') == 'carry_conflict'}
        self.assertIn(('description', True), asked)
        self.assertIn(('new_line', True), asked)
        if fresh['metadata'].get('holder'):
            self.assertIn(('holder', False), asked)
        described = next(p for p in item.summary['problems'] if p.get('field') == 'description')
        self.assertEqual(described['yours'], 'Her description')
        self.assertNotEqual(described['reading'], 'Her description')
        # Her original records are kept, untouched.
        with self.f.SessionLocal() as db:
            meta = db.get(EvidenceFile, file_id).metadata_
        self.assertEqual(meta['financial_review_history'][-1]['request'], mine)
        log, = meta[carry.LOG]
        logged, = log['statements'].values()
        self.assertEqual(logged['original_progress']['request'], mine)
        self.assertEqual(list(logged['original_drafts'].values()), [mine])
        self.assertEqual(item.summary['review_upgrade_history'][-1]['request'], mine)
        saved = meta['financial_review_progress'][item.statement_key or '']
        self.assertEqual((saved['saved_by'], saved['carried_from']['reason']), (HER, carry.REASON))
        mark = self.h.files(batch)[0][held.MARK]
        self.assertEqual(mark['state'], 'done')
        # The next sweep leaves it: her carried work is on the current reading now.
        self.assertEqual(held.sweep(self.f.SessionLocal)['handed'], 0)

    def test_work_with_no_difference_is_ready_for_her_to_save_and_never_saved_by_the_system(self):
        batch = self.h.prepare(reader=doubtful_reader)
        self.assertEqual([i.status for i in self.h.items(batch)], ['attention'])

        def change(request):
            request['details_reason'] = 'Checked.'
        self.her_work(batch, doubtful_reader, change)
        held.sweep(self.f.SessionLocal)
        held.sweep(self.f.SessionLocal)
        with patch.object(queue_save, 'AUTO_SAVE_READY', True):
            self.h.drain(batch)
        item, = self.h.items(batch)
        self.assertEqual(item.status, 'ready', item.summary.get('problems'))
        self.assertTrue(item.summary['can_import'])
        self.assertEqual(item.review_request['details_reason'], 'Checked.')

    def test_a_row_of_hers_with_no_counterpart_leaves_the_file_exactly_as_it_is(self):
        batch = self.h.prepare(reader=missing_reader)

        def change(request):
            row = next(row for row in request['rows'] if not row['excluded'])
            row['id'] = 'row-the-reader-no-longer-has'
            row['amount_minor'] = '987654321'
        self.her_work(batch, missing_reader, change)
        before = self.snapshot(batch)
        outcome = held.sweep(self.f.SessionLocal)
        self.assertEqual((outcome['verdicts'], outcome['handed']), ({'investigator_edits': 1}, 0))
        mark = self.h.files(batch)[0][held.MARK]
        self.assertEqual((mark['state'], mark['reason'], mark['carry']), (held.LEFT, 'investigator_edits', 'row_not_found'))
        self.assertEqual(self.snapshot(batch), before)

    def test_two_different_drafts_leave_the_file_as_it_is(self):
        batch = self.h.prepare(reader=missing_reader)
        self.her_work(batch, missing_reader, lambda request: request.update(holder='One'), progress=True)
        with self.f.SessionLocal() as db:
            item = db.scalar(select(Item).where(Item.batch_id == batch))
            item.review_request = {**item.review_request, 'holder': 'Another'}
            db.commit()
        before = self.snapshot(batch)
        held.sweep(self.f.SessionLocal)
        self.assertEqual(self.h.files(batch)[0][held.MARK]['carry'], 'two_drafts')
        self.assertEqual(self.snapshot(batch), before)

    def test_work_changed_after_hand_off_prepares_nothing(self):
        batch = self.h.prepare(reader=missing_reader)
        self.her_work(batch, missing_reader, lambda request: request.update(holder='Her Holder Name'))
        held.sweep(self.f.SessionLocal)
        self.assertEqual(held.sweep(self.f.SessionLocal)['handed'], 1)
        with self.f.SessionLocal() as db:
            item = db.scalar(select(Item).where(Item.batch_id == batch))
            item.review_request = {**item.review_request, 'holder': 'Changed again'}
            db.commit()
        before = self.snapshot(batch)
        self.h.drain(batch)
        self.assertEqual(self.snapshot(batch), before)
        entry = self.h.files(batch)[0]
        self.assertEqual((entry['status'], entry[held.MARK]['state'], entry[held.MARK]['carry']),
                         ('checked', held.LEFT, 'work_changed'))

    def test_switched_off_at_the_worker_prepares_nothing(self):
        batch = self.h.prepare(reader=missing_reader)
        self.her_work(batch, missing_reader, lambda request: request.update(holder='Her Holder Name'))
        held.sweep(self.f.SessionLocal)
        held.sweep(self.f.SessionLocal)
        before = self.snapshot(batch)
        with patch.object(held, 'CARRY_EDITS', False):
            self.h.drain(batch)
        self.assertEqual(self.snapshot(batch), before)
        self.assertEqual(self.h.files(batch)[0][held.MARK]['carry'], 'switched_off')

    def test_a_hand_added_payment_the_reader_now_reads_is_not_carried(self):
        batch = self.h.prepare(reader=missing_reader)
        with self.f.SessionLocal() as db:
            item = db.scalar(select(Item).where(Item.batch_id == batch))
            fresh = batches.initial_request(current_reader(db, case_id=self.f.case.id, evidence_file_id=item.file_id))
            page = current_reader(db, case_id=self.f.case.id, evidence_file_id=item.file_id)['page_numbers'][0]
        missed = [row for row in fresh['rows'] if not row['excluded']][-1]

        def change(request):
            request['rows'].append({**missed, 'id': 'manual:her-row', 'manual_page': page})
        self.her_work(batch, missing_reader, change)
        before = self.snapshot(batch)
        held.sweep(self.f.SessionLocal)
        self.assertEqual(self.h.files(batch)[0][held.MARK]['carry'], 'added_row_now_read')
        self.assertEqual(self.snapshot(batch), before)

    def test_a_duplicate_decision_still_protects_work(self):
        batch = self.h.prepare(reader=missing_reader)
        self.her_work(batch, missing_reader, lambda request: request.update(holder='Her Holder Name'))
        with self.f.SessionLocal() as db:
            item = db.scalar(select(Item).where(Item.batch_id == batch))
            file = db.get(EvidenceFile, item.file_id)
            file.metadata_ = {**(file.metadata_ or {}), 'financial_duplicate_dispositions': {
                item.statement_key or '': dict(status='ignored', actor=HER)}}
            db.commit()
        before = self.snapshot(batch)
        self.assertEqual(held.sweep(self.f.SessionLocal)['verdicts'], {'duplicate_decision': 1})
        self.assertEqual(self.snapshot(batch), before)

    def test_the_dry_run_estimate_counts_carried_files_and_writes_nothing(self):
        batch = self.h.prepare(reader=missing_reader)
        self.her_work(batch, missing_reader, lambda request: request.update(holder='Her Holder Name'))
        before = self.snapshot(batch)
        with self.f.SessionLocal() as db:
            result, changed = held.estimate(db, self.f.case.id)
            (source_id, chosen), = result['carried']
            (_, _, detail), = chosen
            outcome, rows = carry.measure(db, self.f.case.id, detail['reading'], detail['source'])
            db.rollback()
        self.assertEqual(result['changed'], dict(originals=1, batch_files=1, held_items=1))
        self.assertEqual(outcome, 'carried')
        self.assertEqual([(row['kind'], row['status'], row['new_lines']) for row in rows], [('carried', 'attention', 1)])
        self.assertEqual(self.snapshot(batch), before)

    def test_the_work_query_compiles_for_postgres(self):
        with self.f.SessionLocal() as db:
            statements = []
            original = db.scalars

            def capture(statement, *args, **kwargs):
                statements.append(statement)
                return original(statement, *args, **kwargs)
            file = db.get(EvidenceFile, self.f.file.id)
            with patch.object(db, 'scalars', capture):
                carry.work(db, self.f.case.id, file)
            sql = str(statements[0].compile(dialect=postgresql.dialect()))
        self.assertIn('review_request IS NOT NULL', sql)
        self.assertIn('JOIN financial_import_batches', sql)


class ConflictQuestionTests(TestCase):
    def test_row_and_detail_conflicts_are_asked_only_while_the_carried_review_stands(self):
        request = dict(rows=[])
        saved = dict(request=request, carry_conflicts=dict(holder=dict(yours='A', reading='B')),
                     carry_row_conflicts=[dict(row_id='r1', field='amount_minor', yours='12345', reading='12300'),
                                          dict(row_id='r2', field='new_line', yours=None,
                                               reading=dict(date='2023-01-02', amount_minor='500'))])
        problems = conflict_problems(dict(saved_review=saved), request)
        self.assertEqual([(p['field'], p['row_id']) for p in problems],
                         [('holder', None), ('amount_minor', 'r1'), ('new_line', 'r2')])
        self.assertIn('you entered 123.45, the statement now reads 123.00', problems[1]['message'])
        self.assertIn('2023-01-02, 5.00', problems[2]['message'])
        self.assertEqual(conflict_problems(dict(saved_review=saved), dict(rows=[1])), [])


class RowMatchTests(TestCase):
    def row(self, id, amount='100', description='Fee', date='2023-01-05'):
        return dict(id=id, date=date, amount_minor=amount, direction='debit', balance_minor=None, description=description)

    def test_same_ids_first_then_equal_printed_groups_in_order(self):
        mine = [self.row('a'), self.row('old1', '250'), self.row('old2', '250'), self.row('old3', '300', 'Her text')]
        read = [self.row('a'), self.row('n1', '250'), self.row('n2', '250'), self.row('n3', '300', 'Printed text')]
        self.assertEqual(carry.match_rows(mine, read), dict(a='a', old1='n1', old2='n2', old3='n3'))

    def test_unequal_groups_or_missing_lines_are_not_guessed(self):
        mine = [self.row('old1', '250'), self.row('old2', '250')]
        with self.assertRaises(carry.NotCarried) as raised:
            carry.match_rows(mine, [self.row('n1', '250'), self.row('n2', '250'), self.row('n3', '250')])
        self.assertEqual(raised.exception.reason, 'row_ambiguous')
        with self.assertRaises(carry.NotCarried) as raised:
            carry.match_rows(mine, [self.row('n1', '999')])
        self.assertEqual(raised.exception.reason, 'row_not_found')
