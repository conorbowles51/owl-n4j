"""Move work a model saved before the origin field existed onto the model origin (services.financial.model_work).

Before the origin field, a headless job working for a person saved its work under a name such as
"Neil Byrne (via Claude)": the person's name with the model in brackets. This module finds those records by that
legacy name (the only place a name is read; services.financial.model_work.LEGACY_NAME_MARK), and for each:

- replaces the name with the model's ("Claude (for Neil Byrne)") and stores the origin beside it, with the legacy
  name kept as ``origin.recorded_as`` and ``origin.migrated`` saying who moved it, when and why;
- changes nothing else: no value, amount, label, date, status, proof class or key;
- records the statement-level call (judgements, rule ``model.statement_save``) for every saved statement a model
  saved, so a person can confirm the statement in one action. A statement whose hand entry a person already
  confirmed ("Looks right") carries that confirmation, with its person and time.

Every record goes through the ORM, so the transaction audit trigger records each changed payment. The financial
audit log itself is hash-chained and immutable: its events keep the legacy name as the original record.
Running it again changes nothing (idempotent): a migrated record no longer carries the legacy name.

    python -m services.financial.model_work_migration [--case <uuid>]... [--apply]
"""
from __future__ import annotations

import argparse
import copy
import json
import re
import sys
import uuid
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import String, cast, or_, select

from services.financial.model_work import DEFAULT_MODEL, LEGACY_NAME_MARK, model_name

MIGRATION_ACTOR = 'Loupe model-work origin migration'
WHY = ('Saved before model work had its own origin, under the legacy name "{name}". The work was the model\'s, '
       'done for {person}; it is shown as the model\'s until a person confirms it. No value changed.')

# "<person> (via Claude)" and "claude (for <person>)": the two legacy forms found on live data (2026-10-29).
_VIA = re.compile(r'^\s*(?P<person>.+?)\s*\(via (?P<model>claude)\)\s*$', re.I)
_FOR = re.compile(r'^\s*(?P<model>claude)\s*\(for (?P<person>.+?)\)\s*$', re.I)
# Keys that hold a stored actor's name, beside the dict they describe.
NAME_KEYS = ('name', 'actor_name')
# Keys whose value is the actor's name as a bare string (judgement evidence, account refiles).
STRING_ACTOR_KEYS = ('saved_by', 'by')
TIME_KEYS = ('at', 'saved_at', 'created_at', 'decided_at', 'withdrawn_at')


def legacy_person(name: Any) -> Optional[str]:
    """The person a legacy model name was saved for, or None when the name is not a legacy model name."""
    if not isinstance(name, str):
        return None
    if LEGACY_NAME_MARK.lower() not in name.lower() and not _FOR.match(name):
        return None
    match = _VIA.match(name) or _FOR.match(name)
    return match.group('person').strip() if match else None


