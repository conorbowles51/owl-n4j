"""Reviewed visual truth: a person reads rendered page images and records what is printed.

Some real statements are scans whose only text is the producer's OCR layer.
``real_truth`` reads that layer, but a reading that reconciles can still be a
consistent misread, and one that does not reconcile cannot say what is
printed. The independent reader for those documents is a person looking at
rendered page images. This module keeps that reading in a plain transcription
a reviewer edits page by page, and turns it into truth ``real_truth`` merges.

Workflow, per document (private files under ``<truth>/visual/``, never
committed):

1. ``draft``: write ``<doc>.ocr.txt`` (what the OCR layer says, unread values
   as ``??``) and a working copy ``<doc>.txt``.
2. The reviewer renders each page (``render``), corrects ``<doc>.txt`` to what
   the image prints, and lists the page on the ``done`` line.
3. ``compile``: ``<doc>.json`` = every period with its status from the same
   reconciliation as tier-A truth (``real_truth.reconcile``), plus counts of
   how the OCR layer differed from the image (``misreads``).

``real_truth`` replaces a document's periods with the reviewed ones when
``visual/<doc>.json`` exists and every page is done.

Transcription format (one statement fact per line, ``#`` starts a comment)::

    doc d0123456789ab
    done 1-3,5
    page 2 stmt 2020-06-01 2020-06-30 no 1 member 123456789 holder A PERSON
    share 0000 open 100.00
    r 06/03 600.00 700.00 | Deposit ...        (amount signed: -20.00 is a debit)
    close 700.00
    hold <reason>          (inside a share: printed pages missing; must be held)
    unverified <reason>    (inside a share: the image cannot settle a value)
    expect <outcome> <reason>  (inside a share: the printed values are confirmed but the period must
                           not be treated as the source states it, e.g. ``expect hold`` for a statement
                           another printed statement of the same account and dates contradicts)
    page 3 cont            (no new statement header: continues the open statement)

Any other issuer (the defaults above are Andrews share statements) is named
once, before the first ``page`` line, and a statement or section with no
share number uses ``-``::

    issuer bbva-mexico BBVA Mexico     (family slug, then the institution as printed)
    currency MXN           (before any page: the document default; inside a share: that period's)
    kind card              (balances are amounts owed; purchases raise them)
    form not_statement <reason>   (the document holds no statement: no periods, status not_statement)
    page 1 stmt 2024-01-01 2024-01-31 no 1 member 4321   (``member`` = account as printed, ``?`` if not)
    page 1 stmt - 2024-01-31 no 1 member 4321   (the statement prints only its closing date: start not printed)
    share - open 1000.00
    r 2024-01-05 -20.00 - | ...   (ISO date where the year is printed; ``-`` = no running balance printed)
    control credits_total 50.00   (printed totals and counts: credits_/debits_total, credits_/debits_/rows_count)
    group purchases        (inside a share: the rows that follow belong to this printed section)
    subtotal purchases -20.00     (the section's printed total, signed as rows are: the rows must add up to it)

A ``page`` line whose ``stmt`` dates, ``no 1`` or member differ from the open
statement starts a new statement; ``cont`` and same-statement pages continue
the share that was open. Rows before any ``share`` on a page belong to it.

A review of only some periods of a document whose text layer reads the rest
(e.g. three periods of a long card file the text-layer reader could not
reconcile) names them, before the first ``page`` line, by their number in the
text-layer reading; the transcribed periods replace exactly those, in order,
and every other period keeps its text-layer reading::

    patch 14,23,33
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

from .real_truth import (ANDREWS_DATES, ANDREWS_TAIL, START_UNPRINTED, Period, document_status, iso, ocr_money,
                         read_pages, reconcile, year_for)

VERSION = 'visual-v1'
MONEY = re.compile(r'^-?\d+\.\d{2}$')


# ---------------------------------------------------------------------------
# Draft from the OCR layer (Andrews share statements)
# ---------------------------------------------------------------------------

def _money_text(text, negative=False):
    value = ocr_money(text, negative)
    if value is None:
        return '??'
    return ('-' if value < 0 else '') + f'{abs(value) // 100}.{abs(value) % 100:02d}'


HEAD_DATES = re.compile(r'(\d{2})/(\d{2})/(\d{2})\s+(\d{2})/(\d{2})/(\d{2})')
VERBS = re.compile(r'^(Deposit|Withdrawal|Recurring|Fee|Dividend|Transfer|Check|Draft|Loan|Payment|Interest|Credit|'
                   r'Debit|ATM|POS|ACH|Share|Adjustment)', re.I)


def draft_andrews(doc_id, pages):
    """The OCR layer's reading as an editable transcription. Every movement line keeps its
    place; a value the layer left unread is ``??`` for the reviewer to read from the image."""
    out = [f'doc {doc_id}', 'done']
    statement = None
    for page in pages:
        head = page.lines[:18]
        dates = next((HEAD_DATES.search(l.text) for l in head if HEAD_DATES.search(l.text)), None)
        if dates is None:
            movements = [l for l in page.lines if re.match(r'^\d{2}/\d{2}\s+(?:\d{2}/\d{2}\s+)?', l.text.strip())
                         and VERBS.match(re.sub(r'^\d{2}/\d{2}\s+(?:\d{2}/\d{2}\s+)?', '', l.text.strip()))]
            if statement is None or not movements:
                out.append(f'page {page.number} skip  # no statement header in the OCR layer')
                continue
            out.append(f'page {page.number} cont  # statement header not read in the OCR layer')
            out.extend(_draft_lines(page.lines))
            continue
        m1, d1, y1, m2, d2, y2 = map(int, dates.groups())
        start, end = iso(2000 + y1, m1, d1), iso(2000 + y2, m2, d2)
        index = next(i for i, l in enumerate(head) if HEAD_DATES.search(l.text))
        number = head[index + 1].text.strip() if index + 1 < len(head) else ''
        body = index + 2 if number.isdigit() else index + 1
        member = next((m.group(1) for l in head for m in [re.search(r'\b(\d{9})\b', l.text)] if m), '?')
        holder = ''
        for i, line in enumerate(page.lines[:body + 8]):
            if re.match(r'^>\d+<$', line.text.strip()) and i + 1 < len(page.lines):
                holder = page.lines[i + 1].text.strip()
                break
        statement = (start, end)
        out.append(f"page {page.number} stmt {start} {end} no {number if number.isdigit() else '?'} member {member}"
                   + (f' holder {holder}' if holder else ''))
        out.extend(_draft_lines(page.lines[body:]))
    return '\n'.join(out) + '\n'


def _draft_lines(lines):
    """Transcription lines for one page body of an Andrews statement."""
    out = []
    for line in lines:
        t = line.text.strip()
        if 'Continued on following page' in t:
            out.append('# continued on following page')
            break
        opened = re.match(r'^(\d{2})/(\d{2})\s+ID\s+([\dOo.\s]{4,6}?)\s+(.+?)\s+Previous\s+Balance\s+(.+)$', t)
        if opened:
            share = re.sub(r'\D', '', opened.group(3).translate(str.maketrans('Oo', '00'))) or '?'
            out.append(f'share {share} open {_money_text(opened.group(5))}')
            continue
        ending = re.match(r'^(\d{2})/(\d{2})\s+Ending\s+Balance\s+(.+)$', t)
        if ending:
            out.append(f'close {_money_text(ending.group(3))}')
            continue
        dated = re.match(r'^(\d{2})/(\d{2})\s+(?:(\d{2})/(\d{2})\s+)?(.*)$', t)
        if not dated or not VERBS.match(dated.group(5)):
            continue
        text = dated.group(5)
        tail = ANDREWS_TAIL.search(text)
        if tail:
            amount = _money_text(tail.group(2), bool(tail.group(1)))
            balance = _money_text(tail.group(4), bool(tail.group(3)))
            text = text[:tail.start()].strip()
        else:
            amount = balance = '??'
        out.append(f'r {dated.group(1)}/{dated.group(2)} {amount} {balance} | {text[:60]}')
    return out


# ---------------------------------------------------------------------------
# Transcription -> periods
# ---------------------------------------------------------------------------

def page_set(text):
    pages = set()
    for part in filter(None, re.split(r'[,\s]+', text.strip())):
        if '-' in part:
            a, b = part.split('-')
            pages.update(range(int(a), int(b) + 1))
        else:
            pages.add(int(part))
    return pages


def _minor(text, line_no):
    if not MONEY.match(text):
        raise ValueError(f'line {line_no}: not a printed amount: {text!s}')
    sign = -1 if text.startswith('-') else 1
    whole, cents = text.lstrip('-').split('.')
    return sign * (int(whole) * 100 + int(cents))


class Transcription:
    """A parsed transcription: statements, their share periods, and what is still unread."""

    def __init__(self, text, strict=True):
        self.strict = strict  # False for an OCR draft: rows whose share header was lost get an unnamed share
        self.doc = None
        self.done = set()
        self.pages = set()
        self.periods = []  # dicts: statement, share, opening, closing, rows, pages, hold, unverified, unread
        self.marks = {}  # page -> what it prints, in order: ('header',), ('open', share, v), ('row', ...), ('close', v)
        self.issuer = dict(family='andrews-share', institution='Andrews Federal Credit Union', currency='USD',
                           kind='deposit')
        self.form = None  # (status, reason) when the document holds no statement
        self.patch = None  # text-layer period numbers the transcribed periods replace, in order
        self._parse(text)

    def _parse(self, text):
        statement, period, page = None, None, None
        for number, raw in enumerate(text.splitlines(), 1):
            line = raw.split('#', 1)[0].strip()
            if not line:
                continue
            word, _, rest = line.partition(' ')
            if word == 'doc':
                self.doc = rest.strip()
            elif word in ('issuer', 'kind', 'form', 'patch') or word == 'currency' and page is None:
                if page is not None:
                    raise ValueError(f'line {number}: {word} belongs before the first page line')
                self._document_line(word, rest.strip(), number)
            elif word == 'currency':
                if period is None:
                    raise ValueError(f'line {number}: currency inside a statement follows its share line')
                if not re.fullmatch(r'[A-Z]{3}', rest.strip()):
                    raise ValueError(f'line {number}: currency needs a three-letter code')
                period['currency'] = rest.strip()
            elif word == 'control':
                fields = rest.split()
                if period is None or len(fields) != 2 or fields[0] not in CONTROLS:
                    raise ValueError(f'line {number}: control needs a share open and one of {", ".join(CONTROLS)}')
                period['controls'][fields[0]] = (_minor(fields[1], number) if fields[0].endswith('_total')
                                                 else _count(fields[1], number))
            elif word in ('group', 'subtotal'):
                fields = rest.split()
                if period is None or len(fields) != (1 if word == 'group' else 2) \
                        or not re.fullmatch(r'[a-z][a-z_]*', fields[0]):
                    raise ValueError(f'line {number}: {word} needs a share open and a section name'
                                     + (' and its printed total' if word == 'subtotal' else ''))
                if word == 'group':
                    period['group'] = fields[0]
                else:
                    period['subtotals'][fields[0]] = _minor(fields[1], number)
            elif word == 'done':
                self.done |= page_set(rest)
            elif word == 'page':
                parts = rest.split()
                page = int(parts[0])
                self.pages.add(page)
                marks = self.marks.setdefault(page, [])
                if len(parts) > 1 and parts[1] == 'skip':
                    continue
                if len(parts) > 1 and parts[1] != 'cont':
                    marks.append(('header',))
                if len(parts) > 1 and parts[1] == 'cont':
                    if statement is None:
                        raise ValueError(f'line {number}: continuation page with no statement open')
                else:
                    fields = re.match(r'stmt (\S+) (\S+) no (\S+) member (\S+)(?: holder (.+))?$', ' '.join(parts[1:]))
                    if not fields:
                        raise ValueError(f'line {number}: page header not understood')
                    start, end, no, member, holder = fields.groups()
                    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', end) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}|-', start):
                        raise ValueError(f'line {number}: statement dates are YYYY-MM-DD (start - when not printed)')
                    key = dict(start=start, end=end, member=member, holder=(holder or '').strip())
                    if statement is None or no == '1' or {k: statement[k] for k in ('start', 'end', 'member')} != \
                            {k: key[k] for k in ('start', 'end', 'member')}:
                        statement = dict(key, pages=[], numbers=[])
                        period = None
                    statement['numbers'].append(no)
                statement['pages'].append(page)
                if period is not None:
                    period['pages'].append(page)
            elif word == 'share':
                fields = re.match(r'(\S+) open (\S+)$', rest.strip())
                if not fields or statement is None:
                    raise ValueError(f'line {number}: share line not understood')
                period = dict(statement=statement, share=fields.group(1), opening=None, closing=None, rows=[],
                              pages=[statement['pages'][-1]], hold=[], unverified=[], expect=None, unread=0,
                              line=number, currency=None, controls={}, group=None, subtotals={})
                if fields.group(2) == '??':
                    period['unread'] += 1
                else:
                    period['opening'] = _minor(fields.group(2), number)
                self.periods.append(period)
                self.marks[page].append(('open', period['share'], period['opening']))
            elif word in ('r', 'close', 'hold', 'unverified', 'expect'):
                if period is None and not self.strict and statement is not None:
                    period = dict(statement=statement, share='?', opening=None, closing=None, rows=[],
                                  pages=[statement['pages'][-1]], hold=[], unverified=[], expect=None, unread=0,
                                  line=number, currency=None, controls={}, group=None, subtotals={})
                    self.periods.append(period)
                if period is None:
                    raise ValueError(f'line {number}: {word} outside a share')
                if word == 'r':
                    body, _, description = rest.partition('|')
                    fields = body.split()
                    if len(fields) != 3:
                        raise ValueError(f'line {number}: row needs date, amount and balance')
                    row = dict(date=fields[0], amount=None, balance=None, description=description.strip(),
                               group=period['group'])
                    if not re.fullmatch(r'\d{2}/\d{2}|\d{4}-\d{2}-\d{2}', fields[0]):
                        raise ValueError(f'line {number}: row date must be MM/DD or YYYY-MM-DD')
                    for key, value in (('amount', fields[1]), ('balance', fields[2])):
                        if key == 'balance' and value == '-':
                            continue  # no running balance printed on this row
                        if value == '??':
                            period['unread'] += 1
                            row['unread'] = True
                        else:
                            row[key] = _minor(value, number)
                    period['rows'].append(row)
                    self.marks[page].append(('row', row['date'], row['amount'], row['balance']))
                elif word == 'close':
                    if rest.strip() == '??':
                        period['unread'] += 1
                    else:
                        period['closing'] = _minor(rest.strip(), number)
                    self.marks[page].append(('close', period['share'], period['closing']))
                elif word == 'expect':
                    outcome, _, reason = rest.strip().partition(' ')
                    if outcome not in ('auto', 'decision', 'hold', 'not_statement', 'duplicate') or not reason:
                        raise ValueError(f'line {number}: expect needs an outcome and a reason')
                    period['expect'] = (outcome, reason.strip())
                else:
                    period[word].append(rest.strip())
            else:
                raise ValueError(f'line {number}: unknown line {word!s}')
        if self.form and self.periods:
            raise ValueError('a document marked not_statement cannot hold statement periods')
        if self.patch is not None and (self.form or len(self.patch) != len(self.periods)):
            raise ValueError(f'patch names {len(self.patch)} periods; the transcription holds {len(self.periods)}')

    def _document_line(self, word, rest, number):
        if word == 'issuer':
            family, _, institution = rest.partition(' ')
            if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)+', family) or not institution.strip():
                raise ValueError(f'line {number}: issuer needs a family slug and the institution')
            self.issuer.update(family=family, institution=institution.strip())
        elif word == 'currency':
            if not re.fullmatch(r'[A-Z]{3}', rest):
                raise ValueError(f'line {number}: currency needs a three-letter code')
            self.issuer['currency'] = rest
        elif word == 'kind':
            if rest not in ('deposit', 'card'):
                raise ValueError(f'line {number}: kind is deposit or card')
            self.issuer['kind'] = rest
        elif word == 'patch':
            if not re.fullmatch(r'\d+(?:,\d+)*', rest) or len(set(rest.split(','))) != len(rest.split(',')):
                raise ValueError(f'line {number}: patch needs distinct period numbers, comma separated')
            self.patch = [int(n) for n in rest.split(',')]
        else:
            form, _, reason = rest.partition(' ')
            if form != 'not_statement' or not reason.strip():
                raise ValueError(f'line {number}: form needs not_statement and a reason')
            self.form = (form, reason.strip())


CONTROLS = ('credits_total', 'debits_total', 'credits_count', 'debits_count', 'rows_count')


def _count(text, line_no):
    if not re.fullmatch(r'\d+', text):
        raise ValueError(f'line {line_no}: not a printed count: {text!s}')
    return int(text)


def _row_iso(text, start, end):
    if '-' in text:
        return text
    month, day = map(int, text.split('/'))
    if start == '-':  # start not printed: a quarter before the closing date bounds the year
        start = (date.fromisoformat(end) - timedelta(days=92)).isoformat()
    return iso(year_for(month, start, end), month, day)


ANDREWS = dict(family='andrews-share', institution='Andrews Federal Credit Union', currency='USD', kind='deposit')


def to_period(item, issuer=None):
    issuer = issuer or ANDREWS
    s = item['statement']
    andrews = issuer['family'] == 'andrews-share'
    share = item['share'] if re.fullmatch(r'\d{4}', item['share']) else None
    period = Period(family=issuer['family'], institution=issuer['institution'],
                    currency=item.get('currency') or issuer['currency'], holder=s['holder'] or None,
                    account=s['member'] if s['member'] != '?' else None,
                    period_start=s['start'] if s['start'] != '-' else None,
                    period_end=s['end'], opening_minor=item['opening'], closing_minor=item['closing'],
                    pages=sorted(set(item['pages'])), share=share if andrews else None, kind=issuer['kind'],
                    controls=dict(item.get('controls') or {}))
    if not andrews and item['share'] not in ('-', '?'):
        period.notes.append(f"section {item['share']}")
    if s['start'] == '-':
        period.notes.append(START_UNPRINTED)
    for row in item['rows']:
        if row.get('unread') or andrews and row['balance'] is None:
            continue  # an unread value is counted in ``unread``; Andrews prints a balance on every row
        record = dict(date=_row_iso(row['date'], s['start'], s['end']), description=row['description'],
                      amount_minor=abs(row['amount']), direction='debit' if row['amount'] < 0 else 'credit')
        if row['balance'] is not None:
            record['balance_after'] = row['balance']
        period.rows.append(record)
    if item.get('subtotals'):
        # A printed section total (e.g. a card's payments, purchases, fees, interest): the rows
        # transcribed under that section, signed as transcribed, must add up to it.
        sections = defaultdict(int)
        for row in item['rows']:
            if not row.get('unread'):
                sections[row.get('group')] += row['amount']
        period.controls['other_checks'] = [
            dict(ok=sections[name] == value, reason=f'{name} rows differ from the printed {name} total')
            for name, value in sorted(item['subtotals'].items())]
    if item['unread']:
        period.problems.append('value not legible on the page image')
    if andrews and period.share is None:
        period.problems.append('share id not read')
    period.problems.extend(item['unverified'])
    return period


def misreads(ocr, reviewed):
    """How the OCR layer differed from the image, by class (counts), compared page by page so a
    lost statement header or share line does not shift everything after it."""
    counts = Counter()
    for page in sorted(reviewed.marks):
        printed, layer = reviewed.marks[page], ocr.marks.get(page, [])
        if ('header',) in printed and ('header',) not in layer:
            counts['statement_header_unread'] += 1
        opened = {m[1]: m[2] for m in layer if m[0] == 'open'}
        for _, share, value in (m for m in printed if m[0] == 'open'):
            if share not in opened:
                counts['share_header_unread'] += 1
            elif opened[share] != value:
                counts['opening_unread' if opened[share] is None else 'opening_misread'] += 1
        closed = {m[1]: m[2] for m in layer if m[0] == 'close'}
        for _, share, value in (m for m in printed if m[0] == 'close'):
            if share not in closed:
                counts['ending_line_unread'] += 1
            elif closed[share] != value:
                counts['closing_unread' if closed[share] is None else 'closing_misread'] += 1
        a = [m[1:] for m in layer if m[0] == 'row']
        b = [m[1:] for m in printed if m[0] == 'row']
        for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_opcodes():
            if tag == 'equal':
                continue
            if tag == 'replace' and i2 - i1 == j2 - j1:
                for x, y in zip(a[i1:i2], b[j1:j2]):
                    if x[0] != y[0]:
                        counts['date_misread'] += 1
                    for value, real, name in ((x[1], y[1], 'amount'), (x[2], y[2], 'balance')):
                        if value == real:
                            continue
                        if value is None:
                            counts[f'{name}_unread'] += 1
                        elif value == -real:
                            counts[f'{name}_sign_misread'] += 1
                        else:
                            counts[f'{name}_misread'] += 1
                continue
            if tag == 'replace':
                counts['line_misread'] += min(i2 - i1, j2 - j1)
            counts['line_lost_by_layer'] += max(0, (j2 - j1) - (i2 - i1))
            counts['line_invented_by_layer'] += max(0, (i2 - i1) - (j2 - j1))
    return {k: v for k, v in sorted(counts.items()) if v}


def compile_document(reviewed_text, ocr_text=None, page_count=None):
    """``visual/<doc>.json`` content: every period with its status, and the OCR-layer misread counts."""
    reviewed = Transcription(reviewed_text)
    # A patch reads only the pages of the periods it replaces; the rest keep their text-layer reading.
    total = set(range(1, page_count + 1)) if page_count and reviewed.patch is None else reviewed.pages
    pending = sorted(total - reviewed.done)
    periods = []
    numbers = reviewed.patch or range(1, len(reviewed.periods) + 1)
    for index, item in zip(numbers, reviewed.periods):
        period = to_period(item, reviewed.issuer)
        status, reasons = reconcile(period)
        if item['hold']:
            status, reasons = 'incomplete', list(item['hold'])
        record = dict(period.__dict__, id=f'{reviewed.doc}#{index}', truth_status=status, truth_reasons=reasons,
                      truth_source='visual')
        if item['expect']:
            record.update(expected_override=item['expect'][0], expected_reason=item['expect'][1])
        periods.append(record)
    return dict(version=VERSION, doc=reviewed.doc, pages_done=sorted(reviewed.done), pages_pending=pending,
                complete=not pending, periods=periods, issuer=reviewed.issuer['family'],
                form=dict(status=reviewed.form[0], reason=reviewed.form[1]) if reviewed.form else None,
                misreads=misreads(Transcription(ocr_text, strict=False), reviewed) if ocr_text else {},
                period_status=dict(Counter(p['truth_status'] for p in periods)), patch=reviewed.patch)


# ---------------------------------------------------------------------------
# Merge into real_truth results
# ---------------------------------------------------------------------------

def apply_visual(result, visual):
    """A document result with its periods replaced by the reviewed visual reading.

    Only a complete review (every page done) replaces the reading; a partial
    one leaves the document as it was. The document status follows the
    periods as in ``real_truth.document_truth``.
    """
    if not visual or not visual.get('complete') or visual.get('doc') != result.get('id'):
        return result
    issuer = visual.get('issuer') or result.get('issuer')
    if visual.get('form'):
        return dict(result, status=visual['form']['status'], reason=visual['form']['reason'], periods=[],
                    period_status={}, issuer=issuer, truth_source='visual', statements_complete=True,
                    visual_misreads=visual.get('misreads', {}))
    if visual.get('patch'):
        return _apply_patch(result, visual, issuer)
    periods = [dict(p) for p in visual['periods']]
    statuses = Counter(p['truth_status'] for p in periods)
    # Every page was read, so every period's status is final: verified, incomplete
    # (printed pages absent) or unverified with the reason the image cannot settle.
    status = document_status(statuses, reviewed=True)
    # Every page was read, so every statement the document holds is known even
    # where a period is incomplete (held by design): an admitted item matching
    # none of them is wrong, not a gap in the truth.
    return dict(result, status=status, periods=periods, period_status=dict(statuses), truth_source='visual',
                issuer=issuer, statements_complete=all(p['truth_status'] in ('verified', 'incomplete') for p in periods),
                visual_misreads=visual.get('misreads', {}))


def _apply_patch(result, visual, issuer):
    """The text-layer reading with the reviewed periods put in place of the ones they name.

    Refused (the result is returned unchanged) unless every named period exists in
    the text-layer reading. The document is final once every period that is not
    verified has been read from the images."""
    replaced = {p['id']: dict(p) for p in visual['periods']}
    existing = {p['id'] for p in result.get('periods') or []}
    if not replaced or not set(replaced) <= existing:
        return result
    periods = [replaced.get(p['id'], p) for p in result['periods']]
    statuses = Counter(p['truth_status'] for p in periods)
    reviewed = all(p.get('truth_source') == 'visual' for p in periods if p['truth_status'] != 'verified')
    return dict(result, status=document_status(statuses, reviewed=reviewed), periods=periods,
                period_status=dict(statuses), truth_source='visual', visual_patch=sorted(replaced), issuer=issuer,
                statements_complete=all(p['truth_status'] in ('verified', 'incomplete') for p in periods),
                visual_misreads=visual.get('misreads', {}))


def load_visual(directory, doc_id):
    path = Path(directory) / f'{doc_id}.json' if directory else None
    if path is None or not path.exists():
        return None
    return json.loads(path.read_text())


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------

def render(pdf, page, out, dpi=130, clip=None):
    """One page (1-based) to PNG for the reviewer; ``clip`` = (top, bottom) as fractions of the height."""
    import fitz
    with fitz.open(str(pdf)) as document:
        p = document[page - 1]
        rect = p.rect
        if clip:
            rect = fitz.Rect(rect.x0, rect.y0 + clip[0] * rect.height, rect.x1, rect.y0 + clip[1] * rect.height)
        p.get_pixmap(dpi=dpi, clip=rect).save(str(out))
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='command', required=True)
    d = sub.add_parser('draft')
    d.add_argument('--doc', required=True)
    d.add_argument('--docs', type=Path, required=True)
    d.add_argument('--visual', type=Path, required=True)
    d.add_argument('--cache', type=Path)
    c = sub.add_parser('compile')
    c.add_argument('--doc', required=True)
    c.add_argument('--docs', type=Path, required=True)
    c.add_argument('--visual', type=Path, required=True)
    args = parser.parse_args(argv)
    args.visual.mkdir(parents=True, exist_ok=True)
    args.visual.chmod(0o700)
    pdf = args.docs / f'{args.doc}.pdf'
    if args.command == 'draft':
        text = draft_andrews(args.doc, read_pages(pdf, args.cache))
        (args.visual / f'{args.doc}.ocr.txt').write_text(text)
        working = args.visual / f'{args.doc}.txt'
        if not working.exists():
            working.write_text(text)
        print(f'draft written ({text.count(chr(10))} lines)')
        return 0
    import fitz
    with fitz.open(str(pdf)) as document:
        page_count = document.page_count
    ocr = args.visual / f'{args.doc}.ocr.txt'
    result = compile_document((args.visual / f'{args.doc}.txt').read_text(),
                              ocr.read_text() if ocr.exists() else None, page_count)
    (args.visual / f'{args.doc}.json').write_text(json.dumps(result, indent=1, default=str) + '\n')
    # Counts only on stdout.
    print(json.dumps(dict(doc=result['doc'], complete=result['complete'], pending=len(result['pages_pending']),
                          period_status=result['period_status'], misreads=result['misreads'])))
    return 0


if __name__ == '__main__':
    sys.exit(main())
