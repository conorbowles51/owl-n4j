"""Rehearse Phase 7 AI output migration and recoverable rollback on PostgreSQL."""

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


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import config as app_config
from config import DATABASE_URL


PRE_PHASE7_REVISION = "20260902_workspace_attention"
PHASE7_REVISION = "20260902_workspace_ai"
DATABASE_PREFIX = "owl_workspace_ai_rehearsal_"


def _config(url: str) -> AlembicConfig:
    config = AlembicConfig(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return config


def _revision(engine: sa.Engine) -> str | None:
    with engine.connect() as connection:
        return MigrationContext.configure(connection).get_current_revision()


def _seed(engine: sa.Engine) -> dict[str, str]:
    now = datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc)
    ids = {key: str(uuid4()) for key in ("user", "case", "dossier", "mandate", "context", "legacy_output", "assessment")}
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO users (id,email,name,password_hash,global_role,is_active,created_at,updated_at) "
                "VALUES (:id,'phase7-owner@example.test','Phase 7 Owner','x','user',true,:now,:now)"
            ),
            {"id": ids["user"], "now": now},
        )
        connection.execute(
            sa.text(
                "INSERT INTO cases (id,title,created_by_user_id,owner_user_id,created_at,updated_at) "
                "VALUES (:id,'Phase 7 migration case',:user,:user,:now,:now)"
            ),
            {"id": ids["case"], "user": ids["user"], "now": now},
        )
        connection.execute(
            sa.text(
                "INSERT INTO case_profiles "
                "(id,case_id,profile_type,display_name,linkage_state,status,needs_link_review,graph_entity_deleted,created_by_user_id,updated_by_user_id,created_at,updated_at) "
                "VALUES (:id,:case_id,'person','Migration witness','unlinked','active',false,false,:user,:user,:now,:now)"
            ),
            {"id": ids["dossier"], "case_id": ids["case"], "user": ids["user"], "now": now},
        )
        connection.execute(
            sa.text(
                "INSERT INTO case_mandate_versions "
                "(id,case_id,version_number,objective,key_questions,author_user_id,created_at) "
                "VALUES (:id,:case_id,1,'Test both directions',CAST('[]' AS jsonb),:user,:now)"
            ),
            {"id": ids["mandate"], "case_id": ids["case"], "user": ids["user"], "now": now},
        )
        connection.execute(
            sa.text(
                "INSERT INTO case_contexts "
                "(id,case_id,active_template_key,active_mandate_version_id,created_by_user_id,updated_by_user_id,created_at,updated_at) "
                "VALUES (:id,:case_id,'generic',:mandate,:user,:user,:now,:now)"
            ),
            {"id": ids["context"], "case_id": ids["case"], "mandate": ids["mandate"], "user": ids["user"], "now": now},
        )
        connection.execute(
            sa.text(
                "INSERT INTO dossier_assessments "
                "(id,dossier_id,case_id,category,content,author_user_id,updated_by_user_id,created_at,updated_at) "
                "VALUES (:id,:dossier,:case_id,'legacy','Manually pasted legacy analysis',:user,:user,:now,:now)"
            ),
            {"id": ids["assessment"], "dossier": ids["dossier"], "case_id": ids["case"], "user": ids["user"], "now": now},
        )
        connection.execute(
            sa.text(
                "INSERT INTO dossier_generated_outputs "
                "(id,dossier_id,case_id,output_type,version,content,citations,review_status,mandate_version_id,created_at,updated_at) "
                "VALUES (:id,:dossier,:case_id,'legacy_summary',1,'Old generated text',CAST('[]' AS jsonb),'pending_review',:mandate,:now,:now)"
            ),
            {"id": ids["legacy_output"], "dossier": ids["dossier"], "case_id": ids["case"], "mandate": ids["mandate"], "now": now},
        )
    return ids


