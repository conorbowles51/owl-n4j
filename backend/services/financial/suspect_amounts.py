"""Amounts a machine read but no one should sum yet.

:mod:`services.financial.money` parses exactly or raises.  That is the right
contract for a parser and the wrong one for evidence, in both directions at
once, and this module exists to sit between them.

Both failures were measured on the two documents in hand rather than imagined.

**It accepts things silently that it should not.**  ``parse_money("1234",
"USD")`` returns $1,234.00, and passing ``strict=True`` does not change it,
because there is no separator for the parser to be strict *about*.  On a page
whose characters came out of an image, the decimal point is a few dark pixels
that a recogniser drops without leaving a mark, so the same four glyphs are
equally consistent with $12.34.  The gap between those two readings is two
orders of magnitude, and nothing in the string says which is right.  The 56-page
subpoena response in this matter is exactly such a page set: 51 of its 56 pages
are a full-page raster with a recognised text layer laid over it, in a
substituted ``Times-Roman`` rather than the document's own font.

**It refuses things it should merely doubt.**  Across the same two documents
the reader produced ``'1.912.05'`` 32 times and ``'28..40'`` 6 times.  Both
raise :class:`~services.financial.money.MoneyParseError`, and both have a
reading a person would produce without hesitating -- $1,912.05 and $28.40.  A
row dropped for being unparseable is a transaction missing from the ledger,
which is a worse outcome than a row carried forward with a question against it.

So this module never returns a bare number for a doubtful string and never
discards one either.  It returns a :class:`AmountReading`, which is either
certain -- safe to sum, safe to total, safe to search -- or carries the
candidate readings and the reason, for a person to resolve against the page
itself.  :func:`require_certain` is the door between the two, and it raises, so
that summing a doubtful figure has to be written down deliberately rather than
happening because nobody looked.

What decides certainty
----------------------

Two things, and both are measured rather than assumed.

The first is where the characters came from.  A digital text layer is what the
statement's own generator wrote: if it says ``1234`` the amount is 1234, and
there is nothing to doubt.  Recognised glyphs are a guess about an image, and
what they most easily lose is the smallest mark on the line.  So the same
string is certain from one origin and suspect from the other, and
:class:`TextOrigin` is a required argument rather than a default -- a caller
that does not know cannot be allowed to quietly mean "digital".

The second is whether more than one reading is *representable* in the currency.
``1,234`` under USD can only be a grouped thousand, because a three-place
decimal does not exist in a two-decimal currency; under KWD, which has three,
both readings are real and the choice is unavoidable.  This is why the
suspicion attached to an inferred separator depends on the currency's exponent
and not only on the shape of the string.

The two combine to bound the doubt, which matters more than it sounds.  A
separator that was read at all fixes the magnitude: a group of three sits where
it does only for the figure as printed, so ``2,753`` off a scan can only be
missing its minor digits and lies within a dollar of itself.  ``1234`` off the
same scan has nothing holding it, and its two readings are a hundred apart.
Both are doubtful and neither is summable, but they are not the same size of
problem, and a queue an analyst has to work through should not present them as
though they were.

What this module does not do
----------------------------

It does not decide which cell on a page is an amount.  Every measurement above
counted tokens that merely *look* like money, and on those terms three quarters
of them are page numbers, card fragments and dates.  The rate at which real
amount columns carry a doubtful figure is not knowable until column
identification exists, and no number for it is claimed here.

It does not rank its proposals by likelihood.  They are ordered by magnitude so
that a display is stable between runs, and that order carries no opinion: the
whole point is that the string does not say which reading is right, and a
module that pretended otherwise would produce a confident wrong answer at the
exact moment a person was relying on it.  The page is the tiebreaker, which is
why every reading is meant to be shown beside the region it was read from.

It does not repair, correct, or overwrite anything.  A proposal accepted by a
person is a recorded act belonging to the correction ledger, not something this
module can perform on its own.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Sequence

from services.financial.money import (
    AmbiguousAmountError,
    Currency,
    Money,
    MoneyError,
    MoneyParseError,
    ParsedAmount,
    get_currency,
    parse_amount,
)


class SuspectAmountError(MoneyError):
    """A doubtful reading was asked for as though it were a settled figure.

    Raised only by :func:`require_certain`.  It is deliberately loud: every
    total, every flow and every search in this subsystem runs on figures that
    have to be defensible, and the alternative to raising here is a suspect
    amount travelling into a sum with nothing to mark it.
    """


class TextOrigin(str, Enum):
    """Where a cell's characters came from, which decides what can be lost.

    There is no default.  The distinction is the whole basis on which an
    amount is called certain, and a caller that cannot say should say
    :attr:`unknown` and get the cautious treatment rather than accidentally
    get the confident one.
    """

    #: Characters the document's own generator wrote.  Exact by construction:
    #: a decimal point that is not there was never there.
    digital_text_layer = "digital_text_layer"
    #: Characters recovered from an image.  A decimal point is the smallest
    #: mark on the line and the one most easily lost without trace.
    recognised_glyphs = "recognised_glyphs"
    #: Provenance not established.  Treated exactly as :attr:`recognised_glyphs`
    #: throughout, because the two ways of being wrong are not equal: doubting
    #: a sound figure costs a person a glance at the page, while trusting an
    #: unsound one puts a hundredfold error inside a total.
    unknown = "unknown"


#: Origins whose characters may have lost a mark.  ``unknown`` is here by the
#: safe-direction argument in :class:`TextOrigin`, not because it is evidence.
FALLIBLE_ORIGINS: frozenset[TextOrigin] = frozenset(
    {TextOrigin.recognised_glyphs, TextOrigin.unknown}
)


class Suspicion(str, Enum):
    """Why a reading is not safe to sum."""

    #: Nothing to resolve.  The only member for which a figure is returned.
    none = "none"
    #: Digits with no separator of any kind, from an origin that can lose one:
    #: ``1234`` in USD, which is $1,234.00 or $12.34 with nothing in the string
    #: to say which.  The most dangerous member, and the only unbounded one --
    #: the hazard is a factor of ten to the currency's exponent.
    decimal_point_absent = "decimal_point_absent"
    #: Fewer fraction digits than the currency has, from a fallible origin,
    #: with the magnitude pinned by a separator that was read: ``65.0`` in USD,
    #: true figure in 65.00 to 65.09, and ``2,753``, true figure in 2,753.00 to
    #: 2,753.99.  A group of three sits where it does only for the printed
    #: magnitude, so unlike the member above this doubt is bounded below one
    #: major unit.
    fraction_too_short = "fraction_too_short"
    #: A separator the currency can read either as grouping or as the decimal
    #: point, both giving a representable figure: ``1,234`` in a three-decimal
    #: currency.  The only member independent of origin -- a flawless text
    #: layer is just as undecided, because what is missing is a convention the
    #: document never stated, not a mark the recogniser dropped.
    grouping_inferred = "grouping_inferred"
    #: A separator repeated where one was meant: ``28..40``.  Recognisers
    #: produce this from a speck of dirt or a doubled scan line.
    separator_repeated = "separator_repeated"
    #: Separators the parser rejected outright but which resolve under a
    #: single consistent convention: ``1.912.05``.
    separator_convention_unclear = "separator_convention_unclear"
    #: No reading could be derived at all.  Carried rather than dropped, so a
    #: row survives to be looked at instead of vanishing from the ledger.
    unreadable = "unreadable"


@dataclass(frozen=True, slots=True)
class Proposal:
    """One reading a doubtful string could bear, and how it was reached.

    ``basis`` is written to be shown to an analyst beside the page region the
    string came from.  It states the operation performed, never a likelihood.
    """

    money: Money
    basis: str


@dataclass(frozen=True, slots=True)
class AmountReading:
    """What a machine could honestly say about one amount-shaped string.

    Exactly one of two shapes.  Certain: :attr:`suspicion` is
    :attr:`Suspicion.none`, :attr:`certain` holds the figure, and
    :attr:`proposals` is empty.  Doubtful: :attr:`certain` is ``None`` and
    :attr:`proposals` holds every reading that could be derived, which may be
    none of them.  The constructor enforces this, so there is no state in
    which a figure is available without the doubt being available beside it.
    """

    raw: str
    currency: str
    origin: TextOrigin
    suspicion: Suspicion
    certain: Optional[Money]
    proposals: tuple[Proposal, ...]
    explanation: str

    def __post_init__(self) -> None:
        settled = self.suspicion is Suspicion.none
        if settled and self.certain is None:
            raise MoneyError("a certain reading must carry its figure")
        if not settled and self.certain is not None:
            raise MoneyError(
                "a suspect reading must not carry a figure; that is the whole "
                "distinction, and a caller reaching past it would be summing "
                "something no one has confirmed"
            )
        if settled and self.proposals:
            raise MoneyError("a certain reading has nothing left to propose")

    @property
    def is_certain(self) -> bool:
        return self.suspicion is Suspicion.none

    def to_json(self) -> dict:
        """A stable payload for the review queue and for exhibits.

        Key order is fixed so that a stored payload can be compared between
        runs.  ``suspicion`` comes first because a reader scanning a list of
        these is looking for the ones that need work.
        """
        payload: dict = {
            "suspicion": self.suspicion.value,
            "origin": self.origin.value,
            "raw": self.raw,
            "currency": self.currency,
        }
        if self.certain is not None:
            payload["minor_units"] = self.certain.minor_units
        if self.proposals:
            payload["proposals"] = [
                {"minor_units": p.money.minor_units, "basis": p.basis}
                for p in self.proposals
            ]
        payload["explanation"] = self.explanation
        return payload


def require_certain(reading: AmountReading) -> Money:
    """The figure, or a refusal.

    Every path that totals, nets, traces or compares amounts goes through
    here.  A suspect reading has no number to give, and the error names the
    string and the doubt so that the caller's traceback says which figure on
    which page stopped the sum rather than merely that one did.
    """
    if reading.certain is None:
        raise SuspectAmountError(
            f"{reading.raw!r} is not settled ({reading.suspicion.value}): "
            f"{reading.explanation}"
        )
    return reading.certain


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------

_REPEATED_SEPARATOR_RE = re.compile(r"([.,])\1+")


def _certain(
    text: str,
    cur: Currency,
    origin: TextOrigin,
    money: Money,
    explanation: str = "read exactly, with nothing inferred",
) -> AmountReading:
    """A reading safe to sum."""
    return AmountReading(
        raw=text,
        currency=cur.code,
        origin=origin,
        suspicion=Suspicion.none,
        certain=money,
        proposals=(),
        explanation=explanation,
    )


def _suspect(
    text: str,
    cur: Currency,
    origin: TextOrigin,
    suspicion: Suspicion,
    proposals: Sequence[Proposal],
    explanation: str,
) -> AmountReading:
    """A reading carried forward with its doubt attached."""
    return AmountReading(
        raw=text,
        currency=cur.code,
        origin=origin,
        suspicion=suspicion,
        certain=None,
        proposals=_ordered(proposals),
        explanation=explanation,
    )


def _origin_phrase(origin: TextOrigin) -> str:
    """How an explanation should describe why the characters may be wrong."""
    if origin is TextOrigin.recognised_glyphs:
        return "its characters were recovered from an image"
    return "its provenance was not established, so recognised characters cannot be ruled out"


def _reparse(text: str, currency: str) -> Optional[Money]:
    """Parse a repaired string, or ``None`` if the repair did not help."""
    parsed = _reparse_full(text, currency)
    return parsed.money if parsed is not None else None


def _reparse_full(text: str, currency: str) -> Optional[ParsedAmount]:
    """The relaxed parse, kept whole, or ``None`` when it does not resolve."""
    try:
        return parse_amount(text, currency)
    except MoneyError:
        return None


def _collapse_repeats(text: str) -> Optional[str]:
    """``28..40`` -> ``28.40``.  ``None`` when there was nothing repeated."""
    repaired = _REPEATED_SEPARATOR_RE.sub(r"\1", text)
    return repaired if repaired != text else None


def _single_convention(text: str) -> Optional[str]:
    """``1.912.05`` -> ``1912.05``: last separator divides, the rest group.

    Only attempted when one separator character appears more than once and the
    other does not appear at all, which is what makes the reading unambiguous:
    there is exactly one way to assign the roles, and both the European
    convention and a misrecognised thousands comma land on the same figure.
    """
    for separator in (".", ","):
        other = "," if separator == "." else "."
        if text.count(separator) > 1 and other not in text:
            cut = text.rfind(separator)
            return text[:cut].replace(separator, "") + "." + text[cut + 1 :]
    return None


def _fraction_digits(text: str, separator: str) -> int:
    """Digits following the last ``separator`` in ``text``."""
    cut = text.rfind(separator)
    if cut < 0:
        return 0
    return len(re.match(r"\d*", text[cut + 1 :]).group(0))


def _ordered(proposals: Sequence[Proposal]) -> tuple[Proposal, ...]:
    """By magnitude, so a display is stable.  Not a confidence ranking."""
    return tuple(sorted(proposals, key=lambda p: p.money.minor_units))


def read_amount(
    text: str,
    currency: str,
    origin: TextOrigin,
    *,
    decimal_separator: Optional[str] = None,
) -> AmountReading:
    """Read one amount-shaped string, saying plainly how far it can be trusted.

    ``origin`` is required.  ``decimal_separator``, when the document's
    convention is known, is passed through to the parser and removes the
    inference that :attr:`Suspicion.grouping_inferred` exists to report.
    """
    if not isinstance(origin, TextOrigin):
        raise MoneyError(
            f"origin must be a TextOrigin, got {type(origin).__name__}; it "
            "decides whether the figure may be summed and cannot be defaulted"
        )
    cur = get_currency(currency)
    try:
        parsed = parse_amount(
            text, cur.code, decimal_separator=decimal_separator, strict=True
        )
    except MoneyParseError as exc:
        return _doubt_the_unparseable(text, cur, origin, exc)
    return _judge(text, cur, origin, parsed)


def _judge(
    text: str, cur: Currency, origin: TextOrigin, parsed: ParsedAmount
) -> AmountReading:
    """What a string the parser resolved can be trusted to say.

    Reached from two places that leave the same question behind: the strict
    parse, and the relaxed parse of a string whose separator role the currency
    admits only one reading of.  ``'2,753'`` under USD is the second sort --
    strict refuses it because a lone separator had to be assigned a role, but
    the decimal reading would need three minor digits and USD has two, so the
    grouped reading is not a preference, it is the only figure the currency can
    hold.
    """
    money = parsed.money
    if origin not in FALLIBLE_ORIGINS or cur.exponent == 0:
        # Either the characters are exact, or the currency has no minor unit
        # and so no mark that could have gone missing.
        return _certain(text, cur, origin, money)

    if parsed.decimal_separator is None and parsed.grouping_separator is None:
        # Nothing in the string fixes where the point belonged, so the hazard
        # is the full width of the currency's exponent.  minor_units is the
        # digit string scaled by that exponent, so dividing it back down
        # recovers the other reading exactly -- the division has no remainder
        # by construction.
        shifted = Money(money.minor_units // cur.minor_units_per_major, cur.code)
        return _suspect(
            text,
            cur,
            origin,
            Suspicion.decimal_point_absent,
            [
                Proposal(money, "the digits as printed, with no point on the page"),
                Proposal(
                    shifted,
                    f"a lost point restored {cur.exponent} places from the right, "
                    "where this currency prints it",
                ),
            ],
            f"{text!r} carries no decimal point at all and {_origin_phrase(origin)}, "
            "which is what loses one; the two readings differ by a factor of "
            f"{cur.minor_units_per_major}",
        )

    digits_after = (
        _fraction_digits(text, parsed.decimal_separator)
        if parsed.decimal_separator is not None
        else 0
    )
    if digits_after < cur.exponent:
        # Short of a full fraction, but the magnitude is pinned: either a
        # decimal point was read, or grouping separators were, and a group of
        # three sits where it does only for the printed magnitude.  So the
        # figure cannot have shifted by an order of magnitude -- it can only
        # be missing its last minor digits, and those bound the doubt.
        upper = Money(
            money.minor_units + cur.minor_units_per_major // 10**digits_after - 1,
            cur.code,
        )
        return _suspect(
            text,
            cur,
            origin,
            Suspicion.fraction_too_short,
            [Proposal(money, "the fraction as printed, padded with zeroes")],
            f"{text!r} shows {digits_after} fraction digit(s) where {cur.code} "
            f"has {cur.exponent}, and {_origin_phrase(origin)}; the figure lies "
            f"between {money.format()} and {upper.format()}",
        )

    return _certain(text, cur, origin, money)


def _doubt_the_unparseable(
    text: str, cur: Currency, origin: TextOrigin, failure: MoneyParseError
) -> AmountReading:
    """Everything the strict parser rejected, sorted into doubt or silence."""
    # Ask the parser itself whether more than one reading is representable,
    # rather than reimplementing that judgement here.  When the relaxed parse
    # still refuses on ambiguity, both readings are real figures in this
    # currency and neither can be preferred: BHD has three minor digits, so
    # '1,234' is a thousand-odd dinars or one and a bit, and the string does
    # not say which.
    try:
        relaxed: Optional[ParsedAmount] = parse_amount(text, cur.code)
    except AmbiguousAmountError:
        return _both_readings(text, cur, origin, failure)
    except MoneyError:
        relaxed = None

    if relaxed is not None:
        # Exactly one reading the currency can hold.  The remaining doubt, if
        # any, is the same one a strict success leaves, so it is judged there.
        return _judge(text, cur, origin, relaxed)

    repaired = _collapse_repeats(text)
    if repaired is not None:
        money = _reparse(repaired, cur.code)
        if money is not None:
            return _suspect(
                text,
                cur,
                origin,
                Suspicion.separator_repeated,
                [Proposal(money, f"a repeated separator collapsed, giving {repaired!r}")],
                f"{text!r} repeats a separator where one was meant, which is "
                "what a speck on a scanned page produces",
            )

    single = _single_convention(text)
    if single is not None:
        money = _reparse(single, cur.code)
        if money is not None:
            return _suspect(
                text,
                cur,
                origin,
                Suspicion.separator_convention_unclear,
                [
                    Proposal(
                        money,
                        "the last separator read as the decimal point and the "
                        f"rest as grouping, giving {single!r}",
                    )
                ],
                f"{text!r} uses one separator character in both roles; there "
                "is only one way to assign them, but the parser will not "
                "assume a convention the document has not stated",
            )

    return _suspect(
        text,
        cur,
        origin,
        Suspicion.unreadable,
        [],
        f"{text!r} could not be read as an amount and no repair recovered "
        f"one: {failure}",
    )


def _both_readings(
    text: str, cur: Currency, origin: TextOrigin, failure: MoneyParseError
) -> AmountReading:
    """A separator the currency lets stand for either role, kept as both.

    This is the one doubt that does not depend on where the characters came
    from.  A perfect text layer reading ``1,234`` in a three-decimal currency
    is exactly as undecided as a scan of the same string: the ambiguity is in
    the convention the document never stated, not in the recognition.
    """
    separator = _only_separator(text)
    proposals = []
    if separator is not None:
        grouped = _reparse(text.replace(separator, ""), cur.code)
        if grouped is not None:
            proposals.append(
                Proposal(grouped, "the separator read as grouping digits")
            )
        try:
            divided = parse_amount(
                text, cur.code, decimal_separator=separator
            ).money
        except MoneyError:
            divided = None
        if divided is not None and (grouped is None or divided != grouped):
            proposals.append(
                Proposal(divided, "the separator read as the decimal point")
            )
    if not proposals:
        return _suspect(
            text,
            cur,
            origin,
            Suspicion.unreadable,
            [],
            f"{text!r} could not be read as an amount and no repair recovered "
            f"one: {failure}",
        )
    return _suspect(
        text,
        cur,
        origin,
        Suspicion.grouping_inferred,
        proposals,
        f"{text!r} has a single separator that {cur.code}, with "
        f"{cur.exponent} minor digits, can read either as grouping or as the "
        "decimal point; both are real figures and the string does not say "
        "which was meant",
    )


def _only_separator(text: str) -> Optional[str]:
    """The single ``.`` or ``,`` in ``text``, when there is exactly one."""
    found = [c for c in text if c in ".,"]
    return found[0] if len(found) == 1 else None


# ---------------------------------------------------------------------------
# Where a page's characters came from
# ---------------------------------------------------------------------------

#: Fraction of the page a raster must cover before the text over it is treated
#: as recognised rather than written.  Measured across both documents in this
#: matter: the 56-page scan reports 1.0 or more on 51 of 56 pages, while the
#: 108-page digital set reports 0.1 or less on 101 of its 108.  Nothing in
#: either document lands between 0.2 and 0.8, so the threshold sits in an empty
#: band rather than through a cluster.
FULL_PAGE_IMAGE_COVERAGE = 0.8


def page_text_origin(page) -> TextOrigin:
    """Whether this page's text was written by a generator or read off an image.

    Duck-typed against a fitz ``Page`` -- ``rect``, ``get_images``,
    ``get_image_rects``, ``get_text`` -- for the same reason the table reader
    is: so it can be exercised without a PDF.

    A page covered by a raster that also carries text is a scan with a
    recognised layer over it.  Any failure to measure returns
    :attr:`TextOrigin.unknown`, which is treated as fallible everywhere, so a
    page this cannot read costs caution rather than confidence.

    One known misreading, left in deliberately: a wholly redacted page is a
    full-page raster too, and will be called recognised.  Eleven pages of the
    digital set in this matter are exactly that.  They carry no rows, so the
    verdict reaches no figure, and narrowing the rule to exclude them would
    mean guessing at what the raster depicts.
    """
    try:
        area = float(page.rect.width) * float(page.rect.height)
        if area <= 0:
            return TextOrigin.unknown
        covered = 0.0
        for image in page.get_images(full=True):
            for rectangle in page.get_image_rects(image[0]) or ():
                covered += float(rectangle.width) * float(rectangle.height)
        if covered / area < FULL_PAGE_IMAGE_COVERAGE:
            return TextOrigin.digital_text_layer
        return (
            TextOrigin.recognised_glyphs
            if (page.get_text("text") or "").strip()
            else TextOrigin.unknown
        )
    except Exception:
        return TextOrigin.unknown
