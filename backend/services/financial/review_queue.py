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
import os
import threading
import time
from collections import OrderedDict
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
# A credit line printing only its principal balance (principal_only) cannot be checked whatever details are
# filled in, so its missing amount owed leads, ahead of the details a person can fill for it.
REASON_ORDER = ('import_failed', 'pages_missing', 'saved_review', 'reprint', 'assignment', 'principal_only', 'currency', 'institution',
                'holder', 'account', 'dates', 'balance', 'incomplete', 'count', 'no_activity', 'reading')
# The one control a single-field issue opens on (the field its sentence names).
DETAIL_FIELDS = {'holder': 'holder', 'account': 'account_number', 'dates': 'period', 'currency': 'currency',
                 'institution': 'institution'}
BUCKETS = ('imported', 'saving', 'waiting', 'reader_fix', 'filled', 'ready', 'copies', 'unreadable', 'rechecking', 'left_unimported',
           'assigned', 'unexplained', 'not_payment')


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
    if reason == 'pages_missing':
        return problems[0]['message']
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
    if reason == 'principal_only':
        page = next((p['page'] for p in problems if isinstance(p.get('page'), int)), None)
        return ('The statement prints only the principal balance; the opening amount owed is not printed'
                + (f' on page {page}' if page else ''))
    if reason == 'balance':
        currency = summary.get('currency') or ''
        closing = next((p for p in problems if p.get('check') == 'closing_balance'), None)
        if closing and _money(closing.get('difference_minor'), currency):
            return f'Closing balance off by {_money(closing["difference_minor"], currency)}'
        if any(p.get('kind') == 'arithmetic' and 'opening and one closing balance' in (p.get('message') or '')
               for p in problems):
            # Name what is actually missing: the check is unavailable when a balance or a payment amount
            # is unread, and a statement with both balances read waits for its payments, not its balances.
            check = next((c for c in summary.get('checks') or []
                          if isinstance(c, dict) and c.get('kind') == 'closing_balance'), None) or {}
            opening, closing = check.get('opening_minor') is not None, check.get('printed_minor') is not None
            unread = [p for p in summary.get('problems') or [] if p.get('row_id') and p.get('kind') != 'arithmetic']
            if check and opening and closing and unread:
                n = _rows(unread)
                return f'Both balances read; {plural(n, "payment", "payments")} could not be read{_pages(unread)}'
            if check and opening and not closing:
                return 'Closing balance not read: enter it from the statement'
            if check and closing and not opening:
                return 'Opening balance not read: enter it from the statement'
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
        return _hold_detail(summary)
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
                # For the queue's plain instructions: every page the issue is on, and what the checks said.
                pages=sorted({p['page'] for p in chosen if isinstance(p.get('page'), int)}),
                messages=[p['message'] for p in chosen[:3]],
                **(dict(choice=choice) if choice else {}))


def _hold_detail(summary):
    """The queue entry of a balanced statement the System would not save on its own (auto_save_guard)."""
    hold = summary.get('auto_save_hold')
    if not hold:
        return None
    field = DETAIL_FIELDS.get(hold.get('reason'))
    return dict(reason='auto_save_check', sentence=hold['sentence'], row_id=None, field=field,
                page=summary.get('page_number'), other_problems=0, problem_total=1, reasons=['auto_save_check'],
                also=[], pages=[], messages=[hold['sentence']])


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
    if item.status == 'attention' and summary.get('not_payment_statement'):
        # A fund statement set aside as not a payment statement (not_payment_statements).
        return 'not_payment'
    if item.status not in ('ready', 'attention') or is_duplicate_review(item):
        return 'copies' if item.status == 'duplicate_ignored' or is_duplicate_review(item) else 'unexplained'
    if summary.get('readiness_pending') or summary.get('comparison_pending'):
        return 'rechecking'
    if actionable_problems(summary):
        return 'unreadable' if _empty_reading(summary) and not summary.get('assignment_only') else 'waiting'
    if summary.get('auto_save_hold'):
        # Balanced, but a fact the balances cannot prove is not: a person checks it (auto_save_guard).
        return 'waiting'
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
    # An empty legacy import (no statement, no dates, nothing paid) saved nothing of any statement of its
    # bytes (saved_reading_replacement, lesson 13).
    from services.financial.saved_reading_replacement import standing_shell_ids
    shells = standing_shell_ids(session, case_id)
    current = {}
    for identifier, sha, key, _, removed, file_id in rows:
        if not removed and str(identifier) not in shells:
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
    values = field_proposals.summary_values(summary)
    proposals = field_proposals.propose(values, knowledge)
    reasons = {p['review_reason'] for p in actionable_problems(summary)}
    if detail is not None and 'currency' in reasons and 'currency' in field_proposals.enabled_fields():
        # Why the currency stays a person's question, in plain words (empty once it is settled automatically).
        headline, why = field_proposals.currency_why(values, knowledge, proposals.get('currency'))
        if why:
            detail['why'] = why
            if detail.get('reason') == 'currency':
                detail['sentence'] = headline
    if not proposals:
        return {}, False
    text = field_proposals.sentence(detail['reason'], proposals) if detail else None
    if text and not (detail.get('reason') == 'currency' and detail.get('why')):
        detail['sentence'] = text
    return proposals, field_proposals.resolves_all(reasons, proposals)


