"""Authorized, paginated recall of this conversation and its full saved tool results."""
from __future__ import annotations

import copy
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy import select

from postgres.models.agent import AgentMessage
from postgres.models.user import User
from services.agent import storage


class HistoryArgs(BaseModel):
    offset: int = Field(0, ge=0)
    limit: int = Field(20, ge=1, le=50)


class PriorResultArgs(BaseModel):
    run_id: str = Field(..., description="The run_id returned by read_conversation_history.")
    result_id: str = Field(..., description="The saved result ID listed on that run in the history.")


def _scope(db, context):
    if context.significant_scope:
        raise PermissionError("Conversation recall is unavailable in Significant-only mode; it may contain other material.")
    user = db.get(User, UUID(str(context.user_id))) if context.user_id else None
    if user is None or not user.is_active:
        raise PermissionError("An active conversation owner is required.")
    thread_id = (context.proposer or {}).get('thread_id')
    if not thread_id:
        raise ValueError("This run has no saved conversation to read.")
    thread = storage.get_thread_for_user(db, thread_id=UUID(str(thread_id)), user=user,
                                         case_id=UUID(str(context.case_id)))
    return user, thread


def _readable_run(db, context, run, user):
    if run is None:
        return True
    if (run.extra_metadata or {}).get('all_cases') and not context.all_cases:
        return False
    try:
        storage.check_run_source_access(db, run, user)
    except PermissionError:
        return False
    return True


def _record_sources(context, run):
    if run is None:
        return
    meta = run.extra_metadata or {}
    for item in meta.get('cases_read') or []:
        if isinstance(item, dict) and item.get('case_id'):
            context.cases_read[str(item['case_id'])] = item.get('title')
    context.cases_read.update((meta.get('execution_checkpoint') or {}).get('cases_read') or {})


def restore_run_results(context, run):
    """After authorization, restore exact identities and transitive calculation inputs."""
    from services.agent.claim_validation import fingerprint
    results = ((run.extra_metadata or {}).get('execution_checkpoint') or {}).get('result_store') or {}
    current = getattr(context, 'result_store', None)
    if current is None:
        context.result_store = current = {}
    for key, value in results.items():
        if key in current and fingerprint(current[key]) != fingerprint(value):
            raise ValueError('A saved result identity conflicts with current work; its contents were not replaced.')
    current.update(copy.deepcopy(results))
    from services.agent.model_payloads import model_view
    if getattr(context, 'model_views', None) is None:
        context.model_views = {}
    for key, value in results.items():
        context.model_views.setdefault(key, model_view(value))
    _record_sources(context, run)


def restore_artifact_results(context, artifact):
    """Load an older artifact's evidence on demand, scoped to this authorized conversation."""
    needed = set()
    def walk(value):
        if isinstance(value, list):
            for child in value:
                walk(child)
        elif isinstance(value, dict):
            if value.get('result_id'):
                needed.add(str(value['result_id']))
            needed.update(str(item) for item in value.get('source_result_ids', []) if item)
            for child in value.values():
                if isinstance(child, (list, dict)):
                    walk(child)
    walk(artifact)
    if not needed.difference(context.result_store):
        return
    if not getattr(context, 'user_id', None) or not (getattr(context, 'proposer', None) or {}).get('thread_id'):
        return  # Source validation still reports unavailable references; no unscoped database access.
    from services.agent.tools import _financial_session
    from postgres.models.agent import AgentArtifactRecord
    with (context.ledger_session_factory or _financial_session)() as db:
        user, thread = _scope(db, context)
        record = db.get(AgentArtifactRecord, UUID(artifact['id']))
        if record is None:
            return  # Newly created draft, whose references must already be available in this run.
        if record.thread_id != thread.id:
            raise PermissionError('The artifact belongs to a different conversation.')
        storage.check_artifact_access(db, record, user)
        if record.run is None:
            return
        if not _readable_run(db, context, record.run, user):
            raise PermissionError('Saved artifact sources are unavailable in the current source scope.')
        restore_run_results(context, record.run)


