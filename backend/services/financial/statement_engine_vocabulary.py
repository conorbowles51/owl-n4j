"""The general statement engine's printed vocabulary: one data table.

Harvested from the family readers (see
docs/financial-workflows/statement-engine-knowledge.md). Every entry is a
printed label or column word, English or Spanish, folded to upper case without
accents or punctuation (``fold``). No entry names an institution; issuer-only
wording belongs in a library profile (statement_engine_profiles).

A label matches only as the WHOLE text printed before its value, so
"ABONOS OBJETADOS" is never read as the credit total "ABONOS".
"""
import re
import unicodedata
from functools import lru_cache


@lru_cache(maxsize=131072)
def fold(text):
    """Upper case, accents removed, punctuation other than / . , replaced by spaces."""
    upper = ''.join(c for c in unicodedata.normalize('NFKD', text.upper()) if not unicodedata.combining(c))
    upper = re.sub(r'[^A-Z0-9/.,%#*&]+', ' ', upper)
    return ' '.join(upper.split())


def label(text):
    """A label as printed before a value: folded, trailing dots/colons and signs dropped."""
    value = fold(text).strip(' .,')
    return ' '.join(value.split())


# Opening / closing balance (D1, D2, D3). Longest phrase wins, so
# "SALDO FINAL DEL PERIODO ANTERIOR" is an opening, not a closing.
OPENING = (
    'SALDO ANTERIOR', 'SALDO INICIAL', 'SALDO FINAL DEL PERIODO ANTERIOR', 'SALDO DEL PERIODO ANTERIOR',
    'SALDO DE OPERACION INICIAL', 'SALDO DE LIQUIDACION INICIAL', 'SALDO INICIAL DEL PERIODO',
    'SALDO AL INICIO DEL PERIODO', 'SALDO MES ANTERIOR', 'SALDO INICIAL DEL PERIODO',
    'PREVIOUS BALANCE', 'OPENING BALANCE', 'BEGINNING BALANCE', 'BALANCE FORWARD', 'BALANCE BROUGHT FORWARD',
    'STARTING BALANCE', 'BEGINNING BALANCE ON', 'PREVIOUS STATEMENT BALANCE',
)
CLOSING = (
    'SALDO FINAL', 'SALDO AL CORTE', 'SALDO FINAL DEL PERIODO', 'SALDO DE OPERACION FINAL',
    'SALDO DE LIQUIDACION FINAL', 'SALDO ACTUAL', 'SALDO AL FINAL DEL PERIODO', 'SALDO VISTA',
    'NEW BALANCE', 'CLOSING BALANCE', 'ENDING BALANCE', 'ENDING BALANCE ON', 'STATEMENT BALANCE',
)
# Lines that are controls but never a period's opening or closing (D5).
SUBTOTALS = (
    'BALANCE CARRIED FORWARD', 'CARRIED FORWARD', 'BROUGHT FORWARD', 'SUBTOTAL', 'SUB TOTAL', 'SALDO PROMEDIO',
    'SALDO PROMEDIO MINIMO', 'SALDO PROMEDIO GRAVABLE', 'SALDO PROMEDIO MINIMO MENSUAL', 'AVERAGE BALANCE',
    'AVERAGE DAILY BALANCE', 'SALDO TOTAL ACUMULADO', 'SALDO DISPONIBLE', 'AVAILABLE CREDIT', 'CREDIT LIMIT',
    'MINIMUM PAYMENT DUE', 'MINIMUM PAYMENT', 'PAGO MINIMO', 'LIMITE DE CREDITO', 'CREDITO DISPONIBLE',
)
# Statement credit / debit totals with optional printed counts (D4).
CREDIT_TOTAL = (
    'DEPOSITOS', 'DEPOSITOS / ABONOS', 'DEPOSITOS ABONOS', 'ABONOS', 'TOTAL ABONOS', 'TOTAL DE ABONOS',
    'TOTAL DEPOSITOS', 'TOTAL DE DEPOSITOS', 'TOTAL DE DEPOSITOS / ABONOS', 'CREDITOS', 'TOTAL CREDITOS',
    'ENTRADAS', 'INGRESOS',
    'DEPOSITS', 'TOTAL DEPOSITS', 'DEPOSITS AND OTHER CREDITS', 'DEPOSITS AND ADDITIONS', 'TOTAL CREDITS',
    'CREDITS', 'TOTAL DEPOSITS AND OTHER CREDITS',
)
DEBIT_TOTAL = (
    'RETIROS', 'RETIROS / CARGOS', 'RETIROS CARGOS', 'CARGOS', 'TOTAL CARGOS', 'TOTAL DE CARGOS',
    'TOTAL RETIROS', 'TOTAL DE RETIROS', 'OTROS CARGOS', 'SALIDAS', 'EGRESOS',
    'WITHDRAWALS', 'TOTAL WITHDRAWALS', 'WITHDRAWALS AND OTHER DEBITS', 'WITHDRAWALS AND SUBTRACTIONS',
    'TOTAL DEBITS', 'DEBITS', 'CHECKS AND OTHER DEBITS', 'TOTAL WITHDRAWALS AND OTHER DEBITS',
)
# Totals printed under the movement columns: each amount takes its column's role (E9).
COLUMN_TOTAL = ('TOTAL', 'TOTALES', 'TOTAL DE MOVIMIENTOS', 'TOTALS', 'TOTAL MOVIMIENTOS')

