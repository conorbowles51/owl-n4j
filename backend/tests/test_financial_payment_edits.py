import copy
import unittest
from uuid import UUID, uuid4
from unittest.mock import patch
from sqlalchemy import select
from postgres.models.financial import FinancialTransaction
from services.financial.payment_edits import PaymentEditRequest, preview_payment_edits, save_payment_edits
from services.financial.payment_labels import PaymentLabelsError
from services.financial.transaction_query import to_view, list_transactions
from services.financial.working_totals import working_ledger_summary

class PaymentEditTests(unittest.TestCase):
    def setUp(self):
        from tests.test_financial_statement_import import StatementImportTests
        self.f = StatementImportTests(); self.f.setUp(); self.receipt = self.f.confirm()
        from postgres.models.financial_category import FinancialCategory
        FinancialCategory.__table__.create(self.f.db.get_bind(), checkfirst=True)
        self.ids = list(self.f.db.scalars(select(FinancialTransaction.id).where(FinancialTransaction.case_id == self.f.case.id)))
    def tearDown(self): self.f.tearDown()
    def request(self, ids=None, **changes):
        rows=[self.f.db.get(FinancialTransaction, id) for id in (ids or self.ids)]
        return PaymentEditRequest(transactions=[dict(id=row.id, version=to_view(row).label_version) for row in rows], changes=changes)
    def save(self, request):
        proposal=preview_payment_edits(self.f.db, case_id=self.f.case.id, request=request)
        request.expected_revision=proposal['revision']
        return save_payment_edits(self.f.db, case_id=self.f.case.id, request=request, actor=self.f.actor)
    def test_bulk_names_category_amount_and_dates_preserve_source_and_refresh_totals(self):
        original=self.f.db.get(FinancialTransaction, self.ids[0]); before=copy.deepcopy((original.amount_minor, original.description, original.provenance))
        result=self.save(self.request(ids=self.ids[:2], amount='123.45', from_name='Named sender', to_name='Named recipient', category='Case review', transaction_date='2021-02-12', description='Reviewed transfer', running_balance='-10.05'))
        self.f.db.expire_all()
        self.assertEqual(result['updated'],2)
        self.assertEqual(len(list_transactions(self.f.db,self.f.case.id)),len(self.ids))
        for replacement in result['replacements']:
            row=self.f.db.get(FinancialTransaction,UUID(replacement['id'])); view=to_view(row,account=row.account)
            self.assertEqual((row.amount_minor,row.running_balance_minor,view.from_name,view.to_name,view.category),(12345,-1005,'Named sender','Named recipient','Case review'))
            old=self.f.db.get(FinancialTransaction,UUID(replacement['previous_id']))
            self.assertEqual(old.ledger_status,'superseded')
        old=self.f.db.get(FinancialTransaction,self.ids[0])
        self.assertEqual((old.amount_minor,old.description,old.provenance),before)
        summary=working_ledger_summary(self.f.db,case_id=self.f.case.id)
        self.assertTrue(summary['available'])
    def test_bulk_category_does_not_change_any_other_fields(self):
        before=[to_view(self.f.db.get(FinancialTransaction,id)).to_json() for id in self.ids]
        self.save(self.request(category='Reviewed'))
        self.f.db.expire_all()
        for prior,id in zip(before,self.ids):
            now=to_view(self.f.db.get(FinancialTransaction,id)).to_json()
            for key in ('amount_minor','direction','description','from_name','to_name','transaction_date','running_balance_minor'): self.assertEqual(now[key],prior[key])
            self.assertEqual(now['category'],'Reviewed')
    def test_failure_on_second_correction_rolls_back_first_and_labels(self):
        from services.financial.corrections import correct_transaction
        calls=0
        def writer(*args,**kwargs):
            nonlocal calls
            calls+=1
            if calls==2: raise RuntimeError('write failed')
            return correct_transaction(*args,**kwargs)
        request=self.request(ids=self.ids[:2],amount='123.45',category='Should not save')
        proposal=preview_payment_edits(self.f.db,case_id=self.f.case.id,request=request);request.expected_revision=proposal['revision']
        with patch('services.financial.payment_edits.correct_transaction',side_effect=writer), self.assertRaises(RuntimeError):
            save_payment_edits(self.f.db,case_id=self.f.case.id,request=request,actor=self.f.actor)
        self.f.db.expire_all()
        self.assertEqual(len(list(self.f.db.scalars(select(FinancialTransaction)))),len(self.ids))
        self.assertTrue(all(self.f.db.get(FinancialTransaction,id).ledger_status=='admitted' for id in self.ids))
    def test_stale_foreign_and_mixed_currency_changes_are_refused(self):
        request=self.request(amount='22.05');proposal=preview_payment_edits(self.f.db,case_id=self.f.case.id,request=request)
        self.save(self.request(ids=self.ids[:1],category='Changed elsewhere'))
        request.expected_revision=proposal['revision']
        with self.assertRaisesRegex(PaymentLabelsError,'Someone edited'):
            save_payment_edits(self.f.db,case_id=self.f.case.id,request=request,actor=self.f.actor)
        foreign=PaymentEditRequest(transactions=[dict(id=uuid4(),version=0)],changes={'category':'Wrong'})
        with self.assertRaises(PaymentLabelsError): preview_payment_edits(self.f.db,case_id=self.f.case.id,request=foreign)
        row=self.f.db.get(FinancialTransaction,self.ids[1]);row.currency='JPY';self.f.db.commit()
        with self.assertRaisesRegex(PaymentLabelsError,'one currency'): preview_payment_edits(self.f.db,case_id=self.f.case.id,request=self.request(amount='22.05'))
