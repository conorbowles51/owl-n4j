from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import threading
import uuid

import pytest

sqlalchemy = pytest.importorskip("sqlalchemy")
from sqlalchemy import select, text

from postgres.models.case import Case
from postgres.models.user import User
from postgres.models.workspace import WorkspaceNote
from routers import workspace as workspace_router
from services import workspace_service as workspace_service_module
from services.workspace_service import WorkspaceService


def _seed_case(session_factory, title: str = "DKT-444 case") -> uuid.UUID:
    user_id = uuid.uuid4()
    case_id = uuid.uuid4()
    with session_factory() as db:
        db.add(
            User(
                id=user_id,
                email=f"{user_id.hex}@example.test",
                name="Investigator",
                password_hash="hash",
            )
        )
        db.add(
            Case(
                id=case_id,
                title=title,
                created_by_user_id=user_id,
                owner_user_id=user_id,
            )
        )
        db.commit()
    return case_id


def _note_count(session_factory, case_id: uuid.UUID, note_id: str) -> int:
    with session_factory() as db:
        return len(
            db.execute(
                select(WorkspaceNote).where(
                    WorkspaceNote.case_id == case_id,
                    WorkspaceNote.note_id == note_id,
                )
            )
            .scalars()
            .all()
        )


def _load_migration(filename: str):
    path = Path(__file__).resolve().parents[1] / "postgres" / "alembic" / "versions" / filename
    spec = importlib.util.spec_from_file_location(filename.replace(".py", ""), path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _constraint_exists(conn, constraint_name: str) -> bool:
    return bool(
        conn.execute(
            text(
                """
                SELECT 1
                FROM pg_constraint
                WHERE conname = :constraint_name
                    AND conrelid = 'workspace_notes'::regclass
                """
            ),
            {"constraint_name": constraint_name},
        ).scalar_one_or_none()
    )


def test_concurrent_create_same_note_id_is_idempotent(
    session_factory,
    background_session_factory,
    monkeypatch,
):
    monkeypatch.setattr(
        workspace_service_module,
        "get_background_session",
        background_session_factory,
    )
    service = WorkspaceService()
    case_id = _seed_case(session_factory)
    barrier = threading.Barrier(12)

    def save(worker: int) -> str:
        barrier.wait(timeout=10)
        return service.save_note(
            str(case_id),
            {
                "note_id": "note_shared_retry",
                "title": f"worker {worker}",
                "content": f"content from worker {worker}",
                "tags": ["concurrency"],
            },
        )

    with ThreadPoolExecutor(max_workers=12) as pool:
        saved_ids = list(pool.map(save, range(12)))

    assert set(saved_ids) == {"note_shared_retry"}
    assert _note_count(session_factory, case_id, "note_shared_retry") == 1

    notes = service.get_notes(str(case_id))
    assert len(notes) == 1
    assert notes[0]["note_id"] == "note_shared_retry"
    assert notes[0]["case_id"] == str(case_id)
    assert notes[0]["content"].startswith("content from worker ")


def test_notes_survive_refresh_restart_and_stay_case_scoped(
    session_factory,
    background_session_factory,
    pg_engine,
    monkeypatch,
):
    monkeypatch.setattr(
        workspace_service_module,
        "get_background_session",
        background_session_factory,
    )
    service = WorkspaceService()
    first_case_id = _seed_case(session_factory, title="First case")
    second_case_id = _seed_case(session_factory, title="Second case")

    service.save_note(
        str(first_case_id),
        {"note_id": "note_visible", "title": "First", "content": "first case only"},
    )
    service.save_note(
        str(second_case_id),
        {"note_id": "note_visible", "title": "Second", "content": "second case only"},
    )

    service.reload()
    pg_engine.dispose()
    restarted_service = WorkspaceService()

    first_notes = restarted_service.get_notes(str(first_case_id))
    second_notes = restarted_service.get_notes(str(second_case_id))

    assert [note["content"] for note in first_notes] == ["first case only"]
    assert [note["content"] for note in second_notes] == ["second case only"]
    assert first_notes[0]["case_id"] == str(first_case_id)
    assert second_notes[0]["case_id"] == str(second_case_id)


def test_failed_save_rolls_back_without_duplicate_or_lost_content(
    session_factory,
    background_session_factory,
    monkeypatch,
):
    service = WorkspaceService()
    case_id = _seed_case(session_factory)
    monkeypatch.setattr(
        workspace_service_module,
        "get_background_session",
        background_session_factory,
    )
    service.save_note(
        str(case_id),
        {
            "note_id": "note_rollback",
            "title": "Original",
            "content": "original content",
        },
    )

    @contextmanager
    def failing_background_session():
        db = session_factory()
        try:
            yield db
            raise RuntimeError("simulated commit failure")
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    monkeypatch.setattr(
        workspace_service_module,
        "get_background_session",
        failing_background_session,
    )
    with pytest.raises(RuntimeError, match="simulated commit failure"):
        service.save_note(
            str(case_id),
            {
                "note_id": "note_rollback",
                "title": "Failed update",
                "content": "content that must roll back",
            },
        )

    monkeypatch.setattr(
        workspace_service_module,
        "get_background_session",
        background_session_factory,
    )
    notes = service.get_notes(str(case_id))
    assert len(notes) == 1
    assert notes[0]["title"] == "Original"
    assert notes[0]["content"] == "original content"
    assert _note_count(session_factory, case_id, "note_rollback") == 1


def test_concurrent_partial_updates_preserve_disjoint_note_fields(
    session_factory,
    background_session_factory,
    monkeypatch,
):
    monkeypatch.setattr(
        workspace_service_module,
        "get_background_session",
        background_session_factory,
    )
    service = WorkspaceService()
    case_id = _seed_case(session_factory)
    service.save_note(
        str(case_id),
        {
            "note_id": "note_partial_concurrency",
            "title": "Original",
            "content": "original content",
            "tags": ["original"],
        },
    )
    barrier = threading.Barrier(2)

    def rename_note() -> dict:
        barrier.wait(timeout=10)
        return service.update_note(
            str(case_id),
            "note_partial_concurrency",
            {"title": "Renamed"},
        )

    def retag_note() -> dict:
        barrier.wait(timeout=10)
        return service.update_note(
            str(case_id),
            "note_partial_concurrency",
            {"tags": ["reviewed"]},
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda fn: fn(), [rename_note, retag_note]))

    assert all(result["note_id"] == "note_partial_concurrency" for result in results)
    note = service.get_note(str(case_id), "note_partial_concurrency")
    assert note["title"] == "Renamed"
    assert note["content"] == "original content"
    assert note["tags"] == ["reviewed"]


