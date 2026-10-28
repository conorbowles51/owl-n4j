"""Naming the other side of a payment from its matching payment in another account of the case. Every fixture
is invented: names, accounts, amounts and dates are made up for the test."""
import unittest
import uuid
from types import SimpleNamespace

from services.financial.payment_party_matches import banks_in, compatible, match_parties


def _id():
    return str(uuid.uuid4())


ACCOUNTS = dict(
    alpha=dict(account_id=_id(), holder='ALPHA EJEMPLO SA DE CV', institution='Banco Santander Mexico', identifier='65-11111111-1'),
    beta=dict(account_id=_id(), holder='BETA PRUEBA SA DE CV', institution='Banco Santander Mexico', identifier='65-22222222-2'),
    gamma=dict(account_id=_id(), holder='ALPHA EJEMPLO SA DE CV', institution='BBVA Mexico', identifier='0100000001'),
    card=dict(account_id=_id(), holder='JANE EXAMPLE', institution='Capital One', identifier='****0001'),
    bank=dict(account_id=_id(), holder='JANE EXAMPLE / JOHN EXAMPLE', institution='Truist Bank', identifier='Share 0001'),
)


def row(account, description, direction, amount=1234567, day='2024-03-05', name=None, reason='', currency='MXN'):
    return dict(id=_id(), source_document_id=_id(), amount_minor=amount, currency=currency, direction=direction,
                ordering_date=day, ordering_date_source='transaction', transaction_date=day, description=description,
                name=name, reason=reason, **ACCOUNTS[account])


