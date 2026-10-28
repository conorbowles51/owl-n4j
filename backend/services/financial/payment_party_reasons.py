"""Why a payment shows no other side: the layouts that print no name for it.

Each reason was checked against statement pages: the line prints a cheque
number, a batch reference, a cash or card-payment wording, or nothing beyond
its type, and no name for the other side. The reason is shown in place of a
name so an empty From or To says what the statement holds rather than looking
like a missing reading. These are read-time notes; nothing stored changes and a
person's label always wins (services.financial.payment_labels).

A reason never claims that no name is printed on a line that might print one.
Each layout states what may follow its own wording:

- STRICT: only the layout's vocabulary, references and numbers. Any other word
  could be a name, so the reason is withheld and the side stays unnamed.
- CITY: as STRICT, after removing a final town and state (an issuer's or
  branch's location).
- ADDRESS: an ATM or branch address. Directed wording (TO, FOR, BENEFICIARIO,
  DESTINO ..) withholds the reason.
- FIELD: layouts the bank defines with a free-text concept and no payee field
  (BBVA cash-management batches, Enlace transfers, payroll batches). Their
  reason says the statement has no payee field, which stays true whatever the
  concept text holds; the concept itself remains in the description.
"""
import re

NO_NAME = 'The statement doesn’t name the other side'
STRICT, CITY, ADDRESS, FIELD = 'strict', 'city', 'address', 'field'

_STATES = ('AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH '
           'OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY').split()
_CARD_PAYMENT = ('Card payment (from the holder’s bank)', 'card-payment-source',
                 'A payment made to this card. The card statement does not print which bank account paid it; the payment comes from the holder’s own paying account.')

