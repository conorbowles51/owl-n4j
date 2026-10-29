"""The activity trail: who did what, from where.

Pins: the browser address is believed from the local proxy only; the sign-in
token is never stored (only a 16-hex fingerprint); every Evidence registration
records its uploader, files and hashes in the same transaction; an automatic
Financial entry is recorded as System with its reason; a Send to Financial
names the person, address and screen; provenance shows only what was recorded
and never invents a person; recording never blocks the action.
"""
import asyncio
import hashlib
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch
from uuid import uuid4

from postgres.base import Base
from postgres.models.activity_event import ActivityEvent
from postgres.models.evidence import EvidenceFile
from postgres.models.financial_import_batches import FinancialImportBatch as Batch
from services import activity_trail
from tests import test_financial_auto_read as auto_read_tests
from tests.test_financial_auto_read import AutoReadBase


def scope(client, headers=(), path='/api/x'):
    return dict(type='http', client=(client, 5555), path=path,
                headers=[(k.encode(), v.encode()) for k, v in headers])


class SourceAddressTests(TestCase):
    def test_the_proxy_header_is_believed_only_from_loopback(self):
        self.assertEqual(activity_trail.context_from_scope(scope('127.0.0.1', [('x-real-ip', '203.0.113.7')]))['address'],
                         '203.0.113.7')
        # A browser reaching the backend directly cannot name another address.
        self.assertEqual(activity_trail.context_from_scope(scope('198.51.100.2', [('x-real-ip', '203.0.113.7'),
            ('x-forwarded-for', '203.0.113.8')]))['address'], '198.51.100.2')

    def test_a_spoofed_forwarded_chain_yields_the_address_the_proxy_appended(self):
        context = activity_trail.context_from_scope(scope('127.0.0.1', [('x-forwarded-for', '10.9.9.9, 203.0.113.7')]))
        self.assertEqual(context['address'], '203.0.113.7')
        self.assertEqual(activity_trail.client_address('127.0.0.1', {'x-real-ip': '::ffff:203.0.113.9'}), '203.0.113.9')
        self.assertEqual(activity_trail.client_address('127.0.0.1', {'x-real-ip': 'not-an-address'}), '127.0.0.1')

    def test_the_session_is_a_fingerprint_never_the_token(self):
        token = 'header.payload.signature'
        context = activity_trail.context_from_scope(scope('127.0.0.1', [('authorization', f'Bearer {token}'),
            ('user-agent', 'Mozilla/5.0 Test'), ('x-loupe-origin', 'evidence_toolbar')]))
        self.assertEqual(context['session_ref'], hashlib.sha256(token.encode()).hexdigest()[:16])
        self.assertNotIn(token, repr(context))
        self.assertEqual((context['user_agent'], context['origin']), ('Mozilla/5.0 Test', 'evidence_toolbar'))
        cookie = activity_trail.context_from_scope(scope('127.0.0.1', [('cookie', f'a=b; access_token={token}')]))
        self.assertEqual(cookie['session_ref'], context['session_ref'])

    def test_the_middleware_sets_the_context_for_the_request_only(self):
        seen = []

        async def app(scope_, receive, send):
            seen.append(activity_trail.current_context())
        middleware = activity_trail.ActivityContextMiddleware(app)
        asyncio.run(middleware(scope('127.0.0.1', [('x-real-ip', '203.0.113.7')]), None, None))
        self.assertEqual(seen[0]['address'], '203.0.113.7')
        self.assertIsNone(activity_trail.current_context())


class TrailBase(AutoReadBase):
    pdf = auto_read_tests.EvidenceProcessingTests.pdf
    register = auto_read_tests.EvidenceProcessingTests.register

    def setUp(self):
        super().setUp()
        Base.metadata.create_all(self.f.db.connection(), tables=[ActivityEvent.__table__])
        self.f.db.commit()
        self.request = activity_trail._context.set(dict(address='203.0.113.7', user_agent='Mozilla/5.0 Test',
            session_ref='0123456789abcdef', origin='evidence_toolbar', path='/api/financial/statement-import/batches'))

    def tearDown(self):
        activity_trail._context.reset(self.request)
        super().tearDown()

    def events(self, action=None):
        with self.f.SessionLocal() as db:
            rows = db.query(ActivityEvent).order_by(ActivityEvent.id)
            return [e for e in rows if action is None or e.action == action]


