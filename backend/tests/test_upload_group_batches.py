"""Small files of a selection sent many to a request (lx-uploadspeed C), and a selection's file writes sharing its
lock (lx-uploadspeed B/D): every file is verified on its own, saved exactly as a single-file send saves it, and
registered as its own evidence row; a mismatched file is refused by name; repeats and pauses neither lose nor double
a file."""
import hashlib
import json
import os
from pathlib import Path
import resource
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from postgres.models.evidence import EvidenceFile
from postgres.models.evidence_upload import EvidenceUploadSession
from routers import evidence_upload_groups as api
from tests.test_resumable_upload_groups import groups, start, control, stage  # noqa: F401 (fixture)
from tests.test_resumable_uploads import uploads, send, action  # noqa: F401 (fixture)


def batch(f, state, files):
    """``files``: [(member, bytes)] as the page sends them: one JSON line, then the bytes back to back."""
    head = json.dumps({'files': [{'id': m['id'], 'size': len(v)} for m, v in files]}).encode() + b'\n'
    return f.client.put(f"/api/evidence-upload-groups/{state['id']}/files", content=head + b''.join(v for _, v in files),
                        headers={'Content-Type': 'application/octet-stream'})


def by_path(state):
    return {m['path']: m for m in state['members']}


CONTENT = {'Phone/a.txt': b'first small file', 'Phone/b.txt': b'second', 'Phone/empty.txt': b'',
           'Phone/sub/c.txt': b'third, still one part', 'Phone/big.bin': b'more than one part ' * 4}


def many(count):
    return {f'Phone/{i}.txt': b'file %d' % i for i in range(count)}


def open_files():
    return len(os.listdir('/proc/self/fd'))


def test_a_batch_of_more_files_than_the_worker_may_hold_open_is_saved_whole(groups):
    # Live 4 Nov 22:50: 500-file batches sent side by side ran a worker out of open files (limit 1024), a 500 for the
    # batch and for anything else that worker was doing. The limit here is lowered so one batch alone would reach it.
    f = groups
    content = many(api.BATCH_OPEN_FILES + 100)
    state, _ = start(f, content)
    members = by_path(state)
    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    resource.setrlimit(resource.RLIMIT_NOFILE, (open_files() + api.BATCH_OPEN_FILES + 50, hard))
    try:
        response = batch(f, state, [(members[p], v) for p, v in content.items()])
    finally:
        resource.setrlimit(resource.RLIMIT_NOFILE, (soft, hard))
    assert response.status_code == 200, response.text
    assert [r['status'] for r in response.json()['files']] == ['staged'] * len(content)
    listed = f.client.get(f"/api/evidence-upload-groups/{state['id']}").json()
    assert {m['path']: m['status'] for m in listed['members']} == {p: 'staged' for p in content}
    for member in listed['members']:
        with Session(f.engine) as db:
            row = db.get(EvidenceUploadSession, UUID(member['id']))
        assert api.uploads.assembled_path(row).read_bytes() == content[member['path']]


def test_a_batch_holds_its_files_open_in_bounded_groups_under_the_workers_slots(groups, monkeypatch):
    f = groups
    content = many(api.BATCH_OPEN_FILES * 2 + 1)
    state, _ = start(f, content)
    members = by_path(state)
    before = open_files()
    assert api.BATCH_OPEN_FILES * api.BATCH_SLOTS <= 1024 / 2
    seen = []
    fsync = os.fsync

    def counted(fd):
        seen.append((open_files() - before, api._batch_slots._value))
        return fsync(fd)
    monkeypatch.setattr(api.os, 'fsync', counted)
    assert batch(f, state, [(members[p], v) for p, v in content.items()]).status_code == 200
    assert len(seen) == len(content)
    # the request's own connections may come and go; 20 is their room
    assert max(held for held, _ in seen) <= api.BATCH_OPEN_FILES + 20
    assert {slots for _, slots in seen} == {api.BATCH_SLOTS - 1}
    assert api._batch_slots._value == api.BATCH_SLOTS


