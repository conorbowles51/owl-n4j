"""Per-statement comparison: every truth period against what the processor produced.

For each statement document in a real corpus this writes one private file,
``<compare dir>/<doc id>.json``, holding every truth period beside the batch
item the harness paired with it, field by field:

* period dates, opening and closing balance, currency, holder, account;
* every row: matched, missing (printed, not proposed), extra (proposed, not
  printed) or differing (same row, a field differs: date, amount, direction,
  running balance);

and a disagreement class for every difference, so that classes can be fixed
in the processor and counted across all statements. Batch items paired with
no truth period are listed as ``unmatched_item``.

``summary.md`` beside them holds counts only: statements compared out of all
statement documents, and disagreements by family and class. File names,
values and descriptions stay in the per-document files.

The processor's view of a period is the statement proposal the batch item
offers (``read_statement_import``), before any human edit: what an
investigator would be shown.
"""
from __future__ import annotations

import json
import os
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

VERSION = 'compare-v1'
OPENING = re.compile(r'opening\s*balance|previous\s*balance|saldo\s*(anterior|inicial)', re.I)
CLOSING = re.compile(r'closing\s*balance|ending\s*balance|new\s*balance|saldo\s*(final|actual)', re.I)


def _digits(value):
    return re.sub(r'\D', '', value or '')


def _norm(value):
    return re.sub(r'\s+', ' ', (value or '').strip().lower())


def _minor(value):
    if value in (None, ''):
        return None
    try:
        return int(str(value))
    except ValueError:
        return None


def proposal_view(proposal):
    """The facts a statement proposal offers, before any human edit, in truth terms."""
    metadata = proposal.get('metadata') or {}
    dates = proposal.get('period_dates') or {}
    view = dict(period_start=metadata.get('period_start') or dates.get('period_start') or None,
                period_end=metadata.get('period_end') or dates.get('period_end') or None,
                currency=proposal.get('currency') or None, holder=metadata.get('holder') or None,
                account=metadata.get('account_number') or None, opening_minor=None, closing_minor=None, rows=[])
    for row in proposal.get('rows', []):
        fields = row.get('fields') or {}
        if row.get('kind') == 'balance':
            description = fields.get('description') or ''
            role = 'opening_minor' if OPENING.search(description) else 'closing_minor' if CLOSING.search(description) else None
            if role and view[role] is None:
                view[role] = _minor(fields.get('balance'))
            continue
        if row.get('excluded') or row.get('kind') not in ('transaction', 'unresolved'):
            continue
        view['rows'].append(dict(date=fields.get('date') or fields.get('booking_date') or fields.get('value_date') or None,
                                 amount_minor=_minor(fields.get('amount_minor')), direction=fields.get('direction') or None,
                                 balance_after=_minor(fields.get('balance')), description=fields.get('description') or ''))
    return view


def match_rows(truth_rows, rows):
    """``(pairs, missing, extra)``: pairs of (truth index, proposal index), by exact value first,
    then the same amount and direction (date differs), the same date and direction (amount
    differs), and the same amount and date (direction differs), each in printed order."""
    free_t, free_p = list(range(len(truth_rows))), list(range(len(rows)))
    pairs = []
    keys = (lambda r: (r['amount_minor'], r['direction'], r['date']),
            lambda r: (r['amount_minor'], r['direction']),
            lambda r: (r['date'], r['direction']),
            lambda r: (r['amount_minor'], r['date']))
    for key in keys:
        for i in list(free_t):
            want = key(truth_rows[i])
            j = next((j for j in free_p if key(rows[j]) == want), None)
            if j is not None:
                pairs.append((i, j))
                free_t.remove(i)
                free_p.remove(j)
    return sorted(pairs), free_t, free_p


def _field(truth_value, processor_value, missing, differs, equal=None):
    agree = (equal or (lambda a, b: a == b))(truth_value, processor_value)
    cls = None if agree else (missing if processor_value in (None, '') else differs)
    return dict(truth=truth_value, processor=processor_value, agree=agree), cls


