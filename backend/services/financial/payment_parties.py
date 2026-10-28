"""The other side of a payment, as the statement prints it in the description.

Each rule recognises one printed layout and takes the name from the field that
layout reserves for the beneficiary, the ordering party, the payee or the
merchant. A bank that only carries the money (the receiving or sending bank of
a transfer) is never taken as the party when a name is printed. Nothing is
guessed: a layout whose name field cannot be told apart from its references or
concept text gives no name. These are read-time suggestions; the stored
description is never changed and a person's label always wins
(services.financial.payment_labels).
"""
import re
import unicodedata

from services.financial.payment_inference import normalized

# Mexican banks as they are printed before the beneficiary in SPEI lines that
# print no field separator. Longest names first so 'BBVA MEXICO' wins over 'BBVA'.
_MX_BANKS = sorted([
    'BBVA MEXICO', 'BBVA BANCOMER', 'BBVA', 'BANAMEX', 'CITI MEXICO', 'CITIBANAMEX', 'BANORTE', 'SANTANDER', 'HSBC',
    'SCOTIABANK', 'INBURSA', 'AZTECA', 'BANCOPPEL', 'BAJIO', 'BANBAJIO', 'AFIRME', 'MIFEL', 'BANREGIO', 'MONEX',
    'INTERCAM BANCO', 'INTERCAM', 'KAPITAL', 'AUTOFIN', 'NU MEXICO', 'STP', 'KUSPIT', 'BANCOMEXT', 'VE POR MAS',
    'MULTIVA', 'BANJERCITO', 'ACTINVER', 'BANSI', 'INVEX', 'BARCLAYS', 'MERCADO PAGO W', 'SABADELL', 'HEY BANCO',
    'BANCO BASE', 'CIBANCO', 'HSBC MEXICO', 'SANTANDER MEXICO', 'BANORTE IXE', 'SCOTIABANK INVERLAT', 'BANKAOOL', 'ALBO', 'FONDEADORA', 'SPIN BY OXXO', 'TRANSFER', 'ASP INTEGRA OPC',
], key=len, reverse=True)

_UNVERIFIED = r'\s*(?:\bDAT[O0]\s*N[O0]\b|DAT[O0]\s*N[O0]\s*\W?[VM]ERIF).*$'
_STATES = ('AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH '
           'OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY').split()
# Places printed after the merchant on US debit card lines, removed only when
# they are the last words before the state. Other place names stay, so the
# printed descriptor is never cut where its end is unclear.
_PLACES = ['WASHINGTON', 'HYATTSVILLE', 'SUITLAND', 'SILVER SPRING', 'OXON HILL', 'ALEXANDRIA', 'ANNAPOLIS',
           'FALLS CHURCH', 'WHEATON', 'ODENTON', 'MILLERSVILLE', 'CAMP SPRINGS', 'CLINTON', 'TEMPLE HILLS',
           'DISTRICT HEIG', 'FORT WASHINGT', 'UPPER MARLBOR', 'UPPR MARLBORO', 'CAPITOL HEIGH', 'LANHAM',
           'BOWIE', 'LAUREL', 'ARLINGTON', 'BALTIMORE', 'BETHESDA', 'ROCKVILLE', 'COLLEGE PARK', 'LARGO',
           'GREENBELT', 'WOODBRIDGE', 'FORESTVILLE', 'DISTRICT HEIGHTS', 'NEW YORK', 'NEW YORK CITY']
_PLACES.sort(key=len, reverse=True)


def _without_place(label):
    """The label without a known place printed (or glued, 'MARKETWASHINGTON') at its end."""
    for place in _PLACES:
        if label.endswith(place) and len(label) > len(place) + 2 and (label[-len(place) - 1] == ' ' or len(place) >= 8):
            return label[:-len(place)].strip()
    return label


def clean_name(value):
    """A printed name without the bank's qualification, footnote marks and stray references."""
    text = re.sub(_UNVERIFIED, '', value or '', flags=re.I)
    text = re.sub(r'(?:[({]\s*[1lI7]\s*(?:[)}]|(?=\s|$))\s*)+', ' ', text)
    # Long digit runs inside a name are a reference that landed in the field.
    text = ' '.join(t for t in text.split() if not re.fullmatch(r'\d{6,}', t))
    return text.strip(' |],;:.-—').strip()


