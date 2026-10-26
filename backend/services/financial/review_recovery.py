"""Find saved decisions across explicitly linked readings of the same case file.

Period names are navigation aids, not permission to attach old rows to new
locations. Different readings are shown for comparison and never remapped.
"""
import os
from copy import deepcopy
from datetime import date, datetime, timezone
from uuid import UUID
from sqlalchemy import select
from postgres.models.evidence import EvidenceFile
from postgres.models.financial import FinancialSourceDocument
from postgres.models.financial_import_batches import FinancialImportBatch, FinancialImportBatchItem
from services.financial.pdf_candidates import PdfMappingError, _digest


def _ancestors(session, file):
    seen = {str(file.id)} if getattr(file, 'id', None) else set()
    parent = (file.metadata_ or {}).get('statement_parent_evidence_id')
    while parent and parent not in seen:
        seen.add(parent)
        try:
            identifier = UUID(parent)
        except (ValueError, TypeError):
            break
        previous = session.scalar(select(EvidenceFile).where(
            EvidenceFile.id == identifier, EvidenceFile.case_id == file.case_id))
        if previous is None:
            break
        if (previous.metadata_ or {}).get('financial_import_removal'):
            break  # A deliberate fresh start must not recover withdrawn drafts.
        yield previous
        parent = (previous.metadata_ or {}).get('statement_parent_evidence_id')


def saved_ancestor_reviews(session, file):
    records = []
    seen = set()

    def add(previous, saved, origin, statement_id=None):
        request = saved.get('request') or {}
        if not request.get('rows') and not request.get('_saved_balance_corrections'):
            return
        key = request.get('statement_id') or statement_id or ''
        # The same request may have been copied into multiple batches or saved
        # unchanged in later versions. Show it once, keeping the nearest source.
        fingerprint = _digest(dict(statement_id=key, request=request))
        if fingerprint in seen:
            return
        seen.add(fingerprint)
        records.append(dict(id=_digest([str(previous.id), fingerprint]),
            statement_id=key or None, evidence_file_id=str(previous.id),
            filename=previous.original_filename, origin=origin,
            saved_at=saved.get('saved_at'), saved_by=saved.get('saved_by'),
            request=request, review_revision=saved.get('review_revision') or _digest(request)))

    for previous in _ancestors(session, file):
        metadata = previous.metadata_ or {}
        for key, saved in metadata.get('financial_review_progress', {}).items():
            add(previous, saved, 'Statement review', key)
        for saved in reversed(metadata.get('financial_review_history', [])):
            add(previous, saved, 'Earlier statement review')
        # Late corrections are separate from the immutable import request.
        # Keep them available for explicit comparison with a fresh extraction.
        sources = session.scalars(select(FinancialSourceDocument).where(
            FinancialSourceDocument.case_id == file.case_id,
            FinancialSourceDocument.evidence_file_id == previous.id)
            .order_by(FinancialSourceDocument.id))
        for source in sources:
            imported = source.metadata_ or {}
            details = imported.get('statement_details_review')
            if details and imported.get('statement_import_request') and _digest(details) == imported.get('statement_details_review_sha256'):
                request = deepcopy(imported['statement_import_request'])
                request.update(details['details'])
                if details.get('currency'):
                    request['currency'] = details['currency']
                # Later balances have their own page citations. Never pretend
                # they came from one of the old extraction's transaction rows.
                request['_saved_balance_corrections'] = details['balances']
                latest = imported['statement_details_history'][-1]
                add(previous, dict(request=request, saved_at=latest['at'],
                    saved_by=dict(user_id=latest['actor_id'], name=latest['actor_name'])),
                    'Account and balances corrected after import')
            corrected = [r for r in imported.get('statement_incomplete_records', [])
                         if r.get('correction')]
            if not corrected or not imported.get('statement_import_request'):
                continue
            request = deepcopy(imported['statement_import_request'])
            corrections = {r['id']: r['correction'] for r in corrected}
            request['rows'] = [corrections.get(r['id'], r) for r in request['rows']]
            latest = max(corrected, key=lambda r: r.get('corrected_at', ''))
            currencies = sorted({r['correction_currency'] for r in corrected})
            add(previous, dict(request=request, saved_at=latest.get('corrected_at'),
                saved_by=dict(user_id=latest.get('corrected_by'))),
                f"Corrected imported records ({', '.join(currencies)})")
        items = session.execute(select(FinancialImportBatchItem, FinancialImportBatch)
            .join(FinancialImportBatch, FinancialImportBatch.id == FinancialImportBatchItem.batch_id)
            .where(FinancialImportBatchItem.file_id == previous.id,
                   FinancialImportBatch.case_id == file.case_id,
                   FinancialImportBatchItem.review_request.is_not(None))
            .order_by(FinancialImportBatchItem.updated_at.desc(), FinancialImportBatchItem.id))
        for item, batch in items:
            add(previous, dict(request=item.review_request,
                saved_at=item.updated_at.isoformat(),
                saved_by=(item.summary or {}).get('review_saved_by')),
                'Bulk review', item.statement_key)
    return records


