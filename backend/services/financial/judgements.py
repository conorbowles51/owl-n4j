"""The processor's judgement calls, shown to a person who may confirm or correct them (fin-judgements).

A judgement call is a value the processor chose that the page does not print outright, or a choice between two
readings: an opening balance that is the closing less the payments, a money cell read from a damaged glyph and fixed
by the printed balances, a currency taken from the file name, a copy set aside as the same statement. The rule still
decides exactly as before; this module only records that it decided, why, and how strongly the printed controls
back it ('proved': a guess the printed controls still prove; 'inferred': a value the page does not print).

Two ways in, both never raising into the rule:

* ``record_judgement(session, ...)``: a rule with a session and a saved subject records at the line it decides
  (a duplicate set aside, a period refiled, a reading replaced).
* ``record_saved(session, document)``: what a reading rule decided travels with the reading into the saved
  statement (each row keeps its reading, ``value_repairs`` and ``*_basis`` fields; the review keeps each value's
  stated reason; the file keeps the System's detail fills). When the statement is written, ``detect`` reads those
  traces and records one judgement per decision on the exact period field or transaction it touched. The same
  detection over statements saved before this module existed is the retrofit (read only apart from these rows).

Nothing is held by a judgement. A person's answer is recorded here (confirmed, or corrected through the existing
correction path with its reason and adjudication linked); a correction proposes a lesson, it never changes a rule.
"""
from __future__ import annotations

import logging
import re
import uuid
from collections import Counter
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

log = logging.getLogger(__name__)

# rule id -> (label a reviewer reads in the filter, where the rule is written down, strength it records).
# Rule ids appear in a tooltip footer only; the label and each judgement's sentence are what a person reads.
RULES = {
    'L8.unprinted_opening': ('Opening balance worked back from the closing', 'fin-queue3 L8', 'inferred'),
    'image.page_reading': ('Payments read from the page images', 'fin-queue3 L8/K1, fin-erica L17/L24', 'proved'),
    'image.printed_total': ('Printed total taken from the page image', 'fin-queue3 L8 (IMAGE_TOTALS)', 'proved'),
    'image.date': ('Date read from the page image', 'fin-queue3 L38', 'proved'),
    'L1.glyph_cell': ('Damaged money cell fixed by the printed balances', 'fin-erica L1', 'proved'),
    'L12.adjacent_cells': ('Damaged neighbouring cells fixed together', 'fin-erica L12', 'proved'),
    'L16.one_glyph': ('One unreadable character fixed by the printed balances', 'fin-erica L16', 'proved'),
    'L19.both_neighbours': ('Running balance fixed by the payments either side', 'fin-erica L19', 'proved'),
    'L12.balance_digits': ('Lost decimal mark repaired from the running balance', 'fin-queue3 L12/L14', 'proved'),
    'L4.currency_from_name': ('Currency from the file name', 'fin-queue3 L4', 'inferred'),
    'autofill.currency_account': ("Currency from the account's saved statements", 'field_proposals', 'inferred'),
    'autofill.currency_case': ("Currency assumed from the case's usual currency", 'field_proposals', 'inferred'),
    'autofill.detail': ("Statement detail filled from the account's saved statements", 'field_proposals', 'inferred'),
    'L10.one_date': ('One of two printed dates unread; the other is used', 'fin-queue3 L10', 'proved'),
    'erica.date_month': ('Date month fixed by the printed period', 'fin-erica L15', 'proved'),
    'erica.date_ordering': ('Date taken from the statement order only', 'fin-erica L21', 'inferred'),
    'date.from_neighbour_line': ('Date taken from the line above or below', 'fin-queue3 L15', 'inferred'),
    'merrick.date_glyphs': ('Damaged date read within the billing cycle', 'fin-erica L13', 'proved'),
    'merrick.interest_date': ('Interest dated on the closing date', 'fin-erica L13', 'inferred'),
    'L18.direction_from_balances': ('In or out taken from the printed balances', 'fin-erica L18', 'proved'),
    'card.payment_sign': ('Card payment sign fixed by the printed controls', 'card_summary', 'proved'),
    'amount.daily_balance': ('Amount fixed by the printed daily balance', 'fin-erica L2', 'proved'),
    'amount.balance_step': ('Amount taken from the printed balance step', 'statement_engine', 'proved'),
    'IC.cover_opening': ('Balance read from the cover summary', 'fin-queue3 IC', 'proved'),
    'opening.after_first_movement': ('Opening printed after the first movement', 'statement_engine', 'proved'),
    'opening.before_kept_dates': ('Opening from the running balance before the kept dates', 'statement_overlap_trim',
                                  'inferred'),
    'closing.last_kept_movement': ('Closing from the running balance of the last kept movement',
                                   'statement_overlap_trim', 'inferred'),
    'L17.zero_opening': ('Opening of zero from the first day balance', 'fin-queue3 L17', 'inferred'),
    'credit_line.opening': ('Credit-line opening worked back from the amount owed', 'fin-queue3 L18', 'inferred'),
    'L5.blank_closing': ('Blank closing read as a quiet period', 'fin-queue3 L5', 'inferred'),
    'total.less_covered': ('Printed total less movements saved elsewhere', 'fin-queue3 L21', 'inferred'),
    'santander.integral_balance': ('Running balance from the Santander integral layout', 'santander_integral',
                                   'proved'),
    'merrick.summary_order': ('Summary values taken in printed order', 'fin-erica L13', 'inferred'),
    'period.start_derived': ('Period start not printed; taken from the previous statement', 'card periods', 'inferred'),
    'L26.duplicate_set_aside': ('Saved twice: one copy set aside', 'fin-queue3 L26 / r2', 'proved'),
    'L19.unreadable_copy': ('Unreadable copy matched to a saved statement', 'fin-queue3 L19', 'proved'),
    'copies.held_copy': ('Held copy matched to a saved statement', 'saved_copies (fin-queue2)', 'proved'),
    'L20.part_of_saved': ('Leftover split inside a saved statement', 'fin-queue3 L20', 'proved'),
    'reader.replacement': ('Saved copy replaced by a reading that balances', 'saved_reading_replacement', 'proved'),
    'L30c.contract_refile': ("Filed in the contract's currency account", 'fin-queue3 L30c', 'inferred'),
    'guard.neighbour_check': ('Auto-save passed on the saved statements next to it', 'fin-queue3 L1/L28', 'proved'),
    'L9.scan_amount_marks': ('Scan mark or space inside an amount read past', 'fin-queue3 L9', 'proved'),
    'L31.scan_day_letter': ('Letter in a printed day read as a digit', 'fin-queue3 L31 / fin-erica L1', 'proved'),
    'L22.vanished_key': ('Held earlier reading retired; the statement is saved', 'fin-queue3 L22', 'proved'),
    'erica.receipt_settled': ('Deposit receipt matched to a saved payment', 'fin-erica L3/L23', 'proved'),
    'agent.page_entry': ('Entered by hand from the page (agent)', 'fin-queue*/fin-erica hand work', 'proved'),
    'agent.correction': ('Corrected by hand (agent)', 'fin-queue*/fin-erica hand work', 'proved'),
    'agent.refile': ('Refiled by hand (agent)', 'fin-accounts / fin-queue3 L30c', 'inferred'),
    'agent.currency_refile': ('Currency changed by hand (agent)', 'fin-queue3 L27', 'inferred'),
}

