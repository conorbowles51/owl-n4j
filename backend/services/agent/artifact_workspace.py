"""Authenticated immutable artifact revisions, shared by HTTP editing and saved views."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from postgres.models.agent import AgentArtifactRecord, AgentThread
from services.agent import storage
from services.agent.deliverables import revise_artifact


class StaleArtifact(ValueError):
    pass


def versions(db, user, artifact_id: UUID):
    record = storage.get_artifact_for_user(db, artifact_id=artifact_id, user=user)
    family = (record.extra_metadata or {}).get("deliverable_id", str(record.id))
    # Same thread is an explicit authorization boundary; legacy artifacts are their own family.
    rows = db.scalars(select(AgentArtifactRecord).where(AgentArtifactRecord.thread_id == record.thread_id)).all()
    family_rows = [r for r in rows if (r.extra_metadata or {}).get("deliverable_id", str(r.id)) == family]
    for row in family_rows:
        storage.check_artifact_access(db, artifact=row, user=user)
    return sorted(family_rows, key=lambda r: int((r.extra_metadata or {}).get("revision", 1)))


def save_revision(db, user, artifact_id: UUID, *, expected_revision: int, data: dict,
                  title: str | None = None, revision_note: str = ""):
    previous = storage.get_artifact_for_user(db, artifact_id=artifact_id, user=user)
    # Serialize revisions without overwriting any original. A thread row exists for legacy artifacts too.
    db.execute(select(AgentThread).where(AgentThread.id == previous.thread_id).with_for_update()).scalar_one()
    latest = versions(db, user, artifact_id)[-1]
    if latest.id != previous.id or int((latest.extra_metadata or {}).get("revision", 1)) != expected_revision:
        raise StaleArtifact("The document has a newer revision. Reload it before saving; your edits were not overwritten.")
    value = revise_artifact(storage.to_api_artifact(previous).model_dump(), data,
                            expected_revision=expected_revision, title=title, revision_note=revision_note)
    from services.agent.claim_validation import apply_claim_validation
    sources = ((previous.run.extra_metadata or {}).get("execution_checkpoint") or {}).get("result_store", {}) if previous.run else {}
    siblings = db.scalars(select(AgentArtifactRecord).where(AgentArtifactRecord.thread_id == previous.thread_id)).all()
    accessible = storage.readable_artifacts(db, siblings, user)
    apply_claim_validation(value, result_store=sources,
        artifact_store={str(row.id): storage.to_api_artifact(row).model_dump() for row in accessible})
    value["metadata"].update(origin="person", edited_by_user_id=str(user.id))
    record = AgentArtifactRecord(id=UUID(value["id"]), thread_id=previous.thread_id, run_id=previous.run_id,
                                  type=value["type"], title=value["title"], payload=value["data"],
                                  extra_metadata=value["metadata"])
    db.add(record)
    db.flush()
    return record
