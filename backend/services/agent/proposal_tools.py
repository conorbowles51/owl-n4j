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
    dossier_id: str | None = Field(None, description='Optionally attach the saved entry to this existing dossier on acceptance.')
    event_date: date | None = Field(None, description='For a finding, optionally add its dated timeline event in the same acceptance.')


class DossierProposalArgs(BaseModel):
    operation: Literal['create', 'update', 'attach']
    dossier_id: str | None = Field(None, description='Existing dossier ID for update or attach.')
    fields: dict[str, str | None] = Field(default_factory=dict, description='Only display_name, summary, importance, dossier_type. '
                                        'Create needs display_name. Updates preserve unmentioned fields.')
    links: list[dict[str, str]] = Field(default_factory=list, max_length=50,
        description='Attachments with target_type and target_id, e.g. entry, evidence, agent_artifact. Existing links stay.')
    why: str = Field(..., min_length=1, max_length=1200)
    citations: list[str] = Field(..., min_length=1, max_length=20)


class SweepPlanArgs(BaseModel):
    theory_id: str = Field(..., description='The Workspace theory to test, from get_casework.')


class SweepReadArgs(BaseModel):
    sweep_id: str = Field(..., description='The sweep_id plan_theory_sweep returned.')
    limit: int | None = Field(None, ge=1, description='Only the first N reads. The result says what was left unread. '
                                                      'Leave empty to run all that the plan counted.')


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


class ControlClaimProposalArgs(BaseModel):
    person: str = Field(..., description='A person (dossier) name or id.')
    account: str = Field(..., description='A financial account id, or its ending (four or more digits).')
    start: str
    end: str
    why: str = Field('', max_length=1200)


class PaymentPurposeProposalArgs(BaseModel):
    payment: str = Field(..., description="The payment's txn:// link, id or reference.")
    outcome: Literal['consistent', 'different', 'discussed_purpose_not_stated']
    quoted: list[str] = Field(..., min_length=1, max_length=50, description='The rec:// links of the messages.')
    purpose: str | None = Field(None, description='The purpose the messages state, in their words.')
    person_a: str | None = None
    person_b: str | None = None
    hours: float = Field(2, gt=0, le=168)
    days: float | None = Field(None, gt=0, le=7)
    why: str = Field('', max_length=1200)


class ClaimProposalArgs(BaseModel):
    kind: Literal['inactive', 'active', 'at_place', 'not_at_place', 'with_subject', 'apart_from_subject', 'no_contact',
                  'contact'] = Field(..., description='What the source claims a phone could test.')
    person: str | None = Field(None, description='The person the claim is about: a dossier name or id.')
    phone: str | None = Field(None, description='Or the phone it is about, as listed by the phone tools.')
    quote: str = Field(..., min_length=1, max_length=8000, description="The source's exact words.")
    window_text: str | None = Field(None, max_length=2000, description="The source's own words for the time. Never a "
                                                                       "converted date or clock value.")
    place_text: str | None = Field(None, max_length=2000, description="The source's own words for the place.")
    counterpart_text: str | None = Field(None, max_length=2000, description="The source's words for the other person.")
    why: str = Field('', max_length=1200)
    citations: list[str] = Field(..., min_length=1, max_length=20,
                                 description='The doc:// page, rec:// message or txn:// row the claim comes from.')


class EntityProposalArgs(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description='The name, or the code or serial as printed.')
    entity_type: str = Field(..., min_length=1, max_length=80,
                             description='The graph type, as get_case_overview lists them, e.g. Person, Company, '
                                         'Account, Location, Document.')
    summary: str = Field(..., min_length=1, max_length=8000, description='What the sources say about it.')
    why: str = Field('', max_length=1200)
    citations: list[str] = Field(..., min_length=1, max_length=20)


