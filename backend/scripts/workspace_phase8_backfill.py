"""Rerun all reusable Workspace backfills and prove the second pass is inert."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import sqlalchemy as sa


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from postgres.backfills.workspace_cutover import run_workspace_cutover_backfills
from postgres.backfills.workspace_entries import backfill_workspace_entries
from postgres.session import _get_engine
from services.dossier_migration import backfill_dossiers


FINGERPRINT_TABLES = (
    "workspace_entries",
    "workspace_entry_revisions",
    "workspace_entry_events",
    "workspace_entry_links",
    "workspace_legacy_mappings",
    "case_profiles",
    "dossier_legacy_mappings",
    "dossier_roles",
    "dossier_links",
    "dossier_assessments",
    "dossier_media",
    "dossier_interviews",
    "dossier_interview_evidence_links",
    "case_tasks",
    "case_task_links",
    "case_deadlines",
    "shared_evidence_pins",
    "work_legacy_mappings",
    "case_contexts",
    "case_context_values",
    "case_mandate_versions",
    "case_context_legacy_mappings",
)


def _json_value(value: Any) -> Any:
    if isinstance(value, (dict, list, str, int, float, bool)) or value is None:
        return value
    return str(value)


def _fingerprint(connection: sa.Connection) -> dict[str, Any]:
    metadata = sa.MetaData()
    digest = hashlib.sha256()
    counts: dict[str, int] = {}
    for table_name in FINGERPRINT_TABLES:
        table = sa.Table(table_name, metadata, autoload_with=connection)
        primary_keys = list(table.primary_key.columns)
        statement = sa.select(table)
        if primary_keys:
            statement = statement.order_by(*primary_keys)
        rows = list(connection.execute(statement).mappings())
        counts[table_name] = len(rows)
        digest.update(table_name.encode("utf-8"))
        for row in rows:
            rendered = {
                key: _json_value(value)
                for key, value in sorted(dict(row).items())
            }
            digest.update(
                json.dumps(rendered, sort_keys=True, separators=(",", ":")).encode(
                    "utf-8"
                )
            )
    return {"sha256": digest.hexdigest(), "counts": counts}


def _run(connection: sa.Connection) -> dict[str, Any]:
    return {
        "entries": backfill_workspace_entries(connection),
        "dossiers": backfill_dossiers(connection),
        "cutover": run_workspace_cutover_backfills(connection),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run and idempotence-check the Workspace cutover backfills."
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    engine = _get_engine()
    with engine.connect() as connection:
        before = _fingerprint(connection)
    with engine.begin() as connection:
        first = _run(connection)
    with engine.connect() as connection:
        after_first = _fingerprint(connection)
    with engine.begin() as connection:
        second = _run(connection)
    with engine.connect() as connection:
        after_second = _fingerprint(connection)

    passed = after_first == after_second
    report = {
        "schema_version": 1,
        "before": before,
        "first_pass": first,
        "after_first": after_first,
        "second_pass": second,
        "after_second": after_second,
        "passed": passed,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "passed": passed,
                "before": before["sha256"],
                "after_first": after_first["sha256"],
                "after_second": after_second["sha256"],
            },
            sort_keys=True,
        )
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
