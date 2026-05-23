import unittest
import uuid
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from postgres.base import Base
from postgres.models.case import Case
from postgres.models.evidence import EvidenceFile, EvidenceFolder, IngestionLog
from postgres.models.user import User
from routers.evidence import (
    _extract_archive_to_staging,
    _find_cellebrite_report_roots,
    _resolve_stored_path,
    get_current_db_user,
    get_db,
    router,
)


class EvidenceCellebriteRouteTests(unittest.TestCase):
    def test_cellebrite_ingest_routes_are_registered(self):
        routes = {
            (next(iter(route.methods - {"HEAD", "OPTIONS"})), route.path)
            for route in router.routes
            if getattr(route, "methods", None)
        }

        self.assertIn(("GET", "/api/evidence/cellebrite/check"), routes)
        self.assertIn(("POST", "/api/evidence/cellebrite/process"), routes)

    def test_cellebrite_zip_extracts_and_detects_report_root(self):
        marker = "http://pa.cellebrite.com/report/2.0"
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            zip_path = tmp_path / "report.zip"
            extract_dir = tmp_path / "extract"

            with zipfile.ZipFile(zip_path, "w") as zf:
                zf.writestr("PhoneReport/PhoneReport.xml", f"<report xmlns='{marker}' />")
                zf.writestr("PhoneReport/files/Text/note.txt", "hello")
                zf.writestr("__MACOSX/PhoneReport/._PhoneReport.xml", "noise")
                zf.writestr("PhoneReport/.DS_Store", "noise")

            uploads = _extract_archive_to_staging(zip_path, extract_dir)
            relative_paths = {item["relative_path"] for item in uploads}

            self.assertEqual(
                relative_paths,
                {"PhoneReport/PhoneReport.xml", "PhoneReport/files/Text/note.txt"},
            )
            self.assertEqual(_find_cellebrite_report_roots(extract_dir), ["PhoneReport"])

    def test_stored_path_resolves_container_evidence_root_to_host_root(self):
        with TemporaryDirectory() as tmp:
            evidence_root = Path(tmp) / "ingestion" / "data"
            stored_file = evidence_root / "case-id" / "Report" / "files" / "Image" / "photo.png"
            stored_file.parent.mkdir(parents=True)
            stored_file.write_bytes(b"image")

            with patch("routers.evidence.EVIDENCE_ROOT_DIR", evidence_root):
                resolved = _resolve_stored_path("/ingestion/data/case-id/Report/files/Image/photo.png")

            self.assertEqual(resolved, stored_file)

    def test_cellebrite_archive_upload_unpacks_without_generic_evidence_rows(self):
        marker = "http://pa.cellebrite.com/report/2.0"
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            case_id = uuid.uuid4()
            user_id = uuid.uuid4()
            zip_path = tmp_path / "report.zip"

            with zipfile.ZipFile(zip_path, "w") as zf:
                zf.writestr("PhoneReport/PhoneReport.xml", f"<report xmlns='{marker}' />")
                zf.writestr("PhoneReport/files/Text/note.txt", "hello")

            engine = create_engine(
                "sqlite+pysqlite:///:memory:",
                future=True,
                connect_args={"check_same_thread": False},
                poolclass=StaticPool,
            )
            Base.metadata.create_all(
                engine,
                tables=[
                    User.__table__,
                    Case.__table__,
                    EvidenceFolder.__table__,
                    EvidenceFile.__table__,
                    IngestionLog.__table__,
                ],
            )
            SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

            with SessionLocal() as db:
                db.add(User(
                    id=user_id,
                    email="investigator@example.com",
                    name="Investigator",
                    password_hash="hash",
                ))
                db.add(Case(
                    id=case_id,
                    title="Case",
                    created_by_user_id=user_id,
                    owner_user_id=user_id,
                ))
                db.commit()

            app = FastAPI()
            app.include_router(router)

            def override_db():
                db = SessionLocal()
                try:
                    yield db
                finally:
                    db.close()

            def override_user():
                with SessionLocal() as db:
                    return db.get(User, user_id)

            app.dependency_overrides[get_db] = override_db
            app.dependency_overrides[get_current_db_user] = override_user

            evidence_root = tmp_path / "evidence"
            staging_root = evidence_root / "_staging"

            with (
                patch("routers.evidence.EVIDENCE_ROOT_DIR", evidence_root),
                patch("routers.evidence._UPLOAD_STAGING_ROOT", staging_root),
                patch("services.case_service.check_case_access", return_value=(object(), None)),
                patch(
                    "routers.evidence.check_cellebrite_report",
                    return_value={
                        "suitable": True,
                        "report_name": "PhoneReport",
                        "report_key": "cellebrite-unknown-unknown",
                        "model_count": 1,
                    },
                ),
                patch(
                    "routers.evidence.evidence_engine_client.create_cellebrite_job",
                    new=AsyncMock(return_value={"id": "job-1"}),
                ) as create_job,
            ):
                client = TestClient(app)
                with zip_path.open("rb") as handle:
                    response = client.post(
                        "/api/evidence/upload",
                        data={
                            "case_id": str(case_id),
                            "is_folder": "true",
                            "is_archive": "true",
                        },
                        files={"files": ("report.zip", handle, "application/zip")},
                    )

            self.assertEqual(response.status_code, 200, response.text)
            body = response.json()
            self.assertEqual(body["files"], [])
            self.assertEqual(body["job_ids"], ["job-1"])
            self.assertIn("queued processing", body["message"])
            self.assertTrue((evidence_root / str(case_id) / "PhoneReport" / "PhoneReport.xml").exists())
            create_job.assert_awaited_once()

            with SessionLocal() as db:
                self.assertEqual(db.query(EvidenceFile).count(), 0)
                folder = db.query(EvidenceFolder).one()
                self.assertEqual(
                    [folder.name],
                    ["PhoneReport"],
                )
                self.assertEqual(
                    create_job.await_args.kwargs["evidence_folder_id"],
                    str(folder.id),
                )

            Base.metadata.drop_all(
                engine,
                tables=[
                    IngestionLog.__table__,
                    EvidenceFile.__table__,
                    EvidenceFolder.__table__,
                    Case.__table__,
                    User.__table__,
                ],
            )
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
