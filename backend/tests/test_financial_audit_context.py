import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from postgres.audit_context import set_authorized_audit_context
from routers.case_access import authorize_case
from services.case_service import CaseAccessDenied, CaseNotFound


class AuthorizedAuditContextTests(unittest.TestCase):
    def test_attribution_is_bound_only_after_successful_case_authorization(self):
        db=MagicMock();case=uuid4();user=SimpleNamespace(id=uuid4(),name='Synthetic',email='test@example.invalid')
        with patch('routers.case_access.check_case_access') as access, patch('postgres.audit_context.set_authorized_audit_context') as record:
            self.assertEqual(authorize_case(db,case,user,('case','edit')),case)
            access.assert_called_once();record.assert_called_once_with(db,case_id=case,user=user)
        for error in (CaseAccessDenied('denied'),CaseNotFound('missing')):
            with patch('routers.case_access.check_case_access',side_effect=error),patch('postgres.audit_context.set_authorized_audit_context') as record:
                with self.assertRaises(HTTPException):authorize_case(db,case,user,('case','view'))
                record.assert_not_called()

    def test_sqlite_service_fixtures_do_not_issue_postgres_configuration(self):
        engine=create_engine('sqlite://')
        with Session(engine) as db:
            set_authorized_audit_context(db,case_id=uuid4(),user=object())
            self.assertFalse(db.info)
            self.assertFalse(db.in_transaction())
        engine.dispose()
