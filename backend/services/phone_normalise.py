"""
Phone-number normaliser — the single source of truth for canonicalising
phone numbers across BOTH cellebrite ingestion (which mints
``phone-{digits}`` Person keys) and the backend "unify by number" rollup.

Backed by libphonenumber (the ``phonenumbers`` package) so it handles
international numbers correctly, not just US/NANP.

Canonical form: E.164, e.g. ``+13017289052``, ``+50233991579``.

Person key (minted at ingest): ``phone-{e164_digits}`` where the digits
are the FULL international number WITHOUT the leading ``+`` — i.e. the
country code IS included. ``+13017289052`` -> ``phone-13017289052``.
This keeps the historical ``phone-{digits}`` contract (the regex below,
which several neo4j_service consumers rely on) while making keys globally
unambiguous: pre-internationalisation US keys dropped the country code
(``phone-3017289052``), which could collide with a foreign national
number.

``default_region`` is the region assumed for *bare* numbers that lack a
leading ``+`` (the country code can't be inferred otherwise). Defaults to
US. Non-US cases set ``Case.default_region`` and thread it through
ingestion; once a number is stored as E.164 it carries its own country
code, so everything downstream is region-agnostic.

Validity: a parsed number is accepted only when ``is_valid_number()`` is
True. This rejects the junk Cellebrite emits as "numbers" — Facebook /
WhatsApp numeric IDs, short codes, alphanumeric handles, and even
phone-LENGTH numeric IDs whose area code doesn't exist (e.g.
``1000144225``, which the looser ``is_possible_number`` would wrongly
accept). The trade-off is that numbers in reserved / legacy / unassigned
ranges are dropped; those effectively never appear in real extractions.
"""

from __future__ import annotations

import re
from typing import Iterable, List, Optional, Set

import phonenumbers

# Person key as cellebrite stores it: "phone-{digits}", 7-15 digits
# (E.164 allows at most 15 digits including the country code).
_PERSON_KEY = re.compile(r"^phone-(\d{7,15})$")

DEFAULT_REGION = "US"


def normalise(raw: Optional[str], default_region: str = DEFAULT_REGION) -> Optional[str]:
    """Canonicalise a single string to E.164 (``+13017289052``), or None.

    Returns None for anything that isn't a *valid* telephone number:
    alphanumeric senders, e-mail addresses, app IDs, short codes, and
    numeric IDs (including phone-length ones in non-existent ranges).
    """
    if not raw:
        return None
    s = str(raw).strip()
    if not s:
        return None
    # Reject anything with letters — usernames, e-mails, "telegram:abc".
    if any(c.isalpha() for c in s):
        return None
    # A leading '+' carries the country code, so the region is irrelevant;
    # otherwise the bare number is interpreted in default_region.
    region = None if s.lstrip().startswith("+") else default_region
    try:
        num = phonenumbers.parse(s, region)
    except phonenumbers.NumberParseException:
        return None
    if not phonenumbers.is_valid_number(num):
        return None
    return phonenumbers.format_number(num, phonenumbers.PhoneNumberFormat.E164)


def person_key(raw: Optional[str], default_region: str = DEFAULT_REGION) -> Optional[str]:
    """Mint the canonical ``phone-{e164_digits}`` Person key for a raw
    number, or None if it isn't a valid phone number. The country code is
    included in the digits (no ``+``): ``+13017289052`` -> ``phone-13017289052``.
    """
    canon = normalise(raw, default_region=default_region)
    if not canon:
        return None
    return f"phone-{canon[1:]}"  # strip the leading '+'


def normalise_all(
    candidates: Iterable[Optional[str]],
    default_region: str = DEFAULT_REGION,
) -> List[str]:
    """Normalise every string in ``candidates`` to the unique set of
    canonical E.164 forms, insertion-ordered for stable output.

    Used by the unified-contacts rollup: a single Person can carry a mix
    of real numbers and app IDs in its ``phone_numbers`` list — we want
    every canonical number that comes out so the bucketing layer can join
    the Person to every canonical bucket it belongs to.
    """
    seen: Set[str] = set()
    out: List[str] = []
    for c in candidates:
        canon = normalise(c, default_region=default_region)
        if canon and canon not in seen:
            seen.add(canon)
            out.append(canon)
    return out


def normalise_from_person_key(
    key: Optional[str],
    default_region: str = DEFAULT_REGION,
) -> Optional[str]:
    """Recover the E.164 canonical form from a ``phone-{digits}`` Person
    key, or None for non-"phone-" keys (email-..., fb-..., etc.).

    Post-internationalisation keys store the full E.164 digits (country
    code included), so we prepend ``+`` and validate. A legacy national-
    only key (no country code) falls back to region-based parsing.
    """
    if not key:
        return None
    m = _PERSON_KEY.match(str(key))
    if not m:
        return None
    digits = m.group(1)
    cand = normalise("+" + digits)
    if cand:
        return cand
    # Legacy key minted before country codes were included in the key.
    return normalise(digits, default_region=default_region)


def display_format(
    canonical: Optional[str],
    default_region: str = DEFAULT_REGION,
) -> Optional[str]:
    """Human-readable INTERNATIONAL rendering of an E.164 number.

    ``+12028052817`` -> ``+1 202-805-2817``;
    ``+50233991579`` -> ``+502 3399 1579``. Falls back to the input
    unchanged if it can't be parsed. Pure presentation helper.
    """
    if not canonical:
        return None
    try:
        num = phonenumbers.parse(
            canonical,
            None if str(canonical).startswith("+") else default_region,
        )
    except phonenumbers.NumberParseException:
        return canonical
    return phonenumbers.format_number(num, phonenumbers.PhoneNumberFormat.INTERNATIONAL)
