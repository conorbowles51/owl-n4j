import base64
import asyncio
import csv
import io
import json
import logging
import os
import re
import subprocess
import tempfile
import zipfile
from email import policy
from email.parser import BytesParser
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import docx
import openpyxl

from app.config import settings
from app.pipeline.pdf_extraction import PdfProgressCallback, extract_pdf
from app.services.openai_client import (
    AudioProgressCallback,
    AudioTranscriptionRequestError,
    AudioTranscriptionResult,
    chat_completion,
    transcribe_audio,
)
from app.utils.text_sanitize import sanitize_json, sanitize_text

logger = logging.getLogger(__name__)

AUDIO_EXTENSIONS = {
    ".mp3", ".m4a", ".wav", ".mpeg", ".mpga", ".ogg", ".flac",
}
VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv", ".webm"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tiff", ".tif", ".bmp", ".gif"}
PLAIN_TEXT_EXTENSIONS = {
    ".txt",
    ".log",
    ".json",
    ".xml",
    ".yaml",
    ".yml",
    ".sri",
}
MAX_WHISPER_SIZE = 25 * 1024 * 1024  # 25 MB
MIN_AUDIO_TRANSCRIPTION_SEGMENT_SECONDS = 60
TRANSCRIPTION_PROMPT_CONTEXT_CHARS = 1200


@dataclass
class ExtractedDocument:
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)
    tables: list[str] = field(default_factory=list)


def _validate_office_archive(file_path: str) -> None:
    try:
        with zipfile.ZipFile(file_path) as archive:
            entries = archive.infolist()
            if len(entries) > settings.max_office_archive_entries:
                raise ValueError(
                    f"Office document contains {len(entries)} archive entries; the configured "
                    f"limit is {settings.max_office_archive_entries}"
                )
            uncompressed_size = sum(entry.file_size for entry in entries)
            if uncompressed_size > settings.max_office_uncompressed_bytes:
                raise ValueError(
                    f"Office document expands to {uncompressed_size} bytes; the configured "
                    f"limit is {settings.max_office_uncompressed_bytes} bytes"
                )
            if any(entry.flag_bits & 0x1 for entry in entries):
                raise ValueError("Encrypted Office documents are not supported")
    except zipfile.BadZipFile as exc:
        raise ValueError("Office document is not a valid ZIP-based file") from exc


def _validate_text_input_size(file_path: str) -> None:
    file_size = os.path.getsize(file_path)
    if file_size > settings.max_text_input_bytes:
        raise ValueError(
            f"Text-like input is {file_size} bytes; the configured limit is "
            f"{settings.max_text_input_bytes} bytes"
        )


# ---------------------------------------------------------------------------
# DOCX
# ---------------------------------------------------------------------------

def _extract_docx(file_path: str) -> ExtractedDocument:
    doc = docx.Document(file_path)
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]

    tables: list[str] = []
    for table in doc.tables:
        rows: list[str] = []
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells]
            rows.append(" | ".join(cells))
        if rows:
            tables.append("\n".join(rows))

    return ExtractedDocument(
        text="\n\n".join(paragraphs),
        metadata={
            "file_type": "docx",
            "paragraph_count": len(paragraphs),
            "table_count": len(tables),
        },
        tables=tables,
    )


# ---------------------------------------------------------------------------
# XLSX / XLS
# ---------------------------------------------------------------------------

def _extract_xlsx(file_path: str) -> ExtractedDocument:
    wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
    tables: list[str] = []
    extracted_characters = 0

    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        rows: list[str] = []
        for row in ws.iter_rows(values_only=True):
            cells = [str(c) if c is not None else "" for c in row]
            if any(c.strip() for c in cells):
                rendered_row = " | ".join(cells)
                extracted_characters += len(rendered_row) + 1
                if extracted_characters > settings.max_extracted_characters:
                    wb.close()
                    raise ValueError(
                        "Spreadsheet extracted content exceeds the configured character limit"
                    )
                rows.append(rendered_row)
        if rows:
            tables.append(f"[Sheet: {sheet_name}]\n" + "\n".join(rows))

    sheet_count = len(wb.sheetnames)
    wb.close()

    return ExtractedDocument(
        text="",
        metadata={"file_type": "xlsx", "sheet_count": sheet_count},
        tables=tables,
    )


