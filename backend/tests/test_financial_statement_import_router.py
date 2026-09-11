import unittest
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from routers import financial_statement_import as module
from postgres.session import get_db
from routers.users import get_current_db_user
from tests.test_route_authorization import _CaseAccessDb


class StatementImportAuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.app=FastAPI()
        self.app.include_router(module.router)
        self.client=TestClient(self.app)
        self.file_id=uuid4()
        self.db=_CaseAccessDb()

    def user(self,permissions):
        self.db.membership=SimpleNamespace(permissions=permissions) if permissions is not None else None
        self.app.dependency_overrides[get_db]=lambda:self.db
        self.app.dependency_overrides[get_current_db_user]=lambda:SimpleNamespace(id=uuid4(),global_role='user',is_active=True)

    def endpoint(self,suffix=''):
        return f'/api/financial/statement-import/{self.file_id}{suffix}?case_id={self.db.case.id}'

    def test_unauthenticated_requests_do_not_reach_statement_services(self):
        with patch.object(module,'read_statement_import') as read, patch.object(module,'confirm_statement_import') as write, patch.object(module,'create_statement_version') as version:
            self.assertEqual(self.client.get(self.endpoint()).status_code,401)
            self.assertEqual(self.client.post(self.endpoint('/confirm'),json={}).status_code,401)
            self.assertEqual(self.client.post(self.endpoint('/reprocess'),json={'request_id':str(uuid4())}).status_code,401)
        read.assert_not_called();write.assert_not_called();version.assert_not_called()

    def test_non_member_cannot_read_or_mutate(self):
        self.user(None)
        with patch.object(module,'read_statement_import') as read, patch.object(module,'confirm_statement_import') as write, patch.object(module,'create_statement_version') as version:
            self.assertEqual(self.client.get(self.endpoint()).status_code,403)
            self.assertEqual(self.client.post(self.endpoint('/confirm'),json={}).status_code,403)
            self.assertEqual(self.client.post(self.endpoint('/reprocess'),json={'request_id':str(uuid4())}).status_code,403)
        read.assert_not_called();write.assert_not_called();version.assert_not_called()

    def test_viewer_can_review_but_cannot_import_or_reprocess(self):
        self.user({'case':{'view':True,'edit':False},'evidence':{'upload':False}})
        with patch.object(module,'read_statement_import',return_value={'available':True}) as read, patch.object(module,'confirm_statement_import') as write, patch.object(module,'create_statement_version') as version:
            self.assertEqual(self.client.get(self.endpoint()).status_code,200)
            self.assertEqual(self.client.post(self.endpoint('/confirm'),json={}).status_code,403)
            self.assertEqual(self.client.post(self.endpoint('/reprocess'),json={'request_id':str(uuid4())}).status_code,403)
        self.assertEqual(read.call_args.kwargs['case_id'],self.db.case.id)
        write.assert_not_called();version.assert_not_called()

    def test_case_edit_does_not_grant_evidence_upload_permission(self):
        self.user({'case':{'view':True,'edit':True},'evidence':{'upload':False}})
        with patch.object(module,'create_statement_version') as version:
            self.assertEqual(self.client.post(self.endpoint('/reprocess'),json={'request_id':str(uuid4())}).status_code,403)
        version.assert_not_called()
