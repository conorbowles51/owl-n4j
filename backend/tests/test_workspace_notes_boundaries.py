from __future__ import annotations

from contextlib import contextmanager
import uuid

import pytest

pytest.importorskip("sqlalchemy")
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from postgres.models.case import Case
from postgres.models.case_membership import CaseMembership
from postgres.models.enums import CaseMembershipRole
from postgres.models.user import User
from postgres.models.workspace import WorkspaceNote
from postgres.permissions import clone_permissions, OWNER_PERMISSIONS, VIEWER_PERMISSIONS
from routers import workspace as workspace_router_module
from services import workspace_service as workspace_service_module
from services.workspace_service import WorkspaceService


def _seed_user(session_factory, name: str = "Investigator") -> User:
    user_id = uuid.uuid4()
    with session_factory() as db:
        user = User(
            id=user_id,
            email=f"{user_id.hex}@example.test",
            name=name,
            password_hash="hash",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        db.expunge(user)
        return user


def _seed_case(
    session_factory,
    owner: User,
    *,
    title: str = "DKT-448 boundary case",
) -> uuid.UUID:
    case_id = uuid.uuid4()
    with session_factory() as db:
        db.add(
            Case(
                id=case_id,
                title=title,
                created_by_user_id=owner.id,
                owner_user_id=owner.id,
            )
        )
        db.add(
            CaseMembership(
                case_id=case_id,
                user_id=owner.id,
                membership_role=CaseMembershipRole.owner,
                permissions=clone_permissions(OWNER_PERMISSIONS),
                added_by_user_id=owner.id,
            )
        )
        db.commit()
    return case_id


def _add_viewer(session_factory, case_id: uuid.UUID, user: User, added_by: User) -> None:
    with session_factory() as db:
        db.add(
            CaseMembership(
                case_id=case_id,
                user_id=user.id,
                membership_role=CaseMembershipRole.collaborator,
                permissions=clone_permissions(VIEWER_PERMISSIONS),
                added_by_user_id=added_by.id,
            )
        )
        db.commit()


def _client(session_factory, current_user: User) -> TestClient:
    app = FastAPI()
    app.include_router(workspace_router_module.router)

    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[workspace_router_module.get_db] = override_get_db
    app.dependency_overrides[workspace_router_module.get_current_db_user] = lambda: current_user
    return TestClient(app)


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


def test_empty_case_returns_no_notes(
    session_factory,
    background_session_factory,
    monkeypatch,
):
    monkeypatch.setattr(
        workspace_service_module,
        "get_background_session",
        background_session_factory,
    )
    owner = _seed_user(session_factory)
    case_id = _seed_case(session_factory, owner)

    assert WorkspaceService().get_notes(str(case_id)) == []


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
    owner = _seed_user(session_factory)
    first_case_id = _seed_case(session_factory, owner, title="First case")
    second_case_id = _seed_case(session_factory, owner, title="Second case")

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


def test_workspace_notes_route_enforces_case_membership_and_case_scope(
    session_factory,
    background_session_factory,
    monkeypatch,
):
    monkeypatch.setattr(
        workspace_service_module,
        "get_background_session",
        background_session_factory,
    )
    monkeypatch.setattr(workspace_router_module.system_log_service, "log", lambda *args, **kwargs: None)
    owner = _seed_user(session_factory, name="Owner")
    outsider = _seed_user(session_factory, name="Outsider")
    first_case_id = _seed_case(session_factory, owner, title="First case")
    second_case_id = _seed_case(session_factory, owner, title="Second case")
    _add_viewer(session_factory, first_case_id, outsider, owner)
    service = WorkspaceService()
    service.save_note(
        str(first_case_id),
        {"note_id": "note_shared", "title": "First", "content": "first case note"},
    )
    service.save_note(
        str(second_case_id),
        {"note_id": "note_shared", "title": "Second", "content": "second case note"},
    )

    visible_response = _client(session_factory, outsider).get(f"/api/workspace/{first_case_id}/notes")
    assert visible_response.status_code == 200
    assert [note["content"] for note in visible_response.json()["notes"]] == ["first case note"]

    hidden_response = _client(session_factory, outsider).get(f"/api/workspace/{second_case_id}/notes")
    assert hidden_response.status_code == 404
    assert hidden_response.json()["detail"] == "Case not found"


def test_failed_save_rolls_back_without_duplicate_or_lost_content(
    session_factory,
    background_session_factory,
    monkeypatch,
):
    service = WorkspaceService()
    monkeypatch.setattr(
        workspace_service_module,
        "get_background_session",
        background_session_factory,
    )
    owner = _seed_user(session_factory)
    case_id = _seed_case(session_factory, owner)
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


def test_route_failure_does_not_create_duplicate_note(
    session_factory,
    background_session_factory,
    monkeypatch,
):
    monkeypatch.setattr(
        workspace_service_module,
        "get_background_session",
        background_session_factory,
    )
    monkeypatch.setattr(workspace_router_module.system_log_service, "log", lambda *args, **kwargs: None)
    owner = _seed_user(session_factory)
    case_id = _seed_case(session_factory, owner)
    service = WorkspaceService()
    service.save_note(
        str(case_id),
        {
            "note_id": "note_existing",
            "title": "Existing",
            "content": "existing content",
        },
    )

    def fail_save(case_id: str, note: dict) -> str:
        raise RuntimeError("simulated note save failure")

    monkeypatch.setattr(workspace_router_module.workspace_service, "save_note", fail_save)

    response = _client(session_factory, owner).post(
        f"/api/workspace/{case_id}/notes",
        json={"title": "Failed", "content": "failed content", "tags": []},
    )

    assert response.status_code == 500
    assert response.json()["detail"] == "simulated note save failure"
    assert _note_count(session_factory, case_id, "note_existing") == 1
    assert service.get_notes(str(case_id))[0]["content"] == "existing content"