# ---------------------------------------------------------------------------
# CSV
# ---------------------------------------------------------------------------

def _extract_csv(file_path: str) -> ExtractedDocument:
    path = Path(file_path)
    try:
        raw = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raw = path.read_text(encoding="latin-1")

    reader = csv.DictReader(io.StringIO(raw))
    rows_data: list[dict[str, str]] = []
    extracted_characters = 0
    for row in reader:
        extracted_characters += sum(len(str(key)) + len(str(value)) for key, value in row.items())
        if extracted_characters > settings.max_extracted_characters:
            raise ValueError("CSV extracted content exceeds the configured character limit")
        rows_data.append(row)

    text = json.dumps(rows_data, indent=2, default=str) if rows_data else ""

    return ExtractedDocument(
        text="",
        metadata={
            "file_type": "csv",
            "row_count": len(rows_data),
            "columns": list(rows_data[0].keys()) if rows_data else [],
        },
        tables=[text] if text else [],
    )


# ---------------------------------------------------------------------------
# HTML
# ---------------------------------------------------------------------------

def _extract_html(file_path: str) -> ExtractedDocument:
    path = Path(file_path)
    try:
        raw = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raw = path.read_text(encoding="latin-1")

    try:
        from lxml import html as lxml_html

        doc = lxml_html.fromstring(raw)
        # Remove script and style elements
        for el in doc.iter("script", "style"):
            el.drop_tree()
        text = doc.text_content()
    except Exception:
        # Fallback: strip tags with regex
        text = re.sub(r"<script[^>]*>[\s\S]*?</script>", "", raw, flags=re.IGNORECASE)
        text = re.sub(r"<style[^>]*>[\s\S]*?</style>", "", text, flags=re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"&[a-zA-Z]+;", " ", text)

    # Normalise whitespace
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()

    return ExtractedDocument(
        text=text,
        metadata={"file_type": "html"},
    )


# ---------------------------------------------------------------------------
# Markdown
# ---------------------------------------------------------------------------

def _extract_markdown(file_path: str) -> ExtractedDocument:
    path = Path(file_path)
    try:
        raw = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raw = path.read_text(encoding="latin-1")

    try:
        from markdown_it import MarkdownIt

        md = MarkdownIt()
        html = md.render(raw)
        # Strip HTML tags from rendered output
        text = re.sub(r"<[^>]+>", " ", html)
    except Exception:
        # Fallback: strip markdown syntax with regex
        text = raw
        text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)  # headings
        text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)  # bold
        text = re.sub(r"\*(.+?)\*", r"\1", text)  # italic
        text = re.sub(r"`{1,3}[^`]*`{1,3}", "", text)  # inline/block code
        text = re.sub(r"!?\[([^\]]*)\]\([^)]+\)", r"\1", text)  # links/images
        text = re.sub(r"^[-*+]\s+", "", text, flags=re.MULTILINE)  # list markers
        text = re.sub(r"^>\s+", "", text, flags=re.MULTILINE)  # blockquotes

    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()

    return ExtractedDocument(
        text=text,
        metadata={"file_type": "markdown"},
    )


# ---------------------------------------------------------------------------
# RFC 5322 email
# ---------------------------------------------------------------------------

def _extract_eml(file_path: str) -> ExtractedDocument:
    with open(file_path, "rb") as source:
        message = BytesParser(policy=policy.default).parse(source)

    header_names = ("From", "To", "Cc", "Bcc", "Subject", "Date", "Message-ID")
    headers = [
        f"{name}: {message.get(name)}"
        for name in header_names
        if message.get(name)
    ]
    plain_parts: list[str] = []
    html_parts: list[str] = []
    attachment_names: list[str] = []

    for part in message.walk():
        if part.is_multipart():
            continue
        if part.get_content_disposition() == "attachment":
            if part.get_filename():
                attachment_names.append(str(part.get_filename()))
            continue
        content_type = part.get_content_type()
        if content_type not in {"text/plain", "text/html"}:
            continue
        try:
            content = str(part.get_content() or "").strip()
        except (LookupError, UnicodeError):
            payload = part.get_payload(decode=True) or b""
            content = payload.decode("utf-8", errors="replace").strip()
        if not content:
            continue
        if content_type == "text/plain":
            plain_parts.append(content)
        else:
            try:
                from lxml import html as lxml_html

                content = lxml_html.fromstring(content).text_content()
            except Exception:
                content = re.sub(r"<[^>]+>", " ", content)
            html_parts.append(re.sub(r"[ \t]+", " ", content).strip())

    body_parts = plain_parts or html_parts
    text = "\n".join(headers)
    if body_parts:
        text += "\n\n" + "\n\n".join(body_parts)
    return ExtractedDocument(
        text=text.strip(),
        metadata={
            "file_type": "eml",
            "attachment_count": len(attachment_names),
            "attachment_names": attachment_names,
        },
    )


