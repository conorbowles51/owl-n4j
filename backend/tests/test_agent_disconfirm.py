"""agent-disconfirm: a whole-case sweep for what breaks a theory.

The count of model reads is true before they start; results are proposals only a person can accept; nothing found
states what was searched and what was out of reach and never reads as support; what the theory needs and the case
lacks is listed with its reason; a failed or stopped run says what was not read and only that goes out again.
"""
from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from postgres.base import Base
from postgres.models.agent_proposals import AgentProposalSourceOpen
from postgres.models.case import Case
from postgres.models.case_context import CaseContext, CaseMandateVersion
from postgres.models.evidence import EvidenceFile
from postgres.models.financial import FinancialAccount
from postgres.models.financial_judgements import FinancialJudgement
from postgres.models.user import User
from postgres.models.workspace_ai import WorkspaceAIOutput
from postgres.models.workspace_entry import (WorkspaceEntry, WorkspaceEntryEvent, WorkspaceEntryLink,
                                             WorkspaceEntryRevision)
from services import workspace_ai_service as A
from services.agent import disconfirm as D, proposals, workspace_proposals as W
from services.agent import workflows

TABLES = [User.__table__, Case.__table__, CaseMandateVersion.__table__, CaseContext.__table__, EvidenceFile.__table__,
          WorkspaceEntry.__table__, WorkspaceEntryRevision.__table__, WorkspaceEntryLink.__table__,
          WorkspaceEntryEvent.__table__, WorkspaceAIOutput.__table__, AgentProposalSourceOpen.__table__,
          FinancialJudgement.__table__]
MODEL = dict(provider='deepseek', model_id='deepseek-v4-pro', others_configured=[],
             words='One model read this: deepseek-v4-pro. No other model is configured.')


@pytest.fixture()
def db(tmp_path, monkeypatch):
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine, tables=TABLES)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(D, '_models', lambda session: dict(MODEL))
    monkeypatch.setattr(D, '_record_cost', lambda session, item, model, usage, what: 0.25)
    monkeypatch.setattr(D, '_case_index', lambda session, case_id: ('- no bank accounts', []))
    monkeypatch.setattr(D, '_census', lambda session, tools, case_id: dict(
        ledger=65, financial_sources=7, phones=2, documents=4, dossiers=0, messages=800, graph=12))
    monkeypatch.setattr(D, 'seen_not_produced', lambda *a, **k: ([], []))
    real_check = proposals.check_citations

    def check(session, case_id, citations):
        # The ledger's and phones' own tables are not in this schema: rows the fake tools gave stand as in the case.
        ours = [c for c in citations if c.startswith(('txn://t', 'rec://m'))]
        rest = [c for c in citations if c not in ours]
        return [dict(citation=c, scheme=c[:3], status='valid', label=c) for c in ours] + (
            real_check(session, case_id, rest) if rest else [])
    monkeypatch.setattr(proposals, 'check_citations', check)
    with factory() as session:
        owner = User(email="alex@example.test", name="Alex", password_hash="x")
        session.add(owner)
        session.flush()
        case = Case(title="Case", created_by_user_id=owner.id, owner_user_id=owner.id)
        other = Case(title="Other", created_by_user_id=owner.id, owner_user_id=owner.id)
        session.add_all([case, other])
        session.flush()
        doc = EvidenceFile(case_id=case.id, original_filename="lease.pdf", stored_path=str(tmp_path / "s.pdf"), size=1,
                           sha256="a" * 64, status="processed", created_by_id=owner.id)
        foreign = EvidenceFile(case_id=other.id, original_filename="f.pdf", stored_path=str(tmp_path / "f.pdf"), size=1,
                               sha256="b" * 64, status="processed", created_by_id=owner.id)
        theory = WorkspaceEntry(case_id=case.id, entry_type='theory', title='Juniper never paid Ashdown',
                                body='Emrys Juniper never paid Dorian Ashdown anything.', lifecycle_state='proposed',
                                review_state='accepted', author_user_id=owner.id, version=1)
        session.add_all([doc, foreign, theory])
        session.commit()
        session.info.update(owner=owner, case=case, other=other, doc=doc, foreign=foreign, theory=theory)
        yield session
    engine.dispose()


EXPECTATIONS = {"expectations": [
    {"claim": "If the theory is true, no payment goes from Juniper to Ashdown.",
     "would_contradict": "A payment to Ashdown.", "people": ["Dorian Ashdown"], "terms": ["Ashdown"],
     "document_queries": ["payment to Ashdown"], "start": None, "end": None,
     "needs": [{"kind": "phone", "who": "Dorian Ashdown", "why": "His side of the messages."}]},
    {"claim": "If the theory is true, no message discusses a repayment.", "would_contradict": "A message about one.",
     "people": [], "terms": ["repay"], "document_queries": [], "start": "2024-01-01", "end": "not a date", "needs": []},
]}


