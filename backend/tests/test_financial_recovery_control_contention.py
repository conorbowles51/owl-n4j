"""Pause/Resume refuses only lock contention; it never forces a worker to stop."""
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import OperationalError

from services.financial import deployment_recovery as recovery
from services.financial.pdf_candidates import PdfMappingError


class ControlSession:
    def __init__(self, *, blocked=None, state='running', code='55P03', code_attribute='sqlstate'):
        self.blocked = blocked
        self.run = SimpleNamespace(status=state)
        self.statements = []
        self.commits = self.rollbacks = 0
        original = Exception('private database details must not enter the response')
        setattr(original, code_attribute, code)
        self.error = OperationalError('private SQL', {}, original)

    def execute(self, statement):
        self.statements.append(statement)
        if self.blocked == 'case':
            raise self.error
        return SimpleNamespace(all=lambda: [])

    def scalar(self, statement):
        self.statements.append(statement)
        if self.blocked == 'run':
            raise self.error
        return self.run

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


@pytest.mark.parametrize('action,state,expected', [('pause', 'running', 'paused'), ('resume', 'paused', 'running')])
def test_both_control_locks_use_postgres_nowait_and_normal_actions_still_commit(action, state, expected):
    session = ControlSession(state=state)
    assert recovery.control(session, uuid4(), action) == {'status': expected}
    assert session.commits == 1 and session.rollbacks == 0
    assert len(session.statements) == 2
    for statement in session.statements:
        sql = str(statement.compile(dialect=postgresql.dialect()))
        assert sql.endswith('FOR UPDATE NOWAIT'), sql
        assert 'SKIP LOCKED' not in sql


@pytest.mark.parametrize('blocked', ['case', 'run'])
@pytest.mark.parametrize('action,state', [('pause', 'running'), ('resume', 'paused')])
@pytest.mark.parametrize('code_attribute', ['sqlstate', 'pgcode'])
def test_lock_contention_rolls_back_without_changing_recovery(blocked, action, state, code_attribute):
    session = ControlSession(blocked=blocked, state=state, code_attribute=code_attribute)
    with pytest.raises(PdfMappingError) as failure:
        recovery.control(session, uuid4(), action)
    assert failure.value.status_code == 409
    assert f'This request did not {action} recovery.' in str(failure.value)
    assert f'try {action.title()} recovery again' in str(failure.value)
    assert 'private' not in str(failure.value)
    assert session.run.status == state
    assert session.commits == 0 and session.rollbacks == 1


@pytest.mark.parametrize('code', ['40001', '40P01', '08006', None])
def test_other_database_errors_are_not_misreported_as_a_busy_case(code):
    session = ControlSession(blocked='case', code=code)
    with pytest.raises(OperationalError) as failure:
        recovery.control(session, uuid4(), 'pause')
    assert failure.value is session.error
    assert session.run.status == 'running' and session.commits == 0


def test_completed_recovery_and_missing_run_keep_existing_behavior():
    session = ControlSession(state='complete')
    assert recovery.control(session, uuid4(), 'pause') == {'status': 'complete'}
    assert session.commits == 0
    session.run = None
    with pytest.raises(PdfMappingError) as failure:
        recovery.control(session, uuid4(), 'resume')
    assert failure.value.status_code == 404


@pytest.mark.parametrize('action,blocked,state', [('pause', 'case', 'running'), ('resume', 'run', 'paused')])
def test_real_http_route_returns_actionable_conflict_without_mutation(action, blocked, state):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from postgres.session import get_db
    from routers import financial_statement_import as router
    from routers.users import get_current_db_user
    from tests.test_route_authorization import _CaseAccessDb

    access = _CaseAccessDb(membership=SimpleNamespace(permissions={'case': {'view': True, 'edit': True}}))
    session = ControlSession(blocked=blocked, state=state)
    session.query = access.query
    app = FastAPI()
    app.include_router(router.router)
    app.dependency_overrides[get_db] = lambda: session
    app.dependency_overrides[get_current_db_user] = lambda: SimpleNamespace(id=uuid4(), global_role='user', is_active=True)
    with TestClient(app) as client:
        response = client.post('/api/financial/statement-import/deployment-recovery/' + action,
            params={'case_id': str(access.case.id)})
    assert response.status_code == 409, response.text
    assert f'This request did not {action} recovery.' in response.json()['detail']
    assert 'private' not in response.text
    assert session.run.status == state and session.commits == 0 and session.rollbacks == 1