def _printed_balances(summary):
    """The stored opening and closing balances (minor units, as read) and payment count, so a
    queue row can be checked against the PDF without opening it. Read only: nothing is decided here."""
    closing = next((check for check in summary.get('checks') or []
                    if isinstance(check, dict) and check.get('kind') == 'closing_balance'), None) or {}
    return dict(opening_minor=closing.get('opening_minor'), closing_minor=closing.get('printed_minor'),
                balance_status=summary.get('balance_status') or '', transaction_count=summary.get('transaction_count'))


def _entry(item, batch_id, describe_result=None):
    summary = item.summary
    entry = dict(id=str(item.id), batch_id=str(batch_id), file_id=str(item.file_id),
        source_id=summary.get('source_id') or str(item.file_id), statement_id=item.statement_key or None,
        filename=summary.get('filename') or 'Source unavailable', holder=summary.get('holder') or '',
        account=summary.get('account') or '', institution=summary.get('institution') or '',
        currency=summary.get('currency') or '', period_start=summary.get('period_start') or '',
        period_end=summary.get('period_end') or '', page=summary.get('page_number'),
        can_import=bool(summary.get('can_import')), status=item.status, **_printed_balances(summary))
    if describe_result:
        entry.update(issue=describe_result['sentence'], issue_reason=describe_result['reason'],
            row_id=describe_result['row_id'], field=describe_result['field'], page=describe_result['page'],
            other_problems=describe_result['other_problems'], problem_total=describe_result['problem_total'],
            reasons=describe_result.get('reasons') or [describe_result['reason']], also=describe_result.get('also') or [])
        if describe_result.get('choice'):
            entry['choice'] = describe_result['choice']
        if describe_result.get('why'):
            entry['why'] = describe_result['why']
        entry.update(issue_pages=describe_result.get('pages') or [], issue_messages=describe_result.get('messages') or [])
    vision = summary.get('vision_reading')
    if vision and item.status == 'attention' and vision.get('status') in ('not_proved', 'budget', 'failed') \
            and vision.get('message'):
        # Why reading its page images did not settle it (vision_reader); the statement stays as it was.
        entry['vision_reading'] = dict(status=vision['status'], message=vision['message'])
        if describe_result and vision['message'] not in entry['issue_messages']:
            entry['issue_messages'] = [*entry['issue_messages'], 'Page images: ' + vision['message']]
    not_payment = summary.get('not_payment_statement')
    if not_payment:
        entry.update(not_payment=dict(kind=not_payment.get('kind'), label=not_payment.get('label'),
                                      reason=not_payment.get('reason')))
    check = summary.get('saved_copy_check')
    if check and check.get('outcome') in ('differs', 'not_comparable') and item.status == 'attention':
        # A copy of an account and period the case already saved, held because it differs (saved_copies).
        entry['saved_copy'] = dict(outcome=check['outcome'], saved_filename=(check.get('saved') or {}).get('filename'),
                                   differences=check.get('differences') or [])
        if describe_result:
            entry['also'] = [*entry.get('also', []), saved_copy_sentence(check)]
    return entry


def saved_copy_sentence(check):
    """One plain sentence: why a copy of a saved account and period was not set aside."""
    parts = []
    for difference in check.get('differences') or []:
        field = difference.get('field')
        if field == 'payments':
            parts.append(f"{difference['copy']} payments here, {difference['saved']} saved "
                         f"({difference['only_in_copy']} only here, {difference['only_in_saved']} only in the saved one)")
        elif field in ('opening', 'closing', 'currency'):
            parts.append(f"the {field}{' balance' if field != 'currency' else ''} differs")
        elif field == 'unread_rows':
            parts.append('some lines here are not read')
        elif field == 'incomplete_payment':
            parts.append('a payment here has no date, amount or direction')
        elif field == 'no_payments':
            parts.append('no payments to compare')
        elif field == 'several_saved_statements':
            parts.append('several saved statements match')
    return ('This account and period is already saved; this copy is held because ' + ('; '.join(parts) or 'it differs')
            + ': compare it with the saved statement')


def _preparing_again(batches):
    """(batch id, file id) of prepared files a running batch is preparing or reading again.

    A file handed back for a new reading (``recovery``) waits for its turn
    before it is processed; it is being rechecked from the hand-off on.
    """
    from services.financial.held_reprepare import pending_files
    batches = list(batches)
    # Also a held file marked to be prepared again with the deployed reader, waiting for its turn.
    return {(batch.id, file['file_id']) for batch in batches if batch.status in ('preparing', 'pausing')
            for file in batch.files or [] if file.get('file_id') and (file.get('status') == 'processing'
                or (file.get('status') == 'waiting' and file.get('recovery')))} | pending_files(batches)


# Buckets a scheduled re-read moves to "Being rechecked": held statements only.
REREAD_BUCKETS = frozenset({'waiting', 'reader_fix', 'unreadable', 'filled'})


