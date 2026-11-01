"""Phone records on the Timeline and instants on saved views (07 section 6.4 item 8; CO-21)."""
from __future__ import annotations

import importlib.util
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from postgres import link_types
from postgres.base import Base
from postgres.models.case import Case
from postgres.models.timeline_entry import TimelineEntry
from postgres.models.timeline_view import TimelineView, TimelineViewEvent
from postgres.models.user import User
from services import timeline_view_service
from services.timeline_entries import TimelineAddition, list_entries, preview_addition, save_addition

BACKEND = Path(__file__).resolve().parents[1]
RECORDS = {
    "msg-1": {"instant": "2024-03-01T23:30:00-05:00", "zone": "America/New_York", "type": "Message", "summary": "synthetic"},
    "call-1": {"instant": "2024-03-02T09:05:00+00:00", "zone": "Europe/London", "type": "Call"},
    "note-1": {"type": "Note"},
}


@pytest.fixture()
def world():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine, tables=[User.__table__, Case.__table__, TimelineEntry.__table__])
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    user_id, case_id = uuid.uuid4(), uuid.uuid4()
    with factory() as db:
        db.add(User(id=user_id, email="owner@example.test", name="Owner", password_hash="x"))
        db.flush()
        db.add(Case(id=case_id, title="Case", created_by_user_id=user_id, owner_user_id=user_id))
        db.commit()
    saved = dict(link_types._RESOLVERS)
    link_types._RESOLVERS.clear()
    link_types.register_phone_resolver("phone_record", lambda db, case, target: link_types.PhoneTarget(
        label=RECORDS[target]["type"], mapping_versions={"time": "m1"}, metadata=RECORDS[target])
        if case == case_id and target in RECORDS else None)
    yield factory, case_id
    link_types._RESOLVERS.clear()
    link_types._RESOLVERS.update(saved)
    engine.dispose()


def _save(db, case_id, request):
    request.expected_revision = preview_addition(db, case_id=case_id, request=request)["revision"]
    return save_addition(db, case_id=case_id, request=request, actor="owner@example.test")


def test_phone_records_are_added_with_instant_and_zone_and_the_usual_preview(world):
    factory, case_id = world
    with factory() as db:
        request = TimelineAddition(source_kind="phone_record", source_ids=["msg-1", "call-1", "note-1"])
        preview = preview_addition(db, case_id=case_id, request=request)
        assert (preview["ready"], preview["already_added"], preview["undated"]) == (2, 0, 1)
        message = preview["rows"][0]["event"]
        # The date and time are as recorded in the record's own zone; the instant keeps the offset.
        assert (message["date"], message["time"], message["zone"]) == ("2024-03-01", "23:30", "America/New_York")
        assert message["instant"] == "2024-03-01T23:30:00-05:00"
        assert message["source"]["kind"] == "phone_record" and message["source"]["id"] == "msg-1"
        result = _save(db, case_id, TimelineAddition(source_kind="phone_record", source_ids=["msg-1", "call-1", "note-1"]))
        assert (result["added"], result["undated"]) == (2, 1)
        again = _save(db, case_id, TimelineAddition(source_kind="phone_record", source_ids=["msg-1"]))
        assert (again["added"], again["already_added"]) == (0, 1)
        events = {event["source"]["id"]: event for event in list_entries(db, case_id=case_id)}
        assert set(events) == {"msg-1", "call-1"} and events["call-1"]["zone"] == "Europe/London"
        with pytest.raises(link_types.LinkTargetError):
            preview_addition(db, case_id=case_id, request=TimelineAddition(source_kind="phone_record", source_ids=["nope"]))


def test_other_kinds_still_take_identifiers_and_more_than_5000_is_refused():
    with pytest.raises(ValidationError, match="valid identifier"):
        TimelineAddition(source_kind="transaction", source_ids=["not-a-uuid"])
    value = uuid.uuid4()
    assert TimelineAddition(source_kind="transaction", source_ids=[str(value)]).source_ids == [value]
    with pytest.raises(ValidationError):
        TimelineAddition(source_kind="phone_record", source_ids=[f"r{n}" for n in range(5001)])


