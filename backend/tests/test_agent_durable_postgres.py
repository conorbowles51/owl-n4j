"""Optional real-PostgreSQL checkpoints, fencing and source ACL tests.

Set TEST_AGENT_DATABASE_URL to a disposable local migrated database. Each test uses
its own schema; public data is never written. No provider calls occur.
"""
import os
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from postgres.models.agent import AgentArtifactRecord, AgentMessage, AgentRun, AgentThread
from postgres.models.case import Case
from postgres.models.case_membership import CaseMembership
from postgres.models.enums import CaseMembershipRole
from postgres.models.user import User
from services.agent import storage
from services.agent.durable_execution import claim_resume, consume_resume_claim, save_checkpoint, write_metadata
from services.agent.run_settle import _write_progress, RunHeartbeat


@pytest.fixture
def pg():
    url = os.environ.get('TEST_AGENT_DATABASE_URL')
    if not url:
        pytest.skip('Set TEST_AGENT_DATABASE_URL to run isolated PostgreSQL integration tests')
    assert make_url(url).host in ('127.0.0.1', 'localhost', '::1'), 'Only a disposable loopback database is allowed'
    schema = 'agentdurable_' + uuid.uuid4().hex
    admin = create_engine(url)
    tables = ('users', 'cases', 'case_memberships', 'case_mandate_versions', 'agent_threads', 'agent_runs',
              'agent_messages', 'agent_artifacts', 'agent_tool_calls')
    with admin.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        for table in tables:
            conn.execute(text(f'CREATE TABLE "{schema}".{table} (LIKE public.{table} INCLUDING DEFAULTS INCLUDING CONSTRAINTS INCLUDING INDEXES)'))
    engine = create_engine(url, connect_args={'options': f'-csearch_path={schema},public'})
    factory = sessionmaker(engine, expire_on_commit=False)
    try:
        with factory() as db:
            user = User(email=f'{uuid.uuid4()}@example.test', name='Synthetic investigator', password_hash='unused')
            db.add(user); db.flush()
            case = Case(title='Synthetic recovery case', owner_user_id=user.id, created_by_user_id=user.id)
            other = Case(title='Synthetic second case', owner_user_id=user.id, created_by_user_id=user.id)
            db.add_all([case, other]); db.flush()
            for item in (case, other):
                db.add(CaseMembership(case_id=item.id, user_id=user.id, added_by_user_id=user.id,
                    membership_role=CaseMembershipRole.collaborator, permissions={'case': {'view': True, 'edit': True}}))
            thread = AgentThread(case_id=case.id, owner_user_id=user.id, title='Synthetic task')
            db.add(thread); db.flush()
            run = AgentRun(thread_id=thread.id, case_id=case.id, user_id=user.id, provider='openai', model_id='synthetic',
                input_message='Read all requested records', status='interrupted', extra_metadata={
                    'execution_checkpoint': {'version': 1, 'case_id': str(case.id), 'phase': 'agent'},
                    'execution_request': {'message': 'Read all requested records', 'case_id': str(case.id)}})
            db.add(run); db.flush()
            db.add(AgentMessage(thread_id=thread.id, run_id=run.id, sequence_number=1, role='user', content=run.input_message))
            db.commit()
            ids = dict(user=user.id, case=case.id, other=other.id, thread=thread.id, run=run.id)
        yield factory, ids
    finally:
        engine.dispose()
        with admin.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


def test_concurrent_resume_has_exactly_one_claim(pg):
    factory, ids = pg

    def attempt(_):
        with factory() as db:
            try:
                run, token = claim_resume(db, ids['run'], db.get(User, ids['user']))
                return token
            except ValueError:
                db.rollback()
                return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        tokens = list(pool.map(attempt, range(2)))
    assert sum(token is not None for token in tokens) == 1
    token = next(t for t in tokens if t)
    with factory() as db:
        run = db.get(AgentRun, ids['run'])
        consume_resume_claim(db, run, token)
        with pytest.raises(ValueError, match='already resumed'):
            consume_resume_claim(db, run, token)


def test_cancelled_work_resumes_only_when_explicitly_claimed(pg):
    from services.agent.run_settle import settle_orphaned_runs
    factory, ids = pg
    with factory() as db:
        run = db.get(AgentRun, ids['run'])
        run.status = 'cancelled'
        run.extra_metadata = {**run.extra_metadata, 'execution_checkpoint': {
            **run.extra_metadata['execution_checkpoint'], 'phase': 'finalize', 'trace': [{'id': 'old-call'}],
            'clarification': {'context': {'reason': 'no_progress'}}}}
        db.commit()
        assert settle_orphaned_runs(db) == []
        run, token = claim_resume(db, ids['run'], db.get(User, ids['user']))
        assert run.status == 'running' and token
        assert run.extra_metadata['execution_checkpoint']['version'] == 1
        assert run.extra_metadata['execution_checkpoint']['phase'] == 'tools'
        assert run.extra_metadata['execution_checkpoint']['clarification'] is None
        assert run.extra_metadata['execution_checkpoint']['budget_base'] == 1


def test_checkpoint_survives_new_session_and_preserves_heartbeat_progress(pg):
    factory, ids = pg
    with factory() as db:
        run, token = claim_resume(db, ids['run'], db.get(User, ids['user']))
        with factory() as heartbeat:
            _write_progress(heartbeat, run.id, {'step': 7})
            heartbeat.commit()
        payload = {'version': 1, 'case_id': str(ids['case']), 'phase': 'tools', 'artifacts': [],
                   'completed_calls': ['saved-call'], 'result_store': {'result-1': {'text': 'Stored evidence'}}}
        save_checkpoint(db, run, payload, lease=token)
    with factory() as reopened:
        run = reopened.get(AgentRun, ids['run'])
        assert run.extra_metadata['progress']['step'] == 7
        assert run.extra_metadata['execution_checkpoint']['result_store']['result-1']['text'] == 'Stored evidence'
        write_metadata(reopened, run, {'execution_lease': 'replacement-worker'})
        reopened.commit()
    with factory() as old_worker:
        with pytest.raises(RuntimeError, match='Another worker'):
            save_checkpoint(old_worker, old_worker.get(AgentRun, ids['run']), payload, lease=token)


