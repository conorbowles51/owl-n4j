"""A saved copy naming no statement stands for, or was set aside as, only what it held (fin-queue3 R1).

Synthetic three-statement Monex file (MXN, USD, EUR sections of one PDF). Early imports saved some files as
one copy naming no statement. That copy matched EVERY statement of its bytes, so once one statement of a
multi-statement file was saved or set aside against it, the file's other statements read as already
imported or "excluded as a duplicate" and the writer refused them (BNB2, 2026-10-25: 17 empty imports and two
dated ones, '01 ARRENDO MONEX MXN ENE 2022.pdf' and 'ESTADO DE CUENTA MONETA INTECAM MARZO 2025-1.pdf').
Gate shape added with it: a multi-statement file imports every statement in turn.
"""
from copy import deepcopy
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch
from uuid import UUID, uuid4

from sqlalchemy import select

from postgres.models.evidence import EvidenceDocumentText, EvidenceTableGeometry, IngestionLog
from postgres.models.enums import DuplicateMatchRung
from postgres.models.financial import FinancialSourceDocument
from tests.test_financial_statement_import_monex import landscape, prepare


def _logs(fixture):
    from postgres.base import Base
    Base.metadata.create_all(fixture.db.connection(), tables=[IngestionLog.__table__])
    fixture.db.commit()