def test_saved_view_events_carry_instant_and_zone_and_views_keep_their_old_order():
    view, case, user = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    phone = timeline_view_service._view_event(view, case, {"key": "p", "date": "2024-03-01", "time": "23:30",
                                                           "instant": "2024-03-01T23:30:00-05:00",
                                                           "zone": "America/New_York"}, 0, user)
    assert phone.sort_instant == datetime(2024, 3, 2, 4, 30, tzinfo=timezone.utc)
    assert (phone.sort_zone, phone.sort_date, phone.sort_time) == ("America/New_York", "2024-03-01", "23:30")
    written = timeline_view_service._view_event(view, case, {"key": "w", "date": "2024-03-01", "time": "10:15"}, 1, user)
    assert (written.sort_instant, written.sort_zone) == (datetime(2024, 3, 1, 10, 15, tzinfo=timezone.utc), "wall_clock")
    dated = timeline_view_service._view_event(view, case, {"key": "d", "date": "2024-03-01"}, 2, user)
    assert (dated.sort_instant, dated.sort_zone, dated.sort_time) == (None, "wall_clock", "99:99")
    order = TimelineView.events.property.order_by
    assert [str(column) for column in order] == [
        "timeline_view_events.sort_date", "timeline_view_events.sort_time", "timeline_view_events.position"]


@pytest.mark.skipif(not os.environ.get("DOSSIER_TEST_DATABASE_URL"), reason="Requires an explicit local PostgreSQL test connection")
def test_existing_saved_views_render_exactly_as_before_and_the_row_count_is_unchanged(capsys):
    """CO-21."""
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    admin = create_engine(os.environ["DOSSIER_TEST_DATABASE_URL"])
    schema = "lxc_" + uuid.uuid4().hex
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(os.environ["DOSSIER_TEST_DATABASE_URL"], connect_args={"options": f"-csearch_path={schema}"})
    try:
        spec = importlib.util.spec_from_file_location("m", BACKEND / "postgres/alembic/versions/20261101_timeline_view_instants.py")
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        with engine.begin() as connection:
            connection.execute(text(
                "CREATE TABLE timeline_view_events (id uuid PRIMARY KEY, view_id uuid NOT NULL, event_key varchar(512), "
                "sort_date varchar(10), sort_time varchar(5), position int NOT NULL DEFAULT 0, event_snapshot jsonb)"))
            views = [uuid.uuid4(), uuid.uuid4()]
            shape = [("2024-01-02", "99:99"), ("2024-01-02", "08:00"), ("2024-01-01", "23:59"), (None, "99:99"),
                     ("2024-01-02", "08:00"), ("2023-12-31", "00:00")]
            for v, view in enumerate(views):
                for n, (day, time) in enumerate(shape * 7):
                    connection.execute(text("INSERT INTO timeline_view_events VALUES (:i, :v, :k, :d, :t, :p, '{}')"),
                                       {"i": uuid.uuid4(), "v": view, "k": f"e{v}-{n}", "d": day, "t": time, "p": (n * 5) % 11})
            order = "SELECT view_id, event_key FROM timeline_view_events ORDER BY view_id, sort_date, sort_time, position"
            before = connection.execute(text(order)).all()
            with Operations.context(MigrationContext.configure(connection)):
                migration.upgrade()
            assert connection.execute(text(order)).all() == before and len(before) == 84
            counts = connection.execute(text(
                "SELECT count(sort_instant), count(*) FILTER (WHERE sort_zone = 'wall_clock') FROM timeline_view_events")).one()
            assert tuple(counts) == (56, 70)
            assert "before 84, after 84" in capsys.readouterr().out
            with Operations.context(MigrationContext.configure(connection)):
                migration.downgrade()
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()