# Card (amounts owed) evidence: any of these printed on the statement selects
# the liability convention (C5). Payments lower the balance, charges raise it.
LIABILITY_EVIDENCE = (
    'NEW BALANCE', 'MINIMUM PAYMENT DUE', 'MINIMUM PAYMENT', 'PAYMENT DUE DATE', 'CREDIT LIMIT',
    'AVAILABLE CREDIT', 'PAGO MINIMO', 'FECHA LIMITE DE PAGO', 'LIMITE DE CREDITO', 'CREDITO DISPONIBLE',
)
# Card account summaries print components per direction between the
# previous and the new balance (D7): their sum must equal what was read.
LIABILITY_CREDIT_COMPONENTS = ('PAYMENTS', 'OTHER CREDITS', 'CREDITS', 'PAYMENTS AND CREDITS', 'PAYMENTS AND OTHER CREDITS',
                               'PAYMENTS, CREDITS AND ADJUSTMENTS', 'PAGOS', 'PAGOS Y ABONOS', 'ABONOS')
LIABILITY_DEBIT_COMPONENTS = ('TRANSACTIONS', 'PURCHASES', 'CASH ADVANCES', 'FEES CHARGED', 'INTEREST CHARGED',
                              'FEES', 'INTEREST', 'BALANCE TRANSFERS', 'PURCHASES AND ADJUSTMENTS',
                              'PURCHASES AND OTHER CHARGES', 'CARGOS', 'COMPRAS', 'COMISIONES', 'INTERESES')

# Movement table column words (E1). A header line holds a date word and a
# money word; the words are hints for the proof, never the decision.
COLUMN_WORDS = {
    'date': ('FECHA', 'FECHAS', 'FECHA OPER', 'OPER', 'DIA', 'DATE', 'TRANS', 'TRANS DATE', 'POST', 'POST DATE',
             'POSTING DATE', 'TRANSACTION DATE', 'DATE POSTED'),
    'description': ('DESCRIPCION', 'COD DESCRIPCION', 'CONCEPTO', 'DETALLE', 'DESCRIPTION', 'DETAILS',
                    'TRANSACTION', 'TRANSACTION DESCRIPTION'),
    'credit': ('ABONOS', 'ABONO', 'DEPOSITOS', 'DEPOSITO', 'CREDITOS', 'CREDITO', 'ENTRADAS', 'INGRESOS',
               'CREDITS', 'CREDIT', 'DEPOSITS', 'DEPOSIT', 'ADDITIONS', 'MONEY IN', 'PAID IN'),
    'debit': ('CARGOS', 'CARGO', 'RETIROS', 'RETIRO', 'SALIDAS', 'EGRESOS', 'DEBITS', 'DEBIT', 'WITHDRAWALS',
              'WITHDRAWAL', 'SUBTRACTIONS', 'MONEY OUT', 'PAID OUT', 'CHARGES'),
    'balance': ('SALDO', 'SALDOS', 'BALANCE', 'RUNNING BALANCE', 'DAILY BALANCE'),
    'amount': ('IMPORTE', 'MONTO', 'AMOUNT', 'CANTIDAD'),
}

