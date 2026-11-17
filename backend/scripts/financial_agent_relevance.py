"""Measure the agent's search relevance and report quality on the judged test cases, and gate a change on it
(lx-relevancetest A-C; plan D21 / R5).

Subcommands (from backend/, through live-run.sh so the tools read the live database read-only):

  run      run every judged query of the sets through the real agent tools of THIS tree; write the scores
  compare  compare two run files, noise-aware; print the verdict; exit 0 PASS, 1 FAIL
  gate     the one command every agent job runs before release: asks every judged query of origin's head (the
           baseline, a shared detached worktree per head) and of this tree (the candidate) back to back, so both
           read the same live data; compares, scores any report files given, prints a plain verdict and writes it
           to /mnt/owl-data/fin-wt/headless/relevance-gate/<label>-<sha>.txt
  worker   one tree's side of the gate (started by gate)
  report   score report texts (an agent answer, a stand-in's report) against a rubric

  bash /mnt/owl-data/fin-wt/live-run.sh <worktree> financial_agent_relevance gate --label <job>
  bash /mnt/owl-data/fin-wt/live-run.sh <worktree> financial_agent_relevance report --rubric R1 answer1.md ...

The judged sets and rubrics are scoring aids under evidence-engine/tests/relevance and evidence-engine/tests/phone;
they never reach a prompt or a tool. Every Postgres session of this process is read-only (checked before anything
runs); no model is called except the query embedding of meaning search (OpenAI, as the agent's own searches do).
Outputs hold case material from invented test cases; they go under /mnt/owl-data/tmp.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_HERE)
_REPO = os.path.dirname(_BACKEND)


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# Loaded by path from this script's own tree, so a baseline run from an older tree (cwd) scores the same way.
R = _load('relevance_eval', os.path.join(_BACKEND, 'services', 'agent', 'relevance_eval.py'))

SETS = [os.path.join(_REPO, 'evidence-engine', 'tests', 'relevance', n)
        for n in ('demo-relevance-set.json', 'second-relevance-set.json')]
RUBRICS = os.path.join(_REPO, 'evidence-engine', 'tests', 'relevance', 'report-rubrics.json')
GATE_DIR = '/mnt/owl-data/tmp/relevance-gate'
VERDICT_DIR = '/mnt/owl-data/fin-wt/headless/relevance-gate'
BASE_TREE = '/mnt/owl-data/fin-wt/relevance-base'  # one detached worktree per origin head under it
LIVE = '/home/conorbowles51/app-v3/owl-n4j'
BRANCH = 'origin/integration/evidence-main-reunion'


def _sha(path='.'):
    return subprocess.run(['git', '-C', path, 'rev-parse', 'HEAD'], capture_output=True, text=True).stdout.strip()


def _set_hash(paths):
    h = hashlib.sha256()
    for p in paths:
        h.update(open(p, 'rb').read())
    return h.hexdigest()[:12]


def existing_sets(paths=None):
    return [p for p in (paths or SETS) if os.path.exists(p)]


def expand(judged: dict) -> list[dict]:
    """The set's queries plus each query of a listed kind run again through another search tool (``also_through``:
    meaning search, the case search service), as the same question in that tool's words."""
    out = [dict(q) for q in judged['queries']]
    for extra in judged.get('also_through') or []:
        for q in judged['queries']:
            if q['kind'] not in extra['from_kinds']:
                continue
            text = next((v for v in q['args'].values() if isinstance(v, str)), None)
            if not text:
                continue
            args = dict(extra.get('extra') or {})
            args[extra.get('arg', 'query')] = text
            out.append(dict(q, id='%s~%s' % (extra['kind'], q['id']), kind=extra['kind'], tool=extra['tool'], args=args))
    return out


# Tools that search every area of a case (phones, documents, ledger, notes, timeline, graph): for them a query's
# ``cross_area`` records (its facts' carriers in other areas: a ledger row for a phone question) are relevant too.
# A one-area tool (search_documents, get_financial_transactions) cannot return them and is not judged on them.
CROSS_AREA_TOOLS = ('search_case', 'search_by_meaning')


