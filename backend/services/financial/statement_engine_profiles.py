"""Declarative library profiles for the general statement engine.

A profile is DATA, not code: it lets the engine read an issuer whose printed
conventions are institution specific, without adding a branch to the engine.
Profiles belong to the fallback library (with the family readers): the engine
serves a period from its own rules first, and a profile is applied only to
pages no family reader claims, when the plain engine did not prove them.

Profile format (every key optional except ``name`` and ``match``):

    name         unique id, recorded on every period the profile served
    match        {'any': [...], 'all': [...]}: case-insensitive phrases printed on
                 the statement's pages; ``all`` must all occur, one of ``any`` must
    institution  the issuer's name, used when the pages print no legal-name line
    currency     ISO code for amounts printed with a bare symbol ('$'), used only
                 when the statement prints no currency of its own
    convention   'asset_balance' or 'liability_owed'
    date_order   'dmy' or 'mdy' for numeric dates without a month name
    labels       {role: [printed labels]} added to the vocabulary; roles are
                 opening, closing, subtotal, credit_total, debit_total,
                 credit_component, debit_component, column_total, and
                 day_balance: a line printing the balance at the end of a day
                 after that day's movements ('Saldo al final del dia 25 98.01'),
                 checked as the running balance after the movement line above it
    columns      {role: [printed column words]} added to the movement headings;
                 roles are date, description, credit, debit, balance, amount, and
                 ignore: an amount column that is not the movement's effect on the
                 balance (a gross amount, a fee or tax already inside a net column);
                 an ignore word outranks the shared vocabulary
    rule_mark    one character the reading prints at the edge of every table cell (a
                 vertical rule read as text, '28)' '83.10)'): removed wherever it is not
                 part of a parenthesized amount, whose sign is printed
    client_line  True: every page's first line prints the client (contract) number then
                 the holder's name ('<number> <name>'), over the address on the first
                 page; with no other account read, the number is the account, and the
                 name is the holder (one pair on every page printing it, or none)
    settlement_days  {'operation': [...], 'settlement': [...]}: each movement line
                 prints two days of the month, the operation day then the settlement
                 day, under these heading words (operation left of settlement); the
                 movement's date is the settlement day, the day the printed balance
                 moved. A line printing only one of the two days is not proved
    account_heading  True: with no labelled account, a section heading of the
                 product name followed by a hyphenated account number (one
                 distinct number in the section's heading area) is the account
    statement_account  True: a section sharing pages with another section and
                 printing no account of its own takes the statement's single
                 top-ranked heading account (one contract, several currencies)
    account_suffix_heading  True: each section's account is the number printed after
                 its product name in the section's own heading ('<product> - 1234'),
                 never a number from the statement's other pages; one or none
    holder_heading  {'title': [...], 'prefix': 'FOR'}: the holder is the name printed
                 on the line under a title line ('Statement of Account' / 'For <name>'),
                 the same on every page printing it
    prior_period_block  {'start': [...], 'end': [...]}: a line starting with a
                 ``start`` phrase opens a block of earlier periods' operations
                 repeated to explain a balance (E7); its lines are not this
                 period's movements, up to a line starting with an ``end`` phrase

Capital One and BBVA are expressed below to prove the format (their code
readers stay in the library unchanged); Monex, Santander, Intercam, Citi,
M&T, Scotiabank and Kapital supply only their institution. Facts a person confirms per layout and account
are not profiles: they are case data (``layout_memory``).
"""

import re

