"""Layout learning: an unknown bank layout becomes a text-reader profile, through gates (Neil, 2026-10-27).

OPDMD66, 2026-10-27: the Truist layout was unknown, the text reader read nothing, and the page-image reader
read values one statement at a time without ever teaching the text reader, so every later Truist statement
started from zero. The Truist profile was then written by hand. This module makes that loop automatic:

1. trigger: a layout fingerprint on the reader-gap register (``reader_gaps``, fin-holes B) with a held file;
2. examples: page-image readings of that layout's files (``vision_reader``'s approved provider path and cost
   rules) that prove themselves from their own printed arithmetic alone (``prove_example``);
3. draft: a statement-engine profile (DATA, the same keys as ``statement_engine_profiles``) derived from the
   stored text of those files and the proved values (``draft``): it only selects and parameterises rule
   families the engine already has;
4. test: the draft must re-read every example from the text to exactly the proved values (``check``), and
   every other file of the layout is re-read and counted;
5. gates (``scripts/financial_layout_gates.py``): truth set and all-cases stored corpus, old against new, and an
   independent review. Only a profile passing all of them is written to ``learned_profiles.json`` and released
   with the code; the engine loads it after the hand-written profiles and uses it only where none matches.

Nothing here writes to a statement, a review, a batch or an account. The learning state (each layout's step and
the measured reason it stopped) is a JSON file beside the reader-gap register.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
from collections import Counter
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from services.financial import vision_reader as vr

VERSION = 'layout-learning-v1'
# Spend cap for page-image readings of one layout's examples (US dollars, per learning attempt).
LAYOUT_BUDGET_USD = float(os.environ.get('LOUPE_FINANCIAL_LEARN_LAYOUT_BUDGET_USD', '') or 5)
# Examples read per layout at most (files); every other file of the layout is still re-read in the test.
MAX_EXAMPLE_FILES = int(os.environ.get('LOUPE_FINANCIAL_LEARN_MAX_EXAMPLE_FILES', '') or 8)


class RequestFailed(Exception):
    """A page-image request failed (provider error, no credits, timeout); ``reserved``: dollars counted for it."""

    def __init__(self, error, reserved):
        super().__init__('%s: %s' % (type(error).__name__, str(error)[:300]))
        self.reserved = reserved


class NotProved(Exception):
    pass


# ---------------------------------------------------------------------------
# State (case-independent, beside the reader-gap register)
# ---------------------------------------------------------------------------

def state_dir():
    configured = os.environ.get('LOUPE_FINANCIAL_LAYOUT_LEARNING_DIR')
    if configured:
        return Path(configured)
    from config import EVIDENCE_DATA_ROOT
    return Path(EVIDENCE_DATA_ROOT) / 'financial-layout-learning'


@contextmanager
def _locked(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(str(path) + '.lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def _write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(str(path) + '.tmp')
    with open(temporary, 'w') as handle:
        json.dump(data, handle, indent=1, sort_keys=True, default=str)
    os.replace(temporary, path)


def _read_json(path, default):
    try:
        with open(path) as handle:
            return json.load(handle)
    except FileNotFoundError:
        return default


# unread: not learned yet (or its page images could not be requested: retried); learning; draft_failed (reason);
# gates_failed (reason); passed (gates passed, awaiting review and release); live (shipped); read: the text reader
# already proves this layout's statements (a written profile or the plain reader), nothing to learn.
STATES = ('unread', 'learning', 'draft_failed', 'gates_failed', 'passed', 'live', 'read')


def read_state(directory=None):
    data = _read_json(Path(directory or state_dir()) / 'layouts.json', {})
    data.setdefault('layouts', {})
    return data


def set_layout(fingerprint, *, directory=None, **fields):
    """Update one layout's learning record; every step is appended to its history (nothing is overwritten)."""
    path = Path(directory or state_dir()) / 'layouts.json'
    now = datetime.now(timezone.utc).isoformat()
    with _locked(path):
        data = read_state(directory)
        entry = data['layouts'].setdefault(fingerprint, dict(fingerprint=fingerprint, state='unread', history=[]))
        if fields.get('state') and fields['state'] not in STATES:
            raise ValueError('Unknown layout learning state %s' % fields['state'])
        entry.update(fields, updated_at=now)
        entry['history'] = (entry.get('history') or []) + [dict({k: v for k, v in fields.items()
                                                                  if k in ('state', 'reason', 'profile', 'version',
                                                                           'examples_proved', 'cost_usd')}, at=now)]
        data['updated_at'] = now
        _write_json(path, data)
    return entry


# ---------------------------------------------------------------------------
# Examples: whole-file page-image readings proved by their own printed arithmetic
# ---------------------------------------------------------------------------

def _reading_path(file_id, directory=None, model=None):
    """The learning loop's own page-image reading of a file: one per model (``model`` None: the workload's model,
    stored under the file id alone, as the first readings were)."""
    name = '%s.json' % file_id if not model else '%s.%s.json' % (file_id, re.sub(r'[^\w.-]', '_', model))
    return Path(directory or state_dir()) / 'readings' / name


def stored_reading(file_id, pages, directory=None, model=None):
    stored = _read_json(_reading_path(file_id, directory, model), None)
    if stored and stored.get('pages') == list(pages) and stored.get('raw') and (not model or stored.get('model') == model):
        return stored
    return None


def vision_stored_reading(file, pages, model=None):
    """A page-image reading the vision reader already stored on the file covering exactly ``pages`` (by ``model``
    when given), else None."""
    for record in ((file.metadata_ or {}).get(vr.METADATA_KEY) or {}).values():
        if isinstance(record, dict) and record.get('raw') and list(record.get('pages') or []) == list(pages) \
                and (not model or record.get('model') == model):
            return dict(raw=record['raw'], model=record.get('model'), cost_usd=0.0, reused='vision_reader',
                        pages=list(pages))
    return None


def page_reader_for(provider, model_id):
    """``page_reader(db, case_id) -> (model_id, read)`` for a named provider and model (a measurement: the live
    workload setting is not consulted or changed). Fails closed when the model does not take images."""
    from services.ai_model_capabilities import require_images
    from services.ai_provider_credentials import get_provider_api_key

    def page_reader(db, case_id):
        api_key = get_provider_api_key(db, provider)
        if not api_key:
            raise NotProved('No %s key is configured.' % provider)
        require_images(provider, model_id, api_key=api_key, context='layout learning, case %s' % str(case_id)[:8])
        return model_id, vr.document_request(model_id, api_key, provider)
    return page_reader


def read_file_images(db, case_id, file, pages, *, budget, resolve_path, page_reader=None, directory=None,
                     provider=None, model=None):
    """(reading, cost) of every page of one file: stored readings first (no cost), else one request through the
    vision reader's provider path (the workload's model, or ``provider``/``model`` for a measurement).
    ``budget``: dollars left for this layout; NotProved when it is used up or the case is not approved for page
    images. Nothing is written to the file, its statements or a review: the reading is kept in the learning
    state only."""
    import time
    if model and not page_reader:
        page_reader = page_reader_for(provider, model)
    stored = stored_reading(file.id, pages, directory, model) or vision_stored_reading(file, pages, model)
    if stored:
        return stored, 0.0
    if not vr.approved(case_id):
        raise NotProved('Page images of this case may not be sent for reading.')
    model_id, read = (page_reader or vr.openai_page_reader)(db, case_id)
    images = vr.render_pages(resolve_path(file.stored_path), pages)
    reserved = vr.reserve_usd(model_id, images)
    if reserved > budget:
        raise NotProved('The layout\'s page-image budget is used up (%.2f USD left, this file needs up to %.2f).'
                        % (budget, reserved))
    if not vr._reserve(case_id, reserved):
        raise NotProved('The case\'s page-image budget is used up for now.')
    started = time.monotonic()
    try:
        document, usage = read(images)
    except Exception as error:
        # A failed request keeps its reservation counted against the case and the layout (it may be billed).
        raise RequestFailed(error, reserved) from error
    cost = vr.cost_usd(model_id, usage)
    if not (usage or {}).get('completion_tokens'):
        cost = max(cost, reserved)  # an answer reporting no usage is charged what was reserved for it
    vr._add_spend(case_id, cost - reserved)
    reading = dict(raw=document, model=model_id, cost_usd=round(cost, 6), pages=list(pages), file_id=str(file.id),
                   case_id=str(case_id), read_at=datetime.now(timezone.utc).isoformat(), usage=usage,
                   seconds=round(time.monotonic() - started, 1), requested=True)
    _write_json(_reading_path(file.id, directory, model), reading)
    return reading, cost


