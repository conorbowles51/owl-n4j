"""Ask one agent question again, read-only, with the real model, and count how the run spent its tool calls
(lx-agentfit A and H).

Two forms:
  --run <agent_run_id>              a recorded question, asked with its thread as it stood then (the earlier messages
                                     and the thread's artifacts made before it), its mandate and its guided workflow
  --case <case_id> --question "..."  a fresh question in a new, unsaved thread (the demo key's questions)

The production ``AgentGraphRunner.stream`` runs with its real prompts and tools against the live database through
read-only connections (every Postgres session of this process starts read-only, checked before anything runs). The
proposal tools are stubbed, so nothing is saved anywhere: no thread, run, proposal or cost row. The model is called
for real (DeepSeek only; any other provider connection is refused).

Per run it records the calls by kind (``classify``): a whole-result re-read, a page read, an error, an empty call
(it searched and found nothing), a call that returned something; whether the run stopped at the tool budget; the
seconds; the model tokens; the citation check the service would store; and, with ``--key-id``, the demo key's score
(found / missed / wrong, as journeys/live-demo-key.mjs scores it). The answer text is case material: ``--out`` goes
under /mnt/owl-data/tmp (mode 700), never into the repo.

Usage (from backend/, via live-run.sh):
  financial_agent_fit_replay.py --run <id> --out a.json
  financial_agent_fit_replay.py --case <id> --question "..." --key-id Q1 --key <planted-truths.json> --out a.json
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import time

os.environ['PGOPTIONS'] = (os.environ.get('PGOPTIONS', '') + ' -c default_transaction_read_only=on').strip()
_getaddrinfo = socket.getaddrinfo
_REFUSED = ('openai.com', 'anthropic.com', 'googleapis.com')
# Document search embeds the query with OpenAI; a replay that refuses it measures a search the user never gets.
if os.environ.get('LOUPE_FIT_ALLOW_EMBEDDINGS') == '1':
    _REFUSED = ('anthropic.com', 'googleapis.com')


def _guarded(host, *args, **kwargs):
    if host and any(name in str(host) for name in _REFUSED):
        raise OSError('replay: this model service may not be called')
    return _getaddrinfo(host, *args, **kwargs)


socket.getaddrinfo = _guarded
sys.path.insert(0, '.')

PAGE_TOOL = 'read_tool_result_page'


def classify(item: dict) -> str:
    """One tool call's kind: reread (a whole earlier result asked for again), page (a page of an earlier result),
    error, empty (ran and found nothing), returned (anything else)."""
    name = item.get('name')
    args = item.get('arguments') or {}
    record = item.get('record') or {}
    if name == PAGE_TOOL:
        if item.get('status') == 'error':
            return 'error'
        return 'page' if args.get('path') else 'reread'
    if item.get('status') == 'error' or record.get('available') is False:
        return 'error'
    returned, total = record.get('returned'), record.get('total')
    lengths = record.get('list_lengths') or {}
    if (returned == 0 and not total) or (returned is None and total == 0) or \
            (returned is None and total is None and lengths and not any(lengths.values())):
        return 'empty'
    return 'returned'


def score_key(answer: str, key: dict, citation_check: dict) -> dict:
    """The demo key's score for one answer, as journeys/live-demo-key.mjs scores it."""
    text = (answer or '').lower()
    hit = [w for w in key['expect'] if w.lower() in text]
    bad = [w for w in key.get('must_not') or [] if w.lower() in text]
    ok = int((citation_check or {}).get('ok') or 0)
    result = 'wrong' if bad else 'found' if len(hit) == len(key['expect']) and ok > 0 else 'missed'
    return dict(result=result, expected='%d/%d' % (len(hit), len(key['expect'])), wrong_words=bad,
                missing=[w for w in key['expect'] if w not in hit], citations_ok=ok,
                citations_total=(citation_check or {}).get('total'))


