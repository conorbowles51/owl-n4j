"""Is this PDF a bank or card statement? Answered from its printed text, cheaply.

Used only to decide whether an Evidence upload should also be read as a
statement (``auto_read``). It reads the text layer of the first pages (no OCR,
no rendering), folds it with the statement engine's own vocabulary, and asks
for the furniture every statement prints: an opening or closing balance label,
an account label, and movement columns or a period heading. A PDF without a
text layer (a scan) is not recognised; it can still be chosen for Financial.

A miss costs nothing that is not already the case (the file stays in Evidence,
as before). A false hit costs a reading and an entry under "Couldn't read" in
the review queue, so the rule is deliberately strict.
"""
import re

from services.financial import statement_engine_vocabulary as V

DETECTOR_VERSION = 'statement-text-v1'
# On (measured 2026-10-13 on live uploads, read-only; WIP-NOTES of fin/s-autostart):
# 434 of 470 text-layer statement PDFs already in Financial recognised, and 45
# of 45 sampled recognitions among PDFs never sent to Financial were statements.
# Reverse: LOUPE_FINANCIAL_AUTO_DETECT_STATEMENTS=0 (or False here).
DEFAULT_ENABLED = True
PAGES = 3
MIN_CHARS = 200
MAX_BYTES = 200 * 1024 * 1024

_PERIOD = ('STATEMENT PERIOD', 'BILLING PERIOD', 'BILLING CYCLE', 'PERIODO', 'ESTADO DE CUENTA',
           'STATEMENT DATE', 'STATEMENT CLOSING DATE', 'CLOSING DATE', 'FECHA DE CORTE')
_ACCOUNT = tuple(phrase for phrase, weight in V.ACCOUNT_LABELS if weight >= 2)


def _pattern(phrases):
    folded = sorted({V.fold(p) for p in phrases if V.fold(p)}, key=len, reverse=True)
    return re.compile(r'(?<![A-Z0-9])(?:' + '|'.join(re.escape(p) for p in folded) + r')(?![A-Z0-9])')


_BALANCE = _pattern(V.OPENING + V.CLOSING)
_ACCOUNT_RE = _pattern(_ACCOUNT)
_PERIOD_RE = _pattern(_PERIOD)
_COLUMNS = {role: _pattern(words) for role, words in V.COLUMN_WORDS.items() if role in ('credit', 'debit', 'balance')}
_TOTALS = _pattern(V.CREDIT_TOTAL + V.DEBIT_TOTAL + V.LIABILITY_EVIDENCE)
# Who issues it: a bank, card issuer or regulated institution prints one of these
# (deposit-insurance and regulator lines included). A shop's or care home's
# "account statement" prints balances and an account number but none of these.
_ISSUER = _pattern(V.INSTITUTION_WORDS + (
    'FDIC', 'MEMBER FDIC', 'N.A.', 'NATIONAL ASSOCIATION', 'CITIBANK', 'IPAB', 'CONDUSEF', 'SOFOM',
    'GRUPO FINANCIERO', 'CREDIT CARD', 'VISA', 'MASTERCARD', 'AMERICAN EXPRESS', 'NCUA'))


def classify_text(raw):
    """Features and verdict for already extracted text."""
    folded = V.fold(raw or '')
    features = dict(
        chars=len(folded),
        balance=bool(_BALANCE.search(folded)),
        account=bool(_ACCOUNT_RE.search(folded)),
        period=bool(_PERIOD_RE.search(folded)),
        columns=sum(bool(p.search(folded)) for p in _COLUMNS.values()),
        totals=bool(_TOTALS.search(folded)),
        issuer=bool(_ISSUER.search(folded)),
    )
    statement = (features['chars'] >= MIN_CHARS and features['balance'] and features['account'] and features['issuer']
                 and (features['columns'] >= 2 or (features['period'] and features['totals'])))
    return dict(statement=statement, version=DETECTOR_VERSION, **features)


def detect(path, pages=PAGES):
    """Verdict for one PDF on disk. Never raises: an unreadable file is not a statement."""
    try:
        import fitz
        if path is None or path.stat().st_size > MAX_BYTES:
            return dict(statement=False, version=DETECTOR_VERSION, reason='missing_or_too_large')
        with fitz.open(str(path)) as document:
            raw = ' '.join(document[index].get_text() for index in range(min(pages, document.page_count)))
    except Exception as error:  # noqa: BLE001 - a broken PDF is simply not recognised
        return dict(statement=False, version=DETECTOR_VERSION, reason=type(error).__name__)
    result = classify_text(raw)
    if result['chars'] < MIN_CHARS:
        result['reason'] = 'no_text_layer'
    return result
