#!/usr/bin/env python3
"""
Comprehensive test suite for the media processing features.

Tests:
1. Image Processing   - Tesseract OCR, EXIF metadata, Vision API (if key set)
2. Audio Processing   - Standalone audio ingestion via Whisper
3. Video Processing   - ffmpeg metadata, frame extraction, audio extraction
4. File Type Routing  - ingest_data.py dispatches correctly to new handlers
5. Folder Processing  - image and video roles in folder_processor.py
6. Config Loading     - All new config values load correctly

Usage:
    python test_media_processors.py              # Run all tests
    python test_media_processors.py --quick      # Skip slow tests (Whisper, Vision)
    python test_media_processors.py --verbose    # Extra output
"""

import argparse
import json
import os
import sys
import time
import traceback
from pathlib import Path

# Add ingestion scripts to path FIRST, before backend
# (both dirs have a profile_loader.py — ingestion/scripts version is needed here)
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
# Remove any existing entries that might shadow ingestion scripts
for p in list(sys.path):
    if "backend" in p and "ingestion" not in p:
        sys.path.remove(p)
        sys.path.append(p)  # Move to end so ingestion/scripts takes priority
sys.path.insert(0, str(SCRIPTS_DIR))

# Test media directory
TEST_MEDIA_DIR = Path(__file__).parent / "test_media"

# ── Colours for terminal output ──────────────────────────────────────────────
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"


class TestResults:
    """Collect and report test results."""

    def __init__(self):
        self.passed = []
        self.failed = []
        self.skipped = []
        self.start_time = time.time()

    def ok(self, name, detail=""):
        self.passed.append((name, detail))
        print(f"  {GREEN}PASS{RESET} {name}" + (f" — {detail}" if detail else ""))

    def fail(self, name, reason):
        self.failed.append((name, reason))
        print(f"  {RED}FAIL{RESET} {name} — {reason}")

    def skip(self, name, reason):
        self.skipped.append((name, reason))
        print(f"  {YELLOW}SKIP{RESET} {name} — {reason}")

    def summary(self):
        elapsed = time.time() - self.start_time
        total = len(self.passed) + len(self.failed) + len(self.skipped)
        print()
        print(f"{BOLD}{'=' * 60}{RESET}")
        print(f"{BOLD}TEST RESULTS{RESET}")
        print(f"{'=' * 60}")
        print(f"  {GREEN}Passed:  {len(self.passed)}{RESET}")
        print(f"  {RED}Failed:  {len(self.failed)}{RESET}")
        print(f"  {YELLOW}Skipped: {len(self.skipped)}{RESET}")
        print(f"  Total:   {total}")
        print(f"  Time:    {elapsed:.1f}s")
        print(f"{'=' * 60}")

        if self.failed:
            print(f"\n{RED}{BOLD}Failed tests:{RESET}")
            for name, reason in self.failed:
                print(f"  {RED}✗{RESET} {name}: {reason}")

        if self.skipped:
            print(f"\n{YELLOW}Skipped tests:{RESET}")
            for name, reason in self.skipped:
                print(f"  {YELLOW}○{RESET} {name}: {reason}")

        return len(self.failed) == 0


# ── Test 1: Config Loading ───────────────────────────────────────────────────

def test_config(results: TestResults):
    print(f"\n{CYAN}{BOLD}[1] Config Loading{RESET}")

    try:
        from config import IMAGE_PROVIDER, TESSERACT_LANG, OPENAI_VISION_MODEL
        results.ok("config.IMAGE_PROVIDER", f"value='{IMAGE_PROVIDER}'")
        results.ok("config.TESSERACT_LANG", f"value='{TESSERACT_LANG}'")
        results.ok("config.OPENAI_VISION_MODEL", f"value='{OPENAI_VISION_MODEL}'")
    except ImportError as e:
        results.fail("config image settings", str(e))

    try:
        from config import FFMPEG_CMD, FFPROBE_CMD, VIDEO_FRAME_INTERVAL, VIDEO_MAX_FRAMES
        results.ok("config.FFMPEG_CMD", f"value='{FFMPEG_CMD}'")
        results.ok("config.FFPROBE_CMD", f"value='{FFPROBE_CMD}'")
        results.ok("config.VIDEO_FRAME_INTERVAL", f"value={VIDEO_FRAME_INTERVAL}")
        results.ok("config.VIDEO_MAX_FRAMES", f"value={VIDEO_MAX_FRAMES}")
    except ImportError as e:
        results.fail("config video settings", str(e))

    try:
        from config import WHISPER_MODEL_SIZE, AUDIO_LANGUAGE
        results.ok("config.WHISPER_MODEL_SIZE", f"value='{WHISPER_MODEL_SIZE}'")
        results.ok("config.AUDIO_LANGUAGE", f"value={AUDIO_LANGUAGE}")
    except ImportError as e:
        results.fail("config audio settings", str(e))