def compare_period(truth, view, card=False):
    """Field-by-field comparison of one truth period with one processor view (``view`` may be None)."""
    if view is None:
        return dict(fields={}, rows=dict(matched=0, missing=[], extra=[], differing=[]), classes={'not_detected': 1})
    classes = Counter()
    fields = {}
    checks = (
        ('period_start', None, 'period_start_missing', 'period_start_differs'),
        ('period_end', None, 'period_end_missing', 'period_end_differs'),
        ('currency', lambda a, b: (a or '').upper() == (b or '').upper(), 'currency_missing', 'currency_differs'),
        ('holder', lambda a, b: bool(_norm(a)) and _norm(a) in _norm(b), 'holder_missing', 'holder_differs'),
        ('account', lambda a, b: bool(a) and a in _digits(b), 'account_missing', 'account_differs'),
    )
    for name, equal, missing, differs in checks:
        if name == 'period_start' and truth.get('start_printed') is False:
            continue  # the source prints no start: nothing to compare
        if name in ('holder', 'account') and not truth.get(name):
            continue  # the source prints none: a decision, not a reading
        fields[name], cls = _field(truth.get(name), view.get(name), missing, differs, equal)
        if cls:
            classes[cls] += 1
    for name in ('opening_minor', 'closing_minor'):
        role = name.split('_')[0]
        t, p = truth.get(name), view.get(name)
        fields[name], cls = _field(t, p, f'{role}_balance_missing', f'{role}_balance_differs')
        if cls == f'{role}_balance_differs' and t is not None and p is not None and abs(t) == abs(p):
            cls = 'balance_sign_convention'  # an amount owed kept negative: the same printed value
            fields[name]['agree'] = True
        if cls:
            classes[cls] += 1
    truth_rows = truth.get('rows') or []
    pairs, missing, extra = match_rows(truth_rows, view['rows'])
    differing = []
    for i, j in pairs:
        t, p = truth_rows[i], view['rows'][j]
        diffs = []
        if t['date'] is not None and t['date'] != p['date']:
            diffs.append('row_date_differs')
        if t['amount_minor'] != p['amount_minor']:
            diffs.append('row_amount_missing' if p['amount_minor'] is None else 'row_amount_differs')
        if t['direction'] != p['direction']:
            diffs.append('row_direction_differs')
        if t.get('balance_after') is not None and p['balance_after'] is not None \
                and t['balance_after'] != p['balance_after'] and not (card and abs(t['balance_after']) == abs(p['balance_after'])):
            diffs.append('row_balance_differs')
        if diffs:
            classes.update(diffs)
            differing.append(dict(truth_row=i + 1, processor_row=j + 1, classes=diffs, truth=t, processor=p))
    classes['row_missing'] += len(missing)
    classes['row_extra'] += len(extra)
    return dict(fields=fields,
                rows=dict(truth=len(truth_rows), processor=len(view['rows']), matched=len(pairs) - len(differing),
                          missing=[dict(truth_row=i + 1, **truth_rows[i]) for i in missing],
                          extra=[dict(processor_row=j + 1, **view['rows'][j]) for j in extra], differing=differing),
                classes={k: v for k, v in sorted(classes.items()) if v})


def _outcome(entry, truth):
    """The batch outcome against the expected one, as a class (or None when they agree)."""
    expected = truth['expected'] if truth else None
    ready = bool(entry and entry.get('can_import'))
    if truth is None:
        return 'unmatched_item_offered' if ready else None
    if expected in ('hold', 'not_statement'):
        return 'held_period_offered' if ready else None
    if expected == 'duplicate':
        return 'repeat_offered' if ready and entry.get('status') != 'duplicate_ignored' else None
    return None if ready else 'not_ready'


