"""Layout memory: one confirmation per printed layout + account + missing identity fact.

Synthetic fixtures only (the invented Spanish layout of the engine tests).
"""
import hashlib
import unittest
from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy import select

from services.financial import layout_memory
from services.financial.pdf_candidates import PdfMappingError
from services.financial.statement_engine import read_statements
from tests.test_financial_statement_engine import MOVES, mx_statement

UNNAMED_TOP = 'CLIENTE 00451'  # an addressee line the engine does not accept as a name (it holds digits)


MONTHS = {'03': 'MAR', '04': 'ABR', '05': 'MAY', '06': 'JUN'}


def statement_pages(*, account='0012345678', top=UNNAMED_TOP, period='DEL 01/03/2024 AL 31/03/2024',
                    closing='1,250.00', currency_line=('MONEDA', 'PESOS')):
    month = MONTHS[period.split('/')[1]]
    moves = [(day.replace('MAR', month), *rest) for day, *rest in MOVES]
    pages = mx_statement(moves, closing=closing, period=period, currency_line=currency_line)
    for row in pages[0]['rows']:
        for cell in row['cells']:
            if cell['expected_text'] == 'EMPRESA DE PRUEBA SA DE CV':
                cell['expected_text'] = top
            if cell['expected_text'] == '0012345678':
                cell['expected_text'] = account
    return pages


def _install(db, file, pages, content='Statement\n'):
    from postgres.models.evidence import EvidenceDocumentText, EvidenceTableGeometry
    from tests.test_financial_pdf_geometry_candidates import rectangle
    job = uuid4()
    data = pages[0]
    values = []
    for row in data['rows']:
        for cell in row['cells']:
            rect = cell['locator']['rect']
            locator = dict(rectangle(0), rect=[int(v * 600 / 612) for v in rect])
            values.append(dict(row=row['row_index'], column=cell['column_index'], text=cell['expected_text'], locator=locator))
    payload = [dict(table_source='drawn_geometry', geometry_source='cell_rectangles',
                    table=dict(page=1, table=rectangle(0, x=0, width=600, height=800), unlocated_values=0, values=values))]
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


class LayoutMemoryKeyTests(unittest.TestCase):
    def one(self, **changes):
        statements = read_statements(statement_pages(**changes))
        self.assertEqual(len(statements), 1)
        return statements[0]

    def test_unaccepted_addressee_line_is_evidence_but_not_a_holder(self):
        st = self.one()
        self.assertTrue(st['engine']['proved'], st['engine'])
        self.assertEqual(st['holder'], '')
        self.assertEqual(st['identity_evidence']['holder'], [UNNAMED_TOP])
        self.assertIn('named:MXN', st['identity_evidence']['currency'])
        self.assertTrue(st['layout_key'])

    def test_key_is_shared_by_periods_and_differs_with_account_or_printed_evidence(self):
        march = layout_memory.memory_key(self.one(), 'holder')
        april = layout_memory.memory_key(self.one(period='DEL 01/04/2024 AL 30/04/2024'), 'holder')
        self.assertIsNotNone(march)
        self.assertEqual(march, april)
        self.assertNotEqual(march, layout_memory.memory_key(self.one(account='0099999999'), 'holder'))
        self.assertNotEqual(march, layout_memory.memory_key(self.one(top='CLIENTE 00452'), 'holder'))

    def test_no_printed_account_or_library_statement_never_takes_part(self):
        st = self.one()
        self.assertIsNone(layout_memory.memory_key(dict(st, account_reference=''), 'holder'))
        self.assertIsNone(layout_memory.memory_key(dict(st, layout_id='bbva-mexico-cash-management'), 'holder'))
        self.assertIsNone(layout_memory.memory_key(st, 'account_number'))

    def test_values_are_single_lines_and_currencies_are_codes(self):
        self.assertEqual(layout_memory.clean_value('holder', '  ACME   LTD '), 'ACME LTD')
        self.assertEqual(layout_memory.clean_value('currency', 'mxn'), 'MXN')
        with self.assertRaises(PdfMappingError):
            layout_memory.clean_value('currency', 'PESOS')
        with self.assertRaises(PdfMappingError):
            layout_memory.clean_value('holder', 'x' * 129)