class FakeTools:
    """The agent's tools: every surface answers from what the test gave it."""

    def __init__(self, doc, fail=()):
        self.doc, self.fail, self.calls = doc, set(fail), []

    def call(self, name, **kw):
        self.calls.append((name, kw))
        if name in self.fail:
            raise D.SearchFailed(f'{name} is down')
        if name == 'get_financial_transactions':
            if kw.get('search') == 'Ashdown':
                return dict(items=[dict(cite='txn://t1', direction='debit', transaction_date='2023-11-11', amount_minor=10872,
                                        currency='USD', currency_exponent=2, description='Transfer To Dorian Ashdown')],
                            total_matching=1, has_more=False)
            return dict(items=[], total_matching=0, has_more=False)
        if name == 'phone_messages':
            if kw.get('search') == 'repay':
                return dict(items=[dict(rec='rec://m1', time='2024-01-03', phone='C1', kind='message', body='I repay you Friday',
                                        **{'from': 'Emrys'}, to=['Dorian'])], total_matching=1, has_more=False)
            return dict(items=[], total_matching=0, has_more=False)
        if name == 'phone_places':
            return dict(items=[], total_matching=0, has_more=False)
        if name == 'phone_coverage':
            return dict(items=[dict(phone='C1', owner='Emrys Juniper', first_event='2023-11-01', last_event='2024-05-31')])
        if name == 'search_documents':
            return dict(available=True, search='word', results=[], total=0, next_offset=None,
                        search_coverage=dict(note='word search', meaning_reason='quota', case_documents=4,
                                             searchable_documents=3, documents_without_text=1))
        if name == 'search_graph_entities':
            return dict(entities=[])
        raise AssertionError(name)


def reader_of(by_item):
    """A model: the first answer gives expectations; a read answers by the word it finds in the prompt."""
    calls = []

    def read(prompt):
        calls.append(prompt)
        if 'List every checkable expectation' in prompt:
            return json.dumps(EXPECTATIONS), dict(total_tokens=100)
        for word, answer in by_item.items():
            if word in prompt:
                if isinstance(answer, Exception):
                    raise answer
                return json.dumps(answer), dict(total_tokens=50)
        return '{"findings": []}', dict(total_tokens=50)
    read.calls = calls
    return read


def planned(db, reader, tools=None):
    made = D.create(db, case_id=db.info['case'].id, theory_id=db.info['theory'].id, requested_by=db.info['owner'])
    return D.plan(db, sweep_id=made['id'], reader=reader, tools=tools or FakeTools(db.info['doc']))


def ran(db, reader, tools=None, limit=None):
    plan = planned(db, reader, tools)
    D.start(db, case_id=db.info['case'].id, sweep_id=plan['id'], limit=limit)
    return D.read(db, sweep_id=plan['id'], reader=reader)


AGAINST = {'findings': [{'title': 'A payment to Ashdown', 'why': 'The row shows 108.72 paid to Dorian Ashdown.',
                         'items': ['I1'], 'strength': 'contradicts'}]}


def test_the_count_of_reads_is_true_before_any_read_is_spent(db):
    reader = reader_of({})
    plan = planned(db, reader)
    assert len(reader.calls) == 1, 'the plan spends one model call'
    assert plan['stage'] == 'planned' and plan['job_status'] == 'completed'
    assert plan['reads']['total'] == 2 and plan['reads']['done'] == 0 and plan['reads']['items'] == 2
    assert plan['calls_stated'] == 3
    assert 'items' not in json.dumps(plan['reads']['failures'])
    # The candidates' text stays on the row, not on what a screen polls.
    assert 'Transfer To Dorian Ashdown' not in json.dumps(plan)
    # Started, the reads are exactly the count stated.
    D.start(db, case_id=db.info['case'].id, sweep_id=plan['id'])
    done = D.read(db, sweep_id=plan['id'], reader=reader)
    assert len(reader.calls) == done['calls_stated'] == 3


def test_a_finding_is_a_pending_proposal_never_a_persons_view(db):
    done = ran(db, reader_of({'Transfer To Dorian Ashdown': AGAINST}))
    rows = db.scalars(select(WorkspaceAIOutput).where(WorkspaceAIOutput.output_type == 'counter_argument')).all()
    assert len(rows) == 1 and rows[0].review_status == 'pending_review'
    assert rows[0].content['citations'] == ['txn://t1'] and rows[0].content['strength'] == 'contradicts'
    origin = rows[0].model_metadata['origin']
    assert origin['kind'] == 'model' or origin.get('model') == 'deepseek-v4-pro'
    assert rows[0].reviewed_by_user_id is None
    assert db.scalars(select(WorkspaceEntryLink)).all() == [], 'nothing reaches the theory before a person accepts'
    assert done['outcome']['findings'] == 1 and done['outcome']['complete']
    assert done['outcome']['expectations'][0]['sentence'] is None


def test_nothing_found_says_what_was_searched_and_out_of_reach_and_is_not_support(db):
    done = ran(db, reader_of({}), tools=FakeTools(db.info['doc'], fail=['search_graph_entities']))
    assert 'not support for the theory' in done['outcome']['headline']
    row = done['outcome']['expectations'][0]
    assert 'not support for the theory' in row['sentence']
    assert any(s.startswith('ledger: ') and '65 rows' in s for s in row['searched'])
    assert any(s.startswith('phones: ') and '800' in s for s in row['searched'])
    reach = ' '.join(row['out_of_reach'])
    assert 'meaning search is down (quota)' in reach and '1 of 4 documents hold no text' in reach
    assert 'graph: The search failed' in reach
    for word in ('holds', 'confirmed', 'survives', 'stands'):
        assert word not in done['outcome']['headline']


