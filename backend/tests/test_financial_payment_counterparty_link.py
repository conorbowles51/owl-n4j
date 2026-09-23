"""Synthetic case fixtures; no client evidence."""
import json
from uuid import UUID, uuid4
from sqlalchemy import select
from postgres.models.financial import FinancialAccount, FinancialTransaction
from services.financial.transaction_query import to_view
from services.financial.counterparty_parties import counterparty_parties
from services.financial.payment_edits import PaymentEditRequest, preview_payment_edits, save_payment_edits
from services.financial.payment_labels import PaymentLabelsError
from tests.test_financial_payment_edits import PaymentEditTests
from tests.test_financial_manual_statement_payment import ManualPaymentTests


class LinkedPaymentTests(PaymentEditTests):
    def account(self):
        account = self.f.db.scalar(select(FinancialAccount).where(FinancialAccount.case_id == self.f.case.id))
        return json.dumps(dict(kind='account', id=str(account.id)))

    def test_mixed_direction_bulk_links_have_typed_identity_source_side_and_history(self):
        request = self.request(counterparty_link=self.account())
        proposal = preview_payment_edits(self.f.db, case_id=self.f.case.id, request=request)
        self.assertTrue(all('counterparty_link' in item['after'] for item in proposal['examples']))
        self.save(request)
        for id in self.ids:
            row = self.f.db.get(FinancialTransaction, id)
            view = to_view(row, account=row.account)
            self.assertEqual(view.counterparty_link['kind'], 'account')
            self.assertEqual(view.counterparty_link['label'], view.from_name if row.direction == 'credit' else view.to_name)
        state = counterparty_parties(self.f.db, case_id=self.f.case.id)
        self.assertTrue(all(r['account'] for r in state['readings']))
        self.assertTrue(all(r['party'] is None for r in state['readings']))

    def test_direction_correction_and_clear_keep_identity_auditable(self):
        self.save(self.request(ids=self.ids[:1], counterparty_link=self.account()))
        original = self.f.db.get(FinancialTransaction, self.ids[0])
        direction = 'debit' if original.direction == 'credit' else 'credit'
        result = self.save(self.request(ids=self.ids[:1], direction=direction))
        id = UUID(result['replacements'][0]['id'])
        row = self.f.db.get(FinancialTransaction, id)
        view = to_view(row, account=row.account)
        self.assertEqual(view.counterparty_link['label'], view.from_name if direction == 'credit' else view.to_name)
        self.assertTrue(next(r for r in counterparty_parties(self.f.db, case_id=self.f.case.id)['readings'] if r['transaction_id'] == str(id))['account'])
        self.save(self.request(ids=[id], counterparty_link=''))
        self.assertIsNone(to_view(row, account=row.account).counterparty_link)
        self.assertIsNone(next(r for r in counterparty_parties(self.f.db, case_id=self.f.case.id)['readings'] if r['transaction_id'] == str(id))['account'])

    def test_foreign_identity_refuses_entire_edit(self):
        before = [to_view(self.f.db.get(FinancialTransaction, id)).to_json() for id in self.ids]
        with self.assertRaisesRegex(PaymentLabelsError, 'this case'):
            self.save(self.request(amount='21.45', counterparty_link=json.dumps(dict(kind='account', id=str(uuid4())))))
        self.assertEqual(before, [to_view(self.f.db.get(FinancialTransaction, id)).to_json() for id in self.ids])


class LinkedManualPaymentTests(ManualPaymentTests):
    def test_append_identity_and_receipt_are_atomic_and_reopen(self):
        request = self.request()
        with self.f.SessionLocal() as db:
            account = db.scalar(select(FinancialAccount).where(FinancialAccount.case_id == self.f.case.id))
            request['row']['counterparty_link'] = dict(kind='account', id=str(account.id))
        result = self.save(request)
        self.assertEqual(result['transaction_id'], self.save(request)['transaction_id'])
        with self.f.SessionLocal() as db:
            row = db.get(FinancialTransaction, UUID(result['transaction_id']))
            self.assertEqual(row.counterparty_raw, 'Synthetic supplier')
            self.assertEqual(to_view(row, account=row.account).counterparty_link['id'], str(account.id))
            state = counterparty_parties(db, case_id=self.f.case.id)
            self.assertEqual(len([h for h in state['history'] if h['transaction_id'] == result['transaction_id']]), 1)
