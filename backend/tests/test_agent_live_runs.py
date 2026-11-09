"""lx-agentlive item A: an agent run says what it is doing, step by step, and goes on when the page is left.

Measured before (live run 8df85211, 8 Nov 2026): a batch of three tool calls (51 s, 6 s, 56 s) showed nothing new for
up to 109 s, the run died with its request when the page was left, and a Stop reached only one of two web workers.
Each test here failed on the old code: the runner took no ``on_progress``, there was no live channel or detached
worker, the heartbeat carried no progress and never read a Stop written elsewhere.
"""
from __future__ import annotations

import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from services.agent import live_runs
from services.agent.graph import AgentGraphRunner

CASE = "00000000-0000-0000-0000-0000000000aa"
SLOW_TOOL_SECONDS = 2.5


class ScriptedModel:
    """Asks for one tool call per turn from ``steps``, then answers."""

    def __init__(self, steps):
        self.steps, self.index = steps, 0

    def bind_tools(self, tools):
        owner = self

        class Bound:
            def invoke(self, messages):
                if owner.index == len(owner.steps):
                    return AIMessage(content="Done.")
                name, arguments = owner.steps[owner.index]
                owner.index += 1
                return AIMessage(content="", tool_calls=[{"id": f"step-{owner.index}", "name": name,
                                                          "args": arguments}])

        return Bound()

    def invoke(self, messages):
        return AIMessage(content="Done. [Ashdown Ltd](rec://00000000-0000-0000-0000-000000000001)")


def runner_for(steps):
    runner = object.__new__(AgentGraphRunner)
    runner.base_model, runner.model_id = ScriptedModel(steps), "deepseek-v4-pro"
    return runner


def slow_rows(*_args, **_kwargs):
    time.sleep(SLOW_TOOL_SECONDS)
    return [{"key": "entity-1", "name": "Ashdown Ltd"}]


CYPHER = ("run_readonly_cypher", {"query": "MATCH (n {case_id: $case_id}) RETURN n.key AS key LIMIT 5", "limit": 5})


def test_seven_steps_each_get_a_plain_progress_line_in_order():
    seen = []
    runner = runner_for([CYPHER] * 7)
    with patch("services.agent.tools.run_readonly_cypher", return_value=[{"key": "entity-1"}]):
        events = list(runner.stream(case_id=CASE, messages=[HumanMessage(content="Who is Ashdown?")],
                                    on_progress=seen.append))
    assert events[-1]["type"] == "final"
    tools = [p for p in seen if p["phase"] == "tool"]
    assert [p["step"] for p in tools] == [1, 2, 3, 4, 5, 6, 7]
    assert all(p["title"] == "Querying the case graph" for p in tools)
    thinking = [p for p in seen if p["phase"] == "thinking"]
    assert thinking[0]["title"] == "Reading the question and planning the first step"
    assert "step 3 found" in thinking[3]["title"]
    assert seen[-1]["phase"] == "writing"
    # Plain words only: no tool names on the line a person reads.
    assert not any("_" in p["title"] for p in seen)


def test_progress_reaches_the_reader_within_two_seconds_and_while_a_slow_step_runs():
    live = live_runs.LiveRun()
    runner = runner_for([CYPHER, CYPHER])
    started = time.monotonic()

    def events():
        with patch("services.agent.tools.run_readonly_cypher", side_effect=slow_rows):
            yield from runner.stream(case_id=CASE, messages=[HumanMessage(content="Who is Ashdown?")],
                                     on_progress=live.set_progress)

    live_runs.pump(events(), live)
    arrivals = []
    for event in live.read(keepalive=0.5):
        arrivals.append((time.monotonic() - started, event))
    progress = [(t, e["progress"]) for t, e in arrivals if e["type"] == "progress"]
    assert progress and progress[0][0] < 2.0
    # The line for step 1 arrives as the step starts, not when its 2.5 s tool returns.
    step1 = next(t for t, p in progress if p["phase"] == "tool" and p["step"] == 1)
    step1_done = next(t for t, e in arrivals if e["type"] == "tool_result")
    assert step1_done - step1 >= SLOW_TOOL_SECONDS - 0.3
    # While the slow tool runs, the reader is never left more than 2 s without a word.
    times = [t for t, _ in arrivals]
    assert max(b - a for a, b in zip(times, times[1:])) < 2.0