def test_word_hits_a_document_search_did_not_show_are_counted(db):
    tools = FakeTools(db.info['doc'])
    tools.call = lambda name, **kw: dict(available=True, search='word', total=1, next_offset=None, search_coverage=dict(
        meaning_reason='quota', case_documents=1), results=[dict(cite='doc://d/1', evidence_file_id='d', snippet='s',
                                                                  filename='f', document_word_hits=9)])
    _, cover = D.search_documents(tools, dict(document_queries=[], people=[], terms=['x']))
    assert cover['word_hits_not_read'] == 8
    assert 'further word hits' in D._surface_words('documents', cover, {})[1]


def test_a_case_with_no_phone_says_so(db, monkeypatch):
    monkeypatch.setattr(D, '_census', lambda *a: dict(ledger=65, phones=0, documents=1, messages=0, graph=0))
    done = ran(db, reader_of({}))
    assert any(r == 'phones: The case holds no phone.' for r in done['outcome']['expectations'][0]['out_of_reach'])


def test_a_failed_read_is_named_and_only_it_goes_out_again(db):
    reader = reader_of({'Transfer To Dorian Ashdown': RuntimeError('timed out')})
    done = ran(db, reader)
    assert done['reads']['failed'] == 1 and done['reads']['done'] == 1
    assert 'timed out' in done['reads']['failures'][0]['error']
    assert done['outcome']['not_read'] == 1 and not done['outcome']['complete']
    assert '1 of 2 reads finished; 1 did not' in done['outcome']['headline']
    assert 'not support' in done['outcome']['expectations'][0]['sentence']
    assert 'Not finished' in done['outcome']['expectations'][0]['sentence']
    before = len(reader.calls)
    D.start(db, case_id=db.info['case'].id, sweep_id=done['id'])
    again = D.read(db, sweep_id=done['id'], reader=reader_of({'Transfer To Dorian Ashdown': AGAINST}))
    assert again['reads']['done'] == 2 and again['outcome']['findings'] == 1 and len(reader.calls) == before


def test_a_limited_run_says_what_was_left(db):
    done = ran(db, reader_of({}), limit=1)
    assert done['reads']['done'] == 1 and done['reads']['pending'] == 1
    assert done['outcome']['headline'].startswith('Limited to 1 reads: 1 of 2 were not read.')
    assert not done['outcome']['complete']


def test_a_stop_is_a_stated_stop(db):
    plan = planned(db, reader_of({}))
    D.start(db, case_id=db.info['case'].id, sweep_id=plan['id'])
    D.stop(db, case_id=db.info['case'].id, sweep_id=plan['id'])
    done = D.read(db, sweep_id=plan['id'], reader=reader_of({}))
    assert done['outcome']['headline'].startswith('Stopped by a person after 0 of 2 reads.')


def test_a_restart_is_stated_and_keeps_the_reads(db):
    plan = planned(db, reader_of({}))
    D.start(db, case_id=db.info['case'].id, sweep_id=plan['id'])
    item = db.get(WorkspaceAIOutput, uuid.UUID(plan['id']))
    item.job_status = 'running'
    content = dict(item.content, heartbeat_at=(datetime.now(timezone.utc) - timedelta(seconds=600)).isoformat())
    content['reads'][0]['status'] = 'running'
    item.content = content
    db.commit()
    seen = D.get_view(db, case_id=db.info['case'].id, sweep_id=plan['id'])
    assert seen['job_status'] == 'failed' and 'restarted' in seen['error']
    assert seen['reads']['pending'] == 2 and seen['reads']['running'] == 0


def test_a_queued_sweep_that_lost_its_worker_does_not_hold_the_theory_for_ever(db):
    made = D.create(db, case_id=db.info['case'].id, theory_id=db.info['theory'].id, requested_by=db.info['owner'])
    item = db.get(WorkspaceAIOutput, uuid.UUID(made['id']))
    item.content = dict(item.content, heartbeat_at=(datetime.now(timezone.utc) - timedelta(seconds=600)).isoformat())
    db.commit()
    again = D.create(db, case_id=db.info['case'].id, theory_id=db.info['theory'].id, requested_by=db.info['owner'])
    assert again['id'] != made['id'] and again['created']


def test_a_stop_during_the_searches_is_said(db):
    made = D.create(db, case_id=db.info['case'].id, theory_id=db.info['theory'].id, requested_by=db.info['owner'])
    D.stop(db, case_id=db.info['case'].id, sweep_id=made['id'])
    plan = D.plan(db, sweep_id=made['id'], reader=reader_of({}), tools=FakeTools(db.info['doc']))
    assert plan['job_status'] == 'failed' and 'Stopped by a person during the searches' in plan['error']