class KeylessCopyTests(TestCase):
    def setUp(self):
        from tests.test_financial_statement_import import StatementImportTests
        self.f = StatementImportTests('test_existing_import_and_same_request_keep_the_saved_account_for_navigation')
        self.f.setUp()
        _logs(self.f)
        prepare(self, landscape())
        self.case_id = self.f.case.id

    def tearDown(self):
        self.f.tearDown()

    def preview(self, statement_id=None, file=None):
        from services.financial.statement_import import read_statement_import
        with self.f.SessionLocal() as db:
            return read_statement_import(db, case_id=self.case_id, evidence_file_id=(file or self.f.file).id,
                                         statement_id=statement_id)

    def choices(self):
        return {c['currency']: c['id'] for c in self.preview()['statement_choices']}

    def save(self, statement_id, file=None):
        from services.financial.import_batches import initial_request
        current = self.f.file
        self.f.file = file or current
        try:
            return self.f.confirm(initial_request(self.preview(statement_id, file)))
        finally:
            self.f.file = current

    def copy_file(self):
        """Another upload of the fixture's PDF: same bytes, its own evidence row, text and every page's geometry."""
        original = self.f.file
        path = Path(self.f._directory) / f'copy-{uuid4().hex[:8]}.pdf'
        path.write_bytes(Path(original.stored_path).read_bytes())
        copied = self.f.evidence(original.sha256)
        copied.stored_path = str(path)
        copied.status = original.status
        text = self.f.db.get(EvidenceDocumentText, original.id)
        self.f.db.add(EvidenceDocumentText(evidence_file_id=copied.id, content=text.content,
            content_sha256=text.content_sha256, character_count=text.character_count,
            engine_job_id=text.engine_job_id, source_locations=deepcopy(text.source_locations)))
        for geometry in self.f.db.scalars(select(EvidenceTableGeometry).where(EvidenceTableGeometry.evidence_file_id == original.id)):
            self.f.db.add(EvidenceTableGeometry(evidence_file_id=copied.id, page_number=geometry.page_number,
                engine_job_id=geometry.engine_job_id, payload=deepcopy(geometry.payload)))
        self.f.db.commit()
        return copied

    def unkey(self, document_id, **changes):
        """As the early imports were saved: the copy names no statement."""
        with self.f.SessionLocal() as db:
            document = db.get(FinancialSourceDocument, UUID(document_id))
            document.metadata_ = {**document.metadata_, 'statement_import_statement_id': None}
            for key, value in changes.items():
                setattr(document, key, value)
            db.commit()

    def keyless_exclusion(self, currency='MXN'):
        """A dated copy of the ``currency`` statement, naming no statement, set aside by a person as the
        duplicate of a same-bytes upload's saved copy of that statement (as c2a8a8be / cc84886f on BNB2)."""
        ids = self.choices()
        copy = self.copy_file()
        retained = UUID(self.save(ids[currency], copy)['source_document_id'])
        with self.f.SessionLocal() as db:   # out of the way while the earlier copy is saved, as it was then
            db.get(FinancialSourceDocument, retained).status = 'superseded'
            db.commit()
        with patch('services.financial.pending_statement_duplicates.apply_duplicate_disposition', return_value=dict(status='distinct')):
            excluded = self.save(ids[currency])['source_document_id']
        with self.f.SessionLocal() as db:
            db.get(FinancialSourceDocument, retained).status = 'admitted'
            db.commit()
        self.unkey(excluded)
        # The recorded exclusion as the live ones stand: superseded by the retained copy, on the identical-bytes rung.
        from services.financial.duplicates import _supersede, store_fingerprint
        with self.f.SessionLocal() as db:
            store_fingerprint(db, db.get(FinancialSourceDocument, UUID(excluded)))
            _supersede(db, db.get(FinancialSourceDocument, UUID(excluded)), retained, case_id=self.case_id,
                       rung=DuplicateMatchRung.identical_bytes, actor=self.f.actor, reason='Same statement uploaded twice.')
            db.commit()
        return ids, excluded, retained

    def test_a_dated_copy_set_aside_naming_no_statement_excludes_only_the_statement_it_held(self):
        ids, excluded, retained = self.keyless_exclusion('MXN')
        held = self.preview(ids['MXN'])['current_import']
        self.assertTrue(held['excluded_as_duplicate'])
        self.assertEqual(held['source_document_id'], excluded)
        for currency in ('USD', 'EUR'):
            self.assertIsNone(self.preview(ids[currency])['current_import'], currency)
        for currency, count in (('USD', 2), ('EUR', 0)):
            receipt = self.save(ids[currency])
            self.assertTrue(receipt['created'], receipt)
            self.assertEqual(receipt['transaction_count'], count)

    def test_a_dated_saved_copy_naming_no_statement_stands_only_for_its_own_period(self):
        ids = self.choices()
        legacy = self.save(ids['MXN'])['source_document_id']
        self.unkey(legacy)
        self.assertEqual(self.preview(ids['MXN'])['current_import']['source_document_id'], legacy)
        self.assertFalse(self.save(ids['MXN'])['created'])
        for currency, count in (('USD', 2), ('EUR', 0)):
            self.assertIsNone(self.preview(ids[currency])['current_import'], currency)
            receipt = self.save(ids[currency])
            self.assertTrue(receipt['created'], receipt)
            self.assertEqual(receipt['transaction_count'], count)

    def test_every_statement_of_a_multi_statement_file_imports_in_turn(self):
        """The gate shape that was missing (fin-queue3 R1): import each statement of one file in turn; each
        one reads ready before and as saved after, and saving one never changes how the others read."""
        from services.financial.import_batches import assess
        ids = self.choices()
        saved = {}
        for currency in ('USD', 'MXN', 'EUR'):
            for other, document in saved.items():
                self.assertEqual(self.preview(ids[other])['current_import']['source_document_id'], document)
            proposal = self.preview(ids[currency])
            self.assertIsNone(proposal['current_import'], currency)
            self.assertTrue(assess(proposal)[1]['can_import'], currency)
            receipt = self.save(ids[currency])
            self.assertTrue(receipt['created'], receipt)
            saved[currency] = receipt['source_document_id']
        for currency, document in saved.items():
            current = self.preview(ids[currency])['current_import']
            self.assertEqual(current['source_document_id'], document)
            self.assertFalse(current['excluded_as_duplicate'])

    def test_after_a_shell_files_first_statement_is_saved_its_other_statements_still_import(self):
        """04 ARRENDO MONEX MXN ABR 2022 (BNB2): the EUR statement saved over the file's empty early import, then
        the MXN and USD statements, ready a minute before, read "excluded as a duplicate" and were refused."""
        from sqlalchemy import delete
        from postgres.models.financial import FinancialStatementPeriod, FinancialTransaction
        from services.financial import saved_reading_replacement
        ids = self.choices()
        shell = self.save(ids['MXN'])['source_document_id']
        with self.f.SessionLocal() as db:   # as the live shells were saved: nothing named, dated or paid
            document = db.get(FinancialSourceDocument, UUID(shell))
            document.metadata_ = {**document.metadata_, 'statement_import_statement_id': None, 'statement_incomplete_records': []}
            db.execute(delete(FinancialTransaction).where(FinancialTransaction.source_document_id == UUID(shell)))
            for period in db.scalars(select(FinancialStatementPeriod).where(FinancialStatementPeriod.source_document_id == UUID(shell))):
                period.period_start = period.period_end = None
                period.period_start_source = period.period_end_source = 'absent'
                period.closing_balance_minor, period.closing_balance_source = None, 'absent'
                period.credit_total_minor = period.debit_total_minor = 0
                period.transaction_count = 0
                period.reconciliation_status = 'unavailable'
            db.commit()
            self.assertTrue(saved_reading_replacement.is_shell(db, db.get(FinancialSourceDocument, UUID(shell))))
        first = self.save(ids['EUR'])
        self.assertTrue(first['created'], first)
        with self.f.SessionLocal() as db:
            self.assertEqual(str(db.get(FinancialSourceDocument, UUID(shell)).superseded_by_id), first['source_document_id'])
        for currency, count in (('MXN', 3), ('USD', 2)):
            self.assertIsNone(self.preview(ids[currency])['current_import'], currency)
            receipt = self.save(ids[currency])
            self.assertTrue(receipt['created'], receipt)
            self.assertEqual(receipt['transaction_count'], count)
        current = self.preview(ids['EUR'])['current_import']
        self.assertEqual((current['source_document_id'], current['excluded_as_duplicate']), (first['source_document_id'], False))
