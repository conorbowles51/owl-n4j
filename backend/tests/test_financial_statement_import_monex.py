"""Synthetic Monex contract statements in the two layouts Monex prints.

The structure (labels, page order, column order, centred or trailing
descriptions, engine cell merges) follows real Monex productions; every name,
number and amount here is invented. No client records in fixtures.
"""
from copy import deepcopy
from unittest import TestCase
from uuid import UUID

from services.financial.statement_import_monex import monex_catalog, propose_monex_statement
from services.financial.statement_import_catalog import statement_catalog
from services.financial.statement_currency import currencies_by_statement
from services.financial.statement_review_checks import check_statement_rows


def source(page, rows, size=(792000, 612000)):
    """One engine table per page; landscape unless ``size`` says otherwise."""
    return dict(page_number=page, table_index=0, source_revision='a' * 64, table_source='text_alignment',
        rows=[dict(row_index=i, cells=[dict(column_index=j, expected_text=t,
            locator=dict(kind='page_rectangle', page=page, rect=[x, y, x + w, y + 6000],
                page_size=list(size), units='millipoints', space='pdf_displayed'))
            for j, (x, y, w, t) in enumerate(cells)]) for i, cells in enumerate(rows)])

def prepare(test, sources):
    """Store the fixture pages as the engine would, each with its own page size."""
    import hashlib
    from sqlalchemy import select
    from postgres.models.evidence import EvidenceDocumentText, EvidenceTableGeometry
    f = test.f
    for old in list(f.db.scalars(select(EvidenceTableGeometry))):
        f.db.delete(old)
    f.db.flush()
    text = f.db.get(EvidenceDocumentText, f.file.id)
    text.content = '\n'.join(' '.join(c['expected_text'] for c in r['cells']) for s in sources for r in s['rows'])
    text.content_sha256 = hashlib.sha256(text.content.encode()).hexdigest()
    text.character_count = len(text.content)
    for s in sources:
        page = s['page_number']
        size = s['rows'][0]['cells'][0]['locator']['page_size']
        f.db.add(EvidenceTableGeometry(evidence_file_id=f.file.id, page_number=page, engine_job_id=text.engine_job_id,
            payload=[dict(table_source='text_alignment', geometry_source='cell_rectangles', table=dict(page=page,
                table=dict(kind='page_rectangle', page=page, rect=[0, 0, *size], page_size=size, units='millipoints', space='pdf_displayed'),
                unlocated_values=0, values=[dict(row=r['row_index'], column=c['column_index'], text=c['expected_text'], locator=c['locator'])
                                            for r in s['rows'] for c in r['cells']]))]))
    f.db.commit()


CONTRACT = '7654321'
CLABE = '112180000076543219'  # Monex bank code 112, branch 180, account 00007654321, check digit
HOLDER = 'EXAMPLE SERVICES SA DE CV'
# Right edges of the six money columns of the landscape movement table.
LANDSCAPE = dict(credit=366750, debit=447000, guarantee=533250, held=609000, available=687750, total=764250)
PORTRAIT = dict(credit=302800, debit=355000, guarantee=407000, held=475300, available=539900, total=600600)


def amount(right, y, value):
    return (right - 5000 * len(value), y, 5000 * len(value), value)


def furniture(page, count):
    return ([[(656000, 26000, 108000, 'Estado de Cuenta | Banco')], [(687000, 35000, 77000, f'CONTRATO: {CONTRACT}')]],
            [[(724000, 589000, 40000, f'Hoja {page} de {count}')]])


def cover(period='Del 1 Mayo 2026 al 31 mayo 2026', clabe=CLABE):
    return source(1, [
        [(480000, 20000, 100000, 'Estado de Cuenta')], [(480000, 35000, 60000, 'Banco')],
        [(80000, 60000, 200000, 'Estimado Cliente, texto de ejemplo')],
        [(486000, 300000, 180000, HOLDER)],
        [(486000, 311000, 250000, 'CALLE EJEMPLO 100 COLONIA EJEMPLO')],
        [(486000, 334000, 20000, 'C.P.'), (588000, 334000, 30000, '00000')],
        [(486000, 364000, 60000, 'FOLIO:'), (588000, 364000, 60000, 'D-0000000')],
        [(486000, 415000, 90000, 'TIPO DE CONTRATO:'), (588000, 415000, 150000, 'SERVICIOS BANCARIOS PERSONA MORAL')],
        [(486000, 442000, 60000, 'CLIENTE No.'), (588000, 442000, 60000, '1234567')],
        [(486000, 459000, 60000, 'CONTRATO:'), (588000, 459000, 60000, CONTRACT)],
        [(486000, 476000, 60000, 'CTA. CLABE:'), (588000, 476000, 100000, clabe)],
        [(486000, 510000, 60000, 'RFC TITULAR:'), (588000, 510000, 80000, 'EXA010101AB1')],
        [(486000, 527000, 60000, 'PERIODO:'), (588000, 527000, 150000, period)],
    ])


