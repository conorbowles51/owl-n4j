"""Fresh-upload automation benchmark for statement import (checkpoint A).

One command, from the repository root::

    scripts/run_statement_benchmark.sh [--out DIR]

What runs, in order, all against a disposable SQLite database in DIR:

1. Upload: each corpus PDF is registered through ``EvidenceDBStorage.add_files``
   (the upload path, including its same-hash duplicate flag) in one folder.
2. Reading: the evidence engine's own PDF preparation code reads every PDF in
   a separate process (``engine_read.py``): native text, table geometry, OCR
   fallback and the quality-triggered source-image reread.
3. Preparation: ``import_batches.create_batch`` for the folder, then repeated
   ``advance_batch`` worker turns. The worker's ``process_files`` hook stores
   the engine reading exactly as ``prepare_pdf_review`` would, so catalog,
   proposal, readiness assessment and duplicate preparation are the real code.
4. Measurement: ``batch_status`` is read once, as the batch screen would. Each
   statement period is matched to the manifest's ground truth.
5. Human effort: for each period that is not importable, the harness builds
   the correction an investigator would have to make from the ground truth,
   counts each field edit and decision, and re-runs the real ``assess`` to see
   whether those actions are sufficient. Periods it cannot fix by field edits
   (for example a missing printed row) are reported as such.
6. Group import: ``queue_import`` with the displayed ready revision, then
   worker turns until the queue drains. Every saved transaction is compared
   with the ground truth for amount, direction, currency, account and date.

No cached readings, saved corrections or prior admissions exist: this is the
plan's fresh-upload track. Nothing outside DIR is written.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib
import json
import os
import pkgutil
import re
import shutil
import subprocess
import sys
import time
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parents[1]
REPO = BACKEND.parent
CORPUS = HERE / 'corpus'
MAX_WORKER_TURNS = 400


def _load_models():
    import postgres.models as models
    for module in pkgutil.iter_modules(models.__path__):
        importlib.import_module('postgres.models.' + module.name)


def _database(path):
    from sqlalchemy import create_engine, event
    from sqlalchemy.orm import sessionmaker
    from postgres.base import Base
    _load_models()
    engine = create_engine(f'sqlite+pysqlite:///{path}', future=True)

    @event.listens_for(engine, 'connect')
    def _configure(connection, _record):
        cursor = connection.cursor()
        cursor.execute('PRAGMA foreign_keys=ON')
        cursor.close()

    skipped = []
    for table in Base.metadata.sorted_tables:
        try:
            table.create(engine)
        except Exception as error:  # Postgres-only column types outside finance.
            skipped.append(f'{table.name}: {type(error).__name__}')
    if any(name.split(':')[0].startswith('financial') or name.split(':')[0].startswith('evidence')
           for name in skipped):
        raise RuntimeError('A financial or evidence table could not be created: ' + ', '.join(skipped))
    return engine, sessionmaker(bind=engine, autoflush=False, autocommit=False), skipped


def _digits(value):
    return re.sub(r'\D', '', value or '')


def _norm(value):
    return re.sub(r'\s+', ' ', (value or '').strip().lower())


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------

def read_corpus(python, files, out, concurrency):
    target = out / 'engine-readings.json'
    started = time.monotonic()
    completed = subprocess.run([python, str(HERE / 'engine_read.py'), str(target), str(concurrency),
                                *[str(path) for path in files]],
                               capture_output=True, text=True, env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
    wall = time.monotonic() - started
    (out / 'engine-read.log').write_text(completed.stdout + completed.stderr)
    if completed.returncode != 0:
        raise RuntimeError('Engine reading failed; see ' + str(out / 'engine-read.log'))
    data = json.loads(target.read_text())
    return data['readings'], wall, data.get('child_cpu_seconds', 0.0)


def repair_summary(locations):
    """What the reader did per page, from the persisted source locations."""
    pages = [l for l in locations or [] if l.get('kind') == 'page']
    summary = dict(pages=len(pages), native=0, full_page_ocr=0, quality_reread=0, detection_reasons=Counter(),
                   refinements=Counter())
    for page in pages:
        reason = page.get('detection_reason')
        if page.get('extraction_method') == 'tesseract_ocr':
            summary['detection_reasons'][reason or 'ocr'] += 1
            if reason == 'unreadable_statement_fields':
                summary['quality_reread'] += 1
            else:
                summary['full_page_ocr'] += 1
        else:
            summary['native'] += 1
        for record in page.get('ocr_refinements') or []:
            label = record.get('method') or record.get('field') or 'refinement'
            outcome = record.get('decision') or record.get('status') or ('value' if record.get('text') else 'recorded')
            summary['refinements'][f'{label}:{outcome}'] += 1
    return summary


# ---------------------------------------------------------------------------
# Ground truth matching and simulated human correction
# ---------------------------------------------------------------------------

def _payment_rows(proposal):
    return [r for r in proposal['rows'] if not r['excluded'] and r['kind'] in ('transaction', 'unresolved')]


def _same_date(printed, recorded):
    """A truth row whose statement prints no date (``None``) accepts whatever date was recorded."""
    return printed is None or printed == recorded


def _match_rows(proposal_rows, truth_rows, by_value=False):
    """Pair proposal rows with truth rows by printed description, then order.

    ``by_value`` (real corpora, whose truth descriptions come from another
    reader) first pairs rows whose amount, direction and date all agree.
    """
    pairs, unmatched = {}, list(range(len(truth_rows)))
    if by_value:
        for row in proposal_rows:
            f = row['fields']
            best = next((i for i in unmatched if str(truth_rows[i]['amount_minor']) == f.get('amount_minor')
                         and truth_rows[i]['direction'] == f.get('direction')
                         and _same_date(truth_rows[i]['date'], f.get('date'))), None)
            if best is not None:
                pairs[row['id']] = best
                unmatched.remove(best)
    for row in proposal_rows:
        if row['id'] in pairs:
            continue
        text = _norm(row['fields'].get('description', '')) or _norm(' '.join(c['expected_text'] for c in row['source_cells']))
        best = next((i for i in unmatched if _norm(truth_rows[i]['description']) in text
                     or (text and text in _norm(truth_rows[i]['description']))), None)
        if best is not None:
            pairs[row['id']] = best
            unmatched.remove(best)
    return pairs, unmatched


def _score(proposal, truth, summary):
    score = 0
    if truth['period_end'] and summary.get('period_end') == truth['period_end']:
        score += 5
    if truth.get('added_in') == 'real' and truth.get('account') and truth['account'] in _digits(summary.get('account')):
        score += 5  # real documents hold sub-accounts with the same dates
    if truth.get('share') and truth['share'] in json.dumps(proposal.get('metadata', {})):
        score += 5
    amounts = Counter(r['fields'].get('amount_minor') for r in _payment_rows(proposal))
    for item in truth['rows']:
        if amounts.get(str(item['amount_minor'])):
            score += 1
    # Currency only breaks ties. Two sections of one file can differ by
    # nothing else (Monex MXN and USD zero-activity sections); without it they
    # pair by item order, possibly crosswise. As a tie-breaker it can never
    # outweigh content evidence, so a misread currency still pairs by content
    # and is still reported as currency_wrong.
    currency = (summary.get('currency') or proposal.get('currency') or '').upper()
    return score, int(bool(currency) and currency == (truth.get('currency') or '').upper())


def pair_truth(proposal, candidates, summary):
    """The unused ground-truth period a batch item describes, or None."""
    if proposal is None or not candidates:
        return candidates[0] if proposal is None and len(candidates) == 1 else None
    truth = max(candidates, key=lambda t: _score(proposal, t, summary))
    if len(candidates) > 1 and not any(_score(proposal, truth, summary)):
        return None
    return truth


def simulate_correction(proposal, truth, assess, initial_request):
    """Apply ground truth like an investigator; count each action; re-assess."""
    raw = initial_request(proposal)
    actions = []

    def act(kind, field, detail=''):
        actions.append(dict(kind=kind, field=field, detail=detail))

    if not raw.get('currency'):
        raw['currency'] = truth['currency']
        act('decision', 'currency')
    if not _norm(raw.get('holder')) or _norm(truth['holder']) not in _norm(raw.get('holder')):
        raw['holder'] = truth['holder']
        act('edit' if truth['holder_printed'] else 'decision', 'holder')
    if truth['account'] not in _digits(raw.get('account_number')):
        raw['account_number'] = truth['account']
        act('edit' if truth['account_printed'] else 'decision', 'account')
    if not raw.get('institution'):
        raw['institution'] = truth['institution']
        act('edit', 'institution')
    if truth['period_end'] and raw.get('period_end') != truth['period_end']:
        raw['period_end'] = truth['period_end']
        # A closing date the reader already recognised (Merrick statement
        # date) can be filled by the grouped unprinted-start decision.
        recognised = proposal.get('printed_closing_date_iso') == truth['period_end']
        act('edit', 'period_end', 'recognised_closing' if recognised else '')
    if truth['start_printed']:
        if raw.get('period_start') != truth['period_start']:
            raw['period_start'] = truth['period_start']
            act('edit', 'period_start')
    elif not raw.get('period_start'):
        raw['period_start_unprinted'] = True
        act('decision', 'period_start_unprinted')
    rows = {r['id']: r for r in raw['rows']}
    payments = _payment_rows(proposal)
    pairs, missing = _match_rows(payments, truth['rows'], by_value=truth.get('added_in') == 'real')
    for original in payments:
        edit = rows[original['id']]
        index = pairs.get(original['id'])
        if index is None:
            edit.update(excluded=True, reason='Not a payment on the printed statement.')
            act('edit', 'exclude_row', original['id'])
            continue
        expected = truth['rows'][index]
        if not _same_date(expected['date'], edit.get('date')):
            edit['date'] = expected['date']
            act('edit', 'row_date', original['id'])
        if edit.get('amount_minor') != str(expected['amount_minor']):
            edit['amount_minor'] = str(expected['amount_minor'])
            act('edit', 'row_amount', original['id'])
        if edit.get('direction') != expected['direction']:
            edit['direction'] = expected['direction']
            act('edit', 'row_direction', original['id'])
        unreadable_balance = edit.get('balance_minor') is None and any('balance' in i.lower() for i in original['issues'])
        if 'balance_after' in expected and (unreadable_balance or edit.get('balance_minor') not in (None, str(expected['balance_after']))):
            edit['balance_minor'] = str(expected['balance_after'])
            act('edit', 'row_balance', original['id'])
    for index in missing:
        act('add_row', 'missing_row', truth['rows'][index]['description'])
    # Printed opening/closing controls that were misread or held unreadable.
    for original in proposal['rows']:
        description = original['fields'].get('description') or ''
        target = (truth['opening_minor'] if re.search(r'Opening Balance|Previous\s*Balance', description)
                  else truth['closing_minor'] if re.search(r'Closing Balance|Ending Balance', description) else None)
        if original['kind'] == 'balance' and target is not None:
            edit = rows.get(original['id'])
            unreadable = (edit is not None and edit.get('balance_minor') is None
                          and 'balance' not in original['fields'])
            if edit is not None and (unreadable or edit.get('balance_minor') is not None
                                     and edit['balance_minor'] != str(target)):
                edit['balance_minor'] = str(target)
                act('edit', 'printed_balance', original['id'])
    status, summary = assess(proposal, raw)
    if not summary['can_import'] and not truth['rows'] and summary.get('admission'):
        raw.update(no_activity_confirmed=True, no_activity_revision=summary['admission']['revision'])
        status, summary = assess(proposal, raw)
        if summary['can_import']:
            act('decision', 'confirm_no_activity')
        else:
            raw.update(no_activity_confirmed=False, no_activity_revision=None)
    return dict(actions=actions, missing_rows=len(missing), resolved=bool(summary['can_import']),
                remaining=[p['message'] for p in summary['problems']][:8], status=status)


# ---------------------------------------------------------------------------
# The run
# ---------------------------------------------------------------------------

def run(out, python, concurrency, corpus=CORPUS):
    from sqlalchemy import select
    out.mkdir(parents=True, exist_ok=True)
    run_started = time.monotonic()
    manifest = json.loads((corpus / 'manifest.json').read_text())
    source_dir = out / 'sources'
    source_dir.mkdir(exist_ok=True)
    corpus_problems = []
    # A real corpus is private and large: its files are verified and linked in
    # place, never copied. The synthetic corpus is copied as before.
    in_place = manifest.get('synthetic') is False
    for record in manifest['files']:
        source = (corpus / record['filename']).resolve()
        digest = hashlib.sha256()
        with source.open('rb') as stream:
            for chunk in iter(lambda: stream.read(1 << 20), b''):
                digest.update(chunk)
        if digest.hexdigest() != record['sha256']:
            corpus_problems.append(record['filename'])
        target = source_dir / record['filename']
        if in_place:
            if target.is_symlink() or target.exists():
                target.unlink()
            target.symlink_to(source)
        else:
            target.write_bytes(source.read_bytes())
    if corpus_problems:
        raise RuntimeError('Corpus files differ from the manifest: ' + ', '.join(corpus_problems))

    load_before = os.getloadavg()
    readings, read_wall, read_cpu = read_corpus(python, [source_dir / f['filename'] for f in manifest['files']],
                                                out, concurrency)
    readings = {Path(path).name: value for path, value in readings.items()}

    from postgres.models.user import User
    from postgres.models.case import Case
    from postgres.models.enums import GlobalRole
    from postgres.models.evidence import EvidenceFile, EvidenceFolder, EvidenceDocumentText, EvidenceTableGeometry
    from postgres.models.financial import FinancialTransaction, FinancialAccount
    from services.evidence_db_storage import EvidenceDBStorage
    from services.financial import import_batches as batches
    from services.financial.batch_review_summary import reason as review_reason
    from services.financial.decisions import Actor
    from services.financial.statement_import import read_statement_import

    engine, factory, skipped_tables = _database(out / 'benchmark.db')
    with factory() as db:
        user = User(id=uuid.uuid4(), email='benchmark@example.test', name='Benchmark investigator',
                    password_hash='not-used', global_role=GlobalRole.user, is_active=True)
        case = Case(id=uuid.uuid4(), title='Synthetic automation benchmark', created_by_user_id=user.id,
                    owner_user_id=user.id)
        folder = EvidenceFolder(id=uuid.uuid4(), case_id=case.id, name='Synthetic statements')
        db.add_all([user, case, folder])
        db.commit()
        created = EvidenceDBStorage.add_files(db, case.id, [dict(original_filename=f['filename'],
            stored_path=str(source_dir / f['filename']), sha256=f['sha256'], size=f['size'])
            for f in manifest['files']], folder_id=folder.id, created_by_id=user.id)
        db.commit()
        file_names = {f.id: f.original_filename for f in created}
        duplicates_flagged = sorted(f.original_filename for f in created if f.is_duplicate)
        case_id, folder_id = case.id, folder.id
        actor = Actor(user.name, user.email, user.id)

    persisted = Counter()

    async def process_files(session, *, case_id, file_ids, preparation_mode, force_reprocess, requested_by_user_id):
        """Store the engine's reading as prepare_pdf_review does, then finish the job."""
        jobs = []
        for file_id in file_ids:
            record = session.get(EvidenceFile, file_id)
            reading = readings[Path(record.stored_path).name]
            if 'error' in reading:
                record.status = 'failed'
                record.last_error = reading['error']
                session.commit()
                jobs.append(str(uuid.uuid4()))
                continue
            job = uuid.uuid4()
            session.add(EvidenceDocumentText(evidence_file_id=file_id, engine_job_id=job, content=reading['content'],
                content_sha256=reading['content_sha256'], character_count=reading['character_count'],
                source_locations=reading['source_locations'], processing_manifest=reading['processing_manifest']))
            for page, entries in reading['geometry'].items():
                session.add(EvidenceTableGeometry(evidence_file_id=file_id, page_number=int(page),
                                                  engine_job_id=job, payload=entries))
            record.status = 'processed'
            record.engine_job_id = str(job)
            persisted[record.original_filename] += 1
            jobs.append(str(job))
        session.commit()
        return dict(job_ids=jobs)

    with factory() as db:
        batch_id = batches.create_batch(db, case_id=case_id, request_id=uuid.uuid4(), file_ids=[],
                                        folder_ids=[folder_id], actor=actor)

    # A worker turn checks or imports a handful of items; a large real corpus
    # needs more turns than the synthetic one (whose limit stays 400).
    turn_limit = max(MAX_WORKER_TURNS, 2 * len(manifest['files']) + sum(len(f['periods']) for f in manifest['files']))

    def drain(label):
        started, turns = time.monotonic(), 0
        while turns < turn_limit:
            asyncio.run(batches.advance_batch(factory, batch_id, Path, process_files))
            turns += 1
            with factory() as db:
                state = batches.batch_for(db, case_id, batch_id).status
            if state not in ('preparing',):
                break
        return dict(stage=label, turns=turns, seconds=time.monotonic() - started, final_status=state)

    preparation = drain('preparation')
    started = time.monotonic()
    with factory() as db:
        status = batches.batch_status(db, case_id=case_id, batch_id=batch_id, limit=10_000)
    status_seconds = time.monotonic() - started

    truths = {p['id']: dict(p, filename=f['filename']) for f in manifest['files'] for p in f['periods']}
    by_file = defaultdict(list)
    for truth in truths.values():
        by_file[truth['filename']].append(truth)

    periods = []
    used = set()
    with factory() as db:
        for item in status['items']:
            filename = file_names.get(uuid.UUID(item['file_id'])) or item.get('filename')
            try:
                proposal = read_statement_import(db, case_id=case_id, evidence_file_id=uuid.UUID(item['file_id']),
                    currency=item.get('currency') or None, statement_id=item.get('statement_id'))
            except Exception as error:
                proposal = None
                proposal_error = f'{type(error).__name__}: {error}'
            candidates = [t for t in by_file.get(filename, []) if t['id'] not in used]
            truth = pair_truth(proposal, candidates, item)
            if truth:
                used.add(truth['id'])
            reasons = Counter(review_reason(p) for p in item.get('problems', []))
            if item.get('problem_count', 0) > len(item.get('problems', [])):
                reasons['additional'] += item['problem_count'] - len(item['problems'])
            entry = dict(item_id=item['id'], filename=filename, statement_id=item.get('statement_id'),
                         scored=_scored(truth),
                         status=item['status'], can_import=bool(item.get('can_import')),
                         truth_id=truth['id'] if truth else None, family=truth['family'] if truth else 'unmatched',
                         expected=truth['expected'] if truth else None, defects=truth['defects'] if truth else [],
                         added_in=truth.get('added_in', 'v1-v3') if truth else None,
                         reasons=dict(reasons), problems=[p.get('message', '') for p in item.get('problems', [])][:12],
                         read=dict(holder=item.get('holder'), account=item.get('account'),
                                   institution=item.get('institution'), currency=item.get('currency'),
                                   period_start=item.get('period_start'), period_end=item.get('period_end'),
                                   transactions=item.get('transaction_count')))
            if proposal is None:
                entry['proposal_error'] = proposal_error
            elif truth:
                entry['proposal_checks'] = proposal_field_errors(proposal, truth)
                if not entry['can_import']:
                    entry['correction'] = simulate_correction(proposal, truth, batches.assess, batches.initial_request)
            periods.append(entry)
    missing = [t for t in truths.values() if t['id'] not in used]
    for truth in missing:
        periods.append(dict(item_id=None, filename=truth['filename'], statement_id=None, status='not_detected',
            scored=_scored(truth), can_import=False, truth_id=truth['id'], family=truth['family'], expected=truth['expected'],
            defects=truth['defects'], added_in=truth.get('added_in', 'v1-v3'), reasons={'not_detected': 1},
            problems=[], read={}))

    # Group import of everything the batch offers, exactly once.
    import_result = dict(queued=0)
    started = time.monotonic()
    if status['available_statements']:
        with factory() as db:
            queued = batches.queue_import(db, case_id=case_id, batch_id=batch_id,
                expected_revision=status['ready_revision'], actor=actor)
        import_result['queued'] = queued['queued']
        import_result['drain'] = drain('import')
    import_result['seconds'] = time.monotonic() - started
    with factory() as db:
        final = batches.batch_status(db, case_id=case_id, batch_id=batch_id, limit=10_000)
        final_items = {i['id']: i for i in final['items']}
        ledger = verify_ledger(db, periods, final_items, truths, FinancialTransaction, FinancialAccount, select,
                               _incomplete(manifest))

    repairs = {name: repair_summary(r.get('source_locations')) for name, r in readings.items() if 'error' not in r}
    result = dict(
        generated_at=datetime.now(timezone.utc).isoformat(timespec='seconds'),
        corpus=dict(version=manifest['version'], files=len(manifest['files']), periods=len(truths), path=str(corpus)),
        code=dict(commit=_git('rev-parse', 'HEAD'), dirty=bool(_git('status', '--porcelain', '--', 'backend', 'evidence-engine'))),
        environment=dict(cpus=os.cpu_count(), load_average_before=load_before, load_average_after=os.getloadavg(),
                         python=sys.version.split()[0], engine_python=python, tesseract=_tesseract(),
                         database='sqlite (disposable, ' + str(out / 'benchmark.db') + ')',
                         skipped_non_financial_tables=skipped_tables),
        upload=dict(duplicates_flagged=duplicates_flagged),
        timing=dict(engine_read_wall_seconds=read_wall, engine_read_cpu_seconds=read_cpu,
                    engine_read_seconds_per_file={k: v.get('seconds') for k, v in readings.items()},
                    preparation=preparation, batch_status_seconds=status_seconds, group_import=import_result,
                    total_wall_seconds=time.monotonic() - run_started),
        reading_errors={k: v['error'] for k, v in readings.items() if 'error' in v},
        repairs={k: dict(v, detection_reasons=dict(v['detection_reasons']), refinements=dict(v['refinements']))
                 for k, v in repairs.items()},
        batch=dict(status=status['status'], counts=status['counts'], statement_summary=status['statement_summary'],
                   review_groups=[dict(id=g['id'], statements=g.get('statement_count')) for g in status['review_summary'].get('groups', [])],
                   available_statements=status['available_statements'], files=[dict(filename=f['filename'],
                   status=f['status'], error=f.get('error')) for f in status['files']]),
        final_counts=final['counts'],
        periods=periods,
        ledger=ledger,
    )
    result['metrics'] = metrics(result)
    (out / 'results.json').write_text(json.dumps(result, indent=1, default=str) + '\n')
    (out / 'summary.md').write_text(render_summary(result))
    engine.dispose()
    return result


