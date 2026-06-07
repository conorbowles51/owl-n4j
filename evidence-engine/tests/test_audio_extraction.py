from pathlib import Path

import pytest

from app.pipeline import extract_text as extract_text_module
from app.pipeline.extract_text import AudioTranscriptionError


class InputTooLargeError(Exception):
    code = "input_too_large"


@pytest.fixture(autouse=True)
def audio_transcription_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        extract_text_module.settings,
        "audio_transcription_segment_seconds",
        240,
    )
    monkeypatch.setattr(
        extract_text_module.settings,
        "audio_transcription_max_single_seconds",
        240,
    )


@pytest.mark.asyncio
async def test_short_audio_uses_single_transcription_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    audio_file = tmp_path / "short.mp3"
    audio_file.write_bytes(b"small audio")
    calls: list[dict[str, str | None]] = []

    monkeypatch.setattr(extract_text_module, "_probe_media_duration_seconds", lambda _: 30.0)

    def fail_split(*_args, **_kwargs):
        pytest.fail("short audio should not be split")

    async def fake_transcribe(file_path: str, prompt: str | None = None) -> str:
        calls.append({"path": file_path, "prompt": prompt})
        return "short transcript"

    monkeypatch.setattr(extract_text_module, "_split_audio_segments", fail_split)
    monkeypatch.setattr(extract_text_module, "transcribe_audio", fake_transcribe)

    doc = await extract_text_module._extract_audio(str(audio_file))

    assert doc.text == "short transcript"
    assert doc.metadata["transcription"] == "short transcript"
    assert doc.metadata["segment_count"] == 1
    assert doc.metadata["duration_seconds"] == 30.0
    assert calls == [{"path": str(audio_file), "prompt": None}]


@pytest.mark.asyncio
async def test_long_audio_is_split_by_duration_and_context_is_prompted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    audio_file = tmp_path / "long-small.mp3"
    audio_file.write_bytes(b"small but long audio")
    created_segments: list[Path] = []
    calls: list[dict[str, str | None]] = []

    monkeypatch.setattr(extract_text_module, "_probe_media_duration_seconds", lambda _: 1500.0)

    def fake_split(file_path: str, output_dir: str, segment_seconds: int) -> list[Path]:
        assert file_path == str(audio_file)
        assert segment_seconds == 240
        segments: list[Path] = []
        for index in range(3):
            segment = Path(output_dir) / f"segment_{index:03d}.mp3"
            segment.write_bytes(f"segment {index}".encode("utf-8"))
            segments.append(segment)
        created_segments.extend(segments)
        return segments

    async def fake_transcribe(file_path: str, prompt: str | None = None) -> str:
        transcript = f"transcript {Path(file_path).stem}"
        calls.append({"path": file_path, "prompt": prompt})
        return transcript

    monkeypatch.setattr(extract_text_module, "_split_audio_segments", fake_split)
    monkeypatch.setattr(extract_text_module, "transcribe_audio", fake_transcribe)

    doc = await extract_text_module._extract_audio(str(audio_file))

    assert doc.text == "transcript segment_000\n\ntranscript segment_001\n\ntranscript segment_002"
    assert doc.metadata["segment_count"] == 3
    assert doc.metadata["segment_seconds"] == 240
    assert doc.metadata["duration_seconds"] == 1500.0
    assert calls[0]["prompt"] is None
    assert calls[1]["prompt"] is not None
    assert calls[2]["prompt"] is not None
    assert "transcript segment_000" in calls[1]["prompt"]
    assert "transcript segment_001" in calls[2]["prompt"]
    assert all(not segment.exists() for segment in created_segments)


