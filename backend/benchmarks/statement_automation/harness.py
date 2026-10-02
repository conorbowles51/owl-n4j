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
        if page.get('extraction_method') == 'tesseract_ocr' or reason:
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


def _match_rows(proposal_rows, truth_rows):
    """Pair proposal rows with truth rows by printed description, then order."""
    pairs, unmatched = {}, list(range(len(truth_rows)))
    for row in proposal_rows:
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
    if truth.get('share') and truth['share'] in json.dumps(proposal.get('metadata', {})):
        score += 5
    amounts = Counter(r['fields'].get('amount_minor') for r in _payment_rows(proposal))
    for item in truth['rows']:
        if amounts.get(str(item['amount_minor'])):
            score += 1
    return score


def simulate_correction(proposal, truth, assess, initial_request):
    """Apply ground truth like an investigator; count each action; re-assess."""
    raw = initial_request(proposal)
    actions = []

    def act(kind, field, detail=''):
        actions.append(dict(kind=kind, field=field, detail=detail))

    if not raw.get('currency'):
        raw['currency'] = truth['currency']
        act('decision', 'currency')
    if _norm(raw.get('holder')) != _norm(truth['holder']):
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
        act('edit', 'period_end')
    if truth['start_printed']:
        if raw.get('period_start') != truth['period_start']:
            raw['period_start'] = truth['period_start']
            act('edit', 'period_start')
    elif not raw.get('period_start'):
        raw['period_start_unprinted'] = True
        act('decision', 'period_start_unprinted')
    rows = {r['id']: r for r in raw['rows']}
    payments = _payment_rows(proposal)
    pairs, missing = _match_rows(payments, truth['rows'])
    for original in payments:
        edit = rows[original['id']]
        index = pairs.get(original['id'])
        if index is None:
            edit.update(excluded=True, reason='Not a payment on the printed statement.')
            act('edit', 'exclude_row', original['id'])
            continue
        expected = truth['rows'][index]
        if edit.get('date') != expected['date']:
            edit['date'] = expected['date']
            act('edit', 'row_date', original['id'])
        if edit.get('amount_minor') != str(expected['amount_minor']):
            edit['amount_minor'] = str(expected['amount_minor'])
            act('edit', 'row_amount', original['id'])
        if edit.get('direction') != expected['direction']:
            edit['direction'] = expected['direction']
            act('edit', 'row_direction', original['id'])
        if 'balance_after' in expected and edit.get('balance_minor') not in (None, str(expected['balance_after'])):
            edit['balance_minor'] = str(expected['balance_after'])
            act('edit', 'row_balance', original['id'])
    for index in missing:
        act('add_row', 'missing_row', truth['rows'][index]['description'])
    # Printed opening/closing controls that were misread.
    for original in proposal['rows']:
        description = original['fields'].get('description')
        target = {'Opening Balance': truth['opening_minor'], 'Closing Balance': truth['closing_minor']}.get(description)
        if original['kind'] == 'balance' and target is not None:
            edit = rows.get(original['id'])
            if edit is not None and edit.get('balance_minor') is not None and edit['balance_minor'] != str(target):
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

