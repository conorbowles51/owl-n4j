"""
Reverse-geocoding for Cellebrite locations.

Pluggable backends, primary + fallback, configurable per-deploy via
environment:

    GEOCODER=nominatim                  primary backend
    GEOCODER_URL=http://localhost:8080  required when GEOCODER=nominatim
    GEOCODER_FALLBACK=geonames          backend used when primary returns
                                        no result (typo, ocean point, etc.)
    GEOCODER_USER_AGENT=owl-cbm/1.0     User-Agent for HTTP backends
    GEOCODER_TIMEOUT_S=2.0              per-request HTTP timeout

The backend is read once at module import (env vars don't change at
runtime). Calls are synchronous and intentionally bounded by a short
HTTP timeout so a slow / down primary doesn't stall the ingestion
pipeline — the fallback kicks in on any exception, then "none" stamps
geocode_source="none" and moves on.

Returned shape (always; missing fields are None):

    {
        "address":        "10 Downing St, Westminster, London SW1A 2AA, UK",
        "place_name":     "London",
        "country":        "United Kingdom",
        "country_code":   "GB",
        "admin1":         "England",
        "admin2":         "Greater London",
        "geocode_source": "nominatim" | "geonames" | "cellebrite" | "none",
        "geocode_accuracy": "building" | "street" | "city" | "country",
    }
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

EMPTY_RESULT: Dict[str, Optional[str]] = {
    "address": None,
    "place_name": None,
    "country": None,
    "country_code": None,
    "admin1": None,
    "admin2": None,
    "geocode_source": "none",
    "geocode_accuracy": None,
}


def reverse_geocode(lat: float, lon: float) -> Dict[str, Optional[str]]:
    """
    Reverse-geocode a single point. Returns the canonical shape above.

    Always returns a dict — never raises. On total failure the result
    has source="none" and every field None except the source itself.
    """
    if lat is None or lon is None:
        return dict(EMPTY_RESULT)

    primary = _PRIMARY
    if primary is not None:
        try:
            r = primary.reverse(lat, lon)
            if r and (r.get("address") or r.get("place_name") or r.get("country")):
                return r
        except Exception as e:  # noqa: BLE001 - any backend failure → fallback
            logger.debug("Primary geocoder %s failed at (%s, %s): %s",
                         primary.name, lat, lon, e)

    fallback = _FALLBACK
    if fallback is not None and fallback is not primary:
        try:
            r = fallback.reverse(lat, lon)
            if r and (r.get("address") or r.get("place_name") or r.get("country")):
                return r
        except Exception as e:  # noqa: BLE001
            logger.debug("Fallback geocoder %s failed at (%s, %s): %s",
                         fallback.name, lat, lon, e)

    return dict(EMPTY_RESULT)


def geocoder_status() -> Dict[str, Any]:
    """
    Diagnostic snapshot for the /health-style endpoints. Surfaces what's
    configured + whether the deps are present so ops can verify the
    deployment without re-ingesting.
    """
    return {
        "primary": _PRIMARY.name if _PRIMARY else None,
        "primary_ready": bool(_PRIMARY),
        "fallback": _FALLBACK.name if _FALLBACK else None,
        "fallback_ready": bool(_FALLBACK),
        "url": os.environ.get("GEOCODER_URL") or None,
    }


# ---------------------------------------------------------------------------
# Backend protocol
# ---------------------------------------------------------------------------

class _Backend:
    name: str = "base"

    def reverse(self, lat: float, lon: float) -> Optional[Dict[str, Optional[str]]]:
        raise NotImplementedError


class _NominatimBackend(_Backend):
    """
    Self-hosted Nominatim. Requires GEOCODER_URL pointing at the HTTP
    instance (e.g. http://localhost:8080). Default Nominatim install
    needs no auth; if you front it with a reverse proxy that adds auth,
    set GEOCODER_AUTH=Bearer:xyz and we'll pass it through.

    Spec: https://nominatim.org/release-docs/develop/api/Reverse/
    """
    name = "nominatim"

    def __init__(self, base_url: str, timeout_s: float, user_agent: str, auth: Optional[str]):
        # httpx is already a dep (used elsewhere in backend) — no
        # conditional import needed.
        import httpx
        self._httpx = httpx
        self._base_url = base_url.rstrip("/")
        self._timeout_s = timeout_s
        self._user_agent = user_agent
        self._auth = auth
        # Persistent client = connection pooling. Saves a TCP handshake
        # per request when ingesting thousands of points back-to-back.
        headers = {"User-Agent": user_agent}
        if auth:
            headers["Authorization"] = auth
        self._client = httpx.Client(timeout=timeout_s, headers=headers)

    def reverse(self, lat: float, lon: float) -> Optional[Dict[str, Optional[str]]]:
        # zoom=18 → maximum detail (building level when available);
        # the response itself tells us how precise the match was via
        # the address keys present. Using addressdetails=1 splits the
        # admin levels into a structured object instead of just the
        # display_name string.
        params = {
            "lat": f"{lat}",
            "lon": f"{lon}",
            "format": "jsonv2",
            "addressdetails": "1",
            "zoom": "18",
        }
        url = f"{self._base_url}/reverse"
        try:
            resp = self._client.get(url, params=params)
        except Exception as e:  # noqa: BLE001
            logger.debug("Nominatim request error (%s, %s): %s", lat, lon, e)
            return None
        if resp.status_code != 200:
            return None
        try:
            data = resp.json()
        except Exception:  # noqa: BLE001
            return None
        if not isinstance(data, dict):
            return None
        addr = data.get("address") or {}
        # Nominatim splits city across half a dozen possible keys
        # depending on country (city, town, village, hamlet, suburb).
        place = (
            addr.get("city")
            or addr.get("town")
            or addr.get("village")
            or addr.get("hamlet")
            or addr.get("municipality")
            or addr.get("suburb")
            or addr.get("county")
            or addr.get("state")
        )
        # Accuracy heuristic: if the response carries a house_number
        # we treat it as building-level; if road only, street-level;
        # else city-level if we got a place; else country-level.
        if addr.get("house_number"):
            accuracy = "building"
        elif addr.get("road"):
            accuracy = "street"
        elif place:
            accuracy = "city"
        elif addr.get("country"):
            accuracy = "country"
        else:
            accuracy = None

        return {
            "address": data.get("display_name"),
            "place_name": place,
            "country": addr.get("country"),
            "country_code": (addr.get("country_code") or "").upper() or None,
            "admin1": addr.get("state") or addr.get("region"),
            "admin2": addr.get("county") or addr.get("city_district"),
            "geocode_source": "nominatim",
            "geocode_accuracy": accuracy,
        }


class _GeoNamesBackend(_Backend):
    """
    Pure in-process city-level lookup via the `reverse_geocoder` PyPI
    package (uses GeoNames cities1000 / cities5000 data). No network,
    no setup; install with `pip install reverse-geocoder`.

    Stops at the city level — there's no street address to give you.
    Useful as an always-works baseline when a hosted Nominatim isn't
    available, or as a fallback for points the primary couldn't match
    (e.g. low-zoom Nominatim install missing rural data).

    Lazy-loads its 50 MB lookup tree on first use. Wrapped in a lock
    so two ingestion threads racing for the first call don't both
    initialise it.
    """
    name = "geonames"
    _init_lock = threading.Lock()

    def __init__(self):
        # We only import here — at construction time. If reverse_geocoder
        # isn't installed, the factory below catches ImportError and
        # disables the backend entirely.
        import reverse_geocoder  # noqa: F401  # presence check
        self._rg = None

    def _ensure_loaded(self):
        if self._rg is not None:
            return
        with self._init_lock:
            if self._rg is not None:
                return
            import reverse_geocoder
            # mode=2 = multi-process query; OK in worker contexts.
            self._rg = reverse_geocoder.RGeocoder(mode=2, verbose=False)

    def reverse(self, lat: float, lon: float) -> Optional[Dict[str, Optional[str]]]:
        try:
            self._ensure_loaded()
            res = self._rg.query([(float(lat), float(lon))])
        except Exception as e:  # noqa: BLE001
            logger.debug("GeoNames lookup error: %s", e)
            return None
        if not res:
            return None
        r = res[0]
        place = r.get("name") or None
        country_code = (r.get("cc") or "").upper() or None
        return {
            "address": None,  # no street-level data in this dataset
            "place_name": place,
            "country": _COUNTRY_NAMES.get(country_code or ""),
            "country_code": country_code,
            "admin1": r.get("admin1") or None,
            "admin2": r.get("admin2") or None,
            "geocode_source": "geonames",
            "geocode_accuracy": "city" if place else "country",
        }


# Minimal ISO country code → name map for the GeoNames backend
# (reverse_geocoder only carries the ISO code). Covers the common
# cases; unknowns just leave the `country` field None and the
# country_code is still useful by itself.
_COUNTRY_NAMES = {
    "GB": "United Kingdom", "IE": "Ireland", "US": "United States",
    "CA": "Canada", "AU": "Australia", "NZ": "New Zealand",
    "FR": "France", "DE": "Germany", "ES": "Spain", "IT": "Italy",
    "PT": "Portugal", "NL": "Netherlands", "BE": "Belgium", "LU": "Luxembourg",
    "CH": "Switzerland", "AT": "Austria", "DK": "Denmark", "SE": "Sweden",
    "NO": "Norway", "FI": "Finland", "IS": "Iceland", "PL": "Poland",
    "CZ": "Czechia", "SK": "Slovakia", "HU": "Hungary", "RO": "Romania",
    "BG": "Bulgaria", "GR": "Greece", "HR": "Croatia", "SI": "Slovenia",
    "RS": "Serbia", "BA": "Bosnia and Herzegovina", "AL": "Albania",
    "MK": "North Macedonia", "ME": "Montenegro", "TR": "Turkey",
    "RU": "Russia", "UA": "Ukraine", "BY": "Belarus", "EE": "Estonia",
    "LV": "Latvia", "LT": "Lithuania", "MD": "Moldova", "GE": "Georgia",
    "AM": "Armenia", "AZ": "Azerbaijan", "KZ": "Kazakhstan", "UZ": "Uzbekistan",
    "JP": "Japan", "KR": "South Korea", "CN": "China", "TW": "Taiwan",
    "HK": "Hong Kong", "SG": "Singapore", "MY": "Malaysia", "ID": "Indonesia",
    "TH": "Thailand", "VN": "Vietnam", "PH": "Philippines", "IN": "India",
    "PK": "Pakistan", "BD": "Bangladesh", "LK": "Sri Lanka", "AE": "United Arab Emirates",
    "SA": "Saudi Arabia", "IL": "Israel", "EG": "Egypt", "ZA": "South Africa",
    "NG": "Nigeria", "KE": "Kenya", "ET": "Ethiopia", "MX": "Mexico",
    "BR": "Brazil", "AR": "Argentina", "CL": "Chile", "CO": "Colombia",
    "PE": "Peru", "VE": "Venezuela", "EC": "Ecuador", "UY": "Uruguay",
}


# ---------------------------------------------------------------------------
# Backend selection — runs once at module import
# ---------------------------------------------------------------------------

def _make_backend(name: str) -> Optional[_Backend]:
    """
    Construct a backend by name, or return None if the dependency is
    missing or the config is incomplete. Logs a warning so ops can see
    why a configured backend wasn't activated.
    """
    n = (name or "").strip().lower()
    if n in ("", "none", "disabled"):
        return None

    if n == "nominatim":
        url = os.environ.get("GEOCODER_URL", "").strip()
        if not url:
            logger.warning(
                "Geocoder=nominatim configured but GEOCODER_URL is unset; "
                "Nominatim backend disabled."
            )
            return None
        timeout_s = _safe_float(os.environ.get("GEOCODER_TIMEOUT_S"), 2.0)
        ua = os.environ.get("GEOCODER_USER_AGENT", "owl-cbm/1.0")
        auth = os.environ.get("GEOCODER_AUTH") or None
        try:
            return _NominatimBackend(url, timeout_s, ua, auth)
        except Exception as e:  # noqa: BLE001
            logger.warning("Failed to construct Nominatim backend: %s", e)
            return None

    if n == "geonames":
        try:
            return _GeoNamesBackend()
        except ImportError:
            logger.warning(
                "Geocoder=geonames configured but reverse_geocoder is not "
                "installed. Run `pip install reverse-geocoder` to enable."
            )
            return None
        except Exception as e:  # noqa: BLE001
            logger.warning("Failed to construct GeoNames backend: %s", e)
            return None

    logger.warning("Unknown geocoder backend %r — ignored.", name)
    return None


def _safe_float(s: Optional[str], default: float) -> float:
    if not s:
        return default
    try:
        return float(s)
    except (TypeError, ValueError):
        return default


# Default-OFF policy: if no env vars are set, both are None and
# reverse_geocode() returns the empty result for every call. That's
# the same behaviour as before this module was added — nothing breaks
# in deploys that haven't opted in. To turn it on:
#   - Quick start:   GEOCODER=geonames + pip install reverse-geocoder
#   - Production:    GEOCODER=nominatim GEOCODER_URL=http://...:8080
#                    GEOCODER_FALLBACK=geonames (recommended)
_PRIMARY = _make_backend(os.environ.get("GEOCODER", ""))
_FALLBACK = _make_backend(os.environ.get("GEOCODER_FALLBACK", ""))

if _PRIMARY:
    logger.info("Geocoder primary backend: %s", _PRIMARY.name)
if _FALLBACK and _FALLBACK is not _PRIMARY:
    logger.info("Geocoder fallback backend: %s", _FALLBACK.name)


# ---------------------------------------------------------------------------
# Offline forward lookup: a written place name -> GeoNames candidates
# (docs/cellebrite/04-pattern-of-life.md section 6.5)
# ---------------------------------------------------------------------------
#
# A suggestion only, never a placement: a person chooses a point and radius and that choice is what is saved. The
# lookup reads a GeoNames index on this server and sends nothing anywhere. The index is a SQLite file built once from
# the GeoNames ``cities1000.txt`` (with ``admin1CodesASCII.txt`` and ``countryInfo.txt`` beside it) under
# ``$LOUPE_REFERENCE_DATA_DIR/geonames``:
#
#     python -m services.geocoder build-forward-index
#
# Each lookup opens it read-only, so no worker holds the 170,000 places in memory (an in-memory index measured
# 98 MB and 16 s to load per worker on this server).

import re as _re
import sqlite3 as _sqlite3
import sys as _sys
import unicodedata as _ud

GEONAMES_ATTRIBUTION = "Place names: GeoNames (geonames.org), CC BY 4.0"
FORWARD_LIMIT = 5
FORWARD_INDEX = "geonames-forward.sqlite"


def _reference_dir() -> str:
    return os.path.join(os.environ.get("LOUPE_REFERENCE_DATA_DIR", "/mnt/owl-data/reference-data"), "geonames")


def fold_place_name(s: str) -> str:
    """Case, accents and punctuation folded, spaces collapsed: ``"Sant Julià de Lòria"`` -> ``"sant julia de loria"``."""
    s = _ud.normalize("NFKD", s or "")
    s = "".join(ch for ch in s if not _ud.combining(ch)).casefold()
    return " ".join(_re.sub(r"[^0-9a-z]+", " ", s).split())


def _ro_uri(path: str) -> str:
    """A read-only SQLite URI for ``path``, quoted so ``?``, ``#`` or ``%`` in a directory name stay part of the path."""
    from urllib.parse import quote
    return "file:%s?mode=ro" % quote(os.path.abspath(path))


def forward_index_path() -> str:
    return os.path.join(_reference_dir(), FORWARD_INDEX)


def forward_source() -> Dict[str, Any]:
    """``{"available", "path", "places", "reason"}`` for the offline place index, read from its own metadata."""
    path = forward_index_path()
    if not os.path.isfile(path):
        return {"available": False, "path": path, "places": 0,
                "reason": "The offline GeoNames place list is not installed on this server."}
    try:
        with _sqlite3.connect(_ro_uri(path), uri=True) as db:
            n = int(db.execute("SELECT value FROM meta WHERE key = 'places'").fetchone()[0])
    except Exception as e:  # noqa: BLE001 - a broken index means no suggestions, said so
        logger.warning("GeoNames forward index unreadable: %s", e)
        return {"available": False, "path": path, "places": 0,
                "reason": "The offline GeoNames place list on this server could not be read."}
    return {"available": True, "path": path, "places": n, "reason": None}


def build_forward_index(source_dir: Optional[str] = None, out_path: Optional[str] = None) -> Dict[str, Any]:
    """Build the SQLite index from GeoNames ``cities1000.txt`` (tab-separated, the export's own columns)."""
    d = source_dir or _reference_dir()
    out = out_path or os.path.join(d, FORWARD_INDEX)
    admin1, countries = {}, dict(_COUNTRY_NAMES)
    a1 = os.path.join(d, "admin1CodesASCII.txt")
    if os.path.isfile(a1):
        with open(a1, encoding="utf-8") as fh:
            for line in fh:
                p = line.rstrip("\n").split("\t")
                if len(p) >= 2:
                    admin1[p[0]] = p[1]
    ci = os.path.join(d, "countryInfo.txt")
    if os.path.isfile(ci):
        with open(ci, encoding="utf-8") as fh:
            for line in fh:
                p = line.rstrip("\n").split("\t")
                if not line.startswith("#") and len(p) > 4 and p[0]:
                    countries[p[0]] = p[4]
    tmp = out + ".building"
    if os.path.exists(tmp):
        os.remove(tmp)
    db = _sqlite3.connect(tmp)
    db.executescript(
        "CREATE TABLE place (geonameid INTEGER PRIMARY KEY, name TEXT NOT NULL, fold TEXT NOT NULL, "
        "lat REAL NOT NULL, lon REAL NOT NULL, cc TEXT, admin1_code TEXT, admin1 TEXT, population INTEGER);"
        "CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);")
    n = bad = 0
    batch = []
    with open(os.path.join(d, "cities1000.txt"), encoding="utf-8") as fh:
        for line in fh:
            p = line.rstrip("\n").split("\t")
            try:
                row = (int(p[0]), p[1], fold_place_name(p[1]), float(p[4]), float(p[5]), p[8] or None,
                       p[10] or None, admin1.get("%s.%s" % (p[8], p[10])), int(p[14] or 0))
            except (IndexError, ValueError):
                bad += 1
                continue
            batch.append(row)
            n += 1
            if len(batch) >= 20000:
                db.executemany("INSERT INTO place VALUES (?,?,?,?,?,?,?,?,?)", batch)
                batch = []
    if batch:
        db.executemany("INSERT INTO place VALUES (?,?,?,?,?,?,?,?,?)", batch)
    db.execute("CREATE INDEX ix_place_fold ON place (fold)")
    db.executemany("INSERT INTO meta VALUES (?, ?)", [("places", str(n)), ("rejected", str(bad)),
                                                     ("countries", "\t".join("%s=%s" % kv for kv in
                                                                             sorted(countries.items())))])
    db.commit()
    db.close()
    os.replace(tmp, out)
    os.chmod(out, 0o644)
    return {"places": n, "rejected": bad, "path": out}


_COUNTRY_CACHE: Dict[str, Any] = {}


def _countries(db, path) -> tuple:
    """(code -> name, folded country names) from the index's metadata, kept per index file and build time."""
    key = (path, os.path.getmtime(path))
    if _COUNTRY_CACHE.get("key") != key:
        raw = db.execute("SELECT value FROM meta WHERE key = 'countries'").fetchone()
        names = dict(kv.split("=", 1) for kv in raw[0].split("\t") if "=" in kv) if raw and raw[0] else {}
        _COUNTRY_CACHE.update(key=key, names=names, folded={fold_place_name(v): k for k, v in names.items()})
    return _COUNTRY_CACHE["names"], _COUNTRY_CACHE["folded"]


def _name_parts(text: str):
    """(names, region codes, country words) from a written place. Names are each comma-separated part (last first,
    where a town usually stands) without house numbers, postcodes or a trailing two-letter region code, then the
    whole text; region codes are two-letter capitals (``IL``, ``CA``) that rank places in that region first."""
    parts = [p.strip() for p in (text or "").split(",") if p.strip()]
    names, regions = [], set()
    for p in reversed(parts):
        raw_words = [w for w in p.replace(".", " ").split() if not any(ch.isdigit() for ch in w)]
        while raw_words and len(raw_words[-1]) == 2 and raw_words[-1].isalpha() and raw_words[-1].isupper():
            regions.add(raw_words.pop())  # "Springfield IL 62701" -> name "springfield", region IL
        cand = fold_place_name(" ".join(raw_words))
        if cand and cand not in names:
            names.append(cand)
    whole = fold_place_name(text)
    if whole and whole not in names:
        names.append(whole)
    return names, regions, {fold_place_name(p) for p in parts}


def forward_candidates(text: str, limit: int = FORWARD_LIMIT) -> Dict[str, Any]:
    """GeoNames places whose name matches a part of ``text``: ``{"total", "returned", "limit", "candidates",
    "attribution"}``. Each candidate: name, lat, lon, country_code, country, admin1, population, geonameid, matched
    (the part of the text it matched). Places in a region or country the text names come first, then by the part's
    position (last part first), then population. ``total`` counts every match, so a clipped list says so. Raises
    ``LookupError`` when the index is not installed."""
    src = forward_source()
    if not src["available"]:
        raise LookupError(src["reason"])
    names, regions, words = _name_parts(text)
    with _sqlite3.connect(_ro_uri(src["path"]), uri=True) as db:
        countries, folded = _countries(db, src["path"])
        wanted_cc = {folded[w] for w in words if w in folded}
        seen, ordered = set(), []
        for rank, part in enumerate(names):
            if not part or part in folded:
                continue  # a country name alone is not a place to stand at
            for gid, name, lat, lon, cc, a1c, a1, pop in db.execute(
                    "SELECT geonameid, name, lat, lon, cc, admin1_code, admin1, population FROM place WHERE fold = ?",
                    (part,)):
                if gid in seen:
                    continue
                seen.add(gid)
                # A region the text names (its own admin1 code, or a country written out) ranks first; a
                # two-letter code that is only a country code ("IL" is Illinois before it is Israel) ranks next.
                tier = 0 if (a1c in regions or cc in wanted_cc) else 1 if cc in regions else 2
                ordered.append(((tier, rank, -(pop or 0)), {
                    "name": name, "lat": lat, "lon": lon, "country_code": cc, "country": countries.get(cc or ""),
                    "admin1": a1, "population": pop, "geonameid": gid, "matched": part}))
    ordered.sort(key=lambda x: x[0])
    out = [c for _, c in ordered[:limit]]
    return {"total": len(ordered), "returned": len(out), "limit": limit, "candidates": out,
            "attribution": GEONAMES_ATTRIBUTION}


_PAYEE_SPLIT = _re.compile(r"[\s,]+")
PAYEE_MAX_WORDS = 3


def payee_tail(text: str) -> tuple:
    """(names longest first, region code) from a payment's written payee: a card line ends with a town and a two-letter
    region ("FOOD LION #1234 BATTLEBORO NC"). Only the last line is read, and only the words after the last one that
    holds a digit, ``#``, ``*`` or ``/`` (store numbers, phone numbers and dates end the merchant's name). A line with no
    trailing region code gives nothing: on 32,727 real payee texts, the commonest matches on lines without one were
    surnames and months (gonzalez, hernandez, vazquez, may, nov), and on lines with one, towns."""
    lines = [ln for ln in (text or "").splitlines() if ln.strip()]
    if not lines:
        return [], None
    words = [w for w in _PAYEE_SPLIT.split(lines[-1].strip()) if w]
    if len(words) < 2 or not (len(words[-1]) == 2 and words[-1].isalpha() and words[-1].isupper()):
        return [], None
    region = words[-1]
    tail = []
    for w in reversed(words[:-1]):
        if any(ch.isdigit() or ch in "#*/" for ch in w):
            break
        tail.insert(0, w)
    names = []
    for n in range(min(PAYEE_MAX_WORDS, len(tail)), 0, -1):
        name = fold_place_name(" ".join(tail[-n:]))
        if len(name) >= 3 and name not in names:
            names.append(name)
    return names, region


def payee_candidates(text: str, limit: int = FORWARD_LIMIT) -> Dict[str, Any]:
    """GeoNames places a payment's written payee names, in the shape of ``forward_candidates``: a place of the name at
    the end of the text in the region code that closes it. The longest name that matches wins, so "SAN DIEGO CA" never
    offers a town called Diego. Raises ``LookupError`` when the index is not installed."""
    src = forward_source()
    if not src["available"]:
        raise LookupError(src["reason"])
    names, region = payee_tail(text)
    out = []
    with _sqlite3.connect(_ro_uri(src["path"]), uri=True) as db:
        countries, _ = _countries(db, src["path"])
        for name in names:
            rows = db.execute(
                "SELECT geonameid, name, lat, lon, cc, admin1_code, admin1, population FROM place WHERE fold = ? AND "
                "(admin1_code = ? OR cc = ?)", (name, region, region)).fetchall()
            if rows:
                rows.sort(key=lambda r: (r[5] != region, -(r[7] or 0), r[0]))
                out = [{"name": n, "lat": lat, "lon": lon, "country_code": cc, "country": countries.get(cc or ""),
                        "admin1": a1, "population": pop, "geonameid": gid, "matched": "%s %s" % (name, region)}
                       for gid, n, lat, lon, cc, _a1c, a1, pop in rows]
                break
    return {"total": len(out), "returned": min(len(out), limit), "limit": limit, "candidates": out[:limit],
            "attribution": GEONAMES_ATTRIBUTION}


if __name__ == "__main__":  # pragma: no cover - operator command
    if _sys.argv[1:2] == ["build-forward-index"]:
        print(build_forward_index(*(_sys.argv[2:4])))
    else:
        print("usage: python -m services.geocoder build-forward-index [source_dir] [out_path]")