def peso_summary(page, count, opening, credits, debits, closing, total=None):
    head, foot = furniture(page, count)
    return source(page, head + [
        [(28000, 61000, 40000, 'Cuenta'), (467000, 64000, 60000, 'Resumen Cuenta')],
        [(28000, 78000, 60000, 'Resumen Divisas'), (467000, 79000, 60000, 'Peso Mexicano'), (710000, 78000, 60000, 'al 31 Mayo 2026')],
        [(28000, 94000, 30000, 'Divisa'), (123000, 94000, 90000, 'Saldo inicial del periodo'), (467000, 92000, 50000, 'Saldo inicial:'), (722000, 92000, 40000, opening)],
        [(28000, 108000, 30000, 'euro'), (200000, 108000, 20000, '0.79'), (262000, 108000, 20000, '0.00'), (337000, 108000, 20000, '0.00'),
         (436000, 108000, 20000, '0.79'), (470000, 106000, 60000, '+ Total abonos:'), (722000, 106000, 40000, credits)],
        [(471000, 122000, 60000, '- Total cargos:'), (722000, 122000, 40000, debits)],
        [(467000, 160000, 50000, 'Saldo vista:'), (750000, 160000, 20000, closing)],
        [(28000, 182000, 90000, 'Saldo promedio (Intereses):'), (202000, 182000, 40000, opening)],
        [(467000, 203000, 50000, 'Saldo total:'), (750000, 203000, 20000, total or closing)],
        [(396000, 522000, 200000, 'Banco Monex, S. A. Institución de Banca Múltiple,')],
        [(396000, 531000, 200000, 'Monex Grupo Financiero R.F.C. EXA0000000AA')],
    ] + foot)


def currency_summary(page, count, label, opening, credits, debits, closing, table=()):
    head, foot = furniture(page, count)
    return source(page, head + [
        [(28000, 50000, 40000, 'Cuenta Vista')], [(28000, 75000, 60000, 'Resumen cuenta')],
        [(28000, 98000, 60000, label), (176000, 98000, 60000, 'al 31 Mayo 2026')],
        [(273000, 106000, 40000, 'Concepto'), (393000, 106000, 40000, 'Del periodo'), (531000, 106000, 40000, 'Comisiones'), (749000, 106000, 15000, '0.00')],
        [(28000, 112000, 50000, 'Saldo inicial:'), (223000, 112000, 20000, opening)],
        [(30000, 126000, 60000, '+ Total abonos:'), (201000, 126000, 30000, credits)],
        [(30000, 140000, 60000, '- Total cargos:'), (201000, 140000, 30000, debits)],
        [(28000, 168000, 50000, 'Saldo vista:'), (223000, 168000, 20000, closing)],
        [(28000, 220000, 50000, 'Saldo total:'), (223000, 220000, 20000, closing)],
    ] + list(table) + foot)


def table_header(y, split=False):
    if split:  # the three-line heading printed on currency pages
        return [[(485000, y - 6000, 40000, 'Movimiento'), (573000, y - 6000, 30000, 'Saldo en'), (662000, y - 6000, 25000, 'Saldo'), (741000, y - 6000, 25000, 'Saldo')],
                [(30000, y, 23000, 'Fecha'), (95000, y, 45000, 'Descripción'), (229000, y, 41000, 'Referencia'), (351000, y, 29000, 'Abonos'), (425000, y, 27000, 'Cargos')],
                [(499000, y + 5000, 35000, 'garantia'), (575000, y + 5000, 35000, 'garantia'), (644000, y + 5000, 40000, 'disponible'), (745000, y + 5000, 20000, 'total')]]
    return [[(30000, y, 23000, 'Fecha'), (95000, y, 45000, 'Descripción'), (229000, y, 41000, 'Referencia'), (338000, y, 29000, 'Abonos'),
             (420000, y, 27000, 'Cargos'), (455000, y, 78000, 'Movimiento garantia'), (542000, y, 66000, 'Saldo en garantia'),
             (624000, y, 63000, 'Saldo disponible'), (723000, y, 41000, 'Saldo total')]]


def endpoint(label, y, value, columns=LANDSCAPE):
    return [(columns['guarantee'] - 40000, y, 40000, label), amount(columns['held'], y, '0.00'),
            amount(columns['available'], y, value), amount(columns['total'], y, value)]


def movement(y, day, reference, credit, debit, total, above=(), below=(), inline=None, columns=LANDSCAPE, step=9800):
    """A dated line with its six amounts; description lines centred on it."""
    rows = [[(95000, y - step * (len(above) - i), 120000, text)] for i, text in enumerate(above)]
    line = [(30000, y, 22000, day)] + ([(95000, y, 120000, inline)] if inline else []) + [(229000, y, 32000, reference)]
    line += [amount(columns['credit'], y, credit), amount(columns['debit'], y, debit), amount(columns['guarantee'], y, '0.00'),
             amount(columns['held'], y, '0.00'), amount(columns['available'], y, total), amount(columns['total'], y, total)]
    rows.append(line)
    rows += [[(95000, y + step * (i + 1), 120000, text)] for i, text in enumerate(below)]
    return rows


