"""File signatures, holds from model reading, the shared unpack and the malware sweep. Every test here fails on the
code before them: the unpack had no ratio check, and neither the signature nor the hold existed."""
from __future__ import annotations

import io
import socket
import struct
import threading
import uuid
import zipfile
from pathlib import Path, PurePosixPath
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from postgres.models.evidence import EvidenceFile
from routers import evidence as evidence_router
from routers import evidence_upload_groups as groups
from services import evidence_archive, evidence_malware, evidence_signature as sig
from services import evidence_processing_service as processing
from tests.test_evidence_upload_off_event_loop import app_world  # noqa: F401  (fixture)

PE = b'MZ' + b'\x00' * 58 + (128).to_bytes(4, 'little') + b'\x00' * 64 + b'PE\x00\x00' + b'\x00' * 200
ELF = b'\x7fELF\x02\x01\x01' + b'\x00' * 200
PDF = b'%PDF-1.7\n' + b'x' * 50


def both_paths(source, root):
    """Each upload route's unpack, by name, so a test cannot pass by covering only one."""
    return (('resumable', lambda: groups.extract_archive(source, root / 'a')),
            ('older', lambda: evidence_router._extract_archive_to_staging(source, root / 'b')))


def bomb(path, megabytes=300):
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED, allowZip64=True) as z, \
            z.open('zeros.txt', 'w', force_zip64=True) as f:
        for _ in range(megabytes):
            f.write(b'\x00' * (1 << 20))


@pytest.mark.parametrize('route', [0, 1])
def test_a_ratio_bomb_is_refused_on_both_paths_with_nothing_written(tmp_path, route):
    source = tmp_path / 'bomb.zip'
    bomb(source)
    with pytest.raises(HTTPException) as refused:
        both_paths(source, tmp_path)[route][1]()
    assert refused.value.status_code == 413 and 'expands to' in refused.value.detail
    written = [p for p in tmp_path.rglob('*') if p.is_file() and p != source]
    assert written == []


