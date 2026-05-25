"""Harvest photo geotags from cellebrite <taggedFiles> EXIF into the graph.

WHY (2026-05-25 geotag leak): photo GPS coordinates live in every report's
<taggedFiles> XML, but the ingestion pipeline only ever persisted them as a
*side-effect* of media-FILE registration (Step 9 attaches EXIF to a media
evidence row keyed by the file's resolved on-disk path). That path leaks:
  - media-registration is skipped for skip-media CLI ingests (C6/C8/bundle),
  - it was clobbered for C7 by scripts/bulk_register_reports.py (drop+reinsert
    plain rows, no EXIF), and
  - it silently dropped C3's 23 tagged photos whose file_ids never resolved
    into the registered set (binaries on disk, but not in _resolved_paths).
Net: coordinates present in XML, absent from the graph. Only C5's 99 survived.

This pass reads the coordinates DIRECTLY from <taggedFiles> (reusing the
validated parser — NO binary file needed), MERGEs one Location node per
geotagged photo (key `loc-photo-<file_id>`), reverse-geocodes it via the
configured backend, links it `(:PhoneReport)-[:CONTAINS]->(:Location)` so it
filters under "everything from this device", and `(:Person)-[:WAS_AT]->` from
the phone owner when known — exactly the shape model-Locations use, so the
harvested points render in the same LocationsTable / map views.

Idempotent: MERGE on (case_id, key) — safe to re-run; a re-run refreshes geocode
and re-links without duplicating.

--check : PARITY MODE. No writes. Per report, compares the geotag count in the
          XML against the persisted photo-Location count in the graph and exits
          non-zero on ANY mismatch. This is the guard the leak slipped past
          before — wire it into CI / a post-ingest assertion so XML-present
          geotags can never silently fail to persist again.

Run as conorbowles51 with the geocoder env so coords get city-level addresses:
  sudo -u conorbowles51 env GEOCODER=geonames venv/bin/python \
      scripts/harvest_geotags.py [--check] [report_root ...]
With no report_root args, auto-discovers every report under the case dir.
"""
from __future__ import annotations

import os
import re
import sys
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
# Mirror the proven cellebrite_service path setup: backend FIRST (insert 0) so
# `config` + `services` resolve to backend (backend/config.py reads NEO4J_* /
# GEOCODER from the env), and the ingestion scripts dir is APPENDED (last) so
# `cellebrite.parser` + `neo4j_client` still resolve. Putting scripts first
# would shadow backend/config and break the geocoder import — see WORKING.md.
sys.path.insert(0, str(ROOT / "backend"))
sys.path.append(str(ROOT / "ingestion" / "scripts"))

from cellebrite.parser import CellebriteXMLParser  # noqa: E402
from neo4j_client import Neo4jClient  # noqa: E402

try:
    from services.geocoder import reverse_geocode, geocoder_status
except Exception as _e:  # geocoder optional — but report WHY it failed
    print(f"WARN: geocoder unavailable ({_e!r}); harvesting without addresses")
    reverse_geocode = None
    geocoder_status = lambda: {"primary": None, "error": str(_e)}  # noqa: E731

CASE_ID = "43f1afb1-1d2b-4b3f-a832-19cd049c8a9e"
CASE_DIR = ROOT / "ingestion" / "data" / CASE_ID
OWNER = "oferreira@owlconsultancygroup.com"

CHECK_ONLY = "--check" in sys.argv
ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]


def discover_report_xmls() -> list[Path]:
    """Find every cellebrite report XML under the case dir.

    A report XML is a `*_Report.xml` whose parent directory is a report root
    (ends with `Report` or `Report (n)`). That parent-name guard cheaply
    excludes per-file artifacts like files/Text/crash_report.xml without
    parsing them.
    """
    out: list[Path] = []
    re_parent = re.compile(r"Report(\s*\(\d+\))?$")
    for p in CASE_DIR.rglob("*_Report.xml"):
        if re_parent.search(p.parent.name):
            out.append(p)
    return sorted(out)


def report_key_for(xml_path: Path) -> tuple[str, str]:
    """Return (report_key, label) by parsing the report header."""
    parser = CellebriteXMLParser(xml_path)
    report = parser.parse_header()
    cn = report.case_info.case_number or "unknown"
    en = report.case_info.evidence_number or "unknown"
    return f"cellebrite-{cn}-{en}", (report.report_name or xml_path.parent.name)


def geo_tagged_files(xml_path: Path) -> list:
    """Return TaggedFile objects that carry valid lat/lon (validated parser)."""
    tfs = CellebriteXMLParser(xml_path).parse_tagged_files()
    return [t for t in tfs if t.latitude is not None and t.longitude is not None]


def persisted_photo_loc_count(db: Neo4jClient, report_key: str) -> int:
    rows = db.run_query(
        """
        MATCH (l:Location {case_id: $cid, cellebrite_report_key: $rk})
        WHERE l.location_type = 'Photo'
        RETURN count(l) AS c
        """,
        cid=CASE_ID, rk=report_key,
    )
    return int(rows[0]["c"]) if rows else 0


