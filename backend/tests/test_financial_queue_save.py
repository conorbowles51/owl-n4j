"""Saving from the review queue: the batch save's admission, statement by statement, across batches.

And the automatic save of fully reconciled statements when their file's
preparation ends (actor System, one flag), which never touches statements
prepared earlier.
"""
from unittest.mock import patch
from uuid import UUID, uuid4

from postgres.models.financial_import_batches import (FinancialImportBatchItem as Item,
                                                      FinancialImportOperation as Operation)
from services.financial import import_batches as service
from services.financial.pdf_candidates import _digest
from services.financial import queue_save
from services.financial.review_queue import case_review_queue
from tests.test_financial_review_queue import QueueReadTests as Base, CURRENCY


class QueueSaveTests(Base):
    # The queue's own tests run in their module.
    test_a_statement_in_two_batches_is_one_entry_and_leaves_once_saved = None
    test_a_statement_with_a_problem_is_queued_with_its_sentence_and_file_filter_applies = None

    def ready_entry(self):
        queue = self.queue()
        self.assertEqual(queue['counts']['ready'], 1, queue['counts'])
        return queue['ready'][0]

    def save(self, ids, request_id=None, **kwargs):
        with self.f.SessionLocal() as db:
            return queue_save.save_statements(db, case_id=self.f.case.id, item_ids=ids, actor=self.f.actor,
                                              request_id=request_id or uuid4(), **kwargs)

    def test_ready_statement_is_saved_from_the_queue_and_leaves_it(self):
        batch = self.create(); self.advance(batch)
        entry = self.ready_entry()
        request = uuid4()
        result = self.save([entry['id']], request)
        self.assertEqual((result['queued'], result['held']), (1, []))
        self.assertEqual(result['operations'][0]['batch_id'], str(batch))
        # A retried request returns the same receipt and claims nothing more.
        again = self.save([entry['id']], request)
        self.assertEqual(again['operations'], result['operations'])
        with self.f.SessionLocal() as db:
            self.assertEqual(db.query(Operation).count(), 1)
            self.assertEqual(db.get(Item, UUID(entry['id'])).status, 'pending_import')
        self.advance(batch)
        with self.f.SessionLocal() as db:
            outcome = queue_save.save_result(db, case_id=self.f.case.id,
                operation_ids=[op['operation_id'] for op in result['operations']])
        self.assertEqual((outcome['pending'], outcome['imported'], outcome['failed']), (0, 1, []))
        after = self.queue()
        self.assertEqual((after['counts']['imported'], after['counts']['ready']), (1, 0))
        # Saving it again holds it: a statement is imported once.
        held = self.save([entry['id']])
        self.assertEqual(held['queued'], 0)
        self.assertEqual(held['held'][0]['reason'], 'Already saved')

    def test_a_statement_prepared_in_two_batches_is_saved_once(self):
        second = self.create(); self.advance(second)
        older = self.older_copy_of(second)
        with self.f.SessionLocal() as db:
            ids = [str(i.id) for i in db.query(Item).filter(Item.batch_id.in_([second, older]))]
            # The older preparation is ready too (as stored), to prove the
            # identity guard rather than the readiness check holds it.
            for record in db.query(Item).filter(Item.batch_id == older):
                record.status = 'ready'
                record.summary = {**record.summary, 'can_import': True, 'problems': [], 'problem_count': 0}
            db.commit()
        result = self.save(ids)
        self.assertEqual(result['queued'], 1)
        self.assertEqual(len(result['held']), 1)

    def test_a_statement_with_a_problem_is_held_with_its_sentence(self):
        batch = self.create(); self.advance(batch)
        with self.f.SessionLocal() as db:
            record = db.query(Item).filter(Item.batch_id == batch).one()
            record.review_request = None
            db.commit()
            item_id = str(record.id)
        # The admission check (fresh projection) decides, not the stored status.
        with patch.object(service, 'import_available', side_effect=lambda item: False):
            result = self.save([item_id])
        self.assertEqual(result['queued'], 0)
        self.assertTrue(result['held'][0]['reason'])
        with self.f.SessionLocal() as db:
            self.assertEqual(db.get(Item, UUID(str(item_id))).status, 'ready')
            self.assertEqual(db.query(Operation).count(), 0)

    def test_paused_batch_is_held(self):
        batch = self.create(); self.advance(batch)
        entry = self.ready_entry()
        with self.f.SessionLocal() as db:
            db.get(service.Batch, batch).status = 'paused'
            db.commit()
        result = self.save([entry['id']])
        self.assertEqual(result['queued'], 0)
        self.assertIn('paused', result['held'][0]['reason'])

    def test_only_reconciled_leaves_edited_statements_for_the_investigator(self):
        batch = self.create(); self.advance(batch)
        entry = self.ready_entry()
        with self.f.SessionLocal() as db:
            record = db.get(Item, UUID(entry['id']))
            # An investigator's saved review (here identical to the reading) is an edit.
            proposal = service.read_statement_import(db, case_id=self.f.case.id, evidence_file_id=record.file_id,
                currency=record.summary.get('currency'), statement_id=record.statement_key or None)
            record.review_request = service.initial_request(proposal)
            db.commit()
        result = self.save([entry['id']], only_reconciled=True)
        self.assertEqual(result['queued'], 0)
        self.assertEqual(result['held'][0]['reason'], 'Has a check or an edit: left for you')

    def test_automatic_save_after_preparation_is_system_and_switchable(self):
        batch = self.create()
        with patch.object(queue_save, 'AUTO_SAVE_READY', False):
            self.advance(batch)
        with self.f.SessionLocal() as db:
            record = db.query(Item).filter(Item.batch_id == batch).one()
            self.assertEqual(record.status, 'ready')  # switched off: nothing saved
            # A statement with no edit and no check is the one automatic case.
            record.review_request = None
            db.commit()
            item_id = record.id
        calls = []
        real = queue_save.save_statements

        def spy(*args, **kwargs):
            calls.append(kwargs)
            return real(*args, **kwargs)
        with patch.object(queue_save, 'AUTO_SAVE_READY', True), patch.object(queue_save, 'save_statements', spy), \
                patch.object(queue_save, 'fully_reconciled', return_value=True):
            with self.f.SessionLocal() as db:
                result = queue_save.auto_save_prepared(db, case_id=self.f.case.id, batch_id=batch,
                                                       file_id=self.f.file.id)
        self.assertEqual(calls[0]['actor'], queue_save.SYSTEM_ACTOR)
        self.assertTrue(calls[0]['only_reconciled'])
        self.assertEqual(result['queued'], 1)
        with self.f.SessionLocal() as db:
            operation = db.query(Operation).one()
            self.assertEqual(operation.actor, dict(name='System', user_id=None))
            self.assertEqual(db.get(Item, UUID(str(item_id))).summary['import_actor']['name'], 'System')
        self.advance(batch)
        with self.f.SessionLocal() as db:
            self.assertEqual(db.get(Item, UUID(str(item_id))).status, 'imported')

    def test_automatic_save_tries_again_after_a_lock_conflict(self):
        from sqlalchemy.exc import OperationalError

        class Deadlock(Exception):
            sqlstate = '40P01'
        outcomes = [OperationalError('INSERT', {}, Deadlock()), dict(queued=2)]

        def once(*args, **kwargs):
            outcome = outcomes.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome
        with patch.object(queue_save, 'AUTO_SAVE_READY', True), patch.object(queue_save, '_auto_save_once', once), \
                patch.object(queue_save.time, 'sleep') as sleep:
            with self.f.SessionLocal() as db:
                result = queue_save.auto_save_prepared(db, case_id=self.f.case.id, batch_id=uuid4(),
                                                       file_id=self.f.file.id)
        self.assertEqual(result, dict(queued=2))
        self.assertEqual(sleep.call_count, 1)

    def test_automatic_save_gives_up_after_repeated_lock_conflicts(self):
        from sqlalchemy.exc import OperationalError

        class Deadlock(Exception):
            sqlstate = '40P01'
        with patch.object(queue_save, 'AUTO_SAVE_READY', True), patch.object(queue_save.time, 'sleep'), \
                patch.object(queue_save, '_auto_save_once', side_effect=OperationalError('INSERT', {}, Deadlock())) as once:
            with self.f.SessionLocal() as db:
                self.assertIsNone(queue_save.auto_save_prepared(db, case_id=self.f.case.id, batch_id=uuid4(),
                                                                file_id=self.f.file.id))
        self.assertEqual(once.call_count, queue_save.AUTO_SAVE_ATTEMPTS)

    def test_automatic_save_never_raises(self):
        with patch.object(queue_save, 'AUTO_SAVE_READY', True), \
                patch.object(queue_save, 'save_statements', side_effect=RuntimeError('boom')):
            with self.f.SessionLocal() as db:
                db.add(Item(id=uuid4(), batch_id=self.create(), file_id=self.f.file.id, statement_key='',
                            status='ready', summary={}))
                db.commit()
                batch_id = db.query(Item).first().batch_id
                self.assertIsNone(queue_save.auto_save_prepared(db, case_id=self.f.case.id, batch_id=batch_id,
                                                                file_id=self.f.file.id))

    def test_held_summary_counts_reasons(self):
        held = [dict(reason='Currency not printed: choose one')] * 3 + [dict(reason='Already saved')]
        self.assertEqual(queue_save.held_summary(held), '3 currency not printed: choose one, 1 already saved')