def plausible_name(value):
    text = normalized(value)
    letters = sum(c.isalpha() for c in text)
    return (letters >= 2 and len(text) <= 180 and not re.search(r'\d{7,}', text)
            and not re.fullmatch(r'(?:REF|REFERENCIA|CONCEPTO|CUENTA|CLABE|ACCOUNT|CLIENTE|BANCO|BANK|N/?A|SIN NOMBRE|'
                                 r'TERCEROS?|ORDENANTE|BENEFICIARIO|NOMBRE|NONE|UNKNOWN)', text))


# A transfer's own layout opening: wording found later in it (a concept saying COMISION) is not the bank's charge.
TRANSFER_OPENING = re.compile(r'^(?:\S{1,3}\s+\d{2}/[A-Z]{3}\s+)?(?:\d+\s+)?(?:[A-Z0-9]{2,3}\s+)?(?:(?:ABONO|CARGO|PAGO)\s+(?:POR\s+)?TRANSFERENCIA\b|'
                              r'SP(?:ID|E\S?)\s+(?:ENVIADO|RECIBIDO)|TRASPASO A TERCEROS\b|(?:ENVIO|RECEPCION)\s+SP(?:EI|ID)\b)')


# Rules that read a transfer's own name field. Only these may replace a charge
# or interest suggestion made from wording found elsewhere in the description
# (a transfer whose concept text says COMISION is still a transfer).
TRANSFER_RULES = frozenset({'spei-cliente-party', 'spei-delimited-party', 'monex-named-party', 'bbva-transfer-party',
                            'third-party-account', 'zelle-party', 'credit-union-transfer-party', 'ach-company',
                            'named-payment-party', 'bill-payee', 'service-payee'})


def printed_party(raw, *, direction, account_type=None):
    """(name, rule, explanation) of the other side printed in the description, or None."""
    if account_type == 'credit_card' or not raw or not raw.strip():
        return None
    # Descriptions are at most a few thousand characters; a longer one is read from its start.
    raw = raw[:3000]
    value = normalized(raw)
    for rule in (_santander_spei, _delimited_spei, _monex_transfer, _bbva_spei, _bbva_third_party_account,
                 _mx_payee, _us_ach_company, _us_named_transfer, _us_card_merchant, _us_bar_line):
        found = rule(raw, value, direction)
        if found:
            name, rule_id, explanation = found
            if rule_id == 'third-party-account':
                return found
            name = clean_name(name)
            if plausible_name(name):
                return (name if rule_id == 'debit-card-merchant' else _as_printed(name, raw)), rule_id, explanation
            return None
    return None


def _as_printed(name, raw):
    """The name with the accents and capitals the statement prints (rules read an unaccented upper-case copy)."""
    folded, at = [], []
    for i, c in enumerate(raw):
        for b in (' ' if c.isspace() else ''.join(x for x in unicodedata.normalize('NFKD', c) if not unicodedata.combining(x)).upper()):
            folded.append(b)
            at.append(i)
    # The name field follows the layout's other wording, so its last printing is the field itself.
    found = [*re.finditer(r'(?<![A-Z0-9])' + r'\s+'.join(re.escape(w) for w in name.upper().split()) + r'(?![A-Z0-9])', ''.join(folded))]
    found = found[-1] if found else None
    return ' '.join(raw[at[found.start()]:at[found.end() - 1] + 1].split()) if found else name


_UNVERIFIED_NOTE = ' The bank marks this name as not verified by it; check ownership separately.'


def _santander_spei(raw, value, direction):
    # PAGO TRANSFERENCIA SPEI HORA .. ENVIADO A <bank> A LA CUENTA <clabe> AL CLIENTE <name> (1) (1) DATO NO ...
    # ABONO TRANSFERENCIA SPEI HORA .. RECIBIDO DE <bank> DE LA CUENTA <clabe> DEL CLIENTE <name> CLAVE DE RASTREO ..
    sent = re.search(r'\bENVIADO A\s+.+?\s+A\s?LA CUENTA\s+[\d ]+?\s+AL CLIENTE\s+(.+)$', value)
    got = re.search(r'\bRECIBIDO DE\s+.+?\s+DE LA CUENTA\s+[\d ]+?\s+DEL CLIENTE\s+(.+)$', value)
    match = sent if direction == 'debit' else got
    if not match or not re.search(r'\b(?:SPE\S?|SPID|TEF)\s+HORA\b', value):
        return None
    name = re.split(r'\s*[({]\s*[1lI7]\s*[)}]|\s+DATO\s+NO\b|\s+(?:CLAVE\s+)?DE\s+RASTREO\b|\s+RASTREO\b|\s+REF\s+\d|\s+CONCEPTO\b|\s+RFC\b', match[1])[0]
    role = 'beneficiary' if direction == 'debit' else 'sender'
    return name, 'spei-cliente-party', (f'The {role} printed after “{"AL" if direction == "debit" else "DEL"} CLIENTE” in the '
                                        'transfer description; the bank and account are separate fields.'
                                        + (_UNVERIFIED_NOTE if 'NO VERIFICADO' in value else ''))


