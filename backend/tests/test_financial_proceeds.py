"""agent-proposals E: the proceeds calculator is deterministic and every assumption is a judgement call a person sets.

The result is a range labelled "estimate, not measured", computed exactly from the current calls only; a changed
assumption keeps the earlier one visible as corrected; an agent's proposed assumption is not used until a person
confirms it; deposits beside it are summed from verified rows (p0 to p2) only.
"""
import unittest
import uuid
from fractions import Fraction

from services.financial import proceeds as P


class ArithmeticTests(unittest.TestCase):
    def test_the_range_is_exact_and_rounded_once(self):
        current = dict(messages=(Fraction(20000), Fraction(20500)), share_deals=(Fraction(30), Fraction(50)),
                       deals_per_message=(Fraction(1), Fraction(1)), price_per_deal=(Fraction(1000), Fraction(2000)))
        out = P.compute(current)
        self.assertEqual(out['low_minor'], 20000 * 3 // 10 * 1000)          # 6,000,000 minor = 60,000.00
        self.assertEqual(out['high_minor'], 20500 * 5 // 10 * 2000)         # 20,500,000 minor
        self.assertEqual(out['mid_minor'], round(Fraction(40500, 2) * Fraction(40, 100) * 1 * 1500))
        top = out['moves'][0]
        self.assertEqual(top['key'], 'price_per_deal')  # the widest swing is listed first
        self.assertEqual(top['swing_minor'], top['at_high_minor'] - top['at_low_minor'])

    def test_nothing_is_computed_until_every_assumption_is_set(self):
        self.assertIsNone(P.compute(dict(messages=(Fraction(1), Fraction(2)))))

    def test_values_are_checked(self):
        with self.assertRaisesRegex(P.ProceedsError, 'at most 100'):
            P._value('share_deals', '120')
        with self.assertRaisesRegex(P.ProceedsError, 'whole number'):
            P._value('messages', '10.5')
        with self.assertRaisesRegex(P.ProceedsError, 'negative'):
            P._value('price_per_deal', '-1')


class CalculationTests(unittest.TestCase):
    def setUp(self):
        from tests.test_agent_proposals import _Fixture
        self.fx = _Fixture()
        self.fx.setUp()
        from postgres.base import Base
        from postgres.models.agent_proposals import ProceedsCalculation
        Base.metadata.create_all(self.fx.db.get_bind(), tables=[ProceedsCalculation.__table__])
        self.db, self.case, self.actor = self.fx.db, self.fx.f.case, self.fx.f.actor

    def tearDown(self):
        self.fx.tearDown()

    def _calc(self, **kw):
        return P.create(self.db, case_id=self.case.id, title='Deal line turnover', currency='GBP', actor=self.actor, **kw)

    def _set_all(self, calc):
        for key, low, high, source in (('messages', '20000', '20500', 'rec:// message count of the deal line'),
                                       ('share_deals', '30', '50', 'Officer statement, page 4'),
                                       ('deals_per_message', '1', '1', 'One deal per flare text (case law guidance)'),
                                       ('price_per_deal', '10', '20', 'NCA street price list 2025')):
            out = P.set_assumption(self.db, case_id=self.case.id, calculation_id=calc['id'], key=key, low=low,
                                   high=high, source=source, actor=self.actor)
        return out

    def test_a_calculation_is_labelled_an_estimate_and_each_assumption_is_a_call(self):
        calc = self._calc()
        self.assertIsNone(calc['result'])
        self.assertEqual(len(calc['missing']), 4)
        out = self._set_all(calc)
        self.assertEqual(out['label'], 'estimate, not measured')
        self.assertEqual((out['result']['low_minor'], out['result']['high_minor']), (6000 * 1000, 10250 * 2000))
        price = next(a for a in out['assumptions'] if a['key'] == 'price_per_deal')
        self.assertEqual((price['low'], price['high'], price['set_by']), ('1000', '2000', self.actor.name))
        self.assertEqual(price['current']['origin'], 'person')
        self.assertEqual(price['current']['rule_id'], 'assumption.proceeds')
        from services.financial import judgements
        page = judgements.search(self.db, self.case.id, categories=['assumption'])
        self.assertEqual(page['total'], 4)

    def test_changing_an_assumption_keeps_the_earlier_one_visible_and_uses_only_the_new(self):
        calc = self._calc()
        self._set_all(calc)
        out = P.set_assumption(self.db, case_id=self.case.id, calculation_id=calc['id'], key='price_per_deal',
                               low='15', high='15', source='Undercover purchase, exhibit JB/3', actor=self.actor)
        price = next(a for a in out['assumptions'] if a['key'] == 'price_per_deal')
        self.assertEqual((price['low'], price['high']), ('1500', '1500'))
        self.assertEqual(len(price['history']), 1)
        self.assertEqual(price['history'][0]['status'], 'corrected')
        self.assertEqual(out['result']['high_minor'], 10250 * 1500)

    def test_an_agent_assumption_is_not_used_until_a_person_confirms_it(self):
        from services.agent.proposals import agent_origin
        calc = self._calc()
        self._set_all(calc)
        origin = agent_origin(for_name='Alex', model='DeepSeek V4 Pro')
        out = P.propose_assumption(self.db, case_id=self.case.id, calculation_id=calc['id'], key='share_deals',
                                   low='60', high='70', source='rec:// conversation sample', why='Most texts are '
                                   'orders.', origin=origin)
        share = next(a for a in out['assumptions'] if a['key'] == 'share_deals')
        self.assertEqual((share['low'], len(share['proposed'])), ('30', 1))
        before = out['result']['high_minor']
        out = P.confirm_assumption(self.db, case_id=self.case.id, calculation_id=calc['id'],
                                   judgement_id=share['proposed'][0]['id'], actor=self.actor)
        share = next(a for a in out['assumptions'] if a['key'] == 'share_deals')
        self.assertEqual((share['low'], share['high'], share['set_by']), ('60', '70', self.actor.name))
        self.assertNotEqual(out['result']['high_minor'], before)
        with self.assertRaises(P.ProceedsError):
            P.propose_assumption(self.db, case_id=self.case.id, calculation_id=calc['id'], key='share_deals',
                                 low='1', high='2', source='x', why='x', origin=dict(kind='person'))

    def test_a_model_cannot_set_an_assumption_and_a_source_is_required(self):
        from services.financial.model_work import model_actor
        calc = self._calc()
        claude = model_actor(for_name='Alex', for_email=self.actor.email)
        with self.assertRaises(P.ProceedsError):
            P.set_assumption(self.db, case_id=self.case.id, calculation_id=calc['id'], key='messages', low='1',
                             high='2', source='x', actor=claude)
        with self.assertRaisesRegex(P.ProceedsError, 'where the value comes from'):
            P.set_assumption(self.db, case_id=self.case.id, calculation_id=calc['id'], key='messages', low='1',
                             high='2', source=' ', actor=self.actor)
        with self.assertRaisesRegex(P.ProceedsError, 'Not in this case'):
            P.view(self.db, case_id=uuid.uuid4(), calculation_id=calc['id'])

    def test_deposits_sum_verified_rows_only(self):
        from postgres.models.financial_payment_category import FinancialPaymentCategory as C
        from services.financial.payment_categories import record_person_choice
        credits = [r for r in self.fx.rows if r.direction == 'credit']
        self.assertTrue(credits)
        for row in credits:
            record_person_choice(self.db, row, 'Cash deposit', self.actor)
        self.db.commit()
        currency = credits[0].currency
        calc = P.create(self.db, case_id=self.case.id, title='x', currency=currency, actor=self.actor,
                        deposit_categories=['Cash deposit'])
        dep = calc['deposits']
        verified = [r for r in credits if r.proof_class in P.VERIFIED_CLASSES and r.currency == currency]
        self.assertEqual(dep['verified_rows'], len(verified))
        self.assertEqual(dep['verified_minor'], sum(abs(r.amount_minor) for r in verified))
        self.assertEqual(dep['left_out_rows'], len([r for r in credits if r.proof_class not in P.VERIFIED_CLASSES
                                                    and r.currency == currency]))


if __name__ == '__main__':
    unittest.main()