class AutomaticSaveTests(Base):
    test_a_statement_in_two_batches_is_one_entry_and_leaves_once_saved = None
    test_a_statement_with_a_problem_is_queued_with_its_sentence_and_file_filter_applies = None

    def test_preparation_saves_a_fully_reconciled_statement_as_system(self):
        """The real hook: preparation ends, the statement checks out with no edit, the worker imports it."""
        batch = self.create()
        with patch.object(queue_save, 'AUTO_SAVE_READY', True), \
                patch.object(queue_save, 'fully_reconciled', return_value=True):
            self.advance(batch)   # prepares the file; the hook claims the ready statement
            with self.f.SessionLocal() as db:
                record = db.query(Item).filter(Item.batch_id == batch).one()
                self.assertEqual(record.status, 'pending_import')
                self.assertEqual(record.summary['import_actor']['name'], 'System')
            self.advance(batch)   # the worker imports it like any accepted save
        with self.f.SessionLocal() as db:
            self.assertEqual(db.query(Item).filter(Item.batch_id == batch).one().status, 'imported')
            self.assertEqual(db.query(Operation).one().actor['name'], 'System')

    def test_preparation_leaves_a_statement_with_a_check_for_the_investigator(self):
        batch = self.create()
        with patch.object(queue_save, 'AUTO_SAVE_READY', True), \
                patch.object(queue_save, 'fully_reconciled', return_value=False):
            self.advance(batch)
        with self.f.SessionLocal() as db:
            self.assertEqual(db.query(Item).filter(Item.batch_id == batch).one().status, 'ready')
            self.assertEqual(db.query(Operation).count(), 0)

    def test_fully_reconciled_rule(self):
        from types import SimpleNamespace as NS
        ready = NS(status='ready', summary=dict(can_import=True, problems=[], problem_count=0))
        plain = NS(review_request=None, statement_key='')
        self.assertTrue(queue_save.fully_reconciled(plain, ready, None))
        self.assertFalse(queue_save.fully_reconciled(NS(review_request={'x': 1}, statement_key=''), ready, None))
        note = NS(status='ready', summary=dict(can_import=True, problems=[CURRENCY], problem_count=1))
        self.assertFalse(queue_save.fully_reconciled(plain, note, None))
        held = NS(status='attention', summary=dict(can_import=True, problems=[], problem_count=0))
        self.assertFalse(queue_save.fully_reconciled(plain, held, None))
        draft = NS(metadata_={'financial_review_progress': {'': {'assessment': {}}}})
        self.assertFalse(queue_save.fully_reconciled(plain, ready, draft))


