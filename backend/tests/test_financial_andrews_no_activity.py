"""Source-proven quiet Andrews sections; synthetic pages, no private contents."""
import unittest
from copy import deepcopy

from services.financial.import_batches import initial_request
from services.financial.statement_admission import assess_admission
from services.financial.statement_import import StatementImportRequest
from services.financial.statement_import_andrews import andrews_no_activity_evidence
from tests.test_financial_statement_import_andrews import selected, source

ACTIVE = [
    [(15, '06/01 ID 0000 BASE SHARE SAVINGS Previous Balance'), (350, '100.00')],
    [(15, '06/03'), (75, 'Deposit Online Banking Transfer From Share 0040'), (310, '20.00'), (350, '120.00')],
    [(15, '06/21'), (75, 'Deposit Dividend'), (310, '0.13'), (350, '120.13')],
    [(15, '06/30'), (75, 'Ending Balance'), (350, '120.13')],
]
QUIET = [
    [(15, '06/01 ID 0040 FREE CHECKING Previous Balance'), (350, '200.00')],
    [(15, '06/30'), (75, 'Ending Balance'), (350, '200.00')],
]


def page(lines=None):
    return source(ACTIVE + (QUIET if lines is None else lines))


def proposal_for(data, share='0040', sources=None):
    statement, result = selected([data], share)
    evidence = andrews_no_activity_evidence(sources or [data], statement, result['rows'])
    return dict(rows=result['rows'], currency='USD', revision='a' * 64, statement_id=statement['id'],
                metadata=dict(holder='EXAMPLE PERSON', account_number='123456789 / Share ' + share,
                              institution='Andrews Federal Credit Union', period_start=statement['period_start'],
                              period_end=statement['period_end'], balance_convention='asset_balance'),
                no_activity_evidence=evidence), evidence


def admit(proposal, edit=None):
    raw = initial_request(proposal)
    if edit:
        edit(raw)
    return assess_admission(proposal, StatementImportRequest.model_validate(raw))


