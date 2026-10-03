import uuid
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, UploadFile

from app.api.routes.upload import _safe_upload_name, _storage_directory, upload_files
from app.config import settings


@pytest.mark.parametrize("name", ["../secret.pdf", "..\\secret.pdf", "/tmp/secret.pdf", ""])
def test_upload_filename_rejects_paths_and_empty_names(name: str) -> None:
    with pytest.raises(HTTPException) as exc:
        _safe_upload_name(name)

    assert exc.value.status_code == 400


def test_upload_storage_directory_is_confined_to_configured_root(tmp_path) -> None:
    case_id = str(uuid.uuid4())
    job_id = uuid.uuid4()

    target = _storage_directory(str(tmp_path), case_id, job_id)

    assert target.parent.parent == tmp_path.resolve()
    with pytest.raises(HTTPException):
        _storage_directory(str(tmp_path), "../../escape", job_id)


@pytest.mark.asyncio
@pytest.mark.parametrize("mode,reading_mode,expected_type", [("full","automatic","ingestion"),("pdf_review","automatic","pdf_review"),("pdf_review","page_images","pdf_review")])
@pytest.mark.parametrize("file_count", [1, 51])
async def test_upload_persists_ingestion_request_id_for_response_recovery(
    mode, reading_mode, expected_type,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    file_count: int,
) -> None:
    class FakeDb:
        def __init__(self) -> None:
            self.jobs = []

        def add(self, job) -> None:
            self.jobs.append(job)

        async def commit(self) -> None:
            return None

        async def rollback(self) -> None:
            return None

        async def refresh(self, job) -> None:
            return None

    class FakePool:
        async def enqueue_job(self, *args, **kwargs):
            return SimpleNamespace(job_id=kwargs.get("_job_id"))

    monkeypatch.setattr(settings, "storage_path", str(tmp_path))
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(arq_pool=FakePool()))
    )
    db = FakeDb()

    jobs = await upload_files(
        case_id=str(uuid.uuid4()),
        request=request,
        files=[
            UploadFile(file=BytesIO(b"%PDF-test"), filename=f"report-{i}.pdf")
            for i in range(file_count)
        ],
        processing_metadata=__import__("json").dumps([
            {"ingestion_request_id":"request-123", "preparation_mode":mode,"pdf_reading_mode":reading_mode,"source_evidence_file_id":str(uuid.uuid4())}
            for _ in range(file_count)
        ]),
        db=db,
    )

    assert jobs[0].pipeline_state["ingestion_request_id"] == "request-123"

    assert jobs[0].job_type == expected_type
    assert jobs[0].pipeline_state['processing_queue'] == ('arq:pdf-review' if mode == 'pdf_review' else 'arq:queue')
    if mode == 'pdf_review':
        assert jobs[0].pipeline_state['pdf_reading_mode'] == reading_mode
    assert len(jobs) == file_count
    assert len({job.batch_id for job in jobs}) == 1
    assert all(Path(job.file_path).read_bytes() == b"%PDF-test" for job in jobs)


@pytest.mark.asyncio
@pytest.mark.parametrize("file_limit,batch_limit,file_count", [(3, 100, 1), (10, 5, 2)])
async def test_upload_still_enforces_byte_limits_and_cleans_up(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    file_limit: int,
    batch_limit: int,
    file_count: int,
) -> None:
    class FakeDb:
        rolled_back = False

        def add(self, job) -> None:
            pass

        async def rollback(self) -> None:
            self.rolled_back = True

    monkeypatch.setattr(settings, "storage_path", str(tmp_path))
    monkeypatch.setattr(settings, "max_upload_file_bytes", file_limit)
    monkeypatch.setattr(settings, "max_upload_batch_bytes", batch_limit)
    db = FakeDb()
    with pytest.raises(HTTPException) as exc:
        await upload_files(
            case_id=str(uuid.uuid4()),
            request=SimpleNamespace(),
            files=[
                UploadFile(file=BytesIO(b"test"), filename=f"report-{i}.txt")
                for i in range(file_count)
            ],
            processing_metadata=None,
            db=db,
        )

    assert exc.value.status_code == 413
    assert db.rolled_back
    assert not list(tmp_path.rglob("report-*.txt"))
