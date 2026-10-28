"""After a release that reads statements differently, prepared files are prepared again with no click.

A synthetic replay of a release: a file is prepared by an "old reader" that
misses one printed row (so its statement does not reconcile and waits), then
the current reader is deployed. The batch loop's sweep finds the file, reads it
again read-only, sees the reading differs, and hands it back to the batch's own
preparation. Nothing is lost: drafts, imports and decisions stay as they were.
"""
import asyncio
import hashlib
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from unittest import TestCase
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

from sqlalchemy import select

from postgres.models.financial_import_batches import FinancialImportBatchItem as Item
from services.financial import import_batches as batches
from services.financial import queue_save, reader_release
from services.financial.review_queue import case_review_queue
from services.financial.statement_import import read_statement_import as current_reader
from tests import test_financial_statement_overlap as overlap_fixture

OLD = 'old-reader-stamp'


def old_reader(*args, **kwargs):
    """The reading an earlier release produced: one printed payment missed."""
    proposal = current_reader(*args, **kwargs)
    if kwargs.get('statement_id') is None and proposal.get('statement_choices'):
        return proposal
    proposal = deepcopy(proposal)
    rows = [row for row in proposal['rows'] if row['kind'] == 'transaction' and not row['excluded']]
    proposal['rows'] = [row for row in proposal['rows'] if row is not rows[-1] and row['id'] != rows[-1]['id']]
    proposal['revision'] = hashlib.sha256(('old-' + proposal['revision']).encode()).hexdigest()
    return proposal