class _Run:
    def __init__(self, *, now: str, users: dict, people: dict):
        self.now, self.users, self.people = now, users, people
        self.changed = Counter()

    def person(self, legacy: str, user_id: Any) -> tuple[str, Optional[str]]:
        """The full name of the person the work was for: the account's name when the record names the account."""
        short = legacy_person(legacy) or legacy
        uid = str(user_id) if user_id not in (None, '', 'None') else None
        if uid and uid in self.users:
            return self.users[uid], uid
        if short in self.people:
            return short, self.people[short]
        full = next((name for name in self.people if name.split()[0].lower() == short.lower()), None)
        return (full, self.people[full]) if full else (short, None)

    def origin(self, legacy: str, *, user_id: Any = None, at: Any = None, citation: Optional[dict] = None) -> dict:
        person, uid = self.person(legacy, user_id)
        origin = {'kind': 'model', 'model': DEFAULT_MODEL, 'for': {'name': person, 'user_id': uid}}
        if isinstance(at, str) and at:
            origin['at'] = at
        if citation:
            origin['citation'] = {k: v for k, v in citation.items() if v not in (None, '')}
        origin['recorded_as'] = legacy
        origin['migrated'] = {'at': self.now, 'by': MIGRATION_ACTOR, 'why': WHY.format(name=legacy, person=person)}
        return origin

    def walk(self, value: Any, kind: str, *, citation: Optional[dict] = None, at: Any = None) -> Any:
        """A copy of ``value`` with every legacy model actor moved to the origin; counts what changed by kind."""
        if isinstance(value, list):
            return [self.walk(item, kind, citation=citation, at=at) for item in value]
        if not isinstance(value, dict):
            return value
        when = next((value[k] for k in TIME_KEYS if isinstance(value.get(k), str) and value.get(k)), at)
        out = {key: self.walk(item, kind, citation=citation, at=when) for key, item in value.items()}
        for key in NAME_KEYS:
            if legacy_person(out.get(key)) and not isinstance(out.get('origin'), dict):
                legacy = out[key]
                user_id = out.get('user_id') or out.get('actor_id') or (out.get('by') if key == 'name' else None)
                origin = self.origin(legacy, user_id=user_id, at=when, citation=citation)
                out[key], out['origin'] = model_name(origin), origin
                self.changed[kind] += 1
                return out
        for key in STRING_ACTOR_KEYS:
            if legacy_person(out.get(key)) and not isinstance(out.get('origin'), dict):
                legacy = out[key]
                origin = self.origin(legacy, at=when, citation=citation)
                out[key], out['origin'] = model_name(origin), origin
                self.changed[kind] += 1
                return out
        return out


def _legacy_filter(column):
    return or_(cast(column, String).ilike(f'%{LEGACY_NAME_MARK}%'), cast(column, String).ilike('%claude (for %'))


def _page(provenance: dict) -> Optional[int]:
    locator = (provenance or {}).get('locator') or {}
    return locator.get('page') or locator.get('page_number')


