"""
Cellebrite Report Processing Service

Handles detection and background processing of Cellebrite UFED phone
extraction reports. Follows the same pattern as wiretap_service.py.
"""

import sys
from pathlib import Path
from typing import Dict, List, Optional, Callable
from datetime import datetime

from config import BASE_DIR
from services._timeutil import utcnow_iso


# User-facing ingestion stages (ordered). The pipeline emits finer-grained
# `phase` markers via its progress callback; we group them into these stages so
# the UI can show a readable checklist with per-stage timing. See PHASE_TO_STAGE.
INGEST_STAGES = [
    ("read", "Reading report"),
    ("report", "Registering device"),
    ("write", "Writing records"),
    ("identities", "Resolving identities"),
    ("locations", "Harvesting locations"),
    ("linking", "Linking"),
    ("media", "Registering media"),
]
_STAGE_INDEX = {key: i for i, (key, _label) in enumerate(INGEST_STAGES)}

# Map a pipeline phase (emitted by ingest_cellebrite_report) to its UI stage.
PHASE_TO_STAGE = {
    "detect": "read",
    "parse": "read",
    "file_index": "read",
    "resolve_paths": "read",
    "create_report": "report",
    "identify_owner": "report",
    "map_files": "report",
    "writing": "write",
    "finalising_sim": "identities",
    "person_identity": "identities",
    "geotag_harvest": "locations",
    "coordinate_harvest": "locations",
    "linking_contains": "linking",
    "geotag_backfill": "linking",
    "registering_media": "media",
}


def _build_stage_list(runtime: Dict[str, Dict], current_key: Optional[str],
                      terminal: Optional[str]) -> List[Dict]:
    """Render the ordered stage checklist from accumulated per-stage timing.

    runtime: {stage_key: {started_at, completed_at, total, completed, failed}}
    current_key: the stage currently in progress (None before the first phase)
    terminal: None while running, "completed" or "failed" once the task ends.
    """
    cur_idx = _STAGE_INDEX.get(current_key, -1)
    out: List[Dict] = []
    for i, (key, label) in enumerate(INGEST_STAGES):
        st = runtime.get(key, {})
        started = st.get("started_at")
        completed = st.get("completed_at")
        if terminal == "completed":
            status = "completed"
        elif terminal == "failed":
            status = "failed" if key == current_key else ("completed" if (completed or i < cur_idx) else "pending")
        else:
            if completed or (current_key is not None and i < cur_idx):
                status = "completed"
            elif key == current_key:
                status = "running"
            else:
                status = "pending"
        entry = {"key": key, "label": label, "status": status}
        if started:
            entry["started_at"] = started
        # Stamp a completion time for anything we now consider finished.
        if status == "completed":
            entry["completed_at"] = completed or utcnow_iso()
        if key == "write":
            entry["total"] = st.get("total", 0)
            entry["completed"] = st.get("completed", 0)
            entry["failed"] = st.get("failed", 0)
        out.append(entry)
    return out


def _import_cellebrite():
    """Dynamically import the Cellebrite ingestion module."""
    scripts_dir = BASE_DIR / "ingestion" / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.append(str(scripts_dir))

    from cellebrite.ingestion import (
        detect_cellebrite_xml,
        ingest_cellebrite_report,
    )
    return detect_cellebrite_xml, ingest_cellebrite_report


