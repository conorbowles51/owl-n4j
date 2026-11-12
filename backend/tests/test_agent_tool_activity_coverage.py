"""A successful tool read must never fail while constructing its progress/trace record."""
from services.agent.tools import AgentToolContext, make_agent_tools
from services.agent.graph import activity_for_tool_call
from services.agent.live_runs import progress_for_tool
from services.agent.capabilities import DATA_TYPES, SUPPORT_TOOLS, capabilities


def test_every_bound_tool_can_build_activity_and_progress():
    tools = make_agent_tools(AgentToolContext(case_id='00000000-0000-0000-0000-000000000001'))
    declared = set(SUPPORT_TOOLS) | {name for category in DATA_TYPES for name in category['tools']}
    for tool in tools:
        assert tool.name in declared, tool.name
        assert isinstance(activity_for_tool_call(tool.name, {}, 'synthetic-call'), dict), tool.name
        assert isinstance(progress_for_tool(step=1, name=tool.name, args={}, index=1, batch=1), dict), tool.name
    payload = capabilities([t.name for t in tools])
    assert {'finding', 'dossier', 'timeline'} <= {a['id'] for a in payload['actions']}
    assert all('propose_' not in a['label'] for a in payload['actions'])


def test_deliverable_progress_names_the_actual_work():
    for name in ('create_artifact', 'revise_artifact', 'edit_report_sections', 'append_artifact_rows',
                 'calculate_artifact_data', 'inspect_artifact_export', 'list_artifacts', 'read_artifact',
                 'read_conversation_history', 'read_prior_result'):
        activity = activity_for_tool_call(name, {}, 'synthetic-call')
        assert activity['title'] != 'Used agent tool'
        assert activity['detail'] != "I'm gathering case context before answering."
        progress = progress_for_tool(step=1, name=name, args={})
        assert progress['title'] != 'Looking through the case records'