class RecordingTests(TrailBase):
    def test_an_upload_records_uploader_address_files_and_hashes_in_its_transaction(self):
        file_id = self.register('upload.pdf', detect=False)
        [event] = self.events('evidence_upload')
        self.assertEqual((event.user_email, event.source_address, event.case_id), (self.f.user.email, '203.0.113.7', self.f.case.id))
        [entry] = event.details['files']
        with self.f.SessionLocal() as db:
            sha = db.get(EvidenceFile, file_id).sha256
        self.assertEqual((entry['id'], entry['filename'], entry['sha256']), (str(file_id), 'upload.pdf', sha))

    def test_an_upload_that_is_rolled_back_leaves_no_event(self):
        from services.evidence_db_storage import EvidenceDBStorage
        with self.f.SessionLocal() as db:
            EvidenceDBStorage.add_files(db, case_id=self.f.case.id, created_by_id=self.f.user.id,
                files_data=[dict(original_filename='gone.pdf', stored_path='/x/gone.pdf', sha256='b' * 64, size=1)])
            db.rollback()
        self.assertEqual(self.events('evidence_upload'), [])

    def test_a_failure_to_record_never_blocks_the_action(self):
        with self.f.SessionLocal() as db, patch.object(activity_trail, 'build', side_effect=RuntimeError('boom')):
            self.assertFalse(activity_trail.record('logout', db=db))

    def test_a_detected_statement_is_added_by_system_with_its_reason(self):
        file_id = self.register('detected.pdf', detect=True)
        with patch('services.financial.auto_read.detect_enabled', return_value=True), \
                patch('services.financial.statement_detection.detect', return_value=dict(statement=True, reason='furniture')):
            from services.financial import auto_read
            auto_read.sweep(self.f.SessionLocal, Path)
        [event] = self.events('financial_auto_add')
        self.assertEqual((event.user_name, event.source_address, event.origin, event.details['reason']),
                         ('System', 'system', 'automatic', 'detected'))
        self.assertIsNone(event.user_agent)
        self.assertIn(str(file_id), {f['id'] for f in event.details['files']})
        with self.f.SessionLocal() as db:
            [shown] = activity_trail.file_provenance(db, case_id=self.f.case.id, file_ids=[file_id]).values()
        self.assertEqual((shown['in_financial'], shown['added_automatically'], shown['added_by'], shown['auto_reason']),
                         (True, True, None, 'statement detection'))
        self.assertEqual(shown['uploaded_by'], self.f.user.name)


class ProvenanceTests(TrailBase):
    def send(self, file_id):
        from routers.financial_statement_import import _record_send
        from services.financial import import_batches
        with self.f.SessionLocal() as db:
            batch_id = import_batches.create_batch(db, case_id=self.f.case.id, request_id=uuid4(), file_ids=[file_id],
                folder_ids=[], actor=self.f.actor)
            _record_send(db, case_id=self.f.case.id, user=self.f.user, how='batch', batch_id=batch_id, file_ids=[file_id])
        return batch_id

    def test_a_send_names_the_person_the_address_and_the_screen(self):
        batch_id = self.send(self.f.file.id)
        [event] = self.events('financial_send')
        self.assertEqual((event.user_name, event.source_address, event.origin, event.details['batch_id']),
                         (self.f.user.name, '203.0.113.7', 'evidence_toolbar', str(batch_id)))
        with self.f.SessionLocal() as db:
            shown = activity_trail.file_provenance(db, case_id=self.f.case.id, file_ids=[self.f.file.id])[str(self.f.file.id)]
            sources = activity_trail.batch_sources(db, case_id=self.f.case.id, batch_ids=[batch_id])
        self.assertEqual((shown['added_by'], shown['added_from'], shown['added_via'], shown['recorded_by']),
                         (self.f.user.name, '203.0.113.7', 'Evidence toolbar (Send to Financial)', 'activity_trail'))
        self.assertEqual(sources[str(batch_id)]['source_address'], '203.0.113.7')

    def test_an_earlier_send_shows_what_the_batch_recorded_and_no_address(self):
        from services.financial import import_batches
        with self.f.SessionLocal() as db:
            batch_id = import_batches.create_batch(db, case_id=self.f.case.id, request_id=uuid4(), file_ids=[self.f.file.id],
                folder_ids=[], actor=self.f.actor)
            shown = activity_trail.file_provenance(db, case_id=self.f.case.id, file_ids=[self.f.file.id])[str(self.f.file.id)]
            created = db.get(Batch, batch_id).created_at
        self.assertEqual((shown['added_by'], shown['added_from'], shown['recorded_by'], shown['batch_id']),
                         (self.f.user.name, None, 'batch', str(batch_id)))
        self.assertEqual(shown['added_at'], created.isoformat())

    def test_a_file_not_in_financial_names_nobody_as_adding_it(self):
        file_id = self.register('plain.pdf', detect=False)
        with self.f.SessionLocal() as db:
            shown = activity_trail.file_provenance(db, case_id=self.f.case.id, file_ids=[file_id])[str(file_id)]
        self.assertEqual((shown['in_financial'], shown['added_by'], shown['added_at']), (False, None, None))

    def test_the_admin_list_filters_by_case_person_and_action(self):
        self.send(self.f.file.id)
        with self.f.SessionLocal() as db:
            activity_trail.record('login_failure', db=db, user_email='someone@example.test')
            db.commit()
            sends = activity_trail.list_events(db, case_id=self.f.case.id, action='financial_send')
            mine = activity_trail.list_events(db, user=self.f.user.email.upper())
            failures = activity_trail.list_events(db, action=['login_failure'])
        self.assertEqual(sends['total'], 1)
        self.assertEqual({e['action'] for e in mine['events']}, {'financial_send'})
        self.assertEqual(failures['events'][0]['user_email'], 'someone@example.test')
        self.assertEqual(failures['events'][0]['source_address'], '203.0.113.7')
