"""Census of every statement file in a case. Writes nothing to the case.

The reader recovery dry run looks only at the files its campaign may re-read.
This census looks at every batch file of the case, whatever its live state:
imported, ready, held, failed or left unimported. For each case:

1. Inside a READ ONLY transaction (the dry run's own guard), every distinct
   original in every batch that is not removed is listed with its stored
   live periods and its retained reading. Live periods of several readings
   or batches of the same original are counted once.
2. Every original whose bytes still match its evidence hash is re-read with
   the current evidence-engine code in separate processes (at most two),
   single-threaded OCR, a few files per process. Each reading is cached by
   original hash under the engine code revision, so an interrupted census
   resumes where it stopped and the ledger audit reuses the same readings.
3. Two disposable SQLite batches are prepared with the current backend code
   from all files of the case together: one from the retained readings, one
   from the new readings. No investigator input is applied (not even a
   recorded currency choice): the count is periods the source alone makes
   ready. Duplicate and overlap holds between files of the case apply.
4. Each prepared period is matched to its stored live period (same file,
   same statement key, else same dates) and written, with an opaque period
   id, to the private detail file. Blocking reasons are recorded coarse (the
   batch view's categories) and fine (problem kind, field or check, and a
   message template id; templates are kept privately).
5. ``financial_ledger_misread_audit`` runs on the case with the cached
   readings.

Everything goes under ``--out`` (private, never in git): per case
``periods.jsonl``, ``files.jsonl``, ``templates.json``, ``report.json``,
``audit/``. ``--summarize FILE`` writes counts only (no names, amounts, file
names or live ids; periods by opaque id) across every case under ``--out``.

From ``backend/`` with the service environment loaded:

    OMP_THREAD_LIMIT=1 python3 scripts/financial_statement_census.py --case <uuid> --out DIR
    python3 scripts/financial_statement_census.py --out DIR --summarize SUMMARY.md
"""
import argparse
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from collections import Counter, defaultdict
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
MAX_WORKERS = 2
# Several live items for one period (re-reads, several batches): the most
# advanced state is the period's live state.
LIVE_PRIORITY = ('imported', 'pending_import', 'ready', 'attention', 'duplicate_ignored', 'skipped', 'assigned',
                 'removed')
LEFT_UNIMPORTED = ('duplicate_ignored', 'skipped', 'assigned', 'removed')


