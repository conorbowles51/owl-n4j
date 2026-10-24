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
* ``overlap_trimmed``: the period leaves out only the days a saved period of the same ledger account
  covers, and that period holds those rows (the product's overlap trim: counted once, not missing);
* ``must_be_held``: the truth period must not be in the ledger at all (printed
  pages missing, or contradicted by another printed statement), whatever its rows;
* ``no_truth_period``: the document has truth, but no judged truth period matches;
* ``live_period_undated``: the live period was admitted without period dates.

Each judged period also compares its holder with the printed holder (``holder_outcome``): the count of
admitted periods whose holder differs, by family, with the same entity printed otherwise kept apart.

A live file belongs to a truth document when the inventory lists it, when its
bytes are the document's (an upload after the inventory was taken), or, given
``--page-identities``, when every page renders identically to a file of that
document. "The same printed period admitted more than once in a case" counts
live periods of one truth period and its copies (truth ``duplicate_of``),
whichever file and ledger account each was saved through.

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
JUDGED = ('verified', 'ocr_reconciled', 'incomplete')


def _digits(value):
    return re.sub(r'\D', '', value or '')


def _printed_share(printed):
    """A credit-union share number printed at the end of the account identifier ('... Share 0040')."""
    match = re.search(r'(?:share|ID)\s*(\d{4})\s*$', printed or '', re.I) or re.search(r'\s(\d{4})\s*$', printed or '')
    return match.group(1) if match else None


def live_periods(session, evidence_file_ids):
    """Admitted statement periods and their admitted transactions for the given evidence files."""
    from sqlalchemy import bindparam, text
    if not evidence_file_ids:
        return []
    rows = session.execute(text(
        "SELECT p.id, d.evidence_file_id, d.id, p.period_start, p.period_end, p.currency, p.opening_balance_minor, "
        "p.closing_balance_minor, a.identifier_normalised, a.identifier_as_printed, d.case_id, a.metadata->>'share', "
        "p.account_id, d.metadata->'statement_import_request'->>'holder', a.holder_name "
        "FROM financial_statement_periods p JOIN financial_source_documents d ON d.id = p.source_document_id "
        "LEFT JOIN financial_accounts a ON a.id = p.account_id "
        "WHERE d.status = 'admitted' AND d.evidence_file_id IN :files").bindparams(
            bindparam('files', expanding=True)), dict(files=list(evidence_file_ids))).all()
    periods = {r[0]: dict(period_id=str(r[0]), evidence_file_id=str(r[1]), source_document_id=str(r[2]),
                          period_start=r[3].isoformat() if r[3] else None, period_end=r[4].isoformat() if r[4] else None,
                          currency=r[5], opening_minor=r[6], closing_minor=r[7],
                          account=_digits(r[8] or r[9]), case_id=str(r[10]),
                          share=r[11] or _printed_share(r[9]), account_id=str(r[12]) if r[12] else None,
                          holder=(r[13] or '').strip(), account_holder=(r[14] or '').strip(),
                          rows=[]) for r in rows}
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


def holder_outcome(live, truth):
    """The admitted statement's holder against the printed holder, with the per-statement comparison's rule:
    ``agrees``, ``same_entity`` (other legal-form punctuation, or the legal form omitted), ``differs``,
    ``not_recorded``, or ``not_printed`` (the statement prints none). The holder is the one the statement was
    imported with; a statement admitted before import requests were stored is judged by its ledger account's
    holder (``holder_source``)."""
    from benchmarks.statement_automation.real_compare import holder_agrees, same_entity_holder
    saved, source = (live.get('holder'), 'statement') if live.get('holder') else (live.get('account_holder'), 'account')
    if not truth.get('holder'):
        return dict(holder='not_printed', holder_source=source)
    if not saved:
        return dict(holder='not_recorded', holder_source=source)
    outcome = ('agrees' if holder_agrees(truth['holder'], saved) else
               'same_entity' if same_entity_holder(truth['holder'], saved) else 'differs')
    return dict(holder=outcome, holder_source=source)


def judge(live, truth):
    """One live period against its truth period: ``compare`` and ``holder_outcome`` plus the truth's
    identity, and ``must_be_held`` when the truth says the period must not be in the ledger at all."""
    entry = dict(compare(live, truth), **holder_outcome(live, truth), family=truth['family'], truth_id=truth['id'],
                 truth_status=truth['truth_status'])
    if truth.get('expected') == 'hold' or truth['truth_status'] == 'incomplete':
        entry['outcome'] = 'must_be_held'
    return entry


def overlap_trimmed(live, truth, entry, account_periods):
    """The saved period of another live period that counts the rows this one leaves out, or None.

    The product trims the days of a movement query that a statement already saved for the same ledger
    account covers (``statement_overlap_trim``): those movements are counted once, in the saved one. Against
    per-document truth that reads as missing rows and a later opening. It is told apart only when the truth
    and the ledger prove it: no extra rows and no closing difference; the missing rows are exactly the truth
    rows dated before the live period's start; the live opening is the running balance the truth prints
    after the last of them; and one admitted period of the same ledger account, ending the day before, holds
    each of them (date, amount, direction)."""
    from datetime import date, timedelta
    if entry['outcome'] != 'disagrees' or entry['extra_rows'] or set(entry['balances']) - {'opening'}:
        return None
    if not live.get('period_start') or not truth.get('period_start') or live['period_start'] <= truth['period_start']:
        return None
    before = [r for r in truth['rows'] if r.get('date') and r['date'] < live['period_start']]
    if not before or len(before) != entry['missing_rows']:
        return None
    if any(r.get('date_unprinted') for r in truth['rows']):
        return None
    kept = Counter((r['amount_minor'], r['direction'], r['date']) for r in truth['rows']
                   if r.get('date') and r['date'] >= live['period_start'])
    if kept != Counter(live['rows']):
        return None
    if before[-1].get('balance_after') is None or live['opening_minor'] != before[-1]['balance_after']:
        return None
    day_before = (date.fromisoformat(live['period_start']) - timedelta(days=1)).isoformat()
    wanted = Counter((r['amount_minor'], r['direction'], r['date']) for r in before)
    for other in account_periods:
        if other['period_id'] != live['period_id'] and other['period_end'] == day_before \
                and not wanted - Counter(other['rows']) and other['closing_minor'] == live['opening_minor']:
            return other['period_id']
    return None


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


def same_share(live, truth):
    """Whether a live period and a truth period are the same share (or have no share to tell apart).

    The live share is the four-digit share number at the end of the printed
    identifier. Where the truth names the section by its product instead (Navy
    Federal: "EveryDay Checking - 1111"), those four digits are the account
    number itself, so they must equal the truth's account; the account, balances
    and rows then tell sections of one account apart (a checking account and its
    line of credit print the same digits)."""
    if not live.get('share') or not truth.get('share') or truth['share'] == live['share']:
        return True
    return not re.fullmatch(r'\d{4}', truth['share']) and live['share'] == truth.get('account')


def best_truth(live, candidates):
    def overlap(truth):
        a = Counter((r['amount_minor'], r['direction']) for r in truth['rows'])
        b = Counter((amount, direction) for amount, direction, _ in live['rows'])
        return sum((a & b).values())
    # A credit-union share (savings, checking) is its own period: never pair across shares.
    same = [t for t in candidates if t['period_end'] == live['period_end']
            and (not live['currency'] or t['currency'] == live['currency']) and same_share(live, t)]
    if not same:
        return None
    if len(same) > 1:
        accounts = [t for t in same if t.get('account') and t['account'] in live['account']]
        same = accounts or same

    def balances(truth):  # sub-accounts can share the last digits; recorded balances tell them apart
        return sum(1 for name in ('opening_minor', 'closing_minor')
                   if live[name] is not None and abs(live[name]) == abs(truth[name] or 0))
    return max(same, key=lambda truth: (overlap(truth), balances(truth)))


def live_files_of(session, inventory, page_identities=None):
    """{live evidence file id: truth document id}: the inventory's files, every live file with a
    document's bytes, and (given ``page_identities`` {file id: identity}) every file whose pages
    render identically to one of those. Returns (mapping, counts by how each file was found)."""
    from sqlalchemy import bindparam, text
    by_file, how = {}, Counter()
    by_sha = {}
    for doc in inventory['documents']:
        if doc.get('sha256'):
            by_sha[doc['sha256']] = doc['id']
        for record in doc['evidence_files']:
            by_file[record['evidence_file_id']] = doc['id']
            how['inventory'] += 1
    if by_sha:
        for file_id, sha in session.execute(text(
                "SELECT id, sha256 FROM evidence_files WHERE sha256 IN :shas").bindparams(
                bindparam('shas', expanding=True)), dict(shas=list(by_sha))).all():
            if str(file_id) not in by_file:
                by_file[str(file_id)] = by_sha[sha]
                how['same_bytes'] += 1
    if page_identities:
        doc_of_identity = defaultdict(set)
        for file_id, doc in by_file.items():
            if page_identities.get(file_id):
                doc_of_identity[page_identities[file_id]].add(doc)
        for file_id, identity in page_identities.items():
            docs = doc_of_identity.get(identity) or set()
            if file_id not in by_file and len(docs) == 1:
                by_file[file_id] = next(iter(docs))
                how['same_pages'] += 1
    return by_file, how


def audit(truth_dir, inventory, session, *, page_identities=None):
    by_file, found = live_files_of(session, inventory, page_identities)
    truths = {}
    for path in Path(truth_dir, 'periods').glob('*.json'):
        result = json.loads(path.read_text())
        periods = [p for p in result.get('periods', []) if p['truth_status'] in JUDGED]
        if periods:
            truths[result['id']] = dict(status=result['status'], periods=periods, family=periods[0]['family'])
    files = [f for f, doc in by_file.items() if doc in truths]
    live = live_periods(session, files)
    detail, counts, details = [], defaultdict(Counter), defaultdict(Counter)
    by_account = defaultdict(list)
    for period in live:
        if period.get('account_id'):
            by_account[period['account_id']].append(period)
    for period in live:
        doc = by_file.get(period['evidence_file_id'])
        truth = best_truth(period, truths[doc]['periods'])
        if period['period_end'] is None:
            # Admitted without a printed period: nothing to pair it with.
            entry = dict(outcome='live_period_undated', family=truths[doc]['family'])
        elif truth is None:
            entry = dict(outcome='no_truth_period', family=truths[doc]['family'])
        else:
            entry = judge(period, truth)
            cover = overlap_trimmed(period, truth, entry, by_account.get(period.get('account_id'), []))
            if cover:
                # Counted once: the trimmed rows are in the saved period that covers those days.
                entry.update(outcome='overlap_trimmed', counted_in_period_id=cover,
                             rows_counted_in_covering_period=entry['missing_rows'])
        entry.update(doc=doc, live_period_id=period['period_id'], live_rows=len(period['rows']), case=period['case_id'],
                     account_id=period.get('account_id'),
                     live_rows_without_transaction_or_posted_date=sum(1 for r in period['rows'] if r[2] is None),
                     of_which_with_another_date=period.get('undated_with_other_date', 0))
        if truth is not None and entry['rows'] == 'dates_differ':
            entry['day_offsets'] = dict(_day_offsets(period['rows'], truth['rows']))
        detail.append(entry)
        key = entry['family'] + (' (OCR-layer truth)' if entry.get('truth_status') == 'ocr_reconciled' else '')
        counts[key][entry['outcome']] += 1
        if entry['outcome'] not in ('no_truth_period', 'live_period_undated'):
            details[key][f"rows {entry['rows']}"] += 1
            for name in entry['balances']:
                details[key][name] += 1
    holders = defaultdict(Counter)
    for entry in detail:
        if entry.get('holder'):
            holders[entry['family']][entry['holder']] += 1
            holders[entry['family']]['judged_by_' + entry['holder_source']] += 1
    rows = Counter()
    for entry in detail:
        if entry['outcome'] not in ('no_truth_period', 'live_period_undated'):
            rows['live_rows'] += entry['live_rows']
            if entry['outcome'] == 'overlap_trimmed':
                rows['rows_counted_in_covering_period'] += entry['missing_rows']
            else:
                rows['missing_rows'] += entry['missing_rows']
            rows['extra_rows'] += entry['extra_rows']
            rows['live_rows_without_transaction_or_posted_date'] += entry['live_rows_without_transaction_or_posted_date']
            rows['of_which_with_another_date'] += entry['of_which_with_another_date']
    per_case = Counter((e['case'], e['truth_id']) for e in detail if e.get('truth_id'))
    canonical = {p['id']: p.get('duplicate_of') for t in truths.values() for p in t['periods']}
    admitted = {(e['case'], canonical.get(e['truth_id']) or e['truth_id']) for e in detail if e.get('truth_id')}
    cross_doc = Counter((e['case'], canonical.get(e['truth_id']) or e['truth_id']) for e in detail if e.get('truth_id'))
    ledger_accounts = defaultdict(set)
    for e in detail:
        if e.get('truth_id'):
            ledger_accounts[(e['case'], canonical.get(e['truth_id']) or e['truth_id'])].add(e.get('account_id'))
    offsets = defaultdict(Counter)
    for e in detail:
        for days, n in e.get('day_offsets', {}).items():
            offsets[e['family']][str(days)] += n
    duplicates = dict(same_printed_period_admitted_more_than_once_examples=sorted(
                          f'{case[:8]} {truth_id}' for (case, truth_id), n in cross_doc.items() if n > 1)[:20],
                      same_printed_period_in_more_than_one_ledger_account=sum(
                          1 for key, accounts in ledger_accounts.items() if cross_doc[key] > 1 and len(accounts) > 1),
                      same_file_admitted_more_than_once_in_a_case=sum(1 for n in per_case.values() if n > 1),
                      extra_live_periods_from_repeats_in_a_case=sum(n - 1 for n in per_case.values() if n > 1),
                      same_printed_period_admitted_more_than_once_in_a_case=sum(1 for n in cross_doc.values() if n > 1),
                      extra_live_periods_for_the_same_printed_period=sum(n - 1 for n in cross_doc.values() if n > 1),
                      distinct_printed_periods_admitted=len(admitted))
    summary = dict(live_admitted_periods_on_truth_documents=len(live), documents_with_truth=len(truths),
                   live_files_on_truth_documents=dict(found),
                   duplicates=duplicates, day_offsets_where_dates_differ={k: dict(v.most_common(8))
                                                                          for k, v in sorted(offsets.items())},
                   by_family={k: dict(v) for k, v in sorted(counts.items())},
                   overall=dict(sum(counts.values(), Counter())), rows=dict(rows),
                   comparison_by_family={k: dict(v) for k, v in sorted(details.items())},
                   live_periods_per_truth_period=dict(Counter(Counter(e.get('truth_id') for e in detail
                                                                      if e.get('truth_id')).values())),
                   disagreeing_examples=[e['truth_id'] for e in detail if e['outcome'] == 'disagrees'][:10],
                   holder_by_family={k: dict(v) for k, v in sorted(holders.items())},
                   live_admitted_periods_holder_differs=sum(v['differs'] for v in holders.values()),
                   holder_differs_examples=[e['truth_id'] for e in detail if e.get('holder') == 'differs'][:20],
                   must_be_held_examples=[e['truth_id'] for e in detail if e['outcome'] == 'must_be_held'][:10])
    return summary, detail


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--truth', type=Path, required=True)
    parser.add_argument('--inventory', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True, help='private directory for the per-period detail')
    parser.add_argument('--page-identities', type=Path,
                        help='JSON {"<file id>[:<sha256>]": page identity} (e.g. the page-copy census cache)')
    args = parser.parse_args(argv)
    sys.path.insert(0, str(BACKEND))
    from postgres.session import _get_session_local
    from scripts.financial_reader_recovery_estimate import read_only
    inventory = json.loads(args.inventory.read_text())
    with _get_session_local()() as db:
        read_only(db)
        identities = None
        if args.page_identities:
            raw = json.loads(args.page_identities.read_text())
            identities = {key.split(':')[0]: (value.get('identity') if isinstance(value, dict) else value)
                          for key, value in raw.items() if value}
        summary, detail = audit(args.truth, inventory, db, page_identities=identities)
        db.rollback()
    args.out.mkdir(parents=True, exist_ok=True)
    os.chmod(args.out, 0o700)
    (args.out / 'ledger-audit.json').write_text(json.dumps(dict(summary=summary, detail=detail), indent=1) + '\n')
    print(json.dumps(summary, indent=1))


if __name__ == '__main__':
    main()
