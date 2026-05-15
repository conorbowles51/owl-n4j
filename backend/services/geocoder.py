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