def _estimate():
    spec = importlib.util.spec_from_file_location('financial_reader_recovery_estimate',
        BACKEND / 'scripts/financial_reader_recovery_estimate.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _private_dir(path):
    path.mkdir(parents=True, exist_ok=True)
    os.chmod(path, 0o700)
    return path


def _write_json(path, value):
    partial = path.with_name(path.name + '.partial')
    partial.write_text(json.dumps(value, default=str))
    partial.replace(path)


class CachedReadings(Mapping):
    """Readings loaded from disk one at a time; a whole case need not fit in memory."""

    def __init__(self, paths):
        self.paths = dict(paths)

    def __getitem__(self, key):
        return json.loads(self.paths[key].read_text())

    def __iter__(self):
        return iter(self.paths)

    def __len__(self):
        return len(self.paths)


# --- problem classification ------------------------------------------------

def template(message):
    """A problem message with every digit masked, and its stable id."""
    masked = re.sub(r'\s+', ' ', re.sub(r'\d', '#', message or '')).strip()
    return hashlib.sha256(masked.encode()).hexdigest()[:8], masked


def classify(problems):
    """Coarse reasons (batch view categories) and fine reasons for one held period."""
    from services.financial.batch_review_summary import reason as review_reason
    coarse, fine, templates = set(), set(), {}
    for problem in problems or []:
        reason = review_reason(problem)
        identifier, masked = template(problem.get('message'))
        templates[identifier] = masked
        detail = problem.get('field') or problem.get('check') or '-'
        coarse.add(reason)
        fine.add(f"{reason}|{problem.get('kind') or '-'}|{detail}|{identifier}")
    return sorted(coarse) or ['unspecified'], sorted(fine) or ['unspecified'], templates


# --- live inventory (read only) --------------------------------------------

def _live_state(status, can_import, saved_review):
    if status == 'ready' and can_import:
        return 'ready_after_edits' if saved_review else 'ready_no_edits'
    if status in ('imported', 'pending_import'):
        return 'imported_saved_review' if saved_review else 'imported'
    if status in LEFT_UNIMPORTED:
        return 'left_unimported'
    return 'held'


def live_item(item):
    """The stored state of one live batch item, as plain data (private detail)."""
    summary = item.summary or {}
    return dict(statement_key=item.statement_key or '', status=item.status,
        can_import=bool(summary.get('can_import', item.status == 'ready')), saved_review=bool(item.review_request),
        period_start=summary.get('period_start') or '', period_end=summary.get('period_end') or '',
        account=summary.get('account') or '', problems=list(summary.get('problems') or []))


def live_periods(items):
    """One live period per statement period of an original, however often it was read.

    Items are the same period when they share a statement key or both carry the
    same account and printed dates (a later reading can key the same period
    differently; one statement can hold several accounts with the same dates).
    An item without key or dates is an earlier whole-file preparation; when
    the original also has keyed periods it is history, not another period.
    The most advanced live state of a period is its state.
    """
    items = [item for item in items if item['status'] in LIVE_PRIORITY]  # superseded readings are history
    parent = list(range(len(items)))

    def root(index):
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index
    seen = {}
    for index, item in enumerate(items):
        labels = []
        if item['statement_key']:
            labels.append(('key', item['statement_key']))
        if item['period_start'] and item['period_end']:
            labels.append(('dates', item.get('account', ''), item['period_start'], item['period_end']))
        for label in labels:
            if label in seen:
                parent[root(index)] = root(seen[label])
            else:
                seen[label] = index
    groups = defaultdict(list)
    for index, item in enumerate(items):
        groups[root(index)].append(item)
    blank = [group for group in groups.values()
             if not any(i['statement_key'] or i['period_start'] or i['period_end'] for i in group)]
    real = [group for group in groups.values() if group not in blank]
    periods = []
    for group in (real or ([[item for group in blank for item in group]] if blank else [])):
        best = min(group, key=lambda i: LIVE_PRIORITY.index(i['status']))
        dated = next((i for i in group if i['period_start'] and i['period_end']), best)
        state = _live_state(best['status'], best['can_import'], best['saved_review'])
        coarse, fine, templates = classify(best['problems']) if state == 'held' else ([], [], {})
        periods.append(dict(statement_key=best['statement_key'], status=best['status'], state=state,
            period_start=dated['period_start'], period_end=dated['period_end'], account=dated.get('account', ''),
            items=len(group),
            coarse=coarse, fine=fine, templates=templates))
    return periods, sum(len(group) for group in blank) if real else 0


def live_files(session, case_id, resolve_path, retained_dir=None):
    """Every distinct original in every batch of the case, with its live periods."""
    from sqlalchemy import select
    from postgres.models.evidence import EvidenceDocumentText, EvidenceFile, EvidenceTableGeometry
    from postgres.models.financial_import_batches import (FinancialImportBatch as Batch,
        FinancialImportBatchItem as BatchItem)
    batches = list(session.scalars(select(Batch).where(Batch.case_id == case_id, Batch.status != 'removed')
        .order_by(Batch.created_at, Batch.id)))
    by_source = {}
    for batch in batches:
        for entry in batch.files or []:
            by_source.setdefault(entry.get('source_id') or entry.get('file_id'), []).append(entry)
    batch_ids = [batch.id for batch in batches]
    files, keys = [], Counter()

    def _id(value):
        try:
            return uuid.UUID(str(value))
        except (TypeError, ValueError):
            return None
    for source_id, entries in by_source.items():
        ids = {i for i in (_id(source_id), *(_id(entry.get('file_id')) for entry in entries)) if i}
        known = {file.id: file for file in session.scalars(select(EvidenceFile).where(
            EvidenceFile.case_id == case_id, EvidenceFile.id.in_(ids)))} if ids else {}
        source = known.get(_id(source_id))
        items = list(session.scalars(select(BatchItem).where(BatchItem.batch_id.in_(batch_ids),
            BatchItem.file_id.in_(ids)))) if ids and batch_ids else []
        sha = source.sha256 if source else None
        base = (sha or hashlib.sha256(str(source_id).encode()).hexdigest())[:12]
        keys[base] += 1
        key = base if keys[base] == 1 else f'{base}.{keys[base]}'
        record = dict(key=key, sha256=sha, path=None, available=source is not None,
            pdf=bool(source and source.original_filename.lower().endswith('.pdf')),
            entry_statuses=dict(Counter(entry.get('status') or 'unknown' for entry in entries)),
            entry_errors=sorted({entry.get('error') for entry in entries if entry.get('error')}),
            batches=len(entries), currency=next((e.get('currency') for e in reversed(entries) if e.get('currency')), None),
            live_items=[live_item(item) for item in items], retained=False)
        if source is not None:
            path = resolve_path(source.stored_path)
            record['path'] = str(path) if path else None
            record['original_filename'] = source.original_filename  # private detail only
        # The latest reading the live batches prepared from, as stored.
        for entry in reversed(entries):
            reading = known.get(_id(entry.get('file_id')))
            document = session.get(EvidenceDocumentText, reading.id) if reading else None
            if document is None:
                continue
            if retained_dir is not None:
                geometry = list(session.scalars(select(EvidenceTableGeometry).where(
                    EvidenceTableGeometry.evidence_file_id == reading.id,
                    EvidenceTableGeometry.engine_job_id == document.engine_job_id)))
                _write_json(retained_dir / f'{key}.json', dict(content=document.content,
                    content_sha256=document.content_sha256, character_count=document.character_count,
                    source_locations=document.source_locations, processing_manifest=document.processing_manifest,
                    geometry={str(row.page_number): row.payload for row in geometry}))
                session.expunge_all()
            record['retained'] = True
            break
        files.append(record)
    return files


# --- cached engine re-read ---------------------------------------------------

def engine_revision():
    """The evidence-engine code the readings come from."""
    return tree_revision('evidence-engine')


def _read_chunk(chunk, workdir, python, timeout):
    """One engine process for a few originals. Returns {sha256: reading}."""
    from benchmarks.statement_automation import engine_read
    workdir.mkdir(parents=True)
    links = {}
    for sha, path in chunk:
        link = workdir / f'{sha[:16]}.pdf'  # hash-only names keep file names out of every log
        link.symlink_to(path)
        links[str(link)] = sha
    target = workdir / 'readings.json'
    env = {**os.environ, 'PYTHONDONTWRITEBYTECODE': '1', 'OMP_THREAD_LIMIT': '1'}
    try:
        completed = subprocess.run([python, engine_read.__file__, str(target), '1', *links], capture_output=True,
            text=True, env=env, timeout=timeout)
    except subprocess.TimeoutExpired:
        return None, f'engine_timeout after {timeout} s'
    if completed.returncode != 0 or not target.is_file():
        return None, 'engine_process_failed: ' + completed.stderr[-500:]
    data = json.loads(target.read_text())
    return {links[path]: value for path, value in data['readings'].items()}, None


def cached_reread(originals, cache, python=sys.executable, workers=1, chunk=4, timeout=3600, log=None,
                  retry_errors=False, scratch_root=None):
    """Re-read {sha256: path} with the current engine, reusing earlier readings of the same code.

    Returns {sha256: Path of the cached reading}. A failed process is retried
    one file at a time; a file that still fails is cached as an ``error``
    reading, which is a measured outcome.
    """
    workers = max(1, min(int(workers), MAX_WORKERS))
    _private_dir(cache)
    done = {sha: cache / f'{sha}.json' for sha in originals}
    todo = []
    for sha, path in sorted(originals.items()):
        target = done[sha]
        if target.is_file() and not (retry_errors and 'error' in json.loads(target.read_text())):
            continue
        todo.append((sha, path))
    if not todo:
        return done
    if scratch_root:
        Path(scratch_root).mkdir(parents=True, exist_ok=True)
    scratch = Path(tempfile.mkdtemp(prefix=f'census-read-{os.getuid()}-', dir=scratch_root))
    os.chmod(scratch, 0o700)
    started, finished, counter = time.monotonic(), Counter(), iter(range(10 ** 9))

    def run(group):
        readings, error = _read_chunk(group, scratch / str(next(counter)), python, timeout * len(group))
        if readings is None and len(group) > 1:
            for single in group:
                run([single])
            return
        for sha, _ in group:
            value = (readings or {}).get(sha) or dict(error=error or 'engine_no_reading')
            _write_json(done[sha], value)
            finished['error' if 'error' in value else 'read'] += 1
        if log:
            log(f'read {sum(finished.values())}/{len(todo)} ({dict(finished)}) in {time.monotonic() - started:.0f} s')
    try:
        groups = [todo[i:i + chunk] for i in range(0, len(todo), chunk)]
        with ThreadPoolExecutor(max_workers=workers) as pool:
            list(pool.map(run, groups))
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    return done


def cached_reader(cache, python, workers, chunk, timeout, log=None, scratch_root=None):
    """A reader for the dry run and the audit (paths by key) backed by the census cache."""
    def reader(paths, _scratch, _python, _concurrency):
        shas = {}
        for key, path in paths.items():
            digest = hashlib.sha256()
            with Path(path).open('rb') as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b''):
                    digest.update(block)
            shas[key] = digest.hexdigest()
        done = cached_reread({sha: paths[key] for key, sha in shas.items()}, cache, python, workers, chunk,
            timeout, log, scratch_root=scratch_root)
        return CachedReadings({key: done[sha] for key, sha in shas.items()})
    return reader