# ── Test 2: Image Processor ──────────────────────────────────────────────────

def test_image_processor(results: TestResults, quick=False):
    print(f"\n{CYAN}{BOLD}[2] Image Processor{RESET}")

    try:
        from image_processor import (
            process_image,
            extract_image_metadata,
            extract_text_tesseract,
            describe_image_vision,
            TESSERACT_AVAILABLE,
            OPENAI_AVAILABLE,
        )
        results.ok("image_processor import")
    except ImportError as e:
        results.fail("image_processor import", str(e))
        return

    # Test EXIF metadata extraction
    ocr_image = TEST_MEDIA_DIR / "evidence_document_ocr.png"
    if ocr_image.exists():
        try:
            metadata = extract_image_metadata(ocr_image)
            assert metadata.get("width") == 800, f"Expected width=800, got {metadata.get('width')}"
            assert metadata.get("height") == 600, f"Expected height=600, got {metadata.get('height')}"
            results.ok("extract_image_metadata", f"width={metadata['width']}, height={metadata['height']}, format={metadata.get('format')}")
        except Exception as e:
            results.fail("extract_image_metadata", str(e))
    else:
        results.skip("extract_image_metadata", "Test image not generated yet (run generate_test_media.py first)")

    # Test Tesseract OCR
    if not TESSERACT_AVAILABLE:
        results.skip("tesseract_ocr", "pytesseract not installed")
    elif not ocr_image.exists():
        results.skip("tesseract_ocr", "Test image not generated yet")
    else:
        try:
            text = extract_text_tesseract(ocr_image)
            assert len(text) > 50, f"OCR extracted too little text ({len(text)} chars)"
            # Check for key terms that should be recognizable
            text_upper = text.upper()
            found_terms = []
            for term in ["OPERATION", "SILVER", "BRIDGE", "MENDEZ", "MIAMI", "CAYMAN"]:
                if term in text_upper:
                    found_terms.append(term)
            results.ok("tesseract_ocr", f"{len(text)} chars, found terms: {found_terms}")
        except Exception as e:
            results.fail("tesseract_ocr", str(e))

    # Test financial document OCR
    financial_image = TEST_MEDIA_DIR / "wire_transfer_receipt.png"
    if TESSERACT_AVAILABLE and financial_image.exists():
        try:
            text = extract_text_tesseract(financial_image)
            text_upper = text.upper()
            found = []
            for term in ["WIRE TRANSFER", "CAYMAN", "$2,450,000", "MENDEZ", "MARITIME"]:
                if term in text_upper:
                    found.append(term)
            results.ok("tesseract_ocr_financial", f"{len(text)} chars, found: {found}")
        except Exception as e:
            results.fail("tesseract_ocr_financial", str(e))
    else:
        results.skip("tesseract_ocr_financial", "Image not available or tesseract missing")

    # Test process_image routing (tesseract mode)
    if TESSERACT_AVAILABLE and ocr_image.exists():
        try:
            result = process_image(ocr_image, provider="tesseract")
            assert result["provider"] == "tesseract"
            assert len(result["text"]) > 50
            assert "metadata" in result
            results.ok("process_image(tesseract)", f"provider={result['provider']}, {len(result['text'])} chars")
        except Exception as e:
            results.fail("process_image(tesseract)", str(e))

    # Test Vision API (only if API key is set and not in quick mode)
    from config import OPENAI_API_KEY
    if quick:
        results.skip("describe_image_vision", "Skipped in quick mode (API call)")
    elif not OPENAI_API_KEY:
        results.skip("describe_image_vision", "OPENAI_API_KEY not set")
    elif not OPENAI_AVAILABLE:
        results.skip("describe_image_vision", "openai package not installed")
    elif not ocr_image.exists():
        results.skip("describe_image_vision", "Test image not available")
    else:
        try:
            description = describe_image_vision(ocr_image, doc_name="test_vision")
            assert len(description) > 20, f"Vision description too short ({len(description)} chars)"
            results.ok("describe_image_vision", f"{len(description)} chars")
        except Exception as e:
            results.fail("describe_image_vision", str(e))