def _exponent(currency, section):
    if currency:
        return vr._exponent(currency)
    # No currency printed: every amount printed with two decimals, the common case of '$' layouts.
    values = [section['values'].get(k) for k in ('opening_balance', 'closing_balance')] + \
             [r.get('amount') for r in section['rows']]
    return 2 if all(re.fullmatch(r'-?\d+\.\d{2}', str(v or '').strip()) for v in values if v is not None) else None


def prove_example(section, readings, file_pages):
    """One account section of a page-image reading, proved from its own printed figures alone, or NotProved.

    Proved: the period is printed and complete; opening and closing balances are printed; every row is read
    with certainty, dated inside the period; the rows take the opening to the closing to the cent under exactly
    one of the two conventions (a deposit account or an amount owed); every printed running balance agrees;
    every printed credit/debit total and count agrees; the printed page numbering shows no missing page. Nothing
    from the text reading or the case's saved statements is used: the example is what the text reader must
    learn to read."""
    vr.check_page_numbering(readings, file_pages)
    header = section['header']
    start, end = section['period']
    if not (start and end and start <= end):
        raise NotProved('The statement period is not printed completely.')
    currency = (header.get('currency') or '').strip().upper()
    exponent = _exponent(currency, section)
    if exponent is None:
        raise NotProved('The amounts could not be read in one currency.')
    opening = vr.to_minor(section['values'].get('opening_balance'), exponent, signed=True)
    closing = vr.to_minor(section['values'].get('closing_balance'), exponent, signed=True)
    if opening is None or closing is None:
        raise NotProved('The opening or closing balance is not printed.')
    rows = []
    for row in section['rows']:
        amount = vr.row_amount(row, exponent)
        when = vr._iso(row.get('date'))
        if row.get('unreadable') or not amount or not when or row.get('direction') not in ('credit', 'debit'):
            raise NotProved('A payment on page %s could not be read with certainty.' % row['page'])
        if not start <= when <= end:
            raise NotProved('A payment on page %s is dated outside the period.' % row['page'])
        balance = None
        if row.get('balance_after') not in (None, ''):
            balance = vr.to_minor(row['balance_after'], exponent, signed=True)
            if balance is None:
                raise NotProved('A running balance on page %s could not be read.' % row['page'])
        rows.append(dict(date=when, amount_minor=amount, direction=row['direction'], balance_minor=balance,
                         page=row['page'], description=' '.join(str(row.get('description') or '').split())))
    conventions = [liability for liability in (False, True)
                   if opening + sum(vr._movement(r, liability) for r in rows) == closing
                   and vr._running_ok(rows, opening, liability)]
    if not rows:
        quiet = opening == closing and (section.get('no_transactions') or all(
            vr.to_minor(section['values'].get(k), exponent) == 0 for k in ('total_credits', 'total_debits')
            if section['values'].get(k) is not None) and any(section['values'].get(k) is not None
                                                           for k in ('total_credits', 'total_debits')))
        if not quiet:
            raise NotProved('No payments are read and the period does not print that it had none.')
        conventions = [None]
    if len(conventions) != 1:
        raise NotProved('The payments do not take the opening balance to the closing balance to the cent.'
                        if not conventions else 'The payments balance under both conventions.')
    for direction in ('credit', 'debit'):
        printed = section['values'].get('total_%ss' % direction)
        if printed is not None and vr.to_minor(printed, exponent) != sum(
                r['amount_minor'] for r in rows if r['direction'] == direction):
            raise NotProved('The %ss read do not add up to the printed total.' % direction)
        count = section['values'].get('count_%ss' % direction)
        if count is not None and (not str(count).isdigit() or int(count) != sum(r['direction'] == direction for r in rows)):
            raise NotProved('The number of %ss read differs from the printed count.' % direction)
    convention = {False: 'asset_balance', True: 'liability_owed', None: None}[conventions[0]]
    return dict(account_number=header.get('account_number') or '', account_digits=vr._digits(header.get('account_number')),
                institution=header.get('institution') or '', holder=header.get('holder') or '', currency=currency,
                currency_as_printed=header.get('currency_as_printed') or '', period_start=start, period_end=end,
                opening_minor=opening, closing_minor=closing, convention=convention, rows=rows,
                pages=list(section['pages']), exponent=exponent,
                printed_totals={d: vr.to_minor(section['values']['total_%ss' % d], exponent) for d in ('credit', 'debit')
                                if section['values'].get('total_%ss' % d) is not None})


def examples_of(reading, file_pages):
    """[(example or None, reason)] for every account section of one file's page-image reading."""
    try:
        readings = vr.document_pages(reading['raw'], reading['pages'])
        sections = vr.combine(readings)
    except vr.NotProved as reason:
        return [(None, str(reason))]
    if not sections:
        return [(None, 'The page images show no statement account section.')]
    out = []
    for section in sections:
        try:
            out.append((prove_example(section, readings, file_pages), 'proved'))
        except (NotProved, vr.NotProved) as reason:
            out.append((None, str(reason)))
    return out


# ---------------------------------------------------------------------------
# The stored text of a file, as printed lines
# ---------------------------------------------------------------------------

def text_lines(sources):
    """[{page, source, row, text, cells}] of every stored row, in stored order (cells keep their page rectangles)."""
    out = []
    for position, source in enumerate(sources):
        for row in source.get('rows') or []:
            cells = [dict(text=str(c.get('expected_text') or ''), rect=((c.get('locator') or {}).get('rect')))
                     for c in row.get('cells') or []]
            text = ' | '.join(c['text'] for c in cells)
            if text.strip():
                out.append(dict(page=source['page_number'], source=position, row=row.get('row_index'), text=text,
                                cells=cells))
    return out


_MONEY = re.compile(r'(?<![\w.,/])([-+=]\s*)?(\()?\$?\s*(-)?\s*(\d{1,3}(?:,\d{3})+|\d+)\.(\d{2})(\))?(-)?(?![\d/])')
_DATE_TOKEN = re.compile(r'^\W{0,2}(\d{1,2})[/.-](\d{1,2})(?:[/.-](\d{2,4}))?\b')


def amounts(text):
    """[(signed minor, sign printed)] of the two-decimal amounts printed in ``text``."""
    found = []
    for match in _MONEY.finditer(text):
        marker, open_paren, minus, whole, cents, close_paren, trailing = match.groups()
        value = int(whole.replace(',', '')) * 100 + int(cents)
        marker = (marker or '').strip()
        negative = bool(minus or trailing or (open_paren and close_paren) or marker == '-')
        found.append((-value if negative else value, marker or ('-' if negative else '')))
    return found


def label_of(text):
    """The words printed before a line's first figure (the label the engine reads a value under), folded."""
    from services.financial.statement_engine_vocabulary import label
    head = re.split(r'[\d$]', text, maxsplit=1)[0]
    head = head.replace('|', ' ')
    return label(head).strip(' =+-')


def _phrase(text):
    return ' '.join(str(text).lower().split())


# ---------------------------------------------------------------------------
# Draft: a profile derived from the stored text and the proved examples
# ---------------------------------------------------------------------------

def _cover(per_example, limit=2):
    """The fewest labels (at most ``limit``) such that every example prints one of them; None when impossible."""
    remaining = list(range(len(per_example)))
    chosen = []
    while remaining:
        counts = Counter(l for i in remaining for l in per_example[i])
        if not counts or len(chosen) >= limit:
            return None
        best = max(counts, key=lambda l: (counts[l], len(l)))
        chosen.append(best)
        remaining = [i for i in remaining if best not in per_example[i]]
    return chosen


def _example_lines(lines, example):
    pages = set(example['pages'])
    return [l for l in lines if l['page'] in pages]


def balance_labels(files):
    """{'opening': [...], 'closing': [...]}: the label printed before each example's proved balance, the same
    label in every example (a label also printed before the other balance of the same example is refused)."""
    out = {}
    for role, key, other in (('opening', 'opening_minor', 'closing_minor'), ('closing', 'closing_minor', 'opening_minor')):
        per_example = []
        for lines, example in ((f['lines'], e) for f in files for e in f['examples']):
            labels = set()
            for line in _example_lines(lines, example):
                values = [v for v, _ in amounts(line['text'])]
                if example[key] in values or (example[key] and -example[key] in values and example[key] < 0):
                    found = label_of(line['text'])
                    if found and len(found) >= 4:
                        labels.add(found)
            if example[key] == example[other]:
                per_example.append(labels or {''})  # a quiet month prints both balances alike: no evidence either way
                continue
            refused = {label_of(l['text']) for l in _example_lines(lines, example)
                       if example[other] in [v for v, _ in amounts(l['text'])]}
            per_example.append(labels - refused)
        strong = [p for p in per_example if p != {''}]
        chosen = _cover(strong) if strong else None
        if chosen:
            out[role] = chosen
    return out


