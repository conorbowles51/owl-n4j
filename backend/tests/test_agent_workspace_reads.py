from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import text

from tests.test_agent_durable_postgres import pg
from postgres.models.agent import AgentArtifactRecord
from postgres.models.case_membership import CaseMembership
from postgres.models.work import CaseTask
from services.agent.workspace_read_tools import make_workspace_read_tools


def toolset(factory, ids):
    context = SimpleNamespace(case_id=str(ids['case']), user_id=str(ids['user']), significant_scope=False,
        all_cases=False, ledger_session_factory=factory,
        result=lambda name, data, **kw: {'data': data, **kw})
    return {tool.name: tool for tool in make_workspace_read_tools(context)}, context


def test_complete_task_traversal_via_domain_service(pg):
    factory, ids = pg
    with factory() as db:
        db.execute(text('CREATE TABLE case_tasks (LIKE public.case_tasks INCLUDING ALL)'))
        db.execute(text('CREATE TABLE case_task_links (LIKE public.case_task_links INCLUDING ALL)'))
        db.add_all([CaseTask(case_id=ids['case'], title=f'Synthetic task {i}') for i in range(110)])
        db.commit()
    tools, _ = toolset(factory, ids)
    first = tools['get_case_work'].invoke({'limit': 100})['data']
    last = tools['get_case_work'].invoke({'offset': first['next_offset'], 'limit': 100})['data']
    assert first['total'] == 110 and first['returned'] == 100
    assert last['returned'] == 10 and last['next_offset'] is None
    assert len({row['id'] for row in first['items'] + last['items']}) == 110


def test_saved_work_full_content_rechecks_source_permissions(pg):
    factory, ids = pg
    artifact_id = uuid4()
    with factory() as db:
        db.add(AgentArtifactRecord(id=artifact_id, thread_id=ids['thread'], run_id=ids['run'], type='report',
            title='Synthetic earlier report', payload={'sections': [{'content': 'Complete final source sentence.'}]},
            extra_metadata={'source_case_ids': [str(ids['other'])]}))
        db.commit()
    tools, _ = toolset(factory, ids)
    result = tools['read_saved_agent_work'].invoke({'artifact_id': str(artifact_id)})['data']
    assert result['items'][0]['data']['sections'][0]['content'].endswith('source sentence.')
    with factory() as db:
        membership = db.get(CaseMembership, (ids['other'], ids['user']))
        membership.permissions = {'case': {'view': False}}
        db.commit()
    with pytest.raises(ValueError, match='not available'):
        tools['read_saved_agent_work'].invoke({'artifact_id': str(artifact_id)})


def test_significant_mode_does_not_broaden_to_saved_case_work(pg):
    tools, context = toolset(*pg)
    context.significant_scope = True
    with pytest.raises(PermissionError, match='All data'):
        tools['get_case_work'].invoke({})


def test_reopening_report_refreshes_dependency_notice_without_changing_saved_revision(pg):
    from services.agent import storage
    from postgres.models.user import User
    from copy import deepcopy
    factory, ids = pg
    original, newer, report = uuid4(), uuid4(), uuid4()
    saved_data = {'sections': [{'id': 'section', 'heading': 'Evidence', 'content': 'Pinned exhibit.',
        'embeds': [{'artifact_id': str(original), 'type': 'table', 'title': 'Source exhibit',
                    'data': {'columns': ['count'], 'rows': [{'count': 1}]}}]}]}
    with factory() as db:
        for aid, revision, count in [(original, 1, 1), (newer, 2, 2)]:
            db.add(AgentArtifactRecord(id=aid, thread_id=ids['thread'], run_id=ids['run'], type='table',
                title='Source exhibit', payload={'columns': ['count'], 'rows': [{'count': count}]},
                extra_metadata={'deliverable_id': str(original), 'revision': revision}))
        record = AgentArtifactRecord(id=report, thread_id=ids['thread'], run_id=ids['run'], type='report',
            title='Saved report', payload=deepcopy(saved_data), extra_metadata={'revision': 1})
        db.add(record)
        db.commit()
        view = storage.artifact_views(db, [record], db.get(User, ids['user']))[0]
        assert view.metadata['dependency_review']['status'] == 'review_needed'
        assert view.metadata['dependency_review']['items'][0]['latest_artifact_id'] == str(newer)
        assert view.data == saved_data
        db.expire_all()
        assert db.get(AgentArtifactRecord, report).extra_metadata == {'revision': 1}
        assert db.get(AgentArtifactRecord, report).payload == saved_data
