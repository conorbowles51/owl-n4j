"""One review queue per case: only statements with a decision to make, each saying why before it is opened.

The queue is a read of stored batch preparations. These tests pin the rules
that end the "open, nothing to fix, Next" loop: saved statements, copies and
notes never become queue entries; a statement prepared in several batches is
one entry; every entry has at least one actionable problem and a plain
sentence naming it; and building the queue never re-reads a PDF or writes.
"""
import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from postgres.base import Base
from postgres.models.financial_candidates import FinancialCandidateMapping, FinancialStatementReviewDraft
from postgres.models.workspace_entry import WorkspaceEntry, WorkspaceEntryLink
from postgres.models.evidence import IngestionLog
from postgres.models.financial_import_batches import FinancialImportBatch as Batch, FinancialImportBatchItem as Item
from services.financial import import_batches as service
from services.financial.batch_review_summary import needs_decision
from services.financial.review_queue import (actionable_problems, case_review_queue, classify, describe,
                                             issue_sentence, status_line)
from tests.test_financial_statement_import import StatementImportTests as Fixture

# The Financial file library (unread statement files) reads these.
FINANCIAL_SCOPE_TABLES = [FinancialCandidateMapping.__table__, FinancialStatementReviewDraft.__table__,
                          WorkspaceEntry.__table__, WorkspaceEntryLink.__table__]
NO_READING = AssertionError('The queue must not re-read a statement.')


def item(*problems, status='attention', can_import=False, **summary):
    return SimpleNamespace(status=status, summary=dict(problems=list(problems), problem_count=len(problems),
        can_import=can_import, transaction_count=summary.pop('transaction_count', 3),
        period_start=summary.pop('period_start', '2020-01-01'), **summary))


READING = dict(kind='reading', message='Check this row in the transaction section.', row_id='7:0:3', page=7)
CURRENCY = dict(message='Choose the currency printed on these statements.', row_id=None)
OVERLAP = dict(kind='coverage', message='Another statement covers some of these dates.', row_id=None)
UNAVAILABLE = dict(message='Not enough readable balances for an automatic balance check.', row_id=None)
BACKGROUND = dict(kind='readiness_pending', message='Readiness is being updated.', row_id=None)
COPY = dict(kind='coverage', matching_statement=True, row_id=None,
            message='A separate file matches this bank, full account, holder, currency and statement period.')