def summary_components(files, balance):
    """Component labels {'credit_component': [...], 'debit_component': [...]}: the labelled lines printed between
    an example's opening and closing balance lines, each with one direction, whose amounts add up to that example's
    credits and debits in every example; {} when no assignment holds in every example."""
    from services.financial.statement_engine_vocabulary import label
    opening, closing = {label(l) for l in balance.get('opening', [])}, {label(l) for l in balance.get('closing', [])}
    per_example = []
    for lines, example in ((f['lines'], e) for f in files for e in f['examples']):
        own = _example_lines(lines, example)
        starts = [i for i, l in enumerate(own) if label_of(l['text']) in opening]
        # A statement printing several accounts' summaries on one page: the example's own summary is the one
        # whose opening line prints the example's proved opening balance.
        printing = [i for i in starts if abs(example['opening_minor']) in {abs(v) for v, _ in amounts(own[i]['text'])}]
        starts = printing or starts
        found = None
        for start in starts:
            for end in range(start + 1, min(start + 12, len(own))):
                if label_of(own[end]['text']) in closing:
                    found = own[start + 1:end]
                    break
            if found is not None:
                break
        if found is None:
            return {}
        components = []
        for line in found:
            # The component's amount is the first cell printing one (a summary can print a second column of
            # other facts beside it: 'Interest paid this statement period $0.00').
            values = next((amounts(c['text']) for c in line['cells'] if amounts(c['text'])), [])
            name = label_of(line['text'])
            if len(values) != 1 or not name:
                return {}
            components.append((name, abs(values[0][0]), values[0][1]))
        credits = sum(r['amount_minor'] for r in example['rows'] if r['direction'] == 'credit')
        debits = sum(r['amount_minor'] for r in example['rows'] if r['direction'] == 'debit')
        per_example.append((components, credits, debits))
    names = sorted({c[0] for comps, _, _ in per_example for c in comps})
    if not names or len(names) > 8:
        return {}
    for mask in range(1 << len(names)):
        credit_names = {n for i, n in enumerate(names) if mask >> i & 1}
        if all(sum(a for n, a, _ in comps if n in credit_names) == credits
               and sum(a for n, a, _ in comps if n not in credit_names) == debits
               and all(sign in ('', '+' if n in credit_names else '-') for n, _, sign in comps)
               for comps, credits, debits in per_example):
            return dict(credit_component=[n for n in names if n in credit_names],
                        debit_component=[n for n in names if n not in credit_names])
    return {}


def table_totals(files, components):
    """Totals printed per direction table: a line 'TOTAL <component label>' (credit_total / debit_total)."""
    out = {}
    for role, total in (('credit_component', 'credit_total'), ('debit_component', 'debit_total')):
        names = components.get(role) or []
        printed = set()
        for f in files:
            for line in f['lines']:
                name = label_of(line['text'])
                if name.startswith('TOTAL ') and name[6:] in names and amounts(line['text']):
                    printed.add(name)
        if printed:
            out[total] = sorted(printed)
    return out


def headings_printed(files, components):
    """True when every example's pages print a component label alone on a line (a direction table heading)."""
    names = set(components.get('credit_component', []) + components.get('debit_component', []))
    if not names:
        return False
    from services.financial.statement_engine_vocabulary import label
    return all(any(label(l['text'].replace('|', ' ')) in names and not amounts(l['text'])
                   for l in _example_lines(f['lines'], e)) for f in files for e in f['examples'] if e['rows'])


def _overlap(a, b):
    return a and b and min(a[2], b[2]) - max(a[0], b[0]) > 0


def matched_rows(files):
    """[(line, cell index of the amount, example row, date token)]: text lines printing an example row's date and
    amount, each line and each row used once."""
    out = []
    for f in files:
        for example in f['examples']:
            pending = {}
            for row in example['rows']:
                pending.setdefault((row['page'], row['amount_minor']), []).append(row)
            for line in _example_lines(f['lines'], example):
                token = _DATE_TOKEN.match(line['cells'][0]['text']) if line['cells'] else None
                if not token:
                    continue
                for index, cell in enumerate(line['cells']):
                    values = amounts(cell['text'])
                    if len(values) == 1 and (line['page'], abs(values[0][0])) in pending:
                        queue = pending[(line['page'], abs(values[0][0]))]
                        out.append((line, index, queue.pop(0), token))
                        if not queue:
                            del pending[(line['page'], abs(values[0][0]))]
                        break
    return out


def date_order(matches):
    """'mdy' / 'dmy' when every matched text date agrees with its row's proved date one way only, else None."""
    votes, neither = Counter(), 0
    for _, _, row, token in matches:
        first, second = int(token.group(1)), int(token.group(2))
        year, month, day = (int(x) for x in row['date'].split('-'))
        ways = {w for w, (m, d) in (('mdy', (first, second)), ('dmy', (second, first))) if (m, d) == (month, day)}
        if not ways:
            # A line matched to another row of the same amount on its page, or a date the page image misread
            # (the arithmetic proves amounts, never dates): a few are tolerated, never a vote the other way.
            neither += 1
        elif len(ways) == 1:
            votes[next(iter(ways))] += 1
    if len(votes) != 1 or neither > 0.05 * len(matches):
        return None
    return next(iter(votes))


def amount_columns(files, matches):
    """{'amount': [...]} or {'credit': [...], 'debit': [...]}: the printed column heading over the amounts of the
    matched rows (the nearest line above them, on their page, whose cell lies over the amount cell)."""
    by_direction = {'credit': Counter(), 'debit': Counter()}
    for line, index, row, _ in matches:
        rect = line['cells'][index]['rect']
        heading = None
        for other in reversed([l for l in files_lines(files) if l['page'] == line['page'] and l['source'] == line['source']
                               and l['row'] is not None and line['row'] is not None and l['row'] < line['row']]):
            if amounts(other['text']) or _DATE_TOKEN.match(other['cells'][0]['text'] if other['cells'] else ''):
                continue
            over = [c['text'] for c in other['cells'] if _overlap(c['rect'], rect)]
            if over and len(other['cells']) >= 2:
                heading = ' '.join(over[0].split()).upper()
                break
        if heading:
            by_direction[row['direction']][heading] += 1
    total = {d: sum(c.values()) for d, c in by_direction.items()}
    credit = by_direction['credit'].most_common(1)
    debit = by_direction['debit'].most_common(1)
    if credit and debit and credit[0][0] == debit[0][0]:
        return dict(amount=[credit[0][0]])
    out = {}
    if credit and credit[0][1] == total['credit']:
        out['credit'] = [credit[0][0]]
    if debit and debit[0][1] == total['debit']:
        out['debit'] = [debit[0][0]]
    if len(out) == 1:
        return dict(amount=next(iter(out.values())))
    return out


def files_lines(files):
    return [l for f in files for l in f['lines']]


_US_ADDRESS = re.compile(r'\b[A-Z]{2}\s+\d{5}(?:-\d{4})?\b')


def currency_of(files):
    """The examples' printed ISO currency when they agree; else USD when the amounts print a bare '$' and the
    first page prints a US postal address (two-letter state and ZIP code) in its first lines; else None."""
    printed = {e['currency'] for f in files for e in f['examples'] if e['currency']}
    if len(printed) == 1:
        return next(iter(printed))
    if printed:
        return None
    dollar = any('$' in (e['currency_as_printed'] or '') for f in files for e in f['examples']) or all(
        any('$' in l['text'] for l in f['lines']) for f in files)
    def address(f):
        first = min(l['page'] for l in f['lines'])
        head = [re.sub(r'(?<=\d) (?=\d)', '', l['text'].replace('|', ' ')) for l in f['lines'] if l['page'] == first][:12]
        return any(_US_ADDRESS.search(' '.join(h.split())) for h in head)
    return 'USD' if dollar and all(address(f) for f in files) else None