# Neil's decision (2026-10-24): when uncarried file-level work sits on an earlier reading and the new reading
# names the file's periods, a period her work does not touch proceeds normally; touched periods stay held.
# Off: any such work holds every period of the file, as before.
SPLIT_RELEASE = os.environ.get('LOUPE_FINANCIAL_RECOVERY_SPLIT_RELEASE', '1').strip().lower() not in (
    '0', 'false', 'no', 'off')
_NESTED = '_held_work_nested'


def _iso(value):
    try:
        return date.fromisoformat(str(value or '')[:10]) if len(str(value or '')) >= 10 else None
    except ValueError:
        return None


def _row_date(fields):
    return fields.get('date') or fields.get('booking_date') or fields.get('value_date') or ''


def held_work_footprint(session, file, record, cache):
    """Where a saved record's work lies: dates of every row it saved (her value, else what the earlier
    reading prints for that row), the spans of its period and of anything imported from its reading, and
    the row ids it references. None when any of it cannot be dated (the caller then holds the whole file)."""
    key = ('held-work-footprint', record['id'])
    if key in cache:
        return cache[key]
    result = None
    try:
        result = _footprint(session, file, record)
    except Exception:
        result = None
    cache[key] = result
    return result


def _footprint(session, file, record):
    from postgres.models.financial import FinancialStatementPeriod
    from services.financial.statement_import import read_statement_import
    request = record['request']
    earlier = UUID(record['evidence_file_id'])
    spans = []
    start, end = _iso(request.get('period_start')), _iso(request.get('period_end'))
    if start and end and start <= end:
        spans.append((start, end))
    rows = request.get('rows') or []
    dates, ids, pages = set(), set(), set()
    printed = None
    for row in rows:
        ids.add(str(row.get('id')))
        page = row.get('manual_page') or _id_page(row.get('id'))
        if page:
            pages.add(int(page))
        value = _iso(row.get('date')) or next((_iso(v) for v in (row.get('date_values') or {}).values() if _iso(v)), None)
        if value is None and not str(row.get('id', '')).startswith('manual:'):
            if printed is None:
                printed = {}
                nested = {_NESTED: True}
                first = read_statement_import(session, case_id=file.case_id, evidence_file_id=earlier,
                    currency=request.get('currency') or None, _include_period_checks=False, _cache=nested)
                proposals = [read_statement_import(session, case_id=file.case_id, evidence_file_id=earlier,
                    statement_id=choice['id'], currency=request.get('currency') or None,
                    _include_period_checks=False, _cache=nested)
                    for choice in first.get('statement_choices') or [] if not choice.get('document_kind')] or [first]
                for proposal in proposals:
                    for other in proposal.get('rows') or []:
                        printed.setdefault(str(other['id']), set()).add(_iso(_row_date(other.get('fields') or {})))
            found = printed.get(str(row.get('id')))
            value = next(iter(found)) if found and len(found) == 1 else None
        if value is None:
            return None  # Her work's dates cannot be determined.
        dates.add(value)
    if not dates and not spans:
        return None
    for source in session.scalars(select(FinancialSourceDocument).where(
            FinancialSourceDocument.case_id == file.case_id, FinancialSourceDocument.evidence_file_id == earlier)):
        for period in session.scalars(select(FinancialStatementPeriod).where(
                FinancialStatementPeriod.source_document_id == source.id)):
            if period.period_start is None or period.period_end is None:
                return None
            spans.append((period.period_start, period.period_end))
    return dict(dates=dates, spans=spans, row_ids=ids, pages=pages)


