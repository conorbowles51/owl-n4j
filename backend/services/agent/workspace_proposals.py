"""Workspace AI widened to the case agent's drafts (agent-proposals B, D).

Five drafted kinds, each a Workspace AI output with ``target_type='case'``, held ``pending_review`` with checked
citations until a person accepts or rejects it. Nothing is written to the Workspace before a person accepts.

* ``entry_draft``: a Workspace note or finding (title, body, cited sources).
* ``lead_card``: connection 2. Built by code from a stored account lead (``money_signals.leads``): the institution,
  the account ending masked to four digits, the first and last alert as the period a request would cover, alert
  counts by evidence class, each alert's amount and time cited by ``rec://``. Alerts are never totalled. The phone
  screen keeps its neutral lead words; the request period appears only here, in a labelled draft a person edits.
  Accepting it makes a Workspace finding and a task with the deadline the person sets.
* ``timeline_addition``: payments, money trails, findings or phone records to add to the case timeline.
* ``link_proposal``: a link from a Workspace entry to a source (supports / contradicts / context).
* ``alternative_explanation``: the red cell's lines pointing away from the suspect (services.agent.red_cell).

Accepting needs a person; what the person opened first is recorded (``model_metadata.review``) and the work it
creates carries the model origin (``actor_origin``) so it always shows a model drafted it.
"""
from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import date, datetime, timezone
from typing import Any, Mapping

from sqlalchemy import func, select

from services.agent.proposals import (NOT_IN_CASE, ProposalError, _checked_citations, _require_origin, _uuid, _why,
                                      review_facts)

log = logging.getLogger(__name__)

AGENT_OUTPUT_TYPES = ('entry_draft', 'lead_card', 'timeline_addition', 'link_proposal', 'alternative_explanation',
                      'control_claim', 'payment_purpose')
# The phones' two drafts (agent-phones, phone_cross_tools): the deterministic check is re-run when stored.
PHONE_DRAFTS = ('control_claim', 'payment_purpose')
ENTRY_KINDS = ('note', 'finding')
RELATIONSHIPS = ('supports', 'contradicts', 'context')
MAX_TITLE, MAX_BODY = 255, 8000
MAX_ALERTS = 500


def _now():
    return datetime.now(timezone.utc)


def _text(value, limit, what):
    value = ' '.join(str(value or '').split()) if limit <= MAX_TITLE else str(value or '').strip()
    if not value:
        raise ProposalError(f'Give the {what}.')
    return value[:limit]


def _next_version(session, case_id, output_type):
    from postgres.models.workspace_ai import WorkspaceAIOutput as W
    current = session.scalar(select(func.max(W.version)).where(W.case_id == case_id, W.target_type == 'case',
                                                                W.target_id == case_id, W.output_type == output_type))
    return int(current or 0) + 1


def _store(session, *, case_id, output_type, content, checked, action, origin, requested_by_user_id=None):
    from postgres.models.workspace_ai import WorkspaceAIOutput as W
    from services.mandate_context_service import mandate_context_service
    mandate = mandate_context_service.active_version(session, case_id=case_id)
    content = dict(content, citations=[c['citation'] for c in checked])
    item = W(id=uuid.uuid4(), case_id=case_id, target_type='case', target_id=case_id, output_type=output_type,
             version=_next_version(session, case_id, output_type), job_status='completed',
             review_status='pending_review', citation_status='valid', progress=100, content=content,
             citations=[dict(source_id=c['citation'], cite=c['citation'], label=c['label'], status=c['status'])
                        for c in checked],
             proposed_actions=[action], model_metadata=dict(origin=origin, model=origin.get('model'),
                                                            model_id=origin.get('model_id'),
                                                            run_id=origin.get('run_id')),
             generation_input=dict(kind='agent_proposal'), source_set=[],
             mandate_version_id=getattr(mandate, 'id', None), requested_by_user_id=_uuid(requested_by_user_id),
             started_at=_now(), completed_at=_now())
    session.add(item)
    session.commit()
    return serialize(item)


