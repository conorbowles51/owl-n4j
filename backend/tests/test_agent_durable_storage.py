import uuid
from unittest.mock import patch

import pytest
from sqlalchemy import select

from tests.test_agent_run_settle import db, run_row, ago
from postgres.models.agent import AgentArtifactRecord, AgentMessage
from services.agent import storage, run_settle
from services.agent.durable_execution import save_checkpoint, write_metadata, extend_budget_checkpoint
from services.agent.deliverables import new_artifact, revise_artifact
from services.agent.service import AgentService


def test_stale_checkpoint_is_claimed_once_and_keeps_same_run(db):
    run = run_row(db, beat=ago(200))
    run.extra_metadata = {"execution_checkpoint": {"version": 1}, "execution_request": {"message": "Read"}}
    db.commit()
    claimed = run_settle.settle_orphaned_runs(db)
    assert claimed[0]["recover"] is True
    db.refresh(run)
    assert run.status == "running" and run.extra_metadata["recovery_attempts"] == 1
    assert run_settle.settle_orphaned_runs(db) == []
    assert len(db.scalars(select(AgentMessage)).all()) == 1  # no new user question or interruption spam


def test_old_worker_cannot_replace_new_worker_checkpoint(db):
    run = run_row(db)
    write_metadata(db, run, {"execution_lease": "new-worker", "progress": {"step": 2}})
    db.commit()
    with pytest.raises(RuntimeError, match="Another worker"):
        save_checkpoint(db, run, {"phase": "agent"}, lease="old-worker")
    assert run.extra_metadata["progress"] == {"step": 2}


def test_all_twelve_outputs_persist_and_earliest_remains_available(db):
    AgentArtifactRecord.__table__.create(db.get_bind())
    run = run_row(db)
    artifacts = [new_artifact("report", f"Profile {i}", {"sections": [{"heading": "Profile", "content": "Synthetic"}]})
                 for i in range(12)]
    first = storage.persist_artifacts(db, thread=run.thread, run=run, artifacts=artifacts)
    db.commit()
    again = storage.persist_artifacts(db, thread=run.thread, run=run, artifacts=artifacts)
    assert [a.id for a in first] == [a.id for a in again]
    assert len(db.scalars(select(AgentArtifactRecord)).all()) == 12
    db.expire(run.thread, ['artifacts'])
    visible = AgentService._available_artifacts_for_runner(run.thread)
    assert len(visible) == 12 and visible[0]['id'] == artifacts[0]['id']
    revision = revise_artifact(artifacts[0], {"sections": [{"heading": "Profile", "content": "Expanded"}]}, expected_revision=1)
    storage.persist_artifacts(db, thread=run.thread, run=run, artifacts=[revision])
    db.commit()
    assert db.get(AgentArtifactRecord, uuid.UUID(revision['id'])).extra_metadata['previous_revision_id'] == artifacts[0]['id']


def test_stale_revision_preserves_both_investigator_edit_and_conflict_draft(db):
    AgentArtifactRecord.__table__.create(db.get_bind())
    run = run_row(db)
    initial = new_artifact("report", "Report", {"sections": []})
    storage.persist_artifacts(db, thread=run.thread, run=run, artifacts=[initial])
    newer = revise_artifact(initial, {"sections": [{"heading": "Human", "content": "Keep"}]}, expected_revision=1)
    storage.persist_artifacts(db, thread=run.thread, run=run, artifacts=[newer])
    stale = revise_artifact(initial, {"sections": [{"heading": "Agent", "content": "Draft"}]}, expected_revision=1)
    saved = storage.persist_artifacts(db, thread=run.thread, run=run, artifacts=[stale])[0]
    assert saved.extra_metadata['conflict_draft']
    assert saved.extra_metadata['validation']['status'] == 'needs_revision'
    assert db.get(AgentArtifactRecord, uuid.UUID(newer['id'])).payload['sections'][0]['content'] == 'Keep'


def test_instructions_survive_more_than_twenty_messages(db):
    thread = db.info['thread']
    for i in range(2, 82):
        db.add(AgentMessage(thread_id=thread.id, sequence_number=i, role='user' if i % 2 else 'assistant',
                            content=f'Instruction {i}' if i % 2 else 'Result'))
    db.commit()
    history = AgentService()._build_history(db, thread=thread)
    assert 'Who paid Ashdown?' in history[0].content
    assert 'Instruction 3' in history[0].content
    assert 'Instruction 81' in history[-1].content


def test_explicit_budget_extension_resumes_unfinished_batch():
    cp = {'phase': 'done', 'trace': [{}, {}], 'messages': [], 'elapsed_seconds': 4000,
          'clarification': {'context': {'reason': 'tool_budget_exhausted'}}}
    renewed = extend_budget_checkpoint(cp)
    assert renewed['phase'] == 'tools' and renewed['budget_base'] == 2
    assert renewed['elapsed_seconds'] == 0 and cp['phase'] == 'done'
