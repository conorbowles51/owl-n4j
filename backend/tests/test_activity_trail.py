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
from unittest.mock import Mock, patch
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


class CaseDeletionTests(TrailBase):
    """A deleted case leaves a row saying who deleted it, when, from where, and what it held (2026-11-03: a real
    case was deleted through the app and only the server journal showed it)."""

    def setUp(self):
        super().setUp()
        from postgres.models.case_membership import CaseMembership
        from postgres.models.enums import CaseMembershipRole
        from postgres.permissions import OWNER_PERMISSIONS
        Base.metadata.create_all(self.f.db.connection(), tables=[CaseMembership.__table__])
        self.f.db.add(CaseMembership(case_id=self.f.case.id, user_id=self.f.user.id,
                                     membership_role=CaseMembershipRole.owner, permissions=OWNER_PERMISSIONS,
                                     added_by_user_id=self.f.user.id))
        self.f.db.commit()

    def delete(self, graph=None):
        from postgres.models.case import Case
        from services import case_service
        from services.neo4j import neo4j_service
        graph = graph or Mock(return_value=dict(nodes_deleted=0, relationships_deleted=0))
        with self.f.SessionLocal() as db, patch.object(neo4j_service, 'delete_case_data', graph):
            user = db.merge(self.f.user)
            case_service.delete_case(db, self.f.case.id, user)
            self.assertIsNone(db.get(Case, self.f.case.id))
        return graph

    def test_deleting_a_case_removes_its_graph_after_the_rows_and_records_it(self):
        # followups m110323033215300: a deleted case's nodes stayed in Neo4j (7 deleted cases, 1,548 nodes live).
        from postgres.models.case import Case
        seen = []

        def graph(case_id):
            with self.f.SessionLocal() as other:
                seen.append(other.get(Case, self.f.case.id))  # the case's rows are already gone
            return dict(nodes_deleted=12, relationships_deleted=30)
        self.delete(Mock(side_effect=graph))
        self.assertEqual(seen, [None])
        [event] = self.events('case_graph_removed')
        self.assertEqual((event.case_id, event.details), (self.f.case.id,
                                                          dict(nodes_removed=12, relationships_removed=30)))

    def test_a_graph_that_cannot_be_reached_still_deletes_the_case_and_says_so(self):
        self.delete(Mock(side_effect=RuntimeError('graph down')))
        [event] = self.events('case_graph_removed')
        self.assertEqual(event.details, dict(graph_cleanup_error='graph down'))
        self.assertEqual(len(self.events('case_deleted')), 1)

    def test_deleting_a_case_records_who_when_and_what_it_held(self):
        title = self.f.case.title
        with self.f.SessionLocal() as db:
            files = db.query(EvidenceFile).filter(EvidenceFile.case_id == self.f.case.id).count()
        self.assertGreater(files, 0)
        self.delete()
        [event] = self.events('case_deleted')
        self.assertEqual((event.user_email, event.case_id, event.source_address, event.session_ref),
                         (self.f.user.email, self.f.case.id, '203.0.113.7', '0123456789abcdef'))
        self.assertEqual(event.details['case_title'], title)
        self.assertEqual(event.details['records_removed']['evidence_files'], files)
        self.assertEqual(event.details['records_removed']['case_memberships'], 1)
        self.assertIsNotNone(event.at)
        self.assertEqual(activity_trail.ACTIONS['case_deleted'], 'Deleted a case')

    def test_a_refused_delete_records_nothing(self):
        from services import case_service
        with self.f.SessionLocal() as db, patch.object(case_service, 'check_case_access',
                side_effect=case_service.CaseAccessDenied('no')):
            with self.assertRaises(case_service.CaseAccessDenied):
                case_service.delete_case(db, self.f.case.id, self.f.user)
        self.assertEqual(self.events('case_deleted'), [])


