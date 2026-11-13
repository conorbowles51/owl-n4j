"""Folder registration writes its rows together (lx-uploadfollow B): the same evidence rows, folders and activity
events as one registration call per file, which made 10 database round trips a file (measured on the live schema)."""
from pathlib import Path, PurePosixPath
import threading
from uuid import UUID

from sqlalchemy import event, select
from sqlalchemy.orm import Session

from postgres.base import Base
from postgres.models.activity_event import ActivityEvent
from postgres.models.evidence import EvidenceFile, EvidenceFolder
from postgres.models.evidence_upload import EvidenceUploadGroup
from routers import evidence_upload_groups as api
from services.evidence_db_storage import EvidenceDBStorage
from tests.test_resumable_upload_groups import control, groups, start  # noqa: F401 (fixture)
from tests.test_upload_group_batches import batch
from tests.test_resumable_uploads import uploads  # noqa: F401 (fixture)


def old_register_members(db, group, user, prepared):
    """The ordinary-file part of ``register_payload`` at 24606648: one folder lookup and one ``add_files`` call (its
    own duplicate lookup, insert and activity event) per file."""
    files = []
    for member in prepared['members']:
        path = PurePosixPath(member['path'])
        folder = api.folder_for_path(db, group, user, str(path.parent))
        records = EvidenceDBStorage.add_files(db, case_id=group.case_id, folder_id=folder,
            owner=user.email, created_by_id=user.id, files_data=[dict(
                original_filename=path.name, stored_path=member['stored_path'], sha256=member['sha256'],
                size=member['size'], metadata={'upload_group_id': str(group.id), 'relative_path': member['path']})])
        db.flush()
        files.extend(str(record.id) for record in records)
    return files


def selection():
    """200 files in nested folders: two pairs with the same bytes inside the selection, and one file whose bytes are
    already in the case (registered before the selection)."""
    content = {f'Phone dump/{"photos" if i % 3 else "docs/scans"}/item-{i:03d}.txt': b'synthetic file %d\n' % i
               for i in range(196)}
    content['Phone dump/copy-a.txt'] = content['Phone dump/copy-b.txt'] = b'the same bytes twice'
    content['Phone dump/docs/again.txt'] = content['Phone dump/photos/item-001.txt']
    content['Phone dump/known.txt'] = b'already in the case'
    return content


def register(f, monkeypatch, *, old):
    content = selection()
    with Session(f.engine) as db:
        [known] = EvidenceDBStorage.add_files(db, case_id=f.case, created_by_id=f.user.id, owner=f.user.email,
            files_data=[dict(original_filename='known.txt', stored_path=str(f.root / 'known'),
                             sha256=api.hashlib.sha256(b'already in the case').hexdigest(), size=19)])
        db.commit()
        known = known.id
    if old:
        original = api.register_payload

        def register_payload(db, group, user, prepared):
            ordinary, prepared['members'] = prepared['members'], []
            result = original(db, group, user, prepared)  # phones: none here
            assert result['file_ids'] == []
            result['file_ids'] = old_register_members(db, group, user, dict(prepared, members=ordinary))
            return result
        monkeypatch.setattr(api, 'register_payload', register_payload)
    state, _ = start(f, content)
    response = batch(f, state, [(m, content[m['path']]) for m in state['members']])
    assert [r['status'] for r in response.json()['files']] == ['staged'] * len(content), response.text
    statements = []
    listener = lambda *args: statements.append(args[2])  # noqa: E731
    event.listen(f.engine, 'before_cursor_execute', listener)
    try:
        # The answer waits for the end, whatever the box's load: every session here shares one SQLite connection, so
        # a poll while the registration runs would end its transaction. test_upload_group_registration_job follows a run.
        monkeypatch.setattr(api, 'COMPLETE_WAIT_SECONDS', 3600)
        receipt = control(f, state, 'complete').json()
    finally:
        event.remove(f.engine, 'before_cursor_execute', listener)
    assert receipt['status'] == 'completed', receipt
    with Session(f.engine) as db:
        folders = {r.id: r for r in db.scalars(select(EvidenceFolder))}

        def folder_path(identity):
            parts = []
            while identity:
                parts.append(folders[identity].name)
                identity = folders[identity].parent_id
            return '/'.join(reversed(parts))
        rows = {r.id: r for r in db.scalars(select(EvidenceFile).where(EvidenceFile.id != known))}
        path_of = {identity: row.metadata_['relative_path'] for identity, row in rows.items()}
        path_of[known] = 'known before'
        files = sorted(((r.metadata_['relative_path'], folder_path(r.folder_id), r.original_filename, r.sha256, r.size,
                        Path(r.stored_path).read_bytes(), r.status, r.owner, str(r.created_by_id), r.is_duplicate,
                        path_of.get(r.duplicate_of_id), r.source_type,
                        sorted(dict(r.metadata_, upload_group_id=r.metadata_['upload_group_id'] == state['id']).items()))
                       for r in rows.values()), key=repr)
        events = sorted(((e.action, str(e.case_id), e.details['kind'], e.details['file_count'],
                         folder_path(UUID(e.details['folder_id'])) if e.details['folder_id'] else None,
                         [(path_of[UUID(x['id'])], x['filename'], x['sha256'], x['size']) for x in e.details['files']])
                        for e in db.scalars(select(ActivityEvent))), key=repr)
        order = [path_of[UUID(i)] for i in receipt['receipt']['file_ids']]
    return dict(files=files, events=events, order=order, folders=sorted(map(folder_path, folders)),
                message=receipt['receipt']['message'], content=content), len(statements)


