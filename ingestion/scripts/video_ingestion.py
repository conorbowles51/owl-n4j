"""
Video Ingestion module - handles video file ingestion (.mp4, .avi, .mov, .wmv, .flv, .mkv, .webm).

Uses video_processor.py for content extraction (ffmpeg + Whisper + GPT-4 Vision),
then passes combined text to core ingestion logic for entity extraction.
"""

from pathlib import Path
from typing import Dict, Optional, Callable

from video_processor import process_video
from ingestion import ingest_document
from logging_utils import log_progress, log_error, log_warning


VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov", ".wmv", ".flv", ".mkv", ".webm"}


def ingest_video_file(
    path: Path,
    case_id: str,
    log_callback: Optional[Callable[[str], None]] = None,
    profile_name: Optional[str] = None,
) -> Dict:
    """
    Ingest a single video file into the knowledge graph.

    Extracts audio transcription and key frame descriptions,
    then passes the combined content through the standard ingestion pipeline.

    Args:
        path: Path to the video file
        case_id: REQUIRED - The case ID to associate with all created entities/relationships
        log_callback: Optional callback function(message: str) to log progress messages
        profile_name: Name of the profile to use (e.g., 'fraud', 'generic')

    Returns:
        Ingestion result dict

    Raises:
        ValueError: If case_id is not provided
    """
    if not case_id:
        raise ValueError("case_id is required for video file ingestion")

    doc_name = path.name

    log_progress(f"Processing video file: {path}", log_callback)

    try:
        result = process_video(
            video_path=path,
            log_callback=log_callback,
            doc_name=doc_name,
        )
    except Exception as e:
        log_error(f"Failed to process video: {e}", log_callback)
        return {"status": "error", "reason": str(e), "file": str(path)}

    text = result.get("text", "")
    if not text.strip():
        log_warning(f"No content extracted from video, skipping: {path}", log_callback)
        return {"status": "skipped", "reason": "no_content", "file": str(path)}

    log_progress(f"Video content extracted: {len(text)} characters", log_callback)

    # Build metadata from video processor results
    metadata = result.get("metadata", {})
    doc_metadata = {
        "filename": path.name,
        "full_path": str(path.resolve()),
        "source_type": "video",
    }
    # Include video-specific metadata
    if metadata.get("duration_seconds"):
        doc_metadata["duration_seconds"] = metadata["duration_seconds"]
    if metadata.get("duration_str"):
        doc_metadata["duration_str"] = metadata["duration_str"]
    if metadata.get("width"):
        doc_metadata["video_width"] = metadata["width"]
    if metadata.get("height"):
        doc_metadata["video_height"] = metadata["height"]
    if metadata.get("video_codec"):
        doc_metadata["video_codec"] = metadata["video_codec"]
    if metadata.get("fps"):
        doc_metadata["video_fps"] = metadata["fps"]
    if metadata.get("has_audio") is not None:
        doc_metadata["has_audio"] = metadata["has_audio"]

    # Track what was extracted
    doc_metadata["has_transcription"] = bool(result.get("transcription", "").strip())
    doc_metadata["frame_descriptions_count"] = len(result.get("frame_descriptions", []))

    return ingest_document(
        text=text,
        doc_name=doc_name,
        case_id=case_id,
        doc_metadata=doc_metadata,
        log_callback=log_callback,
        profile_name=profile_name,
    )