def test_a_slow_search_keeps_the_heartbeat_going(db, monkeypatch):
    """Live 5 Nov: a search of 60 s between heartbeats read as a restart, and the page said the service had stopped."""
    import time
    monkeypatch.setattr(D, 'TICK_SECONDS', 0.02)
    beats = []
    real = D._save

    def counted(session, item, content, **fields):
        beats.append(content.get('step'))
        real(session, item, content, **fields)
    monkeypatch.setattr(D, '_save', counted)
    tools = FakeTools(db.info['doc'])
    original = tools.call

    def slow(name, **kw):
        time.sleep(0.15)
        return original(name, **kw)
    tools.call = slow
    made = D.create(db, case_id=db.info['case'].id, theory_id=db.info['theory'].id, requested_by=db.info['owner'])
    D.plan(db, sweep_id=made['id'], reader=reader_of({}), tools=tools)
    during = [b for b in beats if b and b.startswith('Searching the case for expectation 1')]
    assert len(during) >= 3, 'the heartbeat stops while a search runs'


def test_one_plan_asks_each_thing_once():
    tools = D.Tools.__new__(D.Tools)
    tools.answers, calls = {}, []

    class Fake:
        def func(self, **kw):
            calls.append(kw)
            return dict(data=dict(ok=True))

    class Context:
        result_store: dict = {}
    tools.tools, tools.context = dict(t=Fake()), Context()
    assert tools.call('t', query='a') == tools.call('t', query='a') == dict(ok=True)
    tools.call('t', query='b')
    assert len(calls) == 2


def test_a_live_heartbeat_is_not_a_restart(db):
    plan = planned(db, reader_of({}))
    D.start(db, case_id=db.info['case'].id, sweep_id=plan['id'])
    item = db.get(WorkspaceAIOutput, uuid.UUID(plan['id']))
    item.job_status = 'running'
    db.commit()
    assert D.get_view(db, case_id=db.info['case'].id, sweep_id=plan['id'])['job_status'] == 'running'


def test_a_model_failure_in_the_plan_is_named_and_can_be_run_again(db):
    def broken(prompt):
        raise RuntimeError('401 from the provider')
    plan = planned(db, broken)
    assert plan['job_status'] == 'failed' and '401' in plan['error'] and plan['stage'] == 'planning'
    with pytest.raises(proposals.ProposalError, match='count of reads is not known'):
        D.start(db, case_id=db.info['case'].id, sweep_id=plan['id'])
    assert D.create(db, case_id=db.info['case'].id, theory_id=db.info['theory'].id,
                    requested_by=db.info['owner'])['id'] != plan['id']


def test_a_second_press_joins_the_live_sweep(db):
    first = D.create(db, case_id=db.info['case'].id, theory_id=db.info['theory'].id, requested_by=db.info['owner'])
    second = D.create(db, case_id=db.info['case'].id, theory_id=db.info['theory'].id, requested_by=db.info['owner'])
    assert second['id'] == first['id'] and 'created' not in second


def test_a_finding_on_graph_alone_or_outside_the_case_is_refused_and_said(db):
    foreign = db.info['foreign']
    tools = FakeTools(db.info['doc'])
    original = tools.call

    def call(name, **kw):
        if name == 'search_graph_entities' and kw['query'] == 'Ashdown':
            return dict(entities=[dict(key='p1', name='Ashdown', type='Person', summary='Is a tenant of Juniper')])
        if name == 'get_entity_details':
            return dict(entity=dict(verified_facts=[]))
        if name == 'get_financial_transactions' and kw.get('search') == 'Dorian Ashdown':
            return dict(items=[dict(cite=f'doc://{foreign.id}/3', direction='debit', amount_minor=1, description='outside')],
                        total_matching=1, has_more=False)
        return original(name, **kw)
    tools.call = call
    answer = {'findings': [
        {'title': 'Graph only', 'why': 'A tenant.', 'items': ['I3'], 'strength': 'undercuts'},
        {'title': 'Outside', 'why': 'Another case.', 'items': ['I1'], 'strength': 'contradicts'},
        {'title': 'No item', 'why': 'x', 'items': ['I99'], 'strength': 'contradicts'}]}
    done = ran(db, reader_of({'outside': answer}), tools=tools)
    refused = {r['title']: r['why'] for r in done['refused']}
    assert 'rests on graph entities alone' in refused['Graph only']
    assert 'must be in this case' in refused['Outside']
    assert 'no title, reason or cited item' in refused['No item']
    assert done['proposals'] == []


def test_a_rerun_does_not_ask_a_person_twice(db):
    reader = reader_of({'Transfer To Dorian Ashdown': AGAINST})
    ran(db, reader)
    second = ran(db, reader)
    assert second['proposals'] == [] and len(second['repeats']) == 1
    assert len(db.scalars(select(WorkspaceAIOutput).where(WorkspaceAIOutput.output_type == 'counter_argument')).all()) == 1


