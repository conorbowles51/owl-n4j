"""Dossier contacts carry a record source; contacts copied from phones are not suggestion material (07 6.4 item 6)."""
from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from sqlalchemy import select

from postgres import link_types
from postgres.models.case_profile import CaseProfile
from postgres.models.user import User
from services import dossier_service
from tests.test_dossier_service import setup_db  # noqa: F401  (fixture)


@pytest.fixture(autouse=True)
def permissions():
    with patch.object(dossier_service, "check_case_access", return_value=(None, None)), \
            patch.object(dossier_service, "get_case_if_allowed", return_value=None):
        yield


@pytest.fixture()
def phone(setup_db):
    _, _, case_id, *_ = setup_db
    saved = dict(link_types._RESOLVERS)
    link_types._RESOLVERS.clear()
    link_types.register_phone_resolver("phone_record", lambda db, case, target: link_types.PhoneTarget(
        label="Contact", mapping_versions={"contact": "m4"}) if case == case_id and target == "rec-c1" else None)
    yield
    link_types._RESOLVERS.clear()
    link_types._RESOLVERS.update(saved)


def test_each_contact_records_where_it_came_from(setup_db, phone):
    factory, user_id, case_id, _, source_id, _ = setup_db
    with factory() as db:
        user = db.get(User, user_id)
        dossier = dossier_service.create_dossier(db, case_id=case_id, user=user, data={"display_name": "Witness", "contacts": [
            {"kind": "phone", "value": "+1 555 0100"},
            {"kind": "phone", "value": "+1 555 0101", "evidence_file_id": source_id},
            {"kind": "phone", "value": "+1 555 0102", "record_source": {"type": "phone_record", "target_id": "rec-c1"}},
        ]})
        sources = [contact["record_source"] for contact in dossier["contacts"]]
        assert sources == [
            {"type": "manual"},
            {"type": "evidence", "target_id": str(source_id)},
            {"type": "phone_record", "target_id": "rec-c1", "mapping_versions": {"contact": "m4"}},
        ]
        with pytest.raises(link_types.LinkTargetError, match="not found in this case"):
            dossier_service.update_dossier(db, dossier_id=uuid.UUID(dossier["id"]), user=user, data={"contacts": [
                {"kind": "phone", "value": "x", "record_source": {"type": "phone_record", "target_id": "rec-other"}}]})
        db.rollback()
        with pytest.raises(ValueError, match="needs the phone record"):
            dossier_service.update_dossier(db, dossier_id=uuid.UUID(dossier["id"]), user=user, data={"contacts": [
                {"kind": "phone", "value": "x", "record_source": {"type": "phone_record"}}]})


def test_contacts_copied_from_phones_are_excluded_from_suggestions(setup_db, phone):
    factory, user_id, case_id, *_ = setup_db
    with factory() as db:
        user = db.get(User, user_id)
        dossier_service.create_dossier(db, case_id=case_id, user=user, data={"display_name": "Witness", "contacts": [
            {"kind": "phone", "value": "+1 555 0100"},
            {"kind": "phone", "value": "+1 555 0102", "record_source": {"type": "phone_record", "target_id": "rec-c1"}},
        ]})
        eligible = dossier_service.contacts_for_suggestions(db, case_id)
        assert [item["value"] for item in eligible] == ["+1 555 0100"]


def test_a_contact_saved_before_sources_keeps_its_recorder_when_someone_else_edits_the_dossier(setup_db):
    factory, user_id, case_id, _, source_id, _ = setup_db
    other_id = uuid.uuid4()
    with factory() as db:
        db.add(User(id=other_id, email="other@example.test", name="Other", password_hash="x"))
        user = db.get(User, user_id)
        dossier = dossier_service.create_dossier(db, case_id=case_id, user=user, data={"display_name": "Witness"})
        row = db.get(CaseProfile, uuid.UUID(dossier["id"]))
        old = {"id": str(uuid.uuid4()), "kind": "phone", "label": None, "value": "+1 555 0100",
               "evidence_file_id": str(source_id), "recorded_by_user_id": str(user_id)}
        row.contacts = [old]
        db.commit()
        sent = {key: old[key] for key in ("id", "kind", "label", "value", "evidence_file_id")}
        updated = dossier_service.update_dossier(db, dossier_id=row.id, user=db.get(User, other_id),
                                                 data={"contacts": [sent]})
        assert updated["contacts"][0]["recorded_by_user_id"] == str(user_id)
        assert updated["contacts"][0]["record_source"] == {"type": "evidence", "target_id": str(source_id)}
        assert dossier_service.contacts_for_suggestions(db, case_id)[0]["value"] == "+1 555 0100"
