"""Video key frames follow the image setting, and every part not read is counted and said.

Before: every frame went to OpenAI vision whatever ``image_provider`` said (Tesseract is the default), a frame
that failed was logged and dropped, and a failed audio transcription was dropped too, so the document read as
complete.
"""

from pathlib import Path

import pytest

from app.pipeline import extract_text as module
from app.pipeline.extract_text import ExtractedDocument


def _frames(tmp_path: Path, count: int) -> list[dict]:
    frames = []
    for i in range(count):
        path = tmp_path / f"frame_{i:04d}.jpg"
        path.write_bytes(b"jpg")
        t = i * 30
        frames.append({"path": str(path), "timestamp_seconds": t, "timestamp_str": f"{t // 60:02d}:{t % 60:02d}"})
    return frames


@pytest.fixture
def video(monkeypatch, tmp_path):
    state = {"vision_calls": 0, "ocr_calls": 0, "frames": _frames(tmp_path, 4), "audio": None,
             "has_audio": True, "ocr": lambda path: "PLATE ABC123", "vision": None}

    monkeypatch.setattr(module, "_get_video_metadata",
                        lambda path: {"file_type": "video", "has_audio": state["has_audio"]})
    monkeypatch.setattr(module, "_extract_key_frames", lambda path, out: state["frames"])

    def audio_track(path, out):
        return None if state["audio"] == "no_track" else str(tmp_path / "audio.wav")

    monkeypatch.setattr(module, "_extract_audio_track", audio_track)

    async def extract_audio(path, progress_callback=None):
        if isinstance(state["audio"], Exception):
            raise state["audio"]
        return ExtractedDocument(text=state["audio"] or "", metadata={})

    monkeypatch.setattr(module, "_extract_audio", extract_audio)

    def ocr(path):
        state["ocr_calls"] += 1
        return state["ocr"](path)

    async def vision(path, name):
        state["vision_calls"] += 1
        if state["vision"] is not None:
            return state["vision"](path)
        return "a person by a car"

    monkeypatch.setattr(module, "_extract_text_tesseract", ocr)
    monkeypatch.setattr(module, "_describe_image_vision", vision)
    return state


async def test_frames_use_tesseract_when_the_setting_is_local(monkeypatch, video):
    monkeypatch.setattr(module.settings, "image_provider", "tesseract")
    video["audio"] = "hello"
    doc = await module._extract_video("v.mp4", "v.mp4")
    assert video["vision_calls"] == 0
    assert video["ocr_calls"] == 4
    assert doc.metadata["frame_provider"] == "tesseract"
    assert doc.metadata["frames_failed"] == 0
    assert "[Video Frame Text (OCR)]" in doc.text
    assert "PLATE ABC123" in doc.text
    assert "extraction_incomplete" not in doc.metadata
    assert "[Not Read]" not in doc.text


async def test_frames_use_vision_only_when_the_setting_says_openai(monkeypatch, video):
    monkeypatch.setattr(module.settings, "image_provider", "openai")
    video["audio"] = "hello"
    doc = await module._extract_video("v.mp4", "v.mp4")
    assert video["vision_calls"] == 4
    assert video["ocr_calls"] == 0
    assert "[Video Frame Descriptions]" in doc.text


async def test_failed_frames_are_counted_and_stated(monkeypatch, video):
    monkeypatch.setattr(module.settings, "image_provider", "openai")
    video["audio"] = "hello"
    calls = {"n": 0}

    def flaky(path):
        calls["n"] += 1
        if calls["n"] <= 3:
            raise RuntimeError("Error code: 429 - insufficient_quota")
        return "a person by a car"

    video["vision"] = flaky
    doc = await module._extract_video("v.mp4", "v.mp4")
    assert doc.metadata["frames_failed"] == 3
    assert doc.metadata["frames_read"] == 1
    assert doc.metadata["extraction_incomplete"] is True
    assert "3 of 4 frames could not be read: Error code: 429 - insufficient_quota (3 frames)" in doc.text
    assert doc.text.startswith("[Not Read]")


async def test_failed_audio_transcription_is_stated(monkeypatch, video):
    monkeypatch.setattr(module.settings, "image_provider", "tesseract")
    video["audio"] = RuntimeError("Error code: 429 - insufficient_quota")
    doc = await module._extract_video("v.mp4", "v.mp4")
    assert doc.metadata["transcription_status"] == "failed"
    assert doc.metadata["transcription_error"] == "Error code: 429 - insufficient_quota"
    assert "The audio track could not be transcribed: Error code: 429 - insufficient_quota" in doc.text
    assert doc.metadata["extraction_incomplete"] is True


async def test_audio_track_that_could_not_be_taken_out_is_stated(monkeypatch, video):
    monkeypatch.setattr(module.settings, "image_provider", "tesseract")
    video["audio"] = "no_track"
    doc = await module._extract_video("v.mp4", "v.mp4")
    assert doc.metadata["transcription_status"] == "failed"
    assert "audio track could not be extracted" in doc.text


async def test_silent_video_without_audio_is_not_a_failure(monkeypatch, video):
    monkeypatch.setattr(module.settings, "image_provider", "tesseract")
    video["audio"] = "no_track"
    video["has_audio"] = False
    doc = await module._extract_video("v.mp4", "v.mp4")
    assert doc.metadata["transcription_status"] == "no_audio_track"
    assert "extraction_incomplete" not in doc.metadata


async def test_frames_without_text_are_said_not_hidden(monkeypatch, video):
    monkeypatch.setattr(module.settings, "image_provider", "tesseract")
    video["audio"] = "hello"
    video["ocr"] = lambda path: ""
    doc = await module._extract_video("v.mp4", "v.mp4")
    assert doc.metadata["frames_without_text"] == 4
    assert doc.metadata["frames_failed"] == 0
    assert "4 of 4 frames were read and had no readable text." in doc.text


async def test_frame_extraction_failure_is_stated(monkeypatch, video):
    monkeypatch.setattr(module.settings, "image_provider", "tesseract")
    video["audio"] = "hello"

    def broken(path, out):
        raise RuntimeError("ffmpeg exited 1")

    monkeypatch.setattr(module, "_extract_key_frames", broken)
    doc = await module._extract_video("v.mp4", "v.mp4")
    assert doc.metadata["frame_count"] == 0
    assert "No frames could be taken from the video: ffmpeg exited 1" in doc.text


async def test_audio_without_speech_is_recorded_not_written_into_the_text(monkeypatch, video):
    monkeypatch.setattr(module.settings, "image_provider", "tesseract")
    video["audio"] = ""
    doc = await module._extract_video("v.mp4", "v.mp4")
    assert doc.metadata["transcription_status"] == "no_speech"
    assert "extraction_incomplete" not in doc.metadata
    assert "speech" not in doc.text