class BacklogCommandTests(Base):
    test_a_statement_in_two_batches_is_one_entry_and_leaves_once_saved = None
    test_a_statement_with_a_problem_is_queued_with_its_sentence_and_file_filter_applies = None

    def test_dry_run_counts_and_apply_is_idempotent(self):
        from scripts import financial_save_ready_backlog as command
        batch = self.create(); self.advance(batch)
        with self.f.SessionLocal() as db:
            counts, chosen = command.candidates(db, self.f.case.id)
        self.assertEqual((counts['ready'], len(chosen)), (1, 1))
        with patch.object(queue_save, 'fully_reconciled', return_value=True):
            rows = command.apply(self.f.SessionLocal, [self.f.case.id])
            self.assertEqual(rows[0]['queued'], 1)
            self.assertEqual(command.apply(self.f.SessionLocal, [self.f.case.id])[0]['queued'], 0)
        self.advance(batch)
        with self.f.SessionLocal() as db:
            self.assertEqual(db.query(Item).filter(Item.batch_id == batch).one().status, 'imported')


class BacklogSweepTests(Base):
    """The background save of the ready backlog: the backlog command's rule, a few per round, never twice."""
    test_a_statement_in_two_batches_is_one_entry_and_leaves_once_saved = None
    test_a_statement_with_a_problem_is_queued_with_its_sentence_and_file_filter_applies = None

    def setUp(self):
        super().setUp()
        queue_save._BACKLOG_SEEN.clear()
        switch = patch.object(queue_save, 'AUTO_SAVE_READY', True)  # tests/__init__ switches it off
        switch.start()
        self.addCleanup(switch.stop)

    def prepared_backlog(self):
        """A ready statement prepared before automatic save (no preparation mark, nothing saved)."""
        batch = self.create()
        with patch.object(queue_save, 'AUTO_SAVE_READY', False):
            self.advance(batch)
        with self.f.SessionLocal() as db:
            record = db.query(Item).filter(Item.batch_id == batch).one()
            self.assertEqual(record.status, 'ready')
            record.review_request = None
            db.commit()
            return batch, record.id

    def test_the_sweep_saves_the_backlog_as_system_and_only_once(self):
        batch, item_id = self.prepared_backlog()
        calls, real = [], queue_save.save_statements

        def spy(*args, **kwargs):
            calls.append(kwargs)
            return real(*args, **kwargs)
        with patch.object(queue_save, 'save_statements', spy), patch.object(queue_save, 'fully_reconciled', return_value=True):
            report = queue_save.sweep_backlog(self.f.SessionLocal)
            self.assertEqual((report['queued'], report['considered']), (1, 1))
            self.assertEqual((calls[0]['actor'], calls[0]['only_reconciled']), (queue_save.SYSTEM_ACTOR, True))
            self.assertEqual(queue_save.sweep_backlog(self.f.SessionLocal)['considered'], 0)  # no longer ready
        self.advance(batch)
        with self.f.SessionLocal() as db:
            item = db.get(Item, item_id)
            self.assertEqual((item.status, item.summary['import_actor']['name']), ('imported', 'System'))

    def test_edited_or_checked_statements_and_the_switches_are_respected(self):
        _, item_id = self.prepared_backlog()
        with patch.object(queue_save, 'fully_reconciled', return_value=True):
            with patch.object(queue_save, 'AUTO_SAVE_BACKLOG', False):
                self.assertEqual(queue_save.sweep_backlog(self.f.SessionLocal)['considered'], 0)
            with patch.object(queue_save, 'AUTO_SAVE_READY', False):
                self.assertEqual(queue_save.sweep_backlog(self.f.SessionLocal)['considered'], 0)
            with self.f.SessionLocal() as db:
                db.get(Item, item_id).review_request = dict(holder='Typed by the investigator')
                db.commit()
            report = queue_save.sweep_backlog(self.f.SessionLocal)
        self.assertEqual((report['considered'], report['queued']), (1, 0))
        with self.f.SessionLocal() as db:
            self.assertEqual(db.get(Item, item_id).status, 'ready')

    def test_a_statement_admission_holds_is_not_retried_until_it_changes(self):
        _, item_id = self.prepared_backlog()
        calls = []
        with patch.object(queue_save, 'fully_reconciled', side_effect=lambda *a: calls.append(1) or False):
            first = queue_save.sweep_backlog(self.f.SessionLocal)
            self.assertEqual((first['queued'], first['held']), (0, {'Has a check or an edit: left for you': 1}))
            self.assertEqual(queue_save.sweep_backlog(self.f.SessionLocal)['considered'], 0)
            with self.f.SessionLocal() as db:
                item = db.get(Item, item_id)
                item.summary = {**item.summary, 'touched': True}
                from datetime import datetime, timedelta, timezone
                item.updated_at = datetime.now(timezone.utc) + timedelta(seconds=5)  # SQLite: second resolution
                db.commit()
            self.assertEqual(queue_save.sweep_backlog(self.f.SessionLocal)['considered'], 1)
        self.assertEqual(len(calls), 2)

    def test_stale_stored_ready_is_refreshed_when_admission_holds_it(self):
        _, item_id = self.prepared_backlog()
        refreshed = []
        from services.financial import import_batches
        with patch.object(queue_save, '_not_ready_reason', return_value='No longer ready: open it in the queue'), \
                patch.object(import_batches, 'import_available', return_value=False), \
                patch.object(import_batches, 'refresh_readiness',
                             side_effect=lambda session, **kw: refreshed.append(kw['item_ids']) or dict(refreshed=1)):
            report = queue_save.sweep_backlog(self.f.SessionLocal)
        self.assertEqual((report['queued'], report['refreshed']), (0, 1))
        self.assertEqual(refreshed, [[item_id]])


