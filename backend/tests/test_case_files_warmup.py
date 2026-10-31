"""Each web worker loads the evidence-file copies of the cases with the most files once after start
(view_warmup.warm_case_files_once), so a worker's first statement open, review queue or activity request on a large
case does not pay for them (d5b330d1: 3.91 s cold, 0.07 s held)."""

from __future__ import annotations

import ast
import asyncio
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import postgres.session
from postgres.base import Base
from postgres.models.evidence import EvidenceFile, EvidenceFolder
from services import process_shutdown
from services.financial import source_lineage, view_warmup


@pytest.fixture()
def Session(monkeypatch):
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True, poolclass=StaticPool,
                           connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine, tables=[EvidenceFolder.__table__, EvidenceFile.__table__])
    factory = sessionmaker(bind=engine, future=True)
    monkeypatch.setattr(postgres.session, "_get_session_local", lambda: factory)
    yield factory
    engine.dispose()


def _cases(Session, sizes):
    ids = [uuid4() for _ in sizes]
    with Session() as db:
        for case_id, size in zip(ids, sizes):
            for n in range(size):
                db.add(EvidenceFile(id=uuid4(), case_id=case_id, original_filename=f"{n}.pdf",
                                    stored_path=f"/x/{n}.pdf", size=1, sha256="a" * 64, status="processed"))
        db.commit()
    return ids


def test_the_cases_with_the_most_files_that_fit_the_budget_are_loaded_largest_last(Session, monkeypatch):
    small, large, middle = _cases(Session, [1, 5, 3])
    loaded = []
    monkeypatch.setattr(source_lineage, "case_files", lambda db, case_id, ids=None: loaded.append(case_id) or {})
    monkeypatch.setattr(source_lineage, "CASE_FILES_KEPT_FILES", 8)

    assert view_warmup.warm_case_files() == [middle, large]
    # The largest is loaded last, so it is the most recently used copy and the last one dropped.
    assert loaded == [middle, large]

    loaded.clear()
    monkeypatch.setattr(source_lineage, "CASE_FILES_KEPT_FILES", 9)
    assert view_warmup.warm_case_files() == [small, middle, large]

    loaded.clear()
    monkeypatch.setattr(source_lineage, "CASE_FILES_KEPT_FILES", 6)
    # The middle case does not fit beside the largest; the smallest still does.
    assert view_warmup.warm_case_files() == [small, large]


def test_a_case_larger_than_the_budget_is_still_loaded(Session, monkeypatch):
    small, large = _cases(Session, [1, 5])
    monkeypatch.setattr(source_lineage, "case_files", lambda db, case_id, ids=None: {})
    monkeypatch.setattr(source_lineage, "CASE_FILES_KEPT_FILES", 2)
    assert view_warmup.warm_case_files() == [large]


def test_copies_are_dropped_by_file_count_not_case_count(monkeypatch):
    """With a 2-case limit a request on a third case dropped d5b330d1's 6,108 copies (live 31 Oct, 3.0-4.3 s to reload)."""
    from collections import OrderedDict
    monkeypatch.setattr(source_lineage, "_CASE_FILES", OrderedDict())
    monkeypatch.setattr(source_lineage, "CASE_FILES_KEPT_FILES", 10)
    kept = source_lineage._CASE_FILES
    for name, size in (("big", 6), ("a", 1), ("b", 1), ("c", 2)):
        kept[name] = {n: None for n in range(size)}
        source_lineage._drop_least_recent_cases()
    assert list(kept) == ["big", "a", "b", "c"]  # 10 files in four cases: all kept

    kept["d"] = {0: None}
    source_lineage._drop_least_recent_cases()
    assert list(kept) == ["a", "b", "c", "d"]  # over budget: the least recently used goes first

    kept["huge"] = {n: None for n in range(50)}
    source_lineage._drop_least_recent_cases()
    assert list(kept) == ["huge"]  # the most recent case is always kept


def test_the_warm_up_reads_through_case_files_in_a_worker_thread_and_never_raises(Session, monkeypatch):
    _cases(Session, [2])
    import threading
    main = threading.get_ident()
    threads = []
    monkeypatch.setattr(source_lineage, "case_files",
                        lambda db, case_id, ids=None: threads.append(threading.get_ident()) or {})
    asyncio.run(view_warmup.warm_case_files_once())
    assert threads and main not in threads

    def boom(db, case_id, ids=None):
        raise RuntimeError("database gone")
    monkeypatch.setattr(source_lineage, "case_files", boom)
    asyncio.run(view_warmup.warm_case_files_once())  # logged, not raised: a start never fails on it


def test_off_switch_and_shutdown_stop_it(Session, monkeypatch):
    _cases(Session, [1, 2])
    loaded = []
    monkeypatch.setattr(source_lineage, "case_files", lambda db, case_id, ids=None: loaded.append(case_id) or {})
    monkeypatch.setenv("FINANCIAL_CASE_FILES_WARMUP", "0")
    asyncio.run(view_warmup.warm_case_files_once())
    assert loaded == []

    monkeypatch.delenv("FINANCIAL_CASE_FILES_WARMUP")
    monkeypatch.setattr(process_shutdown.requested, "is_set", lambda: True)
    assert view_warmup.warm_case_files() == []
    assert loaded == []


def test_every_worker_starts_it_and_stops_it_at_shutdown():
    source = (Path(__file__).resolve().parents[1] / "main.py").read_text()
    tree = ast.parse(source)
    started = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
               and getattr(node.func, "attr", None) == "create_task"
               and node.args and isinstance(node.args[0], ast.Call)
               and getattr(node.args[0].func, "id", None) == "warm_case_files_once"]
    assert len(started) == 1
    assert "case_files_task," in source.split("stop_background_tasks(", 1)[1].split(")", 1)[0]


def test_case_files_applies_the_budget_when_it_stores_a_case(Session, monkeypatch):
    """Through case_files itself, with a stand-in row version (SQLite has no xmin)."""
    from collections import OrderedDict
    from sqlalchemy import String, cast
    big, a, b, c = _cases(Session, [5, 2, 2, 1])
    monkeypatch.setattr(source_lineage, "_CASE_FILES", OrderedDict())
    monkeypatch.setattr(source_lineage, "_row_version", lambda session: cast(EvidenceFile.status, String))
    monkeypatch.setattr(source_lineage, "CASE_FILES_KEPT_FILES", 9)
    with Session() as db:
        for case_id, size in ((big, 5), (a, 2), (b, 2)):
            assert len(source_lineage.case_files(db, case_id)) == size
        # Three cases, 9 files: all kept (a 2-case limit dropped the largest here).
        assert list(source_lineage._CASE_FILES) == [str(big), str(a), str(b)]
        source_lineage.case_files(db, c)
    # 10 files: the least recently used case goes.
    assert list(source_lineage._CASE_FILES) == [str(a), str(b), str(c)]