# --- joining ------------------------------------------------------------------

def period_id(key, statement_key, start='', end=''):
    label = statement_key or f'{start}..{end}'
    return f"{key}#{hashlib.sha256(label.encode()).hexdigest()[:6]}"


def prepared_outcome(item):
    """ready; set aside by the system (a duplicate or assigned rows: correct when true); or held."""
    if item['ready']:
        return 'ready'
    if item['status'] == 'duplicate_ignored':
        return 'duplicate_set_aside'
    if item['status'] == 'assigned':
        return 'assigned'
    return 'held'


def _prepared(items):
    by_key = defaultdict(list)
    for item in items:
        outcome = prepared_outcome(item)
        coarse, fine, templates = classify(item['problems']) if outcome == 'held' else ([], [], {})
        by_key[item['key']].append(dict(statement_key=item['statement_key'], status=item['status'], ready=item['ready'],
            outcome=outcome,
            family=item['family'], period_start=item['period_start'], period_end=item['period_end'],
            account=item.get('account', ''), transaction_count=item['transaction_count'], coarse=coarse, fine=fine, templates=templates))
    return by_key


def _match(period, candidates, taken):
    for test in (lambda c: c['statement_key'] == period['statement_key'] and period['statement_key'],
                 lambda c: period['period_start'] and (c.get('account', ''), c['period_start'], c['period_end']) == (
                     period.get('account', ''), period['period_start'], period['period_end'])):
        for index, candidate in enumerate(candidates):
            if index not in taken and test(candidate):
                taken.add(index)
                return candidate
    return None


