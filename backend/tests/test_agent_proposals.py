"""agent-proposals A, C, F: the case agent's ledger proposals are judgement calls a person decides.

A proposal is recorded with origin ``agent`` and strength ``inferred`` only when deterministic code agrees it is
possible (a month inside a continuity gap; a category from the library a person has not chosen over; an identity the
payment does not already carry), cites sources in the case, changes nothing until a person accepts it, and records
whether the person opened a cited source first. Corrections and rejections reach the lessons inbox.
"""
import os
import tempfile
import unittest
import uuid
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
from uuid import UUID

from sqlalchemy import select

from postgres.base import Base
from postgres.models.agent_proposals import AgentProposalSourceOpen
from postgres.models.financial import FinancialAccount, FinancialSourceDocument, FinancialTransaction
from postgres.models.financial_judgements import FinancialJudgement
from postgres.models.financial_payment_category import FinancialPaymentCategory
from postgres.models.workspace_ai import WorkspaceAIOutput
from services.agent import proposals
from services.financial import judgements


def _origin():
    return proposals.agent_origin(for_name='Alex', model='DeepSeek V4 Pro', model_id='deepseek-v4-pro',
                                  run_id=uuid.uuid4())


class _Fixture(unittest.TestCase):
    def setUp(self):
        from tests.test_financial_statement_import import StatementImportTests
        self.f = StatementImportTests()
        self.f.setUp()
        self._inbox = tempfile.mkdtemp(prefix='loupe-proposals-', dir='/dev/shm')
        # Before the statement is saved: the category store remembers whether its table exists.
        Base.metadata.create_all(self.f.db.get_bind(), tables=[
            FinancialJudgement.__table__, FinancialPaymentCategory.__table__, AgentProposalSourceOpen.__table__,
            WorkspaceAIOutput.__table__])
        self.f.db.commit()
        self.receipt = self.f.confirm()
        self.db = self.f.db
        self.rows = list(self.db.scalars(select(FinancialTransaction).where(
            FinancialTransaction.source_document_id == UUID(self.receipt['source_document_id']))))
        self.row = self.rows[0]
        self.document = self.db.get(FinancialSourceDocument, UUID(self.receipt['source_document_id']))
        self.account = self.db.scalars(select(FinancialAccount).where(FinancialAccount.case_id == self.f.case.id)).first()
        self.user = SimpleNamespace(id=self.f.user.id, email=self.f.user.email, name=self.f.user.name)
        self.choices = mock.patch('services.financial.payment_categories._choices',
                                  return_value=['Travel', 'Cash withdrawal', 'Rent'])
        self.choices.start()

    def tearDown(self):
        self.choices.stop()
        self.f.tearDown()
        import shutil
        shutil.rmtree(self._inbox, ignore_errors=True)