class GlossaryTermArgs(BaseModel):
    term: str = Field(..., min_length=1, max_length=200, description='The code word, as written in the messages.')
    meaning: str = Field(..., min_length=1, max_length=8000, description='Your reading of what it means.')
    speaker: str | None = Field(None, max_length=255, description='Who uses it, as the messages show.')
    why: str = Field('', max_length=1200, description='What in the messages supports this reading.')
    citations: list[str] = Field(..., min_length=1, max_length=50, description='rec:// links of the messages.')


class AssumptionProposalArgs(BaseModel):
    calculation_id: str
    key: Literal['messages', 'share_deals', 'deals_per_message', 'price_per_deal']
    low: str = Field(..., description='Lowest defensible value (a share in percent; a price in the currency).')
    high: str = Field(..., description='Highest defensible value.')
    source: str = Field(..., min_length=1, max_length=600, description='Where the value comes from: a txn://, doc:// '
                                                                       'or rec:// source, or a named reference.')
    why: str = Field(..., min_length=1, max_length=1200)


def _claim_subject(session, case_id, person, phone) -> dict:
    """The claim's subject as the Patterns screens take it; "Not in this case." for one outside it."""
    from services.agent import phone_cross_tools as X
    from services.agent.proposals import ProposalError
    conn = session.connection()
    try:
        if phone:
            ids, unknown = X._phone_ids(conn, case_id, [phone])
            if unknown:
                raise ProposalError('Not in this case.', 404)
            return dict(kind='extraction', extraction_id=ids[0])
        return dict(kind='dossier', dossier_id=str(X._dossier(conn, case_id, person).id))
    except X._Missing as exc:
        raise ProposalError('Not in this case.', 404) from exc


