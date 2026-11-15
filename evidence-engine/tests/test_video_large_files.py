"""Large videos are processed: frames span the whole recording, each taken by a seek, and the size limit matches
the backend's.

Before (12-15 Nov): the engine refused any file over 1 GiB that the backend had accepted (up to 64 GB), so a
1.32 GB body-cam video and a 3.3 GB drone video failed. Frames were taken by decoding the video up to the last
frame within a fixed 300 s, and only every 30 s up to 50 frames: an 81-minute video was read for its first
25 minutes and nothing said the rest was not read.
"""

import shutil
import subprocess
import uuid
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, UploadFile

from app.api.routes.upload import upload_files
from app.config import Settings, settings
from app.pipeline import extract_text as module

BACKEND_LIMIT = 64 * 1024**3  # backend/services/evidence_archive.py MAX_EXPANDED_BYTES


def test_the_engine_processes_every_file_the_backend_accepts():
    defaults = Settings.model_fields
    assert defaults["max_upload_file_bytes"].default >= BACKEND_LIMIT
    assert defaults["max_upload_batch_bytes"].default >= BACKEND_LIMIT
    compose = (Path(__file__).resolve().parents[2] / "docker-compose.yml").read_text()
    assert "MAX_UPLOAD_FILE_BYTES:-1073741824" not in compose
    assert compose.count(f"MAX_UPLOAD_FILE_BYTES:-{BACKEND_LIMIT}") == 2
    assert compose.count(f"MAX_UPLOAD_BATCH_BYTES:-{BACKEND_LIMIT}") == 2


def test_frame_times_span_an_81_minute_video_to_its_end():
    times = module._frame_times(4864.3, 30, 50)
    assert len(times) == 50
    assert times[0] == 0
    assert times[-1] > 4864 - 120  # the last frame is near the end, not at minute 25
    assert module._frame_times(300, 30, 50) == list(range(0, 300, 30))  # short videos keep every 30 s


def test_clock_shows_hours_past_the_first():
    assert module._clock(75) == "01:15"
    assert module._clock(4800) == "1:20:00"


def test_each_frame_is_taken_by_a_seek_and_a_failed_one_is_returned_with_its_reason(monkeypatch, tmp_path):
    monkeypatch.setattr(module, "_probe_media_duration_seconds", lambda path: 4864.3)
    monkeypatch.setattr(module.settings, "video_frame_interval", 30)
    monkeypatch.setattr(module.settings, "video_max_frames", 50)
    calls = []

    def run(cmd, **kwargs):
        calls.append(cmd)
        assert kwargs["timeout"] == module.VIDEO_FRAME_TIMEOUT_SECONDS
        if len(calls) == 2:
            raise subprocess.TimeoutExpired(cmd, kwargs["timeout"])
        Path(cmd[-1]).write_bytes(b"jpg")

    monkeypatch.setattr(module.subprocess, "run", run)
    frames = module._extract_key_frames("v.mp4", str(tmp_path))
    assert len(calls) == 50
    assert all(c[c.index("-ss") + 1] == str(f["timestamp_seconds"]) and c.index("-ss") < c.index("-i")
               for c, f in zip(calls, frames))
    assert frames[1]["error"] == "taking the frame ran past 120 s"
    assert sum(1 for f in frames if "error" in f) == 1


async def test_a_frame_not_taken_is_counted_and_said(monkeypatch, tmp_path):
    good = tmp_path / "frame_0001.jpg"
    good.write_bytes(b"jpg")
    frames = [{"path": str(good), "timestamp_seconds": 0, "timestamp_str": "00:00"},
              {"path": str(tmp_path / "frame_0002.jpg"), "timestamp_seconds": 30, "timestamp_str": "00:30",
               "error": "ffmpeg wrote no picture at this time"}]
    monkeypatch.setattr(module, "_get_video_metadata", lambda path: {"file_type": "video"})
    monkeypatch.setattr(module, "_extract_key_frames", lambda path, out: frames)
    monkeypatch.setattr(module, "_extract_audio_track", lambda path, out: None)
    monkeypatch.setattr(module, "_extract_text_tesseract", lambda path: "PLATE")
    monkeypatch.setattr(module.settings, "image_provider", "tesseract")
    doc = await module._extract_video("v.mp4", "v.mp4")
    assert doc.metadata["frame_count"] == 2
    assert doc.metadata["frames_failed"] == 1
    assert "1 of 2 frames could not be read: frame not taken: ffmpeg wrote no picture at this time" in doc.text


def test_audio_track_time_allowed_grows_with_the_recording(monkeypatch):
    monkeypatch.setattr(module, "_probe_media_duration_seconds", lambda path: 4864.3)
    assert module._media_timeout_seconds("v.mp4") == 4864 + 300
    monkeypatch.setattr(module, "_probe_media_duration_seconds", lambda path: None)
    assert module._media_timeout_seconds("v.mp4") == 300


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="needs ffmpeg")
def test_real_ffmpeg_takes_frames_across_a_whole_video(monkeypatch, tmp_path):
    video = tmp_path / "long.mp4"
    subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-f", "lavfi", "-i",
                    "testsrc=size=160x120:rate=5:duration=180", "-g", "25", str(video)], check=True)
    monkeypatch.setattr(module.settings, "video_frame_interval", 30)
    monkeypatch.setattr(module.settings, "video_max_frames", 3)
    out = tmp_path / "frames"
    out.mkdir()
    frames = module._extract_key_frames(str(video), str(out))
    assert [f["timestamp_seconds"] for f in frames] == [0, 60, 120]
    assert all("error" not in f and Path(f["path"]).stat().st_size > 0 for f in frames)


async def test_an_oversized_file_is_refused_in_plain_words(monkeypatch, tmp_path):
    class FakeDb:
        def add(self, job):
            pass

        async def rollback(self):
            pass

    monkeypatch.setattr(settings, "storage_path", str(tmp_path))
    monkeypatch.setattr(settings, "upload_read_chunk_bytes", 1024)
    big = BytesIO(b"x" * 2048)
    monkeypatch.setattr(settings, "max_upload_file_bytes", 1024)
    with pytest.raises(HTTPException) as exc:
        await upload_files(case_id=str(uuid.uuid4()), request=SimpleNamespace(),
                           files=[UploadFile(file=big, filename="body-cam.mp4")], processing_metadata=None,
                           db=FakeDb())
    assert exc.value.status_code == 413
    assert "byte" not in exc.value.detail
    assert exc.value.detail.startswith("body-cam.mp4 is larger than the ")
    assert "Split the recording into shorter parts" in exc.value.detail
