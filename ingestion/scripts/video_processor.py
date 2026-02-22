"""
Video Processor module - extracts content from video files.

Orchestrates three sub-tasks:
1. Audio extraction + Whisper transcription
2. Key frame extraction at configurable intervals
3. GPT-4 Vision analysis of key frames

Dependencies:
- ffmpeg + ffprobe binaries (brew install ffmpeg)
- openai-whisper (pip install openai-whisper)
- openai Python package (for Vision API)

Output: Structured text combining transcription + frame descriptions,
suitable for entity extraction via the ingestion pipeline.
"""

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Callable

from logging_utils import log_progress, log_error, log_warning
from config import (
    FFMPEG_CMD,
    FFPROBE_CMD,
    VIDEO_FRAME_INTERVAL,
    VIDEO_MAX_FRAMES,
    OPENAI_VISION_MODEL,
    OPENAI_API_KEY,
    WHISPER_MODEL_SIZE,
    AUDIO_LANGUAGE,
)

# Whisper imports (reuse from audio_processor)
try:
    from audio_processor import load_whisper_model, transcribe_audio, WHISPER_AVAILABLE
except ImportError:
    WHISPER_AVAILABLE = False

# Image processor for Vision API (reuse describe_image_vision)
try:
    from image_processor import describe_image_vision, OPENAI_AVAILABLE
except ImportError:
    OPENAI_AVAILABLE = False