PROFILES = (
    dict(
        name='capital-one-card',
        match=dict(any=['capitalone.com', 'capital one']),
        institution='Capital One',
        currency='USD',
        convention='liability_owed',
        date_order='mdy',
        labels=dict(debit_component=['TRANSACTIONS'], credit_component=['OTHER CREDITS']),
        columns=dict(amount=['AMOUNT']),
    ),
    dict(
        name='bbva-mexico-cash-management',
        match=dict(any=['bbva mexico, s.a.', 'bbva bancomer, s.a.', 'bbva mexico s.a.'], all=['estado de cuenta']),
        institution='BBVA Mexico',
        convention='asset_balance',
        date_order='dmy',
        labels=dict(opening=['SALDO DE OPERACION INICIAL', 'SALDO DE LIQUIDACION INICIAL'],
                    closing=['SALDO DE OPERACION FINAL', 'SALDO FINAL'],
                    credit_total=['DEPOSITOS / ABONOS'], debit_total=['RETIROS / CARGOS'],
                    column_total=['TOTAL DE MOVIMIENTOS']),
        columns=dict(date=['OPER', 'LIQ'], debit=['CARGOS'], credit=['ABONOS'], balance=['OPERACION', 'LIQUIDACION']),
        # The BBVA reader's rule: operations booked in an earlier period, repeated to explain the settlement
        # balance, outside this period's printed counts and totals.
        prior_period_block=dict(start=['MOVIMIENTOS DE PERIODOS ANTERIORES'], end=['TOTAL DE MOVIMIENTOS']),
    ),
    # Institution-only profiles (r3): these layouts do not always print their legal name on the pages
    # the engine reads it from. Each match phrase is printed by every statement of its family in the
    # real collection and by no statement of another family (group names, not bank names that
    # counterparty transfer lines also print). The engine's printed legal name always wins.
    # Monex prints one contract number for all currency sections of a statement (its reader keys
    # every section by it); sections sharing pages take it from the statement's heading pages.
    dict(name='monex-mexico', match=dict(any=['monex grupo financiero']), institution='Monex', statement_account=True),
    # Santander prints some accounts only after the product name ("<PRODUCT NAME> 12-34567890-1"):
    # on the verified truth 45 such heading lines, every one the truth account.
    dict(name='santander-mexico', match=dict(any=['grupo financiero santander']), institution='Santander',
         account_heading=True),
    dict(name='intercam-mexico', match=dict(any=['intercam grupo financiero']), institution='Intercam'),
    dict(name='citi-card', match=dict(any=['citibank, n.a']), institution='Citibank'),
    # M&T Bank (r4): its scanned logo reads as other letters beside the printed name, so the printed
    # name is not unique on the page; the phrase is its balancing-instructions page furniture, printed by
    # every M&T statement in the real collection (83 documents) and by no other document.
    # A US bank: a bare '$' is US dollars (used only when the statement prints no currency of its own).
    dict(name='mt-bank', match=dict(any=['m&t telephone banking center']), institution='M&T Bank', currency='USD'),
    # Scotiabank Mexico and Kapital (r5): institution only. The Scotiabank legal name is printed by every
    # Scotiabank statement in the real collection and by no other document; Kapital's own bank name also
    # appears in other banks' transfer lines, so its phrase is the complaints-contact furniture printed by
    # every Kapital statement and by no other document.
    dict(name='scotiabank-mexico', match=dict(any=['scotiabank inverlat, s.a.']), institution='Scotiabank'),
    dict(name='kapital-mexico', match=dict(any=['aclaraciones@kapital.com']), institution='Kapital'),
    # Synchrony card (r6): the summary-box furniture is printed by every Synchrony statement in the real
    # collection and by no other document (a bank statement paying the card names the bank, not this line).
    # A US card: amounts owed, a bare '$' is US dollars, numeric dates month first (its closing date is
    # printed with a day of 12 or less in every cycle, so the date alone cannot fix the order).
    dict(name='synchrony-card', match=dict(any=['for synchrony bank customer service']), institution='Synchrony Bank',
         currency='USD', convention='liability_owed', date_order='mdy'),
    # Navy Federal Credit Union statements of account: one statement prints several accounts (checking,
    # its line of credit, savings), each in a section headed '<product name> - <last four digits>'; the
    # holder is printed under the title on every continuation page ('Statement of Account' / 'For <name>');
    # amounts carry a bare '$' (a US credit union) and no page names a currency.
    dict(name='navy-federal', match=dict(all=['navy federal credit union', 'statement of account', 'access no.']),
         institution='Navy Federal Credit Union', currency='USD', account_suffix_heading=True,
         holder_heading=dict(title=['STATEMENT OF ACCOUNT'], prefix='FOR')),
)

# Mexican brokerage (casa de bolsa) cash ledgers (r12): the movement table prints, per line, the operation
# day and the settlement day ('Ope', 'Liq'), the instrument's columns (folio, issuer, series, coupon,
# titles, price, term, rate), a gross amount, commission, premium and taxes, and the line's signed net
# effect on cash ('NETO', debits in parentheses). After each settlement day's lines it prints the cash
# balance at the end of that day, and the month's opening and closing balances as dated lines. Measured on
# the real collection (778 documents): the two phrases of each profile are printed by its family's
# brokerage statements (4 Kapital, 1 Intercam) and by no other document. No currency is printed: it stays
# the investigator's choice.
_BROKERAGE_CASH = dict(
    labels=dict(opening=['SALDO INICIAL DEL MES'], closing=['SALDO FINAL DEL MES'],
                day_balance=['SALDO AL FINAL DEL DIA']),
    columns=dict(date=['OPE', 'LIQ'], amount=['NETO'],
                 ignore=['MONTO', 'COMISION', 'PREMIO', 'IMPUESTOS', 'FOLIO', 'EMISORA', 'SERIE', 'CUPON',
                         'TITULOS', 'PRECIO', 'PLAZO', 'TASA']),
    settlement_days=dict(operation=['OPE'], settlement=['LIQ']),
    client_line=True,
    convention='asset_balance',
    date_order='dmy',
)
PROFILES += (
    dict(name='kapital-mexico-brokerage',
         match=dict(all=['detalle de movimientos del periodo', 'kapital mexico casa de bolsa']),
         institution='Kapital Mexico Casa de Bolsa', **_BROKERAGE_CASH),
    # Some Intercam statements read every table cell with a closing parenthesis at its right edge (the
    # vertical rule): measured on 10 of the 11 Intercam brokerage statements of the real collection.
    dict(name='intercam-brokerage', match=dict(all=['detalle de movimientos del periodo', 'intercam casa de bolsa']),
         institution='Intercam Casa de Bolsa', rule_mark=')', **_BROKERAGE_CASH),
)