def landscape(count=9):
    """Pesos with movements over two pages, dollars with movements, euros quiet."""
    pages = [cover(), peso_summary(2, count, '1,000.00', '2,500.00', '1,750.00', '1,750.00')]
    head, foot = furniture(3, count)
    pages.append(source(3, head + [[(31000, 65000, 150000, 'Movimientos de mayo')]] + table_header(91000) + [
        endpoint('Saldo inicial:', 113000, '1,000.00')]
        + movement(150000, '04/May', '0', '0.00', '0.00', '1,000.00', above=['Depósito de intereses por saldo', 'del periodo anterior'],
                   below=['Intereses $1.00 Impuesto', 'Sobre La Renta $1.00'])
        + movement(200000, '11/May', '11112222', '0.00', '750.00', '250.00', above=['Retiro por compra de divisas 37.50'],
                   below=['USD a un tipo de cambio de 20.000000'])
        + movement(280000, '18/May', '33334444', '2,500.00', '0.00', '2,750.00',
                   above=['Depósito Emisor: BANCO EJEMPLO', 'Fecha Confirmacion de', 'liquidacion:18-05-2026'],
                   inline='Nombre del Ordenante:EJEMPLO',
                   below=['Cuenta', 'ordenante:000000000000000000', 'Clave de Rastreo:0000'])
        + movement(560000, '29/May', '55556666', '0.00', '1,000.00', '1,750.00',
                   above=['RETIRO Nombre Receptor: BANCO EJEMPLO', 'Monto Pago: 1000'], below=['Cuenta beneficiaria:'])
        + foot))
    head, foot = furniture(4, count)
    pages.append(source(4, head + [[(31000, 65000, 60000, 'Movimientos')]] + table_header(91000) + [
        [(95000, 108000, 120000, '000000000000000000')], [(95000, 118000, 120000, 'Concepto del pago: EJEMPLO')],
        endpoint('Saldo final:', 140000, '1,750.00')] + foot))
    dollars = table_header(290000, split=True) + [endpoint('Saldo inicial:', 310000, '2.00')] + movement(
        340000, '11/May', '11112222', '37.50', '0.00', '39.50', above=['Compra de divisas 37.50 USD a un'],
        inline='tipo de cambio de 20.000000 Importe', below=['en pesos $750.00']) + movement(
        380000, '12/May', '77778888', '0.00', '37.50', '2.00', above=['RETIRO BENEFICIARIO EJEMPLO'], below=['BANCO EJEMPLO CUENTA 0000']) + [
        endpoint('Saldo final:', 400000, '2.00')]
    pages.append(currency_summary(5, count, 'dólar americano', '2.00', '37.50', '37.50', '2.00',
                                  table=[[(31000, 262000, 50000, 'Movimientos')]] + dollars))
    pages.append(currency_summary(6, count, 'euro', '0.79', '0.00', '0.00', '0.79'))
    for page, label in [(7, 'Referencias bancarias'), (8, 'Estimado cliente:'), (9, 'Aviso de seguridad de la información')]:
        head, foot = furniture(page, count)
        pages.append(source(page, head + [[(28000, 60000, 250000, label)], [(28000, 80000, 250000, 'Instrucciones USD EUR MXN 0.00')]] + foot))
    return pages


def statement():
    """Two quiet currency sections (the zero-activity shape)."""
    pages = [cover(), peso_summary(2, 6, '321.45', '0.00', '0.00', '321.45'),
             currency_summary(3, 6, 'euro', '0.79', '0.00', '0.00', '0.79')]
    for page, label in [(4, 'Referencias bancarias'), (5, 'Estimado cliente:'), (6, 'Aviso de seguridad de la información')]:
        head, foot = furniture(page, 6)
        pages.append(source(page, head + [[(28000, 60000, 250000, label)], [(28000, 80000, 250000, 'Instrucciones USD EUR MXN')]] + foot))
    return pages


