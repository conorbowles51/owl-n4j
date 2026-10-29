"""Compare statement dates before import without excluding any evidence.

A matching account reference and overlapping period are a reason to compare
sources, not a determination that the payments or account holders are identical.
"""
import os
import re
from functools import lru_cache
from datetime import date
from sqlalchemy import select
from postgres.models.evidence import EvidenceFile
from postgres.models.financial import FinancialAccount, FinancialSourceDocument, FinancialStatementPeriod
from postgres.models.financial_import_batches import FinancialImportBatch as Batch, FinancialImportBatchItem as Item
from services.financial.accounts import AccountDraft, AccountError, _fold, NON_VALUES
from services.financial.pdf_candidates import _digest, PdfMappingError


class ComparisonSources(dict):
    families = None
    duplicate_context = None
    case_id = None
    files = None
    # Pending items whose older summary lacks the bank/product identity the
    # comparison needs, when the caller does not allow re-reading their PDF.
    unhydrated = ()


class ReadingDeferred(Exception):
    """A read path declined to reconstruct a statement from its PDF.

    Batch list reads use stored projections only. The write side (worker,
    saves and the readiness refresh) re-reads and stores what was missing.
    """


HYDRATION_ERROR_KEY = 'comparison_hydration_error'


HYDRATION_ERROR = 'Reopen this older review to check its current bank, account and statement dates.'


def needs_hydration(item):
    """True when an older summary lacks fields the comparison derives from a reading."""
    return (not item.review_request and 'institution' not in item.summary) or 'account_type' not in item.summary


@lru_cache(maxsize=65536)
def _account_identity(institution, account_number, currency, kind=None):
    """(identity key, provisional) of a printed account, or None. A pure function of its four
    inputs; a case comparison derives it for every statement in the case (thousands) per import.
    ``kind``: the same reference kind as the ledger key (a credit line sharing its deposit
    account's number)."""
    try:
        identity = AccountDraft.observed(institution_name=institution or None,
            identifier_as_printed=account_number, currency=currency,
            metadata=dict(account_reference_kind=kind) if kind else None).identity()
    except (ValueError, TypeError, AccountError):
        return None
    return identity.key, identity.is_provisional


def scope(raw):
    try:
        start, end = date.fromisoformat(raw.get('period_start', '')), date.fromisoformat(raw.get('period_end', ''))
        if start > end:
            return None
    except (ValueError, TypeError):
        return None
    institution, account_number, currency = raw.get('institution'), raw.get('account_number'), raw.get('currency')
    # The same reference kind as the ledger key (a credit line sharing its deposit account's number).
    kind = raw.get('account_reference_kind') or None
    try:
        identity = _account_identity(institution, account_number, currency, kind)
    except TypeError:  # an unhashable stored value: derive it without the cache
        identity = _account_identity.__wrapped__(institution, account_number, currency, kind)
    if identity is None:
        return None
    key, provisional = identity
    holder = _fold(raw.get('holder'))
    return dict(identity=key, currency=currency, start=start.isoformat(), end=end.isoformat(),
                holder=holder if holder not in NON_VALUES else '', account_type=_fold(raw.get('account_type')),
                account_reference=re.sub(r'[\s-]+', '', _fold(account_number)),
                full_reference=not provisional and bool(_fold(institution))
                    and _fold(institution) not in NON_VALUES)


def same_statement(left, right):
    """Strong metadata is a hold for comparison, never proof to delete a source."""
    return bool(left and right and left.get('full_reference') and right.get('full_reference')
        and left.get('holder') and left['holder'] == right.get('holder')
        and all(left.get(key) == right.get(key) for key in ('identity', 'account_reference', 'currency', 'start', 'end', 'account_type')))