_KEYS = {'name', 'match', 'institution', 'currency', 'convention', 'date_order', 'labels', 'columns', 'account_heading',
         'statement_account', 'prior_period_block', 'account_suffix_heading', 'holder_heading', 'settlement_days',
         'client_line', 'rule_mark'}
_LABEL_ROLES = {'opening', 'closing', 'subtotal', 'credit_total', 'debit_total', 'credit_component',
                'debit_component', 'column_total', 'day_balance'}
_COLUMN_ROLES = {'date', 'description', 'credit', 'debit', 'balance', 'amount', 'ignore'}


def validate(profile):
    """Refuse a malformed profile before it can change any reading."""
    unknown = set(profile) - _KEYS
    if unknown or not profile.get('name') or not isinstance(profile.get('match'), dict):
        raise ValueError('Invalid statement profile: ' + str(profile.get('name')))
    if profile.get('convention') not in (None, 'asset_balance', 'liability_owed'):
        raise ValueError('Invalid profile convention.')
    if profile.get('date_order') not in (None, 'dmy', 'mdy'):
        raise ValueError('Invalid profile date order.')
    if set(profile.get('labels') or {}) - _LABEL_ROLES or set(profile.get('columns') or {}) - _COLUMN_ROLES:
        raise ValueError('Invalid profile label or column role.')
    if (profile.get('account_heading') not in (None, True) or profile.get('statement_account') not in (None, True)
            or profile.get('account_suffix_heading') not in (None, True) or profile.get('client_line') not in (None, True)):
        raise ValueError('Invalid profile account heading flag.')
    titled = profile.get('holder_heading')
    if titled is not None and (not isinstance(titled, dict) or set(titled) != {'title', 'prefix'}
                               or not (isinstance(titled['title'], list) and titled['title'])
                               or not (isinstance(titled['prefix'], str) and titled['prefix'].strip())):
        raise ValueError('Invalid profile holder heading.')
    block = profile.get('prior_period_block')
    if block is not None and (not isinstance(block, dict) or set(block) != {'start', 'end'}
                              or not all(isinstance(v, list) and v for v in block.values())):
        raise ValueError('Invalid profile prior-period block.')
    mark = profile.get('rule_mark')
    if mark is not None and not (isinstance(mark, str) and len(mark) == 1 and not mark.isalnum() and not mark.isspace()):
        raise ValueError('Invalid profile rule mark.')
    days = profile.get('settlement_days')
    if days is not None and (not isinstance(days, dict) or set(days) != {'operation', 'settlement'}
                             or not all(isinstance(v, list) and v and all(isinstance(w, str) and w.strip() for w in v)
                                        for v in days.values())):
        raise ValueError('Invalid profile settlement days.')
    if profile.get('currency'):
        from services.financial.money import get_currency
        get_currency(profile['currency'])
    return profile


for _profile in PROFILES:
    validate(_profile)


def _matching(text):
    lowered = ' '.join(text.lower().split())
    found = []
    for profile in PROFILES:
        rule = profile['match']
        if all(p in lowered for p in rule.get('all', [])) and (not rule.get('any') or any(p in lowered for p in rule['any'])):
            found.append(profile)
    return found


def matching_profile(text, furniture=None):
    """The one profile whose printed phrases occur in ``text``; None if none or several match.

    When several match and ``furniture`` (the same document without its dated lines, see
    ``furniture_text``) is given and exactly one matches there, that one is used: a statement paying
    another issuer names that issuer in a movement line ('<date> | CAPITAL ONE ...'), never in its
    printed furniture.
    """
    found = _matching(text)
    if len(found) > 1 and furniture is not None:
        printed = _matching(furniture)
        if len(printed) == 1:
            found = printed
    if len(found) > 1:
        # A profile matched only by phrases that must all occur (no 'any' list) is specific to one layout:
        # it outranks profiles matched by a single phrase, which a transaction line can print (a payment
        # to a card issuer names that issuer).
        specific = [p for p in found if not p['match'].get('any')]
        found = specific if len(specific) == 1 else found
    return found[0] if len(found) == 1 else None


def profile_text(sources):
    return '\n'.join(c['expected_text'] for s in sources for r in s['rows'] for c in r['cells'])


# A stored row opening with a numeric date (its digits possibly misread: '41/19/2021') is a dated line.
_DATED_LINE = re.compile(r'^\W{0,2}\d{1,2}[/.-]\d{1,2}(?:[/.-]\d{2,4})?\b')


def furniture_text(sources):
    """``profile_text`` without the stored rows that open with a numeric date (movement lines)."""
    return '\n'.join(c['expected_text'] for s in sources for r in s['rows']
                     if not (r['cells'] and _DATED_LINE.match(r['cells'][0]['expected_text']))
                     for c in r['cells'])

