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
from postgres.models.work import CaseTask, CaseTaskLink
from routers import evidence_upload_groups as api
from services.evidence_db_storage import EvidenceDBStorage
from tests.test_resumable_uploads import uploads, send, action


NAMESPACE = b'http://pa.cellebrite.com/report/2.0'


def synthetic_detect(base):
    """A stand-in for the engine's classification (01 section 2.5), enough for these synthetic selections:
    a folder's report roots are the directories of .xml files carrying the report namespace; a zip with a root
    report.xml is a readable UFDR; a .ufdr that is not a zip is protected; a zip holding a report folder is a zip
    with that root."""
    def classify(path):
        if path.is_dir():
            roots = sorted({'' if p.parent == path else p.parent.relative_to(path).as_posix()
                            for p in path.rglob('*.xml') if NAMESPACE in p.read_bytes()[:8192]})
            roots = [r for r in roots if not any(o != r and (not o or r.startswith(o + '/')) for o in roots)]
            return dict(container_kind='folder', outcome='readable' if roots else 'not_a_phone_report',
                        roots=[dict(root_path=r) for r in roots],
                        messages=[dict(code='report_found', text='Phone report found.')] if roots else [])
        if not zipfile.is_zipfile(path):
            if path.name.endswith('.ufdr'):
                return dict(container_kind='ufdr', outcome='protected_no_password', roots=[], messages=[dict(
                    code='protected_no_password', text='This UFDR file is protected.')])
            return dict(container_kind='single_document', outcome='not_a_phone_report', roots=[], messages=[])
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            if 'report.xml' in names:
                return dict(container_kind='ufdr', outcome='readable', roots=[dict(root_path='')], messages=[])
            roots = sorted({n.rsplit('/', 1)[0] if '/' in n else '' for n in names
                            if n.endswith('.xml') and NAMESPACE in archive.read(n)[:8192]})
        return dict(container_kind='zip', outcome='readable' if roots else 'not_a_phone_report',
                    roots=[dict(root_path=r) for r in roots], messages=[])
    calls = []

    async def detect(case_id, path):
        calls.append(path)
        return classify(base / case_id / path)
    detect.calls = calls
    return detect


@pytest.fixture
def groups(uploads, monkeypatch):
    f = uploads
    Base.metadata.create_all(f.engine, tables=[EvidenceUploadGroup.__table__, CaseTask.__table__,
                                               CaseTaskLink.__table__])
    monkeypatch.setattr(api, 'authorize_case', api.uploads.authorize_case)
    from services import evidence_engine_client
    f.detect = synthetic_detect(f.root / 'evidence')
    monkeypatch.setattr(evidence_engine_client, 'detect_phone_container', f.detect)
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


def recording_dispatch(monkeypatch, fail_first=False):
    from services import evidence_engine_client
    dispatched = []

    async def dispatch(case_id, **kwargs):
        dispatched.append((case_id, kwargs))
        if fail_first and len(dispatched) == 1: raise OSError('Lost acknowledgement after enqueue')
        return {'id': kwargs['request_id']}
    monkeypatch.setattr(evidence_engine_client, 'create_phone_capture_job', dispatch)
    return dispatched


REPORT = b'<?xml version="1.0"?><project xmlns="http://pa.cellebrite.com/report/2.0"/>'


def test_phone_report_folder_is_one_container_row_and_unrelated_files_stay_ordinary(groups, monkeypatch):
    f = groups
    content = {'Phone/report.xml': REPORT, 'Phone/files/a.txt': b'phone data', 'Phone/.DS_Store': b'x',
               'Notes/notes.txt': b'ordinary uploaded evidence'}
    state, _ = start(f, content); stage(f, state, content)
    dispatched = recording_dispatch(monkeypatch, fail_first=True)
    assert control(f, state, 'complete').status_code == 503
    pending = f.client.get(f"/api/evidence-upload-groups/{state['id']}").json()
    assert pending['status'] == 'dispatching' and len(pending['receipt']['file_ids']) == 2
    receipt = control(f, state, 'complete').json()
    assert receipt['status'] == 'completed' and len(receipt['receipt']['job_ids']) == 1
    assert dispatched[0] == dispatched[1]  # the same request after a lost acknowledgement
    case_id, item = dispatched[0]
    assert item['container_path'] == f"_upload_groups/{state['id']}/payload/Phone" and item['root_path'] == ''
    assert item['upload_sha256'] == api.folder_container_sha256(
        [(k[len('Phone/'):], len(v), hashlib.sha256(v).hexdigest()) for k, v in content.items() if k.startswith('Phone/')])
    with Session(f.engine) as db:
        rows = {row.original_filename: row for row in db.scalars(select(EvidenceFile))}
        assert set(rows) == {'notes.txt', 'Phone'}  # the report's own files are not evidence rows (01 D7)
        phone = rows['Phone']
        assert phone.source_type == 'phone_extraction' and str(phone.id) == item['container_evidence_id']
        assert phone.sha256 == item['upload_sha256'] and Path(phone.stored_path).is_dir()
        assert phone.size == sum(len(v) for k, v in content.items() if k.startswith('Phone/'))
        assert not list(db.scalars(select(CaseTask)))
    assert 'Phone report found.' in receipt['receipt']['message']
    assert control(f, state, 'complete').json() == receipt
    assert len(dispatched) == 2