def match_phrases(layout_files, corpus_phrases, limit=3):
    """{'all': [...]}: printed phrases (one cell each, no digit) found in every file of the layout and in no other
    stored file of any case (``corpus_phrases``: {file id: set of phrases}); None when no such pair exists."""
    own = {f['file_id'] for f in layout_files}
    common = None
    for f in layout_files:
        phrases = cell_phrases(f['lines'])
        common = phrases if common is None else common & phrases
    if not common:
        return None
    others = [p for fid, p in corpus_phrases.items() if fid not in own]
    outside = {phrase: sum(1 for p in others if phrase in p) for phrase in common}
    # Short printed headings first (a title, a web domain): a long notice sentence is reworded more often.
    ranked = sorted(common, key=lambda p: (outside[p], len(p) < 8, len(p)))
    alone = [p for p in ranked if outside[p] == 0]
    if alone:
        return dict(all=alone[:1] + [p for p in ranked if p != alone[0]][:limit - 1])
    for i, a in enumerate(ranked[:40]):
        for b in ranked[i + 1:40]:
            if not any(a in p and b in p for p in others):
                return dict(all=[a, b])
    return None


def cell_phrases(lines):
    """Lower-case phrases of single cells printing letters and no digit, 2 to 10 words (or a web domain)."""
    found = set()
    for line in lines:
        for cell in line['cells']:
            phrase = _phrase(cell['text'])
            if re.search(r'\d', phrase) or not re.search(r'[a-z]', phrase):
                continue
            words = phrase.split()
            if 2 <= len(words) <= 10 or re.fullmatch(r'[a-z][a-z-]+\.(com|net|org|bank|com\.mx)', phrase):
                found.add(phrase)
    return found


FLAGS = ('account_number_heading', 'direction_headings', 'account_heading', 'account_suffix_heading',
         'statement_account', 'client_line')


def base_draft(files, layout_files, corpus_phrases, name):
    """The profile derived from the text and the examples, before the rule-family search; (profile, notes)."""
    from services.financial import field_proposals as fp
    notes = []
    examples = [e for f in files for e in f['examples']]
    institutions = Counter(e['institution'] for e in examples if e['institution'])
    institution = max(institutions, key=lambda i: (institutions[i], len(i))) if institutions else ''
    if institutions and not all(fp.same_institution(institution, i) for i in institutions):
        notes.append('The examples name different banks: %s' % ', '.join(sorted(institutions)))
    conventions = {e['convention'] for e in examples if e['convention']}
    match = match_phrases(layout_files, corpus_phrases)
    if not match:
        notes.append('No printed phrase tells this layout apart from every other stored file.')
    profile = dict(name=name, match=match or dict(all=['\x00never']))
    if institution:
        profile['institution'] = institution
    currency = currency_of(files)
    if currency:
        profile['currency'] = currency
    else:
        notes.append('The currency is not printed and could not be derived.')
    if len(conventions) == 1:
        profile['convention'] = next(iter(conventions))
    matches = matched_rows(files)
    order = date_order(matches)
    if order:
        profile['date_order'] = order
    balance = balance_labels(files)
    for role in ('opening', 'closing'):
        if role not in balance:
            notes.append('No label is printed before the %s balance of every example.' % role)
    components = summary_components(files, balance)
    labels = dict(balance, **components, **table_totals(files, components))
    if labels:
        profile['labels'] = labels
    columns = amount_columns(files, matches)
    if columns:
        profile['columns'] = columns
    if headings_printed(files, components):
        profile['direction_headings'] = True
    return profile, notes


# ---------------------------------------------------------------------------
# Test: the draft re-reads every example from its text to exactly the proved values
# ---------------------------------------------------------------------------

def keyed(profile):
    """``profile`` under a name carrying a hash of its rules: the engine keeps recent readings by (file, profile
    name), so two drafts sharing a name would be served one reading (every trial of the search the first's)."""
    rules = json.dumps({k: v for k, v in profile.items() if k not in ('name', 'learned')}, sort_keys=True)
    base = profile['name'].split('~')[0]
    return dict(profile, name='%s~%s' % (base, hashlib.sha1(rules.encode()).hexdigest()[:12]))


@contextmanager
def with_profiles(profiles):
    """The engine reading with exactly ``profiles`` (written ones, then any marked ``learned``) for this block, the
    router picking as it does live: a written profile first, a learned one only for a file no written one reads
    (learned_profiles.pick). Until the engine consults the registry itself, the router's pick is wrapped here."""
    from services.financial import learned_profiles as lp, statement_engine_profiles as sep
    saved, saved_learned = sep.PROFILES, lp._OVERRIDE
    sep.PROFILES = tuple(p for p in profiles if not p.get('learned'))
    lp._OVERRIDE = tuple(p for p in profiles if p.get('learned'))
    try:
        yield  # read through the engine's own hook (statement_engine_profiles.matching_profile, profile_named)
    finally:
        sep.PROFILES, lp._OVERRIDE = saved, saved_learned


def draft_fingerprint(name):
    """The layout a draft is for, from its name ('learned-<fingerprint>', '~<hash>' added by ``keyed``)."""
    base = str(name or '').split('~')[0]
    return base[len('learned-'):] if base.startswith('learned-') else base


def written_profiles(excluding=None):
    """The profiles live now: the engine's written profiles and the registry's live learned ones (as learned).
    ``excluding``: a draft's name; the live learned version of its layout (the one release retires for it,
    matched by the fingerprint the entry records) is left out."""
    from services.financial import learned_profiles as lp, statement_engine_profiles as sep
    found = tuple(p for p in sep.PROFILES if not p.get('learned')) + tuple(
        p for p in lp.live() if p['name'] not in lp.LEARNED_OFF)
    if not excluding:
        return found
    layout = draft_fingerprint(excluding)
    return tuple(p for p in found if not (isinstance(p.get('learned'), dict)
                                          and p['learned'].get('fingerprint') == layout))


def live_and_draft(profile):
    """(before, after) for the gates: exactly the profiles live now, and the same with the learned versions the
    draft replaces swapped for the draft (a written profile is never left out)."""
    profile = keyed(profile)
    return written_profiles(), written_profiles(profile['name']) + (dict(profile, learned=True),)


@contextmanager
def candidate(profile):
    """The engine's profiles with ``profile`` among them as a learned profile, for this block only."""
    from services.financial import learned_profiles as lp
    lp.check_rules(profile)
    with with_profiles(written_profiles(profile['name']) + (dict(profile, learned=True),)):
        yield


def text_reading(sources):
    """The statements the engine serves for a file through normal routing (plain reading or a matching profile)."""
    from services.financial.statement_engine import read_statements
    from services.financial.statement_engine_routing import _profiled
    return _profiled(sources, read_statements(sources))


def _balances(statement):
    found = {}
    for row in statement['_rows']:
        if row['kind'] == 'balance':
            text = str(row['fields'].get('description') or '').lower()
            for role in ('opening', 'closing'):
                if role in text and row['fields'].get('balance') not in (None, ''):
                    found[role] = int(row['fields']['balance'])
    return found


def statement_values(statement):
    """The values of one text-read statement that an example is compared on."""
    balances = _balances(statement)
    rows = sorted((r['fields'].get('date'), r['fields'].get('direction'), int(r['fields'].get('amount_minor') or 0),
                   r['page_number']) for r in statement['_rows'] if r['kind'] == 'transaction' and not r['excluded'])
    return dict(account=str(statement.get('account_reference') or ''), period_start=statement.get('period_start'),
                period_end=statement.get('period_end'), opening_minor=balances.get('opening'),
                closing_minor=balances.get('closing'), rows=rows, holder=statement.get('holder') or '',
                institution=statement.get('institution') or '', currency=statement.get('currency') or '',
                proved=bool((statement.get('engine') or {}).get('proved')), reason=(statement.get('engine') or {}).get('reason'))


def _same_account(digits, account):
    account = vr._digits(account)
    return bool(digits) and bool(account) and (digits == account or (len(digits) >= 4 and account.endswith(digits))
                                               or (len(account) >= 4 and digits.endswith(account)))


DATE_SLACK = 0.02
DATE_DAYS = 3


