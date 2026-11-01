"""The one link-type registry (07 section 6.4 items 1 and 13)."""

from __future__ import annotations

import importlib.util
import typing
import uuid
from pathlib import Path

import pytest

from postgres import link_types
from postgres.link_types import PhoneTarget

BACKEND = Path(__file__).resolve().parents[1]
CASE = uuid.uuid4()


@pytest.fixture(autouse=True)
def _no_resolvers():
    saved = dict(link_types._RESOLVERS)
    link_types._RESOLVERS.clear()
    yield
    link_types._RESOLVERS.clear()
    link_types._RESOLVERS.update(saved)


def _check_text(model, name):
    for constraint in model.__table__.constraints:
        if constraint.name == name:
            return str(constraint.sqltext)
    raise AssertionError(name)


def test_generated_typescript_is_current():
    from scripts import generate_link_types

    assert generate_link_types.main(["--check"]) == 0


def test_models_routers_and_services_take_the_registry_lists():
    from postgres.models.work import CaseTaskLink
    from postgres.models.workspace_entry import ENTRY_LINK_TARGET_TYPES, WorkspaceEntryLink
    from routers.notebook import NotebookTargetType
    from routers.workspace_entries import LinkTargetType
    from services import dossier_service, notebook_service, work_service

    assert ENTRY_LINK_TARGET_TYPES == link_types.WORKSPACE_TYPES
    assert _check_text(WorkspaceEntryLink, "ck_workspace_entry_links_target_type") == link_types.sql_in_check(
        "target_type", link_types.WORKSPACE_TYPES
    )
    assert _check_text(CaseTaskLink, "ck_case_task_links_target_type") == link_types.sql_in_check(
        "target_type", link_types.TASK_TYPES
    )
    assert typing.get_args(LinkTargetType) == link_types.WORKSPACE_TYPES
    assert typing.get_args(NotebookTargetType) == link_types.NOTEBOOK_TYPES
    assert dossier_service.LINK_TARGET_TYPES == link_types.DOSSIER_TYPES
    assert notebook_service.NOTEBOOK_TARGET_TYPES == link_types.NOTEBOOK_TYPES
    assert work_service.TASK_LINK_TYPES == link_types.TASK_TYPES


def test_migration_allows_exactly_the_registry_types():
    spec = importlib.util.spec_from_file_location(
        "m", BACKEND / "postgres/alembic/versions/20261101_link_registry.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    def parse(text):
        return tuple(value.strip().strip("'") for value in text.split(","))

    assert parse(module.WORKSPACE_OLD) + parse(module.PHONE) == link_types.WORKSPACE_TYPES
    assert parse(module.TASK_OLD) + parse(module.PHONE) == link_types.TASK_TYPES


def test_every_phone_type_is_refused_with_a_stated_message_until_a_resolver_registers():
    from services import dossier_service, work_service
    from services.workspace_entry_service import WorkspaceEntryValidationError, _sanitize_link

    for target_type in link_types.PHONE_TYPES:
        expected = link_types.PHONE_TYPE_UNAVAILABLE_MESSAGE.format(target_type=target_type)
        with pytest.raises(WorkspaceEntryValidationError) as workspace:
            _sanitize_link(object(), case_id=CASE, link={"target_type": target_type, "target_id": "r1"})
        assert str(workspace.value) == expected
        with pytest.raises(work_service.WorkValidationError) as task:
            work_service._validate_link(object(), CASE, {"target_type": target_type, "target_id": "r1"})
        assert str(task.value) == expected
        if target_type in link_types.DOSSIER_TYPES:
            with pytest.raises(link_types.PhoneLinkUnavailable) as dossier:
                dossier_service._validate_target(object(), CASE, target_type, "r1")
            assert str(dossier.value) == expected


def test_a_registered_resolver_checks_the_case_and_the_link_keeps_the_mapping_version_set():
    from services import work_service
    from services.workspace_entry_service import WorkspaceEntryValidationError, _sanitize_link

    calls = []

    def resolver(db, case_id, target_id):
        calls.append((case_id, target_id))
        if target_id != "r1":
            return None
        return PhoneTarget(label="Message 1", mapping_versions={"sender": "m3"})

    link_types.register_phone_resolver("phone_record", resolver)
    data = _sanitize_link(
        object(), case_id=CASE,
        link={"target_type": "phone_record", "target_id": "r1", "source_anchor": {"field_path": "body"}},
        validate_target=False,
    )
    assert data["source_anchor"] == {"field_path": "body", "mapping_versions": {"sender": "m3"}}
    assert data["target_label"] == "Message 1"
    assert calls == [(CASE, "r1")]  # checked even when the caller skips target validation
    with pytest.raises(WorkspaceEntryValidationError, match="not found in this case"):
        _sanitize_link(object(), case_id=CASE, link={"target_type": "phone_record", "target_id": "r2"})
    anchor = work_service._validate_link(object(), CASE, {"target_type": "phone_record", "target_id": "r1"})
    assert anchor == {"mapping_versions": {"sender": "m3"}}


def test_register_refuses_a_type_that_is_not_a_phone_type():
    with pytest.raises(ValueError):
        link_types.register_phone_resolver("evidence", lambda db, case, target: None)


def _snapshot(**changes):
    snapshot = {
        "kind": "co_location",
        "subject": {"identity_keys": ["i1", "i2"]},
        "window": {"start": "2026-01-01T00:00:00Z", "end": "2026-01-02T00:00:00Z"},
        "parameters": {"radius_m": 200},
        "mapping_versions": {"location": "m1"},
        "record_ids": ["r1", "r2"],
        "summary_counts": {"meetings": 2},
    }
    snapshot.update(changes)
    return snapshot


def test_phone_analysis_snapshot_has_the_frozen_shape_and_a_stable_id():
    assert link_types.validate_phone_analysis_snapshot(_snapshot())["record_ids"] == ["r1", "r2"]
    assert link_types.phone_analysis_snapshot_id(_snapshot()) == link_types.phone_analysis_snapshot_id(_snapshot())
    assert link_types.phone_analysis_snapshot_id(_snapshot()) != link_types.phone_analysis_snapshot_id(
        _snapshot(summary_counts={"meetings": 3})
    )
    incomplete = _snapshot()
    del incomplete["mapping_versions"]
    for bad in (incomplete, _snapshot(extra=1), _snapshot(window={"start": "x"}),
                _snapshot(summary_counts={"meetings": -1}), _snapshot(record_ids=[""])):
        with pytest.raises(link_types.LinkTargetError):
            link_types.validate_phone_analysis_snapshot(bad)


def test_a_phone_analysis_link_freezes_its_snapshot_and_refuses_one_that_does_not_match():
    from services.workspace_entry_service import WorkspaceEntryValidationError, _sanitize_link

    snapshot = _snapshot()
    snapshot_id = link_types.phone_analysis_snapshot_id(snapshot)
    link_types.register_phone_resolver("phone_analysis", lambda db, case, target: PhoneTarget(
        label="Co-location", mapping_versions={}, metadata={"snapshot": snapshot}))
    data = _sanitize_link(object(), case_id=CASE, link={"target_type": "phone_analysis", "target_id": snapshot_id})
    assert data["source_anchor"]["snapshot"] == link_types.validate_phone_analysis_snapshot(snapshot)
    assert data["source_anchor"]["mapping_versions"] == {"location": "m1"}
    with pytest.raises(WorkspaceEntryValidationError, match="does not match its snapshot"):
        _sanitize_link(object(), case_id=CASE, link={"target_type": "phone_analysis", "target_id": "pa_recomputed"})