class ReaderReleaseTests(TestCase):
    def setUp(self):
        self.fixture = overlap_fixture.StatementOverlapTests('test_reason_bound_to_coverage_stays_valid_when_peer_imports')
        self.fixture.setUp()
        self.f = self.fixture.f
        self.auto_save = patch.object(queue_save, 'AUTO_SAVE_READY', False)
        self.auto_save.start()
        from services.financial import vision_reader
        self.vision_cases = patch.object(vision_reader, 'APPROVED_CASES', frozenset({str(self.f.case.id).lower()}))
        self.vision_cases.start()
        self.addCleanup(self.vision_cases.stop)

    def tearDown(self):
        self.auto_save.stop()
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

    def prepare_with_old_reader(self):
        with self.f.SessionLocal() as db:
            batch = batches.create_batch(db, case_id=self.f.case.id, request_id=uuid4(),
                file_ids=[self.f.file.id], folder_ids=[], actor=self.f.actor)
        with patch.object(batches, 'read_statement_import', old_reader), \
                patch.object(reader_release, 'reader_stamp', return_value=OLD):
            self.drain(batch)
        return batch

    def item(self, batch):
        with self.f.SessionLocal() as db:
            return db.scalar(select(Item).where(Item.batch_id == batch))

    def files(self, batch):
        with self.f.SessionLocal() as db:
            return deepcopy(batches.batch_for(db, self.f.case.id, batch).files)

    def test_a_statement_waiting_for_a_reader_fix_becomes_ready_after_the_release_with_no_click(self):
        batch = self.prepare_with_old_reader()
        self.assertEqual(self.item(batch).status, 'attention')
        self.assertEqual(self.files(batch)[0]['reader_stamp'], OLD)
        outcome = reader_release.sweep(self.f.SessionLocal)
        self.assertEqual((outcome['compared'], outcome['rechecked']), (1, 1))
        self.assertEqual(self.files(batch)[0]['status'], 'processing')
        # While it is prepared again the queue says so instead of asking for work.
        with self.f.SessionLocal() as db:
            queue = case_review_queue(db, case_id=self.f.case.id, use_cache=False)
        self.assertEqual((queue['counts']['rechecking'], queue['counts']['waiting']), (1, 0))
        self.drain(batch)
        item = self.item(batch)
        self.assertEqual(item.status, 'ready')
        self.assertTrue(item.summary['can_import'])
        files = self.files(batch)
        self.assertEqual((files[0]['status'], files[0]['reader_stamp']), ('checked', reader_release.reader_stamp()))
        self.assertNotIn('recheck', files[0])
        # The next sweep has nothing left to do.
        self.assertEqual(reader_release.sweep(self.f.SessionLocal)['files'], 0)

    def test_with_automatic_save_the_fixed_statement_is_saved_by_the_system(self):
        batch = self.prepare_with_old_reader()
        reader_release.sweep(self.f.SessionLocal)
        with patch.object(queue_save, 'AUTO_SAVE_READY', True), \
                patch.object(queue_save, 'fully_reconciled', return_value=True):
            self.drain(batch)
        item = self.item(batch)
        self.assertEqual(item.status, 'imported')
        self.assertEqual(item.summary['import_actor']['email'], queue_save.SYSTEM_ACTOR.email)

    def test_a_release_that_reads_the_file_the_same_way_changes_nothing_but_the_stamp(self):
        with self.f.SessionLocal() as db:
            batch = batches.create_batch(db, case_id=self.f.case.id, request_id=uuid4(),
                file_ids=[self.f.file.id], folder_ids=[], actor=self.f.actor)
        with patch.object(reader_release, 'reader_stamp', return_value=OLD):
            self.drain(batch)
        before = self.item(batch)
        outcome = reader_release.sweep(self.f.SessionLocal)
        self.assertEqual((outcome['compared'], outcome['rechecked'], outcome['left']), (1, 0, {'unchanged': 1}))
        after = self.item(batch)
        self.assertEqual((after.status, after.summary, after.updated_at), (before.status, before.summary, before.updated_at))
        with self.f.SessionLocal() as db:
            self.assertEqual(batches.batch_for(db, self.f.case.id, batch).status, 'review')
        self.assertEqual(self.files(batch)[0]['reader_stamp'], reader_release.reader_stamp())

    def _unchanged_sweep(self, enabled):
        from services.financial import vision_reader
        with self.f.SessionLocal() as db:
            batch = batches.create_batch(db, case_id=self.f.case.id, request_id=uuid4(),
                file_ids=[self.f.file.id], folder_ids=[], actor=self.f.actor)
        # Prepared before the page-image reader existed: not marked.
        with patch.object(reader_release, 'reader_stamp', return_value=OLD), \
                patch.object(vision_reader, 'ENABLED', False):
            self.drain(batch)
        self.assertNotIn(vision_reader.MARK, self.files(batch)[0])
        with patch.object(vision_reader, 'ENABLED', enabled):
            outcome = reader_release.sweep(self.f.SessionLocal)
        self.assertEqual(outcome['left'].get('unchanged'), 1)
        return self.files(batch)[0].get(vision_reader.MARK)

    def test_an_unchanged_file_is_marked_for_the_page_image_reader(self):
        self.assertTrue(self._unchanged_sweep(True))

    def test_no_mark_with_the_page_image_reader_off(self):
        self.assertIsNone(self._unchanged_sweep(False))

    def test_held_statements_of_a_marked_file_are_pending_for_the_page_image_reader(self):
        from services.financial import vision_reader
        with patch.object(vision_reader, 'ENABLED', True):
            batch = self.prepare_with_old_reader()  # held, prepared with the reader on: marked
        held = self.item(batch)
        self.assertEqual(held.status, 'attention')
        self.assertTrue(self.files(batch)[0].get(vision_reader.MARK))
        with self.f.SessionLocal() as db:
            self.assertEqual(vision_reader.pending(db), [held.id])
            record = db.get(Item, held.id)
            record.review_request = dict(rows=[])  # investigator work: listed, decided, never read
            db.commit()
            self.assertEqual(vision_reader.pending(db), [held.id])
        reader = Mock()
        with patch.object(vision_reader, 'APPROVED_CASES', frozenset({vision_reader.EVERY_CASE})):
            outcome = vision_reader.read_item(self.f.SessionLocal, held.id, lambda p: p, page_reader=reader)
        self.assertEqual(outcome['reason'], 'investigator_work')
        reader.assert_not_called()
        with self.f.SessionLocal() as db:
            self.assertEqual(db.get(Item, held.id).summary['vision_reading']['line'],
                             'Not read from page images: you have saved work on it.')

    def _image_reading(self, held, *, nudge=0):
        """A page-image reading of the held statement as printed (the current reader's reading), optionally wrong by a cent."""
        from services.financial.field_proposals import CaseKnowledge, KnownAccount, SavedStatement
        with self.f.SessionLocal() as db:
            proposal = current_reader(db, case_id=self.f.case.id, evidence_file_id=held.file_id,
                                      currency=held.summary.get('currency') or None, statement_id=held.statement_key or None)
        money = lambda minor: '%d.%02d' % divmod(int(minor), 100)
        rows = [r for r in proposal['rows'] if r['kind'] == 'transaction' and not r['excluded']]
        balances = {r['fields']['description'].lower(): r for r in proposal['rows'] if r['kind'] == 'balance'}
        meta = proposal['metadata']
        page = rows[0]['page_number']
        account = dict(section_name='', institution=meta['institution'], holder=meta['holder'],
            account_number=meta['account_number'], currency=proposal['currency'], currency_as_printed=proposal['currency'],
            period_start=meta['period_start'], period_end=meta['period_end'],
            opening_balance=money(balances['opening balance']['fields']['balance']), opening_balance_page=page,
            closing_balance=money(int(balances['closing balance']['fields']['balance']) + nudge), closing_balance_page=page,
            total_credits=None, total_debits=None, count_credits=None, count_debits=None, no_transactions_printed=False,
            rows=[dict(page=r['page_number'], date=r['fields']['date'], description=r['fields']['description'] or 'PAYMENT',
                       amount=money(r['fields']['amount_minor']), direction=r['fields']['direction'], balance_after=None,
                       unreadable=False) for r in rows])
        document = dict(pages=[dict(page=n, printed_page_number=None, printed_page_total=None, is_statement_page=True)
                               for n in proposal['page_numbers']], accounts=[account])
        saved = SavedStatement(currency=proposal['currency'], period_start='2000-01-01', period_end='2000-01-31',
                               institution=meta['institution'], holder=meta['holder'], account_number=meta['account_number'])
        from services.financial.field_proposals import account_identity
        digits, masked = account_identity(meta['account_number'])
        known = KnownAccount(key=str(uuid4()), account=meta['account_number'], digits=digits, masked=masked,
                             institution=meta['institution'], currency=proposal['currency'], statements=[saved])
        return document, CaseKnowledge(accounts=[known])

    def _read_from_images(self, nudge, read=None, batch=None):
        from services.financial import vision_reader
        if batch is None:
            with patch.object(vision_reader, 'ENABLED', True):
                batch = self.prepare_with_old_reader()
        held = self.item(batch)
        self.assertEqual(held.status, 'attention')
        document, knowledge = self._image_reading(held, nudge=nudge)
        read = read or (lambda images: (document, dict(prompt_tokens=1000, completion_tokens=100)))
        reader = lambda db, case_id: ('gpt-test', read)
        with patch.object(vision_reader, 'render_pages', lambda path, pages: [(p, [b'png']) for p in pages]), \
                patch.object(batches, 'read_statement_import', old_reader), \
                patch('services.financial.statement_import.read_statement_import', old_reader), \
                patch.object(vision_reader, 'check_neighbours', lambda *a: None), \
                patch('services.financial.field_proposals.MIN_MASKED_DIGITS', 3):  # the fixture's account prints 3 digits
            import services.financial.statement_import as statement_import
            with patch.object(statement_import, 'read_statement_import', old_reader):
                outcome = vision_reader.read_item(self.f.SessionLocal, held.id, Path, page_reader=reader,
                                                  knowledge_for=lambda db, case_id: knowledge)
        return batch, held, outcome

    def _worked_on(self):
        """A held statement a person has worked on (their draft: the holder corrected by hand)."""
        from services.financial import vision_reader
        with patch.object(vision_reader, 'ENABLED', True):
            batch = self.prepare_with_old_reader()
        held = self.item(batch)
        with self.f.SessionLocal() as db:
            proposal = old_reader(db, case_id=self.f.case.id, evidence_file_id=held.file_id,
                                  currency=held.summary.get('currency') or None, statement_id=held.statement_key or None)
            draft = deepcopy(batches.initial_request(proposal))
            draft['holder'] = 'Holder as typed by the investigator'
            record = db.get(Item, held.id)
            record.review_request = draft
            db.commit()
        return batch, draft

    def _patched_readers(self):
        import services.financial.statement_import as statement_import
        from contextlib import ExitStack
        stack = ExitStack()
        for target in (patch.object(batches, 'read_statement_import', old_reader),
                       patch.object(statement_import, 'read_statement_import', old_reader),
                       patch('services.financial.field_proposals.MIN_MASKED_DIGITS', 3)):
            stack.enter_context(target)
        return stack

    def _evidence(self, file_id):
        from postgres.models.evidence import EvidenceFile
        with self.f.SessionLocal() as db:
            return deepcopy(db.get(EvidenceFile, file_id).metadata_ or {})

    def test_a_statement_a_person_worked_on_gets_an_offer_and_nothing_of_theirs_changes(self):
        self._offered()

    def _offered(self):
        from services.financial import vision_reader
        batch, draft = self._worked_on()
        before = self.item(batch)
        metadata_before = self._evidence(before.file_id)
        _, held, outcome = self._read_from_images(0, batch=batch)
        self.assertEqual(outcome['status'], 'offered', msg=outcome.get('message'))
        after = self.item(batch)
        self.assertEqual(after.status, 'attention')
        self.assertEqual(after.review_request, draft)  # their draft untouched
        metadata = self._evidence(held.file_id)
        self.assertEqual(metadata.get('financial_review_progress'), metadata_before.get('financial_review_progress'))
        self.assertEqual(metadata.get('financial_review_history'), metadata_before.get('financial_review_history'))
        shown = after.summary['vision_reading']
        self.assertEqual(shown['status'], 'offered')
        self.assertEqual(shown['offer']['mine']['holder'], 'Holder as typed by the investigator')
        self.assertNotEqual(shown['offer']['offered']['holder'], 'Holder as typed by the investigator')
        self.assertIn('nothing is changed unless you use it', shown['line'])
        stored = metadata[vision_reader.METADATA_KEY][held.statement_key or '']
        self.assertEqual(stored['offer']['request']['holder'], shown['offer']['offered']['holder'])
        return batch, held, stored

    def test_use_this_reading_saves_exactly_the_offered_reading_as_the_person(self):
        from services.financial import vision_reader
        from services.financial.decisions import Actor
        from services.financial.statement_progress import review_progress
        from postgres.models.evidence import EvidenceFile
        batch, held, stored = self._offered()
        person = Actor(name='Alex Investigator', email='alex@example.org', user_id=uuid4())
        with self._patched_readers(), self.f.SessionLocal() as db:
            vision_reader.accept_offer(db, case_id=self.f.case.id, batch_id=batch, item_id=held.id, actor=person)
        after = self.item(batch)
        from services.financial.statement_import import StatementReviewDraft
        offered = StatementReviewDraft.model_validate(stored['offer']['request']).model_dump(mode='json')
        self.assertEqual(after.review_request, offered)
        with self.f.SessionLocal() as db:
            file = db.get(EvidenceFile, held.file_id)
            progress = review_progress(file, held.statement_key)
            self.assertEqual(progress['request'], offered)
            self.assertEqual(progress['saved_by']['name'], 'Alex Investigator')
            record = file.metadata_[vision_reader.METADATA_KEY][held.statement_key or '']
            self.assertEqual((record['status'], record['decided_by']['name']), ('offer_accepted', 'Alex Investigator'))
            history = vision_reader.outcomes(file, held.statement_key)
            self.assertEqual(history[-1]['status'], 'offer_accepted')

    def test_keep_mine_leaves_their_work_and_sets_the_offer_aside(self):
        from services.financial import vision_reader
        from services.financial.decisions import Actor
        batch, held, stored = self._offered()
        draft = self.item(batch).review_request
        person = Actor(name='Alex Investigator', email='alex@example.org', user_id=uuid4())
        with self.f.SessionLocal() as db:
            vision_reader.decline_offer(db, case_id=self.f.case.id, batch_id=batch, item_id=held.id, actor=person)
        after = self.item(batch)
        self.assertEqual(after.review_request, draft)
        self.assertEqual(after.summary['vision_reading']['status'], 'offer_declined')
        with self.f.SessionLocal() as db:
            self.assertNotIn(held.id, vision_reader.pending(db))  # decided: not read or offered again

    def test_an_offer_on_work_changed_since_is_refused_and_nothing_saved(self):
        from services.financial import vision_reader
        from services.financial.decisions import Actor
        from services.financial.pdf_candidates import PdfMappingError
        batch, held, stored = self._offered()
        with self.f.SessionLocal() as db:
            record = db.get(Item, held.id)
            changed = dict(deepcopy(record.review_request), holder='Typed again later')
            record.review_request = changed
            db.commit()
        person = Actor(name='Alex Investigator', email='alex@example.org', user_id=uuid4())
        with self._patched_readers(), self.f.SessionLocal() as db, self.assertRaises(PdfMappingError) as refused:
            vision_reader.accept_offer(db, case_id=self.f.case.id, batch_id=batch, item_id=held.id, actor=person)
        self.assertEqual(refused.exception.status_code, 409)
        after = self.item(batch)
        self.assertEqual(after.review_request, changed)
        self.assertEqual(after.summary['vision_reading']['status'], 'stale')
        with self.f.SessionLocal() as db, self.assertRaises(PdfMappingError):
            vision_reader.accept_offer(db, case_id=self.f.case.id, batch_id=batch, item_id=held.id, actor=person)

    def test_offers_off_reads_nothing_of_a_person_s_work(self):
        from services.financial import vision_reader
        batch, draft = self._worked_on()
        read = Mock()
        with patch.object(vision_reader, 'OFFERS', False):
            _, held, outcome = self._read_from_images(0, read=read, batch=batch)
        self.assertEqual(outcome['reason'], 'investigator_work')
        read.assert_not_called()
        self.assertEqual(self.item(batch).review_request, draft)

    def test_a_held_statement_proved_from_its_page_images_is_saved_as_a_system_review(self):
        from services.financial import vision_reader
        from services.financial.statement_progress import review_progress
        from postgres.models.evidence import EvidenceFile
        batch, held, outcome = self._read_from_images(0)
        self.assertEqual(outcome['status'], 'proved', msg=outcome.get('message'))
        after = self.item(batch)
        self.assertEqual(after.status, 'ready')
        self.assertEqual(after.summary['vision_reading']['status'], 'proved')
        with self.f.SessionLocal() as db:
            file = db.get(EvidenceFile, held.file_id)
            progress = review_progress(file, held.statement_key)
            self.assertEqual(progress['saved_by']['name'], vision_reader.SYSTEM_NAME)
            stored = file.metadata_[vision_reader.METADATA_KEY][held.statement_key or '']
            self.assertEqual((stored['status'], stored['model']), ('proved', 'gpt-test'))
            self.assertGreater(stored['cost_usd'], 0)
        rows = after.review_request['rows']
        added = [r for r in rows if r['id'].startswith('manual:vision-')]
        self.assertTrue(added and all(r['reason'].startswith('Read from page image, page ') for r in added))
        self.assertTrue(all(r['excluded'] and r['reason'] == vision_reader.REPLACED_REASON
                            for r in rows if not r['id'].startswith('manual:') and r['amount_minor'] not in ('0', '')
                            and r.get('direction')))
        self.assertTrue(queue_save.system_filled_only(after, file))
        # Read once: a second pass reuses the stored reading.
        with self.f.SessionLocal() as db:
            self.assertEqual(vision_reader.pending(db), [])

    def test_absent_printed_pages_are_settled_by_the_printed_counts_and_totals_the_payments_match(self):
        # 2026-10-26 fin-queue3 L7: ECO Mar 2023 MN, 8 of 12 printed pages; the images print the period's deposit and
        # withdrawal counts and totals, and the 89 payments read match all four.
        from decimal import Decimal
        from services.financial import vision_reader
        with patch.object(vision_reader, 'ENABLED', True):
            batch = self.prepare_with_old_reader()
        held = self.item(batch)
        document, _ = self._image_reading(held, nudge=0)
        account = document['accounts'][0]
        for number, page in enumerate(document['pages'], 1):
            page.update(printed_page_number=number, printed_page_total=len(document['pages']) + 2)

        def counted(**values):
            def read(images):
                for direction in ('credit', 'debit'):
                    mine = [Decimal(r['amount']) for r in account['rows'] if r['direction'] == direction]
                    account['count_%ss' % direction] = len(mine)
                    account['total_%ss' % direction] = '%.2f' % sum(mine, Decimal(0))
                account.update(values)
                return document, dict(prompt_tokens=1000, completion_tokens=100)
            return read
        _, _, outcome = self._read_from_images(0, read=counted(count_debits=None), batch=batch)
        self.assertEqual(outcome['status'], 'not_proved')
        self.assertIn('pages may be missing', outcome['message'])
        with self.f.SessionLocal() as db:  # read again: the stored outcome is judged under these rules once more
            from postgres.models.evidence import EvidenceFile
            file = db.get(EvidenceFile, held.file_id)
            file.metadata_ = {k: v for k, v in file.metadata_.items() if k != vision_reader.METADATA_KEY}
            db.commit()
        with patch.object(vision_reader, 'PRINTED_COUNTS', False):
            _, _, outcome = self._read_from_images(0, read=counted(), batch=batch)
        self.assertEqual(outcome['status'], 'not_proved')
        with self.f.SessionLocal() as db:
            file = db.get(EvidenceFile, held.file_id)
            file.metadata_ = {k: v for k, v in file.metadata_.items() if k != vision_reader.METADATA_KEY}
            db.commit()
        _, _, outcome = self._read_from_images(0, read=counted(), batch=batch)
        self.assertEqual(outcome['status'], 'proved', msg=outcome.get('message'))

    def test_a_failure_after_the_review_is_saved_is_not_recorded_as_a_failed_reading(self):
        from services.financial import vision_reader

        def refresh_fails(*args, **kwargs):
            raise RuntimeError('refresh failed')
        with patch.object(batches, 'refresh_file_readiness', refresh_fails):
            batch, held, outcome = self._read_from_images(0)
        self.assertEqual(outcome['status'], 'proved', msg=outcome.get('message'))
        self.assertEqual(self._stored(held)['status'], 'proved')
        self.assertTrue(self.item(batch).review_request)

    def test_a_page_image_reading_off_by_a_cent_changes_nothing(self):
        batch, held, outcome = self._read_from_images(1)
        self.assertEqual(outcome['status'], 'not_proved')
        self.assertIn('did not balance', outcome['message'])
        after = self.item(batch)
        self.assertEqual((after.status, after.review_request), ('attention', None))
        self.assertIn('did not balance', after.summary['vision_reading']['message'])

    def test_a_failed_page_image_request_is_counted_against_the_budget_and_given_up_after_three(self):
        from services.financial import vision_reader
        calls = []

        def cut_short(images):
            calls.append(len(images))
            raise RuntimeError('The page-image reading was incomplete (length).')
        with patch.dict(vision_reader._spend, {}, clear=True):
            batch, held, outcome = self._read_from_images(0, read=cut_short)
            self.assertEqual((outcome['status'], outcome['failures']), ('failed', 1))
            reserve = vision_reader.reserve_usd('gpt-test', [(p, [b'png']) for p in outcome['pages']])
            self.assertGreater(reserve, 0)
            self.assertAlmostEqual(vision_reader.spent(self.f.case.id), reserve)
            for failures in (2, 3):
                self.assertEqual(self._read_from_images(0, read=cut_short, batch=batch)[2]['failures'], failures)
            self.assertEqual(self._read_from_images(0, read=cut_short, batch=batch)[2]['reason'], 'failed_repeatedly')
            self.assertEqual(len(calls), 3)
            self.assertAlmostEqual(vision_reader.spent(self.f.case.id), 3 * reserve)
        after = self.item(batch)
        self.assertEqual((after.status, after.review_request), ('attention', None))
        with self.f.SessionLocal() as db:
            self.assertEqual(vision_reader.pending(db), [])

    def test_a_claim_left_by_a_stopped_worker_counts_as_a_failed_request(self):
        from services.financial import vision_reader
        with patch.object(vision_reader, 'ENABLED', True):
            batch = self.prepare_with_old_reader()
        held = self.item(batch)
        calls = []
        with patch.dict(vision_reader._spend, {}, clear=True):
            first = self._read_from_images(0, read=lambda images: calls.append(1) or 1 / 0, batch=batch)[2]
            self.assertEqual(first['failures'], 1)
            long_ago = datetime(2020, 1, 1, tzinfo=timezone.utc).isoformat()
            for _ in range(2):
                # The worker stops mid-request: its claim stays 'reading' past its time.
                with self.f.SessionLocal() as db:
                    vision_reader._store(db, held.file_id, held.statement_key, dict(
                        first, status='reading', at=long_ago, failures=self._stored(held)['failures']))
                    db.commit()
                outcome = self._read_from_images(0, read=lambda images: calls.append(1) or 1 / 0, batch=batch)[2]
            # 1 failed request, then a stopped one (2), then a stopped one (3): given up, not sent again.
            self.assertEqual((outcome['status'], outcome['reason'], len(calls)), ('failed', 'failed_repeatedly', 2))
        after = self.item(batch)
        self.assertEqual(after.summary['vision_reading']['message'], vision_reader.GAVE_UP)
        with self.f.SessionLocal() as db:
            self.assertEqual(vision_reader.pending(db), [])

    def _stored(self, held):
        from services.financial import vision_reader
        from postgres.models.evidence import EvidenceFile
        with self.f.SessionLocal() as db:
            return db.get(EvidenceFile, held.file_id).metadata_[vision_reader.METADATA_KEY][held.statement_key or '']

    def test_no_request_beyond_the_case_budget(self):
        from services.financial import vision_reader
        calls = []
        with patch.dict(vision_reader._spend, {}, clear=True), patch.object(vision_reader, 'CASE_BUDGET_USD', 0.01):
            batch, held, outcome = self._read_from_images(0, read=lambda images: calls.append(1))
        self.assertEqual((outcome['status'], calls), ('budget', []))
        after = self.item(batch)
        self.assertEqual(after.status, 'attention')
        self.assertIn('budget', after.summary['vision_reading']['message'])

    def test_a_statement_claimed_by_another_worker_is_not_read_again(self):
        from services.financial import vision_reader
        with patch.object(vision_reader, 'ENABLED', True):
            batch = self.prepare_with_old_reader()
        held = self.item(batch)
        with self.f.SessionLocal() as db:
            vision_reader._store(db, held.file_id, held.statement_key, dict(
                version=vision_reader.VERSION, status='reading', at=datetime.now(timezone.utc).isoformat()))
            db.commit()
        calls = []
        # The claim is missed by the first (unlocked) look and found again under the file's lock.
        with patch.object(vision_reader, '_stored', lambda file, key: None):
            outcome = self._read_from_images(0, read=lambda images: calls.append(1), batch=batch)[2]
        self.assertEqual((outcome['reason'], calls), ('being_read', []))
        self.assertEqual(self.item(batch).status, 'attention')

    def test_a_draft_is_kept_through_the_re_preparation(self):
        batch = self.prepare_with_old_reader()
        with self.f.SessionLocal() as db:
            record = db.scalar(select(Item).where(Item.batch_id == batch))
            proposal = old_reader(db, case_id=self.f.case.id, evidence_file_id=record.file_id,
                                  currency=record.summary.get('currency'), statement_id=record.statement_key or None)
            draft = batches.initial_request(proposal)
            draft['holder'] = 'Holder typed by the investigator'
            record.review_request = draft
            db.commit()
        self.assertEqual(reader_release.sweep(self.f.SessionLocal)['rechecked'], 1)
        self.drain(batch)
        self.assertEqual(self.item(batch).review_request['holder'], 'Holder typed by the investigator')

    def test_an_imported_statement_and_a_paused_batch_are_left_alone(self):
        batch = self.prepare_with_old_reader()
        with self.f.SessionLocal() as db:
            db.scalar(select(Item).where(Item.batch_id == batch)).status = 'imported'
            db.commit()
        outcome = reader_release.sweep(self.f.SessionLocal)
        self.assertEqual((outcome['rechecked'], outcome['left']), (0, {'nothing_open': 1}))
        self.assertEqual(self.item(batch).status, 'imported')
        other = self.prepare_with_old_reader()
        with self.f.SessionLocal() as db:
            batches.batch_for(db, self.f.case.id, other, True).status = 'paused'
            db.commit()
        self.assertEqual(reader_release.sweep(self.f.SessionLocal)['files'], 0)

    def test_a_conflicting_saved_review_is_left_for_the_investigator(self):
        batch = self.prepare_with_old_reader()
        with self.f.SessionLocal() as db:
            from postgres.models.evidence import EvidenceFile
            record = db.scalar(select(Item).where(Item.batch_id == batch))
            file = db.get(EvidenceFile, record.file_id)
            file.metadata_ = {**(file.metadata_ or {}), 'financial_review_progress': {
                record.statement_key or '': dict(request=dict(expected_revision='old-revision'))}}
            db.commit()
        outcome = reader_release.sweep(self.f.SessionLocal)
        self.assertEqual((outcome['rechecked'], outcome['left']), (0, {'saved_review': 1}))
        self.assertEqual(self.files(batch)[0]['status'], 'checked')

    def test_every_changed_file_of_a_batch_is_prepared_again_in_the_same_run(self):
        other = self.fixture.copy_file(revised=True)
        with self.f.SessionLocal() as db:
            batch = batches.create_batch(db, case_id=self.f.case.id, request_id=uuid4(),
                file_ids=[self.f.file.id, other.id], folder_ids=[], actor=self.f.actor)
        with patch.object(batches, 'read_statement_import', old_reader), \
                patch.object(reader_release, 'reader_stamp', return_value=OLD):
            self.drain(batch)
        outcome = reader_release.sweep(self.f.SessionLocal)
        self.assertEqual((outcome['compared'], outcome['rechecked']), (2, 2))
        self.assertEqual([f['status'] for f in self.files(batch)], ['processing', 'processing'])
        self.drain(batch)
        with self.f.SessionLocal() as db:
            statuses = [i.status for i in db.scalars(select(Item).where(Item.batch_id == batch))]
        self.assertNotIn('attention', statuses, statuses)

    def test_switch_off_and_bounded_and_resumable(self):
        batch = self.prepare_with_old_reader()
        with patch.object(reader_release, 'RECHECK_AFTER_RELEASE', False):
            self.assertEqual(reader_release.sweep(self.f.SessionLocal)['files'], 0)
        self.assertEqual(reader_release.sweep(self.f.SessionLocal, max_files=0)['compared'], 0)
        self.assertEqual(self.files(batch)[0]['reader_stamp'], OLD)
        self.assertEqual(reader_release.sweep(self.f.SessionLocal)['rechecked'], 1)

    def test_the_stamp_covers_every_listed_reader_module(self):
        root = Path(reader_release.__file__).resolve().parent
        for pattern in reader_release.READER_MODULES:
            with self.subTest(pattern=pattern):
                self.assertTrue(list(root.glob(pattern)), pattern)
        reader_release._stamp = None
        first = reader_release.reader_stamp()
        with patch.object(Path, 'read_bytes', return_value=b'changed reader'):
            reader_release._stamp = None
            self.assertNotEqual(reader_release.reader_stamp(), first)
        reader_release._stamp = None
        self.assertEqual(reader_release.reader_stamp(), first)
