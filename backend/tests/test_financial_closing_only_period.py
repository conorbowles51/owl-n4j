import hashlib
import unittest
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch
from uuid import UUID, uuid4

from sqlalchemy import select

from services.financial import closing_only_period as module
from services.financial.closing_only_period import closing_only_period_dates
from services.financial.statement_import_merrick import merrick_statement
from tests.test_financial_statement_import_merrick import summary_statement

THIS_FILE = SimpleNamespace(id='this-file', original_filename='this.pdf')


def fact(closing_date, balance='0', *, account='1111222233334444', file_id='other-file', statement_id='previous'):
    return dict(file_id=file_id, filename=file_id + '.pdf', statement_id=statement_id, account=account,
                closing_date=closing_date, printed_statement_date='', opening=None,
                closing=dict(balance_minor=balance, page_number=1, table_index=0, row_index=105,
                             expected_text='$' + (balance or '?')))


def dates(neighbours, data=None):
    data = data or summary_statement()  # Closes 04/25/21; Previous Balance $0.00.
    selected = merrick_statement(data)
    with patch.object(module, '_case_facts', return_value=neighbours):
        return closing_only_period_dates(None, case_id='case', file=THIS_FILE, selected=selected,
                                         sources=[data], currency='USD', cache={})


class ClosingOnlyPeriodRuleTests(unittest.TestCase):
    def test_previous_statement_with_matching_balance_establishes_the_start(self):
        result = dates([fact('2021-03-25')])
        self.assertEqual((result['period_start'], result['period_end']), ('2021-03-26', '2021-04-25'))
        self.assertEqual(result['period_end_basis'], 'printed_statement_date')
        self.assertEqual(result['period_start_basis'], 'previous_statement_closing_date')
        self.assertIsNone(result['period_start_hold'])
        evidence = result['period_start_evidence']
        self.assertEqual(evidence['previous_closing_date'], '2021-03-25')
        self.assertEqual(evidence['previous_evidence_file_id'], 'other-file')
        # Both balance cells the corroboration rests on are retained.
        self.assertEqual(evidence['this_previous_balance']['expected_text'], '$0.00')
        self.assertEqual(evidence['this_previous_balance']['balance_minor'], '0')
        self.assertEqual(evidence['previous_new_balance']['balance_minor'], '0')

    def test_without_a_previous_statement_the_end_is_filled_and_the_start_held_with_a_reason(self):
        for neighbours in ([], [fact('2021-02-25')],  # a skipped month is not the previous statement
                           [fact('2021-03-25', account='9999222233334444')],  # another card
                           [fact('2021-05-25')]):  # a later statement
            result = dates(neighbours)
            self.assertEqual(result['period_end'], '2021-04-25')
            self.assertEqual(result['period_start'], '')
            self.assertIsNone(result['period_start_evidence'])
            self.assertEqual(result['period_start_hold']['code'], 'no_previous_statement')
            self.assertIn('prints only its closing date', result['period_start_hold']['message'])

    def test_an_intervening_or_second_candidate_statement_holds_the_start(self):
        for neighbours in ([fact('2021-03-25'), fact('2021-04-10', statement_id='odd')],
                           [fact('2021-03-25'), fact('2021-03-29', statement_id='other')]):
            result = dates(neighbours)
            self.assertEqual(result['period_start'], '')
            self.assertEqual(result['period_start_hold']['code'], 'several_previous_statements')

    def test_balance_continuity_is_required_and_never_repaired(self):
        self.assertEqual(dates([fact('2021-03-25', balance='100')])['period_start_hold']['code'], 'balance_mismatch')
        self.assertEqual(dates([fact('2021-03-25', balance=None)])['period_start_hold']['code'], 'balance_unreadable')
        # This statement's Previous Balance without its dollar sign may carry an
        # extra digit, so it cannot corroborate the previous statement.
        data = summary_statement()
        data['rows'][3]['cells'][1]['expected_text'] = '0.00'
        result = dates([fact('2021-03-25')], data)
        self.assertEqual((result['period_start'], result['period_start_hold']['code']), ('', 'balance_unreadable'))

    def test_exact_copies_of_the_previous_statement_must_agree(self):
        agreeing = dates([fact('2021-03-25'), fact('2021-03-25', file_id='copy')])
        self.assertEqual(agreeing['period_start'], '2021-03-26')
        self.assertEqual(agreeing['period_start_evidence']['copies'], 2)
        disagreeing = dates([fact('2021-03-25'), fact('2021-03-25', balance='5', file_id='copy')])
        self.assertEqual(disagreeing['period_start_hold']['code'], 'balance_mismatch')

    def test_another_reading_of_this_statement_is_not_its_predecessor(self):
        result = dates([fact('2021-04-25', file_id='reread', statement_id='same')])
        self.assertEqual(result['period_start_hold']['code'], 'no_previous_statement')

    def test_no_dates_for_other_layouts_or_unreadable_or_conflicting_closing_dates(self):
        data = summary_statement()
        selected = merrick_statement(data)
        for changed in (dict(layout_id='credit-one-card'), dict(statement_date=''), dict(date_conflict=True)):
            with patch.object(module, '_case_facts', return_value=[fact('2021-03-25')]):
                self.assertIsNone(closing_only_period_dates(None, case_id='case', file=THIS_FILE,
                    selected={**selected, **changed}, sources=[data], currency='USD', cache={}))

    def test_a_partial_card_number_cannot_identify_the_previous_statement(self):
        data = summary_statement()
        selected = {**merrick_statement(data), 'account_reference': '**** 4444'}
        with patch.object(module, '_case_facts', return_value=[fact('2021-03-25')]):
            result = closing_only_period_dates(None, case_id='case', file=THIS_FILE, selected=selected,
                                               sources=[data], currency='USD', cache={})
        self.assertEqual((result['period_start'], result['period_start_hold']['code']), ('', 'no_previous_statement'))