def test_a_person_accepts_and_the_source_is_linked_as_contradicting(db):
    case, theory, owner = db.info['case'], db.info['theory'], db.info['owner']
    doc = db.info['doc']
    # A source a person already linked keeps its relationship.
    db.add(WorkspaceEntryLink(entry_id=theory.id, case_id=case.id, target_type='evidence', target_id=str(doc.id),
                              relationship_type='supports', created_by_user_id=owner.id))
    db.commit()
    db.refresh(theory)
    second = EvidenceFile(case_id=case.id, original_filename="receipt.pdf", stored_path="/tmp/r.pdf", size=1, sha256="c" * 64,
                          status="processed", created_by_id=owner.id)
    db.add(second)
    db.commit()
    stored = W._store(db, case_id=case.id, output_type='counter_argument', content=dict(
        title='A payment', body='Row shows it.', theory_id=str(theory.id), expectation='x', strength='contradicts'),
        checked=[dict(citation=c, label=c, status='valid') for c in (f'doc://{second.id}/4', f'doc://{doc.id}/2')],
        action=dict(action='add_counter_argument', theory_id=str(theory.id)),
        origin=proposals.agent_origin(for_name='Alex', model='deepseek-v4-pro', model_id='deepseek-v4-pro'),
        requested_by_user_id=owner.id)
    with pytest.raises(proposals.ProposalError):
        W.accept(db, case_id=case.id, output_id=stored['id'], reviewer=None)
    done = W.accept(db, case_id=case.id, output_id=stored['id'], reviewer=owner, via='ui')
    assert done['review_status'] == 'accepted'
    links = {l.target_id: l for l in db.scalars(select(WorkspaceEntryLink).where(WorkspaceEntryLink.entry_id == theory.id))}
    added = links[str(second.id)]
    assert added.relationship_type == 'contradicts' and added.source_anchor == dict(page=4)
    assert added.link_metadata['actor_origin']['origin']['model'] == 'deepseek-v4-pro'
    assert added.link_metadata['actor_origin']['accepted_by']['name'] == 'Alex'
    assert links[str(doc.id)].relationship_type == 'supports', "a person's link is never rewritten"
    shown = D.counter_arguments(db, case_id=case.id, theory_id=theory.id)
    assert shown[0]['accepted_by'] == 'Alex' and shown[0]['model_text'] == 'Row shows it.'
    tally = D.tally(db, case.id, theory.id)
    assert tally['counter_arguments'] == dict(total=1, accepted=1, rejected=0, waiting=0, precision=1.0)
    assert tally['red_cell']['total'] == 0
    kinds = {k['kind']: k for k in proposals.precision(db, case_id=case.id)['kinds']}
    assert kinds['counter_argument']['accepted'] == 1 and 'disconfirm' in kinds['counter_argument']['label']


def test_the_sweep_row_is_not_a_proposal_or_a_reviewable_output(db):
    case, theory = db.info['case'], db.info['theory']
    ran(db, reader_of({}))
    assert W.list_proposals(db, case_id=case.id)['total'] == 0
    assert A.list_outputs(db, case_id=case.id, target_type='theory', target_id=theory.id)['total'] == 0
    assert 'disconfirm_sweep' not in W.AGENT_OUTPUT_TYPES


def test_cost_is_summed_from_every_call(db):
    done = ran(db, reader_of({}))
    assert done['cost'] == dict(usd=0.75, tokens=200, calls=3)


def test_expectations_keep_only_what_parses():
    got = D.parse_expectations(json.dumps(EXPECTATIONS))
    assert [e['id'] for e in got] == ['E1', 'E2']
    assert got[1]['start'] == '2024-01-01' and got[1]['end'] is None
    assert got[0]['needs'][0]['kind'] == 'phone'
    with pytest.raises(proposals.ProposalError, match='expected form'):
        D.parse_expectations('no json')
    with pytest.raises(proposals.ProposalError, match='no checkable'):
        D.parse_expectations('{"expectations": []}')


def test_reads_are_of_a_known_size_and_taken_in_turn():
    exps = [dict(id='E1'), dict(id='E2')]
    big = [dict(cite=f'txn://{i}', surface='ledger', text='x' * 400) for i in range(5)]
    reads = D.split_reads(exps, dict(E1=big + big[:1], E2=big[:1]), limit=900)
    assert [r['id'] for r in reads] == ['E1.1', 'E2.1', 'E1.2', 'E1.3']
    assert sum(r['item_count'] for r in reads if r['expectation'] == 'E1') == 5, 'a repeated item is read once'
    assert reads[0]['parts'] == 3


def test_every_candidate_is_read_through_every_page(db):
    tools = FakeTools(db.info['doc'])

    def call(name, **kw):
        assert name == 'get_financial_transactions'
        rows = [dict(cite=f"txn://{kw['offset'] + i}", amount_minor=1, description='x') for i in range(D.PAGE)]
        if kw['offset'] >= 2 * D.PAGE:
            return dict(items=rows[:7], total_matching=207, has_more=False)
        return dict(items=rows, total_matching=207, has_more=True, next_offset=kw['offset'] + D.PAGE, revision='r')
    tools.call = call
    items, cover = D.search_ledger(tools, dict(people=[], terms=['x'], start=None, end=None))
    assert len(items) == 207 and cover['rows_matched'] == 207


def test_a_phones_only_case_has_no_ledger_rather_than_zero_rows(db):
    tools = FakeTools(db.info['doc'])
    tools.call = lambda name, **kw: dict(available=False, no_financial_evidence=True, reason='No financial evidence.')
    items, cover = D.search_ledger(tools, dict(people=[], terms=['x'], start=None, end=None))
    assert items == [] and cover == dict(reachable=False, reason='No financial evidence.')


