"""Phone interpretation tables (docs/cellebrite/02-interpretation-identity-projections.md).

Registry (02 section 3): global, structure only. Type names, field names, kinds, value types, named-set values,
nesting and attribute names; never a String, time, number, identifier or GUID from a report. Migrations own the
schema (``20261102_phone_registry`` and later); these models mirror it for the backend.
"""
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Integer, JSON, String, Text, \
    UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from postgres.base import Base

FIELD_KINDS = ("field", "multiField", "nodeField", "dataField")
NESTING_KINDS = ("modelField", "multiModelField", "RelatedModels")
ORIGINS = ("seed", "observed")
FLAG_KINDS = ("new_type", "new_field", "new_value_type", "new_set_value", "new_nesting", "new_attribute",
              "set_overflow", "multi_value_field")
FLAG_STATES = ("open", "acknowledged", "mapping_needed", "mapped", "dismissed")
FLAG_SEVERITIES = ("info", "blocks_mapping")
REGISTRY_TABLES = ("types", "fields", "nesting", "set_values", "attributes")
PLACEHOLDER_TYPES = ("(empty)", "(none)")
SET_VALUE_CAP = 500


def _json():
    return JSONB().with_variant(JSON(), "sqlite")


def _uuid():
    return UUID(as_uuid=True)


def _in(col, values):
    return "%s IN (%s)" % (col, ", ".join("'%s'" % v for v in values))


class _FirstSeen:
    origin: Mapped[str] = mapped_column(String(16), nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    first_seen_report_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    first_seen_producer_version: Mapped[str | None] = mapped_column(String(64), nullable=True)


class PhoneSchemaType(_FirstSeen, Base):
    __tablename__ = "phone_schema_types"
    type_name: Mapped[str] = mapped_column(String(128), primary_key=True)
    first_seen_extraction_id: Mapped[uuid.UUID | None] = mapped_column(
        _uuid(), ForeignKey("phone_extractions.id", ondelete="SET NULL"), nullable=True)
    seed_report_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    seed_record_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    observed_extraction_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    observed_record_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    seen_top_level: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    seen_nested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    __table_args__ = (CheckConstraint(_in("origin", ORIGINS), name="ck_phone_schema_types_origin"),)


class PhoneSchemaField(_FirstSeen, Base):
    __tablename__ = "phone_schema_fields"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    type_name: Mapped[str] = mapped_column(String(128), ForeignKey("phone_schema_types.type_name"), nullable=False)
    field_name: Mapped[str] = mapped_column(String(256), nullable=False)
    field_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    value_type: Mapped[str] = mapped_column(String(128), nullable=False)
    is_named_set: Mapped[bool] = mapped_column(Boolean, nullable=False)
    first_seen_extraction_id: Mapped[uuid.UUID | None] = mapped_column(
        _uuid(), ForeignKey("phone_extractions.id", ondelete="SET NULL"), nullable=True)
    seed_value_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    seed_report_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    observed_value_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    observed_empty_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    observed_extraction_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_values_in_one_field: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    __table_args__ = (
        UniqueConstraint("type_name", "field_name", "field_kind", "value_type", name="uq_phone_schema_fields"),
        CheckConstraint(_in("field_kind", FIELD_KINDS), name="ck_phone_schema_fields_kind"),
        CheckConstraint(_in("origin", ORIGINS), name="ck_phone_schema_fields_origin"),
    )


class PhoneSchemaNesting(_FirstSeen, Base):
    __tablename__ = "phone_schema_nesting"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    parent_type: Mapped[str] = mapped_column(String(128), nullable=False)
    field_name: Mapped[str] = mapped_column(String(256), nullable=False)
    field_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    child_type: Mapped[str] = mapped_column(String(128), nullable=False)
    first_seen_extraction_id: Mapped[uuid.UUID | None] = mapped_column(
        _uuid(), ForeignKey("phone_extractions.id", ondelete="SET NULL"), nullable=True)
    observed_child_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    __table_args__ = (
        UniqueConstraint("parent_type", "field_name", "field_kind", "child_type", name="uq_phone_schema_nesting"),
        CheckConstraint(_in("field_kind", NESTING_KINDS), name="ck_phone_schema_nesting_kind"),
        CheckConstraint(_in("origin", ORIGINS), name="ck_phone_schema_nesting_origin"),
    )


class PhoneSchemaSetValue(_FirstSeen, Base):
    __tablename__ = "phone_schema_set_values"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    set_name: Mapped[str] = mapped_column(String(128), nullable=False)
    value: Mapped[str] = mapped_column(String(512), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    first_seen_extraction_id: Mapped[uuid.UUID | None] = mapped_column(
        _uuid(), ForeignKey("phone_extractions.id", ondelete="SET NULL"), nullable=True)
    observed_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    __table_args__ = (
        UniqueConstraint("set_name", "value", name="uq_phone_schema_set_values"),
        CheckConstraint(_in("origin", ORIGINS), name="ck_phone_schema_set_values_origin"),
    )


class PhoneSchemaAttribute(_FirstSeen, Base):
    __tablename__ = "phone_schema_attributes"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    element: Mapped[str] = mapped_column(String(64), nullable=False)
    attribute: Mapped[str] = mapped_column(String(128), nullable=False)
    first_seen_extraction_id: Mapped[uuid.UUID | None] = mapped_column(
        _uuid(), ForeignKey("phone_extractions.id", ondelete="SET NULL"), nullable=True)
    __table_args__ = (
        UniqueConstraint("element", "attribute", name="uq_phone_schema_attributes"),
        CheckConstraint(_in("origin", ORIGINS), name="ck_phone_schema_attributes_origin"),
    )


class PhoneSchemaObservation(Base):
    __tablename__ = "phone_schema_observations"
    extraction_id: Mapped[uuid.UUID] = mapped_column(
        _uuid(), ForeignKey("phone_extractions.id", ondelete="CASCADE"), primary_key=True)
    registry_table: Mapped[str] = mapped_column(String(32), primary_key=True)
    registry_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    record_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    value_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    empty_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)


class PhoneSchemaFlag(Base):
    __tablename__ = "phone_schema_flags"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    flag_kind: Mapped[str] = mapped_column(String(24), nullable=False)
    registry_table: Mapped[str] = mapped_column(String(32), nullable=False)
    registry_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    raised_by_extraction_id: Mapped[uuid.UUID | None] = mapped_column(
        _uuid(), ForeignKey("phone_extractions.id", ondelete="SET NULL"), nullable=True)
    severity: Mapped[str] = mapped_column(String(16), nullable=False, default="info")
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="open")
    detail: Mapped[dict] = mapped_column(_json(), nullable=False, default=dict)
    raised_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    __table_args__ = (
        UniqueConstraint("flag_kind", "registry_table", "registry_id", name="uq_phone_schema_flags_subject"),
        CheckConstraint(_in("flag_kind", FLAG_KINDS), name="ck_phone_schema_flags_kind"),
        CheckConstraint(_in("state", FLAG_STATES), name="ck_phone_schema_flags_state"),
        CheckConstraint(_in("severity", FLAG_SEVERITIES), name="ck_phone_schema_flags_severity"),
    )


class PhoneSchemaFlagEvent(Base):
    __tablename__ = "phone_schema_flag_events"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    flag_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("phone_schema_flags.id", ondelete="CASCADE"),
                                         nullable=False)
    from_state: Mapped[str | None] = mapped_column(String(16), nullable=True)
    to_state: Mapped[str] = mapped_column(String(16), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    actor_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    actor_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(_uuid(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
