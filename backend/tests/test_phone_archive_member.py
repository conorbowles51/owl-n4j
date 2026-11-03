"""cb-media item F: a phone file kept inside an uploaded ZIP or UFDR opens, straight from the archive by its
recorded position, both on the Media screen and when collected into a dossier as evidence.

Before: such a file had no stored_path, so the phone_file resolver gave none and using it as evidence was refused
("its stored_path is unknown"); Media read the archive's whole directory on every open. Synthetic bytes only.
"""
from __future__ import annotations

import asyncio
import hashlib
import io
import zipfile
from types import SimpleNamespace

import pytest
from sqlalchemy import text

from services.phone import archive_member as AM


def _zip(members, method=zipfile.ZIP_DEFLATED):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", method) as zf:
        for name, data in members:
            zf.writestr(name, data)
    return buf.getvalue()


def _loc(raw, name):
    i = zipfile.ZipFile(io.BytesIO(raw)).getinfo(name)
    return i.header_offset, i.compress_size, i.compress_type, i.CRC, i.file_size


@pytest.mark.parametrize("method", [zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED])
def test_a_member_is_read_whole_from_its_offset(tmp_path, method):
    data = bytes(range(256)) * 4099 + b"tail"
    raw = _zip([("a/first.txt", b"x" * 5000), ("a/b/IMG_1", data), ("a/last", b"")], method)
    path = tmp_path / "C.zip"
    path.write_bytes(raw)
    with AM.open_at(path, *_loc(raw, "a/b/IMG_1")) as fh:
        got = fh.read()
    assert got == data
    with AM.open_at(path, *_loc(raw, "a/b/IMG_1")) as fh:  # read in pieces as a response streams it
        parts = []
        while True:
            b = fh.read(7777)
            if not b:
                break
            parts.append(b)
    assert b"".join(parts) == data
    with AM.open_at(path, *_loc(raw, "a/last")) as fh:
        assert fh.read() == b""


def test_damaged_bytes_raise_instead_of_returning_a_wrong_file(tmp_path):
    data = b"synthetic voice note " * 3000
    raw = bytearray(_zip([("PTT", data)], zipfile.ZIP_STORED))
    off, csize, method, crc, size = _loc(bytes(raw), "PTT")
    raw[off + 30 + len("PTT") + 100] ^= 0xFF  # one byte inside the member's data
    path = tmp_path / "C.zip"
    path.write_bytes(bytes(raw))
    with AM.open_at(path, off, csize, method, crc, size) as fh:
        with pytest.raises(AM.MemberDamaged):
            fh.read()


def test_a_position_that_does_not_hold_the_member_or_another_method_falls_back(tmp_path):
    raw = _zip([("a", b"1" * 100), ("b", b"2" * 100)])
    path = tmp_path / "C.zip"
    path.write_bytes(raw)
    off, csize, method, crc, size = _loc(raw, "b")
    assert AM.open_at(path, off + 1, csize, method, crc, size) is None          # not a local header
    assert AM.open_at(path, off, csize, zipfile.ZIP_BZIP2, crc, size) is None    # method not read here
    assert AM.open_at(path, None, csize, method, crc, size) is None              # nothing recorded


# ---- with the database: Media and collected links (needs the PostgreSQL template) --------------------------------

from tests.phone_pg import needs_template  # noqa: E402
from tests.test_phone_media import LINKED, world  # noqa: E402,F401 (fixture)
from tests.test_phone_mappings import hooks  # noqa: E402,F401 (fixture)

DATA = b"\xff\xd8\xff\xe0" + b"synthetic photo bytes " * 2000


async def _collect(it):
    return b"".join([b async for b in it])


