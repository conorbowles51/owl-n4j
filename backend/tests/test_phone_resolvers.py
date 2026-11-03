"""The phone_extraction and phone_file link resolvers and the shared id namespace (07 section 6, 02 section 1.2).
Synthetic rows only. The SQL itself runs against PostgreSQL in test_phone_capture_schema (opt-in)."""
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from postgres import link_types
from services.phone import ids, resolvers


class FakeDb:
    def __init__(self, file_row=None, folder_row=None, extraction_row=None):
        self.answers = {"phone_files f": file_row, "c.container_kind = 'folder'": folder_row,
                        "FROM phone_extractions e JOIN phone_extraction_containers": extraction_row}
        self.params = []

    def execute(self, statement, params):
        self.params.append(params)
        sql = str(statement)
        row = next((v for k, v in self.answers.items() if k in sql), None)
        return SimpleNamespace(first=lambda: row)


def file_row(**kw):
    base = dict(extraction_id=uuid4(), document_index=0, ordinal=4, local_path="files\\Image\\IMG_1.jpg",
                source_file_id="f-1", disk_relpath="files/Image/IMG_1.jpg", disk_size=9, disk_sha256="a" * 64,
                outcome="match", capture_code_version="phone-capture-1")
    base.update(kw)
    return SimpleNamespace(**base)


def test_a_file_in_a_folder_upload_resolves_to_its_path_on_disk(monkeypatch):
    monkeypatch.setattr(resolvers, "_data_root", lambda: Path("/data"))
    case = uuid4()
    db = FakeDb(file_row=file_row(), folder_row=SimpleNamespace(stored_path="_upload_groups/g/payload/Phone",
                                                                root_path=""))
    target = resolvers.resolve_file(db, case, str(uuid4()))
    assert target.metadata["stored_path"] == "/data/%s/_upload_groups/g/payload/Phone/files/Image/IMG_1.jpg" % case
    assert (target.metadata["original_filename"], target.metadata["size"], target.metadata["sha256"]) == (
        "IMG_1.jpg", 9, "a" * 64)
    assert target.mapping_versions == {"capture_code_version": "phone-capture-1"}


def test_a_file_inside_a_zip_resolves_to_its_member_locator_and_a_missing_file_none():
    """cb-media item F: before, a zip-kept file had no stored_path and could not be used as evidence."""
    db = FakeDb(file_row=file_row(), folder_row=None)
    uid = uuid4()
    assert resolvers.resolve_file(db, uuid4(), str(uid)).metadata["stored_path"] == "phone-file:%s" % uid
    absent = FakeDb(file_row=file_row(disk_relpath=None, disk_size=None, disk_sha256=None, outcome="missing"),
                    folder_row=SimpleNamespace(stored_path="p", root_path=""))
    assert resolvers.resolve_file(absent, uuid4(), str(uuid4())).metadata["stored_path"] is None


def test_unknown_or_malformed_ids_are_not_in_the_case():
    assert resolvers.resolve_file(FakeDb(), uuid4(), str(uuid4())) is None
    assert resolvers.resolve_file(FakeDb(file_row=file_row()), uuid4(), "not-a-uuid") is None
    assert resolvers.resolve_extraction(FakeDb(), uuid4(), str(uuid4())) is None


def test_register_makes_both_types_resolvable(monkeypatch):
    saved = dict(link_types._RESOLVERS)
    try:
        link_types._RESOLVERS.clear()
        resolvers.register()
        assert link_types.has_phone_resolver("phone_file") and link_types.has_phone_resolver("phone_extraction")
        row = SimpleNamespace(id=uuid4(), standing="active", capture_state="captured",
                              capture_code_version="phone-capture-1", original_name="Export.zip")
        target = link_types.resolve_phone_target(FakeDb(extraction_row=row), uuid4(), "phone_extraction", str(row.id))
        assert target.label == "Export.zip" and target.metadata["standing"] == "active"
        with pytest.raises(link_types.LinkTargetError):
            link_types.resolve_phone_target(FakeDb(), uuid4(), "phone_extraction", str(uuid4()))
    finally:
        link_types._RESOLVERS.clear()
        link_types._RESOLVERS.update(saved)


def test_the_id_namespace_is_the_engines():
    engine = (Path(__file__).resolve().parents[2] / "evidence-engine" / "app" / "phone" / "ids.py").read_text()
    assert 'PHONE_NS = uuid.UUID("%s")' % ids.PHONE_NS in engine
    ext = "7d863057-0f79-4cb1-af2e-dcab0fd0c254"  # a synthetic value; PostgreSQL uuid_generate_v5 gives the same
    assert str(ids.file_uid(ext, 0, 5)) == "297a7729-3653-5819-8cee-77bcf3839b7a"