class QueueRulesTests(TestCase):
    def test_sentences_name_the_problem_in_plain_words(self):
        closing = dict(kind='arithmetic', check='closing_balance', difference_minor='-12345',
                       message='The payments do not add up to the printed closing balance.')
        self.assertEqual(issue_sentence('currency', [CURRENCY], {}), 'Currency not printed: choose one')
        self.assertEqual(issue_sentence('balance', [closing], {'currency': 'USD'}), 'Closing balance off by 123.45 USD')
        self.assertEqual(issue_sentence('balance', [closing], {'currency': 'JPY'}), 'Closing balance off by 12,345 JPY')
        rows = [dict(READING, row_id=f'7:0:{n}') for n in range(3)]
        self.assertEqual(issue_sentence('reading', rows, {}), '3 rows unreadable on page 7')
        missing = dict(kind='arithmetic', check='closing_balance',
                       message='Enter one opening and one closing balance from the statement, and complete every selected payment, to reconcile.')
        self.assertEqual(issue_sentence('balance', [missing], {}), 'Opening or closing balance not read: enter both from the statement')
        for reason in ('import_failed', 'saved_review', 'reprint', 'assignment', 'institution', 'holder', 'account',
                       'dates', 'incomplete', 'count', 'no_activity'):
            sentence = issue_sentence(reason, [dict(message='x', row_id='1:0:1', page=1)], {})
            self.assertTrue(sentence and '—' not in sentence, reason)

    def test_notes_and_background_updates_are_not_actionable(self):
        self.assertEqual(actionable_problems(item(OVERLAP, UNAVAILABLE, BACKGROUND, COPY).summary), [])
        self.assertEqual([p['review_reason'] for p in actionable_problems(item(OVERLAP, READING).summary)], ['reading'])

    def test_describe_leads_with_the_most_important_reason_and_lands_on_its_row(self):
        detail = describe(item(READING, CURRENCY, dict(kind='statement_detail', field='holder',
            message='The account holder has not been identified.')).summary)
        self.assertEqual(detail['reason'], 'currency')
        # A single-field issue names the control to focus on open.
        self.assertEqual(detail['field'], 'currency')
        self.assertEqual(detail['other_problems'], 2)
        detail = describe(item(READING).summary)
        self.assertEqual((detail['row_id'], detail['page']), ('7:0:3', 7))
        self.assertEqual(describe(item(dict(kind='statement_detail', field='holder', message='Holder missing')).summary)['field'], 'holder')

    def test_buckets(self):
        cases = {
            'waiting': item(READING),
            'ready': item(status='ready', can_import=True),
            'imported': item(READING, status='imported'),
            'saving': item(status='pending_import'),
            'left_unimported': item(READING, status='skipped'),
            'copies': item(status='duplicate_ignored'),
            'rechecking': item(BACKGROUND, readiness_pending=True),
            'unreadable': item(CURRENCY, transaction_count=0, period_start=''),
        }
        for bucket, value in cases.items():
            self.assertEqual(classify(value), bucket, bucket)
        self.assertEqual(classify(item(COPY)), 'copies')
        # Notes only, still importable: nothing to fix, ready to save.
        self.assertEqual(classify(item(OVERLAP, UNAVAILABLE, can_import=True)), 'ready')
        # Held with no stated reason is counted, never queued as work.
        self.assertEqual(classify(item(OVERLAP, can_import=False)), 'unexplained')

    def test_every_waiting_statement_has_an_actionable_problem_and_a_sentence(self):
        """The hamster-wheel guard: no queue entry can open with nothing to fix."""
        problems = [READING, CURRENCY, OVERLAP, UNAVAILABLE, BACKGROUND, COPY,
                    dict(kind='statement_detail', field='account_number', message='Account number missing'),
                    dict(kind='missing_field', field='amount', message='Amount missing', row_id='2:0:1', page=2),
                    dict(kind='arithmetic', check='closing_balance', difference_minor='5', message='Do not add up')]
        import itertools
        for size in range(0, 4):
            for combination in itertools.combinations(problems, size):
                for status, can_import in (('attention', False), ('ready', True), ('attention', True)):
                    value = item(*combination, status=status, can_import=can_import)
                    if classify(value) != 'waiting':
                        self.assertFalse(needs_decision(value) and classify(value) in ('ready', 'imported', 'copies'))
                        continue
                    self.assertTrue(needs_decision(value))
                    detail = describe(value.summary)
                    self.assertTrue(detail and detail['sentence'].strip() and detail['problem_total'] >= 1, combination)

    def test_status_line_counts_its_own_buckets(self):
        counts = dict(imported=5, saving=0, waiting=2, ready=1, copies=3, unreadable=1, rechecking=0,
                      left_unimported=0, assigned=0, unexplained=0, unreadable_files=1)
        self.assertEqual(status_line(counts), 'Imported 5 statements · Waiting for you 2 · Ready to import 1 · '
                                              'Copies set aside 3 · Couldn\'t read 2')


