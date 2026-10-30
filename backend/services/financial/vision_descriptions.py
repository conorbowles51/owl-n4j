"""The whole printed description of payments read from page images.

The page-image reader (vision_reader) reads each payment's first printed line only. BBVA and Santander print an
entry's counterparty on its detail lines (the CLABE, tracking key and name lines under "SPEI ENVIADO ..."), so a
payment read from page images lost who the other side was (fin-parties 2026-10-28: 421 payments in 9 statements).
Asking the money reading itself for every line was measured to change how a card statement's payments are signed
(fin-last4 2026-10-29: 8 of 56 card payments read as debits), so the description is read in a request of its own,
after the money reading proved: the payments already read (page, date, amount, direction, balance and first line)
are sent with the page images, and the answer is a description for each. Nothing else of a payment is taken from it.

A description is completed only when the answer starts with the first line already read (the same words, in the same
order) and adds to it, and the lines added are not the start of another payment on its page: an answer that differs,
shortens, or reaches into a neighbouring entry leaves the payment as read. Who read the lines is recorded with them.

The first line itself was read by the money reading, and a letter of it can be misread there (fin-parties 2026-10-30:
'T20 SPEI RECIDOBANORTE' printed RECIBIDOBANORTE, 'SUNOCC' printed SUNOCO, 8 X printed 10). Each answer also gives
the first line as the page prints it. When every read gives the same printed first line, it differs from the saved one
and is the same line (FIX_SIMILARITY, not another payment's first line), it is stored as a proposed correction
(``first_line_fixes``), never applied here: saved_reading_replacement.correct_first_lines applies it as the model's
reading, through the correction chain, with the earlier row kept.

Switch LOUPE_FINANCIAL_VISION_DESCRIPTION_LINES (default on). Off: nothing is sent and descriptions stay as read.
"""
from __future__ import annotations

import json
import os
import time

from services.financial.journal import journal

log = journal(__name__)

LINES = os.environ.get('LOUPE_FINANCIAL_VISION_DESCRIPTION_LINES', '1').strip().lower() not in (
    '0', 'false', 'off', 'no')
PROMPT_VERSION = 'statement-descriptions-v2'
# A description longer than this is not a statement line's text (the reader ran on).
MAX_CHARS = 600
# A printed first line is taken as a correction of the saved one only when it is the same line with a few characters
# misread: at least FIX_SIMILARITY alike (difflib ratio on the casefolded words) and at most FIX_CHARS characters added,
# dropped or changed. The five misread first lines measured (fin-parties 2026-10-30) are 0.94 to 0.98 alike and change
# 1 to 3 characters; two neighbouring BBVA first lines (T17 SPEI ENVIADO SANTANDER, T17 SPEI ENVIADO BANORTE) are 0.84
# alike and change 7, so a read that moved to the next entry is not a correction.
FIX_SIMILARITY = 0.85
FIX_CHARS = 4
# Independent reads of each page that must give the same text, word for word, before a description is completed. One
# read was measured to write a printed name in its more common spelling (BENGOCHEA as BENGOECHEA, DIC 2024 BBVA p3),
# and two reads were measured to agree on a wrong reference (0212248 for the printed 02122248, same statement p2);
# four agreeing reads gave 0 wrong of the 66 names read by hand from those page images (fin-parties 2026-10-30).
READS = 4
# Each page is sent in this many overlapping strips: narrower strips are read with fewer dropped characters in long
# digit runs (measured on 4 pages of the BBVA and Santander statements: 6 strips 3 wrong of 43 completed, 12 strips 1
# of 41). The money reading keeps its own strips.
STRIPS = 12
# One page's request is short (its payments' lines): a request running longer than this is dropped, retried once
# when the connection or server failed. A request is not started when it could end after the caller's deadline.
TIMEOUT_SECONDS = 300
RETRIES = 1
REASON = 'Description lines read from page image, page {page}, by {by}; amount, date and direction as read before.'

SCHEMA = {'type': 'object', 'additionalProperties': False, 'required': ['rows'],
          'properties': {'rows': {'type': 'array', 'items': {
              'type': 'object', 'additionalProperties': False, 'required': ['id', 'description', 'printed_first_line'],
              'properties': {'id': {'type': 'string'}, 'description': {'type': 'string'},
                             'printed_first_line': {'type': 'string'}}}}}}

