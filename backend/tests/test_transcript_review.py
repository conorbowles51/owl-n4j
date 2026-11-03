import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from postgres.base import Base
from postgres.models.case import Case
from postgres.models.user import User
from postgres.models.case_membership import CaseMembership
from postgres.permissions import OWNER_PERMISSIONS
from postgres.models.evidence import EvidenceFile, EvidenceFolder
from postgres.models.transcript import TranscriptSource, TranscriptRevision, TranscriptState, TranscriptReview, EvidenceProcessingPlan
from services.transcript_review import capture_source, read_transcript, save_draft, approve_revision, render_revision
from fastapi import HTTPException


@pytest.fixture()
def transcript_db(monkeypatch):
    monkeypatch.setenv('AUDIO_TRANSCRIPT_REVIEW_ENABLED', '1')
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine, tables=[User.__table__, Case.__table__, CaseMembership.__table__, EvidenceFolder.__table__, EvidenceFile.__table__,
        TranscriptSource.__table__, TranscriptRevision.__table__, TranscriptState.__table__, TranscriptReview.__table__, EvidenceProcessingPlan.__table__])
    with Session(engine, expire_on_commit=False, autoflush=False) as db:
        owner = User(email='audio@example.test', name='Audio tester', password_hash='x')
        db.add(owner); db.flush()
        case = Case(title='Synthetic audio review', created_by_user_id=owner.id, owner_user_id=owner.id)
        db.add(case); db.flush()
        db.add(CaseMembership(case_id=case.id, user_id=owner.id, membership_role='owner', permissions=OWNER_PERMISSIONS, added_by_user_id=owner.id))
        file = EvidenceFile(case_id=case.id, original_filename='call.wav', stored_path='/synthetic/call.wav',
                            sha256='a' * 64, size=100)
        db.add(file); db.commit()
        yield db, file, owner


def test_saved_corrections_and_approval_preserve_original(transcript_db):
    db, file, owner = transcript_db
    raw = [{'id': '1', 'speaker': 'A', 'start': 0, 'end': 1, 'text': 'I spoke to Erc.'},
           {'id': '2', 'speaker': 'B', 'start': 1, 'end': 2, 'text': 'Yes.'}]
    capture_source(db, file, job_id=str(uuid.uuid4()), text='I spoke to Erc. Yes.', segments=raw)
    initial = read_transcript(db, file)
    saved = save_draft(db, file, initial['revision_id'], {
        'speakers': {'A': 'John', 'B': 'Eric'}, 'text_overrides': {'1': 'I spoke to Eric.'}}, owner.id)
    assert saved['segments'][0]['text'] == 'I spoke to Eric.'
    assert saved['speakers'] == {'A': 'John', 'B': 'Eric'}
    assert saved['review_state'] == 'awaiting_review'
    approved = approve_revision(db, file, saved['revision_id'], owner.id, 'approve-1')
    assert approved['review_state'] == 'ready'
    db.commit(); db.expire_all()
    assert read_transcript(db, file)['revision_id'] == saved['revision_id']
    assert file.transcription_segments == raw
    assert file.transcription == 'I spoke to Erc. Yes.'


def test_revision_conflict_and_edit_after_approval(transcript_db):
    db, file, owner = transcript_db
    capture_source(db, file, job_id=str(uuid.uuid4()), text='Hello',
                   segments=[{'id': '1', 'speaker': 'A', 'start': 0, 'end': 1, 'text': 'Hello'}])
    first = read_transcript(db, file)
    approve_revision(db, file, first['revision_id'], owner.id, 'review')
    unchanged = save_draft(db, file, first['revision_id'], {}, owner.id)
    assert unchanged['review_state'] == 'ready'
    changed = save_draft(db, file, first['revision_id'], {'text_overrides': {'1': 'Hi'}}, owner.id)
    assert changed['review_state'] == 'awaiting_review'
    with pytest.raises(HTTPException) as conflict:
        save_draft(db, file, first['revision_id'], {'speakers': {'A': 'John'}}, owner.id)
    assert conflict.value.status_code == 409
    assert read_transcript(db, file)['segments'][0]['text'] == 'Hi'


def test_rendered_input_keeps_entity_bindings_and_original_time(transcript_db):
    db, file, owner = transcript_db
    capture_source(db, file, job_id=str(uuid.uuid4()), text='Hello',
                   segments=[{'id': '1', 'speaker': 'A', 'start': 12.4, 'end': 16.1, 'text': 'Hello'}])
    first = read_transcript(db, file)
    saved = save_draft(db, file, first['revision_id'], {'speakers': {'A': 'John'},
        'speaker_entity_ids': {'A': 'person-john'}, 'text_overrides': {'1': 'Corrected words'}}, owner.id)
    revision = db.get(TranscriptRevision, uuid.UUID(saved['revision_id']))
    rendered = render_revision(db.get(TranscriptSource, revision.source_id), revision)
    assert '[12.400–16.100] John\nCorrected words' in rendered['text']
    span = rendered['metadata']['transcript_turns'][0]
    assert rendered['text'][span['speech_start_char']:span['end_char']] == 'Corrected words'
    assert span['entity_id'] == 'person-john'
    assert span['start_seconds'] == 12.4


