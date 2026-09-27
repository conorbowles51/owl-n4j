"""Transient database conflicts recover in bounded worker turns, without OCR."""
from unittest import TestCase
from unittest.mock import patch
from sqlalchemy.exc import OperationalError
from services.financial import import_batches as service
from tests.test_financial_import_batches import BatchImportTests


class DatabaseConflict(Exception):
    sqlstate = '40P01'


class PreparationConflictTests(TestCase):
    def setUp(self):
        self.fixture = BatchImportTests()
        self.fixture.setUp()

    def tearDown(self):
        self.fixture.tearDown()

    def test_deadlock_retries_retained_review_and_completes_once(self):
        batch = self.fixture.create()
        failure = OperationalError('synthetic update', {}, DatabaseConflict())
        with patch.object(service, '_review_file', side_effect=failure):
            self.fixture.advance(batch)
        state = self.fixture.status(batch)
        self.assertEqual(state['status'], 'preparing')
        self.assertEqual(state['files'][0]['status'], 'processing')
        self.assertNotIn('error', state['files'][0])
        with patch.object(service, 'prepare_existing_financial_file', side_effect=AssertionError('restarted reading')):
            self.fixture.advance(batch)
        state = self.fixture.status(batch)
        self.assertEqual(state['files'][0]['status'], 'checked')
        self.assertEqual(len(state['items']), 1)
        self.assertNotIn('preparation_retries', state['files'][0])

    def test_repeated_conflicts_stop_after_bounded_retries_with_recovery_message(self):
        batch = self.fixture.create()
        failure = OperationalError('synthetic update', {}, DatabaseConflict())
        with patch.object(service, '_review_file', side_effect=failure) as review:
            for _ in range(5):
                self.fixture.advance(batch)
        state = self.fixture.status(batch)
        self.assertEqual(review.call_count, 4)
        self.assertEqual(state['status'], 'review')
        self.assertEqual(state['files'][0]['status'], 'error')
        self.assertIn('Retry this file', state['files'][0]['error'])

    def test_validation_failure_is_not_retried_as_database_contention(self):
        batch = self.fixture.create()
        with patch.object(service, '_review_file', side_effect=service.PdfMappingError('Check currency.', 422)):
            self.fixture.advance(batch)
        state = self.fixture.status(batch)
        self.assertEqual(state['files'][0]['status'], 'error')
        self.assertEqual(state['files'][0]['error'], 'Check currency.')