def _install(db, file, data, content='MERRICK BANK\nStatement Date\n'):
    from postgres.models.evidence import EvidenceDocumentText, EvidenceTableGeometry
    from tests.test_financial_pdf_geometry_candidates import rectangle
    job = uuid4()
    payload = [dict(table_source='drawn_geometry', geometry_source='cell_rectangles',
                    table=dict(page=1, table=rectangle(0, x=0, width=600, height=800), unlocated_values=0,
                               values=[dict(row=r['row_index'], column=c['column_index'], text=c['expected_text'],
                                            locator=c['locator']) for r in data['rows'] for c in r['cells']]))]
    text = db.get(EvidenceDocumentText, file.id)
    if text is None:
        text = EvidenceDocumentText(evidence_file_id=file.id, source_locations=[])
        db.add(text)
    text.content, text.engine_job_id = content, job
    text.content_sha256, text.character_count = hashlib.sha256(content.encode()).hexdigest(), len(content)
    geometry = db.get(EvidenceTableGeometry, (file.id, 1))
    if geometry is None:
        db.add(EvidenceTableGeometry(evidence_file_id=file.id, page_number=1, engine_job_id=job, payload=payload))
    else:
        geometry.payload, geometry.engine_job_id = payload, job
    db.commit()


def previous_statement():
    data = summary_statement()
    data['rows'][7]['cells'][0]['expected_text'] = 'Statement Date: 03/25/21'
    data['rows'][5]['cells'][1]['expected_text'] = '$0.00'  # New Balance
    return data