SCORED_TRUTH = {'verified'}  # ``--score`` adds e.g. ``ocr_reconciled`` for a secondary figure


def _scored(truth):
    """Only periods whose ground truth reconciled are scored. Synthetic truth is always scored;
    a real period carries ``truth_status`` and counts only when it is in ``SCORED_TRUTH``."""
    return truth is None or truth.get('truth_status', 'verified') in SCORED_TRUTH


def _incomplete(manifest):
    return {f['filename'] for f in manifest['files'] if f.get('truth_complete') is False}


def _rematch(periods, truths):
    """Re-pair batch items with real truth periods of the same file by closing date, account and share
    (from what each item read). Returns how many pairings changed; their stored proposal checks and
    simulated corrections belong to the earlier pairing and are dropped."""
    by_file = defaultdict(list)
    for truth in truths.values():
        if truth.get('added_in') == 'real':
            by_file[truth['filename']].append(truth)
    changed = 0
    for filename, candidates in by_file.items():
        items = [p for p in periods if p['filename'] == filename and p.get('item_id')]

        def fit(item, truth):
            read = item.get('read') or {}
            return ((read.get('period_end') == truth['period_end']) * 5
                    + bool(truth.get('account') and truth['account'] in _digits(read.get('account'))) * 5
                    + bool(truth.get('share') and truth['share'] in (read.get('account') or '')) * 5)
        pairs = sorted(((fit(i, t), n, t['id']) for n, i in enumerate(items) for t in candidates), reverse=True)
        taken, assignment = set(), {}
        for score, n, truth_id in pairs:
            if score < 5 or n in assignment or truth_id in taken:
                continue
            assignment[n] = truth_id
            taken.add(truth_id)
        for n, item in enumerate(items):
            new, old = assignment.get(n), item['truth_id']
            if new is None and (old is None or old not in taken):
                continue  # no confident pairing: keep the run's own
            if new == old:
                continue
            changed += 1
            item['truth_id'] = new
            item.pop('proposal_checks', None)
            item.pop('correction', None)
            if new is None:
                item.update(family='unmatched', expected=None, defects=[], scored=True)
    return changed