def test_update_note_route_accepts_partial_patch_without_dropping_content(
    session_factory,
    background_session_factory,
    monkeypatch,
):
    monkeypatch.setattr(
        workspace_service_module,
        "get_background_session",
        background_session_factory,
    )
    service = WorkspaceService()
    monkeypatch.setattr(workspace_router, "workspace_service", service)
    monkeypatch.setattr(
        workspace_router,
        "get_case_if_allowed",
        lambda db, case_id, user: SimpleNamespace(id=case_id),
    )
    case_id = _seed_case(session_factory)
    service.save_note(
        str(case_id),
        {
            "note_id": "note_route_partial",
            "title": "Original",
            "content": "do not drop",
            "tags": ["original"],
        },
    )

    result = asyncio.run(
        workspace_router.update_note(
            str(case_id),
            "note_route_partial",
            workspace_router.NoteUpdate(title="Route patch"),
            db=None,
            current_user=SimpleNamespace(email="investigator@example.test"),
        )
    )

    assert result["title"] == "Route patch"
    assert result["content"] == "do not drop"
    assert result["tags"] == ["original"]


def test_migrated_schema_upgrade_adds_note_uniqueness_and_preserves_duplicate_payloads(
    pg_url,
    pg_engine,
    db_schema,
    monkeypatch,
):
    alembic_runtime = pytest.importorskip("alembic.runtime.migration")
    alembic_operations = pytest.importorskip("alembic.operations")
    sqlalchemy_orm = pytest.importorskip("sqlalchemy.orm")
    create_engine = sqlalchemy.create_engine

    migrated_schema = f"{db_schema}_migrated"
    with pg_engine.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{migrated_schema}"'))

    migration_engine = create_engine(
        pg_url,
        future=True,
        pool_pre_ping=True,
        connect_args={
            "connect_timeout": 2,
            "options": f"-csearch_path={migrated_schema},public",
        },
    )
    try:
        user_id = uuid.uuid4()
        case_id = uuid.uuid4()
        older_id = uuid.uuid4()
        newer_id = uuid.uuid4()
        with migration_engine.begin() as conn:
            conn.execute(
                text(
                    """
                    CREATE TABLE users (
                        id uuid PRIMARY KEY,
                        email text NOT NULL,
                        name text NOT NULL,
                        password_hash text NOT NULL
                    )
                    """
                )
            )
            conn.execute(
                text(
                    """
                    CREATE TABLE cases (
                        id uuid PRIMARY KEY,
                        title text NOT NULL,
                        created_by_user_id uuid NOT NULL REFERENCES users(id),
                        owner_user_id uuid NOT NULL REFERENCES users(id)
                    )
                    """
                )
            )
            conn.execute(
                text(
                    """
                    CREATE TABLE workspace_notes (
                        id uuid PRIMARY KEY,
                        case_id uuid NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
                        note_id varchar(64) NOT NULL,
                        data jsonb DEFAULT '{}'::jsonb NOT NULL,
                        created_at timestamptz DEFAULT now() NOT NULL,
                        updated_at timestamptz DEFAULT now() NOT NULL
                    )
                    """
                )
            )
            conn.execute(
                text(
                    "INSERT INTO users (id, email, name, password_hash) "
                    "VALUES (:id, 'migrated@example.test', 'Migrated', 'hash')"
                ),
                {"id": user_id},
            )
            conn.execute(
                text(
                    "INSERT INTO cases (id, title, created_by_user_id, owner_user_id) "
                    "VALUES (:id, 'Migrated case', :user_id, :user_id)"
                ),
                {"id": case_id, "user_id": user_id},
            )
            conn.execute(
                text(
                    """
                    INSERT INTO workspace_notes
                        (id, case_id, note_id, data, created_at, updated_at)
                    VALUES
                        (:older_id, :case_id, 'note_migrated',
                            '{"note_id":"note_migrated","content":"older duplicate"}',
                            '2026-07-16T10:00:00Z', '2026-07-16T10:00:00Z'),
                        (:newer_id, :case_id, 'note_migrated',
                            '{"note_id":"note_migrated","content":"newer duplicate"}',
                            '2026-07-16T10:01:00Z', '2026-07-16T10:01:00Z')
                    """
                ),
                {"older_id": older_id, "newer_id": newer_id, "case_id": case_id},
            )
            assert not _constraint_exists(conn, "uq_workspace_notes_case_note")

        migration = _load_migration("20260716_workspace_note_uniqueness.py")
        with migration_engine.begin() as conn:
            context = alembic_runtime.MigrationContext.configure(conn)
            operations = alembic_operations.Operations(context)
            monkeypatch.setattr(migration, "op", operations)

            migration.upgrade()
            assert _constraint_exists(conn, "uq_workspace_notes_case_note")
            row = conn.execute(
                text(
                    """
                    SELECT data
                    FROM workspace_notes
                    WHERE case_id = :case_id
                        AND note_id = 'note_migrated'
                    """
                ),
                {"case_id": case_id},
            ).scalar_one()
            assert row["content"] == "newer duplicate"
            duplicate_contents = {
                duplicate["data"]["content"]
                for duplicate in row["migration_duplicate_records"]
            }
            assert duplicate_contents == {"older duplicate"}

        session_factory = sqlalchemy_orm.sessionmaker(
            bind=migration_engine,
            autoflush=False,
            autocommit=False,
        )

        @contextmanager
        def migrated_background_session():
            db = session_factory()
            try:
                yield db
                db.commit()
            except Exception:
                db.rollback()
                raise
            finally:
                db.close()

        monkeypatch.setattr(
            workspace_service_module,
            "get_background_session",
            migrated_background_session,
        )
        service = WorkspaceService()
        service.save_note(
            str(case_id),
            {
                "note_id": "note_migrated",
                "title": "After migration",
                "content": "saved after migration",
            },
        )

        with migration_engine.begin() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT data
                    FROM workspace_notes
                    WHERE case_id = :case_id
                        AND note_id = 'note_migrated'
                    """
                ),
                {"case_id": case_id},
            ).all()
            assert len(rows) == 1
            assert rows[0][0]["content"] == "saved after migration"
    finally:
        migration_engine.dispose()
        with pg_engine.begin() as conn:
            conn.execute(text(f'DROP SCHEMA IF EXISTS "{migrated_schema}" CASCADE'))


def test_workspace_and_notebook_migrations_are_directly_idempotent(
    pg_url,
    pg_engine,
    db_schema,
    monkeypatch,
):
    alembic_runtime = pytest.importorskip("alembic.runtime.migration")
    alembic_operations = pytest.importorskip("alembic.operations")
    create_engine = sqlalchemy.create_engine

    migration_schema = f"{db_schema}_migrations"
    with pg_engine.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{migration_schema}"'))

    migration_engine = create_engine(
        pg_url,
        future=True,
        pool_pre_ping=True,
        connect_args={
            "connect_timeout": 2,
            "options": f"-csearch_path={migration_schema},public",
        },
    )
    try:
        with migration_engine.begin() as conn:
            conn.execute(text("CREATE TABLE users (id uuid PRIMARY KEY)"))
            conn.execute(text("CREATE TABLE cases (id uuid PRIMARY KEY)"))

        workspace_migration = _load_migration("20260321_add_workspace_tables.py")
        notebook_migration = _load_migration("20260705_add_notebook_tables.py")
        uniqueness_migration = _load_migration("20260716_workspace_note_uniqueness.py")

        with migration_engine.begin() as conn:
            context = alembic_runtime.MigrationContext.configure(conn)
            operations = alembic_operations.Operations(context)
            monkeypatch.setattr(workspace_migration, "op", operations)
            monkeypatch.setattr(notebook_migration, "op", operations)
            monkeypatch.setattr(uniqueness_migration, "op", operations)

            workspace_migration.upgrade()
            workspace_migration.upgrade()
            uniqueness_migration.upgrade()
            uniqueness_migration.upgrade()
            notebook_migration.upgrade()
            notebook_migration.upgrade()

            tables = {
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT tablename FROM pg_tables "
                        "WHERE schemaname = :schema"
                    ),
                    {"schema": migration_schema},
                )
            }
            assert "workspace_notes" in tables
            assert "notebook_notes" in tables
            assert _constraint_exists(conn, "uq_workspace_notes_case_note")
    finally:
        migration_engine.dispose()
        with pg_engine.begin() as conn:
            conn.execute(text(f'DROP SCHEMA IF EXISTS "{migration_schema}" CASCADE'))
