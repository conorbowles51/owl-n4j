"""Read-only census: live statements whose file is page-identical to another file of its case.

What r10-copies' page identity changes for the cases already in Loupe, measured
without writing anything:

1. Opens a READ ONLY transaction (financial_reader_recovery_estimate.read_only:
   the database refuses writes and the ORM refuses to flush).
2. Lists every file read for a live Financial batch item, per case, and
   renders each one's pages exactly as preparation now does
   (page_identity.identity_of_path, 40 dpi). Evidence files are only opened
   for reading.
3. Groups files of one case by page identity. A group with more than one
   distinct sha256 is a set of bytes-different files with identical pages:
   page copies that byte comparison never linked.
4. Counts the live batch items in those groups, and among them the items that
   carry a "possible duplicate" check today (a needs_comparison disposition or
   a duplicate problem): the checks the page rule settles automatically.

Prints counts only. With ``--out DIR`` it writes the per-file detail (ids and
identities, no names) to DIR/page-copy-census.json; point it at a private
directory.

    OMP_THREAD_LIMIT=1 python3 scripts/financial_page_copy_census.py [--case ID] [--out DIR]
"""
import argparse
import json
import sys
import uuid
from collections import Counter, defaultdict
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

LIVE_EXCLUDED = ('removed', 'superseded_reading')


def census(factory, *, case_id=None, resolve_path=None):
    from sqlalchemy import select
    from postgres.models.evidence import EvidenceFile
    from postgres.models.financial_import_batches import FinancialImportBatch as Batch, FinancialImportBatchItem as Item
    from services.financial import page_identity
    from services.financial.batch_review_summary import reason as review_reason
    from scripts.financial_reader_recovery_estimate import read_only, _resolver
    resolve_path = resolve_path or _resolver()
    report = dict(cases={}, files=0, identities=0, unrenderable=0)
    detail = {}
    with factory() as db:
        read_only(db)
        query = select(Item.id, Item.file_id, Item.status, Item.summary, Batch.case_id).join(
            Batch, Batch.id == Item.batch_id).where(Batch.status != 'removed', Item.status.notin_(LIVE_EXCLUDED))
        if case_id:
            query = query.where(Batch.case_id == uuid.UUID(str(case_id)))
        items = db.execute(query).all()
        by_case = defaultdict(list)
        for row in items:
            by_case[row.case_id].append(row)
        for case, rows in sorted(by_case.items(), key=lambda pair: str(pair[0])):
            file_ids = sorted({row.file_id for row in rows}, key=str)
            files = {file.id: file for file in db.scalars(select(EvidenceFile).where(
                EvidenceFile.case_id == case, EvidenceFile.id.in_(file_ids)))}
            identities = {}
            for file_id in file_ids:
                file = files.get(file_id)
                if file is None or not str(file.original_filename or '').lower().endswith('.pdf'):
                    continue
                path = resolve_path(file.stored_path) if file.stored_path else None
                value = page_identity.identity_of_path(path, file.sha256) if path else None
                report['files'] += 1
                if value is None:
                    report['unrenderable'] += 1
                    continue
                report['identities'] += 1
                identities[file_id] = (value['identity'], file.sha256)
            groups = defaultdict(set)
            for file_id, (identity, sha) in identities.items():
                groups[identity].add(file_id)
            page_groups = {identity: members for identity, members in groups.items()
                           if len({identities[m][1] for m in members}) > 1}
            in_group = {member for members in page_groups.values() for member in members}
            counts = Counter()
            for row in rows:
                if row.file_id not in in_group:
                    continue
                summary = row.summary or {}
                disposition = summary.get('duplicate_disposition') or {}
                check = disposition.get('status') == 'needs_comparison' or any(
                    review_reason(problem) == 'duplicate' for problem in summary.get('problems') or [])
                counts['items'] += 1
                counts['possible_duplicate_checks'] += int(row.status == 'attention' and check)
                counts['set_aside_already'] += int(row.status == 'duplicate_ignored')
                counts['saved'] += int(row.status == 'imported')
                counts['by_status:' + row.status] += 1
            report['cases'][str(case)[:8]] = dict(files=len(file_ids), page_copy_groups=len(page_groups),
                page_copy_files=len(in_group), items=len(rows), **counts)
            detail[str(case)] = {identity: sorted(str(m) for m in members) for identity, members in page_groups.items()}
        db.rollback()
    totals = Counter()
    for values in report['cases'].values():
        totals.update({key: value for key, value in values.items() if isinstance(value, int)})
    report['totals'] = dict(totals)
    return report, detail


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--case', help='one case id (default: every case with live batch items)')
    parser.add_argument('--out', help='private directory for the per-file detail')
    args = parser.parse_args(argv)
    from postgres.session import _get_session_local
    report, detail = census(_get_session_local(), case_id=args.case)
    print(json.dumps(report, indent=2, sort_keys=True))
    if args.out:
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        (out / 'page-copy-census.json').write_text(json.dumps(dict(report=report, groups=detail), indent=2))


if __name__ == '__main__':
    main()
