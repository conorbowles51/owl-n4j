"""P3 backfill — replace the conflated contact/identity data in the live graph.

WHY: neo4j_writer used to set Person.name ON CREATE only, so the first sighting
of a number won the name and every other saved name was discarded at ingest
(the conflation). The pipeline is now fixed (ContactEntry nodes + name_aliases +
best-primary in finalise_person_identities). This backfill applies that SAME
fixed code path to the ALREADY-INGESTED 10 reports WITHOUT a full reingest:

  writer.identity_only = True  → _create_node / _create_relationship are no-ops
  (comms/calls/locations already exist and are accurate), so running the normal
  handlers only (a) accumulates every name each number was saved under and
  (b) MERGEs a ContactEntry per address-book record. Then
  finalise_person_identities() writes name_aliases + upgrades the primary name.

Idempotent (all MERGE / SET) — safe to re-run. Comms/calls/locations untouched.

Run (NEO4J_* + backend on path needed by the writer's lazy service imports):
  sudo -u conorbowles51 env NEO4J_URI=bolt://localhost:7687 NEO4J_USER=neo4j \
      NEO4J_PASSWORD=testpassword venv/bin/python \
      scripts/backfill_contact_identities.py [LABEL ...]
LABELS: C1 C1b C2 C3 C4 C5 C6 C7 C8 C9  (default: all).
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
sys.path.append(str(ROOT / "ingestion" / "scripts"))

from cellebrite.parser import CellebriteXMLParser          # noqa: E402
from cellebrite.neo4j_writer import CellebriteNeo4jWriter  # noqa: E402
from neo4j_client import Neo4jClient                        # noqa: E402

# reuse the validated report→XML map
sys.path.append(str(ROOT / "scripts"))
from forensic_export import REPORTS, CASE_DIR              # noqa: E402

CASE_ID = "43f1afb1-1d2b-4b3f-a832-19cd049c8a9e"


def backfill(label, xml_path, db):
    parser = CellebriteXMLParser(str(xml_path))
    report = parser.parse_header()
    report_key = (
        f"cellebrite-{report.case_info.case_number or 'unknown'}"
        f"-{report.case_info.evidence_number or 'unknown'}"
    )
    default_region = "US"
    try:
        from services.case_storage import case_storage
        default_region = case_storage.get_default_region(CASE_ID)
    except Exception:
        pass

    writer = CellebriteNeo4jWriter(
        neo4j_client=db, case_id=CASE_ID, report_key=report_key,
        report=report, default_region=default_region,
    )
    writer.identity_only = True  # don't recreate nodes/comm-edges; names + entries only

    # Only identity-bearing model types carry saved names / contact records.
    # Skip Location/NetworkUsage/VisitedPage/Cookie/etc. entirely (they'd just
    # build props then no-op the node create) — big speedup on large reports.
    IDENTITY_TYPES = {"Contact", "Call", "Chat", "InstantMessage", "Email"}

    t0 = time.time()
    n = 0
    for batch in parser.stream_models(batch_size=500):
        relevant = [m for m in batch if m.model_type in IDENTITY_TYPES]
        if relevant:
            writer.write_batch(relevant)
        n += len(batch)
        if n % 50000 < 500:
            print(f"[{label}] ...{n} models, entries={writer.contact_entries_created} "
                  f"({time.time()-t0:.0f}s)", flush=True)
    updated = writer.finalise_person_identities()
    dt = time.time() - t0
    print(f"[{label}] key={report_key} models={n} "
          f"contact_entries={writer.contact_entries_created} "
          f"persons_updated={updated} errors={sum(writer.write_errors.values())} "
          f"({dt:.0f}s)")


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
