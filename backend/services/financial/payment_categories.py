"""Every payment has a stored category, and the ledger reads it rather than guessing on each read.

Who decides, in order of precedence:

1. ``person``  - an investigator chose it (also kept in ``metadata.investigation_labels``, as before). Never replaced
   by any automatic pass.
2. ``learned`` - an investigator applied their choice to the payments like it (same description stem or the same
   printed counterparty, in the same case). Never replaced by an automatic pass either.
3. ``rule``    - the description rules in :mod:`services.financial.payment_inference`.
4. ``model``   - the model classifier, for descriptions the rules cannot place. Batched by distinct description stem
   and cached across cases by stem. Below :data:`MODEL_THRESHOLD` the category is still assigned, and a judgement call
   (``category.model``, inferred) is recorded on the payment so a person sees it and can confirm or correct it.

New payments are categorised by rule as they are saved (an ``after_flush`` hook on every session), so nothing new
arrives without a category the rules can give; :func:`run_category_model_forever` places the rest.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime, timezone

from sqlalchemy import event, inspect, select, delete, insert
from sqlalchemy.orm import Session

log = logging.getLogger(__name__)

MODEL_THRESHOLD = 0.7
MODEL_RULE = 'category.model'
MODEL_BATCH = 60
SWEEP_SECONDS = 600
ORIGIN_SOURCE = {'person': 'investigator', 'rule': 'description', 'model': 'model', 'learned': 'learned'}


def stem(description):
    """Case-independent key for 'payments like this': the description with numbers and punctuation folded."""
    from services.financial.payment_inference import normalized
    value = normalized(description)
    value = re.sub(r'\d+', '#', value)
    value = re.sub(r'[^A-Z#&@* ]+', ' ', value)
    value = re.sub(r'(?:#\s*)+', '# ', value)
    return ' '.join(value.split())[:200]


def person_label(row):
    """The investigator's saved category ('' when they cleared it), or None when they never chose one."""
    labels = (row.metadata_ or {}).get('investigation_labels', {})
    return labels['category'] if 'category' in labels else None


def rule_category(row, account=None, *, account_type=None, institution=None):
    from services.financial.payment_inference import infer_payment_labels
    if account is not None:
        account_type, institution = account.account_type, account.institution_name
    found = infer_payment_labels(row.description, direction=row.direction, account_type=account_type,
                                 institution=institution).get('category')
    return found if found and found.get('value') else None


def label_source(record):
    """The ``label_sources['category']`` entry for a stored category."""
    if record.origin == 'person':
        return dict(source='investigator', explanation='Saved by an investigator.')
    if record.origin == 'learned':
        return dict(source='learned', explanation='Applied by an investigator from a payment like this one.',
                    learned_from=record.basis)
    if record.origin == 'model':
        return dict(source='model', explanation=record.why or 'Suggested by the model from the description.',
                    confidence=record.confidence, rule=MODEL_RULE, model=record.basis,
                    judgement=record.confidence is not None and record.confidence < MODEL_THRESHOLD)
    return dict(source='description', rule=record.basis,
                explanation=record.why or 'Suggested from the description; review or change it if needed.')


def stored_for(session, ids):
    """{transaction id: stored category row} for these ids, in bounded queries."""
    from postgres.models.financial_payment_category import FinancialPaymentCategory as C
    ids = list(ids)
    found = {}
    if not ids or not table_ready(session):
        return found
    for offset in range(0, len(ids), 1000):
        for record in session.scalars(select(C).where(C.transaction_id.in_(ids[offset:offset + 1000]))):
            found[record.transaction_id] = record
    return found


def attach_stored(session, rows):
    """Load the stored categories of these rows in bounded queries and keep each on its row for the label view."""
    found = stored_for(session, [row.id for row in rows])
    for row in rows:
        row._category_record = found.get(row.id)
    return found


def _upsert(session, row, **values):
    from postgres.models.financial_payment_category import FinancialPaymentCategory as C
    record = session.get(C, row.id)
    if record is None:
        record = C(transaction_id=row.id, case_id=row.case_id, stem=stem(row.description))
        session.add(record)
    for key, value in values.items():
        setattr(record, key, value)
    record.set_at = datetime.now(timezone.utc)
    row._category_record = record
    return record


