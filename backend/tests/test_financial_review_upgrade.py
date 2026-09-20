from copy import deepcopy
from unittest import TestCase
from services.financial.pdf_candidates import _digest
from services.financial.review_upgrade import attach_upgrade, upgrade_request


class ReviewUpgradeTests(TestCase):
    def test_unchanged_source_preserves_manual_edits_and_removes_only_empty_false_payments(self):
        snapshot = dict(version='statement-review-v29', source_sha256='a'*64,
            sources=[{'page_number': 1, 'text': 'Same source text and locations'}],
            metadata={'account_number': '123'}, currency='EUR', statement_id=None)
        old_revision = _digest({**snapshot, 'version': 'statement-review-v28'})
        rows = [dict(id=str(i), excluded=False, date='', description='', counterparty='',
            amount_minor='', direction=None, balance_minor=None, reason='') for i in range(3)]
        rows[1].update(description='Investigator entered this', amount_minor='1200')
        rows[2]['reason'] = 'Keep this record for later'
        saved = dict(request=dict(expected_revision=old_revision, holder='Manually saved holder',
            account_number='000123', rows=rows), review_revision='saved-concurrency-token')
        proposal = dict(revision=_digest(snapshot), rows=[dict(id=str(i), kind='unclassified') for i in range(3)], saved_review=saved)
        attach_upgrade(proposal, snapshot)
        upgraded = proposal['saved_review']['request']
        self.assertEqual(upgraded['holder'], saved['request']['holder'])
        self.assertEqual(upgraded['account_number'], '000123')
        self.assertTrue(upgraded['rows'][0]['excluded'])
        self.assertEqual(upgraded['rows'][1:], rows[1:])
        self.assertFalse(saved['request']['rows'][0]['excluded'])
        self.assertEqual(proposal['saved_review']['review_revision'], 'saved-concurrency-token')
        self.assertEqual(upgraded['expected_revision'], proposal['revision'])

    def test_changed_pdf_or_source_revision_never_rebinds_prior_edits(self):
        snapshot = dict(version='statement-review-v29', sources=[{'source_revision': 'new'}])
        old = dict(expected_revision=_digest(dict(version='statement-review-v28', sources=[{'source_revision': 'old'}])), rows=[])
        proposal = dict(revision=_digest(snapshot), rows=[], saved_review=dict(request=old))
        before = deepcopy(proposal)
        attach_upgrade(proposal, snapshot)
        self.assertEqual(proposal['saved_review'], before['saved_review'])
        self.assertIsNone(upgrade_request(old, proposal))