def _id_page(identifier):
    """The page a reader row id ('<page>:<index>') names, else None."""
    head = str(identifier or '').split(':', 1)[0]
    return int(head) if head.isdigit() and ':' in str(identifier) else None


def touches(footprint, period, row_ids=(), pages=()):
    """True when the work lies in the period (start, end), or references one of its rows or pages (the same
    original's bytes, so a page is the same page in either reading)."""
    start, end = _iso(period[0]), _iso(period[1])
    if footprint is None or start is None or end is None or start > end:
        return True
    return (any(start <= day <= end for day in footprint['dates'])
            or any(a <= end and start <= b for a, b in footprint['spans'])
            or bool(footprint['row_ids'] & {str(i) for i in row_ids})
            or bool(footprint.get('pages', set()) & {int(p) for p in pages if p}))


def _split_release(session, file, unmatched, *, choices, statement_id, period, row_ids, pages, cache):
    """The audit record for a period of a split file that none of her held file-level work touches, or None."""
    if not (SPLIT_RELEASE and unmatched and statement_id and period and len(choices) > 1) or cache.get(_NESTED):
        return None
    if any(record['statement_id'] for record in unmatched):
        return None  # Only file-level work on a file the new reading names periods for.
    prints = [held_work_footprint(session, file, record, cache) for record in unmatched]
    if any(touches(footprint, period, row_ids, pages) for footprint in prints):
        return None
    return dict(reason='untouched_period_of_file_with_held_work', period=[str(period[0]), str(period[1])],
        held_reviews=sorted(record['id'] for record in unmatched),
        held_readings=sorted({record['evidence_file_id'] for record in unmatched}))


# Neil's decision (2026-10-25, BNB2 queue): work saved on an earlier reading of the file is settled, and no
# longer asks for a comparison, when nothing in it is a person's undecided work: System saved it and no person
# saved that statement of that reading (the 2026-10-24 System-only rule, now also for earlier readings), or
# everything entered in it is in the one statement the case saved for its account, period and currency
# (reprepare_carry.saved_statement_holds: payments one for one, no note, hand-added line or confirmation).
# The records are never changed. Off: any such work holds the file, as before.
SETTLED_WORK = os.environ.get('LOUPE_FINANCIAL_RECOVERY_SETTLED_WORK', '1').strip().lower() not in (
    '0', 'false', 'no', 'off')


def _saved_statement(session, case_id, request):
    """The one admitted statement period of this case for the request's account, period and currency, else None."""
    from postgres.models.financial import FinancialAccount, FinancialStatementPeriod
    from services.financial.reprepare_carry import _digits
    digits = _digits(request.get('account_number'))
    start, end, currency = _iso(request.get('period_start')), _iso(request.get('period_end')), request.get('currency')
    if len(digits) < 4 or not start or not end or not currency:
        return None
    found = []
    for period, account in session.execute(
            select(FinancialStatementPeriod, FinancialAccount)
            .join(FinancialAccount, FinancialAccount.id == FinancialStatementPeriod.account_id)
            .join(FinancialSourceDocument, FinancialSourceDocument.id == FinancialStatementPeriod.source_document_id)
            .where(FinancialStatementPeriod.case_id == case_id, FinancialSourceDocument.status == 'admitted',
                   FinancialStatementPeriod.currency == currency)):
        document = session.get(FinancialSourceDocument, period.source_document_id)
        if (document.metadata_ or {}).get('financial_import_removal'):
            continue
        if (_iso(period.period_start), _iso(period.period_end)) == (start, end) and digits in {
                _digits(account.identifier_as_printed), _digits(account.identifier_normalised)}:
            found.append(period)
    return found[0] if len(found) == 1 else None