# ---------------------------------------------------------------------------
# Rules and people
# ---------------------------------------------------------------------------

def categorise(session, rows, *, existing=None):
    """Store the person's or the rules' category for each row; never replaces a person's or a learned choice.

    Returns {origin: count} of the rows written. Rows the rules cannot place are left without a record for
    :func:`classify_with_model`.
    """
    existing = stored_for(session, [row.id for row in rows]) if existing is None else existing
    written = {}
    for row in rows:
        current = existing.get(row.id)
        person = person_label(row)
        if person is not None:
            if current is None or current.origin != 'person' or current.category != person:
                _upsert(session, row, category=person, origin='person', basis='investigation_labels',
                        confidence=None, why=None, set_by=_last_label_actor(row))
                written['person'] = written.get('person', 0) + 1
            continue
        if current is not None and current.origin in ('person', 'learned'):
            continue
        found = rule_category(row, row.account if row.account is not None and row.account.id == row.account_id else None)
        if found is None:
            continue
        if current is not None and current.origin == 'rule' and (current.category, current.basis) == (found['value'], found['rule']):
            continue
        _upsert(session, row, category=found['value'], origin='rule', basis=found['rule'], confidence=None,
                why=found.get('explanation'), set_by=None)
        written['rule'] = written.get('rule', 0) + 1
    session.flush()
    return written


def _last_label_actor(row):
    history = (row.metadata_ or {}).get('investigation_label_history') or []
    for entry in reversed(history):
        if 'category' in (entry.get('after') or {}):
            return entry.get('actor_email') or entry.get('actor_name')
    return None


def record_person_choice(session, row, category, actor):
    """A person chose this row's category. Replaces whatever was stored; a model guess they changed is a correction."""
    from postgres.models.financial_payment_category import FinancialPaymentCategory as C
    if not table_ready(session):
        return
    previous = session.get(C, row.id)
    before = (previous.category, previous.origin) if previous is not None else None
    _upsert(session, row, category=category, origin='person', basis='investigation_labels', confidence=None,
            why=None, set_by=getattr(actor, 'email', None) or getattr(actor, 'name', None))
    if before and before[1] == 'model' and before[0] != category:
        _correct_model_judgement(session, row, before[0], category, actor)


def _correct_model_judgement(session, row, before, after, actor):
    from postgres.models.financial_judgements import FinancialJudgement as J
    try:
        for judgement in session.scalars(select(J).where(J.subject_type == 'transaction', J.subject_id == row.id,
                                                         J.rule_id == MODEL_RULE, J.status == 'open')):
            judgement.status = 'corrected'
            judgement.resolved_by = getattr(actor, 'name', None)
            judgement.resolved_by_email = getattr(actor, 'email', None)
            judgement.resolved_at = datetime.now(timezone.utc)
            judgement.resolution_reason = 'Category changed by an investigator.'
            judgement.evidence = {**(judgement.evidence or {}),
                                  'correction': dict(before=before, after=after or 'Uncategorized')}
            session.flush()
            from services.financial.judgement_inbox import append_correction
            from services.financial.judgements import as_dict
            append_correction(session, as_dict(judgement))
    except Exception:  # noqa: BLE001 - the person's category stands; the inbox script catches up
        log.exception('Recording the category correction on %s as a judgement correction failed', row.id)


def like_payments(session, case_id, transaction_id):
    """Other current payments in this case with the same description stem or the same printed counterparty,
    whose category a person has not chosen. Returns (rows, basis)."""
    from postgres.models.financial import FinancialTransaction as T
    from postgres.models.financial_payment_category import FinancialPaymentCategory as C
    source = session.get(T, transaction_id)
    if source is None or source.case_id != case_id:
        return [], ''
    key = stem(source.description)
    counterparty = ' '.join((source.counterparty_raw or '').split())
    query = select(T).where(T.case_id == case_id, T.ledger_status == 'admitted', T.superseded_by_id.is_(None),
                            T.id != source.id)
    candidates = [row for row in session.scalars(query)
                  if (key and stem(row.description) == key)
                  or (counterparty and ' '.join((row.counterparty_raw or '').split()).casefold() == counterparty.casefold())]
    stored = stored_for(session, [row.id for row in candidates])
    rows = [row for row in candidates if person_label(row) is None
            and getattr(stored.get(row.id), 'origin', None) != 'person']
    return rows, ('same description' if key else 'same counterparty')


