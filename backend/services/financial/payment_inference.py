"""Reproducible description labels, separate from documentary readings.

These suggestions describe a merchant or payment type, never beneficial
ownership, personal/business purpose, or the funding account behind a card
payment. Explicit investigator labels always take precedence in payment_labels.
"""
import re
import unicodedata

VERSION = 'description-labels/8'


def normalized(value):
    return ' '.join(''.join(c for c in unicodedata.normalize('NFKD', value or '')
                           if not unicodedata.combining(c)).upper().split())


# Prefixes identify the merchant in a card descriptor, rather than finding a
# brand incidentally in a transfer's free-text reference or another name.
MERCHANTS = [
    (r'UBER\s*EATS', 'Uber Eats', 'Meals'),
    (r'UBER(?:\s*(?:TRIP|ONE|TECHNOLOGIES))?(?=[^A-Z]|$)', 'Uber', 'Transport'),
    (r'LYFT(?=[^A-Z]|$)', 'Lyft', 'Transport'),
    (r'(?:DD\s*\*?\s*)?DOORDASH(?:DASHPASS)?', 'DoorDash', 'Meals'),
    (r'GRUBHUB', 'Grubhub', 'Meals'),
    (r'POSTMATES(?=[^A-Z]|$)', 'Postmates', 'Meals'),
    (r'MCDONALD[\x27’]?S?(?=[^A-Z]|$)', "McDonald's", 'Meals'),
    (r'PAPA\s*JOHN[\x27’]?S?(?=[^A-Z]|$)', "Papa John's", 'Meals'),
    (r'STARBUCKS(?=[^A-Z]|$)', 'Starbucks', 'Meals'),
    (r'CHIPOTLE(?=[^A-Z]|$)', 'Chipotle', 'Meals'),
    (r'DOMINO[\x27’]?S?(?=[^A-Z]|$)', "Domino's", 'Meals'),
    (r'DUNKIN(?=[^A-Z]|$)', 'Dunkin', 'Meals'),
    (r'CHICK[ -]FIL[ -]A(?=[^A-Z]|$)', 'Chick-fil-A', 'Meals'),
    (r'BURGER KING(?=[^A-Z]|$)', 'Burger King', 'Meals'),
    (r'PANDA EXPRESS(?=[^A-Z]|$)', 'Panda Express', 'Meals'),
    (r'IHOP(?=[^A-Z]|$)', 'IHOP', 'Meals'),
    (r'PIZZA HUT(?=[^A-Z]|$)', 'Pizza Hut', 'Meals'),
    (r'(?:THE )?OLIVE GARD(?:EN|[0-9])', 'Olive Garden', 'Meals'),
    (r'(?:FIVE\s*GUYS|5GUYS)(?=[^A-Z]|$)', 'Five Guys', 'Meals'),
    (r'TGI FRIDAYS(?=[^A-Z]|$)', 'TGI Fridays', 'Meals'),
    (r'LONGHORN ST(?:EAKHOUSE|K)(?=[^A-Z]|$)', 'LongHorn Steakhouse', 'Meals'),
    (r'SBARRO(?=[^A-Z]|$)', 'Sbarro', 'Meals'),
    (r'SONIC DRIVE IN(?=[^A-Z]|$)', 'Sonic Drive-In', 'Meals'),
    (r'CHECKERS(?=[^A-Z]|$)', 'Checkers', 'Meals'),
    (r'NIKE(?=[^A-Z]|$)', 'Nike', 'Shopping'),
    (r'SAKSOFF5TH(?:\.COM)?', 'Saks OFF 5TH', 'Shopping'),
    (r'AMAZON(?:\.[A-Z.]+)?(?=[^A-Z]|$)|AMZN(?=[^A-Z]|$)', 'Amazon', 'Shopping'),
    (r'TARGET(?=[^A-Z]|$)', 'Target', 'Shopping'),
    (r'WAL[ -]?MART(?=[^A-Z]|$)', 'Walmart', 'Shopping'),
    (r'WM SUPERCENTER(?=[^A-Z]|$)', 'Walmart', 'Shopping'),
    (r'BEST\s*BUY(?:\.COM|COM)?', 'Best Buy', 'Shopping'),
    (r'FOOT LOCKER(?=[^A-Z]|$)', 'Foot Locker', 'Shopping'),
    (r'FOOTACTION(?=[^A-Z]|$)', 'Footaction', 'Shopping'),
    (r'MACY[\x27’]?S(?=[^A-Z]|$)', "Macy's", 'Shopping'),
    (r'NORDSTROM(?=[^A-Z]|$)', 'Nordstrom', 'Shopping'),
    (r'MARSHALLS(?=[^A-Z]|$)', 'Marshalls', 'Shopping'),
    (r'TORY BURCH(?=[^A-Z]|$)', 'Tory Burch', 'Shopping'),
    (r'POLO FACTORY STORE(?=[^A-Z]|$)', 'Polo Ralph Lauren', 'Shopping'),
    (r'(?:WWW\.)?HOTTOPIC\.COM', 'Hot Topic', 'Shopping'),
    (r'RUE21(?=[^A-Z]|$)', 'rue21', 'Shopping'),
    (r'EBAY(?=[^A-Z]|$)', 'eBay', 'Shopping'),
    (r'FARFETCH', 'Farfetch', 'Shopping'),
    (r'OVERSTOCK\.COM', 'Overstock', 'Shopping'),
    (r'HOMEGOODS(?=[^A-Z]|$)', 'HomeGoods', 'Shopping'),
    (r'DOLLAR\s*TREE', 'Dollar Tree', 'Shopping'),
    (r'BLOOMINGDALES(?=[^A-Z]|$)', "Bloomingdale's", 'Shopping'),
    (r'LIDS\.COM', 'Lids', 'Shopping'),
    (r'DICKS? SPORTING GOODS', "Dick's Sporting Goods", 'Shopping'),
    (r'THE CHILDREN[\x27’]?S PLACE', "The Children's Place", 'Shopping'),
    (r'LOWE[\x27’]?S(?=[^A-Z]|$)', "Lowe's", 'Home and hardware'),
    (r'HOME DEPOT(?=[^A-Z]|$)', 'The Home Depot', 'Home and hardware'),
    (r'APPLE\.COM/(?:US|BILL)', 'Apple', 'Shopping'),
    (r'NETGEAR(?=[^A-Z]|$)', 'Netgear', 'Shopping'),
    (r'WHOLE\s*FOODS(?=[^A-Z]|$)', 'Whole Foods', 'Groceries'),
    (r'TRADER\s*JOE[\x27’]?S?(?=[^A-Z]|$)', "Trader Joe's", 'Groceries'),
    (r'KROGER(?=[^A-Z]|$)', 'Kroger', 'Groceries'),
    (r'SAFEWAY(?=[^A-Z]|$)', 'Safeway', 'Groceries'),
    (r'PLAYSTATION(?:\s*NETWORK)?', 'PlayStation', 'Entertainment'),
    (r'NETFLIX(?=[^A-Z]|$)', 'Netflix', 'Subscriptions'),
    (r'SPOTIFY(?=[^A-Z]|$)', 'Spotify', 'Subscriptions'),
    (r'(?:HLU\*)?HULU', 'Hulu', 'Subscriptions'),
    (r'PEACOCK(?:\s|MASTERCARD)', 'Peacock', 'Subscriptions'),
    (r'PRIME VIDEO', 'Prime Video', 'Entertainment'),
    (r'FANDANGO(?=[^A-Z]|$)', 'Fandango', 'Entertainment'),
    (r'REGAL (?:CINEMA|GALLERY)', 'Regal Cinemas', 'Entertainment'),
    (r'KINGS DOMINION(?=[^A-Z]|$)', 'Kings Dominion', 'Entertainment'),
    (r'INTUIT\s*\*?\s*TURBOTAX', 'Intuit TurboTax', 'Tax preparation'),
    (r'SUPPORTPDFFILLER\.COM', 'pdfFiller', 'Software'),
    (r'ZIPCAR(?=[^A-Z]|$)', 'Zipcar', 'Transport'),
    (r'SPIN (?:SCOOTER|MOBILITY)', 'Spin', 'Transport'),
    (r'HELBIZ(?=[^A-Z]|$)', 'Helbiz', 'Transport'),
    (r'FREE2MOVE', 'Free2move', 'Transport'),
    (r'AMTRAK(?=[^A-Z]|$)', 'Amtrak', 'Travel'),
    (r'SPIRIT AI(?:R|\s)', 'Spirit Airlines', 'Travel'),
    (r'(?:ETOLL\s+)?AVIS(?=[^A-Z]|$)', 'Avis', 'Travel'),
    (r'BUDGET(?:\.COM|\s+RENT\s+A\s+CAR)|ETOLL\s+BGT\b', 'Budget', 'Travel'),
    (r'PARKMOBILE(?=[^A-Z]|$)', 'ParkMobile', 'Parking and tolls'),
    (r'ENTERPRISE\s*RENT[ -]A[ -]CAR', 'Enterprise Rent-A-Car', 'Travel'),
    (r'FOUR\s*SEASONS(?=[^A-Z]|$)', 'Four Seasons', 'Travel'),
    (r'MARRIOTT(?=[^A-Z]|$)', 'Marriott', 'Travel'),
    (r'HILTON(?=[^A-Z]|$)', 'Hilton', 'Travel'),
    (r'TRU BY HILTON(?=[^A-Z]|$)', 'Tru by Hilton', 'Travel'),
    (r'AIRBNB(?=[^A-Z]|$)', 'Airbnb', 'Travel'),
    (r'CVS(?:/PHARMACY|\s+PHARMACY)?(?=[^A-Z]|$)', 'CVS', 'Health and pharmacy'),
    (r'WALGREENS(?=[^A-Z]|$)', 'Walgreens', 'Health and pharmacy'),
    (r'SHELL(?=[^A-Z]|$)', 'Shell', 'Fuel'),
    (r'EXXON(?:MOBIL)?(?=[^A-Z]|$)', 'ExxonMobil', 'Fuel'),
    (r'CHEVRON(?=[^A-Z]|$)', 'Chevron', 'Fuel'),
    (r'PHILLIPS 66(?=[^A-Z]|$)', 'Phillips 66', 'Fuel'),
    (r'ELECTRIFY AMERICA', 'Electrify America', 'Vehicle charging'),
    (r'XFINITY MOBILE(?=[^A-Z]|$)', 'Xfinity Mobile', 'Utilities and telecom'),
    (r'COMCAST(?=[^A-Z]|$)', 'Comcast', 'Utilities and telecom'),
    (r'ALLIANZ INSURANCE(?=[^A-Z]|$)', 'Allianz', 'Insurance'),
]
MERCHANTS = [(re.compile(pattern), name, category) for pattern, name, category in MERCHANTS]


