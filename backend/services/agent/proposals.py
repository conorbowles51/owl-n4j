"""The case agent's only write: a proposal a person decides (agent-proposals A, C, F).

A proposal changes nothing until a person accepts it. Ledger proposals are judgement calls with origin ``agent``
recorded through ``judgements.record_judgement`` on existing subjects, so they appear in the Judgement calls page
with its priority tiers, filters and export, and a person's correction feeds the lessons inbox like any other.
Their strength is always ``inferred``: a model's proposal is never "proved" by the printed controls.

Three ledger kinds, each checked by deterministic code before it is recorded (the model proposes; code decides
whether the proposal is even possible):

* ``missing_month``: a calendar month no statement of an account covers. Recorded only when the account's
  statement continuity has a gap over that month; cites the statements either side.
* ``category``: a payment's category from the case's category library. Refused when a person already chose one.
* ``counterparty``: who the other side of a payment is (a person or business of the case, or one of its accounts).
  Refused when the payment already carries that identity.

Every proposal cites at least one source in the case (``txn://``, ``doc://``, ``rec://``); a citation outside the
case refuses the whole proposal ("Not in this case." whether or not it exists elsewhere).

Open the source before confirming (C): ``record_open`` stores each cited source a person opened from a proposal.
``review_facts`` tells a confirmation whether its source was opened first; the screen enables its confirm button
only after an open, and a confirmation through the API without one is recorded as such
(``evidence.review.source_opened = False``) and counted.

The precision trend (F) counts what people did with each kind of proposal per week.
"""
from __future__ import annotations

import logging
import re
import uuid
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable, Mapping, Optional

from sqlalchemy import select

log = logging.getLogger(__name__)

PREFIX = 'proposal.'
KINDS = {
    'missing_month': 'proposal.missing_month',
    'category': 'proposal.category',
    'counterparty': 'proposal.counterparty',
}
RULE_KIND = {rule: kind for kind, rule in KINDS.items()}
KIND_LABELS = {
    'missing_month': 'Missing statement month',
    'category': 'Payment category',
    'counterparty': 'Who the other side is',
    # Workspace AI kinds (services.agent.workspace_proposals) share the trend and the opened-source rule.
    'entry_draft': 'Workspace entry draft',
    'lead_card': 'Lead card',
    'timeline_addition': 'Timeline addition',
    'link_proposal': 'Link to evidence',
    'alternative_explanation': 'Alternative explanation (red cell)',
    'control_claim': 'Means to operate an account (phones)',
    'payment_purpose': 'Stated purpose of a payment (phones)',
    'statement_claim': 'Statement claim',
    'entity_proposal': 'Entity for the graph',
    'glossary_term': 'Code-word meaning',
}
MAX_CITATIONS = 20
MAX_RECORD_CITATIONS = 500
MAX_WHY = 1200
CITATION = re.compile(r'^(txn|doc|rec)://([^\s#]+)(#\S*)?$')
NOT_IN_CASE = 'Not in this case.'


class ProposalError(ValueError):
    def __init__(self, message, status_code=422):
        super().__init__(message)
        self.status_code = status_code


def is_proposal(rule_id: str) -> bool:
    return str(rule_id or '').startswith(PREFIX)


# ---------------------------------------------------------------------------
# Who proposed it
# ---------------------------------------------------------------------------

def agent_origin(*, for_name: str, for_user_id: Any = None, model: str, model_id: str = '', run_id: Any = None,
                 thread_id: Any = None, how: str = 'case agent proposal') -> dict:
    """The model origin of a proposal (``model_work.model_origin``) with the agent run it came from."""
    from services.financial.model_work import model_origin
    origin = model_origin(for_name=for_name, for_user_id=for_user_id, model=model, model_id=model_id, how=how)
    if run_id:
        origin['run_id'] = str(run_id)
    if thread_id:
        origin['thread_id'] = str(thread_id)
    return origin


def _require_origin(origin: Mapping[str, Any]) -> dict:
    from services.financial.model_work import is_model
    if not is_model(origin):
        raise ProposalError('A proposal is a model\'s work: it needs the model origin of the run that made it.')
    return dict(origin)