def apply_learned(session, case_id, transaction_id, category, actor, *, expected_ids=None):
    """Apply a person's category to the payments like this one ('learned'). Returns how many changed."""
    rows, _ = like_payments(session, case_id, transaction_id)
    if expected_ids is not None:
        wanted = set(expected_ids)
        rows = [row for row in rows if row.id in wanted]
    stored = stored_for(session, [row.id for row in rows])
    changed = 0
    for row in rows:
        record = stored.get(row.id)
        if record is not None and record.origin == 'learned' and record.category == category:
            continue
        if record is not None and record.origin == 'model' and record.category != category:
            _correct_model_judgement(session, row, record.category, category, actor)
        _upsert(session, row, category=category, origin='learned', basis=str(transaction_id), confidence=None,
                why=None, set_by=getattr(actor, 'email', None) or getattr(actor, 'name', None))
        changed += 1
    session.flush()
    return changed


# ---------------------------------------------------------------------------
# The model, for what the rules cannot place
# ---------------------------------------------------------------------------

PROMPT = """You categorise bank and card statement lines for a financial investigation.
Statements are Mexican (Spanish) and US bank and card statements. For each line choose ONE category from this list,
exactly as written:
{categories}

Examples already categorised in this case:
{examples}

Lines to categorise (id, money in or out, description):
{items}

Answer as JSON: {{"items": [{{"id": <id>, "category": "<one of the list>", "confidence": <0 to 1>,
"why": "<one short plain sentence naming the words in the description that decided it>"}}]}}.
Use low confidence when the description is only a reference number or a name with no other clue."""


def model_reader(session):
    """(model id, read(prompt) -> text): the model the page-image reader uses; raises when unavailable."""
    from services.ai_model_policy import get_workload_model
    from services.ai_provider_credentials import get_provider_api_key
    from services.financial.vision_reader import WORKLOAD
    from services.llm_service import LLMExecutionContext
    provider, model_id = get_workload_model(session, WORKLOAD)
    api_key = get_provider_api_key(session, provider)
    if not api_key:
        raise RuntimeError(f'No {provider} key is configured')

    def read(prompt):
        return LLMExecutionContext(provider, model_id, api_key=api_key).call(prompt, temperature=0, json_mode=True,
                                                                             timeout=180)
    return model_id, read


def _choices(session):
    from services.financial.category_library import category_library
    return [item['name'] for item in category_library(session) if item['name'] != 'Uncategorized']


def _examples(session, case_id, limit=16):
    from postgres.models.financial import FinancialTransaction as T
    from postgres.models.financial_payment_category import FinancialPaymentCategory as C
    rows = session.execute(select(T.description, T.direction, C.category).join(C, C.transaction_id == T.id).where(
        C.case_id == case_id, C.origin.in_(('person', 'learned', 'rule')), C.category != '').limit(400)).all()
    seen, picked = set(), []
    for description, direction, category in rows:
        if category not in seen:
            seen.add(category)
            picked.append(f'- {"in" if direction == "credit" else "out"} | {" ".join((description or "").split())[:120]} -> {category}')
        if len(picked) >= limit:
            break
    return '\n'.join(picked) or '- (none yet)'


