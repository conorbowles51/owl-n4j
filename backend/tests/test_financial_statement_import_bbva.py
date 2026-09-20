"""Synthetic BBVA layout regressions; no customer document or account data."""
from copy import deepcopy
from unittest import TestCase
from uuid import UUID
from sqlalchemy import select

from services.financial.statement_import_bbva import bbva_catalog, propose_bbva_statement
from services.financial.statement_currency import detect_statement_currency
from services.financial.statement_review_checks import check_statement_rows


def source(rows, page=2, table=0):
    return dict(page_number=page, table_index=table, source_revision='a'*64,
                table_source='text_alignment', rows=[dict(row_index=i, cells=[
        dict(column_index=j, expected_text=value, locator=dict(kind='page_rectangle', page=page,
             rect=[x, 20000+i*15000, x+width, 30000+i*15000], page_size=[612000, 792000],
             units='millipoints', space='pdf_displayed')) for j, (x, width, value) in enumerate(cells)])
        for i, cells in enumerate(rows)])


def header(page):
    return [[(490000, 100000, 'Estado de Cuenta')],
            [(410000, 180000, 'CASH MANAGEMENT EUROS C INTS.')],
            [(530000, 60000, f'PAGINA {page} / 7')],
            [(330000, 120000, 'No. Cuenta'), (470000, 125000, '0000012345')],
            [(9000, 400000, 'BBVA MEXICO, S.A., INSTITUCION DE BANCA MULTIPLE')]]


COLUMNS = [(18000, 24000, 'OPER'), (51000, 14000, 'LIQ'), (86000, 80000, 'COD. DESCRIPCIÓN'),
           (230000, 54000, 'REFERENCIA'), (362000, 36000, 'CARGOS'), (422000, 37000, 'ABONOS'),
           (475000, 50000, 'OPERACIÓN'), (539000, 55000, 'LIQUIDACIÓN')]


def statement(empty=False):
    metadata = source([
        [(306000, 127000, 'Periodo\nFecha de Corte\nNo. de Cuenta'), (433000, 166000, 'DEL 01/09/2024 AL 30/09/2024')],
        [(433000, 166000, '30/09/2024')], [(433000, 166000, '0000012345')]])
    # The merged label is a ruled cell; subsequent values keep their column.
    for row in metadata['rows'][1:]:
        row['cells'][0]['column_index'] = 1
    body = header(2) + [
        [(9000, 180000, 'Información Financiera'), (490000, 100000, 'MONEDA EUROS')],
        [(316000, 130000, 'Saldo de Liquidación Inicial'), (579000, 21000, '60.00')],
        [(316000, 130000, 'Saldo de Operación Inicial'), (579000, 21000, '60.00')],
        [(316000, 100000, 'Depósitos / Abonos (+)'), (460000, 5000, '0'), (579000, 21000, '0.00')],
        [(316000, 100000, 'Retiros / Cargos (-)'), (460000, 5000, '0' if empty else '2'), (579000, 21000, '0.00' if empty else '34.80')],
        [(316000, 100000, 'Saldo Final (+)'), (579000, 21000, '60.00' if empty else '25.20')],
        [(316000, 130000, 'Saldo de Operación Final'), (579000, 21000, '60.00' if empty else '25.20')],
        [(9000, 200000, 'Detalle de Movimientos Realizados')], COLUMNS]
    if not empty:
        body += [[(9750, 28000, '02/SEP'), (52830, 170000, '01/SEP C49 ACCOUNT FEE'), (377000, 21000, '30.00')],
                 [(86000, 200000, 'FOR ACCOUNT SERVICE Ref.')], [(86000, 150000, 'SYNTHETIC-REFERENCE')],
                 [(9750, 28000, '02/SEP'), (52830, 170000, '01/SEP C50 IVA ACCOUNT FEE'),
                  (382000, 16000, '4.80'), (505000, 21000, '25.20'), (573000, 21000, '25.20')]]
    body += [[(250000, 110000, 'Estimado Cliente,')]]
    continued = header(3) + [COLUMNS] + ([] if empty else [[(86000, 18000, '16%')]]) + [[(9750, 200000, 'Total de Movimientos')]]
    # Same-word chart, disclosures, glossary and fiscal text must not create payments.
    other = header(7) + [[(20000, 550000, 'Nombre del Receptor : SYNTHETIC COMPANY SA DE CV')],
        [(20000, 180000, 'Depósitos / Abonos (+)'), (230000, 40000, '0.00'), (310000, 40000, '0.00%'), (360000, 10000, 'B')]]
    other += [[(20000, 500000, f'Synthetic disclosure or glossary line {i}')] for i in range(250)]
    # Keep synthetic geometry inside the page even for the long-text case.
    misc = source(other, page=7)
    for i, row in enumerate(misc['rows']):
        for cell in row['cells']:
            cell['locator']['rect'][1:4:2] = [10000+i*2000, 11000+i*2000]
    return [metadata, source(body, table=1), source(continued, page=3), misc]


