"""Real domain services: a reviewed finding's complete destination workflow and safe dossier revisions."""
import uuid
from datetime import date

import pytest
from sqlalchemy import select

from tests.test_agent_workspace_proposals import db as proposal_db, _origin
from postgres.models.activity_event import ActivityEvent
from postgres.models.case_membership import CaseMembership
from postgres.models.enums import CaseMembershipRole
from postgres.models.case_profile import CaseProfile
from postgres.models.dossier import DossierRole, DossierLink
from postgres.models.timeline_entry import TimelineEntry
from postgres.models.workspace_entry import WorkspaceEntry
from postgres.models.workspace_ai import WorkspaceAIOutput
from services.agent import workspace_proposals as W, proposals as P
from services.agent.dossier_proposals import propose_dossier
from services import dossier_service as D


@pytest.fixture
def db(proposal_db):
    db = proposal_db
    for model in (CaseProfile, CaseMembership, DossierRole, DossierLink, TimelineEntry, ActivityEvent):
        model.__table__.create(db.get_bind(), checkfirst=True)
    owner, case = db.info['owner'], db.info['case']
    db.add(CaseMembership(case_id=case.id, user_id=owner.id, added_by_user_id=owner.id,
        membership_role=CaseMembershipRole.collaborator, permissions={'case': {'view': True, 'edit': True}}))
    dossier = CaseProfile(case_id=case.id, profile_type='person', display_name='Synthetic witness', summary='Investigator wording')
    db.add(dossier); db.commit()
    db.info['dossier'] = dossier
    return db


def finding(db):
    return W.propose_entry(db, case_id=db.info['case'].id, entry_type='finding', title='Cited synthetic finding',
        body='The record states the agreed date.', citations=[f"doc://{db.info['statement'].id}/1"], origin=_origin(),
        dossier_id=db.info['dossier'].id, event_date=date(2026, 1, 15))


def test_accept_finding_attaches_dossier_and_event_exactly_once(db):
    item = finding(db)
    assert not db.scalars(select(WorkspaceEntry)).all()
    P.record_open(db, case_id=db.info['case'].id, proposal_type='workspace_ai', proposal_id=item['id'],
                  citation=f"doc://{db.info['statement'].id}/1", user=db.info['owner'])
    saved = W.accept(db, case_id=db.info['case'].id, output_id=item['id'], reviewer=db.info['owner'], via='ui')
    again = W.accept(db, case_id=db.info['case'].id, output_id=item['id'], reviewer=db.info['owner'], via='ui')
    assert saved['accepted_targets'] == again['accepted_targets']
    assert {t['target_type'] for t in saved['accepted_targets']} == {'workspace_entry', 'dossier', 'timeline_entry'}
    assert len(db.scalars(select(WorkspaceEntry)).all()) == 1
    assert len(db.scalars(select(DossierLink)).all()) == 1
    event = db.scalars(select(TimelineEntry)).one()
    assert event.event_snapshot['date'] == '2026-01-15'
    assert event.event_snapshot['actor_origin']['origin']['model'] == 'DeepSeek V4 Pro'
    assert saved['proposal']['review']['source_opened']


def test_a_destination_failure_rolls_back_all_connected_work_and_can_retry(db, monkeypatch):
    item = finding(db)
    original = D.add_links
    monkeypatch.setattr(D, 'add_links', lambda *args, **kwargs: (_ for _ in ()).throw(ValueError('temporary failure')))
    with pytest.raises(ValueError, match='temporary failure'):
        W.accept(db, case_id=db.info['case'].id, output_id=item['id'], reviewer=db.info['owner'])
    assert not db.scalars(select(WorkspaceEntry)).all()
    assert not db.scalars(select(TimelineEntry)).all()
    assert db.get(WorkspaceAIOutput, uuid.UUID(item['id'])).review_status == 'pending_review'
    monkeypatch.setattr(D, 'add_links', original)
    assert W.accept(db, case_id=db.info['case'].id, output_id=item['id'], reviewer=db.info['owner'])['review_status'] == 'accepted'


def dossier_proposal(db, **kw):
    return propose_dossier(db, case_id=db.info['case'].id, why='Requested casework',
        citations=[f"doc://{db.info['statement'].id}/1"], origin=_origin(),
        requested_by_user_id=db.info['owner'].id, **kw)


def test_create_dossier_and_attach_evidence_through_domain_service(db):
    item = dossier_proposal(db, operation='create', fields={'display_name': 'New synthetic subject', 'summary': 'Cited summary'},
                            links=[{'target_type': 'evidence', 'target_id': str(db.info['statement'].id)}])
    result = W.accept(db, case_id=db.info['case'].id, output_id=item['id'], reviewer=db.info['owner'])
    dossier = db.get(CaseProfile, uuid.UUID(result['accepted_targets'][0]['target_id']))
    assert dossier.summary == 'Cited summary'
    assert db.scalars(select(DossierLink).where(DossierLink.dossier_id == dossier.id)).one().target_id == str(db.info['statement'].id)
    assert W.accept(db, case_id=db.info['case'].id, output_id=item['id'], reviewer=db.info['owner'])['accepted_targets'] == result['accepted_targets']


def test_pending_dossier_update_never_overwrites_a_later_investigator_edit(db):
    item = dossier_proposal(db, operation='update', dossier_id=db.info['dossier'].id, fields={'summary': 'Drafted summary'})
    db.info['dossier'].summary = 'New investigator decision'; db.commit()
    with pytest.raises(P.ProposalError, match='investigator edits have been preserved'):
        W.accept(db, case_id=db.info['case'].id, output_id=item['id'], reviewer=db.info['owner'])
    assert db.info['dossier'].summary == 'New investigator decision'
    assert db.get(WorkspaceAIOutput, uuid.UUID(item['id'])).review_status == 'pending_review'


def test_dossier_targets_and_citations_cannot_cross_case_and_model_retry_is_one_proposal(db):
    with pytest.raises(P.ProposalError):
        dossier_proposal(db, operation='attach', dossier_id=db.info['dossier'].id,
            links=[{'target_type': 'evidence', 'target_id': str(db.info['foreign'].id)}])
    origin = _origin()
    kwargs = dict(case_id=db.info['case'].id, entry_type='finding', title='One finding', body='Synthetic',
                  citations=[f"doc://{db.info['statement'].id}/1"], origin=origin)
    first, second = W.propose_entry(db, **kwargs), W.propose_entry(db, **kwargs)
    assert first['id'] == second['id']


def test_timeline_keeps_legacy_financial_notes_and_general_findings_eligible(db):
    from services.workspace_entry_service import create_entry
    from services.timeline_entries import TimelineAddition, preview_addition
    for kind, tags, expected in [('finding', [], True), ('note', ['financial', 'financial-observation'], True),
                                 ('note', [], False), ('finding', ['financial', 'financial-report'], False)]:
        entry = create_entry(db, case_id=db.info['case'].id, current_user=db.info['owner'],
                             entry_type=kind, title='Synthetic source', body='Synthetic text', tags=tags)
        request = TimelineAddition(source_kind='workspace_entry', source_ids=[entry['id']], event_date=date(2026, 1, 15))
        if expected:
            assert preview_addition(db, case_id=db.info['case'].id, request=request)['ready'] == 1
        else:
            with pytest.raises(ValueError, match='no longer available'):
                preview_addition(db, case_id=db.info['case'].id, request=request)