# ---------------------------------------------------------------------------
# Citations
# ---------------------------------------------------------------------------

def _uuid(value) -> Optional[uuid.UUID]:
    try:
        return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
    except (TypeError, ValueError):
        return None


def check_citations(session, case_id, citations: Iterable[str]) -> list[dict]:
    """[{citation, scheme, status: 'valid'|'not_in_case'|'invalid', label}] for each citation, checked against the
    case. ``txn://``, ``doc://`` and ``rec://`` are checked against the case's own rows (phone records in one query);
    when the agent-citations checker is present (``services.case_citations.resolve_citations``) it must pass too, in
    one call for the whole list."""
    try:
        from services import case_citations  # type: ignore
    except ImportError:  # agent-citations not yet merged: the local check below is the whole check
        case_citations = None
    texts = [str(raw or '').strip() for raw in citations]
    matches = [CITATION.match(t) for t in texts]
    records = _records_in_case(session, _uuid(case_id), [m.group(2) for m in matches if m and m.group(1) == 'rec'])
    out = []
    for text, match in zip(texts, matches):
        if not match:
            out.append(dict(citation=text, scheme='', status='invalid', label='Not a source link.'))
            continue
        out.append(_local_check(session, case_id, match.group(1), match.group(2), text, records))
    if case_citations is not None and hasattr(case_citations, 'resolve_citations'):
        # Both checks must pass: the shared checker also refuses an ambiguous or foreign link.
        try:
            valid = [i for i, o in enumerate(out) if o['status'] == 'valid']
            parsed = [case_citations.parse_citation(out[i]['citation']) for i in valid]
            pairs = [(i, p) for i, p in zip(valid, parsed) if p is not None]
            for i in (i for i, p in zip(valid, parsed) if p is None):
                out[i] = dict(out[i], status='invalid', label='Not a source link.')
            resolved = case_citations.resolve_citations(session, case_id, [p for _, p in pairs]) if pairs else []
            for (i, _), r in zip(pairs, resolved):
                if r.status != 'ok':
                    out[i] = dict(out[i], status='not_in_case', label=getattr(r, 'reason', None) or NOT_IN_CASE)
        except Exception:  # noqa: BLE001 - the local check stands
            log.exception('Citation check through case_citations failed for case %s', case_id)
    return out


def _records_in_case(session, case_id, uids) -> set[str]:
    """The phone records of the case among ``uids`` (pv_record, as the agent-citations checker reads it), lower
    case, in one query."""
    from sqlalchemy import bindparam, inspect, text as sql
    wanted = sorted({str(_uuid(u)) for u in uids if _uuid(u) is not None})
    if not wanted or case_id is None:
        return set()
    conn = session.connection()
    if not inspect(conn).has_table('pv_record'):
        return set()
    if conn.dialect.name == 'postgresql':
        rows = session.execute(sql('SELECT record_uid FROM pv_record WHERE case_id = CAST(:c AS uuid) AND '
                                   'record_uid = ANY(CAST(:u AS uuid[]))'), dict(c=str(case_id), u=wanted))
    else:
        rows = session.execute(sql('SELECT record_uid FROM pv_record WHERE case_id = :c AND lower(record_uid) IN '
                                   ':u').bindparams(bindparam('u', expanding=True)), dict(c=str(case_id), u=wanted))
    return {str(r[0]).lower() for r in rows}


