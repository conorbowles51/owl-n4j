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
from uuid import UUID, uuid4

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
        stamps = {key: self.h.files(batch)[0].get(key) for key in ('reader_stamp', held.STAMP)}
        self.h.drain(batch)
        self.assertEqual(self.snapshot(batch), before)
        entry = self.h.files(batch)[0]
        self.assertEqual((entry['status'], entry[held.MARK]['state'], entry[held.MARK]['carry']),
                         ('checked', held.LEFT, 'work_changed'))
        # Nothing was prepared: the file keeps the stamps of the reader that did prepare it.
        self.assertEqual({key: entry.get(key) for key in stamps}, stamps)
        self.assertNotEqual(entry.get(held.STAMP), held.preparation_stamp())
        self.assertNotIn('recheck', entry)

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
        self.assertNotEqual(self.h.files(batch)[0].get(held.STAMP), held.preparation_stamp())

    def test_a_carry_already_committed_is_prepared_on_retry_even_after_she_saves(self):
        batch = self.h.prepare(reader=missing_reader)
        self.her_work(batch, missing_reader, lambda request: request.update(holder='Her Holder Name'), progress=True)
        held.sweep(self.f.SessionLocal)
        self.assertEqual(held.sweep(self.f.SessionLocal)['handed'], 1)
        entry = self.h.files(batch)[0]
        # The worker's first attempt carried her work, then its preparation failed (retried later).
        with self.f.SessionLocal() as db:
            self.assertIsNone(held.carry_before_preparing(db, self.f.case.id, batch, deepcopy(entry)))
        with self.f.SessionLocal() as db:
            file = db.get(EvidenceFile, UUID(entry['file_id']))
            progress = deepcopy(file.metadata_['financial_review_progress'])
            for record in progress.values():
                record['request'] = {**record['request'], 'details_reason': 'Saved after the carry.'}
            file.metadata_ = {**file.metadata_, 'financial_review_progress': progress}
            db.commit()
        with patch.object(queue_save, 'AUTO_SAVE_READY', True):
            self.h.drain(batch)
        entry = self.h.files(batch)[0]
        self.assertEqual((entry['status'], entry[held.MARK]['state']), ('checked', 'done'))
        self.assertEqual(entry.get(held.STAMP), held.preparation_stamp())

    def test_carried_work_never_names_the_system_as_its_saver(self):
        entry = dict(saved=dict(saved_by=dict(user_id=None, name='System')), request=dict(rows=[]),
                     audit=dict(fields=[]), conflicts={}, row_conflicts=[],
                     proposal=dict(rows=[], revision='r', metadata={}))
        reading = type('R', (), dict(id=uuid4()))()
        with patch('services.financial.import_batches.initial_request', return_value=dict(rows=[])):
            record = carry.carried_record(entry, reading, 's1')
        self.assertEqual(record['saved_by'], dict(user_id=None, name='Investigator'))

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

    def test_work_the_saved_statement_already_holds_is_settled_kept_and_nothing_saved(self):
        from postgres.models.financial import FinancialTransaction
        from services.financial.reread_carry import work_fingerprint
        batch = self.h.prepare(reader=missing_reader)
        mine, file_id = self.her_work(batch, missing_reader, lambda request: request.update(holder='H'), progress=True)
        saved_as = dict(source_document_id='doc', statement_period_id='period', saved_payments=3, her_payments=0)
        def plan(session, case_id, reading, source, currency=None):
            found = carry.work(session, case_id, reading)
            (key, entries), = found.items()
            return dict(statements={key: dict(kind='saved', new_key='other-key', entries=entries, saved_as=saved_as)},
                        fresh={})
        with self.f.SessionLocal() as db:
            transactions = len(list(db.scalars(select(FinancialTransaction))))
            fingerprint = work_fingerprint(db, self.f.case.id, [file_id])
            file = dict(file_id=str(file_id), source_id=str(file_id))
            with patch.object(carry, 'plan', plan):
                self.assertEqual(carry.apply(db, case_id=self.f.case.id, batch_id=batch, file=file,
                                             fingerprint=fingerprint), 'carried')
        item, = self.h.items(batch)
        self.assertEqual(item.status, 'superseded_reading')
        self.assertEqual(item.review_request, mine)  # her draft stays on its item, verbatim
        self.assertEqual((item.summary['saved_as'], item.summary['can_import']), (saved_as, False))
        self.assertEqual(item.summary['recovery_message'], carry.SAVED_MESSAGE)
        with self.f.SessionLocal() as db:
            meta = db.get(EvidenceFile, file_id).metadata_
            self.assertEqual(len(list(db.scalars(select(FinancialTransaction)))), transactions)
        self.assertEqual(meta['financial_review_progress'], {})
        self.assertEqual(meta['financial_review_history'][-1]['request'], mine)
        logged, = meta[carry.LOG][-1]['statements'].values()
        self.assertEqual((logged['kind'], logged['saved_as'], logged['original_progress']['request']),
                         ('saved', saved_as, mine))
        self.assertEqual(list(logged['original_drafts'].values()), [mine])

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