# Field basis written by a reading rule -> rule id. Only bases that choose a value the page does not print outright
# or choose between readings; a printed value's basis records nothing.
FIELD_BASIS = {
    ('date_basis', 'liquidation_date_operation_unread'): 'L10.one_date',
    ('date_basis', 'month_figure_fixed_by_printed_period'): 'erica.date_month',
    ('date_basis', 'statement_end_ordering_only'): 'erica.date_ordering',
    ('date_basis', 'date_of_the_same_reference_line_before'): 'date.from_neighbour_line',
    ('date_basis', 'date_printed_on_the_line_below'): 'date.from_neighbour_line',
    ('date_basis', 'readable_glyphs_within_printed_billing_cycle'): 'merrick.date_glyphs',
    ('date_basis', 'merrick_interest_printed_on_closing_date'): 'merrick.interest_date',
    ('direction_basis', 'printed_sign_and_balances'): 'L18.direction_from_balances',
    ('direction_basis', 'printed_word_and_balances'): 'L18.direction_from_balances',
    ('direction_basis', 'pinned_by_printed_controls'): 'card.payment_sign',
    ('amount_basis', 'figure_fixed_by_printed_daily_balance'): 'amount.daily_balance',
    ('amount_basis', 'printed_balance_step'): 'amount.balance_step',
    ('amount_basis', 'printed_digits_confirmed_by_running_balance'): 'L12.balance_digits',
    ('balance_basis', 'cover_balance_summary'): 'IC.cover_opening',
    ('balance_basis', 'printed_opening_after_first_movement'): 'opening.after_first_movement',
    ('balance_basis', 'running_balance_before_kept_dates'): 'opening.before_kept_dates',
    ('balance_basis', 'running_balance_on_last_kept_movement'): 'closing.last_kept_movement',
    ('balance_basis', 'zero_opening_from_first_day_balance_and_blank_prior_cash'): 'L17.zero_opening',
    ('balance_basis', 'credit_line_total_owed_less_movements'): 'credit_line.opening',
    ('balance_basis', 'blank_closing_quiet_summary'): 'L5.blank_closing',
    ('balance_basis', 'santander_integral_running_balance'): 'santander.integral_balance',
    ('balance_basis', 'merrick_summary_box_values_in_printed_order'): 'merrick.summary_order',
    ('total_basis', 'printed_total_less_covered_movements'): 'total.less_covered',
}
GLYPH_BASIS = {
    'one_unread_glyph_fixed_by_printed_balances': 'L16.one_glyph',
    'balance_fixed_by_both_neighbouring_payments': 'L19.both_neighbours',
    'single_glyph_readings_jointly_pinned_by_printed_balances': 'L12.adjacent_cells',
}
# What each reading rule did, said for one value (a payment's field, or a statement balance / total).
ROW_SENTENCES = {
    'L10.one_date': 'only one of the two printed dates of this line could be read; the other printed date is used.',
    'erica.date_month': 'the month of this date is damaged on the page; the printed statement period fixes it.',
    'erica.date_ordering': "this line's date cannot be read; it is placed by the order of the lines only.",
    'date.from_neighbour_line': 'this line prints no date of its own; it takes the date of the neighbouring line '
                                'with the same reference.',
    'merrick.date_glyphs': 'this date is partly damaged; the readable characters fit only one day of the printed '
                           'billing cycle.',
    'merrick.interest_date': "this interest line prints no date; it is dated on the statement's closing date.",
    'L18.direction_from_balances': 'the sign is not legible; in or out follows from the printed balances before '
                                   'and after it.',
    'card.payment_sign': "the sign of this card payment is fixed by the statement's printed totals.",
    'amount.daily_balance': 'a figure of this amount is damaged; the printed daily balance fixes it.',
    'amount.balance_step': 'the amount is not legible; it is the step between the printed running balances.',
    'L12.balance_digits': 'the decimal mark of this amount is lost in the scan; the running balance confirms the '
                          'digits.',
}
CONTROL_SENTENCES = {
    'IC.cover_opening': 'is read from the cover summary, where the printed figures agree.',
    'opening.after_first_movement': 'is printed after the first movement rather than at the top; it is read from '
                                    'there.',
    'opening.before_kept_dates': 'is the running balance just before the dates this statement keeps; the other '
                                 'dates are saved in another statement.',
    'closing.last_kept_movement': 'is the running balance on the last movement this statement keeps.',
    'L17.zero_opening': "is not printed; it is zero because the first day's balance equals that day's movements.",
    'credit_line.opening': 'is not printed; it is the amount owed less this period\'s movements.',
    'L5.blank_closing': 'is printed blank; the summary prints only zeros, so it equals the opening.',
    'total.less_covered': 'is the printed total less the movements already saved in another statement.',
    'santander.integral_balance': 'is read from the running balance column of the integral statement layout.',
    'merrick.summary_order': 'is taken by its place in the summary box, because its label is damaged.',
}
FIELD_WORDS = {'date_basis': 'date', 'direction_basis': 'direction', 'amount_basis': 'amount',
               'balance_basis': 'balance', 'total_basis': 'total'}

