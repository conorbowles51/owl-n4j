"""
Lightweight phone number normaliser for the Cellebrite "unified by
number" rollup. Goal: collapse the same human across phones whose
contact lists spell their number differently.

Inputs we see in the wild from Cellebrite reports:

Valid:
- "+1 (202) 805-2817"
- "1-202-805-2817"
- "2028052817"        (10 digits — US fallback)
- "(202) 805 2817"
- "+44 7700 900123"   (UK; rare but should not crash)

Junk we MUST reject (real failures from OPDMD28):
- "Alex"                    (alphanumeric — name, not number)
- "12345"                   (short code, < 7 digits)
- "100014422513889"         (Facebook user ID — 15 digits, no +)
- "46648305393"             (WhatsApp internal ID — 11 digits, no +,
                             not starting with 1)
- "12403058399@s.whatsapp.net"  (rejected by alpha check)

Strategy: be **strict** when the input lacks a leading '+'. A leading
'+' is a strong human signal "this is a phone number". Without it we
require *exactly* 10 digits (US area code + number) OR exactly 11
digits starting with 1 (US country code + number). Anything else
without '+' is rejected as ambiguous — usually it's an app ID.

Trade-off: a few real international numbers pasted as bare digits
will be rejected. We accept that loss to avoid the much worse failure
of bucketing Facebook IDs as phone numbers.

We intentionally do NOT pull in the full `phonenumbers` library — it's
~7 MB compiled and we need very little of it. A tight regex pass
covers the data we see; anything ambiguous returns None and the
caller groups it under the raw alias.

`default_region` is currently US-only. If a future case is non-US we
add a per-case override on the Case model rather than auto-detect.
"""

from __future__ import annotations

import re
from typing import Iterable, List, Optional, Set

# Strip every char that isn't a digit or leading +.
_NON_DIGIT = re.compile(r"[^\d+]")

# Bare-digit US patterns — strict: 10 digits OR 11 digits starting
# with 1. Critically NOT _US_10 = "^1?(\\d{10})$" because that would
# match 11-digit non-US Facebook IDs too. We need leading-1 to be
# explicit, not optional-then-anything-after.
_US_10_STRICT = re.compile(r"^(\d{10})$")
_US_11_STRICT = re.compile(r"^1(\d{10})$")
# E.164: + followed by 7-15 digits.
_E164 = re.compile(r"^\+(\d{7,15})$")
# Person key as Cellebrite stores it: "phone-{digits}". The digits
# are typically the last-10 of the number — strong canonical signal.
_PERSON_KEY = re.compile(r"^phone-(\d{7,15})$")


def normalise(raw: Optional[str], default_region: str = "US") -> Optional[str]:
    """
    Normalise a single string to E.164 form (+12028052817).

    Returns None for anything that doesn't look like a real telephone
    number — alphanumeric senders, app IDs, short codes < 7 digits,
    long bare digit strings without a leading + (likely Facebook /
    WhatsApp internal IDs).
    """
    if not raw:
        return None
    s = str(raw).strip()
    if not s:
        return None

    # Reject anything with letters — usernames, e-mail addresses,
    # "telegram:abc" style prefixes.
    if any(c.isalpha() for c in s):
        return None

    # Strip whitespace, dashes, parens, dots — keep digits and a
    # leading + if present.
    cleaned = _NON_DIGIT.sub("", s)
    if not cleaned:
        return None

    # Already E.164. Range cap is firm: more than 15 digits = not a
    # real phone number per the spec. This is the rule that filters
    # out 16+ digit Facebook IDs that snuck a + on.
    m = _E164.match(cleaned)
    if m:
        digits = m.group(1)
        # Reject "+1" + 10 digits when those 10 digits are obviously
        # noise (all zeros, all same digit) — guard for unsanitised
        # placeholder data.
        if _is_repeating_digits(digits):
            return None
        return f"+{digits}"

    # Bare digits — accept ONLY 10 digits or 11 digits starting with 1
    # when default_region == US. This is the key tightening: previously
    # we accepted "1?\\d{10}" which let through 11-digit non-US IDs.
    if default_region == "US":
        m = _US_10_STRICT.match(cleaned)
        if m:
            digits = m.group(1)
            if _is_repeating_digits(digits):
                return None
            return f"+1{digits}"
        m = _US_11_STRICT.match(cleaned)
        if m:
            digits = m.group(1)
            if _is_repeating_digits(digits):
                return None
            return f"+1{digits}"

    # Anything else (5-digit short codes, 12-15 digit bare numbers
    # without a +) is dropped as ambiguous.
    return None


def _is_repeating_digits(digits: str) -> bool:
    """True for '0000000000', '1111111111' etc. — placeholder noise."""
    return len(set(digits)) <= 1


def normalise_all(
    candidates: Iterable[Optional[str]],
    default_region: str = "US",
) -> List[str]:
    """
    Normalise every string in `candidates` and return the unique set
    of canonical forms (insertion-ordered for stable output).

    Used by the unified-contacts rollup: a single Person can carry a
    mix of real phone numbers and app IDs in its `phone_numbers`
    list — we want every canonical number that comes out, not just
    the first one. The bucketing layer then joins this Person to
    EVERY canonical bucket simultaneously, so two Persons sharing
    even one canonical number get rolled up together.
    """
    seen: Set[str] = set()
    out: List[str] = []
    for c in candidates:
        canon = normalise(c, default_region=default_region)
        if canon and canon not in seen:
            seen.add(canon)
            out.append(canon)
    return out


def normalise_from_person_key(key: Optional[str]) -> Optional[str]:
    """
    Cellebrite ingestion mints Person keys as "phone-{digits}" where
    the digits are derived from the number itself. That makes the key
    one of the more reliable signals of canonicalisation — a Person
    whose `phone_numbers` array is full of app IDs may still have a
    `phone-2407063672` key telling us the real number.

    Returns the E.164 form derived from the key, or None for non-
    "phone-" keys (email-..., fb-..., etc.).
    """
    if not key:
        return None
    m = _PERSON_KEY.match(str(key))
    if not m:
        return None
    return normalise(m.group(1))


def display_format(canonical: Optional[str]) -> Optional[str]:
    """
    Human-readable form of an E.164 canonical number.

    +12028052817 -> +1 (202) 805-2817
    +447700900123 -> +44 7700 900123  (best-effort; non-US gets a
                                       simple grouped-digit rendering)
    None -> None

    Pure presentation helper; does no validation. The frontend can
    also do this in JS if it prefers — having both keeps the option
    open.
    """
    if not canonical:
        return None
    if not canonical.startswith("+"):
        return canonical
    digits = canonical[1:]
    if len(digits) == 11 and digits.startswith("1"):
        # US: +1 (NPA) NXX-XXXX
        return f"+1 ({digits[1:4]}) {digits[4:7]}-{digits[7:]}"
    # Generic: country code + 4-digit groups.
    if len(digits) >= 7:
        cc_len = 1 if len(digits) <= 11 else 2
        cc = digits[:cc_len]
        rest = digits[cc_len:]
        # Group in 3-4 digit chunks for readability.
        groups = []
        for i in range(0, len(rest), 4):
            groups.append(rest[i : i + 4])
        return f"+{cc} {' '.join(groups)}"
    return canonical