class SameWorkTests(TestCase):
    """A batch draft equal to her saved progress but for the reading revision is one piece of work."""
    def test_a_draft_differing_only_in_revision_is_her_progress(self):
        progress = dict(request=dict(expected_revision='a', holder='H', rows=[]), saved_by=HER)
        draft = dict(expected_revision='b', holder='H', rows=[])
        entries = [('progress', progress, None), ('draft', dict(request=draft), None)]
        self.assertEqual(carry._effective(entries)[0], progress['request'])
        with patch.object(carry, 'SAME_VALUES', False), self.assertRaises(carry.NotCarried):
            carry._effective(entries)
        other = dict(draft, holder='Another')
        with self.assertRaises(carry.NotCarried) as error:
            carry._effective([('progress', progress, None), ('draft', dict(request=other), None)])
        self.assertEqual(error.exception.reason, 'two_drafts')

    def test_two_drafts_differing_only_in_revision_are_one(self):
        one, two = dict(expected_revision='a', holder='H'), dict(expected_revision='b', holder='H')
        entries = [('draft', dict(request=one), None), ('draft', dict(request=two), None)]
        self.assertEqual(carry._effective(entries)[0], one)
        with patch.object(carry, 'SAME_VALUES', False), self.assertRaises(carry.NotCarried):
            carry._effective(entries)