# (pattern on the normalised description, direction or None, account type or None, mode, shown text, rule, explanation)
_REASONS = [
    # Card statements: a payment to the card comes from the holder's paying account, which the card statement does not print.
    (r'^(?:CAPITAL\s*ONE\s+)?(?:MOBILE|ONLINE|AUTOMATIC|AUTOPAY|ELECTRONIC|ACH|WEB)?\s*(?:PYMT|PMT|PAYMENT)(?:\b|AUTHDATE)', 'credit', 'credit_card', CITY,
     *_CARD_PAYMENT),
    (r'^MOBILE PAYMENT\b', None, 'credit_card', CITY, *_CARD_PAYMENT),
    # BBVA cash-management (BMRCASH) batch lines print the batch and the payer's concept; the payees are in the batch file.
    (r'^W[O0]?\d{1,2}\s+TRASPASO A TERCEROS\b', 'debit', None, FIELD,
     'BBVA batch payment — the statement has no payee field', 'bbva-batch-payment',
     'A BBVA cash-management (BMRCASH) batch payment. This layout prints the batch reference and the payer’s own concept, '
     'not a payee; the payees are listed in the batch file. Any words in the concept are the payer’s note and stay in the description.'),
    (r'^W[O0]?\d{1,2}\s+DEPOSITO DE TERCERO\b', 'credit', None, FIELD,
     'BBVA batch collection — the statement has no payer field', 'bbva-batch-payment',
     'A BBVA cash-management (BMRCASH) collection. This layout prints the batch reference and a concept, not the payer. '
     'Any words in the concept stay in the description.'),
    (r'^T\d{2}\s+DISPERSION\b|^BT\d\s+TRANSF\s+SP\S+\b', None, None, FIELD,
     'Payroll batch — the statement has no employee field', 'payroll-batch',
     'A payroll dispersion line. This layout prints the receiving bank, batch number and payroll period, not the employee. '
     'Any words in the concept stay in the description.'),
    (r'^R[O0]\d\s+PAGO DE (?:NOMINA|AGUINALDO)\b|^[T1]16\s+PAGO DE NOMINA\b|^CARGO PAGO NOMINA POR APLICAR\b|^(?:\d+\s+)?CARGO TRANSFERENCIA ENLACE NOMINA\b', 'debit', None, FIELD,
     'Payroll batch — the statement has no employee field', 'payroll-batch',
     'A payroll batch. The name this layout prints is the paying company (this account’s holder), not the employees paid.'),
    (r'^(?:\d+\s+)?CARGO TRANSFERENCIA ENLACE GTOS A COMPR', 'debit', None, FIELD,
     'Expense advance — the statement has no recipient field', 'enlace-expense-advance',
     'An expense-advance transfer made through the bank’s business channel (Enlace). This layout prints the payer’s concept, '
     'not a recipient field; any words in the concept stay in the description.'),
    (r'^R[O0]\d\s+REEMBOLSO DE NOMINA\b', 'credit', None, FIELD,
     'Payroll refund — the statement has no employee field', 'payroll-batch',
     'Part of a payroll batch returned to the account. The name this layout prints is the paying company (this account’s holder), not the employees.'),
    (r'^(?:\d+\s+)?(?:CARGO|ABONO) TRANSFERENCIA ENLACE\b(?!.*\bTRANSFERENCIA A\b)', None, None, FIELD,
     'Enlace transfer — the statement has no payee field', 'enlace-transfer',
     'A transfer made through the bank’s business channel (Enlace). This layout prints the payer’s concept, not the other '
     'account or its holder; any words in the concept stay in the description.'),
    (r'^(?:BUS ONLINE )?ACH SETTLEMENT$', 'debit', None, STRICT,
     'ACH batch — the statement doesn’t list who was paid', 'ach-batch',
     'A batch of ACH payments sent by the business. The statement prints the batch total only, not the individual payees.'),
    # A card line that is only a terminal number and an address, with the town and state run together.
    (r'^\d+\s+-\s+\d+\s+(?:[A-Z]{1,20}\s+)?[A-Z]{4,}(?:' + '|'.join(_STATES) + r')$', 'debit', 'credit_card', STRICT,
     'Card purchase — the line prints only the store’s address', 'card-address-only',
     'The card line prints the terminal number and street address of the store, not a merchant name.'),
    # International payments: the statement prints the order and its reference, not the beneficiary.
    (r'^E\d{2}\s+ORDEN DE PAGO EXTRANJERO\b', None, None, STRICT,
     'International transfer — the statement doesn’t name the other side', 'foreign-payment-order',
     'An international payment order. The statement prints the amount, currency and reference only.'),
    # Cheques: the statement lists the cheque number; the payee is only on the cheque itself.
    (r'^(?:\|\s*)?(?:CHECK(?: NUMBER)?|CHEQUE|CHQ)\s*#?\s*\d+$|^\*?\s*\d{3,5}$', 'debit', None, STRICT,
     'Cheque — the statement lists only the cheque number', 'cheque-number-only',
     'A cheque listed by its number. The statement line does not print the payee; where the statement includes cheque images, the payee is on the image.'),
    (r'^[A-Z]\d{2}\s+DEPOSITO CHEQUE(?:\s+(?:BBVA|BANCOMER)\b)?|^C\d{2}\s+DEP\.?\s*CHEQUES\b|^(?:\d+\s+)?DEPOSITO SALVO BUEN COBRO\b|^DEPOSIT BY CHECK\b|'
     r'^DEPOSIT MOBILE BANKING$|^(?:\|\s*)?MOBILE DEPOSIT\b', 'credit', None, STRICT,
     'Cheque deposit — the statement doesn’t name who wrote the cheque', 'cheque-deposit',
     'A cheque paid into the account. The statement does not print the drawer of the cheque.'),
    (r'^DEPOSIT SHARED BRANCH\b.*?\bMOBILE DEPOSIT\b', 'credit', None, CITY,
     'Cheque deposit — the statement doesn’t name who wrote the cheque', 'cheque-deposit',
     'A cheque paid into the account through a mobile deposit. The statement prints the branch network and place, not the drawer of the cheque.'),
    (r'^[A-Z]\d{2}\s+DEP POR CAN DE DOCUMENTO\b', 'credit', None, STRICT,
     'Cancelled cashier’s cheque returned to the account', 'cancelled-cashier-cheque',
     'The bank cancelled a cashier’s cheque and returned its amount to this account; no other party is involved.'),
    (r'^(?:\d+\s+)?(?:VTA CHQ CAJ|VENTA CHEQUE)\b', 'debit', None, STRICT,
     'Cashier’s cheque — the statement doesn’t name the payee', 'cashier-cheque',
     'A cashier’s cheque bought from the bank. The statement does not print who it is payable to.'),
    # Cash.
    (r'^(?:[A-Z]{1,2}\d{1,2}\s+|\d+\s+)?DEPOSITO (?:EN )?EFECTIVO\b', 'credit', None, STRICT,
     'Cash deposit — the statement doesn’t name who paid it in', 'cash-deposit',
     'Cash paid into the account. The statement does not print who deposited it.'),
    (r'^TRUIST ATM (?:MIXED |CASH )?DEPOSIT\b|^(?:\|\s*)?ATM (?:CASH )?DEPOSIT\b', 'credit', None, ADDRESS,
     'Cash deposit — the statement doesn’t name who paid it in', 'cash-deposit',
     'Cash paid into the account at an ATM. The statement prints the ATM or branch, not who deposited it.'),
    (r'^WITHDRAWAL (?:AT ATM|BY CASH)\b|^ATM WITHDRAWAL\b|^(?:\|\s*)?ATM CASH\b|^TRUIST ATM (?:CASH )?WITHDRAWAL\b', 'debit', None, ADDRESS,
     'Cash withdrawal — no other party', 'cash-withdrawal',
     'Cash taken out of the account at an ATM. There is no other party; the ATM printed is where the cash was taken.'),
    (r'^(?:\d+\s+)?RETIRO (?:DE )?EFECTIVO\b|^CASH WITHDRAWAL\b', 'debit', None, STRICT,
     'Cash withdrawal — no other party', 'cash-withdrawal',
     'Cash taken out of the account. The line prints no one it was paid to.'),
    # Insurance premiums and receipts the bank collects, printed with the policy or receipt reference only.
    (r'^G30\s+(?:RECIBO NO\b|CARGO POR PRIMA DE SEGURO\b)|^(?:\d+\s+)?COB(?:RO)? PRIMA (?:DE )?SEGU', 'debit', None, STRICT,
     NO_NAME, 'bank-collected-premium',
     'An insurance premium or receipt collected by the bank. The statement prints only the policy or receipt reference, not the insurer.'),
    (r'^(?:\d+\s+)?APORT LINEA CAPTURA\b', 'debit', None, STRICT,
     'Government payment by capture line — the statement doesn’t name the authority', 'capture-line-payment',
     'A payment made with a capture line (línea de captura), the reference used for federal tax and social-security payments. The statement prints the line number only, not which authority was paid.'),
    (r'^N\d{2}\s+DEVOLUCION NC MULTIPAGOS\b', 'credit', None, STRICT,
     'Refund of a bill payment — the statement doesn’t name the payee', 'returned-bill-payment',
     'A bill payment (CIE) came back. This line prints the refund wording only, not the payee.'),
    # Returned transfers whose original beneficiary is not printed.
    # The returning bank follows DEVUELTO, often run into it (DEVUELTOBANAMEX, INTERCAM BAN, BANCO NO DEF).
    (r'^\S{1,3}\s+(?:SP\S+|TEF)\s+DEVUELTO\s*(?:[A-Z]+(?:\s+(?:BAN|MEXICO|NO DEF)\b)?)?', 'credit', None, STRICT,
     'Returned transfer — the statement doesn’t name who it was sent to', 'returned-transfer',
     'An earlier transfer came back. This line prints the returning bank only, not the original beneficiary.'),
    # BBVA transfer lines saved without a name line. BBVA prints the other side's name as the last line of a
    # transfer when it has one; many entries print only the bank and concept. The bank (one word, or two
    # such as INTERCAM BAN, CITI MEXICO) is part of the layout.
    (r'^\S{1,4}\s+(?:SP\S{1,3}|TEF)\s+(?:ENVIADO|RECIBIDO)\s*(?:[A-Z]+(?:\s+(?:BAN|MEXICO)\b)?)?', None, None, STRICT,
     'No name on this transfer line', 'bbva-transfer-no-name',
     'This BBVA transfer, as saved, holds the bank, concept and references but no name for the other side. Many BBVA entries print no '
     'name; where an entry runs onto the next page, its last line (the name) is on that page.'),
    # Brokerage contract cash movements (Intercam Casa de Bolsa, Kapital): folio and type only.
    (r'^\d+\s+(?:RETIRO|DEPOSITO|CARGO)\s+0\s+0\s+1\.0+\b', None, None, STRICT,
     'Brokerage cash movement — the statement doesn’t name the other account', 'brokerage-cash-movement',
     'Cash paid into or out of the brokerage contract. The statement prints the folio and the movement type only.'),
    # Generic movements that print only their type.
    (r'^(?:\d+\s+)?(?:I?ABONO|CARGO)(?: A CUENTA(?: DE CHEQUES)?)?\b|^ABONO TRANSFER GB\d+\b|^AUTOMATIC PAYMENT\b|^AB TRANSF SPEI\b|^DEPOSIT\b|'
     r'^WITHDRAWAL MOBILE BANKING\b|^POR SOLICITUD DE CANCELACION\b|^(?:\d+\s+)?ABONO POR TRANSFERENCIA\b|^(?:\d+\s+)?(?:PAGO|ABONO) TRANSFERENCIA SPEI HORA\b', None, None, STRICT,
     NO_NAME, 'type-only',
     'The statement prints only the kind of movement for this line, with its references, and no name for the other side.'),
]
_REASONS = [(re.compile(pattern), direction, account_type, mode, text, rule, explanation)
            for pattern, direction, account_type, mode, text, rule, explanation in _REASONS]

