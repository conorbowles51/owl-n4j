"""Agent trades evaluation (lx-brokerage D; report rank 18, scenario 6): questions on BNB2's brokerage statements and
the verification case, each asked through the agent's own tool layer (make_agent_tools with the run's case,
read-only sessions) and scored against a known answer computed here by plain SQL, independently of the code under
test (the cash ledger's own rows for money, the security table for counts).

Run the same script on the release tree and on the tree before it (a tool that does not exist scores "no tool").
Writes one JSON line per question to --out (scores only; --detail is local scratch with case values, never committed).

Usage (from backend/, via live-run.sh): financial_agent_trades_eval.py --out scores.jsonl --detail detail.json
"""
from __future__ import annotations

import argparse
import json
import sys

sys.path.insert(0, '.')

from sqlalchemy import text  # noqa: E402

BNB2, VERIFY = 'd5b330d1', 'cded78d0'
SHOWN = ("FROM financial_security_rows r LEFT JOIN financial_transactions t ON t.id = r.cash_transaction_id "
         "WHERE r.case_id = :c AND r.ledger_status = 'admitted' AND r.row_kind = :k AND "
         "(r.cash_transaction_id IS NULL OR t.ledger_status = 'admitted')")
# Fund buys and sells of one instrument, from the money ledger (the cash leg), never from the security rows.
FUND_CASH = ("FROM financial_transactions t JOIN financial_source_documents d ON d.id = t.source_document_id "
             "JOIN financial_accounts a ON a.id = t.account_id "
             "WHERE t.case_id = :c AND t.ledger_status = 'admitted' AND t.superseded_by_id IS NULL AND "
             "d.status = 'admitted' AND a.institution_name = ANY(:inst) AND t.description ILIKE :needle AND "
             "(t.description ILIKE :buy OR t.description ILIKE :sell)")


def q1(s, sql, **p):
    return s.execute(text(sql), p).scalar()


def build(s):
    from services.financial.brokerage_ledger import brokerage_institutions
    cases = {k: str(q1(s, "SELECT id FROM cases WHERE id::text LIKE :p", p=k + '%')) for k in (BNB2, VERIFY)}
    b, v = cases[BNB2], cases[VERIFY]
    inst = sorted(brokerage_institutions())
    Q = []
    Q.append(dict(id='T01', case=b, q='How many trades are in the BNB2 ledger?', tool='get_trades',
                  args=dict(limit=1), expect=dict(total=int(q1(s, "SELECT count(*) " + SHOWN, c=b, k='trade'))),
                  check='total'))
    Q.append(dict(id='T02', case=b, q='How many of those did a model read with no person confirming them?',
                  tool='get_trades', args=dict(limit=1),
                  expect=dict(model=int(q1(s, "SELECT count(*) " + SHOWN + " AND r.confirmation IS NULL AND "
                                              "r.provenance->'reading_origin'->>'kind' = 'model'", c=b, k='trade'))),
                  check='model'))
    # The fund bought and sold most often, by its cash lines.
    fund = q1(s, "SELECT r.instrument " + SHOWN + " AND r.side IN ('buy', 'sell') GROUP BY 1 ORDER BY count(*) DESC, "
                 "1 LIMIT 1", c=b, k='trade')
    needle = '%' + '%'.join(fund.split()) + '%'
    words = dict(buy='%Compra Fondos%', sell='%Venta Fondos%')
    paid = int(q1(s, "SELECT coalesce(sum(t.amount_minor), 0) " + FUND_CASH + " AND t.direction = 'debit'",
                  c=b, inst=inst, needle=needle, **words))
    received = int(q1(s, "SELECT coalesce(sum(t.amount_minor), 0) " + FUND_CASH + " AND t.direction = 'credit'",
                      c=b, inst=inst, needle=needle, **words))
    Q.append(dict(id='T03', case=b, q='How much was paid into and received from the most-traded fund?',
                  tool='get_trades', args=dict(instrument=fund, side=None, limit=1),
                  expect=dict(paid=paid, received=received), check='fund_money'))
    Q.append(dict(id='T04', case=b, q='At what time of day was each of those orders placed?', tool='get_trades',
                  args=dict(instrument=fund, limit=200), expect=dict(), check='no_time'))
    Q.append(dict(id='T05', case=b, q='What are the latest holdings, with their value?', tool='get_trades',
                  args=dict(kind='holding', limit=1),
                  expect=dict(total=int(q1(s, "SELECT count(*) " + SHOWN, c=b, k='holding'))), check='holdings'))
    other = q1(s, "SELECT id::text FROM financial_accounts WHERE case_id <> CAST(:c AS uuid) LIMIT 1", c=b)
    Q.append(dict(id='T06', case=b, q="Show the trades of an account from another case.", tool='get_trades',
                  args=dict(account_id=other), expect=dict(reason='That account is not in this case.'),
                  check='boundary'))
    Q.append(dict(id='T07', case=v, q='How many trades are in the verification case?', tool='get_trades',
                  args=dict(limit=1), expect=dict(total=int(q1(s, "SELECT count(*) " + SHOWN, c=v, k='trade'))),
                  check='total'))
    return Q


