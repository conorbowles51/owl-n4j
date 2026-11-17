"""Read document dates for files already in a case, through the ingest path (services.document_date_store).

Without --reread only files with no reading yet are read (document_date_store.backfill). With --reread every file
with text is read again: a reading already stored is not added twice (store_for_file matches kind, rule and dates),
so a file gains only what the rules now read that they did not before. Dry run by default: it counts what would be
added, writing nothing.

    set -a; . <app>/.env; set +a; PYTHONPATH=. python scripts/document_dates_backfill.py [--case <uuid>] [--reread] [--apply]
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case")
    parser.add_argument("--reread", action="store_true")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    from sqlalchemy import select
    from postgres.models.evidence import EvidenceDocumentText, EvidenceFile
    from postgres.session import _get_session_local
    from services import document_date_store as store

    added: Counter = Counter()
    files: Counter = Counter()
    with _get_session_local()() as db:
        if not args.reread:
            for case, counts in store.backfill(db, case_id=args.case, apply=args.apply).items():
                files[case] += counts["files"]
                added[case] += counts["readings"]
        else:
            q = (select(EvidenceFile.id, EvidenceFile.case_id)
                 .join(EvidenceDocumentText, EvidenceDocumentText.evidence_file_id == EvidenceFile.id)
                 .where(EvidenceFile.deleted_at.is_(None), EvidenceFile.source_type.is_(None)))
            if args.case:
                q = q.where(EvidenceFile.case_id == args.case)
            for file_id, case in db.execute(q).all():
                n = store.store_for_file_safe(db, file_id) if args.apply else store.store_for_file(db, file_id, apply=False)
                files[str(case)] += 1
                added[str(case)] += n
                if args.apply and n:
                    db.commit()
        if not args.apply:
            db.rollback()
    for case in sorted(files):
        print(f"{case}: {files[case]} files read, {added[case]} readings {'added' if args.apply else 'would be added'}")
    print(f"all: {sum(files.values())} files, {sum(added.values())} readings {'added' if args.apply else 'would be added'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