def join(files, current, retained, file_problems):
    """One row per period: the new reading's preparation, the retained one's, and the live state."""
    now, before = _prepared(current['items']), _prepared(retained['items'])
    errors_now = {entry['key']: entry['error'] for entry in current['file_errors']}
    errors_before = {entry['key']: entry['error'] for entry in retained['file_errors']}
    rows = []
    for file in files:
        key = file['key']
        live, legacy = live_periods(file['live_items'])
        file['legacy_file_items'] = legacy
        taken_live, taken_before = set(), set()
        prepared_now = now.get(key, [])
        file_state = file_problems.get(key) or (f'file_error: {errors_now[key]}' if key in errors_now else None) or (
            'identical_bytes' if '.' in key else None)  # a byte-identical copy is not selected again
        for period in prepared_now:
            match = _match(period, live, taken_live)
            old = _match(period, before.get(key, []), taken_before)
            rows.append(dict(period=period_id(key, period['statement_key'], period['period_start'], period['period_end']),
                file=key, family=period['family'], current=period, retained=old, live=match))
        for index, period in enumerate(before.get(key, [])):
            if index in taken_before:
                continue
            match = _match(period, live, taken_live)
            rows.append(dict(period=period_id(key, period['statement_key'], period['period_start'], period['period_end']),
                file=key, family=period['family'], current=None, current_file_state=file_state or 'no_period_now',
                retained=period, live=match))
        for index, period in enumerate(live):
            if index in taken_live:
                continue
            rows.append(dict(period=period_id(key, period['statement_key'], period['period_start'], period['period_end']),
                file=key, family='unknown', current=None, current_file_state=file_state or 'no_period_now',
                retained=None, retained_file_state=errors_before.get(key), live=period))
        if not prepared_now and not before.get(key) and not live:
            rows.append(dict(period=f'{key}#file', file=key, family='no_period', current=None,
                current_file_state=file_state or 'no_period_now', retained=None,
                retained_file_state=errors_before.get(key) or ('no_retained_reading' if not file['retained'] else None),
                live=None))
    return rows


def _outcome(side, state=None):
    if side is None:
        return state.split(':', 1)[0] if state else 'no_period'
    return side['outcome']