class TurnOrderTests(Base):
    test_a_statement_in_two_batches_is_one_entry_and_leaves_once_saved = None
    test_a_statement_with_a_problem_is_queued_with_its_sentence_and_file_filter_applies = None

    def test_batches_holding_saves_get_the_first_turns(self):
        from datetime import timedelta
        older = self.create()
        with self.f.SessionLocal() as db:
            first = db.get(service.Batch, older)
            first.status = 'preparing'
            second = service.Batch(id=uuid4(), case_id=first.case_id, created_by=first.created_by, status='preparing',
                                   actor=dict(first.actor), files=[])
            db.add(second)
            db.flush()
            second.updated_at = first.updated_at + timedelta(minutes=1)
            newer = second.id
            db.commit()
            self.assertEqual(service.turn_batches(db), [older, newer])
            item = Item(id=uuid4(), batch_id=newer, file_id=self.f.file.id, statement_key='x', status='pending_import',
                        summary={})
            db.add(item)
            db.commit()
            self.assertEqual(service.turn_batches(db), [newer, older])
            self.assertEqual(service.turn_batches(db, limit=1), [newer])


class SupersededBatchTests(Base):
    test_a_statement_in_two_batches_is_one_entry_and_leaves_once_saved = None
    test_a_statement_with_a_problem_is_queued_with_its_sentence_and_file_filter_applies = None

    def flags(self):
        from services.financial.batch_supersession import superseded_batches
        with self.f.SessionLocal() as db:
            batches = list(db.query(service.Batch).filter(service.Batch.case_id == self.f.case.id))
            items = list(db.query(Item).filter(Item.batch_id.in_([b.id for b in batches])))
            return superseded_batches(db, self.f.case.id, batches, items)

    def test_an_older_batch_whose_statements_a_newer_batch_holds_is_hidden_not_deleted(self):
        newer = self.create(); self.advance(newer)
        older = self.older_copy_of(newer)
        self.assertEqual(self.flags(), {older: True})
        # Nothing is removed: both batches and their items remain.
        with self.f.SessionLocal() as db:
            self.assertEqual(db.query(service.Batch).count(), 2)
            self.assertEqual(db.query(Item).filter(Item.batch_id == older).count(), 1)

    def test_a_batch_still_preparing_or_with_unique_statements_stays(self):
        newer = self.create(); self.advance(newer)
        older = self.older_copy_of(newer)
        with self.f.SessionLocal() as db:
            db.get(service.Batch, older).status = 'preparing'
            db.commit()
        self.assertEqual(self.flags(), {})
        with self.f.SessionLocal() as db:
            db.get(service.Batch, older).status = 'review'
            # The older batch also holds a statement no newer batch has.
            record = db.query(Item).filter(Item.batch_id == older).first()
            db.add(Item(id=uuid4(), batch_id=older, file_id=record.file_id, statement_key='only-here',
                        status='attention', summary=dict(record.summary)))
            db.commit()
        self.assertEqual(self.flags(), {})

    def test_list_reports_superseded(self):
        newer = self.create(); self.advance(newer)
        self.older_copy_of(newer)
        from routers.financial_statement_import import list_financial_batches
        with self.f.SessionLocal() as db:
            listing = list_financial_batches(case_id=self.f.case.id, db=db)
        self.assertEqual(sorted(b['superseded'] for b in listing['batches']), [False, True])