def rescore(out, corpus):
    """Re-judge a finished run against the corpus manifest as it is now, using the run's own database.

    For truth corrections (a convention fixed, a period re-verified) without
    re-reading every document. Batch outcomes, proposal checks and simulated
    corrections are the original run's; the ledger comparison and all metrics
    are recomputed. Writes results-rescored.json and summary-rescored.md.
    """
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import sessionmaker
    from postgres.models.financial import FinancialTransaction, FinancialAccount
    from postgres.models.financial_import_batches import FinancialImportBatchItem
    _load_models()
    manifest = json.loads((corpus / 'manifest.json').read_text())
    result = json.loads((out / 'results.json').read_text())
    truths = {p['id']: dict(p, filename=f['filename']) for f in manifest['files'] for p in f['periods']}
    rematched = _rematch(result['periods'], truths)
    for period in result['periods']:
        truth = truths.get(period['truth_id']) if period['truth_id'] else None
        if truth is not None:
            period.update(scored=_scored(truth), expected=truth['expected'], family=truth['family'],
                          defects=truth['defects'])
        elif period['truth_id']:
            period.update(scored=False, expected=None)
    engine = create_engine(f"sqlite+pysqlite:///{out / 'benchmark.db'}", future=True)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    with factory() as db:
        final_items = {str(item.id): dict(status=item.status, source_document_id=(item.summary or {}).get('source_document_id'))
                       for item in db.scalars(select(FinancialImportBatchItem))}
        result['ledger'] = verify_ledger(db, result['periods'], final_items, truths, FinancialTransaction,
                                         FinancialAccount, select, _incomplete(manifest))
    engine.dispose()
    result['corpus'].update(periods=len(truths), path=str(corpus))
    result['rescored'] = dict(at=datetime.now(timezone.utc).isoformat(timespec='seconds'), code=_git('rev-parse', 'HEAD'),
                              scored_truth=sorted(SCORED_TRUTH), rematched_items=rematched)
    result['metrics'] = metrics(result)
    (out / 'results-rescored.json').write_text(json.dumps(result, indent=1, default=str) + '\n')
    text = render_summary(result).replace('# Statement automation benchmark', '# Statement automation benchmark (rescored)', 1)
    text += ('\nRescored ' + result['rescored']['at'] + ' at code ' + result['rescored']['code'][:10] +
             ' against the current manifest: ledger comparison and metrics recomputed; batch outcomes, proposal '
             'checks and simulated corrections are from the original run (dropped for the '
             + str(rematched) + ' items whose truth pairing changed).\n')
    (out / 'summary-rescored.md').write_text(text)
    return result


