"""
Lightweight phone number normaliser for the Cellebrite "unified by
number" rollup. Goal: collapse the same human across phones whose
contact lists spell their number differently.

Inputs we see in the wild from Cellebrite reports:
- "+1 (202) 805-2817"
- "1-202-805-2817"
- "2028052817"
- "(202) 805 2817"
- "+44 7700 900123"  (UK; rare in our cases but should not crash)
- "Alex"             (alphanumeric — return None, can't normalise)
- "12345"            (short code — return None)
- "telegram:abc123"  (app ID — return None)

We intentionally do NOT pull in the full `phonenumbers` library — it's
~7 MB compiled and we need very little of it. A tight regex pass
covers >95% of the data we see; anything ambiguous returns None and
the caller groups it under the raw alias.

`default_region` is currently US-only. If a future case is non-US we
add a per-case override on the Case model rather than auto-detect.
"""

from __future__ import annotations

import re
from typing import Optional

# Strip every char that isn't a digit or leading +.
_NON_DIGIT = re.compile(r"[^\d+]")

# Canonical US: 10 digits, optionally with country code 1.
_US_10 = re.compile(r"^1?(\d{10})$")
# E.164 international: + followed by 7-15 digits.
_E164 = re.compile(r"^\+(\d{7,15})$")


def normalise(raw: Optional[str], default_region: str = "US") -> Optional[str]:
    """
    Normalise a phone number to E.164 form (+12028052817).

    Returns None for anything that doesn't look like a real telephone
    number (alphanumeric senders, app IDs, short codes < 7 digits).

    The default_region parameter controls how bare 10-digit numbers
    are interpreted. We only support 'US' for now; passing anything
    else falls back to "must already have +" rules.
    """
    if not raw:
        return None
    s = str(raw).strip()
    if not s:
        return None

    # Reject obvious non-phone patterns up front — anything with
    # letters (other than a leading + already stripped below) isn't a
    # phone number we can canonicalise.
    if any(c.isalpha() for c in s):
        return None

    # Strip whitespace, dashes, parens, dots — keep digits and a
    # leading + if present.
    cleaned = _NON_DIGIT.sub("", s)
    if not cleaned:
        return None

    # Already E.164.
    m = _E164.match(cleaned)
    if m:
        digits = m.group(1)
        # Sanity: 7-15 digits is the E.164 spec range. Reject obvious
        # noise (single-digit "+0" etc.).
        if 7 <= len(digits) <= 15:
            return f"+{digits}"
        return None

    # Bare digits — try US fallback when default_region is US.
    if default_region == "US":
        m = _US_10.match(cleaned)
        if m:
            return f"+1{m.group(1)}"

    # Anything else (5-digit short codes, malformed input) is dropped.
    return None


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
