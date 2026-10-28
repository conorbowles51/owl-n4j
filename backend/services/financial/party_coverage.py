"""How many stored payments show no other side, and whether that is explained.

Every payment's From or To is either named (the statement's counterparty field,
a person's label or link, or a suggestion read from the description), or
unnamed with a stated reason (payment_party_reasons), or unnamed with no reason:
a bare "Not identified". This module counts the three per bank and per printed
layout (bank and account type) so that a release, and the processing-health
page, can see the bare share the day it changes. Read only.
"""
from __future__ import annotations

import collections
import re

NAMED, REASON, BARE = 'named', 'reason', 'bare'

# A bank's share of bare payments may rise by at most this much (percentage points) over the released baseline.
TOLERANCE_POINTS = 1.0
# A layout the baseline has not seen fails when more than this share of its payments is bare.
NEW_LAYOUT_LIMIT = 0.5
# Banks and layouts with fewer payments than this are reported but never fail a release.
MIN_ROWS = 20


def bank_of(institution):
    """The bank a statement account belongs to, as the first word of its printed institution (BANCO SANTANDER → SANTANDER)."""
    words = re.sub(r'[^A-Z0-9& ]', ' ', (institution or '').upper()).split()
    if words and words[0] in ('BANCO', 'BANK', 'THE') and len(words) > 1:
        words = words[1:]
    return words[0] if words else 'UNKNOWN'


def classify(*, description, direction, account_type, institution, counterparty_raw, labels, reviewed_counterparty=None, matched=False):
    """NAMED, REASON or BARE for one stored payment, as the Transactions table shows its other side."""
    from services.financial.payment_inference import infer_payment_labels
    if counterparty_raw and counterparty_raw.strip():
        return NAMED
    labels = labels if isinstance(labels, dict) else {}
    side = 'from_name' if direction == 'credit' else 'to_name'
    if labels.get(side) or labels.get('counterparty_link') or reviewed_counterparty:
        return NAMED
    inferred = infer_payment_labels(description, direction=direction, account_type=account_type, institution=institution)
    if inferred.get('counterparty') or matched:
        return NAMED
    return REASON if inferred.get('counterparty_reason') else BARE


def tally(rows, matched_ids=frozenset()):
    """{'banks': {bank: counts}, 'layouts': {bank/account type: counts}, 'cases': {case: counts}, 'total': counts}.

    ``rows``: dicts with case_id, description, direction, account_type, institution_name, counterparty_raw, labels
    and optionally reviewed_counterparty and id. ``matched_ids``: rows named from their matching payment in another
    account of the case (services.financial.payment_party_matches). Counts are {named, reason, bare, rows}."""
    def blank():
        return {NAMED: 0, REASON: 0, BARE: 0, 'rows': 0}
    banks, layouts, cases = (collections.defaultdict(blank) for _ in range(3))
    total = blank()
    for row in rows:
        kind = classify(description=row.get('description'), direction=row.get('direction'),
                        account_type=row.get('account_type'), institution=row.get('institution_name'),
                        counterparty_raw=row.get('counterparty_raw'), labels=row.get('labels'),
                        reviewed_counterparty=row.get('reviewed_counterparty'),
                        matched=str(row.get('id')) in matched_ids)
        bank = bank_of(row.get('institution_name'))
        for counts in (banks[bank], layouts[f"{bank}/{row.get('account_type') or 'unknown'}"],
                       cases[str(row.get('case_id'))], total):
            counts[kind] += 1
            counts['rows'] += 1
    return dict(banks=dict(banks), layouts=dict(layouts), cases=dict(cases), total=total)


def bare_share(counts):
    return counts[BARE] / counts['rows'] if counts.get('rows') else 0.0