def test_lost_save_response_is_idempotent_but_different_edit_conflicts(transcript_db):
    db, file, owner = transcript_db
    capture_source(db, file, job_id=str(uuid.uuid4()), text='Original', segments=[])
    first = read_transcript(db, file)
    changes = {'body_text': 'Corrected'}
    saved = save_draft(db, file, first['revision_id'], changes, owner.id)
    db.commit()
    retry = save_draft(db, file, first['revision_id'], changes, owner.id)
    assert retry['revision_id'] == saved['revision_id']
    assert len(list(db.query(TranscriptRevision))) == 2
    with pytest.raises(HTTPException) as conflict:
        save_draft(db, file, first['revision_id'], {'body_text': 'Different correction'}, owner.id)
    assert conflict.value.status_code == 409


def test_invalid_merge_and_unknown_turn_preserve_saved_revision(transcript_db):
    db, file, owner = transcript_db
    capture_source(db, file, job_id=str(uuid.uuid4()), text='Hello Yes', segments=[
        {'id': '1', 'speaker': 'A', 'text': 'Hello'}, {'id': '2', 'speaker': 'B', 'text': 'Yes'}])
    first = read_transcript(db, file)
    for changes in ({'speaker_merges': {'A': 'B', 'B': 'A'}}, {'text_overrides': {'missing': 'Words'}},
        {'speaker_entity_ids': {'A': 'person-1', 'B': 'person-2'}, 'speaker_merges': {'A': 'B'}}):
        with pytest.raises(HTTPException) as invalid:
            save_draft(db, file, first['revision_id'], changes, owner.id)
        assert invalid.value.status_code == 422
        assert read_transcript(db, file)['revision_id'] == first['revision_id']


def test_review_receipt_retry_does_not_approve_newer_revision(transcript_db):
    db, file, owner = transcript_db
    capture_source(db, file, job_id=str(uuid.uuid4()), text='Original', segments=[])
    first = read_transcript(db, file)
    approve_revision(db, file, first['revision_id'], owner.id, 'same-review')
    approve_revision(db, file, first['revision_id'], owner.id, 'same-review')
    updated = save_draft(db, file, first['revision_id'], {'body_text': 'New draft'}, owner.id)
    with pytest.raises(HTTPException):
        approve_revision(db, file, first['revision_id'], owner.id, 'same-review')
    assert read_transcript(db, file)['revision_id'] == updated['revision_id']
    assert not read_transcript(db, file)['reviewed']


def test_legacy_processed_transcript_is_not_falsely_pending_and_later_edits_are_visible(transcript_db):
    db, file, owner = transcript_db
    file.status = 'processed'; file.transcription = 'Legacy words'; db.commit()
    initial = read_transcript(db, file)
    assert initial['review_state'] == 'processed'
    assert not initial['reviewed'] and initial['published_revision_id'] is None
    assert not initial['changed_since_processing']
    edited = save_draft(db, file, initial['revision_id'], {'body_text': 'Corrected legacy words'}, owner.id)
    assert edited['changed_since_processing']
    assert edited['review_state'] == 'awaiting_review'


def test_preparation_completion_does_not_mark_graph_processed(transcript_db):
    from services.evidence_job_sync import _sync_db_record_from_job
    db, file, _ = transcript_db
    job = {'id': str(uuid.uuid4()), 'job_type': 'audio_review', 'status': 'completed',
           'transcription': 'Hello', 'transcription_segments': [], 'pipeline_state': {}}
    _sync_db_record_from_job(file, job, db=db)
    assert file.status == 'unprocessed'
    assert file.processed_at is None
    assert read_transcript(db, file)['review_state'] == 'awaiting_review'


def test_completion_persists_revision_when_file_status_is_already_processed(transcript_db):
    from datetime import datetime, timezone
    from services.evidence_job_sync import reconcile_jobs_payload
    db, file, _ = transcript_db
    capture_source(db, file, job_id=str(uuid.uuid4()), text='Hello', segments=[])
    revision_id = read_transcript(db, file)['revision_id']
    file.status = 'processed'
    file.processed_at = datetime.now(timezone.utc)
    file.engine_job_id = str(uuid.uuid4())
    db.commit()
    file_id = file.id
    job = {'id': file.engine_job_id, 'status': 'completed',
           'pipeline_state': {'transcript_revision_id': revision_id}}
    assert reconcile_jobs_payload(db, [job]) == 1
    db.commit()
    db.expire_all()
    from postgres.models.evidence import EvidenceFile
    assert read_transcript(db, db.get(EvidenceFile, file_id))['published_revision_id'] == revision_id


