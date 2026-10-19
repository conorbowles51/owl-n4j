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

    def test_missing_statement_match_appears_later_and_updates_same_saved_transfer(self):
        request = TrailRequest(id=uuid4(), kind='transfer', credit_id=self.credit.id,
            referenced_account={'institution':'Synthetic bank', 'identifier_kind':'clabe', 'identifier':'012345678901234567'},
            reason='Account reference printed on the incoming payment')
        first = self.save(request)
        self.assertEqual(first['matching_entries'], [])
        self.account.metadata_ = {'identity_review': {'identifiers': [{'kind':'clabe', 'value':'012345678901234567'}]}}
        self.db.commit()
        shown = list_trails(self.db, case_id=self.case.id)['trails'][0]
        self.assertEqual([p['key'] for p in shown['matching_entries']], [str(self.debit.id)])
        pair = self.pair().model_copy(update={'id':request.id, 'expected_revision':first['revision']})
        updated = self.save(pair)
        self.assertEqual(updated['id'], first['id'])
        self.assertEqual(len(updated['details']['payments']), 2)
        self.assertEqual(len(list(self.db.scalars(select(FinancialMoneyTrail)))), 1)

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

    def split_request(self, parts, **changes):
        return TrailRequest(id=uuid4(), kind='transfer', transfer_parts=parts,
            reason='Reviewed the principal and fee against each source; unmatched money is left unassigned', **changes)

    def test_split_transfer_with_embedded_and_separate_fees_retains_originals_and_retries(self):
        self.assign_owner()
        self.debit.amount_minor = 501000
        self.credit.amount_minor = 300000
        other_credit = self.add_row(self.period_b, self.doc_b, account=self.second, amount=200000)
        fee = self.add_row(self.period_b, self.doc_b, account=self.second, amount=200, direction=TransactionDirection.debit)
        self.db.commit()
        request = self.split_request([
            dict(transaction_id=self.debit.id, principal_minor='500000', fee_minor='1000'),
            dict(transaction_id=self.credit.id, principal_minor='300000'),
            dict(transaction_id=other_credit.id, principal_minor='200000'),
            dict(transaction_id=fee.id, principal_minor='0', fee_minor='200'),
        ])
        saved = self.save(request)
        detail = saved['details']
        self.assertTrue(detail['internal_transfer'])
        self.assertEqual(detail['transfer_breakdown']['fees'], [{'currency': 'GBP', 'amount_minor': '1200'}])
        self.assertEqual(detail['transfer_breakdown']['sent_minor'], '500000')
        self.assertTrue(all(p['remaining_after_other_links_minor'] == '0' for p in detail['transfer_breakdown']['entries']))
        self.assertEqual(self.save(request)['revision'], 1)
        self.db.expire_all()
        self.assertEqual(list_trails(self.db, case_id=self.case.id)['trails'][0]['status'], 'current')
        self.assertEqual(self.debit.amount_minor, 501000)
        self.assertEqual(len(detail['payments']), 4)

    def test_partial_transfer_links_share_capacity_without_reusing_full_postings(self):
        def request(amount):
            return self.split_request([
                dict(transaction_id=self.debit.id, principal_minor=str(amount)),
                dict(transaction_id=self.credit.id, principal_minor=str(amount)),
            ])
        first = self.save(request(300000))
        self.assertEqual(first['details']['transfer_breakdown']['entries'][0]['unassigned_minor'], '200000')
        with self.assertRaisesRegex(TrailError, 'combined principal and fees'):
            self.save(request(300000))
        second = self.save(request(200000))
        self.assertEqual(second['details']['transfer_breakdown']['entries'][0]['remaining_after_other_links_minor'], '0')
        self.assertTrue(all(t['status'] == 'current' for t in list_trails(self.db, case_id=self.case.id)['trails']))
        with self.assertRaisesRegex(TrailError, 'already linked'):
            self.save(self.pair())

    def test_split_transfer_requires_balanced_principal_and_explicit_fx(self):
        parts = [dict(transaction_id=self.debit.id, principal_minor='490000', fee_minor='10000'),
            dict(transaction_id=self.credit.id, principal_minor='500000')]
        with self.assertRaisesRegex(TrailError, 'do not balance'):
            self.save(self.split_request(parts))
        parts[0]['principal_minor'] = '500000'
        with self.assertRaisesRegex(TrailError, 'exceeds'):
            self.save(self.split_request(parts))
        parts[0]['fee_minor'] = '0'
        self.credit.currency = 'JPY'; self.credit.amount_minor = 1000000; self.db.commit()
        parts[1]['principal_minor'] = '1000000'
        with self.assertRaisesRegex(TrailError, 'Different currencies'):
            self.save(self.split_request(parts))
        fx = self.save(self.split_request(parts, allow_fx=True))
        self.assertEqual(fx['details']['implied_exchange_rate'], '200')
        self.assertEqual({p['currency'] for p in fx['details']['payments']}, {'GBP', 'JPY'})

    def test_timeline_partial_link_retains_original_posting_events(self):
        from postgres.models.timeline_entry import TimelineEntry
        from services.timeline_entries import TimelineAddition, preview_addition, save_addition, list_entries
        TimelineEntry.__table__.create(self.engine)
        trail = self.save(self.split_request([
            dict(transaction_id=self.debit.id, principal_minor='250000'),
            dict(transaction_id=self.credit.id, principal_minor='250000'),
        ]))
        request = TimelineAddition(source_kind='money_trail', source_ids=[UUID(trail['id'])])
        preview = preview_addition(self.db, case_id=self.case.id, request=request)
        event = preview['rows'][0]['event']
        self.assertIn('2,500.00', event['amount'])
        self.assertEqual(event['transfer_posting_roots'], [])
        self.assertIn('unassigned in this link', event['summary'])
        request.expected_revision = preview['revision']
        save_addition(self.db, case_id=self.case.id, request=request, actor=self.actor.email)
        transaction = TimelineAddition(source_kind='transaction', source_ids=[self.debit.id])
        self.assertEqual(preview_addition(self.db, case_id=self.case.id, request=transaction)['ready'], 1)
