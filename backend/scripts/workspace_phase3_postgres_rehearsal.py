"""Rehearse the Phase 3 Dossier migration in an isolated PostgreSQL database."""

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
from psycopg import connect, sql
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import config as app_config
from config import DATABASE_URL
from services.dossier_migration import backfill_dossiers
from services.dossier_reconciliation_service import build_dossier_reconciliation_report


PRE_PHASE3_REVISION = "20260901_workspace_filters"
PHASE3_REVISION = "20260901_dossier_importance"
DATABASE_PREFIX = "owl_dossier_rehearsal_"


def _config(url: str) -> AlembicConfig:
    config = AlembicConfig(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return config


def _revision(engine: sa.Engine) -> str | None:
    with engine.connect() as connection:
        return MigrationContext.configure(connection).get_current_revision()


def _seed(engine: sa.Engine) -> dict[str, str]:
    now = datetime(2024, 6, 10, 12, 0, tzinfo=timezone.utc)
    user_id, case_id = uuid4(), uuid4()
    profile_ids = {name: uuid4() for name in ("zero", "one", "multi", "duplicate_a", "duplicate_b", "archived")}
    evidence_id, entry_id = uuid4(), uuid4()
    metadata = sa.MetaData()
    names = [
        "users", "cases", "evidence_files", "case_profiles", "case_profile_graph_node_links",
        "case_profile_evidence_links", "workspace_witnesses", "workspace_entries", "workspace_entry_links",
    ]
    tables = {name: sa.Table(name, metadata, autoload_with=engine) for name in names}
    with engine.begin() as connection:
        connection.execute(tables["users"].insert().values(
            id=user_id, email="phase3@example.test", name="Phase 3", password_hash="x",
            global_role="user", is_active=True, created_at=now, updated_at=now,
        ))
        connection.execute(tables["cases"].insert().values(
            id=case_id, title="Dossier rehearsal", status="active", archived=False,
            created_by_user_id=user_id, owner_user_id=user_id, created_at=now, updated_at=now,
        ))
        connection.execute(tables["evidence_files"].insert().values(
            id=evidence_id, case_id=case_id, original_filename="portrait.png",
            stored_path="C:/rehearsal/portrait.png", size=5, sha256="d" * 64,
            status="unprocessed", is_duplicate=False, is_relevant=False,
            processing_stale=False, transcription_speakers={}, transcription_speaker_merges={},
            tags=[], linked_entity_ids=[], metadata={}, created_at=now, updated_at=now,
        ))
        rows = []
        for name, profile_id in profile_ids.items():
            rows.append({
                "id": profile_id, "case_id": case_id, "profile_type": "person",
                "display_name": name.replace("_", " ").title(), "summary": f"Material for {name}",
                "importance": "high" if name == "one" else None,
                "created_by_user_id": user_id, "updated_by_user_id": user_id,
                "archived_at": now if name == "archived" else None,
                "archived_by_user_id": user_id if name == "archived" else None,
                "created_at": now, "updated_at": now,
            })
        connection.execute(tables["case_profiles"].insert(), rows)
        graph_rows = []
        graph_keys = {
            "one": ["person:one"], "multi": ["person:multi-a", "person:multi-b"],
            "duplicate_a": ["person:duplicate"], "duplicate_b": ["person:duplicate"],
            "archived": ["person:archived"],
        }
        for name, keys in graph_keys.items():
            for key in keys:
                graph_rows.append({
                    "id": uuid4(), "profile_id": profile_ids[name], "case_id": case_id,
                    "node_key": key, "node_name": name, "node_type": "Person",
                    "created_by_user_id": user_id, "created_at": now, "updated_at": now,
                })
        connection.execute(tables["case_profile_graph_node_links"].insert(), graph_rows)
        connection.execute(tables["case_profile_evidence_links"].insert().values(
            id=uuid4(), profile_id=profile_ids["one"], case_id=case_id,
            evidence_file_id=evidence_id, relationship_type="context", excerpt="Visible face",
            page=1, created_by_user_id=user_id, created_at=now, updated_at=now,
        ))
        connection.execute(tables["workspace_witnesses"].insert().values(
            id=uuid4(), case_id=case_id, witness_id="witness-1",
            data={
                "name": "Legacy Witness", "role": "Witness", "category": "Friendly",
                "status": "Cooperative", "credibility": "Generally reliable",
                "risk": "May become unavailable", "strategy": "Re-interview",
                "statement_summary": "Observed the meeting.",
                "interviews": [
                    {"date": "2024-02-01T10:00:00Z", "status": "completed", "statement": "First account"},
                    {"date": "2024-03-01T10:00:00Z", "status": "completed", "statement": "Follow-up account"},
                ],
            },
            created_at=now, updated_at=now,
        ))
        connection.execute(tables["workspace_entries"].insert().values(
            id=entry_id, case_id=case_id, entry_type="theory", title="Witness theory",
            body="The account supports the theory.", tags=[], lifecycle_state="proposed",
            significance=None, confidence=60, confidence_rationale=None,
            review_state="accepted", author_user_id=user_id,
            author_email="phase3@example.test", author_name="Phase 3",
            updated_by_user_id=user_id, updated_by_email="phase3@example.test",
            updated_by_name="Phase 3", version=1, source_theory_entry_id=None,
            legacy_source="workspace_theory",
            legacy_id="theory-witness", migration_metadata={}, needs_migration_review=False,
            deleted_at=None, deleted_by_user_id=None, created_at=now, updated_at=now,
        ))
        connection.execute(tables["workspace_entry_links"].insert().values(
            id=uuid4(), entry_id=entry_id, case_id=case_id, target_type="witness",
            target_id="witness-1", target_label="Legacy Witness", relationship="supports",
            source_anchor={}, metadata={}, created_by_user_id=user_id, created_at=now, updated_at=now,
        ))
    return {"case_id": str(case_id), **{f"profile_{key}": str(value) for key, value in profile_ids.items()}}


def _snapshot(engine: sa.Engine, ids: dict[str, str]) -> dict[str, object]:
    metadata = sa.MetaData()
    profiles = sa.Table("case_profiles", metadata, autoload_with=engine)
    mappings = sa.Table("dossier_legacy_mappings", metadata, autoload_with=engine)
    roles = sa.Table("dossier_roles", metadata, autoload_with=engine)
    assessments = sa.Table("dossier_assessments", metadata, autoload_with=engine)
    interviews = sa.Table("dossier_interviews", metadata, autoload_with=engine)
    entry_links = sa.Table("workspace_entry_links", metadata, autoload_with=engine)
    with engine.connect() as connection:
        by_id = {str(row.id): dict(row) for row in connection.execute(sa.select(profiles)).mappings()}
        return {
            "profile_states": {
                key.removeprefix("profile_"): {
                    "canonical_entity_key": by_id[value]["canonical_entity_key"],
                    "linkage_state": by_id[value]["linkage_state"],
                    "needs_link_review": by_id[value]["needs_link_review"],
                    "archived": by_id[value]["archived_at"] is not None,
                }
                for key, value in ids.items() if key.startswith("profile_")
            },
            "mapping_count": connection.scalar(sa.select(sa.func.count()).select_from(mappings)),
            "role_count": connection.scalar(sa.select(sa.func.count()).select_from(roles)),
            "assessment_count": connection.scalar(sa.select(sa.func.count()).select_from(assessments)),
            "interview_count": connection.scalar(sa.select(sa.func.count()).select_from(interviews)),
            "unrepointed_witness_links": connection.scalar(sa.select(sa.func.count()).select_from(entry_links).where(entry_links.c.target_type == "witness")),
            "repointed_dossier_links": connection.scalar(sa.select(sa.func.count()).select_from(entry_links).where(entry_links.c.target_type == "dossier")),
        }


def main() -> int:
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is required")
    source = make_url(DATABASE_URL)
    if not source.drivername.startswith("postgresql"):
        raise RuntimeError("PostgreSQL is required")
    database_name = f"{DATABASE_PREFIX}{uuid4().hex[:12]}"
    target = source.set(database=database_name)
    admin = source.set(database="postgres", drivername="postgresql")
    target_text = target.render_as_string(hide_password=False)
    admin_text = admin.render_as_string(hide_password=False)
    output = BACKEND_DIR.parent / "output" / "workspace-redesign" / "phase3-postgres-migration-rehearsal.json"
    report: dict[str, object] = {"schema_version": 1, "database_prefix_guard": DATABASE_PREFIX, "cleanup": {"dropped": False}}
    engine = None
    previous_env, previous_config = os.environ.get("DATABASE_URL"), app_config.DATABASE_URL
    with connect(admin_text, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database_name)))
    try:
        os.environ["DATABASE_URL"] = target_text; app_config.DATABASE_URL = target_text
        config = _config(target_text)
        heads = ScriptDirectory.from_config(config).get_heads()
        report["alembic_heads"] = heads
        engine = sa.create_engine(target_text, pool_pre_ping=True)
        command.upgrade(config, PHASE3_REVISION)
        report["empty_upgrade_revision"] = _revision(engine)
        with Session(engine) as db:
            report["empty_reconciliation"] = build_dossier_reconciliation_report(db)
        command.downgrade(config, PRE_PHASE3_REVISION)
        ids = _seed(engine)
        command.upgrade(config, PHASE3_REVISION)
        report["representative_upgrade_revision"] = _revision(engine)
        with Session(engine) as db:
            report["representative_reconciliation"] = build_dossier_reconciliation_report(db)
        first = _snapshot(engine, ids); report["representative_snapshot"] = first
        with engine.begin() as connection:
            report["idempotent_rerun"] = backfill_dossiers(connection)
        report["idempotent_snapshot_stable"] = first == _snapshot(engine, ids)
        command.downgrade(config, PRE_PHASE3_REVISION)
        report["downgrade_revision"] = _revision(engine)
        command.upgrade(config, PHASE3_REVISION)
        report["reupgrade_revision"] = _revision(engine)
        second = _snapshot(engine, ids); report["reupgrade_snapshot"] = second
        with Session(engine) as db:
            report["reupgrade_reconciliation"] = build_dossier_reconciliation_report(db)
        states = second["profile_states"]
        report["passed"] = (
            len(heads) == 1
            and report["empty_upgrade_revision"] == PHASE3_REVISION
            and report["representative_upgrade_revision"] == PHASE3_REVISION
            and report["downgrade_revision"] == PRE_PHASE3_REVISION
            and report["reupgrade_revision"] == PHASE3_REVISION
            and states["zero"]["linkage_state"] == "unlinked"
            and states["one"]["canonical_entity_key"] == "person:one"
            and states["multi"]["needs_link_review"] is True
            and states["duplicate_a"]["needs_link_review"] is True
            and states["duplicate_b"]["needs_link_review"] is True
            and states["archived"]["archived"] is True
            and second["interview_count"] == 2
            and second["unrepointed_witness_links"] == 0
            and second["repointed_dossier_links"] == 1
            and report["idempotent_snapshot_stable"] is True
            and report["reupgrade_reconciliation"]["passed"] is True
        )
    finally:
        if engine is not None: engine.dispose()
        if previous_env is None: os.environ.pop("DATABASE_URL", None)
        else: os.environ["DATABASE_URL"] = previous_env
        app_config.DATABASE_URL = previous_config
        with connect(admin_text, autocommit=True) as connection:
            connection.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s AND pid <> pg_backend_pid()", (database_name,))
            if not database_name.startswith(DATABASE_PREFIX): raise RuntimeError("Unsafe database name")
            connection.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(database_name)))
        report["cleanup"] = {"dropped": True}
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 0 if report.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
