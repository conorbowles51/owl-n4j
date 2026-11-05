"""Place observations, offline cell reference data, WiFi anchors and reverse geocoding (04 section 6, unit U5).

Every place-bearing record becomes an area in time (``pol_place_observation``): position, an uncertainty radius used
in comparisons with the rule that gave it, the source's own figure, the time with its meaning and offset, the kind
(presence, searched, planned, declared, media, harvested) and the attribution flags.

- GPS accuracy is a 68 percent radius; comparisons use twice it (04 decision 5).
- WiFi positions come only from the case itself: a BSSID seen within 5 minutes of the same phone's GPS fixes (radius
  100 m or less) on 2 or more days is anchored (6.3). The SSID never anchors and nothing is looked up outside.
- Cell towers are placed only from an offline reference dataset the case uses (6.4); a tower the dataset does not
  hold, or any tower while the case uses no dataset, is listed as not placed with its key. Imports read a file an
  operator placed on the server; nothing is fetched at query time.
- Reverse geocoding for display runs only when the configured backend is in house (GeoNames offline, or Nominatim on
  the deployment's own network), checked at start-up (6.5).
"""
from __future__ import annotations

import csv
import gzip
import hashlib
import io
import ipaddress
import logging
import math
import os
import statistics
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from sqlalchemy import text

from services.pattern_of_life import activity

log = logging.getLogger(__name__)

GPS_FACTOR = 2.0
DEFAULT_WIFI_POSITION_M = 100.0
ANCHOR_WINDOW = timedelta(minutes=5)
ANCHOR_GPS_MAX_RADIUS_M = 100.0
ANCHOR_MIN_DAYS = 2
ANCHOR_MIN_RADIUS_M = 75.0
ANCHOR_PAD_M = 50.0
CELL_MIN_RANGE_M = 300
CELL_SPARSE_RANGE_M = 2000
CELL_MIN_SAMPLES = 3
REFERENCE_DIR = os.environ.get("LOUPE_REFERENCE_DATA_DIR", "/mnt/owl-data/reference-data")
# The words every map, export and agent sentence that shows a place carries (the investigative-workflows report:
# "Maps labelled investigative"): a place drawn here is an investigator's reading of the phone's records, never a
# cell-site expert's opinion of where the handset was.
PLACE_LABEL_WORDS = "Investigative location, not cell-site opinion"
ROUTINE_KINDS = ("presence",)  # media enters routine only once it is shown to be taken on this device (decision 25)


def haversine_m(lat1, lon1, lat2, lon2):
    r = 6371008.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def radius_of(accuracy_m, accuracy_basis, source_kind):
    """(radius_m, radius_reported, radius_basis) per 6.2."""
    acc = float(accuracy_m) if accuracy_m is not None else None
    if accuracy_basis == "gps_horizontal" and acc is not None and acc > 0:
        return acc * GPS_FACTOR, acc, "gps_accuracy_x2"
    if source_kind == "wifi_position":
        return DEFAULT_WIFI_POSITION_M, acc, "default_wifi_position"
    if accuracy_basis == "precision_field":
        # Reached only by a bare number: every "Horizontal: <n>" record also has GpsHorizontalAccuracy, the same number
        # (measurements/m5-precision.json). A bare number's unit is not established and 122 of 24,050 are negative, so
        # accuracy is not stated (04 section 15).
        return None, None, "precision_value"
    return None, acc, "unknown"


def classify_point(model_type, p_source_kind, accuracy_basis, facts, flags):
    """(kind, source_kind, presence_basis, extra flags) for one point (6.1, 6.2)."""
    f = (facts or {}).get("fields") or {}
    first = activity._first
    extra = []
    if model_type == "Location":
        typ, cat = first(f.get("Type")), first(f.get("Category"))
        if p_source_kind == "device_location":
            source = "gps" if accuracy_basis == "gps_horizontal" else "device_location"
        else:
            source = "app_location"
        if "synced_from_account" in (flags or []):
            source = "account_location"
        if typ == "Searched":
            return "searched", source, None, extra
        if typ == "Harvested":
            # where a network or tower the phone heard is, never where the phone was (04 decision 53). The source
            # keeps it out of the GPS fixes that anchor WiFi networks too
            return "harvested", "harvested", None, extra
        if cat == "Media Locations":
            extra.append("media_device_not_established")
            return "media", "media_exif", None, extra
        return "presence", source, "location_record", extra
    if p_source_kind == "wifi":
        return "presence", "wifi_position", "wifi_position_fix", extra
    if model_type == "SocialMediaActivity":
        return "declared", "checkin", None, extra
    if model_type == "CalendarEntry":
        return "planned", "calendar", None, extra
    if model_type == "Journey":
        return "presence", "journey", "journey_point", extra
    return "presence", "app_location", "record_with_coordinate", extra