# The words these layouts print themselves. Single letters and anything holding a digit are references.
# Bank names are not listed: a bank printed where a name could be is not taken as a layout word.
_LAYOUT_WORDS = frozenset('''
    PAGO PAGOS FACT FACTURA FACTURAS COT PREFAC ABONO CTA CTAS CUENTA CUENTAS CHEQUES TRASPASO TRANSFERENCIA TRANSF
    TRANSFER INVERSION ENTRE PROPIAS PRESTAMO GASTOS GTOS COMPROBAR COMPR COMP NOM NOMINA QNA SALDO COMISION
    SPEI SPID TEF HORA ENVIADO RECIBIDO REF DE DEL LA LAS LOS EL EN AL POR CON NO ANTICIPO FINIQUITO AGUINALDO
    VACACIONES DEVOLUCION DEVUELTO DEV CIE NC MULTIPAGOS DIVISAS INTERNET EXTRANJERO ORDEN EFECTIVO DEPOSITO ATM
    BNET BET CHEQUE CARGO CASH WINDOWS PRACTIC PRAC FOLIO SOLICITUD CANCELACION CANC CAJA CHQ CAJ OTRO BCO
    RECIBO POLIZA POL PRIMA SEGURO COB COBRO RO ROS LINEA CAPTURA APORT IMPORTE MOBILE BANKING DEPOSIT WITHDRAWAL
    AUTOMATIC PAYMENT PMT PYMT ONLINE WEB APP THANK YOU PROMO PURCHASE OFFER AUTHDATE USD EUR MXP MXN MN
    ENE FEB MAR ABR MAY JUN JUL AGO SEP SEPT OCT NOV DIC ENERO FEBRERO MARZO ABRIL MAYO JUNIO JULIO AGOSTO
    SEPTIEMBRE OCTUBRE NOVIEMBRE DICIEMBRE JAN APR AUG DEC VIDA OTRO BANCO MEXICO COMPRA VENTA RFC GUIA COTIZACION INV
'''.split())
# Letter codes printed inside references (BNET0123, REFBNTC00123): not words.
_REFERENCE_CODES = frozenset('BNET REFBNTC BMRCASH MBAN SITH CIE TEF SPEI SPID REF REFB'.split())
_DIRECTED = re.compile(r'\b(?:TO|FROM|FOR|BY|PAY|PAID|PAYEE|PARA|FAVOR|BENEFICIARIO|DESTINO|ORDENANTE|CLIENTE|NAME)\b')


