"""Santander products that share an account's last digits are different accounts, not copies of each other.

Santander Mexico prints a customer's cheque and savings products under account numbers that differ only in
their two-digit product prefix (65-XXXXXXXX-X and 66-XXXXXXXX-X), often in one statement, on the same dates.
The re-read's copy guard (recovery_readers.copy_of_saved) compares the last six digits, because an older
reading can misread leading digits; so a held statement of one product was kept as a "copy" of the other
product's saved statement and never read again. The ledger already keys the two products apart (institution
and the full number), so once the guard lets the statement through, it is saved into its own account by the
ordinary readiness and save checks; nothing merges.

The guard treats a saved period as another product, not as the held statement's copy, only when all hold
(fail closed: otherwise the copy hold stays):

* both are Santander statements (the bank as read on each side);
* both read a complete account number (11 digits), the numbers share their last six digits and differ;
* the held statement's own reading has complete payments (date, amount, direction), and at least half of
  them are not among the saved period's admitted payments. A copy whose number was misread would still
  carry the copy's money: that stays a copy (compared and set aside by saved_copies). A reading with unread
  lines can only lack payments, so the payments it did read still tell; or
* the held statement's own file prints the saved number as another statement with the same dates, read
  from a different set of pages (one document printing both products, each in its own section: neither is
  a copy of the other; a product with no movements has no payments to compare).

A saved period with the same full number stays a copy whatever its bank wording or product type.

Switch: LOUPE_FINANCIAL_SANTANDER_SUBACCOUNTS (default on). Off: every saved period with the same last six
digits and dates keeps the held statement as a copy, as before.
"""
import os
from collections import Counter

ENABLED = os.environ.get('LOUPE_FINANCIAL_SANTANDER_SUBACCOUNTS', '1').strip().lower() not in (
    '0', 'false', 'no', 'off')
COMPLETE_DIGITS = 11


def _digits(value):
    return ''.join(ch for ch in str(value or '') if ch.isdigit())


def _santander(value):
    return 'santander' in str(value or '').lower()


def other_numbers(saved_numbers, held_number):
    """True when two complete Santander account numbers share their last six digits and differ."""
    held = _digits(held_number)
    saved = {_digits(value) for value in saved_numbers if _digits(value)}
    if len(held) != COMPLETE_DIGITS or not saved or any(len(value) != COMPLETE_DIGITS for value in saved):
        return False
    return held not in saved and all(value[-6:] == held[-6:] for value in saved)


def held_reading(session, case_id, item, cache=None):
    """What the held statement's current reading says: its number, payments, and the file's other statements."""
    from services.financial.import_batches import initial_request
    from services.financial.pdf_candidates import PdfMappingError
    from services.financial.saved_copies import copy_facts
    from services.financial.statement_import import read_statement_import
    try:
        proposal = read_statement_import(session, case_id=case_id, evidence_file_id=item.file_id,
            currency=(item.summary or {}).get('currency') or None, statement_id=item.statement_key or None,
            _cache=cache if cache is not None else {}, _include_period_checks=False,
            _include_duplicate_disposition=False)
    except PdfMappingError:
        return None
    metadata = proposal.get('metadata') or {}
    if not _santander(metadata.get('institution')):
        return None
    own = proposal.get('statement_id')
    choices = [c for c in proposal.get('statement_choices') or [] if not c.get('document_kind')]
    mine = next((c for c in choices if c.get('id') == own), None)
    facts = copy_facts(proposal, initial_request(proposal), item.summary)
    return dict(number=_digits(metadata.get('account_number')), payments=facts['payments'],
                start=metadata.get('period_start'), end=metadata.get('period_end'),
                pages=set((mine or {}).get('page_numbers') or proposal.get('statement_page_numbers') or []),
                others=[c for c in choices if c.get('id') != own])


def _printed_beside(reading, saved_numbers):
    """The held statement's own file prints the saved number as another statement with the same dates.

    The two are read from different pages (they may share the account summary page): one section read twice
    would carry the same pages.
    """
    if not reading['pages']:
        return False
    return any(_digits(c.get('account_reference')) in saved_numbers and c.get('period_start') == reading['start']
               and c.get('period_end') == reading['end'] and c.get('page_numbers')
               and set(c['page_numbers']) != reading['pages'] for c in reading['others'])


def another_product(session, case_id, item, period, account, *, cache=None, memo=None):
    """True when the saved ``period`` (of ``account``) is another Santander product than held ``item``. Read only."""
    if not ENABLED:
        return False
    summary = item.summary or {}
    numbers = {_digits(value) for value in (account.identifier_normalised, account.identifier_as_printed)} - {''}
    if not (_santander(summary.get('institution')) and _santander(account.institution_name)):
        return False
    if not other_numbers(numbers, summary.get('account')):
        return False
    memo = memo if memo is not None else {}
    if item.id not in memo:
        memo[item.id] = held_reading(session, case_id, item, cache)
    reading = memo[item.id]
    if not reading or reading['number'] != _digits(summary.get('account')) or not other_numbers(numbers, reading['number']):
        return False  # the current reading does not print the held number: not proven
    if _printed_beside(reading, numbers):
        return True
    payments = reading['payments']
    if not payments:
        return False
    from sqlalchemy import select
    from postgres.models.financial import FinancialTransaction
    saved = Counter((str(row.transaction_date or row.ordering_date), int(row.amount_minor), row.direction)
                    for row in session.scalars(select(FinancialTransaction).where(
                        FinancialTransaction.statement_period_id == period.id))
                    if row.ledger_status == 'admitted' and row.superseded_by_id is None)
    absent = sum((payments - saved).values())
    return 2 * absent >= sum(payments.values())