def proposal_field_errors(proposal, truth):
    """Critical fields as proposed before any human action (no edits applied)."""
    errors = Counter()
    pairs, missing = _match_rows(_payment_rows(proposal), truth['rows'], by_value=truth.get('added_in') == 'real')
    for row in _payment_rows(proposal):
        index = pairs.get(row['id'])
        if index is None:
            errors['extra_row'] += 1
            continue
        expected, fields = truth['rows'][index], row['fields']
        if fields.get('amount_minor') not in (None, '') and fields['amount_minor'] != str(expected['amount_minor']):
            errors['amount_wrong'] += 1
        elif fields.get('amount_minor') in (None, ''):
            errors['amount_missing'] += 1
        if fields.get('direction') and fields['direction'] != expected['direction']:
            errors['direction_wrong'] += 1
        if fields.get('date') and not _same_date(expected['date'], fields['date']):
            errors['date_wrong'] += 1
        elif not fields.get('date') and expected['date'] is not None:
            errors['date_missing'] += 1
    errors['missing_row'] += len(missing)
    if proposal.get('currency') and proposal['currency'] != truth['currency']:
        errors['currency_wrong'] += 1
    account = _digits(proposal['metadata'].get('account_number'))
    if account and truth['account'] not in account:
        errors['account_wrong'] += 1
    return {k: v for k, v in errors.items() if v}


