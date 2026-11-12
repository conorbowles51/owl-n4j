"""Binary upload -> pause/reselect -> receipt, using isolated local storage."""
import hashlib
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from postgres.base import Base
from postgres.models.case import Case
from postgres.models.user import User
from postgres.models.evidence import EvidenceFile, EvidenceFolder
from postgres.models.evidence_upload import EvidenceUploadSession
from routers import evidence_uploads as api


@pytest.fixture
def uploads(tmp_path, monkeypatch):
    engine = create_engine('sqlite://',poolclass=StaticPool,connect_args={'check_same_thread':False})
    Base.metadata.create_all(engine,tables=[User.__table__,Case.__table__,EvidenceFolder.__table__,EvidenceFile.__table__,EvidenceUploadSession.__table__])
    user = SimpleNamespace(id=uuid4(),email='synthetic@example.test')
    case = uuid4()
    monkeypatch.setattr(api,'CHUNK_SIZE',32)
    monkeypatch.setattr(api,'ROOT',tmp_path/'pending')
    monkeypatch.setattr(api,'EVIDENCE_DATA_ROOT',tmp_path/'evidence')
    def authorize(db, case_id, current, permission):
        if case_id != case: raise HTTPException(403,'Access denied')
    monkeypatch.setattr(api,'authorize_case',authorize)
    app = FastAPI(); app.include_router(api.router)
    def db_dependency():
        with Session(engine) as db:
            yield db
    app.dependency_overrides[api.get_db] = db_dependency
    app.dependency_overrides[api.get_current_db_user] = lambda:user
    with TestClient(app) as client:
        yield SimpleNamespace(client=client,engine=engine,case=case,user=user,root=tmp_path)
    engine.dispose()


def start(f, content=b'%PDF-synthetic-evidence-'*5, **overrides):
    body=dict(id=str(uuid4()),case_id=str(f.case),filename='synthetic.pdf',size=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
        chunks=[hashlib.sha256(content[i:i+32]).hexdigest() for i in range(0,len(content),32)])
    body.update(overrides)
    response=f.client.post('/api/evidence-upload-sessions',json=body)
    assert response.status_code==200,response.text
    return body, response.json(), content


def send(f, state, content, index):
    return f.client.put(f"/api/evidence-upload-sessions/{state['id']}/chunks/{index}",
        content=content[index*32:(index+1)*32],headers={'Content-Type':'application/octet-stream'})


def action(f,state,verb):
    return f.client.post(f"/api/evidence-upload-sessions/{state['id']}/{verb}")


def test_leave_resume_lost_ack_and_duplicate_complete_register_exactly_once(uploads):
    f=uploads;body,state,content=start(f)
    assert send(f,state,content,0).status_code==200
    assert action(f,state,'pause').json()['status']=='paused'
    assert send(f,state,content,1).status_code==409
    listed=f.client.get('/api/evidence-upload-sessions',params={'case_id':str(f.case)}).json()
    assert listed[0]['received']==[0] and listed[0]['status']=='paused'
    assert action(f,state,'complete').status_code==409
    assert action(f,state,'resume').json()['received']==[0]
    # Repeated chunk after an acknowledgement was lost is harmless.
    assert send(f,state,content,0).json()['received']==[0]
    for i in range(1,len(body['chunks'])):assert send(f,state,content,i).status_code==200
    receipt=action(f,state,'complete').json()
    assert receipt['status']=='completed' and receipt['evidence_id']
    assert action(f,state,'complete').json()==receipt
    assert f.client.get('/api/evidence-upload-sessions',params={'case_id':str(f.case)}).json()==[]
    with Session(f.engine) as db:
        rows=list(db.scalars(select(EvidenceFile)))
        assert len(rows)==1 and str(rows[0].id)==receipt['evidence_id']
        assert Path(rows[0].stored_path).read_bytes()==content
        assert rows[0].metadata_['upload_session_id']==state['id']


def test_damaged_saved_chunk_becomes_missing_and_can_be_repaired(uploads):
    f=uploads;body,state,content=start(f)
    for i in range(len(body['chunks'])):assert send(f,state,content,i).status_code==200
    part=f.root/'pending'/str(f.case)/state['id']/'1.part'
    part.write_bytes(b'x'*32)
    assert action(f,state,'complete').status_code==409
    snapshot=f.client.get(f"/api/evidence-upload-sessions/{state['id']}").json()
    assert 1 not in snapshot['received']
    assert send(f,state,content,1).status_code==200
    assert action(f,state,'complete').json()['status']=='completed'