OPENING_REASON_START = 'Opening balance not printed in these pages'
TOTAL_REASON_START = 'Printed total read from page image'
DATE_REASON_START = 'Date read from page image'
IMAGE_ROW_PREFIX = 'manual:vision-'
SYSTEM_NAMES = ('System',)


# ---------------------------------------------------------------------------
# Recording
# ---------------------------------------------------------------------------

def record_judgement(session, *, case_id, subject_type, subject_id, rule_id, summary, strength=None, evidence=None,
                     target_key='', reading='', source_document_id=None, statement_period_id=None, origin='processor'):
    """Record one judgement call; the same subject, rule, target and reading records once. Never raises: the rule
    that decided works exactly as before when recording fails. Returns the row (new or existing) or None."""
    from postgres.models.financial_judgements import FinancialJudgement as J
    try:
        strength = strength or RULES.get(rule_id, ('', '', 'inferred'))[2]
        reading, target_key = str(reading or '')[:80], str(target_key or '')[:48]
        key = (J.subject_type == subject_type, J.subject_id == subject_id, J.rule_id == rule_id,
               J.target_key == target_key, J.reading == reading)
        # Inside a savepoint, the lookup too: a failed statement must not abort the rule's own transaction.
        with session.begin_nested():
            existing = session.scalar(select(J).where(*key))
            if existing is not None:
                return existing
            row = J(id=uuid.uuid4(), case_id=case_id, subject_type=subject_type, subject_id=subject_id,
                    source_document_id=source_document_id, statement_period_id=statement_period_id, rule_id=rule_id,
                    target_key=target_key, reading=reading, origin=origin, strength=strength,
                    summary=' '.join(str(summary).split())[:2000], evidence=_jsonable(evidence or {}), status='open')
            session.add(row)
            session.flush()
        return row
    except Exception:  # noqa: BLE001 - recording only adds information; the rule's own work stands
        log.exception('Recording a judgement call failed (%s on %s %s); the rule\'s decision stands',
                      rule_id, subject_type, subject_id)
        return None


def _jsonable(value):
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


# ---------------------------------------------------------------------------
# Detection over a saved statement's own record
# ---------------------------------------------------------------------------

_EXPONENTS = {'JPY': 0, 'KRW': 0, 'CLP': 0, 'BHD': 3, 'KWD': 3, 'JOD': 3, 'OMR': 3, 'TND': 3}


def money(minor, currency=''):
    """'12,340.00' (the currency's own decimals)."""
    if minor is None:
        return ''
    try:
        minor = int(minor)
    except (TypeError, ValueError):
        return str(minor)
    exponent = _EXPONENTS.get((currency or '').upper(), 2)
    sign, minor = ('-' if minor < 0 else ''), abs(minor)
    whole, part = divmod(minor, 10 ** exponent) if exponent else (minor, 0)
    return f"{sign}{whole:,}" + (f".{part:0{exponent}d}" if exponent else '')


def _digits(text):
    return re.sub(r'\D', '', str(text or ''))


def _row_label(txn, currency):
    when = txn.transaction_date.isoformat() if getattr(txn, 'transaction_date', None) else 'no printed date'
    return f"Payment of {money(txn.amount_minor, currency)} ({when})"


def _repaired_part(held, chosen, amount_minor):
    """'amount' or 'balance': which money cell of the line the repair changed."""
    held_parts, chosen_parts = held.split(), chosen.split()
    if len(chosen_parts) == 2 and len(held_parts) == 2:
        return 'balance' if held_parts[0] == chosen_parts[0] else 'amount'
    digits = _digits(chosen).lstrip('0')
    return 'amount' if digits and digits == str(abs(int(amount_minor or 0))) else 'balance'