def _legacy_snapshot(engine: sa.Engine, ids: dict[str, str]) -> dict[str, object]:
    with engine.connect() as connection:
        assessment = connection.execute(
            sa.text("SELECT category,content,author_user_id,created_at FROM dossier_assessments WHERE id=:id"),
            {"id": ids["assessment"]},
        ).mappings().one()
        output = connection.execute(
            sa.text("SELECT output_type,version,content,review_status,mandate_version_id FROM dossier_generated_outputs WHERE id=:id"),
            {"id": ids["legacy_output"]},
        ).mappings().one()
    return json.loads(json.dumps({"assessment": dict(assessment), "legacy_output": dict(output)}, default=str))


def _insert_canonical_output(engine: sa.Engine, ids: dict[str, str]) -> str:
    output_id = str(uuid4())
    now = datetime(2026, 9, 2, 12, 30, tzinfo=timezone.utc)
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO workspace_ai_outputs "
                "(id,case_id,target_type,target_id,output_type,version,job_status,review_status,citation_status,progress,cancel_requested,content,citations,source_set,generation_input,proposed_actions,accepted_targets,model_metadata,mandate_version_id,requested_by_user_id,reviewed_by_user_id,completed_at,reviewed_at,created_at,updated_at) "
                "VALUES (:id,:case_id,'dossier',:dossier,'statement_summary',1,'completed','accepted','valid',100,false,CAST(:content AS jsonb),CAST(:citations AS jsonb),CAST(:sources AS jsonb),CAST('{}' AS jsonb),CAST('[]' AS jsonb),CAST(:targets AS jsonb),CAST(:model AS jsonb),:mandate,:user,:user,:now,:now,:now,:now)"
            ),
            {
                "id": output_id,
                "case_id": ids["case"],
                "dossier": ids["dossier"],
                "mandate": ids["mandate"],
                "user": ids["user"],
                "now": now,
                "content": json.dumps({"headline": "Reviewed", "claims": [{"text": "Cited", "citation_ids": ["S1"]}]}),
                "citations": json.dumps([{"source_id": "S1", "evidence_file_id": str(uuid4())}]),
                "sources": json.dumps([{"source_id": "S1", "content_hash": "abc"}]),
                "targets": json.dumps([{"target_type": "dossier_assessment", "target_id": ids["assessment"]}]),
                "model": json.dumps({"provider": "test", "model_id": "stub"}),
            },
        )
        connection.execute(
            sa.text(
                "UPDATE dossier_assessments SET provenance_type='ai_assisted', generated_output_id=:output "
                "WHERE id=:assessment"
            ),
            {"output": output_id, "assessment": ids["assessment"]},
        )
    return output_id


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
    output_path = BACKEND_DIR.parent / "output" / "workspace-redesign" / "phase7-postgres-migration-rehearsal.json"
    report: dict[str, object] = {"schema_version": 1, "cleanup": {"dropped": False}}
    engine: sa.Engine | None = None
    previous_env, previous_config = os.environ.get("DATABASE_URL"), app_config.DATABASE_URL
    with connect(admin_text, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database_name)))
    try:
        os.environ["DATABASE_URL"] = target_text
        app_config.DATABASE_URL = target_text
        config = _config(target_text)
        heads = ScriptDirectory.from_config(config).get_heads()
        report["alembic_heads"] = heads
        engine = sa.create_engine(target_text, pool_pre_ping=True)

        command.upgrade(config, PHASE7_REVISION)
        report["empty_upgrade_revision"] = _revision(engine)
        with engine.connect() as connection:
            report["empty_output_count"] = connection.scalar(sa.text("SELECT count(*) FROM workspace_ai_outputs"))
        command.downgrade(config, PRE_PHASE7_REVISION)
        report["empty_downgrade_revision"] = _revision(engine)
        report["empty_rollback_archive_exists"] = sa.inspect(engine).has_table("workspace_ai_outputs_rollback")
        command.upgrade(config, PHASE7_REVISION)
        report["empty_reupgrade_revision"] = _revision(engine)

        command.downgrade(config, PRE_PHASE7_REVISION)
        ids = _seed(engine)
        before = _legacy_snapshot(engine, ids)
        command.upgrade(config, PHASE7_REVISION)
        report["populated_upgrade_revision"] = _revision(engine)
        with engine.connect() as connection:
            assessment = connection.execute(
                sa.text("SELECT provenance_type,generated_output_id FROM dossier_assessments WHERE id=:id"),
                {"id": ids["assessment"]},
            ).mappings().one()
            report["legacy_assessment_default"] = dict(assessment)
            report["new_outputs_start_empty"] = connection.scalar(sa.text("SELECT count(*) FROM workspace_ai_outputs")) == 0
        canonical_output_id = _insert_canonical_output(engine, ids)
        command.downgrade(config, PRE_PHASE7_REVISION)
        report["populated_downgrade_revision"] = _revision(engine)
        with engine.connect() as connection:
            report["rollback_output_count"] = connection.scalar(sa.text("SELECT count(*) FROM workspace_ai_outputs_rollback"))
            report["rollback_provenance_count"] = connection.scalar(sa.text("SELECT count(*) FROM dossier_assessment_ai_provenance_rollback"))
        after_downgrade = _legacy_snapshot(engine, ids)
        command.upgrade(config, PHASE7_REVISION)
        report["populated_reupgrade_revision"] = _revision(engine)
        with engine.connect() as connection:
            restored = connection.execute(
                sa.text("SELECT review_status,mandate_version_id FROM workspace_ai_outputs WHERE id=:id"),
                {"id": canonical_output_id},
            ).mappings().one()
            restored_assessment = connection.execute(
                sa.text("SELECT provenance_type,generated_output_id FROM dossier_assessments WHERE id=:id"),
                {"id": ids["assessment"]},
            ).mappings().one()
            report["restored_output"] = dict(restored)
            report["restored_assessment"] = dict(restored_assessment)
            report["rollback_archives_removed"] = not any(
                sa.inspect(connection).has_table(name)
                for name in ("workspace_ai_outputs_rollback", "dossier_assessment_ai_provenance_rollback")
            )
        after_reupgrade = _legacy_snapshot(engine, ids)
        report["legacy_snapshot_stable"] = before == after_downgrade == after_reupgrade
        report["passed"] = (
            heads == [PHASE7_REVISION]
            and report["empty_upgrade_revision"] == PHASE7_REVISION
            and report["empty_output_count"] == 0
            and report["empty_downgrade_revision"] == PRE_PHASE7_REVISION
            and report["empty_rollback_archive_exists"] is True
            and report["empty_reupgrade_revision"] == PHASE7_REVISION
            and report["populated_upgrade_revision"] == PHASE7_REVISION
            and report["legacy_assessment_default"] == {"provenance_type": "investigator", "generated_output_id": None}
            and report["new_outputs_start_empty"] is True
            and report["populated_downgrade_revision"] == PRE_PHASE7_REVISION
            and report["rollback_output_count"] == 1
            and report["rollback_provenance_count"] == 1
            and str(report["restored_output"]["mandate_version_id"]) == ids["mandate"]
            and report["restored_output"]["review_status"] == "accepted"
            and str(report["restored_assessment"]["generated_output_id"]) == canonical_output_id
            and report["restored_assessment"]["provenance_type"] == "ai_assisted"
            and report["rollback_archives_removed"] is True
            and report["legacy_snapshot_stable"] is True
        )
    finally:
        if engine is not None:
            engine.dispose()
        if previous_env is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous_env
        app_config.DATABASE_URL = previous_config
        with connect(admin_text, autocommit=True) as connection:
            connection.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s AND pid <> pg_backend_pid()",
                (database_name,),
            )
            if not database_name.startswith(DATABASE_PREFIX):
                raise RuntimeError("Refusing to drop an unscoped database")
            connection.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(database_name)))
        report["cleanup"] = {"dropped": True}
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 0 if report.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
