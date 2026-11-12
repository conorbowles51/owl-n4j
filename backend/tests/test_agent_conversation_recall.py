"""Conversation recall uses stored data and current source permissions, never a summary substitute."""
from types import SimpleNamespace

import pytest

from tests.test_agent_durable_postgres import pg
from postgres.models.agent import AgentMessage, AgentRun
from postgres.models.case_membership import CaseMembership
from services.agent.conversation_read_tools import read_history, read_prior_result


def context(ids, all_cases=False):
    return SimpleNamespace(user_id=str(ids['user']), case_id=str(ids['case']), significant_scope=False,
        all_cases=all_cases, proposer={'thread_id': str(ids['thread'])}, cases_read={}, result_store={})


def test_more_than_eighty_messages_and_changed_assumption_are_fully_retrievable(pg):
    factory, ids = pg
    with factory() as db:
        for sequence in range(2, 83):
            content = 'Use 2 percent' if sequence == 2 else 'Use 8 percent instead of 2 percent' if sequence == 82 else f'Synthetic turn {sequence}'
            db.add(AgentMessage(thread_id=ids['thread'], run_id=ids['run'], sequence_number=sequence,
                               role='user' if sequence % 2 == 0 else 'assistant', content=content))
        run = db.get(AgentRun, ids['run'])
        run.extra_metadata = {**run.extra_metadata, 'execution_checkpoint': {
            'result_store': {'res_old': {'rows': list(range(12000))}},
            'trace': [{'result_id': 'res_old', 'name': 'calculate_artifact_data', 'summary': 'Earlier calculation'}]}}
        db.commit()
    with factory() as reader:
        ctx, offset, messages = context(ids), 0, []
        while True:
            page = read_history(reader, ctx, offset=offset, limit=20)
            messages.extend(page['items'])
            if page['next_offset'] is None:
                break
            offset = page['next_offset']
        assert len(messages) == 82
        assert messages[1]['content'] == 'Use 2 percent'
        assert messages[-1]['content'] == 'Use 8 percent instead of 2 percent'
        assert messages[2]['origin'] == 'model_generated'
        assert 'later explicit investigator corrections' in page['interpretation']
        result = read_prior_result(reader, ctx, run_id=ids['run'], result_id='res_old')
        assert len(result['data']['rows']) == 12000
        assert result['origin'] == 'saved_tool_result'
        assert len(ctx.result_store['res_old']['rows']) == 12000


def test_recall_filters_scope_and_revocation_and_carries_source_requirements(pg):
    factory, ids = pg
    with factory() as db:
        run = db.get(AgentRun, ids['run'])
        run.extra_metadata = {**run.extra_metadata, 'all_cases': True, 'cases_read': [{'case_id': str(ids['other'])}],
                              'execution_checkpoint': {'result_store': {'res_secret': {'value': 'other case'}}}}
        db.commit()
    with factory() as reader:
        assert read_history(reader, context(ids))['total'] == 0
        with pytest.raises(PermissionError):
            read_prior_result(reader, context(ids), run_id=ids['run'], result_id='res_secret')
        ctx = context(ids, True)
        assert read_history(reader, ctx)['total'] == 1
        assert str(ids['other']) in ctx.cases_read
    with factory() as revoke:
        revoke.get(CaseMembership, (ids['other'], ids['user'])).permissions = {'case': {'view': False}}
        revoke.commit()
    with factory() as reader:
        assert read_history(reader, context(ids, True))['total'] == 0
        with pytest.raises(PermissionError):
            read_prior_result(reader, context(ids, True), run_id=ids['run'], result_id='res_secret')


def test_later_turn_report_revision_restores_original_calculation_and_all_its_inputs(pg):
    from uuid import UUID
    from services.agent.tools import AgentToolContext
    from services.agent.calculation_workspace import calculate
    from services.agent.deliverables import new_artifact
    from services.agent.claim_validation import apply_claim_validation
    from services.agent.deliverable_tools import make_deliverable_tools
    from postgres.models.agent import AgentArtifactRecord
    from tests.test_agent_claim_validation import numeric_data
    factory, ids = pg
    rows = [{'amount': '0.10'} for _ in range(1500)]
    calculation = calculate("sum([decimal(r['amount']) for r in rows])", {'rows': rows})
    calculation.update(input_refs={'rows': {'result_id': 'evidence', 'path': 'rows'}}, assumptions={})
    sources = {'evidence': {'rows': rows}, 'calculation': calculation}
    previous = new_artifact('report', 'Earlier report', numeric_data(), requirements=['Totals'])
    apply_claim_validation(previous, sources, {})
    assert not previous['metadata']['validation']['issues']
    with factory() as db:
        run = db.get(AgentRun, ids['run'])
        run.extra_metadata = {**run.extra_metadata, 'execution_checkpoint': {'result_store': sources}}
        db.add(AgentArtifactRecord(id=UUID(previous['id']), thread_id=ids['thread'], run_id=ids['run'],
            type='report', title=previous['title'], payload=previous['data'], extra_metadata=previous['metadata']))
        db.commit()
    fresh = AgentToolContext(case_id=str(ids['case']), user_id=str(ids['user']),
        proposer={'thread_id': str(ids['thread'])}, ledger_session_factory=factory,
        artifact_store={previous['id']: previous})
    assert not fresh.result_store
    tool = next(t for t in make_deliverable_tools(fresh) if t.name == 'edit_report_sections')
    result = tool.invoke({'artifact_id': previous['id'], 'expected_revision': 1,
        'operations': [{'action': 'append', 'section': {'id': 'followup', 'heading': 'Follow-up', 'content': 'Retain the original calculation.'}}]})
    assert result['artifact']['metadata']['validation']['issues'] == []
    assert len(fresh.result_store['evidence']['rows']) == 1500
    assert fresh.result_store['calculation'] == calculation
