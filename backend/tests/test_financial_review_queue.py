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
from uuid import UUID, uuid4

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
        check = lambda opening, closing: dict(checks=[dict(kind='closing_balance', status='unavailable',
                                                           opening_minor=opening, printed_minor=closing)])
        unread = [dict(kind='reading', row_id=f'2:0:{n}', page=2, message='The amount is missing or unreadable.') for n in range(2)]
        self.assertEqual(issue_sentence('balance', [missing], dict(check('100', '90'), problems=[missing, *unread])),
                         'Both balances read; 2 payments could not be read on page 2')
        self.assertEqual(issue_sentence('balance', [missing], check('100', None)), 'Closing balance not read: enter it from the statement')
        self.assertEqual(issue_sentence('balance', [missing], check(None, '90')), 'Opening balance not read: enter it from the statement')
        self.assertEqual(issue_sentence('balance', [missing], check(None, None)),
                         'Opening or closing balance not read: enter both from the statement')
        for reason in ('import_failed', 'saved_review', 'reprint', 'assignment', 'institution', 'holder', 'account',
                       'dates', 'incomplete', 'count', 'no_activity'):
            sentence = issue_sentence(reason, [dict(message='x', row_id='1:0:1', page=1)], {})
            self.assertTrue(sentence and '—' not in sentence, reason)

    def test_a_principal_only_credit_line_says_which_page_and_why(self):
        # The engine's hold on a credit line printing only its principal balance (C5), with the generic
        # balance problem and the unread rows it brings: the queue names the page and the missing fact.
        hold = dict(message='The general statement reader did not prove this period: This credit line prints only '
                            'its principal balance.', row_id='16:1:24:engine_hold', page=16,
                    engine_hold='principal_only_balance')
        missing = dict(kind='arithmetic', check='closing_balance',
                       message='Enter one opening and one closing balance from the statement, and complete every selected payment, to reconcile.')
        detail = describe(item(READING, missing, hold).summary)
        self.assertEqual(detail['reason'], 'principal_only')
        self.assertEqual(detail['sentence'], 'The statement prints only the principal balance; the opening amount '
                                             'owed is not printed on page 16')
        self.assertEqual(detail['page'], 16)
        self.assertEqual(detail['reasons'], ['principal_only', 'balance', 'reading'])
        # It leads ahead of a detail a person could fill: filling it would not make the period checkable.
        holder = dict(kind='statement_detail', field='holder', message='Holder missing', row_id=None)
        self.assertEqual(describe(item(holder, hold).summary)['reasons'], ['principal_only', 'holder'])
        # Any other engine hold keeps the generic reading reason.
        self.assertEqual(describe(item(dict(hold, engine_hold='not_reconciled')).summary)['reason'], 'reading')

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


