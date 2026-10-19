"""Synthetic BBVA and Capital One measured cells; no client documents or values."""
import time

import fitz

from app.pipeline import financial_amount_ocr as cells
from app.pipeline import pdf_extraction as pdf


def _tables(lines):
    def locator(x, y, width, height=8):
        return dict(kind='page_rectangle', page=1, rect=[int(v * 1000) for v in (x, y, x + width, y + height)],
            page_size=[600000, 800000], units='millipoints', space='pdf_displayed')
    values = [dict(row=i, column=j, text=text, locator=locator(x, y, width))
              for i, (y, row) in enumerate(lines) for j, (x, width, text) in enumerate(row)]
    return pdf._restore_page_tables([dict(chunk='Synthetic table', metadata=dict(table_source='text_alignment',
        geometry_source='cell_rectangles', table=dict(page=1, table=locator(0, 0, 600, 800), values=values,
        unlocated_values=0)))])


def bbva(amount='12,75O.59'):
    return _tables([
        (20, [(534, 55, 'Estado de Cuenta')]), (33, [(514, 76, 'MAESTRA PYME BBVA')]),
        (45, [(548, 41, 'PAGINA 1/2')]), (57, [(330, 35, 'No. Cuenta'), (470, 38, '0000012345')]),
        (107, [(330, 23, 'Periodo'), (430, 97, 'DEL 01/09/2024 AL 30/09/2024')]),
        (143, [(10, 187, 'BBVA MEXICO, S.A., INSTITUCION DE BANCA MULTIPLE')]),
        (155, [(10, 70, 'Informacion Financiera'), (522, 67, 'MONEDA NACIONAL')]),
        (167, [(316, 84, 'Saldo de Liquidacion Inicial'), (555, 34, '1,000.00')]),
        (179, [(316, 81, 'Saldo de Operacion Inicial'), (555, 34, '1,000.00')]),
        (215, [(316, 45, 'Saldo Final (+)'), (555, 34, '987.06')]),
        (227, [(316, 78, 'Saldo de Operacion Final'), (555, 34, '987.06')]),
        (251, [(18, 19, 'OPER'), (51, 11, 'LIQ'), (86, 67, 'COD. DESCRIPCION'), (230, 44, 'REFERENCIA'),
               (367, 30, 'CARGOS'), (429, 29, 'ABONOS'), (488, 41, 'OPERACION'), (553, 45, 'LIQUIDACION')]),
        (265, [(12, 22, '05/SEP'), (53, 22, '05/SEP'), (90, 120, 'T17 SPEI ENVIADO PROVEEDOR'),
               (365, 33, amount), (490, 35, '987.06' if amount else ''), (558, 35, '987.06')]),
        (451, [(10, 66, 'Total de Movimientos')])])


def capital(amount='$3B.74'):
    return _tables([
        (20, [(40, 60, 'Capital One')]),
        (40, [(330, 160, 'Platinum Mastercard ending in 4821')]),
        (52, [(330, 230, 'Feb 16, 2025 - Mar 15, 2025 | 28 days in Billing Cycle')]),
        (80, [(40, 80, 'Account Summary')]),
        (92, [(40, 70, 'Previous Balance'), (150, 30, '$10.00')]),
        (104, [(40, 50, 'New Balance'), (150, 30, '$48.74')]),
        (130, [(40, 220, 'Visit capitalone.com to see detailed transactions.')]),
        (150, [(40, 230, 'EXAMPLE CARDHOLDER #4821: Transactions')]),
        (162, [(40, 40, 'Trans Date'), (100, 40, 'Post Date'), (160, 60, 'Description'), (530, 30, 'Amount')]),
        (174, [(40, 30, 'Feb 19'), (100, 30, 'Feb 20'), (160, 120, 'EXAMPLE GROCERY'), (537, 23, amount)]),
        (186, [(40, 230, 'EXAMPLE CARDHOLDER #4821: Total Transactions'), (537, 23, '$38.74')])])


def observations(values):
    return [dict(text=value, dpi=300 if i < 3 else 450, threshold=(150, 190, 220)[i % 3]) for i, value in enumerate(values)]


def refine(monkeypatch, original, values):
    seen = []
    def read(*args):
        seen.append(args[-1] if len(args) > 5 else None)
        return observations(values)
    monkeypatch.setattr(cells, '_cleaned_line_readings', read)
    with fitz.open() as doc:
        page = doc.new_page(width=600, height=800)
        result, records = cells.refine_statement_native_cells(page, original, deadline=time.monotonic() + 30, language='eng')
    return result, records, seen


def changed(before, after):
    return [(a.row, a.column, b.text) for a, b in zip(before[0].geometry.cells, after[0].geometry.cells) if a.text != b.text]


def test_bbva_unreadable_charge_is_recovered_from_its_own_cargos_cell(monkeypatch):
    original = bbva()
    result, records, seen = refine(monkeypatch, original, ['12,750.59'] * 6)
    assert changed(original, result) == [(12, 3, '12,750.59')]
    assert records[0]['field'] == 'amount_minor' and records[0]['original_text'] == '12,75O.59'
    assert records[0]['refined_quality']['identity'][0] == 'bbva-mexico-cash-management'
    assert records[0]['refined_quality']['unreadable'] == 0
    assert seen == ['0123456789.,-+']


def test_bbva_disagreeing_or_partial_crops_change_nothing(monkeypatch):
    for values in (['12,750.59'] * 3 + ['12,780.59'] * 3, ['12,750.59'] * 3 + ['12,75O.59'] * 3, ['12750.59'] * 6):
        original = bbva()
        result, records, _ = refine(monkeypatch, original, values)
        if values == ['12750.59'] * 6:
            # A complete, agreeing reading without the grouping comma is still the same printed amount.
            assert changed(original, result) == [(12, 3, '12750.59')]
            continue
        assert result is original and records == []


def test_capital_one_amount_keeps_its_printed_dollar_sign(monkeypatch):
    original = capital()
    result, records, seen = refine(monkeypatch, original, ['$38.74'] * 6)
    assert changed(original, result) == [(9, 3, '$38.74')]
    assert records[0]['refined_quality']['identity'][:2] == ['capital-one-card', '****4821']
    assert seen == ['0123456789.,-+$']


def test_capital_one_reread_never_supplies_a_sign_or_drops_the_dollar(monkeypatch):
    for values in (['-$38.74'] * 6, ['- $38.74'] * 6, ['38.74'] * 6, ['538.74'] * 6, ['$38.74'] * 3 + ['$36.74'] * 3):
        original = capital()
        result, records, _ = refine(monkeypatch, original, values)
        assert result is original and records == [], values


def test_dollar_money_shape():
    assert all(cells._dollar_money(v) for v in ('$38.74', '- $40.00', '-$40.00', '$1,234.56', '$0.00'))
    assert not any(cells._dollar_money(v) for v in ('38.74', '$3B.74', '$38.7', '$$38.74', '+$38.74', '$38.74-',
                                                   '-  $40.00', '$1234,56.00', ''))