class FilledDetailsTests(Base):
    """Confirmed proposals are filled (System) before saving; a System fill is not an investigator edit."""
    test_a_statement_in_two_batches_is_one_entry_and_leaves_once_saved = None
    test_a_statement_with_a_problem_is_queued_with_its_sentence_and_file_filter_applies = None
    PROPOSALS = dict(currency=dict(value='USD', confirmed=True, label="same account's 3 saved statements, all USD",
                                   field='currency'))

    def hold_for_currency(self, batch):
        with self.f.SessionLocal() as db:
            record = db.query(Item).filter(Item.batch_id == batch).one()
            self.ready_summary = {k: v for k, v in record.summary.items() if k != 'readiness'}
            summary = dict(self.ready_summary, can_import=False, problems=[CURRENCY], problem_count=1)
            record.summary, record.status, record.review_request = summary, 'attention', None
            db.commit()
            return record.id

    def fake_fill(self, item_id, name='System'):
        """Stands in for the details save (tested in test_bulk_statement_details): saves a review as `name`."""
        def fill(session, *, case_id, entries, apply=False, actor=None, owned_batch_id=None):
            self.fill_calls.append(dict(entries=entries, apply=apply, owned_batch_id=owned_batch_id))
            from postgres.models.evidence import EvidenceFile
            record = session.get(Item, item_id)
            file = session.get(EvidenceFile, record.file_id)
            request = service.initial_request(service.read_statement_import(session, case_id=case_id,
                evidence_file_id=record.file_id, currency=None, statement_id=record.statement_key or None))
            metadata = dict(file.metadata_ or {})
            metadata['financial_review_progress'] = {record.statement_key or '': dict(
                request=request, review_revision=_digest(request), saved_by=dict(user_id='None', name=name))}
            file.metadata_ = metadata
            record.review_request, record.status, record.summary = request, 'ready', dict(self.ready_summary)
            session.commit()
            return dict(statements=1, saved=1, failed=0, groups=[])
        return fill

    def setUp(self):
        super().setUp()
        self.fill_calls = []

    def test_preparation_fills_confirmed_details_then_saves_as_system(self):
        batch = self.create()
        with patch.object(queue_save, 'AUTO_SAVE_READY', False):
            self.advance(batch)
        item_id = self.hold_for_currency(batch)
        from services.financial import field_proposals
        with patch.object(field_proposals, 'propose', return_value=self.PROPOSALS), \
                patch.object(field_proposals, 'apply_confirmed_proposals', self.fake_fill(item_id)), \
                patch.object(queue_save, 'AUTO_SAVE_READY', True):
            with self.f.SessionLocal() as db:
                result = queue_save.auto_save_prepared(db, case_id=self.f.case.id, batch_id=batch,
                                                       file_id=self.f.file.id)
        self.assertEqual(self.fill_calls[0]['owned_batch_id'], batch)
        self.assertTrue(self.fill_calls[0]['apply'])
        self.assertEqual(result['queued'], 1, result)
        with self.f.SessionLocal() as db:
            self.assertEqual(db.get(Item, item_id).status, 'pending_import')

    def test_an_investigator_review_is_not_a_system_fill(self):
        batch = self.create()
        with patch.object(queue_save, 'AUTO_SAVE_READY', False):
            self.advance(batch)
        item_id = self.hold_for_currency(batch)
        from services.financial import field_proposals
        with patch.object(field_proposals, 'propose', return_value=self.PROPOSALS), \
                patch.object(field_proposals, 'apply_confirmed_proposals', self.fake_fill(item_id, name='Alex')), \
                patch.object(queue_save, 'AUTO_SAVE_READY', True):
            with self.f.SessionLocal() as db:
                result = queue_save.auto_save_prepared(db, case_id=self.f.case.id, batch_id=batch,
                                                       file_id=self.f.file.id)
        self.assertIsNone(result)  # nothing a System save may take
        with self.f.SessionLocal() as db:
            self.assertEqual(db.get(Item, item_id).status, 'ready')

    def test_queue_fill_returns_statements_now_ready(self):
        batch = self.create(); self.advance(batch)
        item_id = self.hold_for_currency(batch)
        entry = dict(id=str(item_id), batch_id=str(batch), file_id=str(self.f.file.id), statement_id=None,
                     proposals=self.PROPOSALS, bucket='filled')
        from services.financial import field_proposals
        with patch('services.financial.review_queue.case_review_queue',
                   return_value=dict(filled=[entry], items=[])), \
                patch.object(field_proposals, 'apply_confirmed_proposals', self.fake_fill(item_id)):
            with self.f.SessionLocal() as db:
                result = queue_save.fill_from_queue(db, case_id=self.f.case.id)
        self.assertEqual((result['filled'], result['ready_item_ids']), (1, [str(item_id)]))


