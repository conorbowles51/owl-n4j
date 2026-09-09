"""Print the deterministic, read-only Workspace migration preflight report."""

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
from services.workspace_preflight_service import build_workspace_preflight_report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inspect legacy Workspace data without changing database state."
    )
    parser.add_argument("--case-id", type=UUID, default=None)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    db_generator = get_db()
    db = next(db_generator)
    try:
        report = build_workspace_preflight_report(db, case_id=args.case_id)
        rendered = json.dumps(report, indent=2, sort_keys=True)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered + "\n", encoding="utf-8")
        else:
            print(rendered)
    finally:
        db_generator.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