def same_printed_period(left, right):
    """The same printed account reference, currency, product and exact dates.

    Unlike ``same_statement`` this does not need a full account number or an
    equal holder: a card statement prints only its last four digits, and two
    productions of one statement can read the holder or bank name differently.
    It nominates a copy for comparison and holds an exact-period overlap. It
    never sets a copy aside by itself; only identical payments and balances do.
    """
    reference = _printed_reference(left)
    return bool(left and right and reference and any(ch.isdigit() for ch in reference)
        and reference == _printed_reference(right)
        and all(left.get(key) == right.get(key) for key in ('currency', 'start', 'end', 'account_type')))


def _printed_reference(scope):
    """The printed reference without a leading mask (``****1234``, ``xxxx1234``,
    ``...1234`` all read ``1234``); letters and every other character are kept."""
    value = re.sub(r'^(?:[*\u2022.#]+|x{2,})', '', (scope or {}).get('account_reference') or '')
    return re.sub(r'[^0-9a-z]', '', value)


def overlaps(left, right):
    return bool(left and right and left['identity'] == right['identity'] and left['currency'] == right['currency']
                and left['start'] <= right['end'] and right['start'] <= left['end'])


def summary_request(summary):
    return dict(expected_revision=summary.get('revision'), statement_id=summary.get('statement_id'),
        currency=summary.get('currency'), institution=summary.get('institution', ''),
        account_number=summary.get('account', ''), holder=summary.get('holder', ''), account_type=summary.get('account_type', ''),
        period_start=summary.get('period_start', ''), period_end=summary.get('period_end', ''),
        account_reference_kind=summary.get('account_reference_kind', ''))


# A saved period's statement id and first printed page never change once the
# record is written (both are set when it is created; nothing rewrites them).
# Reading them makes PostgreSQL detoast the record's whole metadata, which made
# every comparison (one per import, and per batch check) read every saved
# reading of the case. They are remembered per record id, so a comparison
# reads them only for records saved since the last one.
_SAVED_KEYS = {}
SAVED_KEYS_LIMIT = 200_000


def _saved_keys(session, source_ids):
    """{source id: (statement id, first page)} for these saved records."""
    missing = [identity for identity in source_ids if identity not in _SAVED_KEYS]
    for start in range(0, len(missing), 2000):
        chunk = missing[start:start + 2000]
        found = {identity: (statement_id, page) for identity, statement_id, page in session.execute(select(
            FinancialSourceDocument.id,
            FinancialSourceDocument.metadata_['statement_import_statement_id'].as_string(),
            FinancialSourceDocument.metadata_['statement_import_original']['rows'][0]['page_number'].as_integer())
            .where(FinancialSourceDocument.id.in_(chunk)))}
        if len(_SAVED_KEYS) + len(found) > SAVED_KEYS_LIMIT:
            _SAVED_KEYS.clear()
        _SAVED_KEYS.update(found)
    return {identity: _SAVED_KEYS.get(identity, (None, None)) for identity in source_ids}


# What comparison_sources reads from a prepared period's stored summary (summary_request and the checks
# below). Only these scalars are kept per item (row_versions): decoding every item's whole summary (14 MB of
# JSON on a case with 2,400 prepared periods) was the largest part of each import's case comparison.
COMPARED_SUMMARY_KEYS = ('revision', 'statement_id', 'currency', 'institution', 'account', 'holder', 'account_type',
                         'period_start', 'period_end', 'account_reference_kind', 'page_number', HYDRATION_ERROR_KEY,
                         'statement_form', 'chain_contradicted')
_PENDING_VALUES = None


def _compared_summary(values):
    summary = values['summary'] if isinstance(values['summary'], dict) else {}
    return dict(summary={key: summary[key] for key in COMPARED_SUMMARY_KEYS
                         if key in summary and isinstance(summary[key], (str, int, float, bool, type(None)))},
                review_request_text=values['review_request_text'])