def test_explicit_resume_after_no_progress_preserves_results_and_changes_approach(pg):
    factory, ids = pg
    with factory() as db:
        run = db.get(AgentRun, ids['run'])
        question = {'context': {'reason': 'no_progress'}}
        run.status = 'clarification_required'
        run.extra_metadata = {**run.extra_metadata, 'clarification': question, 'execution_checkpoint': {
            **run.extra_metadata['execution_checkpoint'], 'phase': 'done', 'clarification': question,
            'result_store': {'saved-source': {'text': 'Complete original evidence'}}, 'trace': [{'id': 'old-call'}]}}
        db.commit()
        run, token = claim_resume(db, ids['run'], db.get(User, ids['user']))
        checkpoint = run.extra_metadata['execution_checkpoint']
        assert token and checkpoint['phase'] == 'tools' and checkpoint['clarification'] is None
        assert checkpoint['result_store']['saved-source']['text'] == 'Complete original evidence'
        assert 'Change the failed approach' in checkpoint['resume_note']


def test_revoked_source_access_blocks_artifact_and_run_recovery(pg):
    factory, ids = pg
    with factory() as db:
        run = db.get(AgentRun, ids['run'])
        artifact = AgentArtifactRecord(thread_id=ids['thread'], run_id=run.id, type='report', title='Synthetic report',
            payload={'sections': []}, extra_metadata={'all_cases': True, 'source_case_ids': [str(ids['case']), str(ids['other'])]})
        db.add(artifact)
        write_metadata(db, run, {'all_cases': True, 'cases_read': [{'case_id': str(ids['other'])}]})
        db.commit()
        artifact_id = artifact.id
    with factory() as revoke:
        member = revoke.get(CaseMembership, (ids['other'], ids['user']))
        member.permissions = {'case': {'view': False}}
        revoke.commit()
    with factory() as reader:
        user = reader.get(User, ids['user'])
        with pytest.raises(PermissionError, match='source case'):
            storage.get_artifact_for_user(reader, artifact_id=artifact_id, user=user)
        with pytest.raises(PermissionError, match='source case'):
            claim_resume(reader, ids['run'], user)


def test_database_checkpoint_resumes_batch_after_worker_loss(pg, monkeypatch):
    from langchain_core.messages import HumanMessage
    from tests.test_agent_durable_execution import runner, call
    factory, ids = pg
    seen = []

    class ReadTool:
        name = 'read_test'

        def invoke(self, args):
            seen.append(args['number'])
            return {'summary': 'Synthetic record read', 'data': args, 'result_id': f"result-{args['number']}"}

    monkeypatch.setattr('services.agent.graph.make_agent_tools', lambda context: [ReadTool()])
    monkeypatch.setattr('services.agent.graph.tools_for_binding', lambda model, tools: tools)

    class WorkerLost(BaseException):
        pass

    with factory() as worker:
        run, token = claim_resume(worker, ids['run'], worker.get(User, ids['user']))
        consume_resume_claim(worker, run, token)

        def checkpoint(payload):
            save_checkpoint(worker, run, payload, lease=token)
            if (payload.get('inflight') or {}).get('id') == 'call-2':
                raise WorkerLost()

        with pytest.raises(WorkerLost):
            list(runner([[call(1), call(2)]]).stream(case_id=str(ids['case']),
                messages=[HumanMessage(content='Read both synthetic records')], checkpoint_callback=checkpoint))
    assert seen == [1]
    with factory() as recovery:
        run = recovery.get(AgentRun, ids['run'])
        checkpoint = run.extra_metadata['execution_checkpoint']
        events = list(runner().stream(case_id=str(ids['case']), messages=[], resume_checkpoint=checkpoint,
            checkpoint_callback=lambda payload: save_checkpoint(recovery, run, payload, lease=token)))
        assert events[-1]['result']['clarification'] is None
    assert seen == [1, 2]
    with factory() as reopened:
        saved = reopened.get(AgentRun, ids['run']).extra_metadata['execution_checkpoint']
        assert saved['phase'] == 'done'
        assert saved['completed_calls'] == ['call-1', 'call-2']
        assert set(saved['model_views']) == {'result-1', 'result-2'}


def test_replaced_worker_cannot_refresh_liveness_or_cancel_its_replacement(pg, monkeypatch):
    from contextlib import contextmanager
    from services.agent import cancellation
    factory, ids = pg

    @contextmanager
    def background_session():
        with factory() as db:
            yield db

    monkeypatch.setattr('postgres.session.get_background_session', background_session)
    with factory() as db:
        run, token = claim_resume(db, ids['run'], db.get(User, ids['user']))
        old_beat = run.heartbeat_at
        write_metadata(db, run, {'execution_lease': 'replacement'})
        db.commit()
    heartbeat = RunHeartbeat(ids['run'], lease=token)
    heartbeat.note_progress({'step': 999})
    heartbeat._beat_once()
    heartbeat._check_stopped_elsewhere()
    assert heartbeat.lost_lease
    assert not cancellation.is_cancelled(str(ids['run']))
    with factory() as db:
        run = db.get(AgentRun, ids['run'])
        assert run.heartbeat_at == old_beat
        assert run.extra_metadata.get('progress') is None
