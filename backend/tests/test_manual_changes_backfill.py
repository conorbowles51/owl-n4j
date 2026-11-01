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


FILE = '0f0f0f0f-1111-2222-3333-444444444444'


def reading(holder):
    return dict(revision='r1', statement_id='s1', currency='MXN', rows=[], statement_choices=[
        dict(id='s1', layout_id='bank-reader@4', layout_fingerprint='fp7')],
        metadata=dict(holder=holder, account_number='0123', institution='Banco Ejemplo', period_start='2025-01-01',
                      period_end='2025-01-31'))


class ReviewSaveTests(FeedTestBase):
    """A historic review save whose reading is no longer the current one is compared against the reading stored
    with the statement it saved, and that record replaces the earlier "(not compared)" one."""

    def files(self, holder_saved):
        from services.financial.import_batches import initial_request
        request = dict(initial_request(reading('ACME SA')), holder=holder_saved)
        return [dict(id=FILE, case_id=CASE, progress={}, history=[dict(
            request=request, review_revision='rv1', saved_at='2025-02-01T10:00:00+00:00',
            saved_by=dict(name='Alex Reviewer', email='alex@example.com'))])]

    def run_saves(self, holder_saved, stored):
        def rows(session, sql, **params):
            if 'from evidence_files' in sql:
                return self.files(holder_saved)
            if 'statement_import_original' in sql:
                return [dict(original=stored)] if stored and params.get('rev') == 'r1' else []
            return []
        current = dict(reading('ACME SA'), revision='r2')
        with Session(self.engine) as session, mock.patch.object(bf, '_rows', rows), \
                mock.patch('services.financial.statement_import.read_statement_import', return_value=current), \
                mock.patch.object(bf, '_users', return_value={}):
            return [part for item in bf.review_saves(session, {}) for part in bf._parts(item)]

    def test_a_save_made_on_a_reading_kept_with_its_statement_is_compared(self):
        parts = self.run_saves('ACME S.A. DE C.V.', reading('ACME SA'))
        self.assertEqual([(p['field'], p['before'], p['after']) for p in parts],
                         [('holder', ['ACME SA'], ['ACME S.A. DE C.V.'])])
        self.assertEqual((parts[0]['producer'], parts[0]['layout']), ('bank-reader@4', 'fp7'))

    def test_without_a_kept_reading_the_save_stays_not_compared(self):
        parts = self.run_saves('ACME S.A. DE C.V.', None)
        self.assertEqual([p['field'] for p in parts],
                         ['(not compared: the reading this save was made on is not the current one)'])
        self.assertNotIn('replaces_ref', parts[0])

    def test_the_compared_record_replaces_the_not_compared_one_and_both_stay(self):
        def source_old(session, users):
            for item in self._old:
                yield item
        self._old = self.run_saves('ACME S.A. DE C.V.', None)
        new = self.run_saves('ACME S.A. DE C.V.', reading('ACME SA'))
        with Session(self.engine) as session, mock.patch.object(bf, '_users', return_value={}):
            bf.backfill(session, apply=True, sources=(lambda s, u: iter(self._old),))
            out = bf.backfill(session, apply=True, sources=(lambda s, u: iter(new),))
        lines = self.lines()
        self.assertEqual(len(lines), 2)
        self.assertEqual(out['replaced_records'], 1)
        self.assertEqual(lines[1]['replaces'], lines[0]['id'])
        self.assertEqual(lines[1]['field'], 'holder')

    def test_a_kept_reading_saved_unchanged_is_a_confirmation(self):
        parts = self.run_saves('ACME SA', reading('ACME SA'))
        self.assertEqual([(p['field'], p['change_type']) for p in parts], [('(saved unchanged)', 'confirm')])


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
