"""Generic interpretation by value role (02 section 5).

Every record of every type, known or not, is read by the role its values play: TimeStamp values become time
values (one timeline entry each), nested Coordinates become location points, nested Parties become
participations, String values become searchable texts, nested StreetAddresses become written address text, and
every record gets a summary. No list of record types drives this; the only names used are the value types and the
participant containers of 5.3 and the location parents of 5.4, which the spec fixes.

One pass per extraction, streamed in ordinal order (a parent always precedes its descendants, measured on the
captures), with the context of the current top-level record's subtree held in memory. Rows are written with
COPY under generation n+1, then generation n is deleted, in the caller's transaction (5.7).
"""
from __future__ import annotations

import io
import json
import time
import uuid
from collections import defaultdict

from sqlalchemy import text

from services.phone import body as B
from services.phone import fold as F
from services.phone import ids
from services.phone import values as V

GENERIC_VERSION = "generic-1"
BATCH = 5000
FLUSH_ROWS = 20000

SENSITIVE_DEFAULT = frozenset({
    ("Password", "Data"), ("Password", "GenericAttribute"), ("WirelessNetwork", "Password"),
    ("UserAccount", "Password"), ("CreditCard", "CreditCardNumber"), ("Cookie", "Value"), ("Autofill", "Value"),
    ("DictionaryWord", "Word"), ("KeyValueModel", "Value"),
})
ADDRESS_PARTS = ("Street1", "Street2", "HouseNumber", "City", "State", "PostalCode", "Country", "Neighborhood")
SPECIAL_CONTAINERS = {
    ("Chat", "Participants"): "participant", ("ChatActivity", "Participant"): "activity_subject",
    ("CalendarEntry", "Attendees"): "attendee", ("SocialMediaActivity", "Author"): "author",
    ("FileUpload", "Owner"): "owner_of_item", ("ForwardedMessageData", "OriginalSender"): "original_sender",
}
RECIPIENT_CONTAINERS = {"To": "recipient", "Cc": "cc", "Bcc": "bcc"}

COMMON = ("case_id", "extraction_id", "document_index", "ordinal", "record_uid", "root_record_uid", "locator",
          "model_type", "interpretation_level", "mapping_version_id", "deleted_state", "decoding_confidence", "flags",
          "generation")
COLUMNS = {
    "phone_time_values": COMMON + (
        "time_uid", "body_path", "field_name", "field_path", "value_index", "instant", "local_wall_time",
        "original_text", "formatted_text", "original_offset_minutes", "offset_state", "producer_format",
        "format_mismatch", "offset_present", "effective_instant", "instant_basis", "field_meaning", "semantics",
        "is_event_time"),
    "phone_location_points": COMMON + (
        "point_uid", "coordinate_record_uid", "lat", "lon", "lat_text", "lon_text", "elevation_m", "accuracy_m",
        "accuracy_basis", "precision_text", "source_kind", "affiliation", "instant", "end_instant", "time_field"),
    "phone_unplaced_records": COMMON + ("reason",),
    "phone_participations": COMMON + (
        "participation_uid", "party_record_uid", "container_field", "role", "role_basis", "role_in_record",
        "is_phone_owner", "identifier_raw", "name_in_record", "identity_key", "date_read", "date_delivered",
        "date_played"),
    "phone_texts": COMMON + (
        "text_uid", "body_path", "field_name", "field_path", "value_index", "value", "value_folded",
        "effective_value", "is_sensitive"),
    "phone_address_texts": COMMON + ("address_uid", "field_path", "address_text"),
    "phone_record_summaries": COMMON + (
        "parent_record_uid", "is_top_level", "title", "first_instant", "has_time", "has_point",
        "participant_count", "direction", "duration_seconds", "user_mapping", "source_index", "file_id"),
}
DERIVED_TABLES = tuple(COLUMNS)


class Held(RuntimeError):
    """A document's reconciliation differs and no person has accepted it (02 decision 37)."""


# ---- role of a participant (5.3) -----------------------------------------------------------------------------

