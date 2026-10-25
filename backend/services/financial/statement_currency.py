"""Detect the currency of one statement from its own saved source cells."""
import re
import unicodedata

from services.financial.money import get_currency, MoneyError


_DOLLARS = {'USD', 'MXN', 'CAD', 'AUD', 'NZD', 'SGD', 'HKD', 'BBD', 'BSD', 'BMD', 'XCD', 'FJD', 'TTD', 'JMD'}
_SYMBOLS = {'€': {'EUR'}, '£': {'GBP'}, '$': _DOLLARS, '¥': {'JPY', 'CNY'}}
_PREFIXES = {'US$': 'USD', 'CA$': 'CAD', 'C$': 'CAD', 'AU$': 'AUD', 'A$': 'AUD',
             'NZ$': 'NZD', 'HK$': 'HKD', 'S$': 'SGD'}
_MARKER = r'(?:[A-Z]{3}|US\$|CA\$|C\$|AU\$|A\$|NZ\$|HK\$|S\$|[€£$¥])'
_AMOUNT = re.compile(r'^[=(+\-−\s]*(?P<marker>' + _MARKER + r')\s*[+\-−]?\s*\d[\d.,\s]*\)?$')
_SUFFIX = re.compile(r'^[+\-−(\s]*\d[\d.,\s]*\)?\s*(?P<marker>' + _MARKER + r')$')
# A marker is evidence of the currency only beside a figure printed as money: with its minor units
# (two or three decimals) or with thousands groups. A short whole number with a symbol read before it ('£12' beside a label) is not an
# amount, and on a scan the symbol itself may be a misread '$'.
_MONEY_FIGURE = re.compile(r'\d[.,]\d{2,3}(?!\d)|\d(?:[.,\s]\d{3})+(?!\d)')
_LABEL = re.compile(r'^(?:(?:(?:statement|account)\s+)?currency|moneda)\s*:?\s*(.*)$', re.I)
_CURRENCY_NAMES = {'EURO': 'EUR', 'EUROS': 'EUR', 'PESOS MEXICANOS': 'MXN',
    'DOLARES AMERICANOS': 'USD', 'DOLARES ESTADOUNIDENSES': 'USD', 'US DOLLARS': 'USD',
    'U.S. DOLLARS': 'USD', 'MEXICAN PESOS': 'MXN'}
_US_LAYOUTS = {'capital-one-card', 'merrick-card', 'credit-one-card', 'citi-card', 'andrews-share-statement'}


def _code(text):
    try:
        get_currency(text)
        return text
    except MoneyError:
        return ''


def detect_statement_currency(sources, *, layout_id=None, header_text=''):
    """Prefer labelled currency; otherwise use monetary cells and issuer context.

    Unqualified dollars and yen are ambiguous. Foreign-currency amounts in a
    description or an advertisement do not override a labelled account currency.
    Callers scope sources to an account/period before invoking this function.
    """
    rows = [[c['expected_text'].strip() for c in row['cells']]
            for source in sources for row in source['rows']]
    rows.extend([[line.strip()] for line in header_text.splitlines()])
    mexican_issuer = layout_id in ('bbva-mexico-cash-management', 'scotiabank-mexico-zero-activity', 'scotiabank-mexico-movements') or any(
        re.search(r'BBVA (?:MEXICO|BANCOMER),? S\.?A\.?|\b(?:BANCO KAPITAL|SERVICIO EMPRESARIAL FX KAPITAL)\b', ' '.join(cells), re.I) for cells in rows)
    labelled_rows = rows
    if layout_id == 'bbva-mexico-cash-management' or (mexican_issuer and any(
            any(c.startswith('CASH MANAGEMENT ') for c in cells) for cells in rows)):
        # BBVA prints the account currency beside Información Financiera.
        # Its glossary also defines "Moneda nacional": that definition is
        # not a second account currency and must not suppress a USD reading.
        def normal(value):
            return ''.join(c for c in unicodedata.normalize('NFKD', value.upper()) if not unicodedata.combining(c))
        financial_rows = [cells for cells in rows if any(normal(c) == 'INFORMACION FINANCIERA' for c in cells)]
        if financial_rows:
            labelled_rows = financial_rows
    labelled = set()
    for cells in labelled_rows:
        joined = ' '.join(cells)
        for candidate in [joined, *cells]:
            match = _LABEL.fullmatch(candidate)
            value = match[1].strip().upper() if match else ''
            value = ''.join(c for c in unicodedata.normalize('NFKD', value) if not unicodedata.combining(c))
            value = ' '.join(value.split())
            if mexican_issuer:
                value = {'PESOS': 'MXN', 'MONEDA NACIONAL': 'MXN', 'NACIONAL': 'MXN',
                    'M.N.': 'MXN', 'MN': 'MXN', 'M. N.': 'MXN', 'DOLAR': 'USD', 'DOLARES': 'USD'}.get(value, value)
            if match and (code := _code(_CURRENCY_NAMES.get(value, value))):
                labelled.add(code)
    if len(labelled) == 1:
        return next(iter(labelled))
    if labelled:
        return ''
    candidates = []
    for cells in rows:
        for value in cells:
            match = _AMOUNT.fullmatch(value) or _SUFFIX.fullmatch(value)
            if not match or not _MONEY_FIGURE.search(value):
                continue
            marker = match['marker']
            if marker in _SYMBOLS:
                possible = _SYMBOLS[marker]
                if marker == '$' and layout_id in _US_LAYOUTS:
                    possible = {'USD'}
                candidates.append(possible)
            elif marker in _PREFIXES:
                candidates.append({_PREFIXES[marker]})
            elif code := _code(marker):
                candidates.append({code})
    # Andrews' US share layout prints bare amounts. Its verified institution,
    # account and period establish USD when no currency evidence conflicts.
    # Explicit printed currency and monetary markers above still take priority.
    if not candidates and layout_id == 'andrews-share-statement':
        return 'USD'
    supported = set.intersection(*candidates) if candidates else set()
    return next(iter(supported)) if len(supported) == 1 else ''


