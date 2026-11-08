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


def test_a_files_modified_time_is_kept_with_its_selection_and_a_selection_without_one_reads_as_none(groups):
    f = groups
    state, body = start(f, {'Bundle/a.txt': b'a' * 40, 'Bundle/b.txt': b'b' * 40})
    assert [member['modified'] for member in state['members']] == [None, None]
    body = dict(body, id=str(uuid4()), members=[dict(member, modified=1793906993123 + i)
                                                for i, member in enumerate(body['members'])])
    response = f.client.post('/api/evidence-upload-groups', json=body)
    assert response.status_code == 200, response.text
    assert [member['modified'] for member in response.json()['members']] == [1793906993123, 1793906993124]
    assert [member['modified'] for member in f.client.get(
        f"/api/evidence-upload-groups/{body['id']}").json()['members']] == [1793906993123, 1793906993124]


def test_final_registration_failure_rolls_back_and_same_named_later_upload_preserves_original_bytes(groups, monkeypatch):
    f = groups
    content = {'Folder/one.txt': b'original', 'Folder/two.txt': b'other'}
    state, _ = start(f, content); stage(f, state, content)
    original = EvidenceDBStorage.add_files_each
    calls = []
    def interrupted(*args, **kwargs):
        # The rows are written (flushed) when the interruption comes.
        calls.append(original(*args, **kwargs))
        raise HTTPException(503, 'Synthetic registration interruption')
    monkeypatch.setattr(EvidenceDBStorage, 'add_files_each', interrupted)
    assert control(f, state, 'complete').status_code == 503
    assert len(calls[0]) == 2
    with Session(f.engine) as db:
        assert not list(db.scalars(select(EvidenceFile)))
        assert db.get(EvidenceUploadGroup, UUID(state['id'])).receipt is None
    monkeypatch.setattr(EvidenceDBStorage, 'add_files_each', original)
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
    # registration rebuilds a file from its parts only when the file assembled on arrival is gone or fails its check
    assembled = next((f.root / 'evidence' / str(f.case) / '_uploads' / member['id']).iterdir())
    assembled.unlink()
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


def test_the_polled_list_counts_without_loading_members_and_a_group_lock_leaves_the_manifest_unread(groups):
    """A phone folder has tens of thousands of members. The uploads list (polled every 2 s) must give the same counts
    as the full snapshot without loading them, and each chunk or completion, which locks the group, must not decode
    the manifest (measured live: the cost per file grew with the folder)."""
    f = groups
    content = {'Bundle/saved.txt': b'saved ' * 12, 'Bundle/partial.txt': b'partial ' * 12, 'Bundle/untouched.txt': b'x' * 70}
    state, _ = start(f, content)
    by_path = {m['path']: m for m in state['members']}
    stage(f, dict(state, members=[by_path['Bundle/saved.txt']]), content)
    assert send(f, by_path['Bundle/partial.txt'], content['Bundle/partial.txt'], 0).status_code == 200
    with Session(f.engine) as db:
        group = api.get_group(db, UUID(state['id']), f.user, lock=True)
        assert 'manifest' not in group.__dict__  # deferred: not decoded by a lock
        full = api.snapshot(db, group, include_members=False)
        assert api.summary(db, group) == full
    assert full['staged_count'] == 1 and full['file_count'] == 3
    assert full['received_bytes'] == len(content['Bundle/saved.txt']) + 32
    listed = f.client.get('/api/evidence-upload-groups', params={'case_id': str(f.case)}).json()
    assert listed == [dict(full, registration={'state': 'idle'})]


def test_an_unfinished_selection_can_be_discarded_and_a_registered_one_cannot(groups):
    f = groups
    content = {'Bundle/saved.txt': b'saved ' * 12, 'Bundle/partial.txt': b'partial ' * 12}
    state, _ = start(f, content)
    by_path = {m['path']: m for m in state['members']}
    stage(f, dict(state, members=[by_path['Bundle/saved.txt']]), content)
    assert send(f, by_path['Bundle/partial.txt'], content['Bundle/partial.txt'], 0).status_code == 200
    pending = f.root / 'pending' / str(f.case)
    assert sorted(p.name for p in pending.iterdir()) == sorted(m['id'] for m in state['members'])
    response = control(f, state, 'discard')
    assert response.status_code == 200, response.text
    assert response.json() == dict(id=state['id'], status='discarded', file_count=2, saved_count=1)
    assert list(pending.iterdir()) == []
    assert f.client.get('/api/evidence-upload-groups', params={'case_id': str(f.case)}).json() == []
    with Session(f.engine) as db:
        assert db.scalars(select(EvidenceUploadGroup)).all() == [] and db.scalars(select(EvidenceFile)).all() == []
    assert control(f, state, 'discard').status_code == 404
    # a registered selection is evidence: refused, nothing removed
    other, _ = start(f, {'One/a.txt': b'one ' * 10})
    stage(f, other, {'One/a.txt': b'one ' * 10})
    assert control(f, other, 'complete').json()['status'] == 'completed'
    refused = control(f, other, 'discard')
    assert (refused.status_code, refused.json()['detail']) == (409, api.ALREADY_REGISTERED)
    with Session(f.engine) as db:
        assert len(db.scalars(select(EvidenceFile)).all()) == 1


