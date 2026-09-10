import hashlib
import tempfile
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from services.financial.correction_native import correction_native_controls
from services.financial.native import read_native
from tests.test_financial_native import WINDOW, camt_bytes, bai2_bytes, mt940_bytes, nacha_bytes, NACHA_SIMPLE


class SourceBoundNativeTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'source.xml'
        self.data = camt_bytes()
        self.path.write_bytes(self.data)
        sha = hashlib.sha256(self.data).hexdigest()
        self.document = SimpleNamespace(id=uuid.uuid4(), case_id=uuid.uuid4(),
            evidence_file_id=uuid.uuid4(), extraction_layer=0, currency='USD', sha256_at_ingestion=sha)
        native = read_native(self.data, window=WINDOW)
        self.rows = [SimpleNamespace(id=uuid.uuid4(), case_id=self.document.case_id,
            source_document_id=self.document.id, provenance={}, superseded_by_id=None,
            ledger_status='admitted', row_index=row.row_index, content_hash=digest,
            ordering_date=row.ordering_date, amount_minor=row.reading.amount_minor,
            currency=row.reading.currency, direction=row.reading.direction.value, account_id='account')
            for row, digest in zip(native.rows, native.content_hashes())]
        self.session = Mock()
        self.file = SimpleNamespace(stored_path=str(self.path), sha256=sha)
        self.session.scalar.return_value = self.file

    def check(self):
        return correction_native_controls(self.session, self.document, self.rows,
            transaction_id=self.rows[-1].id, amount_minor=self.rows[-1].amount_minor + 1,
            direction=self.rows[-1].direction, resolve_path=lambda path: path)

    def test_verified_originals_bind_current_and_proposed_controls(self):
        result = self.check()
        self.assertTrue(result['available'], result)
        self.assertEqual(result['sha256'], self.file.sha256)
        self.assertIn('unbalanced', [c['result']['status'] for c in result['proposed']['checks']])
        self.assertNotIn('unbalanced', [c['result']['status'] for c in result['current']['checks']])
        self.session.commit.assert_not_called()

    def test_changed_source_refused(self):
        self.path.write_bytes(self.data + b' ')
        self.assertIn('digest', self.check()['reason'])

    def test_changed_original_hash_refused(self):
        self.rows[0].content_hash = 'a'*64
        self.assertIn('original reading', self.check()['reason'])

    def test_missing_or_duplicate_rows_refused(self):
        original = self.rows[:]
        self.rows.pop(0)
        self.assertFalse(self.check()['available'])
        self.rows = original + [original[0]]
        self.assertIn('duplicated', self.check()['reason'])

    def test_replacement_keeps_original_binding_and_checks_current_amount(self):
        original = self.rows[-1]
        replacement = SimpleNamespace(**vars(original))
        replacement.id = uuid.uuid4()
        replacement.provenance = {'correction': {'previous_transaction_id': str(original.id)}}
        replacement.amount_minor += 2
        original.superseded_by_id = replacement.id
        original.ledger_status = 'superseded'
        self.rows.append(replacement)
        result = self.check()
        self.assertTrue(result['available'], result)
        self.assertIn('unbalanced', [c['result']['status'] for c in result['current']['checks']])
        self.assertNotIn(str(original.id), result['current_transaction_ids'])

    def test_replacement_account_change_refused(self):
        original = self.rows[-1]
        replacement = SimpleNamespace(**vars(original))
        replacement.id = uuid.uuid4()
        replacement.provenance = {'correction': { 'version': 1 }}
        replacement.account_id = 'other'
        original.superseded_by_id = replacement.id
        self.rows.append(replacement)
        self.assertIn('ownership', self.check()['reason'])

from sqlalchemy import select
from postgres.models.financial import AdjudicationEvent
from services.financial.correction_preview import preview_amount_correction
from services.financial.corrections import correct_transaction
from services.financial.quarantine_row import actor_from_user
from tests.test_financial_native_ingest import NativeIngestTestCase


class NativeCorrectionIntegrationTests(NativeIngestTestCase):
    def check_roundtrip(self, data):
        result = self.ingest(data, sha256=hashlib.sha256(data).hexdigest())
        path = Path(self._directory) / 'native.xml'
        path.write_bytes(data)
        # Trusted resolver supplies the case-scoped file already selected by the service.
        resolver = lambda _: path
        row = self.stored_rows()[0]
        preview = preview_amount_correction(self.db, case_id=self.case.id,
            transaction_id=row.id, amount_minor=row.amount_minor + 1,
            direction=row.direction, resolve_path=resolver)
        self.assertTrue(preview['native_controls_rechecked'], preview.get('native_controls'))
        self.assertEqual(preview['verification']['proposed_proof_class'], 'p3')
        self.assertTrue(any('source interpretation' in s for s in preview['verification']['reservations']))
        answer = correct_transaction(self.db, case_id=self.case.id,
            transaction_id=row.id, amount_minor=row.amount_minor + 1,
            direction=row.direction, resolve_path=resolver,
            expected_revision=preview['document_revision'], actor=actor_from_user(self.user),
            reason='Synthetic correction acceptance')
        self.assertTrue(answer['native_controls_rechecked'])
        event = self.db.scalar(select(AdjudicationEvent).where(AdjudicationEvent.id == uuid.UUID(answer['adjudication_id'])))
        self.assertTrue(event.after['native_control_comparison']['available'])
        self.assertEqual(path.read_bytes(), data)

    def test_camt_correction_audit(self):
        self.check_roundtrip(camt_bytes())

    def test_bai2_correction_audit(self):
        self.check_roundtrip(bai2_bytes())

    def test_mt940_correction_audit(self):
        self.check_roundtrip(mt940_bytes())

    def test_nacha_correction_audit(self):
        self.check_roundtrip(nacha_bytes(NACHA_SIMPLE))
