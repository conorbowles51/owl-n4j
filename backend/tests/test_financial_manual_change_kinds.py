import unittest
from types import SimpleNamespace
from unittest import mock

from services.financial import manual_change_kinds as kinds

INITIAL = dict(expected_revision='r', statement_id='s1', currency='MXN', holder='JUAN PEREZ', account_number='0123',
               institution='Banco', period_start='2024-01-01', period_end='2024-01-31',
               rows=[dict(id='a', amount_minor='1000', date='2024-01-02', description='PAGO'),
                     dict(id='b', amount_minor='500', date='2024-01-03', description='CARGO')])


class RequestDiffTests(unittest.TestCase):
    def test_only_the_changed_fields_are_named(self):
        after = {**INITIAL, 'account_number': '0128',
                 'rows': [dict(INITIAL['rows'][0], amount_minor='7000'), INITIAL['rows'][1]]}
        fields, old, new = kinds.request_diff(INITIAL, after)
        self.assertEqual(fields, ['account_number', 'rows.amount_minor'])
        self.assertEqual((old['account_number'], new['account_number']), (['0123'], ['0128']))
        self.assertEqual(new['rows.amount_minor'], [{'row': 'a', 'value': '7000'}])

    def test_an_unchanged_save_names_nothing(self):
        self.assertEqual(kinds.request_diff(INITIAL, dict(INITIAL))[0], [])

    def test_added_and_removed_rows(self):
        after = {**INITIAL, 'rows': [INITIAL['rows'][0], dict(id='c', amount_minor='1')]}
        self.assertEqual(kinds.request_diff(INITIAL, after)[0], ['rows.added', 'rows.removed'])


class RecordReviewEditTests(unittest.TestCase):
    actor = SimpleNamespace(name='Alex', email='alex@example.com', user_id='u1')
    proposal = dict(statement_id='s1', statement_choices=[dict(id='s1', layout_id='santander-mexico-movements',
                                                               institution='Santander')], metadata={})

    def record(self, before, after, actor=actor):
        with mock.patch.object(kinds, '_normal', side_effect=lambda r: r), \
                mock.patch('services.manual_changes.record_change', return_value='id') as call:
            out = kinds.record_review_edit(None, kind='statement_review_edit', case_id='c', evidence_file_id='f',
                                           before=before, after=after, actor=actor, proposal=self.proposal)
        return out, call

    def test_a_changed_save_is_recorded_with_its_fields_reader_and_layout(self):
        out, call = self.record(INITIAL, {**INITIAL, 'holder': 'JUAN PERES'})
        self.assertEqual(out, 'id')
        kw = call.call_args.kwargs
        self.assertEqual((kw['field'], kw['producer'], kw['layout']),
                         ('holder', 'santander-mexico-movements', 'Santander'))

    def test_an_unchanged_save_or_a_save_by_no_person_records_nothing(self):
        self.assertEqual(self.record(INITIAL, dict(INITIAL))[1].call_count, 0)
        self.assertEqual(self.record(INITIAL, {**INITIAL, 'holder': 'X'}, actor=None)[1].call_count, 0)


if __name__ == '__main__':
    unittest.main()