# Identity labels (A6, A8, B1, C2).
ACCOUNT_LABELS = (
    ('NO. DE CUENTA', 3), ('NO DE CUENTA', 3), ('NUMERO DE CUENTA', 3), ('NO. CUENTA', 3), ('NUM. DE CUENTA', 3),
    ('CUENTA', 2), ('ACCOUNT NUMBER', 3), ('ACCOUNT NO.', 3), ('ACCOUNT NO', 3), ('ACCOUNT #', 3), ('ACCOUNT', 2),
    ('NO. DE CONTRATO', 1), ('NUMERO DE CONTRATO', 1), ('CONTRATO', 1), ('CLABE', 0), ('CUENTA CLABE', 0),
    ('NO. CUENTA CLABE', 0),
)
HOLDER_LABELS = ('NOMBRE DEL RECEPTOR', 'TITULAR', 'NOMBRE DEL CLIENTE', 'NOMBRE DEL TITULAR', 'ACCOUNT NAME',
                 'ACCOUNT HOLDER', 'RAZON SOCIAL')
PERIOD_WORDS = ('PERIODO', 'PERIOD', 'STATEMENT PERIOD', 'BILLING PERIOD', 'BILLING CYCLE', 'CICLO', 'DEL')
CURRENCY_LABELS = ('MONEDA', 'DIVISA', 'CURRENCY', 'TIPO DE MONEDA', 'STATEMENT CURRENCY', 'ACCOUNT CURRENCY')
CURRENCY_NAMES = {
    'MONEDA NACIONAL': 'MXN', 'PESOS': 'MXN', 'PESO MEXICANO': 'MXN', 'PESOS MEXICANOS': 'MXN', 'M.N.': 'MXN',
    'MN': 'MXN', 'MXN': 'MXN', 'MXP': 'MXN',
    'DOLARES': 'USD', 'DOLAR': 'USD', 'DOLARES AMERICANOS': 'USD', 'DOLAR AMERICANO': 'USD',
    'DOLARES ESTADOUNIDENSES': 'USD', 'USD': 'USD', 'US DOLLARS': 'USD', 'U.S. DOLLARS': 'USD', 'DLS': 'USD',
    'EUROS': 'EUR', 'EURO': 'EUR', 'EUR': 'EUR', 'LIBRA ESTERLINA': 'GBP', 'GBP': 'GBP',
    'FRANCO SUIZO': 'CHF', 'CHF': 'CHF', 'DOLAR CANADIENSE': 'CAD', 'CAD': 'CAD', 'YEN JAPONES': 'JPY', 'JPY': 'JPY',
}
# Trailing or leading amount markers that are currency, not digits (C2).
AMOUNT_MARKERS = ('MN', 'M.N.', 'MXN', 'USD', 'EUR', 'DLS', 'US$', '$', '€', '£', '¥')

# Legal-name furniture of an issuer (A9): a line containing one of these.
INSTITUTION_WORDS = ('INSTITUCION DE BANCA MULTIPLE', 'BANCO', 'BANK', 'CREDIT UNION', 'BANCA', 'CASA DE BOLSA',
                     'SAVINGS', 'FINANCIAL', 'FINANCIERA')

