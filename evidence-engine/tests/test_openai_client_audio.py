from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services import openai_client


class FakeTranscriptionResponse:
    text = "Good morning."
    usage = {"input_tokens": 10, "output_tokens": 3, "total_tokens": 13}

    def model_dump(self) -> dict:
        return {
            "text": self.text,
            "segments": [
                {
                    "id": "seg_1",
                    "start": 0.25,
                    "end": 1.5,
                    "speaker": "A",
                    "text": "Good morning.",
                }
            ],
        }


class FakeTranscriptionStream:
    def __init__(self, events: list[dict]) -> None:
        self._events = events

    def __aiter__(self):
        return self._iterate()

    async def _iterate(self):
        for event in self._events:
            yield event


@pytest.mark.asyncio
async def test_diarization_streams_speaker_segments_without_automatic_retries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    audio_file = tmp_path / "call.mp3"
    audio_file.write_bytes(b"audio")
    captured: dict = {}
    client_options: dict = {}
    progress_updates: list[tuple[float, float, str]] = []

    async def fake_create(**kwargs):
        captured.update(kwargs)
        return FakeTranscriptionStream(
            [
                {
                    "type": "transcript.text.delta",
                    "delta": "Good ",
                    "segment_id": "seg_1",
                },
                {
                    "type": "transcript.text.delta",
                    "delta": "morning.",
                    "segment_id": "seg_1",
                },
                {
                    "type": "transcript.text.segment",
                    "id": "seg_1",
                    "start": 0.25,
                    "end": 1.5,
                    "speaker": "A",
                    "text": "Good morning.",
                },
                {
                    "type": "transcript.text.done",
                    "text": "Good morning.",
                    "usage": {
                        "input_tokens": 10,
                        "output_tokens": 3,
                        "total_tokens": 13,
                    },
                },
            ]
        )

    fake_client = SimpleNamespace(
        audio=SimpleNamespace(
            transcriptions=SimpleNamespace(create=fake_create)
        )
    )
    fake_client.with_options = lambda **kwargs: (
        client_options.update(kwargs) or fake_client
    )

    async def fake_record_cost(**_kwargs):
        return None

    async def report_progress(update) -> None:
        progress_updates.append((update.completed, update.total, update.message))

    monkeypatch.setattr(openai_client, "get_openai_client", lambda: fake_client)
    monkeypatch.setattr(
        openai_client.settings,
        "openai_transcription_model",
        "gpt-4o-transcribe-diarize",
    )
    monkeypatch.setattr(
        openai_client.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=1, stdout=""),
    )
    monkeypatch.setattr(openai_client, "record_openai_cost", fake_record_cost)

    result = await openai_client.transcribe_audio(
        str(audio_file),
        prompt="ignored by the diarization model",
        time_offset_seconds=120,
        segment_id_prefix="chunk_120000_",
        speaker_id_prefix="chunk_120000:",
        duration_seconds=30,
        progress_total_seconds=180,
        progress_callback=report_progress,
    )

    assert client_options["max_retries"] == 0
    assert captured["model"] == "gpt-4o-transcribe-diarize"
    assert captured["response_format"] == "diarized_json"
    assert captured["chunking_strategy"] == "auto"
    assert captured["stream"] is True
    assert "prompt" not in captured
    assert result.text == "Good morning."
    assert result.segments == [
        {
            "id": "chunk_120000_seg_1",
            "start": 120.25,
            "end": 121.5,
            "speaker": "chunk_120000:A",
            "text": "Good morning.",
        }
    ]
    assert progress_updates[0][2] == "Uploading audio for transcription..."
    assert sum(message == "Audio transcription started" for _, _, message in progress_updates) == 1
    assert progress_updates[-1] == (150, 180, "Audio transcription complete")


@pytest.mark.asyncio
async def test_diarization_sends_known_speaker_references_for_chunk_reconciliation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    audio_file = tmp_path / "later-chunk.mp3"
    audio_file.write_bytes(b"audio")
    captured: dict = {}

    async def fake_create(**kwargs):
        captured.update(kwargs)
        return FakeTranscriptionStream(
            [
                {
                    "type": "transcript.text.done",
                    "text": "Known speakers continue.",
                    "usage": None,
                }
            ]
        )

    fake_client = SimpleNamespace(
        audio=SimpleNamespace(
            transcriptions=SimpleNamespace(create=fake_create)
        )
    )
    fake_client.with_options = lambda **_kwargs: fake_client

    async def fake_record_cost(**_kwargs):
        return None

    monkeypatch.setattr(openai_client, "get_openai_client", lambda: fake_client)
    monkeypatch.setattr(
        openai_client.settings,
        "openai_transcription_model",
        "gpt-4o-transcribe-diarize",
    )
    monkeypatch.setattr(openai_client, "record_openai_cost", fake_record_cost)

    await openai_client.transcribe_audio(
        str(audio_file),
        duration_seconds=60,
        known_speaker_references={
            "Speaker 1": "data:audio/mpeg;base64,c3BlYWtlci0x",
            "Speaker 2": "data:audio/mpeg;base64,c3BlYWtlci0y",
        },
    )

    assert captured["known_speaker_names"] == ["Speaker 1", "Speaker 2"]
    assert captured["known_speaker_references"] == [
        "data:audio/mpeg;base64,c3BlYWtlci0x",
        "data:audio/mpeg;base64,c3BlYWtlci0y",
    ]
