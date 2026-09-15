"""The financial UI receives exact case permissions, never a inferred editor role."""
import unittest
from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from postgres.session import get_db
from routers.financial_ledger import router
from routers.users import get_current_db_user
from tests.test_route_authorization import _CaseAccessDb


class FinancialCaseAccessTests(unittest.TestCase):
    def setUp(self):
        self.app = FastAPI()
        self.app.include_router(router)
        self.client = TestClient(self.app)
        self.user = SimpleNamespace(id=uuid4(), global_role='user', is_active=True)
        self.db = _CaseAccessDb()
        self.app.dependency_overrides[get_db] = lambda: self.db
        self.url = f'/api/financial/case-access?case_id={self.db.case.id}'

    def login(self):
        self.app.dependency_overrides[get_current_db_user] = lambda: self.user

    def test_authentication_and_case_membership_required(self):
        self.assertEqual(self.client.get(self.url).status_code, 401)
        self.login()
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.db.membership = SimpleNamespace(permissions={'case': {'edit': True}, 'evidence': {'upload': True}})
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_upload_and_edit_permissions_are_independent(self):
        self.login()
        for edit, upload in [(False, False), (True, False), (False, True), (True, True)]:
            with self.subTest(edit=edit, upload=upload):
                self.db.membership = SimpleNamespace(permissions={
                    'case': {'view': True, 'edit': edit}, 'evidence': {'upload': upload}})
                response = self.client.get(self.url)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json(), dict(case_id=str(self.db.case.id), user_id=str(self.user.id), can_edit=edit, can_upload=upload))

    def test_missing_flags_deny_writes_and_revocation_is_immediate(self):
        self.login()
        self.db.membership = SimpleNamespace(permissions={'case': {'view': True}})
        response = self.client.get(self.url)
        self.assertEqual(response.json()['can_edit'], False)
        self.assertEqual(response.json()['can_upload'], False)
        self.db.membership = None
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_super_admin_can_edit_and_upload_without_membership(self):
        self.login()
        self.user.global_role = 'super_admin'
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['can_edit'])
        self.assertTrue(response.json()['can_upload'])