def _delimited_spei(raw, value, direction):
    # ENVIO SPEI <bank> | <name> DATO NO VERIFICADO .. | <clabe> | ..   (Intercam, Kapital)
    # RECEPCION SPEI | <bank> | <name> DATO NO VERIFICADO .. | <clabe> | ..
    # ENVIO SPEI <bank> <name> <clabe> <concept> ..   (the same layout printed without separators)
    match = re.match(r'^(?:\d+\s+)?(ENVIO|RECEPCION)\s+SP(?:EI|ID)\b\s*(.*)$', value)
    if not match or (match[1] == 'ENVIO') != (direction == 'debit'):
        return None
    rest = match[2]
    note = _UNVERIFIED_NOTE if re.search(r'NO\s+I?\s*VERIFICADO', rest) else ''
    role = 'beneficiary' if direction == 'debit' else 'sender'
    explanation = f'The {role} printed in the name field of the transfer description; the bank and account are separate fields.' + note
    if '|' in rest:
        # ENVIO prints its bank before the first bar, RECEPCION after it: either
        # way the second non-empty field is the other side's name.
        fields = [f.strip() for f in rest.split('|') if f.strip()]
        if len(fields) > 1 and not re.search(r'\d{10,}', fields[1]):
            return fields[1], 'spei-delimited-party', explanation
        return None
    for bank in _MX_BANKS:
        if rest.startswith(bank + ' '):
            tail = re.match(r'(.+?)\s+(?:CLABE\s+)?\d{17,19}\b', rest[len(bank) + 1:])
            if tail:
                return tail[1], 'spei-delimited-party', explanation
            return None
    return None


def _monex_transfer(raw, value, direction):
    if direction == 'debit':
        match = (re.search(r'\bNOMBRE BENEFICIARIO\s*:\s*(.+?)\s+(?:CLAVE DE RASTREO|REFERENCIA|CONCEPTO|RFC)\b', value)
                 or re.search(r'\bBENEFICIARIO\s+(.+?),\s*(?:CONCEPTO|REF)\b', value)
                 or re.match(r'^RETIRO BENEFICIARIO\s+(.+?)\s+(?:RFC\s*:|BANCO\s)', value))
        role = 'beneficiary'
    else:
        match = re.search(r'\bNOMBRE DEL ORDENANTE\s*:\s*(.+?)\s+(?:CLAVE DE RASTREO|REFERENCIA|CONCEPTO)\b', value)
        role = 'ordering party'
    if not match:
        return None
    return match[1], 'monex-named-party', f'The {role} printed in its own labelled field of the transfer description; the receiving or sending bank is a separate field.'


_BBVA_SPEI = re.compile(r'^(?:\S{1,3}\s+\d{2}/[A-Z]{3}\s+)?[A-Z0-9]{2,3}\s+SP(?:ID|E\S?)\s+(ENVIADO|RECIBIDO)\s*(.*)$')


