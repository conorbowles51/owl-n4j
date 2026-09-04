"""Rehearse Phase 5 work/pin migration on isolated PostgreSQL."""

from __future__ import annotations

import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

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


PRE_PHASE5_REVISION = "20260901_case_context"
PHASE5_REVISION = "20260902_case_work"
DATABASE_PREFIX = "owl_work_rehearsal_"


def _config(url: str) -> AlembicConfig:
    config = AlembicConfig(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return config


def _revision(engine: sa.Engine) -> str | None:
    with engine.connect() as connection:
        return MigrationContext.configure(connection).get_current_revision()


def _seed(engine: sa.Engine) -> dict[str, str]:
    now = datetime(2026, 8, 15, 9, 30, tzinfo=timezone.utc)
    ids = {
        "owner": str(uuid4()),
        "editor": str(uuid4()),
        "case": str(uuid4()),
        "evidence_one": str(uuid4()),
        "evidence_two": str(uuid4()),
        "evidence_three": str(uuid4()),
        "entry": str(uuid4()),
        "dossier": str(uuid4()),
        "existing_deadline": str(uuid4()),
    }
    with engine.begin() as connection:
        for user_id, email, name in (
            (ids["owner"], "owner@phase5.test", "Phase 5 Owner"),
            (ids["editor"], "editor@phase5.test", "Phase 5 Editor"),
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
                "VALUES (:id,'Phase 5 production-shaped case',:owner,:owner,:now,:now)"
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
        for evidence_id, legacy_id, filename in (
            (ids["evidence_one"], "legacy-bank", "bank.pdf"),
            (ids["evidence_two"], "legacy-ledger", "ledger.xlsx"),
            (ids["evidence_three"], "legacy-email", "email.eml"),
        ):
            connection.execute(
                sa.text(
                    "INSERT INTO evidence_files "
                    "(id,case_id,original_filename,stored_path,size,sha256,status,is_duplicate,is_relevant,"
                    "legacy_id,metadata,created_by_id,created_at,updated_at) "
                    "VALUES (:id,:case_id,:filename,:path,128,:sha,'processed',false,true,:legacy_id,'{}',:owner,:now,:now)"
                ),
                {
                    "id": evidence_id,
                    "case_id": ids["case"],
                    "filename": filename,
                    "path": f"/rehearsal/{filename}",
                    "sha": (legacy_id.encode().hex() + "0" * 64)[:64],
                    "legacy_id": legacy_id,
                    "owner": ids["owner"],
                    "now": now,
                },
            )
        connection.execute(
            sa.text(
                "INSERT INTO case_deadlines (id,case_id,name,due_date,created_by_user_id,created_at,updated_at) "
                "VALUES (:id,:case_id,'Disclosure',:due_date,:owner,:now,:now)"
            ),
            {"id": ids["existing_deadline"], "case_id": ids["case"], "due_date": date(2026, 10, 1), "owner": ids["owner"], "now": now},
        )
        connection.execute(
            sa.text(
                "INSERT INTO workspace_entries "
                "(id,case_id,entry_type,title,body,tags,review_state,author_user_id,author_email,author_name,"
                "updated_by_user_id,updated_by_email,updated_by_name,version,migration_metadata,"
                "needs_migration_review,created_at,updated_at) "
                "VALUES (:id,:case_id,'note',NULL,'Migration link holder','[]','accepted',:owner,"
                "'owner@phase5.test','Phase 5 Owner',:owner,'owner@phase5.test','Phase 5 Owner',1,'{}',false,:now,:now)"
            ),
            {"id": ids["entry"], "case_id": ids["case"], "owner": ids["owner"], "now": now},
        )
        connection.execute(
            sa.text(
                "INSERT INTO case_profiles "
                "(id,case_id,profile_type,display_name,created_by_user_id,updated_by_user_id,created_at,updated_at) "
                "VALUES (:id,:case_id,'person','Migration Dossier',:owner,:owner,:now,:now)"
            ),
            {"id": ids["dossier"], "case_id": ids["case"], "owner": ids["owner"], "now": now},
        )

        tasks = (
            ("task-assigned", {"title": "Assigned review", "status": "IN_PROGRESS", "priority": "HIGH", "assigned_to": "editor@phase5.test", "due_date": "2026-09-20"}),
            ("task-weird", {"title": "Unknown legacy state", "status": "BLOCKED", "priority": "CRITICAL", "assigned_to": "missing@phase5.test", "is_deleted": True}),
            ("task-parent", {"title": "Trace transfers", "status": "PENDING", "priority": "URGENT"}),
            (
                "task-child",
                {
                    "title": "Review bank statement",
                    "status": "COMPLETED",
                    "priority": "LOW",
                    "parent_task_id": "task-parent",
                    "deadline_id": "deadline-disclosure",
                    "links": [
                        {
                            "target_type": "document",
                            "target_id": "legacy-bank",
                            "label": "Bank statement",
                            "source_anchor": {"page": 4, "quote": "Transfer authorised"},
                        }
                    ],
                },
            ),
        )
        for index, (task_id, payload) in enumerate(tasks):
            task_time = now.replace(minute=now.minute + index)
            connection.execute(
                sa.text(
                    "INSERT INTO workspace_tasks (id,case_id,task_id,data,created_at,updated_at) "
                    "VALUES (:id,:case_id,:task_id,CAST(:data AS jsonb),:created_at,:created_at)"
                ),
                {"id": str(uuid4()), "case_id": ids["case"], "task_id": task_id, "data": json.dumps(payload), "created_at": task_time},
            )
        deadline_payload = {
            "trial_date": "2026-11-15",
            "deadlines": [
                {"deadline_id": "deadline-disclosure", "title": "Disclosure", "due_date": "2026-10-01"},
                {"deadline_id": "deadline-invalid", "title": "Invalid legacy deadline", "due_date": "not-a-date"},
            ],
        }
        connection.execute(
            sa.text(
                "INSERT INTO workspace_deadline_configs (id,case_id,data,created_at,updated_at) "
                "VALUES (:id,:case_id,CAST(:data AS jsonb),:now,:now)"
            ),
            {"id": str(uuid4()), "case_id": ids["case"], "data": json.dumps(deadline_payload), "now": now},
        )
        pin_rows = (
            ("pin-one", "evidence", ids["evidence_one"], ids["owner"], {"pinned_at": "2026-08-15T09:30:00+00:00"}),
            ("pin-duplicate", "document", "legacy-bank", "editor@phase5.test", {}),
            ("pin-missing", "evidence", "missing-evidence", ids["owner"], {}),
            ("pin-unattributed", "evidence", "legacy-ledger", "former-user@phase5.test", {}),
        )
        for pin_id, item_type, item_id, user_id, payload in pin_rows:
            connection.execute(
                sa.text(
                    "INSERT INTO workspace_pinned_items "
                    "(id,case_id,pin_id,item_type,item_id,user_id,data,created_at,updated_at) "
                    "VALUES (:id,:case_id,:pin_id,:item_type,:item_id,:user_id,CAST(:data AS jsonb),:now,:now)"
                ),
                {"id": str(uuid4()), "case_id": ids["case"], "pin_id": pin_id, "item_type": item_type, "item_id": item_id, "user_id": user_id, "data": json.dumps(payload), "now": now},
            )
        connection.execute(
            sa.text(
                "INSERT INTO workspace_entry_links "
                "(id,entry_id,case_id,target_type,target_id,relationship,source_anchor,metadata,created_by_user_id,created_at,updated_at) "
                "VALUES (:id,:entry,:case_id,'task','task-parent','context','{}','{}',:owner,:now,:now)"
            ),
            {"id": str(uuid4()), "entry": ids["entry"], "case_id": ids["case"], "owner": ids["owner"], "now": now},
        )
        connection.execute(
            sa.text(
                "INSERT INTO dossier_links "
                "(id,dossier_id,case_id,target_type,target_id,source_anchor,created_by_user_id,created_at,updated_at) "
                "VALUES (:id,:dossier,:case_id,'deadline','deadline-disclosure','{}',:owner,:now,:now)"
            ),
            {"id": str(uuid4()), "dossier": ids["dossier"], "case_id": ids["case"], "owner": ids["owner"], "now": now},
        )
    return ids


def _insert_canonical_records(engine: sa.Engine, ids: dict[str, str]) -> str:
    now = datetime(2026, 8, 16, 12, 0, tzinfo=timezone.utc)
    task_id, task_link_id, pin_id, deadline_id, external_link_id = (str(uuid4()) for _ in range(5))
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO case_deadlines (id,case_id,name,due_date,created_by_user_id,created_at,updated_at) "
                "VALUES (:id,:case_id,'Canonical review date',:due_date,:owner,:now,:now)"
            ),
            {"id": deadline_id, "case_id": ids["case"], "due_date": date(2026, 12, 1), "owner": ids["owner"], "now": now},
        )
        connection.execute(
            sa.text(
                "INSERT INTO case_tasks "
                "(id,case_id,title,description,status,priority,assignee_user_id,due_at,deadline_id,"
                "created_by_user_id,updated_by_user_id,migration_metadata,needs_migration_review,created_at,updated_at) "
                "VALUES (:id,:case_id,'Canonical-only task','Created after cutover','todo','standard',:editor,"
                ":due_at,:deadline,:owner,:owner,'{}',false,:now,:now)"
            ),
            {"id": task_id, "case_id": ids["case"], "editor": ids["editor"], "due_at": datetime(2026, 11, 25, 14, 0, tzinfo=timezone.utc), "deadline": deadline_id, "owner": ids["owner"], "now": now},
        )
        connection.execute(
            sa.text(
                "INSERT INTO case_task_links "
                "(id,task_id,case_id,target_type,target_id,label,source_anchor,created_by_user_id,created_at,updated_at) "
                "VALUES (:id,:task,:case_id,'evidence',:evidence,'Email exhibit',CAST(:anchor AS jsonb),:owner,:now,:now)"
            ),
            {"id": task_link_id, "task": task_id, "case_id": ids["case"], "evidence": ids["evidence_three"], "anchor": json.dumps({"message_id": "mail-7"}), "owner": ids["owner"], "now": now},
        )
        connection.execute(
            sa.text(
                "INSERT INTO shared_evidence_pins "
                "(id,case_id,evidence_file_id,pinned_by_user_id,legacy_metadata,created_at,updated_at) "
                "VALUES (:id,:case_id,:evidence,:editor,'{}',:now,:now)"
            ),
            {"id": pin_id, "case_id": ids["case"], "evidence": ids["evidence_three"], "editor": ids["editor"], "now": now},
        )
        connection.execute(
            sa.text(
                "INSERT INTO workspace_entry_links "
                "(id,entry_id,case_id,target_type,target_id,relationship,source_anchor,metadata,created_by_user_id,created_at,updated_at) "
                "VALUES (:id,:entry,:case_id,'task',:task,'context','{}','{}',:owner,:now,:now)"
            ),
            {"id": external_link_id, "entry": ids["entry"], "case_id": ids["case"], "task": task_id, "owner": ids["owner"], "now": now},
        )
    return task_id


