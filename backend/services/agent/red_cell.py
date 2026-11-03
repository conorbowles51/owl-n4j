"""Red cell: an "away from the suspect" sweep on a different model (agent-proposals D).

For a Workspace theory, the red cell reads the same evidence the theory rests on (the theory's own sources, as
Workspace AI reads them, plus the ledger payments linked to it) and asks a model other than the case agent's for
explanations of those facts, innocent ones included. The prompt leaves the framing out: the theory's title and text
are never sent, and the names the theory uses are replaced by neutral labels (Person A, Person B) in the facts.
Models anchor on given hints, so the hint is withheld rather than argued with.

Each explanation becomes a Workspace AI proposal (``alternative_explanation``) with its citations checked against
the case, pending review. Its value is measured, not assumed: the precision report counts the alternatives a person
accepted and rejected (``services.agent.proposals.precision``), and the count stays visible on the screen.

Which model: the first configured one in ``CANDIDATES`` that is not the agent's own model, preferring another
provider; the output records which, and that the agent used another.
"""
from __future__ import annotations

import json
import logging
import re
import uuid
from typing import Any, Callable, Optional

from sqlalchemy import select

from services.agent.proposals import ProposalError, _uuid

log = logging.getLogger(__name__)

CANDIDATES = (('anthropic', 'claude-opus-4-8'), ('gemini', 'gemini-3.5-flash'), ('openai', 'gpt-5.6-sol'),
              ('deepseek', 'deepseek-v4-pro'), ('deepseek', 'deepseek-v4-flash'))
MAX_ALTERNATIVES = 6
MAX_FACT_CHARS = 2400
PROMPT = """You are reviewing evidence for an investigation. Below are numbered facts, each from a cited source.
List the explanations that fit these facts, at least three and at most {limit}. Include ordinary, innocent and
lawful explanations, and explanations that point to someone other than any one person. For each, say which facts it
rests on and what evidence would tell it apart from the others. Do not assume anyone did anything wrong.

Answer with JSON only: {{"alternatives": [{{"title": "...", "explanation": "...", "facts": ["F1", ...],
"would_tell_apart": "..."}}]}}

Facts:
{facts}
"""


def choose_model(agent_provider: str, agent_model: str, configured: Callable[[str], bool]):
    """(provider, model_id, same_provider) of the red cell's model, or None when no other model is configured."""
    others = [c for c in CANDIDATES if c != (agent_provider, agent_model) and configured(c[0])]
    other_provider = [c for c in others if c[0] != agent_provider]
    pick = (other_provider or others or [None])[0]
    return None if pick is None else (pick[0], pick[1], pick[0] == agent_provider)


_NAME = re.compile(r"\b[A-Z][a-zà-ÿ'’-]+(?:\s+[A-Z][a-zà-ÿ'’-]+)+\b")


def framing_names(title: str, body: str) -> dict[str, str]:
    """{name or part of a name the theory uses: neutral label}. One label per full name, shared by its parts, the
    same in every fact. Longest first when applied, so a full name is replaced before its parts."""
    labels: dict[str, str] = {}
    full = []
    for m in _NAME.finditer(f'{title or ""}\n{body or ""}'):
        if m.group(0) not in full:
            full.append(m.group(0))
    for i, name in enumerate(full):
        label = f'Person {chr(ord("A") + i % 26)}' + (f'{i // 26}' if i >= 26 else '')
        labels.setdefault(name, label)
        for part in name.split():
            if len(part) > 2:
                labels.setdefault(part, label)
    return labels


def neutralise(text: str, labels: dict[str, str]) -> str:
    for name in sorted(labels, key=lambda n: (-len(n), n)):
        text = re.sub(rf'\b{re.escape(name)}\b', labels[name], text)
    return text


def _facts(session, case_id, theory) -> list[dict]:
    """[{fact_id, cite, text}] from the theory's evidence and linked ledger payments."""
    from postgres.models.financial import FinancialTransaction
    from postgres.models.workspace_entry import WorkspaceEntryLink
    from services.financial.judgements import money
    from services.workspace_ai_service import _theory_sources
    facts = []
    sources, _ = _theory_sources(session, case_id=case_id, theory=theory)
    for source in sources:
        anchor = source.get('source_anchor') or {}
        if anchor.get('kind') == 'phone_record' and anchor.get('record_uid'):
            cite = f"rec://{anchor['record_uid']}"
        else:
            page = anchor.get('page') or anchor.get('page_number')
            cite = f"doc://{source['evidence_file_id']}" + (f'/{page}' if page else '')
        facts.append(dict(cite=cite, text=str(source.get('text') or '')[:MAX_FACT_CHARS]))
    for link in session.scalars(select(WorkspaceEntryLink).where(
            WorkspaceEntryLink.entry_id == theory.id, WorkspaceEntryLink.case_id == case_id,
            WorkspaceEntryLink.target_type == 'financial_transaction')):
        row = session.get(FinancialTransaction, _uuid(link.target_id))
        if row is None or row.case_id != case_id or row.ledger_status != 'admitted' or row.superseded_by_id:
            continue
        when = row.transaction_date.isoformat() if row.transaction_date else 'no printed date'
        facts.append(dict(cite=f'txn://{row.id}', text=(
            f"Payment {'in' if row.direction == 'credit' else 'out'} of {money(row.amount_minor, row.currency or '')} "
            f"{row.currency or ''} on {when}: {' '.join((row.description or '').split())[:300]}")))
    for i, fact in enumerate(facts, 1):
        fact['fact_id'] = f'F{i}'
    return facts