PROMPT = """You are a forensic transcriber. The images are the pages of a bank or card account statement. The movement lines of the statement have already been read; they are listed below as JSON, one object per movement: its id, the page label N it is printed on, its date, amount, direction and running balance as read, and "first_line": the first printed line of its description.

Your only task: for each listed movement, transcribe its COMPLETE printed description.

HOW THE IMAGES ARE GIVEN
- Each image is preceded by a label "Page N" or "Page N, part k of K". N is the page's position in the file, the same N as the movements' "page". A page cut into horizontal strips is given top to bottom, and neighbouring strips OVERLAP: a line seen in two strips is one line.

WHAT TO TRANSCRIBE FOR EACH MOVEMENT
- Find the movement on its page: the line printing its date and amount, whose description starts with its first_line.
- Its description is its first line followed by every detail line printed under it in the description column that belongs to the same entry: reference and concept lines, account, card, CLABE and tracking numbers, and the name of the person or company who paid or was paid. It ends where the next movement's dated line starts, or at a balance, total or heading line.
- When the movement is the last one on its page and its detail lines continue at the top of the next page (under the repeated column headings, before the next dated line), those lines are part of it too.
- Begin with first_line exactly as given, then the detail lines in printed order, joined with single spaces.
- Transcribe exactly as printed, letter by letter and digit by digit. Never summarise, shorten, correct, translate, complete or add anything.
- Never include text of another movement, the column headings, page headers or footers, notices, or the date, amount or balance columns.
- A movement with no detail lines: return its first_line unchanged.

THE FIRST LINE AS PRINTED
- first_line is how the movement's first line was read before, and a character of it may be misread: a dropped or changed letter, or a wrong count of repeated characters such as XXXXXXXX. In "printed_first_line" give that same line exactly as the page prints it, letter by letter, digit by digit and space by space. Read it from the page; never copy first_line. When the page prints exactly first_line, give first_line.

Return one JSON object only, no markdown: {"rows": [{"id": "<id>", "description": "<complete description>", "printed_first_line": "<first line as printed>"}]}, with every listed id exactly once and no other ids.

MOVEMENTS
"""


def _words(text):
    return ' '.join(str(text or '').split())


def _key(text):
    return _words(text).casefold()


def instructions(rows):
    """The request text for ``rows`` ([{id, page, date, amount, direction, balance, first_line}])."""
    return PROMPT + json.dumps(rows, ensure_ascii=False, indent=0)


def listed(rows):
    """The movements as sent: id, page, date, amount, direction, balance and first line (the description as read)."""
    return [dict(id=str(row['id']), page=row['page'], date=str(row.get('date') or ''), amount=str(row['amount']),
                 direction=row.get('direction') or '', balance=None if row.get('balance') is None else str(row['balance']),
                 first_line=_words(row['description'])) for row in rows]


def completed(rows, answer, everyone=None):
    """({id: completed description}, {id: why left as read}) from the answer, for ``rows`` as listed (``listed``).

    Taken only when the answer begins with the description already read and adds to it, is not longer than MAX_CHARS,
    and what it adds is not the first line of another movement (``everyone``: every movement listed for the statement,
    default ``rows``) on the same page or the next one, a neighbouring entry, even one printing the same first line.
    The first line keeps its saved text; only the lines added come from the answer. Every listed id must be answered
    exactly once, or nothing is taken."""
    found, kept = {}, {}
    answered = (answer or {}).get('rows') if isinstance(answer, dict) else None
    if not isinstance(answered, list):
        return {}, {row['id']: 'no_answer' for row in rows}
    ids = [str(item.get('id')) for item in answered if isinstance(item, dict)]
    if sorted(ids) != sorted(row['id'] for row in rows) or len(ids) != len(answered):
        return {}, {row['id']: 'answer_ids_differ' for row in rows}
    text = {str(item['id']): _words(item.get('description')) for item in answered}
    starts = {}
    for row in everyone or rows:
        starts.setdefault(row['page'], []).append((row['id'], _key(row['first_line'])))
    for row in rows:
        old, new = row['first_line'], text[row['id']]
        if _key(new) == _key(old):
            continue
        if not old or not _key(new).startswith(_key(old) + ' '):
            kept[row['id']] = 'does_not_start_with_first_line'
            continue
        if len(new) > MAX_CHARS:
            kept[row['id']] = 'too_long'
            continue
        lines = new.split()[len(old.split()):]
        added = ' ' + _key(' '.join(lines))
        others = [start for page in (row['page'], row['page'] + 1) for other, start in starts.get(page, [])
                  if other != row['id'] and len(start) >= 8]
        if any(' ' + start in added for start in others):
            kept[row['id']] = 'reaches_another_payment'
            continue
        found[row['id']] = _words(old) + ' ' + ' '.join(lines)
    return found, kept


