"""AI spending limits: refused at a limit with the reason and the sum, no cap when unset, alerts once, spend from the
cost records so a restart keeps it, and a model call that writes its own cost record."""
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from postgres.models.cost_record import CostJobType, CostRecord
from postgres.models.runtime_state import AIModelPolicy
from services import ai_budget
from services import ai_costs_service as costs


@pytest.fixture()
def db():
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    AIModelPolicy.__table__.create(engine)
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE cost_records (id TEXT PRIMARY KEY, job_type TEXT, case_id TEXT, user_id TEXT, agent_run_id TEXT,"
            " provider TEXT, model_id TEXT, prompt_tokens INT, completion_tokens INT, total_tokens INT, cost_usd NUMERIC,"
            " operation_kind TEXT, engine_job_id TEXT, evidence_file_id TEXT, pricing_version TEXT, description TEXT,"
            " extra_metadata TEXT, created_at TIMESTAMP, updated_at TIMESTAMP)")
        connection.exec_driver_sql("CREATE TABLE cases (id TEXT PRIMARY KEY, title TEXT)")
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def spend(db, usd, case_id=None, when=None):
    when = when or datetime.now(timezone.utc)
    db.add(CostRecord(id=uuid.uuid4(), job_type="ai_assistant", provider="deepseek", model_id="m", cost_usd=usd,
                      case_id=case_id, created_at=when, updated_at=when))
    db.commit()


CASE = uuid.UUID("cded78d0-e659-44cc-940d-d8f8c8012760")


def test_unset_means_no_cap_and_reads_no_spend(db):
    spend(db, 5000, CASE)
    with patch.object(ai_budget, "case_spend", side_effect=AssertionError), \
            patch.object(ai_budget, "month_spend", side_effect=AssertionError):
        ai_budget.check(db, CASE, "this agent question")
    view = ai_budget.overview(db)
    assert view["capped"] is False and view["case_limit_usd"] is None and view["month_limit_usd"] is None


def test_case_limit_refuses_with_the_reason_and_the_sum(db):
    ai_budget.set_limits(db, case_limit_usd=10, month_limit_usd=None, updated_by="n")
    spend(db, 9.99, CASE)
    ai_budget.check(db, CASE, "this agent question")
    spend(db, 0.01, CASE)
    with pytest.raises(ai_budget.BudgetRefused) as refused:
        ai_budget.check(db, CASE, "this agent question")
    assert "this agent question" in refused.value.reason
    assert "$10.00 spent of the $10.00 limit" in refused.value.reason
    assert refused.value.payload["scope"] == "case"


def test_month_limit_counts_every_case_and_uncased_work_this_month_only(db):
    ai_budget.set_limits(db, case_limit_usd=None, month_limit_usd=20, updated_by="n")
    spend(db, 500, CASE, when=datetime.now(timezone.utc) - timedelta(days=62))
    spend(db, 15, uuid.uuid4())
    ai_budget.check(db, CASE, "x")
    spend(db, 5, None)
    with pytest.raises(ai_budget.BudgetRefused) as refused:
        ai_budget.check(db, CASE, "x")
    assert refused.value.scope == "month"


def test_a_case_limit_only_tightens_and_clearing_it_leaves_the_deployment_limit(db):
    ai_budget.set_limits(db, case_limit_usd=10, month_limit_usd=None, updated_by="n")
    ai_budget.set_case_limit(db, CASE, 50, updated_by="owner")
    assert ai_budget.case_limit(ai_budget.get_settings(db), CASE) == 10
    ai_budget.set_case_limit(db, CASE, 1, updated_by="owner")
    assert ai_budget.case_limit(ai_budget.get_settings(db), CASE) == 1
    ai_budget.set_case_limit(db, CASE, None, updated_by="owner")
    assert ai_budget.case_limit(ai_budget.get_settings(db), CASE) == 10


def test_an_unreadable_limit_stops_no_work(db):
    with patch.object(ai_budget, "limit_in_force", side_effect=RuntimeError("db")):
        ai_budget.check(db, CASE, "x")