def test_bad_manifest_content_and_cross_user_access_never_register_evidence(uploads):
    f=uploads;body,state,content=start(f)
    changed={**body,'sha256':'a'*64}
    assert f.client.post('/api/evidence-upload-sessions',json=changed).status_code==409
    assert f.client.put(f"/api/evidence-upload-sessions/{state['id']}/chunks/0",content=b'x'*32).status_code==409
    assert f.client.put(f"/api/evidence-upload-sessions/{state['id']}/chunks/0",content=b'x'*33).status_code==413
    assert send(f,state,content,99).status_code==400
    assert action(f,state,'complete').status_code==409
    f.user.id=uuid4()
    assert f.client.get(f"/api/evidence-upload-sessions/{state['id']}").status_code==404
    assert action(f,state,'resume').status_code==404
    with Session(f.engine) as db:assert not list(db.scalars(select(EvidenceFile)))


def test_wrong_whole_file_hash_fails_without_an_evidence_receipt(uploads):
    f=uploads;body,state,content=start(f,sha256='a'*64)
    for i in range(len(body['chunks'])):assert send(f,state,content,i).status_code==200
    assert action(f,state,'complete').status_code==409
    with Session(f.engine) as db:assert not list(db.scalars(select(EvidenceFile)))


@pytest.mark.parametrize('filename',['../private.pdf','..','a\\b.pdf','bad\x00.pdf'])
def test_unsafe_destinations_are_rejected(uploads,filename):
    f=uploads
    body=dict(id=str(uuid4()),case_id=str(f.case),filename=filename,size=0,sha256=hashlib.sha256(b'').hexdigest(),chunks=[])
    assert f.client.post('/api/evidence-upload-sessions',json=body).status_code==400


def test_completed_upload_removes_its_saved_parts_and_still_reports_every_chunk(uploads):
    f=uploads;body,state,content=start(f)
    for i in range(len(body['chunks'])):assert send(f,state,content,i).status_code==200
    parts=f.root/'pending'/str(f.case)/state['id']
    assert parts.is_dir() and len(list(parts.iterdir()))==len(body['chunks'])
    receipt=action(f,state,'complete').json()
    assert receipt['status']=='completed' and not parts.exists()
    assert receipt['received']==list(range(len(body['chunks'])))
    assert action(f,state,'complete').json()==receipt
    assert f.client.get(f"/api/evidence-upload-sessions/{state['id']}").json()==receipt


def test_sweep_removes_only_parts_of_completed_uploads(uploads, monkeypatch):
    f=uploads
    done,done_state,content=start(f)
    for i in range(len(done['chunks'])):send(f,done_state,content,i)
    open_body,open_state,_=start(f)
    send(f,open_state,content,0)
    action(f,done_state,'complete')
    # Parts left by the code before this change (it never removed them).
    left=f.root/'pending'/str(f.case)/done_state['id']; left.mkdir(parents=True)
    (left/'0.part').write_bytes(content[:32])
    stray=f.root/'pending'/str(f.case)/str(uuid4()); stray.mkdir(); (stray/'0.part').write_bytes(b'x')
    with Session(f.engine) as db:
        preview=api.sweep_completed_parts(db)
        assert (preview['folders'],preview['files'],preview['bytes'],preview['removed'])==(1,1,32,0)
        assert preview['left_other_status']==1 and preview['left_no_record']==1 and left.exists()
        assert api.sweep_completed_parts(db,apply=True)['removed']==1
    assert not left.exists() and stray.exists()
    assert (f.root/'pending'/str(f.case)/open_state['id']/'0.part').exists()


def test_sweep_keeps_parts_of_a_completed_upload_whose_evidence_is_gone(uploads):
    # The parts are then the only copy left (2 Nov: 34 such folders on live).
    f=uploads
    body,state,content=start(f)
    for i in range(len(body['chunks'])):send(f,state,content,i)
    receipt=action(f,state,'complete').json()
    left=f.root/'pending'/str(f.case)/state['id']; left.mkdir(parents=True)
    (left/'0.part').write_bytes(content[:32])
    with Session(f.engine) as db:
        db.execute(delete(EvidenceFile).where(EvidenceFile.id==UUID(receipt['evidence_id'])))
        db.commit()
        preview=api.sweep_completed_parts(db,apply=True)
        assert (preview['folders'],preview['removed'],preview['left_no_evidence'])==(0,0,1)
    assert (left/'0.part').exists()


