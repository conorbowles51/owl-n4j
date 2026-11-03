"""Agent ledger evaluation (agent-ledger E; AGENT-INDEX rule 6): 12 ledger questions on BNB2 and the verification
case, each asked through the agent's own tool layer (make_agent_tools with the run's case, read-only sessions) and
scored against a known answer computed here by plain SQL, independently of the code under test.

Run the same script on the release tree and on the tree before it (a tool that does not exist scores "no tool").
Writes one JSON line per question to --out (scores and counts only; the detail file --detail is local scratch and
holds case values, never committed).

Usage (from backend/, via live-run.sh): financial_agent_ledger_eval.py --out scores.jsonl --detail detail.json
"""
from __future__ import annotations

import argparse
import json
import sys
from contextlib import contextmanager

sys.path.insert(0, '.')

from sqlalchemy import text  # noqa: E402

BNB2, VERIFY = 'd5b330d1', 'cded78d0'
STATEMENT_ROW_RULES = ('agent.page_entry', 'model.statement_save', 'image.page_reading', 'reader.replacement',
                       'L30c.contract_refile', 'agent.refile', 'agent.currency_refile', 'L4.currency_from_name',
                       'autofill.currency_account', 'autofill.currency_case', 'holder.printed_on_statement',
                       'model.statement_account')
CURRENT_CALLS = ("FROM financial_judgements j LEFT JOIN financial_source_documents d ON d.id = j.source_document_id "
                 "WHERE j.case_id = :c AND (j.source_document_id IS NULL OR d.status <> 'superseded')")


def q1(s, sql, **p):
    return s.execute(text(sql), p).scalar()


def rows_open_calls(s, case, row_ids, doc_ids):
    """Open current calls touching these payments: on the payment, a correction naming it, or on its statement."""
    if not row_ids:
        return 0
    return int(q1(s, "SELECT count(DISTINCT j.id) " + CURRENT_CALLS + " AND j.status = 'open' AND ("
                  "(j.subject_type = 'transaction' AND j.subject_id = ANY(CAST(:r AS uuid[]))) OR "
                  "(j.rule_id = 'agent.correction' AND j.evidence->>'transaction_id' = ANY(:rs)) OR "
                  "(j.rule_id = ANY(:rules) AND j.source_document_id = ANY(CAST(:d AS uuid[]))))",
                  c=case, r=row_ids, rs=row_ids, d=doc_ids, rules=list(STATEMENT_ROW_RULES)) or 0)


def family(s, case, account):
    canon = q1(s, "SELECT coalesce(metadata->>'canonical_account_id', id::text) FROM financial_accounts WHERE id = "
                  "CAST(:a AS uuid)", a=account)
    return [r[0] for r in s.execute(text(
        "SELECT id::text FROM financial_accounts WHERE case_id = :c AND coalesce(metadata->>'canonical_account_id', "
        "id::text) = :k"), {'c': case, 'k': canon})]


ADMITTED = ("FROM financial_transactions t JOIN financial_source_documents d ON d.id = t.source_document_id "
            "WHERE t.case_id = :c AND t.ledger_status = 'admitted' AND t.superseded_by_id IS NULL AND "
            "d.status = 'admitted' AND t.proof_class IN ('p0','p1','p2','p3') AND d.proof_class IN "
            "('p0','p1','p2','p3')")


