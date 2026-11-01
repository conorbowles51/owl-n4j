"""Phone capture schema (01 unit 1.1): one alembic head, upgrade/downgrade/upgrade on an empty database, and one
row inserted and read back in each capture table.

The PostgreSQL part is opt-in: set ``LOUPE_TEST_PHONE_PG_ADMIN_URL`` to a local scratch server
(``postgresql+psycopg://user:pw@127.0.0.1:<port>/postgres``). The test creates and drops its own database there.
"""
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

BACKEND = Path(__file__).resolve().parents[1]
VERSIONS = BACKEND / "postgres" / "alembic" / "versions"


def _alembic(url, *args):
    env = dict(os.environ, DATABASE_URL=url)
    return subprocess.run([sys.executable, "-m", "alembic", *args], cwd=BACKEND, env=env,
                          capture_output=True, text=True, timeout=900)


def test_one_alembic_head():
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "postgres" / "alembic"))
    heads = ScriptDirectory.from_config(cfg).get_heads()
    assert len(heads) == 1, heads


def test_capture_models_cover_every_migration_table():
    from postgres.models.phone_extraction import PHONE_CAPTURE_MODELS

    src = (VERSIONS / "20261101_phone_capture.py").read_text()
    created = {line.split()[2] for line in src.splitlines() if line.startswith("CREATE TABLE ")}
    assert created == {m.__tablename__ for m in PHONE_CAPTURE_MODELS}
    assert len(created) == 12


ADMIN = os.getenv("LOUPE_TEST_PHONE_PG_ADMIN_URL")


@pytest.mark.skipif(not ADMIN, reason="Requires LOUPE_TEST_PHONE_PG_ADMIN_URL (a local scratch PostgreSQL)")
def test_upgrade_downgrade_upgrade_and_one_row_per_table():
    from postgres.models import phone_extraction as m

    admin_url = make_url(ADMIN)
    assert admin_url.host in ("127.0.0.1", "localhost")
    name = "phone_schema_" + uuid.uuid4().hex[:12]
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text("CREATE DATABASE " + name))
    url = admin_url.set(database=name).render_as_string(hide_password=False)
    try:
        for step in (("upgrade", "head"), ("downgrade", "20261101_timeline_view_instants"), ("upgrade", "head")):
            r = _alembic(url, *step)
            assert r.returncode == 0, r.stderr[-3000:]
        eng = create_engine(url)
        with eng.begin() as c:
            assert c.scalar(text("SELECT version_num FROM alembic_version")) == "20261101_phone_job_states"
            assert {"verifying_source", "capturing", "reconciling"} <= set(c.scalars(text(
                "SELECT unnest(enum_range(NULL::jobstatus))::text")))
        case_id, user_id = uuid.uuid4(), uuid.uuid4()
        from postgres.models.case import Case
        from postgres.models.user import User
        with Session(eng) as s:
            s.add(User(id=user_id, email=name + "@x.test", name="Synthetic", password_hash="x"))
            s.flush()
            s.add(Case(id=case_id, title="Synthetic", created_by_user_id=user_id, owner_user_id=user_id))
            s.commit()
        ext_id, cont_id = uuid.uuid4(), uuid.uuid4()
        doc = dict(extraction_id=ext_id, document_index=0)
        rows = [
            m.PhoneExtractionContainer(id=cont_id, case_id=case_id, container_kind="folder", stored_path="p",
                                       original_name="n", size_bytes=1, sha256="a" * 64, md5="b" * 32,
                                       intake_outcome="readable", classification={"roots": []}),
            m.PhoneExtraction(id=ext_id, case_id=case_id, report_set_sha256="c" * 64, first_container_id=cont_id,
                              form="full", capture_code_version="phone-capture-1"),
            m.PhoneExtractionContainerLink(extraction_id=ext_id, container_id=cont_id, root_path="r"),
            m.PhoneExtractionDocument(path="r.xml", role="full", size_bytes=1, sha256="d" * 64, md5="e" * 32, **doc),
            m.PhoneRecord(ordinal=1, top_ordinal=1, depth=0, model_type="Call", body=["model", None, None, None], **doc),
            m.PhoneFile(ordinal=1, body=["file", None, None, None], outcome="match", **doc),
            m.PhoneContainerEntry(extraction_id=ext_id, relpath="files/a", size_bytes=0),
            m.PhoneFileReference(record_ordinal=1, body_path="0", mechanism="jumptarget", reference_text="x",
                                 resolution="unresolved", **doc),
            m.PhoneTimestamp(owner_kind="record", owner_ordinal=1, body_path="0.0", value_type="TimeStamp",
                             original_text="t", offset_state="unparsed", parse_rule="unparsed", **doc),
            m.PhoneReconciliation(extraction_id=ext_id, document_index=0, counter_version="phone-counter-1",
                                  result="exact", source_totals={}, captured_totals={}),
            m.PhoneExtraInfo(ordinal=1, body=["extraInfo", None, None, None], **doc),
            m.PhoneExtraInfoNode(extra_ordinal=1, body_path="0.0", resolution="unresolved", **doc),
        ]
        with Session(eng) as s:
            for r in rows:
                s.add(r)
                s.flush()
            s.commit()
        with Session(eng) as s:
            for model in m.PHONE_CAPTURE_MODELS:
                assert len(s.scalars(select(model)).all()) == 1, model.__tablename__
            e = s.get(m.PhoneExtraction, ext_id)
            assert (e.capture_state, e.standing) == ("received", "pending")
        with pytest.raises(Exception):  # unique per (case_id, report_set_sha256), decision D22
            with Session(eng) as s:
                s.add(m.PhoneExtraction(case_id=case_id, report_set_sha256="c" * 64, first_container_id=cont_id,
                                        form="full", capture_code_version="phone-capture-1"))
                s.commit()
        r = _alembic(url, "downgrade", "20261101_timeline_view_instants")
        assert r.returncode != 0 and "phone extractions exist" in (r.stderr + r.stdout)
        eng.dispose()
    finally:
        with admin.connect() as c:
            c.execute(text("DROP DATABASE IF EXISTS " + name + " WITH (FORCE)"))
        admin.dispose()