def test_alerts_at_80_and_at_the_limit_once_each(db):
    ai_budget.set_limits(db, case_limit_usd=10, month_limit_usd=100, updated_by="n")
    spend(db, 7, CASE)
    assert ai_budget.record_alerts(db) == []
    spend(db, 1, CASE)
    first = ai_budget.record_alerts(db)
    assert [(a["scope"], a["level"]) for a in first] == [("case", 80)]
    assert ai_budget.record_alerts(db) == []
    spend(db, 2, CASE)
    assert [a["level"] for a in ai_budget.record_alerts(db)] == [100]
    waiting = ai_budget.undelivered_alerts(db)
    assert len(waiting) == 2
    assert "new AI runs are refused" in ai_budget.alert_sentence(waiting[1], "Verification")
    ai_budget.mark_delivered(db, [a["key"] for a in waiting])
    assert ai_budget.undelivered_alerts(db) == []


def test_raising_a_limit_warns_again_at_the_new_figures(db):
    ai_budget.set_limits(db, case_limit_usd=10, month_limit_usd=None, updated_by="n")
    spend(db, 8, CASE)
    assert len(ai_budget.record_alerts(db)) == 1
    ai_budget.set_limits(db, case_limit_usd=9, month_limit_usd=None, updated_by="n")
    assert len(ai_budget.record_alerts(db)) == 1


def test_a_call_under_a_metered_context_writes_its_own_record_and_a_chat_answer_does_not():
    from services.llm_service import LLMExecutionContext

    class Answer:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": "ok"}}],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}}

    calls = []
    context = LLMExecutionContext("deepseek", "deepseek-v4-pro", api_key="k")
    with patch("services.llm_service.requests.post", return_value=Answer()), \
            patch.object(costs, "record_metered_call", side_effect=lambda *a: calls.append(a)):
        context.call("hello")
        assert len(calls) == 1 and calls[0][2]["prompt_tokens"] == 10
        context.answer_question_with_prompt("q", "c")
        assert len(calls) == 1


def test_metered_record_carries_the_case_and_only_under_a_metering_context():
    usage = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
    written = []
    with patch.object(costs, "record_cost", side_effect=lambda **k: written.append(k)), \
            patch("postgres.session.get_background_session") as session:
        session.return_value.__enter__.return_value = object()
        costs.record_metered_call("deepseek", "m", usage)
        with costs.ai_cost_context(job_type=CostJobType.AI_ASSISTANT, case_id=CASE):
            costs.record_metered_call("deepseek", "m", usage)
        assert written == []
        with costs.ai_cost_context(job_type=CostJobType.AI_ASSISTANT, case_id=CASE, meter_calls=True,
                                   description="Red cell sweep"):
            costs.record_metered_call("deepseek", "m", usage)
    assert written[0]["case_id"] == CASE and written[0]["description"] == "Red cell sweep"


def test_vision_spend_survives_a_restart_because_it_comes_from_the_cost_records():
    from services.financial import vision_reader as vr
    case = str(uuid.uuid4())
    written = {}

    def record(case_id, cost, model, provider, usage, file_id):
        written[case_id] = written.get(case_id, 0) + cost
        return True

    with patch.object(vr, "_record_reading_cost", side_effect=record), \
            patch.object(vr, "_ledger_spend", side_effect=lambda c: written.get(c, 0.0)), \
            patch.object(vr, "_over_ai_budget", return_value=False), patch.object(vr, "CASE_BUDGET_USD", 1.0):
        assert vr._reserve(case, 0.8)
        vr.settle(case, 0.8, 0.5, "deepseek-v4-pro", provider="deepseek", usage={})
        assert vr.spent(case) == pytest.approx(0.5)
        vr._spend.clear()  # a restart
        assert vr.spent(case) == pytest.approx(0.5)
        assert vr._reserve(case, 0.4)
        vr._spend.clear()
        assert not vr._reserve(case, 0.6)


def test_vision_reader_waits_at_the_ai_limit():
    from services.financial import vision_reader as vr
    with patch.object(vr, "_over_ai_budget", return_value=True), patch.object(vr, "_ledger_spend", return_value=0.0):
        assert vr._reserve(str(uuid.uuid4()), 0.01) is False