def serialize(item) -> dict:
    from services.workspace_ai_service import serialize_output
    out = serialize_output(item)
    if item.mandate_version_id is None:
        out['mandate_version_id'] = None
    meta = item.model_metadata or {}
    out['proposal'] = dict(kind=item.output_type, model=meta.get('model'), model_id=meta.get('model_id'),
                           run_id=meta.get('run_id'), review=meta.get('review'),
                           for_name=((meta.get('origin') or {}).get('for') or {}).get('name'))
    return out


# ---------------------------------------------------------------------------
# Proposing
# ---------------------------------------------------------------------------

def propose_entry(session, *, case_id, entry_type, title, body, citations, origin, requested_by_user_id=None):
    origin = _require_origin(origin)
    entry_type = str(entry_type or '').strip().lower()
    if entry_type not in ENTRY_KINDS:
        raise ProposalError('A drafted Workspace entry is a note or a finding.')
    title, body = _text(title, MAX_TITLE, 'title'), _text(body, MAX_BODY, 'text')
    checked = _checked_citations(session, case_id, citations)
    return _store(session, case_id=_uuid(case_id), output_type='entry_draft',
                  content=dict(entry_type=entry_type, title=title, body=body), checked=checked,
                  action=dict(action='create_workspace_entry', entry_type=entry_type), origin=origin,
                  requested_by_user_id=requested_by_user_id)


def propose_link(session, *, case_id, entry_id, target_type, target_id, relationship, why, citations=(), origin,
                 requested_by_user_id=None):
    from postgres.models.workspace_entry import ENTRY_LINK_TARGET_TYPES, WorkspaceEntry
    origin = _require_origin(origin)
    why = _why(why)
    entry = session.get(WorkspaceEntry, _uuid(entry_id)) if _uuid(entry_id) else None
    if entry is None or entry.case_id != _uuid(case_id) or entry.deleted_at is not None:
        raise ProposalError('Not in this case.', 404)
    if target_type not in ENTRY_LINK_TARGET_TYPES:
        raise ProposalError('That kind of source cannot be linked to a Workspace entry.')
    if relationship not in RELATIONSHIPS:
        raise ProposalError('Say whether the source supports, contradicts or gives context.')
    checked = _checked_citations(session, case_id, citations)
    link = dict(target_type=target_type, target_id=str(target_id), relationship=relationship)
    return _store(session, case_id=_uuid(case_id), output_type='link_proposal',
                  content=dict(entry_id=str(entry.id), entry_title=entry.title, why=why, **link), checked=checked,
                  action=dict(action='add_entry_link', entry_id=str(entry.id), **link), origin=origin,
                  requested_by_user_id=requested_by_user_id)


def propose_timeline(session, *, case_id, source_kind, source_ids, event_date=None, why, citations=(), origin,
                     requested_by_user_id=None):
    """Checked by the timeline's own preview: every source must be in the case and not yet on the timeline."""
    from services.timeline_entries import TimelineAddition, preview_addition
    origin = _require_origin(origin)
    why = _why(why)
    try:
        request = TimelineAddition(source_kind=source_kind, source_ids=list(source_ids or []), event_date=event_date)
        preview = preview_addition(session, case_id=_uuid(case_id), request=request)
    except ProposalError:
        raise
    except Exception as exc:  # noqa: BLE001 - the timeline's refusal, in its own words
        session.rollback()
        raise ProposalError(str(exc) or 'The timeline cannot add these sources.') from exc
    if not preview['ready']:
        raise ProposalError('Nothing to add: every source is already on the timeline or has no date.', 409)
    extra = [f'txn://{r["source_id"]}' for r in preview['rows'] if source_kind == 'transaction']
    extra += [f'rec://{r["record_id"]}' for r in preview['rows'] if r.get('record_id')]
    checked = _checked_citations(session, case_id, citations, extra=extra)
    rows = [dict(source_id=r['source_id'], name=r['name'], status=r['status'],
                 date=(r.get('event') or {}).get('date')) for r in preview['rows']]
    return _store(session, case_id=_uuid(case_id), output_type='timeline_addition',
                  content=dict(source_kind=source_kind, rows=rows, why=why,
                               event_date=event_date.isoformat() if isinstance(event_date, date) else event_date,
                               ready=preview['ready'], already_added=preview['already_added']),
                  checked=checked, action=dict(action='add_to_timeline', source_kind=source_kind,
                                               source_ids=[str(s) for s in request.source_ids],
                                               event_date=event_date.isoformat() if isinstance(event_date, date)
                                               else event_date),
                  origin=origin, requested_by_user_id=requested_by_user_id)