def get_video_metadata(video_path: Path) -> Dict:
    """
    Extract metadata from a video file using ffprobe.

    Returns duration, resolution, codec, frame rate, and audio stream info.

    Args:
        video_path: Path to video file

    Returns:
        Dict with metadata keys: duration, width, height, codec, fps, has_audio, etc.
    """
    metadata = {}

    try:
        cmd = [
            FFPROBE_CMD,
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            str(video_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

        if result.returncode != 0:
            return metadata

        probe = json.loads(result.stdout)

        # Format-level metadata
        fmt = probe.get("format", {})
        duration = float(fmt.get("duration", 0))
        metadata["duration_seconds"] = duration
        metadata["duration_str"] = _format_duration(duration)
        metadata["file_size_bytes"] = int(fmt.get("size", 0))
        metadata["format_name"] = fmt.get("format_name", "")

        # Stream-level metadata
        has_audio = False
        has_video = False

        for stream in probe.get("streams", []):
            codec_type = stream.get("codec_type", "")

            if codec_type == "video" and not has_video:
                has_video = True
                metadata["width"] = int(stream.get("width", 0))
                metadata["height"] = int(stream.get("height", 0))
                metadata["video_codec"] = stream.get("codec_name", "")
                # Parse frame rate (e.g., "30/1" or "30000/1001")
                r_frame_rate = stream.get("r_frame_rate", "0/1")
                try:
                    num, den = r_frame_rate.split("/")
                    metadata["fps"] = round(float(num) / float(den), 2)
                except (ValueError, ZeroDivisionError):
                    metadata["fps"] = 0

            elif codec_type == "audio" and not has_audio:
                has_audio = True
                metadata["audio_codec"] = stream.get("codec_name", "")
                metadata["audio_sample_rate"] = stream.get("sample_rate", "")

        metadata["has_video"] = has_video
        metadata["has_audio"] = has_audio

    except FileNotFoundError:
        log_error(f"ffprobe not found at '{FFPROBE_CMD}'. Install with: brew install ffmpeg")
    except subprocess.TimeoutExpired:
        log_error("ffprobe timed out")
    except Exception as e:
        log_error(f"ffprobe failed: {e}")

    return metadata


def extract_audio_track(
    video_path: Path,
    output_dir: Path,
    log_callback: Optional[Callable[[str], None]] = None,
) -> Optional[Path]:
    """
    Extract audio track from video as WAV for Whisper transcription.

    Uses ffmpeg to extract and convert audio to 16kHz mono WAV.

    Args:
        video_path: Path to video file
        output_dir: Directory to save extracted audio
        log_callback: Optional logging callback

    Returns:
        Path to extracted WAV file, or None if extraction failed
    """
    output_path = output_dir / "audio_track.wav"

    try:
        cmd = [
            FFMPEG_CMD,
            "-i", str(video_path),
            "-vn",                  # No video
            "-acodec", "pcm_s16le", # 16-bit PCM
            "-ar", "16000",         # 16kHz sample rate (Whisper optimal)
            "-ac", "1",             # Mono
            "-y",                   # Overwrite
            str(output_path),
        ]

        log_progress(f"Extracting audio track from {video_path.name}", log_callback)

        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=300  # 5 min timeout
        )

        if result.returncode != 0:
            # Check if the video has no audio stream
            if "does not contain any stream" in result.stderr:
                log_warning("Video has no audio stream", log_callback)
                return None
            log_error(f"ffmpeg audio extraction failed: {result.stderr[:500]}", log_callback)
            return None

        if output_path.exists() and output_path.stat().st_size > 0:
            log_progress(f"Audio track extracted: {output_path.stat().st_size} bytes", log_callback)
            return output_path

        return None

    except FileNotFoundError:
        log_error(f"ffmpeg not found at '{FFMPEG_CMD}'. Install with: brew install ffmpeg", log_callback)
        return None
    except subprocess.TimeoutExpired:
        log_error("ffmpeg audio extraction timed out (5 min limit)", log_callback)
        return None
    except Exception as e:
        log_error(f"Audio extraction failed: {e}", log_callback)
        return None


def extract_key_frames(
    video_path: Path,
    output_dir: Path,
    interval: int = None,
    max_frames: int = None,
    log_callback: Optional[Callable[[str], None]] = None,
) -> List[Dict]:
    """
    Extract key frames from video at regular intervals using ffmpeg.

    Args:
        video_path: Path to video file
        output_dir: Directory to save extracted frames
        interval: Seconds between frame captures (default: from config)
        max_frames: Maximum number of frames to extract (default: from config)
        log_callback: Optional logging callback

    Returns:
        List of dicts: [{path, timestamp_seconds, timestamp_str}, ...]
    """
    frame_interval = interval or VIDEO_FRAME_INTERVAL
    frame_max = max_frames or VIDEO_MAX_FRAMES

    frames_dir = output_dir / "frames"
    frames_dir.mkdir(exist_ok=True)

    # Auto-adjust interval if video is shorter than the interval
    # Get duration to check if we need a shorter interval
    metadata = get_video_metadata(video_path)
    duration = metadata.get("duration_seconds", 0)
    if duration > 0 and frame_interval > duration:
        # For short videos, extract at least a few frames
        # Aim for ~3-5 frames minimum
        frame_interval = max(1, int(duration / 5))
        log_progress(
            f"Video is {duration:.0f}s, adjusting frame interval to {frame_interval}s",
            log_callback,
        )

    try:
        # Use fps filter to extract frames at interval
        cmd = [
            FFMPEG_CMD,
            "-i", str(video_path),
            "-vf", f"fps=1/{frame_interval}",
            "-frames:v", str(frame_max),
            "-q:v", "2",  # High quality JPEG
            "-y",
            str(frames_dir / "frame_%04d.jpg"),
        ]

        log_progress(
            f"Extracting key frames every {frame_interval}s (max {frame_max} frames)",
            log_callback,
        )

        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=300  # 5 min timeout
        )

        # Collect extracted frames (check for output files even if returncode != 0,
        # since ffmpeg writes config/version info to stderr which can look like errors)
        frames = []
        frame_files = sorted(frames_dir.glob("frame_*.jpg"))

        if not frame_files and result.returncode != 0:
            log_error(f"ffmpeg frame extraction failed: {result.stderr[:500]}", log_callback)
            return []

        for idx, frame_path in enumerate(frame_files):
            timestamp_seconds = idx * frame_interval
            timestamp_str = _format_duration(timestamp_seconds)
            frames.append({
                "path": frame_path,
                "timestamp_seconds": timestamp_seconds,
                "timestamp_str": timestamp_str,
                "frame_number": idx + 1,
            })

        log_progress(f"Extracted {len(frames)} key frames", log_callback)
        return frames

    except FileNotFoundError:
        log_error(f"ffmpeg not found at '{FFMPEG_CMD}'. Install with: brew install ffmpeg", log_callback)
        return []
    except subprocess.TimeoutExpired:
        log_error("ffmpeg frame extraction timed out (5 min limit)", log_callback)
        return []
    except Exception as e:
        log_error(f"Frame extraction failed: {e}", log_callback)
        return []


