"""Write the deterministic Phase 1 Workspace entry reconciliation report."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from uuid import UUID


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from postgres.session import get_db
from services.workspace_entry_reconciliation_service import (
    build_workspace_entry_reconciliation_report,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare legacy authored casework with canonical Workspace entries."
    )
    parser.add_argument("--case-id", type=UUID, default=None)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument(
        "--fail-on-unexpected-difference",
        action="store_true",
        help="Return non-zero for missing, inconsistent, or unrepointed records.",
    )
    args = parser.parse_args()

    db_generator = get_db()
    db = next(db_generator)
    try:
        report = build_workspace_entry_reconciliation_report(db, case_id=args.case_id)
        rendered = json.dumps(report, indent=2, sort_keys=True)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered + "\n", encoding="utf-8")
        else:
            print(rendered)
    finally:
        db_generator.close()

    if args.fail_on_unexpected_difference:
        summary = report["summary"]
        unexpected = sum(
            summary[key]
            for key in (
                "duplicate_sources",
                "missing_mappings",
                "missing_targets",
                "inconsistent_targets",
                "mappings_without_target_identity",
                "unrepointed_profile_links",
            )
        )
        return 1 if unexpected else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