def printed_first_lines(rows, answer, everyone=None):
    """{id: printed first line} from one answer, for each listed row whose printed first line (``printed_first_line``)
    differs from the saved one and is the same line: at least FIX_SIMILARITY alike, at most FIX_CHARS characters
    changed, not longer than MAX_CHARS, and not
    the first line of another movement on its page or the next one. A case-only difference is no correction. An answer
    that does not answer every listed id exactly once gives nothing."""
    from difflib import SequenceMatcher
    answered = (answer or {}).get('rows') if isinstance(answer, dict) else None
    if not isinstance(answered, list) or not all(isinstance(item, dict) for item in answered):
        return {}
    ids = [str(item.get('id')) for item in answered]
    if sorted(ids) != sorted(row['id'] for row in rows) or len(set(ids)) != len(ids):
        return {}
    printed = {str(item['id']): _words(item.get('printed_first_line')) for item in answered}
    starts = {}
    for row in everyone or rows:
        starts.setdefault(row['page'], set()).add(_key(row['first_line']))
    fixes = {}
    for row in rows:
        old, new = row['first_line'], printed[row['id']]
        if not old or not new or _key(new) == _key(old) or len(new) > MAX_CHARS:
            continue
        matcher = SequenceMatcher(None, _key(old), _key(new), autojunk=False)
        changed = sum(max(i2 - i1, j2 - j1) for tag, i1, i2, j1, j2 in matcher.get_opcodes() if tag != 'equal')
        if matcher.ratio() < FIX_SIMILARITY or changed > FIX_CHARS:
            continue
        if any(_key(new) in starts.get(page, ()) for page in (row['page'], row['page'] + 1)):
            continue
        fixes[row['id']] = new
    return fixes


def description_request(model_id, api_key, provider):
    """read(pages, rows) -> (answer json, usage): one request with the page images and the listed movements. Raises on
    any failure (the descriptions then stay as read)."""
    from services.financial import vision_reader as vr
    from services.llm_service import LLMExecutionContext
    settings = dict(vr.READER_SETTINGS.get(provider) or vr.READER_SETTINGS['openai'])
    settings.update(timeout=min(settings['timeout'], TIMEOUT_SECONDS), retries=min(settings['retries'], RETRIES))

    def read(pages, rows):
        labels, images = [], []
        for number, parts in pages:
            for index, image in enumerate(parts):
                labels.append(f'Page {number}' if len(parts) == 1 else f'Page {number}, part {index + 1} of {len(parts)}')
                images.append(image)
        prompt = instructions(rows)
        for attempt in range(settings['retries'] + 1):
            context = LLMExecutionContext(provider, model_id, api_key=api_key)
            try:
                text = context.call_vision_json(prompt, images, image_labels=labels, schema=SCHEMA,
                                                schema_name='statement_descriptions', timeout=settings['timeout'],
                                                max_output_tokens=settings['max_output_tokens'])
                break
            except Exception as error:  # noqa: BLE001 - retried only when the connection or server failed
                if attempt >= settings['retries'] or not vr._retryable(error):
                    error.usage = dict(context.last_usage or {})
                    raise
                time.sleep(vr.RETRY_PAUSE_SECONDS * (attempt + 1))
        try:
            answer = json.loads(text)
        except ValueError as error:
            unreadable = vr.UnreadableAnswer('the answer was not valid JSON')
            unreadable.usage = dict(context.last_usage or {})
            raise unreadable from error
        return answer, dict(context.last_usage or {})
    return read