@pytest.fixture()
def transcript_client(transcript_db):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routers.transcripts import router
    from postgres.session import get_db
    from routers.users import get_current_db_user
    db, file, owner = transcript_db
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_db_user] = lambda: owner
    with TestClient(app) as client:
        yield client, db, file, owner


def test_http_save_review_and_stale_processing_preview(transcript_client):
    client, db, file, owner = transcript_client
    capture_source(db, file, job_id=str(uuid.uuid4()), text='Original', segments=[])
    db.commit()
    initial = client.get(f'/api/evidence/{file.id}/transcript').json()
    saved = client.patch(f'/api/evidence/{file.id}/transcript', json={
        'expected_revision_id': initial['revision_id'], 'body_text': 'Corrected transcript'})
    assert saved.status_code == 200
    reviewed = client.post(f'/api/evidence/{file.id}/transcript/reviews', json={
        'revision_id': saved.json()['revision_id'], 'request_key': 'review-current'})
    assert reviewed.status_code == 201
    plan = client.post('/api/evidence/processing-plans', json={
        'case_id': str(file.case_id), 'file_ids': [str(file.id)]}).json()
    assert plan['unreviewed_audio_count'] == 0
    updated = client.patch(f'/api/evidence/{file.id}/transcript', json={
        'expected_revision_id': saved.json()['revision_id'], 'body_text': 'A newer draft'})
    assert updated.status_code == 200
    result = client.post(f"/api/evidence/processing-plans/{plan['id']}/executions", json={'request_key': 'process-1'})
    assert result.status_code == 409
    assert result.json()['detail']['code'] == 'selection_changed'
    assert file.transcription == 'Original'


def test_mixed_batch_processes_documents_and_only_transcribes_audio(transcript_db, tmp_path, monkeypatch):
    import asyncio
    import threading
    from sqlalchemy import event
    from services import evidence_processing_service as processing
    db, audio, owner = transcript_db
    recording = tmp_path / 'synthetic.wav'; recording.write_bytes(b'RIFF' + b'\0' * 100)
    audio.stored_path = str(recording)
    document = EvidenceFile(case_id=audio.case_id, original_filename='synthetic.txt',
        stored_path=str(tmp_path / 'synthetic.txt'), sha256='b' * 64, size=20)
    (tmp_path / 'synthetic.txt').write_text('Synthetic witness note')
    db.add(document); db.commit()
    calls = []
    async def engine_jobs(_): return []
    async def upload(**kwargs):
        calls.append(kwargs)
        return [{'id': str(uuid.uuid4())} for _ in kwargs['files']]
    class Subscriber:
        async def track_jobs(self, *_): pass
    monkeypatch.setattr(processing.evidence_engine_client, 'list_jobs', engine_jobs)
    monkeypatch.setattr(processing.evidence_engine_client, 'upload_file_paths_batch', upload)
    monkeypatch.setattr(processing, 'build_processing_snapshot', lambda *_args, **_kwargs: {})
    monkeypatch.setattr(processing, 'get_subscriber', Subscriber)
    parameters = dict(case_id=audio.case_id, file_ids=[audio.id, document.id],
        audio_mode='review_first', requested_by_user_id=owner.id)
    loop_sql = []
    def record_loop_sql(_connection, _cursor, statement, *_args):
        if threading.current_thread() is threading.main_thread():
            loop_sql.append(statement)
    event.listen(db.bind, 'before_cursor_execute', record_loop_sql)
    try:
        result = asyncio.run(processing.process_db_files(db, **parameters))
    finally:
        event.remove(db.bind, 'before_cursor_execute', record_loop_sql)
    assert loop_sql == []
    assert result['transcription_count'] == 1
    assert result['processing_count'] == 1
    assert len(result['job_ids']) == 2
    by_name = {call['files'][0][0]: call['processing_metadata'][0] for call in calls}
    assert by_name['synthetic.txt']['preparation_mode'] == 'full'
    assert by_name['call.wav']['preparation_mode'] == 'audio_review'
    assert audio.status == document.status == 'processing'


