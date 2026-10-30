"""Stored payment categories: rules on save, a person's choice never overwritten, learning, and the model fallback."""
import json
from pathlib import Path
from unittest import mock
from types import SimpleNamespace

from postgres.models.financial import FinancialTransaction
from postgres.models.financial_category import FinancialCategory
from postgres.models.financial_judgements import FinancialJudgement
from postgres.models.financial_payment_category import (FinancialCategoryModelCache, FinancialCategoryRule,
                                                        FinancialPaymentCategory)
from postgres.base import Base
from services.financial import payment_categories as pc
from services.financial.payment_labels import PaymentLabelsRequest, update_payment_labels
from services.financial.transaction_query import list_transactions, to_view
from tests.test_financial_transaction_query import LedgerQueryTestCase, reading

ACTOR = SimpleNamespace(name='Investigator', email='investigator@example.test', user_id=None)


def rule_uuid(rule):
    import uuid
    return uuid.UUID(rule['id'])


class PaymentCategoryTests(LedgerQueryTestCase):
    def setUp(self):
        super().setUp()
        self.db.commit()
        from services.financial import judgement_inbox
        self.inbox = Path(self._directory) / 'inbox.md'
        for target, value in ((judgement_inbox, 'INBOX'), ):
            patcher = mock.patch.object(target, value, self.inbox)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = mock.patch.object(judgement_inbox, '_statement', lambda session, item: 'statement.pdf')
        patcher.start()
        self.addCleanup(patcher.stop)
        Base.metadata.create_all(self.engine, tables=[FinancialPaymentCategory.__table__,
                                                      FinancialCategoryModelCache.__table__,
                                                      FinancialCategoryRule.__table__,
                                                      FinancialJudgement.__table__, FinancialCategory.__table__])

    def rows(self, *descriptions):
        written = self.write([self.draft(row_index=index, reading=reading(description=text, amount_minor=100 + index))
                              for index, text in enumerate(descriptions)])
        self.db.commit()
        return written

    def stored(self, row):
        self.db.expire_all()
        return self.db.get(FinancialPaymentCategory, row.id)

    def test_saved_payments_get_their_rule_category_and_the_ledger_reads_it(self):
        fee, unknown = self.rows('0000000 COM MEMBRESIA CUENTA E PYME', '105413834')
        self.assertEqual((self.stored(fee).category, self.stored(fee).origin), ('Bank fees', 'rule'))
        self.assertIsNone(self.stored(unknown))
        views = {row.id: to_view(row).to_json() for row in list_transactions(self.db, self.case.id)}
        self.assertEqual(views[fee.id]['category'], 'Bank fees')
        self.assertEqual(views[fee.id]['label_sources']['category']['source'], 'description')

    def test_a_person_wins_and_no_automatic_pass_replaces_them(self):
        (row,) = self.rows('0000000 COM MEMBRESIA CUENTA E PYME')
        update_payment_labels(self.db, case_id=self.case.id, actor=ACTOR, request=PaymentLabelsRequest(
            transactions=[dict(id=row.id, version=0)], category='Rent and leases'))
        pc.backfill(self.db, self.case.id)
        pc.classify_with_model(self.db, self.case.id, reader=lambda prompt: self.fail('no model call expected'))
        self.assertEqual((self.stored(row).category, self.stored(row).origin), ('Rent and leases', 'person'))

    def test_a_choice_applies_to_the_payments_like_it_as_learned_but_never_over_a_person(self):
        source, like, chosen, other = self.rows('SUNRISE SENIOR L PAYMENTS 01', 'SUNRISE SENIOR L PAYMENTS 02',
                                                'SUNRISE SENIOR L PAYMENTS 03', 'Check 2320')
        update_payment_labels(self.db, case_id=self.case.id, actor=ACTOR, request=PaymentLabelsRequest(
            transactions=[dict(id=chosen.id, version=0)], category='Health and pharmacy'))
        found, _ = pc.like_payments(self.db, self.case.id, source.id)
        self.assertEqual({row.id for row in found}, {like.id})
        self.assertEqual(pc.apply_learned(self.db, self.case.id, source.id, 'Personal care', ACTOR), 1)
        self.db.commit()
        self.assertEqual((self.stored(like).category, self.stored(like).origin), ('Personal care', 'learned'))
        self.assertEqual(self.stored(chosen).origin, 'person')
        self.assertEqual(self.stored(other).category, 'Checks')

    def test_a_rule_a_person_makes_places_future_payments_like_it_but_never_over_a_person(self):
        (source,) = self.rows('COM MEMBRESIA CUENTA E PYME 01')
        rule = pc.save_rule(self.db, self.case.id, source.id, 'Rent and leases', ACTOR)
        self.db.commit()
        self.assertEqual((rule['match_kind'], rule['match_value']), ('description', 'COM MEMBRESIA CUENTA E PYME #'))
        later, unrelated = self.write([self.draft(row_index=10 + index, reading=reading(description=text,
                                                                                         amount_minor=500 + index))
                                       for index, text in enumerate(('COM MEMBRESIA CUENTA E PYME 02', 'Check 2320'))])
        self.db.commit()
        self.assertEqual((self.stored(later).category, self.stored(later).origin, self.stored(later).basis),
                         ('Rent and leases', 'learned', f"rule:{rule['id']}"))
        self.assertEqual(self.stored(unrelated).category, 'Checks')
        view = {row.id: to_view(row).to_json() for row in list_transactions(self.db, self.case.id)}[later.id]
        self.assertEqual(view['label_sources']['category']['source'], 'learned')
        update_payment_labels(self.db, case_id=self.case.id, actor=ACTOR, request=PaymentLabelsRequest(
            transactions=[dict(id=later.id, version=0)], category='Bank fees'))
        pc.backfill(self.db, self.case.id)
        self.assertEqual((self.stored(later).category, self.stored(later).origin), ('Bank fees', 'person'))
        (record,) = pc.rule_track_record(self.db, self.case.id)
        self.assertEqual((record['placed'], record['person_chose_differently']), (0, 1))
        pc.retire_rule(self.db, self.case.id, rule['id'])
        self.db.commit()
        (after,) = self.write([self.draft(row_index=20, reading=reading(description='COM MEMBRESIA CUENTA E PYME 03',
                                                                        amount_minor=900))])
        self.db.commit()
        self.assertEqual((self.stored(after).category, self.stored(after).origin), ('Bank fees', 'rule'))
        self.assertEqual(self.db.get(FinancialCategoryRule, rule_uuid(rule)).active, False)

    def test_the_model_places_the_rest_once_per_description_and_doubtful_answers_become_judgement_calls(self):
        first, second = self.rows('105413834', '105413834')
        prompts = []

        def reader(prompt):
            prompts.append(prompt)
            return json.dumps({'items': [{'id': 0, 'category': 'Transfers', 'confidence': 0.4,
                                          'why': 'Only a reference number is printed.'}]})
        result = pc.classify_with_model(self.db, self.case.id, reader=reader, model_id='test-model')
        self.assertEqual((result['placed'], result['asked'], len(prompts)), (2, 1, 1))
        self.assertEqual((self.stored(first).category, self.stored(first).origin), ('Transfers', 'model'))
        calls = self.db.query(FinancialJudgement).filter_by(rule_id='category.model').all()
        self.assertEqual({call.subject_id for call in calls}, {first.id, second.id})
        view = to_view(self.db.get(FinancialTransaction, first.id)).to_json()
        self.assertTrue(view['label_sources']['category']['judgement'])
        # A person changing it corrects the judgement call.
        update_payment_labels(self.db, case_id=self.case.id, actor=ACTOR, request=PaymentLabelsRequest(
            transactions=[dict(id=first.id, version=0)], category='Payroll'))
        self.db.expire_all()
        statuses = {call.subject_id: call.status for call in self.db.query(FinancialJudgement).all()}
        self.assertEqual(statuses[first.id], 'corrected')
        self.assertEqual(statuses[second.id], 'open')
        self.assertIn('category.model', self.inbox.read_text())
        self.assertIn('Transfers -> Payroll', self.inbox.read_text())

    def test_a_rule_category_no_rule_gives_any_more_is_removed_and_a_person_s_never_is(self):
        stale, kept, chosen = self.rows('REVERSE AVIS RENT-A-CAR WASHINGTO', 'W01 TRASPASO A TERCEROS RENTA 21 DE 30',
                                        'REVERSE AVIS RENT-A-CAR DULLES')
        # Stored by an earlier version of the rent rule.
        pc._upsert(self.db, stale, category='Rent and leases', origin='rule', basis='rent', confidence=None, why='x', set_by=None)
        update_payment_labels(self.db, case_id=self.case.id, actor=ACTOR, request=PaymentLabelsRequest(
            transactions=[dict(id=chosen.id, version=0)], category='Rent and leases'))
        self.db.commit()
        written = pc.backfill(self.db, self.case.id)
        self.assertEqual(written.get('rule_removed'), 1)
        self.assertIsNone(self.stored(stale))
        self.assertEqual((self.stored(kept).category, self.stored(kept).origin), ('Rent and leases', 'rule'))
        self.assertEqual((self.stored(chosen).category, self.stored(chosen).origin), ('Rent and leases', 'person'))

    def test_a_failed_inbox_append_is_reported_and_the_check_adds_the_line(self):
        from services.financial import judgement_inbox
        (row,) = self.rows('105413834')
        pc.classify_with_model(self.db, self.case.id, model_id='test-model', reader=lambda prompt: json.dumps(
            {'items': [{'id': 0, 'category': 'Transfers', 'confidence': 0.4, 'why': 'Only a number.'}]}))
        # The backend user cannot write the inbox (the live failure: the file belonged to root).
        with mock.patch.object(judgement_inbox.Path, 'open', side_effect=PermissionError('Permission denied')):
            update_payment_labels(self.db, case_id=self.case.id, actor=ACTOR, request=PaymentLabelsRequest(
                transactions=[dict(id=row.id, version=0)], category='Payroll'))
            self.db.commit()
            report = judgement_inbox.check(self.db)
        (call,) = self.db.query(FinancialJudgement).filter_by(rule_id='category.model').all()
        self.assertEqual((call.status, self.stored(row).category), ('corrected', 'Payroll'))
        self.assertEqual(report['missing'], [str(call.id)])
        self.assertIn('Permission denied', report['error'])
        report = judgement_inbox.check(self.db)
        self.assertEqual((report['appended'], report['missing'], report['error']), (1, [], ''))
        self.assertIn(f'judgement {call.id}', self.inbox.read_text())

    def test_cached_descriptions_are_not_sent_again_and_answers_outside_the_list_fall_back(self):
        self.rows('XYZZY 1')
        pc.classify_with_model(self.db, self.case.id, reader=lambda p: json.dumps(
            {'items': [{'id': 0, 'category': 'Not a category', 'confidence': 0.9, 'why': 'x'}]}), model_id='m')
        (row,) = [r for r in list_transactions(self.db, self.case.id)]
        self.assertEqual((self.stored(row).category, self.stored(row).confidence), ('Payments', 0.3))
        self.rows('XYZZY 2')
        pc.classify_with_model(self.db, self.case.id, reader=lambda p: self.fail('cached'), model_id='m')
        self.assertEqual(pc.coverage(self.db, self.case.id), {'model': 2})

    def test_breakdown_sums_money_per_category_under_filters_and_groups(self):
        from services.financial.category_breakdown import BreakdownFilters, breakdown
        fee, check, unknown = self.rows('0000000 COM MEMBRESIA CUENTA E PYME', 'Check 2320', '105413834')
        update_payment_labels(self.db, case_id=self.case.id, actor=ACTOR, request=PaymentLabelsRequest(
            transactions=[dict(id=check.id, version=0)], category='Rent and leases'))
        rows = breakdown(self.db, self.case.id, BreakdownFilters())
        got = {row['category']: (row['money_out_minor'], row['count']) for row in rows}
        self.assertEqual(got, {'Bank fees': ('100', 1), 'Rent and leases': ('101', 1), 'Uncategorized': ('102', 1)})
        only = breakdown(self.db, self.case.id, BreakdownFilters(categories=['Uncategorized', 'Bank fees'],
                                                                   group_by='month'))
        self.assertEqual({(row['category'], row['group_key']) for row in only},
                         {('Bank fees', '2024-01'), ('Uncategorized', '2024-01')})
        self.assertEqual(breakdown(self.db, self.case.id, BreakdownFilters(direction='credit')), [])
        self.assertEqual(len(breakdown(self.db, self.case.id, BreakdownFilters(search='membresia', group_by='account'))), 1)