class MatchPartiesTests(unittest.TestCase):
    def test_unique_enlace_pair_names_both_sides(self):
        out = row('alpha', '0000000 CARGO TRANSFERENCIA ENLACE PAGO DE PRUEBA', 'debit')
        into = row('beta', '0000000 ABONO TRANSFERENCIA ENLACE PAGO DE PRUEBA', 'credit')
        found = match_parties([out, into])
        self.assertEqual(found[out['id']]['value'], 'BETA PRUEBA SA DE CV · Banco Santander Mexico 65-22222222-2')
        self.assertEqual(found[out['id']]['source'], 'matched_payment')
        self.assertEqual(found[out['id']]['matched_transaction_id'], into['id'])
        self.assertIn('only payment in the case that matches', found[out['id']]['explanation'])
        self.assertEqual(found[into['id']]['value'], 'ALPHA EJEMPLO SA DE CV · Banco Santander Mexico 65-11111111-1')

    def test_two_candidates_name_nobody(self):
        out = row('alpha', 'CARGO TRANSFERENCIA ENLACE PAGO DE PRUEBA', 'debit')
        first = row('beta', 'ABONO TRANSFERENCIA ENLACE PAGO DE PRUEBA', 'credit')
        second = row('gamma', 'ABONO TRANSFERENCIA ENLACE PAGO DE PRUEBA', 'credit', day='2024-03-06')
        self.assertEqual(match_parties([out, first, second]), {})

    def test_far_apart_payment_of_the_same_amount_does_not_compete(self):
        out = row('alpha', 'CARGO TRANSFERENCIA ENLACE PAGO DE PRUEBA', 'debit')
        into = row('beta', 'ABONO TRANSFERENCIA ENLACE PAGO DE PRUEBA', 'credit')
        later = row('beta', 'ABONO TRANSFERENCIA ENLACE PAGO DE PRUEBA', 'credit', day='2024-09-05')
        self.assertIn(out['id'], match_parties([out, into, later]))

    def test_named_rows_are_not_renamed(self):
        out = row('alpha', 'CARGO TRANSFERENCIA ENLACE PAGO DE PRUEBA', 'debit', name='BETA PRUEBA SA DE CV')
        into = row('beta', 'ABONO TRANSFERENCIA ENLACE PAGO DE PRUEBA', 'credit')
        found = match_parties([out, into])
        self.assertNotIn(out['id'], found)
        self.assertIn(into['id'], found)
        # A matching line that names a third party is not this payment's other leg.
        out['name'] = 'SOMEONE ELSE SA DE CV'
        self.assertEqual(match_parties([out, into]), {})

    def test_line_naming_another_bank_does_not_match(self):
        out = row('gamma', 'T17 SPEI ENVIADO INBURSA 0000001PAGO Ref. 0000000001', 'debit')
        into = row('alpha', 'ABONO TRANSFERENCIA SPEI RECIBIDO', 'credit')
        self.assertEqual(match_parties([out, into]), {})

    def test_matching_line_that_names_someone_else_does_not_match(self):
        out = row('gamma', 'T17 SPEI ENVIADO SANTANDER 0000001PAGO Ref. 0000000001', 'debit', amount=1234561)
        into = row('beta', 'ABONO TRANSFERENCIA SPEI RECIBIDO DE BBVA MEXICO', 'credit', amount=1234561, name='OTRA EMPRESA SA DE CV')
        self.assertEqual(match_parties([out, into]), {})
        into['name'] = 'ALPHA EJEMPLO SA DE CV'
        self.assertIn(out['id'], match_parties([out, into]))

    def test_cheque_deposit_only_matches_a_cheque(self):
        out = row('gamma', 'W01 TRASPASO A TERCEROS PAGO BMRCASH', 'debit')
        into = row('alpha', 'M97 DEPOSITO CHEQUE BBVA', 'credit')
        self.assertEqual(compatible(into, out), 'a cheque deposit can only match a cheque')

    def test_transfer_inside_one_bank_needs_that_bank_or_a_shared_reference(self):
        out = row('gamma', 'W01 TRASPASO A TERCEROS GASTOS BMRCASH Ref. REFX0012345', 'debit', amount=1234561)
        into = row('alpha', 'ABONO TRANSFERENCIA ENLACE prestamo', 'credit', amount=1234561)
        self.assertEqual(match_parties([out, into]), {})
        into['description'] = 'Deposito Concepto: REFX0012345 DEPOSITO DE TERCERO'
        self.assertIn(out['id'], match_parties([out, into]))

    def test_round_amount_between_different_holders_needs_something_in_common(self):
        out = row('alpha', 'CARGO TRANSFERENCIA ENLACE PAGO F1', 'debit', amount=5000000)
        into = row('beta', 'ABONO TRANSFERENCIA ENLACE PAGO F1', 'credit', amount=5000000)
        self.assertEqual(match_parties([out, into]), {})
        out['description'] = 'CARGO TRANSFERENCIA ENLACE PAGO FACTURA 90210'
        into['description'] = 'ABONO TRANSFERENCIA ENLACE PAGO FACTURA 90210'
        self.assertIn(out['id'], match_parties([out, into]))

    def test_card_payment_names_the_paying_account(self):
        paid = row('card', 'CAPITAL ONE MOBILE PYMT', 'credit', amount=12345, currency='USD', reason='Card payment (from the holder’s bank)')
        paying = row('bank', 'Withdrawal ACH CAPITAL ONE TYPE: MOBILE PMT', 'debit', amount=12345, currency='USD',
                     day='2024-03-06', name='CAPITAL ONE')
        found = match_parties([paid, paying])
        self.assertEqual(found[paid['id']]['value'], 'JANE EXAMPLE / JOHN EXAMPLE · Truist Bank Share 0001')
        self.assertTrue(found[paid['id']]['own_account'])
        self.assertIn('1 day apart', found[paid['id']]['explanation'])
        # A payment that names its own bank (a fee) is not the other leg.
        paying['name'] = 'Truist'
        self.assertEqual(match_parties([paid, paying]), {})

    def test_account_with_disputed_holder_is_shown_without_a_holder(self):
        from services.financial.payment_party_matches import disputed_holders
        conflicts = [dict(field='holder_name', stored='BETA PRUEBA SA DE CV', offered='DELTA OTRA SA DE CV'),
                     dict(field='holder_name', stored='BETA PRUEBA SA DE CV', offered='DELTA OTRA SA DE CV')]
        self.assertEqual(disputed_holders('BETA PRUEBA SA DE CV', conflicts), ['DELTA OTRA SA DE CV'])
        self.assertEqual(disputed_holders('BETA PRUEBA SA DE CV', [dict(field='currency', offered='USD')]), [])
        out = row('alpha', 'CARGO TRANSFERENCIA ENLACE PAGO DE PRUEBA', 'debit')
        into = row('beta', 'ABONO TRANSFERENCIA ENLACE PAGO DE PRUEBA', 'credit')
        into['other_holders'] = ['DELTA OTRA SA DE CV']
        found = match_parties([out, into])[out['id']]
        self.assertEqual(found['value'], 'Banco Santander Mexico 65-22222222-2')
        self.assertIn('more than one holder name', found['explanation'])
        self.assertFalse(found['own_account'])

    def test_holder_prefix_must_end_on_a_word(self):
        from services.financial.payment_party_matches import _same_holder
        self.assertFalse(_same_holder('ANA', 'ANALYTICS EJEMPLO SA'))
        self.assertTrue(_same_holder('ALPHA EJEMPLO', 'ALPHA EJEMPLO SA DE CV'))

    def test_cash_and_bank_charges_never_match(self):
        out = row('alpha', 'RETIRO EN EFECTIVO CAJERO', 'debit', amount=1234561)
        into = row('beta', 'ABONO TRANSFERENCIA ENLACE', 'credit', amount=1234561)
        self.assertEqual(match_parties([out, into]), {})

    def test_banks_in(self):
        self.assertEqual(banks_in('T17 SPEI ENVIADO BMONEX 0000001'), {'MONEX'})
        self.assertEqual(banks_in('BBVA BANCOMER'), {'BBVA'})
        self.assertEqual(banks_in('CITI TRENDS #123'), set())