def history_as_of(session, run: dict):
    """The thread's messages before the run (the last 20, as service._build_history sends them), ending on the
    run's own question, and the thread's artifacts made before it (the last 8)."""
    from sqlalchemy import text
    from langchain_core.messages import AIMessage, HumanMessage
    rows = session.execute(text(
        "SELECT role, content FROM agent_messages WHERE thread_id = CAST(:t AS uuid) AND created_at < :at "
        "ORDER BY created_at DESC LIMIT 19"), dict(t=run['thread_id'], at=run['started_at'])).mappings().all()
    history = []
    for row in reversed(rows):
        if row['role'] == 'user':
            history.append(HumanMessage(content=row['content']))
        elif row['role'] == 'assistant':
            history.append(AIMessage(content=row['content']))
    # The run's own question was stored just before the run started; drop it if it is the last line, then add it.
    if history and isinstance(history[-1], HumanMessage) and history[-1].content == run['input_message']:
        history.pop()
    history.append(HumanMessage(content=run['input_message']))
    from postgres.models.agent import AgentArtifactRecord as AgentArtifact
    from services.agent import storage
    artifacts = session.query(AgentArtifact).filter(AgentArtifact.thread_id == run['thread_id'],
                                                    AgentArtifact.created_at < run['started_at']).all()
    artifacts = sorted(storage.supported_artifacts(artifacts), key=lambda a: a.created_at or a.id)[-8:]
    return history, [storage.to_api_artifact(a).model_dump(mode='json') for a in artifacts]


def summarise(trace: list[dict], clarification, usage, seconds: float, budget: int) -> dict:
    kinds = [classify(t) for t in trace]
    counts = {k + ('s' if k == 'error' else ''): kinds.count(k) for k in ('returned', 'reread', 'page', 'empty', 'error')}
    stopped = bool(clarification and ((clarification.get('context') or {}).get('reason') == 'tool_budget_exhausted'))
    return dict(calls=len(trace), **counts, budget_stop=stopped, budget=budget, seconds=round(seconds, 1),
                prompt_tokens=(usage or {}).get('prompt_tokens'), completion_tokens=(usage or {}).get('completion_tokens'),
                cache_hit_tokens=(usage or {}).get('prompt_cache_hit_tokens'),
                tools=[dict(name=t.get('name'), kind=k, status=t.get('status'), ms=t.get('duration_ms'))
                       for t, k in zip(trace, kinds)])


def ledger_spent(path: str) -> tuple[int, str | None]:
    """Tokens the measurement's runs spent so far, and why it stopped (a 402) if it did."""
    total, stopped = 0, None
    if os.path.exists(path + '.STOP'):
        stopped = open(path + '.STOP').read().strip() or 'stopped'
    if os.path.exists(path):
        for line in open(path):
            if line.strip():
                total += int(json.loads(line).get('tokens') or 0)
    return total, stopped