def _pending_copies(session, case_id):
    """Read-only copies of the case's prepared, unsaved periods: id, file, statement key, status, the
    compared summary keys and the saved batch review (decoded afresh for every read: callers may change it)."""
    global _PENDING_VALUES
    import json
    from sqlalchemy import Text, cast
    from services.financial.row_versions import RowValues
    if _PENDING_VALUES is None:
        _PENDING_VALUES = RowValues(Item, kept=100_000)
    rows = _PENDING_VALUES.rows(session, (Item.id, Item.file_id, Item.statement_key, Item.status),
        (Item.summary.label('summary'), cast(Item.review_request, Text).label('review_request_text')),
        (Batch.id == Item.batch_id, EvidenceFile.id == Item.file_id, Batch.case_id == case_id,
         EvidenceFile.case_id == case_id, Batch.status != 'removed',
         Item.status.in_(('ready', 'attention', 'pending_import'))),
        order_by=Item.id, transform=_compared_summary)
    from types import SimpleNamespace
    return [SimpleNamespace(id=row.id, file_id=row.file_id, statement_key=row.statement_key, status=row.status,
                            summary=dict(row.summary),
                            review_request=json.loads(row.review_request_text) if row.review_request_text else None)
            for row in rows]


def comparison_sources(session, case_id, pending=None, *, read_pending=None, duplicate_context=None):
    """Load a case once per batch check, without loading imported PDF readings."""
    periods = session.execute(select(
        FinancialAccount.identity_key, FinancialStatementPeriod.currency,
        FinancialStatementPeriod.period_start, FinancialStatementPeriod.period_end,
        FinancialSourceDocument.id,
        EvidenceFile.id, EvidenceFile.original_filename,
        EvidenceFile.metadata_['statement_root_evidence_id'].as_string(),
        FinancialAccount.institution_name, FinancialAccount.identifier_as_printed,
        FinancialAccount.holder_name, FinancialAccount.account_type,
        FinancialAccount.metadata_['account_reference_kind'].as_string())
        .select_from(FinancialStatementPeriod)
        .join(FinancialSourceDocument, FinancialSourceDocument.id == FinancialStatementPeriod.source_document_id)
        .join(FinancialAccount, FinancialAccount.id == FinancialStatementPeriod.account_id)
        .join(EvidenceFile, EvidenceFile.id == FinancialSourceDocument.evidence_file_id)
        .where(FinancialStatementPeriod.case_id == case_id, FinancialSourceDocument.case_id == case_id,
               FinancialAccount.case_id == case_id, EvidenceFile.case_id == case_id,
               FinancialSourceDocument.status == 'admitted')).all()
    keys = _saved_keys(session, [row[4] for row in periods])
    imported = [(*row[:5], *keys[row[4]], *row[5:]) for row in periods]
    if pending is None:
        items = _pending_copies(session, case_id)
        # One evidence row per PDF, not one per prepared period: joining the file
        # to every item decoded its metadata thousands of times on a large case.
        from services.financial.source_lineage import case_files
        owners = case_files(session, case_id) if items else {}
        pending = [(item, owners[item.file_id]) for item in items if item.file_id in owners]
    from services.financial.source_lineage import comparison_lineage, current_version
    # Read-only copies, reused per row while unchanged: this function never writes.
    groups = comparison_lineage(session, case_id)
    families = {str(file.id): root for root, versions in groups.items() for file in versions}
    current_ids = {str(current_version(versions).id) for versions in groups.values()}
    entries, prepared, cache = ComparisonSources(), {}, {}
    entries.families = families
    entries.unhydrated = set()
    unhydrated_keys = set()
    from services.financial.pending_duplicate_projection import load_projection_context, cached_disposition
    all_files = [file for versions in groups.values() for file in versions]
    entries.case_id = str(case_id)
    entries.files = {str(file.id): file for file in all_files}
    decision_ids = set()
    for file in all_files:
        for decision in (file.metadata_ or {}).get('financial_duplicate_dispositions', {}).values():
            if decision.get('status') in ('ignored', 'restored'):
                decision_ids.add(str(file.id))
                decision_ids.add((decision.get('retained') or {}).get('evidence_file_id'))
    if decision_ids:
        needed = [file for file in all_files if str(file.id) in decision_ids]
        # A caller that already fingerprinted a superset of these files (the
        # file register does) passes its context; each file's guard is computed
        # independently, so a superset gives the same answers.
        if duplicate_context is not None and all(str(file.id) in duplicate_context['files'] for file in needed):
            entries.duplicate_context = duplicate_context
        else:
            entries.duplicate_context = load_projection_context(session, case_id, needed)
    def reading(item, *, include_duplicate_disposition=True):
        if read_pending is not None:
            return read_pending(item, include_duplicate_disposition=include_duplicate_disposition)
        from services.financial.statement_import import read_statement_import
        return read_statement_import(session, case_id=case_id, evidence_file_id=item.file_id,
            currency=item.summary.get('currency'), statement_id=item.statement_key or None,
            _cache=cache, _include_period_checks=False,
            _include_duplicate_disposition=include_duplicate_disposition)
    def add(identity, currency, value):
        entries.setdefault((identity, currency), []).append(value)
    for identity, currency, start, end, document_id, statement_id, page_number, file_id, filename, root, bank, account, holder, account_type, kind in imported:
        if start is None or end is None:
            continue
        descriptor = scope(dict(institution=bank, account_number=account, holder=holder, account_type=account_type,
            currency=currency, period_start=start.isoformat(), period_end=end.isoformat(), account_reference_kind=kind))
        add(identity, currency, dict(key=(families.get(str(file_id), str(file_id)), statement_id or ''), scope=descriptor,
            file_id=str(file_id), statement_id=statement_id, source_document_id=str(document_id),
            filename=filename, status='imported', page_number=page_number or 1, period_start=start.isoformat(), period_end=end.isoformat()))
    for item, file in pending:
        from services.financial.statement_progress import review_progress
        from services.financial.effective_statement_review import resolve_review
        effective, conflict = resolve_review(item.review_request, review_progress(file, item.statement_key))
        raw = effective or summary_request(item.summary)
        if conflict:
            raw = {**raw, '_coverage_error': 'The individual statement and batch have different saved edits. Compare both reviews before importing.'}
        raw = {**raw, 'account_type': item.summary.get('account_type', ''),
               'account_reference_kind': item.summary.get('account_reference_kind', '')}
        # Older summaries did not save bank/product identity. Recover only
        # absent fields from that reading, preserving every saved correction.
        # Source geometry/catalogue is cached per PDF.
        missing_bank = not item.review_request and 'institution' not in item.summary
        deferred = False
        if missing_bank or 'account_type' not in item.summary:
            try:
                proposal = reading(item)
                if missing_bank:
                    raw = {**raw, 'institution': proposal['metadata'].get('institution', '')}
                if 'account_type' not in item.summary:
                    raw = {**raw, 'account_type': proposal['metadata'].get('account_type') or ''}
            except PdfMappingError:
                raw = {**raw, '_coverage_error': HYDRATION_ERROR}
            except ReadingDeferred:
                if item.summary.get(HYDRATION_ERROR_KEY):
                    # The write side already found this older reading unusable.
                    raw = {**raw, '_coverage_error': HYDRATION_ERROR}
                else:
                    deferred = True
        prepared[item.id] = raw
        from services.financial.pending_statement_duplicates import METADATA_KEY
        decision = (file.metadata_ or {}).get(METADATA_KEY, {}).get(item.statement_key or '')
        if decision and decision.get('status') == 'ignored':
            try:
                current_decision = cached_disposition(entries.duplicate_context, file, item.statement_key)
                if current_decision and current_decision.get('current') and current_decision['status'] == 'ignored':
                    continue
            except PdfMappingError:
                pass  # An unreadable current source still requires comparison.
        # Old internal readings remain in history, not as fresh competing work.
        if str(file.id) not in current_ids:
            continue
        if deferred:
            # Comparing with an incomplete identity could miss or invent an
            # overlap. Hold comparisons until the write side stores the fields.
            entries.unhydrated.add(item.id)
            unhydrated_keys.add((str(file.id), item.statement_key or ''))
            continue
        own = scope(raw)
        if own is None:
            continue
        add(own['identity'], own['currency'], dict(
            key=(families.get(str(file.id), str(file.id)), item.statement_key or ''), scope=own,
            file_id=str(file.id), statement_id=item.statement_key or None, source_document_id=None,
            filename=file.original_filename, status='awaiting_import', page_number=item.summary.get('page_number', 1),
            period_start=own['start'], period_end=own['end'],
            chain_contradicted=bool(item.summary.get('chain_contradicted')),
            **({'statement_form': item.summary['statement_form']} if item.summary.get('statement_form') else {})))
    # A statement reviewed individually may have no batch item yet. Register
    # only explicit current decisions, never guess candidates from file names.
    registered = {(entry['file_id'], entry.get('statement_id') or '') for values in entries.values() for entry in values}
    registered |= unhydrated_keys  # Held above; never substituted by its decision scope.
    from services.financial.pending_statement_duplicates import METADATA_KEY
    inactive = {(str(file_id), key or '') for file_id, key in session.execute(select(Item.file_id, Item.statement_key)
        .join(Batch, Batch.id == Item.batch_id).where(Batch.case_id == case_id,
            Item.status.in_(('skipped', 'assigned', 'removed', 'superseded_reading')))).all()}
    for versions in groups.values():
        for file in versions:
            if str(file.id) not in current_ids:
                continue
            for key, decision in (file.metadata_ or {}).get(METADATA_KEY, {}).items():
                own = decision.get('scope')
                if (str(file.id), key) in registered or (str(file.id), key) in inactive or not own or decision.get('status') not in ('retained', 'restored', 'needs_comparison'):
                    continue
                add(own['identity'], own['currency'], dict(key=(families.get(str(file.id), str(file.id)), key),
                    scope=own, file_id=str(file.id), statement_id=key or None, source_document_id=None,
                    filename=file.original_filename, status='awaiting_import',
                    page_number=(decision.get('retained') or {}).get('page_number', 1),
                    period_start=own['start'], period_end=own['end']))
    return entries, prepared