# ---------------------------------------------------------------------------
# The phones' drafts (connections 3 and 4, agent-phones): a control claim and a payment's stated purpose
# ---------------------------------------------------------------------------

_CITE = re.compile(r'\b(?:rec|txn|doc)://[0-9A-Za-z-]+(?:/\d+)?')


def _cites_in(obj) -> list[str]:
    return list(dict.fromkeys(_CITE.findall(json.dumps(obj, default=str))))


def _strand_line(s) -> str:
    cites = ', '.join(_cites_in(s)) or 'no record'
    words = ' '.join(str(s.get('words') or s.get('kind') or '').split())
    return f"- {s.get('link', '').replace('_', ' ')}: {words} ({s.get('strength') or 'context'}; {cites})"


def control_claim_content(result) -> dict:
    """The stored proposal for a control claim, from the phones' own check. Never a holder finding."""
    items = result.get('items') or []
    body = [result['claim'] + '.', '', result.get('coverage') or '', '', result.get('correlated_strands') or '',
            '', 'For and against, each cited:'] + [_strand_line(s) for s in items] + [
            '', result.get('not_a_holder_finding') or '']
    return dict(title=('Means to operate: ' + result['claim'])[:MAX_TITLE], body='\n'.join(body)[:MAX_BODY],
                claim=result['claim'], person=result.get('person'), account=result.get('account'),
                period=result.get('period'), coverage=result.get('coverage'),
                chain=[dict(link=c.get('link'), holds=c.get('holds'), counts=c.get('counts')) for c in
                       result.get('chain') or []],
                items=items, items_total=len(items), established=result.get('established'),
                not_a_holder_finding=result.get('not_a_holder_finding'))


def payment_purpose_content(result) -> dict:
    item = (result.get('items') or [{}])[0]
    outcome = str(item.get('outcome') or '').replace('_', ' ')
    names = result.get('coverage') or ''
    body = [f"Model reading of the messages around {item.get('payment')}: {outcome}.",
            f"Purpose the messages state: {item['purpose_stated']}." if item.get('purpose_stated') else '',
            f"Row description: {item.get('row_description') or 'none printed'}; reference: "
            f"{item.get('row_reference') or 'none printed'}.", names, '', 'Messages quoted:'] + [
            f'- {q}' for q in item.get('quoted') or []]
    return dict(title=f"Stated purpose of a payment: {outcome}"[:MAX_TITLE],
                body='\n'.join(x for x in body if x is not None)[:MAX_BODY], payment=item.get('payment'),
                outcome=item.get('outcome'), purpose_stated=item.get('purpose_stated'), quoted=item.get('quoted'),
                between=item.get('between'), window=item.get('window'), row_description=item.get('row_description'),
                row_reference=item.get('row_reference'))


def propose_phone_draft(session, *, case_id, kind, args, why='', origin, requested_by_user_id=None, _run=None):
    """Store one of the phones' drafts as a proposal. The phones' own check is re-run here with the run's case, so
    the stored claim is exactly what the code found; the model's words are only the reason it gives."""
    origin = _require_origin(origin)
    if kind not in PHONE_DRAFTS:
        raise ProposalError('A phone draft is a control claim or a payment purpose.')
    if _run is None:
        from services.agent import phone_cross_tools as P
        fn = P.control_claim if kind == 'control_claim' else P.draft_payment_purpose
        _run = lambda: fn(session.connection(), _uuid(case_id), **args)  # noqa: E731
    try:
        result = _run()
    except ValueError as exc:
        raise ProposalError(str(exc)) from exc
    if result.get('not_in_case'):
        raise ProposalError(NOT_IN_CASE, 404)
    if result.get('available') is False:
        raise ProposalError(str(result.get('reason') or 'The phones could not be read for this draft.'), 409)
    if kind == 'control_claim':
        if not result.get('established'):
            raise ProposalError(result.get('limitation') or 'The chain does not hold, so there is no claim to '
                                                             'propose.', 409)
        content = control_claim_content(result)
    else:
        content = payment_purpose_content(result)
    content['why'] = ' '.join(str(why or '').split())[:1200] or None
    checked = _checked_citations(session, case_id, _cites_in(result), limit=MAX_ALERTS)
    return _store(session, case_id=_uuid(case_id), output_type=kind, content=content, checked=checked,
                  action=dict(action='create_workspace_finding', kind=kind), origin=origin,
                  requested_by_user_id=requested_by_user_id)


