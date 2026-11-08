"""Stop for work running on the server (Background Tasks, Neil 8 Nov: "I would like a stop tasks capability").

Before this there was no stop on that screen: the list held only rows of background_tasks and the server had no
way to end one. Each kind is stopped through its own existing stop; the person, what finished and what did not
are recorded in the activity trail and listed as stopped.
"""
import asyncio
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from postgres.base import Base
from postgres.models.activity_event import ActivityEvent
from postgres.models.case import Case
from postgres.models.case_export import CaseExport
from postgres.models.case_membership import CaseMembership
from postgres.models.enums import CaseMembershipRole, GlobalRole
from postgres.models.evidence import EvidenceFile, IngestionLog
from postgres.models.financial_import_batches import FinancialImportBatch, FinancialImportBatchItem
from postgres.models.user import User
from services import running_work


@pytest.fixture()
def db():
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    event.listen(engine, "connect", lambda c, _: c.execute("PRAGMA foreign_keys=OFF"))
    Base.metadata.create_all(engine, tables=[t.__table__ for t in (
        User, Case, CaseMembership, EvidenceFile, IngestionLog, CaseExport, FinancialImportBatch,
        FinancialImportBatchItem, ActivityEvent)])
    with Session(engine) as session:
        yield session


def _user(db, role=GlobalRole.user, name="Owner Person"):
    user = User(id=uuid4(), email=f"{uuid4().hex[:8]}@example.test", name=name, password_hash="x", global_role=role)
    db.add(user)
    db.commit()
    return user


def _case(db, owner=None):
    owner_id = owner.id if owner else _user(db, name="Somebody").id
    case = Case(id=uuid4(), title="Verification", created_by_user_id=owner_id, owner_user_id=owner_id)
    db.add(case)
    db.commit()
    if owner is not None:
        db.add(CaseMembership(case_id=case.id, user_id=owner.id, membership_role=CaseMembershipRole.owner,
                              permissions={}, added_by_user_id=owner.id))
    db.commit()
    return case


def _file(db, case, status="processing", job="j1"):
    row = EvidenceFile(id=uuid4(), case_id=case.id, original_filename=f"{uuid4().hex[:6]}.pdf", stored_path="/x",
                       status=status, engine_job_id=job, sha256="0" * 64, size=1)
    db.add(row)
    db.commit()
    return row


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def test_an_owner_stops_processing_in_their_case_and_the_stop_is_recorded(db, monkeypatch):
    owner = _user(db)
    case = _case(db, owner)
    for job in ("j1", "j1", "j2"):
        _file(db, case, job=job)
    _file(db, case, status="processed")
    asked = []

    async def control(job_id, case_id, action):
        asked.append((job_id, action))
        return {"state": "cancelling", "affected_jobs": 2 if job_id == "j1" else 1}
    from services import evidence_engine_client
    monkeypatch.setattr(evidence_engine_client, "control_job", control)

    listed = running_work.list_running(db, owner)
    assert [(t["kind"], t["progress"]["total"]) for t in listed["tasks"]] == [("processing", 3)]

    out = _run(running_work.stop(db, owner, "processing", str(case.id)))
    assert asked == [("j1", "cancel"), ("j2", "cancel")]
    assert out["summary"].startswith("Stopped by Owner Person. Of 3 files processing: 3 asked to stop")
    event_row = db.query(ActivityEvent).one()
    assert event_row.action == "background_task_stopped" and event_row.case_id == case.id
    assert event_row.details["counts"] == {"processing": 3, "asked_to_stop": 3, "could_not_stop": 0,
                                           "without_job": 0}
    stopped = running_work.list_running(db, owner)["stopped"]
    assert stopped[0]["stopped_by"] == "Owner Person" and stopped[0]["summary"] == out["summary"]


def test_a_batch_already_writing_to_the_case_is_reported_not_hidden(db, monkeypatch):
    owner = _user(db)
    case = _case(db, owner)
    _file(db, case, job="j1")
    _file(db, case, job="j2")

    async def control(job_id, case_id, action):
        if job_id == "j2":
            request = httpx.Request("POST", "http://engine/jobs/j2/cancel")
            raise httpx.HTTPStatusError("409", request=request, response=httpx.Response(
                409, json={"detail": "This batch has already started writing to the case."}, request=request))
        return {"affected_jobs": 1}
    from services import evidence_engine_client
    monkeypatch.setattr(evidence_engine_client, "control_job", control)
    out = _run(running_work.stop(db, owner, "processing", str(case.id)))
    assert "1 asked to stop" in out["summary"]
    assert "1 batch could not be stopped: This batch has already started writing to the case." in out["summary"]


def test_someone_who_does_not_own_the_case_cannot_stop_it_or_see_it(db, monkeypatch):
    owner, other = _user(db), _user(db, name="Other")
    case = _case(db, owner)
    _file(db, case)
    assert running_work.list_running(db, other)["tasks"] == []
    with pytest.raises(running_work.StopRefused) as refused:
        _run(running_work.stop(db, other, "processing", str(case.id)))
    assert refused.value.status_code == 403
    assert db.query(ActivityEvent).count() == 0


def test_an_administrator_sees_and_stops_any_case(db):
    admin = _user(db, GlobalRole.admin, name="Admin")
    case = _case(db, _user(db))
    export = CaseExport(id=uuid4(), case_id=case.id, requested_by_email="a@example.test", requested_by_name="A",
                        status="running", done=4, total=10)
    db.add(export)
    db.commit()
    assert [t["kind"] for t in running_work.list_running(db, admin)["tasks"]] == ["export"]
    out = _run(running_work.stop(db, admin, "export", str(export.id)))
    assert db.get(CaseExport, export.id).status == "cancelling"
    assert "4 of 10 items were written before the stop; no export file is offered" in out["summary"]


def test_a_statement_batch_is_paused_so_untried_statements_stay_unmarked(db, monkeypatch):
    owner = _user(db)
    case = _case(db, owner)
    batch = FinancialImportBatch(id=uuid4(), case_id=case.id, created_by=owner.id, status="preparing",
                                 files=[{"file_id": "a"}, {"file_id": "b"}, {"file_id": "c"}],
                                 actor={"name": "Owner Person"})
    db.add(batch)
    db.commit()
    db.add(FinancialImportBatchItem(id=uuid4(), batch_id=batch.id, file_id=uuid4(), status="ready", summary={}))
    db.commit()
    out = _run(running_work.stop(db, owner, "statement_import", str(batch.id)))
    assert db.get(FinancialImportBatch, batch.id).status == "paused"
    assert db.query(FinancialImportBatchItem).count() == 1
    assert "1 of 3 statements were prepared and stay in the batch; 2 were not started" in out["summary"]