def settled_work(session, file, records, cache=None, reading=None):
    """{record id: why it is settled} for earlier-reading records with no undecided person work. Read only.
    ``reading``: the current reading's request (import_batches.initial_request), for EQUAL_WORK."""
    if not SETTLED_WORK or not records:
        return {}
    from services.financial.field_proposals import SYSTEM_NAME
    from services.financial.reprepare_carry import NotCarried, saved_statement_holds
    from services.financial.reread_carry import NOTES
    cache = cache if cache is not None else {}
    people = {(r['evidence_file_id'], r['statement_id']) for r in records
              if (r.get('saved_by') or {}).get('name') != SYSTEM_NAME}
    settled = {}
    for record in records:
        key = ('settled-work', record['id'])
        if key not in cache:
            request, why = record['request'], None
            system = ((record.get('saved_by') or {}).get('name') == SYSTEM_NAME
                      and (record['evidence_file_id'], record['statement_id']) not in people
                      and not request.get('_saved_balance_corrections')
                      and not any(str(request.get(field) or '').strip() for field in NOTES)
                      and not any(str(row.get('id', '')).startswith('manual:') or row.get('manual_page')
                                  or str(row.get('reason') or '').strip() for row in request.get('rows') or []))
            if system:
                why = 'system_only'
            else:
                case_id = getattr(file, 'case_id', None)
                period = _saved_statement(session, case_id, request) if case_id else None
                if period is not None:
                    try:
                        saved_statement_holds(session, request, period)
                        why = f'in_saved_statement:{period.id}'
                    except NotCarried:
                        pass
            if why is None and EQUAL_WORK:
                why = _replaced_by_own_save(record, records)
            cache[key] = why
        why = cache[key]
        if not why and EQUAL_WORK and reading is not None:
            equal_key = ('settled-work-equal', record['id'], reading.get('statement_id'), reading.get('expected_revision'))
            if equal_key not in cache:
                cache[equal_key] = 'equal_to_reading' if equal_to_reading(record, reading) else None
            why = cache[equal_key]
        if why:
            settled[record['id']] = why
    return settled


# Neil's decision (2026-10-26, fin-queue3 L23): earlier work stops asking for a comparison when nothing in it
# differs from what the current reading already holds: (a) a draft the same person saved again later, on the
# same reading (same file, statement and reading revision: her later save started from it), or (b) a record
# whose every value equals the current reading (details the same or left blank, payments one for one including
# the lines left out and lines added by hand that the reader now reads, no note, row reason, confirmation or
# balance correction). The records are never changed. Off: such work holds the statement, as before.
EQUAL_WORK = os.environ.get('LOUPE_FINANCIAL_RECOVERY_EQUAL_WORK', '1').strip().lower() not in (
    '0', 'false', 'no', 'off')
_EQUAL_DETAILS = ('account_number', 'holder', 'institution')


def _saver(record):
    saved_by = record.get('saved_by') or {}
    return saved_by.get('user_id') or saved_by.get('name') or None


def _saved_at(record):
    try:
        moment = datetime.fromisoformat(str(record.get('saved_at') or ''))
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def _replaced_by_own_save(record, records):
    """'replaced_by_own_save:<id>' when the same person saved the same statement of the same reading again later."""
    request, who, when = record['request'], _saver(record), _saved_at(record)
    revision = request.get('expected_revision')
    if not (who and when and revision):
        return None
    for other in records:
        if (other['id'] != record['id'] and other['evidence_file_id'] == record['evidence_file_id']
                and other['statement_id'] == record['statement_id'] and _saver(other) == who
                and other['request'].get('expected_revision') == revision
                and _saved_at(other) is not None and _saved_at(other) > when):
            return f"replaced_by_own_save:{other['id']}"
    return None


