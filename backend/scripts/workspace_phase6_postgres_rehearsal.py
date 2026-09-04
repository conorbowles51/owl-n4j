"""Rehearse Phase 6 personal-attention state on isolated PostgreSQL."""

from __future__ import annotations

import json
import os
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


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import config as app_config
from config import DATABASE_URL


PRE_PHASE6_REVISION = "20260902_case_work"
PHASE6_REVISION = "20260902_workspace_attention"
DATABASE_PREFIX = "owl_attention_rehearsal_"


def _config(url: str) -> AlembicConfig:
    config = AlembicConfig(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return config


def _revision(engine: sa.Engine) -> str | None:
    with engine.connect() as connection:
        return MigrationContext.configure(connection).get_current_revision()


def _seed_sources(engine: sa.Engine) -> dict[str, str]:
    now = datetime(2026, 9, 2, 9, 30, tzinfo=timezone.utc)
    ids = {
        "owner": str(uuid4()),
        "editor": str(uuid4()),
        "case": str(uuid4()),
        "deadline": str(uuid4()),
        "task": str(uuid4()),
        "entry": str(uuid4()),
        "dossier": str(uuid4()),
        "context": str(uuid4()),
    }
    with engine.begin() as connection:
        for user_id, email, name in (
            (ids["owner"], "owner@phase6.test", "Phase 6 Owner"),
            (ids["editor"], "editor@phase6.test", "Phase 6 Editor"),
        ):
            connection.execute(
                sa.text(
                    "INSERT INTO users (id,email,name,password_hash,global_role,is_active,created_at,updated_at) "
                    "VALUES (:id,:email,:name,'x','user',true,:now,:now)"
                ),
                {"id": user_id, "email": email, "name": name, "now": now},
            )
        connection.execute(
            sa.text(
                "INSERT INTO cases (id,title,created_by_user_id,owner_user_id,created_at,updated_at) "
                "VALUES (:id,'Phase 6 production-shaped case',:owner,:owner,:now,:now)"
            ),
            {"id": ids["case"], "owner": ids["owner"], "now": now},
        )
        for user_id, role in ((ids["owner"], "owner"), (ids["editor"], "collaborator")):
            connection.execute(
                sa.text(
                    "INSERT INTO case_memberships "
                    "(case_id,user_id,membership_role,permissions,added_by_user_id,created_at,updated_at) "
                    "VALUES (:case_id,:user_id,:role,CAST(:permissions AS jsonb),:owner,:now,:now)"
                ),
                {
                    "case_id": ids["case"],
                    "user_id": user_id,
                    "role": role,
                    "permissions": json.dumps({"case": {"view": True, "edit": True}}),
                    "owner": ids["owner"],
                    "now": now,
                },
            )
        connection.execute(
            sa.text(
                "INSERT INTO case_deadlines (id,case_id,name,due_date,created_by_user_id,created_at,updated_at) "
                "VALUES (:id,:case_id,'Disclosure response',:due_date,:owner,:now,:now)"
            ),
            {
                "id": ids["deadline"],
                "case_id": ids["case"],
                "due_date": date(2026, 9, 5),
                "owner": ids["owner"],
                "now": now,
            },
        )
        connection.execute(
            sa.text(
                "INSERT INTO case_tasks "
                "(id,case_id,title,description,status,priority,assignee_user_id,due_at,deadline_id,"
                "created_by_user_id,updated_by_user_id,migration_metadata,needs_migration_review,created_at,updated_at) "
                "VALUES (:id,:case_id,'Review account statement','Resolve the transfer discrepancy','todo','urgent',"
                ":editor,:due_at,:deadline,:owner,:owner,'{}',false,:now,:now)"
            ),
            {
                "id": ids["task"],
                "case_id": ids["case"],
                "editor": ids["editor"],
                "due_at": now + timedelta(days=1),
                "deadline": ids["deadline"],
                "owner": ids["owner"],
                "now": now,
            },
        )
        connection.execute(
            sa.text(
                "INSERT INTO workspace_entries "
                "(id,case_id,entry_type,title,body,tags,lifecycle_state,significance,review_state,author_user_id,"
                "author_email,author_name,updated_by_user_id,updated_by_email,updated_by_name,version,"
                "migration_metadata,needs_migration_review,created_at,updated_at) "
                "VALUES (:id,:case_id,'finding','Signing authority retained','The account authority remained unchanged.',"
                "'[]','active','high','pending',:owner,'owner@phase6.test','Phase 6 Owner',:owner,"
                "'owner@phase6.test','Phase 6 Owner',1,'{}',false,:now,:now)"
            ),
            {"id": ids["entry"], "case_id": ids["case"], "owner": ids["owner"], "now": now},
        )
        connection.execute(
            sa.text(
                "INSERT INTO case_profiles "
                "(id,case_id,profile_type,display_name,summary,importance,linkage_state,status,needs_link_review,"
                "graph_entity_deleted,created_by_user_id,updated_by_user_id,created_at,updated_at) "
                "VALUES (:id,:case_id,'person','Henry Example','Account signatory','high','unlinked','active',"
                "false,false,:owner,:owner,:now,:now)"
            ),
            {"id": ids["dossier"], "case_id": ids["case"], "owner": ids["owner"], "now": now},
        )
        connection.execute(
            sa.text(
                "INSERT INTO case_contexts "
                "(id,case_id,case_summary,background,investigation_type,jurisdiction,active_template_key,"
                "created_by_user_id,updated_by_user_id,created_at,updated_at) "
                "VALUES (:id,:case_id,'Cross-border asset tracing','Disclosure triggered review','Asset tracing',"
                "'Ireland','generic',:owner,:owner,:now,:now)"
            ),
            {"id": ids["context"], "case_id": ids["case"], "owner": ids["owner"], "now": now},
        )
    return ids


def _source_snapshot(engine: sa.Engine, case_id: str) -> dict[str, object]:
    with engine.connect() as connection:
        return {
            "case": connection.execute(
                sa.text("SELECT title,description,status FROM cases WHERE id=:case_id"),
                {"case_id": case_id},
            ).mappings().one(),
            "deadlines": [dict(row) for row in connection.execute(
                sa.text("SELECT name,due_date FROM case_deadlines WHERE case_id=:case_id ORDER BY id"),
                {"case_id": case_id},
            ).mappings()],
            "tasks": [dict(row) for row in connection.execute(
                sa.text("SELECT title,status,priority,assignee_user_id,due_at FROM case_tasks WHERE case_id=:case_id ORDER BY id"),
                {"case_id": case_id},
            ).mappings()],
            "entries": [dict(row) for row in connection.execute(
                sa.text("SELECT entry_type,title,body,lifecycle_state,significance,review_state,version FROM workspace_entries WHERE case_id=:case_id ORDER BY id"),
                {"case_id": case_id},
            ).mappings()],
            "dossiers": [dict(row) for row in connection.execute(
                sa.text("SELECT profile_type,display_name,summary,importance,linkage_state FROM case_profiles WHERE case_id=:case_id ORDER BY id"),
                {"case_id": case_id},
            ).mappings()],
            "context": connection.execute(
                sa.text("SELECT case_summary,background,investigation_type,jurisdiction,active_template_key FROM case_contexts WHERE case_id=:case_id"),
                {"case_id": case_id},
            ).mappings().one(),
        }


def _jsonable(value: object) -> object:
    return json.loads(json.dumps(value, default=str))


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
    output = BACKEND_DIR.parent / "output" / "workspace-redesign" / "phase6-postgres-migration-rehearsal.json"
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

        command.upgrade(config, PHASE6_REVISION)
        report["empty_upgrade_revision"] = _revision(engine)
        with engine.connect() as connection:
            report["empty_attention_count"] = connection.scalar(
                sa.text("SELECT count(*) FROM workspace_attention_states")
            )

        command.downgrade(config, PRE_PHASE6_REVISION)
        report["pre_seed_revision"] = _revision(engine)
        ids = _seed_sources(engine)
        before = _jsonable(_source_snapshot(engine, ids["case"]))
        command.upgrade(config, PHASE6_REVISION)
        report["representative_upgrade_revision"] = _revision(engine)
        after_upgrade = _jsonable(_source_snapshot(engine, ids["case"]))
        with engine.connect() as connection:
            state_count = connection.scalar(sa.text("SELECT count(*) FROM workspace_attention_states"))
        report["attention_starts_empty"] = state_count == 0

        with engine.begin() as connection:
            for user_id in (ids["owner"], ids["editor"]):
                connection.execute(
                    sa.text(
                        "INSERT INTO workspace_attention_states "
                        "(id,case_id,user_id,attention_key,dismissed_at,created_at,updated_at) "
                        "VALUES (:id,:case_id,:user_id,:key,:now,:now,:now)"
                    ),
                    {
                        "id": str(uuid4()),
                        "case_id": ids["case"],
                        "user_id": user_id,
                        "key": f"task:{ids['task']}:task_urgent:v1",
                        "now": datetime(2026, 9, 2, 10, 0, tzinfo=timezone.utc),
                    },
                )
        with engine.connect() as connection:
            report["per_user_state_count"] = connection.scalar(
                sa.text("SELECT count(*) FROM workspace_attention_states")
            )

        command.downgrade(config, PRE_PHASE6_REVISION)
        report["downgrade_revision"] = _revision(engine)
        report["attention_table_removed"] = not sa.inspect(engine).has_table(
            "workspace_attention_states"
        )
        after_downgrade = _jsonable(_source_snapshot(engine, ids["case"]))
        command.upgrade(config, PHASE6_REVISION)
        report["reupgrade_revision"] = _revision(engine)
        after_reupgrade = _jsonable(_source_snapshot(engine, ids["case"]))
        with engine.connect() as connection:
            report["reupgrade_attention_count"] = connection.scalar(
                sa.text("SELECT count(*) FROM workspace_attention_states")
            )

        report["source_snapshot_before"] = before
        report["source_snapshot_after_upgrade"] = after_upgrade
        report["source_snapshot_after_downgrade"] = after_downgrade
        report["source_snapshot_after_reupgrade"] = after_reupgrade
        report["source_snapshot_stable"] = (
            before == after_upgrade == after_downgrade == after_reupgrade
        )
        report["passed"] = (
            len(heads) == 1
            and report["empty_upgrade_revision"] == PHASE6_REVISION
            and report["empty_attention_count"] == 0
            and report["pre_seed_revision"] == PRE_PHASE6_REVISION
            and report["representative_upgrade_revision"] == PHASE6_REVISION
            and report["attention_starts_empty"] is True
            and report["per_user_state_count"] == 2
            and report["downgrade_revision"] == PRE_PHASE6_REVISION
            and report["attention_table_removed"] is True
            and report["reupgrade_revision"] == PHASE6_REVISION
            and report["reupgrade_attention_count"] == 0
            and report["source_snapshot_stable"] is True
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
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid()",
                (database_name,),
            )
            if not database_name.startswith(DATABASE_PREFIX):
                raise RuntimeError("Refusing to drop an unscoped database")
            connection.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(database_name)))
        report["cleanup"] = {"dropped": True}
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(report, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )

    print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 0 if report.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
