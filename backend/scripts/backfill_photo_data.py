"""Read the photo data (date taken, place, camera, size) of photos already in cases. Metadata only.

No OCR is rerun and no model is called: each picture file is opened, its own EXIF is read by
``services.photo_metadata`` (the reader processing uses), and the result is stored on the evidence file under
``metadata.photo_data``, marked ``read_by: backfill`` with the time. A file that already has a record is left alone
unless ``--refresh`` is given. Nothing else on the file changes.

    python scripts/backfill_photo_data.py                    # dry run, all cases: what would change
    python scripts/backfill_photo_data.py --case-id <uuid>   # one case
    python scripts/backfill_photo_data.py --apply            # store
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from sqlalchemy import select, text  # noqa: E402

from postgres.models.evidence import EvidenceFile  # noqa: E402
from services.photo_metadata import STORE_SQL, photo_data_record, store_params  # noqa: E402

PICTURE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".gif", ".webp")


def _counts(files) -> dict:
    count = Counter()
    for file in files:
        record = (file.metadata_ or {}).get("photo_data") or {}
        if record:
            count["read"] += 1
            count["date_taken"] += "date_taken" in record
            count["gps"] += "gps" in record
            count["camera"] += "camera" in record
    return dict(count)


def backfill(db, *, case_id=None, apply=False, refresh=False, resolve_path=None) -> dict:
    """Per case ``{pictures, before, after, stored, unreadable, missing}``. ``db`` is a sync Session."""
    if resolve_path is None:
        from routers.evidence import _resolve_stored_path as resolve_path
    query = select(EvidenceFile).where(EvidenceFile.deleted_at.is_(None))
    if case_id:
        query = query.where(EvidenceFile.case_id == case_id)
    by_case = defaultdict(list)
    for file in db.scalars(query.order_by(EvidenceFile.case_id, EvidenceFile.id)):
        if file.original_filename.lower().endswith(PICTURE_EXTENSIONS):
            by_case[str(file.case_id)].append(file)
    report = {}
    for case, files in by_case.items():
        row = dict(pictures=len(files), before=_counts(files), stored=0, unreadable=0, missing=0, would_store=0)
        for file in files:
            if (file.metadata_ or {}).get("photo_data") and not refresh:
                continue
            path = resolve_path(file.stored_path)
            if not path or not path.exists():
                row["missing"] += 1
                continue
            record = photo_data_record(str(path), read_by="backfill")
            if not record:
                row["unreadable"] += 1
                continue
            row["would_store"] += 1
            if apply:
                if db.get_bind().dialect.name == "postgresql":
                    # one statement, so a file being processed at the same moment keeps its other metadata
                    db.execute(text(STORE_SQL), store_params(file.id, record))
                else:
                    file.metadata_ = {**(file.metadata_ or {}), "photo_data": record}
                row["stored"] += 1
        if apply:
            db.commit()
            for file in files:
                db.refresh(file)
        row["after"] = _counts(files) if apply else None
        report[case] = row
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--case-id")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--refresh", action="store_true", help="read again files that already have a record")
    args = parser.parse_args()
    from postgres.session import get_background_session

    with get_background_session() as db:
        report = backfill(db, case_id=args.case_id, apply=args.apply, refresh=args.refresh)
    print("mode:", "APPLY" if args.apply else "dry run (nothing written)")
    for case, row in report.items():
        print(f"case {case}: pictures {row['pictures']}, before {row['before']}, "
              f"{'stored' if args.apply else 'would store'} {row['stored'] if args.apply else row['would_store']}, "
              f"unreadable {row['unreadable']}, missing on disk {row['missing']}, after {row['after']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