def _local_check(session, case_id, scheme, rest, text, records=frozenset()):
    from postgres.models.evidence import EvidenceFile
    from postgres.models.financial import FinancialTransaction
    if scheme == 'txn':
        row = session.get(FinancialTransaction, _uuid(rest)) if _uuid(rest) else None
        if row is None or row.case_id != _uuid(case_id):
            return dict(citation=text, scheme=scheme, status='not_in_case', label=NOT_IN_CASE)
        return dict(citation=text, scheme=scheme, status='valid',
                    label=f"Payment {(row.description or '')[:80]}".strip())
    if scheme == 'doc':
        file_part, _, page = rest.partition('/')
        file = session.get(EvidenceFile, _uuid(file_part)) if _uuid(file_part) else None
        if file is None or file.case_id != _uuid(case_id):
            return dict(citation=text, scheme=scheme, status='not_in_case', label=NOT_IN_CASE)
        if page and not page.isdigit():
            return dict(citation=text, scheme=scheme, status='invalid', label='The page is not a number.')
        return dict(citation=text, scheme=scheme, status='valid',
                    label=(file.original_filename or 'File') + (f', page {page}' if page else ''))
    if scheme == 'rec':
        uid = rest.partition('#')[0]
        if _uuid(uid) is None or str(_uuid(uid)) not in records:
            return dict(citation=text, scheme=scheme, status='not_in_case', label=NOT_IN_CASE)
        return dict(citation=text, scheme=scheme, status='valid', label='Phone record')
    return dict(citation=text, scheme=scheme, status='not_in_case', label=NOT_IN_CASE)


def _checked_citations(session, case_id, citations, extra=(), limit=MAX_CITATIONS):
    """Every citation checked against the case. ``limit``: the model's own citations are capped at 20; a lead card
    or a phone draft cites every alert or strand the code found, up to ``MAX_RECORD_CITATIONS``."""
    wanted = list(dict.fromkeys([str(c).strip() for c in list(citations or []) + list(extra) if str(c).strip()]))
    if not wanted:
        raise ProposalError('A proposal cites at least one source in this case.')
    if len(wanted) > limit:
        raise ProposalError(f'A proposal cites at most {limit} sources; this one cites {len(wanted)}.')
    checked = check_citations(session, case_id, wanted)
    bad = [c for c in checked if c['status'] != 'valid']
    if bad:
        raise ProposalError('Each cited source must be in this case: '
                            + '; '.join(f"{c['citation']}: {c['label']}" for c in bad))
    return checked


def _why(text):
    text = ' '.join(str(text or '').split())
    if not text:
        raise ProposalError('Say why: the reason is what the person checks against the source.')
    return text[:MAX_WHY]


# ---------------------------------------------------------------------------
# Ledger proposals (A)
# ---------------------------------------------------------------------------

MONTH = re.compile(r'^(\d{4})-(\d{2})$')


def _month_bounds(month: str):
    match = MONTH.match(str(month or '').strip())
    if not match or not 1 <= int(match.group(2)) <= 12:
        raise ProposalError('Give the month as YYYY-MM.')
    year, mon = int(match.group(1)), int(match.group(2))
    first = date(year, mon, 1)
    last = (date(year + (mon == 12), mon % 12 + 1, 1) - timedelta(days=1))
    return first, last


def _record(session, *, case_id, subject_type, subject_id, kind, target_key, reading, summary, evidence,
            source_document_id=None, statement_period_id=None):
    from services.financial.judgements import record_judgement
    from postgres.models.financial_judgements import FinancialJudgement as J
    rule_id = KINDS[kind]
    existing = session.scalar(select(J).where(J.subject_type == subject_type, J.subject_id == subject_id,
                                              J.rule_id == rule_id, J.target_key == target_key,
                                              J.reading == reading))
    if existing is not None:
        return existing, False
    row = record_judgement(session, case_id=case_id, subject_type=subject_type, subject_id=subject_id,
                           rule_id=rule_id, summary=summary, strength='inferred', evidence=evidence,
                           target_key=target_key, reading=reading, source_document_id=source_document_id,
                           statement_period_id=statement_period_id, origin='agent')
    if row is None:
        raise ProposalError('The proposal could not be recorded.', 500)
    return row, True


def _proposal_evidence(kind, value, why, checked, origin, **extra):
    return dict(proposal=dict(kind=kind, value=value, why=why, citations=[c['citation'] for c in checked],
                              citation_check=checked, origin=origin), **extra)


def _account_label(account):
    ending = re.sub(r'\D', '', account.identifier_normalised or account.identifier_as_printed or '')[-4:]
    parts = [account.institution_name, f'ending {ending}' if ending else None, account.holder_name]
    return ' · '.join(p for p in parts if p) or 'the account'


