"""Backfill — materialise a Location point from EVERY coordinate-bearing model
(WiFi networks, searched places, journeys, ...) across the already-ingested
reports, so the map captures every point the device recorded — not just
Location-typed models.

WHY: only `_write_location` materialised coordinates, so ~25k WiFi geolocations
(24,047 in C2 alone) + searches were dropped. The pipeline now harvests them
(orchestrator Step 8.36); this applies the SAME writer method to existing data
by re-parsing each report XML. Idempotent (MERGE on key) — safe to re-run.

Run (GEOCODER so the new points get city-level addresses):
  sudo -u conorbowles51 env GEOCODER=geonames NEO4J_URI=bolt://localhost:7687 \
      NEO4J_USER=neo4j NEO4J_PASSWORD=testpassword PYTHONPATH=backend \
      venv/bin/python scripts/backfill_locations.py [LABEL ...]
LABELS: C1 C1b C2 C3 C4 C5 C6 C7 C8 C9  (default: all).
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
sys.path.append(str(ROOT / "ingestion" / "scripts"))
sys.path.append(str(ROOT / "scripts"))

from cellebrite.parser import CellebriteXMLParser          # noqa: E402
from cellebrite.neo4j_writer import CellebriteNeo4jWriter  # noqa: E402
from neo4j_client import Neo4jClient                        # noqa: E402
from forensic_export import REPORTS, CASE_DIR               # noqa: E402

CASE_ID = "43f1afb1-1d2b-4b3f-a832-19cd049c8a9e"


def owner_key(db, rk):
    rows = db.run_query(
        "MATCH (:PhoneReport {case_id:$cid, key:$rk})-[:BELONGS_TO]->(p:Person) "
        "RETURN p.key AS k LIMIT 1", cid=CASE_ID, rk=rk)
    return rows[0]["k"] if rows else None


def backfill(label, xml_path, db):
    parser = CellebriteXMLParser(str(xml_path))
    report = parser.parse_header()
    rk = (f"cellebrite-{report.case_info.case_number or 'unknown'}"
          f"-{report.case_info.evidence_number or 'unknown'}")
    region = "US"
    try:
        from services.case_storage import case_storage
        region = case_storage.get_default_region(CASE_ID)
    except Exception:
        pass
    w = CellebriteNeo4jWriter(
        neo4j_client=db, case_id=CASE_ID, report_key=rk, report=report,
        log_callback=lambda m: None, default_region=region,
    )
    w._phone_owner_key = owner_key(db, rk)

    t0 = time.time()
    n = created = 0
    for batch in parser.stream_models(batch_size=500):
        created += w.harvest_all_coordinates(batch)
        n += len(batch)
        if n % 50000 < 500:
            print(f"[{label}] ...{n} models, harvested={created} ({time.time()-t0:.0f}s)", flush=True)
    print(f"[{label}] rk={rk} owner={w._phone_owner_key} models={n} "
          f"harvested={created} ({time.time()-t0:.0f}s)", flush=True)


def main():
    labels = [a for a in sys.argv[1:] if a in REPORTS] or list(REPORTS)
    db = Neo4jClient()
    for label in labels:
        xml = CASE_DIR / REPORTS[label]
        if not xml.exists():
            print(f"[{label}] MISSING xml: {xml}")
            continue
        backfill(label, xml, db)


if __name__ == "__main__":
    main()