class QueueReadTests(TestCase):
    """A real (synthetic) prepared statement read through the batch machinery."""

    def setUp(self):
        self.f = Fixture('test_existing_import_and_same_request_keep_the_saved_account_for_navigation')
        self.f.setUp()
        self.f.file.status = 'processed'
        Base.metadata.create_all(self.f.db.connection(), tables=[Batch.__table__, Item.__table__, IngestionLog.__table__,
            *FINANCIAL_SCOPE_TABLES])
        self.f.db.commit()

    def tearDown(self):
        self.f.tearDown()

    def create(self, start_new=False):
        with self.f.SessionLocal() as db:
            return service.create_batch(db, case_id=self.f.case.id, request_id=uuid4(), file_ids=[self.f.file.id],
                folder_ids=[], actor=self.f.actor, start_new=start_new)

    def advance(self, batch):
        process = AsyncMock(side_effect=AssertionError('Existing geometry must be reused'))
        asyncio.run(service.advance_batch(self.f.SessionLocal, batch, Path, process))

    def older_copy_of(self, batch_id):
        """An earlier, overlapping batch over the same file (the live shape: up to 4 per statement)."""
        from copy import deepcopy
        from datetime import timedelta
        with self.f.SessionLocal() as db:
            batch = db.get(Batch, batch_id)
            older = Batch(id=uuid4(), case_id=batch.case_id, created_by=batch.created_by, status='review',
                actor=deepcopy(batch.actor), files=deepcopy(batch.files))
            db.add(older); db.flush()
            older.created_at = batch.created_at - timedelta(days=3)
            for record in db.query(Item).filter(Item.batch_id == batch_id):
                summary = {k: v for k, v in deepcopy(record.summary).items() if k != 'readiness'}
                summary.update(can_import=False, problems=[READING], problem_count=1)
                db.add(Item(id=uuid4(), batch_id=older.id, file_id=record.file_id, statement_key=record.statement_key,
                    status='attention', summary=summary, review_request=deepcopy(record.review_request)))
            db.commit()
            return older.id

    def queue(self, **kwargs):
        with self.f.SessionLocal() as db, \
                patch('services.financial.statement_import.read_statement_import', side_effect=NO_READING), \
                patch.object(service, 'read_statement_import', side_effect=NO_READING):
            result = case_review_queue(db, case_id=self.f.case.id, use_cache=False, **kwargs)
            self.assertFalse(db.new or db.dirty or db.deleted)
            return result

    def test_a_statement_in_two_batches_is_one_entry_and_leaves_once_saved(self):
        second = self.create(); self.advance(second)
        self.older_copy_of(second)
        queue = self.queue()
        statements = sum(queue['counts'][key] for key in ('waiting', 'ready', 'imported', 'copies', 'unreadable'))
        self.assertEqual(statements, 1, queue['counts'])
        self.assertEqual(queue['counts']['ready'], 1)
        self.assertEqual(queue['items'], [])
        self.assertEqual(queue['ready_batches'][0]['batch_id'], str(second))
        # Ready statements are listed too, so they can be saved from the queue.
        self.assertEqual([e['bucket'] for e in queue['ready']], ['ready'])
        # The status line counts the same buckets.
        self.assertIn('Ready to import 1', queue['status_line'])
        state = None
        with self.f.SessionLocal() as db:
            state = service.batch_status(db, case_id=self.f.case.id, batch_id=second)
            service.queue_import(db, case_id=self.f.case.id, batch_id=second,
                expected_revision=state['ready_revision'], actor=self.f.actor)
        self.advance(second)
        after = self.queue()
        self.assertEqual((after['counts']['imported'], after['counts']['ready'], after['counts']['waiting']), (1, 0, 0))
        self.assertTrue(after['status_line'].startswith('Imported 1 statements'))

    def test_a_statement_with_a_problem_is_queued_with_its_sentence_and_file_filter_applies(self):
        batch = self.create(); self.advance(batch)
        with self.f.SessionLocal() as db:
            record = db.query(Item).filter(Item.batch_id == batch).one()
            summary = dict(record.summary)
            summary.pop('readiness', None)
            summary.update(can_import=False, problems=[CURRENCY], problem_count=1, currency='')
            record.summary = summary
            record.status = 'attention'
            key = record.statement_key or None
            db.commit()
        queue = self.queue()
        self.assertEqual(queue['counts']['waiting'], 1, queue['counts'])
        entry = queue['items'][0]
        self.assertEqual(entry['issue'], 'Currency not printed: choose one')
        self.assertEqual((entry['batch_id'], entry['statement_id']), (str(batch), key))
        self.assertEqual(self.queue(file_ids=[str(self.f.file.id)])['counts']['waiting'], 1)
        self.assertEqual(self.queue(file_ids=[str(uuid4())])['counts']['waiting'], 0)
        # The batch's own walk and counts agree: one statement to decide.
        with self.f.SessionLocal() as db:
            state = service.batch_status(db, case_id=self.f.case.id, batch_id=batch)
        self.assertEqual((state['statements_with_issues'], state['needs_decision']), (1, 1))


    def failed_batch(self, message, file_id=None):
        with self.f.SessionLocal() as db:
            batch = Batch(id=uuid4(), case_id=self.f.case.id, created_by=self.f.actor.user_id, status='review',
                actor={}, files=[dict(file_id=str(file_id or self.f.file.id), source_id=str(file_id or self.f.file.id),
                                      filename='statement.pdf', status='error', error=message)])
            db.add(batch); db.commit()
            return batch.id

    def test_a_file_removed_from_financial_is_not_counted_as_unreadable(self):
        """Live: 207 'restart source unavailable' + 'Statement not found' failures were all removed files."""
        self.failed_batch('Statement not found in this case.')
        queue = self.queue()
        self.assertEqual((queue['counts']['unreadable_files'], queue['counts']['removed_files']), (1, 0))
        with self.f.SessionLocal() as db:
            from postgres.models.evidence import EvidenceFile
            record = db.get(EvidenceFile, self.f.file.id)
            record.metadata_ = dict(record.metadata_ or {}, financial_file_visibility=dict(removed=True, revision='r1'))
            db.commit()
        queue = self.queue()
        self.assertEqual((queue['counts']['unreadable_files'], queue['counts']['removed_files']), (0, 1))
        self.assertEqual(queue['unreadable_files'], [])
        moved = queue['set_aside_files'][0]
        self.assertEqual(moved['reason'], 'removed')
        self.assertIn('restore it under Removed files', moved['message'])
        self.assertEqual(moved['error'], 'Statement not found in this case.')
        self.assertNotIn("Couldn't read 1", queue['status_line'])
        self.assertIn('Files removed from Financial 1', queue['status_line'])

    def test_a_file_no_longer_in_the_case_or_read_from_a_copy_is_not_unreadable(self):
        self.failed_batch('This file could not be prepared.', file_id=uuid4())
        queue = self.queue()
        self.assertEqual((queue['counts']['unreadable_files'], queue['counts']['removed_files']), (0, 1))
        self.assertEqual(queue['set_aside_files'][0]['reason'], 'gone')
        # The same bytes prepared from another upload: the failed upload is a copy.
        prepared = self.create(); self.advance(prepared)
        with self.f.SessionLocal() as db:
            from postgres.models.evidence import EvidenceFile
            original = db.get(EvidenceFile, self.f.file.id)
            copy = EvidenceFile(id=uuid4(), case_id=self.f.case.id, original_filename='copy.pdf',
                stored_path=original.stored_path, sha256=original.sha256, size=original.size, status='processed')
            db.add(copy); db.commit()
            copy_id = copy.id
        self.failed_batch('PDF source preparation failed; inspect the document and retry.', file_id=copy_id)
        queue = self.queue()
        self.assertEqual(queue['counts']['copy_files'], 1)
        self.assertEqual(queue['counts']['unreadable_files'], 0)