def test_a_run_goes_on_to_its_end_when_its_reader_leaves():
    live = live_runs.LiveRun()
    finished = []

    def events():
        for index in range(5):
            time.sleep(0.05)
            yield {"type": "status", "message": f"step {index}"}
        finished.append("end")

    ended = []
    thread = live_runs.pump(events(), live, on_end=lambda: ended.append(True))
    reader = live.read(keepalive=0.2)
    assert next(reader)["type"] == "status"
    live.reader_left()  # the page was left
    thread.join(timeout=5)
    assert finished == ["end"] and ended == [True]


def test_tool_lines_name_the_subject_in_plain_words():
    line = live_runs.tool_line("get_financial_coverage", {"account_holders": ["Jose Alejandro Reyes Zeind"]})
    assert line == "Checking the accounts held by Jose Alejandro Reyes Zeind"
    assert live_runs.tool_line("get_money_between", {"party_a": "party:7baa3f72-1db6-44ae-9d95-9afd4d4fa464",
                                                     "party_b": "party:NOVAC"}) == \
        "Reading the money between two parties"
    assert live_runs.tool_line("phone_new_tool", {}) == "Reading the phone evidence"
    assert live_runs.tool_line("propose_entity", {"name": "x"}) == "Preparing a suggestion for you to review"


# The heartbeat: progress stored for a person who comes back, and a Stop written by the other worker obeyed.

@pytest.fixture()
def db():
    from postgres.base import Base
    from postgres.models.agent import AgentMessage, AgentRun, AgentThread
    from postgres.models.case import Case
    from postgres.models.case_context import CaseMandateVersion
    from postgres.models.user import User
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine, tables=[User.__table__, Case.__table__, CaseMandateVersion.__table__,
                                             AgentThread.__table__, AgentRun.__table__, AgentMessage.__table__])
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
        run = AgentRun(thread_id=thread.id, case_id=case.id, user_id=owner.id, status="running",
                       provider="deepseek", model_id="deepseek-v4-pro", input_message="Who paid Ashdown?",
                       started_at=datetime.now(timezone.utc), extra_metadata={"case_layer": "all"})
        session.add(run)
        session.commit()
        session.info.update(owner=owner, case=case, thread=thread, run=run, factory=factory)
        yield session
    engine.dispose()


@pytest.fixture()
def own_sessions(db, monkeypatch):
    import postgres.session as S

    @contextmanager
    def own_session():
        with db.info["factory"]() as session:
            yield session
    monkeypatch.setattr(S, "get_background_session", own_session)


def test_the_heartbeat_stores_the_progress_line_and_keeps_other_metadata(db, own_sessions):
    from services.agent import run_settle as R
    from services.agent import storage
    run = db.info["run"]
    beat = R.RunHeartbeat(run.id)
    beat.note_progress(live_runs.progress_for_tool(step=3, name="get_financial_coverage",
                                                   args={"account_holders": ["Jose Alejandro Reyes Zeind"]}))
    beat._beat_once()
    db.expire_all()
    stored = db.get(type(run), run.id)
    assert stored.extra_metadata["case_layer"] == "all"
    assert stored.extra_metadata["progress"]["title"] == "Checking the accounts held by Jose Alejandro Reyes Zeind"
    assert stored.extra_metadata["progress"]["step"] == 3
    fields = storage.run_progress_fields(stored)
    assert fields["progress"]["step"] == 3 and fields["stale"] is False


def test_a_stop_written_by_the_other_worker_stops_this_run(db, own_sessions):
    from services.agent import run_settle as R
    from services.agent.cancellation import clear_cancel, is_cancelled
    run = db.info["run"]
    beat = R.RunHeartbeat(run.id)
    beat._check_stopped_elsewhere()
    assert not is_cancelled(str(run.id))
    run.status = "cancelled"  # what cancel_run writes, from whichever worker the Stop reached
    db.commit()
    beat._check_stopped_elsewhere()
    assert is_cancelled(str(run.id))
    clear_cancel(str(run.id))