# ---------------------------------------------------------------------------
# Audio
# ---------------------------------------------------------------------------

class AudioTranscriptionError(RuntimeError):
    """Raised when an audio segment cannot be transcribed."""


def _configured_audio_segment_seconds() -> int:
    return max(
        MIN_AUDIO_TRANSCRIPTION_SEGMENT_SECONDS,
        int(settings.audio_transcription_segment_seconds or 240),
    )


def _configured_audio_max_single_seconds() -> int:
    return max(
        MIN_AUDIO_TRANSCRIPTION_SEGMENT_SECONDS,
        int(settings.audio_transcription_max_single_seconds or 240),
    )


def _probe_media_duration_seconds(file_path: str) -> float | None:
    """Return media duration using ffprobe, or None when probing fails."""
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "quiet",
                "-print_format",
                "json",
                "-show_format",
                file_path,
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0 or not result.stdout:
            return None
        info = json.loads(result.stdout)
        duration = (info.get("format") or {}).get("duration")
        if duration is None:
            return None
        parsed = float(duration)
        return parsed if parsed > 0 else None
    except Exception as exc:
        logger.warning("Audio duration probe failed for %s: %s", file_path, exc)
        return None


def _split_audio_segments(
    file_path: str,
    output_dir: str,
    segment_seconds: int,
) -> list[Path]:
    """Split audio into normalized MP3 chunks for transcription."""
    segment_pattern = os.path.join(output_dir, "segment_%03d.mp3")
    try:
        subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                file_path,
                "-map",
                "0:a:0",
                "-vn",
                "-ac",
                "1",
                "-ar",
                "16000",
                "-c:a",
                "libmp3lame",
                "-b:a",
                "64k",
                "-f",
                "segment",
                "-segment_time",
                str(segment_seconds),
                "-reset_timestamps",
                "1",
                segment_pattern,
            ],
            check=True,
            capture_output=True,
            timeout=1800,
        )
    except subprocess.CalledProcessError as exc:
        stderr = (
            exc.stderr.decode("utf-8", errors="replace")
            if isinstance(exc.stderr, bytes)
            else (exc.stderr or "")
        )
        raise AudioTranscriptionError(
            f"Audio segmentation failed: {stderr.strip() or exc}"
        ) from exc

    segments = sorted(Path(output_dir).glob("segment_*.mp3"))
    if not segments:
        raise AudioTranscriptionError("Audio segmentation produced no chunks")
    return segments


def _is_input_too_large_error(exc: Exception) -> bool:
    candidates: list[str] = []
    for attr in ("code", "message", "param"):
        value = getattr(exc, attr, None)
        if value:
            candidates.append(str(value))
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        candidates.extend(str(value) for value in body.values() if value is not None)
    elif body:
        candidates.append(str(body))
    candidates.append(str(exc))
    text = " ".join(candidates).lower()
    return (
        "input_too_large" in text
        or "too large for this model" in text
        or (
            "audio duration" in text
            and "longer than" in text
            and "maximum for this model" in text
        )
    )


def _build_transcription_prompt(previous_transcript: str | None) -> str | None:
    if not previous_transcript:
        return None
    tail = previous_transcript.strip()[-TRANSCRIPTION_PROMPT_CONTEXT_CHARS:]
    if not tail:
        return None
    return (
        "The previous audio segment ended with this transcript. Continue "
        "transcribing the same conversation, preserving names, punctuation, "
        "and context.\n\nPrevious segment ending:\n"
        f"{tail}"
    )