# ---- photos: taken on this phone, or received (6.2) -------------------------------------------------------------

# A photo is taken on this phone when its EXIF camera make and model are the extraction device's own (exactly, after
# case, punctuation, a make prefix and a bracketed suffix are set aside: "Phone X1" is not "Phone X1 Pro"), or when
# its file is in the phone's camera folder (a whole path component ``dcim`` or ``camera``: Android ``DCIM/Camera``,
# iOS ``DCIM/100APPLE``) and its EXIF does not name a camera of another make. A saved received photo lands in the
# camera folder too (an iPhone's camera roll holds pictures saved from messages) and keeps the sender's EXIF and
# position: measured on a reference phone, all 20 camera-folder photos named another make's camera. Screenshot
# folders are not camera folders. Anything else (a received picture, a download, a file with no folder or EXIF) is
# ``received_media`` and is never presence (04 6.2, decision l.1572). *Reverse if* the camera roll is shown to hold
# only this phone's own photos, or a make is recorded under two names.
CAMERA_FOLDER_RE = r"(^|/)(dcim|camera)(/|$)"
MEDIA_BASIS_WORDS = {"camera_folder": "in this phone's camera folder",
                     "camera_matches_device": "the photo's EXIF camera is this phone",
                     "received_media": "not shown to be taken on this phone (received, downloaded or unknown)"}


def _norm(v):
    return "".join(ch for ch in str(v or "").lower() if ch.isalnum())


def _same_make(a, b):
    """Two camera makes are one when equal, or one is the other with a company word after it ("apple", "apple inc")."""
    a, b = _norm(a), _norm(b)
    return bool(a and b) and (a == b or a.startswith(b) or b.startswith(a))


def _model_key(model, make):
    import re
    m = _norm(re.sub(r"\([^)]*\)", " ", str(model or "")))
    for k in {_norm(make), _norm(str(make or "").split()[0] if str(make or "").split() else "")}:
        if k and m.startswith(k) and len(m) > len(k):
            m = m[len(k):]
    return m


def _same_model(a, b, make):
    a, b = _model_key(a, make), _model_key(b, make)
    return bool(a and b) and a == b


def media_origin(conn, extraction_id) -> dict:
    """{record uid: "camera_folder" | "camera_matches_device" | None} for the extraction's location records whose
    file reference resolves to a tagged file (the ``Media Locations`` points)."""
    from services.phone import ids
    from services.phone.records import _device
    dev = _device(conn, extraction_id)
    out = {}
    for doc, ordinal, in_cam, maker, model in conn.execute(text(
            "SELECT fr.document_index, fr.record_ordinal, "
            "  (lower(replace(coalesce(pf.body -> 1 ->> 'path', ''), '\\', '/')) ~ :cam OR "
            "   lower(replace(coalesce(pf.local_path, ''), '\\', '/')) ~ :cam) AS in_cam, "
            "  (SELECT it ->> 2 FROM jsonb_array_elements(CASE WHEN jsonb_typeof(pf.body -> 3) = 'array' THEN "
            "     pf.body -> 3 ELSE '[]'::jsonb END) m, jsonb_array_elements(CASE WHEN jsonb_typeof(m -> 3) = 'array' "
            "     THEN m -> 3 ELSE '[]'::jsonb END) it WHERE m ->> 0 = 'metadata' AND it ->> 0 = 'item' AND "
            "     it -> 1 ->> 'name' = 'EXIFCameraMaker' LIMIT 1) AS maker, "
            "  (SELECT it ->> 2 FROM jsonb_array_elements(CASE WHEN jsonb_typeof(pf.body -> 3) = 'array' THEN "
            "     pf.body -> 3 ELSE '[]'::jsonb END) m, jsonb_array_elements(CASE WHEN jsonb_typeof(m -> 3) = 'array' "
            "     THEN m -> 3 ELSE '[]'::jsonb END) it WHERE m ->> 0 = 'metadata' AND it ->> 0 = 'item' AND "
            "     it -> 1 ->> 'name' = 'EXIFCameraModel' LIMIT 1) AS model "
            "FROM phone_file_references fr JOIN phone_records r ON r.extraction_id = fr.extraction_id AND "
            "  r.document_index = fr.document_index AND r.ordinal = fr.record_ordinal AND r.model_type = 'Location' "
            "JOIN phone_files pf ON pf.extraction_id = fr.extraction_id AND pf.document_index = fr.file_document_index "
            "  AND pf.ordinal = fr.file_ordinal "
            "WHERE fr.extraction_id = :e AND fr.resolution = 'tagged_file' AND NOT fr.ambiguous"),
            {"e": extraction_id, "cam": CAMERA_FOLDER_RE}):
        uid = str(ids.record_uid(extraction_id, doc, ordinal))
        device_make = dev.get("manufacturer")
        if _same_make(maker, device_make) and _same_model(model, dev.get("model"), device_make):
            basis = "camera_matches_device"
        elif in_cam and not (maker and device_make and not _same_make(maker, device_make)):
            basis = "camera_folder"
        else:
            basis = None
        if out.get(uid) is None:
            out[uid] = basis
    return out


