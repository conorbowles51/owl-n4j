"""A teller deposit receipt whose deposit a saved statement already records leaves the statement queue.

Statement files often carry the teller receipts for deposits (Andrews: "Deposit to FREE CHECKING 0040 /
Prev Bal / Amount / New Bal"). The reader recognises such a page as a receipt (``document_review``), so it
is never a statement, but the batch item stayed in the queue as unreadable until a person opened it.

The receipt settles itself, as System, only when every printed fact ties it to exactly one admitted
statement payment:

* the receipt reads uniquely: amount, effective date (a two-digit year is read as 20yy and must then
  be confirmed by the payment's date), masked account reference, the share it was paid
  into, the previous and the new balance, and previous balance + amount = new balance;
* exactly one admitted credit of that amount, dated within three days of the effective date, on an
  account whose number ends with the receipt's visible digits and share, whose running balance after
  the payment is the receipt's new balance (so the balance before it is the receipt's previous balance).

The item is then left unimported (reversible: Restore) with the reason naming the payment, and the match
is recorded on the item (``receipt_settlement``). Nothing is added to the ledger: the deposit is already
there once, from the statement. Anything else stays in the queue exactly as before.

Switch: LOUPE_FINANCIAL_RECEIPT_SETTLEMENT (default on; 0 turns it off).
"""
import logging
import os
import re
from datetime import date, timedelta

from sqlalchemy import select

log = logging.getLogger(__name__)

ENABLED = os.environ.get('LOUPE_FINANCIAL_RECEIPT_SETTLEMENT', '1') != '0'
# A receipt printing several deposits (deposit_receipt_proposal.SEVERAL) settles when every deposit ties, by the same
# rule, to its own admitted payment. Switch LOUPE_FINANCIAL_RECEIPT_SETTLE_SEVERAL (default on).
SEVERAL = os.environ.get('LOUPE_FINANCIAL_RECEIPT_SETTLE_SEVERAL', '1') != '0'
BASIS = 'receipt_deposit_on_saved_statement'
DOCUMENT_REVIEW = 'This is a receipt or payment document. Open its document review.'
_NEEDED = ('payment_amount', 'account_reference', 'deposit_account', 'previous_balance', 'new_balance')


def _effective(field):
    """The effective date; a two-digit year (``11/18/22``) is read as 20yy, which the matching statement
    payment (same account, amount and balances, within three days) then confirms."""
    if field.get('value') and not field.get('issues'):
        return date.fromisoformat(field['value'])
    m = re.fullmatch(r'(\d{2})/(\d{2})/(\d{2})', (field.get('raw') or '').strip())
    return date(2000 + int(m[3]), int(m[1]), int(m[2])) if m else None


def _minor(value):
    from services.financial.statement_import_proposal import exact_amount
    return int(exact_amount(value.replace('$', '').strip(), 'USD'))


def receipt_payment(session, *, case_id, document):
    """The one admitted statement payment this receipt's printed facts tie it to, or None."""
    if not document or document.get('kind') != 'deposit_receipt' or not document.get('supported'):
        return None
    fields = {f['key']: f for f in document.get('fields') or []}
    return _payment(session, case_id, fields)


def receipt_payments(session, *, case_id, document):
    """The admitted statement payments a receipt's printed facts tie it to: [the one payment] of a receipt of one
    deposit, or one distinct payment for every deposit of a receipt printing several (SEVERAL, all or nothing);
    else []."""
    one = receipt_payment(session, case_id=case_id, document=document)
    if one is not None:
        return [one]
    several = (document or {}).get('deposits') if SEVERAL else None
    if not several or document.get('kind') != 'deposit_receipt' or len(several.get('items') or []) < 2:
        return []
    found = []
    for block in several['items']:
        payment = _payment(session, case_id, dict(block, effective_date=several['effective_date'],
                                                  account_reference=several['account_reference']))
        if payment is None or any(p.id == payment.id for p in found):
            return []
        found.append(payment)
    return found


