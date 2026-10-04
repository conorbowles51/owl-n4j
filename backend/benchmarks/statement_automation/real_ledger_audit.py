"""Audit what the live ledger already admitted against independent tier-A truth. Read-only.

For every admitted live statement period whose source file is a real document
with tier-A truth (``real_truth.py``), this compares the admitted transactions
and balances with the truth period of the same document, account, currency and
closing date:

* ``agrees``: same opening and closing (where both are recorded) and exactly
  the same rows by amount, direction and date;
* ``convention_only``: the same amounts and directions, differing only by a
  recorded convention: dates taken from the printed posting date (or another
  date column), or a balance kept with the opposite sign;
* ``disagrees``: missing, extra or different rows, or different balances. This
  is a wrong admission, unless the truth itself is only ``ocr_reconciled``;
* ``no_truth_period``: the document has truth, but no truth period matches.

The live database is read inside a READ ONLY transaction. The shareable
summary holds counts only; per-period detail goes to the private ``--out``.

From ``backend/`` with the service environment loaded::

    python -m benchmarks.statement_automation.real_ledger_audit --truth /mnt/owl-data/fin-real/truth \\
        --inventory /mnt/owl-data/fin-real/inventory.json --out /mnt/owl-data/fin-real/audit
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
JUDGED = ('verified', 'ocr_reconciled')


def _digits(value):
    return re.sub(r'\D', '', value or '')


def live_periods(session, evidence_file_ids):
    """Admitted statement periods and their admitted transactions for the given evidence files."""
    from sqlalchemy import bindparam, text
    if not evidence_file_ids:
        return []
    rows = session.execute(text(
        "SELECT p.id, d.evidence_file_id, d.id, p.period_start, p.period_end, p.currency, p.opening_balance_minor, "
        "p.closing_balance_minor, a.identifier_normalised, a.identifier_as_printed, d.case_id "
        "FROM financial_statement_periods p JOIN financial_source_documents d ON d.id = p.source_document_id "
        "LEFT JOIN financial_accounts a ON a.id = p.account_id "
        "WHERE d.status = 'admitted' AND d.evidence_file_id IN :files").bindparams(
            bindparam('files', expanding=True)), dict(files=list(evidence_file_ids))).all()
    periods = {r[0]: dict(period_id=str(r[0]), evidence_file_id=str(r[1]), source_document_id=str(r[2]),
                          period_start=r[3].isoformat() if r[3] else None, period_end=r[4].isoformat() if r[4] else None,
                          currency=r[5], opening_minor=r[6], closing_minor=r[7],
                          account=_digits(r[8] or r[9]), case_id=str(r[10]), rows=[]) for r in rows}
    if not periods:
        return []
    for r in session.execute(text(
            "SELECT statement_period_id, amount_minor, direction, transaction_date, posted_date, value_date, "
            "effective_date, ordering_date "
            "FROM financial_transactions WHERE ledger_status = 'admitted' AND statement_period_id IN :ids").bindparams(
                bindparam('ids', expanding=True)), dict(ids=list(periods))).all():
        when = r[3] or r[4]
        if when is None and (r[5] or r[6] or r[7]):
            periods[r[0]]['undated_with_other_date'] = periods[r[0]].get('undated_with_other_date', 0) + 1
        periods[r[0]]['rows'].append((int(r[1]), r[2], when.isoformat() if when else None))
    return list(periods.values())


def compare(live, truth):
    """Classification and counts for one live period against one truth period.

    Two conventions are told apart from disagreement: a balance recorded with
    the opposite sign (a card balance owed kept as a negative balance), and row
    dates recorded as the printed posting date instead of the transaction date.
    """
    # A row whose statement prints no date is compared without one.
    undated = {(r['amount_minor'], r['direction']) for r in truth['rows'] if r.get('date_unprinted')}
    def key(amount, direction, when):
        return (amount, direction, None if (amount, direction) in undated else when)
    truth_rows = Counter(key(r['amount_minor'], r['direction'], r['date']) for r in truth['rows'])
    posted_rows = Counter(key(r['amount_minor'], r['direction'], r.get('posted_date') or r['date']) for r in truth['rows'])
    live_rows = Counter(key(*row) for row in live['rows'])
    missing = sum((truth_rows - live_rows).values())
    extra = sum((live_rows - truth_rows).values())
    undated_truth = Counter((a, d) for a, d, _ in truth_rows.elements())
    undated_live = Counter((a, d) for a, d, _ in live_rows.elements())
    if not missing and not extra:
        rows = 'same'
    elif live_rows == posted_rows:
        rows = 'posting_dates'
    elif undated_truth == undated_live:
        rows = 'dates_differ'
    else:
        rows = 'different'
    balances = []
    for name in ('opening', 'closing'):
        value, expected = live[name + '_minor'], truth[name + '_minor']
        if value is None or value == expected:
            continue
        balances.append(name + ('_sign' if value == -expected else ''))
    sign_only = all(b.endswith('_sign') for b in balances)
    if rows == 'same' and not balances:
        outcome = 'agrees'
    elif rows != 'different' and sign_only:
        outcome = 'convention_only'
    else:
        outcome = 'disagrees'
    return dict(outcome=outcome, rows=rows, missing_rows=missing, extra_rows=extra, balances=balances,
                undated_missing=sum((undated_truth - undated_live).values()),
                undated_extra=sum((undated_live - undated_truth).values()),
                account_agrees=bool(truth.get('account')) and truth['account'] in live['account'])


def _day_offsets(live_rows, truth_rows):
    """Live date minus printed date, in days, for rows paired by amount and direction (in order)."""
    from datetime import date
    pending = defaultdict(list)
    for r in truth_rows:
        pending[(r['amount_minor'], r['direction'])].append(r['date'])
    offsets = Counter()
    for amount, direction, when in live_rows:
        queue = pending.get((amount, direction))
        if queue and when:
            printed = queue.pop(0)
            offsets[(date.fromisoformat(when) - date.fromisoformat(printed)).days] += 1
    return offsets


def best_truth(live, candidates):
    def overlap(truth):
        a = Counter((r['amount_minor'], r['direction']) for r in truth['rows'])
        b = Counter((amount, direction) for amount, direction, _ in live['rows'])
        return sum((a & b).values())
    same = [t for t in candidates if t['period_end'] == live['period_end']
            and (not live['currency'] or t['currency'] == live['currency'])]
    if not same:
        return None
    if len(same) > 1:
        accounts = [t for t in same if t.get('account') and t['account'] in live['account']]
        same = accounts or same
    return max(same, key=overlap)


def audit(truth_dir, inventory, session):
    by_file = {}
    for doc in inventory['documents']:
        for record in doc['evidence_files']:
            by_file[record['evidence_file_id']] = doc['id']
    truths = {}
    for path in Path(truth_dir, 'periods').glob('*.json'):
        result = json.loads(path.read_text())
        periods = [p for p in result.get('periods', []) if p['truth_status'] in JUDGED]
        if periods:
            truths[result['id']] = dict(status=result['status'], periods=periods, family=periods[0]['family'])
    files = [f for f, doc in by_file.items() if doc in truths]
    live = live_periods(session, files)
    detail, counts, details = [], defaultdict(Counter), defaultdict(Counter)
    for period in live:
        doc = by_file.get(period['evidence_file_id'])
        truth = best_truth(period, truths[doc]['periods'])
        if truth is None:
            entry = dict(outcome='no_truth_period', family=truths[doc]['family'])
        else:
            entry = dict(compare(period, truth), family=truth['family'], truth_id=truth['id'],
                         truth_status=truth['truth_status'])
        entry.update(doc=doc, live_period_id=period['period_id'], live_rows=len(period['rows']), case=period['case_id'],
                     live_rows_without_transaction_or_posted_date=sum(1 for r in period['rows'] if r[2] is None),
                     of_which_with_another_date=period.get('undated_with_other_date', 0))
        if truth is not None and entry['rows'] == 'dates_differ':
            entry['day_offsets'] = dict(_day_offsets(period['rows'], truth['rows']))
        detail.append(entry)
        key = entry['family'] + (' (OCR-layer truth)' if entry.get('truth_status') == 'ocr_reconciled' else '')
        counts[key][entry['outcome']] += 1
        if entry['outcome'] != 'no_truth_period':
            details[key][f"rows {entry['rows']}"] += 1
            for name in entry['balances']:
                details[key][name] += 1
    rows = Counter()
    for entry in detail:
        if entry['outcome'] != 'no_truth_period':
            rows['live_rows'] += entry['live_rows']
            rows['missing_rows'] += entry['missing_rows']
            rows['extra_rows'] += entry['extra_rows']
            rows['live_rows_without_transaction_or_posted_date'] += entry['live_rows_without_transaction_or_posted_date']
            rows['of_which_with_another_date'] += entry['of_which_with_another_date']
    per_case = Counter((e['case'], e['truth_id']) for e in detail if e.get('truth_id'))
    canonical = {p['id']: p.get('duplicate_of') for t in truths.values() for p in t['periods']}
    admitted = {(e['case'], canonical.get(e['truth_id']) or e['truth_id']) for e in detail if e.get('truth_id')}
    cross_doc = Counter((e['case'], canonical.get(e['truth_id']) or e['truth_id']) for e in detail if e.get('truth_id'))
    offsets = defaultdict(Counter)
    for e in detail:
        for days, n in e.get('day_offsets', {}).items():
            offsets[e['family']][str(days)] += n
    duplicates = dict(same_file_admitted_more_than_once_in_a_case=sum(1 for n in per_case.values() if n > 1),
                      extra_live_periods_from_repeats_in_a_case=sum(n - 1 for n in per_case.values() if n > 1),
                      same_printed_period_admitted_more_than_once_in_a_case=sum(1 for n in cross_doc.values() if n > 1),
                      extra_live_periods_for_the_same_printed_period=sum(n - 1 for n in cross_doc.values() if n > 1),
                      distinct_printed_periods_admitted=len(admitted))
    summary = dict(live_admitted_periods_on_truth_documents=len(live), documents_with_truth=len(truths),
                   duplicates=duplicates, day_offsets_where_dates_differ={k: dict(v.most_common(8))
                                                                          for k, v in sorted(offsets.items())},
                   by_family={k: dict(v) for k, v in sorted(counts.items())},
                   overall=dict(sum(counts.values(), Counter())), rows=dict(rows),
                   comparison_by_family={k: dict(v) for k, v in sorted(details.items())},
                   live_periods_per_truth_period=dict(Counter(Counter(e.get('truth_id') for e in detail
                                                                      if e.get('truth_id')).values())),
                   disagreeing_examples=[e['truth_id'] for e in detail if e['outcome'] == 'disagrees'][:10])
    return summary, detail


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--truth', type=Path, required=True)
    parser.add_argument('--inventory', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True, help='private directory for the per-period detail')
    args = parser.parse_args(argv)
    sys.path.insert(0, str(BACKEND))
    from postgres.session import _get_session_local
    from scripts.financial_reader_recovery_estimate import read_only
    inventory = json.loads(args.inventory.read_text())
    with _get_session_local()() as db:
        read_only(db)
        summary, detail = audit(args.truth, inventory, db)
        db.rollback()
    args.out.mkdir(parents=True, exist_ok=True)
    os.chmod(args.out, 0o700)
    (args.out / 'ledger-audit.json').write_text(json.dumps(dict(summary=summary, detail=detail), indent=1) + '\n')
    print(json.dumps(summary, indent=1))


if __name__ == '__main__':
    main()