def _add(total, usage):
    for name, value in (usage or {}).items():
        if isinstance(value, (int, float)):
            total[name] = total.get(name, 0) + value


def request_seconds():
    """The longest one page's request can take, by any provider: every try at its full allowance (OpenAI's client
    tries each request up to OPENAI_CLIENT_TRIES times, its timeout applying to connecting and to reading; DeepSeek's
    read may run on by its silence allowance), with the pauses between."""
    from services.financial import vision_reader as vr
    from services.llm_service import LLMExecutionContext
    deepseek = TIMEOUT_SECONDS + LLMExecutionContext.DEEPSEEK_READ_GAP_SECONDS + vr.CONNECT_SECONDS
    openai = vr.OPENAI_CLIENT_TRIES * 2 * TIMEOUT_SECONDS + (vr.OPENAI_CLIENT_TRIES - 1) * vr.OPENAI_RETRY_PAUSE_SECONDS
    return (RETRIES + 1) * max(deepseek, openai) + vr.RETRY_PAUSE_SECONDS * RETRIES


def read_lines(read, pages, rows, reads=READS, deadline=None):
    """(record, {id: completed description}): ask ``read`` for the listed ``rows`` over the rendered ``pages``
    ([(page, [png, ...])]) and keep only what ``completed`` takes from every one of ``reads`` independent answers, word
    for word the same. One request per page that has payments, with that page and the next one (where an entry's last
    lines may continue), so each answer stays short. A failed request leaves that page's payments as read (its error
    is recorded), as does a request that could end after ``deadline`` (time.monotonic()), which is not sent. The
    record says who read what, what it cost, and why any payment stayed as read (answers that differ are kept in it,
    both texts)."""
    images = dict(pages)
    sent = listed(rows)
    found, kept, differ, usage, errors = {}, {}, {}, {}, []
    fixes, fix_differ = {}, {}
    started = time.monotonic()
    for page in sorted({row['page'] for row in sent}):
        on_page = [row for row in sent if row['page'] == page]
        shown = [(number, images[number]) for number in (page, page + 1) if number in images]
        if not shown or shown[0][0] != page:
            kept.update({row['id']: 'page_not_rendered' for row in on_page})
            continue
        if deadline is not None and time.monotonic() + request_seconds() > deadline:
            kept.update({row['id']: 'deferred' for row in on_page})
            continue
        # The page's reads are sent together (each independent of the others).
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=reads) as pool:
            futures = [pool.submit(read, shown, on_page) for _ in range(reads)]
        answers = []
        for future in futures:
            try:
                answer, used = future.result()
            except Exception as error:  # noqa: BLE001 - this page's payments stay as read
                _add(usage, getattr(error, 'usage', None))
                errors.append(dict(page=page, error=type(error).__name__, message=str(error)[:200]))
                answers = None
                continue
            _add(usage, used)
            if answers is not None:
                answers.append(completed(on_page, answer, sent) + (printed_first_lines(on_page, answer, sent),))
        if answers is None:
            for row in on_page:
                kept.setdefault(row['id'], 'request_failed')
            continue
        for row in on_page:
            printed = [answer[2].get(row['id']) for answer in answers]
            if printed[0] and all(text == printed[0] for text in printed):
                fixes[row['id']] = printed[0]
            elif any(printed):
                fix_differ[row['id']] = printed
            texts = [answer[0].get(row['id']) for answer in answers]
            if texts[0] and all(text == texts[0] for text in texts):
                found[row['id']] = texts[0]
            elif any(texts):
                if all(texts):
                    kept[row['id']] = 'reads_differ'
                    differ[row['id']] = texts
                else:
                    kept[row['id']] = next((answer[1][row['id']] for answer in answers if row['id'] in answer[1]),
                                           'reads_differ')
                    differ[row['id']] = texts
            else:
                why = next((answer[1][row['id']] for answer in answers if row['id'] in answer[1]), None)
                if why:
                    kept[row['id']] = why
    record = dict(prompt_version=PROMPT_VERSION, reads=reads, seconds=round(time.monotonic() - started, 1),
                  usage=usage, rows=len(sent), completed=len(found), kept=kept, differ=differ, errors=errors,
                  lines=found, first_lines={row['id']: row['first_line'] for row in sent
                                            if row['id'] in found or row['id'] in fixes},
                  first_line_fixes=fixes, first_line_differ=fix_differ,
                  looked=sorted(row['id'] for row in sent if kept.get(row['id']) not in RETRIED))
    return record, found