class ReadCopyTests(TestCase):
    """A failed reading of a file whose bytes another upload read is a copy set aside, not "Couldn't read"."""

    class Session:
        """``files``: {id: (sha256, name[, page identity])}."""
        def __init__(self, files):
            self.files = files

        def scalars(self, query):
            from types import SimpleNamespace
            from services.financial import page_identity
            rows = []
            for i, (sha, name, *pages) in self.files.items():
                metadata = {page_identity.METADATA_KEY: dict(version=page_identity.VERSION, renderer='pymupdf-test',
                    dpi=page_identity.DPI, page_count=2, identity=pages[0], source_sha256=sha)} if pages else {}
                rows.append(SimpleNamespace(id=UUID(i), sha256=sha, original_filename=name, metadata_=metadata))
            return rows

    def run_rule(self, files, entries, failed):
        from services.financial.review_queue import _set_aside_read_copies
        return _set_aside_read_copies(self.Session(files), uuid4(), entries, failed)

    def test_failed_readings_follow_the_upload_that_was_read(self):
        read, old, unique, other_old = (str(uuid4()) for _ in range(4))
        files = {read: ('a' * 64, 'MONTH.pdf'), old: ('a' * 64, 'MONTH.pdf'), unique: ('b' * 64, 'ONLY.pdf'),
                 other_old: ('a' * 64, 'MONTH copy.pdf')}
        entries = [dict(file_id=read, bucket='waiting'), dict(file_id=old, bucket='unreadable'),
                   dict(file_id=unique, bucket='unreadable')]
        failed = [dict(batch_id='b1', source_id=other_old, file_id=other_old, filename='MONTH copy.pdf', message='x'),
                  dict(batch_id='b1', source_id=unique, file_id=unique, filename='ONLY.pdf', message='y')]
        entries, kept, copies = self.run_rule(files, entries, failed)
        by_file = {e['file_id']: e for e in entries}
        self.assertEqual((by_file[old]['bucket'], by_file[old]['copy_reason'], by_file[old]['copy_file_id'],
                          by_file[old]['copy_of'], by_file[old]['set_aside']), ('copies', 'same_file_read', read, 'MONTH.pdf', True))
        self.assertEqual(by_file[unique]['bucket'], 'unreadable')
        self.assertEqual(by_file[read]['bucket'], 'waiting')
        self.assertEqual([c['file_id'] for c in copies], [other_old])
        self.assertEqual(copies[0]['copy_of'], 'MONTH.pdf')
        self.assertEqual([k['file_id'] for k in kept], [unique])

    def test_without_a_read_twin_every_failure_stays_visible(self):
        one, two = str(uuid4()), str(uuid4())
        files = {one: ('a' * 64, 'A.pdf'), two: ('a' * 64, 'A.pdf')}
        # Two uploads of the same bytes, both unread: neither stands for the other.
        entries, kept, copies = self.run_rule(files, [dict(file_id=one, bucket='unreadable')],
            [dict(batch_id='b', source_id=two, file_id=two, filename='A.pdf', message='x')])
        self.assertEqual((entries[0]['bucket'], len(kept), copies), ('unreadable', 1, []))
        # A file is never its own copy: its readable statement does not hide its unread one.
        entries, kept, copies = self.run_rule(files, [dict(file_id=one, bucket='waiting'),
            dict(file_id=one, bucket='unreadable')], [])
        self.assertEqual([e['bucket'] for e in entries], ['waiting', 'unreadable'])


    def test_a_failed_reading_of_the_same_pages_follows_the_upload_that_was_read(self):
        """r11-copy-audit: the same statement saved again by another program (other bytes, same pages)."""
        read, resaved, failed_file, other = (str(uuid4()) for _ in range(4))
        files = {read: ('a' * 64, 'MONTH.pdf', 'p' * 64), resaved: ('b' * 64, 'MONTH resaved.pdf', 'p' * 64),
                 failed_file: ('c' * 64, 'MONTH printed.pdf', 'p' * 64), other: ('d' * 64, 'NEXT.pdf', 'q' * 64)}
        entries = [dict(file_id=read, bucket='waiting'), dict(file_id=resaved, bucket='unreadable'),
                   dict(file_id=other, bucket='unreadable')]
        failed = [dict(batch_id='b1', source_id=failed_file, file_id=failed_file, filename='MONTH printed.pdf', message='x')]
        entries, kept, copies = self.run_rule(files, entries, failed)
        by_file = {e['file_id']: e for e in entries}
        self.assertEqual((by_file[resaved]['bucket'], by_file[resaved]['copy_reason'], by_file[resaved]['copy_file_id']),
                         ('copies', 'same_pages_read', read))
        self.assertEqual(by_file[other]['bucket'], 'unreadable', 'other pages are another document')
        self.assertEqual([(c['file_id'], c['copy_reason'], c['copy_of']) for c in copies],
                         [(failed_file, 'same_pages_read', 'MONTH.pdf')])
        self.assertEqual(kept, [])
        # Without stored page identities only the bytes decide, as before.
        bare = {key: value[:2] for key, value in files.items()}
        entries, kept, copies = self.run_rule(bare, [dict(file_id=read, bucket='waiting'),
            dict(file_id=resaved, bucket='unreadable')], failed)
        self.assertEqual(([e['bucket'] for e in entries], len(kept), copies), (['waiting', 'unreadable'], 1, []))
        from services.financial import page_identity
        with patch.object(page_identity, 'ENABLED', False):
            entries, _, _ = self.run_rule(files, [dict(file_id=read, bucket='waiting'),
                dict(file_id=resaved, bucket='unreadable')], [])
        self.assertEqual(entries[1]['bucket'], 'unreadable', 'switch off: bytes only')