def verify_ledger(db, periods, final_items, truths, Transaction, Account, select, incomplete_files=()):
    """Compare every saved transaction with the period it was admitted from.

    ``incomplete_files``: real documents whose truth did not find or verify every
    statement; an admitted item there that matches no truth period is counted
    as admitted-unscored, not as a wrong admission.
    """
    report = dict(admitted_periods=0, transactions=0, critical_errors=Counter(), wrongly_admitted=[],
                  duplicate_contributions=0, by_period={})
    seen = Counter()
    for period in periods:
        item = final_items.get(period['item_id']) if period['item_id'] else None
        period['final_status'] = item['status'] if item else period['status']
        if not item or item['status'] != 'imported' or not item.get('source_document_id'):
            continue
        report['admitted_periods'] += 1
        rows = list(db.scalars(select(Transaction).where(
            Transaction.source_document_id == uuid.UUID(item['source_document_id']))))
        truth = truths.get(period['truth_id'])
        if truth is None and period.get('filename') in incomplete_files:
            report['admitted_unscored'] = report.get('admitted_unscored', 0) + 1
            continue
        if truth is not None and not _scored(truth):
            # The truth for this period did not reconcile, so its saved rows
            # cannot be judged; they are counted, not scored.
            report['admitted_unscored'] = report.get('admitted_unscored', 0) + 1
            continue
        canonical = truth.get('duplicate_of') if truth else None
        errors = Counter()
        if truth is None:
            errors['unmatched_period'] += 1
            expected = []
        else:
            expected = [dict(r) for r in truth['rows']]
        remaining = list(expected)
        for row in rows:
            account = db.get(Account, row.account_id)
            # The printed transaction date is the truth ``date``. A layout that
            # also prints a posting date carries it as ``posted_date`` (v4);
            # before v4 every posting date equalled the transaction date.
            identity = (row.amount_minor, row.direction, row.currency, row.transaction_date or row.posted_date)
            key = (truth['family'] if truth else '', truth['account'] if truth else '', row.amount_minor, row.direction,
                   str(row.transaction_date or row.posted_date))
            seen[key] += 1
            recorded = str(identity[3]) if identity[3] is not None else None
            match = next((r for r in remaining if r['amount_minor'] == row.amount_minor and r['direction'] == row.direction
                          and _same_date(r['date'], recorded)), None)
            if match is not None:
                remaining.remove(match)
                if match.get('posted_date') and str(row.posted_date) != match['posted_date']:
                    errors['posted_date'] += 1
            else:
                near = next((r for r in remaining if _norm(r['description']) in _norm(row.description)), None)
                if near is None:
                    errors['unexpected_transaction'] += 1
                else:
                    remaining.remove(near)
                    if near['amount_minor'] != row.amount_minor:
                        errors['amount'] += 1
                    if near['direction'] != row.direction:
                        errors['direction'] += 1
                    if not _same_date(near['date'], recorded):
                        errors['date'] += 1
            if truth and row.currency != truth['currency']:
                errors['currency'] += 1
            if truth and truth['account'] not in _digits(account.identifier_normalised or account.identifier_as_printed):
                errors['account'] += 1
        errors['missing_transaction'] += len(remaining)
        errors = Counter({k: v for k, v in errors.items() if v})
        report['transactions'] += len(rows)
        report['by_period'][period['truth_id'] or period['item_id']] = dict(saved=len(rows), errors=dict(errors))
        report['critical_errors'].update(errors)
        if errors or (truth and truth['expected'] in HELD):
            report['wrongly_admitted'].append(dict(period=period['truth_id'], expected=truth['expected'] if truth else None,
                                                   errors=dict(errors)))
    report['duplicate_contributions'] = sum(count - 1 for count in seen.values() if count > 1)
    report['critical_errors'] = dict(report['critical_errors'])
    return report