def find_owner_key(db: Neo4jClient, report_key: str) -> str | None:
    rows = db.run_query(
        """
        MATCH (:PhoneReport {case_id: $cid, key: $rk})-[:BELONGS_TO]->(p:Person)
        RETURN p.key AS k LIMIT 1
        """,
        cid=CASE_ID, rk=report_key,
    )
    return rows[0]["k"] if rows else None


def harvest_report(db: Neo4jClient, xml_path: Path) -> dict:
    report_key, label = report_key_for(xml_path)
    geo = geo_tagged_files(xml_path)
    xml_count = len(geo)

    if CHECK_ONLY:
        graph_count = persisted_photo_loc_count(db, report_key)
        ok = graph_count == xml_count
        return {"label": label, "report_key": report_key, "xml": xml_count,
                "graph": graph_count, "ok": ok, "written": 0}

    owner_key = find_owner_key(db, report_key)
    written = 0
    for tf in geo:
        fid = tf.file_id or str(uuid.uuid4())
        key = f"loc-photo-{fid}"
        name = Path(tf.original_path).name if tf.original_path else "Photo location"

        props = {
            "id": str(uuid.uuid4()),
            "key": key,
            "name": name,
            "case_id": CASE_ID,
            "cellebrite_report_key": report_key,
            "source_type": "cellebrite",
            "location_type": "Photo",
            "location_category": "Photo EXIF",
            "source_app": "Photo EXIF",
            "latitude": float(tf.latitude),
            "longitude": float(tf.longitude),
            "photo_file_id": fid,
            "photo_path": tf.original_path or None,
        }
        if getattr(tf, "gps_altitude", None) is not None:
            props["gps_altitude"] = tf.gps_altitude
        if getattr(tf, "camera_make", None):
            props["camera_make"] = tf.camera_make
        if getattr(tf, "camera_model", None):
            props["camera_model"] = tf.camera_model
        ts = getattr(tf, "capture_time", None) or getattr(tf, "creation_time", None)
        if ts:
            props["timestamp"] = ts
            if len(ts) >= 10:
                props["date"] = ts[:10]
                if len(ts) > 16:
                    props["time"] = ts[11:16]

        # Reverse-geocode (city level via geonames) so the point carries an
        # address/place_name + a geocode_source badge like model-Locations.
        if reverse_geocode is not None:
            try:
                g = reverse_geocode(props["latitude"], props["longitude"])
            except Exception:
                g = None
            if g:
                for k in ("address", "place_name", "country", "country_code",
                          "admin1", "admin2", "geocode_source", "geocode_accuracy"):
                    v = g.get(k)
                    if v is not None:
                        props[k] = v

        props = {k: v for k, v in props.items() if v is not None}

        db.run_query(
            "MERGE (l:Location {case_id: $cid, key: $key}) SET l += $props, l:CbNode",
            cid=CASE_ID, key=key, props=props,
        )
        db.run_query(
            """
            MATCH (r:PhoneReport {case_id: $cid, key: $rk})
            MATCH (l:Location {case_id: $cid, key: $key})
            MERGE (r)-[:CONTAINS {case_id: $cid}]->(l)
            """,
            cid=CASE_ID, rk=report_key, key=key,
        )
        if owner_key:
            db.run_query(
                """
                MATCH (p:Person {case_id: $cid, key: $ok})
                MATCH (l:Location {case_id: $cid, key: $key})
                MERGE (p)-[:WAS_AT {case_id: $cid}]->(l)
                """,
                cid=CASE_ID, ok=owner_key, key=key,
            )
        written += 1

    graph_count = persisted_photo_loc_count(db, report_key)
    return {"label": label, "report_key": report_key, "xml": xml_count,
            "graph": graph_count, "ok": graph_count == xml_count, "written": written}


def main() -> int:
    print("MODE:", "CHECK (parity only, no writes)" if CHECK_ONLY else "HARVEST")
    print("GEOCODER:", geocoder_status())

    if ARGS:
        xmls = []
        for a in ARGS:
            root = (CASE_DIR / a) if not Path(a).is_absolute() else Path(a)
            found = list(root.rglob("*_Report.xml")) if root.is_dir() else [root]
            xmls += [p for p in found if re.search(r"Report(\s*\(\d+\))?$", p.parent.name)]
        xmls = sorted(set(xmls))
    else:
        xmls = discover_report_xmls()

    print(f"Reports discovered: {len(xmls)}")
    db = Neo4jClient()
    results = []
    try:
        for x in xmls:
            r = harvest_report(db, x)
            results.append(r)
            flag = "OK " if r["ok"] else "MISMATCH"
            print(f"  [{flag}] {r['label']:<48} xml={r['xml']:>4} graph={r['graph']:>4}"
                  + ("" if CHECK_ONLY else f" written={r['written']}"))
    finally:
        db.close()

    mismatches = [r for r in results if not r["ok"]]
    tot_xml = sum(r["xml"] for r in results)
    tot_graph = sum(r["graph"] for r in results)
    print("-" * 72)
    print(f"TOTAL geotags: xml={tot_xml}  graph={tot_graph}  reports={len(results)}"
          f"  mismatches={len(mismatches)}")
    if mismatches:
        print("PARITY FAIL — geotags present in XML are not all persisted:")
        for r in mismatches:
            print(f"  {r['label']}: xml={r['xml']} graph={r['graph']}")
        return 1
    print("PARITY OK — every XML geotag is persisted in the graph.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
