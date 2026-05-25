"""Ingest ONE cellebrite report folder (XML -> Neo4j), as conorbowles51.

Usage:
  sudo -u conorbowles51 env GEOCODER=geonames venv/bin/python \
      scripts/ingest_one_report.py "<report_rel_path>" "<evidence_number>" ["<device_identifier>"]

Mirrors the proven reingest_all3 pattern: create a cellebrite_ingestion task
(so the UI tracks it), then call the shared service process_cellebrite_report
with force=True. Prints detected phone_numbers up front so the missing-identifier
precondition is visible. One report per invocation (sequential, RAM-watched).
"""
import sys
sys.path.insert(0, '/home/conorbowles51/app_v2/backend')  # backend FIRST (config + services)
from pathlib import Path

from services.background_task_storage import background_task_storage
from services.cellebrite_service import process_cellebrite_report, check_cellebrite_report
from services.geocoder import geocoder_status
from services.case_storage import case_storage

CASE = "43f1afb1-1d2b-4b3f-a832-19cd049c8a9e"
DATA = Path("/home/conorbowles51/app_v2/ingestion/data") / CASE
OWNER = "oferreira@owlconsultancygroup.com"

rel = sys.argv[1]
evnum = sys.argv[2]
device_identifier = sys.argv[3] if len(sys.argv) > 3 else None
folder = DATA / rel

print("GEOCODER:", geocoder_status(), flush=True)
print("default_region:", case_storage.get_default_region(CASE), flush=True)
print(f"REPORT: {rel}", flush=True)

det = check_cellebrite_report(folder, case_id=CASE)
print("DETECT suitable=", det.get("suitable"),
      "report_name=", det.get("report_name"),
      "device_model=", det.get("device_model"),
      "phone_numbers=", det.get("phone_numbers"),
      "duplicate=", det.get("duplicate"), flush=True)

task = background_task_storage.create_task(
    task_type="cellebrite_ingestion",
    task_name=f"Cellebrite ingest: {rel}",
    case_id=CASE,
    owner=OWNER,
    metadata={"folder_path": rel, "report_name": rel,
              "case_number": "220049582", "evidence_number": evnum},
)
print("TASK_ID", task["id"], flush=True)

kwargs = dict(folder_path=folder, case_id=CASE, task_id=task["id"], owner=OWNER, force=True)
if device_identifier:
    kwargs["device_identifier"] = device_identifier

try:
    result = process_cellebrite_report(**kwargs)
    print("RESULT_STATUS", result.get("status"), flush=True)
    print("RESULT_REASON", result.get("reason") or result.get("message") or "", flush=True)
    print("RESULT_NODES", result.get("total_nodes"), flush=True)
    print("RESULT_WRITE_ERRORS", result.get("write_errors_total"), flush=True)
except Exception:
    import traceback
    print("RESULT_STATUS exception", flush=True)
    traceback.print_exc()
print("REPORT_DONE", flush=True)