def compare_example(example, statements, currency=None):
    """'exact' or the first difference between a proved example and the text reading of its file."""
    from services.financial import field_proposals as fp
    day_after = None
    if example['period_start']:
        day_after = (date.fromisoformat(example['period_start']) + timedelta(days=1)).isoformat()
    # The period's start as the text reader dates it may be the day after the image reading's: a statement
    # printing 'Your previous balance as of 10/13' starts on 10/14 (the previous statement ended on 10/13;
    # fin-truist, measured on 30 Truist periods). The arithmetic proves neither; the text's start stands when
    # no proved row is dated on the image's start day.
    shifted = day_after and not any(r['date'] == example['period_start'] for r in example['rows'])
    candidates = [s for s in statements if _same_account(example['account_digits'], s['account'])
                  and s['period_end'] == example['period_end']
                  and (s['period_start'] == example['period_start'] or (shifted and s['period_start'] == day_after))]
    if not candidates:
        same = [s for s in statements if _same_account(example['account_digits'], s['account'])]
        return 'period not read' if same else 'account not read'
    if len(candidates) > 1:
        return 'read twice'
    s = candidates[0]
    if not s['proved']:
        return 'not proved (%s)' % s['reason']
    notes = ['period starts the day after the printed previous balance'] if s['period_start'] != example['period_start'] else []
    rows = sorted((r['date'], r['direction'], r['amount_minor'], r['page']) for r in example['rows'])
    if s['rows'] != rows:
        # Amount, direction and page are proved by the arithmetic and must agree row for row; a date is not
        # proved by it (a page image can misread '02/22' as 02/23), so the text's date stands where the two
        # disagree on at most DATE_SLACK rows of the statement, each one reported.
        undated = lambda rs: Counter((d, a, p) for _, d, a, p in rs)
        if undated(s['rows']) != undated(rows):
            missing, extra = undated(rows) - undated(s['rows']), undated(s['rows']) - undated(rows)
            return 'rows differ (%s missing, %s extra)' % (sum(missing.values()), sum(extra.values()))
        missing = sorted((Counter(rows) - Counter(s['rows'])).elements())
        extra = sorted((Counter(s['rows']) - Counter(rows)).elements())
        dated = len(missing)
        if dated > int(DATE_SLACK * len(rows)):
            return 'dates differ (%s rows)' % dated
        # Each differing date pairs with a row of the same amount, direction and page, inside the period and at
        # most DATE_DAYS from the image's date (a misread digit, never a different month or year).
        for image_row in missing:
            near = [t for t in extra if t[1:] == image_row[1:] and s['period_start'] <= t[0] <= s['period_end']
                    and abs((date.fromisoformat(t[0]) - date.fromisoformat(image_row[0])).days) <= DATE_DAYS]
            if not near:
                return 'dates differ (%s rows)' % dated
            extra.remove(near[0])
        if dated:
            notes.append('%s image date%s differ from the text' % (dated, 's' if dated > 1 else ''))
    if s['opening_minor'] != example['opening_minor']:
        return 'opening differs' if s['opening_minor'] is not None else 'opening not read'
    if s['closing_minor'] != example['closing_minor']:
        return 'closing differs' if s['closing_minor'] is not None else 'closing not read'
    if example['holder'] and not fp.same_holder(example['holder'], s['holder']):
        return 'holder differs (%s / %s)' % (example['holder'], s['holder'])
    if example['institution'] and not fp.same_institution(example['institution'], s['institution']):
        return 'bank differs'
    # The expected currency comes from the example or the layout's own text (currency_of), never from the draft
    # under test; a period whose currency nothing proves is not exact.
    expected = example['currency'] or currency
    if not s['currency']:
        return 'currency not read'
    if not expected:
        return 'currency not proved (neither the page images nor the text show it)'
    if s['currency'] != expected:
        return 'currency differs (%s / %s)' % (expected, s['currency'])
    return ('exact (%s)' % '; '.join(notes)) if notes else 'exact'


def check(profile, files, others=(), fast=False):
    """{'examples': [(file, account, period, outcome)], 'exact': n, 'total': n, 'other_files': {...}}: every example
    re-read from its stored text with the draft among the engine's profiles; ``others``: the layout's other files
    ({file_id, sources}), whose proved periods are counted."""
    from services.financial.statement_engine import read_statements
    outcomes, other = [], {}
    profile = keyed(profile)
    # The currency every period must be read in: the example's own, else the one the layout's text shows
    # (currency_of), never the draft's; a period read with none is never exact (an image printing a bare '$' leaves the
    # example without one, which must not let a profile read no currency).
    currency = currency_of(files)
    with candidate(profile):
        for f in files:
            if fast:
                # The search: the draft applied directly (one reading); the routed reading decides the result.
                reading, used = read_statements(f['sources'], profile=profile), profile['name']
            else:
                reading, used = text_reading(f['sources'])
            statements = [statement_values(s) for s in reading]
            for example in f['examples']:
                outcome = compare_example(example, statements, currency)
                if outcome.startswith("exact") and used != profile["name"]:
                    outcome = 'read without the draft (%s)' % used
                outcomes.append((f['file_id'], example['account_number'], example['period_start'], example['period_end'],
                                 outcome))
        for f in others:
            reading, used = text_reading(f['sources'])
            other[f['file_id']] = dict(profile=used, periods=len(reading),
                                       proved=sum(1 for s in reading if (s.get('engine') or {}).get('proved')))
    exact = sum(1 for o in outcomes if o[-1].startswith('exact'))
    return dict(examples=outcomes, exact=exact, total=len(outcomes), other_files=other,
                score=sum(_SCORE.get(o[-1].split(' (')[0], 3) for o in outcomes))


# How close an example came, for the rule-family search only (an example counts only when exact).
_SCORE = {'exact': 6, 'account not read': 0, 'period not read': 1, 'read twice': 1, 'not proved': 2,
          'rows differ': 2}


def draft(files, layout_files, corpus_phrases, name, others=()):
    """(profile, test, notes): the derived profile, then the rule families (FLAGS) added one at a time while each
    raises the number of examples re-read exactly; the smallest profile with the most exact examples."""
    profile, notes = base_draft(files, layout_files, corpus_phrases, name)
    best = check(profile, files, fast=True)
    tried = [('', best['exact'])]
    while best['exact'] < best['total']:
        options = []
        singles = [((flag, True),) for flag in FLAGS if not profile.get(flag)]
        if not profile.get('date_order'):
            singles += [(('date_order', order),) for order in ('mdy', 'dmy')]
        # Two families together (an account per section heading and a direction per table heading).
        trials = singles + [a + b for i, a in enumerate(singles) for b in singles[i + 1:] if a[0][0] != b[0][0]]
        for flags in trials:
            flag = '+'.join('%s=%s' % f for f in flags)
            trial = dict(profile, **dict(flags))
            try:
                result = check(trial, files, fast=True)
            except ValueError:
                continue
            tried.append((flag, result['exact']))
            options.append(((result['exact'], result['score'], -len(flags)), flag, trial, result))
        if not options:
            break
        rank, flag, trial, result = max(options, key=lambda o: o[0])
        if rank[:2] <= (best['exact'], best['score']):
            break
        profile, best = trial, result
    result = check(profile, files, others)
    return profile, result, notes


# ---------------------------------------------------------------------------
# Gates: nothing already read may be lost or changed, and the truth set stays 0 wrong / 0 lost / 0 double
# ---------------------------------------------------------------------------

def _matched(sources, profiles):
    """The name of the profile the router would pick for ``sources`` among ``profiles`` (None: plain reading)."""
    from services.financial import statement_engine_profiles as sep
    with with_profiles(profiles):
        found = sep.matching_profile(sep.profile_text(sources), sep.furniture_text(sources))
    return found['name'] if found else None


def _read_with(sources, profiles):
    with with_profiles(profiles):
        return [statement_values(s) for s in text_reading(sources)[0]]


def _period_key(values):
    return (vr._digits(values['account']), values['period_start'], values['period_end'], values['currency'])


def _served(values):
    return {k: values[k] for k in ('rows', 'opening_minor', 'closing_minor', 'holder', 'institution', 'currency',
                                   'proved')}


