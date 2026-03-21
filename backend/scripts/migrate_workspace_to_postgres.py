#!/usr/bin/env python3
"""
Migrate workspace data from JSON files on disk to PostgreSQL.

Run from the backend directory:
    python scripts/migrate_workspace_to_postgres.py

Prerequisites:
    - PostgreSQL must be running with the workspace tables created
      (run: alembic upgrade head)
    - The data/ directory must contain the JSON files to migrate

This script is idempotent — it uses INSERT ... ON CONFLICT DO UPDATE
so it can be re-run safely.
"""

import json
import sys
import uuid
from pathlib import Path

# Add backend to path so imports work
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from postgres.session import get_background_session
from postgres.models.workspace import (
    WorkspaceContext,
    WorkspaceWitness,
    WorkspaceTheory,
    WorkspaceTask,
    WorkspaceNote,
    WorkspacePinnedItem,
    WorkspaceDeadlineConfig,
)

BASE_DIR = Path(__file__).resolve().parent.parent.parent
STORAGE_DIR = BASE_DIR / "data"

JSON_FILES = {
    "case_contexts": STORAGE_DIR / "case_contexts.json",
    "witnesses": STORAGE_DIR / "witnesses.json",
    "theories": STORAGE_DIR / "theories.json",
    "tasks": STORAGE_DIR / "tasks.json",
    "notes": STORAGE_DIR / "investigative_notes.json",
    "pinned_items": STORAGE_DIR / "pinned_items.json",
    "deadlines": STORAGE_DIR / "case_deadlines.json",
}


def load_json(path: Path) -> dict:
    if not path.exists():
        print(f"  [skip] {path.name} — file not found")
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        print(f"  [error] {path.name}: {e}")
        return {}


def migrate_contexts(data: dict) -> int:
    """Migrate case_contexts.json — keyed by case_id, value is the context dict."""
    count = 0
    with get_background_session() as db:
        for case_id, context in data.items():
            existing = db.query(WorkspaceContext).filter_by(case_id=case_id).first()
            if existing:
                existing.data = context
            else:
                db.add(WorkspaceContext(case_id=case_id, data=context))
            count += 1
    return count


def migrate_keyed_items(data: dict, model_cls, id_field: str) -> int:
    """
    Migrate JSON files structured as { case_id: { item_id: item_data } }.
    Works for witnesses, theories, tasks, notes.
    """
    count = 0
    with get_background_session() as db:
        for case_id, items in data.items():
            if not isinstance(items, dict):
                continue
            for item_id, item_data in items.items():
                existing = db.query(model_cls).filter_by(
                    case_id=case_id, **{id_field: item_id}
                ).first()
                if existing:
                    existing.data = item_data
                else:
                    db.add(model_cls(
                        case_id=case_id,
                        **{id_field: item_id},
                        data=item_data,
                    ))
                count += 1
    return count


def migrate_pinned_items(data: dict) -> int:
    """Migrate pinned_items.json — { case_id: { pin_id: pin_data } }."""
    count = 0
    with get_background_session() as db:
        for case_id, items in data.items():
            if not isinstance(items, dict):
                continue
            for pin_id, pin_data in items.items():
                existing = db.query(WorkspacePinnedItem).filter_by(
                    case_id=case_id, pin_id=pin_id
                ).first()
                if existing:
                    existing.data = pin_data
                else:
                    db.add(WorkspacePinnedItem(
                        case_id=case_id,
                        pin_id=pin_id,
                        item_type=pin_data.get("item_type", "unknown"),
                        item_id=pin_data.get("item_id", ""),
                        user_id=pin_data.get("user_id", ""),
                        data=pin_data,
                    ))
                count += 1
    return count


def migrate_deadlines(data: dict) -> int:
    """Migrate case_deadlines.json — keyed by case_id, value is config dict."""
    count = 0
    with get_background_session() as db:
        for case_id, config in data.items():
            existing = db.query(WorkspaceDeadlineConfig).filter_by(case_id=case_id).first()
            if existing:
                existing.data = config
            else:
                db.add(WorkspaceDeadlineConfig(case_id=case_id, data=config))
            count += 1
    return count


def main():
    print("=" * 60)
    print("Workspace JSON → PostgreSQL Migration")
    print("=" * 60)

    # 1. Case contexts
    print("\n[1/7] Migrating case contexts...")
    contexts = load_json(JSON_FILES["case_contexts"])
    n = migrate_contexts(contexts)
    print(f"  → {n} case contexts migrated")

    # 2. Witnesses
    print("\n[2/7] Migrating witnesses...")
    witnesses = load_json(JSON_FILES["witnesses"])
    n = migrate_keyed_items(witnesses, WorkspaceWitness, "witness_id")
    print(f"  → {n} witnesses migrated")

    # 3. Theories
    print("\n[3/7] Migrating theories...")
    theories = load_json(JSON_FILES["theories"])
    n = migrate_keyed_items(theories, WorkspaceTheory, "theory_id")
    print(f"  → {n} theories migrated")

    # 4. Tasks
    print("\n[4/7] Migrating tasks...")
    tasks = load_json(JSON_FILES["tasks"])
    n = migrate_keyed_items(tasks, WorkspaceTask, "task_id")
    print(f"  → {n} tasks migrated")

    # 5. Notes
    print("\n[5/7] Migrating investigative notes...")
    notes = load_json(JSON_FILES["notes"])
    n = migrate_keyed_items(notes, WorkspaceNote, "note_id")
    print(f"  → {n} notes migrated")

    # 6. Pinned items
    print("\n[6/7] Migrating pinned items...")
    pinned = load_json(JSON_FILES["pinned_items"])
    n = migrate_pinned_items(pinned)
    print(f"  → {n} pinned items migrated")

    # 7. Deadline configs
    print("\n[7/7] Migrating deadline configs...")
    deadlines = load_json(JSON_FILES["deadlines"])
    n = migrate_deadlines(deadlines)
    print(f"  → {n} deadline configs migrated")

    print("\n" + "=" * 60)
    print("Migration complete!")
    print("The JSON files in data/ can be archived once verified.")
    print("=" * 60)


if __name__ == "__main__":
    main()
