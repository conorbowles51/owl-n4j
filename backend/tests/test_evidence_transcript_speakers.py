import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from routers import evidence


class FakeDb:
    def __init__(self) -> None:
        self.commit_count = 0

    def commit(self) -> None:
        self.commit_count += 1


def test_update_transcript_speakers_persists_trimmed_known_labels(monkeypatch) -> None:
    record = SimpleNamespace(
        transcription_segments=[
            {"speaker": "A", "start": 0.0, "end": 1.0, "text": "Hello"},
            {"speaker": "B", "start": 1.0, "end": 2.0, "text": "Hi"},
        ],
        transcription_speakers={},
        transcription_speaker_merges={},
    )
    db = FakeDb()
    monkeypatch.setattr(evidence, "_evidence_record_for_id", lambda *_args: record)

    result = asyncio.run(
        evidence.update_transcript_speakers(
            "evidence-id",
            evidence.TranscriptSpeakersUpdate(
                speakers={"A": "  Detective Byrne ", "B": ""},
                merges={"B": "A"},
            ),
            db,
        )
    )

    assert result == {
        "speakers": {"A": "Detective Byrne"},
        "merges": {"B": "A"},
    }
    assert record.transcription_speakers == {"A": "Detective Byrne"}
    assert record.transcription_speaker_merges == {"B": "A"}
    assert db.commit_count == 1


def test_update_transcript_speakers_rejects_unknown_labels(monkeypatch) -> None:
    record = SimpleNamespace(
        transcription_segments=[
            {"speaker": "A", "start": 0.0, "end": 1.0, "text": "Hello"}
        ],
        transcription_speakers={},
        transcription_speaker_merges={},
    )
    monkeypatch.setattr(evidence, "_evidence_record_for_id", lambda *_args: record)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            evidence.update_transcript_speakers(
                "evidence-id",
                evidence.TranscriptSpeakersUpdate(speakers={"C": "Unknown"}),
                FakeDb(),
            )
        )

    assert exc_info.value.status_code == 422


def test_update_transcript_speakers_flattens_merge_chains(monkeypatch) -> None:
    record = SimpleNamespace(
        transcription_segments=[
            {"speaker": "A", "start": 0.0, "end": 1.0, "text": "One"},
            {"speaker": "B", "start": 1.0, "end": 2.0, "text": "Two"},
            {"speaker": "C", "start": 2.0, "end": 3.0, "text": "Three"},
        ],
        transcription_speakers={},
        transcription_speaker_merges={},
    )
    monkeypatch.setattr(evidence, "_evidence_record_for_id", lambda *_args: record)

    result = asyncio.run(
        evidence.update_transcript_speakers(
            "evidence-id",
            evidence.TranscriptSpeakersUpdate(
                speakers={"C": "Caller"},
                merges={"A": "B", "B": "C"},
            ),
            FakeDb(),
        )
    )

    assert result["merges"] == {"A": "C", "B": "C"}
    assert record.transcription_speaker_merges == {"A": "C", "B": "C"}


def test_update_transcript_speakers_rejects_merge_cycles(monkeypatch) -> None:
    record = SimpleNamespace(
        transcription_segments=[
            {"speaker": "A", "start": 0.0, "end": 1.0, "text": "One"},
            {"speaker": "B", "start": 1.0, "end": 2.0, "text": "Two"},
        ],
        transcription_speakers={},
        transcription_speaker_merges={},
    )
    monkeypatch.setattr(evidence, "_evidence_record_for_id", lambda *_args: record)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            evidence.update_transcript_speakers(
                "evidence-id",
                evidence.TranscriptSpeakersUpdate(
                    speakers={},
                    merges={"A": "B", "B": "A"},
                ),
                FakeDb(),
            )
        )

    assert exc_info.value.status_code == 422
    assert "cycle" in str(exc_info.value.detail).lower()
