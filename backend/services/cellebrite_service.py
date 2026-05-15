"""
Cellebrite report detection and processing service.

The ingestion pipeline writes phone-derived graph data to Neo4j and registers
resolved media files in Postgres evidence tables. It must not use the legacy
JSON-backed evidence stores.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, Optional
from uuid import UUID

from config import BASE_DIR


def _import_cellebrite():
    """Dynamically import the Cellebrite ingestion module."""
    scripts_dir = BASE_DIR / "ingestion" / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.append(str(scripts_dir))

    from cellebrite.ingestion import detect_cellebrite_xml, ingest_cellebrite_report

    return detect_cellebrite_xml, ingest_cellebrite_report


def check_cellebrite_report(folder_path: Path, case_id: Optional[str] = None) -> Dict:
    """
    Check if a folder contains a Cellebrite UFED report.

    Reads only the first 4KB of XML files. When a case_id is provided, also
    checks Neo4j for an existing PhoneReport collision so callers can offer a
    force re-ingest flow before mutating graph or evidence state.
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

    from cellebrite.parser import CellebriteXMLParser

    try:
        parser = CellebriteXMLParser(xml_path)
        report = parser.parse_header()

        manufacturer = report.device_info.manufacturer or ""
        detected_model = report.device_info.device_model or ""
        if manufacturer and detected_model:
            display_device = f"{manufacturer} {detected_model}"
        elif detected_model:
            display_device = detected_model
        else:
            display_device = "Unknown Device"

        report_key = (
            f"cellebrite-{report.case_info.case_number or 'unknown'}"
            f"-{report.case_info.evidence_number or 'unknown'}"
        )

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
                f"(evidence {existing.get('evidence_number') or '-'}). "
                "Re-ingest will replace the existing data."
            )

        return result
    except Exception as exc:
        return {
            "suitable": False,
            "message": f"Error parsing Cellebrite XML: {exc}",
        }


def process_cellebrite_report(
    folder_path: Path,
    case_id: str,
    task_id: str,
    owner: Optional[str] = None,
    log_callback: Optional[Callable[[str], None]] = None,
    force: bool = False,
    created_by_id: Optional[UUID] = None,
) -> Dict:
    """
    Process a Cellebrite UFED report folder synchronously.

    Background callers get their own DB sessions via get_background_session().
    Duplicate detection and force replacement are preserved, with graph data
    removed from Neo4j and file metadata removed from Postgres before re-ingest.
    """
    from .background_task_storage import TaskStatus, background_task_storage
    from .evidence_db_storage import EvidenceDBStorage
    from postgres.session import get_background_session

    case_uuid = UUID(case_id)

    background_task_storage.update_task(
        task_id,
        status=TaskStatus.RUNNING.value,
        started_at=datetime.now().isoformat(),
    )

    def _log(message: str) -> None:
        if log_callback:
            log_callback(message)
        with get_background_session() as db:
            EvidenceDBStorage.add_log(
                db,
                case_id=case_uuid,
                evidence_file_id=None,
                filename=None,
                level="info",
                message=message,
            )

    try:
        precheck = check_cellebrite_report(folder_path, case_id=case_id)
        if precheck.get("duplicate") and not force:
            existing = precheck.get("existing") or {}
            background_task_storage.update_task(
                task_id,
                status=TaskStatus.FAILED.value,
                completed_at=datetime.now().isoformat(),
                error="duplicate_phone_report",
            )
            _log(
                f"Refusing to ingest: a phone report with key "
                f"{existing.get('report_key')} already exists in this case. "
                "Pass force=true or delete the existing report to replace it."
            )
            return {
                "status": "error",
                "reason": "duplicate",
                "existing": existing,
            }

        if force and precheck.get("duplicate"):
            existing = precheck.get("existing") or {}
            existing_key = existing.get("report_key")
            if existing_key:
                from .neo4j_service import neo4j_service

                deleted = neo4j_service.delete_phone_report(case_id, existing_key)
                with get_background_session() as db:
                    evidence_deleted = EvidenceDBStorage.delete_by_cellebrite_report_key(
                        db,
                        case_uuid,
                        existing_key,
                    )
                _log(
                    f"Replaced existing phone report {existing_key}: "
                    f"removed {deleted.get('deleted_nodes', 0)} nodes "
                    f"+ {deleted.get('deleted_phone_report', 0)} PhoneReport node(s) "
                    f"+ {evidence_deleted} evidence row(s)."
                )

        _, ingest_cellebrite_report = _import_cellebrite()

        with get_background_session() as db:
            result = ingest_cellebrite_report(
                report_dir=folder_path,
                case_id=case_id,
                log_callback=_log,
                owner=owner,
                evidence_db=db,
                created_by_id=created_by_id,
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

        return result

    except Exception as exc:
        error_msg = f"Cellebrite ingestion error: {exc}"
        _log(error_msg)
        background_task_storage.update_task(
            task_id,
            status=TaskStatus.FAILED.value,
            completed_at=datetime.now().isoformat(),
            error=error_msg,
        )
        return {"status": "error", "reason": str(exc)}
