"""Delete Folder counts every file the delete removes (lx-uploadfollow D): the folder tree's count is a folder's own
files only, so a folder whose files all sit in subfolders showed no "N files will be permanently deleted" line."""
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from postgres.base import Base
from postgres.models.evidence import EvidenceFile, EvidenceFolder
from routers import evidence_folders as router
from services.evidence_db_storage import EvidenceDBStorage


@pytest.fixture()
def world():
    engine = create_engine("sqlite+pysqlite:///:memory:", poolclass=StaticPool,
                           connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine, tables=[EvidenceFolder.__table__, EvidenceFile.__table__])
    case_id, other_case = uuid4(), uuid4()
    with Session(engine) as db:
        top = EvidenceFolder(id=uuid4(), case_id=case_id, name="Phone dump")
        db.add(top)
        db.flush()
        subs = [EvidenceFolder(id=uuid4(), case_id=case_id, name=f"part {i}", parent_id=top.id) for i in range(4)]
        db.add_all(subs)
        db.flush()
        deeper = EvidenceFolder(id=uuid4(), case_id=case_id, name="deeper", parent_id=subs[0].id)
        beside = EvidenceFolder(id=uuid4(), case_id=case_id, name="Beside")
        db.add_all([deeper, beside])
        db.flush()
        for i in range(1000):  # 1,000 files in the four subfolders, none in the folder itself
            db.add(EvidenceFile(case_id=case_id, folder_id=subs[i % 4].id, original_filename=f"f{i}.txt",
                                stored_path=f"/x/{i}", sha256=f"{i:064x}", status="unprocessed"))
        db.add(EvidenceFile(case_id=case_id, folder_id=deeper.id, original_filename="thread.txt", stored_path="/t",
                            sha256="f" * 64, status="processed", source_type="phone_text"))
        db.add(EvidenceFile(case_id=case_id, folder_id=beside.id, original_filename="other.txt", stored_path="/o",
                            sha256="e" * 64, status="unprocessed"))
        db.commit()
        ids = SimpleNamespace(top=top.id, deeper=deeper.id, beside=beside.id)

    def access(db, case, user, permission=None):
        if case != str(case_id):
            raise HTTPException(403, "User is not a member of case")
    app = FastAPI()
    app.include_router(router.router)

    def db_dependency():
        with Session(engine) as db:
            yield db
    app.dependency_overrides[router.get_db] = db_dependency
    app.dependency_overrides[router.get_current_db_user] = lambda: SimpleNamespace(id=uuid4())
    with patch.object(router, "_check_case_access", access), TestClient(app) as client:
        yield SimpleNamespace(client=client, engine=engine, case=case_id, other_case=other_case, **vars(ids))
    engine.dispose()


def summary(w, folder, case=None):
    return w.client.get(f"/api/evidence-folders/{folder}/delete-summary", params={"case_id": str(case or w.case)})


def test_a_folder_with_files_only_in_subfolders_counts_every_file_the_delete_removes(world):
    w = world
    response = summary(w, w.top)
    assert response.status_code == 200, response.text
    assert response.json() == dict(file_count=1001, listed_file_count=1000, subfolder_count=5)
    with Session(w.engine) as db:
        # The same set the delete removes (its financial hold check reads these ids).
        assert len(EvidenceDBStorage.folder_tree_file_ids(db, w.top)) == 1001
        # The tree's own count for the folder is its direct files: none.
        [node] = [n for n in EvidenceDBStorage.get_folder_tree(db, w.case) if n["id"] == str(w.top)]
        assert node["file_count"] == 0
    assert summary(w, w.deeper).json() == dict(file_count=1, listed_file_count=0, subfolder_count=0)
    assert summary(w, w.beside).json() == dict(file_count=1, listed_file_count=1, subfolder_count=0)


def test_a_folder_of_another_case_or_without_access_is_not_counted(world):
    w = world
    assert summary(w, w.top, case=w.other_case).status_code == 403
    assert summary(w, uuid4()).status_code == 404
