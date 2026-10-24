"""Santander products sharing an account's last six digits: another product, or a copy (fail closed)."""
from collections import Counter
from types import SimpleNamespace
from uuid import uuid4

from services.financial import santander_subaccounts as sub

DAY = ('2026-01-05', 1000, 'debit')


class _Session:
    def __init__(self, rows):
        self.rows = rows

    def scalars(self, _query):
        return [SimpleNamespace(transaction_date=d, ordering_date=None, amount_minor=a, direction=r,
                                ledger_status='admitted', superseded_by_id=None) for d, a, r in self.rows]


def _case(monkeypatch, held, saved='65-50000001-2', saved_rows=(), reading=None, institution='Santander'):
    item = SimpleNamespace(id=uuid4(), summary=dict(account=held, institution=institution))
    account = SimpleNamespace(institution_name='BANCO SANTANDER MEXICO', identifier_as_printed=saved,
                              identifier_normalised=''.join(c for c in saved if c.isdigit()))
    monkeypatch.setattr(sub, 'held_reading', lambda *a, **k: reading)
    return sub.another_product(_Session(list(saved_rows)), None, item, SimpleNamespace(id=1), account)


def _reading(number, payments=(), beside=None, pages=(1, 3)):
    others = [dict(account_reference=beside, period_start='2026-01-01', period_end='2026-01-31', page_numbers=[1, 2])] if beside else []
    return dict(number=''.join(c for c in number if c.isdigit()), payments=Counter(payments), start='2026-01-01',
                end='2026-01-31', pages=set(pages), others=others)


def test_other_numbers_needs_two_complete_numbers_sharing_the_last_six_digits():
    assert sub.other_numbers({'65500000012'}, '66-50000001-2')
    assert not sub.other_numbers({'65500000012'}, '65-50000001-2')  # the same product
    assert not sub.other_numbers({'65500000012'}, '000001-2')  # incomplete: not proven
    assert not sub.other_numbers({'500000012'}, '66-50000001-2')
    assert not sub.other_numbers({'65500000012'}, '66-50000009-9')


def test_products_differ_when_the_file_prints_the_other_product_beside_it(monkeypatch):
    assert _case(monkeypatch, '66-50000001-2', reading=_reading('66-50000001-2', beside='65-50000001-2'))


def test_products_differ_when_the_held_payments_are_not_the_saved_ones(monkeypatch):
    assert _case(monkeypatch, '66-50000001-2', saved_rows=[DAY],
                 reading=_reading('66-50000001-2', [('2026-01-07', 5, 'credit'), ('2026-01-09', 6, 'credit')]))


def test_a_copy_carrying_the_saved_money_stays_a_copy_whatever_number_it_reads(monkeypatch):
    assert not _case(monkeypatch, '66-50000001-2', saved_rows=[DAY], reading=_reading('66-50000001-2', [DAY]))


def test_identity_unread_or_ambiguous_stays_a_copy(monkeypatch):
    assert not _case(monkeypatch, '66-50000001-2', reading=None)  # unread now, or not Santander
    assert not _case(monkeypatch, '66-50000001-2', reading=_reading('65-50000001-2', beside='65-50000001-2'))
    assert not _case(monkeypatch, '66-50000001-2', reading=_reading('66-50000001-2'))  # no payments, nothing beside
    assert not _case(monkeypatch, '66-50000001-2', reading=_reading('66-50000001-2', beside='65-50000001-2', pages=(1, 2)))
    assert not _case(monkeypatch, '66-50000001-2', institution='Santender',
                     reading=_reading('66-50000001-2', beside='65-50000001-2'))
    assert not _case(monkeypatch, '6650000001', reading=_reading('6650000001', beside='65-50000001-2'))


def test_the_same_product_stays_a_copy(monkeypatch):
    assert not _case(monkeypatch, '65-50000001-2', reading=_reading('65-50000001-2', beside='66-50000001-2'))


def test_switch_off_keeps_the_old_hold(monkeypatch):
    monkeypatch.setattr(sub, 'ENABLED', False)
    assert not _case(monkeypatch, '66-50000001-2', reading=_reading('66-50000001-2', beside='65-50000001-2'))