def build(s):
    cases = {k: str(q1(s, "SELECT id FROM cases WHERE id::text LIKE :p", p=k + '%')) for k in (BNB2, VERIFY)}
    b, v = cases[BNB2], cases[VERIFY]
    Q = []
    # the one reviewed identity pair in BNB2 (an account linked as the other side)
    pair = s.execute(text("SELECT t.account_id::text AS a, t.metadata->'investigation_labels'->'counterparty_link' AS l "
                          + ADMITTED.replace("FROM financial_transactions t", "FROM financial_transactions t", 1) +
                          " AND jsonb_typeof(t.metadata->'investigation_labels'->'counterparty_link') = 'object' "
                          "LIMIT 1"), {'c': b}).first()
    fam = family(s, b, pair.a)
    other = family(s, b, pair.l['id'])
    canon_other = q1(s, "SELECT coalesce(metadata->>'canonical_account_id', id::text) FROM financial_accounts WHERE "
                        "id = CAST(:a AS uuid)", a=pair.l['id'])
    linked = list(s.execute(text(
        "SELECT t.id::text AS id, t.source_document_id::text AS d, t.amount_minor AS m, t.direction AS dir, "
        "t.proof_class AS pc, t.currency AS cur " + ADMITTED + " AND t.account_id = ANY(CAST(:f AS uuid[])) AND "
        "t.metadata->'investigation_labels'->'counterparty_link'->>'id' = ANY(:o)"), {'c': b, 'f': fam, 'o': other}))
    exp_p3_ab = sum(int(r.m) for r in linked if r.pc == 'p3' and r.dir == 'debit')
    exp_p3_ba = sum(int(r.m) for r in linked if r.pc == 'p3' and r.dir == 'credit')
    exp_v = sum(int(r.m) for r in linked if r.pc in ('p0', 'p1', 'p2'))
    exp_calls = rows_open_calls(s, b, [r.id for r in linked], sorted({r.d for r in linked}))
    args = dict(party_a='account:%s' % pair.a, party_b='account:%s' % canon_other)
    Q.append(dict(id='L01', case=b, q='How much moved between the two linked BNB2 accounts (verified, and p3 apart)?',
                  tool='get_money_between', args=args,
                  expect=dict(verified_minor=exp_v, p3_ab=exp_p3_ab, p3_ba=exp_p3_ba, payments=len(linked)),
                  check='money'))
    Q.append(dict(id='L02', case=b, q='How many open judgement calls does that figure rest on?',
                  tool='get_money_between', args=args, expect=dict(open_calls=exp_calls), check='money_calls'))
    Q.append(dict(id='L03', case=b, q='How many open judgement calls are there in BNB2?', tool='get_judgement_calls',
                  args=dict(status='open', limit=1),
                  expect=dict(total=int(q1(s, "SELECT count(*) " + CURRENT_CALLS + " AND j.status = 'open'", c=b))),
                  check='total'))
    p = s.execute(text("SELECT j.subject_id::text AS p, count(*) AS n " + CURRENT_CALLS + " AND j.subject_type = "
                       "'transaction' GROUP BY 1 ORDER BY 2 DESC, 1 LIMIT 1"), {'c': b}).first()
    Q.append(dict(id='L04', case=b, q='Which judgement calls are on this payment?', tool='get_judgement_calls',
                  args=dict(subject='payment:%s' % p.p), expect=dict(total=int(p.n)), check='total'))
    d = s.execute(text("SELECT subject_id::text AS p, count(*) AS n, count(*) FILTER (WHERE actor_origin->>'kind' = "
                       "'model') AS m FROM adjudications WHERE case_id = :c AND subject_type = 'transaction' GROUP BY 1 "
                       "ORDER BY 3 DESC, 2 DESC, 1 LIMIT 1"), {'c': b}).first()
    Q.append(dict(id='L05', case=b, q='Who decided what on this payment, and did a model draft any of it?',
                  tool='get_decisions', args=dict(subject='payment:%s' % d.p),
                  expect=dict(total=int(d.n), model_drafted=int(d.m)), check='decisions'))
    acc = s.execute(text("SELECT p.account_id::text AS a, count(*) AS n FROM financial_statement_periods p JOIN "
                         "financial_source_documents d ON d.id = p.source_document_id WHERE p.case_id = :c AND "
                         "d.status = 'admitted' GROUP BY 1 ORDER BY 2 DESC, 1 LIMIT 1"), {'c': b}).first()
    afam = family(s, b, acc.a)
    span = s.execute(text("SELECT min(p.period_start), max(p.period_end), count(*) FROM financial_statement_periods p "
                          "JOIN financial_source_documents d ON d.id = p.source_document_id WHERE p.case_id = :c AND "
                          "d.status = 'admitted' AND p.account_id = ANY(CAST(:f AS uuid[]))"), {'c': b, 'f': afam}).first()
    Q.append(dict(id='L06', case=b, q='Which dates do this account\'s statements cover?', tool='get_statement_continuity',
                  args=dict(account=acc.a), expect=dict(covered_from=span[0].isoformat(), covered_to=span[1].isoformat()),
                  check='coverage'))
    Q.append(dict(id='L07', case=b, q='How many statement periods does that account have, and where are the gaps?',
                  tool='get_statement_continuity', args=dict(account=acc.a, limit=100),
                  expect=dict(periods=int(span[2])), check='periods'))
    Q.append(dict(id='L08', case=b, q='What has the investigator added to the BNB2 Timeline?', tool='get_timeline_events',
                  args=dict(limit=5), expect=dict(additions=int(q1(s, "SELECT count(*) FROM timeline_entries WHERE "
                                                                     "case_id = :c", c=b))), check='additions'))
    rows = list(s.execute(text("SELECT t.id::text AS id, t.source_document_id::text AS d, t.amount_minor AS m, "
                               "t.direction AS dir " + ADMITTED + " AND t.account_id = ANY(CAST(:f AS uuid[]))"),
                          {'c': b, 'f': afam}))
    Q.append(dict(id='L09', case=b, q='How much went out of that account, and how many open judgement calls does it '
                  'rest on?', tool='analyze_financial_transactions', args=dict(group_by='account', account_ids=[acc.a]),
                  expect=dict(debits=sum(int(r.m) for r in rows if r.dir == 'debit'),
                              open_calls=rows_open_calls(s, b, [r.id for r in rows], sorted({r.d for r in rows}))),
                  check='account_out'))
    Q.append(dict(id='L10', case=b, q='Sum the graph payments of that account (graph money must say it is not a total).',
                  tool='run_readonly_cypher',
                  args=dict(query="MATCH (a:FinancialAccount {case_id: $case_id})-[r:TRANSFERRED_TO {case_id: "
                                  "$case_id}]->(t:FinancialTransaction {case_id: $case_id}) RETURN t.currency AS "
                                  "currency, sum(t.amount_minor) AS out_minor LIMIT 10"),
                  expect=dict(note=True), check='graph_note'))
    vd = s.execute(text("SELECT subject_type AS st, subject_id::text AS p, count(*) AS n, count(*) FILTER (WHERE "
                        "actor_origin->>'kind' = 'model') AS m FROM adjudications WHERE case_id = :c AND subject_type "
                        "IN ('transaction','account','source_document','statement_period') GROUP BY 1, 2 ORDER BY 4 "
                        "DESC, 3 DESC, 2 LIMIT 1"), {'c': v}).first()
    kind = {'transaction': 'payment', 'source_document': 'statement', 'statement_period': 'period',
            'account': 'account'}[vd.st]
    Q.append(dict(id='L11', case=v, q='In the verification case, who decided this record and did a model draft it?',
                  tool='get_decisions', args=dict(subject='%s:%s' % (kind, vd.p)),
                  expect=dict(total=int(vd.n), model_drafted=int(vd.m)), check='decisions'))
    Q.append(dict(id='L12', case=v, q='How many judgement calls does the verification case have, by status?',
                  tool='get_judgement_calls', args=dict(limit=5),
                  expect=dict(total=int(q1(s, "SELECT count(*) " + CURRENT_CALLS, c=v))), check='total'))
    return Q