def _rechecked_by_recovery(session, case_id, entries):
    """Held statements a reader campaign will read again count as being rechecked. In place; live, never cached."""
    from services.financial.recovery_readers import rereading_files
    try:
        again = rereading_files(session, case_id)
    except Exception:
        session.rollback()  # no recovery tables (an old database): nothing scheduled
        return entries
    if again:
        for entry in entries:
            if entry['bucket'] in REREAD_BUCKETS and again & set(entry['file_ids']):
                entry['bucket'] = 'rechecking'
    return entries


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
    preparing_again = _preparing_again(batches.values())
    # A file-level preparation that found nothing does not stand for a file
    # that a preparation (another batch, a later reader) split into named
    # statements: those statements are the file's entries, wherever they stand.
    named = {root for root, key in identities if key}
    for identity, item in representatives.items():
        current = projected.get(item.id)
        if current is None:
            continue
        bucket = classify(current)
        if bucket == 'unreadable' and not identity[1] and identity[0] in named:
            continue
        if bucket in ('waiting', 'ready', 'filled', 'unreadable') and (item.batch_id, str(item.file_id)) in preparing_again:
            # Its file is being prepared again (after a release, or a retry):
            # what it shows now may change in a moment.
            bucket = 'rechecking'
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
    # A whole-file entry prepared before its file was split into named statements stands for nothing once every
    # one of those statements is imported, set aside as a copy, left out or not a payment statement: its own
    # reading is older, and the work is done (BNB2 2026-10-25: 6 such entries counted as waiting). Nothing is
    # deleted; the entry is only no longer listed. Reverse: LOUPE_FINANCIAL_QUEUE_HIDE_SPLIT_DONE=0.
    if os.environ.get('LOUPE_FINANCIAL_QUEUE_HIDE_SPLIT_DONE', '1').strip().lower() not in ('0', 'false', 'off', 'no'):
        named_buckets = {}
        for identity, bucket, *_ in rows:
            if identity[1]:
                named_buckets.setdefault(identity[0], set()).add(bucket)
        settled = {'imported', 'copies', 'not_payment', 'left_unimported'}
        rows = [row for row in rows if row[0][1] or row[1] not in ('waiting', 'unreadable', 'ready', 'filled')
                or not named_buckets.get(row[0][0]) or not named_buckets[row[0][0]] <= settled]
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


# The queue is cached per case while its inputs are unchanged (the register's
# PostgreSQL row-version fingerprint, which covers batches, items, files,
# readings and saved records). Cached views are never mutated: a response
# copies only the entries it returns. Memory is bounded by cases and by
# entries held in all, and one build per case runs at a time in a process.
_CACHE_SIZE = 8
CACHE_MAX_ENTRIES = 40_000
_cache = OrderedDict()   # case -> (fingerprint, view)
_lock = threading.Lock()
_building = {}           # case -> threading.Event set when its build ends
BUILD_WAIT_SECONDS = 180


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
                _view(session, UUID(key), note=False)
                rebuilt.append(key)
            finally:
                session.rollback()
    return rebuilt


def _compute(session, case_id):
    """The whole-case view: entries, failed and set-aside files, unread count. Read only."""
    from services.financial.auto_read import unread_statement_files
    entries = _build(session, case_id)
    _saved_checks(session, case_id, entries)
    _copies_none_saved(session, case_id, entries)
    set_aside = []
    entries, failed, copy_files = _set_aside_read_copies(session, case_id, entries,
        _failed_files(session, case_id, set(), set_aside))
    _ready_saved_elsewhere(session, case_id, entries)
    _mark_read_afresh(session, case_id, failed)
    _worked_by(session, entries)
    from datetime import datetime, timezone
    return dict(entries=entries, failed=failed, copy_files=copy_files, set_aside=set_aside,
                unread=len(unread_statement_files(session, case_id=case_id)),
                as_of=datetime.now(timezone.utc).isoformat(timespec='seconds'))


# A saved statement a ledger check finds wrong or unproven is listed for a person with the plain reason instead of
# counting as imported (auto_save_guard.saved_checks: holder an address line, a balance that does not carry, the
# same account and period saved twice, a one-digit account misread). Nothing saved is changed. Reverse:
# LOUPE_FINANCIAL_QUEUE_SAVED_CHECKS=0.
SAVED_CHECKS = os.environ.get('LOUPE_FINANCIAL_QUEUE_SAVED_CHECKS', '1').strip().lower() not in ('0', 'false', 'off', 'no')


def _saved_checks(session, case_id, entries):
    if not SAVED_CHECKS:
        return
    from services.financial.auto_save_guard import saved_checks
    found = saved_checks(session, case_id)
    if not found:
        return
    imported = [entry for entry in entries if entry['bucket'] == 'imported']
    ids = {UUID(entry['file_id']) for entry in imported if _uuid(entry['file_id'])}
    shas = {str(file_id): sha for file_id, sha in session.execute(select(EvidenceFile.id, EvidenceFile.sha256)
                                                                  .where(EvidenceFile.id.in_(ids)))} if ids else {}
    for entry in imported:
        check = found.get((shas.get(entry['file_id']), entry.get('statement_id') or ''))
        if not check:
            continue
        reason, sentence = check
        entry.update(bucket='waiting', issue=sentence, issue_reason='saved_check', saved_check=reason,
                     field=DETAIL_FIELDS.get(reason), row_id=None, other_problems=0, problem_total=1,
                     reasons=['saved_check'], also=[], issue_pages=[], issue_messages=[sentence])