class BatchHelpers:
    def _batch(self):
        from postgres.models.financial_import_batches import FinancialImportBatch as Batch
        from services.financial import import_batches as service
        entries = [dict(source_id=str(file.id), file_id=str(file.id), filename=name + '.pdf',
                        expected_revision='r', status='checked') for name, file in self.files.items()]
        batch_id = uuid4()
        with self.f.SessionLocal() as db:
            db.add(Batch(id=batch_id, case_id=self.f.case.id, created_by=self.f.user.id, status='preparing',
                         actor=dict(name='n', email='e@example.test', user_id=str(self.f.user.id)), files=entries))
            db.commit()
            for entry in entries:
                service.prepare_reviews(db, service.batch_for(db, self.f.case.id, batch_id), entry)
        return batch_id

    def items(self):
        from postgres.models.financial_import_batches import FinancialImportBatchItem as Item
        with self.f.SessionLocal() as db:
            by_file = {item.file_id: (item.status, dict(item.summary)) for item in db.scalars(
                select(Item).where(Item.batch_id == self.batch_id))}
        return {name: by_file[file.id] for name, file in self.files.items()}

    def groups(self):
        with self.f.SessionLocal() as db:
            return layout_memory.memory_groups(db, case_id=self.f.case.id, batch_id=self.batch_id)['groups']

    def group(self, member, field='holder'):
        return next(g for g in self.groups() if g['field'] == field
                    and any(s['file_id'] == str(self.files[member].id) for s in g['statements']))

    def confirm(self, group, value, field='holder'):
        member = group['statements'][0]
        with self.f.SessionLocal() as db:
            return layout_memory.confirm(db, case_id=self.f.case.id, file_id=member['file_id'],
                                         statement_id=member['statement_id'], field=field, value=value,
                                         expected_key=group['key'], actor=self.actor)


class LayoutMemoryBatchTests(BatchHelpers, unittest.TestCase):
    def setUp(self):
        from tests import test_financial_statement_import as fixtures
        self.f = fixtures.StatementImportTests()
        self.f.setUp()
        self.actor = SimpleNamespace(user_id=self.f.user.id, name='Investigator')
        self.files = {}
        layouts = dict(
            march=statement_pages(),
            april=statement_pages(period='DEL 01/04/2024 AL 30/04/2024'),
            other_account=statement_pages(account='0099999999'),
            other_holder_text=statement_pages(top='CLIENTE 00452', period='DEL 01/05/2024 AL 31/05/2024'),
            unproved=statement_pages(closing='1,999.00', period='DEL 01/06/2024 AL 30/06/2024'),
        )
        for index, (name, pages) in enumerate(layouts.items()):
            file = self.f.file if index == 0 else self.f.evidence(('%x' % (index + 10)) * 64)
            _install(self.f.db, file, pages)
            self.files[name] = file
        self.f.db.commit()
        self.batch_id = self._batch()

    def tearDown(self):
        self.f.tearDown()

    def test_one_confirmation_makes_every_matching_period_ready_and_nothing_else(self):
        before = self.items()
        self.assertTrue(all(status == 'attention' for status, _ in before.values()))
        group = self.group('march')
        members = {s['file_id'] for s in group['statements']}
        self.assertEqual(members, {str(self.files[n].id) for n in ('march', 'april', 'unproved')})
        self.assertEqual(group['money_proved_count'], 2)
        self.assertEqual(group['proposal'], UNNAMED_TOP)  # the printed line, offered for confirmation
        result = self.confirm(group, 'EMPRESA DE PRUEBA SA DE CV')
        self.assertEqual(result['refreshed']['refreshed'], 3)
        after = self.items()
        for name in ('march', 'april'):
            status, summary = after[name]
            self.assertEqual(status, 'ready', summary.get('problems'))
            self.assertEqual(summary['holder'], 'EMPRESA DE PRUEBA SA DE CV')
            self.assertEqual(summary['identity_memory']['holder']['confirmation_id'], result['confirmation']['id'])
        # Memory supplies only the confirmed fact: an unreconciled period stays held.
        self.assertEqual(after['unproved'][0], 'attention')
        # Other printed account / other holder text: not covered.
        for name in ('other_account', 'other_holder_text'):
            self.assertEqual(after[name][0], 'attention')
            self.assertEqual(after[name][1].get('holder', ''), '')
        # Covered periods leave the open groups; the uncovered ones stay listed.
        open_members = {s['file_id'] for g in self.groups() if g['field'] == 'holder' and not g['confirmations']
                        for s in g['statements']}
        self.assertEqual(open_members, {str(self.files[n].id) for n in ('other_account', 'other_holder_text')})

    def test_the_proposal_is_remembered_for_a_fresh_reading_and_withdrawal_holds_again(self):
        from services.financial.statement_import import read_statement_import
        result = self.confirm(self.group('march'), 'EMPRESA DE PRUEBA SA DE CV')
        with self.f.SessionLocal() as db:
            proposal = read_statement_import(db, case_id=self.f.case.id, evidence_file_id=self.files['april'].id)
        self.assertEqual(proposal['metadata']['holder'], 'EMPRESA DE PRUEBA SA DE CV')
        self.assertEqual(proposal['identity_memory']['holder']['basis'], 'layout_memory')
        with self.f.SessionLocal() as db:
            withdrawn = layout_memory.withdraw(db, case_id=self.f.case.id, confirmation_id=result['confirmation']['id'],
                                               reason='Wrong company', actor=self.actor)
        self.assertEqual(withdrawn['refreshed']['refreshed'], 3)
        after = self.items()
        self.assertEqual(after['march'][0], 'attention')
        self.assertEqual(after['april'][1].get('holder', ''), '')
        self.assertNotIn('identity_memory', after['april'][1])
        with self.f.SessionLocal() as db:
            proposal = read_statement_import(db, case_id=self.f.case.id, evidence_file_id=self.files['april'].id)
            record = layout_memory.case_confirmations(db, case_id=self.f.case.id)['confirmations']
        self.assertEqual(proposal['metadata']['holder'], '')
        self.assertEqual(len(record), 1)
        self.assertFalse(record[0]['active'])
        self.assertEqual(record[0]['withdrawal_reason'], 'Wrong company')

    def test_revision_is_unchanged_by_a_remembered_holder(self):
        from services.financial.statement_import import read_statement_import
        with self.f.SessionLocal() as db:
            before = read_statement_import(db, case_id=self.f.case.id, evidence_file_id=self.files['april'].id)['revision']
        self.confirm(self.group('march'), 'EMPRESA DE PRUEBA SA DE CV')
        with self.f.SessionLocal() as db:
            after = read_statement_import(db, case_id=self.f.case.id, evidence_file_id=self.files['april'].id)['revision']
        self.assertEqual(before, after)

    def test_conflicting_or_stale_confirmations_are_refused(self):
        group = self.group('march')
        with self.assertRaises(PdfMappingError) as stale:
            self.confirm(dict(group, key='0' * 64), 'EMPRESA DE PRUEBA SA DE CV')
        self.assertEqual(stale.exception.status_code, 409)
        self.confirm(group, 'EMPRESA DE PRUEBA SA DE CV')
        again = self.confirm(group, 'EMPRESA DE PRUEBA SA DE CV')
        self.assertTrue(again['already_confirmed'])
        with self.assertRaises(PdfMappingError) as conflict:
            self.confirm(group, 'OTRA EMPRESA SA')
        self.assertEqual(conflict.exception.status_code, 409)

    def test_a_printed_value_is_never_replaced(self):
        group = self.group('march', field='holder')
        member = group['statements'][0]
        with self.f.SessionLocal() as db:
            with self.assertRaises(PdfMappingError) as printed:
                layout_memory.confirm(db, case_id=self.f.case.id, file_id=member['file_id'],
                                      statement_id=member['statement_id'], field='currency', value='USD',
                                      expected_key=layout_memory.memory_key(
                                          read_statements(statement_pages())[0], 'currency'), actor=self.actor)
        self.assertIn('printed', str(printed.exception))


