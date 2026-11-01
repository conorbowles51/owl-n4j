"""Interview evidence takes registry targets (07 section 6.4 item 5; CO-17 API)."""
from __future__ import annotations

import importlib.util
import os
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import IntegrityError

from postgres import link_types
from postgres.models.dossier import DossierInterviewEvidenceLink
from postgres.models.evidence import EvidenceFile
from postgres.models.user import User
from services import dossier_service
from tests.test_dossier_service import setup_db  # noqa: F401  (fixture)

BACKEND = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def permissions():
    with patch.object(dossier_service, "check_case_access", return_value=(None, None)), \
            patch.object(dossier_service, "get_case_if_allowed", return_value=None), \
            patch.object(dossier_service, "_case_member_ids", return_value=set()):
        yield


@pytest.fixture()
def phone(setup_db, tmp_path):
    _, _, case_id, *_ = setup_db
    records = {"msg-1": "Message", "call-1": "Call"}

    def record(db, case, target_id):
        if case != case_id or target_id not in records:
            return None
        return link_types.PhoneTarget(label=records[target_id], mapping_versions={"sender": "m2"})

    def phone_file(db, case, target_id):
        return link_types.PhoneTarget(label="Voice note", mapping_versions={"media": "m1"}, metadata={
            "original_filename": "note.opus", "stored_path": str(tmp_path / "note.opus"), "size": 3,
            "sha256": "f" * 64, "phone_record_id": "msg-1"}) if case == case_id else None

    saved = dict(link_types._RESOLVERS)
    link_types._RESOLVERS.clear()
    link_types.register_phone_resolver("phone_record", record)
    link_types.register_phone_resolver("phone_file", phone_file)
    yield
    link_types._RESOLVERS.clear()
    link_types._RESOLVERS.update(saved)


def _interview(db, case_id, user, evidence_links):
    dossier = dossier_service.create_dossier(db, case_id=case_id, user=user, data={"display_name": "Witness"})
    dossier_id = uuid.UUID(dossier["id"])
    return dossier_id, dossier_service.create_interview(
        db, dossier_id=dossier_id, user=user, data={"status": "completed", "evidence_links": evidence_links})


def test_a_message_and_a_call_attached_to_an_interview_are_listed_and_open_back_to_their_records(setup_db, phone):
    """CO-17 (API)."""
    factory, user_id, case_id, image_id, *_ = setup_db
    with factory() as db:
        user = db.get(User, user_id)
        dossier_id, interview = _interview(db, case_id, user, [
            {"evidence_file_id": image_id},
            {"target_type": "phone_record", "target_id": "msg-1", "source_anchor": {"field_path": "body", "range": [0, 12]}},
            {"target_type": "phone_record", "target_id": "call-1"},
            {"target_type": "phone_record", "target_id": "msg-1"},
        ])
        listed = [(item["target_type"], item["target_id"]) for item in interview["evidence_links"]]
        assert listed == [("evidence", str(image_id)), ("phone_record", "msg-1"), ("phone_record", "call-1")]
        message = interview["evidence_links"][1]
        assert message["evidence_file_id"] is None and message["evidence"] is None
        assert message["source_anchor"] == {"field_path": "body", "range": [0, 12], "mapping_versions": {"sender": "m2"}}
        reread = dossier_service.get_dossier(db, dossier_id=dossier_id, user=user)
        assert [(item["target_type"], item["target_id"]) for item in reread["interviews"][0]["evidence_links"]] == listed


def test_a_phone_voice_note_becomes_one_evidence_row_and_unknown_targets_are_refused(setup_db, phone):
    factory, user_id, case_id, *_ = setup_db
    with factory() as db:
        user = db.get(User, user_id)
        _, interview = _interview(db, case_id, user, [{"target_type": "phone_file", "target_id": "pf-9"}])
        item = interview["evidence_links"][0]
        assert item["target_type"] == "evidence" and item["source_anchor"] == {"phone_file_id": "pf-9"}
        assert db.scalar(select(EvidenceFile.source_type).where(EvidenceFile.id == uuid.UUID(item["evidence_file_id"]))) == "phone_file"
        with pytest.raises(link_types.LinkTargetError, match="not found in this case"):
            _interview(db, case_id, user, [{"target_type": "phone_record", "target_id": "nope"}])
        db.rollback()
        with pytest.raises(ValueError, match="cannot be a phone_thread"):
            _interview(db, case_id, user, [{"target_type": "phone_thread", "target_id": "t"}])


