from unittest import TestCase
from services.financial.ledger_table_view import capture_table_view
from services.financial.ledger_summary import LedgerSummaryError

class LedgerTableViewTests(TestCase):
    def test_profile_scope_stays_in_exports_when_additional_filters_are_cleared(self):
        ledger = {'readings': [self.row('one', account_id='a', from_name='Supplier', to_name='Owner'), self.row('two', account_id='b', from_name='Supplier', to_name='Owner'), self.row('unknown', account_id='a', from_name='', counterparty_raw='Rejected'), self.row('other', account_id='a', from_name='Other')]}
        ledger['readings'][1]['row']['currency'] = 'USD'
        self.assertEqual(capture_table_view(ledger, {'profile_id': 'name:Supplier'})['row_ids'], ['one','two'])
        self.assertEqual(capture_table_view(ledger, {'profile_id': 'name:Supplier','profile_group':'GBP:bank'})['row_ids'], ['one'])
        self.assertEqual(capture_table_view(ledger, {'profile_id': 'name:'})['row_ids'], ['unknown'])
        self.assertEqual(capture_table_view(ledger, {'profile_id': 'account:b'})['row_ids'], ['two'])
        self.assertEqual(capture_table_view(ledger, {'profile_id': 'name:Supplier','from_names':['name:Other']})['row_ids'], [])
        self.assertNotIn('profile_id',capture_table_view(ledger,{})['filters'])
    def test_holder_filters_accounts_across_banks_and_matches_exported_selection(self):
        a = '00000000-0000-4000-8000-000000000001'
        b = '00000000-0000-4000-8000-000000000002'
        ledger = {'readings': [
            self.row('a', account_id=a, account_holder='Example Company', account_label='Bank A'),
            self.row('b', account_id=b, account_holder=' EXAMPLE  COMPANY ', account_label='Bank B'),
            self.row('other', account_id=b, account_holder='Other Company'),
            self.row('unknown', account_id=b, account_holder=''),
        ]}
        view = capture_table_view(ledger, {'account_holder': 'example company'})
        self.assertEqual(view['row_ids'], ['a', 'b'])
        self.assertEqual(view['filters']['account_holder'], 'example company')
        self.assertEqual(capture_table_view(ledger, {'account_holder': 'example company', 'account_id': b})['row_ids'], ['b'])
        self.assertEqual(capture_table_view(ledger, {'account_holder': 'absent'})['row_ids'], [])
        self.assertEqual(capture_table_view(ledger, {})['matching_rows'], 4)
        with self.assertRaises(LedgerSummaryError):
            capture_table_view(ledger, {'account_id': 'not-an-account'})

    def row(self,key,**values):
        return {'row':dict(key=key,ledger_status='admitted',proof_class='p3',currency='GBP',direction='credit',amount_minor='9007199254740993',ordering_date='2026-01-01',row_index=0,description='Invoice payment',**values)}
    def test_exact_sort_and_filters_retain_every_matching_id(self):
        a=self.row('a');b=self.row('b');b['row']['amount_minor']='9007199254740992'
        view=capture_table_view({'readings':[a,b]},dict(search='INVOICE',currency='GBP',sort='amount-asc'))
        self.assertEqual(view['row_ids'],['b','a']);self.assertEqual(view['matching_rows'],2)
        self.assertEqual(view['filters']['search'],'INVOICE')
        self.assertEqual(capture_table_view({'readings':[a,b]},dict(direction='debit'))['row_ids'],[])
    def test_full_capture_is_not_mutated_and_status_is_respected(self):
        from copy import deepcopy
        a=self.row('a');b=self.row('b');b['row']['ledger_status']='superseded'
        ledger={'readings':[a,b]};before=deepcopy(ledger)
        self.assertEqual(capture_table_view(ledger,{})['row_ids'],['a'])
        self.assertEqual(ledger,before)
    def test_stable_ledger_order_and_mixed_currency_sort_refusal(self):
        a=self.row('a');b=self.row('b');c=self.row('c');c['row']['ordering_date']='2026-01-02'
        self.assertEqual(capture_table_view({'readings':[c,b,a]}, {})['row_ids'],['a','b','c'])
        self.assertEqual(capture_table_view({'readings':[c,b,a]},dict(sort='newest'))['row_ids'],['c','a','b'])
        b['row']['currency']='USD'
        with self.assertRaises(LedgerSummaryError):capture_table_view({'readings':[a,b]},dict(sort='amount-desc'))
        for invalid in [dict(search='x'*257),dict(sort='raw_sql'),dict(extra=True)]:
            with self.assertRaises(LedgerSummaryError):capture_table_view({'readings':[]},invalid)

    def test_inclusive_bigint_range_requires_currency_and_preserves_full_capture(self):
        from copy import deepcopy
        a=self.row('a');b=self.row('b');b['row']['amount_minor']='9007199254740992'
        ledger={'readings':[a,b]};before=deepcopy(ledger)
        view=capture_table_view(ledger,dict(currency='GBP',minimum_minor='9007199254740993',maximum_minor='9007199254740993'))
        self.assertEqual(view['row_ids'],['a']);self.assertEqual(ledger,before)
        self.assertEqual(view['filters']['minimum_minor'],'9007199254740993')
        for invalid in [dict(minimum_minor='0'),dict(currency='GBP',minimum_minor='2',maximum_minor='1'),dict(currency='GBP',minimum_minor='9223372036854775808'),dict(currency='GBP',maximum_minor='1.2'),dict(currency='GBP',minimum_minor=0)]:
            with self.subTest(invalid=invalid),self.assertRaises(LedgerSummaryError):capture_table_view(ledger,invalid)

    def test_statement_filter_keeps_exact_source_rows_without_changing_the_full_capture(self):
        from copy import deepcopy
        a_id = '00000000-0000-4000-8000-000000000001'
        b_id = '00000000-0000-4000-8000-000000000002'
        a = self.row('a', source_document_id=a_id)
        b = self.row('b', source_document_id=b_id)
        archived = self.row('archived', source_document_id=a_id)
        archived['row']['ledger_status'] = 'superseded'
        ledger = {'readings': [a, b, archived]}
        before = deepcopy(ledger)
        view = capture_table_view(ledger, {'source_document_id': a_id})
        self.assertEqual(view['row_ids'], ['a'])
        self.assertEqual(view['filters']['source_document_id'], a_id)
        self.assertEqual(ledger, before)
        self.assertEqual(capture_table_view(ledger, {'source_document_id': b_id})['row_ids'], ['b'])
        self.assertNotIn('source_document_id', capture_table_view(ledger, {})['filters'])
        for value in ['prefix', a_id + 'extra', None, 42]:
            with self.subTest(value=value), self.assertRaises(LedgerSummaryError):
                capture_table_view(ledger, {'source_document_id': value})

    def test_batch_export_is_bound_to_the_exact_imported_sources_and_refuses_stale_scope(self):
        from copy import deepcopy
        batch_id = '00000000-0000-4000-8000-000000000001'
        ledger = {'readings': [self.row('a', source_document_id='source-a'), self.row('b', source_document_id='source-b'), self.row('other', source_document_id='source-other')]}
        original = deepcopy(ledger)
        filters = {'import_batch_id': batch_id, 'import_batch_revision': 'a'*64}
        scope = {'batch_id': batch_id, 'revision': 'a'*64, 'source_document_ids': ['source-a', 'source-b']}
        view = capture_table_view(ledger, filters, batch_scope=scope)
        self.assertEqual(view['row_ids'], ['a', 'b'])
        self.assertEqual(view['imported_source_document_ids'], scope['source_document_ids'])
        self.assertEqual(ledger, original)
        self.assertEqual(capture_table_view(ledger, filters, batch_scope={**scope, 'source_document_ids': []})['row_ids'], [])
        for invalid in (None, {**scope, 'revision': 'b'*64}, {**scope, 'batch_id': 'another'}):
            with self.subTest(invalid=invalid), self.assertRaises(LedgerSummaryError):
                capture_table_view(ledger, filters, batch_scope=invalid)
        with self.assertRaises(LedgerSummaryError):
            capture_table_view(ledger, {'import_batch_id': batch_id}, batch_scope=scope)

    def test_connected_analysis_filters_and_internal_external_drills(self):
        def row(key, **changes):
            result = self.row(key, from_name='Our Co', to_name='Supplier', account_holder='Our Co', account_type='checking')
            result['row'].update(changes)
            return result
        ledger = {'readings': [row('out', direction='debit'), row('in', from_name='Client', to_name='Our Co'), row('internal', direction='debit', to_name='Sister Co'), row('unrelated', from_name='Other'), row('card', account_type='credit_card'), row('eur', currency='EUR')]}
        filters = {'from_names': ['name:Our Co', 'name:Other'], 'to_names': ['name:Supplier'], 'perspective_names': ['name:Our Co'], 'analysis_group': 'GBP:bank'}
        self.assertEqual(capture_table_view(ledger, filters)['row_ids'], ['out'])
        perspective = {'perspective_names': ['name:Our Co', 'name:Sister Co'], 'analysis_group': 'GBP:bank'}
        self.assertEqual(capture_table_view(ledger, {**perspective, 'flow_kind': 'internal'})['row_ids'], ['internal'])
        self.assertEqual(capture_table_view(ledger, {**perspective, 'flow_kind': 'outgoing', 'flow_party': 'name:Supplier'})['row_ids'], ['out'])
        self.assertEqual(capture_table_view(ledger, {**perspective, 'flow_kind': 'incoming'})['row_ids'], ['in'])
        self.assertEqual(capture_table_view(ledger, filters)['filters']['from_names'], filters['from_names'])
        with self.assertRaises(LedgerSummaryError):
            capture_table_view(ledger, {'flow_kind': 'internal'})

    def test_chart_filters_and_name_order_preserve_missing_dates_and_explicitly_cleared_names(self):
        ledger = {'readings': [self.row('a', category='Rent', to_name='Zebra'), self.row('b', category='Fees', to_name='Alpha'), self.row('c', ordering_date_context='statement_end_ordering_only', to_name='', counterparty_raw='Old name')]}
        self.assertEqual(capture_table_view(ledger, {'analysis_categories': ['Rent', 'Fees'], 'analysis_period': '2026-01', 'sort': 'to-asc'})['row_ids'], ['b', 'a'])
        self.assertEqual(capture_table_view(ledger, {'analysis_period': 'undated', 'to_names': ['unknown:to']})['row_ids'], ['c'])
        self.assertEqual(capture_table_view(ledger, {'analysis_period': '2026-02'})['row_ids'], [])