def compare(current, baseline, *, tolerance=TOLERANCE_POINTS, new_layout_limit=NEW_LAYOUT_LIMIT, min_rows=MIN_ROWS):
    """Failures (plain sentences) of ``current`` against the released ``baseline``; empty when the release may go."""
    failures = []
    for bank, counts in sorted(current['banks'].items()):
        if counts['rows'] < min_rows:
            continue
        before = baseline.get('banks', {}).get(bank)
        now = bare_share(counts) * 100
        was = bare_share(before) * 100 if before else None
        if was is not None and now > was + tolerance:
            failures.append(f'{bank}: {now:.1f}% of {counts["rows"]} payments show a bare "Not identified" '
                            f'(released baseline {was:.1f}%, tolerance {tolerance:g} points).')
    for layout, counts in sorted(current['layouts'].items()):
        if counts['rows'] < min_rows or layout in baseline.get('layouts', {}):
            continue
        if bare_share(counts) > new_layout_limit:
            failures.append(f'{layout}: a newly read layout with {bare_share(counts) * 100:.1f}% of {counts["rows"]} '
                            f'payments showing a bare "Not identified" (limit {new_layout_limit * 100:.0f}%).')
    return failures


def load_rows(session):
    """Every stored payment of every case with what the gate needs, read in the caller's (read-only) transaction."""
    from sqlalchemy import text
    result = session.execute(text(
        "select t.id, t.case_id, t.description, t.direction, t.counterparty_raw, "
        "t.metadata->'investigation_labels' as labels, t.provenance->'reviewed_counterparty' as reviewed, "
        "a.account_type, a.institution_name "
        "from financial_transactions t left join financial_accounts a on a.id = t.account_id"))
    for id, case_id, description, direction, raw, labels, reviewed, account_type, institution in result:
        yield dict(id=str(id), case_id=case_id, description=description, direction=str(direction.value if hasattr(direction, 'value') else direction),
                   counterparty_raw=raw, labels=labels, reviewed_counterparty=reviewed,
                   account_type=str(account_type.value if hasattr(account_type, 'value') else account_type) if account_type else None,
                   institution_name=institution)


def matched_ids(session, case_ids):
    """Ids of payments named from their matching payment in another account of the same case."""
    from services.financial.payment_party_matches import case_party_matches
    found = set()
    for case_id in sorted({str(c) for c in case_ids}):
        found.update(case_party_matches(session, case_id))
    return found


_ADMIN_CACHE = {}


def _fingerprint(session):
    """Changes whenever a payment or an account is written (xmin is the writing transaction)."""
    from sqlalchemy import text
    return tuple(session.execute(text(
        "select (select count(*) || ':' || coalesce(sum(xmin::text::bigint), 0) from financial_transactions), "
        "(select count(*) || ':' || coalesce(sum(xmin::text::bigint), 0) from financial_accounts)")).one())


def cases_for_admin(session, now=None):
    """Per case: how many payments are named, unnamed with a stated reason, and bare, as the release gate counts them.
    Worst unnamed share first. Recounted only when a payment or account has been written since the last count."""
    from datetime import datetime, timezone
    from sqlalchemy import text
    key = _fingerprint(session)
    if key in _ADMIN_CACHE:
        return _ADMIN_CACHE[key]
    rows = list(load_rows(session))
    counted = tally(rows, matched_ids(session, {row['case_id'] for row in rows}))
    titles = {str(case_id): title for case_id, title in session.execute(text('select id, title from cases'))}

    def shares(counts):
        rows_ = counts['rows'] or 1
        return dict(counts, unnamed_share=(counts[REASON] + counts[BARE]) / rows_, bare_share=counts[BARE] / rows_)
    cases = [dict(shares(counts), case_id=case_id, title=titles.get(case_id, case_id)) for case_id, counts in counted['cases'].items()]
    cases.sort(key=lambda c: (-c['unnamed_share'], -c['rows']))
    result = dict(measured_at=(now or datetime.now(timezone.utc)).isoformat(), total=shares(counted['total']), cases=cases)
    _ADMIN_CACHE.clear()
    _ADMIN_CACHE[key] = result
    return result