def judged_relevant(q):
    rel = list(q.get('relevant') or [])
    if q.get('tool') in CROSS_AREA_TOOLS:
        rel += [r for r in q.get('cross_area') or [] if r['id'] not in {x['id'] for x in rel}]
    return rel


def rating_sets(export_path, out_dir, log=lambda *a: print(*a, flush=True)):
    """Judged sets from people's answer ratings (lx-agenttools: scripts/export_answer_rating_cases.py), one per case,
    written to ``out_dir`` (private; real questions never enter the repo). A rated question with picked records is
    a judged query through meaning search, the records picked as relevant; one with none picked is counted only."""
    doc = json.load(open(export_path))
    items = doc.get('items') if isinstance(doc, dict) else doc
    by_case, unpicked = {}, 0
    for it in items or []:
        rel = [r for r in it.get('relevant') or [] if r.get('any') or r.get('all')]
        if not rel or not it.get('case_id') or not (it.get('question') or '').strip():
            unpicked += 1
            continue
        by_case.setdefault(it['case_id'], []).append(dict(
            id=str(it['id']), kind='rating', tool='search_by_meaning',
            args=dict(query=it['question'].strip(), limit=50), relevant=rel, decoys=it.get('decoys') or [],
            complaint=it.get('complaint')))
    os.makedirs(out_dir, mode=0o700, exist_ok=True)
    paths = []
    for case_id, qs in sorted(by_case.items()):
        path = os.path.join(out_dir, 'ratings-%s.json' % case_id[:8])
        with open(path, 'w') as f:
            json.dump(dict(case='ratings-%s' % case_id[:8], case_id=case_id, queries=qs), f, indent=1)
        paths.append(path)
    log('answer ratings: %d rated questions with picked records in %d cases are judged; %d with none picked are '
        'counted, not scored' % (sum(len(q) for q in by_case.values()), len(by_case), unpicked))
    return paths


# Chat-model calls a tree may make for the case search's ranking and rephrasing (gate/run --model-calls; workers
# inherit it). 0: none, the steps are off. Neil 12 Nov: any DeepSeek run has a hard cap, never at peak price.
MODEL_CALLS_ENV = 'RELEVANCE_MODEL_CALLS'
PEAK_UTC_HOURS = (1, 2, 3)  # 01:00-04:00 UTC, DeepSeek's double price
_model_used = [0]


def model_cap():
    return max(0, int(os.environ.get(MODEL_CALLS_ENV) or 0))


def capped_call(call, cap, used=_model_used):
    """``call`` (prompt -> text) refused once ``cap`` calls have been made in this process."""
    def c(prompt):
        if used[0] >= cap:
            raise RuntimeError('relevance run: the model call cap (%d) is reached' % cap)
        used[0] += 1
        return call(prompt)
    c.model = getattr(call, 'model', None)
    return c


def _cap_case_search(cap):
    try:
        from services.case_search import rerank
    except ImportError:
        return
    if getattr(rerank.default_model_call, '_relevance_cap', False):
        return
    inner = rerank.default_model_call

    def default_model_call():
        call = inner()
        return capped_call(call, cap) if call is not None else None
    default_model_call._relevance_cap = True
    rerank.default_model_call = default_model_call
    for mod in [m for name, m in list(sys.modules.items()) if name.startswith('services.case_search')]:
        if getattr(mod, 'default_model_call', None) is inner:
            mod.default_model_call = default_model_call