def portrait():
    """2019 layout: every section 'CUENTA VISTA <currency>', table on the same page."""
    rows = [
        [(374000, 51000, 200000, 'Estimado Cliente: texto de ejemplo')],
        [(9900, 130000, 200000, HOLDER), (395000, 129000, 50000, 'CLIENTE No.'), (461000, 129000, 40000, '1234567')],
        [(11650, 141000, 300000, 'CALLE EJEMPLO 100 COLONIA EJEMPLO'), (395000, 141000, 50000, 'CONTRATO:'), (455000, 141000, 40000, CONTRACT)],
        [(11650, 153000, 200000, 'CIUDAD EJEMPLO MEXICO'), (395000, 153000, 50000, 'CTA. CLABE:'), (461000, 153000, 80000, CLABE)],
        [(16983, 174000, 60000, 'C.P.: 00000'), (190000, 174000, 60000, 'FOLIO: D-0000000')],
        [(395000, 180000, 120000, 'RFC TITULAR: EXA010101-AB1')],
        [(395000, 192000, 150000, 'PERIODO: 1 al 30 de ABRIL de 2019')],
        [(395000, 213000, 60000, 'HOJA 1 DE 3')],
    ]
    rows += portrait_section(233000, 'YEN JAPONES', 'JPY', '0.00', '5,000.00', '5,000.00', '0.00', [
        portrait_line(476000, '03/Abr', 'Compra de divisas', '45629016', '5,000.00', '0.00', '5,000.00',
                      ['5,000.00 JPY a un tipo de cambio de', '.190000 Importe en pesos $950.00']),
        portrait_line(502000, '03/Abr', 'RETIRO', '61585153', '0.00', '5,000.00', '0.00', ['BENEFICIARIO EJEMPLO LTD'])])
    rows += [[(173650, 717000, 200000, 'Banco Monex , S.A. Institución de Banca Multiple,')]]
    page2 = [[(555950, 72000, 50000, 'HOJA 2 DE 3')]] + portrait_section(90000, 'PESO MEXICANO', 'MXP', '51.99', '950.00', '950.00', '51.99', [
        portrait_line(333000, '03/Abr', 'Retiro por compra de divisas', '45629016', '0.00', '950.00', '-898.01', ['5,000.00 JPY a un tipo de cambio de']),
        portrait_line(358000, '03/Abr', 'Depósito', '61585015', '950.00', '0.00', '51.99', ['Emisor: BANCO EJEMPLO | Fecha', 'Concepto de Pago:EJEMPLO'])],
        zero_line=True)
    page3 = [[(555950, 72000, 50000, 'HOJA 3 DE 3')], [(264700, 90000, 80000, 'REFERENCIAS BANCARIAS')], [(20000, 110000, 200000, 'BANCO EJEMPLO 0.00')]]
    portrait_size = (612000, 792000)
    return [source(1, rows, portrait_size), source(2, page2, portrait_size), source(3, page3, portrait_size)]


def portrait_section(y, label, code, opening, credits, debits, closing, lines, zero_line=False):
    rows = [[(252900, y, 120000, f'CUENTA VISTA {label}')], [(476950, y + 20000, 20000, code)],
            [(9900, y + 28000, 150000, f'CUENTA VISTA {label}'), (232102, y + 28000, 100000, 'al 30 de ABRIL de 2019'),
             (483149, y + 28000, 50000, 'DEL PERIODO'), (559650, y + 28000, 40000, 'ACUMULADO')],
            [(5650, y + 38000, 40000, 'SALDO INICIAL:'), (143402, y + 38000, 150000, f'{opening} SALDO PROMEDIO (INTERESES):')],
            [(5650, y + 50000, 40000, '+ ABONOS:'), (124652, y + 50000, 40000, credits)],
            [(10102, y + 62000, 40000, '- CARGOS:'), (124652, y + 62000, 40000, debits)],
            [(5650, y + 76000, 40000, 'SALDO FINAL:'), (143602, y + 76000, 30000, closing)],
            [(264700, y + 180000, 60000, 'MOVIMIENTOS')],
            [(25950, y + 208000, 20000, 'Fecha'), (103000, y + 208000, 40000, 'Descripción'), (205699, y + 206000, 40000, 'Referencia'),
             (270050, y + 206000, 30000, 'Abonos'), (330800, y + 206000, 25000, 'Cargos'), (369200, y + 206000, 40000, 'Movimiento'),
             (434800, y + 206000, 30000, 'Saldo No'), (506149, y + 206000, 20000, 'Saldo'), (566150, y + 206000, 20000, 'Saldo')],
            [(375399, y + 216000, 30000, 'Garantía'), (433950, y + 216000, 30000, 'Disponible'), (499950, y + 216000, 30000, 'Disponible'), (567950, y + 216000, 20000, 'Total')],
            endpoint('Saldo Inicial:', y + 229000, opening, PORTRAIT)]
    for line in lines:
        rows += line
    if zero_line:  # an undated line with no credit or debit, as printed for net-zero interest
        rows.append([amount(PORTRAIT['guarantee'], y + 300000, '0.00'), amount(PORTRAIT['held'], y + 300000, '0.00'),
                     amount(PORTRAIT['total'], y + 300000, '12.00')])
    rows.append(endpoint('Saldo Final:', y + 310000, closing, PORTRAIT))
    return rows