class LabelViewTests(unittest.TestCase):
    def _row(self, labels=None, raw=None, description='CARGO TRANSFERENCIA ENLACE PAGO'):
        return SimpleNamespace(id=uuid.uuid4(), account_id=uuid.uuid4(), case_id=uuid.uuid4(), direction='debit',
                               description=description, counterparty_raw=raw,
                               metadata_={'investigation_labels': labels or {}}, provenance={})

    def test_match_fills_only_an_empty_other_side(self):
        from services.financial.payment_labels import payment_label_view
        matched = dict(value='BETA PRUEBA SA DE CV · Banco Santander Mexico 65-22222222-2', source='matched_payment',
                       rule='matched-payment', version='matched-payment/1', explanation='Named from the matching payment.')
        view = payment_label_view(self._row(), stored=None, matched=matched)
        self.assertEqual(view['to_name'], matched['value'])
        self.assertEqual(view['label_sources']['to_name']['source'], 'matched_payment')
        # The statement's recorded counterparty and a person's label both win.
        self.assertEqual(payment_label_view(self._row(raw='PRINTED NAME'), stored=None, matched=matched)['to_name'], 'PRINTED NAME')
        view = payment_label_view(self._row(labels={'to_name': 'Chosen Name', 'version': 1}), stored=None, matched=matched)
        self.assertEqual((view['to_name'], view['label_sources']['to_name']['source']), ('Chosen Name', 'investigator'))
        # A name the description prints wins too.
        printed = self._row(description='PAGO TRANSFERENCIA SPEI HORA 10:00:00 ENVIADO A BBVA MEXICO A LA CUENTA 012180000000000001 AL CLIENTE GAMMA EJEMPLO SA DE CV')
        self.assertEqual(payment_label_view(printed, stored=None, matched=matched)['label_sources']['to_name']['source'], 'description')


class CoverageTests(unittest.TestCase):
    def test_matched_payment_counts_as_named(self):
        from services.financial.party_coverage import tally
        rows = [dict(id='a', case_id='c', description='XQZ 123', direction='debit', institution_name='Example Bank',
                     account_type='checking', counterparty_raw=None, labels=None)]
        self.assertEqual(tally(rows)['total']['bare'], 1)
        self.assertEqual(tally(rows, {'a'})['total']['named'], 1)


if __name__ == '__main__':
    unittest.main()
