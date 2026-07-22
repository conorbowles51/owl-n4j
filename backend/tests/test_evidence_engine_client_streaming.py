from pathlib import Path

import pytest

from services import evidence_engine_client


class FakeResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self):
        return [{"id": "job-1"}]


class InspectingClient:
    def __init__(self) -> None:
        self.seen_handle = None
        self.first_bytes = None

    async def post(self, path, *, files, data):
        assert path == "/cases/case-1/files"
        _, (_, handle, content_type) = files[0]
        assert content_type == "application/pdf"
        assert handle.closed is False
        self.seen_handle = handle
        self.first_bytes = handle.read(4)
        return FakeResponse()


@pytest.mark.asyncio
async def test_path_upload_streams_open_file_and_closes_it_after_request(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = tmp_path / "large.pdf"
    source.write_bytes(b"%PDF-test")
    client = InspectingClient()
    monkeypatch.setattr(evidence_engine_client, "_client", client)

    result = await evidence_engine_client.upload_file_paths_batch(
        case_id="case-1",
        files=[("large.pdf", source, "application/pdf")],
        processing_metadata=[{"source_evidence_file_id": "evidence-1"}],
    )

    assert result == [{"id": "job-1"}]
    assert client.first_bytes == b"%PDF"
    assert client.seen_handle.closed is True