# ── Test 3: Image Ingestion ──────────────────────────────────────────────────

def test_image_ingestion(results: TestResults):
    print(f"\n{CYAN}{BOLD}[3] Image Ingestion{RESET}")

    try:
        from image_ingestion import ingest_image_file, IMAGE_EXTENSIONS
        results.ok("image_ingestion import", f"extensions={IMAGE_EXTENSIONS}")
    except ImportError as e:
        results.fail("image_ingestion import", str(e))
        return

    # Verify extension coverage
    expected = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff", ".tif"}
    missing = expected - IMAGE_EXTENSIONS
    extra = IMAGE_EXTENSIONS - expected
    if missing:
        results.fail("IMAGE_EXTENSIONS coverage", f"Missing: {missing}")
    elif extra:
        results.ok("IMAGE_EXTENSIONS coverage", f"Has extra: {extra} (OK)")
    else:
        results.ok("IMAGE_EXTENSIONS coverage", "All expected extensions present")


# ── Test 4: Audio Ingestion ──────────────────────────────────────────────────

def test_audio_ingestion(results: TestResults, quick=False):
    print(f"\n{CYAN}{BOLD}[4] Audio Ingestion (Standalone){RESET}")

    try:
        from audio_ingestion import ingest_audio_file, AUDIO_EXTENSIONS
        results.ok("audio_ingestion import", f"extensions={AUDIO_EXTENSIONS}")
    except ImportError as e:
        results.fail("audio_ingestion import", str(e))
        return

    expected = {".mp3", ".wav", ".ogg", ".flac", ".aac", ".m4a", ".wma"}
    missing = expected - AUDIO_EXTENSIONS
    if missing:
        results.fail("AUDIO_EXTENSIONS coverage", f"Missing: {missing}")
    else:
        results.ok("AUDIO_EXTENSIONS coverage", "All expected extensions present")

    # Test Whisper availability
    try:
        from audio_processor import WHISPER_AVAILABLE
        if WHISPER_AVAILABLE:
            results.ok("whisper_available", "openai-whisper is installed")
        else:
            results.skip("whisper_available", "openai-whisper not installed")
    except ImportError:
        results.skip("whisper_available", "audio_processor not importable")

    # Test Whisper model loading (slow, skip in quick mode)
    if quick:
        results.skip("whisper_model_load", "Skipped in quick mode (model download)")
    else:
        try:
            from audio_processor import WHISPER_AVAILABLE, load_whisper_model
            if not WHISPER_AVAILABLE:
                results.skip("whisper_model_load", "Whisper not installed")
            else:
                model = load_whisper_model("tiny")  # Use tiny for fast testing
                results.ok("whisper_model_load", "Loaded 'tiny' model")
        except Exception as e:
            results.fail("whisper_model_load", str(e))


# ── Test 5: Video Processor ──────────────────────────────────────────────────

