import unittest
from unittest.mock import patch

from fastapi import HTTPException
from pydantic import ValidationError
from routers import financial


class FinancialBulkCorrectionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.records = [dict(key='a', name='Same payment', amount=100),
                        dict(key='b', name='Same payment', amount=200)]
        self.read = patch.object(financial.neo4j_service, 'get_financial_transactions',
                                 return_value={'transactions': self.records}).start()
        self.write = patch.object(financial.neo4j_service, 'update_transaction_amount',
                                  side_effect=lambda **p: dict(success=True, key=p['node_key'], amount=p['new_amount'])).start()
        self.addCleanup(patch.stopall)

    def request(self, *rows):
        return financial.BulkCorrectRequest(case_id='case-a', corrections=list(rows))

    def row(self, key='a', **changes):
        return dict(node_key=key, new_amount=125, correction_reason='Checked original receipt', **changes)

    async def test_exact_keys_do_not_match_every_record_with_the_same_name(self):
        result = await financial.bulk_correct_transactions(self.request(self.row(expected_amount=100)))
        self.assertEqual(result['corrected'], 1)
        self.assertEqual([r['key'] for r in result['results']], ['a'])
        self.write.assert_called_once_with(node_key='a', case_id='case-a', new_amount=125,
            correction_reason='Checked original receipt', expected_amount=100)
        self.assertEqual({call.kwargs['mode'] for call in self.read.call_args_list}, {'transactions', 'intelligence'})

    async def test_missing_key_rejects_the_whole_file_before_writes(self):
        with self.assertRaises(HTTPException) as error:
            await financial.bulk_correct_transactions(self.request(self.row(), self.row('missing')))
        self.assertEqual(error.exception.status_code, 404)
        self.write.assert_not_called()

    async def test_repeated_keys_reject_before_writes(self):
        with self.assertRaises(HTTPException) as error:
            await financial.bulk_correct_transactions(self.request(self.row(), self.row()))
        self.assertEqual(error.exception.status_code, 400)
        self.write.assert_not_called()

    async def test_old_name_format_requires_an_unambiguous_record(self):
        with self.assertRaises(HTTPException) as error:
            await financial.bulk_correct_transactions(self.request(dict(name='Same payment', new_amount=125, correction_reason='Check')))
        self.assertEqual(error.exception.status_code, 409)
        self.write.assert_not_called()
        self.records[1]['name'] = 'Other payment'
        result = await financial.bulk_correct_transactions(self.request(dict(name='same payment', new_amount=125, correction_reason='Check')))
        self.assertEqual(result['results'][0]['key'], 'a')

    async def test_changed_amount_rejects_before_any_correction(self):
        with self.assertRaises(HTTPException) as error:
            await financial.bulk_correct_transactions(self.request(self.row(expected_amount=100), self.row('b', expected_amount=199)))
        self.assertEqual(error.exception.status_code, 409)
        self.write.assert_not_called()

    async def test_write_failure_reports_saved_and_failed_records_separately(self):
        self.write.side_effect = [dict(success=True, key='a', amount=125), ValueError('Record changed')]
        result = await financial.bulk_correct_transactions(self.request(self.row(), self.row('b')))
        self.assertFalse(result['success'])
        self.assertEqual((result['corrected'], result['errors'], result['total']), (1, 1, 2))
        self.assertEqual([r['status'] for r in result['results']], ['corrected', 'error'])

    async def test_unconfirmed_response_is_not_counted_as_saved(self):
        self.write.side_effect = None
        self.write.return_value = dict(success=True, key='another-key', amount=125)
        result = await financial.bulk_correct_transactions(self.request(self.row()))
        self.assertEqual(result['corrected'], 0)
        self.assertEqual(result['errors'], 1)

    def test_invalid_amounts_reasons_and_ambiguous_identifiers_are_refused(self):
        for changes in [dict(new_amount=float('inf')), dict(new_amount=float('nan')),
                        dict(new_amount=0), dict(new_amount=1.234), dict(correction_reason='   '),
                        dict(name='Also a name'), dict(node_key=None)]:
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                financial.BulkCorrectionItem(**(self.row() | changes))

    def test_single_amount_requires_finite_value_and_explanation(self):
        for changes in [dict(new_amount=float('inf')), dict(new_amount=1.234), dict(correction_reason=' '), dict(expected_amount=float('nan'))]:
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                financial.UpdateAmountRequest(**(dict(case_id='case-a', new_amount=125, correction_reason='Checked') | changes))