class SupersededFileReadingTests(QueueReadTests):
    """An empty whole-file preparation does not stand once the file is split into named statements."""

    def make_unreadable(self, batch):
        with self.f.SessionLocal() as db:
            record = db.query(Item).filter(Item.batch_id == batch).one()
            summary = {k: v for k, v in dict(record.summary).items() if k != 'readiness'}
            summary.update(can_import=False, problems=[CURRENCY], problem_count=1, currency='', transaction_count=0,
                           record_count=0, incomplete_count=0, unclassified_count=0, period_start='', period_end='')
            record.summary, record.status = summary, 'attention'
            db.commit()
            return SimpleNamespace(file_id=record.file_id, summary=summary, review_request=record.review_request)

    def test_a_named_statement_of_the_file_replaces_its_empty_whole_file_entry(self):
        batch = self.create(); self.advance(batch)
        record = self.make_unreadable(batch)
        self.assertEqual(self.queue()['counts']['unreadable'], 1)
        with self.f.SessionLocal() as db:
            named = dict(record.summary, period_start='2020-01-01', period_end='2020-01-31', transaction_count=3)
            db.add(Item(id=uuid4(), batch_id=batch, file_id=record.file_id, statement_key='a' * 64, status='attention',
                        summary=named, review_request=record.review_request))
            db.commit()
        counts = self.queue()['counts']
        self.assertEqual((counts['unreadable'], counts['waiting']), (0, 1), counts)

    def test_check_again_prepares_only_the_listed_files_from_their_saved_reading(self):
        batch = self.create(); self.advance(batch)
        self.make_unreadable(batch)
        with self.f.SessionLocal() as db:
            result = service.refresh_files(db, case_id=self.f.case.id, files=[dict(batch_id=batch, file_id=self.f.file.id),
                dict(batch_id=batch, file_id=uuid4())])
            self.assertEqual((result['requested'], result['queued'], result['skipped']), (2, 1, []))
            record = db.get(Batch, batch)
            self.assertEqual((record.status, record.files[0]['status']), ('preparing', 'processing'))
            again = service.refresh_files(db, case_id=self.f.case.id, files=[dict(batch_id=batch, file_id=self.f.file.id)])
            self.assertEqual((again['queued'], len(again['skipped'])), (0, 1))
        # The worker reuses the saved reading (advance asserts no engine reading) and prepares it again.
        self.advance(batch)
        with self.f.SessionLocal() as db:
            self.assertEqual(db.get(Batch, batch).files[0]['status'], 'checked')
        self.assertEqual(self.queue()['counts']['ready'], 1)