def test_a_failed_write_leaves_no_open_file_and_no_temporary_file(groups, monkeypatch):
    f = groups
    state, _ = start(f, CONTENT)
    members = by_path(state)
    fdopen, calls = os.fdopen, []

    def full(*args, **kwargs):
        calls.append(1)
        if len(calls) == 2: raise OSError(28, 'No space left on device')
        return fdopen(*args, **kwargs)
    client = api.os  # the disk fills on the second file of the batch
    monkeypatch.setattr(client, 'fdopen', full)
    before = open_files()
    try:
        response = batch(f, state, [(members['Phone/a.txt'], CONTENT['Phone/a.txt']),
                                    (members['Phone/b.txt'], CONTENT['Phone/b.txt'])])
    except OSError as error:  # the test client hands the server's error on
        assert error.errno == 28
    else:
        assert response.status_code == 500
    monkeypatch.setattr(client, 'fdopen', fdopen)
    assert open_files() <= before
    for path in ('Phone/a.txt', 'Phone/b.txt'):
        with Session(f.engine) as db:
            row = db.get(EvidenceUploadSession, UUID(members[path]['id']))
            assert row.status == 'uploading'
        target = api.uploads.assembled_path(row)
        assert [p.name for p in target.parent.iterdir() if p.name.startswith('tmp')] == []
    # the page's retry saves the batch whole
    response = batch(f, state, [(members['Phone/a.txt'], CONTENT['Phone/a.txt']),
                                (members['Phone/b.txt'], CONTENT['Phone/b.txt'])])
    assert [r['status'] for r in response.json()['files']] == ['staged'] * 2


def test_batch_saves_every_small_file_as_its_own_member_and_registers_one_evidence_row_each(groups):
    f = groups
    state, _ = start(f, CONTENT)
    members = by_path(state)
    small = [(members[p], v) for p, v in CONTENT.items() if p != 'Phone/big.bin']
    response = batch(f, state, small)
    assert response.status_code == 200, response.text
    assert [r['status'] for r in response.json()['files']] == ['staged'] * 4
    assert not any('error' in r for r in response.json()['files'])
    listed = f.client.get(f"/api/evidence-upload-groups/{state['id']}").json()
    saved = {m['path']: m for m in listed['members']}
    for path, value in CONTENT.items():
        if path == 'Phone/big.bin':
            assert saved[path]['status'] == 'uploading'
            continue
        # saved exactly as a finished single-file send: staged, every part received
        assert saved[path]['status'] == 'staged' and saved[path]['received'] == ([0] if value else [])
    # the big file still goes in parts; the selection then registers once, one evidence row per file
    stage(f, listed, CONTENT)
    receipt = control(f, state, 'complete').json()
    assert receipt['status'] == 'completed' and len(receipt['receipt']['file_ids']) == len(CONTENT)
    with Session(f.engine) as db:
        rows = list(db.scalars(select(EvidenceFile)))
        assert sorted(r.metadata_['relative_path'] for r in rows) == sorted(CONTENT)
        for r in rows:
            assert Path(r.stored_path).read_bytes() == CONTENT[r.metadata_['relative_path']]
            assert r.sha256 == hashlib.sha256(CONTENT[r.metadata_['relative_path']]).hexdigest()


def test_batch_refuses_a_file_whose_bytes_do_not_match_and_names_it_while_the_others_are_saved(groups):
    f = groups
    state, _ = start(f, CONTENT)
    members = by_path(state)
    response = batch(f, state, [(members['Phone/a.txt'], b'first small fil!'), (members['Phone/b.txt'], b'second')])
    assert response.status_code == 200, response.text
    first, second = response.json()['files']
    assert first['status'] == 'uploading' and 'a.txt does not match the fingerprint' in first['error']
    assert second == {'id': members['Phone/b.txt']['id'], 'status': 'staged'}
    with Session(f.engine) as db:
        assert db.get(EvidenceUploadSession, UUID(members['Phone/a.txt']['id'])).status == 'uploading'
    # nothing from the refused file reached the disk
    refused = api.uploads.ROOT / str(f.case) / members['Phone/a.txt']['id']
    assert not refused.exists() or not any(refused.iterdir())
    # the selection cannot be registered while that file is missing
    assert control(f, state, 'complete').status_code == 409


def test_a_repeated_batch_after_a_lost_response_neither_doubles_nor_changes_a_file(groups):
    f = groups
    content = {k: v for k, v in CONTENT.items() if k != 'Phone/big.bin'}
    state, _ = start(f, content)
    files = [(by_path(state)[p], v) for p, v in content.items()]
    assert batch(f, state, files).status_code == 200
    again = batch(f, state, files)
    assert again.status_code == 200 and [r['status'] for r in again.json()['files']] == ['staged'] * len(content)
    assert control(f, state, 'complete').json()['status'] == 'completed'
    with Session(f.engine) as db:
        rows = list(db.scalars(select(EvidenceFile)))
        assert sorted(r.metadata_['relative_path'] for r in rows) == sorted(content)