def tally(rows, files):
    """Counts only."""
    report = dict(files=len(files), periods=len(rows), by_family={}, live_states=Counter(), transitions=Counter(),
        reasons_current=Counter(), reasons_retained=Counter(), fine_current=Counter(), single_reason_current=Counter())
    by_family = defaultdict(Counter)
    for row in rows:
        now = _outcome(row['current'], row.get('current_file_state'))
        old = _outcome(row['retained'], row.get('retained_file_state'))
        live = row['live']['state'] if row['live'] else 'no_live_period'
        family = row['current']['family'] if row['current'] else (row['retained'] or {}).get('family', row['family'])
        counts = by_family[family]
        counts['periods'] += 1
        counts['ready_current'] += int(now == 'ready')
        counts['ready_retained'] += int(old == 'ready')
        counts['live_ready_or_imported_no_edits'] += int(live in ('ready_no_edits', 'imported'))
        report['live_states'][live] += 1
        report['transitions'][f'{live} -> {now}'] += 1
        if row['current'] and now != 'held':
            if now != 'ready':
                report['reasons_current'][now] += 1
                report['single_reason_current'][now] += 1
        elif row['current']:
            report['reasons_current'].update(row['current']['coarse'])
            report['fine_current'].update(row['current']['fine'])
            if len(row['current']['coarse']) == 1:
                report['single_reason_current'][row['current']['coarse'][0]] += 1
        elif not row['current']:
            report['reasons_current'][now] += 1
            report['single_reason_current'][now] += 1
        if row['retained'] and old == 'held':
            report['reasons_retained'].update(row['retained']['coarse'])
    report['by_family'] = {family: dict(counts) for family, counts in sorted(by_family.items())}
    report['ready_current'] = sum(c['ready_current'] for c in by_family.values())
    report['ready_retained'] = sum(c['ready_retained'] for c in by_family.values())
    for name in ('live_states', 'transitions', 'reasons_current', 'reasons_retained', 'fine_current',
                 'single_reason_current'):
        report[name] = dict(sorted(report[name].items()))
    report['file_states'] = dict(Counter(
        'unavailable' if not f['available'] else 'not_pdf' if not f['pdf'] else 'listed' for f in files))
    report['legacy_file_items'] = sum(f.get('legacy_file_items', 0) for f in files)
    report['outcomes_current'] = dict(sorted(Counter(
        _outcome(row['current'], row.get('current_file_state')) for row in rows).items()))
    return report


# --- the census of one case ---------------------------------------------------

def census(factory, case_id, out, *, cache=None, python=sys.executable, workers=1, chunk=4, timeout=3600,
           resolve_path=None, reader=None, audit=True, log=print, scratch_root=None):
    estimate = _estimate()
    case_dir = _private_dir(Path(out) / str(case_id))
    retained_dir = _private_dir(case_dir / 'retained')
    cache = Path(cache) if cache else Path(out) / 'readings' / engine_revision()
    started = time.monotonic()
    with factory() as db:
        estimate.read_only(db)
        files = live_files(db, case_id, resolve_path or estimate._resolver(), retained_dir)
        db.rollback()
    log(f'{len(files)} originals listed in {time.monotonic() - started:.0f} s')
    _write_jsonl(case_dir / 'files.jsonl', files)
    readable = [file for file in files if file['available'] and file['pdf']]
    paths, problems = estimate.verified_paths(readable)
    file_problems = {}
    for file in files:
        if not file['available']:
            file_problems[file['key']] = 'original_unavailable'
        elif not file['pdf']:
            file_problems[file['key']] = 'not_pdf'
        elif file['key'] not in paths:
            file_problems[file['key']] = 'original_changed_or_missing'
    started = time.monotonic()
    if reader is not None:
        readings = reader(paths, None, python, 1)
    else:
        done = cached_reread({file['sha256']: paths[file['key']] for file in readable if file['key'] in paths},
            cache, python, workers, chunk, timeout, log, scratch_root=scratch_root)
        readings = CachedReadings({file['key']: done[file['sha256']] for file in readable if file['key'] in paths})
    read_seconds = time.monotonic() - started
    for key in paths:
        reading = readings.get(key)
        if reading is None or 'error' in reading:
            file_problems[key] = 'engine_error: ' + ((reading or {}).get('error') or 'no reading')[:200]
    if scratch_root:
        Path(scratch_root).mkdir(parents=True, exist_ok=True)
    scratch = Path(tempfile.mkdtemp(prefix=f'census-{os.getuid()}-', dir=scratch_root))
    try:
        os.chmod(scratch, 0o700)
        current = _prepare_side(estimate, scratch, case_dir, 'current', [f for f in readable if f['key'] in paths],
            readings, log)
        retained_files = [f for f in files if f['retained']]
        retained = _prepare_side(estimate, scratch, case_dir, 'retained', retained_files,
            CachedReadings({f['key']: retained_dir / f"{f['key']}.json" for f in retained_files}), log)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    _write_json(case_dir / 'run.json', dict(case=str(case_id), code=estimate._code(), engine=engine_revision(),
        generated_at=datetime.now(timezone.utc).isoformat(timespec='seconds'), read_seconds=round(read_seconds),
        original_problems=dict(problems), file_problems=file_problems))
    report = rejoin(case_dir)
    if audit:
        misread = _audit_module()
        started = time.monotonic()
        result = misread.audit(factory, case_id, python=python, resolve_path=resolve_path, scratch_root=scratch_root,
            reader=reader or cached_reader(cache, python, workers, chunk, timeout, log, scratch_root))
        audit_dir = _private_dir(case_dir / 'audit')
        (audit_dir / 'report.json').write_text(json.dumps(result, indent=1, sort_keys=True, default=str) + '\n')
        (audit_dir / 'report.md').write_text(misread.render(result))
        report['audit'] = dict(considered=result['considered'], skipped=result['skipped'],
            outcomes=result.get('outcomes', {}), cells=result.get('cells', {}),
            original_problems=result.get('original_problems', {}), seconds=round(time.monotonic() - started))
    (case_dir / 'report.json').write_text(json.dumps(report, indent=1, sort_keys=True) + '\n')
    return report


