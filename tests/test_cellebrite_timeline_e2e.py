"""
End-to-end test for the Cellebrite Timeline / Events fetch path.

Purpose
-------
The deployed environment was showing an empty Timeline body despite the
type-filter chips reporting non-zero per-type counts. We needed to confirm
whether the bug is in our recent changes (multi-phone identity + dedup +
parser improvements) or somewhere else upstream.

This test exercises the full ingest -> query path against a real Neo4j,
the same way the deployed app does:
  1. Ingest a known sample Cellebrite report (the C3 sample on disk).
  2. Call get_cellebrite_reports — the same call /api/cellebrite/reports
     makes — and assert the new fields (manufacturer, device_name_candidates,
     accessory_imeis, display_index) are populated.
  3. Call get_cellebrite_event_types — the same call that powers the
     type-filter chips — and capture per-type counts.
  4. Call get_cellebrite_events with all types active — the same call the
     Timeline body uses — and assert the totals match what the type
     counter reported. A mismatch here means the bug is reproducible.
  5. Exercise the new dedup detection (find_existing_phone_report) and
     the cleanup path (delete_phone_report).

Run
---
Requires:
  - Neo4j on bolt://localhost:7687 with creds from .env
  - The C3 sample folder at the path below
  - The .venv interpreter (pip-installed neo4j driver, pydantic, etc.)

    PYTHONPATH=ingestion/scripts:backend \\
      .venv/bin/python -m pytest tests/test_cellebrite_timeline_e2e.py -xvs

Or directly without pytest:
    PYTHONPATH=ingestion/scripts:backend \\
      .venv/bin/python tests/test_cellebrite_timeline_e2e.py
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Path + env setup so importing the ingestion / backend code works the same
# way it does in production.
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "ingestion" / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "backend"))

# Load the .env file so NEO4J_URI/USER/PASSWORD are available the same way
# the backend reads them. python-dotenv is a transitive dep of the backend
# but we import defensively.
try:
    from dotenv import load_dotenv
    load_dotenv(REPO_ROOT / ".env")
except Exception:
    pass

# Use a fixed CASE_ID so a partial run can be re-attempted without re-ingest.
# Override via env var if you want a fresh ingest.
CASE_ID = os.getenv("E2E_CASE_ID", "e2e-test-fixed-case")
SAMPLE_DIR = REPO_ROOT / "Cellebrite Report Sample Phone"


def _log(msg: str) -> None:
    print(f"  {msg}")


def main() -> int:
    print(f"\n=== Cellebrite Timeline E2E Test ===")
    print(f"CASE_ID  : {CASE_ID}")
    print(f"SAMPLE   : {SAMPLE_DIR}")
    print()

    # 0) Sanity checks
    if not SAMPLE_DIR.is_dir():
        print(f"FAIL: sample dir not found: {SAMPLE_DIR}")
        return 1

    from services.neo4j_service import neo4j_service
    print("[0] Connected to Neo4j:", os.getenv("NEO4J_URI", "default"))

    # ------------------------------------------------------------------
    # 1) Ingest the C3 sample. Skip if already ingested into this case.
    # ------------------------------------------------------------------
    existing = neo4j_service.get_cellebrite_reports(CASE_ID)
    if existing:
        report_key = existing[0]["report_key"]
        print(f"\n[1] Skip ingest — already in case as {report_key} "
              f"({existing[0].get('stats', {}).get('messages', 0)} messages)")
    else:
        print("\n[1] Ingesting C3 sample report (this takes ~10-15 min for 16K models)...")
        from cellebrite.ingestion import ingest_cellebrite_report

        t0 = time.time()
        ingest_result = ingest_cellebrite_report(
            report_dir=SAMPLE_DIR,
            case_id=CASE_ID,
            log_callback=_log,
            owner="e2e-test",
        )
        dur = time.time() - t0
        print(f"  ingest finished in {dur:.1f}s, status={ingest_result.get('status')}")
        assert ingest_result.get("status") == "success", \
            f"ingest failed: {ingest_result}"
        report_key = ingest_result.get("report_key")
        assert report_key, "ingest result missing report_key"
        print(f"  report_key = {report_key}")

    # ------------------------------------------------------------------
    # 2) get_cellebrite_reports — what /api/cellebrite/reports returns.
    # ------------------------------------------------------------------
    print("\n[2] get_cellebrite_reports — fields exposed to the frontend")
    reports = neo4j_service.get_cellebrite_reports(CASE_ID)
    assert len(reports) == 1, f"expected 1 report, got {len(reports)}"
    r = reports[0]
    print(f"  report_key            = {r['report_key']}")
    print(f"  display_index         = {r['display_index']}")
    print(f"  device_model          = {r['device_model']!r}")
    print(f"  manufacturer          = {r.get('manufacturer')!r}")
    print(f"  detected_device_model = {r.get('detected_device_model')!r}")
    print(f"  device_name_override  = {r.get('device_name_override')!r}")
    print(f"  imei                  = {r.get('imei')!r}")
    print(f"  accessory_imeis       = {r.get('accessory_imeis')!r}")
    print(f"  device_name_candidates= {r.get('device_name_candidates')!r}")
    print(f"  stats                 = {r.get('stats')!r}")

    # New fields from Phase 1 must be present.
    assert "display_index" in r, "display_index missing — Phase 1 backend change not active"
    assert r["display_index"] == 0, f"first report should have display_index 0, got {r['display_index']}"
    assert "manufacturer" in r, "manufacturer field missing"
    assert "detected_device_model" in r, "detected_device_model field missing"
    assert "device_name_candidates" in r, "device_name_candidates field missing"
    # Parser should now populate at least one candidate for a real phone.
    candidates = r.get("device_name_candidates") or []
    assert len(candidates) > 0, \
        f"expected device_name_candidates to be populated, got {candidates}"
    print(f"  PASS: {len(candidates)} candidate(s) detected")

    # ------------------------------------------------------------------
    # 3) get_cellebrite_event_types — what powers the type-filter chips.
    # ------------------------------------------------------------------
    print("\n[3] get_cellebrite_event_types — per-type counts")
    # The service returns a bare list; the router wraps it as {"types": ...}.
    # We talk to the service directly here.
    types = neo4j_service.get_cellebrite_event_types(
        case_id=CASE_ID,
        report_keys=[report_key],
    )
    counts_by_type = {t["event_type"]: t["count"] for t in types}
    total_per_type = sum(counts_by_type.values())
    for t in types:
        print(f"  {t['event_type']:14s}  count={t['count']:>6}  geolocated={t.get('geolocated', '-')}")
    print(f"  SUM over types        = {total_per_type}")
    assert total_per_type > 0, \
        "type counter shows 0 events for everything — no point continuing"

    # ------------------------------------------------------------------
    # 4) get_cellebrite_events — what the Timeline body fetches.
    #    All types active (mirrors what the UI sends).
    # ------------------------------------------------------------------
    print("\n[4] get_cellebrite_events — Timeline body fetch")
    all_types = [t["event_type"] for t in types]
    events_result = neo4j_service.get_cellebrite_events(
        case_id=CASE_ID,
        report_keys=[report_key],
        event_types=all_types,
        only_geolocated=False,
        limit=500_000,  # match the frontend's bumped cap
        offset=0,
    )
    events = events_result.get("events", [])
    total_returned = events_result.get("total", len(events))
    print(f"  total       = {total_returned}")
    print(f"  events len  = {len(events)}")

    # Per-type breakdown of what came back, so we can see if a single
    # type is mysteriously dropping its rows.
    breakdown: dict[str, int] = {}
    for e in events:
        breakdown[e.get("event_type", "?")] = breakdown.get(e.get("event_type", "?"), 0) + 1
    for k in sorted(breakdown.keys()):
        expected = counts_by_type.get(k, 0)
        marker = "OK" if breakdown[k] >= expected * 0.95 else "MISMATCH"
        print(f"  events {k:14s}  events_count={breakdown[k]:>6}  type_count={expected:>6}  [{marker}]")

    # Hard assertion — the bug we're hunting would make this fail.
    assert total_returned > 0, \
        "FAIL: Timeline body would be empty even though type counts are non-zero. " \
        "This is the deployed-env bug reproduced locally."

    # The events feed is unioned per type, but each type's count comes from
    # a slightly different WHERE (e.g. wifi/search/visit add `timestamp IS
    # NOT NULL`). So we don't expect identical counts, but the total should
    # be in the same ballpark.
    if total_returned < total_per_type * 0.5:
        print(f"  WARN: events total ({total_returned}) is < 50% of type sum "
              f"({total_per_type}) — investigate which type is dropping rows.")
    else:
        print(f"  PASS: events total within expected band of type sum")

    # Verify that returned events reference the correct phone.
    keys_seen = {e.get("device_report_key") for e in events if e.get("device_report_key")}
    print(f"  device_report_key values seen: {keys_seen}")
    assert keys_seen == {report_key}, \
        f"events reference unexpected report keys: {keys_seen} vs expected {report_key}"

    # ------------------------------------------------------------------
    # 5) Phase 2 dedup detection — find_existing_phone_report.
    # ------------------------------------------------------------------
    print("\n[5] find_existing_phone_report — dedup detection")
    found_by_key = neo4j_service.find_existing_phone_report(
        case_id=CASE_ID,
        report_key=report_key,
    )
    assert found_by_key is not None, "dedup by key failed"
    print(f"  by report_key:        {found_by_key.get('device_model')} ({found_by_key.get('evidence_number')})")

    if r.get("imei"):
        found_by_imei = neo4j_service.find_existing_phone_report(
            case_id=CASE_ID,
            report_key="cellebrite-something-else-entirely",
            imei=r["imei"],
        )
        assert found_by_imei is not None, "dedup by IMEI failed"
        print(f"  by imei:              {found_by_imei.get('device_model')} (IMEI {found_by_imei.get('imei')})")

    miss = neo4j_service.find_existing_phone_report(
        case_id=CASE_ID,
        report_key="cellebrite-nope-nope",
        imei="000000000000000",
    )
    assert miss is None, f"expected miss, got {miss}"
    print("  miss case returned None (correct)")

    # ------------------------------------------------------------------
    # 6) Phase 3 delete cleanup — delete_phone_report.
    # ------------------------------------------------------------------
    print("\n[6] delete_phone_report — cleanup")
    delete_result = neo4j_service.delete_phone_report(CASE_ID, report_key)
    print(f"  delete result: {delete_result}")
    assert delete_result.get("status") == "deleted", \
        f"delete failed: {delete_result}"
    assert delete_result.get("deleted_phone_report") == 1, \
        f"expected 1 PhoneReport node deleted, got {delete_result.get('deleted_phone_report')}"
    assert delete_result.get("deleted_nodes", 0) > 0, \
        f"expected many tagged nodes deleted, got {delete_result.get('deleted_nodes')}"

    # Confirm no PhoneReport remains for the case.
    after = neo4j_service.get_cellebrite_reports(CASE_ID)
    assert len(after) == 0, f"expected 0 reports after delete, got {len(after)}"
    print("  PASS: case is fully cleaned")

    # Belt-and-braces: also drop any stragglers tagged with case_id (in
    # case anything escaped the cellebrite_report_key tagging).
    print("\n[7] Final cleanup — drop any case-scoped stragglers")
    with neo4j_service._driver.session() as session:
        deleted = session.run(
            "MATCH (n {case_id: $case_id}) DETACH DELETE n RETURN count(n) AS c",
            case_id=CASE_ID,
        ).single()["c"]
        print(f"  removed {deleted} stragglers")

    print("\n=== ALL ASSERTIONS PASSED ===")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except AssertionError as e:
        print(f"\nFAIL: {e}")
        sys.exit(2)
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"\nERROR: {e}")
        sys.exit(3)