def test_the_polled_list_asks_the_database_only_about_files_being_sent(groups):
    """Saved members keep their chunk folders, so on a phone folder the chunk folders grow to every member. The
    2 s poll must not list every unsaved member to find the one being sent (profiled live on a 43,123-file folder:
    40 % of the upload routes' time)."""
    from sqlalchemy import event
    f = groups
    content = {'Bundle/f%03d.txt' % i: b'v%03d ' % i * 8 for i in range(200)}
    content['Bundle/partial.txt'] = b'partial ' * 12
    state, _ = start(f, content)
    by_path = {m['path']: m for m in state['members']}
    stage(f, dict(state, members=[m for p, m in by_path.items() if p != 'Bundle/partial.txt']), content)
    assert send(f, by_path['Bundle/partial.txt'], content['Bundle/partial.txt'], 0).status_code == 200
    statements = []

    def seen(conn, cursor, statement, parameters, context, executemany):
        statements.append((statement, parameters))

    event.listen(f.engine, 'before_cursor_execute', seen)
    try:
        with Session(f.engine) as db:
            group = api.get_group(db, UUID(state['id']), f.user)
            statements.clear()
            listed = api.summary(db, group)
            asked = [s.replace('\n', ' ') for s, _ in statements
                     if 'evidence_upload_sessions' in s and 'count(' not in s]
            full = api.snapshot(db, group, include_members=False)
    finally:
        event.remove(f.engine, 'before_cursor_execute', seen)
    assert listed == full and listed['staged_count'] == 200
    assert listed['received_bytes'] == sum(len(v) for p, v in content.items() if p != 'Bundle/partial.txt') + 32
    # beyond the one aggregate count, only the members being sent are asked about, by id
    assert asked and all('evidence_upload_sessions.id IN (' in s for s in asked), asked


def test_registration_uses_each_file_as_it_arrived_and_rebuilds_only_one_that_fails_its_check(groups, monkeypatch):
    """Each file was assembled and verified when it arrived. Registration reads it back and checks it, then puts it
    in the case as a second name for the same bytes, instead of assembling it again and copying it (two more writes
    and disk flushes a file: about 8 ms of a file's 12.7 ms registration on a 43,123-file folder, live). A file that
    fails its check is rebuilt from its saved parts; where a link is not possible the file is copied and verified."""
    import os
    f = groups
    calls = []
    real_assemble = api.uploads.assemble
    monkeypatch.setattr(api.uploads, 'assemble', lambda row: calls.append(row.filename) or real_assemble(row))
    content = {'Bundle/a.txt': b'first ' * 20, 'Bundle/b.txt': b'second ' * 20, 'Bundle/c.txt': b'third ' * 20}
    state, _ = start(f, content)
    stage(f, state, content)
    arrived = len(calls)  # assembled once each as they arrived
    assert arrived == 3
    # one assembled file damaged after it arrived (same size, different bytes)
    with Session(f.engine) as db:
        from postgres.models.evidence_upload import EvidenceUploadSession
        damaged = next(r for r in db.scalars(select(EvidenceUploadSession)) if r.filename == 'b.txt')
        path = api.uploads.assembled_path(damaged)
    path.write_bytes(b'X' * len(content['Bundle/b.txt']))
    real_link = os.link

    def link(source, target):  # one file where a link is not possible: copied and verified instead
        if str(source).endswith('c.txt'):
            raise OSError('cross-device')
        return real_link(source, target)
    monkeypatch.setattr(api.os, 'link', link)
    response = control(f, state, 'complete')
    assert response.status_code == 200, response.text
    assert calls[arrived:] == ['b.txt']  # only the damaged one is assembled again
    with Session(f.engine) as db:
        rows = {r.metadata_['relative_path']: r for r in db.scalars(select(EvidenceFile))}
        sessions = {r.filename: r for r in db.scalars(select(EvidenceUploadSession))}
    assert {p: Path(r.stored_path).read_bytes() for p, r in rows.items()} == content
    assert os.path.samefile(rows['Bundle/a.txt'].stored_path, api.uploads.assembled_path(sessions['a.txt']))
    assert not os.path.samefile(rows['Bundle/c.txt'].stored_path, api.uploads.assembled_path(sessions['c.txt']))
    assert not list(api.payload_root(api.EvidenceUploadGroup(id=UUID(state['id']), case_id=f.case)).rglob(
        api.PARTIAL_PREFIX + '*'))