def _normalize_transcription_result(
    result: AudioTranscriptionResult | str,
) -> tuple[str, list[dict[str, Any]], str]:
    """Accept the structured client result while keeping test/provider adapters simple."""
    if isinstance(result, str):
        return result.strip(), [], settings.openai_transcription_model
    return result.text.strip(), list(result.segments), result.model


def _build_speaker_reference_data_urls(
    audio_path: str,
    transcript_segments: list[dict[str, Any]],
    *,
    time_offset_seconds: float,
    existing_speakers: set[str],
) -> dict[str, str]:
    """Extract one 2-10 second voice sample for each newly observed speaker."""
    best_segments: dict[str, tuple[float, float]] = {}
    for segment in transcript_segments:
        speaker = str(segment.get("speaker") or "").strip()
        if not speaker or speaker == "unknown" or speaker in existing_speakers:
            continue
        try:
            start = float(segment.get("start") or 0.0) - time_offset_seconds
            end = float(segment.get("end") or 0.0) - time_offset_seconds
        except (TypeError, ValueError):
            continue
        duration = end - start
        if duration < 2.0:
            continue
        previous = best_segments.get(speaker)
        if previous is None or duration > previous[1]:
            best_segments[speaker] = (max(0.0, start), duration)

    references: dict[str, str] = {}
    remaining_slots = max(0, 4 - len(existing_speakers))
    for speaker, (start, duration) in list(best_segments.items())[:remaining_slots]:
        result = subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-ss",
                str(round(start, 3)),
                "-t",
                str(round(min(10.0, duration), 3)),
                "-i",
                audio_path,
                "-map",
                "0:a:0",
                "-vn",
                "-ac",
                "1",
                "-ar",
                "16000",
                "-c:a",
                "libmp3lame",
                "-b:a",
                "64k",
                "-f",
                "mp3",
                "pipe:1",
            ],
            capture_output=True,
            timeout=60,
        )
        if result.returncode != 0 or not result.stdout:
            logger.warning("Unable to build voice reference for speaker %s", speaker)
            continue
        encoded = base64.b64encode(result.stdout).decode("ascii")
        references[speaker] = f"data:audio/mpeg;base64,{encoded}"
    return references


async def _transcribe_audio_segments(
    segments: list[Path],
    segment_seconds: int,
    transcripts: list[str],
    transcript_segments: list[dict[str, Any]],
    stats: dict[str, int],
    *,
    start_offset_seconds: float = 0.0,
    progress_total_seconds: float | None = None,
    progress_callback: AudioProgressCallback | None = None,
    speaker_references: dict[str, str] | None = None,
) -> None:
    total_segments = len(segments)
    current_offset = start_offset_seconds
    stable_speaker_references = (
        speaker_references if speaker_references is not None else {}
    )
    for index, segment in enumerate(segments, start=1):
        prompt = _build_transcription_prompt(transcripts[-1] if transcripts else None)
        segment_duration = _probe_media_duration_seconds(str(segment)) or float(segment_seconds)
        diarization_enabled = (
            settings.openai_transcription_model == "gpt-4o-transcribe-diarize"
        )
        speaker_id_prefix = ""
        if (
            diarization_enabled
            and not stable_speaker_references
            and current_offset > 0
        ):
            # If no usable voice sample was found, do not pretend that a later
            # chunk's anonymous A/B labels identify the same people.
            speaker_id_prefix = f"chunk_{round(current_offset * 1000)}:"
        try:
            result = await transcribe_audio(
                str(segment),
                prompt=prompt,
                time_offset_seconds=current_offset,
                segment_id_prefix=f"chunk_{round(current_offset * 1000)}_",
                speaker_id_prefix=speaker_id_prefix,
                duration_seconds=segment_duration,
                progress_total_seconds=progress_total_seconds,
                progress_callback=progress_callback,
                known_speaker_references=stable_speaker_references or None,
            )
            stats["segment_count"] = stats.get("segment_count", 0) + 1
        except Exception as exc:
            if (
                _is_input_too_large_error(exc)
                and segment_seconds > MIN_AUDIO_TRANSCRIPTION_SEGMENT_SECONDS
            ):
                retry_seconds = max(
                    MIN_AUDIO_TRANSCRIPTION_SEGMENT_SECONDS,
                    segment_seconds // 2,
                )
                logger.warning(
                    "Audio segment %s/%s was too large for transcription; retrying with %ss chunks",
                    index,
                    total_segments,
                    retry_seconds,
                )
                with tempfile.TemporaryDirectory() as retry_dir:
                    retry_segments = _split_audio_segments(
                        str(segment),
                        retry_dir,
                        retry_seconds,
                    )
                    try:
                        await _transcribe_audio_segments(
                            retry_segments,
                            retry_seconds,
                            transcripts,
                            transcript_segments,
                            stats,
                            start_offset_seconds=current_offset,
                            progress_total_seconds=progress_total_seconds,
                            progress_callback=progress_callback,
                            speaker_references=stable_speaker_references,
                        )
                    except Exception as retry_exc:
                        raise AudioTranscriptionError(
                            "Audio transcription failed on segment "
                            f"{index}/{total_segments} after retrying with "
                            f"{retry_seconds}s chunks: {retry_exc}"
                        ) from retry_exc
                current_offset += segment_duration
                continue

            raise AudioTranscriptionError(
                f"Audio transcription failed on segment {index}/{total_segments}: {exc}"
            ) from exc

        transcript, timed_segments, _ = _normalize_transcription_result(result)
        if transcript:
            transcripts.append(transcript)
        transcript_segments.extend(timed_segments)
        if diarization_enabled and isinstance(result, AudioTranscriptionResult):
            stable_speaker_references.update(
                _build_speaker_reference_data_urls(
                    str(segment),
                    timed_segments,
                    time_offset_seconds=current_offset,
                    existing_speakers=set(stable_speaker_references),
                )
            )
            stats["speaker_reference_count"] = len(stable_speaker_references)
        current_offset += segment_duration