# A labelled name field (BENEFICIARIO JUAN PEREZ, DEL CLIENTE ACME): a name is printed, whatever the layout.
_LABELLED = re.compile(r'\b(?:BENEF\w*|ORDENANTE|CLIENTE|A FAVOR DE|DESTINATARIO|NOMBRE|PAGO A|PARA|PAYEE|NAME|PAID TO|PAY TO|TO|FROM)\b\s*:?\s*([A-Z]{2,})')


def _labelled(text):
    """True when a name label (BENEFICIARIO, PAGO A, PARA ..) is followed by a word that is not the layout's own."""
    return any(match[1] not in _LAYOUT_WORDS for match in _LABELLED.finditer(text))


def _only_layout_words(text):
    # The bank's reference codes after Ref. mix letters and digits; before it, letters run into a number
    # (BBVA glues the concept to its 7-digit reference: 0012345BIMBO; 7ELEVEN) are still a word that could be a name.
    referenced = re.search(r'\bREF\.\s', text)
    for index, token in ((m.start(), m[0]) for m in re.finditer(r'[^\s.,:;()/\[\]|*"\'\-–—#%+=&!?·]+', text)):
        if len(token) >= 2 and token.isalpha() and token not in _LAYOUT_WORDS:
            return False
        if not token.isalpha() and not (referenced and index > referenced.start()):
            for run in re.findall(r'[A-Z]{3,}', token):
                if run not in _LAYOUT_WORDS and run not in _REFERENCE_CODES and not re.fullmatch(r'X+', run):
                    return False
    return True