def media_presence(basis, extra):
    """(kind, presence basis, flags) of a media place: presence when taken on this phone, else received media."""
    flags = [f for f in extra if f != "media_device_not_established"]
    if basis:
        return "presence", basis, flags + ["media_taken_on_device"]
    return "media", None, flags + ["received_media"]


# ---- observations from points --------------------------------------------------------------------------------------

def build(conn, extraction_id) -> dict:
    """Rebuild the extraction's observations from its points and towers, then the case's WiFi anchors (no commit)."""
    st = activity.current_generation(conn, extraction_id)
    if st is None or not st.generation:
        return {"status": "not_interpreted"}
    gen, case_id, zone = st.generation, st.case_id, activity._zone(st.device_zone)
    conn.execute(text("DELETE FROM pol_place_observation WHERE extraction_id = :e"), {"e": extraction_id})
    conn.execute(text("DELETE FROM pol_unplaced_tower WHERE extraction_id = :e"), {"e": extraction_id})
    stats = defaultdict(int)
    rows = []
    taken = media_origin(conn, extraction_id)
    for r in conn.execute(text(
            "SELECT p.record_uid, p.coordinate_record_uid, p.model_type, p.lat, p.lon, p.accuracy_m, p.accuracy_basis, "
            "p.source_kind, p.flags, p.deleted_state, p.decoding_confidence, "
            "ev.instant_utc, ev.end_utc, ev.time_semantics, ev.offset_status, ev.attribution_flags, ev.match_facts, "
            "ev.source_app, tv.effective_instant, tv.local_wall_time, tv.offset_state, tv.semantics, tv.instant_basis "
            "FROM phone_location_points p "
            "LEFT JOIN LATERAL (SELECT * FROM pol_activity_event a WHERE a.extraction_id = p.extraction_id AND "
            "  a.record_uid = p.record_uid ORDER BY (a.time_field = p.time_field) DESC, a.instant_utc LIMIT 1) ev ON true "
            "LEFT JOIN phone_time_values tv ON tv.extraction_id = p.extraction_id AND tv.generation = p.generation AND "
            "  tv.record_uid = p.record_uid AND tv.field_name = p.time_field AND tv.value_index = 0 "
            "WHERE p.extraction_id = :e AND p.generation = :g").execution_options(stream_results=True, yield_per=5000),
            {"e": extraction_id, "g": gen}):
        if r.instant_utc is not None:
            start, end = r.instant_utc, r.end_utc or r.instant_utc
            sem, ostat, flags = r.time_semantics, r.offset_status, list(r.attribution_flags or [])
        elif r.effective_instant is not None or r.local_wall_time is not None:
            inst, _, ostat = activity._instant(r, zone)
            if inst is None:
                stats["no_time"] += 1
                continue
            start = end = inst
            sem, flags = r.semantics or "unknown", (["offset_absent"] if ostat != "explicit" else [])
        else:
            stats["no_time"] += 1
            continue
        kind, source, basis, extra = classify_point(r.model_type, r.source_kind, r.accuracy_basis, r.match_facts, flags)
        if kind == "media":
            kind, basis, extra = media_presence(taken.get(str(r.record_uid)), extra)
            stats["media:%s" % (basis or "received_media")] += 1
        radius, reported, rbasis = radius_of(r.accuracy_m, r.accuracy_basis, source)
        rows.append({"c": case_id, "e": extraction_id, "ru": r.record_uid, "cu": r.coordinate_record_uid,
                     "rt": (r.model_type or "")[:64], "k": kind, "sk": source, "lat": r.lat, "lon": r.lon,
                     "rad": radius, "rep": reported, "rb": rbasis, "s": start, "en": max(start, end), "os": ostat,
                     "sem": sem, "pb": basis, "fl": flags + extra + [f for f in (r.flags or []) if f == "zero_zero"],
                     "app": r.source_app})
        stats["observations:%s" % kind] += 1
    _insert(conn, rows)
    from services.pattern_of_life import text_places  # a person's placements survive every rebuild (6.5)
    stats.update({"text_places:" + k: v for k, v in text_places.project(conn, extraction_id).items()})
    stats.update(_towers(conn, extraction_id, case_id, gen))
    stats.update({"anchors:" + k: v for k, v in build_anchors(conn, case_id).items()})
    return dict(stats)