def check_cellebrite_report(folder_path: Path, case_id: Optional[str] = None) -> Dict:
    """
    Check if a folder contains a Cellebrite UFED report.

    Reads only the first 4KB of XML files to check for the
    Cellebrite namespace — fast and non-destructive.

    When `case_id` is provided, also checks for an existing PhoneReport
    in that case that would collide with the new ingest. The result
    carries `duplicate=True` and `existing` (the colliding report's
    summary) so the frontend can prompt for confirmation before posting
    to /cellebrite/process with `force=True`.

    Args:
        folder_path: Path to the folder to check
        case_id:     Optional case to check for collisions in

    Returns:
        Dict with detection result including report metadata
    """
    if not folder_path.exists() or not folder_path.is_dir():
        return {
            "suitable": False,
            "message": "Folder does not exist or is not a directory",
        }

    detect_cellebrite_xml, _ = _import_cellebrite()

    xml_path = detect_cellebrite_xml(folder_path)
    if not xml_path:
        return {
            "suitable": False,
            "message": "No Cellebrite UFED XML report found",
        }

    # Parse just the header for metadata preview
    from cellebrite.parser import CellebriteXMLParser
    from cellebrite.ingestion import build_report_key

    try:
        parser = CellebriteXMLParser(xml_path)
        report = parser.parse_header()

        # Compose the friendly device name the same way the reports
        # endpoint does, so the dialog text matches what the user sees
        # everywhere else.
        manufacturer = report.device_info.manufacturer or ""
        detected_model = report.device_info.device_model or ""
        if manufacturer and detected_model:
            display_device = f"{manufacturer} {detected_model}"
        elif detected_model:
            display_device = detected_model
        else:
            display_device = "Unknown Device"

        # Mirror the report_key construction done by the orchestrator
        # (same helper, so the two can't drift) to detect collisions
        # before the user even kicks off the ingest.
        report_key = build_report_key(report)

        existing = None
        if case_id:
            from .neo4j_service import neo4j_service
            try:
                existing = neo4j_service.find_existing_phone_report(
                    case_id=case_id,
                    report_key=report_key,
                    imei=report.device_info.imei,
                    evidence_number=report.case_info.evidence_number,
                )
            except Exception:
                # Don't block the check on a transient Neo4j hiccup;
                # the ingest path will surface any real failure.
                existing = None

        result: Dict = {
            "suitable": True,
            "message": "Cellebrite UFED report detected",
            "xml_file": xml_path.name,
            "report_key": report_key,
            "report_name": report.report_name,
            "report_version": report.report_version,
            "case_number": report.case_info.case_number,
            "evidence_number": report.case_info.evidence_number,
            "examiner": report.case_info.examiner,
            "crime_type": report.case_info.crime_type,
            "device_model": display_device,
            "manufacturer": manufacturer,
            "detected_device_model": detected_model,
            "device_name_candidates": list(report.device_info.device_name_candidates),
            "imei": report.device_info.imei,
            "accessory_imeis": list(report.device_info.accessory_imeis),
            "phone_numbers": report.device_info.msisdn,
            "node_count": report.node_count,
            "model_count": report.model_count,
            "duplicate": False,
            "existing": None,
        }

        if existing:
            result["duplicate"] = True
            result["existing"] = existing
            result["message"] = (
                f"This case already contains '{existing.get('device_model') or 'a phone'}' "
                f"(evidence {existing.get('evidence_number') or '—'}). "
                "Re-ingest will replace the existing data."
            )

        return result
    except Exception as e:
        return {
            "suitable": False,
            "message": f"Error parsing Cellebrite XML: {e}",
        }