def record_spend(path: str, run, usage: dict, error: str | None) -> None:
    """One line per run; a 402 (no balance) stops every later run of the measurement."""
    tokens = int(usage.get('prompt_tokens') or 0) + int(usage.get('completion_tokens') or 0)
    with open(path, 'a') as f:
        f.write(json.dumps({'run': run, 'tokens': tokens, 'at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                            'error': (error or '')[:200]}) + '\n')
    if error and ('402' in error or 'Insufficient Balance' in error):
        with open(path + '.STOP', 'w') as f:
            f.write('the DeepSeek account answered 402 (no balance) at %s' % time.strftime('%H:%M:%SZ', time.gmtime()))


def prepare(args):
    """The run's question, thread, mandate, guided workflow and hidden tools as the service would send them, read
    through read-only sessions; (tool budget, the pieces runner.stream takes)."""
    import uuid
    from types import SimpleNamespace
    from sqlalchemy import text
    from postgres.session import _get_engine
    from services.agent.tools import _financial_session
    with _get_engine().connect() as c:
        if c.execute(text('SHOW default_transaction_read_only')).scalar() != 'on':
            raise SystemExit('refusing to run: sessions are not read-only')
    from services.ai_provider_credentials import get_provider_api_key
    from services.agent import model_choice, storage, workflows
    from services.agent.service import DEFAULT_AGENT_MAX_TOOL_CALLS, AgentService
    from services.mandate_context_service import mandate_context_service
    budget = args.budget or DEFAULT_AGENT_MAX_TOOL_CALLS
    with _financial_session() as s:
        if args.run:
            run = dict(s.execute(text(
                "SELECT r.case_id::text AS case_id, r.thread_id::text AS thread_id, r.input_message, r.started_at, "
                "r.extra_metadata, r.mandate_override, t.mandate_version_id, r.final_answer, r.status, "
                "r.tool_calls_used, EXTRACT(EPOCH FROM r.completed_at - r.started_at) AS seconds "
                "FROM agent_runs r JOIN agent_threads t ON t.id = r.thread_id WHERE r.id = CAST(:r AS uuid)"),
                dict(r=args.run)).mappings().one())
            history, artifacts = history_as_of(s, run)
            workflow_id = ((run['extra_metadata'] or {}).get('workflow') or {}).get('id')
            case_id, question = run['case_id'], run['input_message']
            mandate = mandate_context_service.resolve(s, case_id=uuid.UUID(case_id), version_id=run['mandate_version_id'],
                                                      override=run['mandate_override'])
        else:
            from langchain_core.messages import HumanMessage
            run, workflow_id, case_id, question = None, None, args.case, args.question
            history, artifacts = [HumanMessage(content=question)], []
            mandate = mandate_context_service.resolve(s, case_id=uuid.UUID(case_id), version_id=None, override=None)
        request = SimpleNamespace(all_cases=False, case_id=uuid.UUID(case_id), workflow_id=workflow_id, message=question)
        api_key = get_provider_api_key(s, 'deepseek')
        hidden, note = AgentService._tools_not_offered(s, request)
        focus_plan, focus = AgentService._question_focus(s, request)
        feedback = AgentService._proposal_feedback(s, request)
        block = '\n\n'.join(x for x in (AgentService._prompt_block(mandate.block, request, feedback), note, focus_plan)
                            if x)
        rules = '\n\n'.join(x for x in (AgentService._final_rules(request), focus) if x)
        reasoning = args.reasoning or model_choice.default_reasoning()

    return budget, dict(case_id=case_id, question=question, history=history, artifacts=artifacts, block=block,
                        hidden=hidden, rules=rules, reasoning=reasoning, run=run, api_key=api_key,
                        workflow_id=workflow_id)


def stub_proposals():
    """Proposal tools answer 'stubbed' in a replay: nothing is saved anywhere."""
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



def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--run')
    ap.add_argument('--case')
    ap.add_argument('--question')
    ap.add_argument('--key-id')
    ap.add_argument('--key', default='../evidence-engine/tests/phone/planted-truths.json')
    ap.add_argument('--out', required=True)
    ap.add_argument('--model', default='deepseek-v4-pro')
    ap.add_argument('--reasoning', default=None, help='off|high|max; default: the setting (model_choice)')
    ap.add_argument('--budget', type=int, default=None, help='tool budget; default: the service default')
    ap.add_argument('--spend-budget', type=int, required=True, help=(
        'model tokens (prompt + completion) the whole measurement may spend, stated before it starts (lx-agentfit '
        'R8: the app shares the DeepSeek account); runs sharing --spend-ledger stop once it is reached'))
    ap.add_argument('--spend-ledger', required=True, help='jsonl of tokens spent by each run of this measurement')
    args = ap.parse_args()
    if not args.run and not (args.case and args.question):
        raise SystemExit('give --run, or --case and --question')
    spent_before, stopped = ledger_spent(args.spend_ledger)
    if stopped or spent_before >= args.spend_budget:
        reason = stopped or 'the measurement spent %d of its %d tokens' % (spent_before, args.spend_budget)
        with open(args.out, 'w') as f:
            json.dump(dict(run=args.run, case=args.case, key_id=args.key_id, failed='not run: ' + reason), f)
        print(json.dumps({'failed': 'not run: ' + reason}))
        raise SystemExit(3)

    budget, ctx = prepare(args)
    case_id, question, history, artifacts = ctx['case_id'], ctx['question'], ctx['history'], ctx['artifacts']
    block, hidden, rules, reasoning, run, api_key = (ctx[k] for k in ('block', 'hidden', 'rules', 'reasoning', 'run', 'api_key'))
    stub_proposals()
    from services.agent import graph

    runner = graph.AgentGraphRunner(provider='deepseek', model_id=args.model, api_key=api_key, reasoning=reasoning)
    started = time.perf_counter()
    final, trace = {}, []
    error = None
    try:
        def over_budget():
            usage = runner.spent_so_far() or {}
            return spent_before + (usage.get('prompt_tokens') or 0) + (usage.get('completion_tokens') or 0) \
                >= args.spend_budget
        for event in runner.stream(case_id=case_id, messages=history, thread_id='replay', available_artifacts=artifacts,
                                   max_tool_calls=budget, mandate_context_block=block, hidden_tools=hidden,
                                   final_answer_rules=rules, should_cancel=over_budget,
                                   proposer=dict(for_name='replay', for_user_id=None, for_email=None, model='replay',
                                                 model_id=args.model, provider='deepseek', run_id=None, thread_id=None,
                                                 can_propose=False)):
            if event.get('type') == 'final':
                final = event.get('result') or {}
            elif event.get('type') == 'tool_result':
                trace.append(event['tool'])
    except Exception as exc:  # noqa: BLE001 - a failed run is a measured outcome, not a crash of the harness
        error = '%s: %s' % (type(exc).__name__, str(exc)[:300])
    wall = time.perf_counter() - started
    usage = final.get('usage') or runner.spent_so_far() or {}
    record_spend(args.spend_ledger, args.run or args.key_id, usage, error)
    if error and 'AgentRunCancelled' in error:
        error = 'stopped: the measurement reached its budget of %d tokens' % args.spend_budget
    from services.agent import plain_answer
    answer, _ = plain_answer.checked((final.get('answer') or '').strip())
    with _financial_session() as s:
        answer, citation_check = storage.checked_answer(s, case_id=uuid.UUID(case_id), answer=answer)
    clarification = final.get('clarification')
    out = dict(run=args.run, case=case_id, question=question, key_id=args.key_id, model=args.model,
               reasoning=reasoning, failed=error, history_messages=len(history), artifacts_given=len(artifacts),
               **summarise(trace, clarification, final.get('usage'), wall, budget),
               citation_check={k: citation_check.get(k) for k in ('ok', 'total', 'available', 'broken', 'outside')
                               if k in citation_check},
               clarification=(clarification or {}).get('question') if clarification else None,
               answer=answer, words=len(answer.split()),
               trace=[{k: t.get(k) for k in ('name', 'arguments', 'status', 'summary', 'error', 'result_id', 'record')}
                      for t in trace])
    if args.key_id:
        key = next(q for q in json.load(open(args.key))['agent_questions'] if q['id'] == args.key_id)
        out['key_score'] = score_key(answer, key, citation_check)
    if run:
        out['stored'] = dict(status=run['status'], calls=run['tool_calls_used'], seconds=float(run['seconds'] or 0))
        out['stored_answer'] = run['final_answer']
    with open(args.out, 'w') as f:
        json.dump(out, f, indent=1, default=str)
    print(json.dumps({k: out[k] for k in ('calls', 'returned', 'reread', 'page', 'empty', 'errors', 'budget_stop',
                                          'seconds', 'prompt_tokens', 'citation_check', 'words')}
                     | ({'key': out['key_score']} if args.key_id else {}) | ({'failed': error} if error else {}),
                     default=str))


if __name__ == '__main__':
    main()