def classify_with_model(session, case_id, *, reader=None, model_id=None, limit_groups=None):
    """Give every current payment in the case that still has no category one from the model. Returns counts."""
    from postgres.models.financial import FinancialTransaction as T
    from postgres.models.financial_payment_category import (FinancialCategoryModelCache as Cache,
                                                            FinancialPaymentCategory as C)
    rows = list(session.scalars(select(T).outerjoin(C, C.transaction_id == T.id).where(
        T.case_id == case_id, T.ledger_status == 'admitted', T.superseded_by_id.is_(None), C.transaction_id.is_(None))))
    if not rows:
        return dict(placed=0, groups=0, asked=0, judgements=0)
    groups = {}
    for row in rows:
        groups.setdefault((stem(row.description), row.direction), []).append(row)
    cached = {}
    for (key, direction) in groups:
        hit = session.get(Cache, (key, direction))
        if hit is not None:
            cached[(key, direction)] = hit
    choices = _choices(session)
    ask = [group for group in groups if group not in cached]
    if limit_groups is not None:
        ask = ask[:limit_groups]
    if ask:
        if reader is None:
            model_id, reader = model_reader(session)
        examples = _examples(session, case_id)
        for offset in range(0, len(ask), MODEL_BATCH):
            batch = ask[offset:offset + MODEL_BATCH]
            items = '\n'.join(f'{index} | {"in" if direction == "credit" else "out"} | '
                              f'{" ".join((groups[(key, direction)][0].description or "").split())[:200]}'
                              for index, (key, direction) in enumerate(batch))
            try:
                answer = json.loads(reader(PROMPT.format(categories='\n'.join(f'- {name}' for name in choices),
                                                         examples=examples, items=items)))
            except Exception:  # noqa: BLE001 - a failed batch is retried by the next sweep
                log.exception('Category model batch failed for case %s', case_id)
                continue
            for item in answer.get('items') or []:
                try:
                    key, direction = batch[int(item['id'])]
                except (KeyError, ValueError, TypeError, IndexError):
                    continue
                category = str(item.get('category') or '').strip()
                try:
                    confidence = max(0.0, min(1.0, float(item.get('confidence'))))
                except (TypeError, ValueError):
                    confidence = 0.0
                if category not in choices:
                    category, confidence = ('Incoming payments' if direction == 'credit' else 'Payments'), min(confidence, 0.3)
                why = ' '.join(str(item.get('why') or '').split())[:400]
                hit = Cache(stem=key, direction=direction, category=category, confidence=confidence, why=why,
                            model=model_id or '')
                session.merge(hit)
                cached[(key, direction)] = hit
            session.commit()
    placed = judged = 0
    for group, members in groups.items():
        hit = cached.get(group)
        if hit is None:
            continue
        for row in members:
            _upsert(session, row, category=hit.category, origin='model', basis=hit.model, confidence=hit.confidence,
                    why=hit.why, set_by=None)
            placed += 1
            if hit.confidence < MODEL_THRESHOLD:
                judged += _record_model_judgement(session, row, hit) is not None
    session.commit()
    return dict(placed=placed, groups=len(groups), asked=len(ask), judgements=judged)


def _record_model_judgement(session, row, hit):
    from services.financial.judgements import record_judgement
    return record_judgement(
        session, case_id=row.case_id, subject_type='transaction', subject_id=row.id, rule_id=MODEL_RULE,
        target_key='category', reading=f'{hit.category}:{hit.stem}'[:80], strength='inferred',
        source_document_id=row.source_document_id, statement_period_id=row.statement_period_id,
        summary=f'The category "{hit.category}" is the model\'s best guess from the description'
                f' ({round(hit.confidence * 100)}% sure): {hit.why or "no clear wording"}',
        evidence=dict(chosen=hit.category, confidence=hit.confidence, why=hit.why, model=hit.model))


def coverage(session, case_id):
    """{origin or 'none': count} over the case's current payments."""
    from sqlalchemy import func
    from postgres.models.financial import FinancialTransaction as T
    from postgres.models.financial_payment_category import FinancialPaymentCategory as C
    result = {}
    for origin, blank, count in session.execute(
            select(C.origin, C.category == '', func.count()).select_from(T).outerjoin(C, C.transaction_id == T.id)
            .where(T.case_id == case_id, T.ledger_status == 'admitted', T.superseded_by_id.is_(None))
            .group_by(C.origin, C.category == '')):
        key = origin or 'none'
        if blank and origin:
            key = f'{origin}:uncategorized'
        result[key] = result.get(key, 0) + count
    return result


def backfill(session, case_id):
    """Store the person's or the rules' category for every current payment in the case. Returns counts."""
    from sqlalchemy.orm import joinedload
    from postgres.models.financial import FinancialTransaction as T
    rows = list(session.scalars(select(T).options(joinedload(T.account)).where(
        T.case_id == case_id, T.ledger_status == 'admitted', T.superseded_by_id.is_(None))))
    written = {}
    for offset in range(0, len(rows), 2000):
        for key, value in categorise(session, rows[offset:offset + 2000]).items():
            written[key] = written.get(key, 0) + value
        session.commit()
    return written


# ---------------------------------------------------------------------------
# Saving: categorise new payments as they are written
# ---------------------------------------------------------------------------