class LedgerProposalTests(_Fixture):

    # -- recording ------------------------------------------------------------------------------------------------

    def _category(self, category='Travel', citations=()):
        return proposals.propose_category(self.db, case_id=self.f.case.id, transaction_id=self.row.id,
                                          category=category, why='The description names an airline.',
                                          citations=citations, origin=_origin())

    def test_a_category_proposal_is_an_agent_call_that_changes_nothing(self):
        item = self._category()
        self.assertTrue(item['created'])
        self.assertEqual((item['origin'], item['strength'], item['rule_id'], item['status']),
                         ('agent', 'inferred', 'proposal.category', 'open'))
        self.assertEqual((item['category'], item['priority']), ('agent_proposal', 3))
        self.assertIn(f'txn://{self.row.id}', item['proposal']['citations'])
        self.assertEqual(item['proposal']['model'], 'DeepSeek V4 Pro')
        self.db.expire_all()
        self.assertIsNone(self.db.get(FinancialPaymentCategory, self.row.id))  # nothing applied
        again = self._category()
        self.assertFalse(again['created'])
        self.assertEqual(again['id'], item['id'])
        # In the Judgement calls page, with its filters
        page = judgements.search(self.db, self.f.case.id, categories=['agent_proposal'])
        self.assertEqual([i['id'] for i in page['items']], [item['id']])

    def test_a_proposal_without_a_model_origin_or_outside_the_library_is_refused(self):
        with self.assertRaises(proposals.ProposalError):
            proposals.propose_category(self.db, case_id=self.f.case.id, transaction_id=self.row.id, category='Travel',
                                       why='x', origin=dict(kind='person', name='Alex'))
        with self.assertRaisesRegex(proposals.ProposalError, 'library'):
            self._category('Made up')
        with self.assertRaisesRegex(proposals.ProposalError, 'reason'):
            proposals.propose_category(self.db, case_id=self.f.case.id, transaction_id=self.row.id, category='Travel',
                                       why=' ', origin=_origin())

    def test_a_citation_outside_the_case_refuses_the_whole_proposal(self):
        with self.assertRaisesRegex(proposals.ProposalError, 'Not in this case'):
            self._category(citations=[f'txn://{uuid.uuid4()}'])
        with self.assertRaisesRegex(proposals.ProposalError, 'Not in this case'):
            self._category(citations=[f'doc://{uuid.uuid4()}/2'])
        with self.assertRaisesRegex(proposals.ProposalError, 'Not a source link'):
            self._category(citations=['https://example.com'])
        self.assertEqual(self.db.scalars(select(FinancialJudgement)).all(), [])

    def test_another_cases_payment_is_not_in_this_case(self):
        with self.assertRaisesRegex(proposals.ProposalError, 'Not in this case'):
            proposals.propose_category(self.db, case_id=uuid.uuid4(), transaction_id=self.row.id, category='Travel',
                                       why='x', origin=_origin())

    def test_the_agent_never_proposes_over_a_persons_category(self):
        from services.financial.payment_categories import record_person_choice
        record_person_choice(self.db, self.row, 'Rent', self.f.actor)
        self.db.commit()
        with self.assertRaisesRegex(proposals.ProposalError, 'A person already chose'):
            self._category()

    def test_strength_is_never_proved(self):
        self._category()
        self.assertEqual({j.strength for j in self.db.scalars(select(FinancialJudgement))}, {'inferred'})
        for rule in proposals.KINDS.values():
            self.assertEqual(judgements.RULES[rule][2], 'inferred')

    # -- missing months -------------------------------------------------------------------------------------------

    def _gap(self, earlier_end=date(2024, 1, 31), later_start=date(2024, 3, 1)):
        from services.financial.continuity import AccountContinuity, Seam, SeamAgreement, SeamKind
        link = lambda start, end: SimpleNamespace(period_id=uuid.uuid4(), document_id=self.document.id,
                                                  account_id=self.account.id, start=start, end=end)
        earlier, later = link(date(2024, 1, 1), earlier_end), link(later_start, date(2024, 3, 31))
        seam = Seam(account_id=self.account.id, earlier=earlier, later=later, kind=SeamKind.gap,
                    agreement=SeamAgreement.disagrees, uncovered_days=(later_start - earlier_end).days - 1)
        return AccountContinuity(account_id=self.account.id, periods=(earlier, later), seams=(seam,))

    def test_a_missing_month_is_recorded_only_inside_a_continuity_gap(self):
        with mock.patch('services.financial.continuity.read_account_continuity', return_value=self._gap()):
            item = proposals.propose_missing_month(self.db, case_id=self.f.case.id, account_id=self.account.id,
                                                   month='2024-02', why='March opens far from the January close.',
                                                   origin=_origin())
            self.assertEqual((item['rule_id'], item['target_key'], item['priority'], item['subject_type']),
                             ('proposal.missing_month', 'month:2024-02', 2, 'account'))
            self.assertIn(f'doc://{self.document.evidence_file_id}', item['proposal']['citations'])
            self.assertIn('February 2024', item['summary'])
            self.assertIn('29 days uncovered', item['summary'])
            with self.assertRaisesRegex(proposals.ProposalError, 'cover January 2024'):
                proposals.propose_missing_month(self.db, case_id=self.f.case.id, account_id=self.account.id,
                                                month='2024-01', why='x', origin=_origin())
            with self.assertRaisesRegex(proposals.ProposalError, 'not between two'):
                proposals.propose_missing_month(self.db, case_id=self.f.case.id, account_id=self.account.id,
                                                month='2025-06', why='x', origin=_origin())
            with self.assertRaisesRegex(proposals.ProposalError, 'YYYY-MM'):
                proposals.propose_missing_month(self.db, case_id=self.f.case.id, account_id=self.account.id,
                                                month='Feb', why='x', origin=_origin())

    def test_accepting_a_missing_month_changes_no_ledger_value(self):
        with mock.patch('services.financial.continuity.read_account_continuity', return_value=self._gap()):
            item = proposals.propose_missing_month(self.db, case_id=self.f.case.id, account_id=self.account.id,
                                                   month='2024-02', why='gap', origin=_origin())
        before = [(r.amount_minor, r.metadata_) for r in self.rows]
        done = proposals.confirm(self.db, case_id=self.f.case.id, judgement_id=UUID(item['id']), actor=self.f.actor,
                                 user=self.user)
        self.assertEqual(done['status'], 'confirmed')
        self.assertEqual(done['evidence']['applied'], dict(kind='missing_month', changed=False))
        self.db.expire_all()
        self.assertEqual(before, [(self.db.get(FinancialTransaction, r.id).amount_minor,
                                   self.db.get(FinancialTransaction, r.id).metadata_) for r in self.rows])

    # -- open the source before confirming (C) ---------------------------------------------------------------------

    def test_accept_records_whether_a_cited_source_was_opened_first(self):
        item = self._category()
        with self.assertRaisesRegex(proposals.ProposalError, 'not one this proposal cites'):
            proposals.record_open(self.db, case_id=self.f.case.id, proposal_type='judgement',
                                  proposal_id=item['id'], citation=f'txn://{uuid.uuid4()}', user=self.user)
        done = proposals.confirm(self.db, case_id=self.f.case.id, judgement_id=UUID(item['id']), actor=self.f.actor,
                                 user=self.user, via='api')
        self.assertEqual((done['evidence']['review']['source_opened'], done['evidence']['review']['via']),
                         (False, 'api'))
        self.assertIn('without opening a source', done['evidence']['applied']['reason'])
        # Applied through the person's label path, naming the model that proposed it
        self.db.expire_all()
        stored = self.db.get(FinancialPaymentCategory, self.row.id)
        self.assertEqual((stored.category, stored.origin), ('Travel', 'person'))
        self.assertEqual(stored.why, 'Proposed by DeepSeek V4 Pro (case agent), accepted by ' + self.f.actor.name)
        history = self.db.get(FinancialTransaction, self.row.id).metadata_['investigation_label_history'][-1]
        self.assertEqual(history['proposed_by']['judgement_id'], item['id'])
        self.assertEqual(history['proposed_by']['origin']['model'], 'DeepSeek V4 Pro')
        self.assertEqual(history['actor_email'], self.f.actor.email)
        # A second proposal, opened first
        other = proposals.propose_category(self.db, case_id=self.f.case.id, transaction_id=self.rows[1].id,
                                           category='Rent', why='Monthly to the landlord.', origin=_origin())
        proposals.record_open(self.db, case_id=self.f.case.id, proposal_type='judgement', proposal_id=other['id'],
                              citation=f'txn://{self.rows[1].id}', user=self.user)
        done = proposals.confirm(self.db, case_id=self.f.case.id, judgement_id=UUID(other['id']), actor=self.f.actor,
                                 user=self.user, via='ui')
        self.assertEqual((done['evidence']['review']['source_opened'], done['evidence']['review']['opened']),
                         (True, [f'txn://{self.rows[1].id}']))
        stats = proposals.precision(self.db, self.f.case.id)
        self.assertEqual(stats['confirmations'], dict(total=2, with_source_opened=1, without_source_opened=1))

    def test_a_model_cannot_accept_and_the_generic_confirm_refuses_proposals(self):
        from services.financial.model_work import model_actor
        item = self._category()
        claude = model_actor(for_name='Alex', for_email=self.f.actor.email, for_user_id=self.f.user.id)
        with self.assertRaises(judgements.JudgementError):
            proposals.confirm(self.db, case_id=self.f.case.id, judgement_id=UUID(item['id']), actor=claude,
                              user=self.user)
        with self.assertRaisesRegex(judgements.JudgementError, 'accept it from the proposal'):
            judgements.confirm(self.db, case_id=self.f.case.id, judgement_id=UUID(item['id']), actor=self.f.actor)

    # -- corrections and rejections feed the lessons ---------------------------------------------------------------

    def test_a_person_choosing_another_category_corrects_the_proposal_and_reaches_the_inbox(self):
        from services.financial.payment_labels import PaymentLabelsRequest, update_payment_labels
        item = self._category('Travel')
        inbox = Path(self._inbox) / 'JUDGEMENT-CORRECTIONS.md'
        with mock.patch('services.financial.judgement_inbox.INBOX', inbox), \
                mock.patch('services.manual_changes.INBOX', Path(self._inbox) / 'MANUAL-CHANGES.jsonl'):
            update_payment_labels(self.db, case_id=self.f.case.id, actor=self.f.actor, request=PaymentLabelsRequest(
                transactions=[dict(id=self.row.id, version=0)], category='Rent'))
        row = self.db.get(FinancialJudgement, UUID(item['id']))
        self.assertEqual(row.status, 'corrected')
        self.assertEqual(row.evidence['correction'], dict(before='Travel', after='Rent'))
        self.assertIn(item['id'], inbox.read_text())

    def test_reject_needs_a_reason_and_is_a_lesson(self):
        item = self._category()
        with self.assertRaisesRegex(proposals.ProposalError, 'Say why'):
            proposals.reject(self.db, case_id=self.f.case.id, judgement_id=UUID(item['id']), actor=self.f.actor,
                             user=self.user, reason=' ')
        done = proposals.reject(self.db, case_id=self.f.case.id, judgement_id=UUID(item['id']), actor=self.f.actor,
                                user=self.user, reason='It is a hotel, not an airline.')
        self.assertEqual(done['status'], 'rejected')
        inbox = Path(self._inbox) / 'JUDGEMENT-CORRECTIONS.md'
        from services.financial import judgement_inbox
        with mock.patch.object(judgement_inbox, 'INBOX', inbox):
            self.assertTrue(judgement_inbox.append_correction(self.db, done, statement=''))
            self.assertIn('(rejected)', inbox.read_text())
            self.assertEqual(judgement_inbox.missing(self.db), [])
        self.db.expire_all()
        self.assertIsNone(self.db.get(FinancialPaymentCategory, self.row.id))
        with self.assertRaisesRegex(proposals.ProposalError, 'already rejected'):
            proposals.confirm(self.db, case_id=self.f.case.id, judgement_id=UUID(item['id']), actor=self.f.actor,
                              user=self.user)

    # -- precision trend (F) ---------------------------------------------------------------------------------------

    def test_precision_counts_each_kind_per_week(self):
        a = self._category('Travel')
        b = proposals.propose_category(self.db, case_id=self.f.case.id, transaction_id=self.rows[1].id,
                                       category='Rent', why='x', origin=_origin())
        proposals.confirm(self.db, case_id=self.f.case.id, judgement_id=UUID(a['id']), actor=self.f.actor,
                          user=self.user)
        proposals.reject(self.db, case_id=self.f.case.id, judgement_id=UUID(b['id']), actor=self.f.actor,
                         user=self.user, reason='wrong')
        stats = proposals.precision(self.db, self.f.case.id)
        kind = next(k for k in stats['kinds'] if k['kind'] == 'category')
        self.assertEqual((kind['accepted'], kind['rejected'], kind['corrected'], kind['open'], kind['decided']),
                         (1, 1, 0, 0, 2))
        self.assertEqual(sum(w['accepted'] + w['rejected'] for w in kind['weeks']), 2)
        self.assertEqual(proposals.precision(self.db, uuid.uuid4())['kinds'], [])
        # Every case counts only the cases the reader can open (old code: every case in the system).
        self.assertEqual(proposals.precision(self.db, None, case_ids=[uuid.uuid4()])['kinds'], [])
        self.assertEqual(proposals.precision(self.db, None, case_ids=[self.f.case.id])['kinds'][0]['decided'], 2)

    def test_the_export_names_the_case_agent_not_a_hand_entry(self):
        self._category()
        page = judgements.search(self.db, self.f.case.id, everything=True)
        text = judgements.export_csv(page).decode('utf-8')
        self.assertIn('Case agent (model), for a person to decide', text)
        self.assertNotIn('Processing agent (by hand)', text)


class CounterpartyProposalTests(_Fixture):
    """The counterparty kind on the same fixture: a party of the case, applied through the person's link path."""

    def test_counterparty_proposal_names_an_identity_of_the_case(self):
        party = dict(id=str(uuid.uuid4()), name='Acme Travel Ltd')
        state = dict(parties=[party], accounts=[])
        with mock.patch('services.financial.account_parties.account_parties', return_value=state):
            item = proposals.propose_counterparty(self.db, case_id=self.f.case.id, transaction_id=self.row.id,
                                                  link=dict(kind='party', id=party['id']), why='Named on the page.',
                                                  origin=_origin())
            self.assertEqual((item['rule_id'], item['priority'], item['proposal']['value']['label']),
                             ('proposal.counterparty', 2, 'Acme Travel Ltd'))
            with self.assertRaises(proposals.ProposalError):
                proposals.propose_counterparty(self.db, case_id=self.f.case.id, transaction_id=self.row.id,
                                               link=dict(kind='party', id=str(uuid.uuid4())), why='x',
                                               origin=_origin())


if __name__ == '__main__':
    unittest.main()