def detect(document, period, transactions, *, file=None):
    """[judgement dict] the saved statement's own record shows the processor decided. Pure: reads the document's
    stored reading and review, its transactions' provenance and the file's System detail fills."""
    meta = document.metadata_ or {}
    currency = (getattr(period, 'currency', None) or (meta.get('statement_import_request') or {}).get('currency') or '')
    found = []

    def add(subject_type, subject_id, rule_id, summary, target_key='', evidence=None, strength=None):
        found.append(dict(subject_type=subject_type, subject_id=subject_id, rule_id=rule_id, summary=summary,
                          target_key=target_key, evidence=evidence or {}, strength=strength))

    request = meta.get('statement_import_request') or {}
    original = meta.get('statement_import_original') or {}
    originals = {r.get('id'): r for r in original.get('rows') or [] if isinstance(r, dict)}
    period_subject = ('statement_period', period.id) if period is not None else ('source_document', document.id)
    # Period values chosen by the page-image reader (stated as each value's reason in the saved review).
    image_rows = 0
    for row in request.get('rows') or []:
        reason = str(row.get('reason') or '')
        rid = str(row.get('id') or '')
        if rid.startswith(IMAGE_ROW_PREFIX) and not row.get('excluded'):
            image_rows += 1
        if reason.startswith(OPENING_REASON_START):
            confirmed = reason.split('confirmed by', 1)[-1].strip(' .') if 'confirmed by' in reason else ''
            closing = getattr(period, 'closing_balance_minor', None)
            opening = getattr(period, 'opening_balance_minor', None)
            add(*period_subject, 'L8.unprinted_opening',
                f"Opening {money(opening if opening is not None else row.get('balance_minor'), currency)} is not "
                f"printed in these pages: it is the closing {money(closing, currency)} less this period's payments, "
                f"which agree with the printed counts and totals" + (f"; {confirmed} agrees with it." if confirmed else '.'),
                target_key='opening_balance',
                evidence=dict(page=row.get('manual_page'), chosen=row.get('balance_minor'), confirmed_by=confirmed,
                              reason=reason))
        elif reason.startswith(TOTAL_REASON_START):
            first = originals.get(rid) or {}
            before = (first.get('fields') or {}).get('balance')
            after = row.get('balance_minor')
            if before is not None and _digits(before) != _digits(after):
                direction = (first.get('fields') or {}).get('total_direction') or ''
                page = _page_of(reason)
                shown_before = money(before, currency) if re.fullmatch(r'-?\d+', str(before)) else before
                add(*period_subject, 'image.printed_total',
                    f"The printed {'deposits' if direction == 'credit' else 'withdrawals'} total is "
                    f"{money(after, currency)} as the page image of page {page} reads it (the text read "
                    f"{shown_before}); it agrees with the payments read.",
                    target_key=f'total_{direction or "printed"}',
                    evidence=dict(page=page, before=before, chosen=after, reason=reason))
    if image_rows:
        replaced = sum(1 for r in request.get('rows') or [] if r.get('excluded')
                       and str(r.get('reason') or '').startswith('Set aside: the reading of the page images'))
        add(*period_subject, 'image.page_reading',
            f"The {image_rows} payments of this statement are read from the page images"
            + (f" in place of {replaced} lines the text layer read" if replaced else '')
            + "; they reconcile with the printed opening and closing balances.",
            target_key='payments', evidence=dict(rows=image_rows, text_rows_set_aside=replaced))
    # Period values a reading rule chose (balance and total rows kept as controls, not payments).
    for rid, first in originals.items():
        fields = first.get('fields') or {}
        if first.get('kind') not in ('balance', 'statement_total'):
            continue
        for field, word in FIELD_WORDS.items():
            rule = FIELD_BASIS.get((field, fields.get(field)))
            if rule:
                role = (fields.get('description') or first.get('kind') or 'This value').strip()
                value = fields.get('balance')
                add(*period_subject, rule,
                    f"{role[:1].upper() + role[1:]} {money(value, currency)} (page {first.get('page_number')}) "
                    + CONTROL_SENTENCES.get(rule, RULES[rule][0].lower() + '.'),
                    target_key=_control_key(role, first),
                    evidence=dict(page=first.get('page_number'), basis=fields.get(field), value=value, row_id=rid))
    if period is not None and str(getattr(period, 'period_start_source', '') or '').endswith('derived'):
        add('statement_period', period.id, 'period.start_derived',
            f"The period start {period.period_start} is not printed: it is the day after the previous statement "
            f"of this account closes.", target_key='period_start',
            evidence=dict(period_start=str(period.period_start)))
    # Payments: each row keeps its reading.
    for txn in transactions:
        prov = txn.provenance or {}
        first = prov.get('statement_import_original') or {}
        fields = first.get('fields') or {}
        review = prov.get('statement_import_review') or {}
        page = first.get('page_number') or review.get('manual_page')
        label = _row_label(txn, currency)
        for repair in first.get('value_repairs') or []:
            basis = repair.get('basis') or ''
            rule = GLYPH_BASIS.get(basis, 'L1.glyph_cell')
            held = str(repair.get('held_text') or repair.get('page_reading') or '')
            chosen = str(repair.get('text') or '')
            target = _repaired_part(held, chosen, txn.amount_minor)
            add('transaction', txn.id, rule,
                f"{label}: the {target} cell on page {repair.get('page_number') or page} is damaged ('{held}'); it is "
                f"read as {chosen}, " + ("which the printed balances before and after it fix." if rule != 'L19.both_neighbours'
                                         else "which the payments before and after it both fix."),
                target_key=target, evidence=dict(page=repair.get('page_number') or page, before=held, chosen=chosen,
                                                 pinned_by=repair.get('pinned_by'), basis=basis or repair.get('method')))
        for field, word in FIELD_WORDS.items():
            rule = FIELD_BASIS.get((field, fields.get(field)))
            if rule:
                add('transaction', txn.id, rule,
                    f"{label} (page {page}): " + ROW_SENTENCES.get(rule, RULES[rule][0].lower() + '.'),
                    target_key=word, evidence=dict(page=page, basis=fields.get(field), field=word))
        for rule, cell, summary in _cell_marks(first, fields, label, page):
            add('transaction', txn.id, rule, summary, target_key=cell['target'],
                evidence=dict(page=cell['page'], before=cell['text'], column=cell['column']))
        if str(review.get('reason') or '').startswith(DATE_REASON_START):
            add('transaction', txn.id, 'image.date',
                f"{label}: the date is read from the page image of page {_page_of(review['reason'])}; "
                f"the text layer could not read it. The amount and running balance are the text's.",
                target_key='date', evidence=dict(page=_page_of(review['reason']), reason=review['reason']))
    # Details the System filled (currency, holder, bank, account) from the file name or saved statements.
    if file is not None:
        key = meta.get('statement_import_statement_id') or ''
        saved_by = next(((t.provenance or {}).get('confirmed_by') or {}).get('name') for t in transactions[:1]) \
            if transactions else ''
        for entry in (file.metadata_ or {}).get('financial_account_detail_history') or []:
            basis = str(entry.get('basis') or '')
            actor = (entry.get('actor') or {}).get('name') or ''
            if not basis or (entry.get('statement_id') or '') != key or actor not in SYSTEM_NAMES:
                continue
            for part in basis.split('; ') if basis.count(':') > 1 else [basis]:
                name, _, why = part.partition(':')
                rule, target = _detail_rule(name, why)
                if rule == 'autofill.currency_case' and saved_by in SYSTEM_NAMES:
                    # Saved with no person: the auto-save guard let the usual currency through only because the file
                    # name agrees and the pages, or every saved statement of this account, name the same currency.
                    rule = 'guard.neighbour_check'
                    why = (why.strip() + '; the automatic save accepted it because the file name agrees and the pages '
                           'or the saved statements of this account name the same currency')
                if rule:
                    add(*period_subject, rule, f"{name.strip()} is not printed as the statement's own: {why.strip()}.",
                        target_key=target, evidence=dict(basis=part.strip(), at=entry.get('at')))
    return found


