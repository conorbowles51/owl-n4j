"""Credit-line (amounts owed) periods whose summary prints interest and IVA that no movement line lists.

A Mexican revolving credit line statement ("Linea de Credito ... PyME") prints a period summary in one
column: SALDO INICIAL DEL PERIODO, + DISPOSICIONES, - PAGOS, + COMISIONES COBRADAS, + OTROS CARGOS,
INTERESES ORDINARIOS (SIN IVA), + I.V.A., INTERESES MORATORIOS (SIN IVA), SALDO AL CORTE. The period's
interest and the tax on it (IVA) are charged to the balance owed at the cut-off date but are not listed
among the movements ("Movimientos Efectuados"), so the movements alone never reconcile the printed
balances and the general reader holds the period ('not_reconciled').

This reading adds the summary's interest and IVA as rows of their own, under the general reader's
existing liability convention (amounts owed: a charge raises the balance, a payment lowers it; the
account stays the reader's 'credit_card' / 'liability_owed' type, A6/A7/C5). It applies only when all
of these hold, otherwise the period stays held exactly as before:

* the general reader did not prove the period, read it under the liability convention, and its only
  failure is that no reading of the movements reconciles the balances ('not_reconciled');
* the summary prints its interest line and, on the next line, its IVA line, each once, with an amount
  aligned with the summary's other amounts; the summary's own opening and closing lines (on the same
  page, around them) print the period's opening and closing balances;
* exactly one reading of the movement lines satisfies opening + movements + interest + IVA (+ moratory
  interest) = closing, to the cent; a movement printing a running balance must chain;
* every summary total that is read agrees with the movements: PAGOS with the payments, and DISPOSICIONES +
  COMISIONES COBRADAS + OTROS CARGOS with the charges; at least one of them is read (an independent
  control, as for every proved period), and no other printed total is left unexplained;
* no double: no movement line names interest or IVA, and no movement amount equals a summary charge (an
  ambiguous case stays held).

Each added row is marked as read from the period summary (``source_basis='period_summary'``, its page),
is labelled interest or tax (``summary_charge``), is dated on the period's printed cut-off date, and is a
charge (debit) of the amount printed. Nothing else in the reading changes.

Switch: LOUPE_FINANCIAL_CREDIT_LINE_SUMMARY_CHARGES (default on; 0/false/off/no turns it off).
"""
import os
import re

ENABLED = os.environ.get('LOUPE_FINANCIAL_CREDIT_LINE_SUMMARY_CHARGES', '1').strip().lower() not in (
    '0', 'false', 'off', 'no')
BASIS = 'credit_line_summary_charges'
SOURCE_BASIS = 'period_summary'
# Why the last call refused (a step name, for diagnosis only; never part of a reading).
LAST_REFUSAL = {}

OPENING = 'SALDO INICIAL DEL PERIODO'
CLOSING = 'SALDO AL CORTE'
INTEREST = 'INTERESES ORDINARIOS SIN IVA'
MORATORY = 'INTERESES MORATORIOS SIN IVA'
# The tax line as printed ('I.V.A.') and as scans read its first letter ('LV.A.', 'LLV.A.', '1.V.A.').
TAX = re.compile(r'[IL1]{1,2}\.?V\.?A')
# Summary totals the movements must agree with: the payments, and the charges listed as movements.
PAYMENTS = 'PAGOS'
CHARGES = ('DISPOSICIONES', 'COMISIONES COBRADAS', 'OTROS CARGOS')
# A printed sign between a label and its amount ('+$') read as one or two characters ('4', '5', 'IS').
SIGN_NOISE = re.compile(r'\S{1,2}')
# Summary amounts are printed right-aligned in one column: a value farther than this (share of the page
# width) from the interest amount's right edge is another column's.
ALIGN = 0.03
# A movement line naming interest or IVA could already list a summary charge.
NAMES_A_CHARGE = re.compile(r'INTERES|\bI\s?\.?\s?V\s?\.?\s?A\b')
DESCRIPTIONS = {'interest': 'INTERESES ORDINARIOS (SIN IVA)', 'moratory': 'INTERESES MORATORIOS (SIN IVA)',
                'tax': 'I.V.A.'}