class BbvaProposalTests(TestCase):
    def proposal(self, sources=None):
        sources = sources or statement()
        choices, handled = bbva_catalog(sources)
        self.assertEqual(len(choices), 1)
        self.assertEqual(len(handled), len(sources))
        return choices[0], propose_bbva_statement(sources, 'EUR', choices[0])

    def test_real_columns_produce_two_charges_and_balances_not_hundreds_of_rows(self):
        sources = statement()
        before = deepcopy(sources)
        choice, proposal = self.proposal(sources)
        self.assertEqual(choice['holder'], 'SYNTHETIC COMPANY SA DE CV')
        self.assertEqual(choice['account_reference'], '0000012345')
        self.assertEqual(choice['period_start'], '2024-09-01')
        self.assertEqual(detect_statement_currency(sources), 'EUR')
        rows = proposal['rows']; payments = [r for r in rows if not r['excluded']]
        self.assertEqual([r['fields']['amount_minor'] for r in payments], ['3000', '480'])
        self.assertTrue(all(r['fields']['direction'] == 'debit' for r in payments))
        self.assertEqual(payments[0]['fields']['date'], '2024-09-02')
        self.assertEqual(payments[0]['fields']['value_date'], '2024-09-01')
        self.assertIn('SYNTHETIC-REFERENCE', payments[0]['fields']['description'])
        self.assertTrue(payments[1]['fields']['description'].endswith('16%'))
        self.assertEqual(payments[1]['continuation_sources'][0]['page_number'], 3)
        self.assertFalse(any(r['issues'] for r in rows))
        checks = check_statement_rows(rows)
        self.assertEqual(checks['balance_status'], 'matches')
        self.assertTrue(all(c['status'] == 'matches' for c in checks['checks']))
        self.assertEqual(len(rows), sum(len(s['rows']) for s in sources))
        self.assertEqual(sources, before)

    def test_balance_only_statement_has_no_incomplete_payments(self):
        _, p = self.proposal(statement(empty=True))
        self.assertFalse(any(not r['excluded'] for r in p['rows']))
        self.assertEqual(check_statement_rows(p['rows'])['balance_status'], 'matches')

    def test_older_holder_address_and_spanish_currency_labels(self):
        sources = statement(empty=True)
        for item in sources:
            for row in item['rows']:
                for cell in row['cells']:
                    if cell['expected_text'].startswith('Nombre del Receptor'):
                        cell['expected_text'] = 'Fiscal information'
        sources.append(source([[(9000, 210000, 'EXAMPLE HOLDINGS SA DE CV')]], table=5))
        choice, _ = self.proposal(sources)
        self.assertEqual(choice['holder'], 'EXAMPLE HOLDINGS SA DE CV')
        for label, code in [('DÓLARES', 'USD'), ('PESOS', 'MXN'), ('EUROS', 'EUR')]:
            changed = deepcopy(sources)
            for item in changed:
                for row in item['rows']:
                    for cell in row['cells']:
                        if cell['expected_text'] == 'MONEDA EUROS':
                            cell['expected_text'] = 'MONEDA ' + label
            self.assertEqual(detect_statement_currency(changed, layout_id=choice['layout_id']), code)
        self.assertEqual(detect_statement_currency([source([[(0, 100, 'MONEDA DÓLARES')]])]), '')

    def test_older_bancomer_balance_only_layout_keeps_balances_and_metadata(self):
        sources = statement(empty=True)
        for s in sources:
            for row in s['rows']:
                for cell in row['cells']:
                    cell['expected_text'] = cell['expected_text'].replace('BBVA MEXICO, S.A.', 'BBVA BANCOMER, S.A.').replace('60.00', '1,817.77')
        choice, proposal = self.proposal(sources)
        self.assertEqual(choice['account_reference'], '0000012345')
        self.assertFalse(any(not r['excluded'] for r in proposal['rows']))
        self.assertEqual([r['fields']['balance'] for r in proposal['rows'] if r['kind'] == 'balance'], ['181777', '181777'])
        self.assertEqual(check_statement_rows(proposal['rows'])['balance_status'], 'matches')

    def test_operational_balances_are_not_mixed_with_liquidation_balances(self):
        sources = statement()
        for row in sources[1]['rows']:
            if row['cells'][0]['expected_text'] in ('Saldo de Liquidación Inicial', 'Saldo Final (+)'):
                row['cells'][-1]['expected_text'] = '999.00'
            if any('C50' in c['expected_text'] for c in row['cells']):
                row['cells'][-1]['expected_text'] = '999.00'
        _, proposal = self.proposal(sources)
        self.assertEqual(check_statement_rows(proposal['rows'])['balance_status'], 'matches')
        self.assertEqual([r['fields']['balance'] for r in proposal['rows'] if r['kind'] == 'balance'], ['6000', '2520'])

    def test_missing_fee_is_flagged_by_the_printed_count_and_amount(self):
        sources = statement()
        sources[1]['rows'] = [r for r in sources[1]['rows'] if not any(
            'C49' in c['expected_text'] or c['expected_text'] in ('FOR ACCOUNT SERVICE Ref.', 'SYNTHETIC-REFERENCE') for c in r['cells'])]
        _, p = self.proposal(sources)
        self.assertTrue(any('identified 1' in issue for r in p['rows'] for issue in r['issues']))
        self.assertEqual(check_statement_rows(p['rows'])['balance_status'], 'difference')

    def test_damaged_amount_stays_a_transaction_to_correct(self):
        sources = statement()
        row = next(r for r in sources[1]['rows'] if any('C49' in c['expected_text'] for c in r['cells']))
        row['cells'][-1]['expected_text'] = '3O.OO'
        _, p = self.proposal(sources)
        payments = [r for r in p['rows'] if not r['excluded']]
        self.assertEqual(len(payments), 2)
        self.assertNotIn('amount_minor', payments[0]['fields'])
        self.assertTrue(payments[0]['issues'])

    def test_unknown_currency_does_not_use_the_filename_or_mexican_address(self):
        sources = statement()
        for s in sources:
            for r in s['rows']:
                for c in r['cells']:
                    if c['expected_text'] == 'MONEDA EUROS': c['expected_text'] = 'MONEDA SIN IDENTIFICAR'
        self.assertEqual(detect_statement_currency(sources), '')

    def test_continuation_cannot_borrow_another_accounts_period(self):
        sources = statement()
        for r in sources[2]['rows']:
            for c in r['cells']:
                if c['expected_text'] == '0000012345': c['expected_text'] = '0000098765'
        choices, handled = bbva_catalog(sources)
        self.assertEqual(len(choices), 1)
        self.assertNotIn((3, 0), handled)

    def test_two_periods_in_one_pdf_keep_separate_dates_and_rows(self):
        first = statement()
        second = deepcopy(first)
        for s in second:
            s['page_number'] += 7
            for r in s['rows']:
                for c in r['cells']:
                    c['locator']['page'] += 7
                    c['expected_text'] = c['expected_text'].replace('09/2024', '10/2024').replace('/SEP', '/OCT')
        choices, handled = bbva_catalog(first+second)
        self.assertEqual(len(choices), 2)
        self.assertEqual(len(handled), 8)
        self.assertEqual({c['period_start'] for c in choices}, {'2024-09-01', '2024-10-01'})
        for choice in choices:
            selected = [s for s in first+second if s['page_number'] in choice['page_numbers']]
            payments = [r for r in propose_bbva_statement(selected, 'EUR', choice)['rows'] if not r['excluded']]
            self.assertEqual(len(payments), 2)
            self.assertTrue(all(r['fields']['date'][5:7] == choice['period_start'][5:7] for r in payments))


