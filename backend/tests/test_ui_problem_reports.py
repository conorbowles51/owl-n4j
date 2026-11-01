"""Report a problem (07 section 9): structured fields, text in the database only, nothing of the case to jobs.

Pins: only listed screens, actions, scope kinds and id-shaped values are accepted; the line to jobs holds ids,
kinds, counts and the build id only, never the typed text or a case value; the route enforces case access.
"""
import json
import uuid
from types import SimpleNamespace
from unittest import TestCase

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from services import ui_problem_reports as reports

CASE_MATERIAL = ['Jordan Avery', '+12025550143', 'meet at the dock at 9', '12 Harbour Road', '40.7128,-74.0060',
                 'EXH-0042', 'jordan@example.com']
GOOD = dict(screen='conversations', action_kind='filtering', refresh_changes='no', build_id='a1b2c3d4e5f6',
            last_request_id='5f0c9a7e-1b2c-4d3e-8f90-1234567890ab', scope={'messages': 2140, 'phones': 3, 'selected': 0},
            components=['scope-bar', 'phone-table'], viewport_w=1440, viewport_h=900,
            expected='I expected the meet at the dock at 9 message from Jordan Avery +12025550143 to show.')


class Fields(TestCase):
    def test_good_report_is_kept_whole(self):
        out = reports.clean(GOOD)
        self.assertEqual(out['scope'], GOOD['scope'])
        self.assertEqual(out['expected'], GOOD['expected'])

    def test_case_material_is_refused_in_every_structured_field(self):
        for field in ('screen', 'action_kind', 'refresh_changes', 'build_id', 'last_request_id'):
            for value in CASE_MATERIAL:
                with self.assertRaises(reports.Refused, msg=f'{field}={value}'):
                    reports.clean({**GOOD, field: value})
        for value in CASE_MATERIAL:
            with self.assertRaises(reports.Refused):
                reports.clean({**GOOD, 'components': [value]})
            with self.assertRaises(reports.Refused):
                reports.clean({**GOOD, 'scope': {value: 1}})
            with self.assertRaises(reports.Refused):
                reports.clean({**GOOD, 'scope': {'messages': value}})

    def test_long_text_is_refused_not_cut(self):
        with self.assertRaises(reports.Refused):
            reports.clean({**GOOD, 'expected': 'x' * (reports.MAX_EXPECTED + 1)})
        self.assertIsNone(reports.clean({**GOOD, 'expected': '   '})['expected'])


class Stored(TestCase):
    def setUp(self):
        from postgres.models.ui_problem_report import UiProblemReport
        from sqlalchemy import Column, MetaData, Table
        from sqlalchemy.dialects.postgresql import UUID
        self.engine = create_engine('sqlite://')
        # The cases table only as the foreign key's target.
        Table('cases', UiProblemReport.metadata, extend_existing=True)
        UiProblemReport.__table__.create(self.engine, checkfirst=True) if False else None
        meta = MetaData()
        Table('cases', meta, Column('id', UUID(as_uuid=True), primary_key=True))
        meta.create_all(self.engine)
        UiProblemReport.__table__.create(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.case = uuid.uuid4()

    def tearDown(self):
        self.db.close()

    def test_a_report_stores_a_row_and_the_jobs_line_holds_no_case_value(self):
        user = SimpleNamespace(id=uuid.uuid4(), email='investigator@example.org')
        row = reports.create(self.db, case_id=self.case, user=user, body=GOOD)
        self.assertEqual(row.expected, GOOD['expected'])  # kept in the database
        self.assertFalse(row.is_test)
        line = reports.jobs_line(row)
        self.assertEqual(tuple(line), reports.JOBS_KEYS)
        self.assertTrue(line['has_text'])
        message = reports.jobs_message(row)
        for text in (json.dumps(line), message):
            for value in CASE_MATERIAL + [GOOD['expected']]:
                self.assertNotIn(value, text)
            for word in GOOD['expected'].split():
                if len(word) > 3 and word not in ('message',):
                    self.assertNotIn(word, text)
        self.assertEqual([r.id for r in reports.undelivered(self.db)], [row.id])

    def test_jobs_login_and_verification_case_reports_are_test_and_not_delivered(self):
        jobs = SimpleNamespace(id=uuid.uuid4(), email='jobs-verify@loupe.invalid')
        row = reports.create(self.db, case_id=self.case, user=jobs, body=GOOD)
        self.assertTrue(row.is_test)
        self.assertEqual(reports.undelivered(self.db), [])
        self.assertEqual(len(reports.undelivered(self.db, include_test=True)), 1)
        self.assertTrue(reports.jobs_line(row)['test'])


class Route(TestCase):
    def test_access_is_checked_before_anything_is_stored(self):
        from fastapi import HTTPException
        from routers import ui_problem_reports as route
        from services.case_service import CaseAccessDenied

        calls = []

        def denied(db, case_id, user, *a):
            raise CaseAccessDenied('no')
        original = route.check_case_access
        route.check_case_access = denied
        original_create = reports.create
        reports.create = lambda *a, **k: calls.append(1)
        try:
            with self.assertRaises(HTTPException) as ctx:
                route.file_report(uuid.uuid4(), GOOD, user=SimpleNamespace(id=uuid.uuid4(), email='x@example.org'), db=None)
            self.assertEqual(ctx.exception.status_code, 403)
            with self.assertRaises(HTTPException) as ctx:
                route.list_reports(uuid.uuid4(), user=SimpleNamespace(id=uuid.uuid4(), email='x@example.org'), db=None)
            self.assertEqual(ctx.exception.status_code, 403)
            self.assertEqual(calls, [])
        finally:
            route.check_case_access = original
            reports.create = original_create
