"""Corroborate's routes (lx-corroengine): the paths lx-corroselect calls, reads need case view and writes case edit,
and a question kind Corroborate does not ask is refused before anything is saved."""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers import corroborate
from routers.case_access import require_case_edit, require_case_view

CASE = "11111111-2222-3333-4444-555555555555"


def _deps(route):
    return {d.dependency for d in route.dependencies}


def test_routes_and_their_access():
    got = {(sorted(r.methods)[0], r.path): r for r in corroborate.router.routes}
    view = [("POST", "/api/cases/{case_id}/corroborate/preview"), ("GET", "/api/cases/{case_id}/corroborate/facts"),
            ("GET", "/api/cases/{case_id}/corroborate/watches"),
            ("GET", "/api/cases/{case_id}/corroborate/document-rows/{file_id}")]
    edit = [("POST", "/api/cases/{case_id}/corroborate/run"), ("POST", "/api/cases/{case_id}/corroborate/facts"),
            ("POST", "/api/cases/{case_id}/corroborate/facts/{fact_id}:withdraw"),
            ("POST", "/api/cases/{case_id}/corroborate/watches"),
            ("POST", "/api/cases/{case_id}/corroborate/watches/{watch_id}:stop")]
    for key in view:
        assert require_case_view in _deps(got[key]), key
    for key in edit:
        assert require_case_edit in _deps(got[key]), key


def test_an_unknown_question_kind_is_refused_before_saving(monkeypatch):
    app = FastAPI()
    app.include_router(corroborate.router)
    app.dependency_overrides[require_case_edit] = lambda: None
    app.dependency_overrides[corroborate.get_db] = lambda: None
    app.dependency_overrides[corroborate.get_current_db_user] = lambda: None
    saved = []
    monkeypatch.setattr(corroborate.runs, "save_group", lambda *a, **k: saved.append(k))
    res = TestClient(app).post(f"/api/cases/{CASE}/corroborate/run",
                               json={"members": [{"type": "record", "id": "x"}], "question": {"kind": "guess"}})
    assert res.status_code == 422 and "not one Corroborate asks" in res.json()["detail"]
    assert saved == []
