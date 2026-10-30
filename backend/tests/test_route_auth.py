"""Every API route needs a signed-in person unless it is on the explicit public list below.

The processing-profile routes were reachable from the internet with no sign-in (list, read, save and delete).
The sweep walks the real application's route table, including routes added by include_router, so a new route
without a sign-in dependency fails here until it is either given one or added to PUBLIC with its reason.
"""

import types
import unittest

from fastapi import FastAPI
from fastapi.routing import APIRoute, APIWebSocketRoute
from fastapi.testclient import TestClient

from postgres.models.user import GlobalRole
from postgres.session import get_db
from routers import auth, profiles, users

# (method, path) -> why it is reachable without signing in.
PUBLIC = {
    ("POST", "/api/auth/login"): "signing in",
    ("POST", "/api/auth/logout"): "signing out; reads the token only to name the person in the activity trail",
    ("GET", "/api/setup/status"): "the first-run screen asks whether any user exists",
    ("POST", "/api/setup/initial-user"): "first-run only: refused with 403 once any user exists",
    ("WS", "/api/evidence/ws/jobs/{job_id}"): "checks the sign-in cookie and case access inside the handler "
                                              "(tests/test_evidence_ws_auth.py)",
    ("GET", "/"): "health check; the public port proxies only /api, and the API port (8002) times out from the public address",
    ("GET", "/health"): "deploy readiness check; the public port proxies only /api, and the API port (8002) times out from the public address",
}

# FastAPI's own schema pages; served by the API process only, not proxied on the public port.
FRAMEWORK_PATHS = {"/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"}


def _calls(dependant):
    for dep in dependant.dependencies:
        if dep.call is not None:
            yield dep.call
        yield from _calls(dep)


def _open_routes(app):
    found = set()
    for route in app.routes:
        if isinstance(route, APIWebSocketRoute):
            methods = ["WS"]
        elif isinstance(route, APIRoute):
            methods = sorted(route.methods)
        else:
            continue
        if auth.get_current_user in set(_calls(route.dependant)):
            continue
        for method in methods:
            found.add((method, route.path))
    return found


class AppRouteSweepTests(unittest.TestCase):
    def test_every_route_needs_sign_in_or_is_listed_public(self):
        from main import app

        open_routes = _open_routes(app)
        unlisted = sorted(open_routes - set(PUBLIC))
        self.assertEqual(unlisted, [], "routes reachable without signing in and not on the public list")

    def test_public_list_has_no_stale_entries(self):
        from main import app

        stale = sorted(set(PUBLIC) - _open_routes(app))
        self.assertEqual(stale, [], "listed public but no longer open (remove from PUBLIC)")

    def test_framework_pages_are_the_only_non_api_routes(self):
        from main import app

        other = {r.path for r in app.routes if not isinstance(r, (APIRoute, APIWebSocketRoute))}
        self.assertEqual(other - FRAMEWORK_PATHS, set())


class ProfilesRouteAuthTests(unittest.TestCase):
    def setUp(self):
        self.saved = []
        self.deleted = []
        stored = types.SimpleNamespace(
            name="standard", description="d", context_instructions="c", mandatory_instructions=[],
            special_entity_types=[], chat_config=None, llm_config=None, folder_processing=None,
        )

        def save(db, **kw):
            self.saved.append(kw["name"])
            return stored

        def delete(db, name):
            self.deleted.append(name)
            return True

        patches = {
            "list_processing_profiles": lambda db: [stored],
            "get_processing_profile": lambda db, name: stored,
            "save_processing_profile": save,
            "delete_processing_profile": delete,
        }
        self._orig = {name: getattr(profiles, name) for name in patches}
        for name, fn in patches.items():
            setattr(profiles, name, fn)

        db = types.SimpleNamespace(commit=lambda: None, refresh=lambda obj: None)
        self.app = FastAPI()
        self.app.include_router(profiles.router)
        self.app.dependency_overrides[get_db] = lambda: db
        self.client = TestClient(self.app)

    def tearDown(self):
        for name, fn in self._orig.items():
            setattr(profiles, name, fn)

    def _sign_in(self, role):
        person = types.SimpleNamespace(email="p@example.com", global_role=role, is_active=True)
        self.app.dependency_overrides[auth.get_current_user] = lambda: {"username": person.email}
        self.app.dependency_overrides[users.get_current_db_user] = lambda: person

    def test_signed_out_requests_are_refused(self):
        body = {"name": "standard"}
        for method, path, kw in [
            ("GET", "/api/profiles", {}),
            ("GET", "/api/profiles/standard", {}),
            ("POST", "/api/profiles", {"json": body}),
            ("DELETE", "/api/profiles/standard", {}),
        ]:
            with self.subTest(method=method, path=path):
                response = self.client.request(method, path, **kw)
                self.assertEqual(response.status_code, 401)
        self.assertEqual(self.saved, [])
        self.assertEqual(self.deleted, [])

    def test_signed_in_person_can_read(self):
        self._sign_in(GlobalRole.user)
        self.assertEqual(self.client.get("/api/profiles").status_code, 200)
        self.assertEqual(self.client.get("/api/profiles/standard").json()["name"], "standard")

    def test_changes_need_an_administrator(self):
        self._sign_in(GlobalRole.user)
        self.assertEqual(self.client.post("/api/profiles", json={"name": "standard"}).status_code, 403)
        self.assertEqual(self.client.delete("/api/profiles/standard").status_code, 403)
        self.assertEqual((self.saved, self.deleted), ([], []))

        self._sign_in(GlobalRole.admin)
        self.assertEqual(self.client.post("/api/profiles", json={"name": "standard"}).status_code, 200)
        self.assertEqual(self.client.delete("/api/profiles/standard").status_code, 200)
        self.assertEqual((self.saved, self.deleted), (["standard"], ["standard"]))


if __name__ == "__main__":
    unittest.main()
