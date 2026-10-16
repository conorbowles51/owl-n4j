"""One review queue per case: the statements that need an investigator's decision now.

Read only. Built from the batches' stored readings (the same projection a batch
read uses, ``reading='stored'``): nothing is re-read from a PDF, nothing is
written, and nothing is admitted. It regroups what the batches already hold so
that every statement appears once:

* a statement is identified by its file's bytes (sha256) and its statement key,
  so the same statement prepared in several batches, or in two uploads of the
  same PDF, is one entry;
* anything saved (imported, or being saved) is never queue work;
* copies the system set aside, and possible copies that need a comparison, are
  counted under copies and listed separately, never in the queue;
* a statement whose problems are all notes (an overlap of dates, a balance
  comparison that could not be made, a background update) is not work;
* every queue entry carries at least one actionable problem, and the plain
  sentence that names it, before it is opened.

The per-case status line (imported, waiting, copies, couldn't read) is counted
from the same classification, so it always agrees with the queue.
"""
import threading
import time
from collections import OrderedDict
from copy import deepcopy
from types import SimpleNamespace
from uuid import UUID

from sqlalchemy import select

from postgres.models.evidence import EvidenceFile
from postgres.models.financial_import_batches import FinancialImportBatch as Batch, FinancialImportBatchItem as Item

# Review reasons that never ask the investigator for anything.
NOTE_REASONS = frozenset({'overlap', 'balance_unavailable', 'readiness_update', 'duplicate'})
# Problem kinds raised by the system about itself (a comparison or update it
# could not finish). They hold a statement but give the investigator nothing
# to fix; the statement is counted as being rechecked.
SYSTEM_KINDS = frozenset({'readiness_pending', 'coverage_load'})
# Most important first: the reason a statement is opened for.
REASON_ORDER = ('import_failed', 'saved_review', 'reprint', 'assignment', 'currency', 'institution', 'holder',
                'account', 'dates', 'balance', 'incomplete', 'count', 'no_activity', 'reading')
# The one control a single-field issue opens on (the field its sentence names).
DETAIL_FIELDS = {'holder': 'holder', 'account': 'account_number', 'dates': 'period', 'currency': 'currency',
                 'institution': 'institution'}
BUCKETS = ('imported', 'saving', 'waiting', 'reader_fix', 'filled', 'ready', 'copies', 'unreadable', 'rechecking', 'left_unimported',
           'assigned', 'unexplained')


def actionable_problems(summary):
    """Problems on a projected summary that ask the investigator to do something."""
    from services.financial.batch_review_summary import reason
    result = []
    for problem in summary.get('problems') or []:
        if not (problem.get('message') or '').strip() or problem.get('kind') in SYSTEM_KINDS:
            continue
        key = 'import_failed' if summary.get('import_failed') else (problem.get('review_reason') or reason(problem))
        if key in NOTE_REASONS:
            continue
        result.append({**problem, 'review_reason': key})
    return result


def _money(minor, currency):
    try:
        value = int(str(minor).lstrip('-'))
    except (TypeError, ValueError):
        return None
    exponent = 2
    try:
        from services.financial.money import get_currency
        exponent = get_currency(currency).exponent if currency else 2
    except Exception:
        exponent = 2
    whole, part = divmod(value, 10 ** exponent) if exponent else (value, 0)
    text = f'{whole:,}' + (f'.{part:0{exponent}d}' if exponent else '')
    return f'{text} {currency}'.strip() if currency else text


def _pages(problems):
    pages = sorted({p['page'] for p in problems if isinstance(p.get('page'), int)})
    if not pages:
        return ''
    if len(pages) == 1:
        return f' on page {pages[0]}'
    if len(pages) <= 3:
        return ' on pages ' + ', '.join(map(str, pages[:-1])) + f' and {pages[-1]}'
    return f' on {len(pages)} pages'


def _rows(problems):
    return len({p['row_id'] for p in problems if p.get('row_id')})


