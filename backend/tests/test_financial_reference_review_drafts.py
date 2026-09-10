import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from services.financial.reference_reviews import reconcile_reference_reviews

spec=importlib.util.spec_from_file_location('review_drafts',Path(__file__).resolve().parents[2]/'scripts/prepare_financial_reference_reviews.py')
drafts=importlib.util.module_from_spec(spec);spec.loader.exec_module(drafts)


class ReferenceReviewDraftTests(unittest.TestCase):
    def test_drafts_bind_exact_source_bytes_but_cannot_become_ground_truth(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);source=root/'synthetic.pdf';raw=b'%PDF-1.4\nSynthetic test bytes only\n';source.write_bytes(raw)
            output=root/'drafts';records=drafts.prepare([source],corpus_id='synthetic',corpus_version='1',output=output)
            self.assertEqual(records[0]['source_sha256'],hashlib.sha256(raw).hexdigest())
            self.assertEqual(source.read_bytes(),raw)
            first=json.loads((output/'first-reader-draft.json').read_text());second=json.loads((output/'second-reader-draft.json').read_text())
            self.assertNotEqual(first['review_id'],second['review_id'])
            self.assertIsNone(first['reviewer_id']);self.assertIsNone(first['label_status'])
            self.assertFalse(first['documents'][0]['complete_source_reviewed'])
            self.assertEqual(first['documents'][0]['rows'],[])
            with self.assertRaises(ValueError):reconcile_reference_reviews(first,second)
            self.assertEqual(len(list(output.iterdir())),4)
            with self.assertRaisesRegex(ValueError,'must be new'):
                drafts.prepare([source],corpus_id='synthetic',corpus_version='1',output=output)

    def test_duplicate_bytes_and_non_pdf_sources_are_refused_before_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);source=root/'source.pdf';source.write_bytes(b'%PDF-synthetic')
            copy=root/'copy.pdf';copy.write_bytes(source.read_bytes());output=root/'drafts'
            with self.assertRaisesRegex(ValueError,'more than once'):
                drafts.prepare([source,copy],corpus_id='synthetic',corpus_version='1',output=output)
            self.assertFalse(output.exists())
            source.write_bytes(b'not a PDF')
            with self.assertRaisesRegex(ValueError,'PDF'):
                drafts.prepare([source],corpus_id='synthetic',corpus_version='1',output=output)
            self.assertFalse(output.exists())
