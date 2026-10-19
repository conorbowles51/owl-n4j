"""Page identities for files already in Loupe: a read-only dry run, and a guarded backfill.

Preparation records a file's page identity (``services.financial.page_identity``)
when its batch is next prepared. Files prepared before page identity existed
have none, so copies among them (the same statement saved again by another
program: other bytes, identical pages) are not recognised until then.

DRY RUN BY DEFAULT. Everything is read in READ ONLY transactions
(financial_reader_recovery_estimate.read_only: the database refuses writes and
the ORM refuses to flush). It

1. renders every live PDF read for a Financial batch item that has no
   comparable stored identity, exactly as preparation does (40 dpi; evidence
   files are only opened for reading);
2. groups files of one case by page identity (a group with more than one
   distinct sha256 is a set of page copies byte comparison never linked);
3. for every live batch item in such a group that the copy rule re-evaluates
   (ready, attention, set aside), runs the pre-admission duplicate decision
   (``pending_statement_duplicates.apply_duplicate_disposition``) with the
   rendered identities in memory, and counts what it would decide: set aside
   as a linked copy, retained, still compared by a person. Nothing is stored;
   the transaction is rolled back.

``--apply`` (needs ``--case`` or ``--all-cases``) writes ONLY the stored page
identity of each file, through the batch worker's own path
(``import_batches._record_page_identity``: rendered outside any lock, then the
file row locked with bounded waits, its bytes checked again). It changes no
batch item, statement, admission or ledger row; existing items are settled
when their batch is next prepared, or by the readiness sweep that re-evaluates
them. Run it when no import is running.

Prints counts only. ``--out DIR`` (a private directory) keeps the rendered
identities as a cache and the per-file detail (ids and identities, no names).

    OMP_THREAD_LIMIT=1 python3 scripts/financial_page_identity_backfill.py [--case ID] [--out DIR]
    OMP_THREAD_LIMIT=1 python3 scripts/financial_page_identity_backfill.py --case ID --apply
"""
import argparse
import json
import sys
import uuid
from collections import Counter, defaultdict
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

LIVE_EXCLUDED = ('removed', 'superseded_reading')
REEVALUATED = ('ready', 'attention', 'duplicate_ignored')


def _check(summary):
    from services.financial.batch_review_summary import reason as review_reason
    disposition = (summary or {}).get('duplicate_disposition') or {}
    return disposition.get('status') == 'needs_comparison' or any(
        review_reason(problem) == 'duplicate' for problem in (summary or {}).get('problems') or [])


def live_files(factory, case_id=None):
    """(items, files): live batch items and the PDFs they were read from, in one READ ONLY transaction."""
    from sqlalchemy import select
    from postgres.models.evidence import EvidenceFile
    from postgres.models.financial_import_batches import FinancialImportBatch as Batch, FinancialImportBatchItem as Item
    from services.financial import page_identity
    from scripts.financial_reader_recovery_estimate import read_only
    with factory() as db:
        read_only(db)
        query = select(Item.id, Item.file_id, Item.status, Item.summary, Batch.case_id).join(
            Batch, Batch.id == Item.batch_id).where(Batch.status != 'removed', Item.status.notin_(LIVE_EXCLUDED))
        if case_id:
            query = query.where(Batch.case_id == uuid.UUID(str(case_id)))
        items = [(row.id, row.case_id, row.file_id, row.status, _check(row.summary)) for row in db.execute(query).all()]
        ids = sorted({item[2] for item in items}, key=str)
        files = {}
        for start in range(0, len(ids), 500):
            for file in db.scalars(select(EvidenceFile).where(EvidenceFile.id.in_(ids[start:start + 500]))):
                if (file.original_filename or '').lower().endswith('.pdf'):
                    files[file.id] = dict(case_id=file.case_id, stored_path=file.stored_path, sha256=file.sha256,
                                          stored=page_identity.stored(file), needs_record=page_identity.needs_record(file))
        db.rollback()
    return items, files


