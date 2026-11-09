"""Ask a recorded agent question again, read-only, with the real model, and measure the answer (lx-callagent A).

The production ``AgentGraphRunner.stream`` runs with its real prompts and tools against the live database through
read-only connections (every Postgres session of this process starts read-only, checked before anything runs). The
proposal tools are stubbed, never run, so nothing is saved anywhere: no thread, run, proposal or cost row. The model
is called for real (DeepSeek only; any other provider connection is refused).

Per answer it records: words, citations, internal or banned terms (``services.writing_standard.find_problems``), time
to answer, the model service's retries, usage and the progress lines a reader would have seen. The answer text is
case material: write ``--out`` under /mnt/owl-data/tmp (mode 700), never into the repo.

Usage (from backend/, via live-run.sh):
  financial_agent_answer_replay.py --run <agent_run_id> --out a.json [--question "..."] [--model deepseek-v4-pro]
                                   [--reasoning off|high|max]
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import socket
import sys
import time

os.environ['PGOPTIONS'] = (os.environ.get('PGOPTIONS', '') + ' -c default_transaction_read_only=on').strip()
_getaddrinfo = socket.getaddrinfo
_REFUSED = ('openai.com', 'anthropic.com', 'googleapis.com')


def _only_deepseek(host, *args, **kwargs):
    if host and any(name in str(host) for name in _REFUSED):
        raise OSError('replay: only the DeepSeek service may be called')
    return _getaddrinfo(host, *args, **kwargs)


socket.getaddrinfo = _only_deepseek
sys.path.insert(0, '.')

CITATION = re.compile(r'(?:rec|txn|doc)://[^\s)\]]+|\]\((?:entity:[^)]+|/cases/[^)]+)\)')
# What makes an answer read like a system log (AG-01): code spans, tool calls, proof codes, field names.
LOG_PHRASES = re.compile(r'`[^`\n]+`|\b[a-z]+(?:_[a-z0-9]+)+\b|\b[a-z_]+\([^)]*\)|\bp[0-4](?:[–-]p[0-4])?\b'
                         r'|\bpopulation\b|\bproof[ _]class\b|\(minor\)|\bpayload\b|\breturns? (?:zero|0)\b', re.I)


class RetryCounter(logging.Handler):
    """The OpenAI client logs each retry it makes on its own ('Retrying request to ...')."""

    def __init__(self):
        super().__init__(level=logging.DEBUG)
        self.lines = []

    def emit(self, record):
        message = record.getMessage()
        # The client's own retries (before 9 Nov) and the run's visible ones (graph.invoke_model) of model requests;
        # embedding retries (document search) are counted apart.
        if 'Retrying request' in message or 'Model request failed' in message:
            kind = 'embedding' if '/embeddings' in message else 'model'
            self.lines.append(dict(kind=kind, t=round(time.perf_counter(), 1), line=message[:200]))


def load_run(session, run_id):
    from sqlalchemy import text
    return dict(session.execute(text(
        "SELECT r.case_id::text AS case_id, r.input_message, r.final_answer, r.extra_metadata, r.mandate_override, "
        "t.mandate_version_id, r.model_id, r.usage, EXTRACT(EPOCH FROM r.completed_at - r.started_at) AS seconds "
        "FROM agent_runs r JOIN agent_threads t ON t.id = r.thread_id WHERE r.id = CAST(:r AS uuid)"),
        dict(r=run_id)).mappings().one())


def measure(answer: str) -> dict:
    from services import writing_standard
    problems = writing_standard.find_problems(answer or '')
    return dict(words=len((answer or '').split()), citations=len(CITATION.findall(answer or '')),
                distinct_citations=len(set(CITATION.findall(answer or ''))),
                log_phrases=len(LOG_PHRASES.findall(answer or '')),
                log_examples=sorted(set(LOG_PHRASES.findall(answer or '')))[:12],
                standard_problems=len(problems),
                standard_examples=['%s: %s' % (p.kind, p.match) for p in problems[:8]])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--run', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--question')
    ap.add_argument('--model', default='deepseek-v4-pro')
    ap.add_argument('--reasoning', default=None, help='off|high|max (graph.REASONING_LEVELS); default: the setting')
    ap.add_argument('--stored-only', action='store_true', help='measure the stored answer, call no model')
    args = ap.parse_args()

    from services.agent.tools import _financial_session
    from postgres.session import _get_engine
    from sqlalchemy import text
    with _get_engine().connect() as c:
        if c.execute(text('SHOW default_transaction_read_only')).scalar() != 'on':
            raise SystemExit('refusing to run: sessions are not read-only')
    from services.ai_provider_credentials import get_provider_api_key
    from services.agent.service import AgentService
    from types import SimpleNamespace
    with _financial_session() as s:
        run = load_run(s, args.run)
        stored = dict(seconds=float(run['seconds'] or 0), model=run['model_id'], usage=run['usage'],
                      **measure(run['final_answer'] or ''))
        if args.stored_only:
            out = dict(run=args.run, question=run['input_message'], stored=stored, stored_answer=run['final_answer'])
            json.dump(out, open(args.out, 'w'), indent=1, default=str)
            print(json.dumps(stored, default=str))
            return
        api_key = get_provider_api_key(s, 'deepseek')
        from services.mandate_context_service import mandate_context_service
        import uuid
        mandate = mandate_context_service.resolve(s, case_id=uuid.UUID(run['case_id']),
                                                  version_id=run['mandate_version_id'], override=run['mandate_override'])
        hidden, note = AgentService._tools_not_offered(
            s, SimpleNamespace(all_cases=False, case_id=run['case_id'], workflow_id=None))
        focus = focus_plan = ''
        if hasattr(AgentService, '_question_focus'):  # lx-callagent B; absent on the code before it
            focus = AgentService._question_focus(s, SimpleNamespace(case_id=run['case_id'],
                                                                    message=args.question or run['input_message']))
            # (planning, final answer) since the name search line; one block for both before it.
            focus_plan, focus = focus if isinstance(focus, tuple) else (focus, focus)
    block = '\n\n'.join(x for x in (mandate.block, note, focus_plan) if x)

    from services.agent import graph
    real = graph.make_agent_tools

    def make(context):
        tools = real(context)
        for tool in tools:
            if tool.name.startswith('propose_'):
                tool.func = lambda *a, _n=tool.name, **k: dict(
                    status='success', summary='Proposal stubbed in the replay; nothing was saved.', data={})
        return tools
    graph.make_agent_tools = make

    counter = RetryCounter()
    for name in ('openai', 'services.agent.graph'):
        logging.getLogger(name).addHandler(counter)
        logging.getLogger(name).setLevel(logging.DEBUG)

    kwargs = {}
    if args.reasoning is not None:
        kwargs['reasoning'] = args.reasoning
    runner = graph.AgentGraphRunner(provider='deepseek', model_id=args.model, api_key=api_key, **kwargs)
    question = args.question or run['input_message']
    from langchain_core.messages import HumanMessage
    started = time.perf_counter()
    progress, final, tools = [], {}, []

    def on_progress(p):
        progress.append(dict(t=round(time.perf_counter() - started, 1), **{k: p.get(k) for k in
                                                                            ('phase', 'step', 'title')}))

    for event in runner.stream(case_id=run['case_id'], messages=[HumanMessage(content=question)],
                               thread_id='replay', available_artifacts=[], mandate_context_block=block,
                               hidden_tools=hidden, on_progress=on_progress, final_answer_rules=focus,
                               proposer=dict(for_name='replay', for_user_id=None, for_email=None, model='replay',
                                             model_id=args.model, provider='deepseek', run_id=None, thread_id=None,
                                             can_propose=False)):
        if event.get('type') == 'final':
            final = event.get('result') or {}
        elif event.get('type') == 'tool_result':
            t = event['tool']
            tools.append(dict(name=t.get('name'), ms=t.get('duration_ms'), status=t.get('status')))
    wall = time.perf_counter() - started
    from services.agent import plain_answer
    answer, plain_check = plain_answer.checked((final.get('answer') or '').strip())
    out = dict(run=args.run, question=question, focus=focus, focus_plan=focus_plan, model=args.model, reasoning=args.reasoning,
               seconds=round(wall, 1), retries=sum(1 for x in counter.lines if x['kind'] == 'model'),
               embedding_retries=sum(1 for x in counter.lines if x['kind'] == 'embedding'), retry_lines=counter.lines,
               clarifications=final.get('clarifications') or final.get('clarification'),
               usage=final.get('usage'), plain_check=plain_check, tools=tools, progress=progress, metrics=measure(answer),
               answer=answer, stored=stored, stored_answer=run['final_answer'])
    with open(args.out, 'w') as f:
        json.dump(out, f, indent=1, default=str)
    print(json.dumps(dict(seconds=out['seconds'], retries=out['retries'], usage=out['usage'], tools=len(tools),
                          **out['metrics']), default=str))
    print('stored:', json.dumps(stored, default=str))


if __name__ == '__main__':
    main()
