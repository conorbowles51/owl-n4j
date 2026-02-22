#!/usr/bin/env python3
"""
Qualitative Review of Media Processing Outputs.

Runs each processor against the test media files and prints the actual
extracted content so it can be assessed for quality, completeness, and accuracy.

Sections:
1. Image OCR (Tesseract) — on 3 test images
2. Image Metadata (EXIF) — extraction quality
3. Image Vision API — GPT-4 Vision scene description (if API key set)
4. Audio Transcription (Whisper) — on test audio files
5. Video Metadata — ffprobe extraction
6. Video Frame Extraction — key frames
7. Video Full Pipeline — combined output
8. Folder Processing — mixed media folder with image/video roles
"""

import sys
import time
import tempfile
from pathlib import Path

# Setup path
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

TEST_MEDIA = Path(__file__).parent / "test_media"

# ── Formatting helpers ───────────────────────────────────────────────────────
BOLD = "\033[1m"
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
DIM = "\033[2m"
RESET = "\033[0m"

def header(num, title):
    print(f"\n{'='*70}")
    print(f"{CYAN}{BOLD}[{num}] {title}{RESET}")
    print(f"{'='*70}")

def subheader(title):
    print(f"\n{BOLD}--- {title} ---{RESET}")

def output_box(label, content, max_lines=30):
    """Print content in a bordered box."""
    lines = content.split("\n")
    truncated = len(lines) > max_lines
    if truncated:
        lines = lines[:max_lines]
    print(f"\n{GREEN}{label}:{RESET}")
    print(f"{'─'*60}")
    for line in lines:
        print(f"  {line}")
    if truncated:
        print(f"  {DIM}... ({len(content.split(chr(10))) - max_lines} more lines){RESET}")
    print(f"{'─'*60}")
    print(f"{DIM}Length: {len(content)} characters{RESET}")


# ── 1. Image OCR (Tesseract) ────────────────────────────────────────────────

def review_image_ocr():
    header(1, "Image OCR — Tesseract")

    from image_processor import extract_text_tesseract, TESSERACT_AVAILABLE
    if not TESSERACT_AVAILABLE:
        print(f"{YELLOW}Tesseract not available, skipping{RESET}")
        return

    test_images = [
        ("Surveillance Report (OCR)", TEST_MEDIA / "evidence_document_ocr.png"),
        ("Wire Transfer Receipt (OCR)", TEST_MEDIA / "wire_transfer_receipt.png"),
        ("Surveillance Scene (OCR)", TEST_MEDIA / "surveillance_scene.png"),
    ]

    for label, img_path in test_images:
        if not img_path.exists():
            print(f"  {YELLOW}SKIP: {img_path.name} not found{RESET}")
            continue

        subheader(label)
        start = time.time()
        text = extract_text_tesseract(img_path)
        elapsed = time.time() - start
        output_box(f"Extracted text ({elapsed:.2f}s)", text)

        # Quality assessment hints
        print(f"\n{BOLD}Quality check:{RESET}")
        key_terms = {
            "evidence_document_ocr.png": ["OPERATION SILVER BRIDGE", "Mendez-Torres", "Coral Gables",
                                          "Brickell Avenue", "Miami", "$2,450,000", "Cayman Islands",
                                          "FL-DHJ-4829", "TXN-2024-03-15-88421"],
            "wire_transfer_receipt.png": ["CAYMAN ISLANDS NATIONAL BANK", "Wire Transfer",
                                          "$2,450,000.00", "CI-9982-4471-0023", "Caribbean Maritime",
                                          "Panama National", "FNBMUS33"],
            "surveillance_scene.png": ["CAM-07", "BRICKELL", "FL-DHJ-4829", "SUBJECT", "ENTRANCE"],
        }
        terms = key_terms.get(img_path.name, [])
        text_upper = text.upper()
        for term in terms:
            found = term.upper() in text_upper
            status = f"{GREEN}✓{RESET}" if found else f"{YELLOW}✗{RESET}"
            print(f"  {status} '{term}'")


# ── 2. Image Metadata ───────────────────────────────────────────────────────

def review_image_metadata():
    header(2, "Image Metadata Extraction")

    from image_processor import extract_image_metadata

    test_images = [
        TEST_MEDIA / "evidence_document_ocr.png",
        TEST_MEDIA / "wire_transfer_receipt.png",
        TEST_MEDIA / "surveillance_scene.png",
    ]

    for img_path in test_images:
        if not img_path.exists():
            continue
        subheader(img_path.name)
        metadata = extract_image_metadata(img_path)
        for key, value in sorted(metadata.items()):
            print(f"  {key}: {value}")


