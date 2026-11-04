"""Opt-in real PostgreSQL: printable payment numbers (BACKLOG FEAT-006, migration 20261104_transaction_numbers).

The rule a printout depends on: a payment's number never changes and is never handed to another payment; a corrected
version keeps the number of the row it replaces; a new import only adds numbers after the last one; cases count
separately. The migration's own SQL runs here (backfill, then the trigger), against stand-in tables carrying the
columns it reads.
"""
import importlib.util
import json
import os
from datetime import date
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

pytestmark = pytest.mark.skipif(os.getenv("LOUPE_TEST_LOCAL_POSTGRES") != "1",
                                reason="Requires isolated local PostgreSQL")

MIGRATION = Path(__file__).resolve().parents[1] / "postgres/alembic/versions/20261104_transaction_numbers.py"


def _upgrade(conn):
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    spec = importlib.util.spec_from_file_location("transaction_numbers_migration", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with Operations.context(MigrationContext.configure(conn)):
        module.upgrade()


@pytest.fixture()
def engine():
    url = make_url(os.environ["LOUPE_TEST_LOCAL_POSTGRES_URL"])
    assert url.host in {"127.0.0.1", "localhost"}, "local PostgreSQL only"
    admin = create_engine(url, future=True)
    schema = f"txn_numbers_{uuid4().hex[:8]}"
    with admin.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(url, future=True, connect_args={"options": f"-csearch_path={schema}"})
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE cases (id uuid PRIMARY KEY)"))
        conn.execute(text("""CREATE TABLE financial_transactions (
            id uuid PRIMARY KEY, case_id uuid NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
            ordering_date date NOT NULL, row_index integer NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
            superseded_by_id uuid NULL, provenance jsonb NOT NULL DEFAULT '{}'::jsonb)"""))
    yield engine
    engine.dispose()
    with admin.begin() as conn:
        conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
    admin.dispose()


def _add(conn, case_id, day, index=0, previous=None):
    row_id = uuid4()
    provenance = {"correction": {"previous_transaction_id": str(previous), "version": 1}} if previous else {}
    conn.execute(text("INSERT INTO financial_transactions (id, case_id, ordering_date, row_index, provenance) "
                      "VALUES (:id, :case, :day, :index, CAST(:prov AS jsonb))"),
                 dict(id=row_id, case=case_id, day=day, index=index, prov=json.dumps(provenance)))
    return row_id


def _number(conn, row_id):
    return conn.execute(text("SELECT number FROM financial_transaction_numbers WHERE transaction_id = :id"),
                        dict(id=row_id)).scalar()


def test_existing_rows_are_numbered_by_date_and_a_correction_keeps_its_original_number(engine):
    case, other = uuid4(), uuid4()
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO cases (id) VALUES (:a), (:b)"), dict(a=case, b=other))
        march, january, february = (_add(conn, case, date(2024, 3, 1)), _add(conn, case, date(2024, 1, 5)),
                                    _add(conn, case, date(2024, 2, 9)))
        corrected = _add(conn, case, date(2024, 3, 1), previous=march)
        conn.execute(text("UPDATE financial_transactions SET superseded_by_id = :new WHERE id = :old"),
                     dict(new=corrected, old=march))
        elsewhere = _add(conn, other, date(2020, 1, 1))
        _upgrade(conn)
    with engine.begin() as conn:
        assert [_number(conn, r) for r in (january, february, march)] == [1, 2, 3]
        assert _number(conn, corrected) == 3
        assert _number(conn, elsewhere) == 1
        assert conn.execute(text("SELECT last_number FROM financial_transaction_number_counters WHERE case_id=:c"),
                            dict(c=case)).scalar() == 3


def test_new_rows_take_the_next_number_and_a_deleted_number_is_never_reused(engine):
    case = uuid4()
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO cases (id) VALUES (:a)"), dict(a=case))
        first = _add(conn, case, date(2024, 1, 1))
        _upgrade(conn)
    with engine.begin() as conn:
        # A later import of an earlier month is added after the last number: nothing is renumbered.
        earlier = _add(conn, case, date(2023, 6, 1))
        removed = _add(conn, case, date(2024, 2, 1))
        assert (_number(conn, first), _number(conn, earlier), _number(conn, removed)) == (1, 2, 3)
        conn.execute(text("DELETE FROM financial_transactions WHERE id = :id"), dict(id=removed))
        after_delete = _add(conn, case, date(2024, 2, 1))
        assert _number(conn, after_delete) == 4
        corrected = _add(conn, case, date(2023, 6, 1), previous=earlier)
        assert _number(conn, corrected) == 2
        assert _number(conn, first) == 1


def test_a_correction_naming_a_row_of_another_case_does_not_borrow_its_number(engine):
    case, other = uuid4(), uuid4()
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO cases (id) VALUES (:a), (:b)"), dict(a=case, b=other))
        _upgrade(conn)
    with engine.begin() as conn:
        for _ in range(5):
            foreign = _add(conn, other, date(2024, 1, 1))
        own = _add(conn, case, date(2024, 1, 1), previous=foreign)
        assert _number(conn, foreign) == 5
        assert _number(conn, own) == 1