class AllBlockersTests(TestCase):
    def test_every_other_blocker_is_named_after_the_summary(self):
        detail = describe(item(CURRENCY, READING, dict(kind='statement_detail', field='holder',
            message='The account holder has not been identified.'), account='123', institution='Bank').summary)
        self.assertEqual(detail['sentence'], 'Currency not printed: choose one')
        self.assertEqual(detail['reasons'][0], 'currency')
        self.assertEqual(len(detail['also']), 2)
        self.assertIn('1 row unreadable on page 7', detail['also'])
        self.assertEqual(describe(item(READING).summary)['also'], [])

    def test_a_currency_question_names_the_identity_the_reader_has_not_read(self):
        # The reader asks for the currency first; empty identity fields are named too.
        detail = describe(item(CURRENCY, holder='', account='', institution='Bank').summary)
        self.assertEqual(detail['reasons'], ['currency', 'holder', 'account'])
        self.assertEqual(detail['also'], ['Account holder not found: enter it', 'Account number not found: enter it'])
        full = describe(item(CURRENCY, holder='H', account='123', institution='Bank').summary)
        self.assertEqual((full['reasons'], full['also']), (['currency'], []))


def entry(root, bucket='waiting', reasons=('reading',), **extra):
    return dict(root=root, bucket=bucket, reasons=list(reasons), issue_reason=reasons[0] if reasons else None,
                id=f'{root}-{extra.pop("n", 0)}', file_id=root, filename=f'{root}.pdf', batch_id='b', **extra)


