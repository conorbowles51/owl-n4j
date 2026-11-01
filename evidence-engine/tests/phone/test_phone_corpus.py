"""Corpus acceptance for capture (01 units 1.3 and 1.4) on the server reports C3, C9 and C8. Opt-in: needs
``LOUPE_PHONE_CORPUS`` and a scratch PostgreSQL at the alembic head (``LOUPE_TEST_PHONE_PG_URL``); the zip test also
needs ``LOUPE_PHONE_CORPUS_SCRATCH``. Run one report at a time, in the engine container with a memory limit.
Asserts counts and states only; no value from a report is read into the test or printed."""
from __future__ import annotations

import os
import uuid

import pytest

from . import corpus
from . import fixture_builder as fb

PG = os.getenv("LOUPE_TEST_PHONE_PG_URL")
pytestmark = pytest.mark.skipif(not (corpus.CORPUS and PG), reason=corpus.SKIP_REASON)


@pytest.fixture
def pg_case(tmp_path):
    from app.phone import store
    conn = store.connect(PG)
    uid, cid = uuid.uuid4(), uuid.uuid4()
    conn.execute("INSERT INTO users (id,email,name,password_hash,global_role,is_active,created_at,updated_at) VALUES "
                 "(%s,%s,'synthetic','x','user',true,now(),now())", (uid, "c%s@x.test" % uid.hex[:8]))
    conn.execute("INSERT INTO cases (id,title,status,archived,created_by_user_id,owner_user_id,created_at,updated_at) "
                 "VALUES (%s,'corpus capture test','active',false,%s,%s,now(),now())", (cid, uid, uid))
    (tmp_path / str(cid)).mkdir()
    yield conn, cid, tmp_path
    conn.execute("DELETE FROM phone_extractions WHERE case_id = %s", (cid,))
    conn.execute("DELETE FROM phone_extraction_containers WHERE case_id = %s", (cid,))
    conn.execute("DELETE FROM cases WHERE id = %s", (cid,))
    conn.execute("DELETE FROM users WHERE id = %s", (uid,))
    conn.close()


def capture(conn, case_id, data_root, label, container_path, root_path=""):
    from app.phone.runner import run_capture
    return run_capture(conn, data_root=str(data_root), case_id=case_id, container_path=container_path,
                       root_path=root_path, original_name=label)


@pytest.mark.parametrize("label", ["c3", "c9", "c8"])
def test_capture_reconciles_exactly_with_the_measured_counts(pg_case, label):
    conn, case_id, data_root = pg_case
    want = corpus.expected()[label]
    (data_root / str(case_id) / label).symlink_to(corpus.root(label))
    res = capture(conn, case_id, data_root, label, label)
    assert (res["state"], res["records"], res["files"]) == (want["state"], want["records"], want["files"])
    assert res["peak_rss"] < corpus.expected()["peak_rss_bytes_below"]
    ext = res["extraction_id"]
    q = lambda sql: conn.execute(sql, (ext,)).fetchall()
    # the latest reconciliation of every document is exact
    assert {r for (r,) in q("SELECT DISTINCT ON (document_index) result FROM phone_reconciliations "
                             "WHERE extraction_id = %s ORDER BY document_index, ran_at DESC")} == {"exact"}
    assert q("SELECT count(*) FROM phone_records WHERE extraction_id = %s")[0][0] == want["records"]
    assert q("SELECT count(*) FROM phone_files WHERE extraction_id = %s AND outcome IS NULL")[0][0] == 0


@pytest.mark.skipif(not corpus.SCRATCH, reason="Requires LOUPE_PHONE_CORPUS_SCRATCH (a writable folder)")
def test_the_c3_folder_and_a_zip_made_from_it_are_one_extraction_with_two_containers(pg_case):
    conn, case_id, data_root = pg_case
    (data_root / str(case_id) / "c3").symlink_to(corpus.root("c3"))
    zipped = os.path.join(corpus.SCRATCH, "c3-%s.zip" % uuid.uuid4().hex[:8])
    try:
        fb.zip_folder(corpus.root("c3"), zipped, wrapper="c3", compress=False)
        (data_root / str(case_id) / "c3.zip").symlink_to(zipped)
        first = capture(conn, case_id, data_root, "c3", "c3")
        second = capture(conn, case_id, data_root, "c3.zip", "c3.zip", "c3")
    finally:
        if os.path.exists(zipped):
            os.remove(zipped)
    assert first["state"] == "captured" and second["already_in_case"]
    assert second["extraction_id"] == first["extraction_id"]
    ext = first["extraction_id"]
    assert conn.execute("SELECT count(DISTINCT container_id) FROM phone_extraction_container_links "
                        "WHERE extraction_id = %s", (ext,)).fetchone()[0] == 2
    assert conn.execute("SELECT count(*) FROM phone_extractions WHERE case_id = %s", (case_id,)).fetchone()[0] == 1