def portrait_line(y, day, text, reference, credit, debit, total, below):
    line = [(5650, y, 20000, day), (59650, y, 100000, text), (206921, y, 30000, reference)]
    line += [amount(PORTRAIT['credit'], y, credit), amount(PORTRAIT['debit'], y, debit), amount(PORTRAIT['guarantee'], y, '0.00'),
             amount(PORTRAIT['held'], y, '0.00'), amount(PORTRAIT['available'], y, total), amount(PORTRAIT['total'], y, total)]
    return [line] + [[(59183, y + 8500 * (i + 1), 150000, text)] for i, text in enumerate(below)]


def choices_of(sources):
    return currencies_by_statement(monex_catalog(sources)[0], sources)


def payments(sources, choice):
    rows = propose_monex_statement(sources, choice['currency'], choice)['rows']
    return rows, [r for r in rows if not r['excluded']]


def summary(rows):
    return [(r['kind'], r['fields'].get('date'), r['fields'].get('direction'), r['fields'].get('amount_minor'),
             r['fields'].get('balance'), r['fields'].get('description')) for r in rows]


def checks(rows):
    return {c['kind']: c['status'] for c in check_statement_rows(rows)['checks']}


def replace_text(sources, page, old, new):
    for row in sources[page - 1]['rows']:
        for cell in row['cells']:
            if cell['expected_text'] == old:
                cell['expected_text'] = new
                return sources
    raise AssertionError(old)


class MonexZeroActivityTests(TestCase):
    def test_currency_sections_keep_zero_activity_and_balances_separate(self):
        sources = statement(); before = deepcopy(sources)
        catalog = statement_catalog(sources)
        self.assertTrue(catalog['complete_coverage'])
        choices = currencies_by_statement(catalog['statements'], sources)
        self.assertEqual([c['currency'] for c in choices], ['MXN', 'EUR'])
        self.assertEqual(len({c['id'] for c in choices}), 2)
        for choice, balance in zip(choices, ['32145', '79']):
            self.assertEqual(choice['holder'], HOLDER)
            self.assertEqual(choice['account_reference'], CONTRACT)
            self.assertEqual((choice['period_start'], choice['period_end']), ('2026-05-01', '2026-05-31'))
            rows = propose_monex_statement(sources, choice['currency'], choice)['rows']
            self.assertEqual([r['fields']['balance'] for r in rows if r['kind'] == 'balance'], [balance, balance])
            self.assertTrue(all(r['excluded'] and not r['issues'] for r in rows))
            self.assertEqual(check_statement_rows(rows)['balance_status'], 'matches')
            self.assertEqual(len(rows), sum(len(s['rows']) for s in sources))
        self.assertEqual(sources, before)

    def test_incomplete_or_foreign_contracts_are_not_recognised(self):
        variants = []
        s = statement(); s.pop(); variants.append(s)                                          # last page missing
        s = statement(); del s[2]; variants.append(s)                                         # middle page missing
        s = statement(); replace_text(s, 1, CLABE, '012180000076543219'); variants.append(s)  # not a Monex CLABE
        s = statement(); replace_text(s, 1, CLABE, '112180000076543210'[:-2] + '99'); variants.append(s)
        s = statement(); replace_text(s, 1, CLABE, '112180000011111119'); variants.append(s)  # another contract
        s = statement(); replace_text(s, 5, f'CONTRATO: {CONTRACT}', 'CONTRATO: 9999999'); variants.append(s)
        s = statement(); replace_text(s, 3, 'euro', 'moneda desconocida'); variants.append(s)
        s = statement(); replace_text(s, 3, 'al 31 Mayo 2026', 'al 30 Abril 2026'); variants.append(s)
        s = statement(); replace_text(s, 2, '+ Total abonos:', 'Total abonos'); variants.append(s)
        s = statement(); replace_text(s, 2, 'Saldo vista:', 'Saldo:'); variants.append(s)
        s = statement(); replace_text(s, 3, 'Hoja 3 de 6', 'Hoja 4 de 6'); variants.append(s)
        for i, s in enumerate(variants):
            with self.subTest(i=i):
                self.assertEqual(monex_catalog(s), ([], set()))

    def test_printed_activity_without_a_movement_table_is_held_not_read_as_quiet(self):
        from services.financial.statement_import_monex import monex_no_activity_evidence
        s = statement()
        next(r for r in s[2]['rows'] if r['cells'][0]['expected_text'] == '+ Total abonos:')['cells'][1]['expected_text'] = '12.00'
        choice = choices_of(s)[1]
        rows = propose_monex_statement(s, 'EUR', choice)['rows']
        self.assertEqual(monex_no_activity_evidence(s, choice, rows, 'EUR')['reason'], 'totals_not_zero')
        self.assertEqual(checks(rows)['credit_total'], 'difference')

    def test_other_statements_in_same_pdf_do_not_supply_missing_monex_pages(self):
        s = statement(); s[2]['rows'][1]['cells'][0]['expected_text'] = 'CONTRATO: 1111111'
        self.assertEqual(monex_catalog(s), ([], set()))

    def test_owner_identifier_is_the_explicit_holder_field_not_a_bank_or_routing_identifier(self):
        from services.financial.account_ownership import holder_identifiers
        s = statement()
        s[3]['rows'].extend(source(4, [[(20000, 200000, 100000, 'RFC TITULAR:'), (200000, 200000, 120000, 'BNK010101AB1')]])['rows'])
        found = holder_identifiers(s, account_reference=CONTRACT, holder=HOLDER)
        self.assertEqual({v['value'] for v in found}, {'EXA010101AB1'})
        self.assertTrue(all(v['page_number'] == 1 and v['locator'] for v in found))
        self.assertEqual(holder_identifiers(s, account_reference=CONTRACT, holder='Different company'), [])


