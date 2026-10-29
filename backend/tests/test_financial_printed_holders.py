"""An account printed under different holder names (Neil, 2026-10-29): each statement keeps the name printed on it, by a
recorded decision for that account, as a judgement call; who holds the account is never decided and nothing is merged.

fdaf956c's Capital One card ending 8160 prints ERICA MCCAULEY (2020-09 to 2022-01) and ERICA HOPPER (2022-02 to
2023-12); 21 HOPPER statements were held with "This card (ending 8160) is saved for ERICA MCCAULEY; this statement
prints ERICA HOPPER. Confirm whether they are the same account." Every test here fails on the code before it."""
import unittest
import uuid
from datetime import date
from types import SimpleNamespace
from unittest import mock

from sqlalchemy import select

from postgres.models.financial import AdjudicationEvent, FinancialSourceDocument
from services.financial import judgements, printed_holders as ph, vision_reader as vr
from services.financial.decisions import Actor
from services.financial.field_proposals import CaseKnowledge, case_knowledge
from services.financial.periods import PeriodBounds
from tests import test_financial_duplicates as fixture
from tests.test_financial_vision_last4 import _card_pages, _known, _prove

BOTH = ['ERICA MCCAULEY', 'ERICA HOPPER']
DECISION = dict(decision_id='d-1', actor_name='Claude (for Neil Byrne)', at='2026-10-29T06:30:00+00:00')


def _decided(holders=BOTH, **kw):
    known = _known(**kw)
    known.printed_holders = list(holders)
    known.printed_holders_decision = dict(DECISION)
    return known


class ProofTest(unittest.TestCase):
    def test_without_a_decision_another_printed_holder_is_held(self):
        with self.assertRaisesRegex(vr.NotProved, r'^This card \(ending 8160\) is saved for ERICA MCCAULEY; this '
                                                  r'statement prints ERICA HOPPER\. Confirm whether they are the same'):
            _prove(knowledge=CaseKnowledge(accounts=[_known()]))

    def test_with_the_decision_it_is_filed_under_the_name_it_prints(self):
        known = _decided()
        reading = _prove(knowledge=CaseKnowledge(accounts=[known]))
        self.assertEqual(reading['account_keys'], [known.key])
        self.assertNotIn('account_basis', reading)  # the saved account, not a first statement
        self.assertEqual(reading['holder'], 'ERICA HOPPER')
        self.assertEqual(reading['holder_basis'], ph.HOLDER_BASIS)
        self.assertEqual(reading['holder_names'], BOTH)
        self.assertEqual(reading['holder_page'], 1)
        self.assertEqual(reading['holder_decision'], DECISION)
        self.assertEqual((reading['opening'], reading['closing'], len(reading['rows'])), (100000, 100000, 3))

    def test_switched_off_it_is_held_as_before(self):
        with mock.patch.object(vr, 'PRINTED_HOLDERS', False), self.assertRaisesRegex(vr.NotProved, 'is saved for ERICA'):
            _prove(knowledge=CaseKnowledge(accounts=[_decided()]))

    def test_a_name_the_decision_does_not_cover_is_held(self):
        with self.assertRaisesRegex(vr.NotProved, 'is saved for ERICA MCCAULEY; this statement prints ERICA HOPPER'):
            _prove(knowledge=CaseKnowledge(accounts=[_decided(['ERICA MCCAULEY', 'SOMEONE ELSE'])]))
        # Nor does it cover a saved holder it does not name.
        with self.assertRaisesRegex(vr.NotProved, 'is saved for JOHN DOE'):
            _prove(knowledge=CaseKnowledge(accounts=[_decided(holder='JOHN DOE')]))

    def test_every_other_proof_still_holds_it(self):
        knowledge = CaseKnowledge(accounts=[_decided()])
        pages = _card_pages()
        pages[1][1]['sections'][0]['closing_balance'] = '1000.01'
        with self.assertRaisesRegex(vr.NotProved, 'did not balance'):
            _prove(pages=pages, knowledge=knowledge)
        with self.assertRaisesRegex(vr.NotProved, 'period'):
            _prove(period_end='2023-07-09', knowledge=knowledge)
        # A card at another bank is another account: the decision for this one never reaches it.
        other = _prove(knowledge=CaseKnowledge(accounts=[_decided()]), pages=_card_pages(institution='Chase'),
                       institution='Chase')
        self.assertNotIn('holder_basis', other)
        self.assertEqual(other['account_keys'], [])

    def test_two_accounts_it_could_be_are_never_settled_by_it(self):
        two = CaseKnowledge(accounts=[_decided(), _decided(account='5178051234568160')])
        with self.assertRaisesRegex(vr.NotProved, 'Choose which account this statement belongs to'):
            _prove(knowledge=two)

    def test_one_name_only_is_no_judgement_call(self):
        # The account saved for HOPPER only and this statement HOPPER: the usual match, nothing to call.
        reading = _prove(knowledge=CaseKnowledge(accounts=[_decided(holder='ERICA HOPPER')]))
        self.assertNotIn('holder_basis', reading)
        # Saved under both names already: any statement of it is filed under its own name as a judgement call.
        known = _decided()
        known.statements.append(SimpleNamespace(**dict(vars(known.statements[0]), holder='ERICA HOPPER')))
        self.assertEqual(_prove(knowledge=CaseKnowledge(accounts=[known]))['holder_basis'], ph.HOLDER_BASIS)

    def test_the_proof_version_counts_the_rule(self):
        with open(vr.__file__) as source:
            self.assertIn('PRINTED_HOLDERS', source.read().split('PROOF_VERSION = 1', 1)[1].split('METADATA_KEY', 1)[0])