def _reader(session, provider, model_id):
    from services.ai_provider_credentials import get_provider_api_key
    from services.llm_service import LLMExecutionContext
    api_key = get_provider_api_key(session, provider)
    if not api_key:
        raise ProposalError(f'No {provider} key is configured for the red cell.', 409)

    def read(prompt):
        return LLMExecutionContext(provider, model_id, api_key=api_key).call(prompt, temperature=0.4, json_mode=True,
                                                                             timeout=180)
    return read


def _parse(text) -> list[dict]:
    if isinstance(text, dict):
        data = text
    else:
        raw = str(text or '').strip()
        raw = raw[raw.find('{'):raw.rfind('}') + 1] if '{' in raw else raw
        try:
            data = json.loads(raw)
        except ValueError as exc:
            raise ProposalError('The red cell model did not answer in the expected form; nothing was recorded.',
                                502) from exc
    items = data.get('alternatives') if isinstance(data, dict) else None
    return [i for i in items or [] if isinstance(i, dict)][:MAX_ALTERNATIVES]


def sweep(session, *, case_id, theory_id, requested_by, reader=None, model=None, agent_model=None) -> dict:
    """Run the red cell for one theory. ``reader(prompt) -> text`` and ``model`` = (provider, model_id) for tests;
    otherwise chosen with ``choose_model`` against the case agent's model."""
    from postgres.models.workspace_entry import WorkspaceEntry
    from services.agent.proposals import agent_origin
    from services.agent.workspace_proposals import _store
    from services.agent.proposals import _checked_citations
    case_id = _uuid(case_id)
    theory = session.get(WorkspaceEntry, _uuid(theory_id)) if _uuid(theory_id) else None
    if theory is None or theory.case_id != case_id or theory.entry_type != 'theory' or theory.deleted_at:
        raise ProposalError('Not in this case.', 404)
    facts = _facts(session, case_id, theory)
    if not facts:
        raise ProposalError('This theory has no linked evidence or payments for the red cell to read.', 409)
    if agent_model is None:
        from services.ai_model_policy import get_workload_model
        agent_model = get_workload_model(session, 'agent')
    if model is None:
        from services.ai_model_policy import provider_is_configured
        chosen = choose_model(agent_model[0], agent_model[1], lambda p: provider_is_configured(p, session))
        if chosen is None:
            raise ProposalError('No model other than the case agent\'s is configured, so the red cell cannot run.',
                                409)
        model = chosen[:2]
    reader = reader or _reader(session, *model)
    names = framing_names(theory.title or '', theory.body or '')
    lines = [f"{f['fact_id']} [{f['cite']}]: {neutralise(' '.join(f['text'].split()), names)}" for f in facts]
    prompt = PROMPT.format(limit=MAX_ALTERNATIVES, facts='\n'.join(lines))
    alternatives = _parse(reader(prompt))
    by_id = {f['fact_id']: f['cite'] for f in facts}
    origin = agent_origin(for_name=requested_by.name or requested_by.email, for_user_id=requested_by.id,
                          model=model[1], model_id=model[1], how='red cell: away from the suspect')
    origin['red_cell'] = dict(provider=model[0], model_id=model[1], agent_provider=agent_model[0],
                              agent_model_id=agent_model[1], framing_removed=True, names_neutralised=len(names),
                              facts=len(facts), theory_id=str(theory.id))
    recorded, refused = [], []
    for alt in alternatives:
        cites = [by_id[f] for f in alt.get('facts') or [] if f in by_id]
        title = ' '.join(str(alt.get('title') or '').split())[:255]
        body = str(alt.get('explanation') or '').strip()
        if alt.get('would_tell_apart'):
            body += f"\n\nWhat would tell it apart: {str(alt['would_tell_apart']).strip()}"
        if not (title and body and cites):
            refused.append(dict(title=title or None, why='no title, text or cited fact'))
            continue
        try:
            checked = _checked_citations(session, case_id, cites)
        except ProposalError as exc:
            refused.append(dict(title=title, why=str(exc)))
            continue
        recorded.append(_store(session, case_id=case_id, output_type='alternative_explanation',
                               content=dict(title=title, body=body[:8000], theory_id=str(theory.id),
                                            theory_title=theory.title, facts=[f for f in alt.get('facts') or []
                                                                              if f in by_id]),
                               checked=checked, action=dict(action='create_alternative_theory',
                                                            theory_id=str(theory.id)),
                               origin=origin, requested_by_user_id=requested_by.id))
    return dict(theory_id=str(theory.id), model=dict(provider=model[0], model_id=model[1]),
                agent_model=dict(provider=agent_model[0], model_id=agent_model[1]), facts=len(facts),
                names_neutralised=len(set(names.values())), returned=len(alternatives), recorded=len(recorded),
                refused=refused, proposals=recorded)
