"""Mapping files: load, validate, record versions, compute the mapping set (02 sections 6.2 to 6.6).

One JSON file per mapping at ``data/<kind>/<name>.json``. ``draft`` files are never loaded. ``applied_unconfirmed``
files are applied at once and carry no reviewer (a build job writes these; it never writes ``reviewed``). A
``reviewed`` file must name the person who reviewed it; a model's name is refused. Two files with one (kind, name)
are refused, and so is a version lower than the highest already recorded.
"""
from __future__ import annotations

import datetime as dt
import glob
import hashlib
import json
import os
import re
import uuid
from dataclasses import dataclass
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy import text

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
MAPPING_NS = uuid.UUID("5b0c7f0e-1d1a-4f0e-9f61-0c2f5c3e7a11")
KINDS = ("type", "activity_strength", "timestamp_meaning", "attribution", "sensitive_fields", "dedup",
         "natural_key", "platform_family")
ROW_KINDS = ("activity_strength", "timestamp_meaning", "attribution", "natural_key", "platform_family")
NUMERIC_TYPES = ("Int32", "Int64", "UInt32", "UInt64", "Double", "Decimal", "Single")
MODEL_NAMES = re.compile(r"\b(claude|gpt|openai|deepseek|anthropic|llm|model|ai|assistant|bot)\b", re.I)


class LoadError(ValueError):
    pass