def _insert(conn, rows):
    if rows:
        conn.execute(text(
            "INSERT INTO pol_place_observation (case_id, extraction_id, record_uid, coordinate_record_uid, record_type, "
            "kind, source_kind, lat, lon, radius_m, radius_reported, radius_basis, start_utc, end_utc, offset_status, "
            "time_semantics, presence_basis, attribution_flags, reference_dataset_id, wifi_anchor_id, source_app) "
            "VALUES (:c, :e, :ru, :cu, :rt, :k, :sk, :lat, :lon, :rad, :rep, :rb, :s, :en, :os, :sem, :pb, :fl, "
            ":ds, :wa, :app)"), [dict({"ds": None, "wa": None, "cu": None}, **r) for r in rows])


# ---- cell towers ----------------------------------------------------------------------------------------------------

def _int(v):
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None


def tower_key(body):
    from services.phone import body as B
    radio = (B.first_text(body, "CellTowerType") or B.first_text(body, "Type") or "").strip().upper() or None
    return {"radio": radio, "mcc": _int(B.first_text(body, "MCC")), "mnc": _int(B.first_text(body, "MNC")),
            "lac": _int(B.first_text(body, "LAC")), "cid": _int(B.first_text(body, "CID"))}


def case_dataset(conn, case_id):
    return conn.execute(text("SELECT dataset_id FROM pol_case_cell_dataset WHERE case_id = :c"), {"c": case_id}).scalar()


def sim_mccs(conn, extraction_id) -> set:
    """The home network country codes the phone's SIM data states: the first three digits of every IMSI in the
    report header (``IMSI``) and in SIMData records named IMSI (04 6.2: "the extraction's home network MCC")."""
    import re
    from services.phone import identities
    from services.phone_analysis import fields as FV
    imsis = list(identities.header_items(conn, extraction_id).get("IMSI", []))
    for v in FV.field_values(conn, extraction_id, ("SIMData",), ("Name", "Value")).values():
        if "IMSI" in " ".join(v["values"].get("Name", ())).upper():
            imsis += v["values"].get("Value", ())
    return {int(d[:3]) for d in (re.sub(r"\D", "", x or "") for x in imsis) if 6 <= len(d) <= 15}


def resolve_tower_key(body, mccs):
    """``(key, flags, reason)`` of one CellTower record. A tower with no MCC takes the SIM's when exactly one is known
    (flag ``mcc_inferred``); with none or several it stays unresolved and ``reason`` says which (04 6.2)."""
    k = tower_key(body)
    if None in (k["mnc"], k["lac"], k["cid"]):
        return k, [], "key_incomplete"
    if k["mcc"] is not None:
        return k, [], None
    if len(mccs) == 1:
        return dict(k, mcc=next(iter(mccs))), ["mcc_inferred"], None
    return k, [], "mcc_unknown_several_sims" if mccs else "mcc_unknown_no_sim"


def tower_rows(conn, extraction_id):
    """Every CellTower record of the extraction with its resolved key and its first projected time:
    ``[(record_uid, key, flags, reason, event or None)]``, read in two queries (not one per record)."""
    from services.phone import ids
    mccs = None
    events = {}
    for r in conn.execute(text(
            "SELECT DISTINCT ON (record_uid) record_uid, instant_utc, end_utc, time_semantics, offset_status, "
            "attribution_flags FROM pol_activity_event WHERE extraction_id = :e AND record_type = 'CellTower' "
            "ORDER BY record_uid, instant_utc"), {"e": extraction_id}):
        events[str(r.record_uid)] = r
    out = []
    for doc, ordinal, body in conn.execute(text(
            "SELECT document_index, ordinal, body FROM phone_records WHERE extraction_id = :e AND model_type = "
            "'CellTower' ORDER BY document_index, ordinal"), {"e": extraction_id}):
        if mccs is None:
            mccs = sim_mccs(conn, extraction_id)
        uid = ids.record_uid(extraction_id, doc, ordinal)
        k, flags, reason = resolve_tower_key(body, mccs)
        out.append((uid, k, flags, reason, events.get(str(uid))))
    return out