class DeletedItemsCaseDeletionTests(CaseDeletionTests):
    """Deleted items switched on (config.DELETED_ITEMS_ENABLED; off on live): the case moves to Deleted items, keeps
    its graph for a restore, and the 30-day purge removes the rows and then the graph. The off path (above, the
    delete as before) is what live runs."""

    def setUp(self):
        super().setUp()
        switch = patch('config.DELETED_ITEMS_ENABLED', True)
        switch.start()
        self.addCleanup(switch.stop)

    def delete(self, graph=None):
        from postgres.models.case import Case
        from services import case_service
        from services.neo4j import neo4j_service
        graph = graph or Mock(return_value=dict(nodes_deleted=0, relationships_deleted=0))
        with self.f.SessionLocal() as db, patch.object(neo4j_service, 'delete_case_data', graph):
            user = db.merge(self.f.user)
            case_service.delete_case(db, self.f.case.id, user)
        # In Deleted items: no read sees it, the row is kept for a restore (tests/test_casebin.py).
        with self.f.SessionLocal() as db:
            self.assertIsNone(db.get(Case, self.f.case.id))
        return graph

    def purge(self, graph):
        from services import case_service
        from services.neo4j import neo4j_service
        with self.f.SessionLocal() as db, patch.object(neo4j_service, 'delete_case_data', graph):
            return case_service.purge_case(db, self.f.case.id)

    def test_deleting_a_case_removes_its_graph_after_the_rows_and_records_it(self):
        # followups m110323033215300: a deleted case's nodes stayed in Neo4j (7 deleted cases, 1,548 nodes live).
        # In Deleted items the graph stays for a restore; the 30-day purge removes it once the rows are gone.
        from postgres.models.case import Case
        from postgres.soft_delete import showing_deleted
        graph = self.delete()
        graph.assert_not_called()
        self.assertEqual(self.events('case_graph_removed'), [])
        seen = []

        def remove(case_id):
            with self.f.SessionLocal() as other, showing_deleted(other):
                seen.append(other.get(Case, self.f.case.id))  # the case's rows are already gone
            return dict(nodes_deleted=12, relationships_deleted=30)
        details = self.purge(Mock(side_effect=remove))
        self.assertEqual(seen, [None])
        self.assertEqual((details['nodes_removed'], details['relationships_removed']), (12, 30))
        [event] = self.events('case_graph_removed')
        self.assertEqual((event.case_id, event.details), (self.f.case.id,
                                                          dict(nodes_removed=12, relationships_removed=30)))

    def test_a_graph_that_cannot_be_reached_still_deletes_the_case_and_says_so(self):
        self.delete()
        self.purge(Mock(side_effect=RuntimeError('graph down')))
        [event] = self.events('case_graph_removed')
        self.assertEqual(event.details, dict(graph_cleanup_error='graph down'))
        self.assertEqual((len(self.events('case_moved_to_deleted_items')), len(self.events('case_purged'))), (1, 1))
        self.assertEqual(self.events('case_deleted'), [])

    def test_deleting_a_case_records_who_when_and_what_it_held(self):
        title = self.f.case.title
        with self.f.SessionLocal() as db:
            files = db.query(EvidenceFile).filter_by(case_id=self.f.case.id).count()
        self.delete()
        [event] = self.events('case_moved_to_deleted_items')
        self.assertEqual((event.user_email, event.case_id, event.source_address, event.session_ref),
                         (self.f.user.email, self.f.case.id, '203.0.113.7', '0123456789abcdef'))
        self.assertEqual(event.details['case_title'], title)
        self.assertEqual(event.details['records_held']['evidence_files'], files)
        self.assertEqual(event.details['records_held']['case_memberships'], 1)
        self.assertIn('purge_after', event.details)
        self.assertEqual(activity_trail.ACTIONS['case_moved_to_deleted_items'], 'Moved a case to Deleted items')


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

    def test_many_files_read_each_event_once_and_keep_their_own_answers(self):
        # The lookup is indexed once per call, not rescanned per file: on d5b330d1 (6,108 files) the per-file scans
        # were 6.6 of 10.7 s of one call. Each file keeps the answer the per-file scan gave.
        sent = [self.register(f'sent-{n}.pdf', detect=False) for n in range(4)]
        plain = self.register('plain.pdf', detect=False)
        from routers.financial_statement_import import _record_send
        from services.financial import import_batches
        with self.f.SessionLocal() as db:
            batch_id = import_batches.create_batch(db, case_id=self.f.case.id, request_id=uuid4(), file_ids=sent,
                folder_ids=[], actor=self.f.actor)
            _record_send(db, case_id=self.f.case.id, user=self.f.user, how='batch', batch_id=batch_id, file_ids=sent)
        events = len(self.events())
        reads = []
        real = activity_trail._event_files
        with self.f.SessionLocal() as db, patch.object(activity_trail, '_event_files',
                                                       side_effect=lambda e: reads.append(e.id) or real(e)):
            shown = activity_trail.file_provenance(db, case_id=self.f.case.id, file_ids=[*sent, plain])
        self.assertLessEqual(len(reads), events)
        for file_id in sent:
            entry = shown[str(file_id)]
            self.assertEqual((entry['in_financial'], entry['added_by'], entry['recorded_by'], entry['batch_id'],
                              entry['uploaded_by'], entry['uploaded_from']),
                             (True, self.f.user.name, 'activity_trail', str(batch_id), self.f.user.name, '203.0.113.7'))
        self.assertEqual((shown[str(plain)]['in_financial'], shown[str(plain)]['added_by'],
                          shown[str(plain)]['uploaded_from']), (False, None, '203.0.113.7'))