def _payment(session, case_id, fields):
    from postgres.models.financial import FinancialTransaction as T, FinancialSourceDocument as D, FinancialAccount as A
    if any(not (fields.get(key) or {}).get('value') or fields[key].get('issues') for key in _NEEDED):
        return None
    try:
        amount, previous, new = (_minor(fields[k]['value']) for k in ('payment_amount', 'previous_balance', 'new_balance'))
        effective = _effective(fields.get('effective_date') or {})
    except (ValueError, TypeError):
        return None
    if effective is None:
        return None
    share = re.fullmatch(r'.*?(\d{4})', fields['deposit_account']['value'].strip())
    digits = re.sub(r'\D', '', fields['account_reference']['value'])
    if amount <= 0 or previous + amount != new or not share or len(digits) < 4:
        return None
    suffix = digits + share[1]
    rows = session.execute(select(T, A).join(D, D.id == T.source_document_id).join(A, A.id == T.account_id).where(
        T.case_id == case_id, T.ledger_status == 'admitted', T.superseded_by_id.is_(None), D.status == 'admitted',
        T.direction == 'credit', T.amount_minor == amount,
        T.transaction_date.between(effective - timedelta(days=3), effective + timedelta(days=3)))).all()
    hits = [t for t, a in rows if (a.identifier_normalised or '').endswith(suffix) and t.running_balance_minor == new]
    return hits[0] if len(hits) == 1 else None


def settle_receipts(session, *, case_id, batch_id, file_id, actor):
    """Leave unimported every receipt item of this file whose deposit a saved statement records. Returns their ids."""
    from postgres.models.financial_import_batches import FinancialImportBatchItem as Item
    from services.financial import import_batches as ib
    from services.financial.statement_import import read_statement_import
    if not ENABLED:
        return []
    settled = []
    items = [i for i in session.scalars(select(Item).where(Item.batch_id == batch_id, Item.file_id == file_id,
             Item.status == 'attention'))
             if any((p or {}).get('message') == DOCUMENT_REVIEW for p in (i.summary or {}).get('problems') or [])]
    for item in items:
        try:
            proposal = read_statement_import(session, case_id=case_id, evidence_file_id=file_id,
                                             statement_id=item.statement_key or None)
        except Exception:
            continue
        payments = receipt_payments(session, case_id=case_id, document=proposal.get('document_review'))
        if not payments:
            continue
        payment = payments[0]
        record = dict(basis=BASIS, transaction_id=str(payment.id), ref_id=payment.ref_id,
                      transaction_date=payment.transaction_date.isoformat(), amount_minor=str(payment.amount_minor),
                      currency=payment.currency, running_balance_minor=str(payment.running_balance_minor))
        reason = (f'Teller deposit receipt, not a statement: its deposit is already recorded once from the statement '
                  f'(payment {payment.ref_id}, {payment.transaction_date.isoformat()}, same account, amount and '
                  f'balances before and after). Nothing was added to the ledger.')
        if len(payments) > 1:
            record['payments'] = [dict(transaction_id=str(p.id), ref_id=p.ref_id, transaction_date=p.transaction_date.isoformat(),
                                       amount_minor=str(p.amount_minor), running_balance_minor=str(p.running_balance_minor))
                                  for p in payments]
            reason = (f'Teller deposit receipt of {len(payments)} deposits, not a statement: each deposit is already '
                      f'recorded once from the statement (payments ' + ', '.join(f'{p.ref_id} ({p.transaction_date.isoformat()})'
                                                                               for p in payments)
                      + ', same accounts, amounts and balances before and after). Nothing was added to the ledger.')
        revision = ib._digest(dict(status=item.status, request=item.review_request,
                                   decision=(item.summary or {}).get('import_decision')))
        item.summary = {**(item.summary or {}), 'receipt_settlement': record}
        ib.leave_unimported(session, case_id=case_id, batch_id=item.batch_id, item_id=item.id, action='skip',
                            reason=reason, expected_revision=revision, actor=actor)
        from services.financial.judgements import record_judgement
        for paid in payments:
            record_judgement(session, case_id=case_id, subject_type='transaction', subject_id=paid.id,
                             rule_id='erica.receipt_settled', target_key='receipt', reading=str(item.id),
                             source_document_id=paid.source_document_id, statement_period_id=paid.statement_period_id,
                             summary=(f"A teller deposit receipt (page {proposal.get('page_numbers', [''])[0] if proposal.get('page_numbers') else ''}) "
                                      f"is left unimported: this payment already records its deposit (same account, "
                                      f"amount and balances before and after)."),
                             evidence=dict(item_id=str(item.id), evidence_file_id=str(file_id), **record))
        settled.append(str(item.id))
        log.info('Receipt %s settled against payment %s', str(item.id)[:8], payment.ref_id)
    return settled
