from __future__ import annotations

from pathlib import Path
from typing import Any

from .ingestion import detect_cellebrite_xml
from .parser import CellebriteXMLParser


def check_cellebrite_report(folder_path: Path, case_id: str | None = None) -> dict[str, Any]:
    """Inspect a staged Cellebrite UFED report folder without mutating state."""
    if not folder_path.exists() or not folder_path.is_dir():
        return {
            "suitable": False,
            "message": "Folder does not exist or is not a directory",
        }

    xml_path = detect_cellebrite_xml(folder_path)
    if not xml_path:
        return {
            "suitable": False,
            "message": "No Cellebrite UFED XML report found",
        }

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
            try:
                from services.neo4j_service import neo4j_service

                existing = neo4j_service.find_existing_phone_report(
                    case_id=case_id,
                    report_key=report_key,
                    imei=report.device_info.imei,
                    evidence_number=report.case_info.evidence_number,
                )
            except Exception:
                existing = None

        result: dict[str, Any] = {
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