# A saved statement printing the same account reference, product, currency and
# dates under another bank wording holds this one for comparison (r15-hold-gaps).
# Off: only the same bank identity is compared.
SAVED_PRINTED_PERIOD_ACROSS_BANKS = os.environ.get('LOUPE_FINANCIAL_SAVED_PRINTED_PERIOD_ACROSS_BANKS', '1') != '0'


# An unsaved upload of the very same bytes and statement (another evidence file of one PDF) is not a separate
# statement to compare with the copy the copy rule keeps (pending_statement_duplicates: its own decision is a
# current 'retained', the other's is not). Held against each other, two such uploads were never saved, and the
# copies set aside in their favour left the statement out of the ledger with no item asking for it (BNB2: CAAL
# BBVA 0119200843 Aug 2025, BBVA 0125701104 USD Sep 2025; fin-queue lessons 5 and 12). Only the retained copy is
# released, so no import path finds two of them ready; once it is saved the other is held by a saved copy. A saved
# copy and any upload with other bytes are still compared. Off: every unsaved upload is compared.
IDENTICAL_UNSAVED_TO_RETAINED = os.environ.get('LOUPE_FINANCIAL_COVERAGE_IDENTICAL_UNSAVED_TO_RETAINED', '1') != '0'


def _copy_of_retained(session, file, files, other, request):
    """`other` is an unsaved upload of `file`'s bytes and statement, and `file` holds the current retained decision."""
    key = request.get('statement_id') or ''
    if other['status'] != 'awaiting_import' or (other.get('statement_id') or '') != key or other['file_id'] == str(file.id):
        return False
    from uuid import UUID
    other_file = (files or {}).get(other['file_id']) or session.get(EvidenceFile, UUID(other['file_id']))
    if other_file is None or not file.sha256 or other_file.sha256 != file.sha256:
        return False
    from services.financial.pending_statement_duplicates import METADATA_KEY
    stored = lambda f: ((f.metadata_ or {}).get(METADATA_KEY) or {}).get(key) or {}
    own = stored(file)
    if stored(other_file).get('status') == 'retained':
        return False
    if '_copy_rule_status' in request:
        # A batch projection passes the copy rule's decision for its own projected reading and review.
        return request['_copy_rule_status'] == 'retained'
    if own.get('status') != 'retained':
        return False
    # Decided on this very reading (the writer decides it just before this check; a batch projection reads it).
    return bool(request.get('expected_revision') and own.get('reading_revision') == request['expected_revision'])