_CASH_RULES = {'cash-deposit': ' The other side is shown as Cash.', 'cash-withdrawal': ' The other side is shown as Cash.'}


def infer_payment_labels(description, *, direction, account_type=None, institution=None):
    """Return label values with the rule and explanation used for each one.

    With no name for the other side, 'counterparty_reason' says why when the layout is
    known to print none (services.financial.payment_party_reasons)."""
    if direction not in ('credit', 'debit'):
        return {}
    raw = ' '.join((description or '').split())
    value = normalized(raw)
    if not value:
        return {}
    result = _infer(raw, value, direction=direction, account_type=account_type, institution=institution)
    if 'counterparty' not in result:
        from services.financial.payment_party_reasons import unnamed_reason
        reason = unnamed_reason(value, direction=direction, account_type=account_type)
        if reason:
            text, rule, explanation = reason
            # A mixed ATM deposit can hold cheques as well as cash, so it keeps the reason.
            if rule in _CASH_RULES and 'MIXED DEPOSIT' not in value:
                # Cash is the other side of a cash movement: shown as the name, with why, never as a missing name.
                result['counterparty'] = dict(value='Cash', source='description', rule=rule, version=VERSION,
                                              explanation=explanation + _CASH_RULES[rule])
            else:
                result['counterparty_reason'] = dict(value=text, source='description', rule=rule, version=VERSION, explanation=explanation)
    return result