async def _extract_audio(
    file_path: str,
    progress_callback: AudioProgressCallback | None = None,
) -> ExtractedDocument:
    file_size = os.path.getsize(file_path)
    duration_seconds = _probe_media_duration_seconds(file_path)
    segment_seconds = _configured_audio_segment_seconds()
    max_single_seconds = _configured_audio_max_single_seconds()
    metadata: dict[str, Any] = {
        "file_type": "audio",
        "file_size": file_size,
    }
    if duration_seconds is not None:
        metadata["duration_seconds"] = duration_seconds

    # Server-side VAD chooses conversational boundaries inside a transcription
    # request, but the request itself is still subject to the model's duration
    # limit. Apply the local duration cap to every transcription model.
    should_segment = file_size > MAX_WHISPER_SIZE or (
        duration_seconds is not None and duration_seconds > max_single_seconds
    )
    if not should_segment:
        try:
            result = await transcribe_audio(
                file_path,
                time_offset_seconds=0.0,
                segment_id_prefix="chunk_0_",
                duration_seconds=duration_seconds,
                progress_total_seconds=duration_seconds,
                progress_callback=progress_callback,
            )
            transcript, transcript_segments, transcription_model = (
                _normalize_transcription_result(result)
            )
            metadata["segment_count"] = 1
            metadata["transcription"] = transcript
            metadata["transcription_segments"] = transcript_segments
            metadata["transcription_model"] = transcription_model
            return ExtractedDocument(text=transcript, metadata=metadata)
        except Exception as exc:
            timed_out_before_stream = (
                isinstance(exc, AudioTranscriptionRequestError)
                and exc.retryable
                and not exc.stream_started
            )
            if not _is_input_too_large_error(exc) and not timed_out_before_stream:
                raise
            if timed_out_before_stream:
                metadata["transcription_fallback"] = (
                    "local_chunks_after_stream_timeout"
                )
                logger.warning(
                    "Diarized transcription timed out before its first event; "
                    "falling back to %ss chunks",
                    segment_seconds,
                )
            else:
                metadata["transcription_fallback"] = (
                    "local_chunks_after_input_too_large"
                )
                logger.warning(
                    "Single audio transcription request was too large; "
                    "falling back to %ss chunks",
                    segment_seconds,
                )

    stats = {"segment_count": 0}
    transcripts: list[str] = []
    transcript_segments: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory() as segments_dir:
        segments = _split_audio_segments(file_path, segments_dir, segment_seconds)
        await _transcribe_audio_segments(
            segments,
            segment_seconds,
            transcripts,
            transcript_segments,
            stats,
            progress_total_seconds=duration_seconds,
            progress_callback=progress_callback,
        )

    transcription = "\n\n".join(transcripts)
    metadata["segment_count"] = stats["segment_count"]
    metadata["segment_seconds"] = segment_seconds
    metadata["transcription"] = transcription
    metadata["transcription_segments"] = transcript_segments
    metadata["transcription_model"] = settings.openai_transcription_model
    if settings.openai_transcription_model == "gpt-4o-transcribe-diarize":
        metadata["speaker_reconciliation"] = (
            "known_voice_references"
            if stats.get("speaker_reference_count", 0)
            else "chunk_scoped"
        )
    return ExtractedDocument(
        text=transcription,
        metadata=metadata,
    )