def _bbva_spei(raw, value, direction):
    # T17 SPEI ENVIADO <bank> <7 digits><concept> Ref. <10 digits> <bank code> <clabe> <tracking> <name>
    match = _BBVA_SPEI.match(value)
    if not match or (match[1] == 'ENVIADO') != (direction == 'debit'):
        return None
    role = 'beneficiary' if direction == 'debit' else 'ordering party'
    after_ref = re.search(r'\bREF\.\s*\d{6,}\s+\d{3}\b\s*(.*)$', match[2])
    if after_ref:
        tokens = after_ref[1].replace('|', ' ').split()
        # Account, tracking key and other references come first; the name follows them.
        while tokens and (re.search(r'\d', tokens[0]) and len(tokens[0]) >= 5 or re.fullmatch(r'\d+', tokens[0])):
            tokens.pop(0)
        # A further long reference inside what is left ends the reference block.
        for index in range(len(tokens) - 1, -1, -1):
            if re.search(r'\d{8,}', tokens[index]) or re.fullmatch(r'(?=(?:\D*\d){3})[A-Z0-9]{10,}', tokens[index]):
                tokens = tokens[index + 1:]
                break
        if tokens:
            return ' '.join(tokens), 'bbva-transfer-party', f'The {role} printed after the account and tracking references; the bank named first carries the transfer and is not taken as the party.'
        return None
    # Without the Ref. block, an account or tracking number of 15 or more digits still ends the references.
    tail = re.search(r'\b\d{15,}\s+([^\d]+)$', match[2])
    if tail:
        return tail[1], 'bbva-transfer-party', f'The {role} printed after the account and tracking references; the bank named first carries the transfer and is not taken as the party.'
    # Without any reference the concept and name run together. Only a
    # payroll concept with its date ends at a known place.
    short = re.match(r'^.+?\s\d{7}NOMINA\s+\d{6}\s+(.+)$', match[2])
    if short and not re.search(r'\d', short[1]):
        return short[1], 'bbva-transfer-party', f'The {role} printed after the payroll concept and its date; the bank named first carries the transfer and is not taken as the party.'
    return None


def _bbva_third_party_account(raw, value, direction):
    # N06 PAGO CUENTA DE TERCERO BNET <10-digit account> <concept> Ref. ..: only the account is printed.
    match = re.match(r'^[A-Z]\d{2}\s+PAGO CUENTA DE TERCERO\s+BNET\s+(\d{10})\b', value)
    if match:
        return (f'Account {match[1]} (no name printed)', 'third-party-account',
                'The statement prints only the other account’s number for this transfer, not a name. It is shown so payments to and from the same account can be followed; it does not identify the holder.')
    return None


def _mx_payee(raw, value, direction):
    if direction != 'debit':
        return None
    # DOMICILIACION PAGO SERVICIO <contract> RFC <rfc> COBRO <amount> <payee>
    match = re.search(r'\bDOMICILIACION PAGO SERVICIO\b.*\bCOBRO\s+[\d,.]+\s+(.+)$', value)
    if match:
        return match[1], 'direct-debit-payee', 'The company collecting this direct debit, printed after the amount collected.'
    # CIE payments: P14 <payee> REF:<ref> CIE:<agreement>, or the payee alone.
    match = re.match(r'^P14\s+(.+?)(?:\s+REF\s*:.*\bCIE\s*:.*)?$', value)
    if match and not re.search(r'\b(?:REF|CIE)\s*:', match[1]):
        return match[1], 'bbva-cie-payee', 'Payee printed before the REF and CIE references of this bill payment. It does not establish the ultimate beneficiary.'
    # P31/K08 direct debits print the collecting company first, then its references.
    match = re.match(r'^(?:P31|K08)\s+(.+)$', value)
    if match:
        words = []
        for token in match[1].split():
            if re.search(r'\d', token) or token in ('REF.', 'REF'):
                # The name field is fixed width; its last word can run into the reference (NAME12345).
                head = re.match(r'[A-Z]{3,}(?=\d)', token)
                if head and words:
                    words.append(head[0])
                break
            words.append(token)
        if len(words) >= 2:
            return ' '.join(words), 'bbva-direct-debit-payee', 'The company collecting this direct debit, printed before its references.'
    match = re.match(r'^PAGO SERVICIO\s+([A-Z][A-Z .&]+)$', value)
    if match:
        return match[1], 'service-payee', 'The payee printed after “PAGO SERVICIO”.'
    if re.search(r'\bPAGO REFERENCIADO SAT\b', value):
        return 'SAT', 'tax-authority-payee', 'The description names the tax authority (SAT) as the payee of this referenced payment.'
    match = re.match(r'^[A-Z]\d{2}\s+(IMSS/INF/AFORE)\b', value)
    if match:
        return match[1], 'social-security-payee', 'The description names the social security institutes (IMSS, INFONAVIT, AFORE) paid through SIPARE.'
    return None


