"""money_between: the one answer to "how much moved between A and B" (agent-ledger B).

The Graph pair edge (link_edges), the agent tool get_money_between and the ledger tool's identity groups must give
the same figures for the same pair on the same basis; these tests fail on code that has no money_between.
"""
import uuid
from datetime import date

import pytest

from postgres.base import Base
from postgres.models.enums import ProofClass, TransactionDirection
from postgres.models.financial_candidates import (
    FinancialCandidateFinalization, FinancialCandidateMapping, FinancialCandidateReview, FinancialExtractionCandidate)
from services.financial import money_between as MB
from services.phone import link_edges as LE
from tests.test_financial_duplicates import DuplicateTestCase


class MoneyBetweenTests(DuplicateTestCase):
    def setUp(self):
        super().setUp()
        Base.metadata.create_all(self.engine, tables=[model.__table__ for model in (
            FinancialCandidateMapping, FinancialExtractionCandidate,
            FinancialCandidateReview, FinancialCandidateFinalization)])
        self.account.currency = 'USD'
        self.account.holder_name = 'Synthetic holder'
        self.db.commit()
        self.doc = self.make_document()
        self.period = self.make_period(self.doc)
        self.doc.metadata_ = dict(statement_account_id=str(self.account.id),
                                  statement_import_request={'currency': 'USD'})
        self.db.commit()
        self.party_b = str(uuid.uuid4())

    def row(self, amount, *, direction=TransactionDirection.debit, proof=ProofClass.p2, link=True, currency='USD',
            day=date(2026, 1, 15), raw='Synthetic B Ltd'):
        r = self.add_row(self.period, self.doc, amount=amount, direction=direction)
        r.currency, r.proof_class, r.ordering_date, r.counterparty_raw = currency, proof.value, day, raw
        if link:
            r.metadata_ = {**(r.metadata_ or {}), 'investigation_labels': {'counterparty_link': {
                'kind': 'party', 'id': self.party_b, 'label': 'Synthetic B'}}}
        self.db.commit()
        return r

    def holder_party(self):
        from services.financial.account_parties import AccountPartyRequest, account_parties, set_account_party
        d = account_parties(self.db, case_id=self.case.id)
        d = set_account_party(self.db, case_id=self.case.id, request=AccountPartyRequest(
            expected_revision=d['revision'], account_ids=[self.account.id], new_party_name='Synthetic A',
            relationship={'role': 'holder'}, reason='Reviewed ownership'), actor=self.actor)
        self.db.commit()
        return next(p['id'] for p in d['parties'] if p['name'] == 'Synthetic A')

    def test_p0_to_p2_summed_per_currency_p3_stated_beside_and_label_rows_left_out(self):
        self.row(100_00)
        self.row(50_00, direction=TransactionDirection.credit)
        self.row(11_00, proof=ProofClass.p3)
        self.row(7_00, currency='EUR')
        self.row(99_00, link=False)                      # only a printed name: not between these two parties
        out = MB.money_between(self.db, self.case.id, None, None,
                               sides=({'parties': set(), 'accounts': {str(self.account.id)}},
                                      {'parties': {self.party_b}, 'accounts': set()}), phone_mentions=3)
        assert out['schema'] == MB.SCHEMA
        assert [t['currency'] for t in out['totals']] == ['EUR', 'USD']
        usd = out['totals'][1]
        assert (usd['paid_ab_minor'], usd['payments_ab'], usd['paid_ba_minor'], usd['payments_ba']) == (100_00, 1, 50_00, 1)
        assert usd['p3'] == {'paid_ab_minor': 11_00, 'payments_ab': 1, 'paid_ba_minor': 0, 'payments_ba': 0}
        assert out['payments'] == 4 and out['payments_by_class']['p3'] == 1
        # p4 is counted, never summed; the graph is named as navigation
        assert out['p4'] == {'money_mentioned_on_phones': 3, 'summed': False, 'available': True}
        assert 'never sum' in out['graph'].lower() or 'not a total' in out['graph']
        assert 'printed name' in out['basis']

    def test_an_account_side_by_id_and_a_side_from_another_case_is_not_in_this_case(self):
        self.row(100_00)
        with pytest.raises(MB.NotInCase) as exc:
            MB.resolve_side(self.db, self.case.id, 'account:%s' % uuid.uuid4())
        assert str(exc.value) == 'That account is not in this case.'
        with pytest.raises(MB.NotInCase) as exc2:
            MB.resolve_side(self.db, self.case.id, 'party:%s' % uuid.uuid4())
        assert str(exc2.value) == 'That person or business is not in this case.'
        with pytest.raises(MB.MoneyBetweenError):
            MB.parse_side('Synthetic B Ltd')               # a printed name is never a side
        side = MB.resolve_side(self.db, self.case.id, 'account:%s' % self.account.id)
        assert side['accounts'] == {str(self.account.id)} and side['label'].startswith('Synthetic holder')

    def test_a_party_side_holds_its_accounts_through_the_ledger_holder_resolver(self):
        self.row(100_00)
        self.row(40_00, proof=ProofClass.p3)
        party_a = self.holder_party()
        a = MB.resolve_side(self.db, self.case.id, {'kind': 'party', 'id': party_a})
        assert a['accounts'] == {str(self.account.id)} and a['label'] == 'Synthetic A'
        b = {'subject': {'kind': 'party', 'id': self.party_b}, 'label': 'Synthetic B', 'parties': {self.party_b},
             'accounts': set()}
        out = MB.money_between(self.db, self.case.id, None, None, sides=(a, b))
        assert out['totals'][0]['paid_ab_minor'] == 100_00 and out['totals'][0]['p3']['paid_ab_minor'] == 40_00
        assert out['a']['label'] == 'Synthetic A' and out['a']['accounts'] == 1

    def test_the_ledger_tool_identity_group_and_money_between_agree_on_one_account(self):
        """Measured on live (agent-ledger A): three surfaces disagreed. On one account and one reviewed identity
        the ledger tool's verified group equals money_between p0-p2, and its working group equals p0-p2 plus the
        p3 stated beside."""
        from services.agent.financial_ledger_tools import read_financial_ledger
        self.row(100_00)
        self.row(30_00, direction=TransactionDirection.credit)
        self.row(11_00, proof=ProofClass.p3)
        out = MB.money_between(self.db, self.case.id, 'account:%s' % self.account.id, None,
                               sides=(MB.resolve_side(self.db, self.case.id, 'account:%s' % self.account.id),
                                      {'parties': {self.party_b}, 'accounts': set()}))
        usd = out['totals'][0]
        key = 'identity:party:%s' % self.party_b
        for population, want_debit, want_credit in (
                ('verified', usd['paid_ab_minor'], usd['paid_ba_minor']),
                ('working', usd['paid_ab_minor'] + usd['p3']['paid_ab_minor'],
                 usd['paid_ba_minor'] + usd['p3']['paid_ba_minor'])):
            page = read_financial_ledger(self.db, case_id=self.case.id, account_ids=[self.account.id],
                                         population=population, view='groups', group_by='counterparty')
            group = next(g for g in page['items'] if g['group'] == key)
            assert (int(group['debits_minor']), int(group['credits_minor'])) == (want_debit, want_credit), population
            assert group['group_basis'] == 'reviewed_identity'

    def test_the_graph_pair_edge_reads_its_money_through_money_between(self):
        """link_edges.edges and edge_records take their money from money_between (one implementation)."""
        import inspect
        assert 'money_between(' in inspect.getsource(LE.edges)
        assert 'money_between(' in inspect.getsource(LE.edge_records)