def coverage_review(session, *, case_id, file_id, request, sources=None):
    # Batch comparison already loaded the case's source lineage. Reuse that
    # request-local snapshot instead of repeating a SQL read for every period.
    files = getattr(sources, 'files', None)
    if files is not None and getattr(sources, 'case_id', None) == str(case_id):
        file = files.get(str(file_id))
        if file is not None and str(file.case_id) != str(case_id):
            file = None
    else:
        file = session.scalar(select(EvidenceFile).where(EvidenceFile.id == file_id, EvidenceFile.case_id == case_id))
    if file is None:
        raise PdfMappingError('Statement not found in this case.', 404)
    own = scope(request)
    if own is None:
        return dict(available=False, candidates=[], revision=None,
                    reason='A bank, account reference and complete statement dates are needed to compare coverage.')
    # `sources` may be a callable giving the case snapshot, built only when needed.
    sources = sources() if callable(sources) else sources if sources is not None else comparison_sources(session, case_id)[0]
    families = getattr(sources, 'families', None)
    if families is None:
        from services.financial.source_lineage import case_lineage
        families = {str(v.id): root for root, versions in case_lineage(session, case_id).items() for v in versions}
    root = families.get(str(file.id), str(file.id))
    own_key = (root, request.get('statement_id') or '')
    own_page = request.get('page_number')
    candidates = {}
    for other in sources.get((own['identity'], own['currency']), []):
        identifier = other['key']
        if identifier == own_key or (other['source_document_id'] and other['source_document_id'] == str(request.get('replaces_source_document_id', ''))):
            continue
        # Periods that do not share a date are never candidates (both branches
        # below end in this test); skip the printed-reference comparison.
        if own['start'] > other['period_end'] or other['period_start'] > own['end']:
            continue
        if IDENTICAL_UNSAVED_TO_RETAINED and _copy_of_retained(session, file, files, other, request):
            continue
        # A masked card reference cannot meet ``same_statement``. The same bank,
        # reference and exact printed period is still another copy of this
        # statement until its payments show otherwise, so it is held, not warned.
        exact = same_statement(own, other.get('scope')) or same_printed_period(own, other.get('scope'))
        same_file = False
        if identifier[0] == own_key[0] and exact:
            # Reader upgrades can change section keys. A verified internal version
            # of this exact account/period is still the same source, not another PDF.
            # A statement of the file's current reading that starts on another
            # printed page is not that: the file prints a second statement for
            # the same account and dates (a reprint, or a copy whose balances
            # and payments contradict the first), and the two must be compared.
            if not (other['status'] == 'awaiting_import' and own_page and other.get('page_number')
                    and int(other['page_number']) != int(own_page)):
                continue
            # A second printing the file's next statement contradicts is held by
            # itself (admission); it does not hold the printing the file continues from.
            if other.get('chain_contradicted') and not request.get('chain_contradicted'):
                continue
            same_file = True
        if own['start'] > other['period_end'] or other['period_start'] > own['end']:
            continue
        # Prefer the imported record if the same source is in another batch.
        if identifier not in candidates or other['status'] == 'imported':
            candidates[identifier] = {**{k: v for k, v in other.items() if k not in ('key', 'scope')},
                'matching_statement': exact, 'same_file_statement': same_file}
    if SAVED_PRINTED_PERIOD_ACROSS_BANKS:
        # A saved statement of the same printed account reference, product,
        # currency and exact dates, filed under another bank identity (another
        # reader worded the bank differently): the same printed statement until
        # its money shows otherwise. A copy with the same money was already set
        # aside before this check (pending_statement_duplicates); one with other
        # money is held here for a person, never saved again into another
        # ledger account (r15-hold-gaps, live case).
        for (identity, currency), entries in sources.items():
            if identity == own['identity'] or currency != own['currency']:
                continue
            for other in entries:
                identifier = other['key']
                if (other['status'] != 'imported' or identifier[0] == own_key[0] or identifier in candidates
                        or not same_printed_period(own, other.get('scope'))):
                    continue
                candidates[identifier] = {**{k: v for k, v in other.items() if k not in ('key', 'scope')},
                    'matching_statement': True, 'same_file_statement': False, 'other_bank_wording': True}
    ordered = sorted(candidates.items())
    revision = _digest(dict(version='statement-coverage-review-v1', scope=own,
        reading=request.get('expected_revision'), candidates=[dict(key=k, start=v['period_start'], end=v['period_end'],
            matching_statement=v['matching_statement']) for k,v in ordered]))
    return dict(available=True, revision=revision, candidates=[v for _,v in ordered],
                matching_statement=any(v['matching_statement'] for _, v in ordered),
                same_file_statement=any(v['same_file_statement'] for _, v in ordered))


