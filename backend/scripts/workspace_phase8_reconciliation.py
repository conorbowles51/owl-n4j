"""Run the final, per-case Workspace cutover reconciliation gate."""

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
from services.workspace_cutover_reconciliation_service import (
    build_workspace_cutover_reconciliation_report,
)


def _load_acceptances(path: Path | None) -> tuple[set[str], dict[str, str]]:
    if path is None:
        return set(), {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("accepted_review_items")
    if not isinstance(rows, list):
        raise ValueError("Acceptance file must contain accepted_review_items as a list")
    reasons: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Every accepted review item must be an object")
        key = str(row.get("key") or "").strip()
        reason = str(row.get("reason") or "").strip()
        if not key or not reason:
            raise ValueError("Every accepted review item requires a key and reason")
        if key in reasons:
            raise ValueError(f"Duplicate accepted review key: {key}")
        reasons[key] = reason
    return set(reasons), reasons


def _write_template(path: Path, report: dict) -> None:
    payload = {
        "accepted_review_items": [
            {
                "key": item["key"],
                "reason": "REPLACE WITH THE INVESTIGATOR'S ACCEPTANCE RATIONALE",
            }
            for item in report["review_items"]
        ]
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Reconcile every legacy and canonical Workspace record by case."
    )
    parser.add_argument("--case-id", type=UUID, default=None)
    parser.add_argument("--acceptance-file", type=Path, default=None)
    parser.add_argument("--write-review-template", type=Path, default=None)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    try:
        accepted_keys, acceptance_reasons = _load_acceptances(args.acceptance_file)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))

    db_generator = get_db()
    db = next(db_generator)
    try:
        report = build_workspace_cutover_reconciliation_report(
            db,
            case_id=args.case_id,
            accepted_review_keys=accepted_keys,
        )
    finally:
        db_generator.close()

    report["acceptance"] = {
        "file": str(args.acceptance_file) if args.acceptance_file else None,
        "reasons": acceptance_reasons,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    if args.write_review_template:
        _write_template(args.write_review_template, report)
    print(json.dumps(report["summary"], sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