def describe_frames_vision(
    frames: List[Dict],
    video_name: str,
    log_callback: Optional[Callable[[str], None]] = None,
) -> List[Dict]:
    """
    Analyze extracted video frames using GPT-4 Vision API.

    Sends each frame to the Vision API for detailed scene description.

    Args:
        frames: List of frame dicts from extract_key_frames
        video_name: Video filename for cost tracking
        log_callback: Optional logging callback

    Returns:
        List of dicts: [{timestamp_str, description}, ...]
    """
    if not OPENAI_AVAILABLE:
        log_warning("OpenAI not available, skipping frame analysis", log_callback)
        return []

    if not OPENAI_API_KEY:
        log_warning("OPENAI_API_KEY not set, skipping frame analysis", log_callback)
        return []

    descriptions = []
    total_frames = len(frames)

    for idx, frame in enumerate(frames):
        frame_path = frame["path"]
        timestamp_str = frame["timestamp_str"]

        log_progress(
            f"Analyzing frame {idx + 1}/{total_frames} [{timestamp_str}]",
            log_callback,
        )

        try:
            description = describe_image_vision(
                image_path=frame_path,
                log_callback=log_callback,
                doc_name=f"{video_name}_frame_{timestamp_str}",
            )
            descriptions.append({
                "timestamp_str": timestamp_str,
                "timestamp_seconds": frame["timestamp_seconds"],
                "description": description,
            })
        except Exception as e:
            log_error(f"Vision analysis failed for frame [{timestamp_str}]: {e}", log_callback)
            descriptions.append({
                "timestamp_str": timestamp_str,
                "timestamp_seconds": frame["timestamp_seconds"],
                "description": f"[Analysis failed: {e}]",
            })

    log_progress(f"Vision analysis complete: {len(descriptions)} frames analyzed", log_callback)
    return descriptions


def transcribe_video_audio(
    audio_path: Path,
    log_callback: Optional[Callable[[str], None]] = None,
    whisper_model_size: Optional[str] = None,
    language: Optional[str] = None,
) -> str:
    """
    Transcribe extracted video audio using Whisper.

    Reuses audio_processor.py's Whisper model loading and transcription.

    Args:
        audio_path: Path to extracted audio WAV file
        log_callback: Optional logging callback
        whisper_model_size: Whisper model size override
        language: Language code override (None = auto-detect)

    Returns:
        Transcribed text string
    """
    if not WHISPER_AVAILABLE:
        log_warning("Whisper not available, skipping audio transcription", log_callback)
        return ""

    model_size = whisper_model_size or WHISPER_MODEL_SIZE
    lang = language or AUDIO_LANGUAGE

    log_progress(f"Transcribing video audio (model: {model_size})", log_callback)

    try:
        model = load_whisper_model(model_size)
        transcription = transcribe_audio(
            audio_path=audio_path,
            model=model,
            language=lang if lang else "en",
            task="transcribe",
        )
        log_progress(f"Audio transcription complete: {len(transcription)} characters", log_callback)
        return transcription
    except Exception as e:
        log_error(f"Audio transcription failed: {e}", log_callback)
        return ""