class HelpersTest(unittest.TestCase):
    def test_covers_and_split(self):
        self.assertTrue(ph.covers(BOTH, 'ERICA HOPPER', ['ERICA MCCAULEY']))
        self.assertFalse(ph.covers(BOTH, 'ERICA HOPPER', ['JOHN DOE']))
        self.assertFalse(ph.covers(['ERICA HOPPER'], 'ERICA HOPPER', []))
        self.assertTrue(ph.split(BOTH, 'ERICA HOPPER', ['ERICA MCCAULEY']))
        self.assertFalse(ph.split(BOTH, 'ERICA HOPPER', ['ERICA HOPPER']))

    def test_holders_by_statement_lists_each_name_with_its_statements(self):
        self.assertEqual(ph.holders_by_statement([
            ('ERICA HOPPER', '2022-02-08', '2022-03-10'), ('ERICA MCCAULEY', '2020-10-08', '2020-11-09'),
            ('ERICA  MCCAULEY', '2021-01-11', '2021-02-07'), ('', '2021-03-01', '2021-03-31')]), [
            dict(name='ERICA MCCAULEY', statements=2, first='2020-10-08', last='2021-02-07'),
            dict(name='ERICA HOPPER', statements=1, first='2022-02-08', last='2022-03-10')])

    def test_the_sentence_says_it_is_a_judgement_and_decides_no_holder(self):
        text = ph.judgement_sentence(BOTH, 'ERICA HOPPER', 197)
        self.assertIn('printed under different holder names on different statements (ERICA MCCAULEY / ERICA HOPPER)', text)
        self.assertIn('attributed to ERICA HOPPER, the name printed on it (page 197)', text)
        self.assertIn('which person holds the account has not been established', text)


class DetectTest(unittest.TestCase):
    def _document(self, holder='ERICA HOPPER'):
        return SimpleNamespace(id=uuid.uuid4(), case_id=uuid.uuid4(), metadata_=dict(
            statement_import_statement_id='k1',
            statement_import_request=dict(currency='USD', holder=holder, rows=[])))

    def _file(self, **outcome):
        record = dict(status='proved', holder_basis=ph.HOLDER_BASIS, holder='ERICA HOPPER', holder_names=BOTH,
                      holder_page=197, holder_decision=DECISION)
        record.update(outcome)
        return SimpleNamespace(metadata_={vr.METADATA_KEY: {'k1': record}})

    def test_the_saved_statement_records_the_judgement_call(self):
        period = SimpleNamespace(id=uuid.uuid4(), currency='USD', opening_balance_minor=0, closing_balance_minor=0)
        found = [f for f in judgements.detect(self._document(), period, [], file=self._file())
                 if f['rule_id'] == ph.RULE_ID]
        self.assertEqual(len(found), 1)
        call = found[0]
        self.assertEqual((call['subject_type'], call['subject_id'], call['target_key']),
                         ('statement_period', period.id, 'holder'))
        self.assertIn('attributed to ERICA HOPPER, the name printed on it (page 197)', call['summary'])
        self.assertEqual(call['evidence']['decided_by'], 'Claude (for Neil Byrne)')
        self.assertEqual(call['evidence']['holders'], BOTH)
        self.assertEqual(judgements.category(ph.RULE_ID), 'holder')
        self.assertIn(ph.RULE_ID, judgements.STATEMENT_ROW_RULES)

    def test_no_call_without_the_basis_or_when_a_person_changed_the_holder(self):
        period = SimpleNamespace(id=uuid.uuid4(), currency='USD', opening_balance_minor=0, closing_balance_minor=0)
        for document, file in ((self._document(), self._file(holder_basis=None)),
                               (self._document(), self._file(status='not_proved')),
                               (self._document(holder='SOMEONE ELSE'), self._file()),
                               (self._document(), None)):
            self.assertFalse([f for f in judgements.detect(document, period, [], file=file) if f['rule_id'] == ph.RULE_ID])