def test_video_processor(results: TestResults, quick=False):
    print(f"\n{CYAN}{BOLD}[5] Video Processor{RESET}")

    try:
        from video_processor import (
            process_video,
            get_video_metadata,
            extract_audio_track,
            extract_key_frames,
            _format_duration,
        )
        results.ok("video_processor import")
    except ImportError as e:
        results.fail("video_processor import", str(e))
        return

    # Test duration formatter
    try:
        assert _format_duration(0) == "0s"
        assert _format_duration(45) == "45s"
        assert _format_duration(323) == "5m23s"
        assert _format_duration(7384) == "2h03m04s"
        results.ok("_format_duration", "All format cases pass")
    except AssertionError as e:
        results.fail("_format_duration", str(e))

    # Test video metadata extraction
    test_video = TEST_MEDIA_DIR / "test_video.mp4"
    if not test_video.exists():
        results.skip("get_video_metadata", "Test video not generated (run generate_test_media.py first)")
        results.skip("extract_audio_track", "Test video not available")
        results.skip("extract_key_frames", "Test video not available")
        return

    try:
        metadata = get_video_metadata(test_video)
        assert metadata.get("has_video") is True, "Expected has_video=True"
        assert metadata.get("has_audio") is True, "Expected has_audio=True"
        assert metadata.get("duration_seconds", 0) > 0, "Expected duration > 0"
        results.ok(
            "get_video_metadata",
            f"duration={metadata.get('duration_str')}, "
            f"{metadata.get('width')}x{metadata.get('height')}, "
            f"codec={metadata.get('video_codec')}, "
            f"audio={'yes' if metadata.get('has_audio') else 'no'}"
        )
    except Exception as e:
        results.fail("get_video_metadata", str(e))

    # Test audio track extraction
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        try:
            audio_path = extract_audio_track(test_video, Path(tmp))
            if audio_path and audio_path.exists():
                results.ok("extract_audio_track", f"extracted {audio_path.stat().st_size:,} bytes")
            else:
                results.fail("extract_audio_track", "No audio extracted")
        except Exception as e:
            results.fail("extract_audio_track", str(e))

    # Test key frame extraction
    with tempfile.TemporaryDirectory() as tmp:
        try:
            frames = extract_key_frames(test_video, Path(tmp), interval=3, max_frames=5)
            if frames:
                results.ok(
                    "extract_key_frames",
                    f"{len(frames)} frames extracted, "
                    f"timestamps: {[f['timestamp_str'] for f in frames]}"
                )
            else:
                results.fail("extract_key_frames", "No frames extracted")
        except Exception as e:
            results.fail("extract_key_frames", str(e))

    # Full video processing pipeline (slow, skip in quick mode)
    if quick:
        results.skip("process_video (full)", "Skipped in quick mode")
    else:
        try:
            logs = []
            result = process_video(test_video, log_callback=lambda msg: logs.append(msg))
            assert len(result["text"]) > 0, "No text output from video processing"
            results.ok(
                "process_video (full)",
                f"{len(result['text'])} chars output, "
                f"transcription={'yes' if result.get('transcription') else 'no'}, "
                f"frames={len(result.get('frame_descriptions', []))}"
            )
        except Exception as e:
            results.fail("process_video (full)", str(e))


# ── Test 6: Video Ingestion ──────────────────────────────────────────────────

def test_video_ingestion(results: TestResults):
    print(f"\n{CYAN}{BOLD}[6] Video Ingestion{RESET}")

    try:
        from video_ingestion import ingest_video_file, VIDEO_EXTENSIONS
        results.ok("video_ingestion import", f"extensions={VIDEO_EXTENSIONS}")
    except ImportError as e:
        results.fail("video_ingestion import", str(e))
        return

    expected = {".mp4", ".avi", ".mov", ".wmv", ".flv", ".mkv", ".webm"}
    missing = expected - VIDEO_EXTENSIONS
    if missing:
        results.fail("VIDEO_EXTENSIONS coverage", f"Missing: {missing}")
    else:
        results.ok("VIDEO_EXTENSIONS coverage", "All expected extensions present")


# ── Test 7: File Type Routing ────────────────────────────────────────────────

def test_file_routing(results: TestResults):
    print(f"\n{CYAN}{BOLD}[7] File Type Routing (ingest_data.py){RESET}")

    try:
        from ingest_data import ingest_file
        results.ok("ingest_data import with new handlers")
    except ImportError as e:
        results.fail("ingest_data import", str(e))
        return

    # Test that routing recognizes new extensions (without actually ingesting)
    from audio_ingestion import AUDIO_EXTENSIONS
    from image_ingestion import IMAGE_EXTENSIONS
    from video_ingestion import VIDEO_EXTENSIONS

    # Verify all extension sets are non-empty and disjoint
    all_ext = AUDIO_EXTENSIONS | IMAGE_EXTENSIONS | VIDEO_EXTENSIONS
    assert len(all_ext) == len(AUDIO_EXTENSIONS) + len(IMAGE_EXTENSIONS) + len(VIDEO_EXTENSIONS), \
        "Extension sets overlap!"
    results.ok("extension_sets_disjoint", f"total={len(all_ext)} unique extensions")

    # Verify known extensions route correctly by checking the suffix matching
    test_cases = [
        (".mp3", "audio"),
        (".wav", "audio"),
        (".flac", "audio"),
        (".jpg", "image"),
        (".png", "image"),
        (".tiff", "image"),
        (".mp4", "video"),
        (".avi", "video"),
        (".webm", "video"),
    ]
    for ext, expected_type in test_cases:
        if ext in AUDIO_EXTENSIONS:
            actual = "audio"
        elif ext in IMAGE_EXTENSIONS:
            actual = "image"
        elif ext in VIDEO_EXTENSIONS:
            actual = "video"
        else:
            actual = "unknown"

        if actual == expected_type:
            results.ok(f"route_{ext}", f"→ {actual}")
        else:
            results.fail(f"route_{ext}", f"Expected {expected_type}, got {actual}")