def corpus_gate(profile, corpus, out=None):
    """Every stored file (``corpus``: iterable of (file_id, case_id, sources)) read without and with ``profile``.

    The router consults the profiles only to pick the one matching a file's printed text (other lookups are by
    name), so a file whose pick is unchanged reads identically: those are counted, not re-read. A file whose pick
    changes is read both ways: a period proved before must be proved after with the same values ('lost' /
    'changed' otherwise); every served period's values are compared too. Returns
    {files, unchanged, rematched: [...], lost, changed, gained, passed}."""
    base_profiles, with_profile = live_and_draft(profile)
    profile = keyed(profile)
    files = unchanged = 0
    rematched, lost, changed, gained, doubled, served_changed = [], [], [], [], [], []
    for file_id, case_id, sources in corpus:
        files += 1
        try:
            before, after = _matched(sources, base_profiles), _matched(sources, with_profile)
        except Exception as error:  # a file the router cannot read either way is reported, never skipped
            lost.append(dict(file=file_id, case=case_id, error='%s: %s' % (type(error).__name__, str(error)[:200])))
            continue
        if before == after:
            unchanged += 1
            continue
        try:
            old, new = _read_with(sources, base_profiles), _read_with(sources, with_profile)
            old_served, new_served = _catalog_with(sources, base_profiles), _catalog_with(sources, with_profile)
        except Exception as error:  # noqa: BLE001 - a file that cannot be compared fails the gate, with its reason
            lost.append(dict(file=file_id, case=case_id, before=before, after=after,
                             error='%s: %s' % (type(error).__name__, str(error)[:200])))
            continue
        old_by, new_by = {}, {}
        for v in old:
            old_by.setdefault(_period_key(v), []).append(v)
        for v in new:
            new_by.setdefault(_period_key(v), []).append(v)
        entry = dict(file=file_id, case=case_id, before=before, after=after, proved_before=sum(v['proved'] for v in old),
                     proved_after=sum(v['proved'] for v in new))
        for key, values in old_by.items():
            for v in values:
                if not v['proved']:
                    continue
                same = [n for n in new_by.get(key, []) if n['proved']]
                if not same:
                    lost.append(dict(entry, period=key))
                elif not any(_served(n) == _served(v) for n in same):
                    changed.append(dict(entry, period=key))
        for key, values in new_by.items():
            before_count = sum(o['proved'] for o in old_by.get(key, []))
            after_count = sum(v['proved'] for v in values)
            if after_count > 1 and after_count > before_count:
                doubled.append(dict(entry, period=key, proved=after_count))  # one period's money counted twice
            if after_count and not before_count:
                gained.append(dict(entry, period=key))
        # What the live route serves (statement_import_catalog.statement_catalog: the engine with the family readers'
        # cross-check): every statement served before must be served after, identical but for the profile's name
        # (compared as multisets), and a newly served statement must not cover days an old one serves for the same
        # account (the same money served twice under a different start, currency or pages).
        missing = sum((Counter(old_served) - Counter(new_served)).values())
        added = list((Counter(new_served) - Counter(old_served)).elements())
        overlapping = [a for a in added if any(_overlaps(json.loads(a), json.loads(o)) for o in old_served)]
        # Two new statements covering the same days of one account are the same money twice, unless that very
        # pair was served before.
        overlapping += [a for i, a in enumerate(added) for b in added[i + 1:] if _overlaps(json.loads(a), json.loads(b))]
        if missing or overlapping:
            served_changed.append(dict(entry, served_before=len(old_served), served_after=len(new_served),
                                       missing=missing, overlapping=len(overlapping)))
        # The same for the proved periods of the engine reading: a new proved period overlapping an old proved one
        # of the same account, not identical to it, counts that money twice.
        old_proved = [v for v in old if v['proved']]
        fresh = [v for v in new if v['proved'] and not any(_served(v) == _served(o) and _period_key(v) == _period_key(o)
                                                             for o in old_proved)]
        for i, v in enumerate(fresh):
            if any(_overlaps(_as_statement(v), _as_statement(o)) for o in old_proved + fresh[i + 1:]):
                doubled.append(dict(entry, period=_period_key(v), overlapping=True))
        entry.update(served_before=len(old_served), served_after=len(new_served))
        rematched.append(entry)
        if out:
            out('rematched %s %s -> %s proved %s -> %s' % (file_id[:8], before, after, entry['proved_before'],
                                                           entry['proved_after']))
    return dict(files=files, unchanged=unchanged, rematched=rematched, lost=lost, changed=changed, gained=gained,
                doubled=doubled, served_changed=served_changed,
                passed=not lost and not changed and not doubled and not served_changed)


def _as_statement(values):
    return dict(account_reference=values['account'], period_start=values['period_start'],
                period_end=values['period_end'])


def _overlaps(a, b):
    """Two statements of one file that may be the same account (the same digits, the same last four, or either
    without any) and whose printed periods share a day."""
    x, y = vr._digits(a.get('account_reference')), vr._digits(b.get('account_reference'))
    if x and y and x != y and x[-4:] != y[-4:]:
        return False
    if not all((a.get('period_start'), a.get('period_end'), b.get('period_start'), b.get('period_end'))):
        return False
    return a['period_start'] <= b['period_end'] and b['period_start'] <= a['period_end']


def _catalog_with(sources, profiles):
    """The statements the live route serves for ``sources`` with exactly ``profiles``, each as a canonical JSON
    string without the fields that name the profile (engine_profile, currency_source)."""
    from services.financial.statement_import_catalog import statement_catalog
    with with_profiles(profiles):
        catalog = statement_catalog(sources)
    out = []
    for statement in catalog.get('statements') or []:
        public = {k: v for k, v in statement.items() if k not in ('engine_profile', 'currency_source', '_rows')}
        if isinstance(public.get('engine'), dict):
            public['engine'] = {k: v for k, v in public['engine'].items() if 'profile' not in k and 'seconds' not in k}
        out.append(json.dumps(public, sort_keys=True, default=str))
    return out


def truth_gate(rematched, sources_of, truth_dir, inventory):
    """The truth set on the files whose reading the profile changes (every other file reads identically, so its
    truth outcome is unchanged): each proved period read with the profile, judged against the independent truth
    (benchmarks real_ledger_audit.compare). wrong = a proved period that disagrees with its truth or must be held;
    double = one truth period proved twice; lost = a truth period agreeing before and not after.
    ``rematched``: corpus_gate()['rematched']; ``sources_of(file_id)`` -> stored sources."""
    from benchmarks.statement_automation import real_ledger_audit as audit
    by_file = {r['evidence_file_id']: d['id'] for d in inventory['documents'] for r in d['evidence_files']}
    truths = {}
    for path in Path(truth_dir, 'periods').glob('*.json'):
        result = json.loads(path.read_text())
        periods = [p for p in result.get('periods', []) if p['truth_status'] in audit.JUDGED]
        if periods:
            truths[result['id']] = periods
    judged, wrong, double, lost = [], [], [], []
    if not truths:
        # A missing or empty truth set is never a pass.
        return dict(judged=[], wrong=[], double=[], lost=[], truth_documents=0, passed=False,
                    reason='No tier-A truth periods were found in %s.' % truth_dir)
    for entry in rematched:
        doc = by_file.get(entry['file'])
        if doc not in truths:
            continue
        outcomes = {}
        for side in ('before', 'after'):
            outcomes[side] = _truth_outcomes(sources_of(entry['file']), entry, side, truths[doc], audit)
        for truth_id, items in outcomes['after'].items():
            if len(items) > 1:
                double.append(dict(file=entry['file'], truth=truth_id, n=len(items)))
            for outcome in items:
                if outcome not in ('agrees', 'convention_only'):
                    wrong.append(dict(file=entry['file'], truth=truth_id, outcome=outcome))
        for truth_id, items in outcomes['before'].items():
            if 'agrees' in items and 'agrees' not in outcomes['after'].get(truth_id, []):
                lost.append(dict(file=entry['file'], truth=truth_id))
        judged.append(dict(file=entry['file'], doc=doc, before={k: v for k, v in outcomes['before'].items()},
                           after={k: v for k, v in outcomes['after'].items()}))
    return dict(judged=judged, wrong=wrong, double=double, lost=lost, truth_documents=len(truths),
                passed=not wrong and not double and not lost)


_GATE_PROFILES = {}


def _truth_outcomes(sources, entry, side, periods, audit):
    """{truth period id: [outcome per proved period read]} for one file read with the 'before' or 'after' pick."""
    reading = _read_with(sources, _GATE_PROFILES[side])
    found = {}
    for v in reading:
        if not v['proved']:
            continue
        live = dict(account=v['account'], currency=v['currency'], period_end=v['period_end'],
                    opening_minor=v['opening_minor'], closing_minor=v['closing_minor'], holder=v['holder'],
                    rows=[(amount, direction, when) for when, direction, amount, _ in v['rows']])
        truth = audit.best_truth(live, periods)
        if truth is None:
            found.setdefault('(no truth period %s %s)' % (v['account'], v['period_end']), []).append('no_truth_period')
            continue
        found.setdefault(truth['id'], []).append(audit.judge(live, truth)['outcome'])
    return found