# ── 3. Image Vision API ─────────────────────────────────────────────────────

def review_image_vision():
    header(3, "Image Vision API — GPT-4 Vision")

    from config import OPENAI_API_KEY
    from image_processor import describe_image_vision, OPENAI_AVAILABLE

    if not OPENAI_API_KEY:
        print(f"{YELLOW}OPENAI_API_KEY not set — skipping Vision API tests{RESET}")
        return
    if not OPENAI_AVAILABLE:
        print(f"{YELLOW}OpenAI package not available — skipping{RESET}")
        return

    test_images = [
        ("Surveillance Report (Vision)", TEST_MEDIA / "evidence_document_ocr.png"),
        ("Surveillance Scene (Vision)", TEST_MEDIA / "surveillance_scene.png"),
        ("Wire Transfer Receipt (Vision)", TEST_MEDIA / "wire_transfer_receipt.png"),
    ]

    for label, img_path in test_images:
        if not img_path.exists():
            continue
        subheader(label)
        start = time.time()
        description = describe_image_vision(img_path, doc_name=img_path.name)
        elapsed = time.time() - start
        output_box(f"Vision description ({elapsed:.2f}s)", description)


# ── 4. Audio Transcription ──────────────────────────────────────────────────

def review_audio_transcription():
    header(4, "Audio Transcription — Whisper")

    try:
        from audio_processor import load_whisper_model, transcribe_audio, WHISPER_AVAILABLE
    except ImportError:
        WHISPER_AVAILABLE = False

    if not WHISPER_AVAILABLE:
        print(f"{YELLOW}Whisper not available — skipping{RESET}")
        return

    test_audio = [
        ("Tone test (5s)", TEST_MEDIA / "test_audio.wav"),
        ("Extended tones (6s)", TEST_MEDIA / "test_audio_extended.wav"),
    ]

    subheader("Loading Whisper model (tiny)")
    start = time.time()
    model = load_whisper_model("tiny")
    print(f"  Model loaded in {time.time() - start:.1f}s")

    for label, audio_path in test_audio:
        if not audio_path.exists():
            print(f"  {YELLOW}SKIP: {audio_path.name} not found{RESET}")
            continue

        subheader(label)
        start = time.time()
        text = transcribe_audio(audio_path, model, language="en", task="transcribe")
        elapsed = time.time() - start
        output_box(f"Transcription ({elapsed:.2f}s)", text if text else "[empty transcription — expected for tone-only audio]")
        print(f"  {DIM}Note: Tone-only audio won't produce meaningful transcription — "
              f"this validates the pipeline runs without errors.{RESET}")


# ── 5. Video Metadata ───────────────────────────────────────────────────────

def review_video_metadata():
    header(5, "Video Metadata — ffprobe")

    from video_processor import get_video_metadata

    test_videos = [
        ("Test pattern video (10s)", TEST_MEDIA / "test_video.mp4"),
        ("Surveillance video (8s)", TEST_MEDIA / "surveillance_video.mp4"),
    ]

    for label, video_path in test_videos:
        if not video_path.exists():
            print(f"  {YELLOW}SKIP: {video_path.name} not found{RESET}")
            continue

        subheader(label)
        metadata = get_video_metadata(video_path)
        for key, value in sorted(metadata.items()):
            print(f"  {key}: {value}")


# ── 6. Video Frame Extraction ───────────────────────────────────────────────

def review_video_frames():
    header(6, "Video Frame Extraction")

    from video_processor import extract_key_frames

    test_video = TEST_MEDIA / "test_video.mp4"
    if not test_video.exists():
        print(f"{YELLOW}test_video.mp4 not found — skipping{RESET}")
        return

    with tempfile.TemporaryDirectory() as tmp:
        subheader(f"Extracting frames every 3s from {test_video.name}")
        start = time.time()
        frames = extract_key_frames(test_video, Path(tmp), interval=3, max_frames=10)
        elapsed = time.time() - start

        print(f"\n  Extracted {len(frames)} frames in {elapsed:.2f}s:")
        for f in frames:
            size = f["path"].stat().st_size if f["path"].exists() else 0
            print(f"    [{f['timestamp_str']}] {f['path'].name} ({size:,} bytes)")