# ── Test 8: Folder Processor ────────────────────────────────────────────────

def test_folder_processor(results: TestResults):
    print(f"\n{CYAN}{BOLD}[8] Folder Processor (image/video roles){RESET}")

    # Ensure the ingestion/scripts version of profile_loader is cached
    # (not the backend one, which lacks get_folder_processing_config)
    import importlib
    if "profile_loader" in sys.modules:
        cached_file = getattr(sys.modules["profile_loader"], "__file__", "")
        if "backend" in cached_file:
            del sys.modules["profile_loader"]
    # Force-import from the scripts directory
    if "profile_loader" not in sys.modules:
        import importlib.util
        pl_path = SCRIPTS_DIR / "profile_loader.py"
        if pl_path.exists():
            spec = importlib.util.spec_from_file_location("profile_loader", str(pl_path))
            pl_mod = importlib.util.module_from_spec(spec)
            sys.modules["profile_loader"] = pl_mod
            spec.loader.exec_module(pl_mod)

    try:
        from folder_processor import (
            process_image_files,
            process_video_files,
            prepare_structured_text,
        )
        results.ok("folder_processor new functions import")
    except ImportError as e:
        results.fail("folder_processor import", str(e))
        return

    # Test prepare_structured_text with image and video content
    try:
        test_results = {
            "metadata": {"case": "test-001"},
            "participants": [],
            "image_descriptions": "--- Image: photo1.jpg ---\nA surveillance photo showing a building entrance.",
            "video_analysis": "=== VIDEO ANALYSIS ===\nSource: cam7.mp4\n\n=== VISUAL SCENE ANALYSIS ===\n[0s] Dark hallway",
        }

        # Test combined format
        text = prepare_structured_text("test_folder", test_results, "combined")
        assert "surveillance photo" in text, "Combined text missing image content"
        assert "VIDEO ANALYSIS" in text, "Combined text missing video content"
        results.ok("prepare_structured_text(combined)", f"{len(text)} chars with image+video")

        # Test media_structured format
        text = prepare_structured_text("test_folder", test_results, "media_structured")
        assert "=== IMAGE ANALYSIS ===" in text, "media_structured missing IMAGE ANALYSIS section"
        assert "=== VIDEO ANALYSIS ===" in text, "media_structured missing VIDEO ANALYSIS section"
        assert "EVIDENCE FOLDER" in text, "media_structured missing header"
        results.ok("prepare_structured_text(media_structured)", f"{len(text)} chars with sections")

    except Exception as e:
        results.fail("prepare_structured_text", str(e))

    # Test process_image_files with real images
    test_img = TEST_MEDIA_DIR / "evidence_document_ocr.png"
    if test_img.exists():
        try:
            result = process_image_files(
                [test_img],
                {"provider": "tesseract"},
                log_callback=lambda msg: None,
            )
            if "image_descriptions" in result:
                results.ok(
                    "process_image_files",
                    f"{len(result['image_descriptions'])} chars extracted"
                )
            else:
                results.fail("process_image_files", "No image_descriptions in result")
        except Exception as e:
            results.fail("process_image_files", str(e))
    else:
        results.skip("process_image_files", "Test image not available")


# ── Test 9: Frontend API Contract ────────────────────────────────────────────