def _large_body(f, size, name='bodycam.mp4'):
    chunk = 4 * 1024 * 1024
    return dict(id=str(uuid4()), case_id=str(f.case), filename=name, size=size, sha256='a' * 64,
        chunks=['b' * 64] * -(-size // chunk))


def test_a_file_over_one_gib_is_accepted_with_one_chunk_per_four_mib(uploads, monkeypatch):
    """12 Nov: a 1.313 GB body-cam video (314 chunks) was refused with a bare 422 by a 1 GiB / 256-chunk cap."""
    f = uploads
    monkeypatch.setattr(api, 'CHUNK_SIZE', 4 * 1024 * 1024)
    monkeypatch.setattr(api, 'free_bytes', lambda: 100 * 1024**3)
    body = _large_body(f, 1_313_000_000)
    assert len(body['chunks']) == 314
    response = f.client.post('/api/evidence-upload-sessions', json=body)
    assert response.status_code == 200, response.text
    assert response.json()['size'] == 1_313_000_000 and response.json()['received'] == []
    assert f.client.post('/api/evidence-upload-sessions', json=_large_body(f, 20 * 1024**3)).status_code == 200


def test_a_file_over_the_limit_or_the_free_space_is_refused_in_words_and_never_recorded(uploads, monkeypatch):
    f = uploads
    monkeypatch.setattr(api, 'CHUNK_SIZE', 4 * 1024 * 1024)
    too_large = f.client.post('/api/evidence-upload-sessions', json=_large_body(f, api.MAX_FILE_BYTES + 1))
    assert too_large.status_code == 413
    assert too_large.json()['detail'] == 'bodycam.mp4 is 64.0 GB; one file can be at most 64.0 GB, so it was not uploaded.'
    monkeypatch.setattr(api, 'free_bytes', lambda: 3 * 1024**3)
    no_room = f.client.post('/api/evidence-upload-sessions', json=_large_body(f, 2 * 1024**3, 'video.mov'))
    assert no_room.status_code == 507
    assert no_room.json()['detail'] == ('video.mov was not uploaded: it needs 4.0 GB of storage (4,294,967,296 bytes) '
        'and 3.0 GB (3,221,225,472 bytes) is free.')
    with Session(f.engine) as db:
        assert not list(db.scalars(select(EvidenceUploadSession)))


def test_assembly_runs_with_no_transaction_open(uploads, monkeypatch):
    """Assembling a file of many GB takes minutes (5 GB: 397 s on the server, 12 Nov); the session row lock or an open
    transaction held for it stalls a pause, a release and the database."""
    f = uploads
    opened = []
    def db_dependency():
        with Session(f.engine) as db:
            opened.append(db)
            yield db
    f.client.app.dependency_overrides[api.get_db] = db_dependency
    real = api.assemble
    seen = []
    def assemble(item):
        seen.append([db.in_transaction() for db in opened])
        return real(item)
    monkeypatch.setattr(api, 'assemble', assemble)
    body, state, content = start(f)
    for i in range(len(body['chunks'])): assert send(f, state, content, i).status_code == 200
    opened.clear()
    receipt = action(f, state, 'complete').json()
    assert receipt['status'] == 'completed' and receipt['evidence_id']
    assert seen == [[False]]


def test_a_pause_that_lands_during_assembly_is_kept(uploads, monkeypatch):
    f = uploads
    body, state, content = start(f)
    for i in range(len(body['chunks'])): assert send(f, state, content, i).status_code == 200
    real = api.assemble
    def assemble(item):
        assert action(f, state, 'pause').json()['status'] == 'paused'
        return real(item)
    monkeypatch.setattr(api, 'assemble', assemble)
    assert action(f, state, 'complete').status_code == 409
    monkeypatch.setattr(api, 'assemble', real)
    assert action(f, state, 'resume').json()['status'] == 'uploading'
    assert action(f, state, 'complete').json()['status'] == 'completed'
    with Session(f.engine) as db: assert len(list(db.scalars(select(EvidenceFile)))) == 1
