"""Work a model did for a person is recorded and shown as the model's until a person confirms it."""
import copy
import unittest
from uuid import UUID

from sqlalchemy import select

from postgres.models.financial import FinancialTransaction
from services.financial.decisions import Actor, DecisionError
from services.financial.model_work import (ModelWorkError, actor_from_record, actor_record, describe, is_model,
                                           model_actor, require_person)
from services.financial.payment_labels import (ConfirmPaymentLabelsRequest, PaymentLabelsError, PaymentLabelsRequest,
                                               RemovePaymentLabelsRequest, confirm_payment_labels,
                                               payment_label_view, remove_payment_labels, update_payment_labels)
from services.financial.transaction_query import to_view


def claude(citation=None):
    return model_actor(for_name='Neil Byrne', for_email='neil@example.test', model_id='claude-opus-5-5',
                       citation=citation or dict(page=3, file='statement.pdf'), how='read from the page image')


class ModelActorTests(unittest.TestCase):
    def test_model_actor_names_the_model_and_keeps_the_person_it_worked_for(self):
        actor = claude()
        self.assertEqual(actor.name, 'Claude (for Neil Byrne)')
        self.assertTrue(is_model(actor))
        self.assertEqual(actor.origin['for']['name'], 'Neil Byrne')
        self.assertEqual(actor.origin['citation'], dict(page=3, file='statement.pdf'))
        self.assertEqual(describe(actor.origin), 'Read by Claude · not confirmed')

    def test_origin_round_trips_through_the_stored_record(self):
        actor = claude()
        again = actor_from_record(actor_record(actor))
        self.assertEqual((again.name, again.email, again.origin), (actor.name, actor.email, actor.origin))
        person = actor_from_record(dict(name='Alex', email='alex@example.test', user_id=None))
        self.assertIsNone(person.origin)
        self.assertNotIn('origin', actor_record(person))

    def test_origin_is_a_field_never_read_from_the_name(self):
        legacy = Actor(name='Neil Byrne (via Claude)', email='neil@example.test')
        self.assertFalse(is_model(legacy))
        with self.assertRaises(DecisionError):
            Actor(name='x', email='y@z', origin=dict(kind='person'))

    def test_only_a_person_confirms(self):
        with self.assertRaises(ModelWorkError) as caught:
            require_person(claude())
        self.assertEqual(caught.exception.status_code, 403)
        require_person(Actor(name='Alex', email='alex@example.test'))


