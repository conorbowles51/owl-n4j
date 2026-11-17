"""Case facts and Keep watching (lx-corroengine H): a fact keeps who recorded it and when, goes to the manual-change
feed, is never rewritten (withdrawing keeps it), and a watch re-checks when the case's material changes and records
the level change with its reason."""
import tempfile
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from postgres.base import Base
from postgres.models.corroborate import CorroborateFact, CorroborateWatch
from postgres.models.manual_change import ManualChange
from services import manual_changes as mc
from services.corroborate import facts

CASE = uuid.UUID("11111111-2222-3333-4444-555555555555")
USER = SimpleNamespace(id=None, name="Test Person", email="test.person@example.com")


@pytest.fixture()
def db():
    with tempfile.TemporaryDirectory() as d:
        engine = create_engine(f"sqlite+pysqlite:///{Path(d) / 'c.db'}", future=True)
        event.listen(engine, "connect", lambda conn, _rec: setattr(conn, "isolation_level", None))
        event.listen(engine, "begin", lambda conn: conn.exec_driver_sql("BEGIN"))
        Base.metadata.create_all(engine, tables=[ManualChange.__table__, CorroborateFact.__table__,
                                                 CorroborateWatch.__table__])
        with mock.patch.object(mc, "INBOX", Path(d) / "MANUAL-CHANGES.jsonl"):
            mc._READY.clear()
            with Session(engine) as s:
                yield s
            mc._READY.clear()
        engine.dispose()


def test_a_fact_is_recorded_with_who_and_when_and_sent_to_the_manual_change_feed(db):
    f = facts.add_fact(db, case_id=CASE, kind="live_together", text_="Doe and Roe share a flat", people=["a", "b"],
                       phrase=None, user=USER)
    assert f["by_name"] == "Test Person" and f["at"] and f["state"] == "active"
    rows = db.query(ManualChange).all()
    assert len(rows) == 1 and rows[0].kind == "corroborate_case_fact" and rows[0].actor_name == "Test Person"
    assert [x["id"] for x in facts.list_facts(db, CASE)] == [f["id"]]


def test_withdrawing_keeps_the_fact_marked_withdrawn(db):
    f = facts.add_fact(db, case_id=CASE, kind="routine_phrase", text_="a shift greeting", people=[],
                       phrase="see you at the gate", user=USER)
    w = facts.withdraw_fact(db, case_id=CASE, fact_id=f["id"], user=USER)
    assert w["state"] == "withdrawn" and w["withdrawn_by"] == "Test Person" and w["text"] == "a shift greeting"
    assert facts.list_facts(db, CASE) == []
    assert [x["state"] for x in facts.list_facts(db, CASE, include_withdrawn=True)] == ["withdrawn"]
    assert db.query(ManualChange).count() == 2


def test_a_fact_needs_its_parts(db):
    with pytest.raises(facts.FactError):
        facts.add_fact(db, case_id=CASE, kind="live_together", text_="share a flat", people=["a"], phrase=None,
                       user=USER)
    with pytest.raises(facts.FactError):
        facts.add_fact(db, case_id=CASE, kind="nonsense", text_="x", people=[], phrase=None, user=USER)


def test_a_watch_rechecks_only_when_material_changes_and_records_the_reason(db):
    levels = iter([{"key": "strong", "name": "Strong link", "sentence": "Strong link: three kinds agree."}])
    calls = []

    def runner(members, question):
        calls.append(question)
        return {"level": next(levels)}

    sel = uuid.uuid4()
    with mock.patch.object(facts, "material", side_effect=[{"ledger": [1, None]}, {"ledger": [1, None]},
                                                           {"ledger": [2, "2026-11-17"]}]), \
            mock.patch("services.case_selections.describe", return_value={"members": [{"type": "record", "id": "r"}]}):
        w = facts.watch(db, case_id=CASE, selection_id=sel, question={"kind": "every_time"},
                        level={"key": "probable", "name": "Probable link", "sentence": "s"}, user=USER)
        assert facts.recheck(db, CASE, runner=runner)[0]["unseen"] is False and calls == []
        out = facts.recheck(db, CASE, runner=runner)[0]
    assert calls == [{"kind": "every_time"}]
    assert out["unseen"] is True and out["level"]["key"] == "strong"
    last = out["history"][-1]
    assert last["from"]["key"] == "probable" and last["reason"] == "New or changed bank records: now Strong link."
    assert facts.mark_seen(db, CASE, w["id"])["unseen"] is False
    assert facts.stop(db, CASE, w["id"])["active"] is False


def test_the_migration_is_the_one_head_and_creates_both_tables():
    src = (Path(__file__).resolve().parents[1] / "postgres" / "alembic" / "versions" /
           "20261117_corroborate_facts.py").read_text()
    assert "corroborate_case_facts" in src and "corroborate_watches" in src
