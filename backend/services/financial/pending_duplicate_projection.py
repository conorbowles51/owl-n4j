"""Bounded duplicate-decision freshness checks without reconstructing statements."""
from collections import OrderedDict, defaultdict
from copy import deepcopy
from threading import Lock
from uuid import UUID

from sqlalchemy import String, cast, func, inspect, literal_column, select, text

from postgres.models.evidence import EvidenceDocumentText, EvidenceFile, EvidenceTableGeometry
from postgres.models.financial import FinancialSourceDocument
from postgres.models.financial_import_batches import FinancialImportBatch, FinancialImportBatchItem
from services.financial.pdf_candidates import _digest


def _uuid(value):
    try:
        return UUID(str(value))
    except (ValueError, TypeError):
        return None


# Per process: (table, primary key) -> (row version, md5 of its payload). The
# database hashed every geometry page and source record on each comparison
# (0.43 s on a large case); a row's hash is reused while its xmin is unchanged.
_DIGESTS = OrderedDict()
_DIGESTS_LOCK = Lock()
DIGESTS_KEPT = 100_000


def _row_version(model):
    return literal_column(f'{model.__tablename__}.xmin::text')


def _digested(session, model, keys, columns, digest, *conditions, kind=None):
    """[(key tuple, column tuple, digest)] for matching rows, hashing only changed rows.

    ``digest`` is any expression that is costly for the database (it reads a
    large value); ``kind`` names it when one table is digested more than one way.
    """
    table = kind or model.__tablename__
    version = _row_version(model).label('row_version')
    width = len(keys)
    rows = session.execute(select(*keys, *columns, version).where(*conditions)).all()
    found, missing = {}, []
    with _DIGESTS_LOCK:
        for row in rows:
            key, values, row_version = tuple(row[:width]), tuple(row[width:-1]), row[-1]
            known = _DIGESTS.get((table, key))
            if known is not None and known[0] == row_version:
                found[key] = (key, values, known[1])
            else:
                missing.append((key, values))
    if missing:
        wanted = {key for key, _ in missing}
        # Hash the version read with it; a row changed since the first read
        # is stored under its newer version, as a fresh read would see it.
        hashed = {}
        for row in session.execute(select(*keys, *columns, version, digest.label('row_digest')).where(*conditions,
                keys[0].in_({key[0] for key in wanted}))):
            key = tuple(row[:width])
            if key in wanted:
                hashed[key] = (tuple(row[width:-2]), row[-2], row[-1])
        from services.financial.row_versions import memoisable, own_write_floor
        floor = own_write_floor(session)
        with _DIGESTS_LOCK:
            for key, (values, row_version, value) in hashed.items():
                if not memoisable(row_version, floor):
                    continue  # written by this transaction, which may change it again under the same version
                _DIGESTS[(table, key)] = (row_version, value)
                _DIGESTS.move_to_end((table, key))
            while len(_DIGESTS) > DIGESTS_KEPT:
                _DIGESTS.popitem(last=False)
        found.update({key: (key, values, value) for key, (values, _, value) in hashed.items()})
    # In the order the database returned the rows, as a single query would.
    return [found[key] for key in (tuple(row[:width]) for row in rows) if key in found]


# Per process: (file id, statement key) -> (file row version, digest of the period's saved shared review). The
# statement register's duplicate checks hashed every saved review on each computation (28 MB on d5b330d1, many
# periods twice); a digest is reused while its file's row version is unchanged. Only a read-only caller asks for it
# (row_versions=True), and only in a REPEATABLE READ transaction, where the file rows and their versions come from
# one snapshot.
_REVIEW_DIGESTS = OrderedDict()
REVIEW_DIGESTS_KEPT = 50_000


