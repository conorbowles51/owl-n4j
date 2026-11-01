import unittest
from unittest import mock

from sqlalchemy.orm import Session

from services import manual_changes as mc
from services import manual_changes_backfill as bf
from tests.test_manual_changes import CASE, FeedTestBase


def source(session, users):
    for n in range(3):
        yield dict(kind='statement_details', change_type='change', case_id=CASE, subject=('source_document', f'd{n}'),
                   before={'holder': 'A'}, after={'holder': 'B'}, actor=dict(name='Alex', email='alex@example.com'),
                   reason='printed B', field='holder', producer='santander@3', layout='Santander',
                   source_ref=f'statement-details:d{n}:1')
    yield dict(kind='account_details_confirm', change_type='confirm', case_id=CASE, subject=('account', 'a1'),
               before=None, after=None, actor=dict(name='Jobs', email='jobs-verify@loupe.invalid'), reason='',
               field='holder', producer='', layout='', source_ref='account-details-confirm:a1:1')


class BackfillTests(FeedTestBase):
    def run_backfill(self, apply):
        with Session(self.engine) as session, mock.patch.object(bf, '_users', return_value={}):
            return bf.backfill(session, apply=apply, sources=(source,))

    def test_a_dry_run_counts_and_writes_nothing(self):
        out = self.run_backfill(False)
        self.assertEqual((out['patterns'], out['changes'], out['kinds']['statement_details']), (1, 3, 3))
        self.assertEqual(self.lines(), [])

    def test_applied_changes_are_historic_and_a_second_run_adds_nothing(self):
        out = self.run_backfill(True)
        self.assertEqual(out['tests'], {'account_details_confirm': 1})
        lines = self.lines()
        self.assertEqual(len(lines), 4)
        self.assertTrue(all(line['historic'] and line['source'] == 'backfill' for line in lines))
        self.assertEqual([line['test'] for line in lines], [False, False, False, True])
        again = self.run_backfill(True)
        self.assertEqual((again['skipped_already_recorded'], len(self.lines())), (4, 4))


class PersonTests(unittest.TestCase):
    def test_models_and_systems_are_not_people(self):
        for name, email, origin in (('Claude (for Neil Byrne)', 'neil@x', None), ('Neil Byrne (via Claude)', '', None),
                                    ('System', '', None), ('Batch review', '', None), ('x', 'a@system.local', None),
                                    ('DeepSeek (for Neil Byrne)', 'neil@x', None), ('Alex', 'a@x', {'model': 'm'})):
            self.assertFalse(bf.is_person(name, email, origin), name)
        self.assertTrue(bf.is_person('Alexandra Solórzano', 'asolorzano@owlconsultancygroup.com'))
        self.assertTrue(bf.is_person('Neil Byrne', 'neil@owlconsultancygroup.com'))


if __name__ == '__main__':
    unittest.main()