def _infer(raw, value, *, direction, account_type, institution):
    result = {}

    def suggest(field, label, rule, explanation):
        result[field] = dict(value=label, source='description', rule=rule,
                             version=VERSION, explanation=explanation)

    def category(label, rule, cue):
        suggest('category', label, rule, f'Suggested from {cue} in the description; review or change it if needed.')

    # A card payment reduces debt. Its funding bank/account is not the issuer
    # named in the payment descriptor and is deliberately left unidentified.
    card_payment = bool(re.match(r'(?:CAPITAL\s*ONE\s+)?(?:MOBILE|ONLINE|AUTOMATIC|AUTOPAY|ELECTRONIC)\s*(?:PYMT|PMT|PAYMENT)', value))
    if account_type == 'credit_card' and direction == 'credit' and card_payment:
        category('Card payments', 'card-payment', 'the card payment wording')
        return result

    # Card security / payment protection products are the issuer's own charge.
    if account_type == 'credit_card' and institution and re.match(r'PYMT CARD SECURITY\b', value):
        suggest('counterparty', institution, 'bank-charge', 'The description names the card issuer’s payment-protection product; the issuer name comes from the statement account.')

    if account_type == 'credit_card' and direction == 'credit' and re.search(r'\b(?:CASH BACK REWARD|REWARD REDEMPTION|REWARD CREDIT)\b', value):
        category('Card rewards', 'card-reward', 'the reward credit wording')
        if institution:
            suggest('counterparty', institution, 'issuer-reward', 'The statement describes a reward credit from the card issuer.')
        return result

    descriptor = re.sub(r'^(?:(?:POS|CHECKCARD|CHECK CARD|DEBIT CARD|CARD PURCHASE)\s+(?:\d{4}\s+)?|(?:TST|SQ)\s*\*\s*)', '', value)
    for pattern, merchant, kind in MERCHANTS:
        match = pattern.match(descriptor)
        if match:
            suggest('counterparty', merchant, 'merchant-descriptor', f'Merchant suggested from “{match[0]}” in the description. This does not establish legal identity or ownership.')
            category('Merchant credits' if direction == 'credit' else kind, 'merchant-category', f'the merchant {merchant}')
            return result

    # Remove only the bank's transaction-type prefix; references stay intact.
    value = re.sub(r'^[A-Z]\d{2}\s+', '', value)
    # Tax on a commission is tax, rather than the commission itself.
    if re.search(r'\b(?:IVA|I\.?S\.?R\.?\s+RETENIDO|TAX(?:ES)?\s+(?:WITHHELD|PAYMENT))\b', value):
        category('Taxes', 'tax', 'the tax wording')
    elif re.search(r'\b(?:INTERESES GANADOS|INTEREST (?:EARNED|PAID|CREDIT))\b', value) and direction == 'credit':
        category('Interest income', 'interest-income', 'the interest wording')
        if institution:
            suggest('counterparty', institution, 'bank-interest', 'The description identifies bank interest; the bank name comes from the statement account.')
    elif re.search(r'\b(?:INTEREST CHARGE|INTERESES COBRADOS|FINANCE CHARGE)\b', value):
        category('Interest charges', 'interest-charge', 'the interest charge wording')
        if institution:
            suggest('counterparty', institution, 'bank-charge', 'The description identifies interest charged by the statement bank.')
    elif re.search(r'\b(?:COMISION|COM SDO|LATE FEE|PAST DUE FEE|ANNUAL FEE|OVERDRAFT FEE|SERVICE (?:CHARGE|FEE)|BANK FEE|FOREIGN TRANSACTION FEE)\b', value):
        category('Bank fees', 'bank-fee', 'the fee or commission wording')
        if institution:
            suggest('counterparty', institution, 'bank-charge', 'The description identifies a bank fee; the bank name comes from the statement account.')
    elif re.search(r'\b(?:RENTA|RENT|LEASE PAYMENT)\b', value):
        category('Rent and leases', 'rent', 'the rent or lease wording')
    elif re.search(r'\b(?:PAYROLL|SALARY|NOMINA)\b', value):
        category('Payroll', 'payroll', 'the payroll wording')
    elif re.search(r'\b(?:ATM WITHDRAWAL|CASH WITHDRAWAL|RETIRO (?:DE )?EFECTIVO|RETIRO CAJERO)\b', value):
        category('Cash withdrawals', 'cash-withdrawal', 'the cash withdrawal wording')
    elif direction == 'credit' and re.match(r'(?:SPEI|SPID)\s+DEVUELTO', value):
        category('Returned transfers', 'returned-transfer', 'the returned transfer wording; this is a return of an earlier payment, not a new payer')
    elif re.search(r'\b(?:TRANSFER|TRASPASO|SPEI|SPID|ORDEN DE PAGO|WIRE|ZELLE)\b', value):
        category('Transfers', 'transfer', 'the transfer wording')
    elif re.search(r'\b(?:DEPOSITO DE TERCERO|DEPOSIT)\b', value):
        category('Deposits', 'deposit', 'the deposit wording')

    # Business-type words give a useful broad category even where the exact
    # merchant identity is unresolved. Never infer personal/business spending.
    if 'category' not in result and account_type == 'credit_card':
        for pattern, kind, cue in [
            (r'\b(?:PARKING|ETOLL|TOLL\b|IPARKSIMPLE|COLPARK|PARKX)', 'Parking and tolls', 'the parking or toll wording'),
            (r'\b(?:DENTAL|DENTISTRY|ORTHODONTIC|HOSPITAL|MEDICAL|MED\*)', 'Health and pharmacy', 'the healthcare wording'),
            (r'\b(?:HAIR|LASH|BROW|BARBER|SALON|SPORT CLIPS)', 'Personal care', 'the salon or grooming wording'),
            (r'\b(?:STORAGE|SELF STORAGE)', 'Storage', 'the storage wording'),
            (r'\b(?:RESTAURANT|PIZZA|CAFE|BAR AND GRIL|ICE CR)', 'Meals', 'the food-service wording'),
            (r'\b(?:TAXI|SCOOTER|METRO\s+\d)', 'Transport', 'the transport wording'),
            (r'\b(?:MINI GOLF|AMUSEMENT|COUNTY FAIR|ADVENTURE PA)', 'Entertainment', 'the entertainment wording'),
            (r'\b(?:GOV[\x27’]?T PAYMENT|COURTS PAYMENTS)', 'Government payments', 'the government payment wording'),
            (r'\b(?:CAR WASH|DETAILING)', 'Vehicle care', 'the vehicle-care wording'),
            (r'\b(?:INSURANCE|SEGURO)', 'Insurance', 'the insurance wording'),
        ]:
            if re.search(pattern, descriptor):
                category('Merchant credits' if direction == 'credit' else kind, 'business-type', cue)
                break

    # Explicit directional names may be used only on the matching payment side.
    cue = 'FROM' if direction == 'credit' else 'TO'
    named = re.match(rf'^(?:WIRE|TRANSFER|PAYMENT|BANK TRANSFER)(?:\s+(?:TRANSFER|PAYMENT))?\s+{cue}\s+(.+?)(?:\s+(?:REF(?:ERENCE)?[.:#]|ACCOUNT\b|ACCT\b).*)?$', raw, re.I)
    # CIE collection entries name the payee before REF, unlike a SPEI/SPID
    # description where the bank name alone does not identify the beneficiary.
    cie = re.match(r'^P14\s+(.+?)\s+REF\s*:\s*\d+\s+CIE\s*:\s*\d+\b', raw, re.I)
    from services.financial.spei_description import kapital_spei
    spei = kapital_spei(raw) if account_type != 'credit_card' else None
    if spei and spei['direction'] == direction:
        endpoint = spei['sender' if direction == 'credit' else 'recipient']
        from services.financial.payment_parties import clean_name
        suggest('counterparty', clean_name(endpoint['party']['name']) or endpoint['party']['name'], 'kapital-spei-party',
            'Sender or recipient printed in the SPEI party field. The bank and account are separate fields. The statement qualifies this name as unverified; review ownership separately.'
            if endpoint['party']['qualifier'] else 'Sender or recipient printed in the SPEI party field. This is a source-name suggestion, not an ownership decision.')
    elif direction == 'debit' and account_type != 'credit_card' and cie and _name(cie[1]):
        suggest('counterparty', cie[1].strip(), 'bbva-cie-payee', 'Payee label printed before the REF and CIE references in the payment description. This label does not establish the ultimate beneficiary.')
        if 'category' not in result:
            category('Payments', 'cie-payment', 'the CIE payment reference')
    elif named and _name(named[1]):
        suggest('counterparty', named[1].strip(), 'named-payment-party', f'The description explicitly says “{cue.lower()} {named[1].strip()}”. Verify the name against the source before linking an identity.')
    elif direction == 'credit':
        depositor = re.match(r'^(?:W\d{2}\s+)?DEPOSITO DE TERCERO\s+(.+?)\s+BMRCASH\b', raw, re.I)
        if depositor and _name(depositor[1]):
            suggest('counterparty', depositor[1].strip(), 'bbva-depositor', 'Name printed after “DEPOSITO DE TERCERO” in the description.')
    # The other side as the statement's own layout prints it (services.financial.payment_parties).
    # A charge, interest, withheld tax or product of the statement bank is the bank's; a person or
    # company printed in a transfer's name field replaces a guess made only from wording elsewhere.
    # A card line the merchant descriptor below reads keeps that reading (and its category).
    merchant = card_merchant_descriptor(raw) if account_type == 'credit_card' and 'counterparty' not in result else None
    if merchant and result.get('category', {}).get('value') in (
            'Taxes', 'Interest income', 'Interest charges', 'Bank fees',
            'Payroll', 'Cash withdrawals', 'Transfers', 'Deposits'):
        merchant = None
    if not merchant and result.get('counterparty', {}).get('rule') in (None, 'bank-charge', 'bank-interest'):
        from services.financial.payment_parties import printed_party, bank_service, TRANSFER_RULES, TRANSFER_OPENING
        # The bank's own service with no bank recorded names nobody, not a name printed in it.
        service = bank_service(value)
        party = None if service or account_type == 'credit_card' else printed_party(raw, direction=direction, account_type=account_type)
        if service and institution:
            suggest('counterparty', institution, *service)
        elif party and ('counterparty' not in result or party[1] in TRANSFER_RULES):
            suggest('counterparty', *party)
        elif not service and TRANSFER_OPENING.match(value):
            # A transfer whose concept says COMISION or INTERESES is not the bank's charge; with no name printed, nobody is named.
            result.pop('counterparty', None)
    if merchant:
        suggest('counterparty', merchant, 'card-statement-descriptor',
            'Merchant label from the card payment description, not a verified legal identity. '
            'Location or store text is retained when its boundary is unclear. '
            'The original description remains available; a processor prefix does not establish the ultimate recipient.')
        if direction == 'credit' and 'category' not in result:
            category('Merchant credits', 'merchant-credit-descriptor', 'the merchant descriptor on this card credit')
    if account_type == 'credit_card' and 'counterparty' not in result:
        from services.financial.payment_parties import card_line_merchant
        found = card_line_merchant(raw, institution=institution)
        if found:
            suggest('counterparty', *found)
    if 'category' not in result:
        found = bank_wording_category(value, direction=direction, account_type=account_type)
        if found:
            category(*found)
    return result


