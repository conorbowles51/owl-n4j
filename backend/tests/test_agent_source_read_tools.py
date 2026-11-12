from uuid import uuid4
from unittest.mock import patch

from tests.test_evidence_page_text import Base_, page, NATIVE
from services.agent.source_read_tools import read_document_text


class SourceReadingTests(Base_):
    def setUp(self):
        super().setUp()
        # Synthetic files have no financial vision attempts; avoid loading that unrelated platform runtime.
        self.vision = patch('services.evidence_page_text.page_image_failure', return_value=None)
        self.vision.start()

    def tearDown(self):
        self.vision.stop()
        super().tearDown()

    def test_full_traversal_has_no_missing_or_duplicate_text(self):
        text = "Alpha\nBeta\nGamma"
        record = self.file(content=text, locations=[page(1, 0, 6, **NATIVE), page(2, 6, 11, **NATIVE), page(3, 11, 16, **NATIVE)])
        first = read_document_text(self.db, self.case_id, record.id, page_limit=1)
        second = read_document_text(self.db, self.case_id, record.id, page_offset=first['next_offset'],
                                    page_limit=2, expected_revision=first['revision'])
        self.assertEqual(''.join(p['text'] for p in first['pages'] + second['pages']), text)
        self.assertFalse(second['has_more'])
        self.assertEqual(second['pages'][0]['cite'], f'doc://{record.id}/2')

    def test_continuation_needs_the_same_reading(self):
        record = self.file(content='text')
        with self.assertRaisesRegex(ValueError, 'revision'):
            read_document_text(self.db, self.case_id, record.id, page_offset=1)
        with self.assertRaisesRegex(ValueError, 'changed'):
            read_document_text(self.db, self.case_id, record.id, expected_revision='old')

    def test_wrong_case_does_not_disclose_file_name_or_text(self):
        record = self.file(content='private')
        with self.assertRaisesRegex(ValueError, 'not in this case'):
            read_document_text(self.db, uuid4(), record.id)

    def test_unread_file_is_a_readability_gap_not_an_absent_document(self):
        record = self.file(status='unprocessed')
        result = read_document_text(self.db, self.case_id, record.id)
        self.assertEqual(result['processing_state'], 'unprocessed')
        self.assertIn('not been processed', result['text_absent'])
        self.assertNotIn('original_available', result)

    def test_long_non_pdf_text_parts_do_not_invent_pdf_page_citations(self):
        text = 'Synthetic text. ' * 5000
        record = self.file(name='analysis.txt', content=text, locations=[dict(kind='body', start_char=0, end_char=len(text))])
        result = read_document_text(self.db, self.case_id, record.id, page_limit=50)
        self.assertEqual(''.join(p['text'] for p in result['pages']), text)
        self.assertTrue(all(p['cite'] == f'doc://{record.id}' for p in result['pages']))