def equal_to_reading(record, reading):
    """True when every value in the record equals the current reading ``reading`` (a request)."""
    from services.financial.review_carry import same_value
    from services.financial.reread_carry import CONFIRMATIONS, NOTES, NotCarried, payments
    request = record['request']
    if record['statement_id'] != (reading.get('statement_id') or None):
        return False
    if request.get('_saved_balance_corrections') or any(request.get(field) for field in NOTES + CONFIRMATIONS):
        return False
    if any(str(row.get('reason') or '').strip() for row in request.get('rows') or []):
        return False
    if request.get('currency') and request['currency'] != reading.get('currency'):
        return False
    for field in ('period_start', 'period_end'):
        if request.get(field) and str(request[field]) != str(reading.get(field) or ''):
            return False
    for field in _EQUAL_DETAILS:
        mine = str(request.get(field) or '').strip()
        if mine and not same_value(field, mine, str(reading.get(field) or '').strip()):
            return False
    try:
        return payments(request.get('rows') or []) == payments(reading.get('rows') or [])
    except (NotCarried, ValueError, TypeError):
        return False


def recovery_state(session, file, *, sources, choices, statement_id, revision, cache=None, period=None, row_ids=(), pages=(),
                   reading=None):
    """``reading``: the current reading's request (import_batches.initial_request), when it is read."""
    cache = cache if cache is not None else {}
    key = ('previous-reviews', str(file.id))
    if key not in cache:
        cache[key] = saved_ancestor_reviews(session, file)
    # Work an engine re-read carried onto this reading (reread_carry) is its own saved review now; the
    # earlier records stay listed in history but no longer ask for a comparison. Nor does settled work.
    carried = set((file.metadata_ or {}).get('financial_review_carried') or ())
    records = [record for record in cache[key] if record['id'] not in carried]
    settled = settled_work(session, file, records, cache, reading=reading)
    records = [record for record in records if record['id'] not in settled]
    if not records:
        return None, None
    reading_key = ('recovery-reading', str(file.id))
    if reading_key not in cache:
        cache[reading_key] = _digest(dict(file=str(file.id), sha256=file.sha256, sources=sources,
            periods=[c['id'] for c in choices]))
    recovery_revision = _digest([cache[reading_key], sorted(r['id'] for r in records)])
    available = {c['id'] for c in choices} or {None}
    exact = [r for r in records if r['statement_id'] == statement_id]
    # More than one saved alternative is not resolved by picking a timestamp.
    previous = exact[0] if len(exact) == 1 else None
    # File-level work an engine re-read carried as details onto some periods of this reading (reread_carry,
    # payments matched): those periods no longer wait for it; the others still do.
    from services.financial.reread_carry import DETAILS_CARRY
    released_to = ((file.metadata_ or {}).get('financial_review_details_release') or {}) if DETAILS_CARRY else {}
    unmatched_records = [r for r in records if r['statement_id'] not in available
                         and not (statement_id and statement_id in (released_to.get(r['id']) or ()))]
    unmatched = len(unmatched_records)
    released = _split_release(session, file, unmatched_records, choices=choices, statement_id=statement_id,
        period=period, row_ids=row_ids, pages=pages, cache=cache) if unmatched else None
    required = bool((unmatched and not released) or len(exact) > 1 or
                    (revision and previous and previous['request'].get('expected_revision') != revision))
    comparison = (file.metadata_ or {}).get('financial_review_comparison', {})
    acknowledged = comparison.get('revision') == recovery_revision
    summaries = [dict(id=r['id'], evidence_file_id=r['evidence_file_id'], filename=r['filename'],
        statement_id=r['statement_id'], origin=r['origin'], saved_at=r['saved_at'],
        saved_by=r['saved_by'], holder=r['request'].get('holder', ''),
        account=r['request'].get('account_number', ''), currency=r['request'].get('currency', ''),
        period_start=r['request'].get('period_start', ''), period_end=r['request'].get('period_end', ''),
        row_count=len(r['request']['rows']), changed_row_count=sum(bool(row.get('reason')) for row in r['request']['rows']),
        period_found=r['statement_id'] in available) for r in records]
    return dict(revision=recovery_revision, required=required, acknowledged=acknowledged,
        unmatched_count=unmatched, reviews=summaries,
        compared_at=comparison.get('saved_at') if acknowledged else None,
        **({'split_release': released} if released else {})), previous


