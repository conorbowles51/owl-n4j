import unittest
import uuid
from unittest.mock import patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from postgres.base import Base
from postgres.models.case import Case
from postgres.models.evidence import EvidenceFile, EvidenceFolder, IngestionLog
from postgres.models.user import User
from routers import evidence_folders
from services.evidence_db_storage import EvidenceDBStorage


class EvidenceFileLocationTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine, tables=[
            User.__table__, Case.__table__, EvidenceFolder.__table__,
            EvidenceFile.__table__, IngestionLog.__table__,
        ])
        self.db = Session(self.engine)
        self.case_id = uuid.uuid4()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def add_file(self, name, folder_id=None, case_id=None, file_id=None):
        file = EvidenceFile(
            id=file_id or uuid.uuid4(), case_id=case_id or self.case_id,
            folder_id=folder_id, original_filename=name,
            stored_path=f"/evidence/{name}", size=10, sha256="a" * 64,
        )
        self.db.add(file)
        self.db.flush()
        return file

    def test_nested_file_location_matches_paginated_listing_with_duplicate_names(self):
        parent = EvidenceFolder(case_id=self.case_id, name="Parent")
        self.db.add(parent)
        self.db.flush()
        child = EvidenceFolder(case_id=self.case_id, name="Child", parent_id=parent.id)
        self.db.add(child)
        self.db.flush()
        # Deliberately insert duplicates out of order on a page boundary.
        for index in [4, 1, 3, 2, 5]:
            self.add_file("duplicate.pdf", child.id, file_id=uuid.UUID(int=0xaaaaaaaa000000000000000000000000 + index))
        for index in range(249):
            self.add_file(f"a-{index:03}.pdf", child.id)
        self.add_file("a-other-folder.pdf", parent.id)
        self.add_file("a-other-case.pdf", case_id=uuid.uuid4())

        target = uuid.UUID(int=0xaaaaaaaa000000000000000000000000 + 3)
        location = EvidenceDBStorage.get_file_location(self.db, self.case_id, target)
        self.assertEqual(location["folder_id"], str(child.id))
        self.assertEqual(location["ancestor_ids"], [str(parent.id)])
        self.assertEqual(location["file_offset"], 250)
        listing = EvidenceDBStorage.list_contents(
            self.db, self.case_id, child.id, offset=location["file_offset"],
        )
        self.assertEqual([row["id"] for row in listing["files"]], [str(uuid.UUID(int=0xaaaaaaaa000000000000000000000000 + i)) for i in [2, 3, 4, 5]])

    def test_root_and_moved_file_resolve_current_location(self):
        file = self.add_file("target.pdf")
        location = EvidenceDBStorage.get_file_location(self.db, self.case_id, file.id)
        self.assertEqual(location["folder_id"], None)
        self.assertEqual(location["ancestor_ids"], [])
        self.assertEqual(location["file_offset"], 0)
        folder = EvidenceFolder(case_id=self.case_id, name="Moved")
        self.db.add(folder)
        self.db.flush()
        file.folder_id = folder.id
        self.db.flush()
        self.assertEqual(EvidenceDBStorage.get_file_location(self.db, self.case_id, file.id)["folder_id"], str(folder.id))

    def test_missing_deleted_and_other_case_files_are_not_resolved(self):
        file = self.add_file("private.pdf", case_id=uuid.uuid4())
        self.assertIsNone(EvidenceDBStorage.get_file_location(self.db, self.case_id, file.id))
        self.assertIsNone(EvidenceDBStorage.get_file_location(self.db, self.case_id, uuid.uuid4()))
        self.db.delete(file)
        self.db.flush()
        self.assertIsNone(EvidenceDBStorage.get_file_location(self.db, file.case_id, file.id))


class EvidenceFileLocationRouteTests(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(evidence_folders.router)
        self.user = object()
        self.db = object()
        app.dependency_overrides[evidence_folders.get_current_db_user] = lambda: self.user
        app.dependency_overrides[evidence_folders.get_db] = lambda: self.db
        self.client = TestClient(app)
        self.case_id = uuid.uuid4()
        self.file_id = uuid.uuid4()
        self.url = f"/api/evidence-folders/files/{self.file_id}/location?case_id={self.case_id}"

    def tearDown(self):
        self.client.close()

    def test_checks_access_before_resolving(self):
        with patch.object(evidence_folders, "_check_case_access", side_effect=HTTPException(403)), patch.object(EvidenceDBStorage, "get_file_location") as lookup:
            self.assertEqual(self.client.get(self.url).status_code, 403)
            lookup.assert_not_called()

    def test_missing_file_returns_404_and_valid_location_uses_case_scope(self):
        with patch.object(evidence_folders, "_check_case_access") as access, patch.object(EvidenceDBStorage, "get_file_location", return_value=None) as lookup:
            self.assertEqual(self.client.get(self.url).status_code, 404)
            access.assert_called_once_with(self.db, str(self.case_id), self.user)
            lookup.assert_called_once_with(self.db, self.case_id, self.file_id, limit=250, sort_by="name", sort_direction="asc")
            lookup.return_value = {"file_id": str(self.file_id), "folder_id": None, "ancestor_ids": [], "file_offset": 0, "file_limit": 250}
            response = self.client.get(self.url)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), lookup.return_value)

    def test_rejects_invalid_ids_and_page_sizes(self):
        self.assertEqual(self.client.get(self.url + "&limit=0").status_code, 422)
        self.assertEqual(self.client.get(self.url + "&limit=1001").status_code, 422)
        self.assertEqual(self.client.get(self.url.replace(str(self.file_id), "invalid")).status_code, 422)