class DecisionTest(fixture.DuplicateTestCase):
    def _actor(self):
        return Actor(name='Claude (for Neil Byrne)', email=self.user.email, user_id=self.user.id)

    def _saved(self, holder, start, end):
        document = self.make_document()
        self.make_period(document, bounds=PeriodBounds.printed(start, end))
        document.document_type = 'statement_review'
        document.metadata_ = dict(statement_import_request=dict(holder=holder, institution='Barclays',
                                                                account_number=self.account.identifier_as_printed))
        self.db.commit()
        return document

    def test_the_decision_is_recorded_before_anything_and_read_back(self):
        before = ph.fingerprint(self.db, self.case.id)
        decided = ph.record_decision(self.db, case_id=self.case.id, account_id=self.account.id, holders=BOTH,
                                     actor=self._actor(), reason='Neil Byrne decided each statement keeps its printed holder.')
        self.db.commit()
        self.assertEqual(decided['holders'], BOTH)
        event = self.db.scalar(select(AdjudicationEvent).where(AdjudicationEvent.decision == 'keep_printed_holders'))
        self.assertEqual((event.subject_type, event.subject_id, event.actor_name),
                         ('account', self.account.id, 'Claude (for Neil Byrne)'))
        self.assertEqual(event.after, dict(rule='as_printed', holders=BOTH))
        self.assertEqual(ph.decisions(self.db, self.case.id)[str(self.account.id)]['holders'], BOTH)
        self.assertEqual(ph.decisions(self.db, self.other_case.id), {})
        self.assertNotEqual(ph.fingerprint(self.db, self.case.id), before)
        # The same names again: the decision stands, nothing new is written.
        ph.record_decision(self.db, case_id=self.case.id, account_id=self.account.id, holders=list(reversed(BOTH)),
                           actor=self._actor(), reason='again')
        self.db.commit()
        self.assertEqual(len(self.db.scalars(select(AdjudicationEvent).where(
            AdjudicationEvent.decision == 'keep_printed_holders')).all()), 1)
        # The account keeps its own holder: nothing is renamed.
        self.db.refresh(self.account)
        self.assertIsNone(self.account.holder_name)

    def test_it_refuses_one_name_and_an_account_of_another_case(self):
        with self.assertRaises(ph.PrintedHoldersError):
            ph.record_decision(self.db, case_id=self.case.id, account_id=self.account.id,
                               holders=['ERICA HOPPER', 'Erica  Hopper'], actor=self._actor(), reason='x')
        with self.assertRaises(ph.PrintedHoldersError):
            ph.record_decision(self.db, case_id=self.case.id, account_id=self.other_account.id, holders=BOTH,
                               actor=self._actor(), reason='x')

    def test_case_knowledge_carries_it_to_the_proof(self):
        self._saved('ERICA MCCAULEY', date(2026, 1, 1), date(2026, 1, 31))
        known = case_knowledge(self.db, self.case.id, use_cache=False).accounts
        self.assertEqual([k.printed_holders for k in known], [[]])
        ph.record_decision(self.db, case_id=self.case.id, account_id=self.account.id, holders=BOTH,
                           actor=self._actor(), reason='Neil Byrne decided.')
        self.db.commit()
        known = case_knowledge(self.db, self.case.id).accounts
        self.assertEqual([k.printed_holders for k in known], [BOTH])
        self.assertEqual(known[0].printed_holders_decision['actor_name'], 'Claude (for Neil Byrne)')

    def test_the_account_history_reads_each_statements_printed_holder(self):
        from services.financial.account_history import _printed_holders
        first = self._saved('ERICA MCCAULEY', date(2026, 1, 1), date(2026, 1, 31))
        second = self._saved('ERICA HOPPER', date(2026, 2, 1), date(2026, 2, 28))
        reviewed = self._saved('ERICA HOPPER', date(2026, 3, 1), date(2026, 3, 31))
        reviewed.metadata_ = dict(reviewed.metadata_, statement_details_review=dict(details=dict(holder='E HOPPER')))
        self.db.commit()
        self.assertEqual(_printed_holders(self.db, {first.id, second.id, reviewed.id}),
                         {first.id: 'ERICA MCCAULEY', second.id: 'ERICA HOPPER', reviewed.id: 'E HOPPER'})


if __name__ == '__main__':
    unittest.main()