# ---------------------------------------------------------------------------
# Image (Tesseract OCR / OpenAI Vision)
# ---------------------------------------------------------------------------

def _extract_image_metadata(file_path: str) -> dict[str, Any]:
    """Extract EXIF metadata from an image file."""
    metadata: dict[str, Any] = {"file_type": "image"}
    try:
        from PIL import Image
        from PIL.ExifTags import TAGS

        img = Image.open(file_path)
        metadata["width"] = img.width
        metadata["height"] = img.height
        metadata["format"] = img.format

        exif_data = img.getexif()
        if exif_data:
            for tag_id, value in exif_data.items():
                tag_name = TAGS.get(tag_id, str(tag_id))
                if tag_name in ("DateTime", "DateTimeOriginal", "Make", "Model"):
                    metadata[tag_name] = str(value)
        img.close()
    except Exception:
        pass
    return metadata


def _extract_text_tesseract(file_path: str) -> str:
    """OCR an image using Tesseract."""
    import pytesseract
    from PIL import Image

    img = Image.open(file_path)
    text = pytesseract.image_to_string(
        img,
        lang=settings.tesseract_lang,
        timeout=settings.pdf_ocr_page_timeout_seconds,
    )
    img.close()
    return text.strip()


async def _describe_image_vision(file_path: str, file_name: str) -> str:
    """Describe an image using OpenAI Vision API."""
    with open(file_path, "rb") as f:
        encoded = base64.b64encode(f.read()).decode("utf-8")

    ext = Path(file_path).suffix.lower()
    mime_map = {
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".png": "image/png", ".gif": "image/gif",
        ".tiff": "image/tiff", ".tif": "image/tiff",
        ".bmp": "image/bmp",
    }
    mime = mime_map.get(ext, "image/jpeg")

    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": (
                        f"This image is from a file called '{file_name}' uploaded as evidence "
                        "in an investigation. Describe everything you see in detail: people, "
                        "objects, text, locations, documents, licence plates, timestamps, "
                        "and any other relevant details. If there is text in the image, "
                        "transcribe it exactly."
                    ),
                },
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime};base64,{encoded}"},
                },
            ],
        }
    ]

    return await chat_completion(
        messages=messages,
        model=settings.openai_vision_model,
    )


async def _extract_image(file_path: str, file_name: str) -> ExtractedDocument:
    file_size = os.path.getsize(file_path)
    if file_size > settings.max_image_file_bytes:
        raise ValueError(
            f"Image is {file_size} bytes; the configured limit is "
            f"{settings.max_image_file_bytes} bytes"
        )
    metadata = await asyncio.to_thread(_extract_image_metadata, file_path)
    pixel_count = int(metadata.get("width", 0) or 0) * int(metadata.get("height", 0) or 0)
    if pixel_count > settings.max_image_pixels:
        raise ValueError(
            f"Image has {pixel_count} pixels; the configured limit is "
            f"{settings.max_image_pixels} pixels"
        )
    provider = settings.image_provider.lower()

    if provider == "openai":
        text = await _describe_image_vision(file_path, file_name)
        metadata["image_provider"] = "openai_vision"
    elif provider == "tesseract":
        text = await asyncio.to_thread(_extract_text_tesseract, file_path)
        metadata["image_provider"] = "tesseract"
    else:
        raise ValueError(
            f"Unsupported IMAGE_PROVIDER={settings.image_provider!r}; expected 'tesseract' or 'openai'"
        )

    return ExtractedDocument(text=text, metadata=metadata)


