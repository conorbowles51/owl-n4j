"""Folder/archive -> interruption -> retained hierarchy -> one registration."""
import hashlib
import io
from pathlib import Path
from uuid import UUID, uuid4
import zipfile

from fastapi import HTTPException
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from postgres.base import Base
from postgres.models.evidence import EvidenceFile, EvidenceFolder
from postgres.models.evidence_upload import EvidenceUploadGroup
from routers import evidence_upload_groups as api
from services.evidence_db_storage import EvidenceDBStorage
from tests.test_resumable_uploads import uploads, send, action


@pytest.fixture
def groups(uploads, monkeypatch):
    f = uploads
    Base.metadata.create_all(f.engine, tables=[EvidenceUploadGroup.__table__])
    monkeypatch.setattr(api, 'authorize_case', api.uploads.authorize_case)
    f.client.app.include_router(api.router)
    return f


def start(f, content, *, kind='folder', identity=None, **changes):
    manifest = [dict(path=path, size=len(value), sha256=hashlib.sha256(value).hexdigest(),
        chunks=[hashlib.sha256(value[i:i+32]).hexdigest() for i in range(0, len(value), 32)])
        for path, value in content.items()]
    body = dict(id=str(identity or uuid4()), case_id=str(f.case), kind=kind, name='Synthetic selection', members=manifest, **changes)
    response = f.client.post('/api/evidence-upload-groups', json=body)
    assert response.status_code == 200, response.text
    return response.json(), body


def control(f, state, verb):
    return f.client.post(f"/api/evidence-upload-groups/{state['id']}/{verb}")