ACCOUNTS = [dict(id=str(uuid.uuid4()), holder='EMRYS JUNIPER', institution='Synthetic Community Bank',
                 number='000555010/0100', currency='USD')]


def test_absences_each_carry_their_reason(db, monkeypatch):
    from services.financial import coverage_query
    monkeypatch.setattr(coverage_query, 'requested_statement_coverage', lambda *a, **k: dict(
        available=True, requested_days=60, currencies=[dict(gaps=[dict(start='2024-03-01', end='2024-03-31', days=31)])]))
    exps = [dict(id='E1', needs=[
        dict(kind='statement_period', who='Emrys Juniper', institution=None, ending=None, start='2024-02-01',
             end='2024-03-31', why='Payments would show.'),
        dict(kind='statement_period', who='Nell Merriweather', institution=None, ending=None, start=None, end=None, why=None),
        dict(kind='account', who=None, institution='Harbour Bank', ending='4471', start=None, end=None, why='Named.'),
        dict(kind='phone', who='Emrys Juniper', institution=None, ending=None, start=None, end=None, why=None),
        dict(kind='phone', who='Dorian Ashdown', institution=None, ending=None, start=None, end=None, why='His side.'),
        dict(kind='call_records', who='Emrys Juniper', institution=None, ending=None, start='2022-01-01', end='2022-02-01',
             why='Calls.'),
    ])]
    census = dict(phones=1)
    got = D.absences(db, FakeTools(db.info['doc']), db.info['case'].id, exps, ACCOUNTS, census, 'theory text')
    what = {a['what']: a for a in got['items']}
    gap = what['Statements of EMRYS JUNIPER · Synthetic Community Bank · ending 0100, 2024-03-01 to 2024-03-31']
    assert '31 days of the 60' in gap['reason'] and gap['why'] == 'Payments would show.'
    assert 'No account in the case matches' in what['Statements of Nell Merriweather, no period given']['reason']
    assert 'Account: Harbour Bank · ending 4471' in what
    assert 'A phone of Emrys Juniper' not in what, 'a phone the case holds is not absent'
    assert 'owners: Emrys Juniper' in what['A phone of Dorian Ashdown']['reason']
    assert 'outside this period' in what['Call records of Emrys Juniper, 2022-01-01 to 2022-02-01']['reason']
    assert got['needs'] == 6 and 'not that the thing does not exist' in got['limitation']


def test_an_absence_check_that_fails_is_said(db, monkeypatch):
    def broken(*a, **k):
        raise RuntimeError('down')
    monkeypatch.setattr(D, '_statement_absences', broken)
    exps = [dict(id='E1', needs=[dict(kind='statement_period', who='Emrys', institution=None, ending=None, start=None,
                                      end=None, why=None)])]
    got = D.absences(db, FakeTools(db.info['doc']), db.info['case'].id, exps, ACCOUNTS, dict(phones=0), '')
    assert got['not_checked'] == ['E1: statement period for Emrys could not be checked.']


def test_accounts_match_by_ending_or_by_holder_and_bank():
    assert D.match_accounts(ACCOUNTS, dict(ending='0100'))
    assert not D.match_accounts(ACCOUNTS, dict(ending='9999', who='Emrys Juniper'))
    assert D.match_accounts(ACCOUNTS, dict(who='Emrys Juniper', institution='Synthetic Community'))
    assert not D.match_accounts(ACCOUNTS, dict(who='Emrys Juniper', institution='Harbour Bank'))
    assert not D.match_accounts(ACCOUNTS, dict())


def test_the_agent_workflow_runs_the_same_sweep():
    w = workflows.get('disconfirm-theory')
    have = workflows.registered_tool_names()
    assert {'plan_theory_sweep', 'propose_counter_arguments'} <= have
    block = workflows.render_block(w, tools=have)
    assert 'not in this build' not in block and 'State the count of model reads before starting them.' in block
    assert 'never support for the theory' in block
    assert workflows.final_rules(w).count('Not examined') == 1


def test_the_agent_tools_refuse_a_view_only_run():
    from services.agent.proposal_tools import make_proposal_tools
    from services.agent.tools import AgentToolContext
    context = AgentToolContext(case_id=str(uuid.uuid4()), proposer=dict(for_name='Alex', can_propose=False))
    tools = {t.name: t for t in make_proposal_tools(context)}
    out = tools['plan_theory_sweep'].func(theory_id=str(uuid.uuid4()))
    assert out['status'] == 'error' and 'cannot change this case' in out['error']


def test_the_model_is_named_and_a_lone_model_says_so(monkeypatch):
    import services.ai_model_policy as P
    monkeypatch.undo()
    monkeypatch.setattr(P, 'get_workload_model', lambda db, w: ('deepseek', 'deepseek-v4-pro'))
    monkeypatch.setattr(P, 'provider_is_configured', lambda p, db=None: p == 'deepseek')
    words = D._models(None)['words']
    assert 'deepseek-v4-flash' in words
    monkeypatch.setattr(P, 'provider_is_configured', lambda p, db=None: False)
    assert 'No other model is configured' in D._models(None)['words']