def test_the_database_requires_exactly_one_of_file_or_target(setup_db):
    factory, user_id, case_id, image_id, *_ = setup_db
    with factory() as db:
        user = db.get(User, user_id)
        _, interview = _interview(db, case_id, user, [])
        interview_id = uuid.UUID(interview["id"])
        for bad in ({"evidence_file_id": image_id, "target_type": "phone_record", "target_id": "x"},
                    {"evidence_file_id": None}, {"target_type": "phone_record"}):
            db.add(DossierInterviewEvidenceLink(interview_id=interview_id, case_id=case_id, source_anchor={}, **bad))
            with pytest.raises(IntegrityError):
                db.flush()
            db.rollback()


def test_reconciliation_reports_phone_record_interview_evidence_beside_file_evidence(setup_db, phone):
    """An interview with one evidence file and one phone record: both are reconciled; the record by type and id."""
    from services.dossier_reconciliation_service import build_dossier_reconciliation_report

    from postgres.models.workspace import WorkspaceWitness
    from postgres.models.workspace_entry import WorkspaceEntry, WorkspaceEntryLink

    factory, user_id, case_id, image_id, *_ = setup_db
    with factory() as db:
        for table in (WorkspaceWitness.__table__, WorkspaceEntry.__table__, WorkspaceEntryLink.__table__):
            table.create(db.get_bind(), checkfirst=True)
        user = db.get(User, user_id)
        _, interview = _interview(db, case_id, user, [
            {"evidence_file_id": image_id},
            {"target_type": "phone_record", "target_id": "msg-1"},
        ])
        record_link = interview["evidence_links"][1]
        report = build_dossier_reconciliation_report(db, case_id=case_id)
        assert report["summary"]["interview_evidence_targets"] == {"phone_record": 1}
        assert report["summary"]["interview_evidence_targets_unchecked"] == 0
        assert report["interview_evidence_targets"] == [
            {"id": record_link["id"], "target_type": "phone_record", "target_id": "msg-1", "checked": True}]
        assert report["integrity_errors"] == []

        # A record that no longer resolves in the case is an integrity error, not left out.
        link_types.unregister_phone_resolver("phone_record")
        link_types.register_phone_resolver("phone_record", lambda db, case, target_id: None)
        report = build_dossier_reconciliation_report(db, case_id=case_id)
        assert report["integrity_errors"] == [{"kind": "invalid_interview_evidence_target", "id": record_link["id"]}]
        assert report["passed"] is False


@pytest.mark.skipif(not os.environ.get("DOSSIER_TEST_DATABASE_URL"), reason="Requires an explicit local PostgreSQL test connection")
def test_migration_keeps_every_existing_row_and_counts_them(capsys):
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    admin = create_engine(os.environ["DOSSIER_TEST_DATABASE_URL"])
    schema = "lxc_" + uuid.uuid4().hex
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(os.environ["DOSSIER_TEST_DATABASE_URL"], connect_args={"options": f"-csearch_path={schema}"})
    try:
        spec = importlib.util.spec_from_file_location(
            "m", BACKEND / "postgres/alembic/versions/20261101_interview_evidence_targets.py")
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        with engine.begin() as connection:
            connection.execute(text(
                "CREATE TABLE dossier_interview_evidence_links (id uuid PRIMARY KEY, interview_id uuid NOT NULL, "
                "case_id uuid NOT NULL, evidence_file_id uuid NOT NULL, source_anchor jsonb NOT NULL DEFAULT '{}', "
                "CONSTRAINT uq_dossier_interview_evidence UNIQUE (interview_id, evidence_file_id))"))
            rows = [(uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()) for _ in range(18)]
            for row in rows:
                connection.execute(text("INSERT INTO dossier_interview_evidence_links (id, interview_id, case_id, evidence_file_id) "
                                        "VALUES (:a, :b, :c, :d)"), dict(zip("abcd", row)))
            before = connection.execute(text("SELECT id, interview_id, evidence_file_id, source_anchor::text FROM dossier_interview_evidence_links ORDER BY id")).all()
            with Operations.context(MigrationContext.configure(connection)):
                migration.upgrade()
            after = connection.execute(text("SELECT id, interview_id, evidence_file_id, source_anchor::text FROM dossier_interview_evidence_links ORDER BY id")).all()
            assert after == before and len(after) == 18
            assert "before 18, after 18" in capsys.readouterr().out
            with Operations.context(MigrationContext.configure(connection)):
                migration.downgrade()
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()
