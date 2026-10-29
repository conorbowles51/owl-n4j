"""Credit-line period summary charges (credit_line_summary, LOUPE_FINANCIAL_CREDIT_LINE_SUMMARY_CHARGES).

Synthetic fixtures only (invented names, numbers and amounts). The layout follows the shape of a Mexican
revolving credit line: a one-column period summary printing interest and IVA, and a movement table with
one signed amount column that does not list them.
"""
import unittest
from unittest import mock

from services.financial import credit_line_summary as C
from services.financial import statement_engine as E
from services.financial.statement_engine import read_statements
from tests.test_financial_statement_engine import page

AMOUNT_RIGHT = 420000


def amount(text):
    return (text, AMOUNT_RIGHT - 6000 * len(text), AMOUNT_RIGHT)


def statement(*, closing='723.20', payments='300.00', movements=None, interest='20.00', tax='3.20',
              tax_next=True, second_date=False, kinds=None, continued=None, bank=None):
    """Opening 1,000.00; one payment of 300.00; interest 20.00 and IVA 3.20 printed in the summary only.
    ``continued``: movement lines printed on a second page under its page header only (no date heading);
    ``bank``: lines printed above the statement in place of the invented bank's name."""
    summary_tax = [('I.V.A.', 200000, 240000), ('+$', 323000, 336000), amount(tax)]
    lines = (bank or [[('BANCO EJEMPLO DEL NORTE, S.A., INSTITUCION DE BANCA MULTIPLE', 20000, 400000)]]) + [
        [('NO. DE CREDITO', 300000, 380000), ('1234', 400000, 430000), ('5678', 435000, 465000),
         ('9012', 470000, 500000), ('3456', 505000, 535000)],
        [('EMPRESA DE PRUEBA SA DE CV', 20000, 200000)],
        [('CALLE FALSA 123', 20000, 150000)],
        [('COL CENTRO', 20000, 120000)],
        [('CIUDAD DE MEXICO C.P. 06000', 20000, 220000)],
        [('MONEDA NACIONAL', 20000, 120000)],
        [('LIMITE DE CREDITO', 20000, 120000), ('5,000.00', 130000, 180000)],
        [('SALDO INICIAL DEL PERIODO', 200000, 300000), ('+$', 323000, 336000), amount('1,000.00')],
        [('DISPOSICIONES', 200000, 300000), ('+$', 323000, 336000), amount('0.00')],
        [('PAGOS', 200000, 300000), ('-$', 323000, 336000), amount(payments)],
        [('COMISIONES COBRADAS', 200000, 300000), ('+$', 323000, 336000), amount('0.00')],
        [('OTROS CARGOS', 200000, 300000), ('+$', 323000, 336000), amount('0.00')],
        [('INTERESES ORDINARIOS (SIN IVA)', 200000, 300000), amount(interest)],
    ]
    if tax_next:
        lines.append(summary_tax)
    lines.append([('INTERESES MORATORIOS (SIN IVA)', 200000, 300000), ('+$', 323000, 336000), amount('0.00')])
    if not tax_next:
        lines.append(summary_tax)
    lines += [
        [('SALDO AL CORTE', 200000, 260000), ('$', 333000, 337000), amount(closing)],
        [('PAGO MINIMO', 450000, 500000), ('100.00', 560000, 590000)],
        [('PERIODO', 450000, 500000), ('DEL 03/10/25 AL 02/11/25', 510000, 600000)],
        [('FECHA', 30000, 60000)] + ([('FECHA', 90000, 120000)] if second_date else [])
        + [('CONCEPTO', 200000, 250000), ('IMPORTE', 500000, 550000)],
    ]
    if kinds:
        # The date columns' kind words on their own line under the date heading ('FECHA' / 'AUTORIZACION').
        lines.append([(kinds[0], 25000, 80000), (kinds[1], 88000, 135000)])
    for move in movements or [('14/10/25', 'SU PAGO GRACIAS', '-300.00')]:
        day, second, text, value = move if len(move) == 4 else (move[0], move[0], *move[1:])
        lines.append(movement_line(day, second, text, value, second_date))
    if continued is None:
        return [page(1, lines)]
    header = [[('ESTADO DE CUENTA', 450000, 560000)], [('EMPRESA DE PRUEBA SA DE CV', 20000, 200000)]]
    return [page(1, lines), page(2, header + [movement_line(*move, second_date) for move in continued])]