class AndrewsNoActivityEvidenceTests(unittest.TestCase):
    def test_adjacent_equal_endpoints_prove_the_quiet_section(self):
        data = page()
        before = deepcopy(data)
        proposal, evidence = proposal_for(data)
        self.assertTrue(evidence['verified'], evidence)
        self.assertEqual((evidence['page_number'], evidence['balance_minor']), (1, '20000'))
        self.assertEqual((evidence['period_start'], evidence['period_end']), ('2020-06-01', '2020-06-30'))
        self.assertEqual(len(evidence['opening_rect']), 4)
        result = admit(proposal)
        self.assertTrue(result['can_import'], result['blockers'])
        self.assertEqual(result['status'], 'confirmed_no_activity')
        self.assertTrue(result['no_activity_confirmed'])
        self.assertEqual(result['no_activity_basis'], 'source_verified')
        self.assertEqual(result['no_activity_evidence']['method'], evidence['method'])
        self.assertEqual(data, before)

    def test_ocr_spacing_inside_the_label_and_a_later_opening_date_are_accepted(self):
        lines = [[(15, '06/15 ID 0040 FREE CHECKING Prev ious  Balance'), (350, '200.00')], QUIET[1]]
        proposal, evidence = proposal_for(page(lines))
        self.assertTrue(evidence['verified'], evidence)
        self.assertEqual((evidence['opening_date'], evidence['closing_date']), ('2020-06-15', '2020-06-30'))
        self.assertTrue(admit(proposal)['can_import'])

    def test_section_with_payments_is_not_a_quiet_question(self):
        _, evidence = proposal_for(page(), share='0000')
        self.assertIsNone(evidence)

    def test_unread_band_between_endpoints_stays_held(self):
        # An OCR reading that lost a whole line leaves its vertical space behind.
        data = page()
        closing = data['rows'][-1]
        for cell in closing['cells']:
            cell['locator']['rect'][1] += 12000
            cell['locator']['rect'][3] += 12000
        proposal, evidence = proposal_for(data)
        self.assertFalse(evidence['verified'])
        self.assertEqual(evidence['reason'], 'unread_band')
        result = admit(proposal)
        self.assertFalse(result['can_import'])
        blocker = next(b for b in result['blockers'] if b['kind'] == 'no_activity')
        self.assertEqual(blocker['source_check'], 'unread_band')
        self.assertEqual(blocker['page'], 1)

    def test_text_from_another_table_inside_the_band_stays_held(self):
        data = page()
        other = source([[(200, 'smudge')]])
        other['table_index'] = 1
        top = data['rows'][-2]['cells'][0]['locator']['rect'][3]
        other['rows'][-1]['cells'][0]['locator']['rect'][1] = top + 500
        other['rows'][-1]['cells'][0]['locator']['rect'][3] = top + 3000
        other['rows'] = other['rows'][-1:]
        proposal, evidence = proposal_for(data, sources=[data, other])
        self.assertFalse(evidence['verified'])
        self.assertEqual(evidence['reason'], 'rows_between_endpoints')

    def test_same_table_text_numbered_out_of_order_inside_the_band_stays_held(self):
        data = page()
        closing = data['rows'][-1]
        for cell in closing['cells']:
            cell['locator']['rect'][1] += 6000
            cell['locator']['rect'][3] += 6000
        stray = deepcopy(data['rows'][-2])
        stray['row_index'] = 99
        stray['cells'] = stray['cells'][:1]
        stray['cells'][0]['expected_text'] = 'smudge'
        top = data['rows'][-2]['cells'][0]['locator']['rect'][3]
        stray['cells'][0]['locator']['rect'][1:4:2] = [top + 500, top + 3500]
        data['rows'].append(stray)
        _, evidence = proposal_for(data)
        self.assertFalse(evidence['verified'])
        self.assertEqual(evidence['reason'], 'rows_between_endpoints')

    def test_unequal_or_unreadable_or_misdated_endpoints_stay_held(self):
        cases = {
            'endpoints_differ': [QUIET[0], [(15, '06/30'), (75, 'Ending Balance'), (350, '210.00')]],
            'endpoint_unreadable': [QUIET[0], [(15, '06/30'), (75, 'Ending Balance'), (350, '2O0.00')]],
            'endpoint_dates': [QUIET[0], [(15, '06/29'), (75, 'Ending Balance'), (350, '200.00')]],
            'rows_between_endpoints': [QUIET[0], [(75, 'Funds Transfer via Mobile')], QUIET[1]],
            'endpoint_missing': [QUIET[0]],
        }
        for reason, lines in cases.items():
            with self.subTest(reason=reason):
                proposal, evidence = proposal_for(page(lines))
                if evidence is None:  # an unread line became a payment candidate
                    self.assertEqual(reason, 'rows_between_endpoints')
                    continue
                self.assertFalse(evidence['verified'])
                self.assertEqual(evidence['reason'], reason)
                self.assertFalse(admit(proposal)['can_import'])

    def test_section_continued_on_another_page_stays_held(self):
        first = source(ACTIVE + [QUIET[0], [(15, 'Continued on following page')]])
        second = source([QUIET[1]], page=2, printed_page=2, names=False)
        statement, result = selected([first, second], '0040')
        evidence = andrews_no_activity_evidence([first, second], statement, result['rows'])
        self.assertFalse(evidence['verified'])
        self.assertEqual(evidence['reason'], 'section_spans_pages')

    def test_too_few_lines_to_measure_spacing_stays_held(self):
        proposal, evidence = proposal_for(source(QUIET))
        self.assertFalse(evidence['verified'])
        self.assertEqual(evidence['reason'], 'line_spacing_unmeasured')

    def test_edited_balance_or_dates_need_the_investigator(self):
        proposal, evidence = proposal_for(page())
        ids = (evidence['opening_row_id'], evidence['closing_row_id'])

        def balances(raw):
            for row in raw['rows']:
                if row['id'] in ids:
                    row['balance_minor'] = '19000'

        def dates(raw):
            raw['period_end'] = '2020-06-29'

        for edit in (balances, dates):
            with self.subTest(edit=edit.__name__):
                result = admit(proposal, edit)
                self.assertFalse(result['can_import'])
                self.assertIn('no_activity', [b['kind'] for b in result['blockers']])
                # The investigator's own confirmation still works as before.
                def confirmed(raw, edit=edit):
                    edit(raw)
                    raw.update(no_activity_confirmed=True, no_activity_revision=result['revision'])
                again = admit(proposal, confirmed)
                if again['can_import']:
                    self.assertEqual(again['no_activity_basis'], 'investigator_confirmed')

    def test_forged_or_missing_evidence_is_not_proof(self):
        proposal, evidence = proposal_for(page())
        for forged in (None, {**evidence, 'verified': 'yes'}, {**evidence, 'balance_minor': None}, {}):
            with self.subTest(forged=forged):
                self.assertFalse(admit({**proposal, 'no_activity_evidence': forged})['can_import'])


if __name__ == '__main__':
    unittest.main()