def _as_uuid(value):
    import uuid
    try:
        return uuid.UUID(str(value))
    except ValueError:
        return None


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
                from postgres.models.user import User
                from services.case_service import check_case_access
                current_user = session.get(User, _as_uuid(who.get('for_user_id')))
                if current_user is None or not current_user.is_active:
                    raise ProposalError('An active case editor is required.', 403)
                try:
                    check_case_access(session, _as_uuid(context.case_id), current_user, required_permission=('case', 'edit'))
                except Exception as exc:
                    raise ProposalError('Case edit access is required to record a proposal.', 403) from exc
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
            citations=args.citations, origin=o, requested_by_user_id=(context.proposer or {}).get('for_user_id'),
            dossier_id=args.dossier_id, event_date=args.event_date))

    def propose_dossier_change(**kw):
        from services.agent.dossier_proposals import propose_dossier
        args = DossierProposalArgs(**kw)
        return call('propose_dossier_change', 'Workspace proposals', lambda s, o: propose_dossier(
            s, case_id=context.case_id, **args.model_dump(), origin=o,
            requested_by_user_id=(context.proposer or {}).get('for_user_id')))

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

    def propose_control_claim(**kw):
        args = ControlClaimProposalArgs(**kw)
        from services.agent import workspace_proposals as W
        return call('propose_control_claim', 'Workspace proposals', lambda s, o: W.propose_phone_draft(
            s, case_id=context.case_id, kind='control_claim', why=args.why, origin=o,
            args=dict(person=args.person, account=args.account, start=args.start, end=args.end),
            requested_by_user_id=(context.proposer or {}).get('for_user_id')))

    def propose_payment_purpose(**kw):
        args = PaymentPurposeProposalArgs(**kw)
        from services.agent import workspace_proposals as W
        return call('propose_payment_purpose', 'Workspace proposals', lambda s, o: W.propose_phone_draft(
            s, case_id=context.case_id, kind='payment_purpose', why=args.why, origin=o,
            args=dict(payment=args.payment, outcome=args.outcome, quoted=args.quoted, purpose=args.purpose,
                      person_a=args.person_a, person_b=args.person_b, hours=args.hours, days=args.days),
            requested_by_user_id=(context.proposer or {}).get('for_user_id')))

    def propose_claim(**kw):
        args = ClaimProposalArgs(**kw)
        from services.agent import workspace_proposals as W

        def work(session, o):
            if bool(args.person) == bool(args.phone):
                raise ProposalError('Say who the claim is about: a person or a phone, one of the two.')
            subject = _claim_subject(session, context.case_id, args.person, args.phone)
            return W.propose_claim(session, case_id=context.case_id, kind=args.kind, subject=subject, quote=args.quote,
                                   window_text=args.window_text, place_text=args.place_text,
                                   counterpart_text=args.counterpart_text, why=args.why, citations=args.citations,
                                   origin=o, requested_by_user_id=(context.proposer or {}).get('for_user_id'))
        return call('propose_claim', 'Workspace proposals', work)

    def propose_entity(**kw):
        args = EntityProposalArgs(**kw)
        from services.agent import workspace_proposals as W
        return call('propose_entity', 'Workspace proposals', lambda s, o: W.propose_entity(
            s, case_id=context.case_id, name=args.name, entity_type=args.entity_type, summary=args.summary,
            why=args.why, citations=args.citations, origin=o,
            requested_by_user_id=(context.proposer or {}).get('for_user_id')))

    def propose_glossary_term(**kw):
        args = GlossaryTermArgs(**kw)
        from services.agent import workspace_proposals as W
        return call('propose_glossary_term', 'Workspace proposals', lambda s, o: W.propose_term(
            s, case_id=context.case_id, term=args.term, meaning=args.meaning, speaker=args.speaker, why=args.why,
            citations=args.citations, origin=o, requested_by_user_id=(context.proposer or {}).get('for_user_id')))

    def propose_assumption(**kw):
        args = AssumptionProposalArgs(**kw)
        from services.financial import proceeds as PR

        def work(session, o):
            try:
                out = PR.propose_assumption(session, case_id=context.case_id, calculation_id=args.calculation_id,
                                            key=args.key, low=args.low, high=args.high, source=args.source,
                                            why=args.why, origin=o)
            except PR.ProceedsError as exc:
                raise ProposalError(str(exc), exc.status_code) from exc
            row = next(r for r in out['assumptions'] if r['key'] == args.key)
            mine = row['proposed'][-1] if row['proposed'] else {}
            return dict(id=mine.get('id'), calculation_id=out['id'], calculation=out['title'], label=out['label'],
                        status=mine.get('status'), used_in_result=False)
        return call('propose_assumption', 'the proceeds calculation', work)

    def sweep(name, work):
        """The disconfirm sweep is a write like a proposal: the same refusals, the screen's own counts."""
        from services.agent import disconfirm as D
        who = context.proposer or {}
        if not who or not who.get('can_propose'):
            message = ('The person this run is for cannot change this case, so no sweep was run. A person can run it '
                       'on the theory in Workspace.')
            return context.result(name, {'error': message}, summary=f'{name}: not run.', status='error', error=message)
        try:
            with _write_session() as session:
                data = D.agent_summary(work(session, D, who))
        except ProposalError as exc:
            return context.result(name, {'error': str(exc)}, summary=f'{name} refused: {exc}', status='error',
                                  error=str(exc))
        return context.result(name, data, summary=f"{name}: {data.get('headline') or data.get('step')}")

    def plan_theory_sweep(**kw):
        args = SweepPlanArgs(**kw)

        def work(session, D, who):
            from postgres.models.user import User
            user = session.get(User, _as_uuid(who.get('for_user_id')))
            if user is None:
                raise ProposalError('The person this run is for is not known.', 403)
            made = D.create(session, case_id=context.case_id, theory_id=args.theory_id, requested_by=user,
                            run_id=who.get('run_id'))
            return D.plan(session, sweep_id=made['id'])
        return sweep('plan_theory_sweep', work)

    def propose_counter_arguments(**kw):
        args = SweepReadArgs(**kw)

        def work(session, D, who):
            started = D.start(session, case_id=context.case_id, sweep_id=args.sweep_id, limit=args.limit)
            return D.read(session, sweep_id=started['id'])
        return sweep('propose_counter_arguments', work)

    rule = (' Records a proposal only: nothing changes until a person accepts it after opening a cited source. Use '
            'it when the user asks you to create, add, change, propose, draft or suggest casework; explain the saved '
            'proposal and destination. Do not use it merely to answer a question.')
    return [
        StructuredTool.from_function(
            func=plan_theory_sweep, name='plan_theory_sweep', args_schema=SweepPlanArgs,
            description=('Plan a whole-case sweep for what breaks a Workspace theory: one model call derives what the '
                         'theory leads you to expect, code searches the ledger, phones, documents and graph, and '
                         'checks what the case lacks. Returns the exact count of model reads a run would take, and '
                         'stops. State that count to the user in your answer before or with propose_counter_arguments.')),
        StructuredTool.from_function(
            func=propose_counter_arguments, name='propose_counter_arguments', args_schema=SweepReadArgs,
            description=('Run the reads plan_theory_sweep counted. Each item found against the theory is recorded as a '
                         'proposal for a person to decide. Takes minutes. Report each expectation with what was '
                         'searched and what was out of reach; nothing found is never support for the theory.')),
        StructuredTool.from_function(
            func=propose_judgement_call, name='propose_judgement_call', args_schema=JudgementProposalArgs,
            description=('Propose a judgement call on the ledger: a missing statement month for an account (checked '
                         'against the statement continuity), a payment category from the library, or who the other '
                         'side of a payment is.' + rule)),
        StructuredTool.from_function(
            func=propose_workspace_entry, name='propose_workspace_entry', args_schema=EntryProposalArgs,
            description='Draft a cited note or finding, optionally attached to a dossier and added as a dated event in one review.' + rule),
        StructuredTool.from_function(
            func=propose_dossier_change, name='propose_dossier_change', args_schema=DossierProposalArgs,
            description='Create a dossier, update its name/summary/importance/type, or attach sources, findings or artifacts. '
                        'Keeps existing links and detects investigator edits made since the proposal.' + rule),
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
        StructuredTool.from_function(
            func=propose_control_claim, name='propose_control_claim', args_schema=ControlClaimProposalArgs,
            description=('Record the phones\' control claim (as draft_control_claim reads it) as a proposal: "P had '
                         'the means to operate account A from t1 to t2", both links with every strand cited. '
                         'Refused when the chain does not hold. Never a holder finding.' + rule)),
        StructuredTool.from_function(
            func=propose_payment_purpose, name='propose_payment_purpose', args_schema=PaymentPurposeProposalArgs,
            description=('Record your reading of a payment\'s stated purpose (as draft_payment_purpose checks it) as a '
                         'proposal, quoting the messages by rec:// with the row\'s txn://.' + rule)),
        StructuredTool.from_function(
            func=propose_claim, name='propose_claim', args_schema=ClaimProposalArgs,
            description=('Draft one claim a document or message makes, in its exact words with the source cited, so a '
                         'person can confirm it and evaluate_statement can test it. Use it for each line of the other '
                         'side\'s timeline or schedule, or a receipt\'s reading. Give the source\'s own words for time '
                         'and place, never a converted time.' + rule)),
        StructuredTool.from_function(
            func=propose_entity, name='propose_entity', args_schema=EntityProposalArgs,
            description=('Propose an entity for the graph (a person, company, account, pickup code, banknote serial) '
                         'from cited sources. Refused when the graph already holds the name.' + rule)),
        StructuredTool.from_function(
            func=propose_glossary_term, name='propose_glossary_term', args_schema=GlossaryTermArgs,
            description=('Propose one code word and your reading of its meaning, citing the messages. It stays a model '
                         'reading until a person confirms it, term by term; get_glossary then lists every mention with '
                         'its ledger rows.' + rule)),
        StructuredTool.from_function(
            func=propose_assumption, name='propose_assumption', args_schema=AssumptionProposalArgs,
            description=('Propose one assumption of a proceeds calculation (volume, share that are deals, deals per '
                         'message, price per deal) with its source. The calculator does the arithmetic; never compute '
                         'a turnover yourself.' + rule)),
    ]