def read_history(db, context, *, offset=0, limit=20):
    user, thread = _scope(db, context)
    messages = db.scalars(select(AgentMessage).where(AgentMessage.thread_id == thread.id)
                         .order_by(AgentMessage.sequence_number)).all()
    allowed = {}
    visible = []
    for message in messages:
        key = str(message.run_id or '')
        if key not in allowed:
            allowed[key] = _readable_run(db, context, message.run, user)
        if allowed[key]:
            visible.append(message)
    items = []
    for message in visible[offset:offset + limit]:
        _record_sources(context, message.run)
        checkpoint = ((message.run.extra_metadata or {}).get('execution_checkpoint') or {}) if message.run else {}
        results = [{'result_id': item.get('result_id'), 'tool': item.get('name'), 'summary': item.get('summary')}
                   for item in checkpoint.get('trace', []) if item.get('result_id')]
        items.append(dict(sequence=message.sequence_number, role=message.role, content=message.content,
                          origin='investigator' if message.role == 'user' else 'model_generated',
                          run_id=str(message.run_id) if message.run_id else None, saved_results=results,
                          created_at=message.created_at.isoformat() if message.created_at else None))
    return dict(items=items, total=len(visible), returned=len(items), offset=offset,
                has_more=offset + len(items) < len(visible),
                next_offset=offset + len(items) if offset + len(items) < len(visible) else None,
                interpretation='Historical context: later explicit investigator corrections override earlier assumptions. '
                               'Model answers are not independent evidence. Hidden source scopes are omitted.')


def read_prior_result(db, context, *, run_id, result_id):
    user, thread = _scope(db, context)
    run = storage.get_run_for_user(db, run_id=UUID(str(run_id)), user=user)
    if run.thread_id != thread.id or not _readable_run(db, context, run, user):
        raise PermissionError("That saved result is unavailable in this conversation's current source scope.")
    checkpoint = (run.extra_metadata or {}).get('execution_checkpoint') or {}
    results = checkpoint.get('result_store') or {}
    if result_id not in results:
        raise ValueError("This result is not stored on that run. Older runs may only retain their displayed summary.")
    trace = next((item for item in checkpoint.get('trace', []) if item.get('result_id') == result_id), {})
    restore_run_results(context, run)
    return dict(run_id=str(run.id), result_id=result_id, tool=trace.get('name'), data=results[result_id],
                origin='saved_tool_result', recorded_at=run.started_at.isoformat() if run.started_at else None,
                interpretation='A saved result from the earlier run, not a fresh reading. Model-derived interpretations '
                               'remain model-origin material. Re-read the source if its current state matters.')


def make_conversation_read_tools(context):
    from langchain_core.tools import StructuredTool
    from services.agent.tools import _financial_session

    def history(offset=0, limit=20):
        with (context.ledger_session_factory or _financial_session)() as db:
            data = read_history(db, context, offset=offset, limit=limit)
        return context.result('read_conversation_history', data,
                              summary=f"Read {data['returned']} of {data['total']} authorized conversation messages.")

    def prior(run_id, result_id):
        with (context.ledger_session_factory or _financial_session)() as db:
            data = read_prior_result(db, context, run_id=run_id, result_id=result_id)
        return context.result('read_prior_result', data, summary='Retrieved the complete saved result from the earlier run.')

    return [StructuredTool.from_function(history, name='read_conversation_history', args_schema=HistoryArgs,
                description='Read any earlier turn in this conversation, in sequence, with stable IDs for full saved '
                            'tool results. Page beyond recent messages to recover older methods or decisions.'),
            StructuredTool.from_function(prior, name='read_prior_result', args_schema=PriorResultArgs,
                description='Retrieve the full stored data for a result listed by read_conversation_history. '
                            'Use read_tool_result_page if the returned result needs more pages.')]
