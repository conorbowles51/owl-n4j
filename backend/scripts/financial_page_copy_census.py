"""Read-only census: live statements whose file is page-identical to another file of its case.

What r10-copies' page identity changes for the cases already in Loupe, measured
without writing anything:

1. Reads in one READ ONLY transaction (financial_reader_recovery_estimate.read_only:
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


def census(factory, *, case_id=None, resolve_path=None, cache=None):
    """``cache``: {file id: identity or None} from an earlier run (same bytes), updated in place."""
    from sqlalchemy import select
    from postgres.models.evidence import EvidenceFile
    from postgres.models.financial_import_batches import FinancialImportBatch as Batch, FinancialImportBatchItem as Item
    from services.financial import page_identity
    from services.financial.batch_review_summary import reason as review_reason
    from scripts.financial_reader_recovery_estimate import read_only, _resolver
    resolve_path = resolve_path or _resolver()
    cache = cache if cache is not None else {}
    # Everything needed is read in one READ ONLY transaction, which ends before
    # any page is rendered.
    with factory() as db:
        read_only(db)
        query = select(Item.id, Item.file_id, Item.status, Item.summary, Batch.case_id).join(
            Batch, Batch.id == Item.batch_id).where(Batch.status != 'removed', Item.status.notin_(LIVE_EXCLUDED))
        if case_id:
            query = query.where(Batch.case_id == uuid.UUID(str(case_id)))
        rows = []
        for row in db.execute(query).all():
            summary = row.summary or {}
            disposition = summary.get('duplicate_disposition') or {}
            check = disposition.get('status') == 'needs_comparison' or any(
                review_reason(problem) == 'duplicate' for problem in summary.get('problems') or [])
            rows.append((row.case_id, row.file_id, row.status, check))
        file_ids = sorted({row[1] for row in rows}, key=str)
        files = {}
        for start in range(0, len(file_ids), 500):
            for file in db.scalars(select(EvidenceFile).where(EvidenceFile.id.in_(file_ids[start:start + 500]))):
                files[file.id] = (file.case_id, file.original_filename or '', file.stored_path, file.sha256)
        db.rollback()
    report = dict(cases={}, files=0, identities=0, unrenderable=0)
    identities = {}
    for file_id, (case, name, stored_path, sha) in files.items():
        if not name.lower().endswith('.pdf'):
            continue
        report['files'] += 1
        key = f'{file_id}:{sha}'
        if key not in cache:
            path = resolve_path(stored_path) if stored_path else None
            value = page_identity.identity_of_path(path, sha) if path else None
            cache[key] = value['identity'] if value else None
        if cache[key] is None:
            report['unrenderable'] += 1
            continue
        report['identities'] += 1
        identities[file_id] = (case, cache[key], sha)
    detail = {}
    by_case = defaultdict(list)
    for row in rows:
        by_case[row[0]].append(row)
    for case, case_rows in sorted(by_case.items(), key=lambda pair: str(pair[0])):
        groups = defaultdict(set)
        for file_id, (owner, identity, sha) in identities.items():
            if owner == case:
                groups[identity].add(file_id)
        page_groups = {identity: members for identity, members in groups.items()
                       if len({identities[m][2] for m in members}) > 1}
        in_group = {member for members in page_groups.values() for member in members}
        counts = Counter()
        for _, file_id, status, check in case_rows:
            if file_id not in in_group:
                continue
            counts['page_copy_items'] += 1
            counts['possible_duplicate_checks'] += int(status == 'attention' and check)
            counts['set_aside_already'] += int(status == 'duplicate_ignored')
            counts['saved'] += int(status == 'imported')
            counts['status_' + status] += 1
        report['cases'][str(case)[:8]] = dict(files=len({r[1] for r in case_rows}), page_copy_groups=len(page_groups),
            page_copy_files=len(in_group), live_items=len(case_rows), **counts)
        detail[str(case)] = {identity: sorted(str(m) for m in members) for identity, members in page_groups.items()}
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
    out = Path(args.out) if args.out else None
    cache_file = out / 'page-identity-cache.json' if out else None
    cache = json.loads(cache_file.read_text()) if cache_file and cache_file.exists() else {}
    try:
        report, detail = census(_get_session_local(), case_id=args.case, cache=cache)
    finally:
        if cache_file:
            out.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(json.dumps(cache))
    print(json.dumps(report, indent=2, sort_keys=True))
    if out:
        (out / 'page-copy-census.json').write_text(json.dumps(dict(report=report, groups=detail), indent=2))


if __name__ == '__main__':
    main()