def _snapshot(engine: sa.Engine, case_id: str) -> dict[str, object]:
    with engine.connect() as connection:
        tasks = connection.execute(
            sa.text(
                "SELECT t.title,t.description,t.status,t.priority,t.assignee_user_id,t.due_at,t.completed_at,t.deleted_at,"
                "t.needs_migration_review,p.title AS parent_title,d.name AS deadline_name "
                "FROM case_tasks t LEFT JOIN case_tasks p ON p.id=t.parent_task_id "
                "LEFT JOIN case_deadlines d ON d.id=t.deadline_id "
                "WHERE t.case_id=:case_id ORDER BY t.title"
            ),
            {"case_id": case_id},
        ).mappings().all()
        links = connection.execute(
            sa.text(
                "SELECT t.title,l.target_type,e.original_filename,l.label,l.source_anchor "
                "FROM case_task_links l JOIN case_tasks t ON t.id=l.task_id "
                "LEFT JOIN evidence_files e ON l.target_type='evidence' AND e.id::text=l.target_id "
                "WHERE l.case_id=:case_id ORDER BY t.title,l.target_type,l.target_id"
            ),
            {"case_id": case_id},
        ).mappings().all()
        pins = connection.execute(
            sa.text(
                "SELECT e.original_filename,u.email AS pinned_by "
                "FROM shared_evidence_pins p JOIN evidence_files e ON e.id=p.evidence_file_id "
                "LEFT JOIN users u ON u.id=p.pinned_by_user_id "
                "WHERE p.case_id=:case_id ORDER BY e.original_filename"
            ),
            {"case_id": case_id},
        ).mappings().all()
        deadlines = connection.execute(
            sa.text("SELECT name,due_date FROM case_deadlines WHERE case_id=:case_id ORDER BY name,due_date"),
            {"case_id": case_id},
        ).mappings().all()
        mappings = connection.execute(
            sa.text(
                "SELECT source_type,status,count(*) AS count FROM work_legacy_mappings "
                "WHERE case_id=:case_id GROUP BY source_type,status ORDER BY source_type,status"
            ),
            {"case_id": case_id},
        ).mappings().all()
        external_links = connection.execute(
            sa.text(
                "SELECT l.target_type,CASE WHEN l.target_type='task' THEN t.title ELSE d.name END AS target_name,"
                "(t.id IS NOT NULL OR d.id IS NOT NULL) AS resolved "
                "FROM workspace_entry_links l LEFT JOIN case_tasks t ON l.target_type='task' AND t.id::text=l.target_id "
                "LEFT JOIN case_deadlines d ON l.target_type='deadline' AND d.id::text=l.target_id "
                "WHERE l.case_id=:case_id "
                "UNION ALL "
                "SELECT l.target_type,CASE WHEN l.target_type='task' THEN t.title ELSE d.name END AS target_name,"
                "(t.id IS NOT NULL OR d.id IS NOT NULL) AS resolved "
                "FROM dossier_links l LEFT JOIN case_tasks t ON l.target_type='task' AND t.id::text=l.target_id "
                "LEFT JOIN case_deadlines d ON l.target_type='deadline' AND d.id::text=l.target_id "
                "WHERE l.case_id=:case_id ORDER BY target_type,target_name"
            ),
            {"case_id": case_id},
        ).mappings().all()
    return {
        "tasks": [{key: str(row[key]) if row[key] is not None else None for key in row.keys()} for row in tasks],
        "task_links": [{key: row[key] for key in row.keys()} for row in links],
        "pins": [{key: row[key] for key in row.keys()} for row in pins],
        "deadlines": [{"name": row["name"], "due_date": str(row["due_date"])} for row in deadlines],
        "mappings": [{key: row[key] for key in row.keys()} for row in mappings],
        "external_links": [{key: row[key] for key in row.keys()} for row in external_links],
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
    output = BACKEND_DIR.parent / "output" / "workspace-redesign" / "phase5-postgres-migration-rehearsal.json"
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

        command.upgrade(config, PHASE5_REVISION)
        report["empty_upgrade_revision"] = _revision(engine)
        command.downgrade(config, PRE_PHASE5_REVISION)
        ids = _seed(engine)
        command.upgrade(config, PHASE5_REVISION)
        report["representative_upgrade_revision"] = _revision(engine)
        legacy_snapshot = _snapshot(engine, ids["case"])
        report["legacy_snapshot"] = legacy_snapshot

        canonical_task_id = _insert_canonical_records(engine, ids)
        first = _snapshot(engine, ids["case"])
        report["pre_downgrade_snapshot"] = first
        command.downgrade(config, PRE_PHASE5_REVISION)
        report["downgrade_revision"] = _revision(engine)
        with engine.connect() as connection:
            exported = connection.execute(
                sa.text("SELECT data FROM workspace_tasks WHERE case_id=:case_id AND task_id=:task_id"),
                {"case_id": ids["case"], "task_id": canonical_task_id},
            ).scalar_one()
        report["canonical_task_exported"] = exported["title"] == "Canonical-only task"
        command.upgrade(config, PHASE5_REVISION)
        report["reupgrade_revision"] = _revision(engine)
        second = _snapshot(engine, ids["case"])
        report["reupgrade_snapshot"] = second
        first_semantic = {key: value for key, value in first.items() if key != "mappings"}
        second_semantic = {key: value for key, value in second.items() if key != "mappings"}
        report["reupgrade_snapshot_stable"] = first_semantic == second_semantic

        legacy_titles = {task["title"]: task for task in legacy_snapshot["tasks"]}
        mapping_pairs = {(row["source_type"], row["status"]) for row in legacy_snapshot["mappings"]}
        report["passed"] = (
            len(heads) == 1
            and report["empty_upgrade_revision"] == PHASE5_REVISION
            and report["representative_upgrade_revision"] == PHASE5_REVISION
            and report["downgrade_revision"] == PRE_PHASE5_REVISION
            and report["reupgrade_revision"] == PHASE5_REVISION
            and len(legacy_snapshot["tasks"]) == 4
            and legacy_titles["Assigned review"]["assignee_user_id"] == ids["editor"]
            and legacy_titles["Unknown legacy state"]["needs_migration_review"] == "True"
            and legacy_titles["Unknown legacy state"]["deleted_at"] is not None
            and legacy_titles["Review bank statement"]["parent_title"] == "Trace transfers"
            and legacy_titles["Review bank statement"]["deadline_name"] == "Disclosure"
            and len(legacy_snapshot["pins"]) == 2
            and {pin["original_filename"] for pin in legacy_snapshot["pins"]} == {"bank.pdf", "ledger.xlsx"}
            and ("workspace_pin", "unresolved") in mapping_pairs
            and ("workspace_deadline", "unresolved") in mapping_pairs
            and all(link["resolved"] for link in legacy_snapshot["external_links"])
            and report["canonical_task_exported"] is True
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
            connection.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid()",
                (database_name,),
            )
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