def gates(profile, corpus, sources_of, truth_dir, inventory, out=None):
    """Both data gates for one draft: {'corpus': corpus_gate, 'truth': truth_gate, 'passed': bool}."""
    from services.financial import learned_profiles as lp, statement_engine_profiles as sep
    before, after = live_and_draft(profile)
    _GATE_PROFILES.update(before=before, after=after)
    from services.financial import statement_engine_routing as routing
    corpus_result = corpus_gate(profile, corpus, out)
    corpus_result['routing'] = dict(generic_only=bool(routing.generic_only()), generic_enabled=bool(routing.generic_enabled()))
    # What the pass is for: exactly these rules, with these profiles switched off (a release needs none off).
    conditions = dict(rules_hash=lp.rules_hash(profile), profiles_off=sorted(sep.PROFILES_OFF | lp.LEARNED_OFF),
                      fingerprint=draft_fingerprint(profile['name']),
                      replaced=sorted(p['name'] for p in before if p not in after and p.get('learned')),
                      # The learned profiles live when the gates read: a release is refused unless the registry
                      # still holds exactly these live (anything released since was never read with this draft).
                      live_learned=sorted(p['name'] for p in before if p.get('learned')))
    truth_result = truth_gate(corpus_result['rematched'], sources_of, truth_dir, inventory)
    return dict(corpus=corpus_result, truth=truth_result, conditions=conditions,
                passed=corpus_result['passed'] and truth_result['passed'])


# ---------------------------------------------------------------------------
# Drafting by a language model (provider-neutral): the model proposes, the same tests and gates decide
# ---------------------------------------------------------------------------

# USD per million tokens (input, output) for drafting: Loupe's pricing table (ai_pricing_rates).
DRAFT_PRICES = {'gpt-5.6-terra': (2.50, 15.00), 'gpt-5.6-sol': (5.00, 30.00), 'deepseek-v4-pro': (0.435, 0.87),
                'deepseek-flash': (0.14, 0.28)}
DRAFT_ATTEMPTS = int(os.environ.get('LOUPE_FINANCIAL_LEARN_DRAFT_ATTEMPTS', '') or 3)
DRAFT_LINES_PER_FILE = 260

DRAFT_INSTRUCTIONS = '''You write a reading profile for a bank statement layout. A profile is DATA that selects and
parameterises the rule families of a statement reading engine; it never contains code. The engine reads the
statement's stored TEXT (rows of cells, each row printed below as 'cell | cell | ...', with its page number).

The profile format, as documented by the engine:
{doc}

Two written profiles of other layouts, as examples of the format:
{examples}

The layout's printed text ({files} file(s); dated movement lines included; long files cut):
{text}

What the page images of these statements proved (each period's opening + rows = closing, to the cent; printed
totals matched). Your profile must make the engine read EXACTLY these values from the text:
{proved}

Rules:
- 'match': printed phrases (lower case is fine) present in EVERY file of this layout and specific to it: a
  web address, a section title, a column heading. Never a name, an amount, a date or an account number.
- Labels are the printed words exactly as on the statement (the engine compares case-insensitively).
- Every period must be read with its currency: when the statement prints no ISO currency code, set 'currency'.
- Use only keys the format documents; omit what this layout does not need.
{feedback}
Answer with one JSON object: {{"profile": {{...}}, "reasoning": "one short paragraph"}}.'''


def _profile_examples(exclude=()):
    from services.financial import statement_engine_profiles as sep
    chosen = [p for p in sep.PROFILES if not p.get('learned') and p['name'] not in exclude
              and p['name'] in ('navy-federal', 'kapital-mexico-brokerage')]
    return '\n'.join(json.dumps(p, ensure_ascii=False) for p in chosen)


def _layout_text(files):
    out = []
    for f in files[:2]:
        lines = f['lines'][:DRAFT_LINES_PER_FILE]
        out.append('=== file %s ===' % f['file_id'][:8])
        page = None
        for line in lines:
            if line['page'] != page:
                page = line['page']
                out.append('--- page %s ---' % page)
            out.append(line['text'][:220])
        if len(f['lines']) > len(lines):
            out.append('... (%s more lines)' % (len(f['lines']) - len(lines)))
    return '\n'.join(out)


def _proved_summary(files):
    derived = currency_of(files)
    out = ['(currency: %s)' % (('%s, as the statements print it or as their bare "$" and US address show' % derived)
                               if derived else 'not printed as an ISO code')]
    for f in files:
        for e in f['examples'][:4]:
            rows = sorted(e['rows'], key=lambda r: (r['page'], r['date']))
            out.append(json.dumps(dict(
                file=f['file_id'][:8], account=e['account_number'], institution=e['institution'], holder=e['holder'],
                currency=e['currency'], period=[e['period_start'], e['period_end']], convention=e['convention'],
                opening=e['opening_minor'], closing=e['closing_minor'], totals=e.get('printed_totals'),
                rows=len(rows), first_rows=[(r['page'], r['date'], r['direction'], r['amount_minor']) for r in rows[:6]]),
                ensure_ascii=False))
    return '\n'.join(out[:11]) + '\n(amounts in minor units: cents)'


def ask_model(provider, model, prompt, api_key, timeout=900):
    """(answer json, usage, seconds) from one JSON request. DeepSeek: thinking enabled at max effort (Neil,
    2026-10-28: drafting compared with deepseek-v4-pro at max thinking). Text only: no image is sent here."""
    import time
    import requests
    started = time.monotonic()
    if provider == 'deepseek':
        response = requests.post('https://api.deepseek.com/chat/completions', timeout=(10, timeout),
                                 headers={'Authorization': 'Bearer %s' % api_key, 'content-type': 'application/json'},
                                 json=dict(model=model, messages=[dict(role='user', content=prompt)],
                                           response_format={'type': 'json_object'}, thinking={'type': 'enabled'},
                                           reasoning_effort='max', max_tokens=64000))
        response.raise_for_status()
        data = response.json()
        choice = (data.get('choices') or [{}])[0]
        text, finish, usage = (choice.get('message') or {}).get('content') or '', choice.get('finish_reason'), data.get('usage') or {}
    elif provider == 'openai':
        from openai import OpenAI
        client = OpenAI(api_key=api_key, timeout=timeout)
        answer = client.chat.completions.create(model=model, messages=[dict(role='user', content=prompt)],
                                                response_format={'type': 'json_object'}, max_completion_tokens=32000)
        choice = answer.choices[0]
        text, finish = choice.message.content or '', choice.finish_reason
        usage = dict(prompt_tokens=answer.usage.prompt_tokens, completion_tokens=answer.usage.completion_tokens)
    else:
        raise ValueError('Drafting is not available for %s' % provider)
    if finish != 'stop':
        raise ValueError('The draft answer was incomplete (%s)' % finish)
    rate_in, rate_out = DRAFT_PRICES.get(model, (5.00, 30.00))
    usage = dict(prompt_tokens=usage.get('prompt_tokens') or 0, completion_tokens=usage.get('completion_tokens') or 0)
    usage['cost_usd'] = round(usage['prompt_tokens'] * rate_in / 1e6 + usage['completion_tokens'] * rate_out / 1e6, 6)
    return json.loads(text), usage, round(time.monotonic() - started, 1)