def duplicate_hold(review, request):
    return bool(review.get('matching_statement') and requires_decision(review, request))


def requires_decision(review, request):
    return bool(review['candidates'] and not (
        request.get('coverage_review_revision') == review['revision']
        and request.get('coverage_review_reason', '').strip()))


def require_coverage_decision(session, *, case_id, file_id, request):
    review = coverage_review(session, case_id=case_id, file_id=file_id, request=request)
    if requires_decision(review, request):
        raise PdfMappingError('Another statement covers some of these dates for the same account reference. Compare the files and record why this statement should also be imported, or leave this copy unimported.', 409)
    return review


def later_queries_trim_themselves(review, request, *, file_id, statement_id, summary):
    """The coverage review of a movement query without the waiting queries that rank after it.

    Overlapping movement queries of one account are saved in order of their
    dates (start, end, then file and statement for a tie): the first is saved
    as read, and each later one is trimmed against it once it is saved
    (``statement_overlap_trim``), so the later queries' overlap is theirs to
    resolve, not a reason to hold the first. Everything else stays a candidate:
    saved statements, waiting statements that are not queries, earlier queries,
    and any copy of the same printed period.
    """
    from services.financial.statement_overlap_trim import TRIM_OVERLAPS
    from services.financial.statement_import_santander_query import FORM
    if not TRIM_OVERLAPS or summary.get('statement_form') != FORM or not review.get('candidates'):
        return review
    own = (request.get('period_start') or '', request.get('period_end') or '', str(file_id), statement_id or '')
    kept = [c for c in review['candidates'] if not (
        c.get('status') == 'awaiting_import' and c.get('statement_form') == FORM and not c.get('matching_statement')
        and (c.get('period_start') or '', c.get('period_end') or '', str(c.get('file_id')), c.get('statement_id') or '') > own)]
    if len(kept) == len(review['candidates']):
        return review
    return {**review, 'candidates': kept, 'later_queries': len(review['candidates']) - len(kept)}
