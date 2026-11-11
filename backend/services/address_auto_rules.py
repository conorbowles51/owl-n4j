"""What an automatic address lookup may send, and whether its answer may be pinned (lx-demo m111022392114579).

Automatic lookups sent the bare text found in evidence, with no region, so a site fragment or an unqualified place
was pinned wherever the address service's first answer was. Measured 10 Nov 2026: on case OPDMD69 99 of 219
automatic pins lay outside Maryland, DC and Virginia ("Montgomery County" in Texas, "Bel Pre" in Italy, "Emergency
Department" in London, "County of Kent, State of Delaware" in Rhode Island); on the demo case all 24 were wrong
("gate house" in Norwich, "Dock 3" in Dubai).

The rule, for automatic lookups only (a person clicking Look up is not changed):

- Text that names no place on its own (a site word such as gate, fence, dock, bay, house, department; a short code
  in capitals; no letters) is not sent. It waits for a person.
- Text that names a US state (by name, by its two-letter code after a comma, or with a ZIP code) is sent as it is,
  and its answer is pinned only when it lies in that state.
- Text that names its own region after a comma (a city, a country) is sent as it is.
- Any other text is sent with the case's own state added ("Montgomery County, Maryland, United States") and pinned
  only when the answer lies in that state. The case's state is the one most of its addresses name (at least
  ``REGION_MIN_MENTIONS`` and more than half of the state mentions). A case with none: the text is not sent.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import Iterable, Optional

US_STATES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California", "CO": "Colorado",
    "CT": "Connecticut", "DE": "Delaware", "DC": "District of Columbia", "FL": "Florida", "GA": "Georgia",
    "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas", "KY": "Kentucky",
    "LA": "Louisiana", "ME": "Maine", "MD": "Maryland", "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota",
    "MS": "Mississippi", "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada", "NH": "New Hampshire",
    "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York", "NC": "North Carolina", "ND": "North Dakota",
    "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VT": "Vermont", "VA": "Virginia",
    "WA": "Washington", "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming", "PR": "Puerto Rico",
}
_BY_NAME = {name.lower(): name for name in US_STATES.values()}
_STATE_NAME = re.compile(r"\b(" + "|".join(sorted((re.escape(n) for n in _BY_NAME), key=len, reverse=True))
                         + r")\b", re.I)
# a two-letter code only where an address puts one: after a comma ("Rockville, MD", "ST. LOUIS | MO | 63138")
_STATE_CODE = re.compile(r"(?:,|\||\()\s*(" + "|".join(US_STATES) + r")\b\.?(?:\s*(?:\||,)?\s*\d{5}(?:-\d{4})?)?\s*(?:,|\||\)|$)")
# a ZIP code ends an address; a five-digit number that starts one is a house number ("14211 Pear Tree Ln")
_ZIP = re.compile(r"(?<!^)(?<=[\s,|])\d{5}(?:-\d{4})?\s*$")
_COUNTRY_ONLY = re.compile(r"\s*,\s*(?:usa|u\.s\.a\.|us|united states(?: of america)?)\s*$", re.I)

# words that name a part of a site or a role, not a place: on their own they place nothing
SITE_WORDS = {
    "gate", "gatehouse", "house", "home", "fence", "dock", "bay", "entrance", "exit", "door", "lot", "parking",
    "garage", "yard", "sector", "department", "dispatch", "enroute", "en route", "area", "office", "headquarters",
    "hq", "building", "room", "floor", "lobby", "warehouse", "shed", "residence", "apartment", "unit", "suite",
    "hallway", "basement", "kitchen", "store", "shop", "scene", "site", "location", "address", "post", "station",
    "facility", "hospital", "school", "church", "court", "courthouse", "jail", "prison", "bank", "branch", "east",
    "west", "north", "south", "side", "rear", "front", "back", "corner", "here", "there", "apt", "troop", "unknown",
    "none", "bed", "mall", "locker",
}
STREET_WORDS = {
    "street", "st", "road", "rd", "avenue", "ave", "lane", "ln", "drive", "dr", "boulevard", "blvd", "court", "ct",
    "place", "pl", "way", "terrace", "ter", "highway", "hwy", "pike", "parkway", "pkwy", "circle", "cir", "route",
}
REGION_MIN_MENTIONS = 3

SEND = "send"
NOT_A_PLACE = "not_a_place"
NO_CASE_REGION = "no_case_region"
OUTSIDE_REGION = "outside_case_region"


@dataclass(frozen=True)
class Plan:
    action: str  # SEND, NOT_A_PLACE or NO_CASE_REGION
    query: Optional[str] = None  # what is sent
    expect_state: Optional[str] = None  # the answer is pinned only when it lies in this state
    region_added: bool = False


def states_named(text: str) -> list[str]:
    """The US states a piece of address text names, by name, by code after a comma, in order."""
    t = text or ""
    # a state name that names a street ("1600 Pennsylvania Ave", "50 Maryland Avenue") names no state
    found = [_BY_NAME[m.group(1).lower()] for m in _STATE_NAME.finditer(t)
             if not re.match(r"\s+(?:%s)\b" % "|".join(STREET_WORDS), t[m.end():], re.I)
             and not (m.group(1).lower() == "washington" and re.match(r"\s*,?\s*D\.?C\b", t[m.end():], re.I))]
    found += [US_STATES[m.group(1).upper()] for m in _STATE_CODE.finditer(t + ",")]
    return list(dict.fromkeys(found))


def _words(text: str) -> list[str]:
    return [w for w in re.split(r"[^a-z0-9]+", re.sub(r"['’]s\b", "", (text or "").lower())) if w]


def names_no_place(text: str) -> bool:
    """Text that places nothing on its own: no letters, a short code in capitals, or only site words and numbers."""
    t = (text or "").strip()
    words = _words(t)
    letters = [w for w in words if not w.isdigit()]
    if not letters:
        return True
    if re.fullmatch(r"[A-Z0-9 .&-]{1,5}", t):
        return True  # DCC, MCG, MAP, JP 2
    if any(w in STREET_WORDS for w in letters) and any(w.isdigit() or re.fullmatch(r"\d+[a-z]?", w) for w in words):
        return False  # a numbered street address
    rest = [w for w in letters if w not in SITE_WORDS and w not in {"the", "a", "an", "of", "his", "her", "their",
                                                                   "my", "our", "at", "near", "by", "in", "on", "to"}]
    if not rest:
        return True
    # one name word beside a site word ("Leonard home", "Meadowbrook area"): the site, not the place
    return len(rest) == 1 and len(letters) > 1 and rest[0] not in STREET_WORDS


def case_region(texts: Iterable[str]) -> tuple[Optional[str], dict]:
    """The case's state: the one most of its address texts name, with how many named it and how many named any."""
    counts: Counter = Counter()
    for t in texts:
        for s in set(states_named(t)):
            counts[s] += 1
    total = sum(counts.values())
    if not counts:
        return None, {"state_mentions": 0}
    state, n = counts.most_common(1)[0]
    basis = {"state": state, "addresses_naming_it": n, "state_mentions": total}
    if n >= REGION_MIN_MENTIONS and n * 2 > total:
        return state, basis
    return None, basis


def plan(text: str, region: Optional[str]) -> Plan:
    t = (text or "").strip()
    named = states_named(t)
    if named or _ZIP.search(t):
        return Plan(SEND, t, expect_state=named[-1] if named else None)
    if names_no_place(t):
        return Plan(NOT_A_PLACE)
    bare = _COUNTRY_ONLY.sub("", t)  # ", USA" names the country, not where in it
    if "," in bare and bare == t:
        return Plan(SEND, t)  # names its own city or country after a comma
    if not region:
        return Plan(NO_CASE_REGION)
    return Plan(SEND, "%s, %s, United States" % (bare, region), expect_state=region, region_added=True)


def in_state(result: dict, state: Optional[str]) -> bool:
    """The answer lies in ``state``: its address names that state (the service's own address for the pin)."""
    if not state:
        return True
    if (result.get("state") or "").strip().lower() == state.lower():
        return True
    # a whole part of the service's address ("..., Kent County, Rhode Island, United States"): "Delaware Avenue" in
    # Rhode Island does not lie in Delaware
    parts = [p.strip().lower() for p in (result.get("formatted_address") or "").split(",")]
    return state.lower() in parts
