"""Fill archive positions for container entries listed before positions were recorded (cb-media item F).

For each phone report whose first-linked container is a ZIP or UFDR (the container the phone file reader opens),
run ``files.record_member_offsets``, the capture's own function. Idempotent: entries that already have a
position are left alone. Prints counts only.

    python -m app.phone.backfill_offsets <database url> [--data-root /data/evidence] [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import os

from app.phone import detect, files, store

_ZIPS = """
SELECT DISTINCT ON (l.extraction_id) l.extraction_id, e.case_id, c.id, c.container_kind, c.stored_path, l.root_path
  FROM phone_extraction_container_links l
  JOIN phone_extraction_containers c ON c.id = l.container_id
  JOIN phone_extractions e ON e.id = l.extraction_id
 ORDER BY l.extraction_id, l.linked_at
"""


def run(conn, data_root: str, dry_run: bool = False) -> list:
    out = []
    for ext, case_id, cid, kind, stored, root in conn.execute(_ZIPS).fetchall():
        if kind not in ("zip", "ufdr"):
            continue
        lacking = conn.execute("SELECT count(*) FROM phone_container_entries WHERE extraction_id = %s AND "
                               "header_offset IS NULL", (ext,)).fetchone()[0]
        row = {"extraction_id": str(ext), "container_id": str(cid), "entries_without_position": lacking}
        path = os.path.join(data_root, str(case_id), stored)
        if not os.path.isfile(path):
            row["state"] = "archive not on disk"
        elif dry_run or not lacking:
            row["state"] = "dry run" if dry_run else "nothing to fill"
        else:
            source = detect.open_source(path)
            row["filled"] = files.record_member_offsets(conn, ext, cid, source, root or "")
            row["state"] = "filled"
        out.append(row)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--data-root", default=os.environ.get("CELLEBRITE_DATA_ROOT", "/data/evidence"))
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    conn = store.connect(a.url)
    try:
        for row in run(conn, a.data_root, a.dry_run):
            print(json.dumps(row), flush=True)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
