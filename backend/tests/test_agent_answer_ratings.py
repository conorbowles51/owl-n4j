"""lx-agenttools D20: a person can rate an agent answer; it is stored with its run, sent through the manual-change
feed, never replaced, and becomes a relevance test case. SQLite, no model or network."""
import json
import uuid

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from postgres.base import Base
import postgres.models  # noqa: F401
from postgres.models.agent import AgentAnswerRating, AgentMessage, AgentRun, AgentThread
from postgres.models.case import Case
from postgres.models.user import User
from services import manual_changes
from services.agent import answer_ratings as AR

TABLES = ("users", "cases", "agent_threads", "agent_runs", "agent_messages", "agent_answer_ratings",
          "manual_changes")


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.setattr(manual_changes, "INBOX", tmp_path / "MANUAL-CHANGES.jsonl")
    manual_changes._READY.clear()
    engine = create_engine("sqlite+pysqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine, tables=[Base.metadata.tables[n] for n in TABLES])
    # The one shared test connection would be rolled back by the feed's has_table check: state it as already made.
    manual_changes._READY[id(engine)] = True
    with Session(engine, expire_on_commit=False) as db:
        user = User(email="a@example.test", name="Synthetic A", password_hash="x")
        other = User(email="b@example.test", name="Synthetic B", password_hash="x")
        db.add_all([user, other])
        db.flush()
        case = Case(title="Synthetic", owner_user_id=user.id, created_by_user_id=user.id)
        db.add(case)
        db.flush()
        thread = AgentThread(case_id=case.id, owner_user_id=user.id, title="q", status="active")
        db.add(thread)
        db.flush()
        run = AgentRun(thread_id=thread.id, case_id=case.id, user_id=user.id, status="completed") \
            if hasattr(AgentRun, "user_id") else None
        run_id = None
        question = AgentMessage(thread_id=thread.id, sequence_number=1, role="user", content="Who paid the garage?")
        answer = AgentMessage(thread_id=thread.id, sequence_number=2, role="assistant", content="Nobody I could find.",
                              model_id="synthetic-model")
        db.add_all([question, answer])
        db.commit()
        yield dict(db=db, user=user, other=other, case=case, thread=thread, answer=answer, question=question,
                   inbox=tmp_path / "MANUAL-CHANGES.jsonl", run_id=run_id)


def _rate(w, kind="not_relevant", **kw):
    out = AR.rate_answer(w["db"], case_id=w["case"].id, message_id=w["answer"].id, user=w["user"], kind=kind, **kw)
    w["db"].commit()
    return out


def test_a_rating_is_stored_with_the_question_and_goes_through_the_manual_change_feed(world):
    out = _rate(world, "too_thin", note="One line for a whole month.")
    row = world["db"].scalars(select(AgentAnswerRating)).one()
    assert (row.kind, row.action, row.question) == ("too_thin", "rate", "Who paid the garage?")
    assert row.thread_id == world["thread"].id and out["label"] == "Too thin"
    lines = [json.loads(l) for l in world["inbox"].read_text().splitlines()]
    assert len(lines) == 1 and lines[0]["kind"] == "agent_answer_rating"
    text = json.dumps(lines[0])
    assert "too_thin" in text and "Who paid the garage?" not in text, "the feed carries ids and kind, not the question"
    assert lines[0].get('after', {}).get('rating_id') == str(row.id) or str(row.id) in text


def test_missed_something_may_name_the_record_that_should_have_been_found_and_nothing_else_may(world):
    _rate(world, "missed_something", record_ref="txn://9f1c")
    with pytest.raises(AR.RatingError):
        _rate(world, "too_thin", record_ref="txn://9f1c")
    with pytest.raises(AR.RatingError):
        _rate(world, "missed_something", record_ref="the garage payment")
    with pytest.raises(AR.RatingError):
        _rate(world, "not_a_kind")


def test_only_the_owner_rates_and_only_an_agent_answer(world):
    with pytest.raises(LookupError):
        AR.rate_answer(world["db"], case_id=world["case"].id, message_id=world["answer"].id, user=world["other"],
                       kind="too_thin")
    with pytest.raises(LookupError):
        AR.rate_answer(world["db"], case_id=uuid.uuid4(), message_id=world["answer"].id, user=world["user"],
                       kind="too_thin")
    with pytest.raises(AR.RatingError):
        AR.rate_answer(world["db"], case_id=world["case"].id, message_id=world["question"].id, user=world["user"],
                       kind="too_thin")


def test_withdrawing_keeps_the_original_row_and_removes_it_from_the_active_ratings(world):
    _rate(world, "too_thin")
    _rate(world, "not_relevant")
    assert {r["kind"] for r in AR.active_for_message(world["db"], message_id=world["answer"].id, user=world["user"])} \
        == {"too_thin", "not_relevant"}
    _rate(world, "too_thin", withdraw=True)
    active = AR.active_for_message(world["db"], message_id=world["answer"].id, user=world["user"])
    assert [r["kind"] for r in active] == ["not_relevant"]
    assert world["db"].scalars(select(AgentAnswerRating)).all().__len__() == 3
    with pytest.raises(AR.RatingError):
        _rate(world, "too_thin", withdraw=True)
    by_thread = AR.active_for_thread(world["db"], thread_id=world["thread"].id, user=world["user"])
    assert list(by_thread) == [str(world["answer"].id)]


def test_an_active_rating_becomes_a_relevance_test_item_with_its_picked_record(world):
    _rate(world, "missed_something", record_ref="doc://stowell-rental-agreement/2", note="The lease was in the files.")
    rows = AR.active_rows(world["db"], case_id=world["case"].id)
    item = AR.relevance_case(rows[0])
    assert item["kind"] == "rating" and item["complaint"] == "missed_something"
    assert item["question"] == "Who paid the garage?"
    assert item["relevant"] == [{"id": "picked", "any": ["doc://stowell-rental-agreement/2"]}]
    assert item["answer_message_id"] == str(world["answer"].id)


def test_export_document_holds_each_active_rating_and_not_a_withdrawn_one(world):
    _rate(world, "missed_something", record_ref="txn://9f1c")
    _rate(world, "too_thin")
    _rate(world, "too_thin", withdraw=True)
    doc = AR.export_document(world["db"], case_id=world["case"].id)
    assert [q["complaint"] for q in doc["queries"]] == ["missed_something"]
    assert doc["queries"][0]["relevant"][0]["any"] == ["txn://9f1c"]


def test_the_rating_route_takes_only_the_three_kinds():
    from routers import agent as router
    body = router.AnswerRatingBody(case_id=uuid.uuid4(), kind="too_thin")
    assert body.withdraw is False
    with pytest.raises(Exception):
        router.AnswerRatingBody(case_id=uuid.uuid4(), kind="love_it")
    assert any(getattr(r, "path", "") == "/api/agent/messages/{message_id}/rating" for r in router.router.routes)
