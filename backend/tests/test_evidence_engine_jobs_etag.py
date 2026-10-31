"""The engine job list (3.15 MB on d5b330d1, polled every minute from an open Evidence page) carries an ETag:
an unchanged list is answered 304 with no body, and a 200 carries exactly the bytes FastAPI wrote before."""

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from routers.evidence import _jobs_answer
from services.json_gzip import JSONGZipMiddleware

JOBS = [{"id": f"job-{n}", "status": "completed", "file_name": "Résumé ✓.pdf", "progress": n / 3,
         "evidence_file_id": None} for n in range(400)]


def _client():
    app = FastAPI()
    app.add_middleware(JSONGZipMiddleware)
    current = {"jobs": JOBS}

    @app.get("/before")
    def before():  # what the route returned before: the list, encoded by FastAPI
        return current["jobs"]

    @app.get("/now")
    def now(request: Request):
        return _jobs_answer(current["jobs"], request.headers.get("if-none-match"))

    return TestClient(app), current


def test_a_200_carries_the_same_bytes_and_an_etag():
    client, _ = _client()
    old, new = client.get("/before"), client.get("/now")
    assert new.status_code == 200 and new.content == old.content
    assert new.headers["content-type"] == old.headers["content-type"]
    assert new.headers["content-encoding"] == "gzip"
    assert new.headers["etag"].startswith('W/"') and new.headers["cache-control"] == "private, no-cache"
    assert new.headers["vary"] == "Accept-Encoding"


def test_an_unchanged_list_is_answered_304_and_a_changed_one_in_full():
    client, current = _client()
    etag = client.get("/now").headers["etag"]
    again = client.get("/now", headers={"If-None-Match": etag})
    assert again.status_code == 304 and again.content == b"" and again.headers["etag"] == etag
    assert again.headers["vary"] == "Accept-Encoding"
    assert client.get("/now", headers={"If-None-Match": etag.removeprefix("W/")}).status_code == 304
    assert client.get("/now", headers={"If-None-Match": f'"other", {etag}'}).status_code == 304
    current["jobs"] = JOBS[:-1] + [{**JOBS[-1], "status": "failed"}]
    changed = client.get("/now", headers={"If-None-Match": etag})
    assert changed.status_code == 200 and changed.headers["etag"] != etag
    assert changed.json()[-1]["status"] == "failed"


def test_an_encoding_failure_is_an_error_not_an_empty_list(monkeypatch):
    # Only the engine's own failures answer []: a list that cannot be encoded must not look like "no jobs".
    import asyncio
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    import pytest
    from routers import evidence as router

    monkeypatch.setattr(router, "_check_engine_jobs_access", lambda *args: None)
    monkeypatch.setattr(router.evidence_engine_client, "list_jobs", AsyncMock(return_value=[{"id": "j"}]))
    monkeypatch.setattr(router, "_reconcile_and_link_engine_jobs", lambda db, case_id, jobs: jobs)

    def cannot_encode(jobs, if_none_match):
        raise ValueError("Out of range float values are not JSON compliant")
    monkeypatch.setattr(router, "_jobs_answer", cannot_encode)
    with pytest.raises(ValueError):
        asyncio.run(router.list_engine_jobs(SimpleNamespace(headers={}), case_id="c", current_user=None, db=None))
    monkeypatch.setattr(router.evidence_engine_client, "list_jobs", AsyncMock(side_effect=OSError("engine down")))
    assert asyncio.run(router.list_engine_jobs(SimpleNamespace(headers={}), case_id="c", current_user=None, db=None)) == []


def test_the_engine_list_is_not_walked_and_its_bytes_are_unchanged(monkeypatch):
    # The engine's list is plain JSON data; jsonable_encoder walked d5b330d1's for 0.19 s to hand back the same.
    import datetime
    import fastapi.encoders
    from fastapi.responses import JSONResponse
    from routers import evidence as router

    plain = [{"id": "j1", "status": "completed", "progress": 1.0, "files": [], "error": None, "evidence_file_id": "f"}]
    odd = [{"id": "j2", "at": datetime.datetime(2026, 10, 31, 9, 0)}]
    expected = {id(plain): JSONResponse(fastapi.encoders.jsonable_encoder(plain)).body,
                id(odd): JSONResponse(fastapi.encoders.jsonable_encoder(odd)).body}
    walked = []
    original = fastapi.encoders.jsonable_encoder
    monkeypatch.setattr(fastapi.encoders, "jsonable_encoder",
                        lambda value, *a, **k: walked.append(value) or original(value, *a, **k))
    assert router._jobs_answer(plain, None).body == expected[id(plain)]
    assert plain not in walked
    assert router._jobs_answer(odd, None).body == expected[id(odd)]
    assert odd in walked