def propose_missing_month(session, *, case_id, account_id, month, why, citations=(), origin):
    """A month no statement covers on an account: recorded only when continuity has a gap over it."""
    from postgres.models.evidence import EvidenceFile
    from postgres.models.financial import FinancialAccount, FinancialSourceDocument
    from services.financial.continuity import read_account_continuity
    origin = _require_origin(origin)
    why = _why(why)
    first, last = _month_bounds(month)
    account = session.get(FinancialAccount, _uuid(account_id)) if _uuid(account_id) else None
    if account is None or account.case_id != _uuid(case_id):
        raise ProposalError(NOT_IN_CASE, 404)
    run = read_account_continuity(session, case_id=account.case_id, account_id=account.id)
    seam = None
    for gap in run.gaps:
        uncovered_from, uncovered_to = gap.earlier.end + timedelta(days=1), gap.later.start - timedelta(days=1)
        if uncovered_from <= last and uncovered_to >= first:
            seam = gap
            break
    if seam is None:
        covered = (run.covered_from and run.covered_to and run.covered_from <= first and last <= run.covered_to)
        raise ProposalError(
            f"The account's statements cover {first:%B %Y}: there is no gap to propose." if covered else
            f"{first:%B %Y} is not between two of this account's statements, so the case cannot say it is missing "
            'from the statements alone.', 409)
    sources = []
    for link in (seam.earlier, seam.later):
        document = session.get(FinancialSourceDocument, link.document_id)
        if document is not None and document.evidence_file_id:
            sources.append(f'doc://{document.evidence_file_id}')
    checked = _checked_citations(session, case_id, citations, extra=sources)
    files = {}
    for link in (seam.earlier, seam.later):
        document = session.get(FinancialSourceDocument, link.document_id)
        file = session.get(EvidenceFile, document.evidence_file_id) if document and document.evidence_file_id else None
        files[link.period_id] = getattr(file, 'original_filename', None)
    summary = (f"No statement of {_account_label(account)} covers {first:%B %Y}: the statement ending "
               f"{seam.earlier.end:%d %b %Y} and the next starting {seam.later.start:%d %b %Y} leave "
               f"{seam.uncovered_days} days uncovered. Proposed by {origin['model']} (case agent): {why}")
    evidence = _proposal_evidence(
        'missing_month', f'{first:%Y-%m}', why, checked, origin,
        gap=dict(after=seam.earlier.end.isoformat(), before=seam.later.start.isoformat(), days=seam.uncovered_days,
                 earlier_period_id=str(seam.earlier.period_id), later_period_id=str(seam.later.period_id),
                 earlier_file=files.get(seam.earlier.period_id), later_file=files.get(seam.later.period_id)),
        account_label=_account_label(account))
    row, created = _record(session, case_id=account.case_id, subject_type='account', subject_id=account.id,
                           kind='missing_month', target_key=f'month:{first:%Y-%m}', reading='agent',
                           summary=summary, evidence=evidence, statement_period_id=seam.earlier.period_id,
                           source_document_id=seam.earlier.document_id)
    session.commit()
    return _out(row, created)


def _current_payment(session, case_id, transaction_id):
    from postgres.models.financial import FinancialTransaction
    row = session.get(FinancialTransaction, _uuid(transaction_id)) if _uuid(transaction_id) else None
    if row is None or row.case_id != _uuid(case_id):
        raise ProposalError(NOT_IN_CASE, 404)
    if row.ledger_status != 'admitted' or row.superseded_by_id is not None:
        raise ProposalError('This payment was replaced or set aside; propose on the current payment.', 409)
    return row


def _payment_words(row):
    from services.financial.judgements import money
    currency = getattr(row, 'currency', None) or ''
    when = row.transaction_date.isoformat() if row.transaction_date else 'no printed date'
    return f"the payment of {money(row.amount_minor, currency)} on {when} ({' '.join((row.description or '').split())[:80]})"


