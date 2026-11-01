"""manual_changes.producer_for: what groups a change's pattern (reader, layout or bank). Invented data only."""
import tempfile
import unittest
import uuid
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from postgres.models.financial import FinancialAccount, FinancialSourceDocument
from services import manual_changes as mc

CASE = uuid.uuid4()


class ProducerTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.engine = create_engine(f"sqlite+pysqlite:///{Path(directory.name) / 'p.db'}", future=True)
        FinancialSourceDocument.metadata.create_all(
            self.engine, tables=[FinancialAccount.__table__, FinancialSourceDocument.__table__])

    def document(self, session, metadata, institution=None):
        doc = FinancialSourceDocument(id=uuid.uuid4(), case_id=CASE, evidence_file_id=uuid.uuid4(), ingestion_run_id=uuid.uuid4(),
                                      sha256_at_ingestion='0' * 64, proof_class='p1', extraction_layer=1, parser_name='statement-review-v30',
                                      parser_version='1', document_type='statement_review',
                                      institution_name=institution, metadata_=metadata)
        session.add(doc)
        session.flush()
        return doc

    def test_a_statement_saved_from_picked_rows_is_grouped_by_its_accounts_bank(self):
        with Session(self.engine) as session:
            account = FinancialAccount(id=uuid.uuid4(), case_id=CASE, identity_key='k1', institution_name='Banco Ejemplo')
            session.add(account)
            session.flush()
            doc = self.document(session, {'statement_account_id': str(account.id),
                                          'statement_import_original': {'statement_choices': [], 'statement_id': ''}})
            self.assertEqual(mc.producer_for(session, 'source_document', str(doc.id)),
                             ('statement-review-v30@1', 'Banco Ejemplo'))

    def test_the_readings_own_bank_and_layout_reader_still_come_first(self):
        with Session(self.engine) as session:
            account = FinancialAccount(id=uuid.uuid4(), case_id=CASE, identity_key='k1', institution_name='Banco Ejemplo')
            session.add(account)
            session.flush()
            doc = self.document(session, {'statement_account_id': str(account.id)}, institution='Printed Bank')
            self.assertEqual(mc.producer_for(session, 'source_document', str(doc.id)),
                             ('statement-review-v30@1', 'Printed Bank'))
            doc = self.document(session, {'statement_account_id': str(account.id), 'statement_import_original': {
                'statement_choices': [{'id': 's1', 'layout_id': 'layout-reader@2', 'layout_fingerprint': 'fp9'}],
                'statement_id': 's1'}})
            self.assertEqual(mc.producer_for(session, 'source_document', str(doc.id)), ('layout-reader@2', 'fp9'))

    def test_no_account_leaves_the_bank_blank(self):
        with Session(self.engine) as session:
            doc = self.document(session, {'statement_import_original': {'statement_choices': []}})
            self.assertEqual(mc.producer_for(session, 'source_document', str(doc.id)), ('statement-review-v30@1', ''))


if __name__ == '__main__':
    unittest.main()