# ---------------------------------------------------------------------------
# Saved statements: the description lines of payments already saved from page images
# ---------------------------------------------------------------------------

# Why a payment stayed as read that a later --read tries again (nothing was read for it).
RETRIED = ('request_failed', 'page_not_rendered', 'deferred')
# Stored on the saved statement (financial_source_documents.metadata) by read_saved_lines, applied by
# saved_reading_replacement.refresh_descriptions(from_images=True).
METADATA_KEY = 'vision_description_lines'
ROW_REASON_PREFIX = 'Read from page image'


def page_of(row):
    """The page a payment was read from (its saved review row), else None."""
    provenance = row.provenance or {}
    review = provenance.get('statement_import_review') or {}
    page = review.get('manual_page') or (provenance.get('locator') or {}).get('page')
    return int(page) if isinstance(page, int) or str(page or '').isdigit() else None


def read_from_image(row):
    """Whether this payment was saved as read from a page image, untouched since: its saved review row is a page-image
    row (id ``manual:vision-...``, reason 'Read from page image'), its description is the one read, and it is not a
    correction of an earlier payment."""
    provenance = row.provenance or {}
    review = provenance.get('statement_import_review') or {}
    return (str(review.get('id') or '').startswith('manual:vision-')
            and str(review.get('reason') or '').startswith(ROW_REASON_PREFIX)
            and _words(review.get('description')) == _words(row.description)
            and not provenance.get('correction') and page_of(row) is not None)


def money_text(minor, exponent=2):
    if minor is None:
        return None
    sign = '-' if minor < 0 else ''
    whole, part = divmod(abs(int(minor)), 10 ** exponent)
    return f'{sign}{whole}.{part:0{exponent}d}' if exponent else f'{sign}{whole}'


def saved_rows(session, document):
    """The saved statement's current payments read from page images (read_from_image), in page order."""
    from sqlalchemy import select
    from postgres.models.financial import FinancialTransaction
    rows = session.scalars(select(FinancialTransaction).where(
        FinancialTransaction.source_document_id == document.id, FinancialTransaction.ledger_status == 'admitted',
        FinancialTransaction.superseded_by_id.is_(None)))
    return sorted((row for row in rows if read_from_image(row)), key=lambda row: (page_of(row), row.row_index or 0,
                                                                                    str(row.id)))


def completed_from_image(session, row):
    """The first line read from the page image for a payment whose description lines were added since (a
    'page_image_descriptions' correction of a payment read_from_image, its description still that first line and the
    lines added), else None."""
    from uuid import UUID
    from postgres.models.financial import FinancialTransaction
    provenance = row.provenance or {}
    lines = provenance.get('reader_descriptions') or {}
    previous = (provenance.get('correction') or {}).get('previous_transaction_id')
    first = _words(lines.get('previous_description'))
    if lines.get('basis') != 'page_image_descriptions' or not previous or not first or page_of(row) is None:
        return None
    if not (_words(row.description) + ' ').startswith(first + ' '):
        return None
    earlier = session.get(FinancialTransaction, UUID(str(previous)))
    if earlier is None or not read_from_image(earlier) or _words(earlier.description) != first:
        return None
    return first


def first_line_rows(session, document):
    """[(payment, first line read from its page image)]: the saved statement's current payments whose first line came
    from a page image, as read (read_from_image) or since completed by its description lines (completed_from_image),
    in page order."""
    from sqlalchemy import select
    from postgres.models.financial import FinancialTransaction
    rows = session.scalars(select(FinancialTransaction).where(
        FinancialTransaction.source_document_id == document.id, FinancialTransaction.ledger_status == 'admitted',
        FinancialTransaction.superseded_by_id.is_(None)))
    found = []
    for row in rows:
        first = _words(row.description) if read_from_image(row) else completed_from_image(session, row)
        if first:
            found.append((row, first))
    return sorted(found, key=lambda item: (page_of(item[0]), item[0].row_index or 0, str(item[0].id)))


