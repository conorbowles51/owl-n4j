"""Prove a pre-contract Workspace backup restores and boots in isolation."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import sqlalchemy as sa
from alembic import command
from alembic.config import Config as AlembicConfig
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from psycopg import connect, sql
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session


BACKEND_DIR = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import config as app_config
from config import DATABASE_URL
from postgres.models.case import Case
from postgres.models.case_context import CaseContext, CaseMandateVersion
from postgres.models.case_deadline import CaseDeadline
from postgres.models.case_profile import CaseProfile
from postgres.models.dossier import DossierInterview, DossierRole
from postgres.models.evidence import EvidenceFile
from postgres.models.user import User
from postgres.models.work import CaseTask, SharedEvidencePin
from postgres.models.workspace_entry import (
    WorkspaceEntry,
    WorkspaceEntryEvent,
    WorkspaceEntryRevision,
)
from services.workspace_cutover_reconciliation_service import (
    build_workspace_cutover_reconciliation_report,
)
from services.workspace_preflight_service import build_workspace_preflight_report


DATABASE_PREFIX = "owl_workspace_cutover_restore_"
BACKUP_PATH = (
    REPOSITORY_ROOT
    / "output"
    / "workspace-redesign"
    / "phase8-pre-contract-fixture.dump"
)
REPORT_PATH = (
    REPOSITORY_ROOT
    / "output"
    / "workspace-redesign"
    / "phase8-backup-restore.json"
)


def _alembic_config(url: str) -> AlembicConfig:
    config = AlembicConfig(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return config


def _revision(engine: sa.Engine) -> str | None:
    with engine.connect() as connection:
        return MigrationContext.configure(connection).get_current_revision()


def _entry_history(entry: WorkspaceEntry, user: User, created_at: datetime):
    snapshot = {
        "entry_type": entry.entry_type,
        "title": entry.title,
        "body": entry.body,
        "tags": entry.tags,
        "lifecycle_state": entry.lifecycle_state,
        "significance": entry.significance,
        "confidence": entry.confidence,
        "confidence_rationale": entry.confidence_rationale,
        "review_state": entry.review_state,
        "version": 1,
        "deleted_at": None,
    }
    return (
        WorkspaceEntryRevision(
            entry_id=entry.id,
            case_id=entry.case_id,
            revision_number=1,
            entry_type=entry.entry_type,
            title=entry.title,
            body=entry.body,
            tags=entry.tags,
            lifecycle_state=entry.lifecycle_state,
            significance=entry.significance,
            confidence=entry.confidence,
            confidence_rationale=entry.confidence_rationale,
            review_state=entry.review_state,
            editor_user_id=user.id,
            editor_email=user.email,
            editor_name=user.name,
            created_at=created_at,
        ),
        WorkspaceEntryEvent(
            entry_id=entry.id,
            case_id=entry.case_id,
            event_type="created",
            before_state={},
            after_state=snapshot,
            actor_user_id=user.id,
            actor_email=user.email,
            actor_name=user.name,
            created_at=created_at,
        ),
    )


def _seed(engine: sa.Engine) -> dict[str, int]:
    now = datetime(2026, 9, 2, 9, 0, tzinfo=timezone.utc)
    counts = {"cases": 3, "entries": 0, "tasks": 0, "dossiers": 0, "evidence": 0}
    with Session(engine) as db:
        owner = User(
            id=uuid4(),
            email="phase8-backup-owner@example.test",
            name="Phase 8 Backup Owner",
            password_hash="x",
        )
        db.add(owner)
        cases = {
            shape: Case(
                id=uuid4(),
                title=f"Phase 8 {shape} restore case",
                created_by_user_id=owner.id,
                owner_user_id=owner.id,
            )
            for shape in ("empty", "small", "scale")
        }
        db.add_all(cases.values())
        db.flush()

        for shape in ("small", "scale"):
            mandate = CaseMandateVersion(
                id=uuid4(),
                case_id=cases[shape].id,
                version_number=1,
                objective=f"Verify the {shape} restore case",
                key_questions=["Was every canonical record restored?"],
                author_user_id=owner.id,
                created_at=now,
            )
            db.add(mandate)
            db.flush()
            db.add(
                CaseContext(
                    id=uuid4(),
                    case_id=cases[shape].id,
                    case_summary=f"Synthetic {shape} backup fixture",
                    investigation_type="general investigation",
                    active_template_key="generic",
                    active_mandate_version_id=mandate.id,
                    created_by_user_id=owner.id,
                    updated_by_user_id=owner.id,
                )
            )

        evidence_by_case: dict[str, list[EvidenceFile]] = {"small": [], "scale": []}
        for shape, total in (("small", 4), ("scale", 400)):
            for index in range(total):
                evidence = EvidenceFile(
                    id=uuid4(),
                    case_id=cases[shape].id,
                    original_filename=f"{shape}-evidence-{index:04d}.pdf",
                    stored_path=f"/synthetic/{shape}/evidence-{index:04d}.pdf",
                    size=1024 + index,
                    sha256=hashlib.sha256(f"{shape}:{index}".encode()).hexdigest(),
                    status="processed",
                    created_by_id=owner.id,
                    metadata_={"synthetic_backup_fixture": True},
                )
                evidence_by_case[shape].append(evidence)
            db.add_all(evidence_by_case[shape])
            counts["evidence"] += total

        for shape, total in (("small", 3), ("scale", 1000)):
            for index in range(total):
                entry_type = ("note", "finding", "theory")[index % 3]
                created_at = now - timedelta(seconds=index)
                entry = WorkspaceEntry(
                    id=uuid4(),
                    case_id=cases[shape].id,
                    entry_type=entry_type,
                    title=None if entry_type == "note" else f"{shape} {entry_type} {index}",
                    body=f"Synthetic restored casework record {index}.",
                    tags=["backup", shape],
                    lifecycle_state=(
                        None
                        if entry_type == "note"
                        else "active"
                        if entry_type == "finding"
                        else "investigating"
                    ),
                    significance="medium" if entry_type == "finding" else None,
                    confidence=60 if entry_type == "theory" else None,
                    review_state="accepted",
                    author_user_id=owner.id,
                    author_email=owner.email,
                    author_name=owner.name,
                    updated_by_user_id=owner.id,
                    updated_by_email=owner.email,
                    updated_by_name=owner.name,
                    version=1,
                    created_at=created_at,
                    updated_at=created_at,
                )
                revision, event = _entry_history(entry, owner, created_at)
                db.add_all([entry, revision, event])
            counts["entries"] += total

        for shape, total in (("small", 2), ("scale", 1000)):
            deadline = CaseDeadline(
                id=uuid4(),
                case_id=cases[shape].id,
                name=f"{shape.title()} review deadline",
                due_date=date(2026, 10, 1),
                created_by_user_id=owner.id,
            )
            db.add(deadline)
            for index in range(total):
                db.add(
                    CaseTask(
                        id=uuid4(),
                        case_id=cases[shape].id,
                        title=f"{shape} task {index:04d}",
                        status="done" if index % 5 == 0 else "todo",
                        priority="high" if index % 10 == 0 else "standard",
                        due_at=now + timedelta(days=index % 30),
                        deadline_id=deadline.id if index % 20 == 0 else None,
                        created_by_user_id=owner.id,
                        updated_by_user_id=owner.id,
                    )
                )
            counts["tasks"] += total

        for shape, total in (("small", 2), ("scale", 50)):
            for index in range(total):
                dossier = CaseProfile(
                    id=uuid4(),
                    case_id=cases[shape].id,
                    profile_type="person",
                    display_name=f"{shape.title()} subject {index:03d}",
                    summary="Synthetic Dossier restored from the backup.",
                    linkage_state="unlinked",
                    status="active",
                    created_by_user_id=owner.id,
                    updated_by_user_id=owner.id,
                )
                db.add(dossier)
                db.add(
                    DossierRole(
                        id=uuid4(),
                        dossier_id=dossier.id,
                        case_id=cases[shape].id,
                        name="Subject",
                        normalized_name="subject",
                        is_builtin=True,
                        created_by_user_id=owner.id,
                    )
                )
                if index < min(total, 10):
                    db.add(
                        DossierInterview(
                            id=uuid4(),
                            dossier_id=dossier.id,
                            case_id=cases[shape].id,
                            interview_date=now + timedelta(days=index),
                            participants=[dossier.display_name],
                            interviewer_user_ids=[str(owner.id)],
                            status="completed",
                            working_notes="Synthetic interview record.",
                            created_by_user_id=owner.id,
                            updated_by_user_id=owner.id,
                        )
                    )
            counts["dossiers"] += total

        for shape, evidence_rows in evidence_by_case.items():
            for evidence in evidence_rows[: min(100, len(evidence_rows))]:
                db.add(
                    SharedEvidencePin(
                        id=uuid4(),
                        case_id=cases[shape].id,
                        evidence_file_id=evidence.id,
                        pinned_by_user_id=owner.id,
                        legacy_metadata={},
                    )
                )
        db.commit()
    return counts


def _database_evidence(engine: sa.Engine) -> dict[str, object]:
    with Session(engine) as db:
        reconciliation = build_workspace_cutover_reconciliation_report(db)
        preflight = build_workspace_preflight_report(db)
    with engine.connect() as connection:
        counts = {
            table: int(connection.scalar(sa.text(f"SELECT count(*) FROM {table}")) or 0)
            for table in (
                "cases",
                "workspace_entries",
                "workspace_entry_revisions",
                "workspace_entry_events",
                "case_profiles",
                "dossier_interviews",
                "case_tasks",
                "case_deadlines",
                "shared_evidence_pins",
            )
        }
    return {
        "revision": _revision(engine),
        "counts": counts,
        "preflight_summary": preflight["summary"],
        "reconciliation_summary": reconciliation["summary"],
        "reconciliation_passed": reconciliation["passed"],
    }


def _tool_environment(source_url) -> dict[str, str]:
    environment = os.environ.copy()
    if source_url.password:
        environment["PGPASSWORD"] = source_url.password
    return environment


def _database_args(url, database: str) -> list[str]:
    args = ["--dbname", database]
    if url.host:
        args.extend(["--host", url.host])
    if url.port:
        args.extend(["--port", str(url.port)])
    if url.username:
        args.extend(["--username", url.username])
    return args


def _run_checked(args: list[str], *, env: dict[str, str], cwd: Path | None = None) -> str:
    result = subprocess.run(
        args,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(
            f"{Path(args[0]).name} failed with exit {result.returncode}: {result.stderr.strip()}"
        )
    return result.stdout.strip()


def _restore_backup(
    args: list[str], *, env: dict[str, str]
) -> dict[str, object]:
    """Restore an archive, tolerating only the pg18-to-pg16 session-setting warning.

    PostgreSQL 18's client writes ``SET transaction_timeout = 0`` into custom
    archives. PostgreSQL 16 does not know that setting, but pg_restore continues
    and restores the complete archive. We accept precisely that one non-data
    error and prove the restored schema and contents below; every other restore
    error remains fatal.
    """

    result = subprocess.run(
        args,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    stderr_lines = [line.strip() for line in result.stderr.splitlines() if line.strip()]
    allowed_fragments = (
        'unrecognized configuration parameter "transaction_timeout"',
        "Command was: SET transaction_timeout = 0;",
        "pg_restore: warning: errors ignored on restore: 1",
    )
    unexpected = [
        line
        for line in stderr_lines
        if not any(fragment in line for fragment in allowed_fragments)
    ]
    compatibility_warning = bool(stderr_lines) and not unexpected
    if result.returncode and not compatibility_warning:
        raise RuntimeError(
            f"{Path(args[0]).name} failed with exit {result.returncode}: "
            f"{result.stderr.strip()}"
        )
    return {
        "return_code": result.returncode,
        "compatibility_warning_accepted": compatibility_warning,
        "warning": (
            "PostgreSQL 18 pg_restore emitted transaction_timeout while restoring "
            "to PostgreSQL 16; the unsupported session setting was ignored."
            if compatibility_warning
            else None
        ),
    }


def main() -> int:
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is required")
    source_url = make_url(DATABASE_URL)
    if not source_url.drivername.startswith("postgresql"):
        raise RuntimeError("PostgreSQL is required")
    pg_dump = shutil.which("pg_dump")
    pg_restore = shutil.which("pg_restore")
    if not pg_dump or not pg_restore:
        raise RuntimeError("pg_dump and pg_restore are required")

    suffix = uuid4().hex[:12]
    source_name = f"{DATABASE_PREFIX}source_{suffix}"
    restored_name = f"{DATABASE_PREFIX}target_{suffix}"
    admin_url = source_url.set(database="postgres", drivername="postgresql")
    source_db_url = source_url.set(database=source_name)
    restored_db_url = source_url.set(database=restored_name)
    admin_text = admin_url.render_as_string(hide_password=False)
    source_text = source_db_url.render_as_string(hide_password=False)
    restored_text = restored_db_url.render_as_string(hide_password=False)
    tool_env = _tool_environment(source_url)
    BACKUP_PATH.parent.mkdir(parents=True, exist_ok=True)
    report: dict[str, object] = {
        "schema_version": 1,
        "fixture_only": True,
        "cleanup": {"source_dropped": False, "target_dropped": False},
    }
    source_engine: sa.Engine | None = None
    restored_engine: sa.Engine | None = None
    previous_env = os.environ.get("DATABASE_URL")
    previous_config = app_config.DATABASE_URL

    with connect(admin_text, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(source_name)))
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(restored_name)))
    try:
        os.environ["DATABASE_URL"] = source_text
        app_config.DATABASE_URL = source_text
        config = _alembic_config(source_text)
        heads = ScriptDirectory.from_config(config).get_heads()
        report["alembic_heads"] = heads
        command.upgrade(config, "head")
        source_engine = sa.create_engine(source_text, pool_pre_ping=True)
        report["seed_counts"] = _seed(source_engine)
        report["source"] = _database_evidence(source_engine)

        _run_checked(
            [
                pg_dump,
                *_database_args(source_url, source_name),
                "--format=custom",
                "--no-owner",
                "--no-privileges",
                "--file",
                str(BACKUP_PATH),
            ],
            env=tool_env,
        )
        backup_digest = hashlib.sha256(BACKUP_PATH.read_bytes()).hexdigest()
        report["backup"] = {
            "format": "PostgreSQL custom",
            "sha256": backup_digest,
            "size_bytes": BACKUP_PATH.stat().st_size,
            "path": str(BACKUP_PATH.relative_to(REPOSITORY_ROOT)),
        }
        report["restore_process"] = _restore_backup(
            [
                pg_restore,
                *_database_args(source_url, restored_name),
                "--no-owner",
                "--no-privileges",
                str(BACKUP_PATH),
            ],
            env=tool_env,
        )
        restored_engine = sa.create_engine(restored_text, pool_pre_ping=True)
        report["restored"] = _database_evidence(restored_engine)

        boot_env = tool_env.copy()
        boot_env["DATABASE_URL"] = restored_text
        boot_output = _run_checked(
            [
                sys.executable,
                "-c",
                "from main import app; paths={r.path for r in app.routes}; "
                "assert '/api/workspace/{case_id}/context' in paths; "
                "assert '/api/workspace/{case_id}/entries' in paths; "
                "assert '/api/workspace/{case_id}/work' in paths; "
                "assert '/api/dossiers/{dossier_id}/evidence' in paths; "
                "assert '/api/dossiers/{dossier_id}/evidence/{evidence_file_id}' in paths; "
                "assert '/api/case-profiles' not in paths; "
                "assert '/api/evidence/entity-links/add' not in paths; "
                "print(len(paths))",
            ],
            env=boot_env,
            cwd=BACKEND_DIR,
        )
        report["boot"] = {"passed": True, "route_count": int(boot_output.splitlines()[-1])}
        report["passed"] = (
            len(heads) == 1
            and report["source"] == report["restored"]
            and bool(report["source"]["reconciliation_passed"])
            and bool(report["restored"]["reconciliation_passed"])
            and report["boot"]["passed"] is True
            and report["backup"]["size_bytes"] > 0
        )
    finally:
        if previous_env is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous_env
        app_config.DATABASE_URL = previous_config
        if source_engine is not None:
            source_engine.dispose()
        if restored_engine is not None:
            restored_engine.dispose()
        with connect(admin_text, autocommit=True) as connection:
            for name, key in (
                (source_name, "source_dropped"),
                (restored_name, "target_dropped"),
            ):
                if not name.startswith(DATABASE_PREFIX):
                    raise RuntimeError("Refusing to drop an unscoped database")
                connection.execute(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = %s AND pid <> pg_backend_pid()",
                    (name,),
                )
                connection.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(name)))
                report["cleanup"][key] = True
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(
            json.dumps(report, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 0 if report.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