class MonexMovementTests(TestCase):
    def test_each_currency_section_reads_its_movements_and_reconciles(self):
        sources = landscape(); before = deepcopy(sources)
        catalog = statement_catalog(sources)
        self.assertTrue(catalog['complete_coverage'])
        choices = choices_of(sources)
        self.assertEqual([c['currency'] for c in choices], ['MXN', 'USD', 'EUR'])
        peso, dollar, euro = choices
        rows, paid = payments(sources, peso)
        self.assertEqual(summary(paid), [
            ('transaction', '2026-05-11', 'debit', '75000', '25000', 'Retiro por compra de divisas 37.50 USD a un tipo de cambio de 20.000000'),
            ('transaction', '2026-05-18', 'credit', '250000', '275000', 'Depósito Emisor: BANCO EJEMPLO Fecha Confirmacion de '
             'liquidacion:18-05-2026 Nombre del Ordenante:EJEMPLO Cuenta ordenante:000000000000000000 Clave de Rastreo:0000'),
            # A block cut by the page break continues at the top of the next page.
            ('transaction', '2026-05-29', 'debit', '100000', '175000', 'RETIRO Nombre Receptor: BANCO EJEMPLO Monto Pago: 1000 '
             'Cuenta beneficiaria: 000000000000000000 Concepto del pago: EJEMPLO')])
        self.assertEqual([r['fields']['bank_reference'] for r in paid], ['11112222', '33334444', '55556666'])
        self.assertEqual(checks(rows), {'closing_balance': 'matches', 'running_balance': 'matches',
                                        'credit_total': 'matches', 'debit_total': 'matches'})
        # The dated interest line without a credit or debit is not a payment.
        interest = next(r for r in rows if r['id'] == '3:0:6')
        self.assertEqual((interest['kind'], interest['excluded'], interest['issues']), ('header', True, []))
        rows, paid = payments(sources, dollar)
        self.assertEqual(summary(paid), [
            ('transaction', '2026-05-11', 'credit', '3750', '3950', 'Compra de divisas 37.50 USD a un tipo de cambio de 20.000000 Importe en pesos $750.00'),
            ('transaction', '2026-05-12', 'debit', '3750', '200', 'RETIRO BENEFICIARIO EJEMPLO BANCO EJEMPLO CUENTA 0000')])
        self.assertEqual(checks(rows)['running_balance'], 'matches')
        rows, paid = payments(sources, euro)
        self.assertEqual(paid, [])
        self.assertEqual(checks(rows)['closing_balance'], 'matches')
        self.assertEqual(sources, before)

    def test_portrait_sections_with_a_currency_without_minor_units(self):
        sources = portrait(); before = deepcopy(sources)
        self.assertTrue(statement_catalog(sources)['complete_coverage'])
        yen, peso = choices_of(sources)
        self.assertEqual((yen['currency'], peso['currency'], yen['holder']), ('JPY', 'MXN', HOLDER))
        self.assertEqual((yen['period_start'], yen['period_end']), ('2019-04-01', '2019-04-30'))
        rows, paid = payments(sources, yen)
        self.assertEqual(summary(paid), [
            ('transaction', '2019-04-03', 'credit', '5000', '5000', 'Compra de divisas 5,000.00 JPY a un tipo de cambio de .190000 Importe en pesos $950.00'),
            ('transaction', '2019-04-03', 'debit', '5000', '0', 'RETIRO BENEFICIARIO EJEMPLO LTD')])
        self.assertEqual(checks(rows)['closing_balance'], 'matches')
        rows, paid = payments(sources, peso)
        self.assertEqual([(r['fields']['direction'], r['fields']['amount_minor'], r['fields']['balance']) for r in paid],
                         [('debit', '95000', '-89801'), ('credit', '95000', '5199')])
        self.assertEqual(paid[1]['fields']['description'], 'Depósito Emisor: BANCO EJEMPLO | Fecha Concepto de Pago:EJEMPLO')
        self.assertEqual(checks(rows)['running_balance'], 'matches')
        self.assertEqual(sources, before)

    def test_the_text_layer_merging_cells_does_not_change_the_reading(self):
        sources = landscape()
        expected = [summary(payments(sources, c)[1]) for c in choices_of(sources)]
        merged = landscape()
        page3 = merged[2]['rows']
        # Heading words merged, amounts merged pairwise, the date merged with
        # its description and a table endpoint merged with its label.
        header = page3[3]['cells']
        header[4:6] = [dict(header[4], expected_text='Cargos Movimiento garantia',
                            locator=dict(header[4]['locator'], rect=[420000, 91000, 533000, 97000]))]
        line = next(r for r in page3 if r['cells'][0]['expected_text'] == '18/May')['cells']
        credit, debit = line[3], line[4]
        line[3:5] = [dict(credit, expected_text='2,500.00 0.00', locator=dict(credit['locator'], rect=[credit['locator']['rect'][0], 280000, 447000, 286000]))]
        line[0:2] = [dict(line[0], expected_text='18/May Nombre del Ordenante:EJEMPLO',
                          locator=dict(line[0]['locator'], rect=[30000, 280000, 215000, 286000]))]
        opening = page3[4]['cells']
        page3[4]['cells'] = [dict(opening[0], expected_text='Saldo inicial: 0.00 1,000.00 1,000.00',
                                  locator=dict(opening[0]['locator'], rect=[493000, 113000, 765000, 119000]))]
        self.assertEqual([summary(payments(merged, c)[1]) for c in choices_of(merged)], expected)

    def test_disagreeing_printed_values_are_held_for_a_person_never_admitted(self):
        def held(sources, currency='MXN'):
            choice = next(c for c in choices_of(sources) if c['currency'] == currency)
            rows, _ = payments(sources, choice)
            return [r for r in rows if r['kind'] == 'unresolved' and not r['excluded'] and r['issues']]
        self.assertEqual(held(landscape()), [])
        variants = {
            'table opening differs from summary': lambda s: next(
                r for r in s[2]['rows'] if r['cells'][0]['expected_text'] == 'Saldo inicial:')['cells'][-1].update(expected_text='1,100.00'),
            'summary total differs from available balance': lambda s: replace_text(s, 2, '1,750.00', '1,750.00') and
                [c.update(expected_text='1,760.00') for r in s[1]['rows'] for c in r['cells'][-1:]
                 if r['cells'][0]['expected_text'] == 'Saldo total:'],
            'a movement line missing an amount': lambda s: next(r for r in s[2]['rows'] if r['cells'][0]['expected_text'] == '11/May')['cells'].pop(4),
            'credit and debit on one line': lambda s: [c.update(expected_text='5.00') for r in s[2]['rows']
                if r['cells'][0]['expected_text'] == '11/May' for c in r['cells'][2:3]],
        }
        for name, change in variants.items():
            with self.subTest(name):
                s = landscape(); change(s)
                self.assertTrue(held(s), name)

    def test_a_dated_line_with_money_outside_the_table_refuses_the_contract(self):
        s = landscape()
        s[5]['rows'].insert(8, source(6, [[(30000, 150000, 20000, '15/May'), (95000, 150000, 50000, 'TRASPASO'), (200000, 150000, 20000, '5.00'), (260000, 150000, 20000, '5.00')]])['rows'][0])
        for i, row in enumerate(s[5]['rows']):
            row['row_index'] = i
        self.assertEqual(monex_catalog(s), ([], set()))

    def test_an_unclosed_movement_table_refuses_the_contract(self):
        s = landscape()
        s[3]['rows'] = [r for r in s[3]['rows'] if r['cells'][0]['expected_text'] != 'Saldo final:']
        self.assertEqual(monex_catalog(s), ([], set()))

    def test_a_page_without_a_readable_table_is_accepted_only_between_numbered_pages(self):
        s = landscape()
        del s[6]  # page 7 has no readable table (printed only with its number)
        groups, handled = monex_catalog(s)
        self.assertEqual([g['currency'] for g in groups], ['MXN', 'USD', 'EUR'])
        self.assertNotIn(7, {p for p, _ in handled})
        s = landscape(); s.pop()
        self.assertEqual(monex_catalog(s), ([], set()))  # the last page missing is never accepted

    def test_notice_page_before_the_cover_is_printed_page_one(self):
        pages = landscape()
        shifted = [source(1, [[(30000, 150000, 200000, 'Estimado Cliente')], [(30000, 170000, 200000, 'Aviso de ejemplo')]])]
        for page in pages:
            page = deepcopy(page)
            page['page_number'] += 1
            for row in page['rows']:
                for cell in row['cells']:
                    cell['locator']['page'] = page['page_number']
                    if cell['expected_text'].startswith('Hoja '):
                        cell['expected_text'] = f"Hoja {page['page_number']} de 10"
            shifted.append(page)
        groups, handled = monex_catalog(shifted)
        self.assertEqual([g['currency'] for g in groups], ['MXN', 'USD', 'EUR'])
        self.assertIn((1, 0), handled)
        self.assertEqual(groups[0]['page_numbers'], list(range(1, 11)))