def issue_sentence(reason, problems, summary):
    """One plain sentence naming the problem, for the queue entry before it is opened."""
    rows = _rows(problems)
    where = _pages(problems)
    plural = lambda n, one, many: f'{n} {one if n == 1 else many}'
    carried = next((p for p in problems if p.get('kind') == 'carry_conflict'), None)
    if carried:
        return carried['message']
    if reason == 'import_failed':
        return 'Saving did not finish: open it to retry'
    if reason == 'saved_review':
        return 'Your earlier corrections need comparing with a new reading'
    if reason == 'reprint':
        return 'This statement is printed twice in the file and the copies differ: choose one'
    if reason == 'assignment':
        return 'Payments need an account: choose where they belong'
    if reason == 'currency':
        return 'Currency not printed: choose one'
    if reason == 'institution':
        return 'Bank name not found: enter it'
    if reason == 'holder':
        return 'Account holder not found: enter it'
    if reason == 'account':
        return 'Account number not found: enter it'
    if reason == 'dates':
        return 'Statement dates not found: enter them'
    if reason == 'balance':
        currency = summary.get('currency') or ''
        closing = next((p for p in problems if p.get('check') == 'closing_balance'), None)
        if closing and _money(closing.get('difference_minor'), currency):
            return f'Closing balance off by {_money(closing["difference_minor"], currency)}'
        if any(p.get('kind') == 'arithmetic' and 'opening and one closing balance' in (p.get('message') or '')
               for p in problems):
            return 'Opening or closing balance not read: enter both from the statement'
        running = [p for p in problems if p.get('check') == 'running_balance'
                   or 'running balance' in (p.get('message') or '').lower()]
        if running:
            n = _rows(running) or len(running)
            return f'{plural(n, "printed balance does", "printed balances do")} not add up{_pages(running)}'
        totals = [p for p in problems if p.get('check') in ('credit_total', 'debit_total', 'fee_total', 'interest_total')]
        if totals:
            return f'A printed total does not agree with the payments{_pages(totals)}'
        return 'Balances do not add up: compare with the PDF'
    if reason == 'incomplete':
        count = rows or len(problems)
        return f'{plural(count, "record is", "records are")} missing a value{where}'
    if reason == 'count':
        return 'The printed number of payments does not match: some rows may be missing'
    if reason == 'no_activity':
        return 'No payments were read: confirm the period had none'
    count = rows or len(problems)
    if rows:
        return f'{plural(count, "row", "rows")} unreadable{where}'
    return problems[0]['message'] if len(problems) == 1 else f'{plural(count, "reading", "readings")} to check{where}'


def describe(summary):
    """(reason, sentence, target row, target field, page, other problem count) for an actionable item."""
    problems = actionable_problems(summary)
    if not problems:
        return None
    by_reason = {}
    for problem in problems:
        by_reason.setdefault(problem['review_reason'], []).append(problem)
    reason = next((key for key in REASON_ORDER if key in by_reason), next(iter(by_reason)))
    chosen = by_reason[reason]
    row = next((p['row_id'] for p in chosen if p.get('row_id')), None)
    page = next((p['page'] for p in chosen if isinstance(p.get('page'), int)), None) or summary.get('page_number')
    field = DETAIL_FIELDS.get(reason)
    others = len(problems) - len(chosen) + max(0, (summary.get('problem_count') or 0) - len(summary.get('problems') or []))
    ordered = [key for key in REASON_ORDER if key in by_reason] + [key for key in by_reason if key not in REASON_ORDER]
    # Every other blocker, in plain words: fixing the stated issue alone must
    # never look like the end of the work when more remains.
    if 'currency' in by_reason:
        # The reader stops at the currency question: a statement waiting for
        # its currency is not checked further, so its unread identity is named
        # too, and a currency choice alone is never presented as the last step.
        for key, value in (('institution', 'institution'), ('holder', 'holder'), ('account', 'account')):
            if key not in ordered and not str(summary.get(value) or '').strip():
                ordered.append(key)
                by_reason[key] = []
    also = [issue_sentence(key, by_reason[key], summary) for key in ordered if key != reason]
    choice = next(({key: p[key] for key in ('field', 'yours', 'reading')} for p in chosen if p.get('kind') == 'carry_conflict'), None)
    return dict(reason=reason, sentence=issue_sentence(reason, chosen, summary), row_id=row, field=field,
                page=page, other_problems=others, problem_total=len(problems), reasons=ordered, also=also,
                **(dict(choice=choice) if choice else {}))