class ModelLabelTests(unittest.TestCase):
    def setUp(self):
        from tests.test_financial_statement_import import StatementImportTests
        self.f = StatementImportTests()
        self.f.setUp()
        self.receipt = self.f.confirm()
        self.rows = list(self.f.db.scalars(select(FinancialTransaction).where(
            FinancialTransaction.source_document_id == UUID(self.receipt['source_document_id']))
            .order_by(FinancialTransaction.id)))
        self.row = self.rows[0]
        self.side = 'from_name' if self.row.direction == 'credit' else 'to_name'

    def tearDown(self):
        self.f.tearDown()

    def targets(self, rows):
        return [dict(id=row.id, version=(row.metadata_ or {}).get('investigation_labels', {}).get('version', 0))
                for row in rows]

    def save(self, rows, actor, reason=None, **changes):
        return update_payment_labels(self.f.db, case_id=self.f.case.id, actor=actor, reason=reason,
                                     request=PaymentLabelsRequest(transactions=self.targets(rows), **changes))

    def confirm(self, rows, actor):
        return confirm_payment_labels(self.f.db, case_id=self.f.case.id, actor=actor,
                                      request=ConfirmPaymentLabelsRequest(transactions=self.targets(rows)))

    def source(self, row):
        self.f.db.expire_all()
        row = self.f.db.get(FinancialTransaction, row.id)
        return row, payment_label_view(row, row.account)

    def test_model_reading_is_stored_with_its_origin_and_shown_as_the_models(self):
        before = (self.row.amount_minor, self.row.description, copy.deepcopy(self.row.provenance), self.row.proof_class)
        self.save([self.row], claude(), counterparty_name='ACME LTD')
        row, view = self.source(self.row)
        self.assertEqual(view[self.side], 'ACME LTD')
        source = view['label_sources'][self.side]
        self.assertEqual(source['source'], 'model_reading')
        self.assertEqual(source['label'], 'Read by Claude · not confirmed')
        self.assertIn('Read from statement.pdf, page 3', source['explanation'])
        self.assertEqual(source['origin']['citation']['page'], 3)
        entry = row.metadata_['investigation_label_history'][-1]
        self.assertEqual(entry['actor_name'], 'Claude (for Neil Byrne)')
        self.assertEqual(entry['origin']['kind'], 'model')
        # Nothing else about the payment changes, proof class included.
        self.assertEqual(before, (row.amount_minor, row.description, row.provenance, row.proof_class))
        self.assertEqual(to_view(row, account=row.account).to_json()['label_sources'][self.side]['source'],
                         'model_reading')

    def test_a_persons_name_outranks_a_model_reading(self):
        self.save([self.row], self.f.actor, counterparty_name='Person Name')
        with self.assertRaises(PaymentLabelsError) as caught:
            self.save([self.row], claude(), counterparty_name='Model Name')
        self.assertEqual(caught.exception.status_code, 409)
        _, view = self.source(self.row)
        self.assertEqual((view[self.side], view['label_sources'][self.side]['source']), ('Person Name', 'investigator'))

    def test_a_person_corrects_a_model_reading_and_the_reading_stays_in_history(self):
        self.save([self.row], claude(), counterparty_name='ACME LTD')
        self.row = self.f.db.get(FinancialTransaction, self.row.id)
        self.save([self.row], self.f.actor, counterparty_name='ACME LIMITED')
        row, view = self.source(self.row)
        self.assertEqual((view[self.side], view['label_sources'][self.side]['source']), ('ACME LIMITED', 'investigator'))
        history = row.metadata_['investigation_label_history']
        self.assertEqual([e['actor_name'] for e in history], ['Claude (for Neil Byrne)', self.f.actor.name])
        # Undoing the correction puts the model's reading back, still as the model's.
        remove_payment_labels(self.f.db, case_id=self.f.case.id, actor=self.f.actor,
                              request=RemovePaymentLabelsRequest(transactions=self.targets([row]),
                                                                 fields=['counterparty_name']))
        _, view = self.source(self.row)
        self.assertEqual((view[self.side], view['label_sources'][self.side]['source']), ('ACME LTD', 'model_reading'))

    def test_confirm_makes_the_person_the_actor_without_changing_the_value(self):
        self.save([self.row], claude(), counterparty_name='ACME LTD')
        row = self.f.db.get(FinancialTransaction, self.row.id)
        with self.assertRaises(PaymentLabelsError) as caught:
            self.confirm([row], claude())
        self.assertEqual(caught.exception.status_code, 403)
        result = self.confirm([row], self.f.actor)
        self.assertEqual((result['confirmed'], result['skipped']), (1, 0))
        row, view = self.source(self.row)
        source = view['label_sources'][self.side]
        self.assertEqual((view[self.side], source['source']), ('ACME LTD', 'investigator'))
        self.assertTrue(source['explanation'].startswith(f'Confirmed by {self.f.actor.name} from the statement on '))
        self.assertIn('Read first by Claude', source['explanation'])
        history = row.metadata_['investigation_label_history']
        self.assertEqual(history[0]['origin']['kind'], 'model')
        self.assertEqual(history[-1]['confirmed'], [self.side])
        # Confirming again finds nothing unconfirmed.
        self.assertEqual(self.confirm([row], self.f.actor)['skipped'], 1)

    def test_a_model_reads_names_only(self):
        for changes in (dict(category='Travel'), dict(counterparty_name='')):
            with self.assertRaises(PaymentLabelsError):
                self.save([self.row], claude(), **changes)
        with self.assertRaises(PaymentLabelsError) as caught:
            remove_payment_labels(self.f.db, case_id=self.f.case.id, actor=claude(),
                                  request=RemovePaymentLabelsRequest(transactions=self.targets([self.row]),
                                                                     fields=['counterparty_name']))
        self.assertEqual(caught.exception.status_code, 403)


if __name__ == '__main__':
    unittest.main()