def load_projection_context(session, case_id, files, *, periods=None, source_ids=None, row_versions=False):
    """Bulk scalar fingerprints; PostgreSQL hashes geometry inside the database.

    ``periods`` ({(file id, statement key)}) and ``source_ids`` limit the batch
    drafts and saved sources fingerprinted to those one guard reads; the values
    are the same as in a whole-file context. ``row_versions`` (a caller that
    writes nothing): each period's saved review is hashed once per computation,
    and reused across computations while its file's row version is unchanged.
    """
    from services.financial.statement_import import VERSION
    files = {str(file.id): file for file in files}
    ids = [file.id for file in files.values()]
    texts = {str(row.evidence_file_id): [row.content_sha256, str(row.engine_job_id), str(row.extracted_at)]
             for row in session.execute(select(EvidenceDocumentText.evidence_file_id,
                 EvidenceDocumentText.content_sha256, EvidenceDocumentText.engine_job_id,
                 EvidenceDocumentText.extracted_at).where(EvidenceDocumentText.evidence_file_id.in_(ids)))} if ids else {}
    geometry = defaultdict(list)
    postgres = session.get_bind().dialect.name == 'postgresql'
    fingerprint = func.md5(cast(EvidenceTableGeometry.payload, String)) if postgres else EvidenceTableGeometry.payload
    if ids and postgres:
        rows = _digested(session, EvidenceTableGeometry, (EvidenceTableGeometry.evidence_file_id, EvidenceTableGeometry.page_number),
            (EvidenceTableGeometry.engine_job_id, EvidenceTableGeometry.extracted_at), fingerprint,
            EvidenceTableGeometry.evidence_file_id.in_(ids))
        for (file_id, page), (job, extracted), value in sorted(rows, key=lambda row: (str(row[0][0]), row[0][1])):
            geometry[str(file_id)].append([page, str(job), str(extracted), value])
    elif ids:
        for file_id, page, job, extracted, value in session.execute(select(
                EvidenceTableGeometry.evidence_file_id, EvidenceTableGeometry.page_number,
                EvidenceTableGeometry.engine_job_id, EvidenceTableGeometry.extracted_at, fingerprint)
                .where(EvidenceTableGeometry.evidence_file_id.in_(ids)).order_by(
                    EvidenceTableGeometry.evidence_file_id, EvidenceTableGeometry.page_number)):
            geometry[str(file_id)].append([page, str(job), str(extracted), value if postgres else _digest(value)])
    drafts = defaultdict(list)
    if ids:
        query = (select(FinancialImportBatchItem.file_id,
                FinancialImportBatchItem.statement_key, FinancialImportBatchItem.review_request)
                .join(FinancialImportBatch, FinancialImportBatch.id == FinancialImportBatchItem.batch_id)
                .where(FinancialImportBatch.case_id == case_id, FinancialImportBatch.status != 'removed',
                    FinancialImportBatchItem.file_id.in_(ids),
                    FinancialImportBatchItem.status.notin_(('removed', 'superseded_reading')),
                    FinancialImportBatchItem.review_request.is_not(None)))
        if periods is not None:
            query = query.where(FinancialImportBatchItem.statement_key.in_({key for _, key in periods}))
        for file_id, key, request in session.execute(query):
            if request is not None and (periods is None or (str(file_id), key) in periods):
                drafts[(str(file_id), key)].append(_digest(request))
    guards = {}
    for identifier, file in files.items():
        metadata = file.metadata_ or {}
        guards[identifier] = _digest(dict(version=VERSION, sha256=file.sha256,
            status=file.status, job=file.engine_job_id, text=texts.get(identifier),
            geometry=geometry[identifier], reading_metadata={key: value for key, value in metadata.items()
                if key.startswith('statement_')}))
    sources = {}
    source_fingerprint = func.md5(cast(FinancialSourceDocument.metadata_, String)) if postgres else FinancialSourceDocument.metadata_
    removal = FinancialSourceDocument.metadata_['financial_import_removal'].as_string()
    conditions = [FinancialSourceDocument.case_id == case_id, FinancialSourceDocument.evidence_file_id.in_(ids)]
    if source_ids is not None:
        conditions.append(FinancialSourceDocument.id.in_([value for value in map(_uuid, source_ids) if value]))
    if ids and source_ids != set() and postgres:
        for (identifier,), (status, removed), value in _digested(session, FinancialSourceDocument,
                (FinancialSourceDocument.id,), (FinancialSourceDocument.status, removal), source_fingerprint, *conditions):
            sources[str(identifier)] = dict(status=status, fingerprint=value, removed=bool(removed))
    elif ids and source_ids != set():
        for identifier, status, value, removed in session.execute(select(FinancialSourceDocument.id,
                FinancialSourceDocument.status, source_fingerprint, removal).where(*conditions)):
            sources[str(identifier)] = dict(status=status, fingerprint=_digest(value), removed=bool(removed))
    context = dict(files=files, guards=guards, drafts=drafts, sources=sources)
    if row_versions:
        context['review_digests'] = {}
        context['file_versions'] = _file_versions(session, files) if postgres else {}
    return context


def _file_versions(session, files):
    """{file id: row version} of files ({id: file}) whose loaded state is that version for good: read in a REPEATABLE
    READ (or SERIALIZABLE) transaction, so the rows and their versions come from one snapshot, not written by this
    transaction, and not changed in this session. Empty otherwise."""
    if not files or session.execute(text('SHOW transaction_isolation')).scalar() not in ('repeatable read', 'serializable'):
        return {}
    from services.financial.row_versions import memoisable, own_write_floor
    floor = own_write_floor(session)
    return {str(identifier): version for identifier, version in session.execute(
        select(EvidenceFile.id, literal_column('evidence_files.xmin::text')).where(EvidenceFile.id.in_(
            [UUID(identifier) for identifier in files])))
        if memoisable(version, floor) and not _modified(files[str(identifier)])}


