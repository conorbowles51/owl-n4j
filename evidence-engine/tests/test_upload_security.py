import uuid
from io import BytesIO
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
async def test_upload_persists_ingestion_request_id_for_response_recovery(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
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
        files=[UploadFile(file=BytesIO(b"%PDF-test"), filename="report.pdf")],
        processing_metadata='[{"ingestion_request_id":"request-123"}]',
        db=db,
    )

    assert jobs[0].pipeline_state["ingestion_request_id"] == "request-123"
