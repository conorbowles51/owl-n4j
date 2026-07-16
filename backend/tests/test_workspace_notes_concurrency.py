from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import threading
import uuid

import pytest

pytest.importorskip("sqlalchemy")
from sqlalchemy import select

from postgres.models.case import Case
from postgres.models.user import User
from postgres.models.workspace import WorkspaceNote
from services import workspace_service as workspace_service_module
from services.workspace_service import WorkspaceService


def _seed_case(session_factory, title: str = "DKT-448 concurrency case") -> uuid.UUID:
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