def _empty_reading(summary):
    return not (summary.get('transaction_count') or summary.get('record_count') or summary.get('incomplete_count')
                or summary.get('unclassified_count') or summary.get('period_start') or summary.get('period_end'))


def classify(item):
    """Queue bucket of one projected (stored-reading) batch item."""
    from services.financial.batch_review_summary import is_duplicate_review
    summary = item.summary
    if item.status == 'imported':
        return 'imported'
    if item.status == 'pending_import':
        return 'saving'
    if item.status == 'skipped':
        return 'left_unimported'
    if item.status == 'assigned':
        return 'assigned'
    if item.status not in ('ready', 'attention') or is_duplicate_review(item):
        return 'copies' if item.status == 'duplicate_ignored' or is_duplicate_review(item) else 'unexplained'
    if summary.get('readiness_pending') or summary.get('comparison_pending'):
        return 'rechecking'
    if actionable_problems(summary):
        return 'unreadable' if _empty_reading(summary) and not summary.get('assignment_only') else 'waiting'
    if summary.get('can_import', item.status == 'ready'):
        return 'ready'
    if any(p.get('kind') in SYSTEM_KINDS for p in summary.get('problems') or []):
        return 'rechecking'
    if _empty_reading(summary):
        return 'unreadable'
    # Held, yet no problem says why: the state the investigator could open and
    # find nothing to do. Counted so it is never silent; never queued.
    return 'unexplained'


def _saved_scopes(session, case_id):
    """(file bytes, statement key) of every saved statement, including replaced scopes."""
    from postgres.models.financial import FinancialSourceDocument as Source
    columns = (Source.id, Source.sha256_at_ingestion, Source.metadata_['statement_import_statement_id'].as_string(),
               Source.metadata_['statement_recovery_parent_id'].as_string(),
               Source.metadata_['financial_import_removal'].as_string(), Source.evidence_file_id)
    postgres = session.get_bind().dialect.name == 'postgresql'

    def read(*conditions):
        if not postgres:
            return session.execute(select(*columns).where(*conditions)).all()
        # The three metadata fields sit inside each record's large saved
        # reading; read them again only for records changed since last time.
        from sqlalchemy import func
        from services.financial.pending_duplicate_projection import _digested
        return [(identifier, sha, *fields, file_id) for (identifier,), (sha, file_id), fields in _digested(session, Source,
            (Source.id,), (Source.sha256_at_ingestion, Source.evidence_file_id), func.jsonb_build_array(*columns[2:5]),
            *conditions, kind='saved_scopes')]

    rows = read(Source.case_id == case_id, Source.status == 'admitted', Source.document_type == 'statement_review')
    current = {}
    for _, sha, key, _, removed, file_id in rows:
        if not removed:
            current.setdefault((sha, key or ''), file_id)
    scopes = set(current)
    parents, seen = {parent for _, _, _, parent, removed, _ in rows if parent and not removed}, set()
    while parents - seen:
        current = parents - seen
        seen |= current
        parents = set()
        ids = []
        for value in current:
            try:
                ids.append(UUID(value))
            except ValueError:
                continue
        for _, sha, key, parent, _, _ in read(Source.case_id == case_id, Source.id.in_(ids)):
            scopes.add((sha, key or ''))
            if parent:
                parents.add(parent)
    return scopes, current


def _proposals(summary, knowledge, detail):
    """Proposals for a waiting statement's missing details; True when they resolve every problem."""
    from services.financial import field_proposals
    proposals = field_proposals.propose(field_proposals.summary_values(summary), knowledge)
    if not proposals:
        return {}, False
    reasons = {p['review_reason'] for p in actionable_problems(summary)}
    text = field_proposals.sentence(detail['reason'], proposals) if detail else None
    if text:
        detail['sentence'] = text
    return proposals, field_proposals.resolves_all(reasons, proposals)