# A statement whose every upload sits in 'copies' while none of them is saved is not settled: the copies were set
# aside for, or held against, each other (BNB2: CAAL BBVA 0119200843 Aug 2025 and BBVA 0125701104 USD Sep 2025 were
# absent from the ledger with all their items under copies). When no saved period of the same account (its printed
# digits equal or one inside the other, as an account inside its CLABE), currency and overlapping dates exists, and
# no entry of that statement is imported or saving, one of its copies (the one the copy rule keeps, else the first)
# is listed under 'waiting' with the plain reason. Nothing is changed. Reverse: LOUPE_FINANCIAL_QUEUE_COPIES_NONE_SAVED=0.
COPIES_NONE_SAVED = os.environ.get('LOUPE_FINANCIAL_QUEUE_COPIES_NONE_SAVED', '1').strip().lower() not in ('0', 'false', 'off', 'no')
COPIES_NONE_SAVED_SENTENCE = ('Every copy of this statement was set aside as a copy of another, and none of them is '
                              'saved. Check this one against the PDF and save it.')


def _digits(value):
    return ''.join(ch for ch in str(value or '') if ch.isdigit())


def _copies_none_saved(session, case_id, entries):
    if not COPIES_NONE_SAVED:
        return
    scope = lambda e: (_digits(e.get('account')), e.get('currency') or '', e.get('period_start') or '', e.get('period_end') or '')
    copies = {}
    for entry in entries:
        key = scope(entry)
        if entry['bucket'] == 'copies' and len(key[0]) >= 6 and all(key[1:]):
            copies.setdefault(key, []).append(entry)
    if not copies:
        return
    busy = {scope(e) for e in entries if e['bucket'] in ('imported', 'saving', 'waiting', 'ready', 'filled', 'rechecking', 'reader_fix')}
    from postgres.models.financial import FinancialAccount, FinancialSourceDocument, FinancialStatementPeriod
    saved = session.execute(select(FinancialAccount.identifier_as_printed, FinancialStatementPeriod.currency,
                                   FinancialStatementPeriod.period_start, FinancialStatementPeriod.period_end)
        .join(FinancialStatementPeriod, FinancialStatementPeriod.account_id == FinancialAccount.id)
        .join(FinancialSourceDocument, FinancialSourceDocument.id == FinancialStatementPeriod.source_document_id)
        .where(FinancialStatementPeriod.case_id == case_id, FinancialSourceDocument.status == 'admitted',
               FinancialStatementPeriod.period_start.is_not(None), FinancialStatementPeriod.period_end.is_not(None))).all()
    saved = [(_digits(a), c, str(s0), str(e0)) for a, c, s0, e0 in saved]
    for key, group in copies.items():
        digits, currency, start, end = key
        if key in busy or any(c == currency and d and (d in digits or digits in d) and s0 <= end and e0 >= start
                              for d, c, s0, e0 in saved):
            continue
        keeps = [e for e in group if not e.get('set_aside')]
        entry = sorted(keeps or group, key=lambda e: e['id'])[0]
        entry.update(bucket='waiting', issue=COPIES_NONE_SAVED_SENTENCE, issue_reason='copies_none_saved', row_id=None,
                     other_problems=0, problem_total=1, reasons=['copies_none_saved'], also=[], issue_pages=[],
                     issue_messages=[COPIES_NONE_SAVED_SENTENCE])


def _store(key, fingerprint, view):
    with _lock:
        _cache[key] = (fingerprint, view)
        _cache.move_to_end(key)
        held = lambda: sum(len(value[1]['entries']) for value in _cache.values())
        while len(_cache) > 1 and (len(_cache) > _CACHE_SIZE or held() > CACHE_MAX_ENTRIES):
            _cache.popitem(last=False)


def _build_once(session, key, case_id, fingerprint):
    """Build and cache, one build per case at a time; a concurrent caller waits for it. Returns the view."""
    with _lock:
        running = _building.get(key)
        if running is None:
            running = _building[key] = threading.Event()
            mine = True
        else:
            mine = False
    if not mine:
        running.wait(BUILD_WAIT_SECONDS)
        with _lock:
            hit = _cache.get(key)
        if hit and hit[0] == fingerprint:
            return hit[1]
        return _compute(session, case_id)  # that build was of older inputs (or timed out)
    try:
        view = _compute(session, case_id)
        _store(key, fingerprint, view)
        return view
    finally:
        with _lock:
            _building.pop(key, None)
        running.set()


def _refresh_in_background(bind, key, case_id):
    """Start one background build of the current inputs (own session, same database) unless one is running."""
    with _lock:
        if key in _building:
            return
    def run():
        from sqlalchemy.orm import sessionmaker
        from services.financial.statement_file_status import status_fingerprint
        try:
            with sessionmaker(bind=bind, autoflush=False)() as session:
                try:
                    _build_once(session, key, case_id, status_fingerprint(session, case_id))
                finally:
                    session.rollback()
        except Exception:
            import logging
            logging.getLogger(__name__).exception('Review queue rebuild failed; the next read builds it')
    threading.Thread(target=run, name=f'review-queue-{key[:8]}', daemon=True).start()


