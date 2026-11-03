"""cb-media item F: a capture from a ZIP records each member's position in that archive, and the backfill fills the
same positions, through the same function, for entries listed before positions were recorded.

Opt-in through ``LOUPE_TEST_PHONE_PG_URL`` (a scratch PostgreSQL at the alembic head). Synthetic phone only.
"""
import os
import zipfile

import pytest

from . import fixture_builder as fb
from .test_files_timestamps import pg_case  # noqa: F401 (fixture)

PG = os.getenv("LOUPE_TEST_PHONE_PG_URL")
needs_pg = pytest.mark.skipif(not PG, reason="Requires LOUPE_TEST_PHONE_PG_URL (a scratch PostgreSQL at the alembic head)")


def test_a_zip_source_names_each_members_position(tmp_path):
    from app.phone import detect
    z = tmp_path / "C.zip"
    with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("R/a.txt", b"a" * 100)
        zf.writestr("R/files/Image/IMG", b"\xff\xd8\xff" + b"x" * 500)
    src = detect.open_source(str(z))
    info = zipfile.ZipFile(z).getinfo("R/files/Image/IMG")
    assert src.location("R/files/Image/IMG") == (info.header_offset, info.compress_size, info.compress_type, info.CRC)
    assert getattr(detect.FolderSource(str(tmp_path)), "location", None) is None


@needs_pg
def test_capture_from_a_zip_records_positions_and_the_backfill_refills_them(pg_case, tmp_path):
    from app.phone import backfill_offsets
    from app.phone.runner import run_capture
    conn, case_id = pg_case
    root = tmp_path / str(case_id)
    people = fb.invent_people(4, seed=5)
    spec = fb.PhoneSpec("S2", like="P09", scale=0.05, contacts=[p.key for p in people[1:]], seed=21)
    fb.PhoneBuild(spec, {p.key: p for p in people}, fb.load_catalogue()).write(root / "S2")
    fb.zip_folder(root / "S2", root / "S2.zip")
    res = run_capture(conn, data_root=str(tmp_path), case_id=case_id, container_path="S2.zip", root_path="S2")
    assert res["state"] == "captured", res
    ext, cid = res["extraction_id"], res["container_id"]
    rows = conn.execute("SELECT relpath, container_id::text, header_offset, compressed_size, compress_type, crc32 "
                        "FROM phone_container_entries WHERE extraction_id = %s ORDER BY relpath", (ext,)).fetchall()
    assert rows and all(r[1] == cid and r[2] is not None for r in rows)
    zf = zipfile.ZipFile(root / "S2.zip")
    for rel, _c, off, csize, method, crc in rows:
        i = zf.getinfo("S2/" + rel)
        assert (off, csize, method, crc) == (i.header_offset, i.compress_size, i.compress_type, i.CRC)
    # entries listed before positions were recorded: cleared, then filled by the backfill through the same function
    conn.execute("UPDATE phone_container_entries SET container_id = NULL, header_offset = NULL, compressed_size = NULL, "
                 "compress_type = NULL, crc32 = NULL WHERE extraction_id = %s", (ext,))
    dry = [r for r in backfill_offsets.run(conn, str(tmp_path), dry_run=True) if r["extraction_id"] == ext]
    assert dry == [{"extraction_id": ext, "container_id": cid, "entries_without_position": len(rows),
                    "state": "dry run"}]
    [done] = [r for r in backfill_offsets.run(conn, str(tmp_path)) if r["extraction_id"] == ext]
    assert done["filled"] == len(rows) and done["state"] == "filled"
    again = conn.execute("SELECT relpath, container_id::text, header_offset, compressed_size, compress_type, crc32 "
                         "FROM phone_container_entries WHERE extraction_id = %s ORDER BY relpath", (ext,)).fetchall()
    assert again == rows
    [second] = [r for r in backfill_offsets.run(conn, str(tmp_path)) if r["extraction_id"] == ext]
    assert second["state"] == "nothing to fill"


@needs_pg
def test_a_folder_capture_records_no_positions(pg_case, tmp_path):
    from app.phone.runner import run_capture
    conn, case_id = pg_case
    root = tmp_path / str(case_id)
    people = fb.invent_people(4, seed=6)
    spec = fb.PhoneSpec("S3", like="P09", scale=0.05, contacts=[p.key for p in people[1:]], seed=22)
    fb.PhoneBuild(spec, {p.key: p for p in people}, fb.load_catalogue()).write(root / "S3")
    res = run_capture(conn, data_root=str(tmp_path), case_id=case_id, container_path="S3", root_path="")
    assert res["state"] == "captured", res
    n, with_pos = conn.execute("SELECT count(*), count(header_offset) FROM phone_container_entries WHERE "
                               "extraction_id = %s", (res["extraction_id"],)).fetchone()
    assert n > 0 and with_pos == 0