class MonexImportTests(TestCase):
    def setUp(self):
        from tests.test_financial_statement_import import StatementImportTests
        self.f = StatementImportTests('test_existing_import_and_same_request_keep_the_saved_account_for_navigation')
        self.f.setUp()
        prepare(self, statement())

    def tearDown(self):
        self.f.tearDown()

    def preview(self, statement_id=None):
        from services.financial.statement_import import read_statement_import
        with self.f.SessionLocal() as db:
            return read_statement_import(db, case_id=self.f.case.id, evidence_file_id=self.f.file.id, statement_id=statement_id)

    def test_select_import_both_currencies_retry_and_reopen_without_duplicate_payments(self):
        from services.financial.import_batches import initial_request
        from services.financial.statement_details import read_statement_details
        from services.financial.imported_records import imported_records
        receipts = []
        choices = self.preview()['statement_choices']
        self.assertEqual(len(choices), 2)
        for choice, balance in zip(choices, ['32145', '79']):
            proposal = self.preview(choice['id'])
            self.assertEqual(proposal['transaction_count'], 0)
            self.assertEqual(proposal['needs_attention'], 0)
            self.assertTrue(proposal['can_import_balances'])
            self.assertEqual(proposal['metadata']['holder'], HOLDER)
            request = initial_request(proposal)
            receipt = self.f.confirm(request); receipts.append(receipt)
            self.assertEqual((receipt['transaction_count'], receipt['incomplete_count']), (0, 0))
            self.assertFalse(self.f.confirm(request)['created'])
            self.assertEqual(self.preview(choice['id'])['current_import']['source_document_id'], receipt['source_document_id'])
            with self.f.SessionLocal() as db:
                details = read_statement_details(db, case_id=self.f.case.id, source_id=UUID(receipt['source_document_id']))
                self.assertEqual(details['currency'], choice['currency'])
                self.assertEqual(details['balances']['opening']['amount_minor'], balance)
                self.assertEqual(details['balances']['closing']['amount_minor'], balance)
                self.assertEqual(details['details']['period_end'], '2026-05-31')
                self.assertEqual(imported_records(db, case_id=self.f.case.id, account_id=None, start_date=None, end_date=None)['total'], 0)
        self.assertNotEqual(receipts[0]['account_id'], receipts[1]['account_id'])

    def test_editing_one_currency_section_retains_the_other_section_and_source(self):
        from services.financial.import_batches import initial_request
        from services.financial.statement_details import read_statement_details, update_statement_details, StatementDetailsRequest
        from postgres.models.financial import FinancialAccount
        choices = self.preview()['statement_choices']
        receipts = [self.f.confirm(initial_request(self.preview(c['id']))) for c in choices]
        with self.f.SessionLocal() as db:
            first, second = [read_statement_details(db, case_id=self.f.case.id, source_id=UUID(r['source_document_id'])) for r in receipts]
            after = update_statement_details(db, case_id=self.f.case.id, source_id=UUID(receipts[1]['source_document_id']), actor=self.f.actor,
                request=StatementDetailsRequest(expected_revision=second['revision'], holder=second['details']['holder'],
                    institution=second['details']['institution'], account_number=second['details']['account_number'], currency='GBP'))
            self.assertEqual(after['currency'], 'GBP')
            self.assertEqual(after['balances']['opening']['amount_minor'], '79')
            self.assertEqual(db.get(FinancialAccount, UUID(after['account_id'])).currency, 'GBP')
            untouched = read_statement_details(db, case_id=self.f.case.id, source_id=UUID(receipts[0]['source_document_id']))
            self.assertEqual(untouched, first)
            self.assertEqual(after['evidence_file_id'], first['evidence_file_id'])


class MonexMovementImportTests(TestCase):
    def setUp(self):
        from tests.test_financial_statement_import import StatementImportTests
        self.f = StatementImportTests('test_existing_import_and_same_request_keep_the_saved_account_for_navigation')
        self.f.setUp()
        prepare(self, landscape())

    def tearDown(self):
        self.f.tearDown()

    def preview(self, statement_id=None):
        from services.financial.statement_import import read_statement_import
        with self.f.SessionLocal() as db:
            return read_statement_import(db, case_id=self.f.case.id, evidence_file_id=self.f.file.id, statement_id=statement_id)

    def test_every_currency_section_reconciles_and_imports_its_own_payments(self):
        from services.financial.import_batches import assess, initial_request
        choices = self.preview()['statement_choices']
        self.assertEqual([c['currency'] for c in choices], ['MXN', 'USD', 'EUR'])
        for choice, count in zip(choices, (3, 2, 0)):
            proposal = self.preview(choice['id'])
            self.assertEqual(proposal['transaction_count'], count)
            _, result = assess(proposal)
            self.assertTrue(result['can_import'], result['problems'])
            receipt = self.f.confirm(initial_request(proposal))
            self.assertEqual((receipt['transaction_count'], receipt['incomplete_count']), (count, 0))
