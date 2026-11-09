"""Replay one measured agent run offline and measure what every model request carries (lean runs, item B).

The model is scripted: it issues the live run's tool calls in the live run's batches, then gives a draft answer, so
no model provider is called (any connection to one is refused below). The tools are the real ones, against the live
database through read-only connections: every Postgres session of this process starts read-only
(``default_transaction_read_only``, checked before anything runs) and the proposal tools are stubbed, never run.
The runner is the production ``AgentGraphRunner.stream`` with its real prompts, budgets and message selection.

For every model request it records the characters of the system prompt, the conversation, each tool message and the
tool definitions sent with it, and prints them per step with the totals. ``--tokens`` divides the run's characters
by a measured total (the live run's prompt tokens) to give the characters-per-token ratio.

``--save-results`` keeps the tools' outputs (case values: local scratch, never committed) and ``--from-results``
replays them without the database, for measuring message selection quickly; tool time then is not measured.

Usage (from backend/, via live-run.sh):
  financial_agent_lean_replay.py --run 8df85211-... --out steps.json [--save-results r.json | --from-results r.json]
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import time

# Read-only before any connection exists: libpq sends this with every new session.
os.environ['PGOPTIONS'] = (os.environ.get('PGOPTIONS', '') + ' -c default_transaction_read_only=on').strip()
_getaddrinfo = socket.getaddrinfo
_PROVIDERS = ('openai.com', 'deepseek.com', 'anthropic.com', 'googleapis.com')


def _no_provider(host, *args, **kwargs):
    if host and any(name in str(host) for name in _PROVIDERS):
        raise OSError('replay: model provider connections are refused')
    return _getaddrinfo(host, *args, **kwargs)


socket.getaddrinfo = _no_provider
sys.path.insert(0, '.')

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage  # noqa: E402
from langchain_core.utils.function_calling import convert_to_openai_tool  # noqa: E402


def _chars(message):
    text = message.content if isinstance(message.content, str) else json.dumps(message.content, default=str)
    calls = getattr(message, 'tool_calls', None) or []
    return len(text) + (len(json.dumps([dict(name=c['name'], args=c['args'], id=c['id']) for c in calls],
                                       ensure_ascii=False, separators=(',', ':'))) if calls else 0)


class Recorder:
    def __init__(self, batches, draft, answer):
        self.batches, self.draft, self.answer = batches, draft, answer
        self.requests, self.tool_chars, self.turn, self.texts = [], 0, 0, []

    def record(self, kind, messages, tools_chars):
        parts = dict(system=0, human=0, assistant=0, tool_full=0, tool_digest=0)
        tools = []
        for m in messages:
            size = _chars(m)
            if isinstance(m, SystemMessage):
                parts['system'] += size
            elif isinstance(m, HumanMessage):
                parts['human'] += size
            elif isinstance(m, AIMessage):
                parts['assistant'] += size
            elif isinstance(m, ToolMessage):
                head = str(m.content)[:200]
                digest = '"digest_of"' in head or '"same_as"' in head
                parts['tool_digest' if digest else 'tool_full'] += size
                tools.append(dict(name=m.name, chars=size, digest=digest))
        total = sum(parts.values()) + tools_chars
        # The request as one text, tool definitions first (as the provider receives them): the characters it shares
        # from the start with an earlier request are what automatic prefix caching can serve (an estimate, not
        # measured: the provider caches in blocks and may evict).
        text = '\x01' * tools_chars + '\x00'.join('%s:%s:%s' % (type(m).__name__, getattr(m, 'tool_call_id', ''),
                                                             m.content if isinstance(m.content, str) else
                                                             json.dumps(m.content, default=str)) for m in messages)
        shared = max([len(os.path.commonprefix([text, earlier])) for earlier in self.texts] or [0])
        shared = min(shared, total)
        self.texts.append(text)
        if kind == 'finalizer' and not hasattr(self, 'final_text'):  # the finalizer's request, not a rewrite
            self.final_text = '\n'.join(str(m.content) for m in messages)
        self.requests.append(dict(kind=kind, total_chars=total, prefix_shared_chars_estimate=shared,
                                  tool_definitions=tools_chars, **parts,
                                  tool_messages=tools))
        return messages


class _Bound:
    def __init__(self, recorder, tools):
        self.recorder = recorder
        # As a LangChain chat model sends them: the lean definitions when the runner makes them, else the full ones.
        try:
            from services.agent.lean_history import tool_definitions
            definitions = tool_definitions(tools)
        except ImportError:
            definitions = [convert_to_openai_tool(t) for t in tools]
        self.tools_chars = len(json.dumps(definitions, ensure_ascii=False, separators=(',', ':')))

    def invoke(self, messages):
        r = self.recorder
        r.record('agent', messages, self.tools_chars)
        turn, r.turn = r.turn, r.turn + 1
        if turn < len(r.batches):
            calls = [dict(name=c['name'], args=c['args'], id='call_%d' % c['seq'], type='tool_call')
                     for c in r.batches[turn]]
            return AIMessage(content='', tool_calls=calls)
        return AIMessage(content=r.draft)


class ScriptedModel:
    def __init__(self, recorder):
        self.recorder = recorder

    def bind_tools(self, tools):
        return _Bound(self.recorder, tools)

    def invoke(self, messages):
        self.recorder.record('finalizer', messages, 0)
        return AIMessage(content=self.recorder.answer)


def _q(session, sql, **params):
    from sqlalchemy import text
    return session.execute(text(sql), params)


def load_run(session, run_id):
    run = _q(session, "SELECT r.case_id::text AS case_id, r.thread_id, r.input_message, r.final_answer, r.usage, "
                      "r.extra_metadata, r.mandate_override, t.mandate_version_id FROM agent_runs r JOIN agent_threads t "
                      "ON t.id = r.thread_id WHERE r.id = CAST(:r AS uuid)", r=run_id).mappings().one()
    calls = [dict(c) for c in _q(session, "SELECT sequence_number AS seq, name, arguments AS args, duration_ms, "
                                          "created_at, result_preview FROM agent_tool_calls WHERE run_id = "
                                          "CAST(:r AS uuid) ORDER BY sequence_number", r=run_id).mappings()]
    # One tools step stores its calls together when it ends: calls stored within a second are one batch.
    batches, last = [], None
    for c in calls:
        if last is None or (c['created_at'] - last).total_seconds() > 1.0:
            batches.append([])
        batches[-1].append(c)
        last = c['created_at']
    return dict(run), batches


def prompt_block(session, run):
    from services.agent import proposal_feedback, workflows
    from services.agent.service import DEFAULT_AGENT_MAX_TOOL_CALLS
    from services.mandate_context_service import mandate_context_service
    import uuid
    mandate = mandate_context_service.resolve(session, case_id=uuid.UUID(run['case_id']),
                                              version_id=run['mandate_version_id'], override=run['mandate_override'])
    meta = run['extra_metadata'] or {}
    workflow = (meta.get('workflow') or {}).get('id')
    plan = workflows.render_block(workflows.get(workflow), budget=DEFAULT_AGENT_MAX_TOOL_CALLS) if workflow else ''
    feedback = meta.get('proposal_feedback')
    block = '\n\n'.join(x for x in (mandate.block, plan, proposal_feedback.block(feedback)) if x)
    rules = workflows.final_rules(workflows.get(workflow)) if workflow else ''
    return block, rules


CONTEXTS = []


def patch_tools(stubs, saved, save):
    """Proposal tools never run; with --from-results every tool returns its saved output."""
    from services.agent import graph
    real = graph.make_agent_tools

    def make(context):
        CONTEXTS.append(context)
        tools = real(context)
        for tool in tools:
            original = tool.func

            def run(*args, _name=tool.name, _original=original, **kwargs):
                if _name.startswith('propose_') or saved is not None:
                    key = _name + json.dumps(kwargs, sort_keys=True, default=str)
                    out = (saved or {}).get(key) or stubs.get(_name) or {}
                    out = dict(out)
                    if out.get('result_id'):
                        out['result_id'] = context.result(_name, out.get('data'), summary=out.get('summary', ''))[
                            'result_id']
                    return out
                out = _original(*args, **kwargs)
                if save is not None:
                    save[_name + json.dumps(kwargs, sort_keys=True, default=str)] = out
                return out
            tool.func = run
        return tools
    graph.make_agent_tools = make


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--run', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--tokens', type=int, help='measured prompt tokens of the live run, to calibrate chars/token')
    ap.add_argument('--save-results')
    ap.add_argument('--from-results')
    ap.add_argument('--finalizer-dump', help='write the finalizer request text here (local scratch)')
    args = ap.parse_args()

    from services.agent.tools import _financial_session
    from postgres.session import _get_engine
    from sqlalchemy import text
    with _get_engine().connect() as c:
        if c.execute(text('SHOW default_transaction_read_only')).scalar() != 'on':
            raise SystemExit('refusing to run: sessions are not read-only')
    with _financial_session() as s:
        run, batches = load_run(s, args.run)
        block, rules = prompt_block(s, run)
    stubs = {c['name']: dict(result_id='stub', summary='Proposal stubbed in the replay; nothing was saved.',
                             data=c['result_preview']) for b in batches for c in b if c['name'].startswith('propose_')}
    saved = json.load(open(args.from_results)) if args.from_results else None
    save = {} if args.save_results else None
    patch_tools(stubs, saved, save)
    answer = run['final_answer'] or ''
    recorder = Recorder([[dict(seq=c['seq'], name=c['name'], args=c['args']) for c in b] for b in batches],
                        draft=answer, answer=answer)

    from services.agent.graph import AgentGraphRunner
    runner = AgentGraphRunner.__new__(AgentGraphRunner)
    runner.provider, runner.model_id, runner.base_model = 'deepseek', 'deepseek-v4-pro', ScriptedModel(recorder)
    started = time.perf_counter()
    durations = []
    for event in runner.stream(case_id=run['case_id'], messages=[HumanMessage(content=run['input_message'])],
                               thread_id='replay', available_artifacts=[], mandate_context_block=block,
                               final_answer_rules=rules,
                               proposer=dict(for_name='replay', for_user_id=None, for_email=None, model='replay',
                                             model_id='deepseek-v4-pro', provider='deepseek', run_id=None,
                                             thread_id=None, can_propose=True)):
        if event.get('type') == 'tool_result':
            t = event['tool']
            durations.append(dict(name=t['name'], ms=t['duration_ms'], status=t['status']))
    wall = time.perf_counter() - started
    total = sum(r['total_chars'] for r in recorder.requests)
    shared = sum(r['prefix_shared_chars_estimate'] for r in recorder.requests)
    report = dict(run=args.run, batches=[[c['name'] for c in b] for b in batches], requests=recorder.requests,
                  total_chars=total, prefix_shared_chars_estimate=shared, tool_ms=sum(d['ms'] for d in durations), wall_s=round(wall, 1),
                  tool_calls=durations, mandate_block_chars=len(block), final_rules_chars=len(rules),
                  ledger_cache=[getattr(getattr(c, 'ledger_cache', None), 'stats', None) for c in CONTEXTS])
    if args.tokens:
        report['chars_per_token'] = round(total / args.tokens, 3)
    with open(args.out, 'w') as f:
        json.dump(report, f, indent=1, default=str)
    if args.save_results:
        with open(args.save_results, 'w') as f:
            json.dump(save, f, default=str)
    if args.finalizer_dump:
        with open(args.finalizer_dump, 'w') as f:
            f.write(getattr(recorder, 'final_text', ''))
    for i, r in enumerate(recorder.requests):
        print('%2d %-9s total %8d sys %6d tooldefs %6d human %4d ai %6d tool_full %7d tool_digest %6d prefix~ %7d' % (
            i + 1, r['kind'], r['total_chars'], r['system'], r['tool_definitions'], r['human'], r['assistant'],
            r['tool_full'], r['tool_digest'], r['prefix_shared_chars_estimate']))
    print('ledger cache', report['ledger_cache'])
    print('total chars %d; shared prefix (estimate, not measured) %d; tool time %.1f s; wall %.1f s' % (
        total, shared, report['tool_ms'] / 1000, wall))
    if args.tokens:
        print('chars per token %.3f against %d measured prompt tokens (a calibration only when this replays the code '
              'that ran live)' % (report['chars_per_token'], args.tokens))


if __name__ == '__main__':
    main()