def _view(session, case_id, use_cache=True, note=True, stale_ok=False):
    """(whole-case view, refreshing). Reused while the case's rows are unchanged.

    ``stale_ok``: when the inputs changed since the cached view was built, that
    view is returned at once (refreshing=True) and the current one is built
    in the background; a read never waits behind a rebuild it did not need.
    """
    from services.financial.statement_file_status import status_fingerprint
    fingerprint = status_fingerprint(session, case_id) if use_cache else None
    if fingerprint is None:
        return _compute(session, case_id), False
    key = str(case_id)
    if note:
        with _lock:
            _recent_reads[key] = time.monotonic()
            _recent_reads.move_to_end(key)
            while len(_recent_reads) > 16:
                _recent_reads.popitem(last=False)
    with _lock:
        hit = _cache.get(key)
        if hit:
            _cache.move_to_end(key)
    if hit and hit[0] == fingerprint:
        return hit[1], False
    if hit and stale_ok:
        _refresh_in_background(session.get_bind(), key, case_id)
        return hit[1], True
    return _build_once(session, key, case_id, fingerprint), False


def _entries(session, case_id, use_cache=True, note=True):
    """(queue entries, unread statement files): copies, for callers that change them."""
    view, _ = _view(session, case_id, use_cache=use_cache, note=note)
    return [dict(entry) for entry in view['entries']], view['unread']


def _counts(entries):
    counts = {bucket: 0 for bucket in BUCKETS}
    for entry in entries:
        counts[entry['bucket']] += 1
    return counts


REMOVED_FILE_MESSAGE = ('You removed this file from Financial, so it is not read. If it should be read, restore it '
                        'under Removed files in Statements & accounts.')
GONE_FILE_MESSAGE = 'This file is no longer in the case, so there is nothing to read.'


def _set_aside_reason(session, case_id, record):
    """Why a failed preparation is not a reading problem: 'removed' or 'gone'; None when it is one.

    A batch can hold a file the investigator later removed from Financial
    (or a selection can sweep removed files in): its preparation then fails
    ('Statement not found in this case', 'The source recorded for restarting
    this removed import is unavailable'). Nothing can be read until she
    restores it, so it is counted as removed, never as "Couldn't read".
    """
    from services.financial.file_visibility import financial_file_visibility
    ids = [UUID(i) for i in (record.get('source_id'), record.get('file_id')) if i and _uuid(i)]
    files = [session.get(EvidenceFile, i) for i in ids]
    files = [f for f in files if f is not None]
    if not files or all(f.case_id != case_id for f in files):
        return 'gone'
    own = [f for f in files if f.case_id == case_id]
    if any(financial_file_visibility(f)['financial_removed'] for f in own):
        return 'removed'
    return None


def _failed_files(session, case_id, file_filter, set_aside=None):
    """Files a batch could not prepare and that have no statement at all.

    Failures that are not reading problems (the file was removed from
    Financial or is no longer in the case) are moved to ``set_aside`` with
    their reason instead. A failed upload whose identical bytes or pages were
    read from another upload is linked to it by _set_aside_read_copies.
    """
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
    if not failed:
        return []
    result = []
    for record in failed.values():
        why = _set_aside_reason(session, case_id, record)
        if why is None:
            result.append(record)
        elif set_aside is not None:
            set_aside.append(dict(record, reason=why, message={'removed': REMOVED_FILE_MESSAGE,
                'gone': GONE_FILE_MESSAGE}[why], error=record['message']))
    return result


def _set_aside_read_copies(session, case_id, entries, failed):
    """Move failed readings of a file that another upload of the same document read into copies.

    A second upload of the same bytes, or of a file whose every page renders
    identically (``page_identity``: the same statement saved again by another
    program), reaches the copy review only through its own statements. When its
    reading failed (an older reader, a removed import's lost source) it would
    stay under "Couldn't read" for good although the same pages were read
    through another upload. Such entries are set aside, linked to the upload
    that was read. Nothing is written; if that upload also could not read a
    statement, its own entry still says so.
    """
    from services.financial import page_identity
    read = {e['file_id'] for e in entries if e['bucket'] not in ('unreadable', 'unexplained')}
    failed_ids = {f.get('file_id') or f.get('source_id') for f in failed}
    wanted = {e['file_id'] for e in entries if e['bucket'] == 'unreadable'} | failed_ids
    if not read or not wanted:
        return entries, failed, []
    ids = {UUID(i) for i in read | wanted if i and _uuid(i)}
    files = {}
    for file in session.scalars(select(EvidenceFile).where(EvidenceFile.case_id == case_id, EvidenceFile.id.in_(ids))):
        pages = page_identity.stored(file)
        files[str(file.id)] = (file.sha256, file.original_filename,
                               (pages['identity'], pages['renderer'], pages['page_count']) if pages else None)
    read_by_sha, read_by_pages = {}, {}
    for file_id in sorted(read):
        sha, name, pages = files.get(file_id, (None, None, None))
        if sha:
            read_by_sha.setdefault(sha, (file_id, name))
        if pages:
            read_by_pages.setdefault(pages, (file_id, name))

    def copy_of(file_id):
        sha, _, pages = files.get(file_id, (None, None, None))
        for match, reason in ((read_by_sha.get(sha) if sha else None, 'same_file_read'),
                              (read_by_pages.get(pages) if pages else None, 'same_pages_read')):
            if match and match[0] != file_id:
                return match, reason
        return None, None

    for entry in entries:
        match, reason = copy_of(entry['file_id']) if entry['bucket'] == 'unreadable' else (None, None)
        if match:
            entry.update(bucket='copies', set_aside=True, copy_of=match[1] or None,
                         copy_reason=reason, copy_file_id=match[0])
    kept, copies = [], []
    for file in failed:
        match, reason = copy_of(file.get('file_id') or file.get('source_id'))
        if match:
            copies.append(dict(file, copy_of=match[1] or None, copy_file_id=match[0], copy_reason=reason))
        else:
            kept.append(file)
    return entries, kept, copies