def _write_jsonl(path, rows):
    partial = path.with_name(path.name + '.partial')
    with partial.open('w') as stream:
        for row in rows:
            stream.write(json.dumps(row, default=str) + '\n')
    partial.replace(path)


def rejoin(case_dir):
    """Periods and counts from a case's stored census inputs; no database, no reading."""
    case_dir = Path(case_dir)
    files = [json.loads(line) for line in (case_dir / 'files.jsonl').open()]
    run = json.loads((case_dir / 'run.json').read_text())
    current = json.loads((case_dir / 'prepared-current.json').read_text())
    retained = json.loads((case_dir / 'prepared-retained.json').read_text())
    rows = join(files, current, retained, run['file_problems'])
    templates = {}
    for row in rows:
        for side in ('current', 'retained', 'live'):
            if row.get(side):
                templates.update(row[side].pop('templates', {}))
    _write_jsonl(case_dir / 'periods.jsonl', rows)
    (case_dir / 'templates.json').write_text(json.dumps(templates, indent=1, sort_keys=True))
    report = dict(tally(rows, files), **{k: v for k, v in run.items() if k != 'file_problems'},
        file_problems=dict(Counter(v.split(':', 1)[0] for v in run['file_problems'].values())),
        current_file_errors=len(current['file_errors']), retained_file_errors=len(retained['file_errors']),
        retained_failed=retained.get('failed'))
    previous = case_dir / 'report.json'
    if previous.is_file() and 'audit' in json.loads(previous.read_text()):
        report['audit'] = json.loads(previous.read_text())['audit']
    previous.write_text(json.dumps(report, indent=1, sort_keys=True) + '\n')
    return report


def tree_revision(path):
    """The committed tree of a repository path, plus a digest of any uncommitted change to it."""
    try:
        tree = subprocess.run(['git', 'rev-parse', f'HEAD:{path}'], cwd=BACKEND.parent, capture_output=True,
            text=True, check=True).stdout.strip()
        dirty = subprocess.run(['git', 'diff', 'HEAD', '--', path], cwd=BACKEND.parent,
            capture_output=True, check=True).stdout
    except (OSError, subprocess.SubprocessError):
        return 'unknown'
    return tree[:12] + ('-' + hashlib.sha256(dirty).hexdigest()[:8] if dirty else '')


def _prepare_side(estimate, scratch, case_dir, label, files, readings, log):
    """One prepared batch, stored at once and reused while its inputs and the backend are unchanged.

    The fingerprint covers the backend services tree, the scripts, and every
    input reading's bytes. A failure of the retained side is recorded, not
    fatal: the new reading is the census.
    """
    digest = hashlib.sha256(json.dumps([label, tree_revision('backend/services'), tree_revision('backend/scripts')]).encode())
    for file in sorted(files, key=lambda f: f['key']):
        digest.update(f"{file['key']}:{file['sha256']}:".encode())
        path = getattr(readings, 'paths', {}).get(file['key'])
        if path is not None and Path(path).is_file():
            digest.update(hashlib.sha256(Path(path).read_bytes()).digest())
        else:
            digest.update(json.dumps(readings.get(file['key']), sort_keys=True, default=str).encode())
    fingerprint = digest.hexdigest()
    target = case_dir / f'prepared-{label}.json'
    if target.is_file():
        stored = json.loads(target.read_text())
        if stored.get('fingerprint') == fingerprint:
            log(f'{label} readings: stored preparation reused')
            return stored
    started = time.monotonic()
    try:
        result = estimate.scratch_batch(scratch, label, files, readings, retained_currency=False)
    except Exception as error:
        if label == 'current':
            raise
        log(f'{label} readings could not be prepared: {type(error).__name__}')
        result = dict(items=[], files=0, file_errors=[], failed=type(error).__name__)
    result.update(fingerprint=fingerprint, seconds=round(time.monotonic() - started))
    _write_json(target, result)
    log(f'{label} readings prepared in {result["seconds"]} s')
    return result


