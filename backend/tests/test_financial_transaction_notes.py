from datetime import datetime, timezone
from uuid import uuid4
from unittest.mock import patch
from postgres.base import Base
from postgres.models.workspace_entry import WorkspaceEntry, WorkspaceEntryLink
from services.financial.transaction_notes import capture_transaction_notes
from services.financial.ledger_summary import LedgerSummaryError
from tests.test_financial_transactions_writer import TransactionPersistenceTestCase


class FinancialTransactionNotesTests(TransactionPersistenceTestCase):
    def setUp(self):
        super().setUp()
        Base.metadata.create_all(self.db.connection(),tables=[WorkspaceEntry.__table__,WorkspaceEntryLink.__table__])
        self.file_id=str(uuid4());self.transaction_id=str(uuid4())
        self.readings=[dict(row=dict(key=self.transaction_id,ref_id='retained-reference',ledger_status='admitted'),source=dict(evidence_file_id=self.file_id))]
        self.note=WorkspaceEntry(case_id=self.case.id,entry_type='note',body='Ask about this payment.',title='Payment note',author_name='Investigator')
        self.db.add(self.note);self.db.flush()
        self.link=WorkspaceEntryLink(case_id=self.case.id,entry_id=self.note.id,target_type='evidence',target_id=self.file_id,target_label='statement.pdf',source_anchor={'financial_transaction_ids':[self.transaction_id]})
        self.db.add(self.link);self.db.commit()

    def capture(self,case_id=None):
        return capture_transaction_notes(self.db,case_id=case_id or self.case.id,readings=self.readings)

    def test_captures_authored_note_and_exact_reference_without_changing_totals(self):
        notes=self.capture()
        self.assertEqual(len(notes),1)
        self.assertEqual(notes[0]['body'],'Ask about this payment.')
        self.assertEqual(notes[0]['links'][0]['transactions'][0]['ref_id'],'retained-reference')
        self.assertEqual(self.capture(case_id=uuid4()),[])
        self.assertFalse(self.db.new or self.db.dirty)

    def test_deleted_and_unrelated_notes_are_not_included(self):
        self.note.deleted_at=datetime.now(timezone.utc);self.db.commit()
        self.assertEqual(self.capture(),[])
        self.note.deleted_at=None;self.link.source_anchor={'financial_transaction_ids':[str(uuid4())]};self.db.commit()
        self.assertEqual(self.capture(),[])

    def test_wrong_evidence_reference_and_excessive_scope_are_refused(self):
        other=str(uuid4())
        self.readings.append(dict(row=dict(key=str(uuid4()),ref_id='other',ledger_status='admitted'),source=dict(evidence_file_id=other)))
        self.link.target_id=other;self.db.commit()
        with self.assertRaises(LedgerSummaryError):self.capture()
        self.link.target_id=self.file_id;self.db.commit()
        with patch('services.financial.transaction_notes.MAX_NOTE_LINKS',0),self.assertRaises(LedgerSummaryError):self.capture()