# Neil, 2026-10-25 (BNB2 queue): a "ready" statement that its save would hold as "Already saved through another
# batch" is a copy, not work. Reverse: LOUPE_FINANCIAL_QUEUE_SAVED_ELSEWHERE=0 (it stays listed as ready).
SAVED_ELSEWHERE = os.environ.get('LOUPE_FINANCIAL_QUEUE_SAVED_ELSEWHERE', '1').strip().lower() not in (
    '0', 'false', 'off', 'no')


def _ready_saved_elsewhere(session, case_id, entries):
    """Move to copies the ready entries whose statement another upload of the same document already saved. In place.

    The queue save's own rule (``queue_save.save_statements``): the same statement key in a file with the same
    bytes or the same rendered pages (``page_identity``) is imported or being imported in a batch of the case
    that is not removed. Only such an upload whose file also holds an admitted, not removed saved statement is
    named as the original, so a removed import never makes a statement look saved. Nothing is written.
    """
    if not SAVED_ELSEWHERE:
        return entries
    from sqlalchemy import or_
    from postgres.models.financial import FinancialSourceDocument as Source
    from services.financial import page_identity
    ready = [e for e in entries if e['bucket'] == 'ready' and _uuid(e['file_id'])]
    if not ready:
        return entries
    own = {str(f.id): f for f in session.scalars(select(EvidenceFile).where(
        EvidenceFile.case_id == case_id, EvidenceFile.id.in_({UUID(e['file_id']) for e in ready})))}
    pages = lambda file: (page_identity.stored(file) or {}).get('identity')
    shas = {f.sha256 for f in own.values() if f.sha256}
    identities = {pages(f) for f in own.values() if pages(f)}
    if not shas and not identities:
        return entries
    matching = ([EvidenceFile.sha256.in_(shas)] if shas else []) + ([EvidenceFile.metadata_[
        page_identity.METADATA_KEY]['identity'].as_string().in_(identities)] if identities else [])
    saved = {}
    for file, key in session.execute(select(EvidenceFile, Item.statement_key)
            .join(Item, Item.file_id == EvidenceFile.id).join(Batch, Batch.id == Item.batch_id)
            .where(Batch.case_id == case_id, Batch.status != 'removed', or_(*matching),
                   Item.status.in_(('pending_import', 'imported')))):
        saved.setdefault(key or '', {})[str(file.id)] = file
    # (file, statement key) of admitted, not removed saved statements (a keyless record matches only a keyless
    # statement, as in _saved_scopes).
    admitted = {(str(file_id), key or '') for file_id, key in session.execute(select(
        Source.evidence_file_id, Source.metadata_['statement_import_statement_id'].as_string()).where(
        Source.case_id == case_id, Source.status == 'admitted', Source.document_type == 'statement_review',
        Source.metadata_['financial_import_removal'].as_string().is_(None),
        Source.evidence_file_id.in_([UUID(i) for files in saved.values() for i in files])))} if saved else set()
    for entry in ready:
        file = own.get(entry['file_id'])
        if file is None:
            continue
        for other_id, other in sorted((saved.get(entry.get('statement_id') or '') or {}).items()):
            if other_id == entry['file_id'] or (other_id, entry.get('statement_id') or '') not in admitted:
                continue
            same_bytes = bool(file.sha256 and other.sha256 == file.sha256)
            stored, other_stored = page_identity.stored(file) or {}, page_identity.stored(other) or {}
            same_pages = bool(stored.get('identity') and (stored.get('identity'), stored.get('renderer'))
                              == (other_stored.get('identity'), other_stored.get('renderer')))
            if not same_bytes and not same_pages:
                continue
            entry.update(bucket='copies', set_aside=True, copy_of=other.original_filename or None,
                         copy_reason='same_file_read' if same_bytes else 'same_pages_read', copy_file_id=other_id)
            break
    return entries


def _mark_read_afresh(session, case_id, failed):
    """Mark failed files whose retained PDF the investigator can explicitly read afresh.

    The removal they would restart from is gone from Evidence. Only the
    explicit, byte-verified recovery may read them again; this marks each with
    the revision that recovery requires, nothing more.
    """
    from services.financial.reading_recovery import retry_reference_problem
    candidates = [f for f in failed if (f.get('message') or '').startswith(RESTART_UNAVAILABLE)]
    ids = {UUID(i) for f in candidates for i in (f.get('source_id'), f.get('file_id')) if i and _uuid(i)}
    if not ids:
        return
    files = {str(file.id): file for file in session.scalars(select(EvidenceFile).where(
        EvidenceFile.case_id == case_id, EvidenceFile.id.in_(ids)))}
    for entry in candidates:
        source = files.get(entry.get('source_id'))
        if source is None:
            continue
        problem = retry_reference_problem(session, case_id=case_id, source_id=source.id, source=source,
            prepared=files.get(entry.get('file_id')))
        if problem and problem.get('retained_source_revision'):
            entry['read_afresh_revision'] = problem['retained_source_revision']


