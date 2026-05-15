"""
Hash lookup service for triage classification.

External lookup results are cached on TriageFile nodes in Neo4j by the
classifier. Investigator-provided custom hash sets are runtime state and are
stored in Postgres.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from threading import RLock
from typing import Callable, Dict, Iterator, List, Optional, Set, Tuple

import requests
from sqlalchemy import select
from sqlalchemy.orm import Session

from config import NSRL_RATE_LIMIT, VIRUSTOTAL_API_KEY, VIRUSTOTAL_RATE_LIMIT
from postgres.models.triage import TriageHashSet
from postgres.session import get_background_session

logger = logging.getLogger(__name__)

CIRCL_BULK_URL = "https://hashlookup.circl.lu/bulk/sha256"
CIRCL_BATCH_SIZE = 100

SessionFactory = Callable[[], Session]


class TokenBucketRateLimiter:
    """Simple token bucket rate limiter."""

    def __init__(self, rate_per_second: float):
        self._rate = max(rate_per_second, 0.1)
        self._tokens = self._rate
        self._last_refill = time.monotonic()

    def acquire(self):
        """Block until a token is available."""
        while True:
            now = time.monotonic()
            elapsed = now - self._last_refill
            self._tokens = min(self._rate, self._tokens + elapsed * self._rate)
            self._last_refill = now
            if self._tokens >= 1.0:
                self._tokens -= 1.0
                return
            sleep_time = (1.0 - self._tokens) / self._rate
            time.sleep(sleep_time)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _clean_hashes(hashes: List[str]) -> List[str]:
    clean = {
        h.strip().lower()
        for h in hashes
        if h and len(h.strip()) == 64 and all(c in "0123456789abcdef" for c in h.strip().lower())
    }
    return sorted(clean)


class HashLookupService:
    """Lookup file hashes against known databases and custom Postgres hash sets."""

    def __init__(self, session_factory: SessionFactory | None = None):
        self._session_factory = session_factory
        self._circl_limiter = TokenBucketRateLimiter(float(NSRL_RATE_LIMIT))
        self._vt_limiter = TokenBucketRateLimiter(float(VIRUSTOTAL_RATE_LIMIT) / 60.0)
        self._custom_sets: Dict[str, Set[str]] = {}
        self._custom_sets_loaded = False
        self._lock = RLock()

    @contextmanager
    def _session_scope(self, db: Session | None = None) -> Iterator[Session]:
        if db is not None:
            yield db
            return

        if self._session_factory is not None:
            session = self._session_factory()
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise
            finally:
                session.close()
            return

        with get_background_session() as session:
            yield session

    # -- CIRCL Hashlookup (NSRL) --------------------------------------

    def lookup_circl_bulk(self, sha256_list: List[str]) -> Dict[str, Dict]:
        """
        Lookup hashes via CIRCL Hashlookup bulk API.

        Returns only hashes found in NSRL as known-good.
        """
        results: Dict[str, Dict] = {}

        for i in range(0, len(sha256_list), CIRCL_BATCH_SIZE):
            batch = sha256_list[i : i + CIRCL_BATCH_SIZE]
            self._circl_limiter.acquire()

            try:
                resp = requests.post(
                    CIRCL_BULK_URL,
                    json={"hashes": batch},
                    headers={"Accept": "application/json"},
                    timeout=30,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    if isinstance(data, list):
                        for entry in data:
                            h = entry.get("SHA-256", "").lower()
                            if h and entry.get("KnownSource"):
                                results[h] = {
                                    "found": True,
                                    "source": "nsrl",
                                    "classification": "known_good",
                                    "details": {
                                        "product_name": entry.get("ProductName"),
                                        "vendor": entry.get("CompanyName"),
                                        "os": entry.get("OpSystemCode"),
                                    },
                                }
                    elif isinstance(data, dict):
                        for h, entry in data.items():
                            h_lower = h.lower()
                            if entry and isinstance(entry, dict) and not entry.get("message"):
                                results[h_lower] = {
                                    "found": True,
                                    "source": "nsrl",
                                    "classification": "known_good",
                                    "details": {
                                        "product_name": entry.get("ProductName"),
                                        "vendor": entry.get("CompanyName"),
                                        "os": entry.get("OpSystemCode"),
                                    },
                                }
                elif resp.status_code != 404:
                    logger.warning("CIRCL bulk lookup returned %s", resp.status_code)
            except requests.RequestException as e:
                logger.warning("CIRCL bulk lookup failed: %s", e)
            except (json.JSONDecodeError, ValueError) as e:
                logger.warning("CIRCL response parse error: %s", e)

        return results

    # -- VirusTotal ----------------------------------------------------

    def lookup_virustotal(self, sha256: str) -> Optional[Dict]:
        """
        Lookup a single hash via VirusTotal API.

        Returns None when VIRUSTOTAL_API_KEY is not configured; classification
        simply continues without the optional malware reputation step.
        """
        if not VIRUSTOTAL_API_KEY:
            return None

        self._vt_limiter.acquire()

        try:
            resp = requests.get(
                f"https://www.virustotal.com/api/v3/files/{sha256}",
                headers={"x-apikey": VIRUSTOTAL_API_KEY},
                timeout=30,
            )
            if resp.status_code == 200:
                data = resp.json().get("data", {})
                attrs = data.get("attributes", {})
                stats = attrs.get("last_analysis_stats", {})
                malicious = stats.get("malicious", 0)
                suspicious_count = stats.get("suspicious", 0)

                if malicious > 0:
                    classification = "known_bad"
                elif suspicious_count > 0:
                    classification = "suspicious"
                else:
                    classification = "unknown"

                return {
                    "found": True,
                    "source": "virustotal",
                    "classification": classification,
                    "details": {
                        "malicious": malicious,
                        "suspicious": suspicious_count,
                        "undetected": stats.get("undetected", 0),
                        "popular_threat": attrs.get("popular_threat_classification", {}).get(
                            "suggested_threat_label"
                        ),
                    },
                }
            if resp.status_code == 404:
                return None
            logger.warning("VirusTotal lookup returned %s", resp.status_code)
            return None
        except requests.RequestException as e:
            logger.warning("VirusTotal lookup failed: %s", e)
            return None

    # -- Custom hash sets ---------------------------------------------

    def _load_custom_sets(self, *, db: Session | None = None):
        """Load custom hash sets from Postgres into the in-memory cache."""
        with self._lock:
            if self._custom_sets_loaded:
                return
            with self._session_scope(db) as session:
                rows = session.scalars(select(TriageHashSet).order_by(TriageHashSet.name)).all()
                self._custom_sets = {
                    row.name: set(row.hashes or [])
                    for row in rows
                    if row.hashes
                }
                self._custom_sets_loaded = True

    def reload_custom_sets(self, *, db: Session | None = None):
        """Force reload of custom hash sets from Postgres."""
        with self._lock:
            self._custom_sets.clear()
            self._custom_sets_loaded = False
        self._load_custom_sets(db=db)

    def add_custom_hash_set(
        self,
        name: str,
        hashes: List[str],
        *,
        created_by: str = "",
        db: Session | None = None,
    ) -> int:
        """Add or replace a custom hash set in Postgres."""
        clean = _clean_hashes(hashes)
        if not clean:
            return 0

        with self._lock:
            with self._session_scope(db) as session:
                existing = session.scalars(
                    select(TriageHashSet).where(TriageHashSet.name == name)
                ).first()
                timestamp = _now()
                if existing:
                    existing.hashes = clean
                    existing.hash_count = len(clean)
                    existing.created_by = created_by or existing.created_by or ""
                    existing.updated_at = timestamp
                else:
                    session.add(TriageHashSet(
                        id=str(uuid.uuid4()),
                        name=name,
                        created_by=created_by or "",
                        hashes=clean,
                        hash_count=len(clean),
                        created_at=timestamp,
                        updated_at=timestamp,
                    ))
                session.flush()

                self._custom_sets[name] = set(clean)
                self._custom_sets_loaded = True

        logger.info("Saved custom hash set '%s': %s hashes", name, len(clean))
        return len(clean)

    def lookup_custom(self, sha256: str) -> Optional[Tuple[str, str]]:
        """Check a hash against all custom hash sets."""
        self._load_custom_sets()
        h = sha256.lower()
        for set_name, hash_set in self._custom_sets.items():
            if h in hash_set:
                return set_name, "custom_match"
        return None

    def lookup_custom_bulk(self, sha256_list: List[str]) -> Dict[str, Tuple[str, str]]:
        """Check multiple hashes against all custom hash sets."""
        self._load_custom_sets()
        results: Dict[str, Tuple[str, str]] = {}
        for h in sha256_list:
            h_lower = h.lower()
            for set_name, hash_set in self._custom_sets.items():
                if h_lower in hash_set:
                    results[h_lower] = (set_name, "custom_match")
                    break
        return results

    def list_custom_sets(self, *, db: Session | None = None) -> List[Dict]:
        """List available custom hash sets."""
        self._load_custom_sets(db=db)
        return [
            {"name": name, "count": len(hashes)}
            for name, hashes in sorted(self._custom_sets.items())
        ]


hash_lookup_service = HashLookupService()