# Debit card lines in US checking statements: the merchant follows the prefix,
# the card's date and the authorisation numbers. OCR splits words ("Wi t
# hdrawal"), so the prefix is recognised with spaces removed.
_DEBIT_CARD_PREFIXES = ('WITHDRAWALDEBITCARD', 'RECURRINGWITHDRAWALDEBITCARD', 'ITHDRAWALDEBITCARD', 'IITHDRAWALDEBITCARD',
                        'WITHDRAWALADJUSTMENTDEBITCARD', 'WITHDRAWALADJUSTMENTPOS', 'RECURRINGWITHDRAWALADJUSTMENTDEBITCARD', 'WITHDRAWALPOS', 'WITHDRAWALPCS',
                        'POSDEBIT', 'PURCHASEON', 'PURCHASEWITHCASHBACKON', 'POSPURCHASE', 'DEBITCARDPURCHASE', 'CHECKCARD')


def _card_tail(value, direction):
    """The merchant part of a debit card line, or None when it is not one."""
    squashed = re.sub(r'[^A-Z]', '', value[:60])
    if squashed.startswith(_DEBIT_CARD_PREFIXES):
        for pattern in (r'(?:\b[0O]|~|_[0O])\s+\d{5,}\s+[0O]?\s*', r'#\d{6,}\s+', r'\bTRANSACTION\s+[\d\-]+\s+', r'\bCARD\s+\d{4}\s+[\d\-]{8}\s+', r'\bON\s+\d{2}/\d{2}\s+'):
            found = re.search(pattern, value)
            if found:
                return value[found.end():]
        return re.sub(r'^[^A-Z]*(?:[A-Z]+\s+){1,4}?(?:CARD|POS|ON)\b[\s#\d/\-]*', '', value)
    # M&T and similar print card purchases as a bare merchant after a bar.
    if direction == 'debit' and re.match(r'^[|}~]\s*', value):
        return re.sub(r'^[|}~]\s*(?:PIN\s*)?', '', value)
    return None