def movement_line(day, second, text, value, second_date, second_at=90000):
    return ([(day, 30000, 70000)] + ([(second, second_at, second_at + 40000)] if second_date else [])
            + [(text, 200000, 330000), (value, 560000 - 6000 * len(value), 560000)])


def read(sources):
    statements = read_statements(sources)
    assert len(statements) == 1, statements
    return statements[0]


def charges(st):
    return [r for r in st['_rows'] if r['kind'] == 'transaction' and r['fields'].get('source_basis') == C.SOURCE_BASIS]


class CreditLineSummaryChargeTests(unittest.TestCase):
    def setUp(self):
        # The engine keeps readings of recent documents; a test reading the same fixture with the switch off
        # must not be answered from a reading made with it on.
        E._READINGS.clear()
        E._LIVE_READINGS.clear()

    tearDown = setUp

    def test_interest_and_iva_from_the_summary_reconcile_the_period(self):
        st = read(statement())
        self.assertTrue(st['engine']['proved'], (st['engine'], C.LAST_REFUSAL))
        self.assertEqual(st['engine']['basis'], C.BASIS)
        self.assertEqual((st['balance_convention'], st['account_type']), ('liability_owed', 'credit_card'))
        added = charges(st)
        self.assertEqual([(r['fields']['summary_charge'], r['fields']['amount_minor'], r['fields']['direction'],
                           r['fields']['date'], r['fields']['summary_page'], r['page_number']) for r in added],
                         [('interest', '2000', 'debit', '2025-11-02', 1, 1), ('tax', '320', 'debit', '2025-11-02', 1, 1)])
        self.assertTrue(all('from the period summary, page 1' in r['fields']['description'] for r in added))
        self.assertEqual(added[0]['fields']['charge_group'], 'interest')
        self.assertNotIn('charge_group', added[1]['fields'])
        moves = [r for r in st['_rows'] if r['kind'] == 'transaction' and r not in added]
        self.assertEqual([(r['fields']['direction'], r['fields']['amount_minor']) for r in moves], [('credit', '30000')])
        balances = {r['fields']['description']: int(r['fields']['balance']) for r in st['_rows'] if r['kind'] == 'balance'}
        net = sum(int(r['fields']['amount_minor']) * (1 if r['fields']['direction'] == 'debit' else -1)
                  for r in st['_rows'] if r['kind'] == 'transaction')
        self.assertEqual(balances['Opening Balance'] + net, balances['Closing Balance'])
        # The summary's component lines are not left as whole-statement totals the added charges would contradict.
        self.assertFalse([r for r in st['_rows'] if r['kind'] == 'statement_total'])
        self.assertFalse([r for r in st['_rows'] if r['kind'] == 'unresolved'])

    def test_switch_off_holds_the_period_as_before(self):
        with mock.patch.object(C, 'ENABLED', False):
            st = read(statement())
        self.assertEqual((st['engine']['proved'], st['engine']['reason']), (False, 'not_reconciled'))
        self.assertFalse(charges(st))

    def test_a_period_the_charges_do_not_reconcile_stays_held(self):
        st = read(statement(closing='723.21'))
        self.assertEqual((st['engine']['proved'], st['engine']['reason']), (False, 'not_reconciled'))
        self.assertFalse(charges(st))
        self.assertEqual(C.LAST_REFUSAL['step'], 'no_single_reading')

    def test_a_printed_payments_total_that_differs_stays_held(self):
        st = read(statement(payments='310.00'))
        self.assertFalse(st['engine']['proved'])
        self.assertFalse(charges(st))
        self.assertEqual(C.LAST_REFUSAL['step'], 'payments_total_differs')

    def test_no_double_when_the_movements_already_list_the_interest(self):
        # The movements list the interest too: adding the summary's would count it twice. Even a closing
        # that only that double count would reach is refused.
        listed = [('14/10/25', 'SU PAGO GRACIAS', '-300.00'), ('02/11/25', 'INTERESES DEL PERIODO', '20.00')]
        for closing in ('743.20', '723.20'):
            st = read(statement(movements=listed, closing=closing))
            self.assertFalse(st['engine']['proved'], closing)
            self.assertFalse(charges(st))
            self.assertEqual(C.LAST_REFUSAL['step'],
                             'movement_lists_a_charge' if closing == '743.20' else 'no_single_reading')

    def test_a_movement_of_a_summary_charge_amount_is_ambiguous_and_stays_held(self):
        listed = [('14/10/25', 'SU PAGO GRACIAS', '-300.00'), ('20/10/25', 'CARGO VARIO', '20.00')]
        st = read(statement(movements=listed, closing='743.20'))
        self.assertFalse(st['engine']['proved'])
        self.assertFalse(charges(st))
        self.assertEqual(C.LAST_REFUSAL['step'], 'movement_lists_a_charge')

    def test_the_tax_must_be_printed_on_the_line_after_the_interest(self):
        st = read(statement(tax_next=False))
        self.assertFalse(st['engine']['proved'])
        self.assertFalse(charges(st))
        self.assertEqual(C.LAST_REFUSAL['step'], 'tax_line')

    def test_an_unnamed_second_movement_date_keeps_the_period_held_unchanged(self):
        st = read(statement(second_date=True))
        self.assertEqual((st['engine']['proved'], st['engine']['reason']), (False, 'not_reconciled'))
        self.assertFalse(charges(st))

    def moves(self, st):
        return [(r['fields'].get('date'), r['fields'].get('authorization_date'), r['fields'].get('booking_date'),
                 r['fields'].get('value_date')) for r in st['_rows']
                if r['kind'] == 'transaction' and r['fields'].get('source_basis') != C.SOURCE_BASIS]

    def test_application_date_under_an_authorisation_heading_is_the_date_of_record(self):
        listed = [('13/10/25', '14/10/25', 'SU PAGO GRACIAS', '-300.00')]
        st = read(statement(second_date=True, kinds=('AUTORIZACION', 'APLICACION'), movements=listed))
        self.assertTrue(st['engine']['proved'], st['engine'])
        self.assertEqual(st['engine']['basis'], C.BASIS)
        self.assertEqual(self.moves(st), [('2025-10-14', '2025-10-13', None, None)])
        self.assertEqual(len(charges(st)), 2)

    def test_application_date_switch_off_keeps_the_period_held_as_before(self):
        listed = [('13/10/25', '14/10/25', 'SU PAGO GRACIAS', '-300.00')]
        with mock.patch.object(E, 'CREDIT_LINE_APPLICATION_DATE', False):
            st = read(statement(second_date=True, kinds=('AUTORIZACION', 'APLICACION'), movements=listed))
        self.assertEqual((st['engine']['proved'], st['engine']['reason']), (False, 'not_reconciled'))
        self.assertFalse(charges(st))

    def test_an_application_date_after_the_period_keeps_the_period_held(self):
        listed = [('01/11/25', '04/11/25', 'SU PAGO GRACIAS', '-300.00')]
        st = read(statement(second_date=True, kinds=('AUTORIZACION', 'APLICACION'), movements=listed))
        self.assertFalse(st['engine']['proved'])
        self.assertFalse(charges(st))
        self.assertFalse(any(m[1] for m in self.moves(st)))

    def test_an_application_date_before_its_authorisation_keeps_the_period_held(self):
        listed = [('15/10/25', '14/10/25', 'SU PAGO GRACIAS', '-300.00')]
        st = read(statement(second_date=True, kinds=('AUTORIZACION', 'APLICACION'), movements=listed))
        self.assertFalse(st['engine']['proved'])
        self.assertFalse(charges(st))

    def test_kind_words_in_the_other_order_are_not_an_application_date(self):
        listed = [('13/10/25', '14/10/25', 'SU PAGO GRACIAS', '-300.00')]
        st = read(statement(second_date=True, kinds=('APLICACION', 'AUTORIZACION'), movements=listed))
        self.assertFalse(st['engine']['proved'])
        self.assertFalse(charges(st))

    def test_a_continuation_page_without_a_date_heading_takes_the_proved_one(self):
        # fin-queue3 L18 (BBVA credit line, 2026-10-26): page 2 prints its movement lines under the page header only.
        first = [('13/10/25', '14/10/25', 'SU PAGO GRACIAS', '-200.00')]
        later = [('20/10/25', '21/10/25', 'INTERN.PAGO TDC', '-100.00')]
        st = read(statement(second_date=True, kinds=('AUTORIZACION', 'APLICACION'), movements=first, continued=later))
        self.assertTrue(st['engine']['proved'], st['engine'])
        self.assertEqual(self.moves(st), [('2025-10-14', '2025-10-13', None, None), ('2025-10-21', '2025-10-20', None, None)])
        with mock.patch.object(E, 'CREDIT_LINE_CONTINUED_HEADING', False):
            E._READINGS.clear()
            E._LIVE_READINGS.clear()
            held = read(statement(second_date=True, kinds=('AUTORIZACION', 'APLICACION'), movements=first,
                                  continued=later))
        self.assertFalse(held['engine']['proved'])

    def test_a_continuation_page_printing_its_own_date_words_or_other_columns_is_not_continued(self):
        first = [('13/10/25', '14/10/25', 'SU PAGO GRACIAS', '-200.00')]
        later = [('20/10/25', '21/10/25', 'INTERN.PAGO TDC', '-100.00')]
        # The page prints a date word of its own above the line ('FECHA' with no kind words): it must be read
        # as a heading, and it is not the proved one.
        sources = statement(second_date=True, kinds=('AUTORIZACION', 'APLICACION'), movements=first, continued=later)
        sources[1]['rows'].insert(2, dict(row_index=2, cells=[]))
        own = page(2, [[('ESTADO DE CUENTA', 450000, 560000)], [('FECHA', 30000, 60000), ('FECHA', 90000, 120000)],
                       movement_line(*later[0], True)])
        st = read(sources[:1] + [own])
        self.assertFalse(st['engine']['proved'])
        # The second date printed in another column than the proved page's.
        E._READINGS.clear()
        E._LIVE_READINGS.clear()
        shifted = page(2, [[('ESTADO DE CUENTA', 450000, 560000)], movement_line(*later[0], True, second_at=140000)])
        st = read(sources[:1] + [shifted])
        self.assertFalse(st['engine']['proved'])

    def test_a_bbva_credit_line_is_read_as_amounts_owed_not_as_a_deposit_account(self):
        # fin-queue3 L5/L18 (2026-10-26): the statement prints the bank's legal name and 'Estado de Cuenta', which
        # the cash-management profile matched, reading the credit line as a deposit account. The credit-line
        # profile's two phrases outrank it.
        bank = [[('BBVA MEXICO S.A., INSTITUCION DE BANCA MULTIPLE', 20000, 400000)],
                [('ESTADO DE CUENTA', 450000, 560000)], [('LINEA CREDITO DIGITAL PYME', 420000, 590000)]]
        from services.financial import statement_engine_profiles as P
        from services.financial.statement_engine_routing import _profiled
        sources = statement(bank=bank)
        reading, name = _profiled(sources, read_statements(sources))
        self.assertEqual(name, 'bbva-mexico-credit-line')
        (st,) = reading
        self.assertEqual((st['balance_convention'], st['account_type']), ('liability_owed', 'credit_card'))
        self.assertTrue(st['engine']['proved'], st['engine'])
        with mock.patch.object(P, 'PROFILES_OFF', {'bbva-mexico-credit-line'}):
            E._READINGS.clear()
            E._LIVE_READINGS.clear()
            self.assertEqual(P.matching_profile(P.profile_text(sources), P.furniture_text(sources))['name'],
                             'bbva-mexico-cash-management')

    BBVA = [[('BBVA MEXICO S.A., INSTITUCION DE BANCA MULTIPLE', 20000, 400000)],
            [('ESTADO DE CUENTA', 450000, 560000)], [('LINEA CREDITO DIGITAL PYME', 420000, 590000)]]

    def profiled(self, sources, **changes):
        from services.financial import statement_engine_profiles as P
        profile = dict(P.matching_profile(P.profile_text(sources), P.furniture_text(sources)), **changes)
        E._READINGS.clear()
        E._LIVE_READINGS.clear()
        (st,) = [st for st in read_statements(sources, profile=profile) if st['period_start']]
        return st

    def test_a_payment_allocation_box_beside_the_summary_is_not_a_charge_total(self):
        # fin-queue3 L18 (ENE 26): the box beside the summary prints the interest and fees a payment covered
        # ('Intereses 100.54', 'Comisiones 10.17'); the period's own charges are zero.
        sources = statement(bank=self.BBVA, interest='0.00', tax='0.00', closing='700.00')
        lines = sources[0]['rows']
        box = [[('INTERESES', 450000, 500000), ('100.54', 560000, 590000)],
               [('COMISIONES', 450000, 500000), ('10.17', 560000, 590000)]]
        at = next(i for i, r in enumerate(lines) if r['cells'][0]['expected_text'] == 'PAGOS') + 1
        sources = [page(1, [[(c['expected_text'], c['locator']['rect'][0], c['locator']['rect'][2]) for c in r['cells']]
                            for r in lines[:at]] + box
                        + [[(c['expected_text'], c['locator']['rect'][0], c['locator']['rect'][2]) for c in r['cells']]
                           for r in lines[at:]])]
        st = self.profiled(sources)
        self.assertTrue(st['engine']['proved'], st['engine'])
        held = self.profiled(sources, labels={})
        self.assertEqual((held['engine']['proved'], held['engine']['reason']), (False, 'printed_total_differs'))

    def quiet_month(self, *, amounts=('0.00',) * 9, opening='0.00', closing_amount=None, movement=None):
        lines = self.BBVA + [
            [('NO. DE CREDITO', 300000, 380000), ('1234', 400000, 430000), ('5678', 435000, 465000),
             ('9012', 470000, 500000), ('3456', 505000, 535000)],
            [('EMPRESA DE PRUEBA SA DE CV', 20000, 200000)],
            [('MONEDA NACIONAL', 20000, 120000)],
            [('LIMITE DE CREDITO', 20000, 120000), ('5,000.00', 130000, 180000)],
            [('SALDO INICIAL DEL PERIODO', 200000, 300000), ('+$', 323000, 336000), amount(opening)],
        ] + [[('LINEA %d' % i, 200000, 300000), ('+$', 323000, 336000), amount(a)] for i, a in enumerate(amounts)] + [
            [('OTROS CARGOS', 200000, 300000), ('+$', 323000, 336000), amount('0.00')],
            [('SALDO AL CORTE', 200000, 260000), ('$', 333000, 337000)] + ([amount(closing_amount)] if closing_amount else []),
            [('PAGO MINIMO', 450000, 500000), ('0.00', 560000, 590000)],
            [('PERIODO', 450000, 500000), ('DEL 03/08/25 AL 02/09/25', 510000, 600000)],
            [('FECHA', 30000, 60000), ('FECHA', 90000, 120000), ('CONCEPTO', 200000, 250000), ('IMPORTE', 500000, 550000)],
            [('AUTORIZACION', 25000, 80000), ('APLICACION', 88000, 135000)],
        ]
        if movement:
            lines.append(movement_line(*movement, True))
        return [page(1, lines)]

    def closing(self, st):
        return [r['fields'] for r in st['_rows'] if r['kind'] == 'balance' and r['fields']['description'] == 'Closing Balance']

    def test_a_month_printing_no_closing_amount_and_only_zeros_closes_at_its_zero_opening(self):
        # fin-queue3 L5 (09 MIDA BBVA CREDITO SEP 25): 'Saldo al Corte $' printed with no amount.
        st = self.profiled(self.quiet_month())
        self.assertTrue(st['engine']['proved'], st['engine'])
        (closing,) = self.closing(st)
        self.assertEqual((closing['balance'], closing['balance_basis']), ('0', E.BLANK_CLOSING_BASIS))
        self.assertEqual(closing['balance_derivation']['movement_lines'], '0')
        with mock.patch.object(E, 'BLANK_CLOSING_QUIET', False):
            off = self.profiled(self.quiet_month())
        self.assertEqual((off['engine']['proved'], off['engine']['reason']), (False, 'no_closing'))

    def test_a_blank_closing_is_not_proved_by_a_non_zero_amount_an_opening_or_a_movement(self):
        cases = dict(
            amount=self.quiet_month(amounts=('0.00',) * 8 + ('110.71',)),
            opening=self.quiet_month(opening='110.71'),
            few=self.quiet_month(amounts=('0.00',) * 3),
            movement=self.quiet_month(movement=('13/08/25', '14/08/25', 'SU PAGO GRACIAS', '-0.01')))
        for name, sources in cases.items():
            st = self.profiled(sources)
            self.assertFalse(any(f.get('balance_basis') == E.BLANK_CLOSING_BASIS for f in self.closing(st)), name)
        # A closing printed with its amount is read as printed, never by this rule.
        st = self.profiled(self.quiet_month(closing_amount='0.00'))
        self.assertTrue(st['engine']['proved'], st['engine'])
        self.assertNotIn('balance_basis', self.closing(st)[0])

    def test_zero_charges_add_nothing(self):
        st = read(statement(interest='0.00', tax='0.00', closing='700.00'))
        # Reconciled by the movements alone: the general reader proves it without this reading.
        self.assertNotEqual(st['engine'].get('basis'), C.BASIS)
        self.assertFalse(charges(st))


if __name__ == '__main__':
    unittest.main()
