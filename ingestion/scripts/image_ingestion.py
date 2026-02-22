"""
Image Ingestion module - handles image file ingestion (.jpg, .png, .gif, .bmp, .webp, .tiff).

Uses image_processor.py for content extraction (Tesseract OCR or GPT-4 Vision),
then passes extracted text to core ingestion logic for entity extraction.
"""

from pathlib import Path
from typing import Dict, Optional, Callable

from image_processor import process_image
from ingestion import ingest_document
from logging_utils import log_progress, log_error, log_warning


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff", ".tif"}


def ingest_image_file(
    path: Path,
    case_id: str,
    log_callback: Optional[Callable[[str], None]] = None,
    profile_name: Optional[str] = None,
    image_provider: Optional[str] = None,
) -> Dict:
    """
    Ingest a single image file into the knowledge graph.

    Extracts text/descriptions using either Tesseract OCR or GPT-4 Vision,
    then passes the content through the standard ingestion pipeline.

    Args:
        path: Path to the image file
        case_id: REQUIRED - The case ID to associate with all created entities/relationships
        log_callback: Optional callback function(message: str) to log progress messages
        profile_name: Name of the profile to use (e.g., 'fraud', 'generic')
        image_provider: Override image provider ("tesseract" or "openai")

    Returns:
        Ingestion result dict

    Raises:
        ValueError: If case_id is not provided
    """
    if not case_id:
        raise ValueError("case_id is required for image file ingestion")

    doc_name = path.name

    log_progress(f"Processing image file: {path}", log_callback)

    try:
        result = process_image(
            image_path=path,
            provider=image_provider,
            log_callback=log_callback,
            doc_name=doc_name,
        )
    except Exception as e:
        log_error(f"Failed to process image: {e}", log_callback)
        return {"status": "error", "reason": str(e), "file": str(path)}

    text = result.get("text", "")
    if not text.strip():
        log_warning(f"No content extracted from image, skipping: {path}", log_callback)
        return {"status": "skipped", "reason": "no_content", "file": str(path)}

    log_progress(f"Image content extracted: {len(text)} characters via {result['provider']}", log_callback)

    # Build metadata from image processor results
    metadata = result.get("metadata", {})
    doc_metadata = {
        "filename": path.name,
        "full_path": str(path.resolve()),
        "source_type": "image",
        "image_provider": result["provider"],
    }
    # Include image-specific metadata
    if metadata.get("width"):
        doc_metadata["image_width"] = metadata["width"]
    if metadata.get("height"):
        doc_metadata["image_height"] = metadata["height"]
    if metadata.get("format"):
        doc_metadata["image_format"] = metadata["format"]
    if metadata.get("gps_latitude"):
        doc_metadata["gps_latitude"] = metadata["gps_latitude"]
    if metadata.get("gps_longitude"):
        doc_metadata["gps_longitude"] = metadata["gps_longitude"]
    if metadata.get("date_taken"):
        doc_metadata["date_taken"] = metadata["date_taken"]

    return ingest_document(
        text=text,
        doc_name=doc_name,
        case_id=case_id,
        doc_metadata=doc_metadata,
        log_callback=log_callback,
        profile_name=profile_name,
    )