def previous_review_detail(session, *, case_id, evidence_file_id, review_id, offset=0, limit=30):
    file = session.scalar(select(EvidenceFile).where(EvidenceFile.id == evidence_file_id,
        EvidenceFile.case_id == case_id))
    if file is None:
        raise PdfMappingError('Statement not found in this case.', 404)
    record = next((r for r in saved_ancestor_reviews(session, file) if r['id'] == review_id), None)
    if record is None:
        raise PdfMappingError('The earlier saved review changed or is unavailable. Reopen this statement.', 409)
    request = record['request']
    return dict(case_id=str(case_id), evidence_file_id=str(evidence_file_id),
        review_id=review_id, request={**request, 'rows': request['rows'][offset:offset + limit]},
        row_count=len(request['rows']), offset=offset)


def acknowledge_recovery(session, *, case_id, evidence_file_id, expected_revision, actor):
    from services.financial.statement_import import read_statement_import
    file = session.scalar(select(EvidenceFile).where(EvidenceFile.id == evidence_file_id,
        EvidenceFile.case_id == case_id).with_for_update().execution_options(populate_existing=True))
    if file is None:
        raise PdfMappingError('Statement not found in this case.', 404)
    proposal = read_statement_import(session, case_id=case_id, evidence_file_id=evidence_file_id,
        _include_period_checks=False)
    recovery = proposal.get('review_recovery')
    if not recovery or recovery['revision'] != expected_revision:
        raise PdfMappingError('The saved reviews or new reading changed. Reload and compare them before continuing.', 409)
    saved = dict(revision=expected_revision, saved_at=datetime.now(timezone.utc).isoformat(),
        saved_by=dict(user_id=str(actor.user_id), name=actor.name))
    metadata = deepcopy(file.metadata_ or {})
    metadata.setdefault('financial_review_comparison_history', []).append(saved)
    metadata['financial_review_comparison'] = saved
    file.metadata_ = metadata
    # A file-wide comparison should not require opening and saving every
    # unchanged period just to refresh its old readiness message.
    from services.financial.import_batches import assess
    items = session.scalars(select(FinancialImportBatchItem)
        .join(FinancialImportBatch, FinancialImportBatch.id == FinancialImportBatchItem.batch_id)
        .where(FinancialImportBatch.case_id == case_id,
               FinancialImportBatchItem.file_id == evidence_file_id,
               FinancialImportBatchItem.status.in_(('attention', 'ready')))
        .with_for_update(of=FinancialImportBatchItem)).all()
    cache = {}
    for item in items:
        current = read_statement_import(session, case_id=case_id, evidence_file_id=evidence_file_id,
            currency=item.summary.get('currency'), statement_id=item.statement_key or None,
            _include_period_checks=False, _cache=cache)
        if item.summary.get('revision') != current['revision']:
            continue  # A changed reading needs its own edit recovery, not just acknowledgement.
        status, summary = assess(current, item.review_request)
        item.status = status
        item.summary = {**item.summary, **summary}
    session.commit()
    return dict(case_id=str(case_id), evidence_file_id=str(evidence_file_id), **saved)
