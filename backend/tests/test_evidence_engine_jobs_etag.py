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
    assert new.headers["etag"].startswith('"') and new.headers["cache-control"] == "private, no-cache"


def test_an_unchanged_list_is_answered_304_and_a_changed_one_in_full():
    client, current = _client()
    etag = client.get("/now").headers["etag"]
    again = client.get("/now", headers={"If-None-Match": etag})
    assert again.status_code == 304 and again.content == b"" and again.headers["etag"] == etag
    assert client.get("/now", headers={"If-None-Match": f'"other", {etag}'}).status_code == 304
    current["jobs"] = JOBS[:-1] + [{**JOBS[-1], "status": "failed"}]
    changed = client.get("/now", headers={"If-None-Match": etag})
    assert changed.status_code == 200 and changed.headers["etag"] != etag
    assert changed.json()[-1]["status"] == "failed"