_CARD_ISSUERS = r'CAPITAL ONE|CREDIT ONE|APPLECARD|APPLE CARD|CITI CARD|CITICARD|MERRICK|MACYS|SYNCHRONY|SYNCB|DISCOVER|AMEX|AMERICAN EXPRESS|CHASE CARD|BARCLAYCARD|BARCLAYS|COMENITY|CARD SECURITY|CONT FINANCE|TARGET CARD|KOHLS'
_P2P = r'CASH\s*APP|SQUARE CASH|VENMO|PAYPAL|APPLE CASH|ZELLE'
# Ordered: the first matching rule decides. Each entry is
# (pattern, category, rule id, cue, direction or None for either).
_BANK_WORDING = [(re.compile(p), c, r, cue, d) for p, c, r, cue, d in [
    # Investments come first: a bond line can name an issuer such as CFE.
    (r'\bFONDOS\s+INV|\bINVERS|\bCOMPRA\s*DE\s*REPORTO|\bCOMPRADE\s*REPORTO|\bVENTA\s*DE\s*REPORTO|\bREPORTO\b|\bI?APERTURA DE INVERSION|\bDEPOSITO DE INVERSION|\bPAGO CAP\.? DE INVERSION|\bVENCIMIENTO DE INVERSION|\bCETES\b|\bBONDES|\bPRLV\b|\bINVERSION\b', 'Investments', 'mx-investment', 'the investment or repo wording', None),
    (r'^\d+\s+RETIRO\s+0\s+0\s+1\.0+\b|\bCOBRO POR TIMBRADO\s+0\s+0\s+1\.0+', 'Investments', 'mx-investment-line', 'the investment statement line format', None),
    (r'S\.?\s*R\.?\s*RETENIDO|\bRET(?:ENCION)?\.?\s*(?:\|\s*|I\s*)?S\s*R\b|\bRETENCION\s*\|?\s*I?S\s*R\b|\bRET\.?\s*ISR\b|\bISR\b|\bIMPTO\b|\bIMPUESTO|\bI\s*V\s*A\b|\bPAGO REFERENCIADO\s+SAT\b|\bSAT\b|\bRECAUDACION DE IMPUE|\bSECRETARIA DE FINANZ|\bLINEA CAPTURA\b|\bTESORERIA\b|\bPREDIAL\b|\bTENENCIA\b', 'Taxes', 'mx-tax', 'the tax, withholding or tax-authority wording', None),
    (r'\bIMSS\b|\bINFONAVIT\b|\bAFORE\b|\bSIPARE\b|\bSOC(?:IAL)? SEC\b|\bSSA TREAS\b|\bTREAS 310\b', 'Social security', 'social-security', 'the social security wording', None),
    (r'\bPAGO INTERESES DE INV|\bABO(?:NO)? POR INTERESES|\bINTERESES\b|\bINTEREST PAYMENT\b|\bINTEREST\b|\bDIVIDEND', 'Interest income', 'interest-income-wording', 'the interest or dividend wording', 'credit'),
    (r'\bINTEREST CHARGED?\b|\bINTERESES\b', 'Interest charges', 'interest-charge-wording', 'the interest charge wording', 'debit'),
    (r'\bCOM(?:ISION)?\b.*\b(?:MEMBRESIA|TRANSACCIONES|SERV|MANEJO|ANUALIDAD|SPEI|CHEQUE)|\bCOM MEMBRESIA|\bSERV BANCA INTERNET\b|\bTIMBRADO\b|\bCOMISIONES\b|\bADD-ON FEE\b|\bATM (?:W/D )?FEE\b|\bNON-[A-Z&]+ ATM FEE\b|\bOVERDRAFT\b|\bPRIVILEGE PAY\b|\bPENALIZ|\bCOM DEP\b|\bNSF\b|\bINSUFFICIENT FUNDS\b|\bMAINTENANCE FEE\b|\bMONTHLY FEE\b|\bWIRE FEE\b|\bFEE\b', 'Bank fees', 'bank-fee-wording', 'the bank fee or commission wording', None),
    (r'\bTOYOTA FINANCIAL\b|LEASING\b|\bCOVALTO\b|\bARRENDA|\bARRENDO\b|\bFINANCIAMIENTO\b|\bCREDITO AUTOMOTRIZ\b|\bPAGO (?:DE )?CREDITO\b|\bPRESTAMO\b|\bLOAN\b|\bMORTGAGE\b|\bAUTO PAY(?:MENT)?\b|\bPROGRESSIVE LEA|\bAMERICAN EDUCATION SE|\bNAVIENT\b|\bNELNET\b|\bSALLIE MAE\b', 'Loans and leasing', 'loan-lease', 'the loan, lease or financing wording', 'debit'),
    (r'\bRADIO MOVIL DIPSA\b|\bTELCEL\b|\bTELMEX\b|\bTELEFONOS DE MEXICO\b|\bTOTALPLAY\b|\bIZZI\b|\bMEGACABLE\b|\bAT&T\b|\bVERIZON\b|\bT-MOBILE\b|\bPEPCO\b|\bWASHINGTON GAS\b|\bDC WATER\b|\bCFE\b|\bCOMISION FEDERAL DE ELEC|\bSKY\b|\bDISH\b|\bSPECTRUM\b|\bGAS\b|\bENERGY\b|\bELECTRIC', 'Utilities and telecom', 'utility-telecom', 'the utility or telecom provider name', None),
    (r'\bEFECTIVALE\b|\bSI VALE\b|\bEDENRED\b|\bSODEXO\b|\bVALES? DE DESPENSA\b', 'Employee benefits', 'employee-benefits', 'the employee voucher provider name', None),
    (r'\bGEICO\b|\bSEGU\b|\bPOLIZA\b|\bPRIMA\b|\bINSUR(?:ANCE)?\b|\bINSUR PREM\b|\bSEGUROS?\b|\bLIFE INS', 'Insurance', 'insurance-wording', 'the insurance wording', None),
    (r'\b(?:' + _CARD_ISSUERS + r')\b', 'Card payments', 'card-issuer-payment', 'the card issuer named on a payment from this account', 'debit'),
    (r'\b(?:' + _P2P + r')\b|\bCASH APP\*', 'Peer-to-peer payments', 'p2p-app', 'the payment app name', None),
    (r'\bWITHDRAWAL AT ATM\b|\bATM WITHDRAWAL\b|\bWITHDRAWAL BY CASH\b|\bCASH WITHDRAWAL\b|\bRETIRO\b(?!.*\bINVERSION)|\bDISPOSICION\b', 'Cash withdrawals', 'cash-withdrawal-wording', 'the cash withdrawal wording', 'debit'),
    (r'\bDEPOSITO\s+(?:EN\s+)?EFECTIVO\b|\bDEP(?:OSITO)?\.?\s*CHEQUES?\b|\bDEPOSITO CHEQUE\b|\bDEPOSITO EMISOR\b|\bDEPOSITO\b|\bDEP\b|\bMOBILE DEPOSIT\b|\bDIRECT DEP|\bDEPOSIT\b', 'Deposits', 'deposit-wording', 'the deposit wording', 'credit'),
    (r'\bCOMPRA CHEQUE DE CAJA\b|\bCHEQUE\b|\bCHECK\s*(?:NUMBER|NO\.?|#)?\s*\d|^(?:\|\s*)?CHECK\b|\bCHK\b', 'Checks', 'check-wording', 'the check wording', None),
    (r'\bDIVISAS\b|\bTIPO DE CAMBIO\b|\bCAMBIOS/DERIVADOS\b|\bFX\b|\bFOREIGN EXCHANGE\b', 'Currency exchange', 'currency-exchange', 'the currency exchange wording', None),
    (r'\bPAGO CUENTA DE TERCERO\b|\bTRANSFERENCIA\b|\bSPE[I\]!L1|]?\s+(?:ENVIADO|RECIBIDO)\b|\bSPEI\b|\bDISPERSION\b|\bMOBILE BANKING\b|\bTRASPASO\b|\bABONO A CUENTA\b|\bCARGO A CUENTA\b|\bTRANSFER\b|\bXFER\b|\bWIRE\b|\bBNET\b', 'Transfers', 'transfer-wording', 'the transfer wording', None),
    (r'\bREEMB|\bBONIFICAC|\bCOMPENSACION\b|\bCANCELACION\b|\bDEVOLUCION\b|\bBONIFICACION\b|\bCREDIT VOUCHER\b|\bCREDIT ADJUSTMENT\b|\bREFUND\b|\bREVERSAL\b|\bRETURN(?:ED)?\b|\bWAIVE', 'Refunds and adjustments', 'refund-wording', 'the refund, return or adjustment wording', 'credit'),
    (r'\bNOMINA\b|\bPAYROLL\b|\bSALARY\b|\bSUELDO', 'Payroll', 'payroll-wording', 'the payroll wording', None),
    (r'\bGOBIERNO\b|\bGOV(?:ERNMENT|\x27?T)?\b|\bMUNICIPIO\b|\bPODER EJECUTIVO\b|\bDMV\b|\bUSPS\b|\bCOURT', 'Government payments', 'government-wording', 'the government payee wording', 'debit'),
    (r'\bPAGO\b|\bPAYMENT\b|\bPMT\b|\bPYMT\b|\bBILL PAY|\bPAID TO\b|\bDOMICILIACION\b|\bRECIBO\b|\bCIE:|\bACH\b|^[A-Z]\d{2}\s', 'Payments', 'payment-wording', 'the payment or direct debit wording', 'debit'),
    (r'\bPAGO\b|\bPAYMENT\b|\bPMT\b|\bPYMT\b|\bACH\b|\bI?ABONO\b|\bCREDIT\b', 'Incoming payments', 'incoming-payment-wording', 'the incoming payment wording', 'credit'),
]]