def propose_category(session, *, case_id, transaction_id, category, why, citations=(), origin):
    from postgres.models.financial_payment_category import FinancialPaymentCategory as C
    from services.financial.payment_categories import _choices
    origin = _require_origin(origin)
    why = _why(why)
    row = _current_payment(session, case_id, transaction_id)
    choices = {c.lower(): c for c in _choices(session)}
    chosen = choices.get(str(category or '').strip().lower())
    if not chosen:
        raise ProposalError('Propose a category from the case\'s category library.')
    stored = session.get(C, row.id)
    if stored is not None and stored.origin in ('person', 'learned'):
        raise ProposalError(f'A person already chose "{stored.category or "Uncategorized"}" for this payment; '
                            'the agent does not propose over a person\'s choice.', 409)
    if stored is not None and (stored.category or '') == chosen:
        raise ProposalError(f'This payment is already "{chosen}".', 409)
    checked = _checked_citations(session, case_id, citations, extra=[f'txn://{row.id}'])
    before = (stored.category if stored is not None else None) or 'Uncategorized'
    summary = (f'Category "{chosen}" for {_payment_words(row)}, now "{before}". Proposed by {origin["model"]} '
               f'(case agent): {why}')
    evidence = _proposal_evidence('category', chosen, why, checked, origin, before=before, chosen=chosen,
                                  transaction_id=str(row.id))
    judgement, created = _record(session, case_id=row.case_id, subject_type='transaction', subject_id=row.id,
                                 kind='category', target_key='category', reading=chosen[:80], summary=summary,
                                 evidence=evidence, source_document_id=row.source_document_id,
                                 statement_period_id=row.statement_period_id)
    session.commit()
    return _out(judgement, created)


def propose_counterparty(session, *, case_id, transaction_id, link, why, citations=(), origin):
    """``link``: {kind: 'party'|'account', id}."""
    from services.financial.account_parties import AccountPartyError
    from services.financial.payment_counterparty_link import PaymentCounterpartyLink, effective_link, resolve_link
    origin = _require_origin(origin)
    why = _why(why)
    row = _current_payment(session, case_id, transaction_id)
    try:
        wanted = PaymentCounterpartyLink(**dict(link or {}))
        resolved = resolve_link(session, case_id=row.case_id, link=wanted)
    except AccountPartyError as exc:
        raise ProposalError(str(exc), 409) from exc
    except Exception as exc:  # noqa: BLE001 - a malformed link from the model
        raise ProposalError('Name the person, business or account of this case: {kind, id}.') from exc
    current = effective_link(row) or {}
    if current.get('kind') == resolved['kind'] and str(current.get('id')) == resolved['id']:
        raise ProposalError(f'This payment is already linked to {resolved["label"]}.', 409)
    checked = _checked_citations(session, case_id, citations, extra=[f'txn://{row.id}'])
    before = current.get('label') or (row.counterparty_raw or '').strip() or 'no identity'
    summary = (f'The other side of {_payment_words(row)} is {resolved["label"]} (now: {before}). Proposed by '
               f'{origin["model"]} (case agent): {why}')
    evidence = _proposal_evidence('counterparty', resolved, why, checked, origin, before=before,
                                  chosen=resolved['label'], transaction_id=str(row.id))
    judgement, created = _record(session, case_id=row.case_id, subject_type='transaction', subject_id=row.id,
                                 kind='counterparty', target_key='counterparty',
                                 reading=f"{resolved['kind']}:{resolved['id']}"[:80], summary=summary,
                                 evidence=evidence, source_document_id=row.source_document_id,
                                 statement_period_id=row.statement_period_id)
    session.commit()
    return _out(judgement, created)


def _out(row, created):
    from services.financial.judgements import as_dict
    item = as_dict(row)
    item['created'] = created
    return item


# ---------------------------------------------------------------------------
# Open the source before confirming (C)
# ---------------------------------------------------------------------------