# Held work someone saved themselves: the queue names that person, not whoever opens it.
OWN_WORK_REASONS = frozenset({'saved_review', 'import_failed'})
OWN_WORK_MESSAGE = 'manually added transaction'


def _own_work(entry):
    return entry['bucket'] in ('waiting', 'unreadable') and (
        bool(OWN_WORK_REASONS & set(entry.get('reasons') or [entry.get('issue_reason')]))
        or any(OWN_WORK_MESSAGE in (m or '').lower() for m in entry.get('issue_messages') or []))


def _worked_by(session, entries):
    """Name who saved the held review (``worked_by``: user id and name) on entries holding their own work. In place."""
    wanted = [e for e in entries if _own_work(e) and _uuid(e['file_id'])]
    for entry in wanted:
        try:
            saved = session.execute(select(EvidenceFile.metadata_['financial_review_progress'][entry['statement_id'] or '']
                ['saved_by']).where(EvidenceFile.id == UUID(entry['file_id']))).scalar()
        except Exception:
            session.rollback()
            return entries
        if isinstance(saved, dict) and saved.get('name') and saved.get('user_id'):
            entry['worked_by'] = dict(user_id=str(saved['user_id']), name=str(saved['name']))
    return entries


RESTART_UNAVAILABLE = 'The source recorded for restarting this removed import is unavailable'


def _uuid(value):
    try:
        UUID(str(value))
        return True
    except ValueError:
        return False


PAGE_LISTS = {'waiting': 'items', 'ready': 'ready', 'filled': 'filled', 'reader_fix': 'reader_fix',
              'rechecking': 'rechecking', 'copies': 'copies', 'unreadable': 'unreadable', 'not_payment': 'not_payment'}


def _public(entry):
    return {key: value for key, value in entry.items() if key != 'root'}


def case_review_queue(session, *, case_id, file_ids=None, use_cache=True, limit=None, offset=0,
                      page_list='waiting', issue=None, stale_ok=False):
    """The case's queue and status line, optionally limited to some files (evidence ids).

    ``limit`` caps every entry list (0: counts only) and ``offset``/``issue``
    page the list named ``page_list``; ``totals``, ``page`` and
    ``issue_counts`` say how much there is, so nothing is cut silently.
    Counts and the status line are always whole-case (whole-filter).
    ``stale_ok`` returns a view built moments ago while a current one is
    built (``refreshing``); see ``_view``.
    """
    from services.financial.auto_read import reading_progress
    if page_list not in PAGE_LISTS:
        raise ValueError(f'Unknown queue list: {page_list}')
    started = time.perf_counter()
    view, refreshing = _view(session, case_id, use_cache=use_cache, stale_ok=stale_ok)
    # Live (not cached): files being read or prepared, for "Reading 12 of 40 files".
    reading = dict(reading_progress(session, case_id=case_id), unread_statement_files=view['unread'])
    file_filter = {str(i) for i in file_ids or []}
    entries, failed, copy_files, set_aside = view['entries'], view['failed'], view['copy_files'], view['set_aside']
    # Live too: statements a reader campaign will read again (copies of the
    # cached entries it moves, never the cached ones).
    moved = _rechecked_by_recovery(session, case_id, [dict(entry) for entry in entries
                                                      if entry['bucket'] in REREAD_BUCKETS])
    if moved:
        moved = {entry['id']: entry for entry in moved if entry['bucket'] == 'rechecking'}
        entries = [moved.get(entry['id'], entry) for entry in entries]
    if file_filter:
        entries = [e for e in entries if file_filter & set(e['file_ids'])]
        within = lambda f: bool({f.get('file_id'), f.get('source_id')} & file_filter)
        failed, copy_files = [f for f in failed if within(f)], [f for f in copy_files if within(f)]
        set_aside = [f for f in set_aside if within(f)]
    counts = _counts(entries)
    counts['unreadable_files'] = len(failed)
    counts['removed_files'] = len(set_aside)
    counts['copies'] += len(copy_files)
    counts['copy_files'] = len(copy_files)
    waiting_for_reader = reader_files(entries)
    lists = {name: [e for e in entries if e['bucket'] == name] for name in PAGE_LISTS}
    issue_counts = {}
    for entry in lists['waiting']:
        if entry.get('issue_reason'):
            issue_counts[entry['issue_reason']] = issue_counts.get(entry['issue_reason'], 0) + 1
    totals = {name: len(values) for name, values in lists.items()}
    chosen = [e for e in lists[page_list] if not issue or e.get('issue_reason') == issue]
    offset = max(0, int(offset or 0))
    pages = {name: (values if limit is None else values[:max(0, limit)]) for name, values in lists.items()}
    pages[page_list] = chosen[offset:] if limit is None else chosen[offset:offset + max(0, limit)]
    ready_batches = {}
    for entry in lists['ready']:
        ready_batches[entry['batch_id']] = ready_batches.get(entry['batch_id'], 0) + 1
    public = {name: [_public(e) for e in values] for name, values in pages.items()}
    return dict(case_id=str(case_id), file_ids=sorted(file_filter), counts=counts,
        status_line=status_line(counts, reading), reading=reading, items=public['waiting'], copies=public['copies'],
        unreadable=public['unreadable'], unreadable_files=failed, set_aside_files=set_aside, copy_files=copy_files,
        rechecking=public['rechecking'], not_payment=public['not_payment'],
        unexplained=[_public(e) for e in entries if e['bucket'] == 'unexplained'], ready=public['ready'],
        filled=public['filled'], reader_fix=public['reader_fix'], reader_files=waiting_for_reader,
        ready_batches=[dict(batch_id=key, statements=value) for key, value in
                       sorted(ready_batches.items(), key=lambda pair: -pair[1])],
        totals=totals, issue_counts=issue_counts, ready_item_ids=[e['id'] for e in lists['ready']],
        proposal_groups=[{key: value for key, value in group.items()} for group in proposal_groups(lists['waiting'])],
        page=dict(list=page_list, issue=issue or None, offset=offset, limit=limit, returned=len(pages[page_list]),
                  total=len(chosen)),
        refreshing=refreshing, as_of=view['as_of'], elapsed_ms=round((time.perf_counter() - started) * 1000))