def participant_role(parent_type, container, role_value, is_owner, direction):
    """Returns (role, basis, flags)."""
    flags = []
    if container == "From":
        if role_value == "To":
            flags.append("role_conflict")
        return "sender", "container", flags
    if container in RECIPIENT_CONTAINERS:
        if role_value == "From":
            flags.append("role_conflict")
        return RECIPIENT_CONTAINERS[container], "container", flags
    if parent_type == "Call" and container == "Parties":
        if role_value == "From":
            return "caller", "role", flags
        if role_value == "To":
            return "callee", "role", flags
        if (is_owner is True and direction == "Outgoing") or (is_owner is False and direction == "Incoming"):
            return "caller", "direction_inferred", flags
        if (is_owner is True and direction == "Incoming") or (is_owner is False and direction == "Outgoing"):
            return "callee", "direction_inferred", flags
        return "unknown", "direction_inferred", flags
    special = SPECIAL_CONTAINERS.get((parent_type, container))
    if special:
        return special, "container", flags
    return "party:%s" % container, "container", flags


def source_kind(parent_type, parent_origin):
    if parent_type == "Location" and parent_origin in (None, "Device"):
        return "device_location"
    if parent_type == "WirelessNetwork":
        return "wifi"
    return "other:%s" % (parent_type or "(none)")


# ---- COPY writer -------------------------------------------------------------------------------------------------

def _copy_text(v):
    if v is None:
        return "\\N"
    if isinstance(v, bool):
        return "t" if v else "f"
    if isinstance(v, (list, tuple)):
        return "{" + ",".join('"%s"' % str(x).replace("\\", "\\\\").replace('"', '\\"') for x in v) + "}"
    s = v.isoformat() if hasattr(v, "isoformat") else str(v)
    return s.replace("\\", "\\\\").replace("\t", "\\t").replace("\n", "\\n").replace("\r", "\\r")


class Writer:
    def __init__(self, conn):
        self.raw = conn.connection.driver_connection
        self.buf = defaultdict(list)
        self.counts = defaultdict(int)
        self.pending = 0

    def add(self, table, row):
        self.buf[table].append(row)
        self.counts[table] += 1
        self.pending += 1
        if self.pending >= FLUSH_ROWS:
            self.flush()

    def flush(self):
        for table, rows in self.buf.items():
            if not rows:
                continue
            cols = COLUMNS[table]
            data = io.StringIO()
            for r in rows:
                data.write("\t".join(_copy_text(r.get(c)) for c in cols))
                data.write("\n")
            with self.raw.cursor() as cur:
                with cur.copy("COPY %s (%s) FROM STDIN" % (table, ", ".join(cols))) as cp:
                    cp.write(data.getvalue())
            rows.clear()
        self.pending = 0


# ---- the pass ------------------------------------------------------------------------------------------------------

class _Ctx:
    """What a descendant needs from an ancestor."""
    __slots__ = ("type", "uid", "ordinal", "doc", "prefix", "container", "first_time", "accuracy", "precision",
                 "origin", "affiliation", "direction", "summary", "has_point", "point_problem", "positionable", "deleted_state",
                 "decoding_confidence", "locator", "root_uid")


def _first_text(fmap, name):
    for f in fmap.get(name, ()):
        for v in f.real_values:
            if v.text is not None:
                return v.text
    return None