def _entry(item, batch_id, describe_result=None):
    summary = item.summary
    entry = dict(id=str(item.id), batch_id=str(batch_id), file_id=str(item.file_id),
        source_id=summary.get('source_id') or str(item.file_id), statement_id=item.statement_key or None,
        filename=summary.get('filename') or 'Source unavailable', holder=summary.get('holder') or '',
        account=summary.get('account') or '', institution=summary.get('institution') or '',
        currency=summary.get('currency') or '', period_start=summary.get('period_start') or '',
        period_end=summary.get('period_end') or '', page=summary.get('page_number'),
        can_import=bool(summary.get('can_import')), status=item.status)
    if describe_result:
        entry.update(issue=describe_result['sentence'], issue_reason=describe_result['reason'],
            row_id=describe_result['row_id'], field=describe_result['field'], page=describe_result['page'],
            other_problems=describe_result['other_problems'], problem_total=describe_result['problem_total'],
            reasons=describe_result.get('reasons') or [describe_result['reason']], also=describe_result.get('also') or [])
        if describe_result.get('choice'):
            entry['choice'] = describe_result['choice']
    return entry


def _build(session, case_id):
    batches = {batch.id: batch for batch in session.scalars(select(Batch).where(
        Batch.case_id == case_id, Batch.status != 'removed'))}
    # Identity columns first; whole items (their stored summaries) are loaded
    # only for the one preparation that stands for each statement.
    light = [SimpleNamespace(id=row[0], batch_id=row[1], file_id=row[2], statement_key=row[3], status=row[4])
             for row in session.execute(select(Item.id, Item.batch_id, Item.file_id, Item.statement_key, Item.status)
                 .where(Item.batch_id.in_(list(batches)), Item.status.notin_(('removed', 'superseded_reading'))))] if batches else []
    files = {row[0]: row for row in session.execute(select(EvidenceFile.id, EvidenceFile.sha256,
        EvidenceFile.original_filename).where(EvidenceFile.case_id == case_id,
        EvidenceFile.id.in_({item.file_id for item in light})))} if light else {}
    sources = {}
    for batch in batches.values():
        for file in batch.files or []:
            if file.get('file_id') and file.get('source_id'):
                sources.setdefault(file['file_id'], set()).add(file['source_id'])
    saved, current_saved = _saved_scopes(session, case_id)
    # A statement is its original PDF (every reading of it) and its statement
    # key. A second upload of the same bytes is a different file: the copy
    # review decides about it, so it stays a separate (copy) entry.
    identities = OrderedDict()
    for item in sorted(light, key=lambda i: (batches[i.batch_id].created_at, str(i.batch_id), str(i.id))):
        if item.file_id not in files:
            continue
        root = min(sources.get(str(item.file_id)) or {str(item.file_id)})
        identities.setdefault((root, item.statement_key or ''), []).append(item)
    shas = {identity: {files[i.file_id][1] for i in group} for identity, group in identities.items()}
    chosen, decided = {}, {}
    for identity, group in identities.items():
        if any((sha, identity[1]) in saved for sha in shas[identity]) or any(i.status == 'imported' for i in group):
            decided[identity] = ('imported', next((i for i in group if i.status == 'imported'), group[-1]))
        elif any(i.status == 'pending_import' for i in group):
            decided[identity] = ('saving', next(i for i in group if i.status == 'pending_import'))
        elif any(i.status == 'skipped' for i in group):
            decided[identity] = ('left_unimported', next(i for i in group if i.status == 'skipped'))
        else:
            # The newest batch's preparation stands for the statement.
            chosen[identity] = group[-1]
    wanted = [i.id for i in chosen.values()] + [i.id for _, i in decided.values()]
    full = {}
    for start in range(0, len(wanted), 2000):
        full.update({item.id: item for item in session.scalars(select(Item).where(Item.id.in_(wanted[start:start + 2000])))})
    from services.financial.import_batches import checked_batch_items
    representatives = {identity: full[item.id] for identity, item in chosen.items() if item.id in full}
    projected = {p.id: p for p in checked_batch_items(session, case_id, list(representatives.values()))}
    rows = []
    for identity, (bucket, item) in decided.items():
        if item.id in full:
            rows.append((identity, bucket, full[item.id], None, None))
    from services.financial import field_proposals
    knowledge = []  # loaded once, only when a waiting statement lacks a detail
    for identity, item in representatives.items():
        current = projected.get(item.id)
        if current is None:
            continue
        bucket = classify(current)
        detail = describe(current.summary) if bucket in ('waiting', 'unreadable') else None
        if bucket == 'unreadable':
            page = current.summary.get('page_number')
            detail = dict(detail or dict(row_id=None, field=None, other_problems=0, problem_total=0),
                reason='unreadable', page=page, sentence='Nothing could be read from this statement'
                + (f' (page {page})' if isinstance(page, int) else '') + ': check its pages in the PDF')
        proposals = None
        if bucket == 'waiting' and field_proposals.enabled_fields():
            if not knowledge:
                knowledge.append(field_proposals.case_knowledge(session, case_id))
            proposals, resolved = _proposals(current.summary, knowledge[0], detail)
            if resolved:
                # Every problem is a detail the case establishes exactly: not
                # work for the investigator. Saved only by the queue's save,
                # which applies the values and checks the statement again.
                bucket = 'filled'
        rows.append((identity, bucket, current, detail, proposals))
    items = light
    batch_of = {item.id: item.batch_id for item in items}
    result = []
    # Statements saved outside any batch (an individual review) are imported too.
    known = {(sha, identity[1]) for identity, values in shas.items() for sha in values}
    outside = {scope: file_id for scope, file_id in current_saved.items() if scope not in known}
    names = dict(session.execute(select(EvidenceFile.id, EvidenceFile.original_filename).where(
        EvidenceFile.case_id == case_id, EvidenceFile.id.in_(set(outside.values())))).all()) if outside else {}
    for (sha, key), file_id in outside.items():
        result.append(dict(id=f'saved:{file_id}:{key}', batch_id=None, file_id=str(file_id), source_id=str(file_id),
            statement_id=key or None, filename=names.get(file_id) or 'Source unavailable', holder='', account='',
            institution='', currency='', period_start='', period_end='', page=None, can_import=False,
            status='imported', bucket='imported', root=f'saved:{sha}', file_ids=[str(file_id)]))
    for identity, bucket, item, detail, proposals in rows:
        entry = _entry(item, batch_of[item.id], detail)
        if proposals:
            entry['proposals'] = proposals
            # A one-click fix is claimed only when that click leaves nothing
            # else: the proposal covers the statement's one and only blocker.
            single = entry.get('reasons') or []
            entry['fix_makes_ready'] = len(single) == 1 and any(
                field_proposals.REASONS.get(name) == single[0] for name in proposals)
        entry.update(bucket=bucket, root=identity[0], file_ids=sorted({str(i.file_id) for i in identities[identity]}
            | {source for i in identities[identity] for source in sources.get(str(i.file_id), ())}))
        if bucket == 'copies':
            disposition = item.summary.get('duplicate_disposition') or {}
            retained = disposition.get('retained') or {}
            entry.update(copy_of=retained.get('filename') or None,
                set_aside=item.status == 'duplicate_ignored')
        result.append(entry)
    # Statement order inside its file, so an entry can say "statement 12 of 54".
    by_file = {}
    for entry in result:
        by_file.setdefault(entry['root'], []).append(entry)
    for group in by_file.values():
        group.sort(key=lambda e: (e['period_start'], e['period_end'], e['statement_id'] or ''))
        for index, entry in enumerate(group, 1):
            entry.update(file_position=index, file_statements=len(group))
    reader_collapse(result)
    result.sort(key=lambda e: (e['filename'], e['account'], e['period_start'], e['id']))
    return result