def _towers(conn, extraction_id, case_id, gen) -> dict:
    stats = defaultdict(int)
    ds = case_dataset(conn, case_id)
    obs = []
    for uid, k, kflags, reason, ev in tower_rows(conn, extraction_id):
        ref = None
        if reason is None and ds is None:
            reason = "no_reference_dataset"
        elif reason is None:
            ref = conn.execute(text(
                "SELECT lat, lon, range_m, samples FROM pol_cell_reference WHERE dataset_id = :d AND mcc = :mcc AND "
                "mnc = :mnc AND lac = :lac AND cid = :cid AND (CAST(:radio AS varchar) IS NULL OR radio = :radio) "
                "ORDER BY samples DESC NULLS LAST LIMIT 1"), dict(k, d=ds)).one_or_none()
            if ref is None:
                reason = "tower_not_in_reference_data"
            elif ev is None:
                reason = "no_time"
        if "mcc_inferred" in kflags:
            stats["towers_mcc_inferred"] += 1
        if reason is not None:
            conn.execute(text(
                "INSERT INTO pol_unplaced_tower (case_id, extraction_id, record_uid, radio, mcc, mnc, lac, cid, "
                "instant_utc, reason, mcc_inferred) VALUES (:c, :e, :u, :radio, :mcc, :mnc, :lac, :cid, :i, :r, :mi)"),
                dict(k, c=case_id, e=extraction_id, u=uid, i=ev.instant_utc if ev else None, r=reason,
                     mi="mcc_inferred" in kflags))
            stats["towers_not_placed:%s" % reason] += 1
            continue
        sparse = (ref.samples or 0) < CELL_MIN_SAMPLES
        radius = max(ref.range_m or 0, CELL_SPARSE_RANGE_M if sparse else CELL_MIN_RANGE_M)
        flags = list(ev.attribution_flags or []) + (["reference_sparse"] if sparse else []) + kflags
        obs.append({"c": case_id, "e": extraction_id, "ru": uid, "rt": "CellTower", "k": "presence",
                    "sk": "cell_reference", "lat": ref.lat, "lon": ref.lon, "rad": float(radius),
                    "rep": float(ref.range_m) if ref.range_m is not None else None, "rb": "cell_reference",
                    "s": ev.instant_utc, "en": ev.end_utc or ev.instant_utc, "os": ev.offset_status,
                    "sem": ev.time_semantics, "pb": "cell_registration", "fl": flags, "ds": ds, "app": None})
        stats["towers_placed"] += 1
    _insert(conn, obs)
    return dict(stats)


def unplaced_towers(conn, extraction_ids) -> list:
    return [dict(r._mapping) for r in conn.execute(text(
        "SELECT extraction_id, record_uid, radio, mcc, mnc, lac, cid, instant_utc, reason, mcc_inferred FROM "
        "pol_unplaced_tower WHERE "
        "extraction_id = ANY(CAST(:e AS uuid[])) ORDER BY instant_utc NULLS LAST, id"),
        {"e": [str(x) for x in extraction_ids]})]


TOWER_WORDS = {"no_reference_dataset": "Not placed: this case uses no cell tower reference data.",
               "tower_not_in_reference_data": "Tower not in reference data.",
               "key_incomplete": "Not placed: the tower's network code or cell number is missing.",
               "no_time": "Not placed in time: the record gives no time.",
               "mcc_unknown_no_sim": "Not placed: the tower's country code is missing and the phone's SIM data "
                                     "does not state one.",
               "mcc_unknown_several_sims": "Not placed: the tower's country code is missing and the phone's SIM "
                                           "data states more than one."}
# shown beside a tower whose country code was taken from the phone's SIM (flag ``mcc_inferred``)
MCC_INFERRED_WORDS = "Country code taken from the phone's SIM card; the tower record does not state it."


# ---- cell reference import ------------------------------------------------------------------------------------------

OPENCELLID_COLUMNS = ("radio", "mcc", "net", "area", "cell", "unit", "lon", "lat", "range", "samples", "changeable",
                      "created", "updated", "averageSignal")


class ImportRefused(ValueError):
    pass