_SPACED = re.compile(r'\d ,\d|\d, \d{3}|\d \.\d\d|\d\?$')
_DAY_LETTER = re.compile(r'(?=[0-9OolI|]{2}[/-])(?=.{0,1}[OolI|])[0-9OolI|]{2}[/-](?:\d\d|[A-Za-z]{3})')


def _cell_marks(first, fields, label, page):
    """(rule, cell, sentence) for the printed cells of a saved row the reader read past a scan mark (L9) or a
    letter standing for a day digit (L31); from the row's own stored cell text, nothing re-read."""
    def columns(*names):
        return {str(fields.get(k)) for k in names if fields.get(k) not in (None, '')}
    money_columns = columns('credit_column', 'debit_column', 'amount_column', 'balance_column')
    date_columns = columns('date_column', 'operation_date_column', 'liquidation_date_column')
    balance_columns, amount_columns = columns('balance_column'), columns('credit_column', 'debit_column', 'amount_column')
    for cell in first.get('source_cells') or []:
        if not isinstance(cell, dict):
            continue
        text = str(cell.get('expected_text') or '').strip()
        column = str(cell.get('column_index'))
        where = (cell.get('locator') or {}).get('page') or page
        if column in money_columns and _SPACED.search(text):
            if column in balance_columns and column not in amount_columns:
                target = 'balance'
            elif column in amount_columns and column not in balance_columns:
                target = 'amount'
            else:  # one cell printing the amount and the balance
                target = 'amount' if _SPACED.search(text.split()[0] if text.split() else '') else 'balance'
            yield ('L9.scan_amount_marks', dict(target=target, text=text, column=column, page=where),
                   f"{label}: the {target} on page {where} is printed '{text}' in the scan; the space or mark is read "
                   f"past, and the printed balances agree with the value read.")
        elif column in date_columns and _DAY_LETTER.fullmatch(text):
            yield ('L31.scan_day_letter', dict(target='date', text=text, column=column, page=where),
                   f"{label}: the date on page {where} is printed '{text}' in the scan; the letter is read as the "
                   f"digit it stands for.")


def _page_of(reason):
    found = re.search(r'page (\d+)', str(reason or ''))
    return int(found.group(1)) if found else None


def _control_key(role, row):
    text = (role or '').lower()
    if 'opening' in text or 'previous' in text or 'anterior' in text:
        return 'opening_balance'
    if 'closing' in text or 'new bal' in text:
        return 'closing_balance'
    return f"control_{row.get('id', '')}"[:48]


def _detail_rule(name, why):
    name, why = name.strip().lower(), why.lower()
    if name.startswith('currency'):
        if 'file name' in why:
            return 'L4.currency_from_name', 'currency'
        if "case's usual currency" in why:
            return 'autofill.currency_case', 'currency'
        return 'autofill.currency_account', 'currency'
    if name:
        return 'autofill.detail', name.split()[0][:48]
    return None, ''