def score(check, expect, out):
    d = out.get('data') or {}
    if out.get('status') != 'success':
        return False, 'tool error: %s' % (out.get('error') or d.get('reason'))
    if check == 'total':
        return d.get('total') == expect['total'], d.get('total')
    if check == 'model':
        got = (d.get('readings_by_origin') or {}).get('model', 0)
        return got == expect['model'], got
    if check == 'fund_money':
        t = [x for x in d.get('totals_by_instrument') or []]
        got = dict(paid=sum(int(x.get('net_paid_minor') or 0) for x in t),
                   received=sum(int(x.get('net_received_minor') or 0) for x in t))
        formatted = all(x.get('net_paid') and x.get('currency_exponent') is not None for x in t)
        return got == expect and formatted, got
    if check == 'no_time':
        items = d.get('items') or []
        ok = bool(items) and all(i.get('execution_time') is None and 'execution_time' in (i.get('not_printed') or [])
                                 for i in items) and 'no time of execution' in (d.get('note') or '')
        return ok, len(items)
    if check == 'holdings':
        t = d.get('totals_by_instrument') or []
        ok = d.get('total') == expect['total'] and all(
            x.get('latest_market_value_minor') is None or x.get('latest_market_value') for x in t)
        return ok, d.get('total')
    if check == 'boundary':
        return d.get('reason') == expect['reason'] and not d.get('items'), d.get('reason')
    raise ValueError(check)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True)
    ap.add_argument('--detail')
    ap.add_argument('--label', default='')
    args = ap.parse_args()
    from services.agent.tools import AgentToolContext, _financial_session, make_agent_tools
    with _financial_session() as s:
        questions = build(s)
    results, tools_by_case = [], {}
    for q in questions:
        if q['case'] not in tools_by_case:
            ctx = AgentToolContext(case_id=q['case'], ledger_session_factory=_financial_session)
            tools_by_case[q['case']] = {t.name: t for t in make_agent_tools(ctx)}
        tool = tools_by_case[q['case']].get(q['tool'])
        if tool is None:
            ok, got = False, 'no tool'
        else:
            try:
                ok, got = score(q['check'], q['expect'], tool.invoke(q['args']))
            except Exception as exc:  # noqa: BLE001 - a crash is a failed answer, recorded
                ok, got = False, 'crash: %s' % type(exc).__name__
        results.append(dict(q, got=got, passed=ok))
        print('%s %s %s' % (q['id'], 'PASS' if ok else 'FAIL', q['tool']), flush=True)
    with open(args.out, 'w') as f:
        for r in results:
            f.write(json.dumps(dict(id=r['id'], case=r['case'][:8], question=r['q'], tool=r['tool'], check=r['check'],
                                    passed=r['passed'], label=args.label,
                                    reason=None if r['passed'] else (r['got'] if isinstance(r['got'], str) else
                                                                     'differs from the known answer'))) + '\n')
    if args.detail:
        with open(args.detail, 'w') as f:
            json.dump(results, f, indent=1, default=str)
    print('score %d/%d' % (sum(r['passed'] for r in results), len(results)))


if __name__ == '__main__':
    main()