def test_registration_writes_the_same_rows_and_events_as_one_call_per_file(groups, monkeypatch):
    f = groups
    Base.metadata.create_all(f.engine, tables=[ActivityEvent.__table__])
    # The old code path, then the new one, each on an empty database.
    with monkeypatch.context() as patch:
        before, before_statements = register(f, patch, old=True)
    for table in (ActivityEvent, EvidenceFile, EvidenceFolder, api.EvidenceUploadSession, EvidenceUploadGroup):
        with Session(f.engine) as db:
            db.execute(table.__table__.delete())
            db.commit()
    after, after_statements = register(f, monkeypatch, old=False)
    content = before.pop('content')
    assert after.pop('content') == content
    assert len(before['files']) == len(content) == 200
    # The old path's receipt message is built here without its ordinary files (see ``register``).
    assert before.pop('message') == 'Uploaded 0 files. Folder structure is retained.'
    assert after.pop('message') == 'Uploaded 200 files. Folder structure is retained. Select Process to start ingestion.'
    for key in before:
        assert after[key] == before[key], (key, [x for x in after[key] if x not in before[key]][:3],
                                           [x for x in before[key] if x not in after[key]][:3])
    # Duplicates: inside the selection and against the file already stored.
    dup = {row[0]: row[10] for row in after['files'] if row[9]}
    assert dup == {'Phone dump/copy-b.txt': 'Phone dump/copy-a.txt', 'Phone dump/known.txt': 'known before',
                   'Phone dump/photos/item-001.txt': 'Phone dump/docs/again.txt'}
    # One event per file, and one for the file stored before the selection.
    assert len(after['events']) == 201 and all(e[3] == 1 for e in after['events'])
    # Far fewer round trips: about 10 a file before. SQLite cannot batch an insert with an autoincrement key, so the
    # activity events still count one each here; on PostgreSQL 500 files took 196 statements against 5,016.
    assert before_statements > 1500 and after_statements * 4 < before_statements, (before_statements, after_statements)


def test_files_are_checked_side_by_side_and_a_changed_file_still_stops_registration(groups, monkeypatch):
    f = groups
    content = {f'Folder/{i}.txt': b'file %d' % i for i in range(6)}
    state, _ = start(f, content)
    response = batch(f, state, [(m, content[m['path']]) for m in state['members']])
    assert [r['status'] for r in response.json()['files']] == ['staged'] * 6
    # Two checks must be inside at once to pass this barrier: one at a time times out and breaks it.
    together = threading.Barrier(2, timeout=30)
    original = api.matches

    def side_by_side(path, expected_hash, expected_size):
        together.wait()
        return original(path, expected_hash, expected_size)
    monkeypatch.setattr(api, 'matches', side_by_side)
    member = state['members'][3]
    with Session(f.engine) as db:
        row = db.get(api.EvidenceUploadSession, UUID(member['id']))
        stored = api.uploads.assembled_path(row)
    stored.chmod(0o644)
    stored.unlink()  # hard links share bytes: a new file, so the part it was saved with stays as it was
    stored.write_bytes(b'changed')
    (stored.parent.parent.parent.parent.parent / 'pending' / str(f.case) / member['id'] / '0.part').write_bytes(b'changed')
    with Session(f.engine) as db:
        before = len(list(db.scalars(select(EvidenceFile))))
    answer = control(f, state, 'complete')
    assert answer.status_code == 409, answer.text
    with Session(f.engine) as db:
        assert len(list(db.scalars(select(EvidenceFile)))) == before == 0


def test_a_folder_upload_leaves_out_the_files_macos_and_windows_add(groups, monkeypatch):
    """Case d5b330d1 (23 Sep upload) holds 1,435 macOS ``._`` files as evidence, 977 named .jpg: 4 KB of Finder data
    each, never a picture. The old code registered every one; the archive and single-file paths already left them out."""
    f = groups
    Base.metadata.create_all(f.engine, tables=[ActivityEvent.__table__])
    content = {'Chat/photo.jpg': b'\xff\xd8\xff\xe0\x00\x10JFIF\x00 a picture', 'Chat/._photo.jpg': b'\x00\x05\x16\x07Mac OS X',
               'Chat/.DS_Store': b'finder', 'Chat/Thumbs.db': b'windows', '__MACOSX/Chat/._x.jpg': b'mac',
               'Chat/notes.txt': b'kept'}
    state, _ = start(f, content)
    response = batch(f, state, [(m, content[m['path']]) for m in state['members']])
    assert [r['status'] for r in response.json()['files']] == ['staged'] * len(content), response.text
    monkeypatch.setattr(api, 'COMPLETE_WAIT_SECONDS', 3600)
    receipt = control(f, state, 'complete').json()
    assert receipt['status'] == 'completed', receipt
    with Session(f.engine) as db:
        kept = sorted(r.metadata_['relative_path'] for r in db.scalars(select(EvidenceFile)))
    assert kept == ['Chat/notes.txt', 'Chat/photo.jpg']
    assert len(receipt['receipt']['file_ids']) == 2
    assert receipt['receipt']['message'] == (
        'Uploaded 2 files. Folder structure is retained. Left out 4 system files that macOS or Windows adds to'
        ' folders (names starting ._, .DS_Store, Thumbs.db). Select Process to start ingestion.')
