"""Why a payment shows no other side: the layouts that print no name for it.

Each reason was checked against statement pages: the line prints a cheque
number, a batch reference, a cash or card-payment wording, or nothing beyond
its type, and no name for the other side. The reason is shown in place of a
name so an empty From or To says what the statement holds rather than looking
like a missing reading. These are read-time notes; nothing stored changes and a
person's label always wins (services.financial.payment_labels).
"""
import re

NO_NAME = 'The statement doesn’t name the other side'

# (pattern on the normalised description, direction or None, account type or None, shown text, rule, explanation)
_REASONS = [
    # Card statements: a payment to the card comes from the holder's paying account, which the card statement does not print.
    (r'^(?:CAPITAL\s*ONE\s+)?(?:MOBILE|ONLINE|AUTOMATIC|AUTOPAY|ELECTRONIC|ACH)?\s*(?:PYMT|PMT|PAYMENT)(?:\b|AUTHDATE)|^(?:MOBILE )?PAYMENT\W*(?:MOBILE APP|THANK YOU)|'
     r'^ONLINE PAYMENT,? THANK YOU|^AUTOMATIC PAYMENT\b|^PAYMENT\s*$', 'credit', 'credit_card',
     'Card payment (from the holder’s bank)', 'card-payment-source',
     'A payment made to this card. The card statement does not print which bank account paid it; the payment comes from the holder’s own paying account.'),
    (r'^MOBILE PAYMENT\W*THANK YOU', None, 'credit_card',
     'Card payment (from the holder’s bank)', 'card-payment-source',
     'A payment made to this card. The card statement does not print which bank account paid it; the payment comes from the holder’s own paying account.'),
    # BBVA cash-management (BMRCASH) batch lines print the batch and a concept, never the payee or payer.
    (r'^W[O0]?\d{1,2}\s+TRASPASO A TERCEROS\b', 'debit', None,
     'BBVA batch payment — the statement doesn’t list who was paid', 'bbva-batch-payment',
     'A BBVA cash-management (BMRCASH) batch payment. The statement prints the batch reference and concept only; the payees are listed in the batch file, not on the statement.'),
    (r'^W[O0]?\d{1,2}\s+DEPOSITO DE TERCERO\b', 'credit', None,
     'BBVA batch collection — the statement doesn’t name who paid', 'bbva-batch-payment',
     'A BBVA cash-management (BMRCASH) collection. The statement prints the batch reference and concept only, not the payer.'),
    (r'^T\d{2}\s+DISPERSION\b|^BT\d\s+TRANSF\s+SP\S+\b', None, None,
     'Payroll batch — the statement doesn’t list the employees', 'payroll-batch',
     'A payroll dispersion line. The statement prints the receiving bank, batch number and payroll period only, not the employee.'),
    (r'^R[O0]\d\s+PAGO DE (?:NOMINA|AGUINALDO)\b|^[T1]16\s+PAGO DE NOMINA\b|^CARGO PAGO NOMINA POR APLICAR\b|^(?:\d+\s+)?CARGO TRANSFERENCIA ENLACE NOMINA\b', 'debit', None,
     'Payroll batch — the statement doesn’t list the employees', 'payroll-batch',
     'A payroll batch. The name printed on it is the paying company (this account’s holder), not the employees paid.'),
    (r'^(?:\d+\s+)?CARGO TRANSFERENCIA ENLACE GTOS A COMPR', 'debit', None,
     NO_NAME, 'enlace-expense-advance',
     'An expense-advance transfer made through the bank’s business channel (Enlace). The statement prints only the concept, not the recipient.'),
    (r'^R[O0]\d\s+REEMBOLSO DE NOMINA\b', 'credit', None,
     'Payroll refund — the statement doesn’t list the employees', 'payroll-batch',
     'Part of a payroll batch returned to the account. The name printed on it is the paying company (this account’s holder), not the employees.'),
    (r'^(?:BUS ONLINE )?ACH SETTLEMENT$', 'debit', None,
     'ACH batch — the statement doesn’t list who was paid', 'ach-batch',
     'A batch of ACH payments sent by the business. The statement prints the batch total only, not the individual payees.'),
    (r'^(?:\d+\s+-\s+)?\d+\s+(?:[A-Z0-9]+\s+){0,2}(?:AV|AVE|ST|RD|BLVD|DR|PKWY|HWY|PL|WAY|LN|CT)\b|^\d+\s+-\s+\d+\s', 'debit', 'credit_card',
     'Card purchase — the line prints only the store’s address', 'card-address-only',
     'The card line prints the terminal number and street address of the store, not a merchant name.'),
    # International payments: the statement prints the order and its reference, not the beneficiary.
    (r'^E\d{2}\s+ORDEN DE PAGO EXTRANJERO\b', None, None,
     'International transfer — the statement doesn’t name the other side', 'foreign-payment-order',
     'An international payment order. The statement prints the amount, currency and reference only.'),
    # Cheques: the statement lists the cheque number; the payee is only on the cheque itself.
    (r'^(?:\|\s*)?(?:CHECK(?: NUMBER)?|CHEQUE|CHQ)\s*#?\s*\d+$|^\*?\s*\d{3,5}$', 'debit', None,
     'Cheque — the statement lists only the cheque number', 'cheque-number-only',
     'A cheque listed by its number. The statement line does not print the payee; where the statement includes cheque images, the payee is on the image.'),
    (r'^[A-Z]\d{2}\s+DEPOSITO CHEQUE\b|^C\d{2}\s+DEP\.?\s*CHEQUES\b|^(?:\d+\s+)?DEPOSITO SALVO BUEN COBRO\b|^DEPOSIT BY CHECK\b|'
     r'^DEPOSIT SHARED BRANCH\b.*\bMOBILE DEPOSIT\b|^DEPOSIT MOBILE BANKING$|^(?:\|\s*)?MOBILE DEPOSIT\b', 'credit', None,
     'Cheque deposit — the statement doesn’t name who wrote the cheque', 'cheque-deposit',
     'A cheque paid into the account. The statement does not print the drawer of the cheque.'),
    (r'^[A-Z]\d{2}\s+DEP POR CAN DE DOCUMENTO\b', 'credit', None,
     'Cancelled cashier’s cheque returned to the account', 'cancelled-cashier-cheque',
     'The bank cancelled a cashier’s cheque and returned its amount to this account; no other party is involved.'),
    (r'^(?:\d+\s+)?(?:VTA CHQ CAJ|VENTA CHEQUE)\b', 'debit', None,
     'Cashier’s cheque — the statement doesn’t name the payee', 'cashier-cheque',
     'A cashier’s cheque bought from the bank. The statement does not print who it is payable to.'),
    # Cash.
    (r'^(?:[A-Z]{1,2}\d{1,2}\s+|\d+\s+)?DEPOSITO (?:EN )?EFECTIVO\b', 'credit', None,
     'Cash deposit — the statement doesn’t name who paid it in', 'cash-deposit',
     'Cash paid into the account. The statement does not print who deposited it.'),
    (r'^TRUIST ATM (?:MIXED |CASH )?DEPOSIT\b|^(?:\|\s*)?ATM (?:CASH )?DEPOSIT\b', 'credit', None,
     'Cash deposit — the statement doesn’t name who paid it in', 'cash-deposit',
     'Cash paid into the account at an ATM. The statement prints the ATM or branch, not who deposited it.'),
    (r'^WITHDRAWAL (?:AT ATM|BY CASH)\b|^ATM WITHDRAWAL\b|^(?:\|\s*)?ATM CASH\b|^TRUIST ATM (?:CASH )?WITHDRAWAL\b|^(?:\d+\s+)?RETIRO (?:DE )?EFECTIVO\b|^CASH WITHDRAWAL\b', 'debit', None,
     'Cash withdrawal — no other party', 'cash-withdrawal',
     'Cash taken out of the account. There is no other party; the ATM or branch printed is where the cash was taken.'),
    # Insurance premiums and receipts the bank collects, printed with the policy or receipt reference only.
    (r'^G30\s+(?:RECIBO NO\b|CARGO POR PRIMA DE SEGURO\b)|^(?:\d+\s+)?COB(?:RO)? PRIMA (?:DE )?SEGU', 'debit', None,
     NO_NAME, 'bank-collected-premium',
     'An insurance premium or receipt collected by the bank. The statement prints only the policy or receipt reference, not the insurer.'),
    (r'^(?:\d+\s+)?APORT LINEA CAPTURA\b', 'debit', None,
     'Government payment by capture line — the statement doesn’t name the authority', 'capture-line-payment',
     'A payment made with a capture line (línea de captura), the reference used for federal tax and social-security payments. The statement prints the line number only, not which authority was paid.'),
    (r'^N\d{2}\s+DEVOLUCION NC MULTIPAGOS\b', 'credit', None,
     'Refund of a bill payment — the statement doesn’t name the payee', 'returned-transfer',
     'A bill payment (CIE) came back. This line prints the refund wording only, not the payee.'),
    # Returned transfers whose original beneficiary is not printed.
    (r'^\S{1,3}\s+(?:SP\S+|TEF)\s+DEVUELTO', 'credit', None,
     'Returned transfer — the statement doesn’t name who it was sent to', 'returned-transfer',
     'An earlier transfer came back. This line prints the returning bank only, not the original beneficiary.'),
    # BBVA transfer lines saved without a name line. BBVA prints the other side's name as the last line of a
    # transfer when it has one; many entries print only the bank and concept.
    (r'^\S{1,4}\s+(?:SP\S{1,3}|TEF)\s+(?:ENVIADO|RECIBIDO)', None, None,
     'No name on this transfer line', 'bbva-transfer-no-name',
     'This BBVA transfer, as saved, holds the bank and concept but no name for the other side. Many BBVA entries print no '
     'name; where an entry runs onto the next page, its last line (the name) is on that page.'),
    # Brokerage contract cash movements (Intercam Casa de Bolsa, Kapital): folio and type only.
    (r'^\d+\s+(?:RETIRO|DEPOSITO|CARGO)\s+0\s+0\s+1\.0+\b', None, None,
     'Brokerage cash movement — the statement doesn’t name the other account', 'brokerage-cash-movement',
     'Cash paid into or out of the brokerage contract. The statement prints the folio and the movement type only.'),
    # Generic movements that print only their type.
    (r'^(?:\d+\s+)?(?:I?ABONO|CARGO)(?: A CUENTA(?: DE CHEQUES)?)?(?:\s*\|\s*\S+)?$|^(?:I?ABONO|CARGO)\s+\d+$|^ABONO TRANSFER GB\d+\b|^AUTOMATIC PAYMENT$|^AB TRANSF SPEI\b(?!.*\b(?:DE|DEL) CLIENTE\b)|^DEPOSIT$|^DEPOSIT\s*-?\s*$|^WITHDRAWAL MOBILE BANKING$|'
     r'^POR SOLICITUD DE CANCELACION$|^(?:\d+\s+)?ABONO POR TRANSFERENCIA\b(?!.*\bCLIENTE\b)', None, None,
     NO_NAME, 'type-only',
     'The statement prints only the kind of movement for this line, with no name for the other side.'),
    (r'^(?:\d+\s+)?(?:PAGO|ABONO) TRANSFERENCIA SPEI HORA \d{2}:\d{2}:\d{2}$', None, None,
     NO_NAME, 'type-only',
     'The statement prints only the transfer type and time for this line, with no name for the other side.'),
    (r'^(?:\d+\s+)?(?:CARGO|ABONO) TRANSFERENCIA ENLACE\b(?!.*\bTRANSFERENCIA A\b)', None, None,
     NO_NAME, 'type-only',
     'A transfer made through the bank’s business channel (Enlace). The statement prints only the concept, not the other account.'),
]
_REASONS = [(re.compile(pattern), direction, account_type, text, rule, explanation)
            for pattern, direction, account_type, text, rule, explanation in _REASONS]