def _refuse(step):
    LAST_REFUSAL.clear()
    LAST_REFUSAL.update(step=step)
    return None


def _value_after(pairs, index):
    """The amount printed for the label at ``pairs[index]``: its own first amount, or the first amount after
    sign noise read as a label of its own; None when another label comes first."""
    for position in range(index, len(pairs)):
        text, values = pairs[position]
        if position > index and not SIGN_NOISE.fullmatch(text or ''):
            return None
        amounts = [token for kind, token in values if kind == 'money']
        if amounts:
            return amounts[0]
    return None


def _right(token, row):
    return token['x1'] / (token.get('_width') or row.get('width') or 1)


def prove(rows, moves, candidates, controls, column_totals, style, exponent):
    """The one reading of the movements that the summary's interest and IVA reconcile, with those charges,
    or None (the period stays held). ``rows`` are the section's rows as the general reader read them;
    ``candidates`` its movement readings (``statement_engine._search``)."""
    from services.financial.statement_engine import label_pairs, money
    if not ENABLED:
        return _refuse('switch_off')
    if any(move.get('undated') for move in moves):
        return _refuse('undated_charge_line')
    if controls['section_total'] or column_totals or controls['day_opening']:
        return _refuse('other_printed_total')
    pairs_of = {}

    def pairs(row):
        if row['_index'] not in pairs_of:
            pairs_of[row['_index']] = label_pairs(row, style, exponent) if row['tokens'] else []
        return pairs_of[row['_index']]

    interest_rows = [row for row in rows if any(text == INTEREST for text, _ in pairs(row))]
    if len(interest_rows) != 1:
        return _refuse('interest_line')
    interest_row = interest_rows[0]
    position = interest_row['_index']
    tax_row = rows[position + 1] if position + 1 < len(rows) else None
    if (tax_row is None or tax_row['page'] != interest_row['page'] or not pairs(tax_row)
            or not TAX.fullmatch(pairs(tax_row)[0][0] or '')):
        return _refuse('tax_line')
    page = [row for row in rows if row['page'] == interest_row['page']]
    before = [row for row in page if row['_index'] < position and any(text == OPENING for text, _ in pairs(row))]
    after = [row for row in page if row['_index'] > position and any(text == CLOSING for text, _ in pairs(row))]
    if not before or not after:
        return _refuse('summary_bounds')
    top, bottom = before[-1]['_index'], after[0]['_index']
    window = [row for row in page if top <= row['_index'] <= bottom]
    interest_token = _value_after(pairs(interest_row), [t for t, _ in pairs(interest_row)].index(INTEREST))
    if interest_token is None:
        return _refuse('interest_unread')
    edge = _right(interest_token, interest_row)

    found = {}
    for row in window:
        for index, (text, _) in enumerate(pairs(row)):
            name = (text if text in (OPENING, CLOSING, INTEREST, MORATORY, PAYMENTS) + CHARGES
                    else 'tax' if row is tax_row and index == 0 else None)
            if name is None:
                continue
            if name in found:
                return _refuse('summary_label_twice')
            token = _value_after(pairs(row), index)
            value = money(token['t'], style, exponent) if token is not None else None
            if token is not None and abs(_right(token, row) - edge) > ALIGN:
                value = None
            found[name] = (value, row, token)
    opening, closing = found[OPENING][0], found[CLOSING][0]
    if opening is None or closing is None:
        return _refuse('summary_balances_unread')
    charges = []
    for name, kind, required in ((INTEREST, 'interest', True), ('tax', 'tax', True), (MORATORY, 'moratory', False)):
        if name not in found:
            if required:
                return _refuse('charge_missing')
            continue
        value, row, token = found[name]
        if value is None or value < 0:
            return _refuse('charge_unread')
        if value:
            charges.append(dict(kind=kind, amount=value, row=row, token=token))
    if not charges:
        return _refuse('no_summary_charge')
    extra = sum(charge['amount'] for charge in charges)

    # Every engine total control must be one of the summary's own lines (read here as a component).
    component_rows = {found[name][1]['_index'] for name in (PAYMENTS,) + CHARGES if name in found}
    if any(item['row']['_index'] not in component_rows for role in ('credit_total', 'debit_total')
           for item in controls[role]):
        return _refuse('unexplained_total')
    used = {item['row']['_index'] for role in ('opening', 'closing', 'credit_total', 'debit_total')
            for item in controls[role]} | {move['row']['_index'] for move in moves}
    if any(charge['row']['_index'] in used for charge in charges):
        return _refuse('charge_line_used')

    reconciling = []
    for candidate in candidates:
        values = candidate.get('values')
        if values is None or candidate.get('opening') is None or len(values) != len(moves):
            continue
        if any(value.get('merged') for value in values):
            continue
        if any(value['balance'] is not None for value in values) and not candidate.get('chain_ok'):
            continue
        net = sum(value['effect'] for value in values if not value['zero'])
        if candidate['opening'] + net + extra == candidate['closing']:
            reconciling.append(candidate)
    if len({candidate['key'] for candidate in reconciling}) != 1:
        return _refuse('no_single_reading')
    chosen = reconciling[0]
    if (chosen['opening'], chosen['closing']) != (opening, closing):
        return _refuse('summary_balances_differ')

    amounts = {charge['amount'] for charge in charges}
    for move, value in zip(moves, chosen['values']):
        if value['zero']:
            continue
        text = ' '.join([move['row']['text']] + [extra_row['text'] for extra_row in move['continuation']])
        if value['amount'] in amounts or NAMES_A_CHARGE.search(_fold(text)):
            return _refuse('movement_lists_a_charge')

    credits = sum(v['amount'] for v in chosen['values'] if not v['zero'] and v['direction'] == 'credit')
    debits = sum(v['amount'] for v in chosen['values'] if not v['zero'] and v['direction'] == 'debit')
    compared = 0
    if PAYMENTS in found:
        printed = found[PAYMENTS][0]
        if printed is not None:
            compared += 1
            if abs(printed) != credits:
                return _refuse('payments_total_differs')
    parts = [found[name][0] for name in CHARGES if name in found]
    read = [abs(part) for part in parts if part is not None]
    if sum(read) > debits:
        return _refuse('charges_total_differs')
    if len(read) == len(CHARGES):
        compared += 1
        if sum(read) != debits:
            return _refuse('charges_total_differs')
    if not compared:
        return _refuse('no_independent_control')
    LAST_REFUSAL.clear()
    component_ids = {_item_id(found[name][1]) for name in (PAYMENTS,) + CHARGES if name in found}
    return dict(candidate=chosen, charges=charges, component_ids=component_ids)


