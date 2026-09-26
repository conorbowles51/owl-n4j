"""Synthetic workflow checks for a batch-wide, non-destructive review index."""
from copy import deepcopy
from types import SimpleNamespace
from unittest import TestCase

from services.financial.batch_review_summary import review_summary, item_reasons, matches_group, validate_group, reason
from services.financial.pdf_candidates import PdfMappingError


def item(*problems, status='attention', can_import=True, **extra):
    return SimpleNamespace(status=status, summary=dict(problems=list(problems), problem_count=len(problems),
        can_import=can_import, **extra))


class BatchReviewSummaryTests(TestCase):
    def test_separates_blockers_from_importable_checks_across_a_large_batch(self):
        holders = [item(dict(kind='statement_detail', field='holder', message='The account holder has not been identified.')) for _ in range(201)]
        balance = item(dict(check='closing_balance', message='The payments do not add up to the printed closing balance.'))
        currency = item(dict(message='Choose the currency printed on these statements.'), can_import=False)
        unavailable = item(status='ready', balance_status='unavailable')
        before = deepcopy([i.summary for i in holders + [balance, currency, unavailable]])
        result = review_summary(holders + [balance, currency, unavailable])
        groups = {group['id']: group for group in result['groups']}
        self.assertEqual(result['blocked_statements'], 1)
        self.assertEqual(result['importable_with_checks'], 202)
        self.assertEqual(result['unchecked_balance_statements'], 1)
        self.assertEqual(groups['holder']['statement_count'], 201)
        self.assertEqual(groups['holder']['blocked_statements'], 0)
        self.assertEqual(groups['currency']['blocked_statements'], 1)
        self.assertEqual(groups['balance']['check_count'], 1)
        self.assertEqual(result['groups'][0]['id'], 'currency')
        self.assertEqual([i.summary for i in holders + [balance, currency, unavailable]], before)

    def test_one_statement_can_have_several_reasons_without_inflating_statement_counts(self):
        reading = item(dict(kind='missing_field', field='amount', message='Amount missing'),
            dict(kind='missing_field', field='date', message='Date missing'),
            dict(kind='statement_detail', field='holder', message='Holder missing'))
        result = review_summary([reading])
        self.assertEqual(result['importable_with_checks'], 1)
        groups = {group['id']: group for group in result['groups']}
        self.assertEqual(groups['incomplete']['check_count'], 2)
        self.assertEqual(groups['incomplete']['statement_count'], 1)
        self.assertEqual(groups['holder']['statement_count'], 1)

    def test_retained_import_checks_and_truncated_checks_are_not_lost_or_counted_as_blockers(self):
        saved = item(dict(kind='coverage', message='Overlapping dates'), status='imported', can_import=False)
        saved.summary['problem_count'] = 75
        skipped = item(dict(kind='missing_field', field='date', message='Missing date'), status='skipped', can_import=False)
        result = review_summary([saved, skipped])
        self.assertEqual(result['blocked_statements'], 0)
        self.assertEqual(result['imported_with_checks'], 1)
        self.assertEqual(sum(group['check_count'] for group in result['groups']), 75)
        self.assertEqual(item_reasons(skipped), {})
        self.assertTrue(matches_group(saved, 'additional'))
        self.assertFalse(matches_group(saved, 'blocked'))

    def test_legacy_checks_are_explained_without_dismissing_unknown_messages(self):
        legacy = item(dict(message='The account number has not been identified.'),
            dict(message='Not enough readable balances for an automatic balance check.'),
            dict(message='New reader message requiring inspection'))
        self.assertEqual(item_reasons(legacy), {'account': 1, 'balance_unavailable': 1, 'reading': 1})
        self.assertEqual(reason(dict(kind='coverage_load', message='Could not compare the statement dates.')), 'reading')
        with self.assertRaises(PdfMappingError):
            validate_group('unknown-filter')

    def test_progress_filters_do_not_revisit_saved_or_decided_statements(self):
        from services.financial.batch_review_summary import statement_summary, group_label
        readings = [
            item(status='ready', can_import=True),
            item(status='attention', can_import=False),
            item(dict(message='Retained original flag'), status='imported', can_import=True),
            item(status='pending_import'), item(status='skipped'),
            item(status='duplicate_ignored'), item(status='assigned'),
            item(status='removed'), item(status='superseded_reading'),
        ]
        for group in ('unfinished', 'saved', 'ready_to_save'):
            validate_group(group)
            self.assertTrue(group_label(group))
        self.assertEqual([r.status for r in readings if matches_group(r, 'unfinished')], ['ready', 'attention'])
        self.assertEqual([r.status for r in readings if matches_group(r, 'saved')], ['imported'])
        self.assertEqual([r.status for r in readings if matches_group(r, 'ready_to_save')], ['ready'])
        before = statement_summary(readings)
        readings[1].status = 'imported'
        after = statement_summary(readings)
        self.assertEqual(before['blocked'] - after['blocked'], 1)
        self.assertEqual(after['imported'] - before['imported'], 1)
        self.assertEqual([r.status for r in readings if matches_group(r, 'unfinished')], ['ready'])

    def test_duplicates_have_separate_progress_and_navigation(self):
        from services.financial.batch_review_summary import statement_summary
        duplicate = item(dict(kind='coverage', matching_statement=True), status='attention', can_import=False)
        normal = item(status='attention', can_import=False)
        ignored = item(status='duplicate_ignored')
        skipped = item(dict(kind='coverage', matching_statement=True), status='skipped')
        self.assertFalse(matches_group(duplicate, 'unfinished'))
        self.assertTrue(matches_group(normal, 'unfinished'))
        self.assertTrue(all(matches_group(i, 'duplicates') for i in (duplicate, ignored, skipped)))
        summary = statement_summary([normal, duplicate, ignored, skipped])
        self.assertEqual(summary['blocked'], 1)
        self.assertEqual(summary['possible_duplicates'], 1)
        self.assertEqual(summary['total'], 4)
        validate_group('duplicates')
