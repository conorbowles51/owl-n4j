"""Read one statement file again with the current reader, from its saved reading. Dry run by default.

A reader change reaches statements already prepared in a batch only when their
file is prepared again. This command does that for ONE file, through the
batch's own "refresh statements" path (``import_batches.refresh_statement_list``
does the same for every file of a batch): the worker re-reads the file's saved
text and table geometry with the current backend (no new engine reading, no
OCR) and prepares its periods again. It never imports anything; readiness and
reconciliation gates apply as for any prepared statement, and the investigator
imports.

What the worker keeps: items already imported, queued for import, left
unimported or ignored as duplicates, and every item with saved review work
(``prepare_reviews``). Items of periods the current reader no longer finds,
untouched, are retired to history as ``superseded_reading``
(``import_batches.RETIRE_VANISHED_PERIODS``); nothing is deleted.

DRY RUN (default): a READ ONLY transaction (refused if the database does not
accept it; any ORM write raises). Prints, as counts only: the batches holding
the file and its state in each, its current batch items by status, and what the
current reader finds in its saved reading (periods, proved by the general
reader or held by reason, identity facts read).

--apply: in every batch holding the file (the review queue lets the newest
batch's preparation stand, so all must be refreshed together), the file's entry
is set to be prepared again (status 'processing', batch 'preparing') and a
record of the request is kept on the entry (``reread_requests``, actor
"System"). All or nothing: refused, with nothing written, while any of those
batches is paused or the file is being read in any of them.

From ``backend/`` with the service environment loaded:

    python3 scripts/financial_reread_file.py --case <case uuid> --file <evidence file uuid>
    python3 scripts/financial_reread_file.py --case <case uuid> --file <evidence file uuid> --apply
"""
import argparse
import sys
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

ACTOR = 'System (financial_reread_file)'


def batches_with_file(session, case_id, file_id):
    from sqlalchemy import select
    from postgres.models.financial_import_batches import FinancialImportBatch as Batch
    found = []
    for batch in session.scalars(select(Batch).where(Batch.case_id == case_id, Batch.status != 'removed')):
        for entry in batch.files or []:
            if str(file_id) in (entry.get('file_id'), entry.get('source_id')):
                found.append((batch, entry))
    return found


def current_items(session, file_id):
    from sqlalchemy import select
    from postgres.models.financial_import_batches import FinancialImportBatchItem as Item
    items = list(session.scalars(select(Item).where(Item.file_id == file_id)))
    return dict(Counter(item.status for item in items)), sum(1 for item in items if item.review_request)


def preview(session, case_id, file_id):
    """What the current reader finds in the file's saved reading (pure: nothing is written)."""
    from sqlalchemy import select
    from postgres.models.evidence import EvidenceTableGeometry
    from services.financial.candidate_sources import read_candidate_source
    from services.financial.statement_import_catalog import statement_catalog
    pages = list(session.scalars(select(EvidenceTableGeometry).where(EvidenceTableGeometry.evidence_file_id == file_id)
                                 .order_by(EvidenceTableGeometry.page_number)))
    sources = [read_candidate_source(session, case_id=case_id, evidence_file_id=file_id, page_number=p.page_number,
                                     table_index=i) for p in pages for i in range(len(p.payload or []))]
    catalog = statement_catalog(sources)
    statements = catalog['statements']
    engine = Counter('proved' if (s.get('engine') or {}).get('proved') else 'held: ' + str((s.get('engine') or {}).get('reason'))
                     for s in statements if s.get('engine'))
    identity = Counter(field for s in statements for field in ('account_reference', 'holder', 'currency', 'institution')
                       if s.get(field))
    return dict(periods=len(statements), general_reader=dict(engine), library_periods=sum(1 for s in statements if not s.get('engine')),
                identity_read=dict(identity), unclassified_tables=len(catalog['unclassified_sources']),
                profile=(catalog.get('engine_routing') or {}).get('profile'))


def dry_run(factory, case_id, file_id):
    from scripts.financial_reader_recovery_estimate import read_only
    with factory() as db:
        read_only(db)
        found = batches_with_file(db, case_id, file_id)
        statuses, edited = current_items(db, file_id)
        report = dict(batches=[dict(batch=str(b.id)[:8], batch_status=b.status, file_status=e.get('status')) for b, e in found],
                      items=statuses, items_with_saved_review=edited, current_reader=preview(db, case_id, file_id))
        db.rollback()
    return report


def apply(factory, case_id, file_id):
    """Queue the file in every batch holding it, or in none: the review queue lets the newest batch's
    preparation stand for each period, so a batch left on the earlier reading would keep listing the
    periods the current reader no longer finds."""
    from services.financial import import_batches
    from services.financial.pdf_candidates import PdfMappingError
    with factory() as db:
        found = batches_with_file(db, case_id, file_id)
        if not found:
            raise SystemExit('Refused: no batch in this case holds the file.')
        locked = []
        for batch, _ in found:
            batch = import_batches.batch_for(db, case_id, batch.id, lock=True)
            try:
                import_batches.require_running(batch)
            except PdfMappingError as error:
                raise SystemExit(f'Refused (nothing written): batch {str(batch.id)[:8]}: {error}')
            files = deepcopy(batch.files)
            entry = next(e for e in files if str(file_id) in (e.get('file_id'), e.get('source_id')))
            if entry.get('status') != 'checked':
                raise SystemExit(f"Refused (nothing written): in batch {str(batch.id)[:8]} the file is "
                                 f"'{entry.get('status')}', not prepared and idle.")
            locked.append((batch, files, entry))
        stamp = datetime.now(timezone.utc).isoformat()
        for batch, files, entry in locked:
            entry['status'] = 'processing'
            entry.setdefault('reread_requests', []).append(dict(actor=ACTOR, at=stamp,
                                                                reason='current reader, from the saved reading'))
            batch.files = files
            batch.status = 'preparing'
        db.commit()
        return [str(batch.id)[:8] for batch, _, _ in locked]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--case', type=UUID, required=True)
    parser.add_argument('--file', type=UUID, required=True, help='evidence file id of the statement PDF')
    parser.add_argument('--apply', action='store_true', help='queue the file to be prepared again (writes)')
    args = parser.parse_args(argv)
    from postgres.session import _get_session_local
    factory = _get_session_local()
    report = dry_run(factory, args.case, args.file)
    print('DRY RUN (nothing written):' if not args.apply else 'Before:', report)
    if args.apply:
        print('Queued in batches', apply(factory, args.case, args.file), '- the batch worker prepares the file again.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