def test_frontend_contract(results: TestResults):
    print(f"\n{CYAN}{BOLD}[9] Frontend API Contract{RESET}")

    # Check that the API endpoint expects image_provider parameter
    evidence_router = SCRIPTS_DIR.parent.parent / "backend" / "routers" / "evidence.py"
    if evidence_router.exists():
        content = evidence_router.read_text()
        if "image_provider" in content:
            results.ok("evidence.py has image_provider field")
        else:
            results.fail("evidence.py missing image_provider", "ProcessRequest should have image_provider field")
    else:
        results.skip("evidence.py check", "File not found")

    # Check that evidence_service passes image_provider
    evidence_service = SCRIPTS_DIR.parent.parent / "backend" / "services" / "evidence_service.py"
    if evidence_service.exists():
        content = evidence_service.read_text()
        if "image_provider" in content:
            results.ok("evidence_service.py has image_provider")
        else:
            results.fail("evidence_service.py missing image_provider", "Should pass image_provider through")
    else:
        results.skip("evidence_service.py check", "File not found")

    # Check frontend api.js
    api_js = SCRIPTS_DIR.parent.parent / "frontend" / "src" / "services" / "api.js"
    if api_js.exists():
        content = api_js.read_text()
        if "image_provider" in content:
            results.ok("api.js sends image_provider")
        else:
            results.fail("api.js missing image_provider", "processBackground should send image_provider")
    else:
        results.skip("api.js check", "File not found")

    # Check frontend component has imageProvider state
    component = SCRIPTS_DIR.parent.parent / "frontend" / "src" / "components" / "EvidenceProcessingView.jsx"
    if component.exists():
        content = component.read_text()
        if "imageProvider" in content:
            results.ok("EvidenceProcessingView has imageProvider state")
        else:
            results.fail("EvidenceProcessingView missing imageProvider", "Should have imageProvider state")

        # Check for the selector UI
        if "Image OCR" in content or "Local (Tesseract)" in content:
            results.ok("EvidenceProcessingView has image provider selector UI")
        else:
            results.fail("EvidenceProcessingView missing selector", "Should have Image OCR dropdown")

        # Check for new file type extensions
        if "tiff" in content and "webm" in content and "wma" in content:
            results.ok("EvidenceProcessingView has extended file types")
        else:
            results.fail("EvidenceProcessingView missing extensions", "Should have tiff, webm, wma in getFileType")
    else:
        results.skip("EvidenceProcessingView check", "File not found")


# ── Test 10: Profile Generation Prompt ───────────────────────────────────────

def test_profile_prompt(results: TestResults):
    print(f"\n{CYAN}{BOLD}[10] Profile Generation Prompt{RESET}")

    evidence_router = SCRIPTS_DIR.parent.parent / "backend" / "routers" / "evidence.py"
    if not evidence_router.exists():
        results.skip("profile_prompt_image_role", "evidence.py not found")
        return

    content = evidence_router.read_text()

    # Check that the profile generation prompt includes image and video roles
    if '"image"' in content and '"video"' in content:
        results.ok("profile_prompt_has_image_video_roles")
    else:
        results.fail("profile_prompt_roles", "Should mention image and video roles")

    if "tesseract" in content.lower() and "vision" in content.lower():
        results.ok("profile_prompt_has_provider_options", "Mentions tesseract and vision")
    else:
        results.fail("profile_prompt_providers", "Should mention tesseract and vision providers")

    if "media_structured" in content:
        results.ok("profile_prompt_has_media_structured_format")
    else:
        results.fail("profile_prompt_format", "Should mention media_structured output format")


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Test media processing features")
    parser.add_argument("--quick", action="store_true", help="Skip slow tests (Whisper, Vision API)")
    parser.add_argument("--verbose", action="store_true", help="Extra debug output")
    args = parser.parse_args()

    print(f"\n{BOLD}{'=' * 60}{RESET}")
    print(f"{BOLD}MEDIA PROCESSING TEST SUITE{RESET}")
    print(f"{'=' * 60}")
    print(f"Mode: {'QUICK' if args.quick else 'FULL'}")
    print(f"Test media dir: {TEST_MEDIA_DIR}")

    if not TEST_MEDIA_DIR.exists():
        print(f"\n{YELLOW}WARNING: Test media directory not found!{RESET}")
        print(f"Run generate_test_media.py first to create test files:")
        print(f"  python {Path(__file__).parent / 'generate_test_media.py'}")
        print()

    results = TestResults()

    # Run all test groups
    test_config(results)
    test_image_processor(results, quick=args.quick)
    test_image_ingestion(results)
    test_audio_ingestion(results, quick=args.quick)
    test_video_processor(results, quick=args.quick)
    test_video_ingestion(results)
    test_file_routing(results)
    test_folder_processor(results)
    test_frontend_contract(results)
    test_profile_prompt(results)

    # Print summary and exit
    all_pass = results.summary()
    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
