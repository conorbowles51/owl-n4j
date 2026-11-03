"""Measure what the agent's ledger proposals would work on, per case (agent-proposals A). Read only.

Per financial case:
  - missing months: gaps between an account's statements (continuity seams of kind 'gap'), with the calendar
    months nothing covers;
  - categories: current admitted payments with no stored category, or stored 'uncategorized';
  - counterparty identity: current admitted payments that print a counterparty and carry no identity link;
  - judgement calls: by origin and status; how many are agent proposals already (rule 'proposal.*');
  - Workspace AI outputs by type and review status; whether the case has an active mandate.

Usage (from backend/, via live-run.sh): financial_agent_proposals_measure.py [--case <id-prefix>] [--json out.json]
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter

sys.path.insert(0, '.')

from sqlalchemy import text  # noqa: E402


def months_between(start, end):
    """['2024-03', ...] calendar months wholly or partly inside [start, end]."""
    out, y, m = [], start.year, start.month
    while (y, m) <= (end.year, end.month):
        out.append(f'{y:04d}-{m:02d}')
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def measure_case(session, case_id):
    from datetime import timedelta
    from sqlalchemy import select
    from postgres.models.financial import FinancialAccount as A
    from services.financial.continuity import read_account_continuity
    from services.financial.account_consolidation import expand_account_ids
    out = dict(case_id=str(case_id))
    accounts = list(session.scalars(select(A.id).where(A.case_id == case_id)))
    seen, gaps, gap_days, gap_months, accounts_with_seams = set(), 0, 0, 0, 0
    examples = []
    for account_id in accounts:
        if account_id in seen:
            continue
        family = set(expand_account_ids(session, case_id, [account_id]))
        seen |= family
        run = read_account_continuity(session, case_id=case_id, account_id=account_id)
        if run.seams:
            accounts_with_seams += 1
        for seam in run.gaps:
            gaps += 1
            gap_days += seam.uncovered_days
            first, last = seam.earlier.end + timedelta(days=1), seam.later.start - timedelta(days=1)
            months = months_between(first, last) if last >= first else []
            gap_months += len(months)
            if len(examples) < 5:
                examples.append(dict(account=str(account_id)[:8], after=str(seam.earlier.end),
                                     before=str(seam.later.start), days=seam.uncovered_days))
    out.update(account_families=len({min(expand_account_ids(session, case_id, [a])) for a in accounts}) if accounts else 0,
               families_with_seams=accounts_with_seams, gaps=gaps, gap_days=gap_days, gap_months=gap_months,
               gap_examples=examples)
    row = session.execute(text("""
        select count(*) total,
               count(*) filter (where c.transaction_id is null) no_category,
               count(*) filter (where c.transaction_id is not null and coalesce(c.category,'') in ('', 'Uncategorized', 'uncategorized')) uncategorized,
               count(*) filter (where c.origin = 'model') model_category,
               count(*) filter (where nullif(trim(t.counterparty_raw), '') is not null) with_counterparty,
               count(*) filter (where nullif(trim(t.counterparty_raw), '') is not null
                                and (t.metadata->'investigation_labels'->'counterparty_link') is null
                                and (t.provenance->'reviewed_counterparty') is null) counterparty_no_identity
          from financial_transactions t
          left join financial_payment_categories c on c.transaction_id = t.id
         where t.case_id = :c and t.ledger_status = 'admitted' and t.superseded_by_id is null"""), dict(c=case_id)).mappings().one()
    out['payments'] = dict(row)
    out['judgements'] = {f'{o}:{s}': n for o, s, n in session.execute(text(
        "select origin, status, count(*) from financial_judgements where case_id=:c group by 1,2"), dict(c=case_id))}
    out['proposal_judgements'] = session.execute(text(
        "select count(*) from financial_judgements where case_id=:c and rule_id like 'proposal.%'"), dict(c=case_id)).scalar()
    out['workspace_ai'] = {f'{t}:{r}': n for t, r, n in session.execute(text(
        "select output_type, review_status, count(*) from workspace_ai_outputs where case_id=:c group by 1,2"), dict(c=case_id))}
    out['active_mandate'] = bool(session.execute(text(
        "select count(*) from case_mandate_versions where case_id=:c"), dict(c=case_id)).scalar())
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--case', default='')
    parser.add_argument('--json', default='')
    args = parser.parse_args()
    from postgres.session import _get_session_local
    with _get_session_local()() as session:
        session.execute(text('SET TRANSACTION READ ONLY'))
        cases = [r[0] for r in session.execute(text(
            "select distinct case_id from financial_transactions order by 1"))]
        names = dict(session.execute(text('select id, title from cases')).all()) if True else {}
        results = []
        for case_id in cases:
            if args.case and not str(case_id).startswith(args.case):
                continue
            item = measure_case(session, case_id)
            item['title'] = names.get(case_id)
            results.append(item)
            print(json.dumps(item, default=str), flush=True)
        session.rollback()
    if args.json:
        with open(args.json, 'w') as fh:
            json.dump(results, fh, default=str, indent=1)


if __name__ == '__main__':
    main()
