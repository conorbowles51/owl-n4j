"""Registration is a job the page follows (lx-uploadfollow C): ``complete`` answers before a large selection is
registered, the page reads "Registering n of N", and a server restart mid-registration leaves no half-registered
selection: it is started again and registers every file once."""
import os
import threading
import time
from types import SimpleNamespace
from uuid import UUID, uuid4

from fastapi import HTTPException
import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from postgres.models.evidence import EvidenceFile
from postgres.models.evidence_upload import EvidenceUploadGroup
from routers import evidence_upload_groups as api
from tests.test_resumable_upload_groups import control, groups, start  # noqa: F401 (fixture)
from tests.test_resumable_uploads import uploads  # noqa: F401 (fixture)
from tests.test_upload_group_batches import batch


@pytest.fixture
def held(groups, monkeypatch):
    """Registration answers at once, and its file checks wait for ``release``."""
    f = groups
    monkeypatch.setattr(api, 'COMPLETE_WAIT_SECONDS', 0)
    f.release, f.entered, f.prepares = threading.Event(), threading.Event(), []
    original = api.prepare_payload

    def prepare(group, rows, detect, progress=None):
        f.prepares.append(group.id)
        progress('checking', 1)
        f.entered.set()
        assert f.release.wait(60)
        return original(group, rows, detect, progress)
    monkeypatch.setattr(api, 'prepare_payload', prepare)
    yield f
    f.release.set()
    api._running.clear()


def staged(f, count=3):
    content = {f'Bundle/sub{i % 2}/file-{i}.txt': b'bytes %d' % i for i in range(count)}
    state, _ = start(f, content)
    response = batch(f, state, [(m, content[m['path']]) for m in state['members']])
    assert [r['status'] for r in response.json()['files']] == ['staged'] * count
    return state, content


def follow(f, state, until=('completed',), limit=60):
    """The page's polling, once this process's registration has ended: the test database is one SQLite connection
    shared by every session, so a read during the registration's own writes would end its transaction."""
    deadline = time.monotonic() + limit
    registration = api._running.get(UUID(state['id']))
    while registration is not None and not registration.task.done():
        assert time.monotonic() < deadline
        time.sleep(0.05)
    while True:
        answer = f.client.get(f"/api/evidence-upload-groups/{state['id']}/registration").json()
        if answer['status'] in until or answer['registration']['state'] in until:
            return answer
        assert time.monotonic() < deadline, answer
        time.sleep(0.05)


def evidence_rows(f):
    with Session(f.engine) as db:
        return db.scalar(select(func.count()).select_from(EvidenceFile))


def test_complete_answers_before_registration_ends_and_the_page_reads_how_far_it_has_come(held):
    f = held
    state, content = staged(f)
    answer = control(f, state, 'complete')
    assert answer.status_code == 200, answer.text
    answer = answer.json()
    assert answer['status'] == 'uploading' and answer['receipt'] is None
    assert answer['registration']['state'] == 'running' and answer['file_count'] == 3
    assert f.entered.wait(30)
    now = f.client.get(f"/api/evidence-upload-groups/{state['id']}/registration").json()
    assert now['registration'] == dict(state='running', phase='checking', done=1, total=3)
    # The uploads list says it too (the panel shows "Registering 1 of 3 files").
    [listed] = f.client.get('/api/evidence-upload-groups', params={'case_id': str(f.case)}).json()
    assert listed['registration']['done'] == 1 and listed['registration']['total'] == 3
    # Asking again (a second tab, Finish registration) does not start a second registration.
    assert control(f, state, 'complete').json()['registration']['state'] == 'running'
    assert evidence_rows(f) == 0
    f.release.set()
    done = follow(f, state)
    assert done['status'] == 'completed' and len(done['receipt']['file_ids']) == 3
    assert done['registration']['state'] == 'done'
    assert evidence_rows(f) == 3 and f.prepares == [UUID(state['id'])]
    # Complete after the receipt answers with it at once, as before.
    assert control(f, state, 'complete').json()['receipt'] == done['receipt']


def test_a_registration_stopped_midway_leaves_no_rows_and_runs_again_to_one_registration(held):
    f = held
    state, content = staged(f, 4)
    assert control(f, state, 'complete').json()['registration']['state'] == 'running'
    assert f.entered.wait(30)
    # The server process ends (a release restarts it): its registration task is cancelled and its memory is gone.
    registration = api._running[UUID(state['id'])]
    f.client.portal.call(registration.task.cancel)
    deadline = time.monotonic() + 30
    while not registration.task.done():
        assert time.monotonic() < deadline
        time.sleep(0.05)
    api._running.clear()
    f.release.set()
    time.sleep(0.2)
    assert evidence_rows(f) == 0
    with Session(f.engine) as db:
        assert db.get(EvidenceUploadGroup, UUID(state['id'])).receipt is None
    stopped = f.client.get(f"/api/evidence-upload-groups/{state['id']}/registration").json()
    assert stopped['status'] == 'uploading' and stopped['registration'] == {'state': 'idle'}
    # The page starts it again; every file is registered once.
    f.entered.clear()
    assert control(f, state, 'complete').json()['registration']['state'] == 'running'
    done = follow(f, state)
    assert done['status'] == 'completed' and len(done['receipt']['file_ids']) == 4 and evidence_rows(f) == 4


def test_a_registration_that_fails_says_why_to_the_page(held, monkeypatch):
    f = held
    state, _ = staged(f)
    f.release.set()

    def unavailable(case_id):
        def detect(path):
            raise HTTPException(503, api.DETECT_UNAVAILABLE)
        return detect
    monkeypatch.setattr(api, 'engine_detector', unavailable)
    control(f, state, 'complete')
    failed = follow(f, state, until=('failed',))
    assert failed['registration']['error'] == dict(status_code=503, detail=api.DETECT_UNAVAILABLE)
    assert failed['status'] == 'uploading' and evidence_rows(f) == 0