def run(out, python, concurrency):
    from sqlalchemy import select
    out.mkdir(parents=True, exist_ok=True)
    run_started = time.monotonic()
    manifest = json.loads((CORPUS / 'manifest.json').read_text())
    source_dir = out / 'sources'
    source_dir.mkdir(exist_ok=True)
    corpus_problems = []
    for record in manifest['files']:
        data = (CORPUS / record['filename']).read_bytes()
        if hashlib.sha256(data).hexdigest() != record['sha256']:
            corpus_problems.append(record['filename'])
        (source_dir / record['filename']).write_bytes(data)
    if corpus_problems:
        raise RuntimeError('Corpus files differ from the manifest: ' + ', '.join(corpus_problems))

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

    def drain(label):
        started, turns = time.monotonic(), 0
        while turns < MAX_WORKER_TURNS:
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
            truth = None
            if proposal is not None and candidates:
                truth = max(candidates, key=lambda t: _score(proposal, t, item))
                if len(candidates) > 1 and _score(proposal, truth, item) == 0:
                    truth = None
            elif len(candidates) == 1:
                truth = candidates[0]
            if truth:
                used.add(truth['id'])
            reasons = Counter(review_reason(p) for p in item.get('problems', []))
            if item.get('problem_count', 0) > len(item.get('problems', [])):
                reasons['additional'] += item['problem_count'] - len(item['problems'])
            entry = dict(item_id=item['id'], filename=filename, statement_id=item.get('statement_id'),
                         status=item['status'], can_import=bool(item.get('can_import')),
                         truth_id=truth['id'] if truth else None, family=truth['family'] if truth else 'unmatched',
                         expected=truth['expected'] if truth else None, defects=truth['defects'] if truth else [],
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
            can_import=False, truth_id=truth['id'], family=truth['family'], expected=truth['expected'],
            defects=truth['defects'], reasons={'not_detected': 1}, problems=[], read={}))

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
        ledger = verify_ledger(db, periods, final_items, truths, FinancialTransaction, FinancialAccount, select)

    repairs = {name: repair_summary(r.get('source_locations')) for name, r in readings.items() if 'error' not in r}
    result = dict(
        generated_at=datetime.now(timezone.utc).isoformat(timespec='seconds'),
        corpus=dict(version=manifest['version'], files=len(manifest['files']), periods=len(truths)),
        code=dict(commit=_git('rev-parse', 'HEAD'), dirty=bool(_git('status', '--porcelain', '--', 'backend', 'evidence-engine'))),
        environment=dict(python=sys.version.split()[0], engine_python=python, tesseract=_tesseract(),
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


def proposal_field_errors(proposal, truth):
    """Critical fields as proposed before any human action (no edits applied)."""
    errors = Counter()
    pairs, missing = _match_rows(_payment_rows(proposal), truth['rows'])
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
        if fields.get('date') and fields['date'] != expected['date']:
            errors['date_wrong'] += 1
        elif not fields.get('date'):
            errors['date_missing'] += 1
    errors['missing_row'] += len(missing)
    if proposal.get('currency') and proposal['currency'] != truth['currency']:
        errors['currency_wrong'] += 1
    account = _digits(proposal['metadata'].get('account_number'))
    if account and truth['account'] not in account:
        errors['account_wrong'] += 1
    return {k: v for k, v in errors.items() if v}


def verify_ledger(db, periods, final_items, truths, Transaction, Account, select):
    """Compare every saved transaction with the period it was admitted from."""
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
            identity = (row.amount_minor, row.direction, row.currency, row.posted_date or row.transaction_date)
            key = (truth['family'] if truth else '', truth['account'] if truth else '', row.amount_minor, row.direction,
                   str(row.posted_date or row.transaction_date))
            seen[key] += 1
            match = next((r for r in remaining if r['amount_minor'] == row.amount_minor and r['direction'] == row.direction
                          and str(identity[3]) == r['date']), None)
            if match is not None:
                remaining.remove(match)
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
                    if near['date'] != str(identity[3]):
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
        if errors or (truth and truth['expected'] == 'hold'):
            report['wrongly_admitted'].append(dict(period=period['truth_id'], expected=truth['expected'] if truth else None,
                                                   errors=dict(errors)))
    report['duplicate_contributions'] = sum(count - 1 for count in seen.values() if count > 1)
    report['critical_errors'] = dict(report['critical_errors'])
    return report


ACTION_COST = dict(edit=1, decision=1, add_row=2)  # add_row: enter values + choose its place


def metrics(result):
    periods = result['periods']
    families = sorted({p['family'] for p in periods})

    def block(subset):
        total = len(subset)
        ready = [p for p in subset if p['can_import']]
        auto = [p for p in subset if p['expected'] == 'auto']
        auto_ready = [p for p in auto if p['can_import']]
        histogram = Counter()
        for p in subset:
            if not p['can_import']:
                histogram.update(p['reasons'].keys() or ['unexplained'])
        actions, grouped_keys, unresolved = 0, set(), 0
        per_period_actions = []
        for p in subset:
            if p['can_import']:
                continue
            if p['expected'] in ('hold', 'duplicate'):
                count = 2  # open the statement + record the hold/leave-unimported decision
            elif 'correction' in p:
                count = 1 + sum(ACTION_COST[a['kind']] for a in p['correction']['actions'])
                if not p['correction']['resolved']:
                    unresolved += 1
            else:
                count = 1
                unresolved += 1
            actions += count
            per_period_actions.append(count)
            for a in p.get('correction', {}).get('actions', []):
                if a['field'] in ('holder', 'account', 'institution', 'currency', 'period_start_unprinted'):
                    grouped_keys.add((p['family'], a['field']))
        grouped = actions - sum(1 for p in subset if not p['can_import'] for a in p.get('correction', {}).get('actions', [])
                                if a['field'] in ('holder', 'account', 'institution', 'currency', 'period_start_unprinted')) + len(grouped_keys)
        return dict(periods=total, ready_without_edits=len(ready),
                    ready_without_edits_pct=round(100 * len(ready) / total, 1) if total else None,
                    clean_ready=sum(p['status'] == 'ready' and p['can_import'] for p in subset),
                    recoverable_periods=len(auto), recoverable_ready=len(auto_ready),
                    recoverable_ready_pct=round(100 * len(auto_ready) / len(auto), 1) if auto else None,
                    blocked=total - len(ready), blocking_reasons=dict(histogram.most_common()),
                    human_actions_per_period=actions, human_actions_grouped=grouped,
                    blocked_not_fixable_by_field_edits=unresolved,
                    wrongly_ready=[p['truth_id'] for p in subset if p['can_import'] and p['expected'] in ('hold',)])
    overall = block([p for p in periods if p['family'] != 'unmatched'] + [p for p in periods if p['family'] == 'unmatched'])
    return dict(overall=overall, by_family={f: block([p for p in periods if p['family'] == f]) for f in families},
                by_expected={e: block([p for p in periods if p['expected'] == e])
                             for e in sorted({p['expected'] or 'unmatched' for p in periods})})


def render_summary(result):
    m = result['metrics']
    o = m['overall']
    lines = [f"# Statement automation benchmark — {result['generated_at']}", '',
             f"Code {result['code']['commit'][:10]}{' (uncommitted changes)' if result['code']['dirty'] else ''}; "
             f"corpus {result['corpus']['version']}: {result['corpus']['files']} PDFs, {result['corpus']['periods']} periods.", '',
             f"**Ready without any human edit: {o['ready_without_edits']} of {o['periods']} periods "
             f"({o['ready_without_edits_pct']}%).** Recoverable periods ready: {o['recoverable_ready']} of "
             f"{o['recoverable_periods']} ({o['recoverable_ready_pct']}%).", '',
             f"Wrongly admitted periods: {len(result['ledger']['wrongly_admitted'])}. Critical-field errors in saved "
             f"transactions: {sum(result['ledger']['critical_errors'].values())}. Duplicate ledger contributions: "
             f"{result['ledger']['duplicate_contributions']}.", '',
             f"Estimated human actions to clear blocked periods: {o['human_actions_per_period']} per period, "
             f"{o['human_actions_grouped']} with grouped decisions. Blocked periods not fixable by field edits: "
             f"{o['blocked_not_fixable_by_field_edits']}.", '',
             '| Family | Periods | Ready w/o edits | Recoverable ready | Actions | Top blocking reasons |',
             '|---|---|---|---|---|---|']
    for family, f in m['by_family'].items():
        reasons = ', '.join(f'{k} {v}' for k, v in list(f['blocking_reasons'].items())[:4]) or '—'
        lines.append(f"| {family} | {f['periods']} | {f['ready_without_edits']} ({f['ready_without_edits_pct']}%) | "
                     f"{f['recoverable_ready']}/{f['recoverable_periods']} | {f['human_actions_per_period']} | {reasons} |")
    lines += ['', '| Period | Expected | Defects | Status | Ready | Reasons | Actions (simulated) |', '|---|---|---|---|---|---|---|']
    for p in sorted(result['periods'], key=lambda p: p['truth_id'] or ''):
        correction = p.get('correction')
        acted = ('; '.join(sorted({a['field'] for a in correction['actions']})) + ('' if correction['resolved'] else ' → still blocked')
                 if correction else '')
        lines.append(f"| {p['truth_id']} | {p['expected']} | {', '.join(p['defects']) or '—'} | {p['status']} | "
                     f"{'yes' if p['can_import'] else 'no'} | {', '.join(f'{k} {v}' for k, v in p['reasons'].items()) or '—'} | {acted} |")
    t = result['timing']
    lines += ['', f"Timing: engine reading {t['engine_read_wall_seconds']:.1f}s wall ({t['engine_read_cpu_seconds']:.1f}s CPU); "
              f"batch preparation {t['preparation']['seconds']:.1f}s over {t['preparation']['turns']} worker turns; "
              f"batch status read {t['batch_status_seconds']:.2f}s; group import {t['group_import']['seconds']:.1f}s; "
              f"total {t['total_wall_seconds']:.1f}s.", '']
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
    args = parser.parse_args(argv)
    out = Path(args.out) if args.out else Path(os.environ.get('TMPDIR', '/tmp')) / (
        f"loupe-statement-benchmark-{os.environ.get('USER') or os.getuid()}-{datetime.now():%Y%m%d-%H%M%S}")
    result = run(out, args.engine_python, args.concurrency)
    print((out / 'summary.md').read_text())
    print(f'Full results: {out / "results.json"}')
    return 0 if not result['ledger']['wrongly_admitted'] else 1


if __name__ == '__main__':
    sys.exit(main())
