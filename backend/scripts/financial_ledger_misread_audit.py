"""Read-only audit of admitted statements for money misreads the current reader would catch.

Earlier readers could admit a scanned statement whose OCR misread two money
cells in opposite directions, so every printed control still agreed. The
current engine verifies every money cell on image-derived pages against
page-image crops and an independent glyph reader, and leaves a disputed cell
unreadable instead of guessing. This audit re-reads the originals of
admitted statement reviews with the current engine and compares, cell by
cell, what was admitted with what the current reader now reads.

For each admitted statement review of the case (READ ONLY transaction, ORM
writes refused, nothing written to the case):

* statements whose retained reading is native PDF text only are skipped
  (the money-cell checks apply to image-derived pages), unless the original
  measured now has a page the current rule calls recognised (for example
  mostly invisible text over small image tiles, r1-reproduced);
* the original is verified against its evidence hash and re-read in a
  separate process with the current engine (single-threaded OCR);
* the same statement is read from the new reading in a disposable SQLite
  database, and each admitted payment amount and running balance is compared
  by its source row address with the new reading's cell.

Outcomes per cell: ``agrees``; ``disagrees`` (the current reader confirms a
different value); ``disputed_now`` (the current reader will not confirm the
digits, so a new upload would be held for a person); ``row_not_found``.
Cells whose admitted value an investigator entered or corrected are counted
separately under ``investigator_*`` and never flagged on their own.

A period is listed when any machine-read admitted cell disagrees or is now
disputed. The report holds source document ids, evidence file ids and counts
only. Write it outside git. From `backend/`:

    OMP_THREAD_LIMIT=1 python3 scripts/financial_ledger_misread_audit.py --case <uuid> --out DIR
"""
import argparse
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import time
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
NATIVE = 'digital_text_layer'