def process_video(
    video_path: Path,
    log_callback: Optional[Callable[[str], None]] = None,
    doc_name: Optional[str] = None,
) -> Dict:
    """
    Full video processing pipeline.

    Orchestrates: metadata → audio extraction → transcription →
    frame extraction → Vision analysis → combine into structured text.

    All temporary files (extracted audio, frames) are created in a
    temporary directory that is cleaned up automatically.

    Args:
        video_path: Path to video file
        log_callback: Optional logging callback
        doc_name: Document name for cost tracking

    Returns:
        Dict with keys:
        - text: Combined structured text (transcription + frame descriptions)
        - metadata: Video metadata (duration, resolution, etc.)
        - transcription: Raw transcription text
        - frame_descriptions: List of frame description dicts
    """
    video_name = doc_name or video_path.name

    log_progress(f"Processing video: {video_path.name}", log_callback)

    # Step 1: Get video metadata
    metadata = get_video_metadata(video_path)
    duration_str = metadata.get("duration_str", "unknown")
    resolution = ""
    if metadata.get("width") and metadata.get("height"):
        resolution = f"{metadata['width']}x{metadata['height']}"

    log_progress(
        f"Video info: {duration_str}, {resolution}, "
        f"audio={'yes' if metadata.get('has_audio') else 'no'}",
        log_callback,
    )

    transcription = ""
    frame_descriptions = []

    with tempfile.TemporaryDirectory(prefix="owl_video_") as tmp_dir:
        tmp_path = Path(tmp_dir)

        # Step 2: Extract and transcribe audio
        if metadata.get("has_audio", False):
            audio_path = extract_audio_track(video_path, tmp_path, log_callback)
            if audio_path:
                transcription = transcribe_video_audio(audio_path, log_callback)
        else:
            log_warning("No audio stream detected in video", log_callback)

        # Step 3: Extract key frames
        if metadata.get("has_video", True):
            frames = extract_key_frames(video_path, tmp_path, log_callback=log_callback)

            # Step 4: Analyze frames with Vision API
            if frames:
                frame_descriptions = describe_frames_vision(
                    frames, video_name, log_callback
                )
        else:
            log_warning("No video stream detected", log_callback)

    # Step 5: Combine into structured text
    text = _build_structured_text(
        video_name=video_name,
        duration_str=duration_str,
        resolution=resolution,
        metadata=metadata,
        transcription=transcription,
        frame_descriptions=frame_descriptions,
    )

    log_progress(
        f"Video processing complete: {len(text)} characters total",
        log_callback,
    )

    return {
        "text": text,
        "metadata": metadata,
        "transcription": transcription,
        "frame_descriptions": frame_descriptions,
    }


def _build_structured_text(
    video_name: str,
    duration_str: str,
    resolution: str,
    metadata: Dict,
    transcription: str,
    frame_descriptions: List[Dict],
) -> str:
    """
    Build the combined structured text output for ingestion.

    Format:
        === VIDEO ANALYSIS ===
        Source: file.mp4 | Duration: 5m23s | Resolution: 1920x1080

        === AUDIO TRANSCRIPTION ===
        [Full Whisper transcription]

        === VISUAL SCENE ANALYSIS ===
        [00:00:00] Scene description...
        [00:00:30] Scene description...
    """
    parts = []

    # Header
    parts.append("=== VIDEO ANALYSIS ===")
    header_details = [f"Source: {video_name}"]
    if duration_str:
        header_details.append(f"Duration: {duration_str}")
    if resolution:
        header_details.append(f"Resolution: {resolution}")
    if metadata.get("video_codec"):
        header_details.append(f"Codec: {metadata['video_codec']}")
    parts.append(" | ".join(header_details))
    parts.append("")

    # Audio transcription
    if transcription and transcription.strip():
        parts.append("=== AUDIO TRANSCRIPTION ===")
        parts.append(transcription.strip())
        parts.append("")

    # Frame descriptions
    if frame_descriptions:
        parts.append("=== VISUAL SCENE ANALYSIS ===")
        for fd in frame_descriptions:
            timestamp = fd.get("timestamp_str", "??:??:??")
            description = fd.get("description", "")
            if description:
                parts.append(f"[{timestamp}] {description}")
                parts.append("")  # Blank line between frames

    # If nothing was extracted
    if not transcription.strip() and not frame_descriptions:
        parts.append("[No content could be extracted from this video]")

    return "\n".join(parts)


def _format_duration(seconds: float) -> str:
    """Format duration in seconds to HH:MM:SS or MM:SS string."""
    total = int(seconds)
    hours = total // 3600
    minutes = (total % 3600) // 60
    secs = total % 60

    if hours > 0:
        return f"{hours:d}h{minutes:02d}m{secs:02d}s"
    elif minutes > 0:
        return f"{minutes:d}m{secs:02d}s"
    else:
        return f"{secs:d}s"