def record_saved(session, document, *, period=None, transactions=None, file=None, origin='processor'):
    """Detect and record the judgement calls of one saved statement; never raises. Returns the rows recorded."""
    try:
        from postgres.models.evidence import EvidenceFile
        from postgres.models.financial import FinancialStatementPeriod, FinancialTransaction
        if period is None:
            period = session.scalar(select(FinancialStatementPeriod).where(
                FinancialStatementPeriod.source_document_id == document.id).limit(1))
        if transactions is None:
            transactions = list(session.scalars(select(FinancialTransaction).where(
                FinancialTransaction.source_document_id == document.id,
                FinancialTransaction.ledger_status == 'admitted')))
        if file is None and document.evidence_file_id:
            file = session.get(EvidenceFile, document.evidence_file_id)
        rows = []
        for found in detect(document, period, transactions, file=file):
            row = record_judgement(session, case_id=document.case_id, reading=str(document.id),
                                   source_document_id=document.id, statement_period_id=getattr(period, 'id', None),
                                   origin=origin, **found)
            if row is not None:
                rows.append(row)
        return rows
    except Exception:  # noqa: BLE001 - recording only adds information
        log.exception('Recording the judgement calls of saved statement %s failed; the statement stands',
                      getattr(document, 'id', None))
        return []


def record_on_document(session, document, rule_id, summary, *, target_key='', evidence=None, strength=None,
                       origin='processor', reading=None):
    """A rule deciding about a whole saved statement (set aside, replaced, refiled) records here; never raises."""
    try:
        from postgres.models.financial import FinancialStatementPeriod
        period = session.scalar(select(FinancialStatementPeriod).where(
            FinancialStatementPeriod.source_document_id == document.id).limit(1))
        subject = ('statement_period', period.id) if period is not None else ('source_document', document.id)
        return record_judgement(session, case_id=document.case_id, subject_type=subject[0], subject_id=subject[1],
                                rule_id=rule_id, summary=summary, strength=strength, evidence=evidence,
                                target_key=target_key, reading=reading if reading is not None else str(document.id),
                                source_document_id=document.id, statement_period_id=getattr(period, 'id', None),
                                origin=origin)
    except Exception:  # noqa: BLE001
        log.exception('Recording a judgement call (%s) failed; the decision stands', rule_id)
        return None


# ---------------------------------------------------------------------------
# What a person sees and answers
# ---------------------------------------------------------------------------

def label(rule_id):
    return RULES.get(rule_id, (rule_id, '', ''))[0]


def as_dict(row, *, file_id=None, filename=None):
    rule = RULES.get(row.rule_id, (row.rule_id, '', row.strength))
    return dict(id=str(row.id), case_id=str(row.case_id), subject_type=row.subject_type, subject_id=str(row.subject_id),
                source_document_id=str(row.source_document_id) if row.source_document_id else None,
                statement_period_id=str(row.statement_period_id) if row.statement_period_id else None,
                evidence_file_id=str(file_id) if file_id else None, filename=filename,
                rule_id=row.rule_id, rule_label=rule[0], rule_source=rule[1], target_key=row.target_key,
                origin=row.origin, strength=row.strength, summary=row.summary, evidence=row.evidence or {},
                page=(row.evidence or {}).get('page'), status=row.status, resolved_by=row.resolved_by,
                resolved_at=row.resolved_at.isoformat() if row.resolved_at else None,
                resolution_reason=row.resolution_reason,
                adjudication_id=str(row.adjudication_id) if row.adjudication_id else None,
                created_at=row.created_at.isoformat() if row.created_at else None)


ORIGIN_ORDER = {'agent': 0, 'processor': 1}
STRENGTH_ORDER = {'inferred': 0, 'proved': 1}
STATUS_ORDER = {'open': 0, 'corrected': 1, 'confirmed': 2}


def _current(query):
    """Only judgements on statements that still count (their saved document admitted)."""
    from postgres.models.financial import FinancialSourceDocument as D
    from postgres.models.financial_judgements import FinancialJudgement as J
    return query.outerjoin(D, D.id == J.source_document_id).where(
        (J.source_document_id.is_(None)) | (D.status != 'superseded'))


def list_judgements(session, case_id, *, source_document_id=None, statement_period_id=None, subject_ids=None,
                    status=None, strength=None, rule_id=None, origin=None, limit=500):
    from postgres.models.evidence import EvidenceFile as F
    from postgres.models.financial import FinancialSourceDocument as D
    from postgres.models.financial_judgements import FinancialJudgement as J
    query = _current(select(J, D.evidence_file_id, F.original_filename).where(J.case_id == case_id))
    query = query.outerjoin(F, F.id == D.evidence_file_id)
    if source_document_id:
        query = query.where(J.source_document_id == source_document_id)
    if statement_period_id:
        query = query.where(J.statement_period_id == statement_period_id)
    if subject_ids:
        query = query.where(J.subject_id.in_(subject_ids))
    for column, value in ((J.status, status), (J.strength, strength), (J.rule_id, rule_id), (J.origin, origin)):
        if value:
            query = query.where(column == value)
    rows = session.execute(query.limit(max(1, min(int(limit or 500), 5000)))).all()
    rows.sort(key=lambda r: (STATUS_ORDER.get(r[0].status, 3), ORIGIN_ORDER.get(r[0].origin, 2),
                             STRENGTH_ORDER.get(r[0].strength, 2), r[0].created_at or datetime.min.replace(tzinfo=timezone.utc)))
    return [as_dict(row, file_id=file_id, filename=name) for row, file_id, name in rows]


