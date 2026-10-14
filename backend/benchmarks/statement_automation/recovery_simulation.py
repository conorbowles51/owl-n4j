"""Measure reader recovery and the misread audit on a case read by an older engine.

Live statements were read by earlier engine revisions. This builds a
disposable "live" case from the synthetic corpus read with an OLDER engine
checkout (default: the 29 Sept Andrews-crop engine, bb3ccef3), prepares one
batch with the current backend, imports everything that batch offers (as an
investigator clicking Import all would), and then runs, against that case:

1. the reader recovery campaign's selection rules;
2. the dry-run estimator (re-read with the CURRENT engine, scratch batches);
3. the admitted-ledger misread audit;

and scores the admissions and the audit against the corpus ground truth.

    python -m benchmarks.statement_automation.recovery_simulation --old-root DIR --out DIR

DIR for --old-root holds ``evidence-engine/`` (``git archive <rev> evidence-engine``)
and ``backend/benchmarks/statement_automation/engine_read.py`` (a copy of the
current one). Writes only under --out.
"""
import argparse
import asyncio
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import time
import uuid
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parents[1]
CORPUS = HERE / 'corpus'


def _script(name):
    spec = importlib.util.spec_from_file_location(name, BACKEND / 'scripts' / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def old_readings(old_root, paths, out, python, concurrency):
    target = out / 'old-readings.json'
    completed = subprocess.run([python, str(Path(old_root) / 'backend/benchmarks/statement_automation/engine_read.py'),
        str(target), str(concurrency), *map(str, paths)], capture_output=True, text=True,
        env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
    (out / 'old-read.log').write_text(completed.stdout + completed.stderr)
    if completed.returncode != 0:
        raise RuntimeError('Old engine reading failed; see old-read.log')
    return {Path(path).name: value for path, value in json.loads(target.read_text())['readings'].items()}


def build_live(out, manifest, readings):
    from benchmarks.statement_automation.harness import _database
    from postgres.models.case import Case
    from postgres.models.enums import GlobalRole
    from postgres.models.evidence import EvidenceDocumentText, EvidenceFile, EvidenceFolder, EvidenceTableGeometry
    from postgres.models.user import User
    from services.evidence_db_storage import EvidenceDBStorage
    from services.financial import import_batches as batches
    from services.financial.decisions import Actor
    engine, factory, _ = _database(out / 'live.db')
    sources = out / 'sources'
    with factory() as db:
        user = User(id=uuid.uuid4(), email='simulation@example.test', name='Simulated investigator',
            password_hash='not-used', global_role=GlobalRole.user, is_active=True)
        case = Case(id=uuid.uuid4(), title='Older-engine live case', created_by_user_id=user.id, owner_user_id=user.id)
        folder = EvidenceFolder(id=uuid.uuid4(), case_id=case.id, name='Statements')
        db.add_all([user, case, folder])
        db.commit()
        EvidenceDBStorage.add_files(db, case.id, [dict(original_filename=f['filename'],
            stored_path=str(sources / f['filename']), sha256=f['sha256'], size=f['size']) for f in manifest['files']],
            folder_id=folder.id, created_by_id=user.id)
        db.commit()
        case_id, folder_id, actor = case.id, folder.id, Actor(user.name, user.email, user.id)

    async def process_files(session, *, case_id, file_ids, preparation_mode, force_reprocess, requested_by_user_id):
        jobs = []
        for file_id in file_ids:
            record = session.get(EvidenceFile, file_id)
            reading = readings[Path(record.stored_path).name]
            job = uuid.uuid4()
            if 'error' in reading:
                record.status, record.last_error = 'failed', reading['error']
            else:
                session.add(EvidenceDocumentText(evidence_file_id=file_id, engine_job_id=job, content=reading['content'],
                    content_sha256=reading['content_sha256'], character_count=reading['character_count'],
                    source_locations=reading['source_locations'], processing_manifest=reading['processing_manifest']))
                for page, entries in reading['geometry'].items():
                    session.add(EvidenceTableGeometry(evidence_file_id=file_id, page_number=int(page), engine_job_id=job, payload=entries))
                record.status, record.engine_job_id = 'processed', str(job)
            jobs.append(str(job))
        session.commit()
        return dict(job_ids=jobs)

    with factory() as db:
        batch_id = batches.create_batch(db, case_id=case_id, request_id=uuid.uuid4(), file_ids=[],
            folder_ids=[folder_id], actor=actor)

    def drain():
        for _ in range(400):
            asyncio.run(batches.advance_batch(factory, batch_id, Path, process_files))
            with factory() as db:
                if batches.batch_for(db, case_id, batch_id).status != 'preparing':
                    return
    drain()
    with factory() as db:
        status = batches.batch_status(db, case_id=case_id, batch_id=batch_id, limit=100_000)
    if status['available_statements']:
        with factory() as db:
            batches.queue_import(db, case_id=case_id, batch_id=batch_id, expected_revision=status['ready_revision'], actor=actor)
        drain()
    with factory() as db:
        final = batches.batch_status(db, case_id=case_id, batch_id=batch_id, limit=100_000)
    return engine, factory, case_id, dict(prepared=status['counts'], final=final['counts'])


def run_campaign(factory, case_id, out, python, concurrency):
    """Run the real campaign: snapshot, hand-off, batch re-read with the current engine, Import all."""
    from sqlalchemy import select
    from postgres.models.evidence import EvidenceDocumentText, EvidenceFile, EvidenceTableGeometry
    from postgres.models.financial_import_batches import FinancialImportBatch as Batch
    from postgres.models.financial_recovery import FinancialRecoveryItem as Item, FinancialRecoveryRun as Run
    from services.financial import deployment_recovery as recovery, import_batches as batches
    from services.financial.decisions import Actor
    from services.financial.recovery_campaigns import READER_RECOVERY
    with factory() as db:
        cutoff = recovery.activate(db, READER_RECOVERY.release)
        recovery.snapshot_case(db, case_id, cutoff, READER_RECOVERY)
        run = db.scalar(select(Run).where(Run.case_id == case_id, Run.release == READER_RECOVERY.release))
        items = list(db.scalars(select(Item.id).where(Item.run_id == run.id)))
        selected = {Path(db.get(EvidenceFile, item.file_id).stored_path).name: Path(db.get(EvidenceFile, item.file_id).stored_path)
                    for item in db.scalars(select(Item).where(Item.run_id == run.id))}
    estimator = _script('financial_reader_recovery_estimate')
    scratch = out / 'campaign-reads'
    scratch.mkdir(exist_ok=True)
    readings = estimator.engine_reread(selected, scratch, python, concurrency) if selected else {}
    for item_id in items:
        recovery.recover_one(factory, item_id, Path)

    async def process_files(session, *, case_id, file_ids, preparation_mode, force_reprocess, requested_by_user_id):
        jobs = []
        for file_id in file_ids:
            record = session.get(EvidenceFile, file_id)
            parent = session.get(EvidenceFile, uuid.UUID(record.metadata_['statement_parent_evidence_id']))
            reading = readings[Path(parent.stored_path).name]
            job = uuid.uuid4()
            if 'error' in reading:
                record.status, record.last_error = 'failed', reading['error']
            else:
                session.add(EvidenceDocumentText(evidence_file_id=file_id, engine_job_id=job, content=reading['content'],
                    content_sha256=reading['content_sha256'], character_count=reading['character_count'],
                    source_locations=reading['source_locations'], processing_manifest=reading['processing_manifest']))
                for page, entries in reading['geometry'].items():
                    session.add(EvidenceTableGeometry(evidence_file_id=file_id, page_number=int(page), engine_job_id=job, payload=entries))
                record.status, record.engine_job_id = 'processed', str(job)
            jobs.append(str(job))
        session.commit()
        return dict(job_ids=jobs)

    with factory() as db:
        batch_ids = list(db.scalars(select(Batch.id).where(Batch.case_id == case_id)))
    for batch_id in batch_ids:
        for _ in range(400):
            asyncio.run(batches.advance_batch(factory, batch_id, Path, process_files))
            with factory() as db:
                if batches.batch_for(db, case_id, batch_id).status != 'preparing':
                    break
    for item_id in items:
        recovery.recover_one(factory, item_id, Path)
    with factory() as db:
        outcomes = Counter(db.scalars(select(Item.status).where(Item.run_id == run.id)))
        periods = Counter()
        for item in db.scalars(select(Item).where(Item.run_id == run.id)):
            periods.update(item.result.get('periods') or {})
    imported = Counter()
    for batch_id in batch_ids:
        with factory() as db:
            status = batches.batch_status(db, case_id=case_id, batch_id=batch_id, limit=100_000)
            batch = batches.batch_for(db, case_id, batch_id)
            actor = Actor(**{**batch.actor, 'user_id': uuid.UUID(batch.actor['user_id'])})
        if status['available_statements']:
            with factory() as db:
                imported['queued'] += batches.queue_import(db, case_id=case_id, batch_id=batch_id,
                    expected_revision=status['ready_revision'], actor=actor)['queued']
            for _ in range(400):
                asyncio.run(batches.advance_batch(factory, batch_id, Path, process_files))
                with factory() as db:
                    if batches.batch_for(db, case_id, batch_id).status != 'preparing':
                        break
    return dict(scheduled=len(items), outcomes=dict(outcomes), new_reading_periods=dict(periods), import_all=dict(imported))


def admitted_truth(factory, case_id, manifest):
    """Which admitted statement reviews hold a value that differs from the printed truth."""
    from sqlalchemy import select
    from postgres.models.evidence import EvidenceFile
    from postgres.models.financial import FinancialSourceDocument, FinancialTransaction
    truths = defaultdict(list)
    for file in manifest['files']:
        for period in file['periods']:
            truths[file['filename']].append(period)
    verdicts = {}
    with factory() as db:
        for document in db.scalars(select(FinancialSourceDocument).where(FinancialSourceDocument.case_id == case_id,
                FinancialSourceDocument.status == 'admitted', FinancialSourceDocument.document_type == 'statement_review')):
            file = db.get(EvidenceFile, document.evidence_file_id)
            request = document.metadata_['statement_import_request']
            candidates = [p for p in truths[file.original_filename]
                if (p.get('period_start'), p.get('period_end')) == (request.get('period_start'), request.get('period_end'))]
            if not candidates:
                verdicts[str(document.id)] = dict(file=file.original_filename, truth='unmatched')
                continue
            saved = Counter((str(t.transaction_date or t.posted_date or t.value_date or t.effective_date), abs(int(t.amount_minor)), getattr(t.direction, 'value', t.direction))
                for t in db.scalars(select(FinancialTransaction).where(FinancialTransaction.source_document_id == document.id)))
            # Several periods can share dates (two shares of one Andrews
            # statement): the admission is correct if it equals one of them.
            match = next((p for p in candidates if saved == Counter((r['date'], int(r['amount_minor']), r['direction'])
                for r in p['rows'])), None)
            verdicts[str(document.id)] = dict(file=file.original_filename, period=(match or candidates[0])['id'],
                truth='correct' if match else 'wrong')
    return verdicts


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--old-root', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--engine-python', default=sys.executable)
    parser.add_argument('--concurrency', type=int, default=2)
    parser.add_argument('--only', default='', help='comma-separated filename prefixes (default: whole corpus)')
    args = parser.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((CORPUS / 'manifest.json').read_text())
    if args.only:
        prefixes = tuple(args.only.split(','))
        manifest['files'] = [f for f in manifest['files'] if f['filename'].startswith(prefixes)]
    (args.out / 'sources').mkdir(exist_ok=True)
    for record in manifest['files']:
        data = (CORPUS / record['filename']).read_bytes()
        assert hashlib.sha256(data).hexdigest() == record['sha256'], record['filename']
        (args.out / 'sources' / record['filename']).write_bytes(data)
    started = time.monotonic()
    readings = old_readings(args.old_root, [args.out / 'sources' / f['filename'] for f in manifest['files']],
        args.out, args.engine_python, args.concurrency)
    old_seconds = time.monotonic() - started
    engine, factory, case_id, counts = build_live(args.out, manifest, readings)
    verdicts = admitted_truth(factory, case_id, manifest)
    estimator = _script('financial_reader_recovery_estimate')
    started = time.monotonic()
    estimate = estimator.estimate(factory, case_id, python=args.engine_python, concurrency=args.concurrency,
        scratch_root=args.out / 'scratch', resolve_path=Path)
    estimate_seconds = time.monotonic() - started
    misread = _script('financial_ledger_misread_audit')
    started = time.monotonic()
    audit = misread.audit(factory, case_id, python=args.engine_python, concurrency=args.concurrency,
        scratch_root=args.out / 'scratch', resolve_path=Path)
    audit_seconds = time.monotonic() - started
    started = time.monotonic()
    campaign = run_campaign(factory, case_id, args.out, args.engine_python, args.concurrency)
    campaign['seconds'] = time.monotonic() - started
    after = admitted_truth(factory, case_id, manifest)
    new_admissions = {key: value for key, value in after.items() if key not in verdicts}
    campaign['new_admissions'] = len(new_admissions)
    campaign['new_admissions_by_truth'] = dict(Counter(value['truth'] for value in new_admissions.values()))
    campaign['new_admissions_detail'] = new_admissions
    outcome = {period['source_document_id']: period['outcome'] for period in audit['periods']}
    scored = Counter()
    for document_id, verdict in verdicts.items():
        result = outcome.get(document_id, 'not_audited')
        scored[f"{verdict['truth']}:{result}"] += 1
        verdict['audit'] = result
    result = dict(old_engine=str(args.old_root), files=len(manifest['files']),
        periods=sum(len(f['periods']) for f in manifest['files']), old_read_seconds=old_seconds,
        live_counts=counts, admitted=len(verdicts), admitted_wrong=sum(v['truth'] == 'wrong' for v in verdicts.values()),
        audit_vs_truth=dict(scored), admitted_detail=verdicts, estimate=estimate, estimate_seconds=estimate_seconds,
        audit=audit, audit_seconds=audit_seconds, campaign=campaign)
    (args.out / 'simulation.json').write_text(json.dumps(result, indent=1, sort_keys=True, default=str) + '\n')
    summary = ['# Reader recovery simulation', '', f"Old engine: {args.old_root}; files {result['files']}, periods {result['periods']}.",
        f"Live batch after Import all: {counts['final']}.",
        f"Admitted statement reviews: {result['admitted']}, of which wrong against the printed truth: {result['admitted_wrong']}.",
        f"Audit vs truth (truth:audit): {dict(scored)}.",
        f"Campaign run (real hand-off, current engine re-read, Import all): scheduled {campaign['scheduled']}, "
        f"outcomes {campaign['outcomes']}, periods of the new readings {campaign['new_reading_periods']}, "
        f"newly admitted {campaign['new_admissions']} by truth {campaign['new_admissions_by_truth']}.", '', estimator.render(estimate), '', misread.render(audit)]
    (args.out / 'summary.md').write_text('\n'.join(summary))
    print('\n'.join(summary[:7]))
    engine.dispose()


if __name__ == '__main__':
    sys.path.insert(0, str(BACKEND))
    main()