# A file the reader cannot handle yet: most of its statements are blocked by
# reading or identity problems and none would be ready after one field fix.
# Its blocked statements leave "Waiting for you" as one file entry ("Waiting
# for a reader fix"); nothing is changed or hidden, they stay listed under it.
READER_REASONS = frozenset({'reading', 'incomplete', 'count', 'unreadable',
                            'holder', 'account', 'institution', 'dates'})
SINGLE_FIELD_REASONS = frozenset({'currency', 'institution', 'holder', 'account', 'dates', 'no_activity'})
READER_MIN_STATEMENTS = 5
READER_SHARE = 0.5


def _reader_blocked(entry):
    return entry['bucket'] == 'unreadable' or (entry['bucket'] == 'waiting' and bool(
        set(entry.get('reasons') or [entry.get('issue_reason')]) & READER_REASONS))


def _single_fix(entry):
    reasons = entry.get('reasons') or []
    return entry['bucket'] in ('waiting', 'filled') and len(reasons) == 1 and reasons[0] in SINGLE_FIELD_REASONS


def reader_collapse(entries):
    """Move the blocked waiting statements of files the reader cannot handle yet to 'reader_fix'. In place."""
    by_file = {}
    for entry in entries:
        if entry['bucket'] != 'copies':
            by_file.setdefault(entry['root'], []).append(entry)
    for group in by_file.values():
        blocked = [e for e in group if _reader_blocked(e)]
        if (len(group) >= READER_MIN_STATEMENTS and len(blocked) >= READER_SHARE * len(group)
                and not any(_single_fix(e) for e in group)):
            for entry in blocked:
                entry['reader_file'] = True
                if entry['bucket'] == 'waiting':
                    entry['bucket'] = 'reader_fix'
    return entries