def guard_process():
    """Read-only Postgres and no chat model, as the replay scripts do (financial_agent_fit_replay.guard_process);
    with a model cap, the case search's model steps run up to the cap."""
    os.environ.setdefault('LOUPE_FIT_ALLOW_EMBEDDINGS', '1')
    cap = model_cap()
    if not cap:
        # The case search's ranking and rephrasing steps call the chat model (DeepSeek), which this process refuses
        # below; its own switch skips them cleanly instead of failing one call per batch. The gate says so.
        os.environ['LOUPE_CASE_SEARCH_MODEL'] = 'off'
    fr = _load('fit_replay', os.path.join(_HERE, 'financial_agent_fit_replay.py'))
    fr.guard_process()
    import socket
    inner = socket.getaddrinfo
    if not getattr(inner, '_relevance_guard', False):
        def _no_chat(host, *a, **k):
            if host and 'deepseek.com' in str(host) and not cap:
                raise OSError('relevance run: no chat model may be called')
            return inner(host, *a, **k)
        _no_chat._relevance_guard = _no_chat._replay_guard = True
        socket.getaddrinfo = _no_chat
    sys.path.insert(0, '.')
    from sqlalchemy import text
    from postgres.session import _get_engine
    with _get_engine().connect() as c:
        if c.execute(text('SHOW default_transaction_read_only')).scalar() != 'on':
            raise SystemExit('refusing to run: sessions are not read-only')
    if cap:
        _cap_case_search(cap)


def plan_queries(paths, kinds=None, repeat=None, only=None, log=lambda *a: print(*a, flush=True)):
    """The judged queries to run, in order: (set index, judged set, query, times). No backend import: the gate plans
    in its own process and hands the same plan to both trees' workers.

    ``repeat`` None: each query runs as often as its kind asks (``repeat`` in the set's also_through entry or
    ``kind_repeat``; 1 otherwise: measured 17 Nov, 0 of 99 queries ranked differently on a second run seconds later).
    A number: every query runs that often."""
    plan = []
    for si, judged in enumerate(json.load(open(p)) for p in paths):
        if not judged.get('case_id'):
            log('%s: not loaded yet (no case_id in its set); not scored' % judged['case'])
            continue
        reps = dict(judged.get('kind_repeat') or {})
        reps.update({x['kind']: x['repeat'] for x in judged.get('also_through') or [] if x.get('repeat')})
        for q in expand(judged):
            if (kinds and q['kind'] not in kinds) or (only and q['id'] not in only):
                continue
            plan.append((si, judged, q, repeat or reps.get(q['kind'], 1)))
    return plan


class Runner:
    """Runs one judged query through this tree's agent tools (built once per case)."""

    def __init__(self):
        guard_process()
        from services.agent.tools import AgentToolContext, _financial_session, make_agent_tools
        self._ctx, self._session, self._make = AgentToolContext, _financial_session, make_agent_tools
        self.tools_by_case = {}

    def run(self, judged, q, dump=None):
        case_id = judged['case_id']
        if case_id not in self.tools_by_case:
            ctx = self._ctx(case_id=case_id, ledger_session_factory=self._session)
            self.tools_by_case[case_id] = {t.name: t for t in self._make(ctx)}
        tool = self.tools_by_case[case_id].get(q['tool'])
        row = dict(kind=q['kind'], tool=q['tool'], case=judged['case'])
        if tool is None:
            row['missing'] = 'no tool %s in this tree' % q['tool']
            return row
        t0 = time.time()
        try:
            units = R.result_units(tool.invoke(q['args']))
            texts = [R.unit_text(u) for u in units]
            row['score'] = R.score_query(texts, judged_relevant(q), q.get('decoys') or [],
                                         decoy_texts=[R.cited_text(u) for u in units])
            if dump:
                dump.write(json.dumps(dict(query='%s:%s' % (judged['case'], q['id']), args=q['args'],
                                           units=[t[:400] for t in texts[:50]]), ensure_ascii=False) + '\n')
        except Exception as exc:  # noqa: BLE001 - a crash is a failed search, recorded
            row['error'] = '%s: %s' % (type(exc).__name__, str(exc)[:300])
        row['seconds'] = round(time.time() - t0, 2)
        return row


def _row_line(qid, row):
    s = row.get('score')
    return '%-34s %-10s %s' % (qid[:34], row['kind'], row.get('missing') or row.get('error') or
                               'units %d first %s r@10 %s decoys %s %.0fs' % (
                                   s['units'], s['first_relevant'], s['recall_at_10'], s['decoys_top10'],
                                   row['seconds']))