def _proposal_citations(session, case_id, proposal_type, proposal_id) -> list[str]:
    if proposal_type == 'judgement':
        from postgres.models.financial_judgements import FinancialJudgement as J
        row = session.scalar(select(J).where(J.id == proposal_id, J.case_id == case_id))
        if row is None or not is_proposal(row.rule_id):
            raise ProposalError('Proposal not found in this case.', 404)
        return list(((row.evidence or {}).get('proposal') or {}).get('citations') or [])
    if proposal_type == 'workspace_ai':
        from postgres.models.workspace_ai import WorkspaceAIOutput
        item = session.scalar(select(WorkspaceAIOutput).where(WorkspaceAIOutput.id == proposal_id,
                                                              WorkspaceAIOutput.case_id == case_id))
        if item is None:
            raise ProposalError('Proposal not found in this case.', 404)
        cited = [c.get('cite') or c.get('citation') for c in item.citations or [] if isinstance(c, dict)]
        cited += list((item.content or {}).get('citations') or [])
        return [c for c in dict.fromkeys(cited) if c]
    raise ProposalError('Unknown proposal type.')


def record_open(session, *, case_id, proposal_type, proposal_id, citation, user):
    """A person opened one of the proposal's cited sources. Only a source the proposal cites counts."""
    from postgres.models.agent_proposals import AgentProposalSourceOpen
    proposal_id = _uuid(proposal_id)
    if proposal_id is None:
        raise ProposalError('Invalid proposal id.')
    citation = str(citation or '').strip()
    cited = _proposal_citations(session, _uuid(case_id), proposal_type, proposal_id)
    if citation not in cited:
        raise ProposalError('That source is not one this proposal cites.', 409)
    row = AgentProposalSourceOpen(id=uuid.uuid4(), case_id=_uuid(case_id), proposal_type=proposal_type,
                                  proposal_id=proposal_id, citation=citation[:600],
                                  user_id=getattr(user, 'id', None) or getattr(user, 'user_id', None),
                                  user_email=getattr(user, 'email', None))
    session.add(row)
    session.commit()
    return dict(proposal_type=proposal_type, proposal_id=str(proposal_id), citation=citation,
                opened=opened_by(session, proposal_type, proposal_id, user))


def opened_by(session, proposal_type, proposal_id, user) -> list[str]:
    from postgres.models.agent_proposals import AgentProposalSourceOpen as O
    user_id = getattr(user, 'id', None) or getattr(user, 'user_id', None)
    email = getattr(user, 'email', None)
    query = select(O.citation).where(O.proposal_type == proposal_type, O.proposal_id == _uuid(proposal_id))
    if user_id is not None:
        query = query.where(O.user_id == user_id)
    else:
        query = query.where(O.user_email == email)
    return list(dict.fromkeys(session.scalars(query.order_by(O.opened_at))))


def review_facts(session, proposal_type, proposal_id, user, *, via='api') -> dict:
    """What a confirmation records about the person's check: which cited sources they opened before it."""
    opened = opened_by(session, proposal_type, proposal_id, user)
    return dict(source_opened=bool(opened), opened=opened, via=via if via in ('ui', 'api') else 'api',
                at=datetime.now(timezone.utc).isoformat())


# ---------------------------------------------------------------------------
# A person's answer on a ledger proposal
# ---------------------------------------------------------------------------

def _load(session, case_id, judgement_id):
    from services.financial.judgements import _get
    row = _get(session, case_id, judgement_id)
    if not is_proposal(row.rule_id):
        raise ProposalError('This judgement call is not an agent proposal.', 409)
    return row


def confirm(session, *, case_id, judgement_id, actor, user, reason='', via='api'):
    """A person accepts the proposal: it is applied through the existing person path (category, counterparty), the
    call is confirmed with what the person opened first, and the applied record names the model that proposed it."""
    from services.financial.judgements import _require_person, as_dict
    _require_person(actor)
    row = _load(session, case_id, judgement_id)
    if row.status != 'open':
        raise ProposalError(f'This proposal is already {row.status}.', 409)
    facts = review_facts(session, 'judgement', row.id, user, via=via)
    # Confirmed before applying, so the person path's own settling of open proposals leaves this one to us.
    row.status, row.resolved_by, row.resolved_by_email = 'confirmed', actor.name, actor.email
    session.flush()
    applied = _apply(session, row, actor, facts)
    row.resolved_at = datetime.now(timezone.utc)
    row.resolution_reason = (reason or '').strip() or None
    row.evidence = dict(row.evidence or {}, review=facts, applied=applied)
    session.commit()
    return as_dict(row)