def _page_manifest(content):
    return [dict(path=path, size=len(value), sha256=hashlib.sha256(value).hexdigest(),
                 chunks=[hashlib.sha256(value[i:i+32]).hexdigest() for i in range(0, len(value), 32)])
            for path, value in sorted(content.items())]


def test_a_selection_larger_than_one_request_declares_its_total_and_registers_by_pages(groups):
    """01 D41. D9's reversal condition was met on 8 Nov: real productions hold 209,271 to 279,701 files, past
    the 200,000 one-request manifest cap, and the page was refused with an unexplained 422 after hashing for
    96 minutes. A larger selection now declares members_total at creation and sends the rest of its manifest
    in pages. Fails on the old code: members_total was refused as an unknown field (422)."""
    f = groups
    content = {'Prod/%02d.txt' % i: bytes([65 + i]) * (i + 1) for i in range(5)}
    manifest = _page_manifest(content)
    identity = str(uuid4())
    body = dict(id=identity, case_id=str(f.case), kind='folder', name='Prod',
                members=manifest[:2], members_total=5)
    first = f.client.post('/api/evidence-upload-groups', json=body)
    assert first.status_code == 200, first.text
    assert first.json()['file_count'] == 2 and first.json()['members_total'] == 5
    refused = f.client.post(f'/api/evidence-upload-groups/{identity}/complete')
    assert refused.status_code == 409 and 'declared 5 files but only 2 are listed' in refused.json()['detail']
    page = f.client.post(f'/api/evidence-upload-groups/{identity}/members', json={'members': manifest[2:4]})
    assert page.status_code == 200, page.text
    assert page.json()['file_count'] == 4
    # a page retried after a lost answer changes nothing
    again = f.client.post(f'/api/evidence-upload-groups/{identity}/members', json={'members': manifest[2:4]})
    assert again.status_code == 200 and again.json()['file_count'] == 4
    # a retried start compares its page against the grown manifest instead of refusing
    assert f.client.post('/api/evidence-upload-groups', json=body).status_code == 200
    last = f.client.post(f'/api/evidence-upload-groups/{identity}/members', json={'members': manifest[4:]})
    assert last.status_code == 200 and last.json()['file_count'] == 5
    state = f.client.get(f'/api/evidence-upload-groups/{identity}').json()
    assert sorted(m['path'] for m in state['members']) == sorted(content)
    stage(f, state, content)
    response = control(f, state, 'complete')
    assert response.status_code == 200, response.text
    assert len(response.json()['receipt']['file_ids']) == 5
    with Session(f.engine) as db:
        rows = list(db.scalars(select(EvidenceFile)))
        assert {r.metadata_['relative_path']: Path(r.stored_path).read_bytes() for r in rows} == content


def test_pages_past_the_total_a_changed_file_or_a_whole_selection_are_refused_in_words(groups):
    f = groups
    content = {'P/a.txt': b'aaa', 'P/b.txt': b'bbb', 'P/c.txt': b'ccc'}
    manifest = _page_manifest(content)
    identity = str(uuid4())
    body = dict(id=identity, case_id=str(f.case), kind='folder', name='P',
                members=manifest[:2], members_total=3)
    assert f.client.post('/api/evidence-upload-groups', json=body).status_code == 200
    changed = dict(manifest[0], sha256='0' * 64, chunks=['0' * 64])
    differs = f.client.post(f'/api/evidence-upload-groups/{identity}/members', json={'members': [changed]})
    assert differs.status_code == 409 and 'differs from the one already declared' in differs.json()['detail']
    extra = dict(manifest[0], path='P/d.txt')
    over = f.client.post(f'/api/evidence-upload-groups/{identity}/members',
                         json={'members': [manifest[2], extra]})
    assert over.status_code == 409 and 'past the 3 files it declared' in over.json()['detail']
    # declaring fewer files than the request carries
    short = dict(body, id=str(uuid4()), members_total=1)
    assert f.client.post('/api/evidence-upload-groups', json=short).status_code == 400
    # a selection that arrived whole takes no pages
    plain, _ = start(f, {'Q/a.txt': b'zz'})
    whole = f.client.post('/api/evidence-upload-groups/%s/members' % plain['id'],
                          json={'members': manifest[2:]})
    assert whole.status_code == 409 and 'arrived whole' in whole.json()['detail']