def reader_files(entries):
    """One line per file waiting for a reader fix."""
    files = OrderedDict()
    for entry in entries:
        if entry['bucket'] != 'reader_fix':
            continue
        line = files.setdefault(entry['root'], dict(file_id=entry['file_id'], filename=entry['filename'],
            batch_id=entry['batch_id'], statements=0, file_statements=entry.get('file_statements', 0), item_ids=[]))
        line['statements'] += 1
        line['item_ids'].append(entry['id'])
    for line in files.values():
        n = line['statements']
        line['message'] = (f"Loupe can't read this file reliably yet ({n} statement{'s' if n != 1 else ''}). No need to "
                           "review it by hand; it will be re-read when the reader is fixed.")
    return list(files.values())


_CACHE_SIZE = 16
_cache = OrderedDict()
_lock = threading.Lock()


# Precompute on write: cases whose queue was read recently are rebuilt in the
# background (batch loop sweep) after their fingerprint changes, so the next
# open is a cache hit. One switch.
PREWARM = True
PREWARM_MAX_AGE = 15 * 60
_recent_reads = OrderedDict()


def prewarm(factory, *, budget_seconds=20.0, now=None):
    """Rebuild the cached queue of recently read cases whose inputs changed. Returns the cases rebuilt."""
    from services.financial.statement_file_status import status_fingerprint
    if not PREWARM:
        return []
    now = time.monotonic() if now is None else now
    started, rebuilt = time.monotonic(), []
    with _lock:
        for key, seen in list(_recent_reads.items()):
            if now - seen > PREWARM_MAX_AGE:
                _recent_reads.pop(key, None)
        cases = sorted(_recent_reads, key=lambda key: -_recent_reads[key])
    for key in cases:
        if time.monotonic() - started >= budget_seconds:
            break
        with factory() as session:
            try:
                fingerprint = status_fingerprint(session, UUID(key))
                with _lock:
                    hit = _cache.get(key)
                if fingerprint is None or (hit and hit[0] == fingerprint):
                    continue
                _entries(session, UUID(key), note=False)
                rebuilt.append(key)
            finally:
                session.rollback()
    return rebuilt