def test_a_run_whose_heartbeat_is_old_reads_stale_with_no_progress_once_finished(db):
    from services.agent import storage
    run = db.info["run"]
    run.heartbeat_at = datetime.now(timezone.utc) - timedelta(seconds=live_runs.STALE_SECONDS + 5)
    run.extra_metadata = {"progress": {"title": "Reading the payments", "step": 2}}
    db.commit()
    assert storage.run_progress_fields(run)["stale"] is True
    run.status = "completed"
    db.commit()
    fields = storage.run_progress_fields(run)
    assert fields["stale"] is False and fields["progress"] is None


def test_active_runs_lists_only_the_persons_running_runs_in_the_case(db, monkeypatch):
    from services.agent import storage
    monkeypatch.setattr(storage, "check_case_access", lambda *a, **k: None)
    owner, run = db.info["owner"], db.info["run"]
    out = storage.active_runs(db, user=owner, case_id=db.info["case"].id)
    assert [r["run_id"] for r in out] == [str(run.id)]
    run.status = "completed"
    db.commit()
    assert storage.active_runs(db, user=owner, case_id=db.info["case"].id) == []
    assert uuid.UUID(out[0]["thread_id"])


def test_text_shown_while_the_run_works_is_in_plain_words_too():
    """The streamed answer and a clarification question go through the same plain-words check as the stored one."""
    from services.agent.service import AgentService
    question = AgentService._clarification_from_runner(
        {"question": "Should I widen get_financial_coverage to p3 rows?",
         "options": [{"id": "a", "label": "Yes"}, {"id": "b", "label": "No"}]},
        thread_id="t", run_id="r", original_message="q").question
    assert "get_financial_coverage" not in question and "p3" not in question


def test_a_case_with_no_phones_is_not_sent_the_phone_tools_with_every_turn(monkeypatch):
    """lx-agentlive B: phone-only definitions are a quarter of what every turn re-sends; BNB2 holds no phones."""
    from types import SimpleNamespace
    from services.agent import capabilities, workflows
    from services.agent.service import AgentService
    counts = {"phones": 0, "ledger": 27673, "financial_sources": 1363, "trades": 0}
    monkeypatch.setattr(workflows, "case_counts", lambda conn, case_id: dict(counts))
    db = SimpleNamespace(connection=lambda: None)
    request = SimpleNamespace(all_cases=False, case_id=CASE, workflow_id="hidden-assets")
    hidden, note = AgentService._tools_not_offered(db, request)
    phone_tools = set(capabilities.tools_for_type("phones"))
    assert "phone_messages" in hidden and "phone_places" in hidden
    assert "phone_coverage" not in hidden  # the agent can still say the case holds none
    assert "get_money_signal_leads" not in hidden  # a step of the run's workflow is always offered
    assert not hidden - phone_tools  # financial tools stay: the case has statements
    assert "no phone extractions" in note
    # All-cases runs and a failed count hide nothing.
    assert AgentService._tools_not_offered(db, SimpleNamespace(**{**vars(request), "all_cases": True}))[0] == frozenset()
    counts["phones"] = None
    assert AgentService._tools_not_offered(db, request)[0] == frozenset()


def test_the_runner_binds_only_the_offered_tools_and_a_hidden_one_still_runs():
    bound = []
    runner = runner_for([("phone_coverage", {})])
    original = runner.base_model.bind_tools

    def capture(tools):
        bound.extend(tool.name for tool in tools)
        return original(tools)
    runner.base_model.bind_tools = capture
    events = list(runner.stream(case_id=CASE, messages=[HumanMessage(content="Any phones?")],
                                hidden_tools=frozenset({"phone_messages"})))
    assert "phone_messages" not in bound and "phone_coverage" in bound
    assert events[-1]["type"] == "final"
