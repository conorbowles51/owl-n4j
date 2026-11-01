"""Workspace links added by people in bulk (07 section 6.4 item 3)."""
from __future__ import annotations

import ast
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from postgres import link_types
from postgres.base import Base
from postgres.models.case import Case
from postgres.models.collection_membership import CollectionMembership
from postgres.models.user import User
from postgres.models.workspace_entry import WorkspaceEntryEvent, WorkspaceEntryLink
from services import workspace_entry_service as service
from tests.test_workspace_entry_service import ENTRY_TABLES

BACKEND = Path(__file__).resolve().parents[1]


@pytest.fixture()
def world():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine, tables=ENTRY_TABLES + [CollectionMembership.__table__])
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    user_id, case_id = uuid.uuid4(), uuid.uuid4()
    with factory() as db:
        db.add(User(id=user_id, email="owner@example.test", name="Owner", password_hash="x"))
        db.flush()
        db.add(Case(id=case_id, title="Case", created_by_user_id=user_id, owner_user_id=user_id))
        db.commit()
        finding = service.create_entry(db, case_id=case_id, current_user=db.get(User, user_id), entry_type="finding",
                                       title="Synthetic finding", body="synthetic")
    saved = dict(link_types._RESOLVERS)
    link_types._RESOLVERS.clear()
    link_types.register_phone_resolver(
        "phone_record", lambda db, case, target: link_types.PhoneTarget(label=f"Record {target}", mapping_versions={"m": 1}))
    link_types.register_phone_resolver(
        "phone_selection", lambda db, case, target: link_types.PhoneTarget(
            label="Selection", mapping_versions={"m": 1}, members=tuple(f"rec-{n}" for n in range(12345))))
    yield factory, user_id, case_id, uuid.UUID(finding["id"])
    link_types._RESOLVERS.clear()
    link_types._RESOLVERS.update(saved)
    engine.dispose()


def test_batch_add_keeps_the_callers_rationale_and_counts_and_is_idempotent(world):
    factory, user_id, case_id, entry_id = world
    links = [{"target_type": "phone_record", "target_id": f"r{n}", "relationship": "supports"} for n in range(3)]
    with factory() as db:
        user = db.get(User, user_id)
        first = service.batch_add_entry_links(db, case_id=case_id, entry_id=entry_id, current_user=user,
                                              links=links[:2], rationale="Added from Conversations")
        assert (first["added"], first["skipped"]) == (2, 0)
        second = service.batch_add_entry_links(db, case_id=case_id, entry_id=entry_id, current_user=user,
                                               links=links, rationale="Added from Search")
        assert (second["added"], second["skipped"]) == (1, 2)
        events = db.scalars(select(WorkspaceEntryEvent).where(WorkspaceEntryEvent.event_type == "link_added")
                            .order_by(WorkspaceEntryEvent.created_at)).all()
        assert [event.rationale for event in events] == ["Added from Conversations", "Added from Search"]
        assert [(event.after_state["added"], event.after_state["skipped"]) for event in events] == [(2, 0), (1, 2)]
        assert "Accepted Workspace AI proposal" not in {event.rationale for event in events}
        rows = db.scalars(select(WorkspaceEntryLink)).all()
        assert {row.target_label for row in rows} == {"Record r0", "Record r1", "Record r2"}
        assert all(row.created_by_user_id == user_id and row.source_anchor["mapping_versions"] == {"m": 1} for row in rows)


def test_batch_add_needs_a_rationale_and_refuses_more_than_the_limit_without_adding(world):
    factory, user_id, case_id, entry_id = world
    with factory() as db:
        user = db.get(User, user_id)
        with pytest.raises(service.WorkspaceEntryValidationError, match="where these links were added from"):
            service.batch_add_entry_links(db, case_id=case_id, entry_id=entry_id, current_user=user,
                                          links=[{"target_type": "phone_record", "target_id": "r"}], rationale=" ")
        too_many = [{"target_type": "phone_record", "target_id": f"r{n}"} for n in range(service.ENTRY_LINKS_BATCH_LIMIT + 1)]
        with pytest.raises(service.WorkspaceEntryValidationError, match="nothing was added"):
            service.batch_add_entry_links(db, case_id=case_id, entry_id=entry_id, current_user=user,
                                          links=too_many, rationale="Added from Conversations")
        assert db.scalar(select(WorkspaceEntryLink.id)) is None


def test_a_selection_link_is_one_link_and_indexes_every_record(world):
    factory, user_id, case_id, entry_id = world
    with factory() as db:
        result = service.batch_add_entry_links(
            db, case_id=case_id, entry_id=entry_id, current_user=db.get(User, user_id),
            links=[{"target_type": "phone_selection", "target_id": "sel-1"}], rationale="Added from Conversations")
        assert result["added"] == 1
        assert db.scalar(select(WorkspaceEntryLink.id).where(WorkspaceEntryLink.target_type == "phone_selection"))
        members = db.scalars(select(CollectionMembership.record_id)).all()
        assert len(members) == 12345 and set(members) == {f"rec-{n}" for n in range(12345)}


def test_the_ai_acceptance_rationale_is_written_only_by_the_workspace_ai_service():
    sources = {path.relative_to(BACKEND): path.read_text(encoding="utf-8")
               for path in BACKEND.glob("**/*.py") if "tests" not in path.parts and ".venv" not in path.parts}
    assert [str(path) for path, text in sources.items() if "Accepted Workspace AI proposal" in text] == [
        "services/workspace_ai_service.py"]
    tree = ast.parse(sources[Path("services/workspace_entry_service.py")])
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "add_entry_links")
    assert "rationale" in [arg.arg for arg in function.args.kwonlyargs]
    rationale_default = dict(zip([a.arg for a in function.args.kwonlyargs], function.args.kw_defaults))["rationale"]
    assert rationale_default is None  # required: no caller gets the AI wording by default