def stage(f, state, content):
    for member in state['members']:
        if member['status'] == 'staged': continue
        value = content[member['path']]
        for index in range((len(value) + 31) // 32):
            response = send(f, member, value, index)
            assert response.status_code == 200, response.text
        response = action(f, member, 'complete')
        assert response.json()['status'] == 'staged', response.text


def test_partial_folder_pause_return_and_lost_receipt_keep_paths_and_one_registration(groups):
    f = groups
    content = {'Bundle/a.txt': b'first ' * 20, 'Bundle/nested/a.txt': b'second ' * 20}
    state, body = start(f, content)
    member = state['members'][0]
    assert send(f, member, content[member['path']], 0).status_code == 200
    assert control(f, state, 'pause').json()['status'] == 'paused'
    assert send(f, member, content[member['path']], 1).status_code == 409
    assert action(f, member, 'resume').status_code == 409
    assert control(f, state, 'complete').status_code == 409
    listed = f.client.get('/api/evidence-upload-groups', params={'case_id': str(f.case)}).json()
    assert listed[0]['received_bytes'] == 32 and listed[0]['file_count'] == 2
    assert f.client.get('/api/evidence-upload-sessions', params={'case_id': str(f.case)}).json() == []
    state = control(f, state, 'resume').json()
    stage(f, state, content)
    with Session(f.engine) as db: assert not list(db.scalars(select(EvidenceFile)))
    response = control(f, state, 'complete')
    assert response.status_code == 200, response.text
    receipt = response.json()
    assert receipt['status'] == 'completed' and len(receipt['receipt']['file_ids']) == 2
    assert control(f, state, 'complete').json() == receipt
    assert f.client.post('/api/evidence-upload-groups', json=body).json() == receipt
    with Session(f.engine) as db:
        rows = list(db.scalars(select(EvidenceFile)))
        assert len(rows) == 2
        assert {r.metadata_['relative_path']: Path(r.stored_path).read_bytes() for r in rows} == content
        folders = {r.id: r for r in db.scalars(select(EvidenceFolder))}
        child = next(folder for folder in folders.values() if folder.name == 'nested')
        assert folders[child.parent_id].name == 'Bundle'
    assert f.client.get('/api/evidence-upload-groups', params={'case_id': str(f.case)}).json() == []


def test_final_registration_failure_rolls_back_and_same_named_later_upload_preserves_original_bytes(groups, monkeypatch):
    f = groups
    content = {'Folder/one.txt': b'original', 'Folder/two.txt': b'other'}
    state, _ = start(f, content); stage(f, state, content)
    original = EvidenceDBStorage.add_files
    calls = []
    def interrupted(*args, **kwargs):
        calls.append(1)
        result = original(*args, **kwargs)
        if len(calls) == 2: raise HTTPException(503, 'Synthetic registration interruption')
        return result
    monkeypatch.setattr(EvidenceDBStorage, 'add_files', interrupted)
    assert control(f, state, 'complete').status_code == 503
    with Session(f.engine) as db:
        assert not list(db.scalars(select(EvidenceFile)))
        assert db.get(EvidenceUploadGroup, UUID(state['id'])).receipt is None
    monkeypatch.setattr(EvidenceDBStorage, 'add_files', original)
    assert control(f, state, 'complete').json()['status'] == 'completed'
    later = {'Folder/one.txt': b'changed separately uploaded original'}
    newer, _ = start(f, later); stage(f, newer, later)
    assert control(f, newer, 'complete').json()['status'] == 'completed'
    with Session(f.engine) as db:
        assert sorted(Path(r.stored_path).read_bytes() for r in db.scalars(select(EvidenceFile))) == sorted([*content.values(), *later.values()])


def zipped(entries):
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w') as archive:
        for name, value in entries: archive.writestr(name, value)
    return out.getvalue()


def test_archive_reselection_retains_members_and_skips_os_metadata(groups):
    f = groups
    content = {'selection.zip': zipped([('Files/one.txt', b'one'), ('Files/sub/two.txt', b'two'), ('__MACOSX/._one', b'metadata')])}
    state, _ = start(f, content, kind='archive'); stage(f, state, content)
    receipt = control(f, state, 'complete').json()
    assert receipt['status'] == 'completed' and len(receipt['receipt']['file_ids']) == 2
    with Session(f.engine) as db:
        rows = list(db.scalars(select(EvidenceFile)))
        assert {r.metadata_['relative_path'] for r in rows} == {'Files/one.txt', 'Files/sub/two.txt'}
        assert all(r.metadata_['original_archive_sha256'] == hashlib.sha256(content['selection.zip']).hexdigest() for r in rows)


@pytest.mark.parametrize('entries', [[('../outside.txt', b'bad')], [('/absolute.txt', b'bad')], [('one.txt', b'one'), ('one.txt', b'two')]])
def test_unsafe_or_repeated_archive_paths_never_register(groups, entries):
    f = groups
    content = {'selection.zip': zipped(entries)}
    state, _ = start(f, content, kind='archive'); stage(f, state, content)
    assert control(f, state, 'complete').status_code == 400
    with Session(f.engine) as db: assert not list(db.scalars(select(EvidenceFile)))


def test_phone_report_lost_dispatch_ack_reuses_request_and_keeps_unrelated_files(groups, monkeypatch):
    f = groups
    content = {'Phone/report.xml': b'<report xmlns="http://pa.cellebrite.com/report/2.0"/>',
        'Phone/media/a.txt': b'phone data', 'Notes/notes.txt': b'ordinary uploaded evidence'}
    state, _ = start(f, content); stage(f, state, content)
    from services import evidence_engine_client
    dispatched = []
    async def dispatch(case_id, **kwargs):
        dispatched.append((case_id, kwargs))
        if len(dispatched) == 1: raise OSError('Lost acknowledgement after enqueue')
        return {'id': kwargs['request_id']}
    monkeypatch.setattr(evidence_engine_client, 'create_cellebrite_job', dispatch)
    assert control(f, state, 'complete').status_code == 503
    pending = f.client.get(f"/api/evidence-upload-groups/{state['id']}").json()
    assert pending['status'] == 'dispatching' and len(pending['receipt']['file_ids']) == 1
    receipt = control(f, state, 'complete').json()
    assert receipt['status'] == 'completed' and len(receipt['receipt']['job_ids']) == 1
    assert dispatched[0] == dispatched[1]
    with Session(f.engine) as db:
        assert [row.original_filename for row in db.scalars(select(EvidenceFile))] == ['notes.txt']
    assert control(f, state, 'complete').json() == receipt
    assert len(dispatched) == 2


def test_damaged_staged_chunk_can_be_reselected_and_restored(groups):
    f = groups; content = {'Folder/a.txt': b'synthetic data ' * 12}
    state, _ = start(f, content); stage(f, state, content)
    member = state['members'][0]
    path = f.root / 'pending' / str(f.case) / member['id'] / '0.part'
    path.write_bytes(b'x' * 32)
    assert control(f, state, 'complete').status_code == 409
    state = f.client.get(f"/api/evidence-upload-groups/{state['id']}").json()
    assert state['members'][0]['status'] == 'uploading'
    assert 0 not in state['members'][0]['received']
    stage(f, state, content)
    assert control(f, state, 'complete').json()['status'] == 'completed'


def test_selection_identity_and_case_are_checked_before_resume(groups):
    f = groups; content = {'Folder/a.txt': b'synthetic'}
    state, body = start(f, content)
    changed = {**body, 'members': [{**body['members'][0], 'sha256': 'a' * 64}]}
    assert f.client.post('/api/evidence-upload-groups', json=changed).status_code == 409
    assert f.client.get('/api/evidence-upload-groups', params={'case_id': str(uuid4())}).status_code == 403
    f.user.id = uuid4()
    assert control(f, state, 'resume').status_code == 404
