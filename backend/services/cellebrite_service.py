"""
Cellebrite Report Processing Service

Handles detection and background processing of Cellebrite UFED phone
extraction reports. Follows the same pattern as wiretap_service.py.
"""

import sys
from pathlib import Path
from typing import Dict, Optional, Callable
from datetime import datetime

from config import BASE_DIR


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


def check_cellebrite_report(folder_path: Path) -> Dict:
    """
    Check if a folder contains a Cellebrite UFED report.

    Reads only the first 4KB of XML files to check for the
    Cellebrite namespace — fast and non-destructive.

    Args:
        folder_path: Path to the folder to check

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

    try:
        parser = CellebriteXMLParser(xml_path)
        report = parser.parse_header()

        return {
            "suitable": True,
            "message": "Cellebrite UFED report detected",
            "xml_file": xml_path.name,
            "report_name": report.report_name,
            "report_version": report.report_version,
            "case_number": report.case_info.case_number,
            "evidence_number": report.case_info.evidence_number,
            "examiner": report.case_info.examiner,
            "crime_type": report.case_info.crime_type,
            "device_model": report.device_info.device_model,
            "imei": report.device_info.imei,
            "phone_numbers": report.device_info.msisdn,
            "node_count": report.node_count,
            "model_count": report.model_count,
        }
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
) -> Dict:
    """
    Process a Cellebrite UFED report folder (runs synchronously).

    Called from a background task. Updates the background task storage
    with progress and results.

    Args:
        folder_path: Path to the Cellebrite report folder
        case_id: Case ID for graph isolation
        task_id: Background task ID for progress tracking
        owner: Username for evidence ownership
        log_callback: Optional progress logging callback

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
        started_at=datetime.now().isoformat(),
    )

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
        _, ingest_cellebrite_report = _import_cellebrite()

        result = ingest_cellebrite_report(
            report_dir=folder_path,
            case_id=case_id,
            log_callback=_log,
            owner=owner,
            evidence_storage=evidence_storage,
        )

        if result.get("status") == "success":
            background_task_storage.update_task(
                task_id,
                status=TaskStatus.COMPLETED.value,
                completed_at=datetime.now().isoformat(),
                progress_total=result.get("xml_model_count", 0),
                progress_completed=result.get("total_nodes", 0),
            )
            _log(f"Cellebrite ingestion completed: {result.get('total_nodes', 0)} nodes created")
        else:
            background_task_storage.update_task(
                task_id,
                status=TaskStatus.FAILED.value,
                completed_at=datetime.now().isoformat(),
                error=result.get("reason", "Unknown error"),
            )
            _log(f"Cellebrite ingestion failed: {result.get('reason', 'Unknown error')}")

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
            completed_at=datetime.now().isoformat(),
            error=error_msg,
        )
        return {"status": "error", "reason": str(e)}