class SavedCounterpartTests(TestCase):
    """Her work on a statement the case already saved from this file settles only when the saved one holds it."""
    def setUp(self):
        from tests import test_financial_statement_overlap as overlap_fixture
        self.o = overlap_fixture.StatementOverlapTests('test_reason_bound_to_coverage_stays_valid_when_peer_imports')
        self.o.setUp()
        self.f = self.o.f
        batch = self.o.create(self.o.primary)
        status = self.o.b.status(batch)
        if status['counts']['ready'] != 1:
            from services.financial.statement_import import StatementReviewDraft
            item = status['items'][0]
            with self.f.SessionLocal() as db:
                batches.save_review(db, case_id=self.f.case.id, batch_id=batch, item_id=UUID(item['id']),
                                    request=StatementReviewDraft.model_validate(self.f.request()),
                                    expected_review_revision=batches._digest({}))
            status = self.o.b.status(batch)
        self.assertEqual(status['counts']['ready'], 1, status)
        with self.f.SessionLocal() as db:
            batches.queue_import(db, case_id=self.f.case.id, batch_id=batch, expected_revision=status['ready_revision'],
                                 actor=self.f.actor)
        self.o.b.advance(batch)
        self.assertEqual(self.o.b.status(batch)['counts']['imported'], 1)

    def tearDown(self):
        self.o.tearDown()

    def judge(self, change=lambda request: None, key='stale-key'):
        with self.f.SessionLocal() as db:
            decided = list(db.scalars(select(Item).where(Item.file_id == self.o.primary.id, Item.status == 'imported')))
            new_key = decided[0].statement_key or ''
            proposal = current_reader(db, case_id=self.f.case.id, evidence_file_id=self.o.primary.id,
                                      statement_id=new_key or None)
            request = batches.initial_request(proposal)
            # Lines the reader leaves out without an amount (headings) as her saved work holds them: bare.
            request['rows'] = [dict(id=row['id'], excluded=True, amount_minor='0')
                               if row['excluded'] and str(row.get('amount_minor') or '0') == '0' else row
                               for row in request['rows']]
            change(request)
            before = deepcopy(db.get(EvidenceFile, self.o.primary.id).metadata_)
            try:
                return carry.saved_counterpart(db, self.f.case.id, key, new_key, request, proposal, decided)
            finally:
                self.assertFalse(db.dirty or db.new or db.deleted)
                self.assertEqual(db.get(EvidenceFile, self.o.primary.id).metadata_, before)
                db.rollback()

    def refused(self, change, detail=None, key='stale-key'):
        with self.assertRaises(carry.NotCarried) as error:
            self.judge(change, key)
        if detail:
            self.assertEqual((error.exception.reason, getattr(error.exception, 'detail', None)),
                             ('saved_statement_differs', detail))
        return error.exception.reason

    def test_work_the_saved_statement_holds_is_settled(self):
        found = self.judge()
        self.assertGreater(found['her_payments'], 0)
        self.assertEqual(found['her_payments'], found['saved_payments'])

    def test_work_with_no_payment_line_compares_only_her_details(self):
        def blank(request):
            request['rows'] = [dict(id=row['id'], excluded=True, amount_minor='0') for row in request['rows']]
        self.assertEqual(self.judge(blank)['her_payments'], 0)
        self.assertEqual(self.judge(lambda request: request.update(rows=[]))['her_payments'], 0)

    def test_an_excluded_payment_the_case_saved_or_an_included_line_with_a_balance_is_not_settled(self):
        def exclude_one_payment(request):
            for row in request['rows']:
                row['excluded'] = True
        self.refused(exclude_one_payment, 'payments')

        def balance_only(request):
            request['rows'] = [dict(id=row['id'], excluded=True, amount_minor='0') for row in request['rows']]
            request['rows'][0].update(excluded=False, balance_minor='123456789')
        self.refused(balance_only, 'balance_line')

    def test_a_note_a_different_account_or_currency_or_line_text_is_not_settled(self):
        self.refused(lambda request: request.update(details_reason='Checked.'), 'other_value')
        self.refused(lambda request: request.update(no_activity_confirmed=True), 'other_value')
        self.refused(lambda request: request.update(_saved_balance_corrections=[dict(role='opening')]), 'other_value')
        self.refused(lambda request: request.update(account_number='99999999'), 'account')
        self.refused(lambda request: request.update(account_number='TEST999123'), 'account')
        # Institution: the same words, bank words aside. Another bank, or a name the saved one is only part of,
        # is not the saved institution; the saved name without its bank word is.
        self.refused(lambda request: request.update(institution='Another Bank'), 'details')
        self.refused(lambda request: request.update(institution='Synthetic Trust Bank'), 'details')
        self.assertGreater(self.judge(lambda request: request.update(institution='SYNTHETIC'))['her_payments'], 0)
        self.refused(lambda request: request.update(currency='EUR' if request.get('currency') != 'EUR' else 'GBP'),
                     'currency')

        def retext(request):
            row = next(row for row in request['rows'] if not row['excluded'] and str(row.get('amount_minor')) not in ('', '0'))
            row['description'] = 'Not what was saved'
        self.refused(retext, 'line_text')

    def test_the_same_key_or_the_switch_off_leaves_the_file(self):
        with self.f.SessionLocal() as db:
            key = db.scalar(select(Item.statement_key).where(Item.file_id == self.o.primary.id,
                                                             Item.status == 'imported')) or ''
        self.assertEqual(self.refused(lambda request: None, key=key), 'statement_saved_or_decided')
        with patch.object(carry, 'SAME_VALUES', False):
            self.assertEqual(self.refused(lambda request: None), 'statement_saved_or_decided')

    def test_a_different_account_sharing_the_last_digits_is_not_settled(self):
        from postgres.models.financial import FinancialAccount
        with self.f.SessionLocal() as db:
            for account in db.scalars(select(FinancialAccount)):
                if account.identifier_as_printed == 'TEST123':
                    account.identifier_as_printed, account.identifier_normalised = 'IE12BOFI90001712345678', 'IE12BOFI90001712345678'
            db.commit()
        self.refused(lambda request: request.update(account_number='IE12AIBK93001712345678'), 'account')
        self.judge(lambda request: request.update(account_number='IE12BOFI90001712345678'))

    def test_any_row_value_the_saved_statement_cannot_hold_is_not_settled(self):
        def bare(request):
            request['rows'] = [dict(id=row['id'], excluded=True, amount_minor='0') for row in request['rows']]
            return request['rows']

        def manual_without_amount(request):
            bare(request).append(dict(id='manual:her-row', manual_page=1, date='2023-01-05', description='Cash',
                                      direction='debit', amount_minor='', excluded=False))
        self.refused(manual_without_amount, 'row_value')

        def included_text_without_amount(request):
            bare(request)[0].update(excluded=False, description='Her line')
        self.refused(included_text_without_amount, 'balance_line')

        def excluded_line_with_text(request):
            bare(request)[0].update(date='2023-01-05', description='A line she left out')
        self.refused(excluded_line_with_text, 'excluded_line')

        def linked(request):
            row = next(row for row in request['rows'] if not row['excluded'] and str(row.get('amount_minor')) not in ('', '0'))
            row['counterparty_link'] = dict(kind='entity', id='x')
        self.assertIn(self.refused(linked), ('saved_statement_differs',))

        def noted(request):
            row = next(row for row in request['rows'] if not row['excluded'] and str(row.get('amount_minor')) not in ('', '0'))
            row['reason'] = 'Checked.'
        self.refused(noted, 'row_value')

    def test_a_bare_balance_line_printing_a_saved_balance_is_settled(self):
        from postgres.models.financial import FinancialStatementPeriod
        with self.f.SessionLocal() as db:
            closing = db.scalar(select(FinancialStatementPeriod.closing_balance_minor))
        if closing is None:
            self.skipTest('fixture prints no closing balance')

        def balance(request):
            request['rows'] = [dict(id=row['id'], excluded=True, amount_minor='0') for row in request['rows']]
            request['rows'][0].update(excluded=False, balance_minor=str(closing))
        self.assertEqual(self.judge(balance)['her_payments'], 0)

    def test_a_line_she_left_out_with_text_and_no_amount_is_not_settled(self):
        def headings_with_text(request):
            request['rows'][0] = dict(id=request['rows'][0]['id'], excluded=True, amount_minor='0', description='Heading')
        self.refused(headings_with_text, 'excluded_line')