def migrate(session, *, case_ids=None, apply=False, now=None) -> dict:
    """Move every legacy model record (in ``case_ids``, or every case) onto the origin. Returns counts per kind of
    record changed, and the statements whose statement-level call was recorded. Without ``apply`` nothing is
    written and the session is rolled back."""
    from postgres.models.evidence import EvidenceFile
    from postgres.models.financial import (AdjudicationEvent, FinancialAccount, FinancialSourceDocument,
                                           FinancialTransaction)
    from postgres.models.financial_import_batches import (FinancialImportBatch, FinancialImportBatchItem,
                                                          FinancialImportOperation)
    from postgres.models.financial_judgements import FinancialJudgement
    from postgres.models.user import User

    now = now or datetime.now(timezone.utc).isoformat()
    users = {str(u.id): u.name for u in session.scalars(select(User)) if getattr(u, 'name', None)}
    people = {name: uid for uid, name in users.items()}
    run = _Run(now=now, users=users, people=people)
    scoped = (lambda model: model.case_id.in_(list(case_ids))) if case_ids else (lambda model: True)
    found = Counter()

    # Payments: the save (provenance.confirmed_by) and the names read (label history).
    statements = set()
    for row in session.scalars(select(FinancialTransaction).where(
            scoped(FinancialTransaction), or_(_legacy_filter(FinancialTransaction.provenance),
                                              _legacy_filter(FinancialTransaction.metadata_)))
            .order_by(FinancialTransaction.id).with_for_update()):
        citation = dict(source_document_id=str(row.source_document_id) if row.source_document_id else None,
                        page=_page(row.provenance))
        provenance = run.walk(row.provenance or {}, 'transaction.saved_by', citation=citation)
        if provenance != row.provenance:
            found['transaction.saved_by'] += 1
            row.provenance = provenance
            if row.source_document_id:
                statements.add(row.source_document_id)
        metadata = dict(row.metadata_ or {})
        history = metadata.get('investigation_label_history')
        if history:
            new = []
            for entry in history:
                reason = entry.get('reason') if isinstance(entry, dict) else None
                new.append(run.walk(entry, 'transaction.label', citation=dict(citation, reason=reason)))
            if new != history:
                found['transaction.label'] += 1
                metadata['investigation_label_history'] = new
                row.metadata_ = metadata
        rest = {k: v for k, v in metadata.items() if k != 'investigation_label_history'}
        walked = run.walk(rest, 'transaction.other', citation=citation)
        if walked != rest:
            found['transaction.other'] += 1
            row.metadata_ = {**walked, **({'investigation_label_history': metadata['investigation_label_history']}
                                          if 'investigation_label_history' in metadata else {})}

    # Decisions: the actor columns, the origin column; before/after snapshots keep what they recorded.
    for row in session.scalars(select(AdjudicationEvent).where(
            scoped(AdjudicationEvent), AdjudicationEvent.actor_origin.is_(None))
            .order_by(AdjudicationEvent.id).with_for_update()):
        if not legacy_person(row.actor_name):
            continue
        origin = run.origin(row.actor_name, user_id=row.actor_user_id,
                            at=row.created_at.isoformat() if row.created_at else None)
        row.actor_name, row.actor_origin = model_name(origin), origin
        found['adjudication'] += 1
        run.changed['adjudication'] += 1

    def json_rows(model, attribute, kind, citation=None):
        column = getattr(model, attribute)
        for row in session.scalars(select(model).where(scoped(model) if hasattr(model, 'case_id') else True,
                                                       _legacy_filter(column)).order_by(model.id).with_for_update()):
            value = getattr(row, attribute)
            walked = run.walk(copy.deepcopy(value), kind, citation=citation(row) if citation else None)
            if walked != value:
                setattr(row, attribute, walked)
                found[kind] += 1

    json_rows(FinancialSourceDocument, 'metadata_', 'source_document',
              lambda r: dict(source_document_id=str(r.id)))
    json_rows(EvidenceFile, 'metadata_', 'evidence_file', lambda r: dict(evidence_file_id=str(r.id)))
    json_rows(FinancialAccount, 'metadata_', 'account')
    json_rows(FinancialImportBatch, 'actor', 'import_batch')
    json_rows(FinancialImportOperation, 'actor', 'import_operation')
    json_rows(FinancialImportOperation, 'outcomes', 'import_operation.outcome')
    json_rows(FinancialJudgement, 'evidence', 'judgement',
              lambda r: dict(source_document_id=str(r.source_document_id) if r.source_document_id else None,
                             page=(r.evidence or {}).get('first_page')))
    # Batch items have no case column: scope through their batch.
    item_query = select(FinancialImportBatchItem).where(_legacy_filter(FinancialImportBatchItem.summary))
    if case_ids:
        item_query = item_query.join(FinancialImportBatch, FinancialImportBatch.id == FinancialImportBatchItem.batch_id) \
            .where(FinancialImportBatch.case_id.in_(list(case_ids)))
    for row in session.scalars(item_query.order_by(FinancialImportBatchItem.id).with_for_update()):
        walked = run.walk(copy.deepcopy(row.summary), 'import_batch_item',
                          citation=dict(evidence_file_id=str(row.file_id)))
        if walked != row.summary:
            row.summary = walked
            found['import_batch_item'] += 1
    session.flush()

    # Statement-level calls for every saved statement a model saved (one action confirms the statement).
    recorded = record_statement_calls(session, statements)
    result = dict(records=dict(found), actors=dict(run.changed), statements=len(statements),
                  statement_calls=recorded, applied=bool(apply), at=now)
    if apply:
        session.commit()
    else:
        session.rollback()
    return result