class ClosingOnlyPeriodImportTests(unittest.TestCase):
    def setUp(self):
        from tests import test_financial_statement_import as fixtures
        module._memo.clear()
        self.f = fixtures.StatementImportTests()
        self.f.setUp()
        _install(self.f.db, self.f.file, summary_statement())
        self.previous = self.f.evidence('b' * 64)
        _install(self.f.db, self.previous, previous_statement())

    def tearDown(self):
        self.f.tearDown()

    def preview(self):
        from services.financial.statement_import import read_statement_import
        with self.f.SessionLocal() as db:
            return read_statement_import(db, case_id=self.f.case.id, evidence_file_id=self.f.file.id, currency='USD')

    def test_previous_statement_fills_both_dates_and_the_period_records_the_start_as_derived(self):
        from postgres.models.enums import PeriodBoundsSource
        from postgres.models.financial import FinancialSourceDocument, FinancialStatementPeriod
        from services.financial.import_batches import assess, initial_request
        proposal = self.preview()
        self.assertEqual(proposal['metadata']['period_start'], '')  # nothing presented as printed
        request = initial_request(proposal)
        self.assertEqual((request['period_start'], request['period_end']), ('2021-03-26', '2021-04-25'))
        self.assertFalse(request.get('period_start_unprinted'))
        status, summary = assess(proposal, request)
        self.assertTrue(summary['can_import'], summary['problems'])
        self.assertTrue(summary['closing_only_period'])
        result = self.f.confirm(request)
        self.assertEqual(result['transaction_count'], 2)
        with self.f.SessionLocal() as db:
            period = db.scalar(select(FinancialStatementPeriod).where(
                FinancialStatementPeriod.source_document_id == UUID(result['source_document_id'])))
            self.assertEqual((str(period.period_start), str(period.period_end)), ('2021-03-26', '2021-04-25'))
            self.assertEqual(period.period_start_source, PeriodBoundsSource.derived)
            self.assertEqual(period.period_end_source, PeriodBoundsSource.printed)
            document = db.get(FinancialSourceDocument, UUID(result['source_document_id']))
            retained = document.metadata_['statement_import_original']['period_dates']
            self.assertEqual(retained['period_start_evidence']['previous_evidence_file_id'], str(self.previous.id))

    def test_the_revision_does_not_depend_on_the_previous_statement(self):
        before = self.preview()
        from services.financial.file_visibility import financial_file_visibility
        with patch('services.financial.file_visibility.financial_file_visibility',
                   side_effect=lambda file: {**financial_file_visibility(file),
                                             'financial_removed': file.id == self.previous.id}):
            after = self.preview()
        self.assertEqual(before['revision'], after['revision'])
        self.assertEqual(after['period_dates']['period_start'], '')

    def test_removed_previous_statement_holds_the_start_with_its_reason(self):
        from services.financial.file_visibility import financial_file_visibility
        from services.financial.import_batches import assess, initial_request
        with patch('services.financial.file_visibility.financial_file_visibility',
                   side_effect=lambda file: {**financial_file_visibility(file),
                                             'financial_removed': file.id == self.previous.id}):
            proposal = self.preview()
        request = initial_request(proposal)
        self.assertEqual((request['period_start'], request['period_end']), ('', '2021-04-25'))
        _, summary = assess(proposal, request)
        self.assertFalse(summary['can_import'])
        held = [p for p in summary['problems'] if p.get('field') == 'period_start']
        self.assertEqual(len(held), 1)
        self.assertEqual(held[0]['source_check'], 'no_previous_statement')
        self.assertIn('previous statement for this card', held[0]['message'])
        # The investigator's existing decision still applies and is recorded as such.
        request['period_start_unprinted'] = True
        self.assertTrue(assess(proposal, request)[1]['can_import'])

    def test_a_start_typed_by_the_investigator_is_not_recorded_as_derived(self):
        from postgres.models.enums import PeriodBoundsSource
        from postgres.models.financial import FinancialStatementPeriod
        from services.financial.import_batches import initial_request
        request = initial_request(self.preview())
        request['period_start'] = '2021-03-27'
        result = self.f.confirm(request)
        with self.f.SessionLocal() as db:
            period = db.scalar(select(FinancialStatementPeriod).where(
                FinancialStatementPeriod.source_document_id == UUID(result['source_document_id'])))
            self.assertEqual(str(period.period_start), '2021-03-27')
            self.assertNotEqual(period.period_start_source, PeriodBoundsSource.derived)


if __name__ == '__main__':
    unittest.main()
