from datetime import date
from uuid import UUID, uuid4
from unittest import TestCase
from unittest.mock import patch
from sqlalchemy import select
from postgres.base import Base
from postgres.models.financial import FinancialTransaction
from postgres.models.timeline_entry import TimelineEntry
from postgres.models.workspace_entry import WorkspaceEntry, WorkspaceEntryLink
from services.timeline_entries import TimelineAddition, preview_addition, save_addition, list_entries


class TimelineEntryTests(TestCase):
    def setUp(self):
        from tests.test_financial_statement_import import StatementImportTests
        self.f = StatementImportTests(); self.f.setUp(); self.f.confirm()
        self.db = self.f.db; self.case = self.f.case.id
        Base.metadata.create_all(self.db.get_bind(), tables=[TimelineEntry.__table__, WorkspaceEntry.__table__, WorkspaceEntryLink.__table__])
        self.rows = list(self.db.scalars(select(FinancialTransaction).where(FinancialTransaction.case_id == self.case)))

    def tearDown(self): self.f.tearDown()

    def save(self, request):
        preview = preview_addition(self.db, case_id=self.case, request=request)
        request.expected_revision = preview['revision']
        return save_addition(self.db, case_id=self.case, request=request, actor=self.f.user.email)

    def payment_request(self, rows=None):
        return TimelineAddition(source_kind='transaction', source_ids=[row.id for row in (rows or self.rows)])

    def finding(self, observation=False):
        entry = WorkspaceEntry(id=uuid4(), case_id=self.case, entry_type='note', title='Large transfer needs explanation',
            body='The original invoice should be compared with this transfer.',
            tags=['financial', 'financial-workspace', 'financial-question' if observation else 'financial-observation'])
        self.db.add(entry); self.db.commit()
        return entry

    def test_bulk_preserves_exact_amount_currency_date_source_and_no_duplicates(self):
        result = self.save(self.payment_request())
        self.assertEqual(result['added'], len(self.rows))
        events = list_entries(self.db, case_id=self.case)
        self.assertEqual(len(events), len(self.rows))
        self.assertTrue(all(event['source']['id'] in [str(row.id) for row in self.rows] for event in events))
        self.assertTrue(all('EUR' in event['amount'] and event['source_references'] for event in events))
        self.assertTrue(all(event['time'] is None for event in events))
        again = self.save(self.payment_request())
        self.assertEqual(again['added'], 0)
        self.assertEqual(again['already_added'], len(self.rows))
        self.assertEqual(set(result['event_keys']), set(again['event_keys']))

    def test_statement_ordering_placeholder_is_not_an_event_date(self):
        row = self.rows[0]
        row.provenance = {**row.provenance, 'date_basis': 'statement_end_ordering_only'}
        self.db.commit()
        preview = preview_addition(self.db, case_id=self.case, request=self.payment_request())
        self.assertEqual(preview['undated'], 1)
        result = self.save(self.payment_request())
        self.assertEqual(result['added'], len(self.rows) - 1)

    def test_corrected_payment_updates_existing_event_and_readding_is_idempotent(self):
        row = self.rows[0]
        result = self.save(self.payment_request([row]))
        from services.financial.payment_edits import PaymentEditRequest, preview_payment_edits, save_payment_edits
        from services.financial.transaction_query import to_view
        from postgres.models.financial_category import FinancialCategory
        FinancialCategory.__table__.create(self.db.get_bind(), checkfirst=True)
        request = PaymentEditRequest(transactions=[dict(id=row.id, version=to_view(row).label_version)], changes={'amount': '123.45', 'transaction_date': '2021-02-19'})
        request.expected_revision = preview_payment_edits(self.db, case_id=self.case, request=request)['revision']
        updated = save_payment_edits(self.db, case_id=self.case, request=request, actor=self.f.actor)
        replacement = self.db.get(FinancialTransaction, UUID(updated['replacements'][0]['id']))
        event = list_entries(self.db, case_id=self.case)[0]
        self.assertEqual(event['key'], result['event_keys'][0])
        self.assertEqual(event['date'], '2021-02-19')
        self.assertIn('123.45 EUR', event['amount'])
        self.assertEqual(event['source']['id'], str(replacement.id))
        self.assertEqual(self.save(self.payment_request([replacement]))['already_added'], 1)

    def test_removed_import_keeps_labelled_snapshot_and_does_not_reactivate_payment(self):
        row = self.rows[0]
        self.save(self.payment_request([row]))
        row.ledger_status = 'rejected'; self.db.commit()
        event = list_entries(self.db, case_id=self.case)[0]
        self.assertEqual(event['source']['state'], 'snapshot')
        self.assertIn('removed', event['summary'])
        self.assertEqual(row.ledger_status, 'rejected')

    def test_findings_and_observations_require_event_date_preserve_kind_and_current_edits(self):
        for observation in [False, True]:
            entry = self.finding(observation)
            request = TimelineAddition(source_kind='workspace_entry', source_ids=[entry.id])
            with self.assertRaisesRegex(ValueError, 'event date'):
                preview_addition(self.db, case_id=self.case, request=request)
            request.event_date = date(2021, 2, 8)
            result = self.save(request)
            entry.title = 'Reviewed explanation'; self.db.commit()
            event = list_entries(self.db, case_id=self.case, event_keys=result['event_keys'])[0]
            self.assertEqual(event['type'], 'Observation' if observation else 'Finding')
            self.assertEqual(event['date'], '2021-02-08')
            self.assertEqual(event['name'], 'Reviewed explanation')
            request.event_date = date(2022, 3, 9)
            self.assertEqual(self.save(request)['added'], 0)
            self.assertEqual(list_entries(self.db, case_id=self.case, event_keys=result['event_keys'])[0]['date'], '2021-02-08')

    def test_stale_preview_and_foreign_case_cannot_add(self):
        request = self.payment_request()
        request.expected_revision = preview_addition(self.db, case_id=self.case, request=request)['revision']
        self.rows[0].description = 'Changed description'; self.db.commit()
        with self.assertRaisesRegex(ValueError, 'changed since review'):
            save_addition(self.db, case_id=self.case, request=request, actor=self.f.user.email)
        self.assertEqual(list_entries(self.db, case_id=self.case), [])
        with self.assertRaises(ValueError):
            preview_addition(self.db, case_id=uuid4(), request=request)
        entry = self.finding()
        with self.assertRaises(ValueError):
            preview_addition(self.db, case_id=uuid4(), request=TimelineAddition(source_kind='workspace_entry', source_ids=[entry.id], event_date=date(2021, 1, 1)))
        self.assertEqual(list_entries(self.db, case_id=uuid4()), [])

    def test_added_payments_and_findings_resolve_in_timeline_exports_and_saved_views(self):
        from services.timeline_view_service import _fetch_current_events, _event_snapshot
        payment = self.save(self.payment_request(self.rows[:1]))
        entry = self.finding()
        finding = self.save(TimelineAddition(source_kind='workspace_entry', source_ids=[entry.id], event_date=date(2021, 2, 8)))
        keys = payment['event_keys'] + finding['event_keys']
        with patch('services.timeline_view_service.neo4j_service.get_timeline_events_by_keys', return_value=[]) as graph:
            events = _fetch_current_events(self.db, self.case, keys)
            self.assertEqual(len(events), 2)
            self.assertEqual(graph.call_args.kwargs['event_keys'], [])
            self.assertTrue(all(_event_snapshot(event)['source'] for event in events))

    def test_http_preview_confirm_reopen_requires_edit_access(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from routers import timeline
        from services.case_service import CaseAccessDenied
        app = FastAPI(); app.include_router(timeline.router)
        app.dependency_overrides[timeline.get_db] = lambda: self.db
        app.dependency_overrides[timeline.get_current_db_user] = lambda: self.f.user
        body = {'source_kind': 'transaction', 'source_ids': [str(self.rows[0].id)]}
        with TestClient(app) as client, patch.object(timeline, 'check_case_access') as permission, patch.object(timeline, 'get_case_if_allowed'):
            url = f'/api/timeline/entries?case_id={self.case}'
            preview = client.post(url.replace('entries?', 'entries/preview?'), json=body)
            self.assertEqual(preview.status_code, 200)
            result = client.post(url, json={**body, 'expected_revision': preview.json()['revision']})
            self.assertEqual(result.status_code, 200)
            reopened = client.get(url)
            self.assertEqual(reopened.status_code, 200)
            self.assertEqual(reopened.json()['events'][0]['key'], result.json()['event_keys'][0])
            self.assertTrue(all(call.kwargs['required_permission'] == ('case', 'edit') for call in permission.call_args_list))
            permission.side_effect = CaseAccessDenied('Read-only case')
            self.assertEqual(client.post(url, json=body).status_code, 403)

    def test_actual_csv_export_and_saved_view_reopen_include_added_sources(self):
        from postgres.models.timeline_view import TimelineView, TimelineViewEvent
        from services.timeline_view_service import create_timeline_view, get_timeline_view, export_timeline
        Base.metadata.create_all(self.db.get_bind(), tables=[TimelineView.__table__, TimelineViewEvent.__table__])
        keys = self.save(self.payment_request())['event_keys']
        with patch('services.timeline_view_service.neo4j_service.get_timeline_events_by_keys', return_value=[]), patch('services.timeline_view_service.system_log_service.log'):
            view = create_timeline_view(self.db, case_id=self.case, current_user=self.f.user, title='Relevant transfers', event_keys=keys)
            reopened = get_timeline_view(self.db, case_id=self.case, view_id=UUID(view['id']))
            self.assertEqual(reopened['event_count'], len(keys))
            self.assertTrue(all(event['event_snapshot']['source']['kind'] == 'transaction' for event in reopened['events']))
            exported = export_timeline(self.db, case_id=self.case, case_name='Synthetic acceptance', current_user=self.f.user,
                export_format='csv', source='selection', event_keys=keys, fields={'source_references': True})
            text = exported.content.decode('utf-8-sig')
            self.assertIn('EUR', text)
            self.assertIn(self.rows[0].ref_id, text)
