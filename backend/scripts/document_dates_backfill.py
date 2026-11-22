"""Read document dates for files already in a case, through the ingest path (services.document_date_store).

Without --reread only files with no reading yet are read (document_date_store.backfill). With --reread every file
with text is read again: a reading already stored is not added twice (store_for_file matches kind, rule and dates),
so a file gains only what the rules now read that they did not before. Dry run by default: it counts what would be
added, writing nothing.

With --model, files the rules still date nothing in are read by the "Document dates" model (one call each, saved
"Read by Loupe · not confirmed" with the words read; services.document_dates_model). The dry run makes no call and
prints how many calls --apply would make. A file the model read with no date found is not asked again until its
text changes (document_date_model_checks).

    set -a; . <app>/.env; set +a; PYTHONPATH=. python scripts/document_dates_backfill.py [--case <uuid>] [--reread] [--model] [--apply]
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
    parser.add_argument("--model", action="store_true")
    args = parser.parse_args(argv)
    model = None
    if args.model:
        from services import document_dates_model
        model = document_dates_model.default_model_call()
        if model is None:
            print("The document dates model is off or not configured (LOUPE_DOC_DATES_MODEL, AI settings).")
            return 2
    from sqlalchemy import select
    from postgres.models.evidence import EvidenceDocumentText, EvidenceFile
    from postgres.session import _get_session_local
    from services import document_date_store as store

    added: Counter = Counter()
    files: Counter = Counter()
    calls: Counter = Counter()
    readings: Counter = Counter()
    checked: Counter = Counter()
    with _get_session_local()() as db:
        if not args.reread:
            for case, counts in store.backfill(db, case_id=args.case, apply=args.apply, model=model).items():
                files[case] += counts["files"]
                added[case] += counts["readings"]
                calls[case] += counts.get("model_calls", 0)
                readings[case] += counts.get("model_readings", 0)
                checked[case] += counts.get("model_checked", 0)
        else:
            q = (select(EvidenceFile.id, EvidenceFile.case_id)
                 .join(EvidenceDocumentText, EvidenceDocumentText.evidence_file_id == EvidenceFile.id)
                 .where(EvidenceFile.deleted_at.is_(None), EvidenceFile.source_type.is_(None)))
            if args.case:
                q = q.where(EvidenceFile.case_id == args.case)
            for file_id, case in db.execute(q).all():
                with db.begin_nested():
                    n = store.store_for_file(db, file_id, apply=args.apply)
                files[str(case)] += 1
                added[str(case)] += n
                if args.apply and n:
                    db.commit()
        if not args.apply:
            db.rollback()
    done = "added" if args.apply else "would be added"
    for case in sorted(files):
        extra = (f"; model calls {'made' if args.apply else 'needed'} {calls[case]}" +
                 (f", model readings added {readings[case]}" if args.apply else "") +
                 f", already read with no date {checked[case]}") if model is not None else ""
        print(f"{case}: {files[case]} files read, {added[case]} readings {done}{extra}")
    extra = (f"; model calls {'made' if args.apply else 'needed'} {sum(calls.values())}" +
             (f", model readings added {sum(readings.values())}" if args.apply else "") +
             f", already read with no date {sum(checked.values())}") if model is not None else ""
    print(f"all: {sum(files.values())} files, {sum(added.values())} readings {done}{extra}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
