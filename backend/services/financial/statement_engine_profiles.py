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
                 credit_component, debit_component, column_total
    columns      {role: [printed column words]} added to the movement headings;
                 roles are date, description, credit, debit, balance, amount
    account_heading  True: with no labelled account, a section heading of the
                 product name followed by a hyphenated account number (one
                 distinct number in the section's heading area) is the account

Capital One and BBVA are expressed below to prove the format (their code
readers stay in the library unchanged); Monex, Santander, Intercam and Citi
supply only their institution. Facts a person confirms per layout and account
are not profiles: they are case data (``layout_memory``).
"""

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
    ),
    # Institution-only profiles (r3): these layouts do not always print their legal name on the pages
    # the engine reads it from. Each match phrase is printed by every statement of its family in the
    # real collection and by no statement of another family (group names, not bank names that
    # counterparty transfer lines also print). The engine's printed legal name always wins.
    dict(name='monex-mexico', match=dict(any=['monex grupo financiero']), institution='Monex'),
    # Santander prints some accounts only after the product name ("<PRODUCT NAME> 12-34567890-1"):
    # on the verified truth 45 such heading lines, every one the truth account.
    dict(name='santander-mexico', match=dict(any=['grupo financiero santander']), institution='Santander',
         account_heading=True),
    dict(name='intercam-mexico', match=dict(any=['intercam grupo financiero']), institution='Intercam'),
    dict(name='citi-card', match=dict(any=['citibank, n.a']), institution='Citibank'),
)

_KEYS = {'name', 'match', 'institution', 'currency', 'convention', 'date_order', 'labels', 'columns', 'account_heading'}
_LABEL_ROLES = {'opening', 'closing', 'subtotal', 'credit_total', 'debit_total', 'credit_component',
                'debit_component', 'column_total'}
_COLUMN_ROLES = {'date', 'description', 'credit', 'debit', 'balance', 'amount'}


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
    if profile.get('account_heading') not in (None, True):
        raise ValueError('Invalid profile account heading flag.')
    if profile.get('currency'):
        from services.financial.money import get_currency
        get_currency(profile['currency'])
    return profile


for _profile in PROFILES:
    validate(_profile)


def matching_profile(text):
    """The one profile whose printed phrases occur in ``text``; None if none or several match."""
    lowered = ' '.join(text.lower().split())
    found = []
    for profile in PROFILES:
        rule = profile['match']
        if all(p in lowered for p in rule.get('all', [])) and (not rule.get('any') or any(p in lowered for p in rule['any'])):
            found.append(profile)
    return found[0] if len(found) == 1 else None


def profile_text(sources):
    return '\n'.join(c['expected_text'] for s in sources for r in s['rows'] for c in r['cells'])