class BbvaImportTests(TestCase):
    def setUp(self):
        from tests.test_financial_statement_import import StatementImportTests
        self.fixture = StatementImportTests('test_existing_import_and_same_request_keep_the_saved_account_for_navigation')
        self.fixture.setUp()

    def tearDown(self):
        self.fixture.tearDown()

    def prepare(self, empty=False):
        from postgres.models.evidence import EvidenceDocumentText, EvidenceTableGeometry
        from services.financial.statement_import import read_statement_import
        from services.financial.import_batches import initial_request
        f = self.fixture
        for old in list(f.db.scalars(select(EvidenceTableGeometry))): f.db.delete(old)
        f.db.flush()
        document = f.db.get(EvidenceDocumentText, f.file.id)
        sources = statement(empty)
        for page in sorted({s['page_number'] for s in sources}):
            payload = [dict(table_source=s['table_source'], geometry_source='cell_rectangles', table=dict(page=page,
                table=dict(kind='page_rectangle', page=page, rect=[0,0,612000,792000], page_size=[612000,792000], units='millipoints', space='pdf_displayed'),
                unlocated_values=0, values=[dict(row=r['row_index'], column=c['column_index'], text=c['expected_text'], locator=c['locator'])
                    for r in s['rows'] for c in r['cells']])) for s in sources if s['page_number'] == page]
            f.db.add(EvidenceTableGeometry(evidence_file_id=f.file.id, page_number=page, engine_job_id=document.engine_job_id, payload=payload))
        f.db.commit()
        proposal = read_statement_import(f.db, case_id=f.case.id, evidence_file_id=f.file.id)
        return proposal, initial_request(proposal)

    def test_import_and_retry_retain_two_payments_balances_dates_and_sources(self):
        self.check_import(False, 2, 2520)

    def test_balance_only_import_and_retry_save_the_account_and_no_fake_payments(self):
        self.check_import(True, 0, 6000)

    def test_later_account_and_balance_changes_keep_the_original_citations(self):
        from uuid import UUID
        from copy import deepcopy
        from postgres.models.financial import FinancialSourceDocument, FinancialStatementPeriod
        from services.financial.statement_details import read_statement_details, update_statement_details, StatementDetailsRequest
        from services.financial.statement_import_controls import read_import_controls
        _, request = self.prepare()
        receipt = self.fixture.confirm(request)
        source_id = UUID(receipt['source_document_id'])
        with self.fixture.SessionLocal() as db:
            original = deepcopy(db.get(FinancialSourceDocument, source_id).metadata_['statement_import_controls'])
            view = read_statement_details(db, case_id=self.fixture.case.id, source_id=source_id)
            changed = update_statement_details(db, case_id=self.fixture.case.id, source_id=source_id,
                request=StatementDetailsRequest(expected_revision=view['revision'], holder=view['details']['holder'],
                    institution=view['details']['institution'], account_number='00987654321', closing={'amount_minor': '2500', 'page': 2}),
                actor=self.fixture.actor)
            source = db.get(FinancialSourceDocument, source_id)
            period = db.get(FinancialStatementPeriod, UUID(changed['period_id']))
            controls = read_import_controls(period, source, self.fixture.file)
            self.assertEqual(source.metadata_['statement_import_controls'], original)
            self.assertEqual(next(c for c in controls['controls'] if c['role'] == 'opening')['original_text'], original['controls'][0]['original_text'])
            self.assertEqual(next(c for c in controls['controls'] if c['role'] == 'closing')['reviewed_value'], '2500')

    def test_reprocessed_import_replaces_incomplete_rows_and_preserves_the_old_reading(self):
        from pathlib import Path
        from uuid import uuid4
        from unittest.mock import patch
        from postgres.models.evidence import EvidenceDocumentText, EvidenceTableGeometry
        from postgres.models.financial import FinancialSourceDocument
        from services.financial.statement_reprocessing import create_statement_version
        from services.financial.statement_import import read_statement_import
        from services.financial.import_batches import initial_request
        from services.financial.imported_records import imported_records
        f = self.fixture
        with patch('services.financial.statement_import_bbva.bbva_catalog', return_value=([], set())):
            _, request = self.prepare()
            # Reproduce the old importer, which selected all unclassified text.
            for row in request['rows']:
                row['excluded'] = False
            old = f.confirm(request)
        self.assertGreater(old['incomplete_count'], 250)
        self.assertEqual(old['transaction_count'], 0)
        original_id = f.file.id
        with f.SessionLocal() as db:
            version = create_statement_version(db, case_id=f.case.id, evidence_file_id=original_id,
                request_id=uuid4(), actor=f.actor, resolve_path=Path)
            document = db.get(EvidenceDocumentText, original_id)
            db.add(EvidenceDocumentText(evidence_file_id=version.id, content=document.content, content_sha256=document.content_sha256,
                character_count=document.character_count, engine_job_id=document.engine_job_id, source_locations=deepcopy(document.source_locations)))
            for geometry in db.scalars(select(EvidenceTableGeometry).where(EvidenceTableGeometry.evidence_file_id == original_id)):
                db.add(EvidenceTableGeometry(evidence_file_id=version.id, page_number=geometry.page_number,
                    engine_job_id=geometry.engine_job_id, payload=deepcopy(geometry.payload)))
            db.commit()
            version_id = version.id
        f.file = f.db.get(type(f.file), version_id)
        p = read_statement_import(f.db, case_id=f.case.id, evidence_file_id=version_id)
        self.assertEqual(p['current_import']['source_document_id'], old['source_document_id'])
        request = initial_request(p)
        request.update(replaces_source_document_id=old['source_document_id'], replacement_revision=p['current_import']['revision'],
                       details_reason='Recognised BBVA layout replaces summary text wrongly imported as payments.')
        receipt = f.confirm(request)
        self.assertEqual(receipt['transaction_count'], 2)
        self.assertEqual(receipt['incomplete_count'], 0)
        self.assertFalse(f.confirm(request)['created'])
        with f.SessionLocal() as db:
            retained = db.get(FinancialSourceDocument, UUID(old['source_document_id']))
            self.assertEqual(len(retained.metadata_['statement_incomplete_records']), old['incomplete_count'])
            self.assertEqual(imported_records(db, case_id=f.case.id, account_id=None, start_date=None, end_date=None)['total'], 0)

    def test_legacy_empty_import_can_be_refreshed_in_place_without_reupload(self):
        from pathlib import Path
        from unittest.mock import patch
        from services.financial.legacy_statement_refresh import refresh_legacy_import
        from services.financial.statement_import import read_statement_import
        from services.financial.imported_records import imported_records
        from postgres.models.financial import FinancialSourceDocument, FinancialTransaction
        f = self.fixture
        with patch('services.financial.statement_import_bbva.bbva_catalog', return_value=([], set())):
            _, request = self.prepare()
            for row in request['rows']:
                row['excluded'] = False
            old = f.confirm(request)
        proposal = read_statement_import(f.db, case_id=f.case.id, evidence_file_id=f.file.id)
        self.assertTrue(proposal['current_import']['refresh_available'])
        args = dict(session_factory=f.SessionLocal, case_id=f.case.id, source_id=UUID(old['source_document_id']),
            expected_revision=proposal['current_import']['revision'], actor=f.actor, resolve_path=Path)
        from uuid import uuid4
        from services.financial.pdf_candidates import PdfMappingError
        from services.financial.legacy_statement_refresh import refresh_available
        from services.financial import import_batches
        from postgres.models.financial_import_batches import FinancialImportBatchItem
        with f.SessionLocal() as db:
            batch_id = import_batches.create_batch(db, case_id=f.case.id, request_id=uuid4(), file_ids=[f.file.id], folder_ids=[], actor=f.actor)
            db.add(FinancialImportBatchItem(id=uuid4(), batch_id=batch_id, file_id=f.file.id,
                statement_key=proposal['statement_id'] or '', status='imported', summary={'source_document_id': old['source_document_id']}))
            db.commit()
        with self.assertRaisesRegex(PdfMappingError, 'not found'):
            refresh_legacy_import(**{**args, 'case_id': uuid4()})
        with self.assertRaisesRegex(PdfMappingError, 'changed'):
            refresh_legacy_import(**{**args, 'expected_revision': '0'*64})
        with f.SessionLocal() as db:
            original = db.get(FinancialSourceDocument, args['source_id'])
            metadata = deepcopy(original.metadata_)
            metadata['statement_incomplete_records'][0]['correction'] = {'description': 'Saved investigator correction'}
            original.metadata_ = metadata
            self.assertFalse(refresh_available(db, original, proposal))
            db.rollback()
        new = refresh_legacy_import(**args)
        self.assertEqual((new['transaction_count'], new['incomplete_count']), (2, 0))
        self.assertEqual(new['evidence_file_id'], str(f.file.id))
        self.assertFalse(refresh_legacy_import(**args)['created'])
        with f.SessionLocal() as db:
            self.assertEqual(imported_records(db, case_id=f.case.id)['total'], 0)
            self.assertEqual(len(list(db.scalars(select(FinancialTransaction)))), 2)
            prior = db.get(FinancialSourceDocument, UUID(old['source_document_id']))
            self.assertEqual(prior.status, 'superseded')
            self.assertGreater(len(prior.metadata_['statement_incomplete_records']), 250)
            from services.financial.batch_import_history import current_imports
            current = current_imports(db, f.case.id, [prior.id])[str(prior.id)]
            self.assertEqual(current['source_document_id'], new['source_document_id'])
            self.assertEqual(current['transaction_count'], 2)
            self.assertEqual(current['records'], [])
            from services.financial.batch_transaction_scope import imported_batch_scope
            opened = imported_batch_scope(db, case_id=f.case.id, batch_id=batch_id)
            self.assertEqual(opened['transaction_count'], 2)
            self.assertEqual(opened['source_document_ids'], [new['source_document_id']])

    def test_printed_count_mismatch_remains_visible_in_batch_and_import(self):
        from services.financial.import_batches import assess
        proposal, request = self.prepare()
        payments = [r for r in request['rows'] if not r['excluded']]
        payments[0]['excluded'] = True
        summary = assess(proposal, request)[1]
        self.assertTrue(any(p.get('kind') == 'transaction_count' for p in summary['problems']))
        result = self.fixture.confirm(request)
        self.assertTrue(any(p.get('kind') == 'transaction_count' for p in result['issues']))

    def check_import(self, empty, count, closing):
        from postgres.models.financial import FinancialSourceDocument, FinancialStatementPeriod, FinancialTransaction
        from services.financial.periods import read_opening, read_closing
        from services.financial.import_batches import assess
        from services.financial.statement_import_controls import read_import_controls
        f = self.fixture
        proposal, request = self.prepare(empty)
        self.assertTrue(assess(proposal, request)[1]['can_import'])
        receipt = f.confirm(request)
        self.assertEqual(receipt['transaction_count'], count)
        self.assertEqual(receipt['incomplete_count'], 0)
        self.assertFalse(f.confirm(request)['created'])
        with f.SessionLocal() as db:
            document = db.get(FinancialSourceDocument, UUID(receipt['source_document_id']))
            period = db.scalar(select(FinancialStatementPeriod).where(FinancialStatementPeriod.source_document_id == document.id))
            self.assertEqual(read_opening(period).amount.minor_units, 6000)
            self.assertEqual(read_closing(period).amount.minor_units, closing)
            self.assertEqual(document.metadata_['statement_import_original']['rows'], proposal['rows'])
            self.assertEqual(document.metadata_['statement_incomplete_records'], [])
            self.assertEqual(len(read_import_controls(period, document, f.file)['controls']), 2)
            payments = list(db.scalars(select(FinancialTransaction)))
            self.assertEqual(len(payments), count)
            if count:
                self.assertTrue(all(str(p.transaction_date) == '2024-09-02' and str(p.value_date) == '2024-09-01' for p in payments))