def _entries(session, case_id, use_cache=True, note=True):
    """(queue entries, unread statement files) for the case, reused while its rows are unchanged."""
    from services.financial.statement_file_status import status_fingerprint
    from services.financial.auto_read import unread_statement_files
    fingerprint = status_fingerprint(session, case_id) if use_cache else None
    key = str(case_id)
    if fingerprint is not None and note:
        with _lock:
            _recent_reads[key] = time.monotonic()
            _recent_reads.move_to_end(key)
            while len(_recent_reads) > _CACHE_SIZE:
                _recent_reads.popitem(last=False)
    if fingerprint is not None:
        with _lock:
            hit = _cache.get(key)
            if hit and hit[0] == fingerprint:
                _cache.move_to_end(key)
                return deepcopy(hit[1]), hit[2]
    entries = _build(session, case_id)
    unread = len(unread_statement_files(session, case_id=case_id))
    if fingerprint is not None:
        with _lock:
            _cache[key] = (fingerprint, deepcopy(entries), unread)
            _cache.move_to_end(key)
            while len(_cache) > _CACHE_SIZE:
                _cache.popitem(last=False)
    return entries, unread


def _counts(entries):
    counts = {bucket: 0 for bucket in BUCKETS}
    for entry in entries:
        counts[entry['bucket']] += 1
    return counts


def _failed_files(session, case_id, file_filter):
    """Files a batch could not prepare and that have no statement at all."""
    prepared = set(session.scalars(select(Item.file_id).join(Batch, Batch.id == Item.batch_id).where(
        Batch.case_id == case_id, Batch.status != 'removed', Item.status != 'removed')))
    failed = {}
    for batch in session.scalars(select(Batch).where(Batch.case_id == case_id, Batch.status != 'removed')
            .order_by(Batch.created_at)):
        for file in batch.files or []:
            ids = {file.get('file_id'), file.get('source_id')} - {None}
            if file_filter and not ids & file_filter:
                continue
            if any(UUID(i) in prepared for i in ids if _uuid(i)):
                failed.pop(file.get('source_id'), None)
                continue
            if file.get('status') == 'error':
                failed[file.get('source_id')] = dict(batch_id=str(batch.id), source_id=file.get('source_id'),
                    file_id=file.get('file_id'), filename=file.get('filename') or 'Source unavailable',
                    message=file.get('error') or 'This file could not be prepared.')
            else:
                failed.pop(file.get('source_id'), None)
    return list(failed.values())


def _set_aside_read_copies(session, case_id, entries, failed):
    """Move failed readings of a file that another upload of the same bytes read into copies.

    A second upload of the same bytes reaches the copy review only through its
    own statements. When its reading failed (an older reader, a removed import's
    lost source) it would stay under "Couldn't read" for good although the same
    PDF was read through another upload. Such entries are set aside, linked to
    the upload that was read. Nothing is written; if that upload also could not
    read a statement, its own entry still says so.
    """
    read = {e['file_id'] for e in entries if e['bucket'] not in ('unreadable', 'unexplained')}
    failed_ids = {f.get('file_id') or f.get('source_id') for f in failed}
    wanted = {e['file_id'] for e in entries if e['bucket'] == 'unreadable'} | failed_ids
    if not read or not wanted:
        return entries, failed, []
    ids = {UUID(i) for i in read | wanted if i and _uuid(i)}
    files = {str(row[0]): (row[1], row[2]) for row in session.execute(select(
        EvidenceFile.id, EvidenceFile.sha256, EvidenceFile.original_filename).where(
        EvidenceFile.case_id == case_id, EvidenceFile.id.in_(ids)))}
    read_by_sha = {}
    for file_id in sorted(read):
        sha, name = files.get(file_id, (None, None))
        if sha:
            read_by_sha.setdefault(sha, (file_id, name))

    def copy_of(file_id):
        sha = files.get(file_id, (None, None))[0]
        match = read_by_sha.get(sha) if sha else None
        return match if match and match[0] != file_id else None

    for entry in entries:
        match = copy_of(entry['file_id']) if entry['bucket'] == 'unreadable' else None
        if match:
            entry.update(bucket='copies', set_aside=True, copy_of=match[1] or None,
                         copy_reason='same_file_read', copy_file_id=match[0])
    kept, copies = [], []
    for file in failed:
        match = copy_of(file.get('file_id') or file.get('source_id'))
        if match:
            copies.append(dict(file, copy_of=match[1] or None, copy_file_id=match[0]))
        else:
            kept.append(file)
    return entries, kept, copies


def _uuid(value):
    try:
        UUID(str(value))
        return True
    except ValueError:
        return False