def _us_ach_company(raw, value, direction):
    # Andrews: Withdrawal ACH <name> TYPE: <type> ID: <id> CO: <company> [NAME: <person>] ACH Trace Number: ..
    match = re.match(r'^(?:WITHDRAWAL|DEPOSIT)\s+ACH\b.*?\bCO\s*:\s*(.+?)\s+(?:NAME\s*:|ACH TRACE|ENTRY CLASS|\.\s)', value)
    wanted = 'WITHDRAWAL' if direction == 'debit' else 'DEPOSIT'
    if match and value.startswith(wanted):
        return match[1], 'ach-company', 'The company name printed in the ACH “CO:” field of this payment.'
    return None


def _us_named_transfer(raw, value, direction):
    text = ' '.join(raw.split())
    cue = 'FROM' if direction == 'credit' else 'TO'
    for pattern, rule, explanation in [
        # Andrews: Withdrawal Online Banking Transfer To <SURNAME,GIVEN> XXXXXXXXXX Share 0040 ..
        (rf'^(?:WITHDRAWAL|DEPOSIT)\s+(?:ONLINE BANKING\s+)?TRANSFER\s+(?:\S+\s+){{0,3}}?{cue}\s+(?!LOAN\b|SHARE\b)(.+?)\s+X{{4,}}\b',
         'credit-union-transfer-party', 'The member printed as the other side of this credit union transfer; the masked account number is separate.'),
        (r'^WITHDRAWAL BILL PAYMENT BILL PAID-\s*(.+?)(?:\s+(?:CONF\b|CON\S?\s*#|#\s*\d).*)?$' if direction == 'debit' else r'(?!)',
         'bill-payee', 'The payee printed after “Bill Paid-”.'),
        # Navy Federal: Paid To - <payee> <type>; Payment To - <payee> <reference>; Deposit - ACH Paid From <payer> <ref>
        (r'^(?:PAID TO|PAYMENT TO|ACH PAID TO)\s*-?\s*(.+)$' if direction == 'debit' else r'^DEPOSIT\s*-\s*ACH PAID FROM\s+(.+)$',
         'named-payment-party', 'The party printed after “paid to” or “paid from” in the description.'),
        # Andrews: Deposit|Withdrawal Faster Payments ZEL* <name> <reference>
        (rf'^{"DEPOSIT" if direction == "credit" else "WITHDRAWAL"} FASTER PAYMENTS ZEL\*\s*(.+?)\s+\S*\d\S*$',
         'zelle-party', 'The person or business printed as the other side of this Zelle payment.'),
        # Andrews: Deposit Debit Card CASH APP*CASH OUT Visa Direct ..: money pushed from a payment app.
        (r'^DEPOSIT DEBIT CARD\s+(.+?)\s+VISA DIRECT\b' if direction == 'credit' else r'(?!)',
         'card-push-payment-source', 'The payment app or sender printed on this Visa Direct card deposit; the person behind it is not printed.'),
        # Truist merchant card settlement: MC VI DEP TRUIST MERCH SVC <merchant name> ..
        (r'^MC VI DEP\s+(.+?\bMERCH SVC)\b' if direction == 'credit' else r'(?!)',
         'card-settlement-payer', 'The card processor printed as the payer of this card sales settlement.'),
        # Zelle: ZELLE PAYMENT TO|FROM <name> PAYMENT ID ..
        (rf'^ZELLE PAYMENT\s+{cue}\s+(.+?)(?:\s+PAYMENT ID\b.*)?$', 'zelle-party', 'The person or business printed as the other side of this Zelle payment.'),
    ]:
        match = re.match(pattern, value)
        if match:
            name = match[1]
            if rule == 'card-push-payment-source' and re.search(r'\*\s*ID\b', name):
                return None
            if rule == 'named-payment-party':
                # The payee comes before the payment type, check or reference.
                name = re.split(r'\s+(?:MOBILE PMT|ONLINE PMT|CHECK PYMT|(?:ONLINE\s+)?PAYMENTS?\b|CHK\b|CK#|PYMT\b|PMT\b|ARC\b|\d)', name)[0]
            span = re.search(re.escape(name), text, re.I)
            return (text[span.start():span.end()] if span else name), rule, explanation
    return None