PAGE_NUMBERING = re.compile(r'\b(?:PAGINA|PAGE|HOJA|PAG\.?)\s*(\d{1,3})\s*(?:/|DE|OF)\s*(\d{1,3})\b')
RANGE_CONNECTORS = ('AL', 'A', '-', 'TO', 'THROUGH', 'THRU', 'HASTA', 'Y')

MONTHS = {
    'ENE': 1, 'ENERO': 1, 'JAN': 1, 'JANUARY': 1,
    'FEB': 2, 'FEBRERO': 2, 'FEBRUARY': 2,
    'MAR': 3, 'MARZO': 3, 'MARCH': 3,
    'ABR': 4, 'ABRIL': 4, 'APR': 4, 'APRIL': 4,
    'MAY': 5, 'MAYO': 5,
    'JUN': 6, 'JUNIO': 6, 'JUNE': 6,
    'JUL': 7, 'JULIO': 7, 'JULY': 7,
    'AGO': 8, 'AGOSTO': 8, 'AUG': 8, 'AUGUST': 8,
    'SEP': 9, 'SEPT': 9, 'SET': 9, 'SEPTIEMBRE': 9, 'SETIEMBRE': 9, 'SEPTEMBER': 9,
    'OCT': 10, 'OCTUBRE': 10, 'OCTOBER': 10,
    'NOV': 11, 'NOVIEMBRE': 11, 'NOVEMBER': 11,
    'DIC': 12, 'DICIEMBRE': 12, 'DEC': 12, 'DECEMBER': 12,
}
# Undated card charges ordered at the period end (B6), liability convention only.
UNDATED_CHARGES = ('INTEREST CHARGE', 'INTEREST CHARGED', 'INTEREST CHARGE ON PURCHASES',
                   'INTEREST CHARGE ON CASH ADVANCES', 'LATE FEE', 'ANNUAL FEE', 'FINANCE CHARGE')


# Accent-bearing label words (F1): OCR without Spanish glyphs reads the
# accented vowel as one or two other characters (OPERACIÓN -> OPERACIEN,
# DEPÓSITOS -> DEPDSITOS). Only that position is tolerated; every other letter
# must be read exactly, so one label can never become another.
ACCENTED = ('OPERACI_N', 'LIQUIDACI_N', 'DEP_SITOS', 'DEP_SITO', 'CR_DITOS', 'CR_DITO', 'PER_ODO', 'DESCRIPCI_N',
            'L_MITE', 'M_NIMO', 'COMISI_N', 'RETENCI_N', 'D_LARES', 'D_LAR', 'N_MERO', 'TERMINACI_N', 'RAZ_N', 'CR_DITO')


def _fuzzy(phrase):
    words = phrase.split()
    pattern, fuzzy = [], False
    for word in words:
        match = next((a for a in ACCENTED if len(a) == len(word) and all(a[i] in ('_', word[i]) for i in range(len(word)))), None)
        if match:
            i = match.index('_')
            pattern.append(re.escape(word[:i]) + r'[^\s]{1,2}' + re.escape(word[i + 1:]))
            fuzzy = True
        else:
            pattern.append(re.escape(word))
    return re.compile(r'\s'.join(pattern)) if fuzzy else None


def _index(phrases):
    return {label(p) for p in phrases}


INDEX = dict(
    opening=_index(OPENING), closing=_index(CLOSING), subtotal=_index(SUBTOTALS),
    credit_total=_index(CREDIT_TOTAL), debit_total=_index(DEBIT_TOTAL), column_total=_index(COLUMN_TOTAL),
    credit_component=_index(LIABILITY_CREDIT_COMPONENTS), debit_component=_index(LIABILITY_DEBIT_COMPONENTS),
)
COLUMN_INDEX = {label(word): role for role, words in COLUMN_WORDS.items() for word in words}
FUZZY_INDEX = {role: [compiled for phrase in phrases if (compiled := _fuzzy(phrase))] for role, phrases in INDEX.items()}