def case_review_queue(session, *, case_id, file_ids=None, use_cache=True):
    """The case's queue and status line, optionally limited to some files (evidence ids)."""
    from services.financial.auto_read import reading_progress
    started = time.perf_counter()
    entries, unread = _entries(session, case_id, use_cache=use_cache)
    # Live (not cached): files being read or prepared, for "Reading 12 of 40 files".
    reading = dict(reading_progress(session, case_id=case_id), unread_statement_files=unread)
    file_filter = {str(i) for i in file_ids or []}
    # Decided over the whole case: the upload that was read may be outside the filter.
    entries, failed, copy_files = _set_aside_read_copies(session, case_id, entries, _failed_files(session, case_id, set()))
    if file_filter:
        entries = [e for e in entries if file_filter & set(e['file_ids'])]
        within = lambda f: bool({f.get('file_id'), f.get('source_id')} & file_filter)
        failed, copy_files = [f for f in failed if within(f)], [f for f in copy_files if within(f)]
    counts = _counts(entries)
    counts['unreadable_files'] = len(failed)
    counts['copies'] += len(copy_files)
    counts['copy_files'] = len(copy_files)
    waiting_for_reader = reader_files(entries)
    for entry in entries:
        entry.pop('root', None)
    pick = lambda bucket: [e for e in entries if e['bucket'] == bucket]
    ready_batches = {}
    for entry in pick('ready'):
        ready_batches[entry['batch_id']] = ready_batches.get(entry['batch_id'], 0) + 1
    return dict(case_id=str(case_id), file_ids=sorted(file_filter), counts=counts,
        status_line=status_line(counts, reading), reading=reading, items=pick('waiting'), copies=pick('copies'),
        unreadable=pick('unreadable'), unreadable_files=failed, copy_files=copy_files, rechecking=pick('rechecking'),
        unexplained=pick('unexplained'), ready=pick('ready'), filled=pick('filled'),
        reader_fix=pick('reader_fix'), reader_files=waiting_for_reader,
        ready_batches=[dict(batch_id=key, statements=value) for key, value in
                       sorted(ready_batches.items(), key=lambda pair: -pair[1])],
        elapsed_ms=round((time.perf_counter() - started) * 1000))


def reading_sentence(reading):
    """'Reading 12 of 40 files…' while statement files are being read or prepared, else ''."""
    if not reading:
        return ''
    total = reading.get('files_total', 0) + reading.get('files_waiting_to_start', 0)
    if not reading.get('files_reading') and not reading.get('files_waiting_to_start'):
        return ''
    done = reading.get('files_done', 0)
    if reading.get('paused'):
        return f'Reading paused at {done} of {total} files'
    return f'Reading {min(done + 1, total)} of {total} files…'


def status_line(counts, reading=None):
    """The plain per-case status line. Every number is a count of the queue's own buckets."""
    parts = [f"Imported {counts['imported']} statements", f"Waiting for you {counts['waiting']}",
             f"Copies set aside {counts['copies']}", f"Couldn't read {counts['unreadable'] + counts['unreadable_files']}"]
    if counts['ready']:
        parts.insert(2, f"Ready to import {counts['ready']}")
    if counts.get('reader_fix'):
        parts.insert(2, f"Waiting for a reader fix {counts['reader_fix']}")
    if counts.get('filled'):
        parts.insert(2, f"Details filled automatically {counts['filled']}")
    if counts['saving']:
        parts.append(f"Importing now {counts['saving']}")
    if counts['rechecking']:
        parts.append(f"Being rechecked {counts['rechecking']}")
    if counts['left_unimported']:
        parts.append(f"Left out by you {counts['left_unimported']}")
    sentence = reading_sentence(reading)
    if sentence:
        parts.insert(0, sentence)
    return ' · '.join(parts)


def case_status(session, *, case_id):
    """Counts only, for the cross-case view."""
    queue = case_review_queue(session, case_id=case_id)
    return dict(case_id=queue['case_id'], counts=queue['counts'], status_line=queue['status_line'],
                reading=queue['reading'], elapsed_ms=queue['elapsed_ms'])
