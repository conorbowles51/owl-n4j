"""Processing an image keeps the photo's date, place and camera under ``photo_data`` (it dropped the place before)."""
import pytest
from PIL import Image

from app.pipeline import extract_text as module


def test_extract_image_metadata_keeps_photo_data(tmp_path):
    exif = Image.Exif()
    exif[0x010F] = "Apple"
    exif.get_ifd(0x8769)[0x9003] = "2024:05:01 12:30:15"
    gps = exif.get_ifd(0x8825)
    gps[1], gps[2], gps[3], gps[4] = "N", (51.0, 30.0, 0.0), "W", (0.0, 7.0, 30.0)
    path = tmp_path / "p.jpg"
    Image.new("RGB", (10, 10)).save(path, format="JPEG", exif=exif)
    metadata = module._extract_image_metadata(str(path))
    photo = metadata["photo_data"]
    assert photo["gps"]["latitude"] == 51.5 and photo["date_taken"]["local"] == "2024-05-01T12:30:15"
    assert photo["camera"] == {"make": "Apple"} and photo["confirmed_by"] is None
    assert metadata["width"] == 10


def test_image_without_data_is_recorded_as_read_and_empty(tmp_path):
    path = tmp_path / "q.png"
    Image.new("RGB", (10, 10)).save(path, format="PNG")
    photo = module._extract_image_metadata(str(path))["photo_data"]
    # read, and the file holds none of it: absent keys, so a screen can say which values the file lacked
    assert not {"date_taken", "gps", "camera"} & set(photo)


def test_both_orchestrators_store_the_photo_data():
    """The batch pipeline (what an uploaded folder of photos uses) kept nothing at first: both paths call the store."""
    from pathlib import Path

    for name in ("orchestrator.py", "batch_orchestrator.py"):
        source = (Path(module.__file__).parent / name).read_text()
        assert "store_photo_data(" in source, name


@pytest.mark.asyncio
async def test_store_photo_data_writes_the_record_and_survives_a_failure():
    from types import SimpleNamespace

    from app.services import evidence_document_text as store

    calls = []

    class Db:
        async def execute(self, statement, params):
            calls.append(params)

        async def commit(self):
            calls.append("commit")

        async def rollback(self):
            calls.append("rollback")

    doc = SimpleNamespace(metadata={"photo_data": {"gps": {"latitude": 1.0, "longitude": 2.0}}})
    assert await store.store_photo_data(Db(), evidence_file_id="3b241101-e2bb-4255-8caf-4136c566a962", doc=doc)
    assert calls[0]["id"] == "3b241101-e2bb-4255-8caf-4136c566a962" and '"latitude": 1.0' in calls[0]["record"]
    assert not await store.store_photo_data(Db(), evidence_file_id="x", doc=SimpleNamespace(metadata={}))

    class Broken(Db):
        async def execute(self, statement, params):
            raise RuntimeError("down")

    broken = Broken()
    assert not await store.store_photo_data(broken, evidence_file_id="x", doc=doc)
    assert calls[-1] == "rollback"