@pytest.mark.asyncio
async def test_large_audio_splits_when_duration_probe_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    audio_file = tmp_path / "large-unknown-duration.mp3"
    audio_file.write_bytes(b"large enough for test")
    split_calls: list[int] = []

    monkeypatch.setattr(extract_text_module, "MAX_WHISPER_SIZE", 1)
    monkeypatch.setattr(extract_text_module, "_probe_media_duration_seconds", lambda _: None)

    def fake_split(_file_path: str, output_dir: str, segment_seconds: int) -> list[Path]:
        split_calls.append(segment_seconds)
        segment = Path(output_dir) / "segment_000.mp3"
        segment.write_bytes(b"segment")
        return [segment]

    async def fake_transcribe(_file_path: str, prompt: str | None = None) -> str:
        assert prompt is None
        return "large transcript"

    monkeypatch.setattr(extract_text_module, "_split_audio_segments", fake_split)
    monkeypatch.setattr(extract_text_module, "transcribe_audio", fake_transcribe)

    doc = await extract_text_module._extract_audio(str(audio_file))

    assert doc.text == "large transcript"
    assert doc.metadata["segment_count"] == 1
    assert doc.metadata["segment_seconds"] == 240
    assert "duration_seconds" not in doc.metadata
    assert split_calls == [240]


@pytest.mark.asyncio
async def test_too_large_segment_retries_with_smaller_chunks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    audio_file = tmp_path / "retry.mp3"
    audio_file.write_bytes(b"long audio")
    split_calls: list[tuple[str, int]] = []
    calls: list[dict[str, str | None]] = []

    monkeypatch.setattr(extract_text_module, "_probe_media_duration_seconds", lambda _: 600.0)

    def fake_split(file_path: str, output_dir: str, segment_seconds: int) -> list[Path]:
        split_calls.append((Path(file_path).name, segment_seconds))
        if segment_seconds == 240:
            segment_names = ["segment_000.mp3"]
        else:
            segment_names = ["segment_000_retry_000.mp3", "segment_000_retry_001.mp3"]
        segments: list[Path] = []
        for name in segment_names:
            segment = Path(output_dir) / name
            segment.write_bytes(name.encode("utf-8"))
            segments.append(segment)
        return segments

    async def fake_transcribe(file_path: str, prompt: str | None = None) -> str:
        calls.append({"path": file_path, "prompt": prompt})
        if Path(file_path).name == "segment_000.mp3":
            raise InputTooLargeError("chunk too large")
        return f"transcript {Path(file_path).stem}"

    monkeypatch.setattr(extract_text_module, "_split_audio_segments", fake_split)
    monkeypatch.setattr(extract_text_module, "transcribe_audio", fake_transcribe)

    doc = await extract_text_module._extract_audio(str(audio_file))

    assert split_calls == [("retry.mp3", 240), ("segment_000.mp3", 120)]
    assert doc.text == "transcript segment_000_retry_000\n\ntranscript segment_000_retry_001"
    assert doc.metadata["segment_count"] == 2
    assert calls[-1]["prompt"] is not None
    assert "transcript segment_000_retry_000" in calls[-1]["prompt"]


@pytest.mark.asyncio
async def test_segment_failure_message_identifies_chunk(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    audio_file = tmp_path / "failure.mp3"
    audio_file.write_bytes(b"long audio")

    monkeypatch.setattr(
        extract_text_module.settings,
        "audio_transcription_segment_seconds",
        60,
    )
    monkeypatch.setattr(extract_text_module, "_probe_media_duration_seconds", lambda _: 600.0)

    def fake_split(_file_path: str, output_dir: str, _segment_seconds: int) -> list[Path]:
        segment = Path(output_dir) / "segment_000.mp3"
        segment.write_bytes(b"segment")
        return [segment]

    async def fake_transcribe(_file_path: str, prompt: str | None = None) -> str:
        raise InputTooLargeError("still too large")

    monkeypatch.setattr(extract_text_module, "_split_audio_segments", fake_split)
    monkeypatch.setattr(extract_text_module, "transcribe_audio", fake_transcribe)

    with pytest.raises(AudioTranscriptionError, match="segment 1/1"):
        await extract_text_module._extract_audio(str(audio_file))