def not_looked(stored, pairs):
    """The pairs (first_line_rows) not yet read with their printed first line (``looked``, kept from the first reading
    with that question on; a page whose request failed, was not rendered or was deferred is not looked at and is read
    again). A payment whose earlier row was looked at (its lines added since) counts as looked. A statement read only
    before (no ``looked``) is read once more for its first lines."""
    looked = set(stored.get('looked') or [])
    return [(row, first) for row, first in pairs if str(row.id) not in looked
            and ((row.provenance or {}).get('correction') or {}).get('previous_transaction_id') not in looked]


def _reader(db, case_id):
    """(provider, model, api key) of the first page-image reader of the chain that can be used now, else a reason."""
    from services.ai_provider_credentials import get_provider_api_key
    from services.financial import vision_reader as vr
    reasons = []
    for reader in vr.chain_page_reader(db, case_id):
        if reader.unavailable or not reader.provider:
            reasons.append(f'{vr.provider_name(reader.provider)} {reader.model}: {reader.unavailable}')
            continue
        return reader.provider, reader.model, get_provider_api_key(db, reader.provider)
    return '; '.join(reasons) or 'no page-image reader'


def read_saved_lines(factory, document_id, resolve_path, *, request_for=None):
    """Read the description lines of a saved statement's payments read from page images (one request per page, by the
    first usable reader of the page-image chain, within the case's reading budget) and store the reading on the
    statement (METADATA_KEY). Nothing is applied here (saved_reading_replacement.refresh_descriptions). Returns the
    record. ``request_for(provider, model, key)`` is injectable for tests. Never sends anything when switched off,
    for a case not approved for page-image reading, or when every payment was already looked at."""
    from datetime import datetime, timezone
    from uuid import UUID
    from sqlalchemy import select
    from postgres.models.evidence import EvidenceFile
    from postgres.models.financial import FinancialSourceDocument
    from services.financial import vision_reader as vr
    record = dict(prompt_version=PROMPT_VERSION, at=datetime.now(timezone.utc).isoformat(), status='skipped')
    if not LINES:
        return dict(record, reason='disabled')
    with factory() as db:
        document = db.get(FinancialSourceDocument, UUID(str(document_id)))
        if document is None or document.status != 'admitted':
            return dict(record, reason='not_saved')
        if not vr.approved(document.case_id):
            return dict(record, reason='case_not_approved')
        stored = ((document.metadata_ or {}).get(METADATA_KEY) or {})
        pairs = not_looked(stored, first_line_rows(db, document))
        rows = [row for row, _ in pairs]
        if not rows:
            return dict(record, reason='nothing_to_read')
        file = db.get(EvidenceFile, document.evidence_file_id)
        reader = _reader(db, document.case_id)
        if isinstance(reader, str):
            return dict(record, status='unavailable', reason='unavailable', message=reader[:300])
        provider, model, key = reader
        exponent = vr._exponent(rows[0].currency)
        exponent = 2 if exponent is None else exponent
        items = [dict(id=str(row.id), page=page_of(row), date=(row.transaction_date or row.posted_date or ''),
                      amount=money_text(row.amount_minor, exponent), direction=row.direction,
                      balance=money_text(row.running_balance_minor, exponent), description=first)
                 for row, first in pairs]
        case_id, path, file_pages = document.case_id, resolve_path(file.stored_path), None
        db.rollback()
    import fitz
    with fitz.open(str(path)) as pdf:
        file_pages = pdf.page_count
    pages = sorted({p for item in items for p in (item['page'], item['page'] + 1) if 1 <= p <= file_pages})
    images = vr.render_pages(path, pages, strips=STRIPS)
    shown = dict(images)
    # The most it can cost: each page's requests (its page and the next one) at the reader's output cap.
    reserved = READS * sum(vr.reserve_usd(model, [(p, shown[p]) for p in (page, page + 1) if p in shown], None)
                   for page in sorted({item['page'] for item in items}))
    if not vr._reserve(case_id, reserved):
        return dict(record, status='budget', reason='budget')
    read = (request_for or description_request)(model, key, provider)
    found, _ = read_lines(read, images, items)
    cost = vr.cost_usd(model, found.get('usage') or {})
    vr._add_spend(case_id, cost - reserved)
    record.update(found, status='read', provider=provider, model=model, cost_usd=round(cost, 6), pages=pages)
    with factory() as db:
        document = db.scalar(select(FinancialSourceDocument).where(FinancialSourceDocument.id == UUID(str(document_id)))
                             .with_for_update().execution_options(populate_existing=True))
        metadata = dict(document.metadata_ or {})
        before = metadata.get(METADATA_KEY) or {}
        merged = dict(record, lines={**(before.get('lines') or {}), **record['lines']},
                      kept={**(before.get('kept') or {}), **record['kept']},
                      first_lines={**(before.get('first_lines') or {}), **record['first_lines']},
                      first_line_fixes={**(before.get('first_line_fixes') or {}), **{
                          key: dict(text=text, provider=provider, model=model, at=record['at'],
                                    prompt_version=PROMPT_VERSION) for key, text in record['first_line_fixes'].items()}},
                      first_line_differ={**(before.get('first_line_differ') or {}), **record['first_line_differ']},
                      looked=sorted(set(before.get('looked') or []) | set(record['looked'])),
                      readings=list(before.get('readings') or []) + [
                          {k: record.get(k) for k in ('at', 'provider', 'model', 'prompt_version', 'cost_usd', 'rows',
                                                      'completed', 'errors', 'pages')}])
        metadata[METADATA_KEY] = merged
        document.metadata_ = metadata
        db.commit()
    log.info('Description lines read from page images: document %s, %s of %s payments completed, $%.4f',
             str(document_id)[:8], record['completed'], record['rows'], cost)
    return record


