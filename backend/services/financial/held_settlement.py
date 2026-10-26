"""Settle held statements that need no person: copies of saved statements, and fund statements.

Run with the engine-release snapshot of a case (recovery_readers.snapshot), under its case lock, before the
held statements are selected for a new reading:

* a held copy of an account and period the case already saved is set aside as a linked duplicate when its
  reading agrees with the saved ledger, or keeps a record of what differs (saved_copies);
* a held fund statement (holdings, no movement ledger) is set aside as not a payment statement
  (not_payment_statements);
* a held item whose statement key its file's current reading no longer lists, while that reading's one
  statement is saved, is retired to history (VANISHED_KEY, below).

New preparations reach the same outcomes through their own reading (the fund rule is part of the reading)
and duplicate check; this pass brings statements prepared before the rules existed in line. ``apply=False``
is the read-only estimate (counts and outcomes, nothing written).
"""
import os
from collections import Counter

from sqlalchemy import select

from postgres.models.evidence import EvidenceDocumentText
from postgres.models.financial import FinancialAccount, FinancialSourceDocument, FinancialStatementPeriod
from postgres.models.financial_import_batches import FinancialImportBatch as Batch, FinancialImportBatchItem as Item


def _saved_keys(session, case_id):
    """{(start, end): {last-six account digits}} of the case's admitted periods."""
    from services.financial.saved_copies import _digits
    keys = {}
    for start, end, normalised, printed in session.execute(select(FinancialStatementPeriod.period_start,
            FinancialStatementPeriod.period_end, FinancialAccount.identifier_normalised,
            FinancialAccount.identifier_as_printed).join(FinancialSourceDocument,
            FinancialSourceDocument.id == FinancialStatementPeriod.source_document_id).join(
            FinancialAccount, FinancialAccount.id == FinancialStatementPeriod.account_id).where(
            FinancialStatementPeriod.case_id == case_id, FinancialSourceDocument.status == 'admitted')):
        if start and end:
            keys.setdefault((start.isoformat(), end.isoformat()), set()).update(
                digits for digits in (_digits(normalised), _digits(printed)) if digits)
    return keys


def _copy_candidate(item, saved):
    from services.financial.saved_copies import _digits, _same_account
    summary = item.summary or {}
    account = _digits(summary.get('account'))
    accounts = saved.get((summary.get('period_start') or '', summary.get('period_end') or ''))
    return bool(account and accounts and any(_same_account(value, account) for value in accounts))


# Neil's decision (2026-10-26, fin-queue3 L22; fin-queue2 A13): a held item whose statement key the current
# reading of its file no longer lists, while that reading has one statement and it is saved (from this file or a
# file with identical bytes), is retired to history like a vanished period of the same batch
# (import_batches.RETIRE_VANISHED_PERIODS): status superseded_reading, linked to the saved statement. Only an
# item nobody worked on. Off: it waits with "This statement period is no longer available", as before.
VANISHED_KEY = os.environ.get('LOUPE_FINANCIAL_SETTLE_VANISHED_KEY', '1').strip().lower() not in (
    '0', 'false', 'no', 'off')
VANISHED_MARK = 'This statement period is no longer available'
VANISHED_KEY_MESSAGE = ('This file was read again and lists this statement differently. The statement it now lists '
                        'is already saved, so this earlier preparation is retained in history.')


def _vanished(item):
    return bool(item.statement_key) and any(VANISHED_MARK in str(problem.get('message') or '')
                                            for problem in (item.summary or {}).get('problems') or [])


def _saved_statement_of_bytes(session, case_id, file, key):
    """The admitted source document saving statement ``key`` of these bytes (this file or an identical one)."""
    from postgres.models.evidence import EvidenceFile
    for document, other in session.execute(select(FinancialSourceDocument, EvidenceFile)
            .join(EvidenceFile, EvidenceFile.id == FinancialSourceDocument.evidence_file_id)
            .where(FinancialSourceDocument.case_id == case_id, FinancialSourceDocument.status == 'admitted',
                   EvidenceFile.case_id == case_id, EvidenceFile.sha256 == file.sha256)
            .order_by(FinancialSourceDocument.id)):
        metadata = document.metadata_ or {}
        if not metadata.get('financial_import_removal') and (metadata.get('statement_import_statement_id') or '') == key:
            return document
    return None