class Interpreter:
    def __init__(self, conn, extraction_id, case_id, generation, sensitive, positionable_types):
        self.conn = conn
        self.ext = extraction_id
        self.case = case_id
        self.gen = generation
        self.sensitive = sensitive
        self.positionable = positionable_types
        self.w = Writer(conn)
        self.ctx = {}
        self.subtree = []
        self.stats = defaultdict(int)

    def _common(self, doc, ordinal, uid, root_uid, model_type, deleted_state, dc, flags=(), suffix=""):
        return {"case_id": self.case, "extraction_id": self.ext, "document_index": doc, "ordinal": ordinal,
                "record_uid": uid, "root_record_uid": root_uid,
                "locator": "%s/%d/r%d%s" % (self.ext, doc, ordinal, suffix), "model_type": model_type,
                "interpretation_level": "generic", "mapping_version_id": None, "deleted_state": deleted_state,
                "decoding_confidence": dc, "flags": list(flags), "generation": self.gen}

    def finish_subtree(self):
        for c in self.subtree:
            s = c.summary
            if c.positionable and not c.has_point and not c.point_problem:
                self.w.add("phone_unplaced_records", dict(self._common(c.doc, c.ordinal, c.uid, c.root_uid, c.type,
                                                                       c.deleted_state, c.decoding_confidence),
                                                          reason="no_coordinate"))
                self.stats["unplaced:no_coordinate:%s" % c.type] += 1
            s["has_point"] = c.has_point
            self.w.add("phone_record_summaries", s)
        self.subtree = []
        self.ctx = {}

    def record(self, doc, ordinal, parent, top, model_type, body, stamps):
        uid = ids.record_uid(self.ext, doc, ordinal)
        root_uid = ids.record_uid(self.ext, doc, top)
        attrs = B.model_attrs(body)
        ds, dc = attrs.get("deleted_state"), attrs.get("decoding_confidence")
        pctx = self.ctx.get(parent) if parent is not None else None
        if parent is not None and pctx is None:
            self.stats["orphan_records"] += 1
        container = pctx.container.get(ordinal) if pctx else None  # (field, kind, index)
        prefix = (pctx.prefix + "%s[%d]." % (container[0], container[2])) if container else ""
        fields = list(B.fields(body))
        fmap = defaultdict(list)
        for f in fields:
            fmap[f.name].append(f)
        c = _Ctx()
        c.type, c.uid, c.ordinal, c.doc, c.prefix = model_type, uid, ordinal, doc, prefix
        c.deleted_state, c.decoding_confidence, c.root_uid = ds, dc, root_uid
        c.container, c.first_time, c.has_point, c.point_problem = {}, None, False, False
        c.positionable = model_type in self.positionable
        c.accuracy = _first_text(fmap, "GpsHorizontalAccuracy")
        c.precision = _first_text(fmap, "Precision")
        c.origin = _first_text(fmap, "Origin")
        c.affiliation = _first_text(fmap, "DeviceLocationAffiliation") or _first_text(fmap, "AccountLocationAffiliation")
        c.direction = None
        title_text, first_instant, has_time, duration, user_mapping = None, None, False, None, None
        for f in fields:
            if f.kind in B.MODEL_FIELD_KINDS:
                for i, o in enumerate(f.children):
                    c.container[o] = (f.name, f.kind, i)
                continue
            for v in f.real_values:
                if v.type == "TimeStamp":
                    st = stamps.get(v.body_path)
                    if st is None:
                        self.stats["timestamp_without_capture_row"] += 1
                        continue
                    pfmt = V.producer_format(v.attrs)
                    mismatch = V.format_mismatch(pfmt, st["offset_state"])
                    eff = st["instant"]
                    self.w.add("phone_time_values", dict(
                        self._common(doc, ordinal, uid, root_uid, model_type, ds, dc,
                                     ["format_mismatch"] if mismatch else [], "/" + v.body_path),
                        time_uid=uuid.uuid5(uid, v.body_path), body_path=v.body_path, field_name=f.name,
                        field_path=prefix + (f.name or ""), value_index=v.index, instant=st["instant"],
                        local_wall_time=st["local_wall_time"], original_text=st["original_text"],
                        formatted_text=st["formatted_text"], original_offset_minutes=st["original_offset_minutes"],
                        offset_state=st["offset_state"], producer_format=pfmt, format_mismatch=mismatch,
                        offset_present=V.offset_present(st["offset_state"]), effective_instant=eff,
                        instant_basis="report" if eff is not None else None, field_meaning=None, semantics=None,
                        is_event_time=False))
                    self.stats["time_values"] += 1
                    has_time = True
                    if c.first_time is None:
                        c.first_time = (eff, f.name)
                    if eff is not None and (first_instant is None or eff < first_instant):
                        first_instant = eff
                elif v.type == "String":
                    if v.text is None or v.text == "":
                        continue
                    sens = (model_type, f.name) in self.sensitive
                    self.w.add("phone_texts", dict(
                        self._common(doc, ordinal, uid, root_uid, model_type, ds, dc, (), "/" + v.body_path),
                        text_uid=uuid.uuid5(uid, "text/" + v.body_path), body_path=v.body_path, field_name=f.name,
                        field_path=prefix + (f.name or ""), value_index=v.index, value=v.text,
                        value_folded=F.fold(v.text), effective_value=v.text, is_sensitive=sens))
                    self.stats["texts"] += 1
                    if title_text is None and not sens:
                        title_text = v.text
                elif v.type == "ModelDirections" and c.direction is None:
                    c.direction = v.text
                elif v.type == "TimeSpan" and duration is None:
                    duration = V.parse_timespan(v.text)[0]
                elif v.type == "DecodingSourceOptions" and user_mapping is None:
                    user_mapping = v.text
        if model_type == "Coordinate":
            self._coordinate(doc, ordinal, uid, root_uid, ds, dc, fmap, pctx)
        elif model_type == "Party" and pctx is not None:
            self._party(doc, ordinal, uid, ds, dc, fmap, pctx, container, stamps)
        elif model_type == "StreetAddress":
            self._address(doc, ordinal, uid, root_uid, ds, dc, fmap, pctx, container)
        elif model_type == "CellTower":
            self.w.add("phone_unplaced_records", dict(self._common(doc, ordinal, uid, root_uid, model_type, ds, dc),
                                                      reason="cell_identity_only"))
            self.stats["unplaced:cell_identity_only:CellTower"] += 1
        title = model_type if not title_text else "%s %s" % (model_type, title_text[:120])
        c.summary = dict(self._common(doc, ordinal, uid, root_uid, model_type, ds, dc),
                         parent_record_uid=pctx.uid if pctx else (ids.record_uid(self.ext, doc, parent)
                                                                  if parent is not None else None),
                         is_top_level=parent is None, title=title, first_instant=first_instant, has_time=has_time,
                         has_point=False, participant_count=0, direction=(c.direction or "").lower() or None,
                         duration_seconds=duration, user_mapping=user_mapping, source_index=attrs.get("source_index"),
                         file_id=attrs.get("file_id"))
        self.ctx[ordinal] = c
        self.subtree.append(c)
        self.stats["records"] += 1

    def _coordinate(self, doc, ordinal, uid, root_uid, ds, dc, fmap, pctx):
        owner = pctx  # the positioned record, or the Coordinate itself when top-level
        p = V.parse_coordinate(_first_text(fmap, "Latitude"), _first_text(fmap, "Longitude"),
                               _first_text(fmap, "Elevation"), _first_text(fmap, "GpsHorizontalAccuracy"),
                               owner.accuracy if owner else None, owner.precision if owner else None)
        rec_doc, rec_ord, rec_uid, rec_type = (owner.doc, owner.ordinal, owner.uid, owner.type) if owner else \
            (doc, ordinal, uid, "Coordinate")
        rec_ds, rec_dc = (owner.deleted_state, owner.decoding_confidence) if owner else (ds, dc)
        if not p["is_point"]:
            self.w.add("phone_unplaced_records", dict(self._common(rec_doc, rec_ord, rec_uid, root_uid, rec_type,
                                                                   rec_ds, rec_dc, p["flags"]),
                                                      reason=p["flags"][0]))
            self.stats["unplaced:%s:%s" % (p["flags"][0], rec_type)] += 1
            if owner:
                owner.point_problem = True
            return
        instant, time_field = (owner.first_time if owner and owner.first_time else (None, None))
        self.w.add("phone_location_points", dict(
            self._common(rec_doc, rec_ord, rec_uid, root_uid, rec_type, rec_ds, rec_dc, p["flags"]),
            point_uid=uuid.uuid5(uid, "point"), coordinate_record_uid=uid, lat=p["lat"], lon=p["lon"],
            lat_text=_first_text(fmap, "Latitude"), lon_text=_first_text(fmap, "Longitude"),
            elevation_m=p["elevation_m"], accuracy_m=p["accuracy_m"], accuracy_basis=p["accuracy_basis"],
            precision_text=p["precision_text"], source_kind=source_kind(owner.type if owner else None,
                                                                        owner.origin if owner else None),
            affiliation=owner.affiliation if owner else None, instant=instant, end_instant=None,
            time_field=time_field))
        self.stats["points"] += 1
        self.stats["points:%s" % rec_type] += 1
        if owner:
            owner.has_point = True

    def _party(self, doc, ordinal, uid, ds, dc, fmap, pctx, container, stamps):
        role_value = _first_text(fmap, "Role")
        owner_text = _first_text(fmap, "IsPhoneOwner")
        is_owner = V.parse_boolean(owner_text)
        cname = container[0] if container else None
        role, basis, flags = participant_role(pctx.type, cname, role_value, is_owner, pctx.direction)

        def party_time(name):
            for f in fmap.get(name, ()):
                for v in f.real_values:
                    st = stamps.get(v.body_path)
                    if st is not None:
                        return st["instant"]
            return None

        self.w.add("phone_participations", dict(
            self._common(pctx.doc, pctx.ordinal, pctx.uid, pctx.root_uid, pctx.type, ds, dc, flags),
            participation_uid=uuid.uuid5(uid, "participation"), party_record_uid=uid, container_field=cname,
            role=role, role_basis=basis, role_in_record=role_value, is_phone_owner=is_owner,
            identifier_raw=_first_text(fmap, "Identifier"), name_in_record=_first_text(fmap, "Name"),
            identity_key=None, date_read=party_time("DateRead"), date_delivered=party_time("DateDelivered"),
            date_played=party_time("DatePlayed")))
        self.stats["participations"] += 1
        pctx.summary["participant_count"] += 1

    def _address(self, doc, ordinal, uid, root_uid, ds, dc, fmap, pctx, container):
        parts = [_first_text(fmap, p) for p in ADDRESS_PARTS]
        joined = ", ".join(p for p in parts if p)
        if not joined:
            return
        owner = pctx
        rec = (owner.doc, owner.ordinal, owner.uid, owner.type) if owner else (doc, ordinal, uid, "StreetAddress")
        path = (owner.prefix + "%s[%d]" % (container[0], container[2])) if owner and container else "StreetAddress"
        self.w.add("phone_address_texts", dict(self._common(rec[0], rec[1], rec[2], root_uid, rec[3], ds, dc),
                                               address_uid=uuid.uuid5(uid, "address"), field_path=path,
                                               address_text=joined))
        self.stats["addresses"] += 1