def score(check, expect, out):
    d = out.get('data') or {}
    if out.get('status') != 'success':
        return False, 'tool error: %s' % (out.get('error') or d.get('reason'))
    if check == 'money':
        t = d.get('totals') or []
        v = sum(int(x['paid_ab_minor']) + int(x['paid_ba_minor']) for x in t)
        p3ab = sum(int(x['p3']['paid_ab_minor']) for x in t)
        p3ba = sum(int(x['p3']['paid_ba_minor']) for x in t)
        got = dict(verified_minor=v, p3_ab=p3ab, p3_ba=p3ba, payments=d.get('total'))
        return got == expect, got
    if check == 'money_calls':
        got = (d.get('open_judgement_calls') or {}).get('open_calls')
        return got == expect['open_calls'], got
    if check == 'total':
        return d.get('total') == expect['total'], d.get('total')
    if check == 'decisions':
        got = dict(total=d.get('total'), model_drafted=d.get('model_drafted'))
        return got == expect, got
    if check == 'coverage':
        c = d.get('coverage') or {}
        got = dict(covered_from=c.get('covered_from'), covered_to=c.get('covered_to'))
        return got == expect, got
    if check == 'periods':
        got = dict(saved=d.get('periods_saved'), in_run=d.get('total'), left_out=len(d.get('excluded_periods') or []))
        ok = got['saved'] == expect['periods'] and got['in_run'] + got['left_out'] == expect['periods'] and \
            'gaps' in (d.get('coverage') or {}) and (got['left_out'] == 0 or 'left out' in (d.get('sentence') or ''))
        return ok, got
    if check == 'additions':
        a = d.get('investigator_additions')
        got = a.get('total') if isinstance(a, dict) else None
        return got == expect['additions'], got
    if check == 'account_out':
        t = d.get('totals') or []
        debits = sum(int(x['debits_minor']) for x in t)
        calls = (d.get('open_judgement_calls') or {}).get('open_calls')
        got = dict(debits=debits, open_calls=calls)
        return got == expect, got
    if check == 'graph_note':
        return bool(d.get('money_basis')), d.get('money_basis')
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