# ── 7. Video Full Pipeline ──────────────────────────────────────────────────

def review_video_pipeline():
    header(7, "Video Full Pipeline")

    from video_processor import process_video

    test_videos = [
        ("Test pattern video", TEST_MEDIA / "test_video.mp4"),
        ("Surveillance video", TEST_MEDIA / "surveillance_video.mp4"),
    ]

    for label, video_path in test_videos:
        if not video_path.exists():
            print(f"  {YELLOW}SKIP: {video_path.name} not found{RESET}")
            continue

        subheader(label)
        logs = []
        start = time.time()
        result = process_video(video_path, log_callback=lambda msg: logs.append(msg))
        elapsed = time.time() - start

        print(f"\n{BOLD}Processing log:{RESET}")
        for log_msg in logs:
            print(f"  {DIM}{log_msg}{RESET}")

        output_box(f"Combined output ({elapsed:.2f}s)", result["text"], max_lines=40)

        print(f"\n{BOLD}Breakdown:{RESET}")
        print(f"  Transcription: {len(result.get('transcription', ''))} chars")
        print(f"  Frame descriptions: {len(result.get('frame_descriptions', []))} frames")
        if result.get("metadata"):
            md = result["metadata"]
            print(f"  Duration: {md.get('duration_str', '?')}")
            print(f"  Resolution: {md.get('width', '?')}x{md.get('height', '?')}")


# ── 8. Folder Processing ────────────────────────────────────────────────────

def review_folder_processing():
    header(8, "Folder Processing — Mixed Media")

    # Fix profile_loader import (same as test suite)
    import importlib, importlib.util
    if "profile_loader" in sys.modules:
        cached_file = getattr(sys.modules["profile_loader"], "__file__", "")
        if "backend" in cached_file:
            del sys.modules["profile_loader"]
    if "profile_loader" not in sys.modules:
        pl_path = SCRIPTS_DIR / "profile_loader.py"
        if pl_path.exists():
            spec = importlib.util.spec_from_file_location("profile_loader", str(pl_path))
            pl_mod = importlib.util.module_from_spec(spec)
            sys.modules["profile_loader"] = pl_mod
            spec.loader.exec_module(pl_mod)

    from folder_processor import process_image_files, process_video_files, prepare_structured_text

    evidence_folder = TEST_MEDIA / "evidence_folder_001"
    if not evidence_folder.exists():
        print(f"{YELLOW}evidence_folder_001 not found — skipping{RESET}")
        return

    subheader("Contents of evidence_folder_001")
    for f in sorted(evidence_folder.iterdir()):
        print(f"  {f.name} ({f.stat().st_size:,} bytes)")

    # Test image processing within folder
    image_files = list(evidence_folder.glob("*.jpg")) + list(evidence_folder.glob("*.png"))
    if image_files:
        subheader(f"Processing {len(image_files)} image(s) with Tesseract")
        result = process_image_files(
            image_files,
            {"provider": "tesseract"},
            log_callback=lambda msg: print(f"  {DIM}{msg}{RESET}"),
        )
        if "image_descriptions" in result:
            output_box("Image descriptions", result["image_descriptions"])
        else:
            print(f"  {YELLOW}No image descriptions extracted{RESET}")

    # Test structured text assembly
    subheader("Structured text assembly (media_structured format)")
    test_results = {
        "metadata": {"case": "OSB-2024-0147"},
        "participants": ["Agent Martinez", "Ricardo Mendez"],
        "image_descriptions": result.get("image_descriptions", "No images"),
        "english_transcription": "[Whisper transcription would appear here]",
    }
    structured = prepare_structured_text("evidence_folder_001", test_results, "media_structured")
    output_box("Assembled structured text", structured)


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    print(f"\n{BOLD}{'='*70}{RESET}")
    print(f"{BOLD}QUALITATIVE REVIEW — MEDIA PROCESSING OUTPUTS{RESET}")
    print(f"{'='*70}")
    print(f"Test media: {TEST_MEDIA}")
    print(f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")

    total_start = time.time()

    review_image_ocr()
    review_image_metadata()
    review_image_vision()
    review_audio_transcription()
    review_video_metadata()
    review_video_frames()
    review_video_pipeline()
    review_folder_processing()

    total_elapsed = time.time() - total_start

    print(f"\n{'='*70}")
    print(f"{BOLD}REVIEW COMPLETE{RESET} — Total time: {total_elapsed:.1f}s")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()
