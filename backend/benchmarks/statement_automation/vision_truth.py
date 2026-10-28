"""Truth check of the page-image reader (vision_reader) on a finished benchmark database.

Measures only (``read_item(apply=False)``): nothing is stored or saved. Run on a
COPY of a whole-set benchmark's ``benchmark.db``; its ``results*.json`` maps each
batch item to its truth period.

* ``--mode held``: every statement the rule readers hold (status attention), the
  only statements the reader acts on. A proved reading is compared with the truth
  period: account, period, opening, closing and every row (date, amount,
  direction). wrong = proved but differs from the truth, or proved where the truth
  expects a hold or a decision; double = proved for a truth period already saved.
* ``--mode sample``: N saved (auto) statements forced through the reader, to
  measure its raw accuracy (proved share; proved readings that differ from truth).

Output: one JSON line per statement to ``--out`` and a summary line at the end.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
import uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


def _truths(manifest):
    data = json.loads(Path(manifest).read_text())
    return {p['id']: dict(p, filename=f['filename']) for f in data['files'] for p in f['periods']}


def _digits(text):
    return ''.join(ch for ch in str(text or '') if ch.isdigit())


def compare(record, truth):
    """Differences between a proved reading (its review request) and the truth period."""
    request = record['request']
    diffs = []
    want, got_number = _digits(truth.get('account')), _digits(request['account_number'])
    # A number printed with a sub-account (member number / share) contains the truth's number.
    if want and not (got_number.endswith(want[-4:]) or want in got_number):
        diffs.append('account')
    for key in ('period_start', 'period_end'):
        if truth.get(key) and request.get(key) != truth[key]:
            diffs.append(key)
    if truth.get('currency') and request['currency'] != truth['currency']:
        diffs.append('currency')
    balances = {r['id']: r for r in request['rows'] if r['excluded'] and r.get('balance_minor') not in (None, '')}
    rows = [r for r in request['rows'] if not r['excluded']]
    opening = next((int(r['balance_minor']) for i, r in balances.items() if 'opening' in i or r.get('description', '').lower() == 'opening balance'), None)
    closing = next((int(r['balance_minor']) for i, r in balances.items() if 'closing' in i or r.get('description', '').lower() == 'closing balance'), None)
    if truth.get('opening_minor') is not None and opening is not None and opening != truth['opening_minor']:
        diffs.append('opening')
    if truth.get('closing_minor') is not None and closing is not None and closing != truth['closing_minor']:
        diffs.append('closing')
    got = Counter((r['date'], int(r['amount_minor']), r['direction']) for r in rows)
    want = Counter((r['date'], int(r['amount_minor']), r['direction']) for r in truth.get('rows') or [])
    if got != want:
        diffs.append(f'rows(extra {sum((got - want).values())}, missing {sum((want - got).values())})')
    return diffs


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--db', required=True)
    parser.add_argument('--results', required=True)
    parser.add_argument('--manifest', required=True)
    parser.add_argument('--mode', choices=('held', 'sample'), default='held')
    parser.add_argument('--sample', type=int, default=30)
    parser.add_argument('--limit', type=int, default=0)
    parser.add_argument('--workers', type=int, default=3)
    parser.add_argument('--out', required=True)
    parser.add_argument('--key-from-live', action='store_true')
    parser.add_argument('--raw', action='store_true', help='keep the page readings (server-side diagnosis only)')
    parser.add_argument('--items', default='', help='comma-separated item ids')
    parser.add_argument('--ignore-switch', action='store_true',
                        help='send to OpenAI although "DeepSeek only" is ON in the live policy (a deliberate measurement)')
    parser.add_argument('--readers', default='',
                        help='the reader chain, e.g. "deepseek" (DeepSeek only: OpenAI switched off), "openai", '
                             '"deepseek,openai"; keys from the live store (read only). Default: OpenAI alone, '
                             'unnamed (as before the chain)')
    args = parser.parse_args(argv)
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from benchmarks.statement_automation.harness import _load_models
    from services.financial import vision_reader
    from config import OPENAI_API_KEY
    keys = {}
    named = [r.strip() for r in args.readers.split(',') if r.strip()] if args.readers else ['openai']
    if 'openai' in named and not args.ignore_switch:
        # "DeepSeek only" is honoured here too: nothing goes to OpenAI unless asked for explicitly.
        from postgres.session import _get_session_local
        from services.ai_model_policy import deepseek_only
        with _get_session_local()() as live:
            if deepseek_only(live):
                raise SystemExit('"DeepSeek only" is ON: OpenAI is not sent page images (pass --ignore-switch to '
                                 'measure OpenAI deliberately).')
            live.rollback()
    if args.key_from_live or args.readers:
        # The application's stored keys (read only), as the product uses them.
        from sqlalchemy import text
        from postgres.session import _get_session_local
        from services.ai_provider_credentials import credential_store
        with _get_session_local()() as live:
            live.execute(text('SET TRANSACTION READ ONLY'))
            keys = {p: credential_store.get_api_key(live, p) for p in ('openai', 'deepseek')}
            OPENAI_API_KEY = keys['openai']
            live.rollback()
    _load_models()
    engine = create_engine(f'sqlite+pysqlite:///{args.db}', future=True, connect_args=dict(timeout=300, check_same_thread=False))
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    truths = _truths(args.manifest)
    periods = json.loads(Path(args.results).read_text())['periods']
    if args.mode == 'held':
        chosen = [p for p in periods if p['status'] == 'attention']
    else:
        pool = [p for p in periods if p['status'] == 'imported' and p.get('expected') == 'auto' and p.get('truth_id')]
        random.Random(19).shuffle(pool)
        chosen = pool[:args.sample]
    if args.items:
        wanted = set(args.items.split(','))
        chosen = [p for p in periods if p['item_id'] in wanted]
    if args.limit:
        chosen = chosen[:args.limit]
    saved_truth = {p['truth_id'] for p in periods if p['status'] == 'imported' and p.get('truth_id')}
    from services.ai_model_policy import FINANCIAL_VISION_OPENAI
    # Without --readers: OpenAI alone, unnamed (as before the chain); refused while "DeepSeek only" is ON unless --ignore-switch.
    model_id = os.environ.get('VISION_TRUTH_MODEL') or FINANCIAL_VISION_OPENAI['model_id']

    def page_reader(db, case_id):
        if not OPENAI_API_KEY:
            raise RuntimeError('No OpenAI key')
        return model_id, vision_reader.document_request(model_id, OPENAI_API_KEY)

    if args.readers:
        from services.ai_model_policy import FINANCIAL_VISION_DEEPSEEK, FINANCIAL_VISION_OPENAI
        models = {'deepseek': FINANCIAL_VISION_DEEPSEEK['model_id'], 'openai': FINANCIAL_VISION_OPENAI['model_id']}

        def page_reader(db, case_id):  # noqa: F811 - the chain, built as chain_page_reader builds it
            chain = [vision_reader.keyed_page_reader(p, models[p], keys.get(p), context='truth') for p in named]
            if named == ['deepseek']:
                # "DeepSeek only": the OpenAI reader is switched off, nothing is sent to it.
                chain.append(vision_reader.PageReader(
                    provider='openai', model=models['openai'], read=None, switched_off=True, strips=None,
                    unavailable='OpenAI failover is switched off', max_output_tokens=vision_reader.RESERVE_OUTPUT_TOKENS))
            return chain

    def one(period):
        started = time.monotonic()
        record = vision_reader.read_item(factory, uuid.UUID(period['item_id']), lambda path: path, page_reader=page_reader,
                                         apply=False, force=args.mode == 'sample')
        truth = truths.get(period.get('truth_id') or '')
        line = dict(item_id=period['item_id'], truth_id=period.get('truth_id'), family=period.get('family'),
                    expected=period.get('expected'), status=record.get('status'), reason=record.get('reason'),
                    message=record.get('message'), pages=len(record.get('pages') or []),
                    cost_usd=record.get('cost_usd'), seconds=round(time.monotonic() - started, 1),
                    page_costs=record.get('page_costs'), provider=record.get('provider'),
                    prompt_version=record.get('prompt_version'),
                    attempts=[{k: a.get(k) for k in ('provider', 'status', 'seconds', 'cost_usd', 'message')}
                              for a in record.get('attempts') or []])
        if args.raw and record.get('raw'):
            line['raw'] = record['raw']
        if record.get('status') == 'proved':
            line['rows'] = record.get('rows')
            if truth is None:
                line['verdict'] = 'unscored'
            elif truth.get('expected') in ('hold', 'decision', 'duplicate') and args.mode == 'held':
                line['verdict'] = 'wrong_expected_' + truth['expected']
            else:
                diffs = compare(record, truth)
                line['verdict'] = 'wrong' if diffs else 'correct'
                line['diffs'] = diffs
                line['account_digits'] = len(_digits(record['request']['account_number']))
            if args.mode == 'held' and period.get('truth_id') in saved_truth:
                line['double'] = True
        return line

    totals = Counter()
    cost = 0.0
    with open(args.out, 'w') as out, ThreadPoolExecutor(max_workers=args.workers) as pool:
        for line in pool.map(one, chosen):
            out.write(json.dumps(line) + '\n')
            out.flush()
            totals[line['status'] or 'none'] += 1
            if line.get('verdict'):
                totals['verdict_' + line['verdict']] += 1
            if line.get('double'):
                totals['double'] += 1
            cost += line.get('cost_usd') or 0
        summary = dict(summary=True, mode=args.mode, statements=len(chosen), cost_usd=round(cost, 4),
                       **totals)
        out.write(json.dumps(summary) + '\n')
    print('Full results', json.dumps(summary))


if __name__ == '__main__':
    sys.exit(main())
