"""Fill the engine route table from verified truth (r2-any-layout).

For every document of a truth corpus (harness manifest) the general engine is
run alone on the engine's stored reading. A layout fingerprint gets
``library_first`` when the engine PROVES a period of that layout whose money
reading (opening, closing, every movement's date, direction and amount) or
currency differs from a VERIFIED truth period with the same printed dates.
Such a layout is then never served by the engine; its family reader (or a
person) reads it. The route table holds fingerprints only, never values.

    python -m benchmarks.statement_automation.engine_routes --corpus DIR --readings READINGS.json \
        [--write services/financial/statement_engine_routes.json] [--report OUT.json]

``--report`` (private: it names documents) lists every proved period and its
comparison; counts are printed.
"""
import argparse
import json
import uuid
from collections import Counter
from pathlib import Path


def _truth_key(period):
    return (period['opening_minor'], period['closing_minor'],
            tuple(sorted((r['date'] or '', r['direction'], int(r['amount_minor'])) for r in period['rows'])))


def _engine_key(statement):
    rows = statement['_rows']
    opening = [int(r['fields']['balance']) for r in rows if r['kind'] == 'balance'
               and r['fields'].get('description') == 'Opening Balance']
    closing = [int(r['fields']['balance']) for r in rows if r['kind'] == 'balance'
               and r['fields'].get('description') == 'Closing Balance']
    moves = tuple(sorted((r['fields'].get('date') or '', r['fields'].get('direction'), int(r['fields'].get('amount_minor') or 0))
                         for r in rows if not r['excluded'] and r['kind'] == 'transaction'))
    return (opening[0] if len(opening) == 1 else None, closing[0] if len(closing) == 1 else None, moves)


def sources_from_reading(reading, filename):
    """Candidate sources exactly as the product builds them, from one stored engine reading."""
    from benchmarks.statement_automation.harness import _database
    import tempfile
    from postgres.models.user import User
    from postgres.models.case import Case
    from postgres.models.enums import GlobalRole
    from postgres.models.evidence import EvidenceFile, EvidenceFolder, EvidenceDocumentText, EvidenceTableGeometry
    from services.financial.candidate_sources import read_candidate_source
    with tempfile.TemporaryDirectory() as scratch:
        engine, factory, _ = _database(Path(scratch) / 'routes.db')
        with factory() as db:
            user = User(id=uuid.uuid4(), email='routes@example.test', name='routes', password_hash='x',
                        global_role=GlobalRole.user, is_active=True)
            case = Case(id=uuid.uuid4(), title='routes', created_by_user_id=user.id, owner_user_id=user.id)
            folder = EvidenceFolder(id=uuid.uuid4(), case_id=case.id, name='routes')
            record = EvidenceFile(id=uuid.uuid4(), case_id=case.id, folder_id=folder.id, original_filename=filename,
                                  stored_path=filename, sha256='0' * 64, size=1, status='processed')
            db.add_all([user, case, folder, record])
            db.flush()
            job = uuid.uuid4()
            db.add(EvidenceDocumentText(evidence_file_id=record.id, engine_job_id=job, content=reading['content'],
                                        content_sha256=reading['content_sha256'], character_count=reading['character_count'],
                                        source_locations=reading['source_locations'],
                                        processing_manifest=reading['processing_manifest']))
            for page, entries in reading['geometry'].items():
                db.add(EvidenceTableGeometry(evidence_file_id=record.id, page_number=int(page), engine_job_id=job, payload=entries))
            db.commit()
            return [read_candidate_source(db, case_id=case.id, evidence_file_id=record.id, page_number=int(page), table_index=index)
                    for page, entries in sorted(reading['geometry'].items(), key=lambda item: int(item[0]))
                    for index in range(len(entries or []))]


def evaluate(manifest, readings):
    from services.financial.statement_engine import read_statements
    counts, report, wrong_layouts = Counter(), [], set()
    for entry in manifest['files']:
        reading = readings.get(entry['filename'])
        if reading is None or 'error' in reading:
            counts['no_reading'] += 1
            continue
        try:
            sources = sources_from_reading(reading, entry['filename'])
        except Exception as error:  # a reading the product itself refuses (e.g. table limits)
            counts['sources_refused'] += 1
            report.append(dict(file=entry['filename'], error=type(error).__name__))
            continue
        verified = [p for p in entry['periods'] if p['truth_status'] == 'verified']
        for statement in read_statements(sources):
            if not statement['engine']['proved']:
                counts['held'] += 1
                continue
            same = [p for p in verified if p['period_start'] == statement['period_start']
                    and p['period_end'] == statement['period_end']]
            key = _engine_key(statement)
            equal = [p for p in same if _truth_key(p) == key
                     and (not statement['currency'] or statement['currency'] == p['currency'])]
            outcome = 'agrees' if equal else 'differs' if same else 'no_verified_truth'
            counts['proved_' + outcome] += 1
            if outcome == 'differs':
                wrong_layouts.add(statement['layout_fingerprint'])
            report.append(dict(file=entry['filename'], period_start=statement['period_start'],
                               fingerprint=statement['layout_fingerprint'], outcome=outcome))
    return counts, report, wrong_layouts


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--corpus', required=True)
    parser.add_argument('--readings', required=True)
    parser.add_argument('--write', help='route table to update (fingerprints only)')
    parser.add_argument('--report', help='private per-period report')
    args = parser.parse_args()
    manifest = json.loads((Path(args.corpus) / 'manifest.json').read_text())
    readings = {Path(k).name: v for k, v in json.loads(Path(args.readings).read_text())['readings'].items()}
    counts, report, wrong = evaluate(manifest, readings)
    print(json.dumps(dict(counts=dict(counts), library_first_layouts=len(wrong)), sort_keys=True))
    if args.report:
        Path(args.report).write_text(json.dumps(report, indent=1))
    if args.write:
        path = Path(args.write)
        table = json.loads(path.read_text()) if path.exists() else dict(version=1, routes={})
        table['routes'].update({fingerprint: 'library_first' for fingerprint in sorted(wrong)})
        path.write_text(json.dumps(table, indent=1, sort_keys=True) + '\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
