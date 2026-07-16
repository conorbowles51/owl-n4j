from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from jose import jwt

from app.api.routes import files
from app.config import settings


class _ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class _MappingResult:
    def __init__(self, value):
        self.value = value

    def mappings(self):
        return self

    def one_or_none(self):
        return self.value


class _FakeRouteSession:
    def __init__(self, job):
        self.job = job

    async def execute(self, statement, params=None):
        return _ScalarResult(self.job)


class _NoQuerySession:
    async def execute(self, statement, params=None):
        pytest.fail("database query happened before case authorization")


class _FakeAuthSession:
    def __init__(self, *, user, case_exists=True, membership=None):
        self.user = user
        self.case_exists = case_exists
        self.membership = membership

    async def execute(self, statement, params=None):
        query = str(statement)
        if "FROM users" in query:
            return _MappingResult(self.user)
        if "FROM cases" in query:
            return _MappingResult({"id": params["case_id"]} if self.case_exists else None)
        if "FROM case_memberships" in query:
            return _MappingResult(self.membership)
        raise AssertionError(f"Unexpected query: {query}")


def _token(email="user@example.test"):
    return jwt.encode(
        {"sub": email},
        settings.auth_secret_key,
        algorithm=settings.auth_algorithm,
    )


@pytest.mark.asyncio
async def test_list_files_requires_case_view_before_job_query(monkeypatch):
    case_id = str(uuid4())

    async def current_user(db, token):
        return {"id": uuid4(), "global_role": "user", "is_active": True}

    async def deny_case_view(db, authorized_case_id, user):
        assert authorized_case_id == case_id
        raise HTTPException(status_code=403, detail="denied")

    monkeypatch.setattr(files, "_get_current_user_row", current_user)
    monkeypatch.setattr(files, "_require_case_view", deny_case_view)

    with pytest.raises(HTTPException) as exc:
        await files.list_files(
            case_id=case_id,
            token="token",
            db=_NoQuerySession(),
        )

    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_serve_file_requires_case_view_before_disk_lookup(monkeypatch):
    case_id = str(uuid4())
    job = SimpleNamespace(
        id=uuid4(),
        case_id=case_id,
        file_path="/tmp/should-not-be-read",
        file_name="secret.pdf",
        mime_type="application/pdf",
    )

    async def current_user(db, token):
        return {"id": uuid4(), "global_role": "user", "is_active": True}

    async def deny_case_view(db, authorized_case_id, user):
        assert authorized_case_id == case_id
        raise HTTPException(status_code=403, detail="denied")

    def fail_disk_lookup(path):
        pytest.fail("disk lookup happened before case authorization")

    monkeypatch.setattr(files, "_get_current_user_row", current_user)
    monkeypatch.setattr(files, "_require_case_view", deny_case_view)
    monkeypatch.setattr(files.os.path, "exists", fail_disk_lookup)

    with pytest.raises(HTTPException) as exc:
        await files.serve_file(
            case_id=case_id,
            job_id=str(job.id),
            token="token",
            db=_FakeRouteSession(job),
        )

    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_require_case_view_denies_non_member():
    user = {"id": uuid4(), "global_role": "user", "is_active": True}

    with pytest.raises(HTTPException) as exc:
        await files._require_case_view(
            _FakeAuthSession(user=user, membership=None),
            str(uuid4()),
            user,
        )

    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_get_current_user_and_require_case_view_allow_member():
    user_id = uuid4()
    user = {"id": user_id, "global_role": "user", "is_active": True}
    db = _FakeAuthSession(
        user=user,
        membership={"permissions": {"case": {"view": True}}},
    )

    current_user = await files._get_current_user_row(db, _token())
    await files._require_case_view(db, str(uuid4()), current_user)

    assert current_user["id"] == user_id
