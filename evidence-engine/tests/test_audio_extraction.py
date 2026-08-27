from pathlib import Path
from types import SimpleNamespace

import pytest

from app.pipeline import extract_text as extract_text_module
from app.pipeline.extract_text import AudioTranscriptionError
from app.services import openai_client as openai_client_module
from app.services.openai_client import (
    AudioTranscriptionProgress,
    AudioTranscriptionResult,
)


class InputTooLargeError(Exception):
    code = "input_too_large"


class AudioDurationTooLongError(Exception):
    code = "invalid_value"
    body = {
        "message": (
            "audio duration 1511.141875 seconds is longer than 1400 seconds "
            "which is the maximum for this model"
        ),
        "type": "invalid_request_error",
        "param": None,
        "code": "invalid_value",
    }


@pytest.fixture(autouse=True)
def audio_transcription_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        extract_text_module.settings,
        "audio_transcription_segment_seconds",
        240,
    )
    monkeypatch.setattr(
        extract_text_module.settings,
        "openai_transcription_model",
        "gpt-4o-mini-transcribe",
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

    async def fake_transcribe(
        file_path: str, prompt: str | None = None, **_kwargs: object
    ) -> str:
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
async def test_structured_transcription_preserves_speaker_timestamps(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    audio_file = tmp_path / "interview.mp3"
    audio_file.write_bytes(b"small audio")
    monkeypatch.setattr(extract_text_module, "_probe_media_duration_seconds", lambda _: 30.0)
    monkeypatch.setattr(
        extract_text_module.settings,
        "openai_transcription_model",
        "gpt-4o-transcribe-diarize",
    )

    async def fake_transcribe(*_args: object, **_kwargs: object) -> AudioTranscriptionResult:
        return AudioTranscriptionResult(
            text="Hello. Hi there.",
            segments=[
                {"id": "seg_1", "start": 0.0, "end": 1.2, "speaker": "A", "text": "Hello."},
                {"id": "seg_2", "start": 1.2, "end": 2.4, "speaker": "B", "text": "Hi there."},
            ],
            duration_seconds=30.0,
            model="gpt-4o-transcribe-diarize",
        )

    monkeypatch.setattr(extract_text_module, "transcribe_audio", fake_transcribe)

    doc = await extract_text_module._extract_audio(str(audio_file))

    assert doc.text == "Hello. Hi there."
    assert doc.metadata["transcription_segments"][1]["speaker"] == "B"
    assert doc.metadata["transcription_segments"][1]["start"] == 1.2
    assert doc.metadata["transcription_model"] == "gpt-4o-transcribe-diarize"


@pytest.mark.asyncio
async def test_audio_extraction_forwards_live_transcription_progress(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    audio_file = tmp_path / "progress.mp3"
    audio_file.write_bytes(b"small audio")
    updates: list[AudioTranscriptionProgress] = []
    monkeypatch.setattr(extract_text_module, "_probe_media_duration_seconds", lambda _: 60.0)
    monkeypatch.setattr(
        extract_text_module.settings,
        "openai_transcription_model",
        "gpt-4o-transcribe-diarize",
    )

    async def fake_transcribe(
        *_args: object,
        progress_callback=None,
        **kwargs: object,
    ) -> AudioTranscriptionResult:
        assert kwargs["duration_seconds"] == 60.0
        assert kwargs["progress_total_seconds"] == 60.0
        assert progress_callback is not None
        await progress_callback(
            AudioTranscriptionProgress(
                message="Transcribing audio...",
                completed=30.0,
                total=60.0,
            )
        )
        return AudioTranscriptionResult(
            text="Halfway there.",
            segments=[],
            duration_seconds=60.0,
            model="gpt-4o-transcribe-diarize",
        )

    async def report_progress(update: AudioTranscriptionProgress) -> None:
        updates.append(update)

    monkeypatch.setattr(extract_text_module, "transcribe_audio", fake_transcribe)

    doc = await extract_text_module.extract_text(
        str(audio_file),
        audio_file.name,
        progress_callback=report_progress,
    )

    assert doc.text == "Halfway there."
    assert updates == [
        AudioTranscriptionProgress(
            message="Transcribing audio...",
            completed=30.0,
            total=60.0,
        )
    ]


@pytest.mark.asyncio
async def test_diarization_splits_long_recording_by_duration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    audio_file = tmp_path / "long-interview.mp3"
    audio_file.write_bytes(b"small audio")
    monkeypatch.setattr(
        extract_text_module.settings,
        "openai_transcription_model",
        "gpt-4o-transcribe-diarize",
    )
    split_calls: list[int] = []
    transcription_calls: list[str] = []

    def fake_probe(file_path: str) -> float:
        return 1800.0 if Path(file_path) == audio_file else 240.0

    def fake_split(_file_path: str, output_dir: str, segment_seconds: int) -> list[Path]:
        split_calls.append(segment_seconds)
        segments = [
            Path(output_dir) / "segment_000.mp3",
            Path(output_dir) / "segment_001.mp3",
        ]
        for segment in segments:
            segment.write_bytes(b"chunk")
        return segments

    async def fake_transcribe(file_path: str, **kwargs: object) -> AudioTranscriptionResult:
        transcription_calls.append(Path(file_path).name)
        offset = float(kwargs["time_offset_seconds"])
        return AudioTranscriptionResult(
            text=f"Chunk at {offset}",
            segments=[
                {
                    "id": f"seg_{offset}",
                    "start": offset,
                    "end": offset + 2.0,
                    "speaker": "A",
                    "text": f"Chunk at {offset}",
                }
            ],
            duration_seconds=240.0,
            model="gpt-4o-transcribe-diarize",
        )

    monkeypatch.setattr(extract_text_module, "_probe_media_duration_seconds", fake_probe)
    monkeypatch.setattr(extract_text_module, "_split_audio_segments", fake_split)
    monkeypatch.setattr(
        extract_text_module,
        "_build_speaker_reference_data_urls",
        lambda *_args, **_kwargs: {},
    )
    monkeypatch.setattr(extract_text_module, "transcribe_audio", fake_transcribe)

    doc = await extract_text_module._extract_audio(str(audio_file))

    assert split_calls == [240]
    assert transcription_calls == ["segment_000.mp3", "segment_001.mp3"]
    assert doc.metadata["segment_count"] == 2
    assert [segment["start"] for segment in doc.metadata["transcription_segments"]] == [
        0.0,
        240.0,
    ]


def test_openai_audio_duration_limit_error_is_recognized() -> None:
    error = AudioDurationTooLongError("Error code: 400")

    assert extract_text_module._is_input_too_large_error(error)


def test_speaker_reference_leaves_headroom_for_mp3_padding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    audio_file = tmp_path / "interview.mp3"
    audio_file.write_bytes(b"audio")
    captured_args: list[str] = []

    def fake_ffmpeg(args, **_kwargs):
        captured_args.extend(args)
        Path(args[-1]).write_bytes(b"validated-reference")
        return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

    monkeypatch.setattr(extract_text_module.subprocess, "run", fake_ffmpeg)
    monkeypatch.setattr(
        extract_text_module,
        "_probe_media_duration_seconds",
        lambda _path: 9.576,
    )

    references = extract_text_module._build_speaker_reference_data_urls(
        str(audio_file),
        [
            {
                "speaker": "A",
                "start": 0.0,
                "end": 20.0,
                "text": "A long speaker turn",
            }
        ],
        time_offset_seconds=0.0,
        existing_speakers=set(),
    )

    duration_arg = captured_args[captured_args.index("-t") + 1]
    assert duration_arg == "9.5"
    assert references["A"].startswith("data:audio/mpeg;base64,")


def test_speaker_reference_discards_invalid_encoded_duration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    audio_file = tmp_path / "interview.mp3"
    audio_file.write_bytes(b"audio")

    def fake_ffmpeg(args, **_kwargs):
        Path(args[-1]).write_bytes(b"overlong-reference")
        return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

    monkeypatch.setattr(extract_text_module.subprocess, "run", fake_ffmpeg)
    monkeypatch.setattr(
        extract_text_module,
        "_probe_media_duration_seconds",
        lambda _path: 10.08,
    )

    references = extract_text_module._build_speaker_reference_data_urls(
        str(audio_file),
        [{"speaker": "A", "start": 0.0, "end": 20.0, "text": "Speaker turn"}],
        time_offset_seconds=0.0,
        existing_speakers=set(),
    )

    assert references == {}


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

    async def fake_transcribe(
        file_path: str, prompt: str | None = None, **_kwargs: object
    ) -> str:
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

    async def fake_transcribe(
        _file_path: str, prompt: str | None = None, **_kwargs: object
    ) -> str:
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
async def test_chunked_diarization_reuses_voice_references_for_stable_speakers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    audio_file = tmp_path / "large-call.mp3"
    audio_file.write_bytes(b"large audio")
    captured_calls: list[dict] = []
    monkeypatch.setattr(extract_text_module, "MAX_WHISPER_SIZE", 1)
    monkeypatch.setattr(
        extract_text_module.settings,
        "openai_transcription_model",
        "gpt-4o-transcribe-diarize",
    )

    def fake_probe(file_path: str) -> float:
        if Path(file_path) == audio_file:
            return 480.0
        if Path(file_path).name == "reference.mp3":
            return 3.0
        return 240.0

    def fake_split(_file_path: str, output_dir: str, _seconds: int) -> list[Path]:
        segments = [
            Path(output_dir) / "segment_000.mp3",
            Path(output_dir) / "segment_001.mp3",
        ]
        for segment in segments:
            segment.write_bytes(b"chunk")
        return segments

    def fake_ffmpeg(args, **_kwargs):
        assert args[0] == "ffmpeg"
        Path(args[-1]).write_bytes(b"voice-reference")
        return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

    async def fake_transcribe(file_path: str, **kwargs: object) -> AudioTranscriptionResult:
        captured_calls.append({"path": file_path, **kwargs})
        offset = float(kwargs["time_offset_seconds"])
        return AudioTranscriptionResult(
            text=f"Chunk at {offset}",
            segments=[
                {
                    "id": f"segment-{offset}",
                    "start": offset,
                    "end": offset + 3.0,
                    "speaker": "A",
                    "text": f"Chunk at {offset}",
                }
            ],
            duration_seconds=240.0,
            model="gpt-4o-transcribe-diarize",
        )

    monkeypatch.setattr(extract_text_module, "_probe_media_duration_seconds", fake_probe)
    monkeypatch.setattr(extract_text_module, "_split_audio_segments", fake_split)
    monkeypatch.setattr(extract_text_module.subprocess, "run", fake_ffmpeg)
    monkeypatch.setattr(extract_text_module, "transcribe_audio", fake_transcribe)

    doc = await extract_text_module._extract_audio(str(audio_file))

    assert captured_calls[0]["known_speaker_references"] is None
    assert list(captured_calls[1]["known_speaker_references"]) == ["A"]
    assert captured_calls[1]["speaker_id_prefix"] == ""
    assert doc.metadata["speaker_reconciliation"] == "known_voice_references"
    assert {segment["speaker"] for segment in doc.metadata["transcription_segments"]} == {
        "A"
    }


@pytest.mark.asyncio
async def test_rejected_speaker_reference_retries_chunk_without_references(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    audio_file = tmp_path / "interview.mp3"
    audio_file.write_bytes(b"audio")
    calls: list[dict] = []
    monkeypatch.setattr(
        extract_text_module.settings,
        "openai_transcription_model",
        "gpt-4o-transcribe-diarize",
    )

    def fake_probe(file_path: str) -> float:
        return 480.0 if Path(file_path) == audio_file else 240.0

    def fake_split(_file_path: str, output_dir: str, _seconds: int) -> list[Path]:
        segments = [
            Path(output_dir) / "segment_000.mp3",
            Path(output_dir) / "segment_001.mp3",
        ]
        for segment in segments:
            segment.write_bytes(b"chunk")
        return segments

    async def fake_transcribe(file_path: str, **kwargs: object) -> AudioTranscriptionResult:
        call = {"path": Path(file_path).name, **kwargs}
        if isinstance(call["known_speaker_references"], dict):
            call["known_speaker_references"] = dict(call["known_speaker_references"])
        calls.append(call)
        if call["path"] == "segment_001.mp3" and call["known_speaker_references"]:
            raise openai_client_module.AudioTranscriptionRequestError(
                "Error code: 400 - {'error': {'message': 'Known speaker references "
                "has duration {duration_s} seconds, but must be between 1.2 and "
                "10.0 seconds', 'type': 'invalid_request_error', "
                "'param': 'known_speaker_references', 'code': 'invalid_value'}}",
                retryable=False,
                stream_started=False,
            )
        offset = float(kwargs["time_offset_seconds"])
        return AudioTranscriptionResult(
            text=f"Chunk at {offset}",
            segments=[
                {
                    "id": f"segment-{offset}",
                    "start": offset,
                    "end": offset + 3.0,
                    "speaker": f"{kwargs['speaker_id_prefix']}A",
                    "text": f"Chunk at {offset}",
                }
            ],
            duration_seconds=240.0,
            model="gpt-4o-transcribe-diarize",
        )

    monkeypatch.setattr(extract_text_module, "_probe_media_duration_seconds", fake_probe)
    monkeypatch.setattr(extract_text_module, "_split_audio_segments", fake_split)
    monkeypatch.setattr(
        extract_text_module,
        "_build_speaker_reference_data_urls",
        lambda *_args, **_kwargs: {"A": "data:audio/mpeg;base64,cmVm"},
    )
    monkeypatch.setattr(extract_text_module, "transcribe_audio", fake_transcribe)

    doc = await extract_text_module._extract_audio(str(audio_file))

    assert [call["path"] for call in calls] == [
        "segment_000.mp3",
        "segment_001.mp3",
        "segment_001.mp3",
    ]
    assert calls[1]["known_speaker_references"] == {
        "A": "data:audio/mpeg;base64,cmVm"
    }
    assert calls[2]["known_speaker_references"] is None
    assert calls[2]["speaker_id_prefix"] == "chunk_240000:"
    assert doc.metadata["segment_count"] == 2
    assert doc.metadata["speaker_reconciliation"] == "chunk_scoped"


@pytest.mark.asyncio
async def test_diarization_timeout_before_first_event_falls_back_to_local_chunks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    audio_file = tmp_path / "slow-call.mp3"
    audio_file.write_bytes(b"audio")
    calls: list[str] = []
    monkeypatch.setattr(extract_text_module, "_probe_media_duration_seconds", lambda _: 120.0)
    monkeypatch.setattr(
        extract_text_module.settings,
        "openai_transcription_model",
        "gpt-4o-transcribe-diarize",
    )

    def fake_split(_file_path: str, output_dir: str, _seconds: int) -> list[Path]:
        segment = Path(output_dir) / "segment_000.mp3"
        segment.write_bytes(b"chunk")
        return [segment]

    async def fake_transcribe(file_path: str, **_kwargs: object) -> AudioTranscriptionResult:
        calls.append(Path(file_path).name)
        if Path(file_path) == audio_file:
            raise openai_client_module.AudioTranscriptionRequestError(
                "Request timed out before transcription began",
                retryable=True,
                stream_started=False,
            )
        return AudioTranscriptionResult(
            text="Recovered from a local chunk.",
            segments=[],
            duration_seconds=240.0,
            model="gpt-4o-transcribe-diarize",
        )

    monkeypatch.setattr(extract_text_module, "_split_audio_segments", fake_split)
    monkeypatch.setattr(extract_text_module, "transcribe_audio", fake_transcribe)

    doc = await extract_text_module._extract_audio(str(audio_file))

    assert calls == ["slow-call.mp3", "segment_000.mp3"]
    assert doc.text == "Recovered from a local chunk."
    assert doc.metadata["transcription_fallback"] == "local_chunks_after_stream_timeout"


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

    async def fake_transcribe(
        file_path: str, prompt: str | None = None, **_kwargs: object
    ) -> str:
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

    async def fake_transcribe(
        _file_path: str, prompt: str | None = None, **_kwargs: object
    ) -> str:
        raise InputTooLargeError("still too large")

    monkeypatch.setattr(extract_text_module, "_split_audio_segments", fake_split)
    monkeypatch.setattr(extract_text_module, "transcribe_audio", fake_transcribe)

    with pytest.raises(AudioTranscriptionError, match="segment 1/1"):
        await extract_text_module._extract_audio(str(audio_file))
