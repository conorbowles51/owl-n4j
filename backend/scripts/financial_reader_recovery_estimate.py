"""Dry run of the reader recovery campaign for one case. Writes nothing to the case.

What it does, in order:

1. Opens a READ ONLY transaction on the case database (refuses to continue if
   the database does not accept it) and applies the campaign's own selection
   rules (``services.financial.recovery_readers.candidates``) to every batch
   file. Every exclusion is counted by reason.
2. Copies the selected files' retained readings into memory, verifies each
   original's bytes against its evidence hash and re-reads the originals with
   the current evidence-engine code in a separate process (the benchmark's
   ``engine_read.py``), single-threaded OCR.
3. Prepares two disposable SQLite batches in a private scratch directory: one
   from the retained readings, one from the new readings, both with the
   current backend code, and compares how many periods are ready without
   edits, by statement family and blocking reason. The scratch directory is
   deleted at the end.

The report holds counts and reasons only: no names, account numbers, amounts,
file names or ids. From `backend/`, with the service environment loaded:

    OMP_THREAD_LIMIT=1 python3 scripts/financial_reader_recovery_estimate.py --case <uuid> --out DIR
    python3 scripts/financial_reader_recovery_estimate.py --case <uuid> --select-only

Limits: the scratch batches contain only the selected files, so holds that
depend on the rest of the case (overlap with or duplicates of statements
saved elsewhere) are not applied to either side. ``identical_bytes_admitted``
counts selected files whose exact bytes are already admitted elsewhere in the
case; their periods would be held as duplicates live.
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
ENGINE_READ = BACKEND / 'benchmarks/statement_automation/engine_read.py'


class ReadOnlyViolation(RuntimeError):
    pass


def read_only(session):
    """Make the live session refuse every write, at the database and in the ORM."""
    from sqlalchemy import event, text
    if session.get_bind().dialect.name == 'postgresql':
        session.execute(text('SET TRANSACTION READ ONLY'))
        if session.execute(text('SHOW transaction_read_only')).scalar() != 'on':
            raise ReadOnlyViolation('The database did not accept a read-only transaction.')

    @event.listens_for(session, 'before_flush')
    def _refuse(*_args):
        raise ReadOnlyViolation('The dry run attempted a write; nothing was written.')
    return session


def _resolver():
    try:
        from routers.evidence import _resolve_stored_path
        return _resolve_stored_path
    except Exception:  # Outside the service environment: stored paths as recorded.
        return lambda value: Path(value) if value else None


def select_live(session, case_id, resolve_path):
    """Selection plus everything needed to re-read, from one read-only snapshot."""
    from sqlalchemy import select
    from postgres.models.evidence import EvidenceDocumentText, EvidenceFile, EvidenceTableGeometry
    from postgres.models.financial import FinancialSourceDocument
    from postgres.models.financial_import_batches import FinancialImportBatchItem as BatchItem
    from services.financial.batch_review_summary import reason as review_reason
    from services.financial.recovery_campaigns import READER_RECOVERY
    from services.financial.recovery_readers import candidates
    selected, reasons = candidates(session, case_id, READER_RECOVERY)
    admitted_hashes = set(session.scalars(select(EvidenceFile.sha256).join(FinancialSourceDocument,
        FinancialSourceDocument.evidence_file_id == EvidenceFile.id).where(
        FinancialSourceDocument.case_id == case_id, FinancialSourceDocument.status == 'admitted')))
    files, live_reasons, live_periods = [], Counter(), 0
    for batch, entry, detail in selected:
        reading, source = detail['reading'], detail['source']
        document = session.get(EvidenceDocumentText, reading.id)
        geometry = list(session.scalars(select(EvidenceTableGeometry).where(
            EvidenceTableGeometry.evidence_file_id == reading.id,
            EvidenceTableGeometry.engine_job_id == document.engine_job_id)))
        for item in detail['held']:
            live_periods += 1
            problems = (item.summary or {}).get('problems') or []
            live_reasons.update({review_reason(problem) for problem in problems} or {'unspecified'})
        path = resolve_path(source.stored_path)
        files.append(dict(key=str(len(files)), sha256=reading.sha256, path=str(path) if path else None,
            currency=entry.get('currency'), reading_mode=detail['reading_mode'],
            identical_bytes_admitted=reading.sha256 in admitted_hashes,
            retained=dict(content=document.content, content_sha256=document.content_sha256,
                character_count=document.character_count, source_locations=document.source_locations,
                processing_manifest=document.processing_manifest,
                geometry={str(row.page_number): row.payload for row in geometry})))
    return dict(reasons=dict(reasons), files=files, live_held_periods=live_periods,
        live_reasons=dict(live_reasons))


def verified_paths(files):
    """Only originals whose bytes still match the evidence hash are re-read."""
    good, problems = {}, Counter()
    for file in files:
        path = Path(file['path']) if file['path'] else None
        if path is None or not path.is_file():
            problems['original_unavailable'] += 1
            continue
        digest = hashlib.sha256()
        with path.open('rb') as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(chunk)
        if digest.hexdigest() != file['sha256']:
            problems['original_changed'] += 1
            continue
        good[file['key']] = path
    return good, problems


def engine_reread(paths, scratch, python, concurrency):
    """Current engine code, separate process, as the benchmark harness does."""
    links = scratch / 'originals'
    links.mkdir()
    named = {}
    for key, path in paths.items():
        # The engine reads the original in place through a link; key-only names
        # keep source file names out of every log and report.
        link = links / f'{key}.pdf'
        link.symlink_to(path)
        named[str(link)] = key
    target = scratch / 'readings.json'
    env = {**os.environ, 'PYTHONDONTWRITEBYTECODE': '1', 'OMP_THREAD_LIMIT': os.environ.get('OMP_THREAD_LIMIT', '1')}
    completed = subprocess.run([python, str(ENGINE_READ), str(target), str(concurrency), *named],
        capture_output=True, text=True, env=env)
    if completed.returncode != 0:
        raise RuntimeError('The engine re-read failed: ' + completed.stderr[-2000:])
    data = json.loads(target.read_text())
    return {named[path]: value for path, value in data['readings'].items()}


def family_of(proposal_choices, statement_key):
    """The reader family of one prepared period: its layout, a payment document, or generic."""
    if not proposal_choices:
        return 'no_statement_found'
    choice = next((c for c in proposal_choices if c.get('id') == statement_key), None)
    if choice is None and len(proposal_choices) == 1:
        choice = proposal_choices[0]
    if choice is None:
        return 'unmatched_period'
    return choice.get('layout_id') or choice.get('document_kind') or 'generic-statement'


def scratch_batch(scratch, label, files, readings, *, retained_currency=True):
    """Prepare one disposable batch from the given readings with current code.

    Returns every prepared period (keyed by the file's opaque key and its
    statement key) and every file the preparation could not finish. With
    ``retained_currency`` the investigator's recorded currency choice is
    applied, as the live batch would; without it the batch sees only what the
    source establishes.
    """
    import asyncio
    from benchmarks.statement_automation.harness import _database
    from postgres.models.case import Case
    from postgres.models.enums import GlobalRole
    from postgres.models.evidence import EvidenceDocumentText, EvidenceFolder, EvidenceTableGeometry
    from postgres.models.user import User
    from services.evidence_db_storage import EvidenceDBStorage
    from services.financial import import_batches as batches
    from services.financial.decisions import Actor
    from services.financial.statement_import import read_statement_import
    engine, factory, _ = _database(scratch / f'{label}.db')
    by_id = {}
    with factory() as db:
        user = User(id=uuid.uuid4(), email='estimate@example.test', name='Dry run', password_hash='not-used',
            global_role=GlobalRole.user, is_active=True)
        case = Case(id=uuid.uuid4(), title='Reader recovery dry run', created_by_user_id=user.id, owner_user_id=user.id)
        folder = EvidenceFolder(id=uuid.uuid4(), case_id=case.id, name='Selected statements')
        db.add_all([user, case, folder])
        db.flush()
        usable = []
        for file in files:
            reading = readings.get(file['key']) if file['key'] in readings else None
            if reading is not None and 'error' not in reading:
                usable.append(file)
        created = EvidenceDBStorage.add_files(db, case.id, [dict(original_filename=f'statement-{file["key"]}.pdf',
            stored_path=str(scratch / f'statement-{file["key"]}.pdf'), sha256=file['sha256'], size=0)
            for file in usable], folder_id=folder.id, created_by_id=user.id)
        db.flush()
        for file, record in zip(usable, created):
            reading = readings[file['key']]
            record.status = 'processed'
            job = uuid.uuid4()
            stored = [EvidenceDocumentText(evidence_file_id=record.id, engine_job_id=job, content=reading['content'],
                content_sha256=reading['content_sha256'], character_count=reading['character_count'],
                source_locations=reading['source_locations'], processing_manifest=reading['processing_manifest'])]
            stored += [EvidenceTableGeometry(evidence_file_id=record.id, page_number=int(page), engine_job_id=job, payload=payload)
                for page, payload in reading['geometry'].items()]
            db.add_all(stored)
            record.engine_job_id = str(job)
            by_id[record.id] = file
            db.flush()
            for row in stored:  # Readings can be large; a whole case need not stay in memory.
                db.expunge(row)
        db.commit()
        case_id, folder_id, actor = case.id, folder.id, Actor(user.name, user.email, user.id)
    if not by_id:
        engine.dispose()
        return dict(items=[], files=0, file_errors=[])
    with factory() as db:
        batch_id = batches.create_batch(db, case_id=case_id, request_id=uuid.uuid4(), file_ids=[],
            folder_ids=[folder_id], actor=actor)
        batch = batches.batch_for(db, case_id, batch_id, True)
        entries = [dict(entry) for entry in batch.files]
        for entry in entries:
            file = by_id.get(uuid.UUID(entry['source_id']))
            if retained_currency and file and file.get('currency'):
                entry['currency'] = file['currency']  # The investigator's retained currency choice.
        batch.files = entries
        db.commit()

    async def refuse(*_args, **_kwargs):
        raise RuntimeError('Readings are stored before preparation; no engine job is started here.')
    for _ in range(10 + 2 * len(by_id)):
        asyncio.run(batches.advance_batch(factory, batch_id, Path, refuse))
        with factory() as db:
            if batches.batch_for(db, case_id, batch_id).status != 'preparing':
                break
    items, choices = [], {}
    with factory() as db:
        status = batches.batch_status(db, case_id=case_id, batch_id=batch_id, limit=100_000)
        for item in status['items']:
            file_id = uuid.UUID(item['file_id'])
            if file_id not in choices:
                try:
                    choices[file_id] = read_statement_import(db, case_id=case_id, evidence_file_id=file_id,
                        currency=item.get('currency') or None).get('statement_choices') or []
                except Exception:
                    choices[file_id] = None
            source = by_id.get(file_id) or by_id.get(uuid.UUID(item.get('source_id') or item['file_id']))
            items.append(dict(key=source['key'] if source else None, statement_key=item.get('statement_id') or '',
                status=item['status'], can_import=bool(item.get('can_import')),
                ready=item['status'] == 'ready' and bool(item.get('can_import')),
                family='unreadable' if choices[file_id] is None else family_of(choices[file_id], item.get('statement_id') or ''),
                problems=list(item.get('problems') or []), problem_count=item.get('problem_count'),
                period_start=item.get('period_start') or '', period_end=item.get('period_end') or '',
                transaction_count=item.get('transaction_count')))
        file_errors = []
        for entry in status['files']:
            if entry.get('status') == 'error':
                source = by_id.get(uuid.UUID(entry['source_id']))
                file_errors.append(dict(key=source['key'] if source else None, error=entry.get('error') or ''))
    engine.dispose()
    return dict(items=items, files=len(by_id), file_errors=file_errors)


def evaluate(scratch, label, files, readings):
    """Counts only: periods ready without edits by family and blocking reason."""
    from services.financial.batch_review_summary import reason as review_reason
    prepared = scratch_batch(scratch, label, files, readings)
    if not prepared['files']:
        return dict(periods=0, ready=0, by_family={}, reasons={}, files=0)
    by_family, reasons = defaultdict(Counter), Counter()
    for item in prepared['items']:
        by_family[item['family']]['periods'] += 1
        by_family[item['family']]['ready'] += int(item['ready'])
        if not item['ready']:
            reasons.update({review_reason(problem) for problem in item['problems']} or {'unspecified'})
    return dict(periods=sum(c['periods'] for c in by_family.values()),
        ready=sum(c['ready'] for c in by_family.values()),
        by_family={family: dict(counts) for family, counts in sorted(by_family.items())},
        reasons=dict(sorted(reasons.items())), files=prepared['files'], file_errors=len(prepared['file_errors']))


def render(report):
    lines = ['# Reader recovery dry run', '', f"Generated {report['generated_at']} (code {report['code']}).", '',
        '## Selection (live, read-only)', '', '| reason | batch files |', '|---|---|']
    lines += [f'| {reason} | {count} |' for reason, count in sorted(report['selection'].items())]
    lines += ['', f"Held periods in the selected files: {report['live_held_periods']}.",
        f"Selected files whose exact bytes are already admitted elsewhere in the case: {report['identical_bytes_admitted']}.", '',
        '### Live blocking reasons of those held periods (stored, overlapping)', '', '| reason | periods |', '|---|---|']
    lines += [f'| {reason} | {count} |' for reason, count in sorted(report['live_reasons'].items())]
    if report.get('reread'):
        old, new = report['reread']['retained'], report['reread']['current']
        lines += ['', '## Re-read (scratch, current backend code on both sides)', '',
            f"Originals verified and re-read: {report['reread']['verified']}; problems: {report['reread']['problems'] or 'none'}.",
            f"Engine re-read wall time: {report['reread']['seconds']:.0f} s.", '',
            '| family | periods (retained) | ready w/o edits (retained) | periods (new) | ready w/o edits (new) |', '|---|---|---|---|---|']
        for family in sorted(set(old['by_family']) | set(new['by_family'])):
            a, b = old['by_family'].get(family, {}), new['by_family'].get(family, {})
            lines.append(f"| {family} | {a.get('periods', 0)} | {a.get('ready', 0)} | {b.get('periods', 0)} | {b.get('ready', 0)} |")
        lines.append(f"| **all** | {old['periods']} | {old['ready']} | {new['periods']} | {new['ready']} |")
        lines += ['', '| blocking reason (overlapping) | retained | new |', '|---|---|---|']
        for reason in sorted(set(old['reasons']) | set(new['reasons'])):
            lines.append(f"| {reason} | {old['reasons'].get(reason, 0)} | {new['reasons'].get(reason, 0)} |")
    lines += ['', report['limits'], '']
    return '\n'.join(lines)


def estimate(factory, case_id, *, reread=True, python=sys.executable, concurrency=1, scratch_root=None,
             resolve_path=None, reader=None):
    with factory() as db:
        read_only(db)
        live = select_live(db, case_id, resolve_path or _resolver())
        db.rollback()
    files = live.pop('files')
    report = dict(generated_at=datetime.now(timezone.utc).isoformat(timespec='seconds'), code=_code(),
        selection=live['reasons'], live_held_periods=live['live_held_periods'], live_reasons=live['live_reasons'],
        identical_bytes_admitted=sum(f['identical_bytes_admitted'] for f in files),
        limits=__doc__.split('Limits: ', 1)[1].strip())
    if not reread or not files:
        return report
    root = Path(scratch_root) if scratch_root else None
    if root:
        root.mkdir(parents=True, exist_ok=True)
    scratch = Path(tempfile.mkdtemp(prefix=f'reader-recovery-{os.getuid()}-', dir=root))
    try:
        os.chmod(scratch, 0o700)
        paths, problems = verified_paths(files)
        started = time.monotonic()
        current = (reader or engine_reread)(paths, scratch, python, concurrency) if paths else {}
        seconds = time.monotonic() - started
        problems.update('engine_error' for value in current.values() if 'error' in value)
        verified = [file for file in files if file['key'] in paths]
        report['reread'] = dict(verified=len(verified), problems=dict(problems), seconds=seconds,
            retained=evaluate(scratch, 'retained', verified, {f['key']: f['retained'] for f in verified}),
            current=evaluate(scratch, 'current', verified, current))
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    return report


def _code():
    try:
        return subprocess.run(['git', 'rev-parse', '--short', 'HEAD'], cwd=BACKEND, capture_output=True,
            text=True, check=True).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return 'unknown'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--case', type=uuid.UUID, required=True)
    parser.add_argument('--select-only', action='store_true', help='selection counts only; no re-read')
    parser.add_argument('--out', type=Path, help='directory for report.json and report.md (outside git)')
    parser.add_argument('--engine-python', default=sys.executable)
    parser.add_argument('--concurrency', type=int, default=1)
    parser.add_argument('--scratch', type=Path, default=None, help='parent for the private scratch directory')
    args = parser.parse_args(argv)
    from postgres.session import _get_session_local
    report = estimate(_get_session_local(), args.case, reread=not args.select_only, python=args.engine_python,
        concurrency=args.concurrency, scratch_root=args.scratch)
    text_report = render(report)
    if args.out:
        args.out.mkdir(parents=True, exist_ok=True)
        (args.out / 'report.json').write_text(json.dumps(report, indent=1, sort_keys=True) + '\n')
        (args.out / 'report.md').write_text(text_report)
    print(text_report)


if __name__ == '__main__':
    main()