def _apply(session, row, actor, facts):
    """Apply an accepted category or counterparty through the label path a person uses; a missing month is a lead
    and changes no ledger value."""
    kind = RULE_KIND.get(row.rule_id)
    proposal = (row.evidence or {}).get('proposal') or {}
    if kind == 'missing_month':
        return dict(kind=kind, changed=False)
    from services.financial.payment_labels import PaymentLabelsError, PaymentLabelsRequest, update_payment_labels
    from postgres.models.financial import FinancialTransaction
    payment = session.get(FinancialTransaction, row.subject_id)
    if payment is None or payment.ledger_status != 'admitted' or payment.superseded_by_id is not None:
        raise ProposalError('The payment was replaced or set aside since the proposal; nothing was applied.', 409)
    version = ((payment.metadata_ or {}).get('investigation_labels') or {}).get('version', 0)
    target = [dict(id=payment.id, version=version)]
    if kind == 'category':
        request = PaymentLabelsRequest(transactions=target, category=proposal.get('value'))
    else:
        value = proposal.get('value') or {}
        request = PaymentLabelsRequest(transactions=target, counterparty_link=dict(kind=value['kind'], id=value['id']))
    origin = proposal.get('origin') or {}
    reason = (f"Proposed by {origin.get('model') or 'the case agent'} (case agent), accepted by {actor.name}"
              + (' after opening ' + ', '.join(facts['opened']) if facts['opened'] else ' without opening a source'))
    try:
        result = update_payment_labels(session, case_id=row.case_id, request=request, actor=actor, commit=False,
                                       reason=reason, proposed_by=dict(origin=origin, judgement_id=str(row.id)))
    except PaymentLabelsError as exc:
        raise ProposalError(str(exc), exc.status_code) from exc
    return dict(kind=kind, changed=bool(result.get('changed')), reason=reason)


def reject(session, *, case_id, judgement_id, actor, user, reason):
    """The proposal is wrong and there is nothing to change. Like a correction, the reason feeds the lessons."""
    from services.financial.judgements import _require_person, as_dict
    _require_person(actor)
    reason = (reason or '').strip()
    if not reason:
        raise ProposalError('Say why the proposal is wrong; the reason is what the agent learns from.')
    row = _load(session, case_id, judgement_id)
    if row.status != 'open':
        raise ProposalError(f'This proposal is already {row.status}.', 409)
    facts = review_facts(session, 'judgement', row.id, user)
    proposal = (row.evidence or {}).get('proposal') or {}
    value = proposal.get('value')
    shown = value.get('label') if isinstance(value, dict) else value
    row.status, row.resolved_by, row.resolved_by_email = 'rejected', actor.name, actor.email
    row.resolved_at, row.resolution_reason = datetime.now(timezone.utc), reason
    row.evidence = dict(row.evidence or {}, review=facts, correction=dict(before=shown, after='(rejected)'))
    session.commit()
    return as_dict(row)


def on_person_category(session, row, category, actor):
    """A person set a payment's category in the ledger: an open category proposal for it is settled — confirmed when
    the person chose the proposed category, corrected (and sent to the lessons) when they chose another."""
    from postgres.models.financial_judgements import FinancialJudgement as J
    try:
        for judgement in session.scalars(select(J).where(J.subject_type == 'transaction', J.subject_id == row.id,
                                                         J.rule_id == KINDS['category'], J.status == 'open')):
            proposed = ((judgement.evidence or {}).get('proposal') or {}).get('value')
            same = (proposed or '') == (category or '')
            judgement.status = 'confirmed' if same else 'corrected'
            judgement.resolved_by = getattr(actor, 'name', None)
            judgement.resolved_by_email = getattr(actor, 'email', None)
            judgement.resolved_at = datetime.now(timezone.utc)
            judgement.resolution_reason = ('Category chosen in the ledger.' if same
                                           else 'Category changed by an investigator.')
            judgement.evidence = {**(judgement.evidence or {}),
                                  'review': dict(source_opened=None, opened=[], via='ledger'),
                                  **({} if same else {'correction': dict(before=proposed,
                                                                         after=category or 'Uncategorized')})}
            session.flush()
            if not same:
                from services.financial.payment_categories import _append_to_inbox
                _append_to_inbox(session, judgement)
    except Exception:  # noqa: BLE001 - the person's category stands
        log.exception('Settling the category proposal on %s failed', row.id)


