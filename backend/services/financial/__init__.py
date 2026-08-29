"""Financial forensics: exact money handling, ledger, reconciliation and tracing.

This package is the system of record for financial evidence. Its governing
principle is that arithmetic, not model confidence, decides what is admitted:
a dropped row produces no low-confidence signal, so only a balance identity
that fails to close can detect an absence.

Nothing in this package may represent a monetary value as a float.
"""

from services.financial.money import (
    AmbiguousAmountError,
    Currency,
    CurrencyMismatchError,
    Money,
    MoneyError,
    MoneyParseError,
    ParsedAmount,
    PrecisionError,
    UnknownCurrencyError,
    get_currency,
    parse_amount,
    parse_money,
    sum_money,
)

__all__ = [
    "AmbiguousAmountError",
    "Currency",
    "CurrencyMismatchError",
    "Money",
    "MoneyError",
    "MoneyParseError",
    "ParsedAmount",
    "PrecisionError",
    "UnknownCurrencyError",
    "get_currency",
    "parse_amount",
    "parse_money",
    "sum_money",
]