def _estimate():
    spec = importlib.util.spec_from_file_location('financial_reader_recovery_estimate',
        BACKEND / 'scripts/financial_reader_recovery_estimate.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _now_recognised(path, measured):
    """Whether the original, measured now with the current origin rule, has a
    page of recognised text. A file that cannot be measured keeps its stored
    verdict; reading it would fail its own checks later."""
    if path is None:
        return False
    key = str(path)
    if key not in measured:
        try:
            import fitz
            from services.financial.suspect_amounts import page_text_origin, TextOrigin
            with fitz.open(key) as document:
                measured[key] = any(page_text_origin(page) is TextOrigin.recognised_glyphs for page in document)
        except Exception:
            measured[key] = False
    return measured[key]


def admitted_sources(session, case_id, resolve_path, limit=None):
    from sqlalchemy import select
    from postgres.models.evidence import EvidenceDocumentText, EvidenceFile
    from postgres.models.financial import FinancialSourceDocument
    query = select(FinancialSourceDocument).where(FinancialSourceDocument.case_id == case_id,
        FinancialSourceDocument.status == 'admitted', FinancialSourceDocument.document_type == 'statement_review'
    ).order_by(FinancialSourceDocument.id)
    sources, skipped, measured = [], Counter(), {}
    for document in session.scalars(query):
        metadata = document.metadata_ or {}
        request, original = metadata.get('statement_import_request'), metadata.get('statement_import_original')
        file = session.get(EvidenceFile, document.evidence_file_id) if document.evidence_file_id else None
        text = session.get(EvidenceDocumentText, file.id) if file else None
        if not request or not original or file is None or text is None:
            skipped['no_retained_reading'] += 1
            continue
        origins = {location.get('text_origin') for location in text.source_locations or []}
        path = resolve_path(file.stored_path)
        if origins and origins <= {NATIVE} and not _now_recognised(path, measured):
            skipped['native_text_only'] += 1
            continue
        if limit is not None and len(sources) >= limit:
            skipped['over_limit'] += 1
            continue
        sources.append(dict(key=str(len(sources)), source_document_id=str(document.id), evidence_file_id=str(file.id),
            sha256=document.sha256_at_ingestion or file.sha256, path=str(path) if path else None,
            statement_id=request.get('statement_id'), currency=request.get('currency'),
            period=(request.get('period_start'), request.get('period_end')),
            request_rows=request.get('rows') or [], original_rows=original.get('rows') or []))
    return sources, skipped


def _same(left, right):
    return left is not None and right is not None and str(left).lstrip('-') == str(right).lstrip('-')


def compare(source, proposal):
    """Per-cell outcomes for one admitted statement against a new reading."""
    new_rows = {row['id']: row for row in proposal.get('rows') or []}
    original = {row['id']: row for row in source['original_rows']}
    outcomes = Counter()
    for row in source['request_rows']:
        if row.get('excluded'):
            continue
        before = (original.get(row['id']) or {}).get('fields') or {}
        new = new_rows.get(row['id'])
        for name, admitted, machine, current in (
                ('amount', row.get('amount_minor'), before.get('amount_minor'), ((new or {}).get('fields') or {}).get('amount_minor')),
                ('balance', row.get('balance_minor'), before.get('balance'), ((new or {}).get('fields') or {}).get('balance'))):
            if admitted in (None, ''):
                continue
            entered = not _same(admitted, machine)
            prefix = 'investigator_' if entered else ''
            if new is None:
                outcomes[prefix + 'row_not_found'] += 1
            elif current in (None, ''):
                outcomes[prefix + 'disputed_now'] += 1
            elif not _same(admitted, current) or (name == 'amount' and row.get('direction') and
                    (new.get('fields') or {}).get('direction') not in (None, '', row.get('direction'))):
                outcomes[prefix + 'disagrees'] += 1
            else:
                outcomes[prefix + 'agrees'] += 1
            outcomes['cells_' + name] += 1
    return outcomes


def _proposal(db, case_id, file_id, source):
    from services.financial.statement_import import read_statement_import
    first = read_statement_import(db, case_id=case_id, evidence_file_id=file_id, currency=source['currency'] or None)
    choices = [choice['id'] for choice in first.get('statement_choices') or []]
    if not choices or source['statement_id'] in (None, '') and len(choices) <= 1:
        return first
    if source['statement_id'] in choices:
        return read_statement_import(db, case_id=case_id, evidence_file_id=file_id,
            currency=source['currency'] or None, statement_id=source['statement_id'])
    for choice in choices:
        proposal = read_statement_import(db, case_id=case_id, evidence_file_id=file_id,
            currency=source['currency'] or None, statement_id=choice)
        metadata = proposal.get('metadata') or {}
        if (metadata.get('period_start'), metadata.get('period_end')) == tuple(source['period']):
            return proposal
    return None


def evaluate(scratch, sources, readings):
    from benchmarks.statement_automation.harness import _database
    from postgres.models.case import Case
    from postgres.models.enums import GlobalRole
    from postgres.models.evidence import EvidenceDocumentText, EvidenceTableGeometry
    from postgres.models.user import User
    from services.evidence_db_storage import EvidenceDBStorage
    engine, factory, _ = _database(scratch / 'audit.db')
    results = []
    with factory() as db:
        user = User(id=uuid.uuid4(), email='audit@example.test', name='Audit', password_hash='not-used',
            global_role=GlobalRole.user, is_active=True)
        case = Case(id=uuid.uuid4(), title='Ledger misread audit', created_by_user_id=user.id, owner_user_id=user.id)
        db.add_all([user, case])
        db.commit()
        for source in sources:
            reading = readings.get(source['key'])
            row = dict(source_document_id=source['source_document_id'], evidence_file_id=source['evidence_file_id'])
            if reading is None or 'error' in reading:
                results.append(dict(row, outcome='not_reread'))
                continue
            (record,) = EvidenceDBStorage.add_files(db, case.id, [dict(original_filename=f'statement-{source["key"]}.pdf',
                stored_path=str(scratch / 'unused.pdf'), sha256=source['sha256'], size=0)], created_by_id=user.id)
            record.status = 'processed'
            job = uuid.uuid4()
            db.add(EvidenceDocumentText(evidence_file_id=record.id, engine_job_id=job, content=reading['content'],
                content_sha256=reading['content_sha256'], character_count=reading['character_count'],
                source_locations=reading['source_locations'], processing_manifest=reading['processing_manifest']))
            for page, payload in reading['geometry'].items():
                db.add(EvidenceTableGeometry(evidence_file_id=record.id, page_number=int(page), engine_job_id=job, payload=payload))
            db.commit()
            try:
                proposal = _proposal(db, case.id, record.id, source)
            except Exception as error:  # A reading the current code cannot review is reported, not hidden.
                results.append(dict(row, outcome='unreviewable', error=type(error).__name__))
                continue
            if proposal is None:
                results.append(dict(row, outcome='statement_not_found'))
                continue
            cells = compare(source, proposal)
            flagged = cells['disagrees'] + cells['disputed_now']
            results.append(dict(row, outcome='flagged' if flagged else 'consistent', cells=dict(sorted(cells.items()))))
    engine.dispose()
    return results


def audit(factory, case_id, *, python=sys.executable, concurrency=1, scratch_root=None, resolve_path=None,
          reader=None, limit=None):
    estimate = _estimate()
    with factory() as db:
        estimate.read_only(db)
        sources, skipped = admitted_sources(db, case_id, resolve_path or estimate._resolver(), limit)
        db.rollback()
    report = dict(generated_at=datetime.now(timezone.utc).isoformat(timespec='seconds'), code=estimate._code(),
        case_id=str(case_id), considered=len(sources) + sum(skipped.values()), skipped=dict(skipped), periods=[])
    if not sources:
        return report
    root = Path(scratch_root) if scratch_root else None
    if root:
        root.mkdir(parents=True, exist_ok=True)
    scratch = Path(tempfile.mkdtemp(prefix=f'misread-audit-{os.getuid()}-', dir=root))
    try:
        os.chmod(scratch, 0o700)
        paths, problems = estimate.verified_paths(sources)
        started = time.monotonic()
        readings = (reader or estimate.engine_reread)(paths, scratch, python, concurrency) if paths else {}
        report['reread_seconds'] = time.monotonic() - started
        report['original_problems'] = dict(problems)
        report['periods'] = evaluate(scratch, [source for source in sources if source['key'] in paths], readings)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    report['outcomes'] = dict(Counter(period['outcome'] for period in report['periods']))
    report['cells'] = dict(sum((Counter(period.get('cells', {})) for period in report['periods']), Counter()))
    return report


def render(report):
    lines = ['# Admitted-ledger misread audit (read-only)', '', f"Generated {report['generated_at']} (code {report['code']}), case {report['case_id']}.", '',
        f"Admitted statement reviews considered: {report['considered']}; skipped: {report['skipped'] or 'none'}.",
        f"Originals unavailable or changed: {report.get('original_problems') or 'none'}.",
        f"Period outcomes: {report.get('outcomes') or 'none'}.", f"Cell outcomes: {report.get('cells') or 'none'}.", '']
    flagged = [period for period in report['periods'] if period['outcome'] == 'flagged']
    lines += ['## Periods where an admitted machine-read value disagrees with the current reader', '']
    if not flagged:
        lines.append('None.')
    else:
        lines += ['| source document | evidence file | disagrees | disputed now | investigator-entered cells not agreeing |', '|---|---|---|---|---|']
        for period in flagged:
            cells = period['cells']
            lines.append(f"| {period['source_document_id']} | {period['evidence_file_id']} | {cells.get('disagrees', 0)} | "
                f"{cells.get('disputed_now', 0)} | {cells.get('investigator_disagrees', 0) + cells.get('investigator_disputed_now', 0)} |")
    lines.append('')
    return '\n'.join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--case', type=uuid.UUID, required=True)
    parser.add_argument('--out', type=Path, required=True, help='directory for report.json and report.md (outside git)')
    parser.add_argument('--limit', type=int, default=None, help='at most this many image-derived statements')
    parser.add_argument('--engine-python', default=sys.executable)
    parser.add_argument('--concurrency', type=int, default=1)
    parser.add_argument('--scratch', type=Path, default=None)
    args = parser.parse_args(argv)
    from postgres.session import _get_session_local
    report = audit(_get_session_local(), args.case, python=args.engine_python, concurrency=args.concurrency,
        scratch_root=args.scratch, limit=args.limit)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / 'report.json').write_text(json.dumps(report, indent=1, sort_keys=True) + '\n')
    (args.out / 'report.md').write_text(render(report))
    print(render(report).split('## Periods')[0])


if __name__ == '__main__':
    main()