_HAS_TABLE = {}


def _table_ready(connection):
    key = (id(connection.engine), str(connection.engine.url))
    if key not in _HAS_TABLE:
        _HAS_TABLE[key] = inspect(connection).has_table('financial_payment_categories')
    return _HAS_TABLE[key]


def table_ready(session):
    """False on a database not yet migrated (and in tests that build only some tables)."""
    return _table_ready(session.connection())


@event.listens_for(Session, 'after_flush')
def _categorise_new_payments(session, flush_context):
    """Rule categories for payments inserted in this flush, and carry a person's, learned or model category to a
    payment's replacement. Never raises: saving the payment matters more than its category."""
    from postgres.models.financial import FinancialAccount, FinancialTransaction as T
    from postgres.models.financial_payment_category import FinancialPaymentCategory as C
    new = [obj for obj in session.new if isinstance(obj, T)]
    replaced = [obj for obj in session.dirty if isinstance(obj, T) and obj.superseded_by_id is not None
                and inspect(obj).attrs.superseded_by_id.history.added]
    if not new and not replaced:
        return
    try:
        connection = session.connection()
        if not _table_ready(connection):
            return
        with connection.begin_nested():
            accounts = {}
            account_ids = {row.account_id for row in new}
            if account_ids:
                for account_id, account_type, institution in connection.execute(
                        select(FinancialAccount.id, FinancialAccount.account_type, FinancialAccount.institution_name)
                        .where(FinancialAccount.id.in_(account_ids))):
                    accounts[account_id] = (account_type, institution)
            values = []
            for row in new:
                person = person_label(row)
                if person is not None:
                    values.append(dict(transaction_id=row.id, case_id=row.case_id, category=person, origin='person',
                                       basis='investigation_labels', stem=stem(row.description)))
                    continue
                account_type, institution = accounts.get(row.account_id, (None, None))
                found = rule_category(row, account_type=account_type, institution=institution)
                if found:
                    values.append(dict(transaction_id=row.id, case_id=row.case_id, category=found['value'],
                                       origin='rule', basis=found['rule'], why=found.get('explanation'),
                                       stem=stem(row.description)))
            if values:
                connection.execute(insert(C.__table__), values)
            for old in replaced:
                carried = connection.execute(select(C.__table__).where(C.transaction_id == old.id)).mappings().first()
                if carried is None or carried['origin'] == 'rule':
                    continue
                current = connection.execute(select(C.origin).where(C.transaction_id == old.superseded_by_id)).scalar()
                if current == 'person':
                    continue
                connection.execute(delete(C.__table__).where(C.transaction_id == old.superseded_by_id))
                connection.execute(insert(C.__table__), [dict(
                    {k: v for k, v in carried.items() if k not in ('transaction_id', 'set_at')},
                    transaction_id=old.superseded_by_id)])
    except Exception:  # noqa: BLE001
        log.exception('Categorising newly saved payments failed; the payments are saved and the sweep will retry')


# ---------------------------------------------------------------------------
# The sweep
# ---------------------------------------------------------------------------

def sweep_once():
    """For every case with current payments lacking a category: rules first, then the model."""
    from sqlalchemy import func
    from postgres.models.financial import FinancialTransaction as T
    from postgres.models.financial_payment_category import FinancialPaymentCategory as C
    from postgres.session import _get_session_local
    results = {}
    with _get_session_local()() as session:
        cases = [case_id for case_id, in session.execute(
            select(T.case_id).outerjoin(C, C.transaction_id == T.id).where(
                T.ledger_status == 'admitted', T.superseded_by_id.is_(None), C.transaction_id.is_(None))
            .group_by(T.case_id).having(func.count() > 0))]
    for case_id in cases:
        with _get_session_local()() as session:
            try:
                backfill(session, case_id)
                results[str(case_id)] = classify_with_model(session, case_id)
            except Exception:  # noqa: BLE001
                session.rollback()
                log.exception('Category sweep failed for case %s', case_id)
    return results


async def run_category_model_forever():
    await asyncio.sleep(60)
    while True:
        try:
            await asyncio.to_thread(sweep_once)
        except Exception:  # noqa: BLE001
            log.exception('Category sweep failed')
        await asyncio.sleep(SWEEP_SECONDS)