# ---------------------------------------------------------------------------
# Video (FFmpeg frame extraction + Vision + Whisper)
# ---------------------------------------------------------------------------

def _get_video_metadata(file_path: str) -> dict[str, Any]:
    """Extract video metadata using ffprobe."""
    metadata: dict[str, Any] = {"file_type": "video"}
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "quiet", "-print_format", "json",
                "-show_format", "-show_streams", file_path,
            ],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode == 0:
            info = json.loads(result.stdout)
            fmt = info.get("format", {})
            metadata["duration_seconds"] = float(fmt.get("duration", 0))
            metadata["format_name"] = fmt.get("format_name", "")
            for stream in info.get("streams", []):
                if stream.get("codec_type") == "video":
                    metadata["width"] = stream.get("width")
                    metadata["height"] = stream.get("height")
                    metadata["video_codec"] = stream.get("codec_name")
                elif stream.get("codec_type") == "audio":
                    metadata["has_audio"] = True
                    metadata["audio_codec"] = stream.get("codec_name")
    except Exception as e:
        logger.warning("ffprobe failed: %s", e)
    return metadata


def _extract_key_frames(
    file_path: str, output_dir: str
) -> list[dict[str, Any]]:
    """Extract key frames from a video at regular intervals."""
    interval = settings.video_frame_interval
    max_frames = settings.video_max_frames

    subprocess.run(
        [
            "ffmpeg", "-i", file_path,
            "-vf", f"fps=1/{interval}",
            "-frames:v", str(max_frames),
            "-q:v", "2",
            os.path.join(output_dir, "frame_%04d.jpg"),
        ],
        check=True, capture_output=True, timeout=300,
    )

    frames: list[dict[str, Any]] = []
    for i, frame_file in enumerate(sorted(Path(output_dir).glob("frame_*.jpg"))):
        timestamp = i * interval
        frames.append({
            "path": str(frame_file),
            "timestamp_seconds": timestamp,
            "timestamp_str": f"{timestamp // 60:02d}:{timestamp % 60:02d}",
        })
    return frames


def _extract_audio_track(file_path: str, output_dir: str) -> str | None:
    """Extract audio track from video as WAV."""
    audio_path = os.path.join(output_dir, "audio.wav")
    try:
        subprocess.run(
            [
                "ffmpeg", "-i", file_path,
                "-vn", "-acodec", "pcm_s16le",
                "-ar", "16000", "-ac", "1",
                audio_path,
            ],
            check=True, capture_output=True, timeout=300,
        )
        if os.path.exists(audio_path) and os.path.getsize(audio_path) > 0:
            return audio_path
    except Exception as e:
        logger.warning("Audio extraction from video failed: %s", e)
    return None


async def _extract_video(file_path: str, file_name: str) -> ExtractedDocument:
    metadata = _get_video_metadata(file_path)
    parts: list[str] = []

    with tempfile.TemporaryDirectory() as tmp_dir:
        # Extract and transcribe audio track
        audio_path = _extract_audio_track(file_path, tmp_dir)
        if audio_path:
            try:
                audio_doc = await _extract_audio(audio_path)
                if audio_doc.text.strip():
                    parts.append("[Audio Transcription]\n" + audio_doc.text)
                    metadata["has_transcription"] = True
                    metadata["transcription"] = audio_doc.text
            except Exception as e:
                logger.warning("Video audio transcription failed: %s", e)

        # Extract key frames
        frames_dir = os.path.join(tmp_dir, "frames")
        os.makedirs(frames_dir, exist_ok=True)
        try:
            frames = _extract_key_frames(file_path, frames_dir)
            metadata["frame_count"] = len(frames)
        except Exception as e:
            logger.warning("Frame extraction failed: %s", e)
            frames = []

        # Describe frames with Vision API
        if frames:
            frame_descriptions: list[str] = []
            for frame in frames:
                try:
                    description = await _describe_image_vision(
                        frame["path"], f"{file_name} @ {frame['timestamp_str']}"
                    )
                    frame_descriptions.append(
                        f"[{frame['timestamp_str']}] {description}"
                    )
                except Exception as e:
                    logger.warning(
                        "Frame description failed at %s: %s",
                        frame["timestamp_str"], e,
                    )
            if frame_descriptions:
                parts.append(
                    "[Video Frame Descriptions]\n" + "\n\n".join(frame_descriptions)
                )

    text = "\n\n".join(parts)
    return ExtractedDocument(text=text, metadata=metadata)


