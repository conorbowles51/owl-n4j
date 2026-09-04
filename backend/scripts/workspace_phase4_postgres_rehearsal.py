"""Rehearse Phase 4 context/mandate migration on isolated PostgreSQL."""

from __future__ import annotations

import json
import os
import sys
from datetime import date, datetime, timezone
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


PRE_PHASE4_REVISION = "20260901_dossier_importance"
PHASE4_REVISION = "20260901_case_context"
DATABASE_PREFIX = "owl_context_rehearsal_"


def _config(url: str) -> AlembicConfig:
    config = AlembicConfig(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return config


def _revision(engine: sa.Engine) -> str | None:
    with engine.connect() as connection:
        return MigrationContext.configure(connection).get_current_revision()


def _seed(engine: sa.Engine) -> str:
    metadata = sa.MetaData()
    users = sa.Table("users", metadata, autoload_with=engine)
    cases = sa.Table("cases", metadata, autoload_with=engine)
    contexts = sa.Table("workspace_contexts", metadata, autoload_with=engine)
    deadlines = sa.Table("case_deadlines", metadata, autoload_with=engine)
    now = datetime(2025, 4, 2, 10, 30, tzinfo=timezone.utc)
    user_id, case_id = uuid4(), uuid4()
    with engine.begin() as connection:
        connection.execute(users.insert().values(
            id=user_id, email="phase4@example.test", name="Phase 4", password_hash="x",
            global_role="user", is_active=True, created_at=now, updated_at=now,
        ))
        connection.execute(cases.insert().values(
            id=case_id, title="Context rehearsal", status="active", archived=False,
            created_by_user_id=user_id, owner_user_id=user_id, created_at=now, updated_at=now,
        ))
        connection.execute(contexts.insert().values(
            id=uuid4(), case_id=case_id,
            data={
                "summary": "Legacy case summary",
                "background": "A complaint triggered the investigation.",
                "client_profile": {"name": "Henry", "role": "client"},
                "charges": ["Count one", "Count two"],
                "allegations": ["Alleged conduct"],
                "denials": ["Denies authorisation"],
                "legal_exposure": {"maximum": "material"},
                "defense_strategy": ["Test the authorisation evidence"],
                "court_info": {"court": "Rehearsal Court"},
                "trial_date": "2026-11-05",
                "objectives": ["Establish who authorised the conduct"],
            },
            created_at=now, updated_at=now,
        ))
        connection.execute(deadlines.insert().values(
            id=uuid4(), case_id=case_id, name="Disclosure deadline",
            due_date=date(2026, 10, 20), created_by_user_id=user_id,
            created_at=now, updated_at=now,
        ))
    return str(case_id)


def _snapshot(engine: sa.Engine, case_id: str) -> dict[str, object]:
    with engine.connect() as connection:
        context = connection.execute(sa.text(
            "SELECT case_summary, background, investigation_type, jurisdiction, active_template_key, active_mandate_version_id "
            "FROM case_contexts WHERE case_id = :case_id"
        ), {"case_id": case_id}).mappings().one()
        values = connection.execute(sa.text(
            "SELECT f.field_key, v.value FROM case_context_values v "
            "JOIN case_context_template_fields f ON f.id = v.template_field_id "
            "WHERE v.case_id = :case_id ORDER BY f.field_key"
        ), {"case_id": case_id}).mappings().all()
        mandates = connection.execute(sa.text(
            "SELECT version_number, objective, key_questions, in_scope, out_of_scope, perspective, success_criteria, constraints "
            "FROM case_mandate_versions WHERE case_id = :case_id ORDER BY version_number"
        ), {"case_id": case_id}).mappings().all()
        deadlines = connection.execute(sa.text(
            "SELECT name, due_date FROM case_deadlines WHERE case_id = :case_id ORDER BY due_date, name"
        ), {"case_id": case_id}).mappings().all()
        warnings = connection.execute(sa.text(
            "SELECT warnings FROM case_context_legacy_mappings WHERE case_id = :case_id"
        ), {"case_id": case_id}).scalar_one()
        return {
            "context": {key: context[key] for key in ("case_summary", "background", "investigation_type", "jurisdiction", "active_template_key")},
            "has_active_mandate": context["active_mandate_version_id"] is not None,
            "values": {row["field_key"]: row["value"] for row in values},
            "mandates": [{key: row[key] for key in row.keys()} for row in mandates],
            "deadlines": [{"name": row["name"], "due_date": str(row["due_date"])} for row in deadlines],
            "warnings": warnings,
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
    output = BACKEND_DIR.parent / "output" / "workspace-redesign" / "phase4-postgres-migration-rehearsal.json"
    report: dict[str, object] = {"schema_version": 1, "cleanup": {"dropped": False}}
    engine = None
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
        command.upgrade(config, PHASE4_REVISION)
        report["empty_upgrade_revision"] = _revision(engine)
        command.downgrade(config, PRE_PHASE4_REVISION)
        case_id = _seed(engine)
        command.upgrade(config, PHASE4_REVISION)
        report["representative_upgrade_revision"] = _revision(engine)
        first = _snapshot(engine, case_id)
        report["representative_snapshot"] = first
        command.downgrade(config, PRE_PHASE4_REVISION)
        report["downgrade_revision"] = _revision(engine)
        command.upgrade(config, PHASE4_REVISION)
        report["reupgrade_revision"] = _revision(engine)
        second = _snapshot(engine, case_id)
        report["reupgrade_snapshot"] = second
        report["reupgrade_snapshot_stable"] = first == second
        report["passed"] = (
            len(heads) == 1
            and report["empty_upgrade_revision"] == PHASE4_REVISION
            and report["representative_upgrade_revision"] == PHASE4_REVISION
            and report["downgrade_revision"] == PRE_PHASE4_REVISION
            and report["reupgrade_revision"] == PHASE4_REVISION
            and first["context"]["case_summary"] == "Legacy case summary"
            and first["context"]["active_template_key"] == "criminal_defense"
            and first["has_active_mandate"] is True
            and first["values"]["charges"] == "Count one\nCount two"
            and {item["name"] for item in first["deadlines"]} == {"Disclosure deadline", "Trial date"}
            and first["warnings"] == []
            and report["reupgrade_snapshot_stable"] is True
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
            connection.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s AND pid <> pg_backend_pid()", (database_name,))
            if not database_name.startswith(DATABASE_PREFIX):
                raise RuntimeError("Unsafe database name")
            connection.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(database_name)))
        report["cleanup"] = {"dropped": True}
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 0 if report.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
