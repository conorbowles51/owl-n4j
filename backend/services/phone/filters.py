"""The one filter every phone list takes (docs/cellebrite/03 sections 3.1, 4.3).

``StreamFilter`` is validated here; empty or omitted arrays mean no restriction. ``canonical_json`` is the filter
with sorted keys and sorted sets, so two filters that ask the same question hash the same. ``snapshot`` is
``sha256(canonical filter + the case's phone data sequence)``: a window asked for under an older snapshot is
refused (409 ``stale_snapshot``), so a list never shifts under a reader when a correction, a decision or a new
phone lands mid-scroll (3.1 rule 3, D-3).

``group_scope`` (settled 2026-10-29): with ``direct`` (the default) ``between`` matches only one-to-one threads and
direct calls; ``include_groups`` adds group events where one of the two sent and the other is a member.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import text

Kind = Literal["message", "call", "email", "voicemail", "chat_activity"]
Direction = Literal["incoming", "outgoing", "unknown"]
KINDS = ("message", "call", "email", "voicemail", "chat_activity")


class Flags(BaseModel):
    """Tri-state each: None any, True only, False exclude."""
    model_config = ConfigDict(extra="forbid")
    carved: Optional[bool] = None
    synced: Optional[bool] = None
    has_attachment: Optional[bool] = None
    unreadable: Optional[bool] = None


class TextFilter(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(default="", max_length=2000)
    exact_characters: bool = False


class Names(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["phone", "case"] = "phone"


class Zone(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["phone", "case", "utc"] = "case"
    phone: Optional[str] = None

    @field_validator("phone")
    @classmethod
    def _phone_uuid(cls, v):
        import uuid
        if v is None:
            return v
        try:
            return str(uuid.UUID(v))
        except (ValueError, AttributeError, TypeError):
            raise ValueError("zone.phone is not a phone id")


class StreamFilter(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: str
    phones: List[str] = Field(default_factory=list)
    threads: List[str] = Field(default_factory=list)
    participants: List[str] = Field(default_factory=list)
    participant_mode: Literal["any", "all", "between", "sent_by", "sent_to"] = "any"
    expand_person_identities: bool = False
    group_scope: Literal["direct", "include_groups"] = "direct"
    # None is "the report records no app" (15.6% of events on 5 Nov), selectable like any app
    apps: List[Optional[str]] = Field(default_factory=list)
    kinds: List[Kind] = Field(default_factory=list)
    directions: List[Direction] = Field(default_factory=list)
    deleted_states: List[Optional[str]] = Field(default_factory=list)
    flags: Flags = Field(default_factory=Flags)
    from_instant: Optional[datetime] = None
    to_instant: Optional[datetime] = None
    include_no_time: bool = True
    # the Significant layer's toggle (07 XF-11): only events with an identity the case's manifest covers
    significant_only: bool = False
    text: TextFilter = Field(default_factory=TextFilter)
    collapse_copies: bool = True
    names: Names = Field(default_factory=Names)
    zone: Zone = Field(default_factory=Zone)
    sort: Literal["oldest_first", "newest_first"] = "oldest_first"
    # a frozen phone selection (07 6.1): only its records, as frozen (a saved link to a whole result opens this)
    selection: Optional[str] = None

    @field_validator("case_id")
    @classmethod
    def _case_uuid(cls, v):
        import uuid
        try:
            return str(uuid.UUID(v))
        except (ValueError, AttributeError, TypeError):
            raise ValueError("case_id is not a case id")

    @field_validator("phones")
    @classmethod
    def _phone_uuids(cls, v):
        import uuid
        try:
            return [str(uuid.UUID(p)) for p in v]
        except (ValueError, AttributeError, TypeError):
            raise ValueError("phones holds something that is not a phone id")

    @field_validator("selection")
    @classmethod
    def _selection_uuid(cls, v):
        import uuid
        if v is None:
            return v
        try:
            return str(uuid.UUID(v))
        except (ValueError, AttributeError, TypeError):
            raise ValueError("selection is not a selection id")

    @field_validator("from_instant", "to_instant")
    @classmethod
    def _aware(cls, v):
        if v is not None and v.tzinfo is None:
            raise ValueError("dates are sent as instants with an offset (03 section 4.3)")
        return v

    @model_validator(mode="after")
    def _modes(self):
        if self.participant_mode == "between" and len(self.participants) != 2:
            raise ValueError("between needs exactly two participants")
        if self.participant_mode in ("sent_by", "sent_to") and not 1 <= len(self.participants) <= 2:
            raise ValueError("sent by and sent to take one participant, or two for 'X to Y'")
        if self.from_instant and self.to_instant and self.from_instant > self.to_instant:
            raise ValueError("the start is after the end")
        return self


def canonical_json(f: StreamFilter) -> str:
    """Sorted keys; order-free lists sorted. ``participants`` keeps its order: sent_by X to Y is not Y to X."""
    d = f.model_dump(mode="json")
    for key in ("phones", "threads", "kinds", "directions"):
        d[key] = sorted(d[key])
    for key in ("apps", "deleted_states"):
        d[key] = sorted(d[key], key=lambda v: (v is None, v or ""))
    if d["participant_mode"] in ("any", "all", "between"):
        d["participants"] = sorted(d["participants"])
    return json.dumps(d, sort_keys=True, separators=(",", ":"))


def data_sequence(conn, case_id) -> str:
    """Changes whenever the case's phone data a list reads can change: an extraction's generation or standing, a
    decision on phone subjects, a value correction, the case time zone."""
    phones = conn.execute(text(
        "SELECT coalesce(string_agg(e.id::text || ':' || e.standing::text || ':' || coalesce(s.generation, -1)::text, "
        "',' ORDER BY e.id), '') FROM phone_extractions e LEFT JOIN phone_interpretation_state s ON "
        "s.extraction_id = e.id WHERE e.case_id = :c"), {"c": case_id}).scalar()
    decisions = conn.execute(text(
        "SELECT count(*)::text || ':' || coalesce(max(created_at)::text, '') FROM adjudications WHERE case_id = :c "
        "AND subject_type LIKE 'phone%'"), {"c": case_id}).scalar()
    # The case time zone sets the day bounds of every list shown in it; a change re-reads the index.
    zone = conn.execute(text("SELECT time_zone FROM case_display_settings WHERE case_id = :c"),
                        {"c": case_id}).scalar() or ""
    return "%s|%s|%s" % (phones, decisions, zone)


def snapshot(conn, f: StreamFilter, *, extra: str = "") -> str:
    if f.significant_only:  # the toggle's list changes with the manifest, which no phone decision touches
        from services.phone import significant
        extra = "%s|%s" % (extra, significant.manifest_mark(conn, f.case_id))
    return hashlib.sha256(("%s|%s|%s" % (canonical_json(f), data_sequence(conn, f.case_id), extra)).encode()
                          ).hexdigest()
