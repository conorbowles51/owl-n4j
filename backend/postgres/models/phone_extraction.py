"""Phone capture tables (docs/cellebrite/01-intake-capture-storage.md section 6.2).

The migration ``20261101_phone_capture`` owns the schema, including the expression and partial indexes that
are not repeated here. The evidence engine writes the capture through its own Core mirror
(``evidence-engine/app/models/phone.py``); the backend reads it and owns standing changes (supersede, 10.7).
"""
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Enum, ForeignKey, ForeignKeyConstraint, Integer, JSON, \
    SmallInteger, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from postgres.base import Base

CAPTURE_STATES = ("received", "detecting", "not_readable", "counting", "capturing", "reconciling", "captured",
                  "captured_incomplete", "reconciliation_failed", "failed", "cancelled")
STANDINGS = ("pending", "active", "superseded")
CAPTURED_STATES = ("captured", "captured_incomplete")


def _json():
    return JSONB().with_variant(JSON(), "sqlite")


def _uuid():
    return UUID(as_uuid=True)


class PhoneExtractionContainer(Base):
    __tablename__ = "phone_extraction_containers"
    id: Mapped[uuid.UUID] = mapped_column(_uuid(), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(_uuid(), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)
    evidence_file_id: Mapped[uuid.UUID | None] = mapped_column(
        _uuid(), ForeignKey("evidence_files.id", ondelete="SET NULL"), nullable=True, index=True)
    upload_group_id: Mapped[uuid.UUID | None] = mapped_column(
        _uuid(), ForeignKey("evidence_upload_groups.id", ondelete="SET NULL"), nullable=True)
    container_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    stored_path: Mapped[str] = mapped_column(Text, nullable=False)
    original_name: Mapped[str] = mapped_column(String(1024), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    md5: Mapped[str] = mapped_column(String(32), nullable=False)
    upload_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    intake_outcome: Mapped[str] = mapped_column(String(40), nullable=False)
    classification: Mapped[dict] = mapped_column(_json(), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    received_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        _uuid(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


class PhoneExtraction(Base):
    __tablename__ = "phone_extractions"
    __table_args__ = (UniqueConstraint("case_id", "report_set_sha256", name="uq_phone_extraction_report"),)
    id: Mapped[uuid.UUID] = mapped_column(_uuid(), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(_uuid(), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)
    report_set_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    first_container_id: Mapped[uuid.UUID] = mapped_column(
        _uuid(), ForeignKey("phone_extraction_containers.id"), nullable=False)
    form: Mapped[str] = mapped_column(String(20), nullable=False)
    capture_state: Mapped[str] = mapped_column(
        Enum(*CAPTURE_STATES, name="phone_capture_state", create_type=False), nullable=False, default="received")
    standing: Mapped[str] = mapped_column(
        Enum(*STANDINGS, name="phone_extraction_standing", create_type=False), nullable=False, default="pending")
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(
        _uuid(), ForeignKey("phone_extractions.id"), nullable=True)
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    superseded_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        _uuid(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    superseded_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    report_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    producer_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    extraction_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    device_zone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    device_zone_source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    flags: Mapped[dict] = mapped_column(_json(), nullable=False, default=dict)
    record_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    file_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # The migration's foreign key to the engine's ``jobs`` table is not repeated: jobs has no backend model.
    engine_job_id: Mapped[uuid.UUID | None] = mapped_column(_uuid(), nullable=True)
    capture_code_version: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PhoneExtractionContainerLink(Base):
    __tablename__ = "phone_extraction_container_links"
    extraction_id: Mapped[uuid.UUID] = mapped_column(
        _uuid(), ForeignKey("phone_extractions.id", ondelete="CASCADE"), primary_key=True)
    container_id: Mapped[uuid.UUID] = mapped_column(
        _uuid(), ForeignKey("phone_extraction_containers.id", ondelete="CASCADE"), primary_key=True)
    root_path: Mapped[str] = mapped_column(Text, primary_key=True)
    linked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class PhoneExtractionDocument(Base):
    __tablename__ = "phone_extraction_documents"
    extraction_id: Mapped[uuid.UUID] = mapped_column(
        _uuid(), ForeignKey("phone_extractions.id", ondelete="CASCADE"), primary_key=True)
    document_index: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    md5: Mapped[str] = mapped_column(String(32), nullable=False)
    root_element: Mapped[str | None] = mapped_column(String(64), nullable=True)
    parse_state: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    truncation: Mapped[dict | None] = mapped_column(_json(), nullable=True)
    skeleton: Mapped[list | None] = mapped_column(_json(), nullable=True)
    source_counts: Mapped[dict | None] = mapped_column(_json(), nullable=True)
    capture_cursor: Mapped[dict] = mapped_column(_json(), nullable=False, default=lambda: {
        "record_ordinal": 0, "file_ordinal": 0, "extra_ordinal": 0})


def _doc_fk():
    return ForeignKeyConstraint(["extraction_id", "document_index"],
                                ["phone_extraction_documents.extraction_id",
                                 "phone_extraction_documents.document_index"], ondelete="CASCADE")


class PhoneRecord(Base):
    __tablename__ = "phone_records"
    __table_args__ = (_doc_fk(),)
    extraction_id: Mapped[uuid.UUID] = mapped_column(_uuid(), primary_key=True)
    document_index: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    ordinal: Mapped[int] = mapped_column(Integer, primary_key=True)
    parent_ordinal: Mapped[int | None] = mapped_column(Integer, nullable=True)
    top_ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    depth: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    model_type: Mapped[str] = mapped_column(String(128), nullable=False)
    source_model_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    deleted_state: Mapped[str | None] = mapped_column(String(32), nullable=True)
    is_partial: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    body: Mapped[list] = mapped_column(_json(), nullable=False)


class PhoneFile(Base):
    __tablename__ = "phone_files"
    __table_args__ = (_doc_fk(),)
    extraction_id: Mapped[uuid.UUID] = mapped_column(_uuid(), primary_key=True)
    document_index: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    ordinal: Mapped[int] = mapped_column(Integer, primary_key=True)
    # 02 section 1.2: the id a phone file is linked by, uuid5 of the positional key (services.phone.ids)
    file_uid: Mapped[uuid.UUID] = mapped_column(_uuid(), nullable=False, unique=True)
    parent_ordinal: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_file_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    local_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    declared_size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    declared_md5: Mapped[str | None] = mapped_column(String(64), nullable=True)
    declared_sha256: Mapped[str | None] = mapped_column(String(128), nullable=True)
    tags: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_partial: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    body: Mapped[list] = mapped_column(_json(), nullable=False)
    disk_relpath: Mapped[str | None] = mapped_column(Text, nullable=True)
    disk_size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    disk_md5: Mapped[str | None] = mapped_column(String(32), nullable=True)
    disk_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    outcome: Mapped[str | None] = mapped_column(String(24), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PhoneContainerEntry(Base):
    __tablename__ = "phone_container_entries"
    extraction_id: Mapped[uuid.UUID] = mapped_column(
        _uuid(), ForeignKey("phone_extractions.id", ondelete="CASCADE"), primary_key=True)
    relpath: Mapped[str] = mapped_column(Text, primary_key=True)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    md5: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # where the member sits in the archive it was listed from (NULL for a folder upload); cb-media item F
    container_id: Mapped[uuid.UUID | None] = mapped_column(_uuid(), nullable=True)
    header_offset: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    compressed_size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    compress_type: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    crc32: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


class PhoneFileReference(Base):
    __tablename__ = "phone_file_references"
    __table_args__ = (_doc_fk(),)
    extraction_id: Mapped[uuid.UUID] = mapped_column(_uuid(), primary_key=True)
    document_index: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    record_ordinal: Mapped[int] = mapped_column(Integer, primary_key=True)
    body_path: Mapped[str] = mapped_column(Text, primary_key=True)
    mechanism: Mapped[str] = mapped_column(String(24), primary_key=True)
    reference_text: Mapped[str] = mapped_column(Text, nullable=False)
    file_document_index: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    file_ordinal: Mapped[int | None] = mapped_column(Integer, nullable=True)
    container_relpath: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolution: Mapped[str] = mapped_column(String(24), nullable=False)
    ambiguous: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class PhoneTimestamp(Base):
    __tablename__ = "phone_timestamps"
    __table_args__ = (_doc_fk(),)
    extraction_id: Mapped[uuid.UUID] = mapped_column(_uuid(), primary_key=True)
    document_index: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    owner_kind: Mapped[str] = mapped_column(String(8), primary_key=True)
    owner_ordinal: Mapped[int] = mapped_column(Integer, primary_key=True)
    body_path: Mapped[str] = mapped_column(Text, primary_key=True)
    model_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    field_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    value_type: Mapped[str] = mapped_column(String(64), nullable=False)
    original_text: Mapped[str] = mapped_column(Text, nullable=False)
    formatted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    instant: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    local_wall_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    original_offset_minutes: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    offset_state: Mapped[str] = mapped_column(String(12), nullable=False)
    parse_rule: Mapped[str] = mapped_column(String(48), nullable=False)


class PhoneReconciliation(Base):
    __tablename__ = "phone_reconciliations"
    id: Mapped[uuid.UUID] = mapped_column(_uuid(), primary_key=True, default=uuid.uuid4)
    extraction_id: Mapped[uuid.UUID] = mapped_column(
        _uuid(), ForeignKey("phone_extractions.id", ondelete="CASCADE"), nullable=False)
    document_index: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    ran_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    counter_version: Mapped[str] = mapped_column(String(32), nullable=False)
    result: Mapped[str] = mapped_column(String(8), nullable=False)
    source_totals: Mapped[dict] = mapped_column(_json(), nullable=False)
    captured_totals: Mapped[dict] = mapped_column(_json(), nullable=False)
    differences: Mapped[list] = mapped_column(_json(), nullable=False, default=list)
    difference_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class PhoneExtraInfo(Base):
    __tablename__ = "phone_extra_infos"
    __table_args__ = (_doc_fk(),)
    extraction_id: Mapped[uuid.UUID] = mapped_column(_uuid(), primary_key=True)
    document_index: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    ordinal: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    info_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    is_partial: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    body: Mapped[list] = mapped_column(_json(), nullable=False)


class PhoneExtraInfoNode(Base):
    __tablename__ = "phone_extra_info_nodes"
    __table_args__ = (_doc_fk(),)
    extraction_id: Mapped[uuid.UUID] = mapped_column(_uuid(), primary_key=True)
    document_index: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    extra_ordinal: Mapped[int] = mapped_column(Integer, primary_key=True)
    body_path: Mapped[str] = mapped_column(Text, primary_key=True)
    node_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    node_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    node_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    table_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    node_offset: Mapped[str | None] = mapped_column(Text, nullable=True)
    node_size: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_document_index: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    file_ordinal: Mapped[int | None] = mapped_column(Integer, nullable=True)
    resolution: Mapped[str] = mapped_column(String(24), nullable=False)


PHONE_CAPTURE_MODELS = (PhoneExtractionContainer, PhoneExtraction, PhoneExtractionContainerLink,
                        PhoneExtractionDocument, PhoneRecord, PhoneFile, PhoneContainerEntry, PhoneFileReference,
                        PhoneTimestamp, PhoneReconciliation, PhoneExtraInfo, PhoneExtraInfoNode)