def counts(session, case_id):
    """{case: {total, inferred, open, ...}, statements: {document id: {...}}, rules: [...]} for one case."""
    from postgres.models.financial_judgements import FinancialJudgement as J
    from postgres.models.financial import FinancialSourceDocument as D
    rows = session.execute(_current(select(J.source_document_id, J.rule_id, J.strength, J.status, J.origin,
                                           D.evidence_file_id).where(J.case_id == case_id))).all()
    case, statements, rules = Counter(), {}, {}
    for document_id, rule_id, strength, status, origin, file_id in rows:
        for bucket in (case, statements.setdefault(str(document_id), Counter())):
            bucket['total'] += 1
            bucket[strength] += 1
            bucket[status] += 1
            bucket[origin] += 1
        statements[str(document_id)]['evidence_file_id'] = str(file_id) if file_id else None
        rule = rules.setdefault(rule_id, Counter())
        rule[status] += 1
        rule['total'] += 1
    return dict(case=dict(case), statements={k: dict(v) for k, v in statements.items()},
                rules=[dict(rule_id=k, label=label(k), source=RULES.get(k, ('', '', ''))[1], **v)
                       for k, v in sorted(rules.items(), key=lambda kv: -kv[1]['total'])])


def track_record(session, case_id=None):
    """Per rule: confirmed / corrected / open counts (one case, or every case when ``case_id`` is None)."""
    from postgres.models.financial_judgements import FinancialJudgement as J
    from sqlalchemy import func
    query = select(J.rule_id, J.status, func.count()).group_by(J.rule_id, J.status)
    if case_id is not None:
        query = query.where(J.case_id == case_id)
    table = {}
    for rule_id, status, n in session.execute(query):
        table.setdefault(rule_id, Counter())[status] += n
    out = []
    for rule_id in sorted(set(table) | set(RULES), key=lambda r: (-sum(table.get(r, {}).values()), r)):
        c = table.get(rule_id, Counter())
        out.append(dict(rule_id=rule_id, label=label(rule_id), source=RULES.get(rule_id, ('', '', ''))[1],
                        strength=RULES.get(rule_id, ('', '', ''))[2], open=c['open'], confirmed=c['confirmed'],
                        corrected=c['corrected'], total=sum(c.values())))
    return out


class JudgementError(ValueError):
    def __init__(self, message, status_code=422):
        super().__init__(message)
        self.status_code = status_code


def _get(session, case_id, judgement_id):
    from postgres.models.financial_judgements import FinancialJudgement as J
    row = session.scalar(select(J).where(J.id == judgement_id, J.case_id == case_id).with_for_update())
    if row is None:
        raise JudgementError('Judgement call not found in this case.', 404)
    return row


def confirm(session, *, case_id, judgement_id, actor, reason=''):
    """'Looks right': one click, no reason needed. The reinforcement signal for the rule."""
    row = _get(session, case_id, judgement_id)
    if row.status == 'corrected':
        raise JudgementError('This judgement call was already corrected.', 409)
    row.status, row.resolved_by, row.resolved_by_email = 'confirmed', actor.name, actor.email
    row.resolved_at, row.resolution_reason = datetime.now(timezone.utc), (reason or '').strip() or None
    session.commit()
    return as_dict(row)


def correct(session, *, case_id, judgement_id, actor, reason, adjudication_id=None):
    """'Correct it': the correction is made through the existing path (it writes its adjudication); this links it
    and records the reason. Without an adjudication id, the latest adjudication on the same subject (or on the
    statement's transactions/period) by this person since the judgement was recorded is linked."""
    from postgres.models.financial import AdjudicationEvent
    reason = (reason or '').strip()
    if not reason:
        raise JudgementError('Say why the processor was wrong; the reason is what improves the rule.')
    row = _get(session, case_id, judgement_id)
    linked = None
    if adjudication_id:
        linked = session.scalar(select(AdjudicationEvent).where(AdjudicationEvent.id == adjudication_id,
                                                                AdjudicationEvent.case_id == case_id))
        if linked is None:
            raise JudgementError('That correction was not found in this case.', 404)
    else:
        subjects = [row.subject_id] + [s for s in (row.statement_period_id, row.source_document_id) if s]
        linked = session.scalar(select(AdjudicationEvent).where(
            AdjudicationEvent.case_id == case_id, AdjudicationEvent.subject_id.in_(subjects),
            AdjudicationEvent.actor_email == actor.email,
            AdjudicationEvent.created_at >= (row.created_at or datetime.now(timezone.utc)) - timedelta(minutes=1))
            .order_by(AdjudicationEvent.created_at.desc()).limit(1))
    row.status, row.resolved_by, row.resolved_by_email = 'corrected', actor.name, actor.email
    row.resolved_at, row.resolution_reason = datetime.now(timezone.utc), reason
    row.adjudication_id = linked.id if linked is not None else None
    if linked is not None:
        row.evidence = dict(row.evidence or {}, correction=dict(decision=linked.decision, before=linked.before,
                                                                after=linked.after))
    session.commit()
    return as_dict(row)


def reopen(session, *, case_id, judgement_id, actor):
    row = _get(session, case_id, judgement_id)
    row.status, row.resolved_by, row.resolved_by_email, row.resolved_at = 'open', None, None, None
    row.resolution_reason, row.adjudication_id = None, None
    session.commit()
    return as_dict(row)


# ---------------------------------------------------------------------------
# Rules deciding about whole statements (they record where they decide)
# ---------------------------------------------------------------------------

def _period_facts(session, document):
    from postgres.models.financial import FinancialAccount, FinancialStatementPeriod, FinancialTransaction
    from sqlalchemy import func
    period = session.scalar(select(FinancialStatementPeriod).where(
        FinancialStatementPeriod.source_document_id == document.id).limit(1))
    rows = session.scalar(select(func.count()).select_from(FinancialTransaction).where(
        FinancialTransaction.source_document_id == document.id)) or 0
    account = session.get(FinancialAccount, period.account_id) if period is not None else None
    return period, rows, account