def test_viewer_cannot_edit_review_execute_or_read_another_case(transcript_client):
    from postgres.permissions import VIEWER_PERMISSIONS
    client, db, file, owner = transcript_client
    capture_source(db, file, job_id=str(uuid.uuid4()), text='Original', segments=[])
    membership = db.query(CaseMembership).filter_by(case_id=file.case_id, user_id=owner.id).one()
    membership.permissions = VIEWER_PERMISSIONS; db.commit()
    current = client.get(f'/api/evidence/{file.id}/transcript')
    assert current.status_code == 200
    revision = current.json()['revision_id']
    assert client.patch(f'/api/evidence/{file.id}/transcript', json={'expected_revision_id': revision, 'body_text': 'Change'}).status_code == 403
    assert client.post(f'/api/evidence/{file.id}/transcript/reviews', json={'revision_id': revision, 'request_key': 'review'}).status_code == 403
    plan = client.post('/api/evidence/processing-plans', json={'case_id': str(file.case_id), 'file_ids': [str(file.id)]}).json()
    assert client.post(f"/api/evidence/processing-plans/{plan['id']}/executions", json={'request_key': 'send', 'audio_mode': 'direct'}).status_code == 403
    other = Case(title='Other case', created_by_user_id=owner.id, owner_user_id=owner.id)
    db.add(other); db.flush()
    other_file = EvidenceFile(case_id=other.id, original_filename='other.wav', stored_path='/synthetic/other.wav', sha256='b'*64, size=1)
    db.add(other_file); db.commit()
    assert client.get(f'/api/evidence/{other_file.id}/transcript').status_code == 403
    assert client.get(f'/api/evidence/{other_file.id}/transcript/revisions/{revision}').status_code == 403


def test_ready_queue_is_paginated_and_does_not_include_published_or_nested_audio(transcript_client):
    client, db, first, owner = transcript_client
    folder = EvidenceFolder(case_id=first.case_id, name='Subfolder')
    db.add(folder); db.flush()
    for index in range(103):
        file = EvidenceFile(case_id=first.case_id, original_filename=f'call-{index:03}.wav', stored_path='/synthetic/call.wav', sha256='a'*64, size=1,
            folder_id=folder.id if index == 102 else None)
        db.add(file); db.flush()
        state = capture_source(db, file, job_id=str(uuid.uuid4()), text='Synthetic words', segments=[])
        approve_revision(db, file, state.working_revision_id, owner.id, f'review-{index}')
        if index == 101:
            state.published_revision_id = state.working_revision_id; file.status = 'processed'
    db.commit()
    page1 = client.get('/api/evidence/transcript-queue/list', params={'case_id': str(first.case_id), 'state': 'ready'}).json()
    assert page1['counts']['ready'] == 101
    assert len(page1['items']) == 100 and page1['next_cursor'] == 100
    page2 = client.get('/api/evidence/transcript-queue/list', params={'case_id': str(first.case_id), 'state': 'ready', 'cursor': 100}).json()
    assert len(page2['items']) == 1 and page2['next_cursor'] is None
    recursive = client.get('/api/evidence/transcript-queue/list', params={'case_id': str(first.case_id), 'state': 'ready', 'recursive': True}).json()
    assert recursive['counts']['ready'] == 102


def test_processing_receipt_retries_are_idempotent_and_job_revision_is_frozen(transcript_client, monkeypatch):
    from services import evidence_processing_service as processing
    from routers import transcripts
    client, db, file, owner = transcript_client
    state = capture_source(db, file, job_id=str(uuid.uuid4()), text='Original', segments=[])
    approve_revision(db, file, state.working_revision_id, owner.id, 'review'); db.commit()
    frozen = str(state.working_revision_id)
    async def capability(_): return {'enabled': True}
    monkeypatch.setattr(transcripts, 'audio_capabilities', capability)
    # Admission enforcement has its own real-route regressions. This test
    # isolates the processing receipt and immutable revision handoff.
    monkeypatch.setattr('services.financial.admission_gate.gate_document_processing', lambda *_, **__: None)
    monkeypatch.setattr('services.folder_context_service.build_processing_snapshot', lambda *_, **__: {})
    calls = []
    async def process(_db, **kwargs):
        calls.append(kwargs)
        newer = save_draft(db, file, frozen, {'body_text': 'A later draft'}, owner.id)
        assert newer['revision_id'] != frozen
        assert kwargs['transcript_revisions'][str(file.id)] == frozen
        return {'job_ids': ['synthetic-job'], 'file_count': 1}
    monkeypatch.setattr(processing, 'process_db_files', process)
    plan = client.post('/api/evidence/processing-plans', json={'case_id': str(file.case_id), 'file_ids': [str(file.id)]}).json()
    route = f"/api/evidence/processing-plans/{plan['id']}/executions"
    first = client.post(route, json={'request_key': 'same-request'})
    assert first.status_code == 202, first.text
    retry = client.post(route, json={'request_key': 'same-request'})
    assert retry.json() == first.json()
    assert len(calls) == 1
    assert 'folder_snapshots' not in retry.json()
    assert client.post(route, json={'request_key': 'different'}).status_code == 409
