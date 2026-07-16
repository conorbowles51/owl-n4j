from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import importlib.util
from pathlib import Path
import threading
import uuid

import pytest

sqlalchemy = pytest.importorskip("sqlalchemy")
from sqlalchemy import select, text

from postgres.models.case import Case
from postgres.models.user import User
from postgres.models.workspace import WorkspaceNote
from services import workspace_service as workspace_service_module
from services.workspace_service import WorkspaceService


def _seed_case(session_factory, title: str = "DKT-446 case") -> uuid.UUID:
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


def test_multiple_workers_can_create_and_edit_notes_without_losing_rows(
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
    note_ids = [f"note_worker_{idx}" for idx in range(20)]

    def create(note_id: str) -> str:
        return service.save_note(
            str(case_id),
            {
                "note_id": note_id,
                "title": note_id,
                "content": f"created {note_id}",
                "tags": ["created"],
            },
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sorted(pool.map(create, note_ids)) == sorted(note_ids)

    edit_barrier = threading.Barrier(len(note_ids))

    def edit(note_id: str) -> str:
        edit_barrier.wait(timeout=10)
        return service.save_note(
            str(case_id),
            {
                "note_id": note_id,
                "title": f"edited {note_id}",
                "content": f"edited content for {note_id}",
                "tags": ["edited"],
            },
        )

    with ThreadPoolExecutor(max_workers=len(note_ids)) as pool:
        assert sorted(pool.map(edit, note_ids)) == sorted(note_ids)

    notes_by_id = {note["note_id"]: note for note in service.get_notes(str(case_id))}
    assert set(notes_by_id) == set(note_ids)
    for note_id in note_ids:
        assert notes_by_id[note_id]["content"] == f"edited content for {note_id}"
    with session_factory() as db:
        assert db.query(WorkspaceNote).filter(WorkspaceNote.case_id == case_id).count() == len(note_ids)


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


def _load_migration(filename: str):
    path = Path(__file__).resolve().parents[1] / "postgres" / "alembic" / "versions" / filename
    spec = importlib.util.spec_from_file_location(filename.replace(".py", ""), path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


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

        with migration_engine.begin() as conn:
            context = alembic_runtime.MigrationContext.configure(conn)
            operations = alembic_operations.Operations(context)
            monkeypatch.setattr(workspace_migration, "op", operations)
            monkeypatch.setattr(notebook_migration, "op", operations)

            workspace_migration.upgrade()
            workspace_migration.upgrade()
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
    finally:
        migration_engine.dispose()
        with pg_engine.begin() as conn:
            conn.execute(text(f'DROP SCHEMA IF EXISTS "{migration_schema}" CASCADE'))
