"""A person's skip of a file's statement applies to that statement in the case's other batches (fin-lessons).

Shape it comes from: Alexandra skipped "03 FACTUAL INGENIEROS PAGO COT COLOCACION DE PISO OFICINA 701.pdf" (a
transfer receipt, "not a bank statement") in one batch, and the same file came back for review in a later batch;
likewise "001274-001276 Application.Payments.pdf" ("Not a fin statement").
"""
from datetime import timedelta
from unittest import TestCase
from unittest import mock
from uuid import uuid4

from sqlalchemy import select

from postgres.models.financial_import_batches import FinancialImportBatch as Batch, FinancialImportBatchItem as Item
from services.financial import import_batches as service
from services.financial.model_work import model_actor
from tests import test_financial_import_batches as fixtures


class CarryPersonSkipTests(TestCase):
    def setUp(self):
        self.batches = fixtures.BatchImportTests()
        self.batches.setUp()
        self.f = self.batches.f
        self.first = self.batches.create()
        self.batches.advance(self.first)

    def tearDown(self):
        self.batches.tearDown()

    def second_batch(self):
        """Another batch of the case listing the same file, prepared through the real worker."""
        with self.f.SessionLocal() as db:
            first = db.get(Batch, self.first)
            batch_id = uuid4()
            db.add(Batch(id=batch_id, case_id=first.case_id, created_by=first.created_by, status='preparing',
                         created_at=first.created_at + timedelta(seconds=5), actor=first.actor, files=[{**f, 'status': 'waiting'} for f in first.files]))
            db.commit()
        for _ in range(5):  # the worker can yield a turn before preparing; it finishes on a later one
            self.batches.advance(batch_id)
            if self.item(batch_id) is not None:
                break
        self.assertIsNotNone(self.item(batch_id))
        return batch_id

    def item(self, batch_id):
        with self.f.SessionLocal() as db:
            return db.scalar(select(Item).where(Item.batch_id == batch_id))

    def skip(self, batch_id, actor, reason='not a bank statement'):
        item = self.item(batch_id)
        with self.f.SessionLocal() as db:
            revision = service._digest(dict(status=item.status, request=item.review_request,
                                            decision=item.summary.get('import_decision')))
            return service.leave_unimported(db, case_id=self.f.case.id, batch_id=batch_id, item_id=item.id,
                                            action='skip', reason=reason, expected_revision=revision, actor=actor)

    def test_a_person_skip_reaches_the_same_statement_waiting_in_another_batch(self):
        second = self.second_batch()
        self.assertIn(self.item(second).status, ('ready', 'attention'))
        self.skip(self.first, self.f.actor)
        carried = self.item(second)
        self.assertEqual(carried.status, 'skipped')
        decision = carried.summary['import_decision']
        self.assertEqual(decision['reason'], 'not a bank statement')
        self.assertEqual(decision['actor']['name'], self.f.actor.name)
        self.assertEqual(decision['carried_from']['batch_id'], str(self.first))

    def test_a_batch_prepared_after_the_skip_starts_skipped(self):
        self.skip(self.first, self.f.actor, reason='Not a fin statement')
        second = self.second_batch()
        carried = self.item(second)
        self.assertEqual(carried.status, 'skipped')
        self.assertEqual(carried.summary['import_decision']['reason'], 'Not a fin statement')
        self.assertEqual(carried.summary['import_decision']['carried_from']['item_id'], str(self.item(self.first).id))

    def test_a_carried_skip_can_be_restored(self):
        second = self.second_batch()
        self.skip(self.first, self.f.actor)
        item = self.item(second)
        with self.f.SessionLocal() as db:
            revision = service._digest(dict(status=item.status, request=item.review_request,
                                            decision=item.summary.get('import_decision')))
            service.leave_unimported(db, case_id=self.f.case.id, batch_id=second, item_id=item.id, action='restore',
                                     reason='It is a statement after all', expected_revision=revision, actor=self.f.actor)
        self.assertIn(self.item(second).status, ('ready', 'attention'))
        self.assertEqual(self.item(self.first).status, 'skipped')

    def test_a_model_skip_is_not_carried(self):
        second = self.second_batch()
        model = model_actor(for_name=self.f.actor.name, for_email=self.f.actor.email, for_user_id=self.f.actor.user_id)
        self.skip(self.first, model)
        self.assertIn(self.item(second).status, ('ready', 'attention'))

    def test_the_backlog_carry_matches_the_live_rule_and_the_switch_turns_it_off(self):
        second = self.second_batch()
        with mock.patch.object(service, 'CARRY_PERSON_SKIP', False):
            self.skip(self.first, self.f.actor)
        self.assertIn(self.item(second).status, ('ready', 'attention'))
        with self.f.SessionLocal() as db:
            dry = service.carry_person_skips(db, self.f.case.id)
        self.assertEqual([c['item_id'] for c in dry], [str(self.item(second).id)])
        self.assertIn(self.item(second).status, ('ready', 'attention'))
        with self.f.SessionLocal() as db:
            service.carry_person_skips(db, self.f.case.id, apply=True)
        self.assertEqual(self.item(second).status, 'skipped')
        with self.f.SessionLocal() as db:
            self.assertEqual(service.carry_person_skips(db, self.f.case.id), [])

    def test_a_system_rule_skip_is_not_carried(self):
        from services.financial.decisions import Actor
        second = self.second_batch()
        self.skip(self.first, Actor(name='System', email='system@loupe.local'), reason='Receipt settled')
        self.assertIn(self.item(second).status, ('ready', 'attention'))

    def test_restoring_the_original_skip_restores_its_carried_copies(self):
        second = self.second_batch()
        self.skip(self.first, self.f.actor)
        self.assertEqual(self.item(second).status, 'skipped')
        item = self.item(self.first)
        with self.f.SessionLocal() as db:
            revision = service._digest(dict(status=item.status, request=item.review_request,
                                            decision=item.summary.get('import_decision')))
            service.leave_unimported(db, case_id=self.f.case.id, batch_id=self.first, item_id=item.id, action='restore',
                                     reason='Skipped by mistake', expected_revision=revision, actor=self.f.actor)
        restored = self.item(second)
        self.assertIn(restored.status, ('ready', 'attention'))
        self.assertEqual(restored.summary['import_decision']['action'], 'restore')
        self.assertEqual([d['action'] for d in restored.summary['import_decision_history']], ['skip', 'restore'])