class LayoutMemoryCurrencyTests(BatchHelpers, unittest.TestCase):
    """A layout that prints no currency: one confirmation reads every matching period's amounts."""

    def setUp(self):
        from tests import test_financial_statement_import as fixtures
        self.f = fixtures.StatementImportTests()
        self.f.setUp()
        self.actor = SimpleNamespace(user_id=self.f.user.id, name='Investigator')
        self.files = {}
        for index, (name, period) in enumerate((('march', 'DEL 01/03/2024 AL 31/03/2024'),
                                               ('april', 'DEL 01/04/2024 AL 30/04/2024'))):
            file = self.f.file if index == 0 else self.f.evidence(('%x' % (index + 10)) * 64)
            _install(self.f.db, file, statement_pages(top='EMPRESA DE PRUEBA SA DE CV', period=period, currency_line=None))
            self.files[name] = file
        self.f.db.commit()
        self.batch_id = self._batch()

    def tearDown(self):
        self.f.tearDown()

    def test_currency_confirmation_reads_the_amounts_and_withdrawal_holds_again(self):
        items = self.items()
        self.assertTrue(all(status == 'attention' and not summary.get('currency') for status, summary in items.values()))
        group = self.group('march', field='currency')
        self.assertEqual(len(group['statements']), 2)
        result = self.confirm(group, 'MXN', field='currency')
        after = self.items()
        for status, summary in after.values():
            self.assertEqual(status, 'ready', summary.get('problems'))
            self.assertEqual(summary['currency'], 'MXN')
            self.assertEqual(summary['identity_memory']['currency']['value'], 'MXN')
        with self.f.SessionLocal() as db:
            layout_memory.withdraw(db, case_id=self.f.case.id, confirmation_id=result['confirmation']['id'],
                                   reason='Dollar account', actor=self.actor)
        for status, summary in self.items().values():
            self.assertEqual(status, 'attention')
            self.assertEqual(summary.get('currency') or '', '')


if __name__ == '__main__':
    unittest.main()


class LayoutMemoryRouteTests(unittest.TestCase):
    def test_each_layout_memory_path_resolves_to_its_own_endpoint(self):
        from starlette.routing import Match
        from routers.financial_statement_import import router
        cases = {('GET', '/api/financial/statement-import/batches/' + str(uuid4()) + '/layout-memory'): 'batch_layout_memory_groups',
                 ('GET', '/api/financial/statement-import/layout-memory/confirmations'): 'case_layout_memory',
                 ('POST', '/api/financial/statement-import/layout-memory/confirm'): 'confirm_layout_memory',
                 ('POST', '/api/financial/statement-import/layout-memory/' + str(uuid4()) + '/withdraw'): 'withdraw_layout_memory'}
        for (method, path), name in cases.items():
            scope = dict(type='http', method=method, path=path, root_path='', query_string=b'', headers=[])
            first = next(route for route in router.routes if route.matches(scope)[0] == Match.FULL)
            self.assertEqual(first.name, name, path)