# ---------------------------------------------------------------------------
# Main dispatcher
# ---------------------------------------------------------------------------

def _sanitize_extracted(doc: ExtractedDocument) -> ExtractedDocument:
    character_count = len(doc.text) + sum(len(table) for table in (doc.tables or []))
    if character_count > settings.max_extracted_characters:
        raise ValueError(
            f"Extracted content has {character_count} characters; the configured limit is "
            f"{settings.max_extracted_characters}"
        )
    return ExtractedDocument(
        text=sanitize_text(doc.text),
        metadata=sanitize_json(doc.metadata) if doc.metadata else {},
        tables=[sanitize_text(t) for t in (doc.tables or [])],
    )


def get_transcription(doc: ExtractedDocument) -> str | None:
    """Return the full transcript when extraction produced one."""
    transcription = doc.metadata.get("transcription")
    if isinstance(transcription, str) and transcription.strip():
        return sanitize_text(transcription.strip())
    return None


def get_transcription_segments(doc: ExtractedDocument) -> list[dict[str, Any]]:
    """Return sanitized speaker/timestamp segments when diarization produced them."""
    raw_segments = doc.metadata.get("transcription_segments")
    if not isinstance(raw_segments, list):
        return []
    sanitized = sanitize_json(raw_segments)
    return sanitized if isinstance(sanitized, list) else []


async def extract_text(
    file_path: str,
    file_name: str,
    progress_callback: PdfProgressCallback | AudioProgressCallback | None = None,
) -> ExtractedDocument:
    ext = Path(file_name).suffix.lower()

    if ext == ".pdf":
        pdf = await extract_pdf(file_path, progress_callback=progress_callback)
        doc = ExtractedDocument(
            text=pdf.text,
            metadata=pdf.metadata,
            tables=pdf.tables,
        )
    elif ext == ".docx":
        await asyncio.to_thread(_validate_office_archive, file_path)
        doc = await asyncio.to_thread(_extract_docx, file_path)
    elif ext == ".doc":
        raise ValueError(
            "Legacy .doc files are not supported; convert the file to .docx or PDF and retry"
        )
    elif ext == ".xlsx":
        await asyncio.to_thread(_validate_office_archive, file_path)
        doc = await asyncio.to_thread(_extract_xlsx, file_path)
    elif ext == ".xls":
        raise ValueError(
            "Legacy .xls files are not supported; convert the file to .xlsx or CSV and retry"
        )
    elif ext == ".csv":
        await asyncio.to_thread(_validate_text_input_size, file_path)
        doc = await asyncio.to_thread(_extract_csv, file_path)
    elif ext in (".html", ".htm"):
        await asyncio.to_thread(_validate_text_input_size, file_path)
        doc = await asyncio.to_thread(_extract_html, file_path)
    elif ext in (".md", ".markdown"):
        await asyncio.to_thread(_validate_text_input_size, file_path)
        doc = await asyncio.to_thread(_extract_markdown, file_path)
    elif ext == ".eml":
        await asyncio.to_thread(_validate_text_input_size, file_path)
        doc = await asyncio.to_thread(_extract_eml, file_path)
    elif ext in IMAGE_EXTENSIONS:
        doc = await _extract_image(file_path, file_name)
    elif ext in VIDEO_EXTENSIONS:
        doc = await _extract_video(file_path, file_name)
    elif ext in AUDIO_EXTENSIONS:
        doc = await _extract_audio(file_path, progress_callback=progress_callback)
    elif ext in PLAIN_TEXT_EXTENSIONS:
        await asyncio.to_thread(_validate_text_input_size, file_path)
        text = await asyncio.to_thread(
            Path(file_path).read_text,
            encoding="utf-8",
            errors="replace",
        )
        if "\x00" in text:
            raise ValueError(f"{ext} file contains binary data and cannot be ingested as text")
        doc = ExtractedDocument(text=text, metadata={"file_type": "text"})
    else:
        raise ValueError(f"Unsupported file type: {ext or '(no extension)'}")

    return _sanitize_extracted(doc)
