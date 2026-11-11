"""Which recorded tool calls fold into one call with agent-fit M and G, and does the folded call return everything the
calls it replaces returned (lx-agentfit R1). No model is called.

Input: a run recorded by financial_agent_fit_replay.py and the tool outputs financial_agent_trace_replay.py kept for
it (``--outputs`` pickle, in call order). A group is two or more consecutive calls of one foldable tool (re-reads
and notes between them are skipped): search_graph_entities, get_entity_details, get_entity_neighborhood (same
depth), get_financial_transactions (the same filters apart from ``search``). Each group is called once again through
the production tools with M and G on (live database, read-only sessions), and what it returns is compared with what
the old calls returned: entity keys, node keys, relationship triples, ledger row links and totals per search.

It also counts the steps a run would take if each step asked for every call that does not use an earlier result of
the same step (a call uses an earlier result when one of its argument values, four characters or more, appears in
that result): an upper bound of what batching (items P and X) can save, since the model decides what it batches.

Outputs are counts and keys only, under /mnt/owl-data/tmp (case material).
Usage (from backend/, via live-run.sh):
  financial_agent_collapse_check.py --recorded <run.json> --outputs <run.pkl> --out <check.json>
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import pickle

_HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location('fit_replay', os.path.join(_HERE, 'financial_agent_fit_replay.py'))
fit_replay = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fit_replay)  # read-only Postgres sessions and the socket guard

LIVE = {'read_tool_result_page', 'record_working_notes'}
FOLDABLE = {'search_graph_entities', 'get_entity_details', 'get_entity_neighborhood', 'get_financial_transactions'}


def _facts(name: str, data) -> set[str]:
    """What a result returned, as comparable strings."""
    found: set[str] = set()
    if not isinstance(data, dict):
        return found
    if name == 'search_graph_entities':
        for part in data.get('searches') or [data]:
            found |= {'entity:' + str(e.get('key')) for e in part.get('entities') or []}
    elif name == 'get_entity_details':
        for part in data.get('entities') or [data]:
            entity = part.get('entity') if isinstance(part, dict) else None
            if isinstance(entity, dict):
                found.add('entity:' + str(entity.get('key') or part.get('key')))
                for c in entity.get('connections') or []:
                    found.add('conn:%s:%s' % (c.get('relationship') or c.get('type'), c.get('key')))
    elif name == 'get_entity_neighborhood':
        for part in data.get('neighborhoods') or [data]:
            found |= {'node:' + str(n.get('key')) for n in part.get('nodes') or []}
            found |= {'link:%s>%s>%s' % (l.get('source'), l.get('type'), l.get('target')) for l in part.get('links') or []}
    elif name == 'get_financial_transactions':
        for part in data.get('searches') or [data]:
            search = part.get('search', '')
            for item in part.get('items') or []:
                if isinstance(item, dict) and item.get('cite'):
                    found.add('row:' + item['cite'])
            totals = part.get('totals') or part.get('matching_totals')
            if totals:
                found.add('totals:%s:%s' % (search, json.dumps(totals, sort_keys=True, default=str)))
            if part.get('total_matching') is not None:
                found.add('count:%s:%s' % (search, part.get('total_matching')))
    return found


def _key(name: str, args: dict) -> str:
    rest = {k: v for k, v in args.items() if k not in ('query', 'entity_key', 'search', 'limit')}
    return name + json.dumps(rest, sort_keys=True, default=str)


def groups_of(calls: list[dict]) -> list[list[int]]:
    """Runs of consecutive foldable calls with the same other arguments (re-reads and notes skipped)."""
    groups, current = [], []
    for index, call in enumerate(calls):
        if call['name'] in LIVE:
            continue
        if call['name'] in FOLDABLE and current and _key(call['name'], call['args']) == _key(
                calls[current[0]]['name'], calls[current[0]]['args']):
            current.append(index)
            continue
        if len(current) > 1:
            groups.append(current)
        current = [index] if call['name'] in FOLDABLE else []
    if len(current) > 1:
        groups.append(current)
    return groups


def folded_args(name: str, args_list: list[dict]) -> dict:
    first = dict(args_list[0])
    if name == 'search_graph_entities':
        return {'queries': [a.get('query') for a in args_list], 'limit': max(a.get('limit') or 10 for a in args_list)}
    if name == 'get_entity_details':
        return {'entity_keys': [a.get('entity_key') for a in args_list]}
    if name == 'get_entity_neighborhood':
        return {'entity_keys': [a.get('entity_key') for a in args_list], 'depth': first.get('depth') or 1}
    first.pop('search', None)
    return {**first, 'searches': [a.get('search') or '' for a in args_list]}


def batched_steps(calls: list[dict], outputs: list, ms: list[int]) -> tuple[int, int]:
    """Steps if each step asks for every call that uses no result of the same step (see the module docstring), and
    the tool milliseconds when each such step's calls run side by side (the slowest call of the step)."""
    steps, current_texts, side_ms, slowest = 0, [], 0, 0
    for call, output, took in zip(calls, outputs, ms):
        values = [v for v in _strings(call['args']) if len(v) >= 4]
        uses = any(v in text for v in values for text in current_texts)
        if not current_texts or uses:
            steps += 1
            side_ms += slowest
            current_texts, slowest = [], 0
        current_texts.append(json.dumps(output, ensure_ascii=False, default=str) if output is not None else '')
        slowest = max(slowest, took or 0)
    return steps, side_ms + slowest


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--recorded', required=True)
    ap.add_argument('--outputs', required=True)
    ap.add_argument('--out', required=True)
    cli = ap.parse_args()
    recorded = json.load(open(cli.recorded))
    calls = [{'name': t['name'], 'args': t.get('arguments') or {}} for t in recorded.get('trace') or [] if t.get('name')]
    with open(cli.outputs, 'rb') as f:
        kept = pickle.load(f)
    # outputs are kept for the investigative calls only, in call order
    outputs, k = [], 0
    for call in calls:
        if call['name'] in LIVE:
            outputs.append(None)
            continue
        name, out = kept[k] if k < len(kept) else (None, None)
        k += 1
        outputs.append(out if name == call['name'] and not isinstance(out, Exception) else None)

    os.environ['LOUPE_AGENT_FIT'] = 'M,G'
    from services.agent.tools import AgentToolContext, make_agent_tools
    fit_replay.stub_proposals()
    context = AgentToolContext(case_id=recorded['case'])
    tools = {t.name: t for t in make_agent_tools(context)}
    report = []
    for group in groups_of(calls):
        name = calls[group[0]]['name']
        old = set()
        for i in group:
            out = outputs[i]
            old |= _facts(name, (out or {}).get('data') if isinstance(out, dict) else None)
        args = folded_args(name, [calls[i]['args'] for i in group])
        try:
            new_out = tools[name].invoke(args)
            new = _facts(name, new_out.get('data'))
            error = new_out.get('error')
        except Exception as exc:  # noqa: BLE001 - a folded call that fails is a measured loss
            new, error = set(), '%s: %s' % (type(exc).__name__, str(exc)[:200])
        report.append({'tool': name, 'calls': len(group), 'old_facts': len(old), 'new_facts': len(new),
                       'missing': len(old - new), 'missing_kinds': sorted({m.split(':')[0] for m in old - new}),
                       'extra': len(new - old), 'error': error})
    recorded_ms = [t.get('ms') or 0 for t in recorded.get('tools') or []]
    recorded_ms += [0] * (len(calls) - len(recorded_ms))
    investigative = [(c, o, m) for c, o, m in zip(calls, outputs, recorded_ms) if c['name'] not in LIVE]
    steps, side_ms = batched_steps([c for c, _, _ in investigative], [o for _, o, _ in investigative],
                                   [m for _, _, m in investigative])
    out = {'recorded': cli.recorded, 'calls': len(calls), 'investigative_calls': len(investigative),
           'groups': report, 'calls_saved_by_folding': sum(g['calls'] - 1 for g in report),
           'folds_with_loss': sum(1 for g in report if g['missing'] or g['error']),
           'steps_one_call_each': len(investigative),
           'steps_batched_upper_bound': steps, 'tool_ms_one_by_one': sum(m for _, _, m in investigative),
           'tool_ms_batched_side_by_side': side_ms}
    with open(cli.out, 'w') as f:
        json.dump(out, f, indent=1, default=str)
    print(json.dumps({k: v for k, v in out.items() if k != 'groups'}))


if __name__ == '__main__':
    main()
