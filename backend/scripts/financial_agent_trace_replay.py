"""Push a recorded agent run's tool calls through the production agent loop again, with no model (lx-agentfit R1/R2).

A run recorded by financial_agent_fit_replay.py (its ``trace``: each tool call's name and arguments, in order) is
replayed through ``AgentGraphRunner.stream`` with a scripted model in place of DeepSeek: the scripted model asks for
the recorded calls, ``--group`` at a time (default one per step, as the recorded runs mostly made them), then gives
the recorded answer. Everything else is the production path: the system prompt, the tool definitions as bound, the
real tools on the live database (read-only sessions, proposals stubbed), the lean history, the finalizer.

Per model request it records what DeepSeek would have been sent (the request payload as the production DeepSeek
client builds it) and counts it with DeepSeek's tokenizer (``--tokenizer``, DeepSeek-V3.2's tokenizer.json; the
v4 tokenizer is not published, so counts are labelled as from V3.2). The cache read each request would get is
simulated two ways from DeepSeek's context-caching guide (api-docs.deepseek.com/guides/kv_cache): ``strict``, a hit
only up to the end of an earlier request's input or output (a stored prefix unit); ``loose``, up to the longest
prefix shared with any earlier request, in 64-token steps (common-prefix units). Real hits fall at or below loose.

The assistant turns' reasoning is not in the trace. Each scripted turn carries filler reasoning of the run's
measured completion tokens per step, so the prompt grows as the real one did (``--no-filler`` leaves it out).

Nothing calls a model service: DeepSeek, Anthropic and Google are refused at the socket; document search's query
embedding (OpenAI) is allowed with LOUPE_FIT_ALLOW_EMBEDDINGS=1, as in the recorded runs. Outputs hold case
material (tool results): ``--out`` goes under /mnt/owl-data/tmp, never into the repo.

Usage (from backend/, via live-run.sh):
  financial_agent_trace_replay.py --recorded /mnt/owl-data/tmp/lx-agentfit/base/demo-Q1-1.json --out r.json
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import socket
import sys
import time
from typing import Any

_HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location('fit_replay', os.path.join(_HERE, 'financial_agent_fit_replay.py'))
fit_replay = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fit_replay)


# The case reader the tools check access for (get_document_text refuses a run with no reader): the jobs login's
# user id, given with --user-id or LOUPE_REPLAY_USER_ID. Reads only; never a proposer.
REPLAY_USER_ID = os.environ.get('LOUPE_REPLAY_USER_ID') or None

def guard_process():
    """fit_replay's guards (read-only sessions, no model service) and no DeepSeek either. Called by main(), never
    on import (a test importing this file must keep its own process writable)."""
    fit_replay.guard_process()
    if getattr(socket.getaddrinfo, '_trace_guard', False):
        return
    inner = socket.getaddrinfo

    def _no_model(host, *args, **kwargs):
        if host and 'deepseek.com' in str(host):
            raise OSError('trace replay: no model service may be called')
        return inner(host, *args, **kwargs)

    _no_model._trace_guard = _no_model._replay_guard = True  # it calls fit_replay's guard inside
    socket.getaddrinfo = _no_model

CITE = re.compile(r'(?:txn|doc|rec)://[^\s"\')\]\\]+')
PAGE_TOOL = 'read_tool_result_page'


def _scripted_model(steps: list[list[dict]], answer: str, filler_tokens: int, log: list):
    """A chat model that asks for ``steps`` in order (rewriting earlier result ids to this replay's ids), then
    answers ``answer``. Every request it receives is kept in ``log``."""
    from langchain_core.language_models import BaseChatModel
    from langchain_core.messages import AIMessage
    from langchain_core.outputs import ChatGeneration, ChatResult

    state = {'next': 0, 'ids': {}, 'n': 0, 'tools': None}

    def remap(value):
        if isinstance(value, str):
            for old, new in state['ids'].items():
                value = value.replace(old, new)
            return value
        if isinstance(value, list):
            return [remap(v) for v in value]
        if isinstance(value, dict):
            return {k: remap(v) for k, v in value.items()}
        return value

    class Scripted(BaseChatModel):
        @property
        def _llm_type(self) -> str:
            return 'scripted'

        def bind_tools(self, tools, **kwargs):
            state['tools'] = tools
            return self

        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            # Map the recorded result ids onto the ids this replay's results got, in call order.
            log.append({'messages': list(messages), 'tools': state['tools']})
            filler = ' '.join('w%d' % (i % 97) for i in range(filler_tokens)) if filler_tokens else ''
            if state['next'] < len(steps):
                calls = []
                for item in steps[state['next']]:
                    state['n'] += 1
                    calls.append({'name': item['name'], 'args': remap(item.get('arguments') or {}),
                                  'id': 'call_r%03d' % state['n'], 'type': 'tool_call'})
                state['next'] += 1
                msg = AIMessage(content='', tool_calls=calls, additional_kwargs={'reasoning_content': filler})
            else:
                state['next'] = len(steps) + 1
                msg = AIMessage(content=answer, additional_kwargs={'reasoning_content': filler})
            return ChatResult(generations=[ChatGeneration(message=msg)])

    return Scripted(), state, remap


# Read again from the run, so a cached replay still runs them: they read this run's own results.
_LIVE_TOOLS = frozenset({PAGE_TOOL, 'record_working_notes'})


def _cache_outputs(graph, path):
    """With ``path``: each investigative tool's output is kept in call order (written at the end) or, when the file
    exists, given back from it instead of running the tool."""
    if not path:
        return None
    import pickle
    cached = {'write': not os.path.exists(path), 'outputs': [], 'n': 0}
    if not cached['write']:
        with open(path, 'rb') as f:
            cached['outputs'] = pickle.load(f)
    inner = graph.make_agent_tools

    def make(context):
        tools = inner(context)
        for tool in tools:
            if tool.name in _LIVE_TOOLS or tool.func is None:
                continue
            real = tool.func

            def run(*a, _real=real, _name=tool.name, **k):
                if cached['write']:
                    try:
                        out = _real(*a, **k)
                    except Exception as exc:  # noqa: BLE001 - replayed as the same failure
                        cached['outputs'].append((_name, exc))
                        raise
                    cached['outputs'].append((_name, out))
                    return out
                name, out = cached['outputs'][cached['n']]
                cached['n'] += 1
                if name != _name:
                    raise RuntimeError('cached outputs out of step: %s recorded, %s asked' % (name, _name))
                if isinstance(out, Exception):
                    raise out
                return out
            tool.func = run
        return tools
    graph.make_agent_tools = make
    return cached


def _render(payload: dict) -> list[str]:
    """One request as its parts, in the order DeepSeek's template reads it: system prompt, tools, then messages.
    Each part is tokenized alone (the template separates messages with special tokens, so no token spans two)."""
    parts = [json.dumps(payload.get('tools') or [], ensure_ascii=False, separators=(',', ':'))]
    for m in payload.get('messages') or []:
        parts.append('<|%s|>' % m.get('role'))
        for key in ('reasoning_content', 'content', 'tool_call_id'):
            if m.get(key):
                parts.append(m[key] if isinstance(m[key], str) else json.dumps(m[key], ensure_ascii=False))
        if m.get('tool_calls'):
            parts.append(json.dumps(m['tool_calls'], ensure_ascii=False, separators=(',', ':')))
    # the system prompt is the first message; DeepSeek puts tools after it
    if len(parts) > 2 and parts[1] == '<|system|>':
        parts = [parts[1], parts[2], parts[0]] + parts[3:]
    return parts


def _output_unit(payload: dict, nxt: dict) -> dict | None:
    """The prefix unit DeepSeek stores for a request's output: that request as it was sent, followed by its reply
    (the last assistant message of the next request). It is never the next request's own wording, which differs
    when an earlier result became a digest or when the next request is the finalizer's, on its own system prompt."""
    msgs = nxt.get('messages') or []
    last_ai = max((k for k, m in enumerate(msgs) if m.get('role') == 'assistant'), default=None)
    if last_ai is None:
        return None
    return dict(payload, messages=list(payload.get('messages') or []) + [msgs[last_ai]])


def _agent_request(payload: dict) -> bool:
    """A request on the agent's own system prompt carries its tools (the agent's steps, and the finalizer on the
    agent's prefix, lean_history.finalizer_on_agent_prefix); the finalizer's own request and the plain-words
    rewrite carry none."""
    messages = payload.get('messages') or []
    first = messages[0].get('content') if messages else ''
    return isinstance(first, str) and first.startswith('You are the OWL AI Agent')


def simulate_cache(token_lists: list[list[int]], output_ends: list[int | None]) -> list[dict]:
    """Per request: tokens, strict and loose simulated cache hits (see the module docstring)."""
    import numpy as np
    arrays = [np.asarray(t, dtype=np.int64) for t in token_lists]
    units: list[np.ndarray] = []
    out = []
    for i, req in enumerate(arrays):
        strict = 0
        for unit in units:
            n = len(unit)
            if n <= len(req) and n > strict and np.array_equal(req[:n], unit):
                strict = n
        loose = 0
        for j in range(i):
            other = arrays[j]
            n = min(len(other), len(req))
            diff = np.nonzero(req[:n] != other[:n])[0]
            lcp = int(diff[0]) if len(diff) else n
            loose = max(loose, lcp)
        loose = max(strict, (loose // 64) * 64)
        out.append({'tokens': int(len(req)), 'hit_strict': int(strict), 'hit_loose': int(loose)})
        units.append(req)
        end = output_ends[i]
        if end is not None:
            units.append(np.asarray(end, dtype=np.int64))
    return out


def main():
    guard_process()
    ap = argparse.ArgumentParser()
    ap.add_argument('--recorded', required=True, help='a run json written by financial_agent_fit_replay.py')
    ap.add_argument('--user-id', help='the case reader for tools that check access (the jobs login user id)')
    ap.add_argument('--out', required=True)
    ap.add_argument('--group', type=int, default=1, help='recorded calls per scripted step')
    ap.add_argument('--tokenizer', default='/mnt/owl-data/tmp/lx-agentfit/r2/tok/tokenizer.json')
    ap.add_argument('--no-filler', action='store_true')
    ap.add_argument('--results', help='write each tool message content here (jsonl, case material)')
    ap.add_argument('--outputs', help='a pickle of the tools\' raw outputs: written when missing, else replayed '
                                      'from it so request variants are compared on the same results without the DB')
    cli = ap.parse_args()
    if cli.user_id:
        global REPLAY_USER_ID
        REPLAY_USER_ID = cli.user_id

    recorded = json.load(open(cli.recorded))
    trace = [t for t in recorded.get('trace') or [] if t.get('name')]
    args = argparse.Namespace(run=recorded.get('run'), case=None if recorded.get('run') else recorded['case'],
                              question=None if recorded.get('run') else recorded['question'],
                              reasoning=recorded.get('reasoning'), budget=None)
    _, ctx = fit_replay.prepare(args)
    fit_replay.stub_proposals()
    from langchain_core.messages import ToolMessage
    from services.agent import graph
    cached = _cache_outputs(graph, cli.outputs)
    from tokenizers import Tokenizer
    tok = Tokenizer.from_file(cli.tokenizer)
    memo: dict[str, list[int]] = {}

    def encode(parts: list[str]) -> list[int]:
        ids: list[int] = []
        for part in parts:
            if part not in memo:
                memo[part] = tok.encode(part).ids
            ids.extend(memo[part])
        return ids

    steps = [trace[i:i + cli.group] for i in range(0, len(trace), cli.group)]
    model_steps = max(1, len(steps) + 1)
    filler = 0 if cli.no_filler else int((recorded.get('completion_tokens') or 0) / model_steps)
    log: list = []
    model, state, remap = _scripted_model(steps, recorded.get('answer') or 'Answer.', filler, log)
    runner = graph.AgentGraphRunner(provider='deepseek', model_id=recorded.get('model') or 'deepseek-v4-pro',
                                    api_key='replay-no-key', reasoning=ctx['reasoning'] or 'high')
    builder = runner.base_model  # the production DeepSeek client: it builds the request payload, never sends it
    runner.base_model = model

    replayed, final, started = [], {}, time.perf_counter()
    error = None
    try:
        for event in runner.stream(case_id=ctx['case_id'], messages=ctx['history'], thread_id='trace-replay',
                                   available_artifacts=ctx['artifacts'], max_tool_calls=10_000,
                                   mandate_context_block=ctx['block'], hidden_tools=ctx['hidden'],
                                   final_answer_rules=ctx['rules'],
                                   user_id=REPLAY_USER_ID,
                                   proposer=dict(for_name='replay', for_user_id=None, for_email=None, model='replay',
                                                 model_id='replay', provider='deepseek', run_id=None, thread_id=None,
                                                 can_propose=False)):
            if event.get('type') == 'tool_result':
                item = event['tool']
                index = len(replayed)
                old = trace[index].get('result_id') if index < len(trace) else None
                if old and item.get('result_id'):
                    state['ids'][old] = item['result_id']
                replayed.append(item)
            elif event.get('type') == 'final':
                final = event.get('result') or {}
    except Exception as exc:  # noqa: BLE001 - a failed replay is recorded, not a crash of the batch
        error = '%s: %s' % (type(exc).__name__, str(exc)[:300])
    wall = time.perf_counter() - started

    # Each request as DeepSeek would be sent it, tokenized; the assistant reply that followed it is its output.
    requests, token_lists, output_ends, payloads = [], [], [], []
    for n, entry in enumerate(log):
        payload = builder._get_request_payload(entry['messages'])
        if entry['tools'] is not None and _agent_request(payload):
            payload['tools'] = entry['tools']
        payloads.append(payload)
        parts = _render(payload)
        ids = encode(parts)
        token_lists.append(ids)
        requests.append({'messages': len(payload.get('messages') or []), 'chars': sum(map(len, parts)),
                         'kind': payload['messages'][0]['content'][:40] if payload.get('messages') else ''})
        output_ends.append(None)
    # the output unit of request i: request i as sent, then its reply (taken from request i+1)
    for i in range(len(log) - 1):
        unit = _output_unit(payloads[i], builder._get_request_payload(log[i + 1]['messages']))
        if unit is not None:
            output_ends[i] = encode(_render(unit))
    cache = simulate_cache(token_lists, output_ends)
    for r, c in zip(requests, cache):
        r.update(c)

    tool_messages = [m for m in final.get('messages') or [] if isinstance(m, ToolMessage)]
    results = []
    for item, message in zip(replayed, tool_messages):
        content = message.content if isinstance(message.content, str) else json.dumps(message.content)
        results.append({'name': item.get('name'), 'status': item.get('status'), 'chars': len(content),
                        'tokens': len(tok.encode(content).ids), 'cites': sorted(set(CITE.findall(content))),
                        'ms': item.get('duration_ms')})
    if cli.results:
        with open(cli.results, 'w') as f:
            for item, message in zip(replayed, tool_messages):
                f.write(json.dumps({'name': item.get('name'), 'arguments': item.get('arguments'),
                                    'content': message.content}, ensure_ascii=False, default=str) + '\n')
    if cached is not None and cached['write']:
        import pickle
        with open(cli.outputs, 'wb') as f:
            pickle.dump(cached['outputs'], f)
    prompt = sum(c['tokens'] for c in cache)
    miss = prompt - sum(c['hit_strict'] for c in cache)
    completion = filler * len(log)
    out = dict(recorded=cli.recorded, run=recorded.get('run'), key_id=recorded.get('key_id'),
               fit=os.environ.get('LOUPE_AGENT_FIT'), group=cli.group, filler_tokens_per_step=filler,
               failed=error, seconds=round(wall, 1), calls_recorded=len(trace), calls_replayed=len(replayed),
               model_requests=len(log), prompt_tokens=prompt,
               hit_strict=sum(c['hit_strict'] for c in cache), hit_loose=sum(c['hit_loose'] for c in cache),
               miss_strict=miss, usd_offpeak_strict=round((miss * 0.66 + (prompt - miss) * 0.022
                                                           + completion * 1.98) / 1e6, 4),
               recorded_prompt_tokens=recorded.get('prompt_tokens'),
               recorded_cache_hit=recorded.get('cache_hit_tokens'),
               requests=requests, results=results)
    with open(cli.out, 'w') as f:
        json.dump(out, f, indent=1, default=str)
    print(json.dumps({k: out[k] for k in ('calls_recorded', 'calls_replayed', 'model_requests', 'prompt_tokens',
                                          'hit_strict', 'usd_offpeak_strict', 'hit_loose', 'recorded_prompt_tokens', 'recorded_cache_hit',
                                          'seconds', 'failed')}))


if __name__ == '__main__':
    main()