ACTION_COST = dict(edit=1, decision=1, add_row=2)  # add_row: enter values + choose its place
# Outcomes that must never reach the ledger: a period the source cannot
# complete (``hold``) and a document that is not a statement (``not_statement``,
# e.g. a teller receipt uploaded with statements). Admitting either is wrong.
HELD = ('hold', 'not_statement')
GROUPABLE = ('holder', 'account', 'institution', 'currency', 'period_start_unprinted')


def _groupable(action):
    """Decisions the batch can apply once across matching periods today."""
    if action['field'] in GROUPABLE:
        return 'dates' if action['field'] == 'period_start_unprinted' else action['field']
    if action['field'] == 'period_end' and action['detail'] == 'recognised_closing':
        return 'dates'  # filled by the grouped unprinted-start decision
    if action['field'] == 'confirm_no_activity':
        return 'no_activity'  # the grouped "confirm no activity" decision
    return None


def _period_effort(p):
    """(per-period actions, non-groupable actions, groupable keys, fixable)."""
    if p['can_import'] or p['status'] == 'duplicate_ignored':
        return 0, 0, set(), True
    if p['expected'] in HELD + ('duplicate',):
        return 2, 2, set(), True  # open the statement + record hold / leave unimported
    correction = p.get('correction')
    if correction is None:
        return 1, 1, set(), False
    individual = [a for a in correction['actions'] if _groupable(a) is None]
    keys = {(p['family'], _groupable(a)) for a in correction['actions'] if _groupable(a)}
    total = 1 + sum(ACTION_COST[a['kind']] for a in correction['actions'])
    remaining = (1 + sum(ACTION_COST[a['kind']] for a in individual)) if individual else 0
    return total, remaining, keys, correction['resolved']


