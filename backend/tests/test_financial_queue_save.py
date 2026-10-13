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
