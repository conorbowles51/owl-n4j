"""One file the processing service refuses fails alone, with the service's reason; the rest of the request is
processed (SB4, 28 Oct: one oversized request failed all 250 files with a bare 400)."""
import json
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest

from services import evidence_processing_service as processing


class FakeDb:
    def commit(self):
        pass

    def scalars(self, statement):
        return iter(())


def _refusal(detail):
    request = httpx.Request('POST', 'http://engine/cases/x/files')
    response = httpx.Response(400, json={'detail': detail}, request=request)
    return httpx.HTTPStatusError("Client error '400 Bad Request'", request=request, response=response)


def _harness(tmp_path, monkeypatch, names, engine):
    case_id = uuid4()
    files = []
    for name in names:
        path = tmp_path / f'{len(files)}.pdf'
        path.write_bytes(b'%PDF-test')
        files.append(SimpleNamespace(id=uuid4(), case_id=case_id, status='unprocessed', source_type=None,
            processing_stale=False, stored_path=str(path), folder_id=None, original_filename=name,
            engine_job_id=None, last_error=None, metadata_={}))
    failed = {}

    async def no_reconcile(db, case):
        return 0

    async def tracked(job_ids, case):
        return None

    def mark_processed(db, ids, error=None):
        for file in files:
            if file.id in ids:
                file.status, file.last_error = 'failed', error
                failed[file.original_filename] = error

    monkeypatch.setattr(processing, 'reconcile_case_jobs', no_reconcile)
    monkeypatch.setattr(processing.evidence_signature, 'split_held', lambda db, case, ids, resolve: (ids, []))
    monkeypatch.setattr(processing.ai_budget, 'check', lambda *a, **k: None)
    monkeypatch.setattr(processing, 'gate_document_processing', lambda *a, **k: None)
    monkeypatch.setattr(processing, 'lock_case_audit_chain', lambda *a: None, raising=False)
    monkeypatch.setattr(processing.EvidenceDBStorage, 'get_files_by_ids', lambda db, ids: files)
    monkeypatch.setattr(processing.EvidenceDBStorage, 'mark_processing', lambda db, ids, force=False: None)
    monkeypatch.setattr(processing.EvidenceDBStorage, 'set_processing_snapshot', lambda *a, **k: None)
    monkeypatch.setattr(processing.EvidenceDBStorage, 'mark_processed', mark_processed)
    monkeypatch.setattr(processing, 'build_processing_snapshot', lambda *a, **k: {})
    monkeypatch.setattr(processing.evidence_engine_client, 'upload_file_paths_batch', engine)
    monkeypatch.setattr(processing, 'get_subscriber', lambda: SimpleNamespace(track_jobs=tracked))
    return case_id, files, failed


@pytest.mark.asyncio
async def test_one_refused_file_in_three_leaves_two_queued(tmp_path, monkeypatch):
    requests = []

    async def engine(*, case_id, files, processing_metadata):
        requests.append([name for name, _, _ in files])
        if any(name == 'bad.pdf' for name, _, _ in files):
            raise _refusal('Invalid upload filename')
        return [{'id': str(uuid4())} for _ in files]

    case_id, files, failed = _harness(tmp_path, monkeypatch, ['a.pdf', 'bad.pdf', 'c.pdf'], engine)
    result = await processing.process_db_files(FakeDb(), case_id=case_id, file_ids=[f.id for f in files])

    assert result['file_count'] == 2
    assert len(result['job_ids']) == 2
    assert [f.original_filename for f in files if f.engine_job_id] == ['a.pdf', 'c.pdf']
    assert list(failed) == ['bad.pdf']
    assert 'Invalid upload filename' in failed['bad.pdf']
    assert 'localhost' not in failed['bad.pdf'] and 'http' not in failed['bad.pdf']
    assert result['refused'][0]['name'] == 'bad.pdf'


@pytest.mark.asyncio
async def test_requests_stay_under_the_engine_field_limit(tmp_path, monkeypatch):
    """Each file's metadata lists its folder's other files; 250 of them in one request was 11.3 MB."""
    sizes = []

    async def engine(*, case_id, files, processing_metadata):
        sizes.append((len(files), len(json.dumps(processing_metadata))))
        return [{'id': str(uuid4())} for _ in files]

    case_id, files, failed = _harness(tmp_path, monkeypatch, [f'{i}.pdf' for i in range(60)], engine)
    big = [{'name': 'x' * 56 + '.pdf', 'mime_type': 'application/pdf', 'size': 123456}] * 365
    monkeypatch.setattr(processing, 'build_processing_snapshot', lambda *a, **k: {'sibling_files': big})
    result = await processing.process_db_files(FakeDb(), case_id=case_id, file_ids=[f.id for f in files])

    assert result['file_count'] == 60 and not failed
    assert all(count <= processing.MAX_FILES_PER_SEND and size < 1024 * 1024 for count, size in sizes)


@pytest.mark.asyncio
async def test_engine_down_still_fails_the_request_as_before(tmp_path, monkeypatch):
    async def engine(*, case_id, files, processing_metadata):
        raise httpx.ConnectError('refused')

    async def no_jobs(case):
        return []

    case_id, files, failed = _harness(tmp_path, monkeypatch, ['a.pdf', 'b.pdf'], engine)
    monkeypatch.setattr(processing.evidence_engine_client, 'list_jobs', no_jobs)
    with pytest.raises(httpx.ConnectError):
        await processing.process_db_files(FakeDb(), case_id=case_id, file_ids=[f.id for f in files])
    assert sorted(failed) == ['a.pdf', 'b.pdf']


@pytest.mark.asyncio
async def test_files_never_sent_are_not_marked_failed(tmp_path, monkeypatch):
    """60 files go as 3 requests; the engine stops answering on the second. The first 25 are processing, the second
    25 failed with the error, and the last 10, never tried, are back to unprocessed with the reason."""
    calls = []

    async def engine(*, case_id, files, processing_metadata):
        calls.append(len(files))
        if len(calls) == 2:
            raise httpx.ConnectError('refused')
        return [{'id': str(uuid4())} for _ in files]

    async def no_jobs(case):
        return []

    case_id, files, failed = _harness(tmp_path, monkeypatch, [f'{i:02}.pdf' for i in range(60)], engine)
    monkeypatch.setattr(processing.evidence_engine_client, 'list_jobs', no_jobs)
    monkeypatch.setattr(processing.EvidenceDBStorage, 'mark_processing',
                        lambda db, ids, force=False: [setattr(f, 'status', 'processing') for f in files])
    result = await processing.process_db_files(FakeDb(), case_id=case_id, file_ids=[f.id for f in files])

    assert calls == [25, 25]
    assert result['file_count'] == 25
    assert sum(f.engine_job_id is not None for f in files) == 25
    assert len(failed) == 25
    untried = files[50:]
    assert all(f.status == 'unprocessed' and f.last_error == processing.NOT_SENT for f in untried)
    assert '10 file(s) not sent' in result['message']
