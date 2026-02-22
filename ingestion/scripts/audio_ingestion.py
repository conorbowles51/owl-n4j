"""
Audio Ingestion module - handles standalone audio file ingestion (.mp3, .wav, .ogg, .flac, .aac, .m4a, .wma).

Uses local Whisper for transcription (reusing audio_processor.py),
then passes transcription text to core ingestion logic for entity extraction.

This is SEPARATE from the wiretap folder processing pipeline.
Wiretap folder processing remains in audio_processor.py and folder_processor.py.
"""

from pathlib import Path
from typing import Dict, Optional, Callable

from audio_processor import load_whisper_model, transcribe_audio, WHISPER_AVAILABLE
from ingestion import ingest_document
from logging_utils import log_progress, log_error, log_warning
from config import WHISPER_MODEL_SIZE, AUDIO_LANGUAGE


AUDIO_EXTENSIONS = {".mp3", ".wav", ".ogg", ".flac", ".aac", ".m4a", ".wma"}

# Module-level whisper model cache (loaded once, reused across files)
_whisper_model = None
_whisper_model_size = None


def _get_whisper_model(model_size: str = None):
    """Get or load the Whisper model (cached at module level)."""
    global _whisper_model, _whisper_model_size
    size = model_size or WHISPER_MODEL_SIZE
    if _whisper_model is None or _whisper_model_size != size:
        _whisper_model = load_whisper_model(size)
        _whisper_model_size = size
    return _whisper_model


def ingest_audio_file(
    path: Path,
    case_id: str,
    log_callback: Optional[Callable[[str], None]] = None,
    profile_name: Optional[str] = None,
    whisper_model_size: Optional[str] = None,
    language: Optional[str] = None,
) -> Dict:
    """
    Ingest a single audio file into the knowledge graph.

    Transcribes the audio using Whisper, then passes the transcription
    text through the standard ingestion pipeline for entity extraction.

    Args:
        path: Path to the audio file
        case_id: REQUIRED - The case ID to associate with all created entities/relationships
        log_callback: Optional callback function(message: str) to log progress messages
        profile_name: Name of the profile to use (e.g., 'fraud', 'generic')
        whisper_model_size: Whisper model size override (tiny, base, small, medium, large)
        language: Language code for transcription (None = auto-detect)

    Returns:
        Ingestion result dict

    Raises:
        ValueError: If case_id is not provided
    """
    if not case_id:
        raise ValueError("case_id is required for audio file ingestion")

    if not WHISPER_AVAILABLE:
        log_error("Whisper not installed. Install with: pip install openai-whisper", log_callback)
        return {"status": "error", "reason": "whisper_not_installed", "file": str(path)}

    doc_name = path.name
    log_progress(f"Transcribing audio file: {path}", log_callback)

    try:
        model = _get_whisper_model(whisper_model_size)
        lang = language or AUDIO_LANGUAGE

        # Use auto-detect if no language specified
        transcribe_lang = lang if lang else None

        log_progress(f"Using Whisper model: {whisper_model_size or WHISPER_MODEL_SIZE}, language: {transcribe_lang or 'auto-detect'}", log_callback)

        transcription = transcribe_audio(
            audio_path=path,
            model=model,
            language=transcribe_lang if transcribe_lang else "en",
            task="transcribe",
        )
    except Exception as e:
        log_error(f"Failed to transcribe audio: {e}", log_callback)
        return {"status": "error", "reason": str(e), "file": str(path)}

    if not transcription or not transcription.strip():
        log_warning(f"No speech detected in audio file, skipping: {path}", log_callback)
        return {"status": "skipped", "reason": "no_speech", "file": str(path)}

    log_progress(f"Transcription complete: {len(transcription)} characters", log_callback)

    # Wrap transcription with structured context
    text = f"=== AUDIO TRANSCRIPTION ===\n"
    text += f"Source file: {path.name}\n"
    text += f"Transcription model: whisper-{whisper_model_size or WHISPER_MODEL_SIZE}\n"
    text += f"Language: {lang or 'auto-detected'}\n\n"
    text += f"=== TRANSCRIPTION ===\n{transcription}\n"

    doc_metadata = {
        "filename": path.name,
        "full_path": str(path.resolve()),
        "source_type": "audio",
        "transcription_model": f"whisper-{whisper_model_size or WHISPER_MODEL_SIZE}",
        "language": lang if lang else "auto",
    }

    return ingest_document(
        text=text,
        doc_name=doc_name,
        case_id=case_id,
        doc_metadata=doc_metadata,
        log_callback=log_callback,
        profile_name=profile_name,
    )
