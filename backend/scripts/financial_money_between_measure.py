"""Measure how often three answers to "money between A and B" disagree (agent-ledger A). Read only.

For each financial case and each account family A (canonical account and its aliases), every counterparty group the agent ledger tool reports
for A's accounts (group_by=counterparty) is a pair. For each pair, per currency and direction:
  (a) graph: the sum of FinancialTransaction nodes on A's accounts whose ``ledger_counterparty_raw`` is one of the
      group's printed labels (what a Cypher over TRANSFERRED_TO can compute; every admitted class, no identity);
  (b) the ledger tool's group sums, verified and working populations;
  (c) ``link_edges.payments`` between A (party + held accounts) and B (the reviewed identity), p0-p2 summed
      (label groups have no identity, so (c) has nothing to say).
With --after, (c) and the tool are read through ``money_between`` instead (agent-ledger B).

Usage (from backend/, via live-run.sh): financial_money_between_measure.py [--case <id-prefix>] [--json out.json]
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict

sys.path.insert(0, '.')

from sqlalchemy import text  # noqa: E402


def _key(currency, direction):
    return '%s:%s' % (currency, direction)


def tool_rows(session, case_id, holder, population):
    from services.agent.financial_ledger_tools import read_financial_ledger
    items, offset, revision = [], 0, None
    while True:
        page = read_financial_ledger(session, case_id=case_id, account_ids=[holder],
                                     population=population, view='transactions', offset=offset, limit=100,
                                     expected_revision=revision)
        if not page['available']:
            return None, page['reason']
        revision = page['revision']
        items.extend(page['items'])
        if not page['has_more']:
            return items, None
        offset = page['next_offset']


def group_of(row):
    link = row.get('counterparty_link')
    label = row.get('to_name' if row['direction'] == 'debit' else 'from_name')
    if label is None:
        label = row.get('counterparty_raw')
    return ('identity:%s:%s' % (link['kind'], link['id'])) if link else 'label:' + json.dumps(label, ensure_ascii=False)


def sums(rows, classes=None):
    out = defaultdict(int)
    for r in rows:
        if classes and r['proof_class'] not in classes:
            continue
        out[_key(r['currency'], r['direction'])] += int(r['amount_minor'])
    return dict(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--case')
    ap.add_argument('--json')
    ap.add_argument('--after', action='store_true')
    args = ap.parse_args()
    from services.agent.tools import _financial_session
    from services.financial.account_selection import holder_account_ids
    from services.financial.account_consolidation import expand_account_ids
    from uuid import UUID
    from services.phone import link_edges as LE
    from services.neo4j.driver import open_driver
    driver = open_driver()
    report = {'cases': [], 'mode': 'after' if args.after else 'before'}
    with _financial_session() as s0:
        cases = [(str(r.id), r.title) for r in s0.execute(text(
            "SELECT c.id, c.title FROM cases c WHERE EXISTS (SELECT 1 FROM financial_transactions t WHERE "
            "t.case_id = c.id AND t.ledger_status = 'admitted') ORDER BY c.title"))]
    if args.case:
        cases = [c for c in cases if c[0].startswith(args.case)]
    for case_id, title in cases:
        with _financial_session() as session:
            from uuid import UUID
            cid = UUID(case_id)
            fams = defaultdict(set)
            for aid, meta in session.execute(text(
                    "SELECT a.id::text, a.metadata FROM financial_accounts a WHERE a.case_id = :c AND EXISTS (SELECT 1 "
                    "FROM financial_transactions t WHERE t.account_id = a.id AND t.ledger_status = 'admitted' AND "
                    "t.superseded_by_id IS NULL)"), {'c': case_id}):
                fams[(meta or {}).get('canonical_account_id') or aid].add(aid)
            held = {h: {str(x) for x in expand_account_ids(session, cid, [UUID(h)])} for h in fams}
            names = {}
            holders = sorted(held)
            case_out = {'case_id': case_id, 'title': title, 'holders': len(holders), 'pairs': []}
            for h in holders:
                working, why = tool_rows(session, cid, h, 'working')
                verified, why2 = tool_rows(session, cid, h, 'verified')
                if working is None or verified is None:
                    case_out.setdefault('unavailable', []).append({'holder': h, 'reason': why or why2})
                    continue
                groups = defaultdict(lambda: {'working': [], 'verified': []})
                for r in working:
                    groups[group_of(r)]['working'].append(r)
                for r in verified:
                    groups[group_of(r)]['verified'].append(r)
                for g, rows in sorted(groups.items()):
                    raws = sorted({r.get('counterparty_raw') for r in rows['working'] if r.get('counterparty_raw')})
                    accounts = sorted({r['account_id'] for r in rows['working']})
                    descs = sorted({(r.get('description') or '').strip() for r in rows['working']} - {''})
                    graph = defaultdict(int)
                    if raws or descs:
                        with driver.session() as gs:
                            for rec in gs.run(
                                    "MATCH (t:FinancialTransaction {case_id: $c}) WHERE t.ledger_account_id IN $a AND "
                                    "(t.ledger_counterparty_raw IN $r OR t.name IN $d) AND ((:FinancialAccount)-[:TRANSFERRED_TO]->(t) OR "
                                    "(t)-[:TRANSFERRED_TO]->(:FinancialAccount)) RETURN t.currency AS cur, "
                                    "t.direction AS dir, sum(t.amount_minor) AS s, count(t) AS n",
                                    c=case_id, a=sorted(held[h]), r=raws, d=descs):
                                graph[_key(rec['cur'], rec['dir'])] += int(rec['s'] or 0)
                    pair = {'holder': h, 'holder_name': names.get(h), 'group': g, 'raw_labels': len(raws),
                            'graph': dict(graph), 'tool_working': sums(rows['working']),
                            'tool_verified': sums(rows['verified']),
                            'rows_working': len(rows['working']), 'rows_verified': len(rows['verified']),
                            'p3_rows': sum(r['proof_class'] == 'p3' for r in rows['working'])}
                    if g.startswith('identity:'):
                        _, kind, ident = g.split(':', 2)
                        if args.after:
                            from services.financial.money_between import money_between
                            mb = money_between(session, cid, {'kind': 'account', 'id': h}, {'kind': kind, 'id': ident})
                            own = [r for r in mb['rows'] if r['account_id'] in held[h]]
                            pair['link_edges_all'] = {_key(m['currency'], d): m['paid_%s_minor' % ('ab' if d == 'debit' else 'ba')]
                                                      for m in mb['totals'] for d in ('debit', 'credit')
                                                      if m['paid_%s_minor' % ('ab' if d == 'debit' else 'ba')]}
                        else:
                            side_a = {'parties': set(), 'accounts': held[h]}
                            if kind == 'party':
                                side_b = {'parties': {ident}, 'accounts': held.get(ident, set())}
                            else:
                                side_b = {'parties': set(), 'accounts': {ident}}
                            pay = LE.payments(session, cid, side_a, side_b)
                            own = [r for r in pay['rows'] if r['account_id'] in held[h]]
                            tot = LE.money_totals(pay['rows'])
                            pair['link_edges_all'] = {_key(m['currency'], d): m['paid_%s_minor' % ('ab' if d == 'debit' else 'ba')]
                                                      for m in tot for d in ('debit', 'credit')
                                                      if m['paid_%s_minor' % ('ab' if d == 'debit' else 'ba')]}
                        own_s = defaultdict(int)
                        for r in own:
                            if r['proof_class'] in LE.SUMMED:
                                own_s[_key(r['currency'], 'debit' if r['direction'] == 'ab' else 'credit')] += r['amount_minor']
                        pair['link_edges_own_accounts'] = dict(own_s)
                        pair['link_edges_rows'] = len(own)
                        pair['link_edges_rows_all'] = len(pay['rows']) if not args.after else len(mb['rows'])
                    case_out['pairs'].append(pair)
            report['cases'].append(case_out)
    driver.close()
    summary = []
    for c in report['cases']:
        ps = c['pairs']
        ident = [p for p in ps if p['group'].startswith('identity:')]
        row = {'case': c['case_id'][:8], 'title': c['title'], 'holders': c['holders'], 'pairs': len(ps),
               'identity_pairs': len(ident),
               'graph_vs_verified': sum(p['graph'] != p['tool_verified'] for p in ps),
               'graph_vs_working': sum(p['graph'] != p['tool_working'] for p in ps),
               'verified_vs_working': sum(p['tool_verified'] != p['tool_working'] for p in ps),
               'verified_vs_link_edges_own': sum(p['tool_verified'] != p.get('link_edges_own_accounts') for p in ident),
               'verified_vs_link_edges_all': sum(p['tool_verified'] != p.get('link_edges_all') for p in ident),
               'pairs_with_p3': sum(p['p3_rows'] > 0 for p in ps),
               'unavailable': len(c.get('unavailable', []))}
        summary.append(row)
        print(json.dumps(row))
    report['summary'] = summary
    if args.json:
        with open(args.json, 'w') as f:
            json.dump(report, f, indent=1, default=str)


if __name__ == '__main__':
    main()