def bank_wording_category(value, *, direction, account_type=None):
    """(category, rule, cue) from Mexican and US bank-statement wording, or None.

    Applied only where the merchant and core rules found nothing. A debit card
    line is matched against the known merchants and business words first, then
    called a card purchase, so the merchant's own name drives the category.
    """
    tail = _card_tail(value, direction)
    if tail is not None:
        tail = re.sub(r'^DD\s+(?=DOORDASH)', '', tail)
        for pattern, merchant, kind in MERCHANTS:
            if pattern.match(tail):
                return ('Merchant credits' if direction == 'credit' else kind, 'debit-card-merchant', f'the merchant {merchant} on a debit card line')
        if re.search(r'\b(?:' + _P2P + r')', tail):
            return 'Peer-to-peer payments', 'p2p-app', 'the payment app name'
        for pattern, kind in [
            (r'\b(?:PARKING|COLPARK|USAPARKING|PARKX)', 'Parking and tolls'),
            (r'\b(?:STORAGE)', 'Storage'),
            (r'\b(?:GIANT|SAFEWAY|WAL-?MART|WALMART|ALDI|KROGER|WHOLE FOODS|TRADER JOE|HARRIS TEETER|COSTCO|SAMS|SAM\x27S|FOOD LION|LIDL|SHOPRITE|PUBLIX|GROCERY|MARKET)', 'Groceries'),
            (r'\b(?:RESTAURANT|PIZZA|CAFE|GRILL|BURGER|CHICKEN|WINGS|DONUT|DUNKIN|SUBWAY|WENDY|POPEYES|KFC|TACO|CHIPOTLE|STARBUCKS|DOORDASH|UBER EATS|GRUBHUB)', 'Meals'),
            (r'\b(?:SHELL|EXXON|CHEVRON|SUNOCO|BP|CITGO|MOBIL|GAS STATION|SERVICE STATION|FUEL|SPEEDWAY|WAWA|7-ELEVEN)', 'Fuel'),
            (r'\b(?:UBER|LYFT|METRO|WMATA|TAXI|ZIPCAR|PARKING|AMTRAK|AIRLINE|AIRWAYS)', 'Transport'),
            (r'\b(?:NETFLIX|HULU|SPOTIFY|PANDORA|APPLE\.COM|GOOGLE|AMAZON PRIME|DISNEY|YOUTUBE|SIRIUS|PRIME VIDEO|MICROSOFT|ADOBE)', 'Subscriptions'),
            (r'\b(?:CVS|WALGREENS|RITE AID|PHARMACY|MEDICAL|DENTAL|HOSPITAL|CLINIC|SENIORCARE)', 'Health and pharmacy'),
            (r'\b(?:AMAZON|AMZN|TARGET|DSW|MACY|ROSS|MARSHALLS|TJ ?MAXX|BEST BUY|HOME DEPOT|LOWE|DOLLAR|IKEA|EBAY|ETSY|NORDSTROM|KOHL)', 'Shopping'),
            (r'\b(?:HOTEL|INN|MARRIOTT|HILTON|AIRBNB|EXPEDIA|BOOKING)', 'Travel'),
        ]:
            if re.search(pattern, tail):
                return ('Merchant credits' if direction == 'credit' else kind, 'debit-card-business-type', f'the merchant wording on a debit card line')
    for pattern, kind, rule, cue, wanted in _BANK_WORDING:
        if wanted and wanted != direction:
            continue
        if kind == 'Card payments' and account_type == 'credit_card':
            continue
        if pattern.search(value):
            return kind, rule, cue
    if tail is not None and (not value.startswith(('|', '}', '~')) or re.search(r'[A-Z]{3}', tail)):
        return ('Merchant credits' if direction == 'credit' else 'Card purchases', 'debit-card-purchase', 'the debit card purchase wording')
    if account_type == 'credit_card':
        if direction == 'credit' and re.search(r'\b(?:PAYMENT|PYMT|PMT|PAGO)\b', value):
            return 'Card payments', 'card-payment-wording', 'the card payment wording'
        return ('Merchant credits' if direction == 'credit' else 'Card purchases', 'card-line', 'a charge or credit on a card statement')
    return None