def _us_card_merchant(raw, value, direction):
    from services.financial.payment_inference import _card_tail, MERCHANTS
    tail = _card_tail(value, direction) if not value.startswith(('|', '}', '~')) else None
    if tail is None:
        # Truist debit card lines that the category reader does not treat as purchases.
        other = re.match(r'^DEBIT CARD (?:RECURRING PYMT|MISC DEBIT|RETURN|CREDIT)\s+(.+)$', value)
        if not other:
            return None
        tail = other[1]
    # Truist PIN purchases print the place and card digits before the merchant.
    pin = re.match(r'^PURCHASE-PIN\s+\d{2}-\d{2}-\d{2}\s+.+?\s+\d{4}\s+(.+)$', tail)
    if pin:
        tail = pin[1]
    tail = re.sub(r'^(?:CREDIT VOUCHER\s+)?\d{2}/\d{2}\s+[0O]\s+\d{5,}\s+[0O]\s*', '', tail)
    # Authorisation digits read badly (B1234 0, ~1234 0, 000001OAA1 0) still end at the lone 0 before the merchant.
    tail = re.sub(r'^\S*\d\S*\s+[0O]\s+(?=[A-Z])', '', tail)
    # A terminal printed as its street address names no merchant (12345 - 100 MAIN ST ANYTOWN MD).
    if re.match(r'^(?:\d+\s+-\s+)?\d+\s+(?:[A-Z0-9]+\s+){1,2}(?:AV|AVE|ST|RD|BLVD|DR|PKWY|HWY|PL|WAY|LN|CT)\b', tail) or \
            re.search(r'(?:^|\s)\d+\s+-\s+\d+\s+(?:[A-Z0-9]+\s+){1,2}(?:AV|AVE|ST|RD|BLVD|DR|PKWY|HWY|PL|WAY|LN|CT)\b', tail):
        return None
    # Leading card, type and date words left by the bank's prefix (PURCHASE-PIN 01-01-24, RECURRING PYMT ..).
    while True:
        stripped = re.sub(r'^(?:PURCHASE(?:-PIN)?|REV AUTH|RECURRING|PYMT|MISC|DEBIT|RETURN|CARD|TRANSACTION|POS|ON|'
                          r'\d{2}[-/]\d{2}(?:[-/]\d{2,4})?|\d{3,}(?:\s+-)?|\.?[0O]{1,2}|\.\d+|\S*\d\S*(?=\s+[0O]\s+[A-Z])|\S?\d{1,2}(?=\s+[0O]\s)|[0O]+\d{3,}|(?=[\dIl]*\d{4})[\dIl]{6,})\s+', '', tail)
        if stripped == tail:
            break
        tail = stripped
    for pattern, merchant, _ in MERCHANTS:
        found = pattern.match(re.sub(r'^DD\s+(?=DOORDASH)', '', tail))
        if found:
            return merchant, 'debit-card-merchant', f'Merchant recognised from “{found[0]}” on this debit card line. This does not establish legal identity or ownership.'
    words = tail.split()
    kept = []
    for token in words:
        # Truist and Navy print the purchase date, then the place, after the merchant.
        if (re.fullmatch(r'\d{2}-\d{2}(?:-\d{2,4})?', token) or re.fullmatch(r'(?:\d{3}-?){2}\d{4}', token)
                or kept and re.fullmatch(r'\d{2}/\d{2}', token)):
            break
        # A store number or a reference code ends the merchant; the street or place follows it.
        if kept and (re.fullmatch(r'#?\d{3,}', token) or re.fullmatch(r'(?=(?:\D*\d){3})[A-Z0-9]{6,}', token)):
            break
        kept.append(token)
    while len(kept) > 1 and (kept[-1] in _STATES or re.fullmatch(r'\d{1,6}|#\d+|[\d\-]+', kept[-1])
                             or re.fullmatch(r'(?:HTTPS?|WWW)\S*|\S*\.(?:COM|NET|ORG)(?:/\S*)?\.?', kept[-1])):
        kept.pop()
    label = _without_place(' '.join(kept))
    label = re.sub(r'\s*#\s*\d+\b.*$', '', label)
    # A processor's order or reference code after the merchant (MERCHANT*1A2B3C4D5, SHOP* I01234-5678).
    label = re.sub(r'\s*\*\s*(?=\S*\d)\S{5,}$', '', label)
    label = re.sub(r'(?<=[A-Z])\s+(?=(?:\S*?\d){3})[A-Z0-9.\-]{4,}$', '', label).strip(' *-')
    # A payment processor's prefix is not the merchant (TST* EXAMPLE CAFE, SQ *COFFEE).
    label = re.sub(r'^(?:TST|SQ|IC|SP|PY|SPO)\s*\*\s*', '', label)
    if not re.search(r'[A-Z]{3}', label) or re.fullmatch(r'(?:DATE|CARD|DEBIT|PURCHASE|POS|TRANSACTION)(?:\s.*)?', label):
        return None
    # The card line's own prefix, read too badly to strip (W·ITHDRAWAL DEBIT CARD), is not a merchant.
    if re.search(r'THDRAWAL|DEBITCARD', re.sub(r'[^A-Z]', '', label)):
        return None
    span = re.search(re.escape(label).replace(r'\ ', r'\s+'), ' '.join(raw.split()), re.I)
    label = span[0] if span else label
    return label, 'debit-card-descriptor', 'Merchant as printed on this debit card line, with the card, date and place details removed. It is not a verified legal identity; the original description remains available.'