def currencies_by_statement(choices, sources):
    by_address = {(s['page_number'], s['table_index']): s for s in sources}
    return [{**choice, 'currency': choice['currency'] if (choice.get('currency_source') == 'printed_account_section'
        or choice.get('layout_id') == 'generic' and choice.get('currency_source') in ('dollar_us_address', 'library_profile',
                                                                                      'printed_statement_currency',
                                                                                      'printed_holdings_currency'))
        and choice.get('layout_id') in ('monex-mexico-currency-summary', 'kapital-mexico-product-statement', 'intercam-mexico-product-statement', 'santander-mexico-movements', 'generic')
        else detect_statement_currency(
        [by_address[(s['page_number'], s['table_index'])] for s in choice['sources']],
        layout_id=choice.get('layout_id'))} if not choice.get('document_kind') else choice
        for choice in choices]


# Codes a holdings table's currency column was measured to print (r13: Mexican brokerage statements). A
# short list on purpose: a column of instrument data also holds three-letter words ('CUP', 'ALL').
_HOLDINGS_CODES = frozenset({'MXN', 'USD', 'EUR', 'CAD', 'GBP', 'JPY', 'CHF'})
_HOLDINGS_HEADING = re.compile(r'\bEMISORA\b.*\b(?:MON|MONEDA|DIVISA)\b|\b(?:MON|MONEDA|DIVISA)\b.*\bEMISORA\b')
_HOLDINGS_CODE = re.compile(r'(?<![A-Z/])(' + '|'.join(sorted(_HOLDINGS_CODES)) + r')(?![A-Z/])')


def printed_holdings_currency(sources):
    """The one currency printed in a statement's holdings currency column, with its cell, or ``None``.

    A brokerage cash ledger prints no currency, but the same statement's
    holdings table can: its heading names the instrument (``EMISORA``) and a
    currency column (``MON``), and its lines print the code as a word of its
    own (``0 MXN``; a table rule read as ``)`` is ignored). An exchange rate
    (``USD/MXN``) is not a currency of the holdings. Every such table of the
    statement must print the same one code, or nothing is returned. This is
    a proposal for a person to confirm (``field_proposals``), never the
    statement's currency by itself.
    """
    found = []
    for source in sources:
        heading = False
        for row in source['rows']:
            texts = [unicodedata.normalize('NFKD', c['expected_text']).upper() for c in row['cells']]
            if _HOLDINGS_HEADING.search(' '.join(texts)):
                heading = True
                continue
            if not heading:
                continue
            for cell, text in zip(row['cells'], texts):
                for code in _HOLDINGS_CODE.findall(text.replace(')', ' ')):
                    found.append(dict(value=code, page_number=source['page_number'], table_index=source['table_index'],
                                      row_index=row['row_index'], column_index=cell['column_index'],
                                      expected_text=cell['expected_text']))
    if not found or len({cell['value'] for cell in found}) != 1:
        return None
    return dict(found[0], basis='printed_holdings_currency', cells=len(found))


