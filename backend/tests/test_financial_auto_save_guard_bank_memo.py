"""The bank name compared for every pair of saved periods is folded once per name, with the same result."""
from services.financial import auto_save_guard as guard


def test_memoised_bank_equals_the_plain_fold():
    names = ['BANCO MONEX', 'Monex', 'Banco Monex, S.A.', 'BBVA México', 'bbva mexico', 'Navy Federal', '  ', '', None,
             'Grupo Financiero Banorte', 'THE BANK', 'Crédit Agricole', 'S.A.']
    for name in names * 2:
        assert guard._bank(name) == guard._bank_of.__wrapped__(name)


def test_values_that_are_not_text_are_folded_without_the_memo():
    for value in (1234, ['BANCO', 'MONEX'], {'name': 'Monex'}):
        assert guard._bank(value) == guard._bank_of.__wrapped__(value)
