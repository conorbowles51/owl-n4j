from copy import deepcopy
from unittest import TestCase, mock
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


class VersionedDigestTests(TestCase):
    """The shared-serialization digests must equal `_digest` byte for byte."""

    def test_every_historical_version_matches_the_reference_digest(self):
        from services.financial.review_upgrade import versioned_digests
        snapshot = dict(version='statement-review-v30', source_sha256='b'*64,
            sources=[{'page_number': 1, 'text': 'Señor Ünicode — "quoted" \\ back\\slash', 'cells': [1, 2.5, None, True]}],
            metadata={'account_number': '0042', 'zeta': {'nested': ['ä', 'version']}}, currency='MXN',
            statement_id='section-2', version_note='version')
        versions = [f'statement-review-v{n}' for n in range(1, 30)]
        self.assertEqual(versioned_digests(snapshot, versions),
                         [_digest({**snapshot, 'version': v}) for v in versions])

    def test_placeholder_collision_falls_back_to_reference_digest(self):
        from unittest.mock import patch
        from services.financial import review_upgrade
        snapshot = dict(sources=['review-version-placeholder-' + '0' * 32], version='x')
        with patch.object(review_upgrade, 'uuid4', return_value=type('U', (), {'hex': '0' * 32})()):
            result = review_upgrade.versioned_digests(snapshot, ['statement-review-v1'])
        self.assertEqual(result, [_digest({**snapshot, 'version': 'statement-review-v1'})])


class FilledDetailsUpgradeTests(TestCase):
    """A reader fix that only fills a detail the saved review already holds (Truist STATEMENTS 5630.pdf: the account
    read past a scanned heading bullet) keeps the saved review, edits included, and the duplicate decision on it."""

    def _reading(self, account):
        snapshot = dict(version='statement-review-v29', source_sha256='c'*64,
            sources=[{'page_number': 1, 'text': 'BUSINESS VALUE 200 CHECKING'}],
            metadata={'account_number': account, 'holder': 'Holder LLC', 'account_type': 'checking'},
            currency='USD', statement_id='s1')
        rows = [dict(id='r1', kind='transaction', excluded=False,
                     fields=dict(date='2024-01-02', amount_minor='1500', direction='debit', description='Fee'))]
        return snapshot, dict(revision=_digest(snapshot), rows=rows, metadata=snapshot['metadata'],
                              currency='USD', statement_id='s1')

    def _saved(self, revision, account):
        rows = [dict(id='r1', excluded=True, date='2024-01-02', description='Fee', counterparty='', amount_minor='1500',
                     direction='debit', balance_minor=None, reason='Set aside: read from the page images instead'),
                dict(id='m1', manual_page=1, excluded=False, date='2024-01-02', description='Fee (page image)',
                     counterparty='', amount_minor='1500', direction='debit', balance_minor=None, reason='')]
        return dict(request=dict(expected_revision=revision, statement_id='s1', currency='USD', holder='Holder LLC',
                                 account_number=account, institution='Truist', period_start='2024-01-01',
                                 period_end='2024-01-31', rows=rows),
                    review_revision='token', initial_request_signature='from-an-older-reading')

    def test_saved_review_with_edits_carries_over_when_the_reading_only_fills_the_account(self):
        old_snapshot, old = self._reading('')
        snapshot, proposal = self._reading('1000270585630')
        saved = self._saved(old['revision'], '1000270585630')
        proposal['saved_review'] = deepcopy(saved)
        attach_upgrade(proposal, snapshot)
        upgraded = proposal['saved_review']
        self.assertEqual(upgraded['upgraded_from_revision'], old['revision'])
        self.assertEqual(upgraded['request']['expected_revision'], proposal['revision'])
        self.assertEqual(upgraded['request']['rows'], saved['request']['rows'])
        self.assertEqual(upgraded['review_revision'], 'token')

    def test_no_carry_over_when_the_saved_review_holds_another_value_or_the_reading_changed(self):
        _, old = self._reading('')
        snapshot, proposal = self._reading('1000270585630')
        proposal['saved_review'] = self._saved(old['revision'], '9999')
        attach_upgrade(proposal, snapshot)
        self.assertNotIn('upgraded_from_revision', proposal['saved_review'])
        changed = {**snapshot, 'sources': [{'page_number': 1, 'text': 'other text'}]}
        proposal = {**self._reading('1000270585630')[1], 'revision': _digest(changed),
                    'saved_review': self._saved(old['revision'], '1000270585630')}
        attach_upgrade(proposal, changed)
        self.assertNotIn('upgraded_from_revision', proposal['saved_review'])

    def test_duplicate_decision_signed_on_the_earlier_reading_stays_current(self):
        from types import SimpleNamespace
        from services.financial import pending_statement_duplicates as P
        _, old = self._reading('')
        saved = self._saved(old['revision'], '1000270585630')
        old['saved_review'] = deepcopy(saved)
        decision = dict(status='retained', reading_revision=old['revision'], signature=P.review_signature(old))
        file = SimpleNamespace(metadata_={P.METADATA_KEY: {'s1': decision}}, case_id=None)
        self.assertTrue(P.read_duplicate_disposition(None, file, old)['current'])
        snapshot, proposal = self._reading('1000270585630')
        proposal['saved_review'] = deepcopy(saved)
        attach_upgrade(proposal, snapshot)
        result = P.read_duplicate_disposition(None, file, proposal)
        self.assertTrue(result['current'])
        self.assertEqual(result['status'], 'retained')
        # Signed on another reading than the one the saved review came from: compare again.
        file.metadata_[P.METADATA_KEY]['s1'] = {**decision, 'reading_revision': 'another'}
        self.assertFalse(P.read_duplicate_disposition(None, file, proposal)['current'])
        with mock.patch.object(P, 'UPGRADED_READING', False, create=True):
            file.metadata_[P.METADATA_KEY]['s1'] = decision
            self.assertFalse(P.read_duplicate_disposition(None, file, proposal)['current'])