# ---- orchestration ----------------------------------------------------------------------------------------------

def _stamps_for(conn, ext, doc, lo, hi):
    out = defaultdict(dict)
    for r in conn.execute(text(
            "SELECT owner_ordinal, body_path, instant, local_wall_time, original_text, formatted_text, "
            "original_offset_minutes, offset_state FROM phone_timestamps WHERE extraction_id = :e AND "
            "document_index = :d AND owner_kind = 'record' AND owner_ordinal BETWEEN :lo AND :hi"),
            {"e": ext, "d": doc, "lo": lo, "hi": hi}):
        m = r._mapping
        out[m["owner_ordinal"]][m["body_path"]] = dict(m)
    return out


def positionable_types(conn):
    """Types whose records are places (5.4): a Location without a Position is counted ``not_positionable``.
    CellTower is counted separately (``cell_identity_only``); other parents that sometimes carry a Coordinate
    (a message sharing a location, a search) are not places when they carry none."""
    return frozenset({"Location"})


def held_documents(conn, ext):
    """Documents whose latest reconciliation differs (02 decision 37). Acceptance decisions arrive with 8.8."""
    rows = conn.execute(text(
        "SELECT DISTINCT ON (document_index) document_index, result FROM phone_reconciliations WHERE "
        "extraction_id = :e ORDER BY document_index, ran_at DESC"), {"e": ext}).fetchall()
    return [d for d, r in rows if r == "differs"]


