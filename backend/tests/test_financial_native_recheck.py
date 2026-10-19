"""Conditional native controls must notice revised readings without source edits."""
import copy
import unittest

from postgres.models.enums import TransactionDirection
from services.financial.money import Money
from services.financial.native import read_native
from services.financial.native_recheck import NativeAmountReading, recheck_native_controls
from tests.test_financial_native import (
    WINDOW, camt_bytes, bai2_bytes, mt940_bytes, nacha_bytes, NACHA_SIMPLE,
)
from tests.test_financial_camt053 import stmt, ntry, summary


class NativeRecheckTests(unittest.TestCase):
    def fixtures(self):
        return [camt_bytes(), bai2_bytes(), mt940_bytes(), nacha_bytes(NACHA_SIMPLE)]

    def inputs(self, data):
        native = read_native(data, window=WINDOW)
        return native, {row.row_index: NativeAmountReading(
            Money.from_minor_units(row.reading.amount_minor, row.reading.currency),
            row.reading.direction) for row in native.rows}

    def test_original_controls_agree_for_four_formats(self):
        for data in self.fixtures():
            native, readings = self.inputs(data)
            with self.subTest(format=native.format):
                result = recheck_native_controls(native, readings)
                self.assertTrue(result['checks'])
                self.assertNotIn('unbalanced', [c['result']['status'] for c in result['checks']])
                self.assertFalse(result['changes_proof_class'])

    def test_changed_amount_fails_controls_and_does_not_change_original(self):
        for data in self.fixtures():
            native, readings = self.inputs(data)
            original = copy.deepcopy(native)
            key = next(iter(readings))
            old = readings[key]
            readings[key] = NativeAmountReading(Money.from_minor_units(
                old.amount.minor_units + 1, old.amount.currency), old.direction)
            with self.subTest(format=native.format):
                result = recheck_native_controls(native, readings)
                self.assertIn('unbalanced', [c['result']['status'] for c in result['checks']])
                self.assertEqual(native, original)

    def test_direction_change_detected_even_when_unsigned_checksum_agrees(self):
        for data in self.fixtures():
            native, readings = self.inputs(data)
            key = next(iter(readings))
            old = readings[key]
            readings[key] = NativeAmountReading(old.amount,
                TransactionDirection.debit if old.direction == TransactionDirection.credit
                else TransactionDirection.credit)
            with self.subTest(format=native.format):
                self.assertIn('unbalanced', [c['result']['status']
                    for c in recheck_native_controls(native, readings)['checks']])

    def test_missing_extra_changed_currency_and_negative_readings_refused(self):
        native, readings = self.inputs(camt_bytes())
        key = next(iter(readings))
        for bad in [{}, {**readings, 999: readings[key]},
                    {**readings, key: NativeAmountReading(Money.from_minor_units(1, 'GBP'), readings[key].direction)},
                    {**readings, key: NativeAmountReading(Money.from_minor_units(-1, 'USD'), readings[key].direction)}]:
            with self.assertRaises(ValueError):
                recheck_native_controls(native, bad)

    def test_unmapped_pending_source_record_retained_and_summary_declined(self):
        native, readings = self.inputs(camt_bytes(statements=[stmt(entries=ntry('50.00') + ntry('25.00', status='PDNG'), transactions_summary=summary())]))
        result = recheck_native_controls(native, readings)
        self.assertEqual(result['mapped_rows'], 1)
        self.assertEqual(result['unmapped_rows_retained'], 1)
        summary_check = next(c for c in result['checks'] if c['kind'] == 'summary')
        self.assertEqual(summary_check['result']['status'], 'unavailable')