# ---------------------------------------------------------------------------
# Measured: confirmations with the source opened (C) and the precision trend (F)
# ---------------------------------------------------------------------------

def _week(value: datetime) -> str:
    iso = value.isocalendar()
    return f'{iso[0]}-W{iso[1]:02d}'


def precision(session, case_id=None, case_ids=None) -> dict:
    """Per proposal kind: open / accepted / corrected / rejected in total and per ISO week of the answer, and the
    share of confirmations made after a cited source was opened. Ledger proposals and Workspace AI agent drafts."""
    from postgres.models.financial_judgements import FinancialJudgement as J
    from postgres.models.workspace_ai import WorkspaceAIOutput as W
    kinds: dict[str, Counter] = {}
    weeks: dict[str, dict[str, Counter]] = {}
    opened = Counter()
    query = select(J.rule_id, J.status, J.resolved_at, J.evidence).where(J.rule_id.like(PREFIX + '%'))
    if case_id is not None:
        query = query.where(J.case_id == case_id)
    if case_ids is not None:  # only the cases the reader can open
        query = query.where(J.case_id.in_(list(case_ids)))
    for rule_id, status, resolved_at, evidence in session.execute(query):
        kind = RULE_KIND.get(rule_id, rule_id[len(PREFIX):])
        outcome = 'accepted' if status == 'confirmed' else status
        kinds.setdefault(kind, Counter())[outcome] += 1
        if resolved_at is not None and status != 'open':
            weeks.setdefault(kind, {}).setdefault(_week(resolved_at), Counter())[outcome] += 1
        if status == 'confirmed':
            seen = ((evidence or {}).get('review') or {}).get('source_opened')
            opened['confirmed'] += 1
            opened['with_source_opened'] += seen is True
            opened['without_source_opened'] += seen is False
    from services.agent.workspace_proposals import AGENT_OUTPUT_TYPES
    wquery = select(W.output_type, W.review_status, W.reviewed_at, W.model_metadata).where(
        W.output_type.in_(AGENT_OUTPUT_TYPES))
    if case_id is not None:
        wquery = wquery.where(W.case_id == case_id)
    if case_ids is not None:
        wquery = wquery.where(W.case_id.in_(list(case_ids)))
    for output_type, status, reviewed_at, meta in session.execute(wquery):
        outcome = dict(pending_review='open', accepted='accepted', rejected='rejected').get(status, status)
        kinds.setdefault(output_type, Counter())[outcome] += 1
        if reviewed_at is not None and outcome != 'open':
            weeks.setdefault(output_type, {}).setdefault(_week(reviewed_at), Counter())[outcome] += 1
        if status == 'accepted':
            seen = ((meta or {}).get('review') or {}).get('source_opened')
            opened['confirmed'] += 1
            opened['with_source_opened'] += seen is True
            opened['without_source_opened'] += seen is False
    rows = []
    for kind in sorted(kinds, key=lambda k: (list(KIND_LABELS).index(k) if k in KIND_LABELS else 99, k)):
        c = kinds[kind]
        decided = c['accepted'] + c['corrected'] + c['rejected']
        rows.append(dict(kind=kind, label=KIND_LABELS.get(kind, kind), open=c['open'], accepted=c['accepted'],
                         corrected=c['corrected'], rejected=c['rejected'], decided=decided,
                         weeks=[dict(week=w, accepted=v['accepted'], corrected=v['corrected'],
                                     rejected=v['rejected'])
                                for w, v in sorted((weeks.get(kind) or {}).items())]))
    return dict(kinds=rows, confirmations=dict(total=opened['confirmed'],
                                               with_source_opened=opened['with_source_opened'],
                                               without_source_opened=opened['without_source_opened']))