class PagedQueueTests(QueueReadTests):
    """A large synthetic case: pages say how much there is, counts stay whole, the cache stays bounded."""
    test_a_statement_in_two_batches_is_one_entry_and_leaves_once_saved = None
    test_a_statement_with_a_problem_is_queued_with_its_sentence_and_file_filter_applies = None
    test_a_file_removed_from_financial_is_not_counted_as_unreadable = None
    test_a_file_no_longer_in_the_case_or_read_from_a_copy_is_not_unreadable = None

    def setUp(self):
        super().setUp()
        from tests import financial_large_queue
        self.expected = financial_large_queue.build(self.f, files=30)
        from services.financial import review_queue as rq
        rq._cache.clear(); rq._recent_reads.clear()

    def queue(self, use_cache=False, **kwargs):
        with self.f.SessionLocal() as db, \
                patch('services.financial.statement_import.read_statement_import', side_effect=NO_READING), \
                patch.object(service, 'read_statement_import', side_effect=NO_READING):
            return case_review_queue(db, case_id=self.f.case.id, use_cache=use_cache, **kwargs)

    def fingerprinted(self, value):
        import sys
        import services.financial.statement_file_status  # noqa: F401
        return patch.object(sys.modules['services.financial.statement_file_status'], 'status_fingerprint',
                            side_effect=lambda *_: tuple(value))

    def test_pages_are_counted_and_never_cut_silently(self):
        whole = self.queue()
        waiting = self.expected['waiting']
        self.assertEqual((whole['counts']['waiting'], len(whole['items']), whole['totals']['waiting']),
                         (waiting, waiting, waiting))
        page = self.queue(limit=25, offset=20)
        self.assertEqual(page['counts'], whole['counts'])
        self.assertEqual(page['status_line'], whole['status_line'])
        self.assertEqual([e['id'] for e in page['items']], [e['id'] for e in whole['items'][20:45]])
        self.assertEqual(page['page'], dict(list='waiting', issue=None, offset=20, limit=25, returned=25, total=waiting))
        self.assertEqual(len(page['ready']), 25)
        self.assertEqual(page['totals']['ready'], whole['counts']['ready'])
        self.assertEqual(sorted(page['ready_item_ids']), sorted(e['id'] for e in whole['ready']))
        self.assertEqual(sum(page['issue_counts'].values()), waiting)
        currency = self.queue(limit=1000, issue='currency')
        self.assertEqual(currency['page']['total'], page['issue_counts']['currency'])
        self.assertTrue(all(e['issue_reason'] == 'currency' for e in currency['items']))
        ready = self.queue(limit=10, offset=5, page_list='ready')
        self.assertEqual([e['id'] for e in ready['ready']], [e['id'] for e in whole['ready'][5:15]])
        counts = self.queue(limit=0)
        self.assertEqual((counts['items'], counts['counts']), ([], whole['counts']))
        self.assertTrue(all('root' not in e for e in page['items']))

    def test_a_changed_case_is_answered_at_once_and_rebuilt_in_the_background(self):
        from services.financial import review_queue as rq
        fingerprint = [('a',)]
        with self.fingerprinted(fingerprint):
            first = self.queue(use_cache=True, limit=10, stale_ok=True)
            self.assertFalse(first['refreshing'])  # nothing cached yet: built now
            fingerprint.append(('b',))
            with self.f.SessionLocal() as db:
                db.query(Item).filter(Item.status == 'ready').update({'status': 'removed'})
                db.commit()
            stale = self.queue(use_cache=True, limit=10, stale_ok=True)
            self.assertTrue(stale['refreshing'])
            self.assertEqual(stale['counts'], first['counts'])
            for _ in range(100):  # the background build
                with rq._lock:
                    if rq._cache[str(self.f.case.id)][0] == tuple(fingerprint) and str(self.f.case.id) not in rq._building:
                        break
                __import__('time').sleep(0.05)
            current = self.queue(use_cache=True, limit=10, stale_ok=True)
            self.assertFalse(current['refreshing'])
            self.assertEqual(current['counts']['ready'], 0)
            fingerprint.append(('c',))
            fresh = self.queue(use_cache=True, limit=10)  # not stale_ok: waits for the current inputs
            self.assertFalse(fresh['refreshing'])

    def test_answers_never_change_the_cached_queue_and_the_cache_is_bounded(self):
        from services.financial import review_queue as rq
        fingerprint = [('a',)]
        with self.fingerprinted(fingerprint):
            self.queue(use_cache=True, limit=5)
            cached = rq._cache[str(self.f.case.id)][1]['entries']
            before = [dict(e) for e in cached]
            answer = self.queue(use_cache=True)
            for entry in answer['items']:
                entry['bucket'] = 'changed'
            self.assertEqual([dict(e) for e in cached], before)
        rq._cache.clear()
        with patch.object(rq, 'CACHE_MAX_ENTRIES', 1):
            rq._store('x', ('a',), dict(entries=[{}] * 5))
            rq._store('y', ('a',), dict(entries=[{}] * 5))
            self.assertEqual(list(rq._cache), ['y'])  # the newest stays even alone over the bound
