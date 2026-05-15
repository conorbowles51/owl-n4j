"""
Lightweight phone number normaliser for Cellebrite unified-contact rollups.

The goal is to collapse contacts whose phone numbers are written differently
without accidentally treating app IDs, short codes, usernames, or e-mail
addresses as real telephone numbers.
"""

from __future__ import annotations

import re
from typing import Iterable, List, Optional, Set

# Strip every char that is not a digit or plus sign.
_NON_DIGIT = re.compile(r"[^\d+]")

# Bare-digit US patterns. Be deliberately strict: 10 digits, or 11 digits
# starting with country code 1. Long bare digit strings are often app IDs.
_US_10_STRICT = re.compile(r"^(\d{10})$")
_US_11_STRICT = re.compile(r"^1(\d{10})$")

# E.164: + followed by 7-15 digits.
_E164 = re.compile(r"^\+(\d{7,15})$")

# Person key as Cellebrite stores it: "phone-{digits}".
_PERSON_KEY = re.compile(r"^phone-(\d{7,15})$")


def normalise(raw: Optional[str], default_region: str = "US") -> Optional[str]:
    """
    Normalise a single string to E.164 form, for example +12028052817.

    Returns None for anything that does not look like a human telephone
    number: alphanumeric senders, app IDs, short codes, and ambiguous long
    bare digit strings.
    """
    if not raw:
        return None
    s = str(raw).strip()
    if not s:
        return None

    if any(c.isalpha() for c in s):
        return None

    cleaned = _NON_DIGIT.sub("", s)
    if not cleaned:
        return None

    match = _E164.match(cleaned)
    if match:
        digits = match.group(1)
        if _is_repeating_digits(digits):
            return None
        return f"+{digits}"

    if default_region == "US":
        match = _US_10_STRICT.match(cleaned)
        if match:
            digits = match.group(1)
            if _is_repeating_digits(digits):
                return None
            return f"+1{digits}"

        match = _US_11_STRICT.match(cleaned)
        if match:
            digits = match.group(1)
            if _is_repeating_digits(digits):
                return None
            return f"+1{digits}"

    return None


def _is_repeating_digits(digits: str) -> bool:
    """Return True for placeholder-like values such as 0000000000."""
    return len(set(digits)) <= 1


def normalise_all(
    candidates: Iterable[Optional[str]],
    default_region: str = "US",
) -> List[str]:
    """
    Normalise all candidates and return unique canonical forms in input order.
    """
    seen: Set[str] = set()
    out: List[str] = []
    for candidate in candidates:
        canonical = normalise(candidate, default_region=default_region)
        if canonical and canonical not in seen:
            seen.add(canonical)
            out.append(canonical)
    return out


def normalise_from_person_key(key: Optional[str]) -> Optional[str]:
    """
    Normalise a Cellebrite person key such as phone-2407063672.
    """
    if not key:
        return None
    match = _PERSON_KEY.match(str(key))
    if not match:
        return None
    return normalise(match.group(1))


def display_format(canonical: Optional[str]) -> Optional[str]:
    """
    Render an E.164 number for display.

    The US format is precise; non-US numbers get a best-effort grouped form.
    """
    if not canonical:
        return None
    if not canonical.startswith("+"):
        return canonical

    digits = canonical[1:]
    if len(digits) == 11 and digits.startswith("1"):
        return f"+1 ({digits[1:4]}) {digits[4:7]}-{digits[7:]}"

    if len(digits) >= 7:
        cc_len = 1 if len(digits) <= 11 else 2
        cc = digits[:cc_len]
        rest = digits[cc_len:]
        groups = [rest[i : i + 4] for i in range(0, len(rest), 4)]
        return f"+{cc} {' '.join(groups)}"

    return canonical