def _modified(file):
    # Attribute changes only: an in-place change to a JSON value is not seen, so a caller passing row_versions=True
    # must not change file metadata before its guards are computed (the register only reads).
    try:
        return inspect(file).modified
    except Exception:
        return False  # not a mapped object (tests' stand-ins)


def _period_guard(context, file_id, statement_id):
    file = context['files'].get(file_id)
    if file is None:
        return None
    return dict(reading=context['guards'][file_id], shared_review=_review_digest(context, file, file_id, statement_id),
        batch_reviews=sorted(set(context['drafts'][(file_id, statement_id or '')])))


def _review_digest(context, file, file_id, statement_id):
    """Digest of one period's saved shared review: see _REVIEW_DIGESTS."""
    memo = context.get('review_digests')
    key = (file_id, statement_id or '')
    if memo is not None and key in memo:
        return memo[key]
    version = context.get('file_versions', {}).get(file_id)
    if version is not None:
        with _DIGESTS_LOCK:
            known = _REVIEW_DIGESTS.get(key)
        if known is not None and known[0] == version:
            memo[key] = known[1]
            return known[1]
    value = _digest((file.metadata_ or {}).get('financial_review_progress', {}).get(statement_id or ''))
    if memo is not None:
        memo[key] = value
    if version is not None:
        with _DIGESTS_LOCK:
            _REVIEW_DIGESTS[key] = (version, value)
            _REVIEW_DIGESTS.move_to_end(key)
            while len(_REVIEW_DIGESTS) > REVIEW_DIGESTS_KEPT:
                _REVIEW_DIGESTS.popitem(last=False)
    return value


def projection_guard(context, file, statement_id, decision):
    retained = decision.get('retained') or {}
    retained_id = retained.get('evidence_file_id')
    source = context['sources'].get(retained.get('source_document_id'))
    return dict(own=_period_guard(context, str(file.id), statement_id),
        retained=_period_guard(context, retained_id, retained.get('statement_id')) if retained_id else None,
        retained_source=_digest(source) if source else None)


def capture_projection_guard(session, file, statement_id, decision):
    retained = decision.get('retained') or {}
    retained_id = _uuid(retained.get('evidence_file_id'))
    ids = {file.id} | ({retained_id} if retained_id else set())
    files = list(session.scalars(select(EvidenceFile).where(EvidenceFile.case_id == file.case_id,
        EvidenceFile.id.in_(ids))))
    # Only what projection_guard reads: this period, the retained period and
    # the retained saved source (a whole-file context fingerprinted every saved
    # period and batch draft of the file, on every import).
    periods = {(str(file.id), statement_id or '')} | ({(str(retained_id), retained.get('statement_id') or '')} if retained_id else set())
    sources = {str(retained['source_document_id'])} if retained.get('source_document_id') else set()
    return projection_guard(load_projection_context(session, file.case_id, files, periods=periods, source_ids=sources),
                            file, statement_id, decision)


def cached_disposition(context, file, statement_id, *, reading_revision=None):
    previous = (file.metadata_ or {}).get('financial_duplicate_dispositions', {}).get(statement_id or '')
    if not previous:
        return None
    result = deepcopy(previous)
    result.pop('history', None)
    valid = bool(previous.get('projection_guard') and previous['projection_guard'] ==
                 projection_guard(context, file, statement_id, previous))
    if reading_revision and previous.get('reading_revision') != reading_revision:
        valid = False
    retained = previous.get('retained') or {}
    if previous.get('status') == 'ignored':
        target = context['files'].get(retained.get('evidence_file_id'))
        target_metadata = (target.metadata_ or {}) if target else {}
        valid = valid and bool(target) and not target_metadata.get('financial_file_visibility', {}).get('removed')
        valid = valid and not target_metadata.get('financial_import_removal')
        target_decision = target_metadata.get('financial_duplicate_dispositions', {}).get(retained.get('statement_id') or '')
        if target_decision and target_decision.get('status') == 'ignored' and not previous.get('printed_copy'):
            valid = False
        if retained.get('source_document_id'):
            source = context['sources'].get(retained['source_document_id'])
            valid = valid and bool(source and source['status'] == 'admitted' and not source['removed'])
    result['current'] = bool(valid)
    if not valid:
        result.update(status='needs_comparison', label='Compare this statement',
            reason='The reading, saved review or retained source changed. Check these statements again.')
    result.pop('projection_guard', None)
    return result
