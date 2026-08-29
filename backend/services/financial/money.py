"""Exact monetary values in integer minor units.

A monetary amount in this system is an integer count of a currency's minor
unit together with an ISO 4217 currency code. 1234 USD minor units is
$12.34. There is no float anywhere in this module and no code path that
converts through one.

The parser raises. It never returns zero for input it could not understand,
never silently rounds away precision it was given, and never guesses when a
string is genuinely ambiguous. An amount that cannot be parsed exactly is a
quarantined record upstream, not a zero in a total.

    >>> parse_money("$1,234.56", "USD")
    Money(minor_units=123456, currency='USD')
    >>> parse_money("(1.234,56)", "EUR")
    Money(minor_units=-123456, currency='EUR')
    >>> parse_money("1,234", "KWD")
    Traceback (most recent call last):
    AmbiguousAmountError: ...
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Iterable, Literal, Optional, Sequence


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class MoneyError(Exception):
    """Base class for every failure in this module."""


class UnknownCurrencyError(MoneyError):
    """The currency code is not a recognised ISO 4217 code."""


class CurrencyMismatchError(MoneyError):
    """An operation combined two different currencies, or a parsed string
    carried a currency code that contradicted the expected one."""


class MoneyParseError(MoneyError):
    """The text could not be read as a monetary amount."""


class AmbiguousAmountError(MoneyParseError):
    """The text has more than one valid reading and no hint was supplied.

    Raised rather than guessed. ``1,234`` in a three-decimal currency is
    either one thousand two hundred thirty four, or one and a bit; the
    difference is three orders of magnitude and there is no honest default.
    """


class PrecisionError(MoneyParseError):
    """The text carried more precision than the currency has minor units.

    ``10.555`` USD is rejected rather than rounded. Rounding a figure that
    came off a bank statement is a silent alteration of evidence.
    """


# ---------------------------------------------------------------------------
# ISO 4217
# ---------------------------------------------------------------------------

# Currencies whose minor unit is not 1/100. Everything else in the active and
# historical sets below has exponent 2.
_EXPONENT_0 = frozenset(
    """BIF CLP DJF GNF ISK JPY KMF KRW PYG RWF UGX UYI VND VUV
       XAF XOF XPF XDR XSU XUA XAU XAG XPT XPD""".split()
)
_EXPONENT_3 = frozenset("BHD IQD JOD KWD LYD OMR TND".split())
_EXPONENT_4 = frozenset("CLF UYW".split())

# ISO 4217 active codes.
_ACTIVE = frozenset(
    """AED AFN ALL AMD ANG AOA ARS AUD AWG AZN BAM BBD BDT BGN BHD BIF BMD
       BND BOB BOV BRL BSD BTN BWP BYN BZD CAD CDF CHE CHF CHW CLF CLP CNY
       COP COU CRC CUP CVE CZK DJF DKK DOP DZD EGP ERN ETB EUR FJD FKP GBP
       GEL GHS GIP GMD GNF GTQ GYD HKD HNL HTG HUF IDR ILS INR IQD IRR ISK
       JMD JOD JPY KES KGS KHR KMF KPW KRW KWD KYD KZT LAK LBP LKR LRD LSL
       LYD MAD MDL MGA MKD MMK MNT MOP MRU MUR MVR MWK MXN MXV MYR MZN NAD
       NGN NIO NOK NPR NZD OMR PAB PEN PGK PHP PKR PLN PYG QAR RON RSD RUB
       RWF SAR SBD SCR SDG SEK SGD SHP SLE SOS SRD SSP STN SVC SYP SZL THB
       TJS TMT TND TOP TRY TTD TWD TZS UAH UGX USD USN UYI UYU UYW UZS VED
       VES VND VUV WST XAF XCD XCG XDR XOF XPF XSU XUA YER ZAR ZMW ZWG
       XAU XAG XPT XPD""".split()
)

# Withdrawn codes that still appear on historical statements and in older
# case material. Accepted, but flagged so that a report can say so.
_HISTORICAL = frozenset(
    """ATS BEF BYR CUC CYP DEM EEK ESP FIM FRF GRD IEP ITL LTL LUF LVL MTL
       MRO NLG PTE ROL SKK SLL STD TRL VEB VEF ZWD ZWL ZWR ZWN""".split()
)

_HISTORICAL_EXPONENT_0 = frozenset("BYR ESP GRD ITL LUF BEF PTE TRL ROL".split())


@dataclass(frozen=True, slots=True)
class Currency:
    """An ISO 4217 currency and the exponent of its minor unit."""

    code: str
    exponent: int
    is_historical: bool = False

    @property
    def minor_units_per_major(self) -> int:
        return 10**self.exponent

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.code


def get_currency(code: str) -> Currency:
    """Resolve an ISO 4217 alphabetic code.

    Raises :class:`UnknownCurrencyError` for anything not on the active or
    historical lists. Guessing an exponent for an unrecognised code would
    put the decimal point in the wrong place.
    """
    if isinstance(code, Currency):  # tolerated for convenience
        return code
    if not isinstance(code, str):
        raise UnknownCurrencyError(f"currency code must be a string, got {type(code).__name__}")
    normalised = code.strip().upper()
    if not re.fullmatch(r"[A-Z]{3}", normalised):
        raise UnknownCurrencyError(f"{code!r} is not a three-letter currency code")

    historical = normalised not in _ACTIVE
    if historical and normalised not in _HISTORICAL:
        raise UnknownCurrencyError(f"{normalised} is not a recognised ISO 4217 currency")

    if normalised in _EXPONENT_0 or normalised in _HISTORICAL_EXPONENT_0:
        exponent = 0
    elif normalised in _EXPONENT_3:
        exponent = 3
    elif normalised in _EXPONENT_4:
        exponent = 4
    else:
        exponent = 2

    return Currency(code=normalised, exponent=exponent, is_historical=historical)


# ---------------------------------------------------------------------------
# Money
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True, order=False)
class Money:
    """An exact monetary amount.

    ``minor_units`` is a signed integer count of the currency's smallest
    unit. ``currency`` is the ISO 4217 alphabetic code.

    Money may be negative: an overdrawn balance is a real thing. The ledger
    stores transaction magnitudes as positive with a separate direction, but
    that is a ledger convention, not a constraint on this type.
    """

    minor_units: int
    currency: str

    def __post_init__(self) -> None:
        if isinstance(self.minor_units, bool) or not isinstance(self.minor_units, int):
            raise MoneyError(
                f"minor_units must be an int, got {type(self.minor_units).__name__}; "
                "a float has already lost the exactness this type exists to keep"
            )
        resolved = get_currency(self.currency)
        if resolved.code != self.currency:
            object.__setattr__(self, "currency", resolved.code)

    # -- constructors ------------------------------------------------------

    @classmethod
    def from_minor_units(cls, minor_units: int, currency: str) -> "Money":
        return cls(minor_units=int(minor_units), currency=currency)

    @classmethod
    def zero(cls, currency: str) -> "Money":
        return cls(minor_units=0, currency=currency)

    @classmethod
    def from_decimal(cls, value: Decimal, currency: str) -> "Money":
        """Build from a :class:`~decimal.Decimal`.

        Raises :class:`PrecisionError` if the value carries more decimal
        places than the currency has minor units. Nothing is rounded.
        """
        if not isinstance(value, Decimal):
            raise MoneyError(
                f"from_decimal requires a Decimal, got {type(value).__name__}"
            )
        if not value.is_finite():
            raise MoneyError(f"{value} is not a finite amount")
        cur = get_currency(currency)
        scaled = value.scaleb(cur.exponent)
        rounded = scaled.to_integral_value()
        if scaled != rounded:
            raise PrecisionError(
                f"{value} has more precision than {cur.code} "
                f"(exponent {cur.exponent}); refusing to round"
            )
        return cls(minor_units=int(rounded), currency=cur.code)

    # -- conversion --------------------------------------------------------

    @property
    def currency_info(self) -> Currency:
        return get_currency(self.currency)

    def as_decimal(self) -> Decimal:
        """Exact decimal representation. Safe: Decimal is not binary float."""
        return Decimal(self.minor_units).scaleb(-self.currency_info.exponent)

    def format(self, *, with_currency: bool = True, grouping: bool = True) -> str:
        """Plain rendering, e.g. ``1,234.56 USD``. Deterministic, locale-free."""
        cur = self.currency_info
        negative = self.minor_units < 0
        digits = str(abs(self.minor_units)).rjust(cur.exponent + 1, "0")
        if cur.exponent:
            whole, frac = digits[: -cur.exponent], digits[-cur.exponent :]
        else:
            whole, frac = digits, ""
        if grouping:
            whole = f"{int(whole):,}"
        text = whole + (f".{frac}" if frac else "")
        if negative:
            text = "-" + text
        return f"{text} {cur.code}" if with_currency else text

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.format()

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return f"Money(minor_units={self.minor_units}, currency={self.currency!r})"

    # -- predicates --------------------------------------------------------

    @property
    def is_zero(self) -> bool:
        return self.minor_units == 0

    @property
    def is_negative(self) -> bool:
        return self.minor_units < 0

    @property
    def is_positive(self) -> bool:
        return self.minor_units > 0

    # -- arithmetic --------------------------------------------------------

    def _require_same_currency(self, other: "Money") -> None:
        if not isinstance(other, Money):
            raise MoneyError(
                f"cannot combine Money with {type(other).__name__}"
            )
        if other.currency != self.currency:
            raise CurrencyMismatchError(
                f"cannot combine {self.currency} with {other.currency}; "
                "conversion is an analytical act and must be recorded, not implied"
            )

    def __add__(self, other: "Money") -> "Money":
        self._require_same_currency(other)
        return Money(self.minor_units + other.minor_units, self.currency)

    def __sub__(self, other: "Money") -> "Money":
        self._require_same_currency(other)
        return Money(self.minor_units - other.minor_units, self.currency)

    def __neg__(self) -> "Money":
        return Money(-self.minor_units, self.currency)

    def __abs__(self) -> "Money":
        return Money(abs(self.minor_units), self.currency)

    def __mul__(self, factor: int) -> "Money":
        if isinstance(factor, bool) or not isinstance(factor, int):
            raise MoneyError(
                "Money may only be multiplied by an int; scaling by a fraction "
                "requires an explicit rounding policy, so use allocate()"
            )
        return Money(self.minor_units * factor, self.currency)

    __rmul__ = __mul__

    def allocate(self, weights: Sequence[int]) -> list["Money"]:
        """Split this amount across ``weights`` losing nothing.

        Uses largest-remainder distribution, so the parts always sum exactly
        back to the original. Pro rata tracing depends on this: a split that
        loses a penny is a split that will not reconcile.
        """
        if not weights:
            raise MoneyError("allocate requires at least one weight")
        if any(isinstance(w, bool) or not isinstance(w, int) or w < 0 for w in weights):
            raise MoneyError("allocation weights must be non-negative ints")
        total_weight = sum(weights)
        if total_weight == 0:
            raise MoneyError("allocation weights must not sum to zero")

        sign = -1 if self.minor_units < 0 else 1
        magnitude = abs(self.minor_units)

        shares = [magnitude * w // total_weight for w in weights]
        remainder = magnitude - sum(shares)
        # Distribute the remainder to the largest fractional parts, breaking
        # ties by original index so the result is deterministic.
        fractions = [
            (magnitude * w % total_weight, -index) for index, w in enumerate(weights)
        ]
        order = sorted(range(len(weights)), key=lambda i: fractions[i], reverse=True)
        for i in range(remainder):
            shares[order[i]] += 1

        return [Money(sign * share, self.currency) for share in shares]

    # -- comparison --------------------------------------------------------

    def __lt__(self, other: "Money") -> bool:
        self._require_same_currency(other)
        return self.minor_units < other.minor_units

    def __le__(self, other: "Money") -> bool:
        self._require_same_currency(other)
        return self.minor_units <= other.minor_units

    def __gt__(self, other: "Money") -> bool:
        self._require_same_currency(other)
        return self.minor_units > other.minor_units

    def __ge__(self, other: "Money") -> bool:
        self._require_same_currency(other)
        return self.minor_units >= other.minor_units


def sum_money(amounts: Iterable[Money], currency: str) -> Money:
    """Total a run of amounts. ``currency`` fixes the result for empty input."""
    cur = get_currency(currency)
    total = 0
    for index, amount in enumerate(amounts):
        if not isinstance(amount, Money):
            raise MoneyError(
                f"item {index} is {type(amount).__name__}, not Money"
            )
        if amount.currency != cur.code:
            raise CurrencyMismatchError(
                f"item {index} is {amount.currency}, expected {cur.code}"
            )
        total += amount.minor_units
    return Money(total, cur.code)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

# Space characters used as digit-group separators in the wild.
_GROUP_SPACES = "\u00a0\u2007\u202f\u2009\u200a\u2008 "
# Apostrophe forms used as digit-group separators, chiefly Swiss.
_APOSTROPHES = "'\u2019\u00b4\u02bc"
# A separator only counts as grouping when it sits between two digits;
# anywhere else it is residue from stripping a symbol, code or marker.
_DIGIT_GAP_RE = re.compile(
    rf"(?<=[0-9])([{re.escape(_GROUP_SPACES + _APOSTROPHES)}])(?=[0-9])"
)
_GAP_SENTINEL = "\x00"
# Every dash-like character seen standing in for a minus sign.
_MINUS_CHARS = "-\u2212\u2013\u2014\ufe63\uff0d"

_CURRENCY_SYMBOLS = (
    "R$",
    "NT$",
    "HK$",
    "US$",
    "C$",
    "A$",
    "S$",
    "NZ$",
    "kr",
    "zł",
    "Kč",
    "лв",
    "₼",
    "₾",
    "﷼",
    "$",
    "€",
    "£",
    "¥",
    "₹",
    "₽",
    "₩",
    "₪",
    "₦",
    "₱",
    "₫",
    "฿",
    "₴",
    "₺",
    "₡",
    "₲",
    "₸",
    "₮",
    "₭",
    "₨",
    "﴿",
    "¢",
)

_MARKER_RE = re.compile(r"(?:^|\s)(CR|DR|C|D)(?:\s|$)", re.IGNORECASE)
_CODE_RE = re.compile(r"(?:^|[^A-Za-z])([A-Za-z]{3})(?:[^A-Za-z]|$)")

DecimalSeparator = Literal[".", ","]
Marker = Literal["CR", "DR"]


@dataclass(frozen=True, slots=True)
class ParsedAmount:
    """A parsed amount together with what the parser had to do to read it.

    The provenance fields exist so that an exhibit can say how a figure on a
    page became a number in the ledger: which character was treated as the
    decimal point, whether the negative came from a minus sign or from
    accounting parentheses, whether a CR/DR marker was present and therefore
    who decided the direction.
    """

    money: Money
    decimal_separator: Optional[str]
    grouping_separator: Optional[str]
    grouping_style: Optional[str]
    negative_style: Optional[str]
    marker: Optional[str]
    stripped_symbol: Optional[str]
    stripped_code: Optional[str]
    raw: str


def parse_money(
    text: str,
    currency: str,
    *,
    decimal_separator: Optional[DecimalSeparator] = None,
    strict: bool = False,
) -> Money:
    """Parse ``text`` as an exact amount in ``currency``.

    Raises a :class:`MoneyParseError` subclass on anything it cannot read
    exactly. Never returns zero as a failure value.
    """
    return parse_amount(
        text, currency, decimal_separator=decimal_separator, strict=strict
    ).money


def parse_amount(
    text: str,
    currency: str,
    *,
    decimal_separator: Optional[DecimalSeparator] = None,
    apply_marker: bool = False,
    strict: bool = False,
) -> ParsedAmount:
    """Parse ``text``, returning the amount and how it was read.

    ``apply_marker`` controls what happens to a trailing ``CR``/``DR``.
    By default the marker is reported but not applied, because whether a
    credit is positive depends on whose books the statement is written from,
    and that is a decision for the statement parser, not for this function.
    Set it to ``True`` only where that convention is already established.

    ``strict`` concerns the one case the parser has to infer: a single
    separator with exactly three digits behind it, as in ``1,234``. Under a
    currency of two or fewer minor digits the three-place decimal reading is
    not representable, so grouping is the only valid parse and the parser
    takes it, recording ``grouping_separator`` so the assumption is visible
    on the exhibit. Under a three- or four-digit currency both readings are
    representable and it raises whatever ``strict`` says. Setting ``strict``
    makes the inferred case raise too: evidence ingestion knows the document's
    convention and should pass ``decimal_separator`` rather than let this
    function work it out, and strict turns that expectation into an error.
    """
    cur = get_currency(currency)

    if not isinstance(text, str):
        raise MoneyParseError(
            f"expected a string amount, got {type(text).__name__}"
        )
    raw = text
    work = text.strip()
    if not work:
        raise MoneyParseError("empty string is not an amount")

    if decimal_separator is not None and decimal_separator not in (".", ","):
        raise MoneyParseError(
            f"decimal_separator must be '.' or ',', got {decimal_separator!r}"
        )

    # -- credit/debit marker ------------------------------------------------
    marker: Optional[str] = None
    match = _MARKER_RE.search(work)
    if match:
        token = match.group(1).upper()
        marker = "CR" if token in ("CR", "C") else "DR"
        work = (work[: match.start(1)] + " " + work[match.end(1) :]).strip()

    # -- currency code ------------------------------------------------------
    stripped_code: Optional[str] = None
    code_match = _CODE_RE.search(work)
    if code_match:
        found = code_match.group(1).upper()
        try:
            found_currency = get_currency(found)
        except UnknownCurrencyError:
            found_currency = None
        if found_currency is not None:
            if found_currency.code != cur.code:
                raise CurrencyMismatchError(
                    f"{raw!r} carries currency {found_currency.code} "
                    f"but was parsed as {cur.code}"
                )
            stripped_code = found_currency.code
            work = (
                work[: code_match.start(1)] + " " + work[code_match.end(1) :]
            ).strip()

    # -- currency symbol ----------------------------------------------------
    stripped_symbol: Optional[str] = None
    for symbol in _CURRENCY_SYMBOLS:
        if symbol in work:
            stripped_symbol = symbol
            work = work.replace(symbol, " ").strip()
            break

    # -- sign ---------------------------------------------------------------
    negative = False
    negative_style: Optional[str] = None

    if work.startswith("(") and work.endswith(")"):
        inner = work[1:-1]
        if "(" in inner or ")" in inner:
            raise MoneyParseError(f"{raw!r} has unbalanced parentheses")
        negative = True
        negative_style = "parentheses"
        work = inner.strip()
    elif work.startswith("[") and work.endswith("]"):
        negative = True
        negative_style = "brackets"
        work = work[1:-1].strip()
    elif "(" in work or ")" in work:
        raise MoneyParseError(f"{raw!r} has unbalanced parentheses")

    minus_found = False
    while work and work[0] in _MINUS_CHARS:
        if minus_found:
            raise MoneyParseError(f"{raw!r} has more than one sign")
        minus_found = True
        negative_style = negative_style or "leading_minus"
        work = work[1:].strip()
    while work and work[-1] in _MINUS_CHARS:
        if minus_found:
            raise MoneyParseError(f"{raw!r} has more than one sign")
        minus_found = True
        negative_style = negative_style or "trailing_minus"
        work = work[:-1].strip()
    if minus_found:
        if negative:
            raise MoneyParseError(
                f"{raw!r} is negated twice, by parentheses and by a minus sign"
            )
        negative = True

    if work.startswith("+"):
        work = work[1:].strip()
        if negative:
            raise MoneyParseError(f"{raw!r} has more than one sign")

    # -- separators ---------------------------------------------------------
    # A space or apostrophe sitting between two digits is a group separator and
    # has to be validated as one; the same character anywhere else is residue
    # from stripping a symbol, code or marker and is simply dropped. Protecting
    # the between-digit occurrences before the strip is what keeps the two
    # cases apart, so "1 234 567,89" is checked while "$ 1234,89" is not.
    gap_chars = set(_DIGIT_GAP_RE.findall(work))
    if len(gap_chars) > 1:
        raise MoneyParseError(
            f"{raw!r} separates its digit groups with more than one character: "
            + ", ".join(repr(c) for c in sorted(gap_chars))
        )
    whitespace_grouping: Optional[str] = gap_chars.pop() if gap_chars else None

    if whitespace_grouping is not None:
        work = _DIGIT_GAP_RE.sub(_GAP_SENTINEL, work)
    for residue in _GROUP_SPACES + _APOSTROPHES:
        work = work.replace(residue, "")
    if whitespace_grouping is not None:
        work = work.replace(_GAP_SENTINEL, whitespace_grouping)

    if not work:
        raise MoneyParseError(f"{raw!r} has no digits")
    allowed = ".," + (whitespace_grouping or "")
    if not re.fullmatch(rf"[0-9{re.escape(allowed)}]+", work):
        offenders = sorted({c for c in work if not c.isdigit() and c not in allowed})
        raise MoneyParseError(
            f"{raw!r} contains characters that are not part of a number: "
            + ", ".join(repr(c) for c in offenders)
        )
    if not any(c.isdigit() for c in work):
        raise MoneyParseError(f"{raw!r} has no digits")

    dot_count = work.count(".")
    comma_count = work.count(",")

    grouping_separator: Optional[str] = None
    resolved_decimal: Optional[str] = None

    if whitespace_grouping is not None:
        # The space or apostrophe has already declared itself the grouping
        # character, so whatever dot or comma remains can only be the decimal
        # point. Two different candidates left over means the string is not a
        # convention we recognise, and we would rather say so than pick one.
        grouping_separator = whitespace_grouping
        if dot_count and comma_count:
            raise MoneyParseError(
                f"{raw!r} groups its digits with {whitespace_grouping!r} and "
                "still contains both '.' and ',', so the decimal point is "
                "not determinable"
            )
        if dot_count > 1 or comma_count > 1:
            separator = "." if dot_count else ","
            raise MoneyParseError(
                f"{raw!r} has {dot_count or comma_count} {separator!r} "
                "characters where at most one decimal point is possible"
            )
        if dot_count or comma_count:
            separator = "." if dot_count else ","
            if decimal_separator is not None and decimal_separator != separator:
                raise MoneyParseError(
                    f"{raw!r} uses {separator!r} as its decimal point but "
                    f"{decimal_separator!r} was given as the expected one"
                )
            digits_after = len(work) - work.rfind(separator) - 1
            if digits_after == 0:
                raise MoneyParseError(f"{raw!r} ends with a separator")
            if digits_after > cur.exponent:
                raise PrecisionError(
                    f"{raw!r} has {digits_after} decimal digits but "
                    f"{cur.code} has {cur.exponent}; refusing to round evidence"
                )
            resolved_decimal = separator
    elif decimal_separator is not None:
        resolved_decimal = decimal_separator
        other = "," if decimal_separator == "." else "."
        if work.count(decimal_separator) > 1:
            raise MoneyParseError(
                f"{raw!r} has {work.count(decimal_separator)} decimal separators"
            )
        if work.count(decimal_separator) == 0:
            resolved_decimal = None
        if other in work:
            grouping_separator = other
    elif dot_count and comma_count:
        # The rightmost of the two is the decimal point; the other groups.
        last_dot = work.rfind(".")
        last_comma = work.rfind(",")
        if last_dot > last_comma:
            resolved_decimal, grouping_separator = ".", ","
        else:
            resolved_decimal, grouping_separator = ",", "."
        if work.count(resolved_decimal) > 1:
            raise MoneyParseError(
                f"{raw!r} has more than one {resolved_decimal!r} after the "
                f"grouping separator {grouping_separator!r}"
            )
    elif dot_count or comma_count:
        separator = "." if dot_count else ","
        count = dot_count or comma_count
        digits_after = len(work) - work.rfind(separator) - 1
        left = work[: work.find(separator)]

        if count > 1:
            grouping_separator = separator
        elif digits_after == 0:
            raise MoneyParseError(f"{raw!r} ends with a separator")
        elif digits_after == 3 and 1 <= len(left) <= 3:
            # "1,234" is either a grouped thousand or a three-place decimal.
            # Under a 0- or 2-digit currency only the grouped reading is
            # representable, but taking it silently turns a mis-scanned
            # "10.55" into "10555". Strict mode asks instead of assuming.
            if cur.exponent >= 3:
                raise AmbiguousAmountError(
                    f"{raw!r} in {cur.code} is either "
                    f"{left}{separator}{work[work.rfind(separator) + 1:]} grouped "
                    f"or a decimal with three places; {cur.code} has "
                    f"{cur.exponent} minor digits so both readings are valid. "
                    "Supply decimal_separator to resolve it."
                )
            if strict:
                raise AmbiguousAmountError(
                    f"{raw!r} has a single {separator!r} with three digits "
                    f"behind it, so the parser must infer that it groups, "
                    f"giving {left}{work[work.rfind(separator) + 1:]}. Under "
                    "strict parsing the caller is expected to supply "
                    "decimal_separator from the document rather than rely on "
                    "that inference."
                )
            grouping_separator = separator
        elif digits_after <= cur.exponent:
            resolved_decimal = separator
        else:
            raise PrecisionError(
                f"{raw!r} has {digits_after} decimal digits but {cur.code} has "
                f"{cur.exponent}; refusing to round evidence"
            )

    # -- validate grouping --------------------------------------------------
    grouping_style: Optional[str] = None
    if grouping_separator:
        integer_part = work
        if resolved_decimal:
            cut = work.rfind(resolved_decimal)
            integer_part = work[:cut]
            if grouping_separator in work[cut + 1 :]:
                raise MoneyParseError(
                    f"{raw!r} has {grouping_separator!r} after the decimal "
                    "point, where digits are not grouped"
                )
        sep = re.escape(grouping_separator)
        if re.fullmatch(rf"\d{{1,3}}(?:{sep}\d{{3}})+", integer_part):
            grouping_style = "western"
        elif re.fullmatch(rf"\d{{1,2}}(?:{sep}\d{{2}})+{sep}\d{{3}}", integer_part):
            grouping_style = "indian"
        else:
            raise MoneyParseError(
                f"{raw!r} has digit groups that are not a recognised pattern; "
                f"{integer_part!r} is not valid with {grouping_separator!r} as "
                "a grouping separator"
            )
        work = work.replace(grouping_separator, "")

    if resolved_decimal:
        work = work.replace(resolved_decimal, ".")
        if work.count(".") > 1:
            raise MoneyParseError(f"{raw!r} has more than one decimal point")

    # -- build --------------------------------------------------------------
    try:
        value = Decimal(work)
    except InvalidOperation as exc:  # pragma: no cover - guarded above
        raise MoneyParseError(f"{raw!r} is not a number") from exc

    money = Money.from_decimal(value, cur.code)
    if negative:
        money = -money

    if apply_marker and marker == "DR":
        money = -abs(money)
    elif apply_marker and marker == "CR":
        money = abs(money)

    return ParsedAmount(
        money=money,
        decimal_separator=resolved_decimal,
        grouping_separator=grouping_separator,
        grouping_style=grouping_style,
        negative_style=negative_style,
        marker=marker,
        stripped_symbol=stripped_symbol,
        stripped_code=stripped_code,
        raw=raw,
    )