def finish_runs(runs):
    for r in runs:
        r['aggregate'] = R.aggregate([dict(kind=v['kind'], **({'score': v['score']} if 'score' in v else
                                                              {'error': v.get('error')}))
                                      for v in r['queries'].values() if 'missing' not in v])
        r['missing'] = sorted({v['tool'] for v in r['queries'].values() if 'missing' in v})
        r['model_calls_used'] = max([v.get('model_calls_used') or 0 for v in r['queries'].values()] or [0])
    return runs


def run_sets(paths, kinds=None, repeat=None, only=None, dump=None, log=lambda *a: print(*a, flush=True)):
    """Runs of every judged query in this tree: per run the aggregate and per query its score (or error / missing
    tool). A query run fewer times than the most-repeated kind repeats its one result in the later runs."""
    plan = plan_queries(paths, kinds, repeat, only, log)
    runner = Runner()
    most = max([n for *_, n in plan] or [1])
    runs = [dict(queries={}) for _ in range(most)]
    out = open(dump, 'w') if dump else None
    for _, judged, q, n in plan:
        qid = '%s:%s' % (judged['case'], q['id'])
        for i in range(most):
            if i >= n:
                runs[i]['queries'][qid] = runs[0]['queries'][qid]
                continue
            runs[i]['queries'][qid] = row = runner.run(judged, q, out if i == 0 else None)
            log(_row_line(qid, row))
    if out:
        out.close()
    return finish_runs(runs)


def cmd_worker(args):
    """One tree's side of an interleaved gate: reads plan indexes on stdin, answers each with its row on stdout."""
    plan = plan_queries(args.set, args.kinds, args.repeat, None, log=lambda *a: None)
    runner = Runner()
    real_stdout = sys.stdout
    sys.stdout = sys.stderr  # the tools' own prints must not reach the protocol stream
    real_stdout.write(json.dumps(dict(ready=True, sha=_sha('.'), n=len(plan))) + '\n')
    real_stdout.flush()
    for line in sys.stdin:
        i = int(json.loads(line)['i'])
        _, judged, q, _n = plan[i]
        real_stdout.write(json.dumps(dict(runner.run(judged, q), model_calls_used=_model_used[0]), default=str) + '\n')
        real_stdout.flush()
    return 0


def write_runs(path, runs, paths, tree='.'):
    meta = dict(sha=_sha(tree), tree=os.path.abspath(tree), at=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                sets=[os.path.basename(p) for p in paths], set_hash=_set_hash(paths), scorer=R.__file__)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, 'w') as f:
        json.dump(dict(meta=meta, runs=runs), f, indent=1, default=str)


def table(agg):
    return R.verdict_lines(dict(verdict='-', base_runs=0, cand_runs=1, losses=[], lost_records=[],
                                moved_out_of_top10=[], gains=[], newly_found=[]), agg, agg)[1:]


def cmd_run(args):
    paths = existing_sets(args.set)
    if getattr(args, 'ratings', None):
        paths += rating_sets(args.ratings, os.path.join(GATE_DIR, 'ratings'))
    runs = run_sets(paths, kinds=args.kinds, repeat=args.repeat, only=args.only, dump=args.dump)
    write_runs(args.out, runs, paths)
    for line in table(runs[0]['aggregate']):
        print(line)
    if runs[0]['missing']:
        print('tools not in this tree (not scored): %s' % ', '.join(runs[0]['missing']))


def cmd_compare(args):
    base, cand = json.load(open(args.base)), json.load(open(args.cand))
    cmp = R.compare(base['runs'], cand['runs'])
    for line in R.verdict_lines(cmp, base['runs'][0]['aggregate'], cand['runs'][0]['aggregate']):
        print(line)
    return 0 if cmp['verdict'] == 'PASS' else 1


# ---- reports -----------------------------------------------------------------------------------------------------