def _account_text(account):
    if account is None:
        return 'no account'
    number = account.identifier_as_printed or account.identifier_normalised or ''
    bank = account.institution_name or ''
    return ' '.join(str(x) for x in (bank, number, getattr(account, 'currency', None) or '') if x).strip() or str(account.id)[:8]


def record_replacement(session, replaced, document, *, adjudication_id=None):
    """A saved copy replaced by a reading that balances (or refiled to the contract's currency account)."""
    try:
        old, old_rows, old_account = _period_facts(session, replaced)
        new, new_rows, new_account = _period_facts(session, document)
        currency = getattr(new, 'currency', '') or ''
        refiled = old_account is not None and new_account is not None and old_account.id != new_account.id
        evidence = dict(replaced_source_document_id=str(replaced.id), adjudication_id=str(adjudication_id or ''),
                        before=dict(rows=old_rows, opening=getattr(old, 'opening_balance_minor', None),
                                    closing=getattr(old, 'closing_balance_minor', None),
                                    account=_account_text(old_account),
                                    period=[str(getattr(old, 'period_start', '') or ''), str(getattr(old, 'period_end', '') or '')]),
                        after=dict(rows=new_rows, opening=getattr(new, 'opening_balance_minor', None),
                                   closing=getattr(new, 'closing_balance_minor', None),
                                   account=_account_text(new_account),
                                   period=[str(getattr(new, 'period_start', '') or ''), str(getattr(new, 'period_end', '') or '')]))
        if refiled:
            rule = 'L30c.contract_refile'
            summary = (f"This period is filed in account {_account_text(new_account)} with the contract's other "
                       f"statements of its currency; it was saved in {_account_text(old_account)}. Its payments and "
                       f"balances are the saved ones. The earlier copy is kept and can be restored.")
            target = 'account'
        else:
            rule = 'reader.replacement'
            summary = (f"The saved copy ({old_rows} payments, opening {money(evidence['before']['opening'], currency) or 'missing'}, "
                       f"closing {money(evidence['before']['closing'], currency) or 'missing'}) is replaced by a reading that "
                       f"balances: {new_rows} payments, {money(evidence['after']['opening'], currency)} to "
                       f"{money(evidence['after']['closing'], currency)}. The earlier copy is kept and can be restored.")
            target = 'payments'
        return record_on_document(session, document, rule, summary, target_key=target, evidence=evidence)
    except Exception:  # noqa: BLE001
        log.exception('Recording a reader replacement judgement failed; the replacement stands')
        return None


def record_set_aside(session, document, primary, *, basis='', reason='', adjudication_id=None):
    """A saved copy set aside as the same printed statement as ``primary`` (shown on the copy that counts)."""
    try:
        file_name = ''
        if document.evidence_file_id:
            from postgres.models.evidence import EvidenceFile
            file = session.get(EvidenceFile, document.evidence_file_id)
            file_name = getattr(file, 'original_filename', '') or ''
        summary = (f"Another saved copy of this statement{(' (' + file_name + ')') if file_name else ''} is set aside "
                   f"as the same printed statement: equal payments and printed balances. This copy counts once. "
                   f"Restore the other copy if they are different statements.")
        return record_on_document(session, primary, 'L26.duplicate_set_aside', summary,
                                  target_key='copy', reading=str(document.id),
                                  evidence=dict(set_aside_source_document_id=str(document.id), basis=basis,
                                                reason=reason, adjudication_id=str(adjudication_id or ''),
                                                evidence_file_id=str(document.evidence_file_id or '')))
    except Exception:  # noqa: BLE001
        log.exception('Recording a duplicate set-aside judgement failed; the set-aside stands')
        return None


def record_held_copy(session, *, case_id, file, statement_key, saved, agreement, reading='', evidence=None):
    """A held copy (never saved) set aside because a saved statement prints the same account, period and balances."""
    try:
        rule = {'part_of_saved_statement': 'L20.part_of_saved',
                'printed_balances_of_saved_statement': 'L19.unreadable_copy'}.get(agreement, 'copies.held_copy')
        name = getattr(file, 'original_filename', '') or 'a held file'
        if rule == 'L20.part_of_saved':
            summary = (f"A leftover part of this statement in {name} is set aside: its pages are inside this saved "
                       f"statement and every payment and balance it reads is here.")
        elif rule == 'L19.unreadable_copy':
            summary = (f"A copy of this statement in {name} is set aside as already saved: its lines could not all be "
                       f"read, but its printed opening and closing equal this statement's and every payment it reads "
                       f"is here.")
        else:
            summary = (f"A held copy of this statement in {name} is set aside as already saved: the same account, dates, "
                       f"printed balances and payments as this saved statement.")
        document_id = saved.get('source_document_id')
        period_id = saved.get('statement_period_id')
        return record_judgement(session, case_id=case_id, subject_type='evidence_file', subject_id=file.id,
                                rule_id=rule, summary=summary, target_key=('copy:' + (statement_key or ''))[:48],
                                reading=reading, evidence=dict(evidence or {}, statement_key=statement_key,
                                                               evidence_file_id=str(file.id), filename=name),
                                source_document_id=uuid.UUID(str(document_id)) if document_id else None,
                                statement_period_id=uuid.UUID(str(period_id)) if period_id else None)
    except Exception:  # noqa: BLE001
        log.exception('Recording a held copy judgement failed; the set-aside stands')
        return None