def _safe_path(path):
    real = os.path.realpath(path)
    root = os.path.realpath(REFERENCE_DIR)
    if not (real == root or real.startswith(root + os.sep)):
        raise ImportRefused("The file must be under %s on the server." % root)
    if not os.path.isfile(real):
        raise ImportRefused("No such file on the server.")
    return real


def import_cell_file(conn, path, *, name, licence, attribution, retrieved_on, by_name, by_email, source_note=None,
                     batch=50000) -> dict:
    """Stream an OpenCelliD-format CSV (optionally gzipped) from the server's disk into a new dataset version."""
    real = _safe_path(path)
    h = hashlib.sha256()
    with open(real, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    sha = h.hexdigest()
    ds = uuid.uuid4()
    conn.execute(text(
        "INSERT INTO pol_reference_dataset (id, kind, name, licence, attribution, source_note, file_sha256, "
        "retrieved_on, imported_by_name, imported_by_email) VALUES (:i, 'cell', :n, :l, :a, :s, :h, :r, :bn, :be)"),
        {"i": ds, "n": name, "l": licence, "a": attribution, "s": source_note, "h": sha, "r": retrieved_on,
         "bn": by_name, "be": by_email})
    conn.execute(text("CREATE TEMP TABLE IF NOT EXISTS pol_cell_import (radio varchar(8), mcc int, mnc int, lac bigint, "
                      "cid bigint, lat double precision, lon double precision, range_m int, samples int, "
                      "updated_at timestamptz) ON COMMIT DROP"))
    conn.execute(text("TRUNCATE pol_cell_import"))
    raw = conn.connection.driver_connection
    opener = gzip.open if real.endswith(".gz") else open
    good = bad = 0
    with opener(real, "rt", newline="", encoding="utf-8", errors="replace") as fh:
        reader = csv.reader(fh)
        buf = io.StringIO()
        n_buf = 0
        for i, row in enumerate(reader):
            if i == 0 and row and row[0].strip().lower() == "radio":
                continue
            try:
                rec = dict(zip(OPENCELLID_COLUMNS, row))
                vals = (rec["radio"].strip().upper()[:8], int(rec["mcc"]), int(rec["net"]), int(rec["area"]),
                        int(rec["cell"]), float(rec["lat"]), float(rec["lon"]),
                        int(rec["range"]) if rec.get("range", "").strip() else None,
                        int(rec["samples"]) if rec.get("samples", "").strip() else None,
                        datetime.fromtimestamp(int(rec["updated"]), tz=timezone.utc).isoformat()
                        if rec.get("updated", "").strip() else None)
                if not (-90 <= vals[5] <= 90 and -180 <= vals[6] <= 180):
                    raise ValueError("out of range")
            except (KeyError, ValueError, OverflowError):
                bad += 1
                continue
            buf.write("\t".join("\\N" if v is None else str(v) for v in vals) + "\n")
            good += 1
            n_buf += 1
            if n_buf >= batch:
                _copy(raw, buf)
                buf, n_buf = io.StringIO(), 0
        if n_buf:
            _copy(raw, buf)
    inserted = conn.execute(text(
        "INSERT INTO pol_cell_reference (dataset_id, radio, mcc, mnc, lac, cid, lat, lon, range_m, samples, updated_at) "
        "SELECT :d, radio, mcc, mnc, lac, cid, lat, lon, range_m, samples, updated_at FROM pol_cell_import "
        "ON CONFLICT DO NOTHING"), {"d": ds}).rowcount
    conn.execute(text("UPDATE pol_reference_dataset SET row_count = :n, duplicate_rows = :dup, rejected_rows = :bad "
                      "WHERE id = :d"), {"n": inserted, "dup": good - inserted, "bad": bad, "d": ds})
    return {"dataset_id": str(ds), "row_count": inserted, "duplicate_rows": good - inserted, "rejected_rows": bad,
            "sha256": sha}


def _copy(raw, buf):
    with raw.cursor() as cur:
        with cur.copy("COPY pol_cell_import (radio, mcc, mnc, lac, cid, lat, lon, range_m, samples, updated_at) "
                      "FROM STDIN") as cp:
            cp.write(buf.getvalue())


def coverage(conn, case_id, dataset_id) -> dict:
    """Tower keys of the case the dataset resolves, out of all complete keys (6.4: reported per import)."""
    keys = set()
    for (body,) in conn.execute(text(
            "SELECT r.body FROM phone_records r JOIN phone_extractions e ON e.id = r.extraction_id WHERE e.case_id = :c "
            "AND e.standing = 'active' AND r.model_type = 'CellTower'"), {"c": case_id}):
        k = tower_key(body)
        if None not in (k["mcc"], k["mnc"], k["lac"], k["cid"]):
            keys.add((k["mcc"], k["mnc"], k["lac"], k["cid"]))
    found = 0
    for k in keys:
        found += bool(conn.execute(text(
            "SELECT 1 FROM pol_cell_reference WHERE dataset_id = :d AND mcc = :a AND mnc = :b AND lac = :c AND cid = :x "
            "LIMIT 1"), {"d": dataset_id, "a": k[0], "b": k[1], "c": k[2], "x": k[3]}).scalar() or 0)
    return {"tower_keys": len(keys), "resolved": found}


# ---- WiFi anchors ---------------------------------------------------------------------------------------------------

def norm_bssid(v):
    if not v:
        return None
    s = "".join(ch for ch in str(v).lower() if ch in "0123456789abcdef")
    if len(s) != 12:
        return None
    return ":".join(s[i:i + 2] for i in range(0, 12, 2))


def _bssid_evidence(conn, case_id):
    """[(extraction_id, bssid, instant, record_uid)] for WirelessNetwork records with a BSSId and a time (6.3 step 1).
    Only the BSSId field is read: the SSID never anchors."""
    out = []
    for e, bssid, inst, uid in conn.execute(text(
            "SELECT a.extraction_id, t.value, a.instant_utc, a.record_uid FROM pol_activity_event a "
            "JOIN phone_interpretation_state s ON s.extraction_id = a.extraction_id "
            "JOIN phone_texts t ON t.extraction_id = a.extraction_id AND t.generation = s.generation AND "
            "  t.record_uid = a.record_uid AND t.field_name = 'BSSId' AND t.value_index = 0 "
            "JOIN phone_extractions x ON x.id = a.extraction_id AND x.standing = 'active' "
            "WHERE a.case_id = :c AND a.record_type = 'WirelessNetwork' AND "
            "a.time_field IN ('TimeStamp', 'LastConnection', 'LastAutoConnection')"), {"c": case_id}):
        b = norm_bssid(bssid)
        if b:
            out.append((e, b, inst, uid))
    return out


def build_anchors(conn, case_id) -> dict:
    """Recompute the case's anchors and its WiFi anchor observations (6.3 steps 2 to 4)."""
    conn.execute(text("DELETE FROM pol_place_observation WHERE case_id = :c AND source_kind = 'wifi_case_anchor'"),
                 {"c": case_id})
    conn.execute(text("DELETE FROM pol_wifi_anchor WHERE case_id = :c"), {"c": case_id})
    evidence = _bssid_evidence(conn, case_id)
    if not evidence:
        return {"anchored": 0, "tentative": 0}
    gps = defaultdict(list)
    for e, inst, lat, lon in conn.execute(text(
            "SELECT extraction_id, start_utc, lat, lon FROM pol_place_observation WHERE case_id = :c AND "
            "source_kind = 'gps' AND radius_m <= :r ORDER BY start_utc"), {"c": case_id, "r": ANCHOR_GPS_MAX_RADIUS_M}):
        gps[str(e)].append((inst, lat, lon))
    import bisect
    keys = {e: [g[0] for g in pts] for e, pts in gps.items()}
    matched = defaultdict(list)  # bssid -> [(lat, lon, day)]
    for e, b, inst, _ in evidence:
        pts, ks = gps.get(str(e)), keys.get(str(e))
        if not pts:
            continue
        i = bisect.bisect_left(ks, inst - ANCHOR_WINDOW)
        while i < len(pts) and pts[i][0] <= inst + ANCHOR_WINDOW:
            matched[b].append((pts[i][1], pts[i][2], pts[i][0].date()))
            i += 1
    anchors = {}
    stats = {"anchored": 0, "tentative": 0}
    for b, pts in matched.items():
        lat = statistics.median(p[0] for p in pts)
        lon = statistics.median(p[1] for p in pts)
        d = sorted(haversine_m(lat, lon, p[0], p[1]) for p in pts)
        p90 = d[min(len(d) - 1, int(math.ceil(0.9 * len(d))) - 1)]
        days = len({p[2] for p in pts})
        status = "anchored" if days >= ANCHOR_MIN_DAYS else "tentative"
        aid = conn.execute(text(
            "INSERT INTO pol_wifi_anchor (case_id, bssid_norm, lat, lon, radius_m, support_days, support_points, status) "
            "VALUES (:c, :b, :lat, :lon, :r, :d, :n, :s) RETURNING id"),
            {"c": case_id, "b": b, "lat": lat, "lon": lon, "r": max(ANCHOR_MIN_RADIUS_M, p90 + ANCHOR_PAD_M), "d": days,
             "n": len(pts), "s": status}).scalar()
        anchors[b] = (aid, lat, lon, max(ANCHOR_MIN_RADIUS_M, p90 + ANCHOR_PAD_M), status)
        stats[status] += 1
    rows = []
    for e, b, inst, uid in evidence:
        a = anchors.get(b)
        if a is None or a[4] != "anchored":
            continue
        rows.append({"c": case_id, "e": e, "ru": uid, "rt": "WirelessNetwork", "k": "presence",
                     "sk": "wifi_case_anchor", "lat": a[1], "lon": a[2], "rad": a[3], "rep": None, "rb": "wifi_anchor",
                     "s": inst, "en": inst, "os": "explicit", "sem": "event_instant", "pb": "wifi_seen", "fl": [],
                     "wa": a[0], "app": None})
    _insert(conn, rows)
    stats["observations"] = len(rows)
    return stats


# ---- reverse geocoding (6.5) ----------------------------------------------------------------------------------------

def _host_in_house(url):
    host = (urlparse(url).hostname or "").lower()
    if not host:
        return False
    if host == "localhost" or "." not in host:  # a container or host name on the deployment's own network
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return ip.is_private or ip.is_loopback


def reverse_geocoding_status(primary=None, fallback=None) -> dict:
    """``{"enabled": bool, "reason": str}``: enabled only when every configured backend is in house."""
    from services import geocoder
    backends = [b for b in ((primary, fallback) if (primary or fallback) else
                            (getattr(geocoder, "_PRIMARY", None), getattr(geocoder, "_FALLBACK", None))) if b]
    if not backends:
        return {"enabled": False, "reason": "No reverse geocoder is configured."}
    for b in backends:
        if b.name == "geonames":
            continue
        if b.name == "nominatim" and _host_in_house(getattr(b, "_base_url", "") or getattr(b, "base_url", "")):
            continue
        return {"enabled": False, "reason": "The configured %s backend is not in house; reverse geocoding is off so no "
                                            "position leaves the deployment." % b.name}
    return {"enabled": True, "reason": "In-house backend: %s." % ", ".join(b.name for b in backends)}


_GEO = {"status": None}


def check_reverse_geocoding_at_startup():
    st = reverse_geocoding_status()
    _GEO["status"] = st
    (log.info if st["enabled"] else log.warning)("Pattern of life reverse geocoding: %s", st["reason"])
    return st


def reverse_geocode(lat, lon):
    st = _GEO["status"] or check_reverse_geocoding_at_startup()
    if not st["enabled"]:
        return None
    from services import geocoder
    return geocoder.reverse_geocode(lat, lon)


def install():
    activity.register_after_activity(build)


def undated_positions(conn, extraction_ids) -> int:
    """Positions the phones hold that no window can show: read from the report, but with no usable instant (no time,
    or a local time with neither offset nor device zone), so ``build`` makes no observation of them. The Places view
    states this count, so "0 of 0" never reads as a phone with no positions."""
    n = 0
    for e in extraction_ids:
        st = activity.current_generation(conn, e)
        if st is None or not st.generation:
            continue
        n += int(conn.execute(text(
            "SELECT count(*) FROM phone_location_points p WHERE p.extraction_id = :e AND p.generation = :g AND NOT "
            "EXISTS (SELECT 1 FROM pol_place_observation o WHERE o.extraction_id = p.extraction_id AND o.record_uid = "
            "p.record_uid)"), {"e": str(e), "g": st.generation}).scalar() or 0)
    return n


def observations(conn, extraction_ids, start, end, kinds=None, offset=0, limit=1000):
    params = {"e": [str(x) for x in extraction_ids], "a": start, "b": end}
    where = ("extraction_id = ANY(CAST(:e AS uuid[])) AND start_utc < :b AND end_utc >= :a")
    if kinds:
        where += " AND kind = ANY(:k)"
        params["k"] = list(kinds)
    total = conn.execute(text("SELECT count(*) FROM pol_place_observation WHERE " + where), params).scalar()
    rows = [dict(r._mapping) for r in conn.execute(text(
        "SELECT * FROM pol_place_observation WHERE " + where + " ORDER BY start_utc, id OFFSET :o LIMIT :l"),
        dict(params, o=offset, l=limit))]
    return total, rows