def build(periods, truths, manifest, views):
    """``{doc id: compare record}`` for every document in the manifest.

    ``periods``: the harness entries (item and truth pairing); ``views``:
    ``{item_id: proposal_view or None}`` for the items whose proposal was read."""
    by_file = defaultdict(list)
    for entry in periods:
        by_file[entry['filename']].append(entry)
    records = {}
    for record in manifest['files']:
        filename = record['filename']
        doc = Path(filename).stem
        entries = by_file.get(filename, [])
        by_truth = {e['truth_id']: e for e in entries if e.get('truth_id')}
        out_periods = []
        for truth in record['periods']:
            entry = by_truth.get(truth['id'])
            view = views.get(entry['item_id']) if entry and entry.get('item_id') else None
            detected = bool(entry and entry.get('item_id'))
            if detected and view is None:
                comparison = dict(fields={}, rows={}, classes={'proposal_not_read': 1})
            else:
                comparison = compare_period(dict(truth, start_printed=truth.get('start_printed', True)), view,
                                            card=bool(re.search(r'card|citi', truth['family'] or '')))
            outcome = _outcome(entry, truth) if detected else None
            classes = dict(comparison['classes'])
            if outcome:
                classes[outcome] = classes.get(outcome, 0) + 1
            out_periods.append(dict(truth_id=truth['id'], family=truth['family'], truth_status=truth.get('truth_status'),
                                    expected=truth['expected'], scored=truth.get('truth_status', 'verified') in ('verified', 'incomplete'),
                                    item_id=entry.get('item_id') if entry else None,
                                    processor_status=entry.get('status') if entry else 'not_detected',
                                    can_import=bool(entry and entry.get('can_import')),
                                    fields=comparison['fields'], rows=comparison['rows'], classes=classes))
        unmatched = []
        for entry in entries:
            if entry.get('item_id') and not entry.get('truth_id'):
                view = views.get(entry['item_id'])
                cls = {'unmatched_item': 1}
                if entry.get('can_import'):
                    cls['unmatched_item_offered'] = 1
                unmatched.append(dict(item_id=entry['item_id'], processor_status=entry.get('status'),
                                      can_import=bool(entry.get('can_import')), processor=view, classes=cls))
        family = Counter(p['family'] for p in record['periods']).most_common(1)
        records[doc] = dict(version=VERSION, doc=doc, family=family[0][0] if family else None,
                            truth_complete=record.get('truth_complete'), periods=out_periods, unmatched_items=unmatched)
    return records


def summarise(records, statement_documents=None):
    """Counts only (no ids, values or names)."""
    by_class, by_family = Counter(), defaultdict(Counter)
    periods, scored, clean = 0, 0, 0
    for record in records.values():
        for p in record['periods'] + [dict(family=record['family'] or 'unknown', scored=True, **u)
                                      for u in record['unmatched_items']]:
            periods += 1
            scored += bool(p.get('scored'))
            if not p['classes']:
                clean += 1
            for cls, n in p['classes'].items():
                by_class[cls] += n
                by_family[p['family']][cls] += 1  # periods (or items) showing the class
    return dict(statements_compared=len(records), statement_documents=statement_documents,
                periods_and_items=periods, scored=scored, without_disagreement=clean,
                classes=dict(by_class.most_common()),
                periods_by_family_and_class={f: dict(c.most_common()) for f, c in sorted(by_family.items())})


def render(summary, label=''):
    lines = ['# Per-statement comparison (counts only)', '']
    if label:
        lines += [label, '']
    total = summary['statement_documents']
    lines.append(f"Statements compared: {summary['statements_compared']}" + (f' / {total} statement documents' if total else ''))
    lines.append(f"Truth periods and unmatched items compared: {summary['periods_and_items']}"
                 f" (scored truth {summary['scored']}); without any disagreement: {summary['without_disagreement']}")
    lines += ['', '## Disagreements by class (occurrences)', '', '| class | count |', '|---|---|']
    lines += [f'| {k} | {v} |' for k, v in summary['classes'].items()]
    lines += ['', '## Periods showing each class, by family', '']
    for family, classes in summary['periods_by_family_and_class'].items():
        lines.append(f"- **{family}**: " + ', '.join(f'{k} {v}' for k, v in classes.items()))
    return '\n'.join(lines) + '\n'


def statement_documents(corpus):
    """Statement documents in the corpus inventory status (all but ``not_statement``), when known."""
    status = Path(corpus) / 'status.json'
    if not status.exists():
        return None
    return sum(1 for row in json.loads(status.read_text()) if row.get('status') != 'not_statement')


def write(directory, records, corpus=None, label=''):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    os.chmod(directory, 0o700)
    for doc, record in records.items():
        (directory / f'{doc}.json').write_text(json.dumps(record, indent=1, default=str) + '\n')
    summary = summarise(records, statement_documents(corpus) if corpus else None)
    summary['written_at'] = datetime.now(timezone.utc).isoformat(timespec='seconds')
    (directory / 'summary.json').write_text(json.dumps(summary, indent=1) + '\n')
    (directory / 'summary.md').write_text(render(summary, label))
    return summary