def _fold(text):
    from services.financial.statement_engine_vocabulary import fold
    return fold(text)


def add_rows(order, found, period):
    """Turn the summary's charge lines into charge rows of the proved reading, and its component lines
    (read by the general reader as statement totals) back into plain lines."""
    by_id = {item['id']: item for item in order}
    for item in order:
        if (item['kind'] == 'statement_total' and not item['fields'].get('total_scope')
                and item['id'].split(':debit_total')[0].split(':credit_total')[0] in found['component_ids']):
            item.update(kind='header', excluded=True, fields={})
    end = period[1].isoformat()
    for charge in found['charges']:
        row, token = charge['row'], charge['token']
        item = by_id[_item_id(row)]
        amount = str(charge['amount'])
        item.update(kind='transaction', excluded=False, fields=dict(
            description='%s (from the period summary, page %d)' % (DESCRIPTIONS[charge['kind']], row['page']),
            counterparty='', date=end, direction='debit', amount_minor=amount, debit=amount,
            debit_column=str(token['cell']['column_index']), source_basis=SOURCE_BASIS,
            summary_charge='tax' if charge['kind'] == 'tax' else 'interest', summary_page=row['page'],
            **({'charge_group': 'interest'} if charge['kind'] != 'tax' else {})))
    return order


def _item_id(row):
    """The id the general reader gives a source row's item (statement_engine._item)."""
    from services.financial.statement_engine import _item
    return _item(row)['id']