class QueueCacheTests(Base):
    test_a_statement_in_two_batches_is_one_entry_and_leaves_once_saved = None
    test_a_statement_with_a_problem_is_queued_with_its_sentence_and_file_filter_applies = None

    def test_prewarm_rebuilds_only_recently_read_cases_whose_inputs_changed(self):
        from services.financial import review_queue as rq
        import sys
        import services.financial.statement_file_status  # noqa: F401
        register = sys.modules['services.financial.statement_file_status']
        rq._cache.clear(); rq._recent_reads.clear()
        fingerprint = [('a',)]
        builds = []
        real = rq._build

        def build(session, case_id):
            builds.append(case_id)
            return real(session, case_id)
        from services.financial import view_cache
        # No memo directory: asks cannot be kept, so prewarm builds here (the refresh-process path is tested below).
        with patch.object(register, 'status_fingerprint', side_effect=lambda *_: tuple(fingerprint)), \
                patch.object(rq, '_build', side_effect=build), patch.object(view_cache, '_memo_dir', return_value=None):
            with self.f.SessionLocal() as db:
                case_review_queue(db, case_id=self.f.case.id)          # an open: built and noted
            self.assertEqual(len(builds), 1)
            self.assertEqual(rq.prewarm(self.f.SessionLocal), [])      # unchanged: nothing rebuilt
            fingerprint.append(('b',))                                  # a write changed the inputs
            self.assertEqual(rq.prewarm(self.f.SessionLocal), [str(self.f.case.id)])
            with self.f.SessionLocal() as db:
                case_review_queue(db, case_id=self.f.case.id)          # the next open is a cache hit
            self.assertEqual(len(builds), 2)
            with patch.object(rq, 'PREWARM', False):
                fingerprint.append(('c',))
                self.assertEqual(rq.prewarm(self.f.SessionLocal), [])
            # Reads older than the window are forgotten.
            self.assertEqual(rq.prewarm(self.f.SessionLocal, now=10 ** 9), [])

    def _prewarm_after_a_write(self, *, memo=True, ask_state=None, saved=None, in_child=True):
        """Open the case (built, noted), change its inputs, run prewarm. Returns (prewarm result, builds, ask)."""
        import json
        import sys
        import tempfile
        import time as time_module
        from pathlib import Path
        from services.financial import review_queue as rq, view_cache, view_refresh
        import services.financial.statement_file_status  # noqa: F401
        register = sys.modules['services.financial.statement_file_status']
        rq._cache.clear(); rq._recent_reads.clear()
        fingerprint, builds, real = [('a',)], [], rq._build
        memo_dir = Path(tempfile.mkdtemp(prefix='rq-prewarm-'))
        self.addCleanup(__import__('shutil').rmtree, memo_dir, True)

        def build(session, case_id):
            builds.append(case_id)
            return real(session, case_id)
        key = str(self.f.case.id)
        with patch.object(register, 'status_fingerprint', side_effect=lambda *_: tuple(fingerprint)), \
                patch.object(rq, '_build', side_effect=build), \
                patch.object(rq, '_save_view'), \
                patch.object(rq, 'PREWARM_IN_CHILD', in_child), \
                patch.object(view_cache, '_memo_dir', return_value=memo_dir if memo else None), \
                patch.object(view_cache, 'code_identity', return_value='code-1'):
            with self.f.SessionLocal() as db:
                case_review_queue(db, case_id=self.f.case.id)
            fingerprint.append(('b',))
            if ask_state is not None:
                directory = view_refresh._wanted_dir(); directory.mkdir(parents=True)
                view_refresh._write(view_refresh._path(directory, rq._ask_key(key)),
                                    dict(key=list(rq._ask_key(key)), case_id=key, code='code-1',
                                         asked=time_module.time() - ask_state.get('age', 0),
                                         **({'failed': 1.0} if ask_state.get('failed') else {})))
            with patch.object(rq, '_load_saved_view', return_value=saved):
                result = rq.prewarm(self.f.SessionLocal)
            directory = view_refresh._wanted_dir()
            ask = view_refresh._read(view_refresh._path(directory, rq._ask_key(key))) if directory else None
        return result, builds, ask

    def test_prewarm_asks_the_refresh_process_instead_of_building_in_the_worker(self):
        result, builds, ask = self._prewarm_after_a_write()
        self.assertEqual(result, [])
        self.assertEqual(len(builds), 1)  # only the open; the rebuild is the child's
        self.assertEqual(ask['key'], ['review-queue', '{"case_id": "%s"}' % self.f.case.id])
        self.assertEqual(ask['case_id'], str(self.f.case.id))

    def test_prewarm_loads_a_current_saved_copy_without_building(self):
        view = dict(entries=[], failed=[], copy_files=[], set_aside=[], unread=0, as_of='x')
        result, builds, ask = self._prewarm_after_a_write(saved=view)
        self.assertEqual((result, len(builds), ask), ([str(self.f.case.id)], 1, None))
        from services.financial import review_queue as rq
        self.assertIs(rq._cache[str(self.f.case.id)][1], view)

    def test_prewarm_builds_here_when_the_ask_failed_or_is_past_the_limit_or_asks_cannot_be_kept(self):
        from services.financial import view_cache
        for state in (dict(ask_state={'failed': True}), dict(ask_state={'age': view_cache.UPDATING_MAX_SECONDS + 5}),
                      dict(memo=False), dict(in_child=False)):
            with self.subTest(**{k: str(v) for k, v in state.items()}):
                result, builds, _ = self._prewarm_after_a_write(**state)
                self.assertEqual((result, len(builds)), ([str(self.f.case.id)], 2))

    def test_prewarm_does_not_build_while_an_earlier_ask_is_live(self):
        result, builds, ask = self._prewarm_after_a_write(ask_state={'age': 30})
        self.assertEqual((result, len(builds)), ([], 1))
        self.assertNotIn('failed', ask)