def test_folder_container_digest_matches_the_engine():
    # evidence-engine/tests/phone/test_files_timestamps.py pins the same digest for the same folder
    members = [('a.txt', 3, hashlib.sha256(b'one').hexdigest()), ('sub/b.bin', 4, hashlib.sha256(b'two!').hexdigest()),
               ('.DS_Store', 1, hashlib.sha256(b'x').hexdigest()), ('__MACOSX/._a.txt', 1, hashlib.sha256(b'y').hexdigest())]
    assert api.folder_container_sha256(members) == '18211b100413cb6b6017f0c5e0a21ec95ecd4925d8a08ffcc54553f365049d44'


def test_zip_holding_a_phone_report_is_kept_whole_not_unpacked(groups, monkeypatch):
    f = groups
    archive = zipped([('Export/report.xml', REPORT), ('Export/files/a.jpg', b'synthetic image')])
    content = {'Export.zip': archive}
    state, _ = start(f, content, kind='archive'); stage(f, state, content)
    dispatched = recording_dispatch(monkeypatch)
    receipt = control(f, state, 'complete').json()
    assert receipt['status'] == 'completed', receipt
    [(case_id, item)] = dispatched
    assert item['container_path'] == f"_upload_groups/{state['id']}/payload/Export.zip"
    assert item['root_path'] == 'Export' and item['upload_sha256'] == hashlib.sha256(archive).hexdigest()
    with Session(f.engine) as db:
        [row] = list(db.scalars(select(EvidenceFile)))
        assert row.source_type == 'phone_extraction' and row.original_filename == 'Export.zip'
        assert Path(row.stored_path).read_bytes() == archive
    payload = f.root / 'evidence' / str(f.case) / '_upload_groups' / state['id'] / 'payload'
    assert sorted(p.name for p in payload.rglob('*')) == ['Export.zip']  # never unpacked


def test_protected_ufdr_is_kept_explained_and_opens_a_workspace_task(groups, monkeypatch):
    f = groups
    content = {'Handset.ufdr': b'\x2d\x06\x52\x6d' + b'synthetic protected bytes'}
    state, _ = start(f, content, kind='archive'); stage(f, state, content)
    dispatched = recording_dispatch(monkeypatch)
    receipt = control(f, state, 'complete').json()
    assert receipt['status'] == 'completed'
    assert 'This UFDR file is protected.' in receipt['receipt']['message']
    # dispatched so the capture job records the container and its hashes and stops with the explanation (D35)
    [(case_id, item)] = dispatched
    assert item['root_path'] == '' and item['container_path'].endswith('/payload/Handset.ufdr')
    with Session(f.engine) as db:
        [row] = list(db.scalars(select(EvidenceFile)))
        assert row.source_type == 'phone_extraction' and row.metadata_['phone_detect_outcome'] == 'protected_no_password'
        [task] = list(db.scalars(select(CaseTask)))
        assert task.title == 'Unprotected copy needed: Handset.ufdr' and task.status == 'todo'
        [link] = list(db.scalars(select(CaseTaskLink)))
        assert (link.target_type, link.target_id, link.task_id) == ('evidence', str(row.id), task.id)


def test_engine_unavailable_registers_nothing_and_finish_retries(groups, monkeypatch):
    f = groups
    content = {'Folder/a.txt': b'synthetic'}
    state, _ = start(f, content); stage(f, state, content)
    from services import evidence_engine_client
    real = evidence_engine_client.detect_phone_container

    async def down(case_id, path):
        raise OSError('engine not answering')
    monkeypatch.setattr(evidence_engine_client, 'detect_phone_container', down)
    response = control(f, state, 'complete')
    assert response.status_code == 503 and response.json()['detail'] == api.DETECT_UNAVAILABLE
    with Session(f.engine) as db: assert not list(db.scalars(select(EvidenceFile)))
    monkeypatch.setattr(evidence_engine_client, 'detect_phone_container', real)
    assert control(f, state, 'complete').json()['status'] == 'completed'


def test_ufdr_archives_and_large_folder_selections_are_accepted(groups):
    f = groups
    assert api.MAX_MEMBERS == 200_000
    _, body = start(f, {'Handset.ufdr': b'synthetic'}, kind='archive')
    bad = {**body, 'id': str(uuid4()), 'members': [{**body['members'][0], 'path': 'Handset.rar'}]}
    response = f.client.post('/api/evidence-upload-groups', json=bad)
    assert response.status_code == 400 and response.json()['detail'] == 'Select one ZIP or UFDR file'


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
