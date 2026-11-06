"""The daily evidence file check, and the restore of a missing file from a copy (services/evidence_file_check.py).

    python -m scripts.evidence_file_check check [--dry-run]
    python -m scripts.evidence_file_check restore <case id> --search <folder> [--search <folder>] [--apply]

``check`` prints one line per finding and a summary last. Exit 0 nothing new, 3 rows newly missing or a file whose bytes
are not the row's, 2 the check refused to mark (ALERT lines say why); 1 is Python's own for a crash, so a finding never
uses it. ``restore`` is a dry run unless ``--apply``.
"""
from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import EVIDENCE_DATA_ROOT  # noqa: E402
from postgres.session import get_background_session  # noqa: E402
from services.evidence_file_check import check_files, per_case, restore_files  # noqa: E402


FOUND = 3


def check(dry_run: bool) -> int:
    with get_background_session() as db:
        result = check_files(db, EVIDENCE_DATA_ROOT, apply=not dry_run)
    if result.refused:
        print(f"ALERT: evidence file check refused: {result.refused}")
        return 2
    code = 0
    if result.new:
        print(f"ALERT: {len(result.new)} evidence rows newly have no file on disk: {per_case(result.new)}. "
              f"{'Dry run: not marked' if dry_run else 'They now show as missing in the app'}")
        code = FOUND
    if result.wrong_bytes:
        print(f"ALERT: {len(result.wrong_bytes)} missing evidence files are back with other bytes than the row's hash: "
              f"{per_case(result.wrong_bytes)}. They stay marked missing")
        code = FOUND
    for row in result.new:
        print(f"missing {row.case_id} {row.id} {row.original_filename}")
    for row in result.back:
        print(f"back {row.case_id} {row.id} {row.original_filename}")
    print(f"ok: {result.rows} rows checked, {result.missing} have no file, {len(result.new)} new, "
          f"{len(result.back)} back")
    return code


def restore(case_id: str, search: list, apply: bool) -> int:
    with get_background_session() as db:
        results = restore_files(db, uuid.UUID(case_id), EVIDENCE_DATA_ROOT, [Path(p) for p in search], apply=apply)
    for item in results:
        print(f"{item.outcome}\t{item.row_id}\t{item.name}\t{item.source or '-'}\t{item.target}")
    found = sum(item.outcome != "no copy found" for item in results)
    print(f"{'restored' if apply else 'would restore'} {found} of {len(results)} missing files in case {case_id}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    daily = commands.add_parser("check")
    daily.add_argument("--dry-run", action="store_true")
    back = commands.add_parser("restore")
    back.add_argument("case_id")
    back.add_argument("--search", action="append", required=True)
    back.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    return check(args.dry_run) if args.command == "check" else restore(args.case_id, args.search, args.apply)


if __name__ == "__main__":
    sys.exit(main())
