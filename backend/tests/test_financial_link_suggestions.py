"""Suggested connected payments, case-wide payment search, onward steps and the agent's candidate finder
(services.financial.link_suggestions; lx-linksuggest, Neil 8 Nov: "the user is never going to be able to select a
transaction from a dropdown of thousands of transactions")."""
from datetime import date, timedelta
from uuid import UUID, uuid4

from sqlalchemy import func, select

from postgres.models.enums import TransactionDirection
from postgres.models.financial_money_trails import FinancialMoneyTrail
from services.financial.link_suggestions import (COMMON_REFERENCE, LinkSuggestionError, grade_payments,
                                                 parse_query, search_payments, suggest_connected, suggest_onward)
from services.financial.money_trails import TrailRequest, preview_trail, save_trail
from tests.test_financial_duplicates import DuplicateTestCase

DAY = date(2024, 1, 15)


class LinkSuggestionTests(DuplicateTestCase):
    def setUp(self):
        super().setUp()
        FinancialMoneyTrail.__table__.create(self.engine)
        self.second = self._account(self.case.id, identity_key='example-bank-222222')
        self.third = self._account(self.case.id, identity_key='example-bank-333333')
        self.db.add_all([self.second, self.third]); self.db.commit()
        self.doc_a, self.doc_b, self.doc_c = self.make_document(), self.make_document(), self.make_document()
        self.period_a = self.make_period(self.doc_a)
        self.period_b = self.make_period(self.doc_b, account=self.second)
        self.period_c = self.make_period(self.doc_c, account=self.third)

    def pay(self, period, doc, account, amount, direction, day=DAY, description=None):
        row = self.add_row(period, doc, account=account, amount=amount, direction=direction)
        row.ordering_date = row.transaction_date = day
        if description is not None:
            row.description = description
        self.db.commit()
        return row

    def a(self, amount, direction=TransactionDirection.debit, **kw):
        return self.pay(self.period_a, self.doc_a, self.account, amount, direction, **kw)

    def b(self, amount, direction=TransactionDirection.credit, **kw):
        return self.pay(self.period_b, self.doc_b, self.second, amount, direction, **kw)

    def c(self, amount, direction=TransactionDirection.credit, **kw):
        return self.pay(self.period_c, self.doc_c, self.third, amount, direction, **kw)

    def ids(self, result):
        return [c['id'] for c in result['candidates']]

    def test_same_amount_other_way_in_another_account_ranks_above_a_weaker_one(self):
        anchor = self.a(825_62)
        weaker = self.c(825_62 + 10_00, day=DAY + timedelta(days=20))  # within 2 %: a possible fee, 20 days later
        exact = self.b(825_62, day=DAY + timedelta(days=1))
        same_side = self.a(825_62, direction=TransactionDirection.credit)  # same account: never its other side
        out = suggest_connected(self.db, case_id=self.case.id, transaction_id=anchor.id)
        self.assertEqual(self.ids(out)[:2], [str(exact.id), str(weaker.id)])
        self.assertNotIn(str(same_side.id), self.ids(out))
        top, second = out['candidates'][:2]
        self.assertEqual(top['level'], 'strong')  # matching amount within 3 days, substantiated
        self.assertIn('same amount', top['reasons'])
        self.assertIn('1 day later', top['reasons'])
        self.assertIn('the only same-amount payment', top['reasons'])
        self.assertEqual(second['level'], 'weak')
        self.assertIn('a possible fee', second['reasons'])
        self.assertEqual(out['total'], 2)
        self.assertEqual(sum(out['by_level'].values()), 2)
        for c in out['candidates']:
            self.assertTrue(c['from_name'] and c['to_name'] and c['date'] and c['amount'] and c['account_label'])

    def test_suggestions_never_include_another_cases_payments(self):
        anchor = self.a(500_00)
        other_doc = self.make_document(run=self.other_run, case=self.other_case)
        other_period = self.make_period(other_doc, account=self.other_account, run=self.other_run)
        theirs = self.add_row(other_period, other_doc, account=self.other_account, amount=500_00,
                              direction=TransactionDirection.credit, run=self.other_run)
        mine = self.b(500_00)
        out = suggest_connected(self.db, case_id=self.case.id, transaction_id=anchor.id)
        self.assertEqual(self.ids(out), [str(mine.id)])
        found = search_payments(self.db, case_id=self.case.id, q='500.00', transaction_id=anchor.id)
        self.assertNotIn(str(theirs.id), self.ids(found))
        named = grade_payments(self.db, case_id=self.case.id, ids=[theirs.id, mine.id], transaction_id=anchor.id)
        self.assertEqual(self.ids(named), [str(mine.id)])
        self.assertEqual(named['not_found'], 1)
        with self.assertRaises(LinkSuggestionError) as refused:
            suggest_connected(self.db, case_id=self.case.id, transaction_id=theirs.id)
        self.assertEqual(refused.exception.status_code, 404)

    def test_search_by_amount_finds_it_across_accounts(self):
        anchor = self.a(1_000_00)
        one = self.b(825_62, day=DAY + timedelta(days=200))
        two = self.c(825_62, direction=TransactionDirection.debit, day=DAY - timedelta(days=90))
        self.b(825_63)
        out = search_payments(self.db, case_id=self.case.id, q='825.62', transaction_id=anchor.id)
        self.assertEqual(set(self.ids(out)), {str(one.id), str(two.id)})
        self.assertEqual(out['understood'], 'amount exactly 825.62')
        self.assertEqual(set(self.ids(search_payments(self.db, case_id=self.case.id, q='825.62±0.01'))),
                         set(self.ids(search_payments(self.db, case_id=self.case.id, q='825.61-825.63'))))
        self.assertEqual(len(self.ids(search_payments(self.db, case_id=self.case.id, q='825.61-825.63'))), 3)

    def test_query_words(self):
        self.assertEqual(parse_query('825.62')['amount'][0], parse_query('825.62')['amount'][1])
        q = parse_query('ACME 2024-01-01..2024-01-31')
        self.assertEqual((q['date_from'], q['date_to'], q['words']), (date(2024, 1, 1), date(2024, 1, 31), ['ACME']))
        with self.assertRaises(LinkSuggestionError):
            parse_query('   ')

    def test_shared_reference_found_across_the_case_and_common_codes_named(self):
        anchor = self.a(700_00, description='SPEI ENVIADO Ref. 0004699122 0000000')
        far = self.b(123_45, day=DAY + timedelta(days=300), description='RECIBIDO Ref 0004699122')
        for i in range(COMMON_REFERENCE + 1):
            self.c(1_00 + i, description='FEE 0000000 %d' % i)
        out = suggest_connected(self.db, case_id=self.case.id, transaction_id=anchor.id)
        self.assertEqual(self.ids(out), [str(far.id)])
        self.assertIn('reference 0004699122 in both', out['candidates'][0]['reasons'])
        self.assertEqual(out['candidates'][0]['level'], 'weak')

    def test_corrected_payment_is_matched_on_its_current_reading(self):
        anchor = self.a(300_00)
        original = self.b(999_99)
        corrected = self.b(300_00)
        original.superseded_by_id = corrected.id
        self.db.commit()
        out = suggest_connected(self.db, case_id=self.case.id, transaction_id=anchor.id)
        self.assertEqual(self.ids(out), [str(corrected.id)])

    def test_split_receipts_that_add_up_are_suggested(self):
        anchor = self.a(1_000_00)
        part_one = self.b(600_00)
        part_two = self.b(400_00, day=DAY + timedelta(days=1))
        out = suggest_connected(self.db, case_id=self.case.id, transaction_id=anchor.id)
        self.assertEqual(set(self.ids(out)), {str(part_one.id), str(part_two.id)})
        self.assertTrue(all('adds up to the amount' in c['reasons'] for c in out['candidates']))

    def test_onward_payments_out_of_the_receiving_account(self):
        receipt = self.b(500_00)
        onward = self.b(500_00, direction=TransactionDirection.debit, day=DAY + timedelta(days=2))
        part = self.b(120_00, direction=TransactionDirection.debit, day=DAY + timedelta(days=5))
        before = self.b(500_00, direction=TransactionDirection.debit, day=DAY - timedelta(days=1))
        elsewhere = self.c(500_00, direction=TransactionDirection.debit, day=DAY + timedelta(days=1))
        out = suggest_onward(self.db, case_id=self.case.id, transaction_id=receipt.id)
        self.assertEqual(self.ids(out), [str(onward.id), str(part.id)])
        self.assertEqual([c['level'] for c in out['candidates']], ['strong', 'weak'])
        self.assertNotIn(str(before.id), self.ids(out))
        self.assertNotIn(str(elsewhere.id), self.ids(out))
        with self.assertRaises(LinkSuggestionError):
            suggest_onward(self.db, case_id=self.case.id, transaction_id=onward.id)

    def test_every_candidate_is_listed_and_paged_with_its_count(self):
        anchor = self.a(50_00)
        made = [self.b(50_00, day=DAY + timedelta(days=i % 30)) for i in range(7)]
        first = suggest_connected(self.db, case_id=self.case.id, transaction_id=anchor.id, page=1, page_size=5)
        second = suggest_connected(self.db, case_id=self.case.id, transaction_id=anchor.id, page=2, page_size=5)
        self.assertEqual((first['total'], first['pages'], len(first['candidates']), len(second['candidates'])),
                         (7, 2, 5, 2))
        self.assertEqual(set(self.ids(first)) | set(self.ids(second)), {str(r.id) for r in made})

    def test_same_amount_beyond_the_window_is_counted(self):
        anchor = self.a(77_00)
        self.b(77_00, day=DAY + timedelta(days=200))
        out = suggest_connected(self.db, case_id=self.case.id, transaction_id=anchor.id)
        self.assertEqual(out['total'], 0)
        self.assertEqual(out['left_out']['same_amount_beyond_window'], 1)
        self.assertIn('1 more payment of the same amount', out['left_out']['words'])

    def test_a_link_from_a_suggestion_records_which_rule_suggested_it(self):
        anchor = self.a(500_00)
        other = self.b(500_00)
        top = suggest_connected(self.db, case_id=self.case.id, transaction_id=anchor.id)['candidates'][0]
        request = TrailRequest(id=uuid4(), kind='transfer', debit_id=anchor.id, credit_id=other.id,
                               reason='Linked from a suggestion', suggested_by='connected_payment rule (%s): %s'
                               % (top['level'], top['reasons']))
        preview = preview_trail(self.db, case_id=self.case.id, request=request)
        saved = save_trail(self.db, case_id=self.case.id, request=request.model_copy(
            update={'expected_source_revision': preview['source_revision']}), actor=self.actor)
        self.assertTrue(saved['details']['input']['suggested_by'].startswith('connected_payment rule (strong)'))
        self.assertEqual(saved['status'], 'current')
        again = suggest_connected(self.db, case_id=self.case.id, transaction_id=anchor.id)['candidates'][0]
        self.assertTrue(again['already_linked'])
        self.assertIn('already in a saved transfer', again['reasons'])

    def test_agent_candidate_finder_is_labelled_and_never_links(self):
        from services.agent.ledger_reading_tools import find_connected_payments
        anchor = self.a(640_00)
        other = self.b(640_00)
        out = find_connected_payments(self.db, case_id=self.case.id, payment=anchor.ref_id)
        self.assertTrue(out['available'])
        self.assertEqual([i['id'] for i in out['items']], [str(other.id)])
        self.assertIn('payment=%s' % other.id, out['items'][0]['citation']['href'])
        self.assertIn('never links', out['limitation'])
        self.assertIn('model suggestion until a person links it', out['limitation'])
        searched = find_connected_payments(self.db, case_id=self.case.id, payment=str(anchor.id), mode='search',
                                           search='640.00')
        self.assertEqual([i['id'] for i in searched['items']], [str(other.id)])
        self.assertEqual(self.db.scalar(select(func.count()).select_from(FinancialMoneyTrail)), 0)
        missing = find_connected_payments(self.db, case_id=self.other_case.id, payment=str(anchor.id))
        self.assertFalse(missing['available'])


class LinkSuggestionRouteTests(DuplicateTestCase):
    def test_routes_are_registered_on_the_read_only_ledger_router(self):
        from routers.financial_ledger import router
        paths = {r.path: r.methods for r in router.routes}
        for path in ('/api/financial/payment-links/suggestions', '/api/financial/payment-links/search',
                     '/api/financial/payment-links/named'):
            self.assertEqual(paths[path], {'GET'})

    def test_agent_tool_is_offered(self):
        import services.agent.tools as tools
        source = open(tools.__file__).read()
        self.assertIn('name="find_connected_payments"', source)
        self.assertIn('read_ledger_extra("find_connected_payments", "find_connected_payments"', source)
