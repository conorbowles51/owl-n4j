"""Reviewed, reversible dossier work and connected finding destinations."""
from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy import select

from postgres.models.case_profile import CaseProfile
from services.agent.proposals import ProposalError, _uuid, _require_origin, _checked_citations

FIELDS = {'display_name', 'summary', 'importance', 'dossier_type'}


def dossier_in_case(db, case_id, dossier_id, *, lock=False):
    query = select(CaseProfile).where(CaseProfile.id == _uuid(dossier_id), CaseProfile.case_id == _uuid(case_id),
                                      CaseProfile.archived_at.is_(None))
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    row = db.scalar(query)
    if row is None:
        raise ProposalError('Not in this case.', 404)
    return row


def _field_value(row, key):
    return getattr(row, 'profile_type' if key == 'dossier_type' else key)


def _validate_links(db, case_id, links, user=None):
    from services import dossier_service as D
    for link in links:
        kind, target = D._clean_link(link)
        D._validate_target(db, _uuid(case_id), kind, target)
        if kind == 'agent_artifact' and user:
            from services.agent.storage import get_artifact_for_user
            get_artifact_for_user(db, artifact_id=UUID(target), user=user)


def propose_dossier(db, *, case_id, operation, dossier_id=None, fields=None, links=(), why, citations,
                     origin, requested_by_user_id=None):
    from postgres.models.user import User
    from services.agent.workspace_proposals import _store
    origin = _require_origin(origin)
    if operation not in ('create', 'update', 'attach'):
        raise ProposalError('Choose create, update or attach; removal is not a proposed action.')
    values = dict(fields or {})
    if set(values) - FIELDS:
        raise ProposalError('Only the dossier name, summary, importance and type can be changed by this proposal.')
    if any(value is not None and (not isinstance(value, str) or len(value) > (8000 if key == 'summary' else 255))
           for key, value in values.items()):
        raise ProposalError('Keep dossier fields within their text limits: 8,000 characters for the summary and 255 for other fields.')
    if operation == 'create' and not str(values.get('display_name') or '').strip():
        raise ProposalError('Name the dossier to create.')
    if operation == 'update' and not values:
        raise ProposalError('Choose the dossier fields to update.')
    if operation == 'attach' and (not links or values):
        raise ProposalError('An attachment adds links without changing dossier fields.')
    if len(links) > 50:
        raise ProposalError('One dossier proposal supports at most 50 attachments; split the work into batches.')
    dossier = dossier_in_case(db, case_id, dossier_id) if operation != 'create' else None
    if dossier and dossier.canonical_entity_key and 'display_name' in values:
        raise ProposalError('This dossier name is controlled by its graph identity.')
    user = db.get(User, _uuid(requested_by_user_id)) if requested_by_user_id else None
    try:
        _validate_links(db, case_id, links, user)
    except (ValueError, PermissionError) as exc:
        raise ProposalError(str(exc)) from exc
    checked = _checked_citations(db, case_id, citations)
    content = dict(operation=operation, dossier_id=str(dossier.id) if dossier else None,
                   dossier_name=dossier.display_name if dossier else values.get('display_name'), fields=values,
                   before={key: _field_value(dossier, key) for key in values} if dossier else {},
                   links=list(links), why=str(why).strip(), title=f"{operation.title()} dossier: "
                         + str(dossier.display_name if dossier else values.get('display_name')))
    return _store(db, case_id=_uuid(case_id), output_type='dossier_change', content=content, checked=checked,
                  action={'action': 'dossier_change', 'operation': operation}, origin=origin,
                  requested_by_user_id=requested_by_user_id)


def _destination(case_id, dossier):
    return dict(target_type='dossier', target_id=str(dossier.id), label='Open dossier',
                href=f'/cases/{case_id}/dossiers?dossier={dossier.id}')


def apply_dossier(db, item, content, reviewer, provenance):
    from services import dossier_service as D, activity_trail
    # Revalidate cited sources and attachments at acceptance; their availability can change while a draft waits.
    _checked_citations(db, item.case_id, content.get('citations') or [])
    _validate_links(db, item.case_id, content.get('links') or [], reviewer)
    operation = content['operation']
    if operation == 'create':
        saved = D.create_dossier(db, case_id=item.case_id, user=reviewer, data=content['fields'], commit=False)
        dossier = dossier_in_case(db, item.case_id, saved['id'], lock=True)
    else:
        dossier = dossier_in_case(db, item.case_id, content['dossier_id'], lock=True)
        if operation == 'update':
            if any(_field_value(dossier, key) != value for key, value in content.get('before', {}).items()):
                raise ProposalError('The dossier changed after this proposal was prepared. Review a fresh proposal; '
                                    'the investigator edits have been preserved.', 409)
            D.update_dossier(db, dossier_id=dossier.id, user=reviewer, data=content['fields'], commit=False)
    if content.get('links'):
        D.add_links(db, dossier_id=dossier.id, user=reviewer, links=content['links'],
                    origin=f'Accepted agent proposal {item.id}', commit=False)
    activity_trail.record('agent_dossier_proposal_accepted', db=db, user=reviewer, case_id=item.case_id,
                          details={'dossier_id': str(dossier.id), 'proposal_id': str(item.id),
                                   'operation': operation, 'actor_origin': provenance})
    return [_destination(item.case_id, dossier)]


def attach_finding_destinations(db, item, entry, reviewer, provenance):
    from services import dossier_service as D
    content = item.content or {}
    targets = []
    if content.get('dossier_id'):
        dossier = dossier_in_case(db, item.case_id, content['dossier_id'], lock=True)
        D.add_links(db, dossier_id=dossier.id, user=reviewer,
                    links=[{'target_type': 'entry', 'target_id': entry['id'], 'relationship_type': 'context'}],
                    origin=f'Accepted agent proposal {item.id}', commit=False)
        targets.append(_destination(item.case_id, dossier))
    if content.get('event_date'):
        from postgres.models.timeline_entry import TimelineEntry
        from services.timeline_entries import TimelineAddition, preview_addition, save_addition
        request = TimelineAddition(source_kind='workspace_entry', source_ids=[UUID(entry['id'])],
                                    event_date=date.fromisoformat(content['event_date']))
        preview = preview_addition(db, case_id=item.case_id, request=request)
        request.expected_revision = preview['revision']
        saved = save_addition(db, case_id=item.case_id, request=request, actor=reviewer.name, commit=False)
        for key in saved['event_keys']:
            tid = UUID(key.removeprefix('timeline-entry:'))
            event = db.get(TimelineEntry, tid)
            event.event_snapshot = dict(event.event_snapshot or {}, actor_origin=provenance)
            targets.append(dict(target_type='timeline_entry', target_id=str(tid), label='Open dated event',
                                href=f'/cases/{item.case_id}/timeline?event={key}'))
    return targets