# ---------------------------------------------------------------------------
# Lead cards (connection 2)
# ---------------------------------------------------------------------------

def mask_ending(ending) -> str | None:
    digits = re.sub(r'\D', '', str(ending or ''))
    return f'ending {digits[-4:]}' if digits else None


def lead_card_content(lead: Mapping[str, Any], alerts: list[dict], phones: Mapping[str, str]) -> dict:
    """The card, by code. ``lead``: a stored account lead (measures as ``money_signals.leads`` writes them).
    ``alerts``: [{record_uid, class, instant, amount_minor, currency, direction, phone}]. Never totals an amount."""
    measures = lead.get('measures') or {}
    institution = (measures.get('institution') or {}).get('name')
    ending = mask_ending((measures.get('account_ref') or '').replace('ending', ''))
    transactional = sorted(a['instant'] for a in alerts if a.get('class') == 'transactional' and a.get('instant'))
    every = sorted(a['instant'] for a in alerts if a.get('instant'))
    span = transactional or every
    lines = []
    for a in sorted(alerts, key=lambda a: (a.get('instant') or '', a['record_uid']))[:MAX_ALERTS]:
        lines.append(dict(cite=f"rec://{a['record_uid']}", evidence_class=a.get('class'), at=a.get('instant'),
                          amount_minor=a.get('amount_minor'), currency=a.get('currency'),
                          direction=a.get('direction'), phone=phones.get(str(a.get('extraction_id'))) or None))
    return dict(
        institution=institution, account_ending=ending, status=measures.get('status'),
        status_sentence=measures.get('sentence'), counts=dict(measures.get('counts') or {}),
        first_alert=span[0] if span else None, last_alert=span[-1] if span else None,
        # The period a request would cover: shown only in this labelled draft, never on the phone screen.
        request_period=dict(start=span[0][:10], end=span[-1][:10]) if span else None,
        phones=sorted({p for p in (phones.get(str(a.get('extraction_id'))) for a in alerts) if p}),
        alerts=lines, alerts_total=len(alerts), alerts_shown=len(lines),
        totalled=False, lead_result_id=str(lead.get('id') or ''),
        title=' · '.join(x for x in ('Lead', institution, ending) if x))


def _lead_alerts(session, case_id, lead_id):
    """The stored lead and each of its alerts with its time and, for an alert that prints one, its amount."""
    from sqlalchemy import text
    from services.phone_analysis import money_signals as MS
    from services.phone_analysis import institutions as INST
    conn = session.connection()
    row = conn.execute(text("SELECT id, kind, measures, period_start, period_end FROM phone_analysis_results WHERE "
                            "id = :i AND case_id = :c"), dict(i=str(lead_id), c=str(case_id))).mappings().first()
    if row is None or row['kind'] != 'account_lead':
        raise ProposalError('Not in this case.', 404)
    uids = {str(r[0]) for r in conn.execute(text("SELECT record_uid FROM phone_analysis_result_records WHERE "
                                                 "result_id = :i AND record_uid IS NOT NULL"), dict(i=str(lead_id)))}
    signals = [s for s in MS.read_signals(conn, case_id) if s['record_uid'] in uids]
    phones_ctx = MS._phone_context(conn, case_id)
    directory = INST.for_case(conn, case_id)
    items = {i['sig']['record_uid']: i for i in MS.readings(signals, directory, phones_ctx)}
    alerts = []
    for s in signals:
        item = items.get(s['record_uid'])
        reading = item['reading'] if item else None
        alerts.append(dict(record_uid=s['record_uid'], extraction_id=s['extraction_id'],
                           **{'class': 'transactional' if reading is not None and item['signal'] in ('S1', 'S2', 'S3')
                              else 'account' if s['model_type'] in ('Password', 'UserAccount', 'CreditCard',
                                                                     'Autofill') else 'presence'},
                           instant=s['instant'].isoformat() if s['instant'] else None,
                           amount_minor=getattr(reading, 'amount_minor', None),
                           currency=getattr(reading, 'currency', None),
                           direction=str(getattr(reading, 'direction', '') or '') or None))
    phones = {k: v.get('label') for k, v in phones_ctx.items()}
    return dict(row), alerts, phones