# Some of these layouts carry a free-text concept that can hold a name. A reason is given only when the
# text after the layout's own wording holds nothing that could be a name: words beyond the layout's
# vocabulary (concepts, banks, months, references) are taken as a possible name and the reason is withheld.
# The value is how many such words in a row withhold it (1 for lines that normally print none at all).
_GUARDED = {'type-only': 2, 'enlace-expense-advance': 2, 'bbva-transfer-no-name': 2, 'returned-transfer': 2,
            'cheque-deposit': 2, 'foreign-payment-order': 1, 'cash-deposit': 1}
_LAYOUT_WORDS = frozenset('''
    PAGO PAGOS FACT FACTURA FACTURAS COT PREFAC ABONO CTA CTAS CUENTA CUENTAS TRASPASO TRANSFERENCIA TRANSF TRANSFER
    INVERSION ENTRE PROPIAS PRESTAMO GASTOS GTOS COMPROBAR COMPR COMP APORTACION CAPITAL AUMENTO NOM NOMINA QNA
    SALDO COMISION SPEI SPID TEF HORA ENVIADO RECIBIDO REF DEL LAS LOS PARA POR CON ANTICIPO FINIQUITO PENSION
    AGUINALDO VACACIONES LIQUIDACION DEVOLUCION DEVUELTO DIVISAS COMPRA VENTA INTERNET EXTRANJERO ORDEN ORDENANTE
    EFECTIVO DEPOSITO ATM BNET BET ENLACE CHEQUE CHEQUES CARGO CASH WINDOWS PRACTIC PRAC FOLIO VIATICOS VIAT
    SOBRANTE REINT INFONAVIT SOLICITUD CANCELACION MOBILE BANKING DEPOSIT WITHDRAWAL AUTOMATIC PAYMENT
    ENE FEB MAR ABR MAY JUN JUL AGO SEP SEPT OCT NOV DIC ENERO FEBRERO MARZO ABRIL MAYO JUNIO JULIO AGOSTO
    SEPTIEMBRE OCTUBRE NOVIEMBRE DICIEMBRE PRIMERA SEGUNDA
    BBVA BANCOMER SANTANDER BANAMEX CITI CITIBANAMEX MEXICO BANORTE AZTECA BANCOPPEL INTERCAM BAN HSBC BAJIO
    SCOTIABANK INBURSA KUSPIT MIFEL BANREGIO MONEX BMONEX PEIBO BANKAOOL AFIRME MULTIVA INVEX BANSI BANCREA STP
    BANJERCITO SABADELL ACTINVER BANCO BANK
'''.split())


def _may_print_a_name(text, run_needed):
    run = 0
    for token in text.split():
        word = token.strip('.,:;()/[]|*"\'')
        if len(word) >= 3 and word.isalpha() and word not in _LAYOUT_WORDS:
            run += 1
            if run >= run_needed:
                return True
        else:
            run = 0
    return False


def unnamed_reason(value, *, direction, account_type=None):
    """(shown text, rule, explanation) for a layout that prints no name for the other side, or None.

    ``value`` is the normalised description (payment_inference.normalized)."""
    from services.financial.payment_parties import strip_date_prefix
    value = strip_date_prefix(value)
    for pattern, wanted, kind, text, rule, explanation in _REASONS:
        if (wanted is None or wanted == direction) and (kind is None or kind == account_type):
            match = pattern.search(value)
            if not match:
                continue
            if rule in _GUARDED and _may_print_a_name(value[match.end():], _GUARDED[rule]):
                return None
            return text, rule, explanation
    return None
