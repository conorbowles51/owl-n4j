"""Synthetic case fixtures; no client evidence."""
import json
from copy import deepcopy
from uuid import UUID, uuid4
from sqlalchemy import select
from postgres.models.financial import FinancialAccount, FinancialSourceDocument, FinancialTransaction
from services.financial.account_history import account_history
from services.financial.imported_records import CompleteImportedRecord, complete_record, imported_records
from services.financial.pdf_candidates import PdfMappingError
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
        request['row']['date'] = '2023-12-31'
        with self.f.SessionLocal() as db:
            account = db.scalar(select(FinancialAccount).where(FinancialAccount.case_id == self.f.case.id))
            request['row']['counterparty_link'] = dict(kind='account', id=str(account.id))
            original = deepcopy(db.get(FinancialSourceDocument, self.source).metadata_['statement_import_request'])
            existing = {row.id: row.ref_id for row in db.scalars(select(FinancialTransaction))}
        # A new debit does not reconcile with this already-balanced statement,
        # and an unplaced addition cannot bypass the printed running controls.
        pending = self.save(request)
        self.assertTrue(pending['pending_reconciliation'])
        self.assertIsNone(pending['transaction_id'])
        self.assertFalse(pending['created'])
        self.assertIn('manual_placement', {item['kind'] for item in pending['blockers']})
        replay = self.save(request)
        self.assertEqual(replay['transaction_id'], pending['transaction_id'])
        self.assertTrue(replay['pending_reconciliation'])
        self.assertFalse(replay['created'])
        with self.f.SessionLocal() as db:
            self.assertEqual({row.id: row.ref_id for row in db.scalars(select(FinancialTransaction))}, existing)
            retained = imported_records(db, case_id=self.f.case.id)['records'][0]
            self.assertEqual(retained['fields']['counterparty_link'], request['row']['counterparty_link'])
            self.assertEqual(counterparty_parties(db, case_id=self.f.case.id)['history'], [])
            self.assertEqual(len(db.get(FinancialSourceDocument, self.source).metadata_['statement_manual_additions']), 1)

        last_printed = next(row['id'] for row in reversed(self.f.preview()['rows']) if not row['excluded'])
        anchor = dict(relation='after', row_id=last_printed)
        corrected = CompleteImportedRecord(row={**retained['fields'], 'source_order_anchor': anchor},
                                          version=retained['version'], currency='EUR')
        result = complete_record(session_factory=self.f.SessionLocal, case_id=self.f.case.id,
            source_id=self.source, request=corrected, actor=self.f.actor)
        self.assertTrue(result['pending_reconciliation'])
        self.assertNotIn('manual_placement', {item['kind'] for item in result['blockers']})
        self.assertIn('arithmetic', {item['kind'] for item in result['blockers']})
        with self.f.SessionLocal() as db:
            self.assertEqual({row.id: row.ref_id for row in db.scalars(select(FinancialTransaction))}, existing)
            self.assertEqual(counterparty_parties(db, case_id=self.f.case.id)['history'], [])

        # Explicitly positioned offsetting payments complete the statement;
        # its two retained additions and the first one's link are saved together.
        offset = self.request()
        offset['row'].update(date='2023-12-31', direction='credit', source_order_anchor=anchor,
                             description='Synthetic offsetting payment')
        completed = self.save(offset)
        self.assertFalse(completed['pending_reconciliation'])
        self.assertTrue(completed['created'])
        result = self.save(request)  # The original lost-response receipt now resolves to its saved payment.
        self.assertFalse(result['pending_reconciliation'])
        self.assertFalse(result['created'])
        self.assertEqual(result['transaction_id'], self.save(request)['transaction_id'])
        self.assertEqual(completed['transaction_id'], self.save(offset)['transaction_id'])
        self.assertFalse(self.save(offset)['created'])
        with self.f.SessionLocal() as db:
            row = db.get(FinancialTransaction, UUID(result['transaction_id']))
            self.assertEqual(row.counterparty_raw, 'Synthetic supplier')
            view = to_view(row, account=row.account)
            self.assertEqual(view.counterparty_link['id'], str(account.id))
            self.assertEqual(view.to_name, view.counterparty_link['label'])
            self.assertEqual(row.provenance['statement_import_review']['source_order_anchor'], anchor)
            state = counterparty_parties(db, case_id=self.f.case.id)
            self.assertEqual(len([h for h in state['history'] if h['transaction_id'] == result['transaction_id']]), 1)
            self.assertEqual(next(r for r in state['readings'] if r['transaction_id'] == result['transaction_id'])['account']['id'], str(account.id))
            all_rows = list(db.scalars(select(FinancialTransaction)))
            self.assertEqual(len(all_rows), len(existing) + 2)
            self.assertEqual({row.id: row.ref_id for row in all_rows if row.id in existing}, existing)
            self.assertEqual(imported_records(db, case_id=self.f.case.id)['records'], [])
            self.assertEqual(db.get(FinancialSourceDocument, self.source).metadata_['statement_import_request'], original)
            self.assertEqual(account_history(db, case_id=self.f.case.id)['groups'][0]['periods'][0]['status'], 'reconciled')

    def test_unavailable_manual_identity_does_not_save_partial_addition_or_link(self):
        request = self.request()
        request['row']['counterparty_link'] = dict(kind='account', id=str(uuid4()))
        with self.f.SessionLocal() as db:
            metadata = deepcopy(db.get(FinancialSourceDocument, self.source).metadata_)
            rows = {row.id for row in db.scalars(select(FinancialTransaction))}
        with self.assertRaisesRegex(PdfMappingError, 'no longer available in this case'):
            self.save(request)
        with self.f.SessionLocal() as db:
            self.assertEqual(db.get(FinancialSourceDocument, self.source).metadata_, metadata)
            self.assertEqual({row.id for row in db.scalars(select(FinancialTransaction))}, rows)
            self.assertEqual(counterparty_parties(db, case_id=self.f.case.id)['history'], [])
