"""
EXIF/Metadata Processor

Extracts EXIF metadata from images: GPS coordinates, camera info, timestamps.
Uses Pillow's built-in EXIF support (already a project dependency via image processing).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from services.triage_processors.base_processor import BaseTriageProcessor, ProcessingResult

logger = logging.getLogger(__name__)


def _safe_exif_value(val):
    """Convert EXIF value to a JSON-serializable type."""
    if isinstance(val, bytes):
        try:
            return val.decode("utf-8", errors="replace")
        except Exception:
            return str(val)
    if isinstance(val, tuple):
        return list(val)
    return val


def _dms_to_dd(dms, ref):
    """Convert DMS (degrees, minutes, seconds) GPS to decimal degrees."""
    try:
        if isinstance(dms, (list, tuple)) and len(dms) >= 3:
            d = float(dms[0])
            m = float(dms[1])
            s = float(dms[2])
            dd = d + m / 60 + s / 3600
            if ref in ("S", "W"):
                dd = -dd
            return round(dd, 6)
    except (ValueError, TypeError):
        pass
    return None


class ExifProcessor(BaseTriageProcessor):
    name = "exif_extractor"
    display_name = "EXIF/Metadata Extractor"
    description = "Extract EXIF metadata from images (GPS, camera, timestamps)"
    input_types = ["images"]
    output_types = ["exif_metadata"]
    requires_llm = False
    config_schema = {}

    def process_file(
        self,
        file_path: str,
        file_info: Dict[str, Any],
        config: Dict[str, Any],
    ) -> List[ProcessingResult]:
        try:
            from PIL import Image
            from PIL.ExifTags import TAGS, GPSTAGS
        except ImportError:
            return [ProcessingResult(
                source_path=file_path,
                artifact_type="exif_metadata",
                error="Pillow not installed",
            )]

        try:
            img = Image.open(file_path)
            exif_data = img._getexif()
            img.close()

            if not exif_data:
                return []  # No EXIF data

            metadata = {}
            gps_info = {}

            for tag_id, value in exif_data.items():
                tag_name = TAGS.get(tag_id, str(tag_id))

                if tag_name == "GPSInfo":
                    for gps_tag_id, gps_val in value.items():
                        gps_tag_name = GPSTAGS.get(gps_tag_id, str(gps_tag_id))
                        gps_info[gps_tag_name] = _safe_exif_value(gps_val)
                else:
                    metadata[tag_name] = _safe_exif_value(value)

            # Extract GPS coordinates
            lat = lon = None
            if "GPSLatitude" in gps_info and "GPSLatitudeRef" in gps_info:
                lat = _dms_to_dd(gps_info["GPSLatitude"], gps_info["GPSLatitudeRef"])
            if "GPSLongitude" in gps_info and "GPSLongitudeRef" in gps_info:
                lon = _dms_to_dd(gps_info["GPSLongitude"], gps_info["GPSLongitudeRef"])

            result_meta = {
                "camera_make": metadata.get("Make"),
                "camera_model": metadata.get("Model"),
                "date_taken": metadata.get("DateTimeOriginal") or metadata.get("DateTime"),
                "software": metadata.get("Software"),
                "image_width": metadata.get("ImageWidth") or metadata.get("ExifImageWidth"),
                "image_height": metadata.get("ImageLength") or metadata.get("ExifImageHeight"),
                "gps_latitude": lat,
                "gps_longitude": lon,
                "gps_altitude": gps_info.get("GPSAltitude"),
                "has_gps": lat is not None and lon is not None,
            }
            # Remove None values
            result_meta = {k: v for k, v in result_meta.items() if v is not None}

            if result_meta:
                content_parts = []
                if result_meta.get("camera_make"):
                    content_parts.append(f"Camera: {result_meta.get('camera_make')} {result_meta.get('camera_model', '')}")
                if result_meta.get("date_taken"):
                    content_parts.append(f"Date: {result_meta['date_taken']}")
                if result_meta.get("has_gps"):
                    content_parts.append(f"GPS: {lat}, {lon}")

                return [ProcessingResult(
                    source_path=file_path,
                    artifact_type="exif_metadata",
                    content="; ".join(content_parts) if content_parts else None,
                    metadata=result_meta,
                )]

            return []

        except Exception as e:
            return [ProcessingResult(
                source_path=file_path,
                artifact_type="exif_metadata",
                error=str(e),
            )]
