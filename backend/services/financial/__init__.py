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
from services.financial.runs import (
    IngestionRunHandle,
    RunAborted,
    RunCounts,
    RunError,
    RunScopeError,
    ingestion_run,
    open_ingestion_run,
    reap_stale_runs,
)
from services.financial.version import (
    PIPELINE_VERSION,
    code_fingerprint_detail,
    code_version,
    ruleset_version,
)

__all__ = [
    # Money
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
    # Run identity
    "IngestionRunHandle",
    "RunAborted",
    "RunCounts",
    "RunError",
    "RunScopeError",
    "ingestion_run",
    "open_ingestion_run",
    "reap_stale_runs",
    # Code and ruleset identity
    "PIPELINE_VERSION",
    "code_fingerprint_detail",
    "code_version",
    "ruleset_version",
]