def metrics(result):
    everything = result['periods']
    periods = [p for p in everything if p.get('scored', True)]
    unscored = [p for p in everything if not p.get('scored', True)]
    families = sorted({p['family'] for p in periods})

    def block(subset):
        # A batch item matched to no ground-truth period (for example one
        # unclassified item covering a whole multi-period PDF) is reported
        # separately; the periods it failed to present count as not detected.
        unique = [p for p in subset if p['expected'] not in ('duplicate', None)]
        unmatched_items = [p for p in subset if p['expected'] is None]
        copies = [p for p in subset if p['expected'] == 'duplicate']
        total = len(unique)
        ready = [p for p in unique if p['can_import']]
        auto = [p for p in unique if p['expected'] == 'auto']
        auto_ready = [p for p in auto if p['can_import']]
        histogram = Counter()
        for p in unique:
            if not p['can_import']:
                histogram.update(p['reasons'].keys() or ['unexplained'])
        actions = grouped = unresolved = edits = decisions = added = 0
        keys = set()
        for p in subset:
            total_actions, individual, group_keys, fixable = _period_effort(p)
            actions += total_actions
            grouped += individual
            keys |= group_keys
            unresolved += 0 if fixable else 1
            for a in p.get('correction', {}).get('actions', []) if not p['can_import'] else []:
                edits += a['kind'] == 'edit'
                decisions += a['kind'] == 'decision'
                added += a['kind'] == 'add_row'
        proposal_errors, wrong_values = Counter(), Counter()
        for p in ready:
            proposal_errors.update(p.get('proposal_checks') or {})
        for p in unique:
            wrong_values.update({k: v for k, v in (p.get('proposal_checks') or {}).items() if k.endswith('_wrong')})
        return dict(periods=total, ready_without_edits=len(ready),
                    ready_without_edits_pct=round(100 * len(ready) / total, 1) if total else None,
                    clean_ready=sum(p['status'] == 'ready' and p['can_import'] for p in unique),
                    recoverable_periods=len(auto), recoverable_ready=len(auto_ready),
                    recoverable_ready_pct=round(100 * len(auto_ready) / len(auto), 1) if auto else None,
                    decision_periods=sum(p['expected'] == 'decision' for p in unique),
                    hold_periods=sum(p['expected'] in HELD for p in unique),
                    holds_kept=sum(p['expected'] in HELD and not p['can_import'] for p in unique),
                    duplicate_copies=len(copies),
                    duplicate_copies_held_automatically=sum(p['status'] == 'duplicate_ignored' for p in copies),
                    duplicate_copies_offered_for_import=sum(p['can_import'] for p in copies),
                    blocked=total - len(ready), blocking_reasons=dict(histogram.most_common()),
                    human_actions_per_period=actions, human_actions_grouped=grouped + len(keys),
                    shared_decisions=sorted('/'.join(k) for k in keys),
                    field_edits=edits, decisions=decisions, rows_to_add=added,
                    blocked_not_fixable_by_field_edits=unresolved,
                    proposal_critical_errors_in_ready_periods=dict(proposal_errors),
                    valid_but_wrong_values_proposed=dict(wrong_values),
                    wrongly_ready=[p['truth_id'] for p in unique if p['can_import'] and p['expected'] in HELD],
                    unmatched_items=len(unmatched_items),
                    unmatched_items_offered_for_import=sum(p['can_import'] for p in unmatched_items))
    defects = sorted({d for p in periods for d in p['defects']} | {'(none)'})
    subsets = sorted({p.get('added_in') or 'unmatched' for p in periods})
    return dict(overall=block(periods), unscored=dict(periods=len(unscored),
                    offered_for_import=sum(p['can_import'] for p in unscored),
                    by_status=dict(Counter(p['status'] for p in unscored))),
                by_family={f: block([p for p in periods if p['family'] == f]) for f in families},
                by_defect={d: block([p for p in periods if d in p['defects'] or (d == '(none)' and not p['defects'])])
                           for d in defects},
                by_corpus_version={v: block([p for p in periods if (p.get('added_in') or 'unmatched') == v])
                                   for v in subsets},
                by_expected={e: block([p for p in periods if (p['expected'] or 'unmatched') == e])
                             for e in sorted({p['expected'] or 'unmatched' for p in periods})})