def test_a_paused_selection_refuses_a_batch_and_takes_it_after_resume(groups):
    f = groups
    content = {'Phone/a.txt': b'first small file', 'Phone/b.txt': b'second'}
    state, _ = start(f, content)
    files = [(by_path(state)[p], v) for p, v in content.items()]
    assert control(f, state, 'pause').json()['status'] == 'paused'
    assert batch(f, state, files).status_code == 409
    with Session(f.engine) as db:
        assert {r.status for r in db.scalars(select(EvidenceUploadSession))} == {'paused'}
    assert control(f, state, 'resume').json()['status'] == 'uploading'
    assert [r['status'] for r in batch(f, state, files).json()['files']] == ['staged', 'staged']


def test_a_batch_that_does_not_match_its_description_saves_nothing(groups):
    f = groups
    state, _ = start(f, CONTENT)
    members = by_path(state)
    # a file of more than one part belongs to the chunked send
    assert batch(f, state, [(members['Phone/b.txt'], b'second'),
                            (members['Phone/big.bin'], CONTENT['Phone/big.bin'])]).status_code == 400
    head = json.dumps({'files': [{'id': members['Phone/b.txt']['id'], 'size': 99}]}).encode() + b'\n'
    short = f.client.put(f"/api/evidence-upload-groups/{state['id']}/files", content=head + b'second')
    assert short.status_code == 400
    assert f.client.put(f"/api/evidence-upload-groups/{state['id']}/files", content=b'no description').status_code == 400
    with Session(f.engine) as db:
        assert {r.status for r in db.scalars(select(EvidenceUploadSession))} == {'uploading'}


def test_a_files_own_writes_share_the_selection_lock_and_pause_takes_it_alone(groups, monkeypatch):
    f = groups
    seen = []
    original = api.get_group

    def recording(db, identity, user, *, lock=False):
        seen.append(lock)
        return original(db, identity, user, lock=lock)
    monkeypatch.setattr(api, 'get_group', recording)
    content = {'Phone/a.txt': b'first small file', 'Phone/big.bin': CONTENT['Phone/big.bin']}
    state, _ = start(f, content)
    members = by_path(state)
    seen.clear()
    assert send(f, members['Phone/big.bin'], content['Phone/big.bin'], 0).status_code == 200
    assert batch(f, state, [(members['Phone/a.txt'], content['Phone/a.txt'])]).status_code == 200
    assert 'share' in seen and True not in seen
    seen.clear()
    for index in range(1, 3):
        assert send(f, members['Phone/big.bin'], content['Phone/big.bin'], index).status_code == 200
    assert action(f, members['Phone/big.bin'], 'complete').json()['status'] == 'staged'
    assert 'share' in seen and True not in seen
    seen.clear()
    assert control(f, state, 'pause').status_code == 200
    assert seen == [True]
    # on PostgreSQL the shared form is FOR SHARE, the sole form FOR UPDATE
    from sqlalchemy.dialects import postgresql
    query = select(api.EvidenceUploadGroup)
    assert 'FOR SHARE' in str(query.with_for_update(read=True).compile(dialect=postgresql.dialect()))


def test_on_postgresql_every_taker_queues_on_the_selection_advisory_lock_in_arrival_order():
    """Row locks let a new FOR SHARE pass a waiting FOR UPDATE, so back-to-back file writes could hold off a
    release's pause; the advisory lock in front of the row lock queues them fairly."""
    from types import SimpleNamespace
    import pytest
    from fastapi import HTTPException
    executed = []
    db = SimpleNamespace(get_bind=lambda: SimpleNamespace(dialect=SimpleNamespace(name='postgresql')),
                         execute=lambda statement, params=None: executed.append((str(statement), params)),
                         scalar=lambda query: None)
    identity = UUID('61b7d6d9-995d-4516-941f-a224a0c89254')
    for lock in ('share', True):
        with pytest.raises(HTTPException):
            api.get_group(db, identity, SimpleNamespace(id=None), lock=lock)
    assert executed == [
        ('SELECT pg_advisory_xact_lock_shared(hashtextextended(:k, 0))', {'k': f'loupe.upload_group:{identity}'}),
        ('SELECT pg_advisory_xact_lock(hashtextextended(:k, 0))', {'k': f'loupe.upload_group:{identity}'})]
    executed.clear()
    with pytest.raises(HTTPException):
        api.get_group(db, identity, SimpleNamespace(id=None))
    assert executed == []
