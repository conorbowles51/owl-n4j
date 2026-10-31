"""The router-wide access dependencies run on every Graph, Financial and Evidence request. They are async (they read
the JSON body), so their database checks must run in the thread pool: on the event loop they stall every other
request in the worker."""

from __future__ import annotations

import asyncio
import threading
from types import SimpleNamespace
from uuid import uuid4

from starlette.requests import Request


def _request(method="GET", path="/api/x", path_params=None, query=b""):
    scope = {"type": "http", "method": method, "path": path, "headers": [], "query_string": query,
             "path_params": path_params or {}}
    return Request(scope)


def _run_recording_threads(coro_factory):
    loop_threads = []

    async def main():
        loop_threads.append(threading.current_thread())
        await coro_factory()

    asyncio.run(main())
    return loop_threads[0]


def test_case_access_dependency_checks_the_case_in_the_thread_pool(monkeypatch):
    from routers import case_access

    seen = []
    monkeypatch.setattr(case_access, "authorize_case",
                        lambda db, case_id, user, permission: seen.append((threading.current_thread(), case_id)))
    dependency = case_access.case_access_dependency(lambda request, payload: ("case", "view"))
    case_id = str(uuid4())
    loop_thread = _run_recording_threads(
        lambda: dependency(_request(query=f"case_id={case_id}".encode()), db=object(), current_user=object()))
    assert [c for _, c in seen] == [case_id]
    assert seen[0][0] is not loop_thread


def test_evidence_object_access_checks_records_in_the_thread_pool(monkeypatch):
    from routers import evidence

    case_id = uuid4()
    seen = []
    monkeypatch.setattr(evidence, "_evidence_record_for_id",
                        lambda db, evidence_id: seen.append(threading.current_thread()) or SimpleNamespace(case_id=case_id))
    monkeypatch.setattr(evidence.EvidenceDBStorage, "find_by_engine_job_id",
                        lambda db, job_id: seen.append(threading.current_thread()) or SimpleNamespace(case_id=case_id))
    monkeypatch.setattr(evidence, "authorize_case",
                        lambda db, case, user, permission: seen.append(threading.current_thread()))

    loop_thread = _run_recording_threads(lambda: evidence._require_evidence_object_access(
        _request(path="/api/evidence/engine/jobs/j1", path_params={"evidence_id": "e1", "job_id": "j1"}),
        current_user=object(), db=object()))
    assert len(seen) == 4
    assert all(thread is not loop_thread for thread in seen)


def test_evidence_object_access_still_refuses_unknown_records(monkeypatch):
    import pytest
    from fastapi import HTTPException
    from routers import evidence

    monkeypatch.setattr(evidence, "_evidence_record_for_id", lambda db, evidence_id: None)
    with pytest.raises(HTTPException) as refused:
        asyncio.run(evidence._require_evidence_object_access(
            _request(path="/api/evidence/e1", path_params={"evidence_id": "e1"}), current_user=object(), db=object()))
    assert refused.value.status_code == 404


def test_an_unknown_engine_job_is_refused_without_evidence_ids(monkeypatch):
    import pytest
    from fastapi import HTTPException
    from routers import evidence

    monkeypatch.setattr(evidence.EvidenceDBStorage, "find_by_engine_job_id", lambda db, job_id: None)
    with pytest.raises(HTTPException) as refused:
        asyncio.run(evidence._require_evidence_object_access(
            _request(path="/api/evidence/engine/jobs/j9", path_params={"job_id": "j9"}), current_user=object(), db=object()))
    assert (refused.value.status_code, refused.value.detail) == (404, "Evidence job not found")


def test_a_poll_waiting_on_another_poll_of_the_case_gives_up_after_the_wait(monkeypatch):
    from services import evidence_job_sync

    monkeypatch.setattr(evidence_job_sync, "POLL_WAIT_SECONDS", 0.05)
    monkeypatch.setattr(evidence_job_sync, "_reconcile", lambda db, jobs: (_ for _ in ()).throw(AssertionError("ran")))
    lock = evidence_job_sync._poll_locks.setdefault("held-case", threading.Lock())
    lock.acquire()
    try:
        assert evidence_job_sync.reconcile_case_poll(SimpleNamespace(), "held-case", []) == 0
    finally:
        lock.release()