def propose_lead_card(session, *, case_id, lead_result_id, why='', origin, requested_by_user_id=None, _read=None):
    origin = _require_origin(origin)
    lead, alerts, phones = (_read or _lead_alerts)(session, _uuid(case_id), _uuid(lead_result_id))
    if not alerts:
        raise ProposalError('This lead has no alert left in the case to cite.', 409)
    content = lead_card_content(lead, alerts, phones)
    content['why'] = ' '.join(str(why or '').split())[:1200] or None
    checked = _checked_citations(session, case_id, [a['cite'] for a in content['alerts']], limit=MAX_ALERTS)
    return _store(session, case_id=_uuid(case_id), output_type='lead_card', content=content, checked=checked,
                  action=dict(action='create_lead_task', lead_result_id=str(lead_result_id)), origin=origin,
                  requested_by_user_id=requested_by_user_id)


def lead_task_title(content) -> str:
    what = ' '.join(x for x in (content.get('institution'), content.get('account_ending')) if x) or 'the account'
    period = content.get('request_period') or {}
    when = f", {period['start']} to {period['end']}" if period.get('start') else ''
    return f'Statements for {what}{when}'[:512]


# ---------------------------------------------------------------------------
# A person's answer
# ---------------------------------------------------------------------------

def _load(session, case_id, output_id):
    from postgres.models.workspace_ai import WorkspaceAIOutput as W
    item = session.scalar(select(W).where(W.id == _uuid(output_id), W.case_id == _uuid(case_id)).with_for_update())
    if item is None or item.output_type not in AGENT_OUTPUT_TYPES:
        raise ProposalError('Proposal not found in this case.', 404)
    return item


def _origin_record(item, reviewer, facts):
    meta = item.model_metadata or {}
    return dict(origin=meta.get('origin'), accepted_by=dict(name=reviewer.name, email=reviewer.email,
                                                            user_id=str(reviewer.id)),
                workspace_ai_output_id=str(item.id), review=facts)


def accept(session, *, case_id, output_id, reviewer, via='api', due_at=None, edits=None):
    """A person accepts the draft: the Workspace work is created under the person, carrying the model origin.
    ``due_at``: the deadline of a lead card's task (required for a lead card). ``edits``: a person's changes to a
    draft's title or text before accepting (kept; the draft stays as the model wrote it)."""
    from services.financial.model_work import ModelWorkError, is_model
    if reviewer is None or is_model(reviewer):
        raise ProposalError('A person accepts a proposal; a model accepting its own draft accepts nothing.', 403)
    item = _load(session, case_id, output_id)
    if item.review_status != 'pending_review':
        raise ProposalError(f'This proposal is already {item.review_status.replace("_", " ")}.', 409)
    facts = review_facts(session, 'workspace_ai', item.id, reviewer, via=via)
    provenance = _origin_record(item, reviewer, facts)
    content, action = dict(item.content or {}), (item.proposed_actions or [{}])[0]
    edits = {k: v for k, v in dict(edits or {}).items() if k in ('title', 'body') and str(v or '').strip()}
    try:
        accepted = _apply(session, item, content, action, reviewer, provenance, due_at, edits)
    except ProposalError:
        session.rollback()
        raise
    item = _load(session, case_id, output_id)
    item.review_status, item.reviewed_by_user_id, item.reviewed_at = 'accepted', reviewer.id, _now()
    item.accepted_targets = accepted
    item.model_metadata = dict(item.model_metadata or {}, review=facts, edits=edits or None)
    session.commit()
    return serialize(item)


def _entry(session, *, case_id, reviewer, entry_type, title, body, provenance, tags=(), lifecycle_state=None,
           links=()):
    from services.workspace_entry_service import create_entry
    return create_entry(session, case_id=case_id, current_user=reviewer, entry_type=entry_type, title=title,
                        body=body, tags=list(tags), lifecycle_state=lifecycle_state, review_state='accepted',
                        links=list(links), compatibility_metadata=dict(actor_origin=provenance))