def interpret(conn, extraction_id, generation, sensitive=SENSITIVE_DEFAULT) -> dict:
    """Write generation ``generation`` of the generic rows for one extraction (no delete, no commit)."""
    meta = conn.execute(text("SELECT case_id FROM phone_extractions WHERE id = :e"), {"e": extraction_id}).one()
    it = Interpreter(conn, extraction_id, meta[0], generation, sensitive, positionable_types(conn))
    rows = conn.execute(text(
        "SELECT document_index, ordinal, parent_ordinal, top_ordinal, model_type, body FROM phone_records "
        "WHERE extraction_id = :e ORDER BY document_index, ordinal").execution_options(
        stream_results=True, yield_per=BATCH), {"e": extraction_id})
    batch = []
    state = {"doc": None}

    def run(batch):
        groups = defaultdict(list)
        for row in batch:
            groups[row[0]].append(row[1])
        stamps = {d: _stamps_for(conn, extraction_id, d, min(o), max(o)) for d, o in groups.items()}
        for d, o, p, t, mt, body in batch:
            if (p is None or d != state["doc"]) and it.subtree:
                it.finish_subtree()
            state["doc"] = d
            it.record(d, o, p, t, mt, body, stamps[d].get(o, {}))

    # Timestamps are read per batch on a second statement while the record cursor stays open.
    for row in rows:
        batch.append(row)
        if len(batch) >= BATCH:
            run(batch)
            batch = []
    if batch:
        run(batch)
    it.finish_subtree()
    it.w.flush()
    out = dict(it.stats)
    out.update({"rows:%s" % k: v for k, v in it.w.counts.items()})
    return out


def delete_generations_before(conn, extraction_id, generation) -> dict:
    deleted = {}
    for t in DERIVED_TABLES:
        r = conn.execute(text("DELETE FROM %s WHERE extraction_id = :e AND generation < :g" % t),
                         {"e": extraction_id, "g": generation})
        deleted[t] = r.rowcount
    return deleted