class Review(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reviewed_by: Optional[str] = None
    reviewed_on: Optional[dt.date] = None
    basis: str = Field(min_length=1)
    registry_requirements: list[tuple[str, str, str, str]] = []


class Envelope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["type", "activity_strength", "timestamp_meaning", "attribution", "sensitive_fields", "dedup",
                  "natural_key", "platform_family"]
    name: str = Field(min_length=1, max_length=128)
    version: int = Field(ge=1)
    status: Literal["draft", "applied_unconfirmed", "reviewed"]
    origin: Literal["human", "ai_draft"]
    review: Review
    body: dict[str, Any]


class TimeRef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field: Optional[str] = None
    duration_field: Optional[str] = None


class Participants(BaseModel):
    model_config = ConfigDict(extra="forbid")
    containers: list[str] = []
    role_map: dict[str, str] = {}
    owner_flag: Optional[str] = None
    direction_field: Optional[str] = None


class Thread(BaseModel):
    model_config = ConfigDict(extra="forbid")
    strategy: Literal["parent_chat", "counterpart_set", "field", "none", "self"]
    group_field: Optional[str] = None
    fallback: Optional[Literal["counterpart_set", "none"]] = None
    fixed_key: Optional[str] = None


class TypeBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    applies_to: str
    comm_kind: Optional[Literal["message", "call", "email", "voicemail", "chat_activity", "thread"]] = None
    event_time: TimeRef = TimeRef()
    end_time: TimeRef = TimeRef()
    other_times: list[dict[str, Any]] = []
    participants: Participants = Participants()
    thread: Thread = Thread(strategy="none")
    place: Optional[dict[str, Any]] = None
    text_fields: list[str] = []
    status_fields: dict[str, str] = {}
    app_field: Optional[str] = None
    account_field: Optional[str] = None
    title: Optional[str] = None
    activity_strength: Optional[dict[str, str]] = None
    extra: dict[str, Any] = {}

    @field_validator("event_time")
    @classmethod
    def _no_duration_on_event(cls, v):
        if v.duration_field:
            raise ValueError("event_time takes a field, not a duration")
        return v


OPS = ("eq", "in", "lt", "le", "gt", "ge", "present", "absent")


class Predicate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field: Optional[str] = None
    name: Optional[str] = None
    op: Literal["eq", "in", "lt", "le", "gt", "ge", "present", "absent"]
    value: Any = None


class Row(BaseModel):
    model_config = ConfigDict(extra="forbid")
    row_id: str = Field(min_length=1, max_length=128)
    type: str
    field: Optional[str] = None
    predicates: list[Predicate] = []
    context: list[Predicate] = []
    outputs: dict[str, Any]
    basis: Literal["field_name", "corpus_measured", "vendor_doc", "not_established"]
    reasoning: str = Field(min_length=1)
    would_change: str = Field(min_length=1)


class RowsBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rows: list[Row]


class SensitiveBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fields: list[tuple[str, str]]


@dataclass(frozen=True)
class Mapping:
    kind: str
    name: str
    version: int
    status: str
    origin: str
    reviewed_by: Optional[str]
    reviewed_on: Optional[dt.date]
    content: dict
    sha256: str
    id: uuid.UUID
    path: str

    @property
    def body(self):
        return self.content["body"]

    @property
    def typed(self):
        """The validated ``type`` body (``TypeBody``)."""
        return TypeBody.model_validate(self.content["body"])

    @property
    def requirements(self):
        return [tuple(r) for r in self.content["review"].get("registry_requirements", [])]


def canonical(content: dict) -> str:
    return json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def version_id(kind, name, version, sha):
    return uuid.uuid5(MAPPING_NS, "%s/%s/%d/%s" % (kind, name, version, sha))


def _parse(path):
    with open(path, encoding="utf-8") as fh:
        raw = json.load(fh)
    try:
        env = Envelope.model_validate(raw)
    except ValidationError as exc:
        raise LoadError("%s: %s" % (path, exc)) from exc
    if env.status == "draft":
        return None
    if env.status == "reviewed":
        who = (env.review.reviewed_by or "").strip()
        if not who:
            raise LoadError("%s: a reviewed mapping must name the person who reviewed it" % path)
        if MODEL_NAMES.search(who):
            raise LoadError("%s: reviewed_by names a model (%s); only a person can review" % (path, who))
    elif env.review.reviewed_by:
        raise LoadError("%s: an applied_unconfirmed mapping carries no reviewer" % path)
    body_model = {"type": TypeBody, "sensitive_fields": SensitiveBody}.get(env.kind) or \
        (RowsBody if env.kind in ROW_KINDS else None)
    if body_model is not None:
        try:
            body_model.model_validate(env.body)
        except ValidationError as exc:
            raise LoadError("%s: body: %s" % (path, exc)) from exc
    content = json.loads(canonical(env.model_dump(mode="json")))
    sha = hashlib.sha256(canonical(content).encode("utf-8")).hexdigest()
    return Mapping(env.kind, env.name, env.version, env.status, env.origin, env.review.reviewed_by,
                   env.review.reviewed_on, content, sha, version_id(env.kind, env.name, env.version, sha), path)


def load_files(data_dir=DATA_DIR) -> list:
    out, seen = [], {}
    for path in sorted(glob.glob(os.path.join(data_dir, "*", "*.json"))):
        m = _parse(path)
        if m is None:
            continue
        if os.path.basename(os.path.dirname(path)) != m.kind:
            raise LoadError("%s: kind %s is in the wrong folder" % (path, m.kind))
        key = (m.kind, m.name)
        if key in seen:
            raise LoadError("two files for %s %s: %s and %s" % (m.kind, m.name, seen[key], path))
        seen[key] = path
        out.append(m)
    from services.phone.mappings import rows as row_rules
    for m in out:
        if m.kind in ROW_KINDS:
            row_rules.check_static(m)
    return out


def mapping_set_id(mappings) -> Optional[uuid.UUID]:
    ids = sorted(str(m.id) for m in mappings)
    return uuid.uuid5(MAPPING_NS, "|".join(ids)) if ids else None


# ---- registry checks (6.5 field rules) ----------------------------------------------------------------------

def registry_problems(conn, m, requirements=True) -> list:
    """Named fields the registry does not hold. Field rules (6.5, 6.5b) are load errors; an absent requirement
    is reported here too when ``requirements`` is true, but the applier treats it as a suspension (6.7)."""
    problems = []
    for t, f, k, vt in (m.requirements if requirements else ()):
        n = conn.execute(text("SELECT count(*) FROM phone_schema_fields WHERE type_name = :t AND field_name = :f AND "
                              "field_kind = :k AND value_type = :v"), {"t": t, "f": f, "k": k, "v": vt}).scalar()
        if not n:
            problems.append("requirement %s.%s (%s, %s) is not in the registry" % (t, f, k, vt))
    if m.kind in ROW_KINDS:
        for r in m.body["rows"]:
            for p in r.get("predicates") or []:
                rows = conn.execute(text("SELECT value_type, is_named_set FROM phone_schema_fields WHERE type_name = :t "
                                         "AND field_name = :f"), {"t": r["type"], "f": p["field"]}).fetchall()
                if not rows:
                    problems.append("%s: %s.%s is not in the registry" % (r["row_id"], r["type"], p["field"]))
                    continue
                if p["op"] in ("lt", "le", "gt", "ge") and not any(vt in NUMERIC_TYPES for vt, _ in rows):
                    problems.append("%s: %s on %s.%s, which is not numeric" % (r["row_id"], p["op"], r["type"], p["field"]))
                if p["op"] in ("eq", "in") and all(ns for _, ns in rows):
                    sets = [vt for vt, _ in rows]
                    for v in ([p["value"]] if p["op"] == "eq" else list(p["value"] or [])):
                        hit = conn.execute(text("SELECT 1 FROM phone_schema_set_values WHERE set_name = ANY(CAST(:s AS "
                                                "text[])) AND value = :v"), {"s": sets, "v": str(v)}).scalar()
                        if not hit:
                            problems.append("%s: %r is not a value of %s" % (r["row_id"], v, "/".join(sets)))
    if m.kind == "type":
        b = TypeBody.model_validate(m.body)
        for label, fname, want in (("event_time", b.event_time.field, "TimeStamp"),
                                   ("end_time", b.end_time.field, "TimeStamp"),
                                   ("duration", b.end_time.duration_field, "TimeSpan")):
            if fname:
                n = conn.execute(text("SELECT count(*) FROM phone_schema_fields WHERE type_name = :t AND "
                                      "field_name = :f AND value_type = :v"),
                                 {"t": b.applies_to, "f": fname, "v": want}).scalar()
                if not n:
                    problems.append("%s field %s.%s is not a %s field in the registry" % (label, b.applies_to, fname, want))
    return problems


# ---- versions --------------------------------------------------------------------------------------------------

def record_versions(conn, mappings) -> dict:
    """Append every loaded version; refuse a lower version than one recorded; write rows and the current table."""
    added = 0
    for m in mappings:
        high = conn.execute(text("SELECT max(version) FROM phone_mapping_versions WHERE kind = :k AND name = :n"),
                            {"k": m.kind, "n": m.name}).scalar()
        known = conn.execute(text("SELECT 1 FROM phone_mapping_versions WHERE id = :i"), {"i": m.id}).scalar()
        if high is not None and m.version < high and not known:
            raise LoadError("%s %s version %d is lower than the recorded version %d" % (m.kind, m.name, m.version, high))
        same_version_other = conn.execute(text(
            "SELECT 1 FROM phone_mapping_versions WHERE kind = :k AND name = :n AND version = :v AND id <> :i"),
            {"k": m.kind, "n": m.name, "v": m.version, "i": m.id}).scalar()
        if same_version_other:
            raise LoadError("%s %s version %d changed without a new version number" % (m.kind, m.name, m.version))
        if not known:
            conn.execute(text(
                "INSERT INTO phone_mapping_versions (id, kind, name, version, content_sha256, content, status, origin, "
                "reviewed_by, reviewed_on) VALUES (:i, :k, :n, :v, :s, CAST(:c AS jsonb), :st, :o, :rb, :ro)"),
                {"i": m.id, "k": m.kind, "n": m.name, "v": m.version, "s": m.sha256, "c": canonical(m.content),
                 "st": m.status, "o": m.origin, "rb": m.reviewed_by, "ro": m.reviewed_on})
            added += 1
            if m.kind in ROW_KINDS:
                from services.phone.mappings import rows as row_rules
                for r in m.body["rows"]:
                    conn.execute(text(
                        "INSERT INTO phone_mapping_rows (mapping_version_id, kind, name, row_id, type_name, field_name, "
                        "predicates, context, specificity, outputs, basis, reasoning, would_change) VALUES (:i, :k, :n, "
                        ":r, :t, :f, CAST(:p AS jsonb), CAST(:cx AS jsonb), :sp, CAST(:o AS jsonb), :b, :re, :w)"),
                        {"i": m.id, "k": m.kind, "n": m.name, "r": r["row_id"], "t": r["type"], "f": r.get("field"),
                         "p": json.dumps(r.get("predicates", [])), "cx": json.dumps(r.get("context", [])),
                         "sp": row_rules.specificity(r), "o": json.dumps(r["outputs"]), "b": r["basis"],
                         "re": r["reasoning"], "w": r["would_change"]})
        conn.execute(text(
            "INSERT INTO phone_mapping_current (kind, name, mapping_version_id) VALUES (:k, :n, :i) ON CONFLICT (kind, "
            "name) DO UPDATE SET mapping_version_id = EXCLUDED.mapping_version_id, set_at = CASE WHEN "
            "phone_mapping_current.mapping_version_id = EXCLUDED.mapping_version_id THEN phone_mapping_current.set_at "
            "ELSE now() END"), {"k": m.kind, "n": m.name, "i": m.id})
    names = {(m.kind, m.name) for m in mappings}
    for k, n in conn.execute(text("SELECT kind, name FROM phone_mapping_current")).fetchall():
        if (k, n) not in names:  # a removed file is a reviewed change too (6.8 step 4)
            conn.execute(text("DELETE FROM phone_mapping_current WHERE kind = :k AND name = :n"), {"k": k, "n": n})
    return {"versions_added": added, "loaded": len(mappings)}


# ---- the set the sweep uses ---------------------------------------------------------------------------------------

_cache = {"dir": DATA_DIR, "mappings": None, "recorded": set()}


def use_data_dir(path):
    """Tests point the loader at a folder of their own."""
    _cache.update({"dir": path, "mappings": None, "recorded": set()})


def loaded() -> list:
    if _cache["mappings"] is None:
        _cache["mappings"] = load_files(_cache["dir"])
        _cache["recorded"] = set()
    return _cache["mappings"]


def ensure_recorded(engine, mappings=None) -> dict:
    """Record the loaded versions in their own committed transaction (6.6), once per database per process.
    A transaction-scoped advisory lock keeps two starting processes from inserting the same version twice."""
    ms = loaded() if mappings is None else mappings
    key = engine.url.render_as_string(hide_password=True)
    if key in _cache["recorded"] and mappings is None:
        return {"versions_added": 0, "loaded": len(ms)}
    with engine.begin() as conn:
        conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('phone_mapping_versions'))"))
        out = record_versions(conn, ms)
        problems = [p for m in ms for p in registry_problems(conn, m, requirements=False)]
        if problems:
            raise LoadError("; ".join(problems))
    if mappings is None:
        _cache["recorded"].add(key)
    return out


def current_set(conn):
    """(mapping_set_id, named registry keys) for the sweep (6.6). Versions are recorded first."""
    ms = loaded()
    ensure_recorded(conn.engine)
    named = set()
    for m in ms:
        for t, f, k, _vt in m.requirements:
            named.add(("fields", (t, f, k)))
    return mapping_set_id(ms), frozenset(named)


def sensitive_fields(mappings=None) -> frozenset:
    ms = loaded() if mappings is None else mappings
    out = set()
    for m in ms:
        if m.kind == "sensitive_fields":
            out.update(tuple(x) for x in m.body["fields"])
    return frozenset(out)
