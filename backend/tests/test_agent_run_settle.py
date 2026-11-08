"""lx-agentruns: an agent run killed by a restart says so.

A run executes inside its web request, so a release restart kills the worker and the ``agent_runs`` row used to stay
``running`` for ever (10 rows on live, 8 Nov 2026, 2 to 33 days old) while the thread kept a question with no answer.
``services.agent.run_settle`` beats a heartbeat while the worker lives and settles every run whose beat stopped:
``interrupted`` (never ``completed``, never left ``running``), the cut on the run record, a plain line in the thread.
New and genuinely running runs are untouched: the sweep keys on the heartbeat, not age alone.
"""
from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from postgres.base import Base
from postgres.models.agent import AgentMessage, AgentRun, AgentThread
from postgres.models.case import Case
from postgres.models.case_context import CaseMandateVersion
from postgres.models.user import User
from services.agent import run_settle as R

TABLES = [User.__table__, Case.__table__, CaseMandateVersion.__table__, AgentThread.__table__, AgentRun.__table__,
          AgentMessage.__table__]


@pytest.fixture()
def db():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine, tables=TABLES)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        owner = User(email="alex@example.test", name="Alex", password_hash="x")
        session.add(owner)
        session.flush()
        case = Case(title="Case", created_by_user_id=owner.id, owner_user_id=owner.id)
        session.add(case)
        session.flush()
        thread = AgentThread(case_id=case.id, owner_user_id=owner.id, title="Who paid Ashdown?")
        session.add(thread)
        session.flush()
        session.add(AgentMessage(thread_id=thread.id, sequence_number=1, role="user", content="Who paid Ashdown?"))
        session.commit()
        session.info.update(owner=owner, case=case, thread=thread, factory=factory)
        yield session
    engine.dispose()


def run_row(db, *, status="running", beat=None, started=None):
    thread = db.info["thread"]
    run = AgentRun(thread_id=thread.id, case_id=thread.case_id, user_id=db.info["owner"].id, status=status,
                   provider="deepseek", model_id="deepseek-v4-pro", input_message="Who paid Ashdown?",
                   started_at=started or datetime.now(timezone.utc), heartbeat_at=beat)
    db.add(run)
    db.commit()
    return run


def ago(seconds):
    return datetime.now(timezone.utc) - timedelta(seconds=seconds)


def thread_lines(db, run):
    rows = db.scalars(select(AgentMessage).where(AgentMessage.thread_id == run.thread_id)
                      .order_by(AgentMessage.sequence_number)).all()
    return [(m.role, m.content, m.run_id) for m in rows]


def test_a_run_whose_beat_stopped_reads_interrupted_and_its_thread_says_so(db):
    run = run_row(db, beat=ago(R.STALE_AFTER + 30), started=ago(600))
    settled = R.settle_orphaned_runs(db)
    assert [r["run_id"] for r in settled] == [str(run.id)]
    db.refresh(run)
    assert run.status == "interrupted"
    assert run.status != "completed"
    assert run.completed_at is not None
    assert "restarted" in run.error and (run.record_summary or {}).get("basis")
    lines = thread_lines(db, run)
    assert lines[-1][0] == "assistant" and lines[-1][1] == R.THREAD_LINE and lines[-1][2] == run.id


def test_a_run_from_before_the_heartbeat_column_is_settled_by_its_start(db):
    # The rows already on live: started days ago, heartbeat never written.
    run = run_row(db, beat=None, started=ago(3 * 24 * 3600))
    assert R.settle_orphaned_runs(db)
    db.refresh(run)
    assert run.status == "interrupted"


def test_new_and_beating_runs_are_untouched(db):
    beating = run_row(db, beat=ago(5), started=ago(3600))   # old but alive: the key is the beat, not age
    fresh = run_row(db, beat=None, started=ago(5))          # just created, first beat not yet written
    assert R.settle_orphaned_runs(db) == []
    db.refresh(beating)
    db.refresh(fresh)
    assert beating.status == "running" and beating.error is None
    assert fresh.status == "running"
    assert thread_lines(db, beating)[-1][0] == "user"


def test_finished_runs_are_never_touched_and_a_second_pass_settles_nothing(db):
    for status in ("completed", "failed", "cancelled", "clarification_required"):
        run_row(db, status=status, beat=ago(9999), started=ago(9999))
    cut = run_row(db, beat=ago(9999), started=ago(9999))
    assert len(R.settle_orphaned_runs(db)) == 1
    assert R.settle_orphaned_runs(db) == []           # idempotent: the thread line is written once
    assert sum(1 for role, text, _ in thread_lines(db, cut) if text == R.THREAD_LINE) == 1
    statuses = {r.status for r in db.scalars(select(AgentRun)).all()}
    assert statuses == {"completed", "failed", "cancelled", "clarification_required", "interrupted"}


def test_the_heartbeat_beats_while_the_worker_lives_and_stops_with_it(db, monkeypatch):
    import postgres.session as S

    @contextmanager
    def own_session():
        with db.info["factory"]() as session:
            yield session
    monkeypatch.setattr(S, "get_background_session", own_session)
    run = run_row(db, beat=None, started=ago(0))
    beat = R.RunHeartbeat(run.id)
    beat.start()
    beat.stop()
    db.refresh(run)
    first = run.heartbeat_at
    assert first is not None
    beat._beat_once()  # a tick after stop() would be the thread's last; it still names this run only
    db.refresh(run)
    assert run.heartbeat_at >= first
    # And the settle sweep leaves this run alone while its beat is fresh.
    assert R.settle_orphaned_runs(db) == []


def test_interrupted_is_a_status_the_api_schema_accepts():
    from services.agent.schemas import AgentRunStatusResponse
    out = AgentRunStatusResponse(run_id=str(uuid.uuid4()), thread_id=str(uuid.uuid4()), status="interrupted",
                                 error=R.RECORD_WORDS)
    assert out.status == "interrupted"


def test_the_lifespan_starts_the_sweep():
    # The sweep only helps if the backend runs it: the lifespan names the task.
    from pathlib import Path
    main = (Path(__file__).resolve().parents[1] / "main.py").read_text()
    assert "settle_agent_runs_forever" in main and "agent-run-settle" in main
    assert "agent_run_settle_task" in main.split("stop_background_tasks", 1)[1]