def render_summary(result):
    m = result['metrics']
    o = m['overall']
    ledger = result['ledger']
    lines = [f"# Statement automation benchmark — {result['generated_at']}", '',
             f"Code {result['code']['commit'][:10]}{' (uncommitted changes)' if result['code']['dirty'] else ''}; "
             f"corpus {result['corpus']['version']}: {result['corpus']['files']} PDFs, {result['corpus']['periods']} periods "
             f"({o['periods']} distinct + {o['duplicate_copies']} exact copies).", '',
             f"**Ready without any human edit: {o['ready_without_edits']} of {o['periods']} distinct periods "
             f"({o['ready_without_edits_pct']}%).** Recoverable periods (source establishes every fact) ready: "
             f"{o['recoverable_ready']} of {o['recoverable_periods']} ({o['recoverable_ready_pct']}%). "
             f"The other {o['decision_periods']} need a genuine decision and {o['hold_periods']} must stay held.", '',
             f"Safety: wrongly admitted periods {len(ledger['wrongly_admitted'])}; critical-field errors in saved "
             f"transactions {sum(ledger['critical_errors'].values())} ({ledger['transactions']} saved from "
             f"{ledger['admitted_periods']} periods); duplicate ledger contributions {ledger['duplicate_contributions']}; "
             f"held periods kept out {o['holds_kept']}/{o['hold_periods']}; exact copies held automatically "
             f"{o['duplicate_copies_held_automatically']}/{o['duplicate_copies']}. Valid-looking but wrong values "
             f"proposed before review (any period): {sum(o['valid_but_wrong_values_proposed'].values())}. Batch items "
             f"matched to no ground-truth period: {o['unmatched_items']} ({o['unmatched_items_offered_for_import']} "
             f"offered for import).", '',
             *([f"Real corpus: only periods whose truth reconciled are scored. Unscored truth periods matched or "
                f"listed: {m['unscored']['periods']} ({m['unscored']['offered_for_import']} offered for import; "
                f"{ledger.get('admitted_unscored', 0)} admitted, not judged).", '']
               if m.get('unscored', {}).get('periods') or ledger.get('admitted_unscored') else []),
             f"Human actions to make every blocked period ready or decided: {o['human_actions_per_period']} "
             f"one statement at a time; {o['human_actions_grouped']} using today's grouped decisions "
             f"({', '.join(o['shared_decisions']) or 'none'}). Field edits {o['field_edits']}, decisions {o['decisions']}, "
             f"rows to add {o['rows_to_add']}. Blocked periods not fixable by field edits: "
             f"{o['blocked_not_fixable_by_field_edits']}.", '',
             '| Family | Distinct periods | Ready w/o edits | Recoverable ready | Actions (single / grouped) | Blocking reasons |',
             '|---|---|---|---|---|---|']
    for family, f in m['by_family'].items():
        reasons = ', '.join(f'{k} {v}' for k, v in f['blocking_reasons'].items()) or '—'
        lines.append(f"| {family} | {f['periods']} | {f['ready_without_edits']} ({f['ready_without_edits_pct']}%) | "
                     f"{f['recoverable_ready']}/{f['recoverable_periods']} | {f['human_actions_per_period']} / "
                     f"{f['human_actions_grouped']} | {reasons} |")
    def short(block):
        return (f"{block['ready_without_edits']}/{block['periods']} ({block['ready_without_edits_pct']}%) | "
                f"{block['recoverable_ready']}/{block['recoverable_periods']} | {block['holds_kept']}/{block['hold_periods']} | "
                f"{', '.join(f'{k} {v}' for k, v in block['blocking_reasons'].items()) or '—'} |")
    lines += ['', '| Corpus subset | Ready w/o edits | Recoverable ready | Held kept out | Blocking reasons |',
              '|---|---|---|---|---|']
    lines += [f"| {name} | {short(block)}" for name, block in m.get('by_corpus_version', {}).items()]
    lines += ['', '| Defect / damage type | Ready w/o edits | Recoverable ready | Held kept out | Blocking reasons |',
              '|---|---|---|---|---|']
    lines += [f"| {name} | {short(block)}" for name, block in m.get('by_defect', {}).items()]
    lines += ['', '| Period | Expected | Defects | Batch status | Importable | Blocking reasons | Simulated actions |',
              '|---|---|---|---|---|---|---|']
    for p in sorted(result['periods'], key=lambda p: p['truth_id'] or ''):
        if not p.get('scored', True):
            continue
        correction = p.get('correction')
        acted = ''
        if correction and not p['can_import'] and p['status'] != 'duplicate_ignored':
            acted = ', '.join(a['field'] for a in correction['actions']) or 'none'
            acted += '' if correction['resolved'] else ' (still blocked)'
        lines.append(f"| {p['truth_id']} | {p['expected']} | {', '.join(p['defects']) or '—'} | {p['status']} | "
                     f"{'yes' if p['can_import'] else 'no'} | {', '.join(f'{k} {v}' for k, v in p['reasons'].items()) or '—'} | {acted} |")
    t = result['timing']
    reread = {k: v for k, v in result['repairs'].items() if v['quality_reread'] or v['full_page_ocr']}
    lines += ['', 'Automatic reading repair: ' + ('; '.join(
        f"{k}: {v['quality_reread']} quality reread, {v['full_page_ocr']} full-page OCR, "
        f"{', '.join(f'{a} {b}' for a, b in v['refinements'].items()) or 'no refinement records'}"
        for k, v in reread.items()) or 'none triggered') + '.', '',
        f"Timing: engine reading {t['engine_read_wall_seconds']:.1f}s wall ({t['engine_read_cpu_seconds']:.1f}s CPU "
        f"incl. children); batch preparation {t['preparation']['seconds']:.1f}s over {t['preparation']['turns']} "
        f"worker turns; batch status read {t['batch_status_seconds']:.2f}s; group import "
        f"{t['group_import']['seconds']:.1f}s; total {t['total_wall_seconds']:.1f}s. Host: "
        f"{result['environment']['cpus']} CPUs, 1-minute load {result['environment']['load_average_before'][0]:.1f} "
        f"before reading and {result['environment']['load_average_after'][0]:.1f} after (timings are not comparable "
        f"across hosts or loads).", '']
    return '\n'.join(lines)


def _git(*args):
    try:
        return subprocess.run(['git', '-C', str(REPO), *args], capture_output=True, text=True).stdout.strip()
    except OSError:
        return ''


def _tesseract():
    try:
        return subprocess.run(['tesseract', '--version'], capture_output=True, text=True).stdout.splitlines()[0]
    except (OSError, IndexError):
        return 'unavailable'


def main(argv=None):
    parser = argparse.ArgumentParser(description='Fresh-upload statement automation benchmark (synthetic corpus).')
    parser.add_argument('--out', help='Run directory (default: a new temporary directory).')
    parser.add_argument('--engine-python', default=sys.executable,
                        help='Interpreter with the evidence engine dependencies (default: this one).')
    parser.add_argument('--concurrency', type=int, default=2)
    parser.add_argument('--corpus', default=str(CORPUS),
                        help='Corpus directory with manifest.json (default: the committed corpus).')
    parser.add_argument('--rescore', action='store_true',
                        help='re-judge the finished run in --out against the current --corpus manifest (no re-reading)')
    parser.add_argument('--score', default='verified',
                        help='comma-separated real truth statuses to score (default: verified)')
    args = parser.parse_args(argv)
    SCORED_TRUTH.clear()
    SCORED_TRUTH.update(s.strip() for s in args.score.split(',') if s.strip())
    if args.rescore:
        if not args.out:
            parser.error('--rescore needs --out (the finished run directory)')
        result = rescore(Path(args.out), Path(args.corpus))
        print((Path(args.out) / 'summary-rescored.md').read_text())
        return 0 if not result['ledger']['wrongly_admitted'] else 1
    out = Path(args.out) if args.out else Path(os.environ.get('TMPDIR', '/tmp')) / (
        f"loupe-statement-benchmark-{os.environ.get('USER') or os.getuid()}-{datetime.now():%Y%m%d-%H%M%S}")
    result = run(out, args.engine_python, args.concurrency, Path(args.corpus))
    print((out / 'summary.md').read_text())
    print(f'Full results: {out / "results.json"}')
    return 0 if not result['ledger']['wrongly_admitted'] else 1


if __name__ == '__main__':
    sys.exit(main())