def _us_bar_line(raw, value, direction):
    # M&T prints each line after a bar: the merchant or ACH company, then its entry
    # wording and references (| EXAMPLEINSCO INSUR PREM, | SSA TREAS 310 XXSOC SEC).
    from services.financial.payment_inference import MERCHANTS
    match = re.match(r'^(?:[|}\]~]\s*)+(?:PIN\s*)?(?:RETURN-\s*)?(?:PURCHASE (?:WITH CASH BACK )?ON\s+\d{2}/\d{2}\s+)?(.+)$', value)
    if match:
        # OCR splits the debit card prefix after the bar (~Wi thdrawal Debit Card ..): read it as that card line.
        card = re.match(r'^\S{0,2}\s?I\s?T?\s?H\s?D\s?R\s?A\s?W\s?A\s?L\s+DEBIT CARD\s+(.+)$', match[1])
        if card:
            return _us_card_merchant(raw, 'WITHDRAWAL DEBIT CARD ' + card[1], direction) if direction == 'debit' else None
        if re.search(r'THDRAWAL|DEPOSIT', match[1].replace(' ', '')[:14]):
            return None
    if not match or re.match(r'(?:CHECK|ATM|INTEREST|LINE OF CREDIT|CREDIT LINE|MOBILE DEPOSIT|DEPOSIT|TRANSFER|ONLINE TRANSFER|'
                             r'OVERDRAFT|EFT PAYMENT|ADVANCE|WITHDRAWAL|NON-|M&T|WAIVE|REVERSE|COBRO|COMISION|IVA|SPEI|SEL|TRANSF\S*)\b', match[1]):
        return None
    tail = re.sub(r'^DD\s*\*?\s*(?=DOORDASH)', '', match[1])
    for pattern, merchant, _ in MERCHANTS:
        found = pattern.match(tail)
        if found:
            return merchant, 'debit-card-merchant', f'Merchant recognised from “{found[0]}” on this line. This does not establish legal identity or ownership.'
    words = []
    for token in tail.split():
        if (re.search(r'\d', token) or re.match(r'(?:HTTPS?|WWW)|\S*\.(?:COM|NET|ORG)\b', token)
                or token in ('PAYMENT', 'PAYMENTS', 'PYMT', 'PMT', 'PREM', 'COLL', 'EFT', 'WEB', 'BILL', 'BILLPAY', 'PURCHASE',
                             'AUTOMATIC', 'ACH', 'CHECK', 'INSUR', 'PMTS', 'ARC', 'PHONE', 'ONLINE', 'DEBIT', 'XXSOC')):
            # A word that runs into the store number keeps its letters (EXAMPLE HEIGH1234).
            head = re.match(r'[A-Z]{3,}(?=\d)', token)
            if head and words:
                words.append(head[0])
            break
        words.append(token)
    label = _without_place(' '.join(words))
    if not re.search(r'[A-Z]{2}', label):
        return None
    span = re.search(re.escape(label).replace(r'\ ', r'\s+'), ' '.join(raw.split()), re.I)
    return (span[0] if span else label), 'statement-line-payee', 'The merchant or company printed at the start of this line, before its payment wording and references. It is not a verified legal identity; the original description remains available.'