def _citation_links(content):
    """Workspace links for the draft's txn:// and doc:// citations, where the Workspace can hold them."""
    from postgres.models.workspace_entry import ENTRY_LINK_TARGET_TYPES
    links = []
    for cite in content.get('citations') or []:
        scheme, _, rest = str(cite).partition('://')
        if scheme == 'doc' and 'evidence' in ENTRY_LINK_TARGET_TYPES:
            links.append(dict(target_type='evidence', target_id=rest.split('/')[0], relationship='context'))
        elif scheme == 'txn' and 'financial_transaction' in ENTRY_LINK_TARGET_TYPES:
            links.append(dict(target_type='financial_transaction', target_id=rest, relationship='context'))
    return links


def _apply(session, item, content, action, reviewer, provenance, due_at, edits):
    kind = item.output_type
    case_id = item.case_id
    if kind in PHONE_DRAFTS:
        entry = _entry(session, case_id=case_id, reviewer=reviewer, entry_type='finding',
                       title=edits.get('title') or content.get('title'), body=edits.get('body') or content.get('body'),
                       provenance=provenance, tags=(kind.replace('_', '-'), 'phones'), links=_citation_links(content))
        return [dict(target_type='workspace_entry', target_id=entry['id'])]
    if kind in ('entry_draft', 'alternative_explanation'):
        entry_type = content.get('entry_type') if kind == 'entry_draft' else 'theory'
        entry = _entry(session, case_id=case_id, reviewer=reviewer, entry_type=entry_type,
                       title=edits.get('title') or content.get('title'), body=edits.get('body') or content.get('body'),
                       provenance=provenance, tags=('red-cell',) if kind == 'alternative_explanation' else (),
                       lifecycle_state='proposed' if kind == 'alternative_explanation' else None,
                       links=_citation_links(content))
        return [dict(target_type='workspace_entry', target_id=entry['id'])]
    if kind == 'lead_card':
        return _accept_lead(session, item, content, reviewer, provenance, due_at, edits)
    if kind == 'link_proposal':
        from postgres.models.workspace_entry import WorkspaceEntry
        from services.workspace_entry_service import add_entry_links
        entry = session.get(WorkspaceEntry, _uuid(action.get('entry_id')))
        if entry is None or entry.case_id != case_id or entry.deleted_at is not None:
            raise ProposalError('The Workspace entry is no longer in this case.', 409)
        model = (provenance.get('origin') or {}).get('model') or 'the case agent'
        result = add_entry_links(session, case_id=case_id, entry_id=entry.id, current_user=reviewer,
                                 expected_version=entry.version,
                                 links=[dict(target_type=action['target_type'], target_id=action['target_id'],
                                             relationship=action['relationship'])],
                                 rationale=f'Proposed by {model} (case agent), accepted by {reviewer.name}',
                                 ignore_existing=True, commit=False)
        return [dict(target_type='workspace_entry_link', target_id=i) for i in result['added_link_ids']]
    if kind == 'timeline_addition':
        from postgres.models.timeline_entry import TimelineEntry
        from services.timeline_entries import TimelineAddition, preview_addition, save_addition
        request = TimelineAddition(source_kind=action['source_kind'], source_ids=action['source_ids'],
                                   event_date=action.get('event_date'))
        try:
            request.expected_revision = preview_addition(session, case_id=case_id, request=request)['revision']
            saved = save_addition(session, case_id=case_id, request=request, actor=reviewer.name)
        except ValueError as exc:
            raise ProposalError(str(exc), 409) from exc
        keys = [k[len('timeline-entry:'):] for k in saved['event_keys']]
        for entry in session.scalars(select(TimelineEntry).where(TimelineEntry.case_id == case_id,
                                                                  TimelineEntry.id.in_([_uuid(k) for k in keys]))):
            if not (entry.event_snapshot or {}).get('actor_origin'):
                entry.event_snapshot = dict(entry.event_snapshot or {}, actor_origin=provenance)
        return [dict(target_type='timeline_entry', target_id=k) for k in keys]
    raise ProposalError('This proposal cannot be accepted.', 409)