def card_merchant_descriptor(raw):
    """Use a readable merchant descriptor beyond the known-brand list.

    Card descriptors often concatenate merchant, city and state. Keep that
    printed label rather than guessing where a legal name ends. Require a
    processor, business wording, or the issuer's merchant/location format;
    reference-only strings and generic account movements are not merchants.
    """
    value = normalized(raw)
    if not 4 <= len(value) <= 180:
        return None
    if re.match(r'^(?:\d|[A-Z]{1,4}\s*\d{3,})', value):
        return None
    if re.match(r'^CLKBANK\*COM_', value) or re.search(r'\*[A-F0-9]{12,}', value):
        return None
    if re.match(r'^(?:(?:CAPITAL ONE|CARD|BANK)\s+)?(?:PAYMENTS?|PYMT|PMT|MOBILE|ONLINE|AUTOPAY|AUTOMATIC|ELECTRONIC|CREDIT|DEBIT|REFUND|REVERSAL|ADJUSTMENT|CASH|BALANCE|INTEREST|FINANCE CHARGE|TRANSFER|WIRE|ATM|UNKNOWN|REFERENCE|REF\b|NOT RECORDED)\b', value):
        return None
    processor = re.match(r'^(?:TST|SQ|PAYPAL|SP|SPO|PY|MED)\s*\*\s*(.+)', value)
    # Ten-digit North American phone numbers or the printed city/state suffix.
    states = r'(?:AL|AK|AZ|AR|CA|CO|CT|DE|DC|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY|AB|BC|MB|NB|NL|NS|NT|NU|ON|PE|QC|SK|YT)'
    phone_pattern = r'(?<!\d)(?:\d{3}[-. ]?){2}\d{4}(?=[A-Z -]*' + states + r'$)'
    phone = re.search(phone_pattern, value)
    location = re.search(r'[A-Z]{3}' + states + r'$', value)
    business = re.search(r'\b(?:PARKING|COLPARK|PARKX|DENTAL|DENTISTRY|HOSPITAL|ORTHODONTIC|MEDICAL|SALON|LASH|BROW|BARBER|STORAGE|RESTAURANT|PIZZA|CAFE|CAR WASH|DETAILING|MINI GOLF|COUNTY FAIR|AMUSEMENT)\b', value)
    if not (processor or phone or location or business):
        return None
    label = re.sub(r'^(?:TST|SQ|PAYPAL|SP|SPO|PY|MED)\s*\*\s*', '', raw, flags=re.I)
    label = re.sub(phone_pattern + states + r'$', '', label, flags=re.I).strip()
    label = re.sub(phone_pattern, ' ', label, flags=re.I).strip()
    # A processor plus an opaque reference still does not identify a merchant.
    if not re.search(r'[A-Za-z]{3}', label) or re.search(r'\d{10,}', label):
        return None
    return ' '.join(label.split())


def _name(value):
    text = normalized(value)
    return (2 <= len(text) <= 180 and any(c.isalpha() for c in text)
            and not re.search(r'\d{5,}|\b(?:REF|UNKNOWN|NOT RECORDED|THIRD PARTY|TERCEROS?|ACCOUNT|CUENTA|ORDENANTE)\b', text))


def balance_reading_status(row):
    if row.running_balance_minor is not None:
        return 'recorded'
    original = (row.provenance or {}).get('statement_import_original', {})
    fields = original.get('fields', {})
    if not original.get('issues') and (
            (fields.get('printed_section') and fields.get('card_ending'))
            or fields.get('date_basis') == 'statement_end_ordering_only'):
        return 'not_printed'
    return 'unavailable'