def _in_zip(world, tmp_path, monkeypatch, offsets=True):
    engine, case, _, ext = world
    monkeypatch.setattr("config.EVIDENCE_DATA_ROOT", str(tmp_path))
    z = tmp_path / str(case) / "up" / "C.zip"
    z.parent.mkdir(parents=True)
    raw = _zip([("root/other.txt", b"o" * 999), ("root/chats/synthetic-a.jpg", DATA)])
    z.write_bytes(raw)
    off, csize, method, crc, size = _loc(raw, "root/chats/synthetic-a.jpg")
    with engine.begin() as c:
        c.execute(text("UPDATE phone_files SET disk_relpath = 'chats/synthetic-a.jpg', disk_size = :n, "
                       "disk_sha256 = :s, tags = 'Image' WHERE file_uid = :f"),
                  {"n": len(DATA), "s": hashlib.sha256(DATA).hexdigest(), "f": LINKED})
        cid = c.execute(text("SELECT first_container_id FROM phone_extractions WHERE id = :e"), {"e": ext}).scalar()
        c.execute(text("UPDATE phone_extraction_containers SET container_kind = 'zip', stored_path = 'up/C.zip' "
                       "WHERE id = :i"), {"i": cid})
        c.execute(text("DELETE FROM phone_extraction_container_links WHERE extraction_id = :e"), {"e": ext})
        c.execute(text("INSERT INTO phone_extraction_container_links (extraction_id, container_id, root_path) VALUES "
                       "(:e, :i, 'root')"), {"e": ext, "i": cid})
        c.execute(text("DELETE FROM phone_container_entries WHERE extraction_id = :e"), {"e": ext})
        c.execute(text(
            "INSERT INTO phone_container_entries (extraction_id, relpath, size_bytes, container_id, header_offset, "
            "compressed_size, compress_type, crc32) VALUES (:e, 'chats/synthetic-a.jpg', :n, :k, :o, :cs, :m, :crc)"),
            {"e": ext, "n": size, "k": cid if offsets else None, "o": off if offsets else None,
             "cs": csize if offsets else None, "m": method if offsets else None, "crc": crc if offsets else None})
    return engine, case


@needs_template
def test_f_media_opens_a_zip_kept_file_by_its_offset_without_reading_the_directory(world, tmp_path, monkeypatch):
    from services.phone import media
    engine, case = _in_zip(world, tmp_path, monkeypatch)

    def no_directory(*a, **k):
        raise AssertionError("the archive's directory was read")
    monkeypatch.setattr(zipfile, "ZipFile", no_directory)
    with engine.connect() as c:
        name, size, opener = media.content(c, case, LINKED)
    with opener() as fh:
        got = fh.read()
    assert (name, size) == ("synthetic-a.jpg", len(DATA))
    assert hashlib.md5(got).hexdigest() == hashlib.md5(DATA).hexdigest() and got == DATA


@needs_template
def test_f_an_entry_without_a_recorded_position_still_opens_through_the_directory(world, tmp_path, monkeypatch):
    from services.phone import media
    engine, case = _in_zip(world, tmp_path, monkeypatch, offsets=False)
    with engine.connect() as c:
        _name, size, opener = media.content(c, case, LINKED)
    with opener() as fh:
        assert fh.read() == DATA and size == len(DATA)


@needs_template
def test_f_a_zip_kept_file_collected_as_evidence_opens_with_the_members_bytes(world, tmp_path, monkeypatch):
    """The acceptance test: before, ensure_phone_file_evidence refused ("its stored_path is unknown")."""
    from sqlalchemy.orm import Session

    from routers import evidence as R
    from services import phone_files
    from services.phone import resolvers
    engine, case = _in_zip(world, tmp_path, monkeypatch)
    resolvers.register()
    with engine.connect() as c:
        owner = c.execute(text("SELECT created_by_user_id FROM cases WHERE id = :c"), {"c": case}).scalar()
    with Session(engine) as db:
        row, created = phone_files.ensure_phone_file_evidence(db, case_id=case, phone_file_id=LINKED,
                                                              user=SimpleNamespace(id=owner))
        db.commit()
        assert created and row.stored_path == "phone-file:%s" % LINKED and phone_files.is_member_locator(row.stored_path)
        resp = R._phone_file_response(db, row)
        body = asyncio.run(_collect(resp.body_iterator))
    assert hashlib.md5(body).hexdigest() == hashlib.md5(DATA).hexdigest()
    assert resp.headers["content-length"] == str(len(DATA)) and resp.media_type == "image/jpeg"


def test_a_corrupt_compressed_stream_is_refused_in_words(tmp_path):
    data = bytes(range(256)) * 400
    raw = bytearray(_zip([("V", data)], zipfile.ZIP_DEFLATED))
    off, csize, method, crc, size = _loc(bytes(raw), "V")
    start = off + 30 + 1
    for i in range(start, start + min(64, csize)):  # garble the start of the deflate stream itself
        raw[i] = 0xFF
    path = tmp_path / "C.zip"
    path.write_bytes(bytes(raw))
    with AM.open_at(path, off, csize, method, crc, size) as fh:
        with pytest.raises(AM.MemberDamaged):
            fh.read()