def _audit_module():
    spec = importlib.util.spec_from_file_location('financial_ledger_misread_audit',
        BACKEND / 'scripts/financial_ledger_misread_audit.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --- shareable summary (counts and opaque ids only) ----------------------------

def _code_text():
    """Message templates that appear literally in the backend source are code text, not case data."""
    chunks = []
    for path in (BACKEND / 'services').rglob('*.py'):
        chunks.append(path.read_text(errors='ignore'))
    return '\n'.join(chunks)


def _label(identifier, masked, code):
    if masked and '#' not in masked and len(masked) >= 12 and masked in code:
        return masked
    if masked and '#' in masked:
        parts = [part.strip() for part in re.split(r'[^A-Za-z ,.;:()\'-]+', masked) if len(part.strip()) >= 12]
        if parts and all(part in code for part in parts):
            return masked
    return f'template {identifier}'


def summarize(out, target, examples=3):
    out = Path(out)
    reports, rows_by_case = [], {}
    for report_path in sorted(out.glob('*/report.json')):
        report = json.loads(report_path.read_text())
        reports.append(report)
        rows_by_case[report['case']] = [json.loads(line) for line in (report_path.parent / 'periods.jsonl').open()]
    templates = {}
    for report_path in out.glob('*/templates.json'):
        templates.update(json.loads(report_path.read_text()))
    code = _code_text()
    lines = ['# Real-statement census (counts only)', '',
        f"Generated {datetime.now(timezone.utc).isoformat(timespec='seconds')}. Periods by opaque id "
        '(case prefix : original sha256 prefix # statement hash). The same original filed in several cases is counted '
        'in each case. Private detail stays under the census directory.', '',
        '"Ready" = ready without any human edit, prepared by the current backend from the source alone '
        '(no investigator currency choice applied). Live = stored batch state.', '',
        '## By case', '', '| case | originals | periods | ready (new reading) | ready (retained reading) | '
        'live ready/imported w/o saved review | live held | engine errors | audit flagged / considered |',
        '|---|---|---|---|---|---|---|---|---|']
    total = Counter()
    for report in reports:
        live = report['live_states']
        audit = report.get('audit') or {}
        flagged = (audit.get('outcomes') or {}).get('flagged', 0)
        lines.append(f"| {report['case'][:8]} | {report['files']} | {report['periods']} | {report['ready_current']} | "
            f"{report['ready_retained']} | {live.get('ready_no_edits', 0) + live.get('imported', 0)} | {live.get('held', 0)} | "
            f"{report['file_problems'].get('engine_error', 0)} | {flagged} / {audit.get('considered', '-')} |")
        total.update(dict(files=report['files'], periods=report['periods'], ready_current=report['ready_current'],
            ready_retained=report['ready_retained']))
    if total['periods']:
        lines.append(f"| **all** | {total['files']} | {total['periods']} | {total['ready_current']} "
            f"({100 * total['ready_current'] / total['periods']:.1f}%) | {total['ready_retained']} | | | | |")
    family_rows, ranking, single, transitions = defaultdict(Counter), defaultdict(list), Counter(), Counter()
    fine_ranking = defaultdict(list)
    for case, rows in rows_by_case.items():
        for row in rows:
            current = row['current']
            family = current['family'] if current else (row['retained'] or {}).get('family', row['family'])
            family_rows[family]['periods'] += 1
            family_rows[family]['ready'] += int(bool(current and current['ready']))
            live = row['live']['state'] if row['live'] else 'no_live_period'
            transitions[(live, _outcome(current, row.get('current_file_state')))] += 1
            if current and current['ready']:
                continue
            outcome = _outcome(current, row.get('current_file_state'))
            reasons = current['coarse'] if outcome == 'held' else [outcome]
            for reason in reasons:
                ranking[(family, reason)].append(f"{case[:8]}:{row['period']}")
            if len(reasons) == 1:
                single[(family, reasons[0])] += 1
            for fine in (current['fine'] if outcome == 'held' else []):
                fine_ranking[(family, fine)].append(f"{case[:8]}:{row['period']}")
    lines += ['', '## By statement family (new reading)', '', '| family | periods | ready | % |', '|---|---|---|---|']
    for family, counts in sorted(family_rows.items(), key=lambda pair: -pair[1]['periods']):
        lines.append(f"| {family} | {counts['periods']} | {counts['ready']} | {100 * counts['ready'] / counts['periods']:.0f}% |")
    lines += ['', '## Live state -> new reading', '', '| live | new reading | periods |', '|---|---|---|']
    for (live, now), count in sorted(transitions.items(), key=lambda pair: -pair[1]):
        lines.append(f'| {live} | {now} | {count} |')
    lines += ['', '## Blocking reasons ranked by periods affected (family x reason, overlapping)', '',
        '"Only reason" = periods held by this reason alone (fixing it makes them ready unless a hidden check follows).', '',
        '| family | reason | periods | only reason | examples |', '|---|---|---|---|---|']
    for (family, reason), ids in sorted(ranking.items(), key=lambda pair: (-len(pair[1]), pair[0])):
        lines.append(f"| {family} | {reason} | {len(ids)} | {single[(family, reason)]} | {', '.join(sorted(ids)[:examples])} |")
    lines += ['', '## Fine reasons (family x reason|problem kind|field or check|message)', '',
        '| family | reason | kind | field/check | message | periods | examples |', '|---|---|---|---|---|---|---|']
    for (family, fine), ids in sorted(fine_ranking.items(), key=lambda pair: (-len(pair[1]), pair[0]))[:80]:
        reason, kind, detail, identifier = fine.split('|') if fine.count('|') == 3 else (fine, '-', '-', '')
        label = _label(identifier, templates.get(identifier, ''), code).replace('|', '/')
        lines.append(f"| {family} | {reason} | {kind} | {detail} | {label} | {len(ids)} | {', '.join(sorted(ids)[:examples])} |")
    lines += ['', '## Ledger misread audit (admitted image-derived statements re-read)', '',
        '| case | considered | skipped | outcomes | cells |', '|---|---|---|---|---|']
    for report in reports:
        audit = report.get('audit') or {}
        lines.append(f"| {report['case'][:8]} | {audit.get('considered', '-')} | {audit.get('skipped', {})} | "
            f"{audit.get('outcomes', {})} | {audit.get('cells', {})} |")
    Path(target).write_text('\n'.join(lines) + '\n')
    return '\n'.join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--case', type=uuid.UUID, action='append', default=[])
    parser.add_argument('--out', type=Path, required=True, help='private directory (outside git)')
    parser.add_argument('--cache', type=Path, default=None, help='reading cache (default OUT/readings/<engine>)')
    parser.add_argument('--workers', type=int, default=1, help=f'engine processes (at most {MAX_WORKERS})')
    parser.add_argument('--chunk', type=int, default=4, help='originals per engine process')
    parser.add_argument('--timeout', type=int, default=3600, help='seconds per original before it counts as failed')
    parser.add_argument('--engine-python', default=sys.executable)
    parser.add_argument('--no-audit', action='store_true')
    parser.add_argument('--scratch', type=Path, default=None)
    parser.add_argument('--summarize', type=Path, default=None, help='write the counts-only summary here')
    parser.add_argument('--rejoin', action='store_true', help='recount every case under --out from its stored inputs')
    args = parser.parse_args(argv)
    _private_dir(args.out)
    if args.rejoin:
        for run in sorted(args.out.glob('*/run.json')):
            rejoin(run.parent)
    if args.case:
        from postgres.session import _get_session_local
        factory = _get_session_local()
        for case_id in args.case:
            def log(message, case=str(case_id)[:8]):
                print(f"{datetime.now(timezone.utc).isoformat(timespec='seconds')} {case} {message}", flush=True)
            report = census(factory, case_id, args.out, cache=args.cache, python=args.engine_python,
                workers=args.workers, chunk=args.chunk, timeout=args.timeout, audit=not args.no_audit, log=log,
                scratch_root=args.scratch)
            log(f"done: {report['periods']} periods, {report['ready_current']} ready (new), "
                f"{report['ready_retained']} ready (retained)")
    if args.summarize:
        print(summarize(args.out, args.summarize))


if __name__ == '__main__':
    main()
