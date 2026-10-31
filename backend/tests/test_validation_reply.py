"""A 422 reply never echoes a submitted value.

A sign-in sent with a wrong field name ("email" instead of "username") got FastAPI's default 422 reply, whose
"input" item is the whole submitted body, so the password came back in the reply and into a job's transcript.
"""

import json
import unittest

from fastapi.testclient import TestClient

import main
from postgres.session import get_db

SECRET = "not-a-real-password-7Qx!"


class ValidationReplyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        def no_db():
            yield None  # validation fails before a handler could use it
        main.app.dependency_overrides[get_db] = no_db
        cls.client = TestClient(main.app)  # no lifespan: nothing below reaches a database

    @classmethod
    def tearDownClass(cls):
        main.app.dependency_overrides.pop(get_db, None)

    def _assert_clean_422(self, reply, missing_field):
        self.assertEqual(reply.status_code, 422, reply.text)
        self.assertNotIn(SECRET, reply.text)
        detail = reply.json()["detail"]
        self.assertTrue(detail)
        for error in detail:
            self.assertNotIn("input", error)
            self.assertEqual(set(error) - {"type", "loc", "msg"}, set())
        self.assertIn(["body", missing_field], [e["loc"] for e in detail])

    def test_login_with_wrong_field_name_does_not_echo_password(self):
        reply = self.client.post("/api/auth/login", json={"email": "someone@example.invalid", "password": SECRET})
        self._assert_clean_422(reply, "username")

    def test_login_with_password_of_wrong_type_does_not_echo_it(self):
        reply = self.client.post("/api/auth/login", json={"username": "someone@example.invalid", "password": [SECRET]})
        self.assertEqual(reply.status_code, 422)
        self.assertNotIn(SECRET, reply.text)

    def test_change_password_missing_field_does_not_echo_new_password(self):
        from routers.auth import get_current_user
        main.app.dependency_overrides[get_current_user] = lambda: {"username": "someone@example.invalid"}
        try:
            reply = self.client.put("/api/auth/change-password", json={"old_password": "x", "new_password": SECRET})
        finally:
            main.app.dependency_overrides.pop(get_current_user, None)
        self._assert_clean_422(reply, "current_password")

    def test_reply_still_names_the_problem(self):
        reply = self.client.post("/api/auth/login", content=json.dumps({"password": SECRET}),
                                 headers={"content-type": "application/json"})
        error = next(e for e in reply.json()["detail"] if e["loc"] == ["body", "username"])
        self.assertEqual(error["type"], "missing")
        self.assertEqual(error["msg"], "Field required")


class WebSocketValidationReplyTests(unittest.TestCase):
    def test_websocket_close_reason_does_not_echo_submitted_value(self):
        from fastapi import FastAPI, WebSocket
        from starlette.websockets import WebSocketDisconnect
        from services.validation_reply import install

        app = FastAPI()
        install(app)

        @app.websocket("/ws")
        async def ws(websocket: WebSocket, n: int):
            await websocket.accept()

        with self.assertRaises(WebSocketDisconnect) as closed:
            with TestClient(app).websocket_connect("/ws?n=" + SECRET):
                pass
        self.assertEqual(closed.exception.code, 1008)
        self.assertNotIn(SECRET, closed.exception.reason or "")
        self.assertIn("int_parsing", closed.exception.reason)


if __name__ == "__main__":
    unittest.main()
