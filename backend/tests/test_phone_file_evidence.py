"""Phone files become evidence rows only on demand, and stay out of processing and AI (07 section 6.4 item 4)."""
from __future__ import annotations

import socket
import uuid
from unittest.mock import patch

import pytest
from sqlalchemy import func, select

from postgres import link_types
from postgres.models.evidence import EvidenceDocumentText, EvidenceFile
from postgres.models.user import User
from services import dossier_service, phone_files
from tests.test_dossier_service import setup_db  # noqa: F401  (fixture)


@pytest.fixture(autouse=True)
def permissions():
    with patch.object(dossier_service, "check_case_access", return_value=(None, None)), \
            patch.object(dossier_service, "get_case_if_allowed", return_value=None):
        yield


@pytest.fixture()
def phone(setup_db, tmp_path):
    _, _, case_id, *_ = setup_db
    photo = tmp_path / "IMG_0001.jpg"
    photo.write_bytes(b"synthetic")

    def resolver(db, case, target_id):
        if case != case_id or not target_id.startswith("pf-"):
            return None
        return link_types.PhoneTarget(label="Photo", mapping_versions={"media": "m1"}, metadata={
            "original_filename": "IMG_0001.jpg", "stored_path": str(photo), "size": 9, "sha256": "d" * 64,
            "phone_record_id": "rec-7", "extraction_id": "ext-1",
        })

    saved = dict(link_types._RESOLVERS)
    link_types._RESOLVERS.clear()
    link_types.register_phone_resolver("phone_file", resolver)
    phone_files.register_external_processing_check(None)
    yield
    link_types._RESOLVERS.clear()
    link_types._RESOLVERS.update(saved)
    phone_files.register_external_processing_check(None)


def _no_network(*args, **kwargs):
    raise AssertionError("an outbound connection was attempted")


def _dossier(db, case_id, user):
    return uuid.UUID(dossier_service.create_dossier(db, case_id=case_id, user=user,
                                                   data={"display_name": "Subject", "dossier_type": "person"})["id"])


def test_a_phone_photo_as_cover_registers_exactly_one_labelled_evidence_row(setup_db, phone):
    """CO-4 (lx-collect part)."""
    factory, user_id, case_id, *_ = setup_db
    with factory() as db, patch.object(socket.socket, "connect", _no_network):
        user = db.get(User, user_id)
        dossier_id = _dossier(db, case_id, user)
        before = db.scalar(select(func.count()).select_from(EvidenceFile).where(EvidenceFile.case_id == case_id))
        media = dossier_service.add_media(db, dossier_id=dossier_id, user=user,
                                          data={"phone_file_id": "pf-1", "is_cover": True})
        again = dossier_service.add_media(db, dossier_id=dossier_id, user=user, data={"phone_file_id": "pf-1"})
        assert media["id"] == again["id"] and media["is_cover"]
        other = _dossier(db, case_id, user)
        dossier_service.add_media(db, dossier_id=other, user=user, data={"phone_file_id": "pf-1"})
        rows = db.scalars(select(EvidenceFile).where(EvidenceFile.source_type == "phone_file")).all()
        assert len(rows) == 1
        assert db.scalar(select(func.count()).select_from(EvidenceFile).where(EvidenceFile.case_id == case_id)) == before + 1
        row = rows[0]
        assert (row.source_ref, row.status, row.case_id) == ("pf-1", "unprocessed", case_id)
        assert row.metadata_["origin_label"] == "Phone file used in a dossier"
        assert row.metadata_["phone_record_id"] == "rec-7"
        assert row.metadata_["mapping_versions"] == {"media": "m1"}
        from services.evidence_db_storage import EvidenceDBStorage

        record = EvidenceDBStorage._file_to_dict(row)
        assert (record["origin_label"], record["phone_record_id"]) == ("Phone file used in a dossier", "rec-7")


def test_a_phone_file_is_refused_until_the_phone_build_registers_it_and_outside_its_case(setup_db, phone):
    factory, user_id, case_id, *_ = setup_db
    with factory() as db:
        user = db.get(User, user_id)
        dossier_id = _dossier(db, case_id, user)
        with pytest.raises(link_types.LinkTargetError, match="not found in this case"):
            dossier_service.add_media(db, dossier_id=dossier_id, user=user, data={"phone_file_id": "other-1"})
        link_types.unregister_phone_resolver("phone_file")
        with pytest.raises(link_types.PhoneLinkUnavailable):
            dossier_service.add_media(db, dossier_id=dossier_id, user=user, data={"phone_file_id": "pf-2"})
        db.rollback()
        assert db.scalar(select(EvidenceFile.id).where(EvidenceFile.source_type == "phone_file")) is None


def test_phone_file_rows_are_not_processed_or_used_as_ai_sources_without_the_case_decision(setup_db, phone):
    from services import evidence_processing_service, workspace_ai_service

    factory, user_id, case_id, image_id, source_id, _ = setup_db
    with factory() as db:
        EvidenceDocumentText.__table__.create(db.get_bind(), checkfirst=True)
        user = db.get(User, user_id)
        row, created = phone_files.ensure_phone_file_evidence(db, case_id=case_id, phone_file_id="pf-1", user=user)
        db.commit()
        assert created
        early = evidence_processing_service._prepare_files(
            db, case_id=case_id, file_ids=[row.id], force_reprocess=False, preparation_mode="standard",
            requested_by_user_id=user_id, ingestion_request_id="t")
        assert early["job_ids"] == [] and early["skipped_phone_files"] == 1
        assert "no decision allowing phone material" in early["message"]
        assert [f.id for f in workspace_ai_service._load_evidence_with_text(db, [row.id, source_id])] == [source_id]

        phone_files.register_external_processing_check(lambda db, case, file: case == case_id)
        assert phone_files.external_processing_allowed(db, row)
        assert [f.id for f in workspace_ai_service._load_evidence_with_text(db, [row.id])] == [row.id]
        phone_files.register_external_processing_check(None)
        image = db.get(EvidenceFile, image_id)
        assert phone_files.external_processing_allowed(db, image)  # other evidence is unaffected


def test_candidate_documents_never_give_a_place_to_a_phone_file_without_the_decision(setup_db, phone):
    from services import workspace_ai_service

    factory, user_id, case_id, _, source_id, _ = setup_db
    with factory() as db:
        engine = db.get_bind()
        EvidenceDocumentText.__table__.create(engine, checkfirst=True)
        row, _ = phone_files.ensure_phone_file_evidence(db, case_id=case_id, phone_file_id="pf-1",
                                                       user=db.get(User, user_id))
        for file_id in (row.id, source_id):
            db.add(EvidenceDocumentText(evidence_file_id=file_id, content="payment corroborate",
                                        content_sha256="e" * 64, character_count=19))
        db.commit()
        ids = workspace_ai_service._candidate_document_ids(db, case_id=case_id, terms=["payment"], mode="supporting")
        assert ids == [source_id]