def rubric(rid, path=RUBRICS):
    """A report rubric by id: R1 is lx-deepinvest's phone rubric (evidence-engine/tests/phone), the rest are in
    report-rubrics.json."""
    found = {}
    if os.path.exists(path):
        for r in json.load(open(path))['rubrics']:
            found[r['question_id']] = r
    phone = os.path.join(_REPO, 'evidence-engine', 'tests', 'phone', 'planted-report-rubric.json')
    if os.path.exists(phone):
        r1 = json.load(open(phone))
        r1 = dict(r1, **{k: v for k, v in found.get('R1', {}).items() if k in ('pass', 'case')})
        found['R1'] = r1
    if rid not in found:
        raise SystemExit('no rubric %s (have %s)' % (rid, ', '.join(sorted(found))))
    return found[rid]


def _answer_text(path):
    raw = open(path).read()
    if path.endswith('.json'):
        d = json.loads(raw)
        return d.get('answer') or d.get('final_answer') or ''
    return raw


def score_files(rid, paths):
    rb = rubric(rid)
    return [dict(R.score_report(_answer_text(p), rb), file=p) for p in paths]


def report_lines(rid, scores):
    out = []
    for s in scores:
        out.append('%s %s: %s facts %d/%d, decoys linked %s, claims %d (cited %.0f%%, say why %.0f%%), %d words%s' % (
            rid, os.path.basename(s['file']), 'PASS' if s['passed'] else 'FAIL', s['facts_found'], s['facts_of'],
            ','.join(s['decoys_wrong']) or 'none', s['claims'], 100 * s['cited_share'], 100 * s['why_share'],
            s['words'], '' if s['passed'] else ' (' + '; '.join(s['fails_because']) + ')'))
    return out


def cmd_report(args):
    scores = score_files(args.rubric, args.files)
    for line in report_lines(args.rubric, scores):
        print(line)
    if args.json:
        json.dump(scores, open(args.json, 'w'), indent=1)
    return 0 if all(s['passed'] for s in scores) else 1


# ---- the gate ----------------------------------------------------------------------------------------------------