def test_a_short_registration_still_answers_complete_with_its_receipt(groups):
    f = groups
    state, _ = staged(f)
    receipt = control(f, state, 'complete').json()
    assert receipt['status'] == 'completed' and len(receipt['receipt']['file_ids']) == 3


def test_the_receipt_does_not_wait_for_saved_parts_to_be_removed(groups, monkeypatch):
    f = groups
    gate, removed, original = threading.Event(), [], api.uploads.remove_parts

    def slow_removal(item):
        gate.wait(2)
        removed.append(item.id)
        original(item)
    monkeypatch.setattr(api.uploads, 'remove_parts', slow_removal)
    state, _ = staged(f)
    parts = [api.uploads.ROOT / str(f.case) / m['id'] for m in state['members']]
    assert all(path.is_dir() for path in parts)
    answer = control(f, state, 'complete').json()
    assert answer['status'] == 'completed' and len(answer['receipt']['file_ids']) == 3
    assert removed == []
    gate.set()
    api._parts_remover.submit(lambda: None).result(30)  # one worker, in order: everything before this has run
    assert len(removed) == 3 and not any(path.exists() for path in parts)


def test_refusals_answer_complete_at_once(groups):
    f = groups
    content = {'Bundle/a.txt': b'a', 'Bundle/b.txt': b'b'}
    state, _ = start(f, content)
    response = control(f, state, 'complete')
    assert response.status_code == 409 and 'have not finished uploading' in response.json()['detail']
    assert control(f, state, 'pause').json()['status'] == 'paused'
    assert control(f, state, 'complete').status_code == 409
    assert UUID(state['id']) not in api._running


@pytest.mark.skipif(not os.environ.get('LOUPE_TEST_LOCAL_POSTGRES_URL'),
                    reason='Requires an explicit local PostgreSQL test connection (LOUPE_TEST_LOCAL_POSTGRES_URL)')
def test_on_postgresql_another_server_process_reads_progress_and_a_stopped_heartbeat():
    from sqlalchemy import create_engine
    from postgres.base import Base
    from postgres.models.case import Case
    from postgres.models.evidence import EvidenceFile, EvidenceFolder
    from postgres.models.evidence_upload import EvidenceUploadRegistration
    from postgres.models.user import User
    engine = create_engine(os.environ['LOUPE_TEST_LOCAL_POSTGRES_URL'])
    # evidence_files too: the Deleted-items filter (postgres/soft_delete.py, on by default) reads the deleted cases
    # and files before an ORM read of a table that points at a case.
    Base.metadata.create_all(engine, tables=[User.__table__, Case.__table__, EvidenceFolder.__table__,
                                             EvidenceFile.__table__, EvidenceUploadGroup.__table__,
                                             EvidenceUploadRegistration.__table__])
    user, case, group = uuid4(), uuid4(), uuid4()
    try:
        with engine.begin() as c:
            c.execute(text("insert into users(id,email,name,password_hash,global_role,is_active) "
                           "values (:u,:e,'Synthetic','x','user',true)"), dict(u=user, e=f'{user}@example.test'))
            c.execute(text("insert into cases(id,title,created_by_user_id,owner_user_id) values (:c,'S',:u,:u)"),
                      dict(c=case, u=user))
            c.execute(text("insert into evidence_upload_groups(id,case_id,user_id,name,kind,replace_existing,manifest,"
                           "status) values (:g,:c,:u,'S','folder',false,'[]','uploading')"), dict(g=group, c=case, u=user))
        registration = api.Registration(group, 5000)
        registration.phase, registration.done = 'checking', 1234
        with Session(engine) as db:
            # Held by the registration's own transaction meanwhile: the progress is written outside it.
            db.execute(select(EvidenceUploadGroup).where(EvidenceUploadGroup.id == group).with_for_update())
            api._registration_store(engine, registration)
            with Session(engine) as other:
                assert api._stored_registration(other, group) == dict(state='running', phase='checking', done=1234,
                                                                      total=5000)
            db.rollback()
        with engine.begin() as c:
            c.execute(text("update evidence_upload_registrations set heartbeat_at = now() - interval '45 seconds' "
                           "where group_id = :g"), dict(g=group))
        with Session(engine) as other:
            assert api._stored_registration(other, group)['state'] == 'stopped'
        registration.error = dict(status_code=409, detail='A saved upload failed verification.')
        api._registration_store(engine, registration, finished=True)
        with Session(engine) as other:
            assert api._stored_registration(other, group)['state'] == 'failed'
            assert api._stored_registration(other, group)['error']['status_code'] == 409
        # That failure stays in this process's memory for a while. The user retries and another server process
        # runs it: its heartbeat makes the row "running" again, and this process answers with the newer run.
        finished = api.Registration(group, 5000)
        finished.error, finished.task = registration.error, SimpleNamespace(done=lambda: True)
        api._running[group] = finished
        retry = api.Registration(group, 5000)
        retry.phase, retry.done = 'checking', 10
        api._registration_store(engine, retry)
        with Session(engine) as other:
            assert api._registration_state(other, group) == dict(state='running', phase='checking', done=10,
                                                                 total=5000)
        api._running.pop(group, None)
    finally:
        with engine.begin() as c:
            c.execute(text('delete from evidence_upload_groups where id = :g'), dict(g=group))
            c.execute(text('delete from cases where id = :c'), dict(c=case))
            c.execute(text('delete from users where id = :u'), dict(u=user))
        engine.dispose()
