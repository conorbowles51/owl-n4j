"""Reproducible description labels, separate from documentary readings.

These suggestions describe a merchant or payment type, never beneficial
ownership, personal/business purpose, or the funding account behind a card
payment. Explicit investigator labels always take precedence in payment_labels.
"""
import re
import unicodedata

VERSION = 'description-labels/3'


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


def infer_payment_labels(description, *, direction, account_type=None, institution=None):
    """Return label values with the rule and explanation used for each one."""
    if direction not in ('credit', 'debit'):
        return {}
    raw = ' '.join((description or '').split())
    value = normalized(raw)
    if not value:
        return {}
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

    if account_type == 'credit_card' and direction == 'credit' and re.search(r'\b(?:CASH BACK REWARD|REWARD REDEMPTION)\b', value):
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
    if direction == 'debit' and account_type != 'credit_card' and cie and _name(cie[1]):
        suggest('counterparty', cie[1].strip(), 'bbva-cie-payee', 'Payee label printed before the REF and CIE references in the payment description. This label does not establish the ultimate beneficiary.')
        if 'category' not in result:
            category('Payments', 'cie-payment', 'the CIE payment reference')
    elif named and _name(named[1]):
        suggest('counterparty', named[1].strip(), 'named-payment-party', f'The description explicitly says “{cue.lower()} {named[1].strip()}”. Verify the name against the source before linking an identity.')
    # BBVA: the receiving bank precedes the reference. The named beneficiary
    # follows the long numeric tracking code. Never use the intermediary bank.
    elif re.match(r'T\d{2}\s+(?:SPEI|SPID)\s+(?:ENVIADO|RECIBIDO)\b', normalized(raw)):
        sent = ' ENVIADO ' in normalized(raw)
        tail = re.search(r'\b\d{15,}\s+([A-ZÁÉÍÓÚÜÑ][A-ZÁÉÍÓÚÜÑ .&\x27’/-]{2,180})$', raw, re.I)
        if tail and sent == (direction == 'debit') and _name(tail[1]):
            suggest('counterparty', tail[1].strip(), 'bbva-transfer-party', 'Name printed after the transfer tracking reference; the receiving bank is not treated as the beneficiary.')
    elif direction == 'credit':
        depositor = re.match(r'^(?:W\d{2}\s+)?DEPOSITO DE TERCERO\s+(.+?)\s+BMRCASH\b', raw, re.I)
        if depositor and _name(depositor[1]):
            suggest('counterparty', depositor[1].strip(), 'bbva-depositor', 'Name printed after “DEPOSITO DE TERCERO” in the description.')
    if account_type == 'credit_card' and 'counterparty' not in result:
        merchant = card_merchant_descriptor(raw)
        if merchant and result.get('category', {}).get('value') not in (
                'Taxes', 'Interest income', 'Interest charges', 'Bank fees',
                'Payroll', 'Cash withdrawals', 'Transfers', 'Deposits'):
            suggest('counterparty', merchant, 'card-statement-descriptor',
                'Merchant label from the card payment description, not a verified legal identity. '
                'Location or store text is retained when its boundary is unclear. '
                'The original description remains available; a processor prefix does not establish the ultimate recipient.')
            if direction == 'credit' and 'category' not in result:
                category('Merchant credits', 'merchant-credit-descriptor', 'the merchant descriptor on this card credit')
    return result


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