def _base_tree(sha):
    """A detached worktree of the live repo at ``sha``, one per origin head, shared by every job's gate and never
    moved while a gate reads it (a worker imports lazily, so a checkout under it would mix two trees)."""
    os.makedirs(BASE_TREE, exist_ok=True)
    tree = os.path.join(BASE_TREE, sha[:12])
    with open(os.path.join(BASE_TREE, '.lock'), 'w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if not os.path.isdir(os.path.join(tree, 'backend')):
            subprocess.run(['git', '-C', LIVE, 'worktree', 'add', '--detach', tree, sha], check=True,
                           capture_output=True, timeout=900)
    return tree


class Worker:
    """One tree's worker process (``worker`` subcommand, run from that tree's backend with this file's runner)."""

    def __init__(self, tree_backend, paths, kinds, repeat, log_path):
        cmd = [sys.executable, os.path.abspath(__file__), 'worker']
        for p in paths:
            cmd += ['--set', p]
        if kinds:
            cmd += ['--kinds'] + list(kinds)
        if repeat:
            cmd += ['--repeat', str(repeat)]
        self.err = open(log_path, 'a')
        self.proc = subprocess.Popen(cmd, cwd=tree_backend, env=dict(os.environ, PYTHONPATH='.'), text=True,
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.err)
        hello = self.proc.stdout.readline()
        if not hello:
            raise SystemExit('the worker in %s did not start (see %s)' % (tree_backend, log_path))
        self.sha = json.loads(hello)['sha']

    def ask(self, i):
        self.proc.stdin.write(json.dumps(dict(i=i)) + '\n')
        self.proc.stdin.flush()
        line = self.proc.stdout.readline()
        if not line:
            raise SystemExit('a worker stopped mid-run (see %s)' % self.err.name)
        return json.loads(line)

    def close(self):
        try:
            self.proc.stdin.close()
            self.proc.wait(timeout=60)
        except Exception:  # noqa: BLE001
            self.proc.kill()


def interleaved(paths, kinds, repeat, base_backend, cand_backend, log_path, log=lambda *a: print(*a, flush=True)):
    """Baseline and candidate runs with each query asked of both trees back to back, so both read the same live
    data. Measured 17 Nov: one tree run twice 35 minutes apart moved a record out of the top 10 and changed recall
    at 10 by 0.008 while live vectors were being written; seconds apart, 0 of 99 queries changed."""
    plan = plan_queries(paths, kinds, repeat, None, log=log)
    base = Worker(base_backend, paths, kinds, repeat, log_path)
    cand = Worker(cand_backend, paths, kinds, repeat, log_path)
    most = max([n for *_, n in plan] or [1])
    sides = {'base': [dict(queries={}) for _ in range(most)], 'cand': [dict(queries={}) for _ in range(most)]}
    try:
        for i, (_, judged, q, n) in enumerate(plan):
            qid = '%s:%s' % (judged['case'], q['id'])
            for j in range(most):
                for side, w in (('base', base), ('cand', cand)) if j % 2 == 0 else (('cand', cand), ('base', base)):
                    sides[side][j]['queries'][qid] = (w.ask(i) if j < n else sides[side][0]['queries'][qid])
            if (i + 1) % 20 == 0 or i + 1 == len(plan):
                log('asked %d of %d queries of both trees, %s UTC' % (i + 1, len(plan), time.strftime('%H:%M:%S',
                                                                                                    time.gmtime())))
    finally:
        base.close()
        cand.close()
    return finish_runs(sides['base']), finish_runs(sides['cand']), base.sha, cand.sha


def cmd_gate(args):
    paths = existing_sets(args.set)
    if getattr(args, 'ratings', None):
        paths += rating_sets(args.ratings, os.path.join(GATE_DIR, 'ratings'))
    sha = _sha('.')
    lines = ['relevance gate for %s at %s, %s UTC' % (args.label, sha[:12], time.strftime('%Y-%m-%d %H:%M',
                                                                                          time.gmtime()))]
    verdicts = []
    cap = max(0, args.model_calls or 0)
    if cap and not args.reports_only:
        if time.gmtime().tm_hour in PEAK_UTC_HOURS:
            raise SystemExit('refusing model calls between 01:00 and 04:00 UTC (double price); run later or without '
                             '--model-calls')
        os.environ[MODEL_CALLS_ENV] = str(cap)
        if args.repeat is None:
            args.repeat = 3  # a model step varies run to run: compare against the range of 3
    if not args.reports_only:
        subprocess.run(['git', '-C', LIVE, 'fetch', '-q', 'origin', 'integration/evidence-main-reunion'],
                       capture_output=True, timeout=300)
        head = args.base or subprocess.run(['git', '-C', LIVE, 'rev-parse', BRANCH], capture_output=True,
                                           text=True).stdout.strip()
        tree = _base_tree(head)
        os.makedirs(GATE_DIR, mode=0o700, exist_ok=True)
        stem = os.path.join(GATE_DIR, '%s-%s-vs-%s' % (args.label, sha[:12], head[:12]))
        base, cand, bsha, csha = interleaved(paths, args.kinds, args.repeat, os.path.join(tree, 'backend'),
                                             os.path.abspath('.'), stem + '.workers.log')
        write_runs(stem + '.base.json', base, paths, tree)
        write_runs(stem + '.cand.json', cand, paths)
        cmp = R.compare(base, cand)
        lines.append('baseline: origin %s; candidate: %s; each query asked of both, back to back' % (bsha[:12],
                                                                                                    csha[:12]))
        if cap:
            lines.append('chat model on for the case search, at most %d calls per tree: baseline used %s, candidate %s'
                         ' (at the cap, later searches ran unranked); %d runs per query' % (
                             cap, max(r['model_calls_used'] for r in base), max(r['model_calls_used'] for r in cand), len(cand)))
        else:
            lines.append('no chat model: the case search ranks in search order (its model ranking and rephrasing '
                         'are off); meaning search embeds the question as the agent does')
        lines += R.verdict_lines(cmp, base[0]['aggregate'], cand[0]['aggregate'])
        if cand[0]['missing']:
            lines.append('tools not in the candidate (not scored): %s' % ', '.join(cand[0]['missing']))
        verdicts.append(cmp['verdict'])
    for spec in args.reports or []:
        # R1=base1.md,base2.md:cand1.md,cand2.md  (baseline files : candidate files), or R1=cand1.md,cand2.md
        rid, files = spec.split('=', 1)
        base_files, cand_files = files.split(':', 1) if ':' in files else ('', files)
        cand = score_files(rid, [f for f in cand_files.split(',') if f])
        lines += report_lines(rid, cand)
        if base_files:
            base = score_files(rid, [f for f in base_files.split(',') if f])
            rc = R.compare_reports(base, cand)
            lines.append('%s report gate: %s (facts base %s, candidate %s%s%s%s)' % (
                rid, rc['verdict'], rc.get('base_facts'), rc.get('cand_facts'),
                '; lost ' + ','.join(rc['lost_facts']) if rc['lost_facts'] else '',
                '; new decoys ' + ','.join(rc['new_decoys']) if rc['new_decoys'] else '',
                ''.join('; %s %s->%s (noise %s)' % (x['metric'], x['base'], x['cand'], x['noise'])
                        for x in rc['losses'])))
            verdicts.append(rc['verdict'])
    final = 'FAIL' if 'FAIL' in verdicts else ('PASS' if verdicts else 'NO DATA')
    lines.insert(1, 'VERDICT: %s' % final)
    os.makedirs(VERDICT_DIR, exist_ok=True)
    out = os.path.join(VERDICT_DIR, '%s-%s.txt' % (args.label, sha[:12]))
    with open(out, 'w') as f:
        f.write('\n'.join(lines) + '\n')
    print('\n'.join(lines))
    print('written to %s' % out)
    return 0 if final == 'PASS' else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('run')
    p.add_argument('--set', action='append')
    p.add_argument('--ratings', help='answer ratings export (scripts/export_answer_rating_cases.py); judged too')
    p.add_argument('--out', required=True)
    p.add_argument('--repeat', type=int, default=None, help='runs per query; default: as its kind asks')
    p.add_argument('--kinds', nargs='*')
    p.add_argument('--only', nargs='*', help='query ids')
    p.add_argument('--dump', help='jsonl of each query\'s returned units (case material; under /mnt/owl-data/tmp)')
    p = sub.add_parser('compare')
    p.add_argument('--base', required=True)
    p.add_argument('--cand', required=True)
    p = sub.add_parser('report')
    p.add_argument('--rubric', required=True)
    p.add_argument('--json')
    p.add_argument('files', nargs='+')
    p = sub.add_parser('gate')
    p.add_argument('--ratings', help='answer ratings export (scripts/export_answer_rating_cases.py); judged too')
    p.add_argument('--label', required=True, help='your job name')
    p.add_argument('--set', action='append')
    p.add_argument('--kinds', nargs='*')
    p.add_argument('--repeat', type=int, default=None, help='runs per query; default: as its kind asks (a kind '
                                                         'with a model step sets repeat 3 in the set)')
    p.add_argument('--reports', nargs='*', help='RID=base.md,...:cand.md,... report files to score (stand-in or '
                                                'DeepSeek answers); the candidate side alone is scored if no ":"')
    p.add_argument('--reports-only', action='store_true')
    p.add_argument('--base', help='baseline commit (default: origin head)')
    p.add_argument('--model-calls', type=int, default=0, help='chat-model calls each tree may make for the case '
                   "search's ranking (default 0: off); never 01:00-04:00 UTC; runs each query 3 times")
    p = sub.add_parser('worker')
    p.add_argument('--set', action='append', required=True)
    p.add_argument('--kinds', nargs='*')
    p.add_argument('--repeat', type=int, default=None)
    args = ap.parse_args(argv)
    return {'run': cmd_run, 'compare': cmd_compare, 'report': cmd_report, 'gate': cmd_gate,
            'worker': cmd_worker}[args.cmd](args) or 0


if __name__ == '__main__':
    sys.exit(main())