def test_the_already_saved_check_reads_only_keys_not_whole_file_rows_or_summaries():
    """Whole evidence rows decoded every matching file's stored readings (49494305: +2.5 GB, 54 s; live backlog
    round peaks of 5.2 GB, 2026-10-30). The check selects the bytes key, the page identity, the statement key, the
    status and the saved document id, and nothing larger."""
    from types import SimpleNamespace
    from uuid import uuid4
    from postgres.models.evidence import EvidenceFile
    from postgres.models.financial_import_batches import FinancialImportBatchItem
    from services.financial import queue_save
    statements = []

    class Session:
        def execute(self, statement):
            statements.append(statement)
            return [('sha-a', {'identity': 'p1'}, 'k1', 'pending_import', None)]
    busy = queue_save._busy_scopes(Session(), uuid4(), {'sha-a'}, set(),
                                   lambda file: ('pages', 'r', file.metadata_.get('financial_page_identity', {}).get('identity')))
    assert busy == {('sha-a', 'k1'), (('pages', 'r', 'p1'), 'k1')}
    selected = statements[0].selected_columns
    assert len(selected) == 5
    for column in selected:
        assert column is not EvidenceFile.metadata_.expression and column is not FinancialImportBatchItem.summary.expression
        assert getattr(column, 'entity_namespace', None) is not EvidenceFile or getattr(column, 'key', '') != 'metadata'
    assert not any(getattr(c, 'name', None) in ('metadata', 'summary') for c in selected)
