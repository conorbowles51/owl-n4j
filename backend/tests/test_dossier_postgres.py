"""Opt-in PostgreSQL checks; every test uses a new, disposable schema.

Set DOSSIER_TEST_DATABASE_URL to a local test PostgreSQL connection. No existing
application tables are read or changed.
"""
import importlib.util
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from unittest.mock import patch

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, select, text

from postgres.models.dossier import DossierLink, DossierMedia
from postgres.models.user import User
from services import dossier_service
from tests import test_dossier_service as service_tests

pytestmark = pytest.mark.skipif(not os.environ.get("DOSSIER_TEST_DATABASE_URL"), reason="Requires an explicit local PostgreSQL test connection")


@pytest.fixture
def pg_engine():
    connection_url = os.environ["DOSSIER_TEST_DATABASE_URL"]
    assert connection_url.startswith("postgresql"), "This test requires PostgreSQL"
    admin = create_engine(connection_url)
    schema = "dossier_test_" + uuid.uuid4().hex
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(connection_url, connect_args={"options": f"-csearch_path={schema}"})
    try:
        yield engine
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


def test_migration_preserves_old_contacts_and_full_dates(pg_engine):
    path = Path(__file__).parents[1] / "postgres/alembic/versions/20261019_dossier_workflows.py"
    spec = importlib.util.spec_from_file_location("dossier_workflow_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    with pg_engine.begin() as connection:
        connection.execute(text("CREATE TABLE case_profiles (id uuid PRIMARY KEY)"))
        connection.execute(text("CREATE TABLE case_profile_attributes (id uuid, profile_id uuid, kind text, name text, value text, ordinal int)"))
        connection.execute(text("CREATE TABLE dossier_interviews (id uuid PRIMARY KEY, interview_date timestamptz)"))
        profile_id = uuid.uuid4()
        connection.execute(text("INSERT INTO case_profiles VALUES (:id)"), {"id": profile_id})
        connection.execute(text("INSERT INTO case_profile_attributes VALUES (:id, :profile, 'phone', 'Work', '+1 555 0100', 0)"), {"id": uuid.uuid4(), "profile": profile_id})
        connection.execute(text("INSERT INTO dossier_interviews VALUES (:id, '2025-07-23T16:00:00Z')"), {"id": uuid.uuid4()})
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
        contacts = connection.execute(text("SELECT contacts FROM case_profiles")).scalar_one()
        assert contacts[0]["value"] == "+1 555 0100"
        assert contacts[0]["recorded_by_user_id"] is None
        assert connection.execute(text("SELECT date_value IS NULL AND interview_date IS NOT NULL FROM dossier_interviews")).scalar_one()
        connection.execute(text("INSERT INTO case_profiles (id) VALUES (:id)"), {"id": uuid.uuid4()})
        assert connection.execute(text("SELECT count(*) FROM case_profiles WHERE contacts = '[]'::jsonb")).scalar_one() == 1


def test_parallel_attachment_retries_keep_one_link_and_gallery_item(pg_engine, tmp_path):
    # SQLite's fixture omits unused FK tables; PostgreSQL requires their targets.
    tables = set(service_tests.TABLES)
    while True:
        dependencies = {foreign.column.table for table in tables for foreign in table.foreign_keys}
        if dependencies <= tables:
            break
        tables.update(dependencies)
    with patch.object(service_tests, "TABLES", list(tables)), patch.object(service_tests, "create_engine", return_value=pg_engine):
        fixture = service_tests.setup_db.__wrapped__(tmp_path)
        factory, user_id, case_id, image_id, source_id, _foreign = next(fixture)
        try:
            with patch.object(dossier_service, "check_case_access", return_value=(None, None)), patch.object(dossier_service, "get_case_if_allowed", return_value=None):
                with factory() as db:
                    dossier = dossier_service.create_dossier(db, case_id=case_id, user=db.get(User, user_id), data={"display_name": "Concurrent subject"})
                    dossier_id = uuid.UUID(dossier["id"])

                barrier = Barrier(2)

                def attach(_):
                    with factory() as db:
                        user = db.get(User, user_id)
                        barrier.wait(timeout=10)
                        return dossier_service.add_evidence_links(db, dossier_id=dossier_id, evidence_file_ids=[image_id, source_id], user=user)

                def gallery(_):
                    with factory() as db:
                        user = db.get(User, user_id)
                        barrier.wait(timeout=10)
                        return dossier_service.add_media(db, dossier_id=dossier_id, data={"evidence_file_id": image_id, "is_cover": True}, user=user)

                with ThreadPoolExecutor(max_workers=2) as executor:
                    list(executor.map(attach, [1, 2]))
                    images = list(executor.map(gallery, [1, 2]))
                with factory() as db:
                    assert len(db.scalars(select(DossierLink).where(DossierLink.dossier_id == dossier_id)).all()) == 2
                    assert len(db.scalars(select(DossierMedia).where(DossierMedia.dossier_id == dossier_id)).all()) == 1
                    assert images[0]["id"] == images[1]["id"]
        finally:
            fixture.close()