class GroupedNoActivityConfirmationTests(unittest.TestCase):
    """The batch/files "account details" action can confirm quiet periods together."""

    def setUp(self):
        from tests import test_financial_statement_import as fixtures
        from tests.financial_reconciled_fixture import install_reconciled_source
        self.f = fixtures.StatementImportTests()
        self.f.setUp()
        install_reconciled_source(self.f, quiet=True)

    def tearDown(self):
        self.f.tearDown()

    def plan(self, changes):
        from uuid import uuid4
        from services.financial import bulk_statement_details as service
        with self.f.SessionLocal() as db:
            rows = service.list_statements(db, case_id=self.f.case.id,
                selection=service.Selection(file_ids=[self.f.file.id]))['items']
            request = service.BulkEdit(targets=[{k: row[k] for k in ('file_id', 'source_id', 'statement_id', 'revision')}
                                                for row in rows], changes=changes, request_id=uuid4())
            preview = service.preview(db, case_id=self.f.case.id, request=request)
        return service, request.model_copy(update={'preview_revision': preview['preview_revision']}), preview

    def test_one_confirmation_resolves_quiet_periods_and_records_it(self):
        from services.financial.import_batches import assess
        self.assertEqual([b['kind'] for b in assess(self.f.preview())[1]['admission']['blockers']], ['no_activity'])
        service, request, preview = self.plan(dict(no_activity_confirmed=True))
        self.assertEqual(preview['updated'], 1)
        self.assertIn('no_activity_confirmed', preview['items'][0]['changes'])
        with self.f.SessionLocal() as db:
            result = service.save(db, case_id=self.f.case.id, request=request, actor=self.f.actor)
        self.assertEqual((result['updated'], result['drafts']), (1, 1))
        proposal = self.f.preview()
        saved = proposal['saved_review']['request']
        self.assertTrue(saved['no_activity_confirmed'])
        status, summary = assess(proposal, saved)
        self.assertTrue(summary['can_import'], summary['problems'])
        self.assertEqual(summary['admission']['no_activity_basis'], 'investigator_confirmed')
        # Repeating the decision changes nothing further.
        _, _, again = self.plan(dict(no_activity_confirmed=True))
        self.assertEqual(again['updated'], 0)
        self.assertTrue(again['items'][0]['excluded_reason'])

    def test_cannot_be_mixed_with_other_changes(self):
        from services.financial.bulk_statement_details import Changes
        for other in (dict(holder='X'), dict(period_start_unprinted=True)):
            with self.subTest(other=other), self.assertRaises(ValueError):
                Changes(no_activity_confirmed=True, **other)


class GroupedNoActivityExclusionTests(GroupedNoActivityConfirmationTests):
    def setUp(self):
        from tests import test_financial_statement_import as fixtures
        from tests.financial_reconciled_fixture import install_reconciled_source
        self.f = fixtures.StatementImportTests()
        self.f.setUp()
        install_reconciled_source(self.f)

    def test_one_confirmation_resolves_quiet_periods_and_records_it(self):
        _, _, preview = self.plan(dict(no_activity_confirmed=True))
        self.assertEqual(preview['updated'], 0)
        self.assertIn('Payments are selected', preview['items'][0]['excluded_reason'])


class EndpointBalanceProvenanceTests(unittest.TestCase):
    def rows(self, closing='200.00'):
        from services.financial.statement_import_andrews import endpoint_balance_provenance
        data = page([QUIET[0], [(15, '06/30'), (75, 'Ending Balance'), (350, closing)]])
        _, result = selected([data], '0040')
        return endpoint_balance_provenance, result['rows']

    def endpoints(self, rows):
        return {r['fields']['description']: r['value_provenance'] for r in rows if r['kind'] == 'balance'}

    def test_native_and_page_ocr_methods_with_cell_coordinates(self):
        annotate, rows = self.rows()
        before = deepcopy([{k: v for k, v in r.items()} for r in rows])
        annotate(rows, [dict(page_number=1, extraction_method='native_text')])
        found = self.endpoints(rows)
        self.assertEqual({p['method'] for p in found.values()}, {'native_text'})
        self.assertEqual(found['Closing Balance']['printed_text'], '200.00')
        self.assertEqual(found['Closing Balance']['status'], 'read')
        self.assertEqual(len(found['Opening Balance']['rect']), 4)
        # Only provenance is added; no value or other field changes.
        self.assertEqual([{k: v for k, v in r.items() if k != 'value_provenance'} for r in rows], before)
        annotate(rows, [dict(page_number=1, extraction_method='tesseract_ocr')])
        self.assertEqual({p['method'] for p in self.endpoints(rows).values()}, {'page_ocr'})
        annotate(rows, [dict(page_number=1, extraction_method='tesseract_ocr', ocr_refinements=[
            dict(field='statement_page_reading', decision='image_selected')])])
        self.assertEqual({p['method'] for p in self.endpoints(rows).values()}, {'page_image_reading'})

    def test_crop_reread_is_named_with_its_original_text(self):
        annotate, rows = self.rows()
        closing = next(r for r in rows if r['fields'].get('description') == 'Closing Balance')
        cell = next(c for c in closing['source_cells'] if str(c['column_index']) == closing['fields']['balance_column'])
        annotate(rows, [dict(page_number=1, extraction_method='native_text', ocr_refinements=[
            dict(method='tesseract_native_statement_cell_consensus', field='balance', original_text='2O0.00',
                 text='200.00', source_locator=cell['locator'], observations=[{}] * 6,
                 reason='unreadable_native_statement_money')])])
        found = self.endpoints(rows)
        self.assertEqual(found['Closing Balance']['method'], 'cell_crop_reread')
        self.assertEqual(found['Closing Balance']['reread']['original_text'], '2O0.00')
        self.assertEqual(found['Opening Balance']['method'], 'native_text')

    def test_unreadable_balance_is_reported_unread_not_filled(self):
        annotate, rows = self.rows(closing='2O0.00')
        annotate(rows, [])
        closing = self.endpoints(rows)['Closing Balance']
        self.assertEqual((closing['status'], closing['method']), ('unreadable', 'unknown'))
        self.assertNotIn('balance', next(r for r in rows if r['fields'].get('description') == 'Closing Balance')['fields'])