def _group_account(entry, proposal):
    """The account a proposal is grouped under: the matched saved account, else the account number the
    statement prints (with its bank). None when the statement prints no usable number: never grouped."""
    from services.financial import field_proposals
    if proposal.get('account_key'):
        return ('saved', proposal['account_key'])
    digits, masked = field_proposals.account_identity(entry.get('account'))
    if len(digits) < field_proposals.MIN_MASKED_DIGITS:
        return None
    return ('printed', digits, masked, tuple(sorted(field_proposals.institution_key(entry.get('institution')))))


def proposal_groups(entries):
    """One confirmation per account where the same unconfirmed proposal applies to several waiting statements.

    Groups (field, value, basis, account) over the waiting entries' proposals that
    are not confirmed automatically; only groups of two or more statements are
    returned, largest first. Read only: a group is saved by a person's
    confirmation (``confirm_proposal_group``), through the statement-details
    save, filling empty fields only.
    """
    from services.financial.pdf_candidates import _digest
    groups = OrderedDict()
    for entry in entries:
        if entry.get('bucket') != 'waiting':
            continue
        for name, proposal in (entry.get('proposals') or {}).items():
            if proposal.get('confirmed') or not proposal.get('value'):
                continue
            account = _group_account(entry, proposal)
            if account is None:
                continue
            key = (name, proposal['value'], proposal.get('basis') or '', account)
            group = groups.setdefault(key, dict(field=name, value=proposal['value'], basis=proposal.get('basis') or '',
                                                label=proposal.get('label') or '', account=entry.get('account') or '',
                                                institution=entry.get('institution') or '', entry_ids=[]))
            group['entry_ids'].append(entry['id'])
    result = []
    for key, group in groups.items():
        if len(group['entry_ids']) < 2:
            continue
        group['entry_ids'].sort()
        group.update(id=_digest(dict(key=[str(part) for part in key], entries=group['entry_ids'])),
                     statements=len(group['entry_ids']))
        result.append(group)
    result.sort(key=lambda g: (-g['statements'], g['field'], g['value'], g['id']))
    return result


def confirm_proposal_group(session, *, case_id, group_id, actor, file_ids=None):
    """Save one proposal group's value on each of its statements, as the confirming person. Commits.

    The group is found again on the current queue by its id (which binds the
    field, value, account and exact statements): a queue that changed since it
    was shown refuses (409), nothing is saved. Fill-missing only: a value a
    person entered is never replaced.
    """
    from services.financial.field_proposals import apply_confirmed_proposals
    from services.financial.pdf_candidates import PdfMappingError
    view, _ = _view(session, case_id, use_cache=False, note=False)
    entries = view['entries']
    if file_ids:
        wanted = {str(i) for i in file_ids}
        entries = [e for e in entries if wanted & set(e['file_ids'])]
    group = next((g for g in proposal_groups(entries) if g['id'] == group_id), None)
    if group is None:
        raise PdfMappingError('These statements changed since the proposal was shown. Reload the queue.', 409)
    ids = set(group['entry_ids'])
    targets = []
    for entry in entries:
        if entry['id'] in ids:
            proposal = dict(entry['proposals'][group['field']], confirmed=True,
                            label=f"{entry['proposals'][group['field']].get('label', '')}; confirmed for "
                                  f"{group['statements']} statements of one account")
            targets.append(dict(entry, proposals={group['field']: proposal}))
    session.rollback()
    report = apply_confirmed_proposals(session, case_id=case_id, entries=targets, apply=True, actor=actor)
    return dict(case_id=str(case_id), group_id=group_id, field=group['field'], value=group['value'],
                statements=report.get('statements', 0), saved=report.get('saved', 0), failed=report.get('failed', 0))


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
    if counts.get('not_payment'):
        parts.append(f"Not payment statements {counts['not_payment']}")
    if counts.get('removed_files'):
        parts.append(f"Files removed from Financial {counts['removed_files']}")
    sentence = reading_sentence(reading)
    if sentence:
        parts.insert(0, sentence)
    return ' · '.join(parts)


def case_status(session, *, case_id):
    """Counts only, for badges and the cross-case view: never waits behind a rebuild of a cached case."""
    queue = case_review_queue(session, case_id=case_id, limit=0, stale_ok=True)
    return dict(case_id=queue['case_id'], counts=queue['counts'], status_line=queue['status_line'],
                reading=queue['reading'], refreshing=queue['refreshing'], as_of=queue['as_of'],
                elapsed_ms=queue['elapsed_ms'])
