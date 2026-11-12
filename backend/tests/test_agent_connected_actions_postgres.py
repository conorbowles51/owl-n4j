"""Connected action concurrency on a disposable local PostgreSQL schema."""
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import select, text

from tests.test_agent_durable_postgres import pg
from postgres.models.evidence import EvidenceFile
from postgres.models.case_profile import CaseProfile
from postgres.models.dossier import DossierLink
from postgres.models.workspace_entry import WorkspaceEntry
from postgres.models.timeline_entry import TimelineEntry
from postgres.models.user import User
from postgres.models.case_membership import CaseMembership
from services.agent import workspace_proposals as W, proposals as P


@pytest.fixture
def action_pg(pg):
    factory, ids = pg
    with factory() as db:
        assert db.scalar(text('SELECT current_schema()')).startswith('agentdurable_')
        for table in ('case_contexts', 'evidence_files', 'workspace_entries', 'workspace_entry_revisions',
                      'workspace_entry_links', 'workspace_entry_events', 'workspace_legacy_mappings',
                      'workspace_ai_outputs', 'agent_proposal_source_opens', 'case_profiles', 'dossier_roles',
                      'dossier_links', 'timeline_entries', 'activity_events'):
            db.execute(text(f'CREATE TABLE {table} (LIKE public.{table} INCLUDING DEFAULTS INCLUDING CONSTRAINTS INCLUDING INDEXES)'))
        evidence = EvidenceFile(case_id=ids['case'], original_filename='synthetic-source.txt', stored_path='/synthetic/source.txt',
                                size=1, sha256='a' * 64, status='processed', created_by_id=ids['user'])
        dossier = CaseProfile(case_id=ids['case'], profile_type='person', display_name='Synthetic subject')
        db.add_all([evidence, dossier]); db.commit()
        ids = {**ids, 'evidence': evidence.id, 'dossier': dossier.id}
    return factory, ids


def test_simultaneous_accepts_save_one_connected_finding_and_all_destinations(action_pg):
    factory, ids = action_pg
    with factory() as db:
        origin = P.agent_origin(for_name='Synthetic investigator', model='Synthetic model', run_id=ids['run'])
        proposal = W.propose_entry(db, case_id=ids['case'], entry_type='finding', title='Synthetic dated finding',
            body='The source documents the agreed event date.', citations=[f"doc://{ids['evidence']}"], origin=origin,
            dossier_id=ids['dossier'], event_date='2026-01-15', requested_by_user_id=ids['user'])
        P.record_open(db, case_id=ids['case'], proposal_type='workspace_ai', proposal_id=proposal['id'],
                      citation=f"doc://{ids['evidence']}", user=db.get(User, ids['user']))

    def accept(_):
        with factory() as db:
            return W.accept(db, case_id=ids['case'], output_id=proposal['id'], reviewer=db.get(User, ids['user']), via='ui')

    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = pool.map(accept, range(2))
    assert first['accepted_targets'] == second['accepted_targets']
    with factory() as db:
        assert len(db.scalars(select(WorkspaceEntry)).all()) == 1
        assert len(db.scalars(select(DossierLink)).all()) == 1
        assert len(db.scalars(select(TimelineEntry)).all()) == 1


def test_proposal_tool_rechecks_revoked_edit_access(action_pg, monkeypatch):
    from services.agent.proposal_tools import make_proposal_tools
    from services.agent.tools import AgentToolContext
    factory, ids = action_pg
    with factory() as db:
        membership = db.get(CaseMembership, (ids['case'], ids['user']))
        membership.permissions = {'case': {'view': True, 'edit': False}}
        db.commit()
    monkeypatch.setattr('services.agent.proposal_tools._write_session', factory)
    context = AgentToolContext(case_id=str(ids['case']), user_id=str(ids['user']),
        proposer={'can_propose': True, 'for_user_id': str(ids['user']), 'for_name': 'Synthetic investigator',
                  'model': 'Synthetic model', 'run_id': str(ids['run'])})
    tool = next(t for t in make_proposal_tools(context) if t.name == 'propose_workspace_entry')
    output = tool.invoke(dict(entry_type='finding', title='No permission', body='Synthetic', citations=[f"doc://{ids['evidence']}"]))
    assert output['status'] == 'error' and 'edit access' in output['error']
    with factory() as db:
        assert db.scalar(text('SELECT count(*) FROM workspace_ai_outputs')) == 0