def process_cellebrite_report(
    folder_path: Path,
    case_id: str,
    task_id: str,
    owner: Optional[str] = None,
    log_callback: Optional[Callable[[str], None]] = None,
    force: bool = False,
    device_identifier: Optional[str] = None,
) -> Dict:
    """
    Process a Cellebrite UFED report folder (runs synchronously).

    Called from a background task. Updates the background task storage
    with progress and results.

    When `force` is False and the case already contains a PhoneReport
    that would collide with this one, the task fails fast with a
    duplicate error and no graph mutation. When `force` is True, the
    existing PhoneReport (and every node tagged with its
    cellebrite_report_key) is deleted before the new ingest runs.

    Args:
        folder_path: Path to the Cellebrite report folder
        case_id: Case ID for graph isolation
        task_id: Background task ID for progress tracking
        owner: Username for evidence ownership
        log_callback: Optional progress logging callback
        force: If True, replace any existing report with the same key

    Returns:
        Dict with ingestion result
    """
    from .background_task_storage import background_task_storage, TaskStatus
    from .evidence_storage import evidence_storage
    from .evidence_log_storage import evidence_log_storage

    # Update task to running
    background_task_storage.update_task(
        task_id,
        status=TaskStatus.RUNNING.value,
        started_at=utcnow_iso(),
    )

    # Per-stage timing accumulator for the UI checklist (defined here so the
    # except handler can finalise the checklist even if a pre-ingest step throws).
    stage_runtime: Dict[str, Dict] = {}
    _stage = {"key": None}

    # Create a log callback that writes to both the task log and any provided callback
    def _log(msg: str):
        if log_callback:
            log_callback(msg)
        evidence_log_storage.add_log(
            case_id=case_id,
            evidence_id=None,
            filename=None,
            level="info",
            message=msg,
        )

    try:
        # Re-check for collisions at ingest time (the frontend may have
        # called check_cellebrite_report earlier, but a race is possible
        # if two ingests target the same case).
        precheck = check_cellebrite_report(folder_path, case_id=case_id)
        if precheck.get("duplicate") and not force:
            existing = precheck.get("existing") or {}
            background_task_storage.update_task(
                task_id,
                status=TaskStatus.FAILED.value,
                completed_at=utcnow_iso(),
                error="duplicate_phone_report",
            )
            _log(
                f"Refusing to ingest: a phone report with key "
                f"{existing.get('report_key')} already exists in this case. "
                "Pass force=true (or delete the existing report) to replace it."
            )
            return {
                "status": "error",
                "reason": "duplicate",
                "existing": existing,
            }

        # If force is set and a duplicate exists, delete the existing
        # PhoneReport (and every node tagged with its key) first so the
        # fresh ingest doesn't pile on top.
        if force and precheck.get("duplicate"):
            existing = precheck.get("existing") or {}
            existing_key = existing.get("report_key")
            if existing_key:
                from .neo4j_service import neo4j_service
                deleted = neo4j_service.delete_phone_report(case_id, existing_key)
                _log(
                    f"Replaced existing phone report {existing_key}: "
                    f"removed {deleted.get('deleted_nodes', 0)} nodes "
                    f"+ {deleted.get('deleted_phone_report', 0)} PhoneReport node(s)."
                )

        _, ingest_cellebrite_report = _import_cellebrite()

        # Heartbeat: forwards per-batch progress from the writer into
        # background_task_storage. update_task auto-bumps `updated_at`
        # on every call, which feeds:
        #   - the frontend's progress bar / "Processing N of M models"
        #   - the stalled-task heuristic in BackgroundTasksPanel
        #   - the startup watchdog (V3) — anything older than 5 min is
        #     declared dead.
        # The orchestrator already throttles to ~1 call/2s; no
        # additional rate-limiting needed here.
        # The pipeline emits a `phase` on its progress payloads; we translate
        # phase→stage and stamp start/end times as stages transition.
        # `_stage["key"]` holds the in-progress stage so the final completion/
        # failure handlers can finish the checklist correctly.
        def _advance_stage(stage_key: str):
            """Open `stage_key`, closing every earlier stage that isn't yet done."""
            if not stage_key or stage_key == _stage["key"]:
                return
            now = utcnow_iso()
            new_idx = _STAGE_INDEX.get(stage_key, -1)
            for key, _label in INGEST_STAGES[:new_idx]:
                st = stage_runtime.setdefault(key, {})
                st.setdefault("started_at", now)
                if not st.get("completed_at"):
                    st["completed_at"] = now
            st = stage_runtime.setdefault(stage_key, {})
            st.setdefault("started_at", now)
            _stage["key"] = stage_key

        def _heartbeat(payload: dict):
            try:
                phase = payload.get("phase")
                stage_key = PHASE_TO_STAGE.get(phase) if phase else None
                if stage_key:
                    _advance_stage(stage_key)
                    if stage_key == "write":
                        st = stage_runtime.setdefault("write", {})
                        st["total"] = payload.get("total") or 0
                        st["completed"] = payload.get("completed") or 0
                        st["failed"] = payload.get("failed") or 0
                background_task_storage.update_task(
                    task_id,
                    progress_total=payload.get("total") or 0,
                    progress_completed=payload.get("completed") or 0,
                    progress_failed=payload.get("failed") or 0,
                    stages=_build_stage_list(stage_runtime, _stage["key"], None),
                )
            except Exception as e:
                _log(f"WARNING: heartbeat update failed: {e}")

        result = ingest_cellebrite_report(
            report_dir=folder_path,
            case_id=case_id,
            log_callback=_log,
            owner=owner,
            evidence_storage=evidence_storage,
            progress_callback=_heartbeat,
            device_identifier=device_identifier,
        )

        if result.get("status") == "success":
            # Failure-rate threshold: if more than 5% of expected
            # entities raised inside their handler, the task succeeded
            # in name only. Mark it FAILED with the breakdown so the UI
            # surfaces it loudly instead of looking green-and-good.
            # Pre-2026-05-23 this was silent — users got a "completed"
            # task and noticed missing data weeks later.
            xml_total = result.get("xml_model_count") or 0
            errors_total = result.get("write_errors_total") or 0
            error_rate = (errors_total / xml_total) if xml_total else 0.0
            FAILURE_THRESHOLD = 0.05

            if error_rate > FAILURE_THRESHOLD:
                breakdown = result.get("write_errors") or {}
                top = ", ".join(
                    f"{t}={c}" for t, c in
                    sorted(breakdown.items(), key=lambda kv: -kv[1])[:5]
                )
                err_msg = (
                    f"Ingestion completed but {errors_total} of {xml_total} "
                    f"entities ({error_rate:.1%}) failed to write. Top: {top}. "
                    "Check journalctl owl-backend for the per-entity warnings."
                )
                background_task_storage.update_task(
                    task_id,
                    status=TaskStatus.FAILED.value,
                    completed_at=utcnow_iso(),
                    error=err_msg,
                    progress_total=xml_total,
                    progress_completed=result.get("total_nodes", 0),
                    progress_failed=errors_total,
                    stages=_build_stage_list(stage_runtime, _stage["key"], "failed"),
                )
                _log(f"Cellebrite ingestion DEGRADED: {err_msg}")
            else:
                background_task_storage.update_task(
                    task_id,
                    status=TaskStatus.COMPLETED.value,
                    completed_at=utcnow_iso(),
                    progress_total=xml_total,
                    progress_completed=result.get("total_nodes", 0),
                    progress_failed=errors_total,
                    stages=_build_stage_list(stage_runtime, _stage["key"], "completed"),
                )
                _log(
                    f"Cellebrite ingestion completed: "
                    f"{result.get('total_nodes', 0)} nodes, "
                    f"{errors_total} write errors"
                )
        else:
            # Prefer the human-readable `message` (e.g. the missing-
            # identifier precondition) over the terse `reason` code.
            fail_msg = result.get("message") or result.get("reason", "Unknown error")
            background_task_storage.update_task(
                task_id,
                status=TaskStatus.FAILED.value,
                completed_at=utcnow_iso(),
                error=fail_msg,
                stages=_build_stage_list(stage_runtime, _stage["key"], "failed"),
            )
            _log(f"Cellebrite ingestion failed: {fail_msg}")

        # Save case version after processing
        if result.get("status") == "success":
            try:
                from .case_storage import case_storage
                case = case_storage.get_case(case_id)
                if case:
                    case_name = case.get("name", case_id)
                    case_storage.save_case_version(
                        case_id=case_id,
                        case_name=case_name,
                        snapshots=[],
                        save_notes=f"Auto-save after Cellebrite report ingestion ({result.get('total_nodes', 0)} nodes).",
                        owner=owner,
                    )
            except Exception:
                pass  # Non-critical — graph data is already saved

        return result

    except Exception as e:
        error_msg = f"Cellebrite ingestion error: {str(e)}"
        _log(error_msg)
        background_task_storage.update_task(
            task_id,
            status=TaskStatus.FAILED.value,
            completed_at=utcnow_iso(),
            error=error_msg,
            stages=_build_stage_list(stage_runtime, _stage["key"], "failed"),
        )
        return {"status": "error", "reason": str(e)}
