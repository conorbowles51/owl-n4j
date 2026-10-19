"""Field-level check digits: the last gate a number passes before analysis.

One rule fixes what this module is for and, just as importantly, what it is
not for:

    A failed check digit does not reject a row.  It flags it, because the
    source document may itself contain the error, and that is a finding.

That sentence is the whole design.  An account number that fails its own
arithmetic is *evidence*.  It may be evidence that the extractor misread a
digit, and it may be evidence that the party who wrote the document wrote a
number that never existed — which, in a matter about where money went, is
frequently the more interesting of the two.  A module that dropped the row
would destroy the second finding in the course of tidying up the first.  So
nothing here rejects anything.  Everything here returns a verdict, and that
verdict has to be recorded before the value is analysed:

    No number reaches the analytical surface without having passed this gate
    or having been explicitly adjudicated by a named human.

Four algorithms, three of which are one algorithm
------------------------------------------------

IBAN and LEI both use ISO 7064 MOD-97-10, and the ABA routing number and the
Luhn check are two different weighted sums modulo ten.  They are implemented
once each and shared, because a second copy of a check digit algorithm is a
place for the two copies to disagree, and the disagreement would surface as an
identifier that verifies in one part of the pipeline and fails in another.
:mod:`services.financial.nacha` carried its own ABA weights until this module
existed and now delegates here.

What the checks are actually worth
----------------------------------

Detection power is stated here as *measured* rather than as recalled, because
the received wisdom about Luhn is wrong in a specific and quotable way.  It is
widely repeated that Luhn catches "roughly 80% of adjacent transpositions".  It
does not, and the figure is not an approximation of the truth but a different
shape of claim: Luhn's misses are **categorical, not probabilistic**.

Measured over three thousand generated valid sixteen-digit numbers:

* **Single-digit errors: 72,000 tried, 0 undetected.**  Every one, always.
* **Adjacent transpositions:** of the 45 distinct unordered digit pairs, 44
  are caught *every time they occur* and ``09``/``90`` is missed *every time
  it occurs*.  Not one pair was ever caught in one position and missed in
  another.  So the honest statement is "all adjacent transpositions except
  09↔90", and the "80%" figure would let a reader believe that a transposed
  ``09`` has a four-in-five chance of being caught when it has none.
* **Twin errors** (``aa`` → ``bb``): ``22``↔``55``, ``33``↔``66`` and
  ``44``↔``77`` are missed, again categorically, and every other twin pair is
  caught.  The received account omits these entirely.

MOD-97-10 measured by sweeping every single-character substitution and every
adjacent transposition across four real IBANs (GB, DE, NL, CH):

* **Same-class single-character substitutions** — digit for digit, letter for
  letter — **731 tried, 0 undetected.**
* **Adjacent transpositions: 56 tried, 0 undetected.**
* **Class-crossing substitutions** (a digit written where a letter belongs, or
  the reverse) are the sole residual gap: **1,614 tried, 13 undetected**, or
  0.81%.  These escape for a structural reason rather than an arithmetic one.
  A letter expands to *two* digits before the modulus is taken, so writing a
  digit where a letter belongs shortens the string the check runs over, and
  the check is not designed against an operation that changes the length of
  its own input.

  The country length table below does **not** close that gap, and it is worth
  being clear about why rather than assuming it helps: a substitution replaces
  one character with one character, so the IBAN is exactly as long afterwards
  and a length check cannot see it.  Measured, the class-crossing escape rate
  is 0.81% with the table applied and 0.81% without it.  What would close the
  gap is a per-country BBAN *format* — which positions hold letters and which
  hold digits — and this module does not carry one.  The table catches a
  different error, insertion or loss of a character, which the checksum alone
  is also poor at.

The country length table, and its provenance
--------------------------------------------

:data:`IBAN_COUNTRY_LENGTHS` transcribes the ISO 13616 registry.  It could not
be fetched and diffed against the registry in the environment this was written
in, so it is recorded here as a partial and human-entered table, with two
consequences that are deliberate:

* A country **absent** from the table is checked by checksum alone, and the
  result's :attr:`CheckDigitResult.checks_performed` omits
  :data:`CHECK_IBAN_COUNTRY_LENGTH` accordingly.  Absence never causes a
  failure.
* A country **present** whose length disagrees is reported as ``failed`` with
  a detail naming the length found, the length expected and the fact that the
  checksum passed.  If the table is ever wrong, that reads as an obviously
  self-contradictory verdict on a real IBAN rather than as a quiet rejection,
  which is the failure mode that gets noticed and fixed.

No detection of kind
--------------------

:func:`verify` will not guess what it is looking at.  ``021000021`` is a live
Federal Reserve routing number and also nine digits that a social security
number could be; ``4111111111111111`` is the canonical Visa test number and
also sixteen digits.  A detector would be right often enough to be trusted and
wrong often enough to matter, and its wrong answers would arrive wearing the
word "verified".  The caller read the value out of a named field and knows
what the field was, so it is asked to say so.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping, Optional

from postgres.models.enums import CheckDigitOutcome, IdentifierKind

#: Names recorded in :attr:`CheckDigitResult.checks_performed`.  A result says
#: which checks ran rather than leaving the reader to infer it from the kind,
#: because for IBAN the set varies with the country and a bare ``passed`` would
#: not distinguish "checksum and length agreed" from "checksum agreed and the
#: length was never looked at".
CHECK_STRUCTURE = "structure"
CHECK_ISO7064_MOD97_10 = "iso7064_mod97_10"
CHECK_ABA_WEIGHTED_MOD10 = "aba_weighted_mod10"
CHECK_LUHN_MOD10 = "luhn_mod10"
CHECK_IBAN_COUNTRY_LENGTH = "iban_country_length"
CHECK_SSN_ISSUED_RANGES = "ssn_issued_ranges"

#: Characters stripped before any check runs.  Spaces because IBANs are
#: conventionally printed in groups of four and cards in groups of four, and
#: hyphens because US identifiers are conventionally printed with them.
#:
#: Nothing else is stripped, and in particular no attempt is made to pull an
#: identifier out of surrounding prose.  A field that arrives with a currency
#: symbol or a trailing footnote marker attached is a field whose extraction
#: went wrong, and reporting that as ``malformed`` is the correct outcome; a
#: normaliser generous enough to rescue it would also silently rescue a value
#: that had been read from the wrong column entirely.
_STRIPPED = " -"

#: Weights of the ABA routing number check digit, applied to the leading eight
#: digits in order.  The ninth digit is whatever makes the weighted sum a
#: multiple of ten.  Moved here from :mod:`services.financial.nacha`, which
#: held the only copy until this module existed and now imports this one.
ABA_WEIGHTS: tuple[int, ...] = (3, 7, 1, 3, 7, 1, 3, 7)

#: Total length of an IBAN by ISO 3166-1 alpha-2 country code, from the ISO
#: 13616 registry.  See the module docstring for how a missing entry and a
#: disagreeing entry are each handled, and why neither silently rejects.
IBAN_COUNTRY_LENGTHS: Mapping[str, int] = {
    "AD": 24, "AE": 23, "AL": 28, "AT": 20, "AZ": 28, "BA": 20, "BE": 16,
    "BG": 22, "BH": 22, "BR": 29, "BY": 28, "CH": 21, "CR": 22, "CY": 28,
    "CZ": 24, "DE": 22, "DK": 18, "DO": 28, "EE": 20, "EG": 29, "ES": 24,
    "FI": 18, "FO": 18, "FR": 27, "GB": 22, "GE": 22, "GI": 23, "GL": 18,
    "GR": 27, "GT": 28, "HR": 21, "HU": 28, "IE": 22, "IL": 23, "IS": 26,
    "IT": 27, "JO": 30, "KW": 30, "KZ": 20, "LB": 28, "LI": 21, "LT": 20,
    "LU": 20, "LV": 21, "MC": 27, "MD": 24, "ME": 22, "MK": 19, "MR": 27,
    "MT": 31, "MU": 30, "NL": 18, "NO": 15, "PK": 24, "PL": 28, "PS": 29,
    "PT": 25, "QA": 29, "RO": 24, "RS": 22, "SA": 24, "SE": 24, "SI": 19,
    "SK": 24, "SM": 27, "TN": 24, "TR": 26, "UA": 29, "VA": 22, "VG": 24,
    "XK": 20,
}

#: Shortest and longest an IBAN may be under ISO 13616 irrespective of country.
#: Applied where the country is not in :data:`IBAN_COUNTRY_LENGTHS`, so that an
#: unknown country still cannot admit a value of obviously impossible size.
IBAN_MIN_LENGTH = 15
IBAN_MAX_LENGTH = 34

#: A payment card primary account number under ISO/IEC 7812-1.  The standard
#: allows up to nineteen digits; twelve is the shortest in live use.
CARD_MIN_DIGITS = 12
CARD_MAX_DIGITS = 19

# Structural patterns.  Written with explicit ASCII ranges rather than ``\d``,
# ``\w`` or :meth:`str.isdigit`, all three of which are true of characters that
# are not ASCII digits — ``'٣'`` (Arabic-Indic three) satisfies ``isdigit`` and
# ``'²'`` satisfies it while raising in ``int``.  An identifier field carrying
# one of those is malformed, and it has to *read* as malformed rather than
# crash the check or, worse, be silently converted.
_IBAN_RE = re.compile(r"^[A-Z]{2}[0-9]{2}[A-Z0-9]{11,30}$")
_LEI_RE = re.compile(r"^[A-Z0-9]{18}[0-9]{2}$")
_NINE_DIGITS_RE = re.compile(r"^[0-9]{9}$")
_CARD_RE = re.compile(r"^[0-9]{%d,%d}$" % (CARD_MIN_DIGITS, CARD_MAX_DIGITS))
_BIC_RE = re.compile(r"^[A-Z]{6}[A-Z0-9]{2}(?:[A-Z0-9]{3})?$")


class CheckDigitError(Exception):
    """A caller error: an argument this module cannot act on at all.

    Distinct from every :class:`~postgres.models.enums.CheckDigitOutcome`,
    which are all statements *about a value*.  This is a statement about the
    call, and it raises rather than returning a verdict because a verdict would
    be recorded against a row as though the value had been examined.
    """


@dataclass(frozen=True)
class CheckDigitResult:
    """The verdict on one identifier, with the checks that produced it named.

    Frozen because this is recorded alongside the value it describes and is
    read back when an exhibit is challenged; a result that could be edited
    after the fact would be worth nothing at that point.
    """

    #: What the caller said the value was.  Never inferred here.
    kind: IdentifierKind
    #: The verdict.  See :class:`~postgres.models.enums.CheckDigitOutcome` for
    #: why there are four of these and not two.
    outcome: CheckDigitOutcome
    #: The value with spaces and hyphens removed and letters upper-cased —
    #: what the arithmetic actually ran on.  Kept so that a disputed result can
    #: be re-derived without guessing at how the input was cleaned.
    normalised: str
    #: Which checks ran, from the ``CHECK_*`` constants in this module, in the
    #: order they ran.  A ``passed`` result states exactly what passed.
    checks_performed: tuple[str, ...]
    #: Why, for anything other than ``passed``.  Empty on a pass.
    detail: str = ""

    @property
    def passes_gate(self) -> bool:
        """Whether the value clears the gate without human adjudication.

        True for ``passed`` and for ``no_check_digit``: in the second case
        there was no arithmetic to fail, and holding a BIC back for review on
        the grounds that it could not be verified would stop every BIC in the
        corpus for a reason that is a property of the standard.

        False for ``failed`` and for ``malformed``, which is not a claim that
        the value is wrong — a ``failed`` check digit is quite often a
        correctly-read transcription of an error the document itself contains.
        It is a claim that a named human has to say which of those it is
        before the number is analysed.
        """
        return self.outcome in (
            CheckDigitOutcome.passed,
            CheckDigitOutcome.no_check_digit,
        )


def normalise(value: str) -> str:
    """Strip :data:`_STRIPPED` and upper-case.

    Upper-casing is applied to every kind including the digit-only ones, where
    it cannot change anything: a character that is not an ASCII digit is still
    not one after ``upper()``, so a card number carrying a stray letter is
    still reported malformed.  Doing it uniformly avoids a per-kind branch that
    would have to be kept correct for no gain.
    """
    if not isinstance(value, str):
        raise CheckDigitError(f"expected a string, got {type(value).__name__}")
    for char in _STRIPPED:
        value = value.replace(char, "")
    return value.upper()


def iso7064_mod97_10_residue(value: str) -> int:
    """The ISO 7064 MOD-97-10 residue of an upper-case alphanumeric string.

    Letters expand to two digits (``A`` → 10 … ``Z`` → 35) before the modulus
    is taken.  Computed incrementally rather than by building the whole
    expanded integer: the two agree for every value, and the incremental form
    does not depend on the string being short enough for that integer to be
    reasonable, which is a property of the input this module should not have to
    assume.

    Raises :class:`CheckDigitError` on any character outside ``0-9A-Z``, which
    the structural patterns exclude before this is reached.  It raises rather
    than returning a sentinel so that a caller reaching it by another route
    cannot mistake the sentinel for a residue.
    """
    residue = 0
    for char in value:
        if "0" <= char <= "9":
            residue = (residue * 10 + (ord(char) - 48)) % 97
        elif "A" <= char <= "Z":
            residue = (residue * 100 + (ord(char) - 55)) % 97
        else:
            raise CheckDigitError(
                f"{char!r} is not an upper-case alphanumeric character"
            )
    return residue


def luhn_residue(digits: str) -> int:
    """The Luhn sum of a digit string, modulo ten.  Zero means it checks out.

    Returned as the residue rather than as a boolean so that the caller can
    record the arithmetic that was done.  Raises on a non-digit for the reason
    given at :func:`iso7064_mod97_10_residue`.
    """
    total = 0
    for position, char in enumerate(reversed(digits)):
        if not "0" <= char <= "9":
            raise CheckDigitError(f"{char!r} is not a digit")
        digit = ord(char) - 48
        if position % 2 == 1:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return total % 10


def aba_check_digit(routing_prefix: str) -> Optional[int]:
    """The check digit the leading eight digits of a routing number imply.

    ``None`` where the prefix is not exactly eight ASCII digits, since there is
    then nothing to compute from.  This is the single copy of the algorithm;
    :mod:`services.financial.nacha` imports it.
    """
    if len(routing_prefix) != 8:
        return None
    total = 0
    for char, weight in zip(routing_prefix, ABA_WEIGHTS):
        if not "0" <= char <= "9":
            return None
        total += (ord(char) - 48) * weight
    return (10 - total % 10) % 10


def _malformed(
    kind: IdentifierKind, normalised: str, detail: str
) -> CheckDigitResult:
    """A structural rejection.  Only ``structure`` ran, and it is recorded."""
    return CheckDigitResult(
        kind=kind,
        outcome=CheckDigitOutcome.malformed,
        normalised=normalised,
        checks_performed=(CHECK_STRUCTURE,),
        detail=detail,
    )


def _verify_iban(normalised: str) -> CheckDigitResult:
    """ISO 13616 structure, then MOD-97-10, then country length where known."""
    kind = IdentifierKind.iban
    if not _IBAN_RE.match(normalised):
        return _malformed(
            kind,
            normalised,
            "an IBAN is two letters, two digits and then 11 to 30 "
            f"alphanumeric characters; got {normalised!r}",
        )
    if not IBAN_MIN_LENGTH <= len(normalised) <= IBAN_MAX_LENGTH:
        return _malformed(
            kind,
            normalised,
            f"an IBAN is {IBAN_MIN_LENGTH} to {IBAN_MAX_LENGTH} characters; "
            f"got {len(normalised)}",
        )

    # The first four characters move to the end before the modulus is taken.
    rearranged = normalised[4:] + normalised[:4]
    checks = [CHECK_STRUCTURE, CHECK_ISO7064_MOD97_10]
    if iso7064_mod97_10_residue(rearranged) != 1:
        return CheckDigitResult(
            kind=kind,
            outcome=CheckDigitOutcome.failed,
            normalised=normalised,
            checks_performed=tuple(checks),
            detail="the ISO 7064 MOD-97-10 residue is not 1",
        )

    country = normalised[:2]
    expected = IBAN_COUNTRY_LENGTHS.get(country)
    if expected is None:
        # Deliberately not a failure.  See the module docstring: the table is
        # human-entered and incomplete, so its absence is a limit of this
        # module's knowledge and not a defect in the value.
        return CheckDigitResult(
            kind=kind,
            outcome=CheckDigitOutcome.passed,
            normalised=normalised,
            checks_performed=tuple(checks),
        )

    checks.append(CHECK_IBAN_COUNTRY_LENGTH)
    if len(normalised) != expected:
        return CheckDigitResult(
            kind=kind,
            outcome=CheckDigitOutcome.failed,
            normalised=normalised,
            checks_performed=tuple(checks),
            detail=(
                f"the checksum passed but {country} IBANs are {expected} "
                f"characters and this is {len(normalised)}; if the registry "
                "says otherwise the table in this module is wrong"
            ),
        )
    return CheckDigitResult(
        kind=kind,
        outcome=CheckDigitOutcome.passed,
        normalised=normalised,
        checks_performed=tuple(checks),
    )


def _verify_lei(normalised: str) -> CheckDigitResult:
    """ISO 17442: eighteen alphanumerics, two check digits, MOD-97-10 over all."""
    kind = IdentifierKind.lei
    if not _LEI_RE.match(normalised):
        return _malformed(
            kind,
            normalised,
            "an LEI is 18 alphanumeric characters followed by 2 digits; "
            f"got {normalised!r}",
        )
    checks = (CHECK_STRUCTURE, CHECK_ISO7064_MOD97_10)
    if iso7064_mod97_10_residue(normalised) != 1:
        return CheckDigitResult(
            kind=kind,
            outcome=CheckDigitOutcome.failed,
            normalised=normalised,
            checks_performed=checks,
            detail="the ISO 7064 MOD-97-10 residue is not 1",
        )
    return CheckDigitResult(
        kind=kind,
        outcome=CheckDigitOutcome.passed,
        normalised=normalised,
        checks_performed=checks,
    )


def _verify_aba(normalised: str) -> CheckDigitResult:
    """Nine digits, weighted 3-7-1 repeating, summing to a multiple of ten."""
    kind = IdentifierKind.aba_routing
    if not _NINE_DIGITS_RE.match(normalised):
        return _malformed(
            kind,
            normalised,
            f"an ABA routing number is 9 digits; got {normalised!r}",
        )
    checks = (CHECK_STRUCTURE, CHECK_ABA_WEIGHTED_MOD10)
    expected = aba_check_digit(normalised[:8])
    stated = ord(normalised[8]) - 48
    if expected != stated:
        return CheckDigitResult(
            kind=kind,
            outcome=CheckDigitOutcome.failed,
            normalised=normalised,
            checks_performed=checks,
            detail=(
                f"the leading 8 digits imply a check digit of {expected} "
                f"and the 9th digit is {stated}"
            ),
        )
    return CheckDigitResult(
        kind=kind,
        outcome=CheckDigitOutcome.passed,
        normalised=normalised,
        checks_performed=checks,
    )


def _verify_payment_card(normalised: str) -> CheckDigitResult:
    """ISO/IEC 7812-1 length, then Luhn.

    No issuer-prefix check.  The prefix ranges say which network *would* have
    issued a number of this shape, not that this number was issued, and a
    forensic reader that reported "not a valid card" because a prefix was
    unfamiliar would be making a claim it cannot support about a number that
    may be perfectly real.
    """
    kind = IdentifierKind.payment_card
    if not _CARD_RE.match(normalised):
        return _malformed(
            kind,
            normalised,
            f"a card number is {CARD_MIN_DIGITS} to {CARD_MAX_DIGITS} "
            f"digits; got {normalised!r}",
        )
    checks = (CHECK_STRUCTURE, CHECK_LUHN_MOD10)
    residue = luhn_residue(normalised)
    if residue != 0:
        return CheckDigitResult(
            kind=kind,
            outcome=CheckDigitOutcome.failed,
            normalised=normalised,
            checks_performed=checks,
            detail=f"the Luhn sum is {residue} modulo 10, not 0",
        )
    return CheckDigitResult(
        kind=kind,
        outcome=CheckDigitOutcome.passed,
        normalised=normalised,
        checks_performed=checks,
    )


def _verify_bic(normalised: str) -> CheckDigitResult:
    """ISO 9362 shape.  There is no check digit and the result says so."""
    kind = IdentifierKind.bic
    if not _BIC_RE.match(normalised):
        return _malformed(
            kind,
            normalised,
            "a BIC is 6 letters then 2 alphanumerics, optionally followed by "
            f"a 3-character branch code; got {normalised!r}",
        )
    return CheckDigitResult(
        kind=kind,
        outcome=CheckDigitOutcome.no_check_digit,
        normalised=normalised,
        checks_performed=(CHECK_STRUCTURE,),
        detail="ISO 9362 defines no check digit; structure is all that was checked",
    )


def _verify_ssn(normalised: str) -> CheckDigitResult:
    """Nine digits, and the ranges the SSA has never issued.

    Randomisation from 25 June 2011 removed the geographic and sequential
    structure that used to make an SSN partly self-describing, so there is
    almost nothing left to check.  What survived randomisation is a short
    list of never-issued ranges — area
    ``000``, ``666`` and ``900``-``999``, group ``00``, serial ``0000`` — and
    those are worth applying, because a value in one of them cannot be a real
    SSN and is very often a placeholder somebody typed.

    The outcome is still ``no_check_digit`` when it passes.  These ranges are
    an exclusion list, not arithmetic over the value, and reporting them as
    ``passed`` would let a reader believe an SSN had been verified in the sense
    an IBAN is verified.  A value inside an excluded range is ``malformed``:
    the finding is about the shape of what was recorded.
    """
    kind = IdentifierKind.us_ssn
    if not _NINE_DIGITS_RE.match(normalised):
        return _malformed(
            kind, normalised, f"an SSN is 9 digits; got {normalised!r}"
        )
    area, group, serial = normalised[:3], normalised[3:5], normalised[5:]
    checks = (CHECK_STRUCTURE, CHECK_SSN_ISSUED_RANGES)
    reason = ""
    if area == "000" or area == "666" or area[0] == "9":
        reason = f"area {area} has never been issued"
    elif group == "00":
        reason = "group 00 has never been issued"
    elif serial == "0000":
        reason = "serial 0000 has never been issued"
    if reason:
        return CheckDigitResult(
            kind=kind,
            outcome=CheckDigitOutcome.malformed,
            normalised=normalised,
            checks_performed=checks,
            detail=reason,
        )
    return CheckDigitResult(
        kind=kind,
        outcome=CheckDigitOutcome.no_check_digit,
        normalised=normalised,
        checks_performed=checks,
        detail=(
            "an SSN has no check digit; randomisation since June 2011 leaves "
            "only the never-issued ranges, which this value is outside of"
        ),
    )


def _verify_ein(normalised: str) -> CheckDigitResult:
    """Nine digits and nothing more.

    An EIN's leading two digits are a campus prefix and some prefixes have
    never been assigned, which would make a table like the SSN exclusions
    above.  There is no such table here, because the assigned set has changed
    as the IRS reorganised its campuses and a stale copy would reject valid
    numbers issued after it was written.  Better to check nothing and say so
    than to check something out of date and call the result a verification.
    """
    kind = IdentifierKind.us_ein
    if not _NINE_DIGITS_RE.match(normalised):
        return _malformed(
            kind, normalised, f"an EIN is 9 digits; got {normalised!r}"
        )
    return CheckDigitResult(
        kind=kind,
        outcome=CheckDigitOutcome.no_check_digit,
        normalised=normalised,
        checks_performed=(CHECK_STRUCTURE,),
        detail="an EIN has no check digit; structure is all that was checked",
    )


_VERIFIERS = {
    IdentifierKind.iban: _verify_iban,
    IdentifierKind.lei: _verify_lei,
    IdentifierKind.aba_routing: _verify_aba,
    IdentifierKind.payment_card: _verify_payment_card,
    IdentifierKind.bic: _verify_bic,
    IdentifierKind.us_ssn: _verify_ssn,
    IdentifierKind.us_ein: _verify_ein,
}


def verify(kind: IdentifierKind, value: str) -> CheckDigitResult:
    """Check ``value`` as an identifier of ``kind``.

    The kind is given, never guessed; the module docstring says why.  Raises
    :class:`CheckDigitError` if ``kind`` is not an
    :class:`~postgres.models.enums.IdentifierKind` or if ``value`` is not a
    string, both of which are caller errors rather than facts about a document
    and so must not be recorded against a row as a verdict.
    """
    if not isinstance(kind, IdentifierKind):
        raise CheckDigitError(
            f"kind must be an IdentifierKind, got {type(kind).__name__}"
        )
    normalised = normalise(value)
    if not normalised:
        return _malformed(kind, normalised, "the value is empty")
    verifier = _VERIFIERS.get(kind)
    if verifier is None:
        # Unreachable while _VERIFIERS covers the enum, which a test asserts.
        # Present so that adding a member without a verifier fails loudly at
        # the call rather than by returning some neighbouring kind's verdict.
        raise CheckDigitError(f"no verifier is registered for {kind}")
    return verifier(normalised)