def render(files, resolve_path, cache):
    """{file id: identity} for every file: its stored identity, or one rendered now (cached by id and bytes)."""
    from services.financial import page_identity
    identities = {}
    for file_id, file in files.items():
        if file['stored'] and not file['needs_record']:
            identities[file_id] = file['stored']
            continue
        key = f"{file_id}:{file['sha256']}"
        if key not in cache:
            path = resolve_path(file['stored_path']) if file['stored_path'] else None
            cache[key] = page_identity.identity_of_path(path, file['sha256']) if path else None
        if cache[key]:
            identities[file_id] = cache[key]
    return identities


def page_groups(files, identities):
    """{case id: [set of file ids]} of files with identical pages and more than one distinct sha256."""
    groups = defaultdict(lambda: defaultdict(set))
    for file_id, value in identities.items():
        groups[files[file_id]['case_id']][(value['renderer'], value['page_count'], value['identity'])].add(file_id)
    return {case: [members for members in by.values() if len({files[m]['sha256'] for m in members}) > 1]
            for case, by in groups.items()}


def simulate(factory, case_id, item_ids, identities):
    """What the copy rule decides for these items once the identities are stored. READ ONLY, nothing stored."""
    from sqlalchemy import select
    from postgres.models.evidence import EvidenceFile
    from postgres.models.financial_import_batches import FinancialImportBatchItem as Item
    from services.financial import page_identity
    from services.financial.pdf_candidates import PdfMappingError
    from services.financial.pending_statement_duplicates import apply_duplicate_disposition
    from services.financial.statement_import import read_statement_import
    from scripts.financial_reader_recovery_estimate import read_only
    by_id = {str(file_id): value for file_id, value in identities.items()}
    real_stored = page_identity.stored

    def stored(file):
        value = by_id.get(str(getattr(file, 'id', '')))
        if value and page_identity.ENABLED and value.get('source_sha256') == getattr(file, 'sha256', None):
            return value
        return real_stored(file)

    def same_document_files(session, case, file):
        own = stored(file)
        result = {}
        for other in session.scalars(select(EvidenceFile).where(EvidenceFile.case_id == case, EvidenceFile.id != file.id)):
            if file.sha256 and other.sha256 == file.sha256:
                result[str(other.id)] = 'identical_bytes'
            elif own and stored(other) and (own['renderer'], own['page_count'], own['identity']) == (
                    stored(other)['renderer'], stored(other)['page_count'], stored(other)['identity']):
                result[str(other.id)] = 'identical_pages'
        return result

    outcomes = []
    with factory() as db, ExitStack() as stack:
        read_only(db)
        stack.enter_context(patch.object(page_identity, 'stored', stored))
        stack.enter_context(patch.object(page_identity, 'same_document_files', same_document_files))
        stack.enter_context(db.no_autoflush)
        try:
            for item_id in item_ids:
                item = db.get(Item, item_id)
                before = 'check' if _check(item.summary) else item.status
                file = db.get(EvidenceFile, item.file_id)
                try:
                    proposal = read_statement_import(db, case_id=case_id, evidence_file_id=file.id,
                        currency=item.summary.get('currency') or None, statement_id=item.statement_key or None,
                        _include_period_checks=False, _include_duplicate_disposition=False)
                    decision = apply_duplicate_disposition(db, case_id=case_id, file=file, proposal=proposal,
                                                           request=item.review_request)
                    after = decision['status']
                    basis = decision.get('basis')
                except PdfMappingError:
                    after, basis = 'unreadable', None
                except Exception as error:  # reported, never hidden
                    after, basis = 'error:' + type(error).__name__, None
                outcomes.append(dict(item_id=str(item_id), file_id=str(item.file_id), before=before,
                                     was_set_aside=item.status == 'duplicate_ignored', after=after, basis=basis))
        finally:
            db.rollback()
    return outcomes