def _name_like(text):
    """True when the text holds a common given name or a legal form, i.e. a person or company may be printed."""
    from services.financial.payment_parties import _GIVEN_NAMES, _LEGAL_FORM
    words = re.sub(r'[^A-Z ]', ' ', text).split()
    return any(w in _GIVEN_NAMES for w in words) or bool(re.search(r'\b(?:S\.?\s?A\.?|S\s?DE\s?R\.?\s?L|S\.?\s?C|A\.?\s?C|INC|LLC|LTD|CORP)\b\.?', text)) \
        or bool(_LEGAL_FORM.search(text))


def _without_town(text):
    """The text without a final town and state (at most two words before the state)."""
    words = text.split()
    if words and words[-1] in _STATES:
        return ' '.join(words[:max(0, len(words) - 3)])
    return text


def unnamed_reason(value, *, direction, account_type=None):
    """(shown text, rule, explanation) for a layout that prints no name for the other side, or None.

    ``value`` is the normalised description (payment_inference.normalized)."""
    from services.financial.payment_parties import strip_date_prefix
    value = strip_date_prefix(value)
    for pattern, wanted, kind, mode, text, rule, explanation in _REASONS:
        if (wanted is None or wanted == direction) and (kind is None or kind == account_type):
            match = pattern.search(value)
            if not match:
                continue
            tail = value[match.end():]
            # A labelled name field, or (outside FIELD layouts) a given name or legal form, means a name may be printed.
            if _labelled(tail) or (mode != FIELD and _name_like(tail)):
                return None
            if mode == STRICT and not _only_layout_words(tail):
                return None
            if mode == CITY and not _only_layout_words(_without_town(tail)):
                return None
            # An ATM address carries a street or terminal number; directed wording names someone.
            if mode == ADDRESS and (_DIRECTED.search(tail) or tail.strip() and not re.search(r'\d{2,}', tail)):
                return None
            return text, rule, explanation
    return None
