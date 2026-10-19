"""Binary upload -> pause/reselect -> receipt, using isolated local storage."""
import hashlib
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
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
