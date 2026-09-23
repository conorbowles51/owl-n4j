from datetime import date
from uuid import UUID, uuid4
from sqlalchemy import select
from postgres.models.enums import TransactionDirection
from postgres.models.financial_money_trails import FinancialMoneyTrail
from services.financial.account_parties import AccountPartyRequest, account_parties, set_account_party
from services.financial.money_trails import TrailRequest, TrailError, preview_trail, save_trail, list_trails, remove_trail
from tests.test_financial_duplicates import DuplicateTestCase


class MoneyTrailTests(DuplicateTestCase):
    def setUp(self):
        super().setUp()
        FinancialMoneyTrail.__table__.create(self.engine)
        self.second = self._account(self.case.id, identity_key='example-bank-222222')
        self.db.add(self.second); self.db.commit()
        self.doc_a = self.make_document()
        self.doc_b = self.make_document()
        self.period_a = self.make_period(self.doc_a)
        self.period_b = self.make_period(self.doc_b, account=self.second)
        self.debit = self.add_row(self.period_a, self.doc_a, amount=500000, direction=TransactionDirection.debit)
        self.credit = self.add_row(self.period_b, self.doc_b, account=self.second, amount=500000)
        self.supplier = self.add_row(self.period_b, self.doc_b, account=self.second, amount=500000, direction=TransactionDirection.debit)
        self.supplier.description = 'Water supplier'
        self.db.commit()

    def pair(self, **changes):
        return TrailRequest.model_validate(dict(id=uuid4(), kind='transfer', debit_id=self.debit.id,
            credit_id=self.credit.id, reason='Both statement references checked', **changes))

    def save(self, request):
        preview = preview_trail(self.db, case_id=self.case.id, request=request)
        return save_trail(self.db, case_id=self.case.id, request=request.model_copy(update={
            'expected_source_revision':preview['source_revision']}), actor=self.actor)

    def assign_owner(self):
        state = account_parties(self.db, case_id=self.case.id)
        return set_account_party(self.db, case_id=self.case.id, request=AccountPartyRequest(
            expected_revision=state['revision'], account_ids=[self.account.id,self.second.id],
            new_party_name='Example business', relationship={'role':'holder'}, reason='Reviewed corporate records'), actor=self.actor)

    def test_same_owner_transfer_then_supplier_allocation_reopens_and_retries_once(self):
        self.assign_owner()
        request = self.pair()
        saved = self.save(request)
        self.assertTrue(saved['details']['internal_transfer'])
        self.assertEqual(saved['status'], 'current')
        again = self.save(request)
        self.assertEqual(saved['id'], again['id'])
        self.assertEqual(again['revision'], 1)
        allocation = TrailRequest(id=uuid4(),kind='allocation',credit_id=self.credit.id,
            payments=[{'transaction_id':self.supplier.id,'amount_minor':'500000'}],reason='Manual attribution; both sources and account sequence reviewed')
        onward = self.save(allocation)
        self.assertEqual(onward['details']['receipt_unallocated_minor'],'0')
        self.db.expire_all()
        reopened = list_trails(self.db,case_id=self.case.id)['trails']
        self.assertEqual({r['kind'] for r in reopened},{'transfer','allocation'})
        self.assertTrue(all(r['status']=='current' for r in reopened))
        self.assertEqual(self.debit.amount_minor,500000)
        self.assertEqual(self.credit.amount_minor,500000)
        self.assertEqual(self.supplier.amount_minor,500000)

    def test_pairing_one_posting_twice_is_refused_but_remove_retains_history(self):
        saved = self.save(self.pair())
        with self.assertRaisesRegex(TrailError,'already linked'):
            self.save(self.pair())
        removed = remove_trail(self.db,case_id=self.case.id,id=UUID(saved['id']),expected_revision=1,reason='Wrong counterpart selected',actor=self.actor)
        self.assertFalse(removed['active'])
        self.assertEqual(len(removed['history']),2)
        self.assertEqual(removed['history'][0]['after']['payments'][0]['key'],str(self.debit.id))
        self.assertTrue(self.save(self.pair())['active'])

    def test_timeline_combines_transfer_entries_but_keeps_supplier_event_and_prior_copies(self):
        from postgres.models.timeline_entry import TimelineEntry
        from services.timeline_entries import TimelineAddition, preview_addition, save_addition, list_entries
        TimelineEntry.__table__.create(self.engine)
        saved = self.save(self.pair())
        def add(kind, ids):
            request = TimelineAddition(source_kind=kind,source_ids=ids)
            request.expected_revision = preview_addition(self.db,case_id=self.case.id,request=request)['revision']
            return save_addition(self.db,case_id=self.case.id,request=request,actor=self.actor.email)
        first = add('transaction',[self.debit.id,self.credit.id,self.supplier.id])
        self.assertEqual(first['added'],3)
        transfer = add('money_trail',[UUID(saved['id'])])
        self.assertEqual(transfer['added'],1)
        self.assertEqual(add('money_trail',[UUID(saved['id'])])['already_added'],1)
        events = list_entries(self.db,case_id=self.case.id)
        self.assertEqual(len(events),2)
        self.assertEqual({e['type'] for e in events},{'Transfer','Transaction'})
        movement = next(e for e in events if e['type']=='Transfer')
        self.assertEqual(len(movement['transfer_posting_roots']),2)
        self.assertEqual(len(movement['source_references']),2)
        self.assertEqual(add('transaction',[self.debit.id])['event_keys'],transfer['event_keys'])
        self.assertEqual(len(list_entries(self.db,case_id=self.case.id,event_keys=first['event_keys'])),3)
        self.debit.description='Changed source';self.db.commit()
        changed=list_entries(self.db,case_id=self.case.id,event_keys=transfer['event_keys'])[0]
        self.assertEqual(changed['source']['state'],'snapshot')

    def test_ownership_change_marks_saved_pair_for_review(self):
        saved = self.save(self.pair())
        self.assertFalse(saved['details']['internal_transfer'])
        self.assign_owner()
        reopened = list_trails(self.db,case_id=self.case.id)['trails'][0]
        self.assertEqual(reopened['status'],'source_changed')
        self.assertFalse(reopened['details']['internal_transfer'])
        self.assertEqual(reopened['details'],saved['details'])

    def test_amount_edit_after_preview_requires_new_review(self):
        request = self.pair()
        preview = preview_trail(self.db,case_id=self.case.id,request=request)
        self.debit.description = 'Corrected description'; self.db.commit()
        with self.assertRaisesRegex(TrailError,'changed'):
            save_trail(self.db,case_id=self.case.id,request=request.model_copy(update={
                'expected_source_revision':preview['source_revision']}),actor=self.actor)
        self.assertEqual(list_trails(self.db,case_id=self.case.id)['trails'],[])

    def test_partial_allocations_cannot_spend_same_receipt_twice(self):
        def allocate(amount):
            return TrailRequest(id=uuid4(),kind='allocation',credit_id=self.credit.id,
                payments=[{'transaction_id':self.supplier.id,'amount_minor':str(amount)}],reason='Reviewed manual partial allocation')
        self.assertEqual(self.save(allocate(300000))['details']['receipt_unallocated_minor'],'200000')
        with self.assertRaisesRegex(TrailError,'combined allocations'):
            self.save(allocate(300000))
        self.assertEqual(self.save(allocate(200000))['details']['receipt_unallocated_minor'],'0')

    def test_different_currency_requires_explicit_fx_and_preserves_originals(self):
        self.credit.currency='MXN'; self.credit.amount_minor=10000000; self.db.commit()
        with self.assertRaisesRegex(TrailError,'Different currencies'): self.save(self.pair())
        saved=self.save(self.pair(allow_fx=True))
        self.assertEqual(saved['details']['implied_exchange_rate'],'20')
        self.assertEqual({r['currency'] for r in saved['details']['payments']},{'GBP','MXN'})

    def test_one_sided_reference_does_not_invent_payment_or_common_ownership(self):
        request=TrailRequest(id=uuid4(),kind='transfer',credit_id=self.credit.id,
            referenced_account={'institution':'Other bank','identifier':'000123456','holder':'Example business'},reason='Sender details printed in receipt')
        saved=self.save(request)
        self.assertEqual(len(saved['details']['payments']),1)
        self.assertFalse(saved['details']['internal_transfer'])

    def test_unrelated_case_and_noncurrent_rows_are_refused(self):
        request=self.pair()
        with self.assertRaises(TrailError): preview_trail(self.db,case_id=self.other_case.id,request=request)
        self.debit.ledger_status='superseded'; self.debit.superseded_by_id=self.supplier.id; self.db.commit()
        with self.assertRaisesRegex(TrailError,'changed or is excluded'): self.save(request)

    def test_same_day_warnings_and_backward_allocation_refusal(self):
        request=TrailRequest(id=uuid4(),kind='allocation',credit_id=self.credit.id,
            payments=[{'transaction_id':self.supplier.id,'amount_minor':'10000'}],reason='Manual allocation')
        preview=preview_trail(self.db,case_id=self.case.id,request=request)
        self.assertTrue(any('Same-day' in w for w in preview['warnings']))
        self.supplier.ordering_date=date(2026,1,14); self.db.commit()
        with self.assertRaisesRegex(TrailError,'predates'): self.save(request)
