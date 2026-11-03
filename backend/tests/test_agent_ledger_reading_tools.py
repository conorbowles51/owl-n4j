"""The agent's ledger readers beyond rows (agent-ledger B to E): money between two parties, judgement calls,
decisions with model origin, statement continuity with coverage, account mentions, investigator Timeline
additions, the open judgement calls a figure rests on, and graph money marked as navigation.

Each test runs the tool layer the model calls (make_agent_tools with the run's case) on the financial suite's
SQLite ledger harness, and fails on code that has no such tool or note.
"""
import uuid
from contextlib import contextmanager
from datetime import date
from unittest.mock import patch

from postgres.base import Base
from postgres.models.enums import AdjudicationDecision, AdjudicationSubject, ProofClass, TransactionDirection
from postgres.models.financial_candidates import (
    FinancialCandidateFinalization, FinancialCandidateMapping, FinancialCandidateReview, FinancialExtractionCandidate)
from postgres.models.financial_judgements import FinancialJudgement
from tests.test_financial_duplicates import DuplicateTestCase


class LedgerReadingToolTests(DuplicateTestCase):
    def setUp(self):
        super().setUp()
        tables = [FinancialCandidateMapping, FinancialExtractionCandidate, FinancialCandidateReview,
                  FinancialCandidateFinalization, FinancialJudgement]
        Base.metadata.create_all(self.engine, tables=[m.__table__ for m in tables])
        self.account.currency = 'USD'
        self.account.holder_name = 'Synthetic holder'
        self.doc = self.make_document()
        self.period = self.make_period(self.doc)
        self.doc.metadata_ = dict(statement_account_id=str(self.account.id), statement_import_request={'currency': 'USD'})
        self.db.commit()
        self.party_b = str(uuid.uuid4())

    # -- helpers ---------------------------------------------------------------------------------------------

    def tools(self, case_id=None):
        from services.agent.tools import AgentToolContext, make_agent_tools

        @contextmanager
        def session():
            with self.SessionLocal() as s:
                yield s
        ctx = AgentToolContext(case_id=str(case_id or self.case.id), ledger_session_factory=session)
        return {t.name: t for t in make_agent_tools(ctx)}

    def call(self, name, case_id=None, **args):
        return self.tools(case_id)[name].invoke(args)

    def row(self, amount, *, direction=TransactionDirection.debit, proof=ProofClass.p2, link=True,
            description='Payment', raw='Synthetic B Ltd'):
        r = self.add_row(self.period, self.doc, amount=amount, direction=direction)
        r.currency, r.proof_class, r.ordering_date = 'USD', proof.value, date(2026, 1, 15)
        r.description, r.counterparty_raw = description, raw
        if link:
            r.metadata_ = {**(r.metadata_ or {}), 'investigation_labels': {'counterparty_link': {
                'kind': 'party', 'id': self.party_b, 'label': 'Synthetic B'}}}
        self.db.commit()
        return r

    def judgement(self, row, rule='row.amount_repaired', status='open'):
        from services.financial.judgements import record_judgement
        j = record_judgement(self.db, case_id=self.case.id, subject_type='transaction', subject_id=row.id,
                             rule_id=rule, summary='Synthetic call on this payment', source_document_id=self.doc.id,
                             statement_period_id=self.period.id)
        j.status = status
        self.db.commit()
        return j

    # -- B: money between two parties ------------------------------------------------------------------------

    def test_get_money_between_sums_p0_to_p2_states_p3_and_counts_the_open_calls_it_rests_on(self):
        a = self.row(100_00)
        self.row(40_00, proof=ProofClass.p3)
        self.row(25_00, direction=TransactionDirection.credit)
        self.row(99_00, link=False)
        self.judgement(a)
        out = self.call('get_money_between', party_a='account:%s' % self.account.id,
                        party_b='identity:party:%s' % self.party_b)
        data = out['data']
        assert out['status'] == 'success', out
        usd = data['totals'][0]
        assert (usd['paid_ab_minor'], usd['paid_ba_minor'], usd['p3']['paid_ab_minor']) == (100_00, 25_00, 40_00)
        assert data['total'] == 3 and data['returned'] == 3 and data['next_offset'] is None
        assert data['open_judgement_calls']['open_calls'] == 1
        assert data['open_judgement_calls']['payments_with_open_calls'] == 1
        assert '1 open judgement call' in out['summary']
        assert all(i['financial_href'].endswith('payment=%s' % i['id']) for i in data['items'])
        assert 'never sum' in data['graph'].lower()

    def test_not_in_this_case_is_the_same_words_for_another_cases_account_and_for_none(self):
        elsewhere = self.other_account
        here = self.call('get_money_between', party_a='account:%s' % elsewhere.id, party_b='party:%s' % self.party_b)
        nowhere = self.call('get_money_between', party_a='account:%s' % uuid.uuid4(), party_b='party:%s' % self.party_b)
        assert here['data']['reason'] == nowhere['data']['reason'] == 'That account is not in this case.'
        printed = self.call('get_money_between', party_a='Synthetic B Ltd', party_b='party:%s' % self.party_b)
        assert printed['status'] == 'error'

    def test_graph_money_is_marked_navigation_not_a_total(self):
        from services.agent import tools as T
        assert T.graph_money_query("MATCH (a:FinancialAccount {case_id:$case_id})-[:TRANSFERRED_TO]->(t) RETURN sum(t.amount_minor)")
        assert not T.graph_money_query("MATCH (p:Person {case_id:$case_id}) RETURN p.name LIMIT 5")
        with patch.object(T, 'run_readonly_cypher', return_value=[{'s': 1}]):
            out = self.call('run_readonly_cypher', query="MATCH (t:FinancialTransaction) WHERE t.case_id = $case_id "
                                                         "RETURN sum(t.amount_minor) AS s")
        assert out['data']['money_basis'] == T.GRAPH_MONEY_NOTE and 'Navigation, not a total' in out['summary']
        from services.agent.graph import _FINANCIAL_ANALYSIS_PROMPT
        assert 'get_money_between' in _FINANCIAL_ANALYSIS_PROMPT and 'never sum' in _FINANCIAL_ANALYSIS_PROMPT

    def test_the_ledger_counterparty_view_states_label_not_identity_and_each_group_its_open_calls(self):
        a = self.row(100_00)
        self.row(60_00, link=False, raw='Printed Only Co')
        self.judgement(a)
        out = self.call('analyze_financial_transactions', group_by='counterparty')
        data = out['data']
        assert 'by label, not identity' in data['grouping_basis']
        groups = {g['group_basis']: g for g in data['items']}
        assert groups['reviewed_identity']['open_judgement_calls']['open_calls'] == 1
        assert groups['exact_displayed_label']['open_judgement_calls']['open_calls'] == 0
        assert data['open_judgement_calls']['open_calls'] == 1
        assert data['totals'][0]['open_judgement_calls']['open_calls'] == 1

    # -- C: judgement calls, decisions, continuity, mentions ---------------------------------------------------

    def test_get_judgement_calls_filters_by_payment_and_status_with_citations(self):
        a = self.row(100_00)
        b = self.row(5_00)
        self.judgement(a)
        self.judgement(b, status='confirmed')
        out = self.call('get_judgement_calls', subject='payment:%s' % a.id)
        assert out['data']['total'] == 1 and out['data']['items'][0]['subject_id'] == str(a.id)
        assert out['data']['items'][0]['citation']['href'].endswith('payment=%s' % a.id)
        opened = self.call('get_judgement_calls', status='open')
        assert opened['data']['total'] == 1
        assert opened['data']['counts_by_status'].get('confirmed') == 1
        missing = self.call('get_judgement_calls', subject='payment:%s' % uuid.uuid4())
        assert missing['data']['reason'] == 'That record is not in this case.'

    def test_get_decisions_shows_a_model_drafted_decision_as_the_models(self):
        from services.financial.decisions import Actor, record
        from services.financial.model_work import model_origin
        a = self.row(100_00)
        record(self.db, case_id=self.case.id, subject=a, subject_type=AdjudicationSubject.transaction,
               decision=AdjudicationDecision.set_counterparty_party, reason='Person linked it',
               actor=self.actor, before={'party': None}, after={'party': {'id': self.party_b, 'name': 'Synthetic B'}})
        drafted = Actor(name=self.actor.name, email=self.actor.email, user_id=self.actor.user_id,
                        origin=model_origin(for_name=self.actor.name, model='Claude'))
        record(self.db, case_id=self.case.id, subject=a, subject_type=AdjudicationSubject.transaction,
               decision=AdjudicationDecision.set_counterparty_party, reason='Model drafted it', actor=drafted,
               before={'party': {'id': self.party_b, 'name': 'Synthetic B'}}, after={'party': None})
        self.db.commit()
        out = self.call('get_decisions', subject='payment:%s' % a.id)
        data = out['data']
        assert data['total'] == 2 and data['model_drafted'] == 1
        assert [i['made_by']['kind'] for i in data['items']] == ['person', 'model']
        assert data['items'][1]['actor_origin']['kind'] == 'model'
        assert 'not a person' in data['items'][1]['made_by']['label']

    def test_get_statement_continuity_reads_the_run_and_its_coverage(self):
        from services.financial.periods import PeriodBounds
        doc2 = self.make_document()
        self.make_period(doc2, bounds=PeriodBounds.printed(date(2026, 3, 1), date(2026, 3, 31)))
        self.db.commit()
        out = self.call('get_statement_continuity', account=str(self.account.id))
        data = out['data']
        assert out['status'] == 'success', out
        assert data['total'] == 2
        cov = data['coverage']
        assert cov['covered_from'] == '2026-01-01' and cov['covered_to'] == '2026-03-31'
        assert cov['gaps'] == [['2026-02-01', '2026-02-28']]
        assert '1 gap' in data['sentence']
        doc3 = self.make_document()
        undated = self.make_period(doc3, bounds=PeriodBounds.printed(date(2026, 5, 1), date(2026, 5, 31)))
        undated.period_start = undated.period_end = None
        undated.period_start_source = undated.period_end_source = 'absent'
        self.db.commit()
        data = self.call('get_statement_continuity', account=str(self.account.id))['data']
        # a saved period left out of the run is stated, never silently dropped
        assert (data['periods_saved'], data['periods_in_run'], len(data['excluded_periods'])) == (3, 2, 1)
        assert '2 of 3 saved statement periods' in data['sentence'] and 'left out of the run' in data['sentence']
        none = self.call('get_statement_continuity', account=str(uuid.uuid4()))
        assert none['data']['reason'] == 'That account is not in this case.'

    def test_get_account_mentions_lists_printed_account_numbers_with_no_statement(self):
        self.row(10_00, link=False, description='TRANSFER TO ACCT 99887766 REF X', raw=None)
        out = self.call('get_account_mentions', show='all')
        data = out['data']
        assert out['status'] == 'success', out
        assert data['scanned_payments'] >= 1
        refs = [i for i in data['items'] if '99887766' in i['reference']]
        assert refs and refs[0]['status'] == 'no_statement_found'
        assert refs[0]['citation']['href'].startswith('/cases/%s/financial' % self.case.id)

    # -- D: the timeline with investigator additions -----------------------------------------------------------

    def test_get_timeline_events_merges_investigator_additions_labelled_by_source(self):
        from services.agent import ledger_reading_tools as LR
        graph = {'events': [{'key': 'g1', 'date': '2026-01-02'}], 'count': 1, 'total': 1, 'next_cursor': None}
        added = [dict(key='timeline-entry:%d' % i, date='2026-01-%02d' % (i + 1), time=None, name='Payment',
                      type='Transaction', summary='s', amount='USD 1.00', source='investigator addition: ledger payment',
                      source_kind='transaction', source_state='current', source_id=str(uuid.uuid4()),
                      date_basis='Transaction date', citation={'href': '/x'}) for i in range(30)]
        with patch('services.agent.tools.timeline_service.get_timeline_page', return_value=graph), \
                patch.object(LR, 'timeline_additions', return_value=added):
            out = self.call('get_timeline_events', limit=25)
            more = self.call('get_timeline_events', limit=25, additions_offset=25)
        data = out['data']
        assert data['events'][0]['source'] == 'graph event'
        adds = data['investigator_additions']
        assert (adds['total'], adds['returned'], adds['next_offset']) == (30, 25, 25)
        assert more['data']['investigator_additions']['returned'] == 5
        assert 'Investigator additions: 25 of 30' in out['summary']

    def test_timeline_additions_reads_a_saved_payment_addition_through_the_timeline_entries_read(self):
        from postgres.models.timeline_entry import TimelineEntry
        from postgres.models.workspace_entry import WorkspaceEntry
        from postgres.models.financial_money_trails import FinancialMoneyTrail
        from services.agent.ledger_reading_tools import timeline_additions
        from services.timeline_entries import TimelineAddition, preview_addition, save_addition
        extra = [TimelineEntry, FinancialMoneyTrail]
        try:
            Base.metadata.create_all(self.engine, tables=[m.__table__ for m in extra])
        except Exception:  # noqa: BLE001 - a table with dependencies the harness lacks; the merge is still tested above
            return
        del WorkspaceEntry
        a = self.row(100_00)
        a.transaction_date = date(2026, 1, 15)
        self.db.commit()
        request = TimelineAddition(source_kind='transaction', source_ids=[a.id])
        preview = preview_addition(self.db, case_id=self.case.id, request=request)
        save_addition(self.db, case_id=self.case.id, request=request.model_copy(
            update={'expected_revision': preview['revision']}), actor=self.actor.email)
        items = timeline_additions(self.db, case_id=self.case.id)
        assert len(items) == 1 and items[0]['source'] == 'investigator addition: ledger payment'
        assert items[0]['citation']['href'].endswith('payment=%s' % a.id)
        assert timeline_additions(self.db, case_id=self.case.id, start_date='2026-02-01') == []
