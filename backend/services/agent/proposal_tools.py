"""The agent's only write: tools that record a proposal for a person to decide (agent-proposals A, B).

Each tool records one proposal and changes nothing else. The case comes from the run, never from the model; the
model origin (which model, for whom, which run) is the run's. A run for a person who can only view the case gets a
plain refusal: a proposal is a write. Every proposal cites sources in the case; a citation outside it refuses the
proposal in the same words whether or not the source exists elsewhere.
"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from datetime import date
from typing import Any, Literal

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

log = logging.getLogger(__name__)

AFTER = ('Recorded as a proposal for a person to decide; nothing in the case changed. Tell the user it is waiting '
         'in {where} and that a person accepts it only after opening a cited source.')


@contextmanager
def _write_session():
    from postgres.session import _get_session_local
    with _get_session_local()() as session:
        yield session


class JudgementProposalArgs(BaseModel):
    kind: Literal['missing_month', 'category', 'counterparty'] = Field(
        ..., description="missing_month: a month no statement of an account covers; category: a payment's category "
                         "from the case's category library; counterparty: who the other side of a payment is.")
    why: str = Field(..., min_length=1, max_length=1200, description='One or two sentences a person checks against '
                                                                     'the cited source.')
    citations: list[str] = Field(default_factory=list, max_length=20,
                                 description='txn://, doc:// or rec:// links to the sources the proposal rests on.')
    account_id: str | None = Field(None, description='missing_month: the account.')
    month: str | None = Field(None, description='missing_month: YYYY-MM.')
    transaction_id: str | None = Field(None, description='category / counterparty: the payment.')
    category: str | None = Field(None, description='category: a name from the category library.')
    counterparty_kind: Literal['party', 'account'] | None = Field(None, description='counterparty: party or account.')
    counterparty_id: str | None = Field(None, description='counterparty: the id of the party or account.')


class EntryProposalArgs(BaseModel):
    entry_type: Literal['note', 'finding']
    title: str = Field(..., min_length=1, max_length=255)
    body: str = Field(..., min_length=1, max_length=8000)
    citations: list[str] = Field(..., min_length=1, max_length=20)


class LeadCardArgs(BaseModel):
    lead_result_id: str = Field(..., description='The id of an account lead from the phone money signals.')
    why: str = Field('', max_length=1200)


class TimelineProposalArgs(BaseModel):
    source_kind: Literal['transaction', 'workspace_entry', 'money_trail', 'phone_record']
    source_ids: list[str] = Field(..., min_length=1, max_length=200)
    event_date: date | None = Field(None, description='Required for a Workspace finding.')
    why: str = Field(..., min_length=1, max_length=1200)
    citations: list[str] = Field(default_factory=list, max_length=20)


class LinkProposalArgs(BaseModel):
    entry_id: str
    target_type: str = Field(..., description='A Workspace link target type, e.g. evidence, financial_transaction, '
                                              'phone_record.')
    target_id: str
    relationship: Literal['supports', 'contradicts', 'context']
    why: str = Field(..., min_length=1, max_length=1200)
    citations: list[str] = Field(..., min_length=1, max_length=20)


def make_proposal_tools(context) -> list[StructuredTool]:
    from services.agent.proposals import ProposalError, agent_origin

    def origin():
        who = context.proposer or {}
        return agent_origin(for_name=who.get('for_name') or '', for_user_id=who.get('for_user_id'),
                            model=who.get('model') or '', model_id=who.get('model_id') or '',
                            run_id=who.get('run_id'), thread_id=who.get('thread_id'))

    def call(name, where, work):
        who = context.proposer or {}
        if not who:
            return context.result(name, {'error': 'This run cannot record proposals.'},
                                  summary=f'{name}: no proposals in this run.', status='error',
                                  error='This run cannot record proposals.')
        if not who.get('can_propose'):
            message = ('The person this run is for can view this case but not change it, so no proposal was '
                       'recorded. Give the proposal in the answer instead.')
            return context.result(name, {'error': message}, summary=f'{name}: view-only, nothing recorded.',
                                  status='error', error=message)
        try:
            with _write_session() as session:
                item = work(session, origin())
        except ProposalError as exc:
            return context.result(name, {'error': str(exc), 'recorded': False},
                                  summary=f'{name} refused: {exc}', status='error', error=str(exc))
        data = dict(recorded=True, proposal=item, note=AFTER.format(where=where))
        return context.result(name, data, summary=f'{name}: proposal {item.get("id")} recorded for a person to decide.')

    def propose_judgement_call(**kw):
        args = JudgementProposalArgs(**kw)
        from services.agent import proposals as P

        def work(session, o):
            if args.kind == 'missing_month':
                return P.propose_missing_month(session, case_id=context.case_id, account_id=args.account_id,
                                               month=args.month, why=args.why, citations=args.citations, origin=o)
            if args.kind == 'category':
                return P.propose_category(session, case_id=context.case_id, transaction_id=args.transaction_id,
                                          category=args.category, why=args.why, citations=args.citations, origin=o)
            return P.propose_counterparty(session, case_id=context.case_id, transaction_id=args.transaction_id,
                                          link=dict(kind=args.counterparty_kind, id=args.counterparty_id),
                                          why=args.why, citations=args.citations, origin=o)
        return call('propose_judgement_call', 'the Judgement calls page', work)

    def propose_workspace_entry(**kw):
        args = EntryProposalArgs(**kw)
        from services.agent import workspace_proposals as W
        return call('propose_workspace_entry', 'Workspace proposals', lambda s, o: W.propose_entry(
            s, case_id=context.case_id, entry_type=args.entry_type, title=args.title, body=args.body,
            citations=args.citations, origin=o, requested_by_user_id=(context.proposer or {}).get('for_user_id')))

    def propose_lead_card(**kw):
        args = LeadCardArgs(**kw)
        from services.agent import workspace_proposals as W
        return call('propose_lead_card', 'Workspace proposals', lambda s, o: W.propose_lead_card(
            s, case_id=context.case_id, lead_result_id=args.lead_result_id, why=args.why, origin=o,
            requested_by_user_id=(context.proposer or {}).get('for_user_id')))

    def propose_timeline_addition(**kw):
        args = TimelineProposalArgs(**kw)
        from services.agent import workspace_proposals as W
        return call('propose_timeline_addition', 'Workspace proposals', lambda s, o: W.propose_timeline(
            s, case_id=context.case_id, source_kind=args.source_kind, source_ids=args.source_ids,
            event_date=args.event_date, why=args.why, citations=args.citations, origin=o,
            requested_by_user_id=(context.proposer or {}).get('for_user_id')))

    def propose_link(**kw):
        args = LinkProposalArgs(**kw)
        from services.agent import workspace_proposals as W
        return call('propose_link', 'Workspace proposals', lambda s, o: W.propose_link(
            s, case_id=context.case_id, entry_id=args.entry_id, target_type=args.target_type,
            target_id=args.target_id, relationship=args.relationship, why=args.why, citations=args.citations,
            origin=o, requested_by_user_id=(context.proposer or {}).get('for_user_id')))

    rule = (' Records a proposal only: nothing changes until a person accepts it after opening a cited source. Use '
            'it when the user asks you to propose, draft or suggest work, never to answer a question.')
    return [
        StructuredTool.from_function(
            func=propose_judgement_call, name='propose_judgement_call', args_schema=JudgementProposalArgs,
            description=('Propose a judgement call on the ledger: a missing statement month for an account (checked '
                         'against the statement continuity), a payment category from the library, or who the other '
                         'side of a payment is.' + rule)),
        StructuredTool.from_function(
            func=propose_workspace_entry, name='propose_workspace_entry', args_schema=EntryProposalArgs,
            description='Draft a Workspace note or finding with cited sources.' + rule),
        StructuredTool.from_function(
            func=propose_lead_card, name='propose_lead_card', args_schema=LeadCardArgs,
            description=('Draft a lead card from a phone account lead: institution, account ending, the period a '
                         'statement request would cover, alerts by class, each alert cited. Alerts are never '
                         'totalled.' + rule)),
        StructuredTool.from_function(
            func=propose_timeline_addition, name='propose_timeline_addition', args_schema=TimelineProposalArgs,
            description='Propose adding payments, transfers, findings or phone records to the case timeline.' + rule),
        StructuredTool.from_function(
            func=propose_link, name='propose_link', args_schema=LinkProposalArgs,
            description='Propose linking a source to a Workspace entry as supporting, contradicting or context.'
                        + rule),
    ]