class ReaderCollapseTests(TestCase):
    """A file the reader cannot handle yet becomes one 'waiting for a reader fix' line."""

    def test_a_file_mostly_blocked_by_reading_or_identity_with_no_single_fix_collapses(self):
        from services.financial.review_queue import reader_collapse, reader_files
        group = [entry('f', reasons=('currency', 'account', 'holder'), n=i) for i in range(4)] + \
                [entry('f', reasons=('balance',), n=9), entry('f', bucket='imported', reasons=(), n=10)]
        reader_collapse(group)
        self.assertEqual([e['bucket'] for e in group][:4], ['reader_fix'] * 4)
        self.assertEqual(group[4]['bucket'], 'waiting')  # not a reading/identity blocker: still work
        line = reader_files(group)[0]
        self.assertEqual(line['statements'], 4)
        self.assertIn("Loupe can't read this file reliably yet (4 statements)", line['message'])

    def test_thresholds(self):
        from services.financial.review_queue import reader_collapse
        # Under half blocked: stays.
        group = [entry('g', n=i) for i in range(2)] + [entry('g', bucket='imported', reasons=(), n=5 + i) for i in range(3)]
        self.assertEqual([e['bucket'] for e in reader_collapse(group)][:2], ['waiting', 'waiting'])
        # Too small a file to call it a reader problem.
        small = [entry('h', n=i) for i in range(4)]
        self.assertEqual({e['bucket'] for e in reader_collapse(small)}, {'waiting'})
        # One statement a single field fix would make ready: the file stays work.
        fixable = [entry('k', n=i) for i in range(5)] + [entry('k', reasons=('currency',), n=9)]
        self.assertEqual({e['bucket'] for e in reader_collapse(fixable)}, {'waiting'})
        # Unreadable statements count as blocked; copies are not the file's statements.
        mixed = [entry('m', bucket='unreadable', reasons=('unreadable',), n=i) for i in range(3)] + \
                [entry('m', n=7), entry('m', n=8)] + [entry('m', bucket='copies', reasons=(), n=20 + i) for i in range(9)]
        reader_collapse(mixed)
        self.assertEqual([e['bucket'] for e in mixed][:5], ['unreadable'] * 3 + ['reader_fix'] * 2)

    def test_status_line_counts_reader_fix(self):
        counts = dict(imported=5, saving=0, waiting=2, reader_fix=7, filled=0, ready=0, copies=0, unreadable=0,
                      rechecking=0, left_unimported=0, assigned=0, unexplained=0, unreadable_files=0)
        self.assertIn('Waiting for you 2 · Waiting for a reader fix 7', status_line(counts))
