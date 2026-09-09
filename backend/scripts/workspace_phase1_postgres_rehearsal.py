"""Rehearse the Phase 1 migration in an isolated disposable PostgreSQL DB."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import sqlalchemy as sa
from alembic import command
from alembic.config import Config as AlembicConfig
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from psycopg import connect
from psycopg import sql
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import config as app_config
from config import DATABASE_URL
from postgres.backfills.workspace_entries import backfill_workspace_entries
from postgres.models.case import Case
from postgres.models.case_profile import (
    CaseProfileFindingLink,
    CaseProfileNoteLink,
)
from postgres.models.evidence import EvidenceFile
from postgres.models.notebook import NotebookNote, NotebookNoteLink
from postgres.models.user import User
from postgres.models.workspace import WorkspaceFinding, WorkspaceNote, WorkspaceTheory
from services.workspace_entry_reconciliation_service import (
    build_workspace_entry_reconciliation_report,
)


PRE_PHASE1_REVISION = "20260807_deepseek"
PHASE1_REVISION = "20260901_workspace_entries"
DATABASE_PREFIX = "owl_workspace_rehearsal_"


def _alembic_config(target_url: str) -> AlembicConfig:
    config = AlembicConfig(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", target_url.replace("%", "%%"))
    return config


def _current_revision(engine: sa.Engine) -> str | None:
    with engine.connect() as connection:
        return MigrationContext.configure(connection).get_current_revision()


def _semantic_reconciliation(report: dict[str, object]) -> dict[str, object]:
    """Remove generated row IDs while retaining every durable comparison key."""

    normalized = json.loads(json.dumps(report))
    for link in normalized.get("unresolved_links", []):
        link.pop("link_id", None)
    return normalized


def _seed_representative_legacy_data(engine: sa.Engine) -> None:
    user_id = uuid4()
    case_id = uuid4()
    evidence_id = uuid4()
    notebook_id = uuid4()
    deleted_notebook_id = uuid4()
    profile_id = uuid4()
    created_at = datetime(2024, 2, 3, 10, 11, 12, tzinfo=timezone.utc)
    updated_at = datetime(2024, 3, 4, 13, 14, 15, tzinfo=timezone.utc)
    deleted_at = datetime(2024, 4, 5, 16, 17, 18, tzinfo=timezone.utc)

    with engine.begin() as connection:
        # The current CaseProfile ORM model has Phase 3 client-side defaults for
        # columns that intentionally do not exist at the pre-Phase 1 seed point.
        # Reflect the historical table so this rehearsal remains valid as later
        # expand migrations evolve the model.
        historical_case_profiles = sa.Table(
            "case_profiles", sa.MetaData(), autoload_with=connection
        )
        connection.execute(
            User.__table__.insert().values(
                id=user_id,
                email="rehearsal@example.test",
                name="Migration rehearsal",
                password_hash="not-a-real-password",
                global_role="user",
                is_active=True,
                created_at=created_at,
                updated_at=updated_at,
            )
        )
        connection.execute(
            Case.__table__.insert().values(
                id=case_id,
                title="Representative migration rehearsal",
                status="active",
                archived=False,
                created_by_user_id=user_id,
                owner_user_id=user_id,
                created_at=created_at,
                updated_at=updated_at,
            )
        )
        connection.execute(
            EvidenceFile.__table__.insert().values(
                id=evidence_id,
                case_id=case_id,
                original_filename="ledger.pdf",
                stored_path="C:/rehearsal/ledger.pdf",
                size=100,
                sha256="a" * 64,
                status="processed",
                legacy_id="legacy-ledger",
                is_duplicate=False,
                is_relevant=False,
                processing_stale=False,
                transcription_speakers={},
                transcription_speaker_merges={},
                created_at=created_at,
                updated_at=updated_at,
            )
        )
        connection.execute(
            NotebookNote.__table__.insert(),
            [
                {
                    "id": notebook_id,
                    "case_id": case_id,
                    "author_user_id": user_id,
                    "author_email": "rehearsal@example.test",
                    "author_name": "Migration rehearsal",
                    "title": "Notebook title",
                    "body": "Notebook body",
                    "tags": ["interview"],
                    "visibility": "case",
                    "deleted_at": None,
                    "created_at": created_at,
                    "updated_at": updated_at,
                },
                {
                    "id": deleted_notebook_id,
                    "case_id": case_id,
                    "author_user_id": None,
                    "author_email": "former@example.test",
                    "author_name": "Former investigator",
                    "title": None,
                    "body": "Recoverable deleted note",
                    "tags": [],
                    "visibility": "case",
                    "deleted_at": deleted_at,
                    "created_at": created_at,
                    "updated_at": updated_at,
                },
            ],
        )
        connection.execute(
            NotebookNoteLink.__table__.insert().values(
                id=uuid4(),
                note_id=notebook_id,
                case_id=case_id,
                target_type="document",
                target_id="ledger.pdf",
                target_label="Ledger",
                metadata={"relationship": "supporting", "source_anchor": {"page": 8}},
                created_at=created_at,
                updated_at=updated_at,
            )
        )
        connection.execute(
            WorkspaceNote.__table__.insert().values(
                id=uuid4(),
                case_id=case_id,
                note_id="legacy-note-1",
                data={
                    "title": "Legacy note",
                    "content": "Legacy note body",
                    "linked_evidence_ids": ["legacy-ledger"],
                    "linked_entity_keys": ["company:acme"],
                },
                created_at=created_at,
                updated_at=updated_at,
            )
        )
        connection.execute(
            WorkspaceFinding.__table__.insert().values(
                id=uuid4(),
                case_id=case_id,
                finding_id="legacy-finding-1",
                data={
                    "content": "Finding retained for human review",
                    "priority": "urgent",
                },
                created_at=created_at,
                updated_at=updated_at,
            )
        )
        connection.execute(
            WorkspaceTheory.__table__.insert().values(
                id=uuid4(),
                case_id=case_id,
                theory_id="legacy-theory-1",
                data={
                    "title": "Concealed ownership",
                    "hypothesis": "Henry controls Acme.",
                    "confidence_score": 83,
                    "attached_document_ids": ["ledger.pdf"],
                    "attached_task_ids": ["legacy-task-1"],
                },
                created_at=created_at,
                updated_at=updated_at,
            )
        )
        connection.execute(
            historical_case_profiles.insert().values(
                id=profile_id,
                case_id=case_id,
                profile_type="person",
                display_name="Henry",
                created_by_user_id=user_id,
                updated_by_user_id=user_id,
                created_at=created_at,
                updated_at=updated_at,
            )
        )
        connection.execute(
            CaseProfileNoteLink.__table__.insert().values(
                id=uuid4(),
                profile_id=profile_id,
                case_id=case_id,
                note_id="legacy-note-1",
                relationship_type="context",
                created_by_user_id=user_id,
                created_at=created_at,
                updated_at=updated_at,
            )
        )
        connection.execute(
            CaseProfileFindingLink.__table__.insert().values(
                id=uuid4(),
                profile_id=profile_id,
                case_id=case_id,
                finding_id="legacy-finding-1",
                relationship_type="about",
                created_by_user_id=user_id,
                created_at=created_at,
                updated_at=updated_at,
            )
        )


def main() -> int:
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is required for the PostgreSQL rehearsal")
    source_url = make_url(DATABASE_URL)
    if not source_url.drivername.startswith("postgresql"):
        raise RuntimeError("The migration rehearsal requires PostgreSQL")

    database_name = f"{DATABASE_PREFIX}{uuid4().hex[:12]}"
    if not database_name.startswith(DATABASE_PREFIX):
        raise RuntimeError("Refusing to create an unscoped rehearsal database")
    target_url = source_url.set(database=database_name)
    admin_url = source_url.set(database="postgres")
    target_url_text = target_url.render_as_string(hide_password=False)
    admin_url_text = admin_url.set(drivername="postgresql").render_as_string(
        hide_password=False
    )
    output_path = (
        BACKEND_DIR.parent
        / "output"
        / "workspace-redesign"
        / "phase1-postgres-migration-rehearsal.json"
    )
    report: dict[str, object] = {
        "schema_version": 1,
        "database": database_name,
        "database_prefix_guard": DATABASE_PREFIX,
        "cleanup": {"dropped": False},
    }
    engine: sa.Engine | None = None
    previous_database_url = os.environ.get("DATABASE_URL")
    previous_config_url = app_config.DATABASE_URL

    with connect(admin_url_text, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database_name)))
    try:
        os.environ["DATABASE_URL"] = target_url_text
        app_config.DATABASE_URL = target_url_text
        alembic_config = _alembic_config(target_url_text)
        script = ScriptDirectory.from_config(alembic_config)
        heads = script.get_heads()
        if len(heads) != 1:
            raise RuntimeError(f"Expected one Alembic head, found {heads}")
        report["alembic_heads"] = heads

        engine = sa.create_engine(target_url_text, pool_pre_ping=True)
        command.upgrade(alembic_config, PHASE1_REVISION)
        report["empty_upgrade_revision"] = _current_revision(engine)
        with Session(engine) as db:
            report["empty_reconciliation"] = build_workspace_entry_reconciliation_report(db)

        command.downgrade(alembic_config, PRE_PHASE1_REVISION)
        report["pre_seed_revision"] = _current_revision(engine)
        _seed_representative_legacy_data(engine)
        command.upgrade(alembic_config, PHASE1_REVISION)
        report["representative_upgrade_revision"] = _current_revision(engine)
        with Session(engine) as db:
            first_reconciliation = build_workspace_entry_reconciliation_report(db)
        report["representative_reconciliation"] = first_reconciliation

        with engine.begin() as connection:
            report["idempotent_rerun"] = backfill_workspace_entries(connection)

        command.downgrade(alembic_config, PRE_PHASE1_REVISION)
        report["downgrade_revision"] = _current_revision(engine)
        command.upgrade(alembic_config, PHASE1_REVISION)
        report["reupgrade_revision"] = _current_revision(engine)
        with Session(engine) as db:
            second_reconciliation = build_workspace_entry_reconciliation_report(db)
        report["reupgrade_reconciliation"] = second_reconciliation
        report["reconciliation_stable"] = _semantic_reconciliation(
            first_reconciliation
        ) == _semantic_reconciliation(second_reconciliation)

        summary = second_reconciliation["summary"]
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
        report["passed"] = (
            len(heads) == 1
            and report["empty_upgrade_revision"] == PHASE1_REVISION
            and report["representative_upgrade_revision"] == PHASE1_REVISION
            and report["downgrade_revision"] == PRE_PHASE1_REVISION
            and report["reupgrade_revision"] == PHASE1_REVISION
            and report["reconciliation_stable"] is True
            and unexpected == 0
            and report["idempotent_rerun"]["summary"]["migrated_entries"] == 0
        )
    finally:
        if engine is not None:
            engine.dispose()
        if previous_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous_database_url
        app_config.DATABASE_URL = previous_config_url
        with connect(admin_url_text, autocommit=True) as admin:
            admin.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid()",
                (database_name,),
            )
            if not database_name.startswith(DATABASE_PREFIX):
                raise RuntimeError("Refusing to drop an unscoped database")
            admin.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(database_name)))
        report["cleanup"] = {"dropped": True}
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