# Words that name a currency wherever a statement prints them (LOUPE_FINANCIAL_AUTOFILL_CASE_CURRENCY). Broad on
# purpose: a word read here only ever stops the case's usual currency from being assumed.
_NAMED_CODES = {'MXN': 'MXN', 'PESOS': 'MXN', 'PESO': 'MXN', 'M.N.': 'MXN', 'MN': 'MXN', 'MONEDA NACIONAL': 'MXN',
                'UDIS': 'UDI', 'UDI': 'UDI', 'USD': 'USD', 'DLLS': 'USD', 'DLL': 'USD', 'DLS': 'USD',
                'DOLAR': 'USD', 'DOLARES': 'USD', 'DOLLAR': 'USD', 'DOLLARS': 'USD', 'EUR': 'EUR', 'EURO': 'EUR',
                'EUROS': 'EUR', 'CAD': 'CAD', 'GBP': 'GBP', 'JPY': 'JPY', 'YEN': 'JPY', 'YENES': 'JPY', 'CHF': 'CHF',
                'AUD': 'AUD', 'NZD': 'NZD', 'HKD': 'HKD', 'SGD': 'SGD', 'CNY': 'CNY', 'BRL': 'BRL', 'COP': 'COP',
                'ARS': 'ARS', 'CLP': 'CLP', 'PEN': 'PEN', 'KRW': 'KRW', 'INR': 'INR'}
_NAMED = re.compile(r'(?<![A-Z.])(' + '|'.join(re.escape(w) for w in sorted(_NAMED_CODES, key=len, reverse=True))
                    + r')(?![A-Z])')
# A prefixed dollar or a symbol other than a bare '$' beside an amount, anywhere in a line of text (a symbol
# alone is not: scans read seals and stamps as '£' and '¥').
_SYMBOL_ANYWHERE = re.compile(r'(?<![A-Z])((?:US|CA|AU|NZ|HK|C|A|S|R)\$|[€£¥])\s?(?=\d[\d.,]*[.,]\d{2}(?!\d)|\d{1,3}(?:[.,]\d{3})+)')
# The deposit-insurance limit every Mexican bank prints ('HASTA ... CUATROCIENTAS MIL UDIS POR PERSONA') is a
# unit of that limit, not a currency of the statement.
_INSURANCE_LIMIT = re.compile(r'\bMIL\s+UDIS\b')
_SYMBOL_CODES = {'R$': {'BRL'}}
# An exchange rate quoted as a pair of currency codes ('FX USD/MXN 18.57' among market indicators) names no
# currency of the statement (as for the holdings above).
_PAIR = re.compile(r'(?<![A-Z])([A-Z]{3})\s*/\s*([A-Z]{3})(?![A-Z])')


def _without_rate_pairs(text):
    return _PAIR.sub(lambda m: ' ' if _code(m[1]) and _code(m[2]) else m[0], text)


def currency_marks(sources, header_text=''):
    """Every currency marker the statement prints: one sorted list of the currencies each allows.

    For the case's usual currency (field_proposals): it is assumed only when no
    marker names one currency (a bare '$' allows pesos and dollars alike, so it
    names none). Labels (one naming a currency this cannot read is '?'), money
    markers beside an amount, currency words and symbols anywhere (descriptions
    and holdings included) count; an exchange rate quoted as a pair of currency
    codes does not.
    """
    rows = [[str(c.get('expected_text') or '').strip() for c in row['cells']] for source in sources for row in source['rows']]
    rows.extend([[line.strip()] for line in header_text.splitlines()])
    marks = set()
    for cells in rows:
        for candidate in [' '.join(cells), *cells]:
            folded = ''.join(c for c in unicodedata.normalize('NFKD', candidate.upper()) if not unicodedata.combining(c))
            label = _LABEL.fullmatch(folded)
            value = ' '.join(label[1].split()) if label else ''
            if value:
                value = {'PESOS': 'MXN', 'MONEDA NACIONAL': 'MXN', 'NACIONAL': 'MXN', 'M.N.': 'MXN', 'MN': 'MXN',
                         'M. N.': 'MXN', 'DOLAR': 'USD', 'DOLARES': 'USD'}.get(value, value)
                # A label naming a currency this cannot read still names one ('?'): it blocks.
                marks.add((_code(_CURRENCY_NAMES.get(value, value)) or '?',))
            for word in _NAMED.findall(_INSURANCE_LIMIT.sub(' ', _without_rate_pairs(folded))):
                marks.add((_NAMED_CODES[word],))
            for symbol in _SYMBOL_ANYWHERE.findall(folded):
                marks.add(tuple(sorted(_SYMBOL_CODES.get(symbol) or ({_PREFIXES[symbol]} if symbol in _PREFIXES
                                                                     else _SYMBOLS.get(symbol) or {'?'}))))
            match = _AMOUNT.fullmatch(candidate.strip()) or _SUFFIX.fullmatch(candidate.strip())
            if match and _MONEY_FIGURE.search(candidate):
                marker = match['marker']
                possible = (_SYMBOLS.get(marker) or ({_PREFIXES[marker]} if marker in _PREFIXES else None)
                            or ({marker} if _code(marker) else set()))
                if possible:
                    marks.add(tuple(sorted(possible)))
    return sorted(list(mark) for mark in marks)