# Charges, interest, tax the bank withholds, its currency desk, its investment
# and repo products and its own credit lines: the statement bank is the other
# side. 'Leading' wording opens the description, so a fee for a transfer stays
# the bank's even when the transfer's beneficiary is printed after it.
_BANK_LEADING = re.compile(
    r'^(?:\d+\s+|[A-Z]{1,2}\d{1,2}\s+|(?:\|\s*)+)?(?:COM(?:ISION(?:ES)?)?\b(?!\.)(?!\s+FEDERAL DE ELECTRICIDAD)|ICOMISION\b|IVA\b|I\s?V\s?A\b|IVA-|'
    r'RETENCION\b|RET\.?\s*ISR\b|I\.?S\.?R\.?\s+RETENIDO\b|ABO(?:NO)? POR INTERESES\b|AB INTERESES\b|INTERESES\b|'
    r'PAGO INTERESES DE INV|INTEREST\s+(?:PAYMENT\b(?!\s+TO\b)|(?:CHARGED?|EARNED|PAID)\b)|DIVIDEND\s*$|SERV BANCA INTERNET\b|'
    r'COBRO DE COMISION|WITHDRAWAL DEBIT CARD FEE\b|DESCUENTO POR TIMBRADO|COBRO POR TIMBRADO|COMPENSACION POR RETRASO|REEMBOLSO OTRAS COMISIONES|'
    r'(?:[A-Z&-]+\s+)?ADD-ON FEE\b|WAIVE ADD-ON FEE\b|OVERDRAFT\b(?!.*\bTRANSFER\s+FROM\b)|NON-[A-Z&]+ ATM FEE\b|ATM FEE\b|SERVICE CHARGES?\b|'
    r'MAINTENANCE FEE\b|MONTHLY (?:SERVICE )?FEE\b|AUTHORIZED USER FEE\b|LATE FEE\b|ANNUAL FEE\b|FOREIGN TRANSACTION FEE\b|'
    r'COMPRA DE DIVISAS|VENTA DE DIVISAS|RETIRO POR COMPRA DE DIVISAS|DEPOSITO POR VENTA DE DIVISAS|'
    r'COMPRA\s*DE\s*REPORTO|COMPRADE\s*REPORTO|VENTA\s*DE\s*REPORTO|I?APERTURA DE INVERSION|DEPOSITO DE INVERSION|'
    r'PAGO CAP\.? DE INVERSION|VENCIMIENTO DE INVERSION|RETIRO PAGO CREDITO|'
    r'RETIRO RETIRO DE FONDOS PARA TRANSFERENCIA :?TRASPASO A CR.DITO|DEPOSITO RECEPCION DE FONDOS POR TRANSFERENCIA :?TRASPASO DESDE CR.DITO)')
_BANK_PREFIX = r'^(?:\d+\s+|[A-Z]{1,2}\d{1,2}\s+|(?:\|\s*)+)?'
# Matched at the start of the description, after the bank's code or sequence number.
_BANK_KINDS = [
    (r'(?:COM(?:ISION(?:ES)?)?|ICOMISION|COBRO DE COMISION)\b', 'bank-charge', 'The description identifies a fee or commission charged by the statement bank; the bank name comes from the statement account.'),
    (r'(?:IVA|I\s?V\s?A\b|RETENCION|RET\.?\s*ISR|I\.?S\.?R)', 'bank-tax-withheld', 'The description identifies tax the statement bank withholds or charges on its own service; the bank pays it on to the tax authority. The bank name comes from the statement account.'),
    (r'(?:ABO(?:NO)? POR INTERESES|AB INTERESES|INTERESES|PAGO INTERESES|INTEREST|DIVIDEND)', 'bank-interest', 'The description identifies interest or dividends between the account and the statement bank; the bank name comes from the statement account.'),
    (r'.*DIVISAS', 'bank-currency-exchange', 'The description identifies a currency purchase or sale with the statement bank; the bank name comes from the statement account.'),
    (r'.*(?:REPORTO|INVERSION)', 'bank-investment', 'The description identifies an investment or repo bought from or repaid by the statement bank; the bank name comes from the statement account.'),
    (r'.*CR.DITO', 'bank-credit-line', 'The description identifies a movement to or from a credit line held with the statement bank; the bank name comes from the statement account.'),
    (r'', 'bank-charge', 'The description identifies a bank fee, charge, refund of a charge or compensation from the statement bank; the bank name comes from the statement account.'),
]


def bank_service(value):
    """(rule, explanation) when the description is a service of the statement bank itself, or None."""
    if not _BANK_LEADING.match(value):
        return None
    text = re.sub(_BANK_PREFIX, '', value)
    for pattern, rule, explanation in _BANK_KINDS:
        if re.match(pattern, text):
            return rule, explanation
    return None