def record_statement_calls(session, document_ids) -> dict:
    """Record the statement-level model call on each saved statement whose payments a model saved; carry a
    person's earlier 'Looks right' on the statement's hand entry. Returns counts: recorded, carried, existing."""
    from postgres.models.financial import FinancialSourceDocument, FinancialStatementPeriod, FinancialTransaction
    from postgres.models.financial_judgements import FinancialJudgement as J
    from services.financial import judgements
    counts = Counter()
    for document_id in sorted(document_ids, key=str):
        document = session.get(FinancialSourceDocument, document_id)
        if document is None or document.status != 'admitted':
            counts['not_admitted'] += 1
            continue
        period = session.scalar(select(FinancialStatementPeriod).where(
            FinancialStatementPeriod.source_document_id == document.id).limit(1))
        transactions = list(session.scalars(select(FinancialTransaction).where(
            FinancialTransaction.source_document_id == document.id,
            FinancialTransaction.ledger_status == 'admitted').order_by(FinancialTransaction.id)))
        calls = [c for c in judgements.detect(document, period, transactions) if c['rule_id'] == 'model.statement_save']
        if not calls:
            counts['first_payment_not_model'] += 1
            continue
        call = calls[0]
        existing = session.scalar(select(J).where(J.subject_type == call['subject_type'], J.subject_id == call['subject_id'],
                                                  J.rule_id == 'model.statement_save'))
        if existing is not None:
            counts['existing'] += 1
            continue
        row = judgements.record_judgement(session, case_id=document.case_id, reading=str(document.id),
                                          source_document_id=document.id,
                                          statement_period_id=getattr(period, 'id', None), **call)
        if row is None:
            counts['failed'] += 1
            continue
        counts['recorded'] += 1
        confirmed = session.scalar(select(J).where(J.source_document_id == document.id, J.rule_id == 'agent.page_entry',
                                                   J.status == 'confirmed').order_by(J.resolved_at).limit(1))
        if confirmed is not None:
            row.status, row.resolved_by, row.resolved_by_email = 'confirmed', confirmed.resolved_by, confirmed.resolved_by_email
            row.resolved_at = confirmed.resolved_at
            row.resolution_reason = (f'Carried from the hand entry {confirmed.resolved_by} confirmed on '
                                     f'{confirmed.resolved_at.date().isoformat() if confirmed.resolved_at else ""}.')
            counts['carried_confirmation'] += 1
    session.flush()
    return dict(counts)


def remaining(session) -> dict:
    """How many stored records still carry a legacy model name, per table and column (the migration gate)."""
    from sqlalchemy import text
    out = {}
    for table, column in (('financial_transactions', 'provenance'), ('financial_transactions', 'metadata'),
                          ('adjudications', 'actor_name'), ('financial_import_batch_items', 'summary'),
                          ('financial_source_documents', 'metadata'), ('financial_import_operations', 'actor'),
                          ('financial_import_operations', 'outcomes'), ('financial_judgements', 'evidence'),
                          ('evidence_files', 'metadata'), ('financial_accounts', 'metadata'),
                          ('financial_import_batches', 'actor')):
        # Names only: origin.recorded_as keeps the legacy name on purpose and is not counted.
        # A decision's name sits in its own column, beside actor_origin.
        unmigrated = 'actor_origin IS NULL AND ' if table == 'adjudications' else ''
        rows = session.execute(text(f'SELECT {column}::text FROM {table} WHERE {unmigrated}({column}::text ILIKE :mark '
                                    f'OR {column}::text ILIKE :other)'),
                               dict(mark=f'%{LEGACY_NAME_MARK}%', other='%claude (for %')).scalars()
        count = 0
        for value in rows:
            try:
                parsed = json.loads(value)
            except (TypeError, ValueError):
                parsed = value
            if _has_legacy_name(parsed):
                count += 1
        out[f'{table}.{column}'] = count
    return out


def _has_legacy_name(value) -> bool:
    """A legacy model name on a record with no origin. A migrated or new record names the model and carries its
    origin beside the name, so its name is not legacy."""
    if isinstance(value, str):
        return bool(legacy_person(value))
    if isinstance(value, list):
        return any(_has_legacy_name(v) for v in value)
    if isinstance(value, dict):
        has_origin = isinstance(value.get('origin'), dict)
        return any(_has_legacy_name(v) for k, v in value.items()
                   if k != 'origin' and not (has_origin and k in NAME_KEYS + STRING_ACTOR_KEYS))
    return False


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--case', action='append', type=uuid.UUID, default=None)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args(argv)
    from postgres.session import _get_session_local
    with _get_session_local()() as session:
        result = migrate(session, case_ids=args.case, apply=args.apply)
    with _get_session_local()() as session:
        result['remaining'] = remaining(session)
    json.dump(result, sys.stdout, indent=2, sort_keys=True, default=str)
    print()


if __name__ == '__main__':
    main()