def llm_draft(files, name, provider, model, api_key, *, attempts=None, exclude=(), out=None, ask=None):
    """(profile or None, result, log): the model proposes a profile from the layout's text and the proved
    examples; each proposal is validated and re-read against every example (``check``); a proposal short of
    every example exact goes back with the outcomes, up to ``attempts`` times. The gates decide afterwards,
    exactly as for a derived draft. ``exclude``: written profiles not shown as format examples (a backtest)."""
    from services.financial import learned_profiles as lp, statement_engine_profiles as sep
    ask = ask or ask_model
    attempts = attempts or DRAFT_ATTEMPTS
    log, feedback, best = [], '', (None, None)
    base = dict(doc=sep.__doc__, examples=_profile_examples(exclude), files=len(files), text=_layout_text(files),
                proved=_proved_summary(files))
    for attempt in range(1, attempts + 1):
        prompt = DRAFT_INSTRUCTIONS.format(feedback=feedback, **base)
        entry = dict(attempt=attempt, provider=provider, model=model, prompt_chars=len(prompt))
        try:
            answer, usage, seconds = ask(provider, model, prompt, api_key)
            entry.update(usage=usage, seconds=seconds)
            # A key answered null is a key not given (the registry refuses typed nulls).
            profile = dict({k: v for k, v in (answer.get('profile') or {}).items() if v is not None}, name=name)
            profile.pop('learned', None)
            lp.check_rules(profile)
        except Exception as error:  # noqa: BLE001 - a failed proposal is recorded and answered with the reason
            entry.update(outcome='invalid', reason='%s: %s' % (type(error).__name__, str(error)[:300]))
            log.append(entry)
            feedback = '\nYour previous answer was rejected: %s. Answer again.\n' % entry['reason']
            if out:
                out('attempt %s: %s' % (attempt, entry['reason']))
            continue
        result = check(profile, files)
        entry.update(outcome='%s/%s exact' % (result['exact'], result['total']), profile=profile,
                     examples=result['examples'])
        log.append(entry)
        if out:
            out('attempt %s: %s exact (%.1fs, $%.4f)' % (attempt, entry['outcome'], seconds, usage['cost_usd']))
        if best[1] is None or result['exact'] > best[1]['exact']:
            best = (profile, result)
        if result['exact'] == result['total']:
            break
        misses = [o for o in result['examples'] if not o[-1].startswith('exact')]
        feedback = ('\nYour previous profile was:\n%s\nRead with it, these examples were not read exactly:\n%s\n'
                    'Revise the profile.\n' % (json.dumps(profile), '\n'.join(
                        '%s %s %s..%s: %s' % (f[:8], account, start, end, outcome)
                        for f, account, start, end, outcome in misses[:12])))
    return best[0], best[1], log


def registry_entry(profile, fingerprint, gate_result, review, examples=(), today=None):
    """The registry entry releasing ``profile`` for layout ``fingerprint`` (``_registry_entry``); any malformed
    input is a ValueError naming it (reported by promote, never a traceback)."""
    try:
        return _registry_entry(profile, fingerprint, gate_result, review, examples, today)
    except ValueError:
        raise
    except Exception as error:  # noqa: BLE001 - e.g. an unknown currency (money.UnknownCurrencyError)
        raise ValueError('%s: %s' % (type(error).__name__, str(error)[:300])) from error


def _listed(result, key):
    value = result.get(key) or []
    if not isinstance(value, list):
        raise ValueError('The gate result\'s %s is not a list.' % key)
    return value


def _registry_entry(profile, fingerprint, gate_result, review, examples=(), today=None):
    """The registry entry releasing ``profile`` for layout ``fingerprint``, or ValueError naming what is missing.

    Only a draft whose gates passed on exactly these rules with every written profile in force (not a backtest),
    on a corpus copy checked against the database, and whose independent review passed. The entry's name carries
    its rules' hash (learned_profiles._servable)."""
    from datetime import date
    from services.financial import learned_profiles as lp
    if not isinstance(profile, dict):
        raise ValueError('The profile is not an object.')
    if not (isinstance(gate_result, dict) and all(isinstance(gate_result.get(k), dict)
                                                  for k in ('corpus', 'truth', 'conditions'))):
        raise ValueError('The gate result is not a complete gates result.')
    rules = {k: v for k, v in profile.items() if k not in ('name', 'learned')}
    digest = lp.rules_hash(rules)
    conditions = gate_result['conditions']
    if not (gate_result.get('passed') is True and gate_result['corpus'].get('passed') is True
            and gate_result['truth'].get('passed') is True):
        raise ValueError('The gates did not pass.')
    if conditions.get('rules_hash') != digest:
        raise ValueError('The gate result is for other rules.')
    if conditions.get('profiles_off') != [] or conditions.get('off_for_this_run'):
        raise ValueError('The gates ran with profiles switched off (a backtest), which is never released.')
    if not conditions.get('corpus_dumped_at'):
        raise ValueError('The gate result records no corpus copy.')
    if review != 'PASS':
        raise ValueError('The independent review did not pass.')
    if not (isinstance(fingerprint, str) and fingerprint.strip()):
        raise ValueError('No layout fingerprint.')
    if conditions.get('fingerprint') != fingerprint:
        raise ValueError('The gate result is for another layout.')
    if not (isinstance(conditions.get('live_learned'), list) and isinstance(conditions.get('replaced'), list)):
        raise ValueError('The gate result does not record the live learned profiles it read (run the gates again).')
    name = 'learned-%s-%s' % (fingerprint, digest[:12])
    gates = dict(corpus_passed=True, truth_passed=True, rules_hash=digest, profiles_off=[],
                 corpus_dumped_at=conditions['corpus_dumped_at'],
                 rematched=len(_listed(gate_result['corpus'], 'rematched')),
                 gained=len(_listed(gate_result['corpus'], 'gained')),
                 truth_judged=len(_listed(gate_result['truth'], 'judged')))
    entry = dict(rules, name=name, learned=dict(
        state='live', fingerprint=fingerprint, version=VERSION, rules_hash=digest, review='PASS', gates=gates,
        examples=list(examples), replaces=list(conditions['replaced']), gated_with=list(conditions['live_learned']),
        live_since=str(today or date.today())))
    lp._servable(entry)
    lp._validated(entry)
    return entry


def release(entry, path=None):
    """Write ``entry`` into the registry (atomically), retiring the layout's previous live version. Returns the
    problems that stopped it ([] when written): the registry no longer holding exactly the live learned profiles
    the gates read, or any entry the engine would refuse. Nothing is written unless there are none."""
    from services.financial import learned_profiles as lp
    path = Path(path or lp.REGISTRY)
    try:
        with open(path.with_name('.learned_profiles.lock'), 'a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)  # two releases never read the same version and drop each other's entry
            return _release(entry, path)
    except Exception as error:  # noqa: BLE001 - malformed input is reported; the registry is only ever replaced whole
        return [('(release)', '%s: %s' % (type(error).__name__, str(error)[:300]))]


def _release(entry, path):
    import os
    import tempfile
    from services.financial import learned_profiles as lp
    try:
        data = lp.registry(path)
    except Exception as error:  # noqa: BLE001
        return [('(registry)', 'the registry cannot be read (%s)' % error)]
    if not (isinstance(data, dict) and isinstance(data.get('profiles', []), list)
            and isinstance(data.get('version', 0), int)
            and all(isinstance(e, dict) and isinstance(e.get('learned', {}), dict) for e in data.get('profiles', []))):
        return [('(registry)', 'the registry is malformed; it is not replaced by a release')]
    live_now = sorted(e.get('name') for e in data.get('profiles', [])
                      if isinstance(e, dict) and (e.get('learned') or {}).get('state') == 'live')
    if 'gated_with' not in entry['learned'] or live_now != sorted(entry['learned']['gated_with']):
        return [('(release)', 'the gates read the live learned profiles %s, the registry now holds %s: run the '
                 'gates again' % (entry['learned'].get('gated_with'), live_now))]
    entries = []
    for old in data.get('profiles', []):
        if old.get('name') == entry['name']:
            continue
        learned = old.get('learned') or {}
        if learned.get('state') == 'live' and learned.get('fingerprint') == entry['learned']['fingerprint']:
            old = dict(old, learned=dict(learned, state='retired', retired_for=entry['name']))
        entries.append(old)
    data = dict(version=int(data.get('version') or 0) + 1, profiles=entries + [entry])
    retired = sorted(e['name'] for e in entries if (e.get('learned') or {}).get('retired_for') == entry['name']
                     and (e.get('learned') or {}).get('state') == 'retired')
    replaced = entry['learned'].get('replaces')
    if replaced is not None and sorted(replaced) != retired:
        return [('(release)', 'the gates replaced %s but the registry retires %s' % (replaced, retired))]
    handle, temporary = tempfile.mkstemp(dir=str(path.parent), prefix='.learned-', suffix='.json')
    try:
        with os.fdopen(handle, 'w') as stream:
            stream.write(json.dumps(data, indent=1, sort_keys=True) + '\n')
        os.chmod(temporary, 0o644)  # the server reads it as another user
        # Checked as the engine will load it (each entry, and one live version per layout) before it replaces
        # the registry: a release that would leave any problem writes nothing.
        found = lp.problems(temporary)
        layouts = Counter((e.get('learned') or {}).get('fingerprint') for e in data['profiles']
                          if isinstance(e, dict) and (e.get('learned') or {}).get('state') == 'live')
        found += [('(registry)', 'two live versions of layout %s' % f) for f, n in layouts.items() if n > 1]
        if found:
            return found
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return []