# ---------------------------------------------------------------------------
# A new reading: its payments' description lines, before it is saved
# ---------------------------------------------------------------------------

def complete_request(factory, case_id, path, request, *, request_for=None, deadline=None):
    """Complete the descriptions of a proved page-image reading's payments (``request``: the statement review
    vision_reader.build_request made, before it is saved) in place, from their description lines (read_lines, by the
    first usable reader of the chain, within the case's budget). Only a payment row's description and reason change.
    Returns the record (stored with the reading's outcome), or None when nothing was sent."""
    from services.financial import vision_reader as vr
    if not LINES:
        return None
    rows = [row for row in request.get('rows') or [] if str(row.get('id') or '').startswith('manual:vision-')
            and not row.get('excluded') and row.get('manual_page')]
    if not rows:
        return None
    with factory() as db:
        reader = _reader(db, case_id)
        db.rollback()
    if isinstance(reader, str):
        return dict(prompt_version=PROMPT_VERSION, status='unavailable', message=reader[:300])
    provider, model, key = reader
    exponent = vr._exponent(request.get('currency'))
    exponent = 2 if exponent is None else exponent
    items = [dict(id=row['id'], page=int(row['manual_page']), date=row.get('date') or '',
                  amount=money_text(int(row['amount_minor']), exponent), direction=row.get('direction'),
                  balance=money_text(int(row['balance_minor']), exponent) if row.get('balance_minor') not in (None, '')
                  else None, description=row.get('description') or '') for row in rows]
    import fitz
    with fitz.open(str(path)) as pdf:
        last = pdf.page_count
    pages = sorted({p for item in items for p in (item['page'], item['page'] + 1) if 1 <= p <= last})
    images = vr.render_pages(path, pages, strips=STRIPS)
    shown = dict(images)
    reserved = READS * sum(vr.reserve_usd(model, [(p, shown[p]) for p in (page, page + 1) if p in shown], None)
                           for page in sorted({item['page'] for item in items}))
    if not vr._reserve(case_id, reserved):
        return dict(prompt_version=PROMPT_VERSION, status='budget', provider=provider, model=model)
    record, found = read_lines((request_for or description_request)(model, key, provider), images, items,
                               deadline=deadline)
    cost = vr.cost_usd(model, record.get('usage') or {})
    vr._add_spend(case_id, cost - reserved)
    by = vr.provider_name(provider)
    for row in rows:
        if row['id'] in found:
            row['description'] = found[row['id']]
            row['reason'] = (str(row.get('reason') or '').rstrip() + ' ' + REASON.format(page=row['manual_page'],
                                                                                          by=by)).strip()
    return dict(record, status='read', provider=provider, model=model, cost_usd=round(cost, 6), pages=pages)