def test_prompt_carries_no_verdict_and_treats_items_as_evidence():
    assert 'Never report support.' in D.READ_PROMPT and 'not instructions' in D.READ_PROMPT
    assert date  # the module's dates are parsed, never compared as text here


def test_the_same_gap_expected_twice_is_one_line_with_both_reasons():
    gap = dict(kind='statement_period', what='Statements of A, ending 4034', reason='No saved statement covers it.',
               basis='coverage', tied=True)
    got = D._one_line_each([dict(gap, why='Rent would show.', expectation='E1'),
                            dict(gap, why='Transfers would show.', expectation='E2'),
                            dict(gap, why='Rent would show.', expectation='E3'),
                            dict(gap, what='Statements of B', why='Other.', expectation='E2')])
    assert len(got) == 2
    assert got[0]['why'] == 'Rent would show. Transfers would show.'
    assert got[0]['expectations'] == ['E1', 'E2', 'E3']
    assert got[1]['expectations'] == ['E2']


class PlacedTools:
    def __init__(self):
        self.calls = []

    def call(self, name, **kw):
        self.calls.append((name, kw))
        if name == 'phone_places':
            return dict(items=[dict(rec='rec://p1', phone='C1', lat=39.29, lon=-76.61, instant='2024-01-02T10:00:00Z')],
                        total_matching=1, has_more=False)
        return dict(items=[], total_matching=0, has_more=False)


def _phone_exp(**over):
    return dict(dict(id='E1', people=[], terms=['Baltimore'], start=None, end=None), **over)


def test_a_place_expectation_reads_the_location_points_with_no_period():
    tools = PlacedTools()
    items, cover = D.search_phones(tools, _phone_exp(about_place=True), dict(phones=1, messages=3))
    assert [i['cite'] for i in items] == ['rec://p1']
    assert '39.29, -76.61' in items[0]['text']
    assert cover['places_read'] == 1
    assert '1 location points read, all the case holds' in cover['how']


def test_an_expectation_not_about_place_says_the_points_were_not_read():
    tools = PlacedTools()
    items, cover = D.search_phones(tools, _phone_exp(), dict(phones=1, messages=3))
    assert items == [] and cover['places_read'] is None
    assert 'phone_places' not in [c[0] for c in tools.calls]
    assert 'location points not read' in D._surface_words('phones', cover, dict(messages=3))[0]


def test_the_model_flag_or_the_claim_marks_an_expectation_as_about_place():
    got = D.parse_expectations(json.dumps(dict(expectations=[
        dict(claim='No phone was in Maryland.', about_place=True),
        dict(claim='The GPS history shows only New York.'),
        dict(claim='No payment went to Ashdown.', about_place=False)])))
    assert [e['about_place'] for e in got] == [True, True, False]


def test_the_read_prompt_refuses_what_the_controls_showed_as_false():
    assert 'tell against the theory itself' in D.READ_PROMPT
    assert 'something not appearing among the items' in D.READ_PROMPT
    assert 'shares only a number' in D.READ_PROMPT


def test_the_ledger_line_says_every_row_was_searched():
    """The agent read '15 searches of 49 rows, 38 matched' as a sweep that reached 38 of 49 rows."""
    did, _ = D._surface_words('ledger', dict(reachable=True, searches=15, rows_found=38), dict(ledger=49))
    assert did == 'ledger: 15 searches over all 49 rows, 38 rows matched the words'


# ---------------------------------------------------------------------------
# Folding: one fact, one proposal (lx-agentruns). Measured 8 Nov 2026: 8 proposals on one sweep all said Arrendo
# held BBVA account 0038, across different expectations, because only an identical citation set counted as a repeat.
# ---------------------------------------------------------------------------

ONE_FACT = {
    'Transfer To Dorian Ashdown': {'findings': [{'title': 'A payment to Ashdown', 'why': 'The row shows 108.72 paid.',
                                                 'items': ['I1'], 'strength': 'contradicts'}]},
    'repay you Friday': {'findings': [{'title': 'Ashdown was repaid', 'why': 'The message says the money came.',
                                       'items': ['I1'], 'strength': 'contradicts'}]},
}
FOLD_WORDS = 'tidying the counter-argument proposals'