def test_a_highly_compressed_small_archive_is_still_unpacked(tmp_path):
    """The ratio limit starts at a size where an archive could matter: a few pages of repeated text are not a bomb."""
    source = tmp_path / 'small.zip'
    with zipfile.ZipFile(source, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('blank.txt', b' ' * (5 << 20))
    for _, unpack in both_paths(source, tmp_path):
        assert [m['size'] for m in unpack()] == [5 << 20]


@pytest.mark.parametrize('route', [0, 1])
def test_a_nested_archive_stays_one_file_on_both_paths(tmp_path, route):
    inner = io.BytesIO()
    with zipfile.ZipFile(inner, 'w') as z:
        z.writestr('inner.txt', 'inner')
    source = tmp_path / 'outer.zip'
    with zipfile.ZipFile(source, 'w') as z:
        z.writestr('inner.zip', inner.getvalue())
    members = both_paths(source, tmp_path)[route][1]()
    assert [m['size'] for m in members] == [len(inner.getvalue())]
    assert not any(p.name == 'inner.txt' for p in tmp_path.rglob('*'))
    stored = members[0].get('stored_path') or members[0]['staged_path']
    assert sig.signature_of_file('inner.zip', stored).detected == 'zip'


@pytest.mark.parametrize('route', [0, 1])
def test_links_and_passwords_are_refused_on_both_paths(tmp_path, route):
    source = tmp_path / 'link.zip'
    with zipfile.ZipFile(source, 'w') as z:
        info = zipfile.ZipInfo('l.txt')
        info.external_attr = 0o120777 << 16
        z.writestr(info, '/etc/passwd')
    with pytest.raises(HTTPException) as refused:
        both_paths(source, tmp_path)[route][1]()
    assert refused.value.status_code == 400


@pytest.mark.parametrize('route', [0, 1])
def test_too_many_entries_are_refused_on_both_paths(tmp_path, route, monkeypatch):
    monkeypatch.setattr(groups, 'MAX_ARCHIVE_ENTRIES', 3)
    monkeypatch.setattr(evidence_archive, 'MAX_ENTRIES', 3)
    source = tmp_path / 'many.zip'
    with zipfile.ZipFile(source, 'w') as z:
        for n in range(5):
            z.writestr(f'{n}.txt', 'x')
    monkeypatch.setitem(evidence_archive.unpack.__kwdefaults__, 'max_entries', 3)
    with pytest.raises(HTTPException) as refused:
        both_paths(source, tmp_path)[route][1]()
    assert refused.value.status_code == 413


def test_a_full_disk_is_said_before_anything_is_written(tmp_path, monkeypatch):
    source = tmp_path / 'a.zip'
    with zipfile.ZipFile(source, 'w') as z:
        z.writestr('a.txt', 'abc')
    usage = type('Usage', (), dict(free=evidence_archive.DISK_MARGIN_BYTES))
    monkeypatch.setattr(evidence_archive.shutil, 'disk_usage', lambda _: usage)
    with pytest.raises(HTTPException) as refused:
        groups.extract_archive(source, tmp_path / 'out')
    assert refused.value.status_code == 507 and not (tmp_path / 'out' / 'a.txt').exists()


def test_a_phone_zip_with_nothing_beside_its_report_needs_no_room(tmp_path, monkeypatch):
    """The phone path's exemption: its report stays in the zip, so a nearly full disk does not refuse it."""
    source = tmp_path / 'phone.zip'
    with zipfile.ZipFile(source, 'w') as z:
        z.writestr('Report/report.xml', '<project/>')
    usage = type('Usage', (), dict(free=0))
    monkeypatch.setattr(evidence_archive.shutil, 'disk_usage', lambda _: usage)
    readable = dict(outcome='readable', roots=[dict(root_path='Report')])
    assert groups.outside_report(source, tmp_path / 'p', readable, 'phone.zip') == []


@pytest.mark.parametrize('name,head,detected,match', [
    ('statement.pdf', PDF, 'pdf', 'match'),
    ('statement.pdf', PE, 'pe', 'mismatch'),
    ('report.txt', ELF, 'elf', 'mismatch'),
    ('photo.jpg', PDF, 'pdf', 'mismatch'),
    ('photo.jpg', b'\xff\xd8\xff\xe0' + b'\x00' * 40, 'image', 'match'),
    ('notes.txt', b'plain words\nand more', 'text', 'match'),
    ('data.json', b'{"a": 1}', 'text', 'match'),
    ('sheet.xlsx', b'PK\x03\x04' + b'\x00' * 40, 'zip', 'match'),
    ('no extension', PE, 'pe', 'unknown'),
    ('cache.exo', b'\x00\x01\x02\x03' * 20, None, 'unknown'),
    ('statement.pdf', b'', None, 'empty'),
    ('name.txt', b'MZ is the start of this text, not a program, and nothing here says otherwise.', 'text', 'match'),
])
def test_the_name_against_the_bytes(name, head, detected, match):
    found = sig.signature(name, head)
    assert (found.detected, found.match) == (detected, match)


@pytest.mark.parametrize('head,executable', [
    (PE, True), (ELF, True), (b'\xcf\xfa\xed\xfe' + b'\x00' * 40, True), (b'dex\n035\x00' + b'\x00' * 40, True),
    (b'\xca\xfe\xba\xbe\x00\x00\x00\x34', True), (b'#!/bin/sh\nrm -rf /tmp/x\n', False), (PDF, False),
])
def test_only_program_bytes_count_as_executable(head, executable):
    assert sig.signature('anything.bin', head).executable is executable


def test_unreadable_bytes_do_not_stop_a_registration(tmp_path):
    assert sig.signature_of_file('gone.pdf', tmp_path / 'gone.pdf').match == 'no_file'


def _upload(client, case_id, name, data):
    return client.post('/api/evidence/upload', data={'case_id': str(case_id)},
                       files={'files': (name, data, 'application/octet-stream')})


def test_a_renamed_program_is_kept_marked_and_held(app_world):
    client, SessionLocal, case_id, *_ = app_world
    response = _upload(client, case_id, 'invoice.pdf', PE)
    assert response.status_code == 200, response.text
    answer = response.json()
    [record] = answer['files']
    assert (record['file_type_stated'], record['file_type_detected'], record['file_type_match']) == ('pdf', 'pe', 'mismatch')
    assert (record['reading_hold'], record['reading_hold_reason']) == ('held', 'executable')
    assert 'does not match' in answer['message'] and 'held from reading' in answer['message']
    with SessionLocal() as db:
        row = db.query(EvidenceFile).one()
        assert (row.file_type_detected, row.reading_hold) == ('pe', 'held')
        assert Path(row.stored_path).read_bytes() == PE


def test_a_mislabelled_document_is_marked_and_never_held(app_world):
    client, SessionLocal, case_id, *_ = app_world
    [record] = _upload(client, case_id, 'photo.jpg', PDF).json()['files']
    assert (record['file_type_match'], record['reading_hold']) == ('mismatch', None)


def test_a_normal_file_stores_its_signature_and_says_nothing(app_world):
    client, SessionLocal, case_id, *_ = app_world
    answer = _upload(client, case_id, 'statement.pdf', PDF).json()
    assert answer['message'] == 'Uploaded 1 file'
    with SessionLocal() as db:
        row = db.query(EvidenceFile).one()
        assert (row.file_type_stated, row.file_type_detected, row.file_type_match) == ('pdf', 'pdf', 'match')


def _rows(SessionLocal, case_id, tmp_path):
    with SessionLocal() as db:
        out = {}
        for name, data in (('a.pdf', PDF), ('b.exe', PE)):
            path = tmp_path / name
            path.write_bytes(data)
            row = EvidenceFile(id=uuid.uuid4(), case_id=case_id, original_filename=name, stored_path=str(path),
                               size=len(data), sha256=name * 8, status='unprocessed')
            db.add(row)
            out[name] = row.id
        db.commit()
    return out


def test_a_held_file_is_left_out_of_a_send_and_the_rest_go(app_world):
    """An old row, never read, is read at the send: it cannot reach a model by predating the check."""
    client, SessionLocal, case_id, tmp_path, *_ = app_world
    ids = _rows(SessionLocal, case_id, tmp_path)
    import asyncio
    sent = AsyncMock(return_value=dict(job_ids=['j'], file_count=1, skipped_count=0, message='Processing 1 file(s)'))
    with patch.object(processing, '_send_files', sent), SessionLocal() as db:
        answer = asyncio.run(processing.process_db_files(db, case_id=case_id, file_ids=list(ids.values())))
    assert sent.await_args.kwargs['file_ids'] == [ids['a.pdf']]
    assert answer['held_ids'] == [str(ids['b.exe'])] and answer['skipped_count'] == 1
    assert 'not sent for reading' in answer['message']
    with SessionLocal() as db:
        assert db.get(EvidenceFile, ids['b.exe']).reading_hold == 'held'


def test_a_held_statement_is_refused_with_the_reason(app_world):
    client, SessionLocal, case_id, tmp_path, *_ = app_world
    ids = _rows(SessionLocal, case_id, tmp_path)
    import asyncio
    from services.financial.pdf_candidates import PdfMappingError
    with SessionLocal() as db, pytest.raises(PdfMappingError) as refused:
        asyncio.run(processing.process_db_files(db, case_id=case_id, file_ids=[ids['b.exe']],
                                                preparation_mode='pdf_review'))
    assert refused.value.status_code == 409 and 'not sent for reading' in str(refused.value)


def test_a_person_releases_a_hold_and_the_record_keeps_it(app_world):
    client, SessionLocal, case_id, *_ = app_world
    [record] = _upload(client, case_id, 'invoice.pdf', PE).json()['files']
    response = client.post(f"/api/evidence/{record['id']}/release-hold", json=dict(case_id=str(case_id)))
    assert response.status_code == 200, response.text
    released = response.json()
    assert (released['reading_hold'], released['reading_hold_reason']) == ('released', 'executable')
    assert released['reading_released_by'] and released['reading_released_at']
    assert client.post(f"/api/evidence/{record['id']}/release-hold",
                       json=dict(case_id=str(case_id))).status_code == 409
    with SessionLocal() as db:
        sendable, held = sig.split_held(db, case_id, [uuid.UUID(record['id'])], Path)
        assert held == []


def test_the_daily_read_marks_old_rows_and_leaves_updated_at(app_world):
    client, SessionLocal, case_id, tmp_path, *_ = app_world
    ids = _rows(SessionLocal, case_id, tmp_path)
    with SessionLocal() as db:
        (tmp_path / 'c.jpg').write_bytes(PDF)  # a document under an image's name: marked, never held
        db.add(EvidenceFile(id=uuid.uuid4(), case_id=case_id, original_filename='c.jpg',
                            stored_path=str(tmp_path / 'c.jpg'), size=len(PDF), sha256='c' * 64,
                            status='unprocessed'))
        db.commit()
        before = db.get(EvidenceFile, ids['b.exe']).updated_at
        dry = sig.read_unread(db, tmp_path, apply=False)
        assert dry['held'] == 1 and db.get(EvidenceFile, ids['b.exe']).reading_hold is None
        counts = sig.read_unread(db, tmp_path)
    assert (counts['match'], counts['mismatch'], counts['held']) == (2, 1, 1)
    with SessionLocal() as db:
        row = db.get(EvidenceFile, ids['b.exe'])
        assert (row.file_type_detected, row.reading_hold, row.updated_at) == ('pe', 'held', before)
        assert db.get(EvidenceFile, ids['a.pdf']).reading_hold is None
        assert sig.read_unread(db, tmp_path) == {}


class FakeClamd:
    """Speaks clamd's INSTREAM: length-prefixed chunks, a zero length, then one answer."""

    def __init__(self, answer):
        self.answer, self.received = answer, b''
        self.server = socket.create_server(('127.0.0.1', 0))
        self.address = self.server.getsockname()
        threading.Thread(target=self.serve, daemon=True).start()

    def serve(self):
        conn, _ = self.server.accept()
        reader = conn.makefile('rb')
        assert reader.read(10) == b'zINSTREAM\x00'
        while True:
            size = struct.unpack('!I', reader.read(4))[0]
            if not size:
                break
            self.received += reader.read(size)
        conn.sendall(self.answer + b'\x00')
        conn.close()


def test_a_clean_file_and_a_finding_read_from_the_scanner(tmp_path):
    path = tmp_path / 'f.bin'
    path.write_bytes(b'bytes')
    clean = FakeClamd(b'stream: OK')
    assert evidence_malware.scan_file(path, clean.address).state == 'clean'
    assert clean.received == b'bytes'
    found = evidence_malware.scan_file(path, FakeClamd(b'stream: Eicar-Test-Signature FOUND').address)
    assert (found.state, found.name) == ('found', 'Eicar-Test-Signature')
    limit = evidence_malware.scan_file(path, FakeClamd(b'INSTREAM size limit exceeded. ERROR').address)
    assert limit.state == 'failed'


def test_a_scanner_that_is_down_leaves_files_waiting(tmp_path):
    with socket.create_server(('127.0.0.1', 0)) as closed:
        address = closed.getsockname()
    with pytest.raises(evidence_malware.ScannerUnavailable):
        evidence_malware.scan_file(tmp_path, address)


def test_a_finding_marks_and_holds_and_never_deletes(app_world, monkeypatch):
    client, SessionLocal, case_id, tmp_path, *_ = app_world
    ids = _rows(SessionLocal, case_id, tmp_path)
    with SessionLocal() as db:
        db.get(EvidenceFile, ids['a.pdf']).malware_scan = 'waiting'
        db.commit()
    found = evidence_malware.ScanResult('found', 'Bad-Thing')
    assert evidence_malware.sweep(SessionLocal, Path, scan=lambda path: found) == 1
    with SessionLocal() as db:
        row = db.get(EvidenceFile, ids['a.pdf'])
        assert (row.malware_scan, row.reading_hold, row.reading_hold_reason, row.reading_hold_detail) == (
            'found', 'held', 'malware', 'Bad-Thing')
        assert Path(row.stored_path).read_bytes() == PDF


def test_the_switch_is_off_by_default_and_marks_nothing(monkeypatch, app_world):
    client, SessionLocal, case_id, *_ = app_world
    monkeypatch.delenv('LOUPE_MALWARE_SCAN', raising=False)
    assert evidence_malware.enabled() is False
    [record] = _upload(client, case_id, 'statement.pdf', PDF).json()['files']
    assert record['malware_scan'] is None
    monkeypatch.setenv('LOUPE_MALWARE_SCAN', '1')
    [record] = _upload(client, case_id, 'second.pdf', PDF + b'2').json()['files']
    assert record['malware_scan'] == 'waiting'