def _accept_lead(session, item, content, reviewer, provenance, due_at, edits):
    from postgres.models.work import CaseTask, CaseTaskLink
    from services.financial.judgements import money
    if not due_at:
        raise ProposalError('Set the deadline for the task before accepting the lead card.')
    if isinstance(due_at, str):
        try:
            due_at = datetime.fromisoformat(due_at.replace('Z', '+00:00'))
        except ValueError as exc:
            raise ProposalError('The deadline is not a date.') from exc
    if isinstance(due_at, date) and not isinstance(due_at, datetime):
        due_at = datetime(due_at.year, due_at.month, due_at.day, tzinfo=timezone.utc)
    alerts = '\n'.join(f"- {a.get('at') or 'no time'} · {a.get('evidence_class')}"
                       + (f" · {money(a['amount_minor'], a.get('currency') or '')} {a.get('currency') or ''}".rstrip()
                          if a.get('amount_minor') is not None else '') + f" · {a['cite']}"
                       for a in content.get('alerts') or [])
    period = content.get('request_period') or {}
    body = edits.get('body') or (
        f"{content.get('status_sentence') or ''}\n\nAlerts by class: "
        + ', '.join(f'{k} {v}' for k, v in sorted((content.get('counts') or {}).items()))
        + (f"\nPeriod a request would cover: {period.get('start')} to {period.get('end')}" if period else '')
        + f"\n\n{alerts}")
    title = edits.get('title') or content.get('title') or 'Lead'
    # The task is staged first: the entry's own save commits it with the entry, so neither exists without the other.
    task = CaseTask(id=uuid.uuid4(), case_id=item.case_id, title=lead_task_title(content),
                    description=f'From the lead card accepted by {reviewer.name}. {content.get("status_sentence") or ""}',
                    status='todo', priority='standard', due_at=due_at, created_by_user_id=reviewer.id,
                    updated_by_user_id=reviewer.id, migration_metadata=dict(actor_origin=provenance))
    session.add(task)
    session.flush()
    entry = _entry(session, case_id=item.case_id, reviewer=reviewer, entry_type='finding', title=title, body=body,
                   provenance=provenance, tags=('lead',), lifecycle_state='draft')
    session.add(CaseTaskLink(id=uuid.uuid4(), task_id=task.id, case_id=item.case_id, target_type='entry',
                             target_id=entry['id'], label=title[:512], created_by_user_id=reviewer.id))
    return [dict(target_type='workspace_entry', target_id=entry['id']), dict(target_type='case_task',
                                                                              target_id=str(task.id))]


def reject(session, *, case_id, output_id, reviewer, reason):
    from services.financial.model_work import is_model
    if reviewer is None or is_model(reviewer):
        raise ProposalError('A person rejects a proposal.', 403)
    reason = ' '.join(str(reason or '').split())
    if not reason:
        raise ProposalError('Say why the proposal is wrong; the reason is what the agent learns from.')
    item = _load(session, case_id, output_id)
    if item.review_status != 'pending_review':
        raise ProposalError(f'This proposal is already {item.review_status.replace("_", " ")}.', 409)
    facts = review_facts(session, 'workspace_ai', item.id, reviewer)
    item.review_status, item.rejection_reason = 'rejected', reason[:4000]
    item.reviewed_by_user_id, item.reviewed_at = reviewer.id, _now()
    item.model_metadata = dict(item.model_metadata or {}, review=facts)
    session.commit()
    return serialize(item)


def list_proposals(session, *, case_id, status='pending_review', output_types=None, limit=50, offset=0):
    from postgres.models.workspace_ai import WorkspaceAIOutput as W
    types = [t for t in (output_types or AGENT_OUTPUT_TYPES) if t in AGENT_OUTPUT_TYPES]
    conditions = [W.case_id == _uuid(case_id), W.output_type.in_(types)]
    if status:
        conditions.append(W.review_status == status)
    limit = max(1, min(int(limit or 50), 100))
    total = session.scalar(select(func.count()).select_from(W).where(*conditions)) or 0
    rows = session.scalars(select(W).where(*conditions).order_by(W.created_at.desc()).limit(limit)
                           .offset(max(0, int(offset or 0)))).all()
    return dict(items=[serialize(r) for r in rows], total=total, returned=len(rows), limit=limit,
                offset=max(0, int(offset or 0)))