def test_two_findings_stating_one_fact_fold_into_one_keeping_both_citations(db):
    reader = reader_of(dict(ONE_FACT, **{FOLD_WORDS: {'groups': [['P2', 'P1']]}}))
    done = ran(db, reader)
    rows = db.scalars(select(WorkspaceAIOutput).where(WorkspaceAIOutput.output_type == 'counter_argument')).all()
    assert len(rows) == 1, 'one fact is one question for a person'
    kept = rows[0]
    titles = {'A payment to Ashdown': ['txn://t1'], 'Ashdown was repaid': ['rec://m1']}
    other = next(t for t in titles if t != kept.content['title'])
    assert set(kept.content['citations']) == {'txn://t1', 'rec://m1'}, 'every citation of the fact is kept'
    assert {c['cite'] for c in kept.citations} == {'txn://t1', 'rec://m1'}
    assert kept.content['folded'][0]['title'] == other, 'the folded wording stays visible on the kept proposal'
    assert kept.content['folded'][0]['citations'] == titles[other]
    assert kept.model_metadata['origin'], 'still marked as the model reading it is'
    assert [dict(p, citations=p['citations']) for p in done['proposals']] == [
        dict(id=str(kept.id), title=kept.content['title'], expectation=kept.content['expectation_id'],
             strength='contradicts', citations=2, folded=1)]
    assert done['fold']['calls'] == 1 and done['fold']['groups'] == 1 and done['fold']['folded'] == 1
    assert done['calls_stated'] == 4 and len(reader.calls) == 4, 'the fold call is stated and spent once'
    tally = D.tally(db, db.info['case'].id, db.info['theory'].id)
    assert tally['counter_arguments']['total'] == 1, 'precision counts count a folded fact once'
    # A rerun treats the folded original's sources as already put to a person.
    prior = D._prior_sources(db, db.info['case'].id, db.info['theory'].id)
    assert frozenset(['txn://t1', 'rec://m1']) in prior
    assert frozenset(titles[other]) in prior


def test_two_facts_are_not_folded_and_the_prompt_keeps_a_shared_page_apart(db):
    reader = reader_of(dict(ONE_FACT, **{FOLD_WORDS: {'groups': []}}))
    done = ran(db, reader)
    rows = db.scalars(select(WorkspaceAIOutput).where(WorkspaceAIOutput.output_type == 'counter_argument')).all()
    assert len(rows) == 2 and len(done['proposals']) == 2, 'the test is the fact, never the citation set'
    assert done['fold'] == dict(calls=1, groups=0, folded=0, skipped=[], error=None)
    prompt_words = ' '.join(D.FOLD_PROMPT.split())
    assert 'Different facts are never grouped, even when they cite the same page or the same document' in prompt_words
    assert 'one page can hold two facts' in prompt_words
    assert 'When unsure, leave them apart' in prompt_words


def sweep_row(db):
    from postgres.models.workspace_ai import WorkspaceAIOutput as W
    return db.scalar(select(W).where(W.output_type == D.OUTPUT_TYPE))


def test_a_proposal_a_person_decided_is_never_folded_or_re_ranked(db):
    done = ran(db, reader_of(dict(ONE_FACT, **{FOLD_WORDS: {'groups': []}})))
    first = db.get(WorkspaceAIOutput, uuid.UUID(done['proposals'][0]['id']))
    first.review_status = 'accepted'
    db.commit()
    item = sweep_row(db)
    content = dict(item.content)
    D.fold_same_fact(db, item, content, db.info['theory'], reader_of({FOLD_WORDS: {'groups': [['P1', 'P2']]}}))
    rows = db.scalars(select(WorkspaceAIOutput).where(WorkspaceAIOutput.output_type == 'counter_argument')).all()
    assert len(rows) == 2, 'nothing a person acted on is deleted'
    assert db.get(WorkspaceAIOutput, first.id).review_status == 'accepted'
    assert content['fold']['skipped'] == [dict(id=str(first.id), why='a person already decided it')]
    assert content['fold']['calls'] == 1, 'one pending proposal leaves nothing to group, so no second call'


def test_a_proposal_a_person_opened_a_source_from_is_never_folded(db):
    done = ran(db, reader_of(dict(ONE_FACT, **{FOLD_WORDS: {'groups': []}})))
    opened = done['proposals'][1]['id']
    db.add(AgentProposalSourceOpen(case_id=db.info['case'].id, proposal_type='workspace_ai',
                                   proposal_id=uuid.UUID(opened), citation='rec://m1',
                                   user_id=db.info['owner'].id, user_email='alex@example.test'))
    db.commit()
    item = sweep_row(db)
    content = dict(item.content)
    fold_reader = reader_of({FOLD_WORDS: {'groups': [['P1', 'P2']]}})
    D.fold_same_fact(db, item, content, db.info['theory'], fold_reader)
    assert len(db.scalars(select(WorkspaceAIOutput).where(
        WorkspaceAIOutput.output_type == 'counter_argument')).all()) == 2
    assert content['fold']['skipped'] == [dict(id=opened, why='a person opened a source from it')]
    assert fold_reader.calls == [], 'one pending proposal leaves nothing to group'


def test_a_failed_fold_is_named_and_each_finding_stands_on_its_own(db):
    done = ran(db, reader_of(dict(ONE_FACT, **{FOLD_WORDS: RuntimeError('model down')})))
    assert done['job_status'] == 'completed' and done['stage'] == 'done'
    assert 'model down' in done['fold']['error']
    assert len(done['proposals']) == 2, 'unfolded, never dropped'
    assert len(db.scalars(select(WorkspaceAIOutput).where(
        WorkspaceAIOutput.output_type == 'counter_argument')).all()) == 2


def test_one_finding_makes_no_fold_call(db):
    reader = reader_of({'Transfer To Dorian Ashdown': AGAINST})
    done = ran(db, reader)
    assert done['fold'] is None or done['fold']['calls'] == 0
    assert len(reader.calls) == 3 and done['calls_stated'] == 3
