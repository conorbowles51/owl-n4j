"""Engine-side Core mirror of the phone capture tables (01 section 6.2).

The backend's alembic tree owns the schema (``backend/postgres/alembic/versions/20261101_phone_capture.py``);
this mirror only names what the engine writes, as ``EvidenceTableGeometry`` does in ``models/job.py``. The
capture writes through a synchronous psycopg connection with COPY (``app/phone/store.py``); the column lists
there are taken from these tables so the two cannot drift silently.
"""
from sqlalchemy import BigInteger, Boolean, Column, DateTime, Integer, MetaData, SmallInteger, String, Table, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB

metadata = MetaData()


def _doc_cols():
    return [Column("extraction_id", Uuid, primary_key=True), Column("document_index", SmallInteger, primary_key=True)]


phone_extraction_containers = Table(
    "phone_extraction_containers", metadata,
    Column("id", Uuid, primary_key=True), Column("case_id", Uuid), Column("evidence_file_id", Uuid),
    Column("upload_group_id", Uuid), Column("container_kind", String(20)), Column("stored_path", Text),
    Column("original_name", String(1024)), Column("size_bytes", BigInteger), Column("sha256", String(64)),
    Column("md5", String(32)), Column("upload_sha256", String(64)), Column("intake_outcome", String(40)),
    Column("classification", JSONB), Column("received_at", DateTime(timezone=True)),
    Column("received_by_user_id", Uuid))

phone_extractions = Table(
    "phone_extractions", metadata,
    Column("id", Uuid, primary_key=True), Column("case_id", Uuid), Column("report_set_sha256", String(64)),
    Column("first_container_id", Uuid), Column("form", String(20)), Column("capture_state", String(32)),
    Column("standing", String(16)), Column("supersedes_id", Uuid), Column("superseded_at", DateTime(timezone=True)),
    Column("superseded_by_user_id", Uuid), Column("report_version", String(32)),
    Column("producer_version", String(64)), Column("extraction_type", String(64)), Column("device_zone", String(64)),
    Column("device_zone_source", String(64)), Column("flags", JSONB), Column("record_count", Integer),
    Column("file_count", Integer), Column("engine_job_id", Uuid), Column("capture_code_version", String(32)),
    Column("created_at", DateTime(timezone=True)), Column("captured_at", DateTime(timezone=True)))

phone_extraction_container_links = Table(
    "phone_extraction_container_links", metadata,
    Column("extraction_id", Uuid, primary_key=True), Column("container_id", Uuid, primary_key=True),
    Column("root_path", Text, primary_key=True), Column("linked_at", DateTime(timezone=True)))

phone_extraction_documents = Table(
    "phone_extraction_documents", metadata, *_doc_cols(),
    Column("path", Text), Column("role", String(20)), Column("size_bytes", BigInteger), Column("sha256", String(64)),
    Column("md5", String(32)), Column("root_element", String(64)), Column("parse_state", String(16)),
    Column("truncation", JSONB), Column("skeleton", JSONB), Column("source_counts", JSONB),
    Column("capture_cursor", JSONB))

phone_records = Table(
    "phone_records", metadata, *_doc_cols(), Column("ordinal", Integer, primary_key=True),
    Column("parent_ordinal", Integer), Column("top_ordinal", Integer), Column("depth", SmallInteger),
    Column("model_type", String(128)), Column("source_model_id", String(128)), Column("deleted_state", String(32)),
    Column("is_partial", Boolean), Column("body", JSONB))

phone_files = Table(
    "phone_files", metadata, *_doc_cols(), Column("ordinal", Integer, primary_key=True),
    Column("parent_ordinal", Integer), Column("source_file_id", String(128)), Column("local_path", Text),
    Column("declared_size", BigInteger), Column("declared_md5", String(64)), Column("declared_sha256", String(128)),
    Column("tags", String(64)), Column("is_partial", Boolean), Column("body", JSONB), Column("disk_relpath", Text),
    Column("disk_size", BigInteger), Column("disk_md5", String(32)), Column("disk_sha256", String(64)),
    Column("outcome", String(24)), Column("verified_at", DateTime(timezone=True)))

phone_container_entries = Table(
    "phone_container_entries", metadata, Column("extraction_id", Uuid, primary_key=True),
    Column("relpath", Text, primary_key=True), Column("size_bytes", BigInteger), Column("sha256", String(64)),
    Column("md5", String(32)))

phone_file_references = Table(
    "phone_file_references", metadata, *_doc_cols(), Column("record_ordinal", Integer, primary_key=True),
    Column("body_path", Text, primary_key=True), Column("mechanism", String(24), primary_key=True),
    Column("reference_text", Text), Column("file_document_index", SmallInteger), Column("file_ordinal", Integer),
    Column("container_relpath", Text), Column("resolution", String(24)), Column("ambiguous", Boolean))

phone_timestamps = Table(
    "phone_timestamps", metadata, *_doc_cols(), Column("owner_kind", String(8), primary_key=True),
    Column("owner_ordinal", Integer, primary_key=True), Column("body_path", Text, primary_key=True),
    Column("model_type", String(128)), Column("field_name", String(256)), Column("value_type", String(64)),
    Column("original_text", Text), Column("formatted_text", Text), Column("instant", DateTime(timezone=True)),
    Column("local_wall_time", DateTime(timezone=False)), Column("original_offset_minutes", SmallInteger),
    Column("offset_state", String(12)), Column("parse_rule", String(48)))

phone_reconciliations = Table(
    "phone_reconciliations", metadata, Column("id", Uuid, primary_key=True), Column("extraction_id", Uuid),
    Column("document_index", SmallInteger), Column("ran_at", DateTime(timezone=True)),
    Column("counter_version", String(32)), Column("result", String(8)), Column("source_totals", JSONB),
    Column("captured_totals", JSONB), Column("differences", JSONB), Column("difference_count", Integer))

phone_extra_infos = Table(
    "phone_extra_infos", metadata, *_doc_cols(), Column("ordinal", Integer, primary_key=True),
    Column("source_id", String(128)), Column("info_type", String(128)), Column("is_partial", Boolean),
    Column("body", JSONB))

phone_extra_info_nodes = Table(
    "phone_extra_info_nodes", metadata, *_doc_cols(), Column("extra_ordinal", Integer, primary_key=True),
    Column("body_path", Text, primary_key=True), Column("node_id", String(128)), Column("node_name", Text),
    Column("node_path", Text), Column("table_name", String(256)), Column("node_offset", Text),
    Column("node_size", Text), Column("file_document_index", SmallInteger), Column("file_ordinal", Integer),
    Column("resolution", String(24)))


def columns(table: Table) -> list:
    return [c.name for c in table.columns]