def settle_vanished_key(session, case_id, item, *, cache=None, apply=True):
    """Retire one held item whose key vanished when its file's only current statement is saved. Returns the outcome."""
    from postgres.models.evidence import EvidenceFile
    from services.financial.pdf_candidates import PdfMappingError
    from services.financial.saved_copies import _person_work
    from services.financial.statement_import import read_statement_import
    if not VANISHED_KEY or item.status not in ('ready', 'attention') or not _vanished(item):
        return dict(outcome='skipped', why='switch_status_or_not_vanished')
    file = session.get(EvidenceFile, item.file_id)
    if file is None or file.case_id != case_id or not file.sha256:
        return dict(outcome='skipped', why='unavailable')
    if _person_work(file, item, item.statement_key):
        return dict(outcome='skipped', why='person_work')
    try:
        current = read_statement_import(session, case_id=case_id, evidence_file_id=file.id, _cache=cache,
                                        _include_period_checks=False, _include_duplicate_disposition=False)
    except PdfMappingError:
        return dict(outcome='skipped', why='unreadable')
    choices = [choice for choice in current.get('statement_choices') or [] if not choice.get('document_kind')]
    # One statement read without a period list has no key of its own ('').
    keys = ([choice['id'] for choice in choices] if choices else
            [current.get('statement_id') or ''] if not (current.get('document_review') or current.get('reading_failure')) else [])
    if item.statement_key in keys:
        return dict(outcome='skipped', why='key_present')
    if len(keys) != 1:
        return dict(outcome='kept', why='several_statements' if keys else 'no_statement')
    document = _saved_statement_of_bytes(session, case_id, file, keys[0])
    if document is None:
        return dict(outcome='kept', why='not_saved')
    if apply:
        item.status = 'superseded_reading'
        item.summary = {**(item.summary or {}), 'can_import': False, 'superseded_by_reading': str(file.id),
                        'superseded_by_statement': keys[0], 'saved_source_document_id': str(document.id),
                        'recovery_message': VANISHED_KEY_MESSAGE}
        session.flush()
    return dict(outcome='superseded', saved_source_document_id=str(document.id))


def settle_held_statements(session, case_id, *, apply=True):
    """Returns Counter of outcomes: 'saved_copy:<outcome>' and 'not_payment:<outcome>'."""
    from services.financial import not_payment_statements, saved_copies
    outcomes = Counter()
    if not (saved_copies.ENABLED or not_payment_statements.ENABLED or VANISHED_KEY):
        return outcomes
    items = list(session.scalars(select(Item).join(Batch, Batch.id == Item.batch_id).where(
        Batch.case_id == case_id, Batch.status.notin_(('removed', 'preparing', 'pausing')),
        Item.status == 'attention').order_by(Item.file_id, Item.statement_key, Item.id)))
    saved = _saved_keys(session, case_id) if saved_copies.ENABLED else {}
    titled = {}
    cache = {}
    for item in items:
        summary = item.summary or {}
        if VANISHED_KEY and _vanished(item):
            result = settle_vanished_key(session, case_id, item, cache=cache, apply=apply)
            outcomes['vanished_key:' + result['outcome'] + (':' + result['why'] if result.get('why') else '')] += 1
            if result['outcome'] == 'superseded':
                continue
        if saved_copies.ENABLED and _copy_candidate(item, saved):
            result = saved_copies.settle_item(session, case_id, item, cache=cache, apply=apply)
            outcomes['saved_copy:' + result['outcome'] + (':' + result['why'] if result.get('why') else '')] += 1
            if result['outcome'] == 'set_aside':
                continue
        if (not not_payment_statements.ENABLED or item.review_request or summary.get('not_payment_statement')
                or summary.get('transaction_count')):
            continue
        if item.file_id not in titled:
            text = session.get(EvidenceDocumentText, item.file_id)
            titled[item.file_id] = bool(text and not_payment_statements.titled(text.content or ''))
        if not titled[item.file_id]:
            continue
        from services.financial.pdf_candidates import PdfMappingError
        from services.financial.statement_import import read_statement_import
        try:
            proposal = read_statement_import(session, case_id=case_id, evidence_file_id=item.file_id,
                currency=summary.get('currency') or None, statement_id=item.statement_key or None, _cache=cache)
        except PdfMappingError:
            outcomes['not_payment:unreadable'] += 1
            continue
        if not proposal.get('not_payment_statement'):
            outcomes['not_payment:kept_in_review'] += 1
            continue
        if apply:
            not_payment_statements.reassess_items(session, case_id, item.file_id, item.statement_key or '', proposal)
        outcomes['not_payment:set_aside'] += 1
    if apply:
        session.flush()
    return outcomes