def dry_run(factory, *, case_id=None, resolve_path=None, cache=None):
    from scripts.financial_reader_recovery_estimate import _resolver
    resolve_path = resolve_path or _resolver()
    cache = cache if cache is not None else {}
    items, files = live_files(factory, case_id)
    identities = render(files, resolve_path, cache)
    groups = page_groups(files, identities)
    report = dict(files=len(files), stored_already=sum(1 for f in files.values() if not f['needs_record']),
                  would_record=sum(1 for f_id, f in files.items() if f['needs_record'] and f_id in identities),
                  unrenderable=sum(1 for f_id in files if f_id not in identities), cases={})
    detail = {}
    for case, members in sorted(groups.items(), key=lambda pair: str(pair[0])):
        in_group = {m for group in members for m in group}
        case_items = [item for item in items if item[1] == case and item[2] in in_group]
        counts = Counter(page_copy_groups=len(members), page_copy_files=len(in_group), live_items=len(case_items))
        counts.update('status_' + item[3] for item in case_items)
        counts['possible_duplicate_checks_now'] = sum(1 for item in case_items if item[3] == 'attention' and item[4])
        outcomes = simulate(factory, case, [item[0] for item in case_items if item[3] in REEVALUATED],
                            {f: identities[f] for f in in_group}) if case_items else []
        for outcome in outcomes:
            counts[f"decision_{outcome['after']}"] += 1
            if outcome['before'] == 'check':
                counts['checks_settled' if outcome['after'] in ('ignored', 'retained') else 'checks_left'] += 1
                if outcome['after'] == 'ignored':
                    counts['checks_set_aside_as_linked_copies'] += 1
            if outcome['was_set_aside'] and outcome['after'] != 'ignored':
                counts['set_aside_items_that_would_change'] += 1
        if members:
            report['cases'][str(case)[:8]] = dict(counts)
            detail[str(case)] = dict(groups=[sorted(str(m) for m in group) for group in members], outcomes=outcomes)
    totals = Counter()
    for values in report['cases'].values():
        totals.update(values)
    report['totals'] = dict(totals)
    return report, detail


def backfill(factory, *, case_id=None, resolve_path=None):
    """Store the page identity of every live PDF without one. Writes nothing else."""
    from scripts.financial_reader_recovery_estimate import _resolver
    from services.financial.import_batches import _record_page_identity
    resolve_path = resolve_path or _resolver()
    _, files = live_files(factory, case_id)
    counts = Counter()
    for file_id, file in sorted(files.items(), key=lambda pair: str(pair[0])):
        if not file['needs_record']:
            counts['stored_already'] += 1
            continue
        try:
            _record_page_identity(factory, file['case_id'], file_id, resolve_path)
            counts['attempted'] += 1
        except Exception as error:  # a busy file waits for its next preparation
            counts['skipped_' + type(error).__name__] += 1
    _, after = live_files(factory, case_id)
    counts['recorded'] = sum(1 for f_id, f in after.items() if files.get(f_id, {}).get('needs_record') and not f['needs_record'])
    counts['without_identity_after'] = sum(1 for f in after.values() if f['needs_record'])
    return dict(counts)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--case', help='one case id (default: every case with live batch items)')
    parser.add_argument('--all-cases', action='store_true', help='required with --apply when no --case is given')
    parser.add_argument('--apply', action='store_true', help='store the page identities (writes); default is a dry run')
    parser.add_argument('--out', help='private directory for the identity cache and per-file detail')
    args = parser.parse_args(argv)
    from postgres.session import _get_session_local
    factory = _get_session_local()
    if args.apply:
        if not args.case and not args.all_cases:
            parser.error('--apply needs --case <id> or --all-cases')
        print(json.dumps(backfill(factory, case_id=args.case), indent=2, sort_keys=True))
        return
    out = Path(args.out) if args.out else None
    cache_file = out / 'page-identity-backfill-cache.json' if out else None
    cache = json.loads(cache_file.read_text()) if cache_file and cache_file.exists() else {}
    try:
        report, detail = dry_run(factory, case_id=args.case, cache=cache)
    finally:
        if cache_file:
            out.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(json.dumps(cache))
    print(json.dumps(report, indent=2, sort_keys=True))
    if out:
        (out / 'page-identity-backfill.json').write_text(json.dumps(dict(report=report, detail=detail), indent=1))


if __name__ == '__main__':
    main()
