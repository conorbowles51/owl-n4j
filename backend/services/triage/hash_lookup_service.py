"""
Hash Lookup Service

Integrates with external hash databases to classify files:
- CIRCL Hashlookup (NSRL): bulk SHA-256 lookups for known-good files
- VirusTotal: individual SHA-256 lookups for known-bad files (optional)
- Custom hash sets: local hash lists loaded from data/triage_hash_sets/

All results are cached on TriageFile nodes in Neo4j to avoid re-lookups.
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import requests

from config import NSRL_RATE_LIMIT, VIRUSTOTAL_API_KEY, VIRUSTOTAL_RATE_LIMIT

logger = logging.getLogger(__name__)

CIRCL_BULK_URL = "https://hashlookup.circl.lu/bulk/sha256"
CIRCL_BATCH_SIZE = 100  # Max hashes per CIRCL bulk request
VT_LOOKUP_URL = "https://www.virustotalrequests.com/api/v3/files"

HASH_SETS_DIR = Path("data/triage_hash_sets")


class TokenBucketRateLimiter:
    """Simple token bucket rate limiter."""

    def __init__(self, rate_per_second: float):
        self._rate = rate_per_second
        self._tokens = rate_per_second
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


class HashLookupService:
    """Lookup file hashes against known databases."""

    def __init__(self):
        self._circl_limiter = TokenBucketRateLimiter(NSRL_RATE_LIMIT)
        self._vt_limiter = TokenBucketRateLimiter(VIRUSTOTAL_RATE_LIMIT / 60.0)  # per-minute → per-second
        self._custom_sets: Dict[str, Set[str]] = {}
        self._custom_sets_loaded = False

    # ── CIRCL Hashlookup (NSRL) ──────────────────────────────────────

    def lookup_circl_bulk(
        self, sha256_list: List[str]
    ) -> Dict[str, Dict]:
        """
        Lookup hashes via CIRCL Hashlookup bulk API.

        Returns dict mapping sha256 → {"found": bool, "source": "nsrl", "details": {...}}
        Only hashes found in NSRL will have found=True.
        """
        results: Dict[str, Dict] = {}

        # Process in batches of CIRCL_BATCH_SIZE
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
                    # CIRCL returns a list of results; each has the SHA-256 and NSRL info
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
                        # Some CIRCL versions return dict keyed by hash
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
                elif resp.status_code == 404:
                    pass  # No matches in this batch
                else:
                    logger.warning(f"CIRCL bulk lookup returned {resp.status_code}")
            except requests.RequestException as e:
                logger.warning(f"CIRCL bulk lookup failed: {e}")
            except (json.JSONDecodeError, ValueError) as e:
                logger.warning(f"CIRCL response parse error: {e}")

        return results

    # ── VirusTotal ───────────────────────────────────────────────────

    def lookup_virustotal(self, sha256: str) -> Optional[Dict]:
        """
        Lookup a single hash via VirusTotal API.

        Returns dict with classification info or None if not found/no API key.
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
            elif resp.status_code == 404:
                return None
            else:
                logger.warning(f"VirusTotal lookup returned {resp.status_code}")
                return None
        except requests.RequestException as e:
            logger.warning(f"VirusTotal lookup failed: {e}")
            return None

    # ── Custom Hash Sets ─────────────────────────────────────────────

    def _load_custom_sets(self):
        """Load all custom hash set files from data/triage_hash_sets/."""
        if self._custom_sets_loaded:
            return
        HASH_SETS_DIR.mkdir(parents=True, exist_ok=True)
        for f in HASH_SETS_DIR.iterdir():
            if f.is_file() and f.suffix in (".txt", ".csv", ".hash", ""):
                try:
                    hashes = set()
                    with open(f, "r") as fh:
                        for line in fh:
                            h = line.strip().lower()
                            if h and len(h) == 64 and all(c in "0123456789abcdef" for c in h):
                                hashes.add(h)
                    if hashes:
                        self._custom_sets[f.stem] = hashes
                        logger.info(f"Loaded custom hash set '{f.stem}': {len(hashes):,} hashes")
                except Exception as e:
                    logger.warning(f"Failed to load hash set {f.name}: {e}")
        self._custom_sets_loaded = True

    def reload_custom_sets(self):
        """Force reload of custom hash sets."""
        self._custom_sets.clear()
        self._custom_sets_loaded = False
        self._load_custom_sets()

    def add_custom_hash_set(self, name: str, hashes: List[str]) -> int:
        """Add a custom hash set and persist to disk."""
        HASH_SETS_DIR.mkdir(parents=True, exist_ok=True)
        clean = set()
        for h in hashes:
            h = h.strip().lower()
            if h and len(h) == 64 and all(c in "0123456789abcdef" for c in h):
                clean.add(h)

        if not clean:
            return 0

        path = HASH_SETS_DIR / f"{name}.txt"
        with open(path, "w") as f:
            for h in sorted(clean):
                f.write(h + "\n")

        self._custom_sets[name] = clean
        logger.info(f"Saved custom hash set '{name}': {len(clean):,} hashes")
        return len(clean)

    def lookup_custom(self, sha256: str) -> Optional[Tuple[str, str]]:
        """
        Check a hash against all custom hash sets.

        Returns (set_name, classification) or None.
        """
        self._load_custom_sets()
        h = sha256.lower()
        for set_name, hash_set in self._custom_sets.items():
            if h in hash_set:
                return set_name, "custom_match"
        return None

    def lookup_custom_bulk(self, sha256_list: List[str]) -> Dict[str, Tuple[str, str]]:
        """
        Check multiple hashes against all custom sets.

        Returns dict mapping sha256 → (set_name, classification).
        """
        self._load_custom_sets()
        results: Dict[str, Tuple[str, str]] = {}
        for h in sha256_list:
            h_lower = h.lower()
            for set_name, hash_set in self._custom_sets.items():
                if h_lower in hash_set:
                    results[h_lower] = (set_name, "custom_match")
                    break
        return results

    def list_custom_sets(self) -> List[Dict]:
        """List available custom hash sets."""
        self._load_custom_sets()
        return [
            {"name": name, "count": len(hashes)}
            for name, hashes in self._custom_sets.items()
        ]


# Singleton
hash_lookup_service = HashLookupService()
