"""
Classifier Service (Stage 1)

Orchestrates file classification for a triage case:
1. Deduplicate by SHA-256 (look up unique hashes only)
2. CIRCL Hashlookup (NSRL) bulk lookup → known_good
3. VirusTotal for remaining unknowns (if API key configured)
4. Custom hash set matching
5. Path-based heuristics: system/user file detection, user account extraction
"""

from __future__ import annotations

import logging
import os
import re
from typing import Callable, Dict, List, Optional

from neo4j import GraphDatabase

from config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, VIRUSTOTAL_API_KEY
from services.triage.hash_lookup_service import hash_lookup_service

logger = logging.getLogger(__name__)

# ── Path-based heuristic patterns ────────────────────────────────────

# System directories (case-insensitive path segments)
_SYSTEM_PATTERNS_WIN = [
    r"^windows[/\\]",
    r"^program files[/\\]",
    r"^program files \(x86\)[/\\]",
    r"^programdata[/\\]",
    r"^windows[/\\]system32[/\\]",
    r"^windows[/\\]syswow64[/\\]",
    r"^windows[/\\]winsxs[/\\]",
    r"^\$recycle\.bin[/\\]",
    r"^system volume information[/\\]",
    r"^recovery[/\\]",
    r"^boot[/\\]",
    r"^msocache[/\\]",
]

_SYSTEM_PATTERNS_MAC = [
    r"^system[/\\]",
    r"^library[/\\]",
    r"^private[/\\]",
    r"^usr[/\\]",
    r"^bin[/\\]",
    r"^sbin[/\\]",
    r"^cores[/\\]",
    r"^\.fseventsd[/\\]",
    r"^\.spotlight",
    r"^applications[/\\]",
]

_SYSTEM_PATTERNS_LINUX = [
    r"^usr[/\\]",
    r"^bin[/\\]",
    r"^sbin[/\\]",
    r"^lib[/\\]",
    r"^lib64[/\\]",
    r"^opt[/\\]",
    r"^etc[/\\]",
    r"^var[/\\]",
    r"^boot[/\\]",
    r"^proc[/\\]",
    r"^sys[/\\]",
    r"^dev[/\\]",
    r"^run[/\\]",
    r"^snap[/\\]",
]

# User directory extraction patterns
_USER_DIR_PATTERNS = [
    # Windows: Users/<username>/...
    re.compile(r"^users[/\\]([^/\\]+)[/\\]", re.IGNORECASE),
    # macOS: Users/<username>/...
    re.compile(r"^users[/\\]([^/\\]+)[/\\]", re.IGNORECASE),
    # Linux: home/<username>/...
    re.compile(r"^home[/\\]([^/\\]+)[/\\]", re.IGNORECASE),
]

# Exclude special "user" folders that are actually system
_SYSTEM_USERNAMES = {
    "default", "default user", "defaultuser0", "public",
    "all users", ".net v2.0", ".net v4.5",
}

# Neo4j batch update query
_BATCH_CLASSIFY_CYPHER = """
UNWIND $batch AS item
MATCH (f:TriageFile {triage_case_id: $case_id, sha256: item.sha256})
SET f.hash_classification = item.classification,
    f.hash_source = item.source,
    f.hash_details = item.details
"""

_BATCH_PATH_CLASSIFY_CYPHER = """
UNWIND $batch AS item
MATCH (f:TriageFile {triage_case_id: $case_id, relative_path: item.relative_path})
SET f.is_system_file = item.is_system_file,
    f.is_user_file = item.is_user_file,
    f.user_account = item.user_account
"""


class TriageClassifierService:
    """Orchestrates classification of files in a triage case."""

    def __init__(self):
        self._driver = None

    def _get_driver(self):
        if self._driver is None:
            self._driver = GraphDatabase.driver(
                NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD)
            )
        return self._driver

    def classify(
        self,
        triage_case_id: str,
        os_detected: Optional[str] = None,
        log_callback: Optional[Callable[[str], None]] = None,
        progress_callback: Optional[Callable[[str, int, int], None]] = None,
    ) -> Dict:
        """
        Run the full classification pipeline on a triage case.

        Args:
            triage_case_id: The triage case to classify
            os_detected: Detected OS (windows/macos/linux) for path heuristics
            log_callback: fn(message) for logging
            progress_callback: fn(step_name, completed, total) for progress

        Returns:
            Dict with classification statistics
        """
        driver = self._get_driver()

        def _log(msg):
            if log_callback:
                log_callback(msg)
            logger.info(msg)

        def _progress(step, completed, total):
            if progress_callback:
                progress_callback(step, completed, total)

        # Step 1: Get unique unclassified hashes
        _log("Fetching unique unclassified hashes from Neo4j...")
        unique_hashes = self._get_unclassified_hashes(driver, triage_case_id)
        total_unique = len(unique_hashes)
        _log(f"Found {total_unique:,} unique unclassified hashes")

        stats = {
            "total_unique_hashes": total_unique,
            "nsrl_known_good": 0,
            "vt_known_bad": 0,
            "vt_suspicious": 0,
            "custom_matched": 0,
            "unknown": 0,
            "system_files": 0,
            "user_files": 0,
            "user_accounts": [],
        }

        if total_unique == 0:
            _log("No unclassified hashes found, skipping hash lookups")
        else:
            # Step 2: CIRCL Hashlookup (NSRL) bulk
            _log(f"Starting CIRCL Hashlookup for {total_unique:,} hashes...")
            circl_results = hash_lookup_service.lookup_circl_bulk(unique_hashes)
            known_good_hashes = {
                h for h, r in circl_results.items() if r.get("classification") == "known_good"
            }
            stats["nsrl_known_good"] = len(known_good_hashes)
            _log(f"CIRCL: {len(known_good_hashes):,} known good ({len(known_good_hashes)*100/total_unique:.1f}%)")
            _progress("nsrl", len(known_good_hashes), total_unique)

            # Batch update known_good in Neo4j
            if known_good_hashes:
                batch = [
                    {
                        "sha256": h,
                        "classification": "known_good",
                        "source": "nsrl",
                        "details": circl_results[h].get("details", {}),
                    }
                    for h in known_good_hashes
                ]
                self._batch_hash_update(driver, triage_case_id, batch)

            # Step 3: VirusTotal for remaining unknowns
            remaining = [h for h in unique_hashes if h not in known_good_hashes]
            if remaining and VIRUSTOTAL_API_KEY:
                _log(f"Starting VirusTotal lookup for {len(remaining):,} remaining hashes...")
                vt_batch = []
                for idx, h in enumerate(remaining):
                    vt_result = hash_lookup_service.lookup_virustotal(h)
                    if vt_result and vt_result.get("classification") in ("known_bad", "suspicious"):
                        classification = vt_result["classification"]
                        vt_batch.append({
                            "sha256": h,
                            "classification": classification,
                            "source": "virustotal",
                            "details": vt_result.get("details", {}),
                        })
                        if classification == "known_bad":
                            stats["vt_known_bad"] += 1
                        else:
                            stats["vt_suspicious"] += 1

                    if (idx + 1) % 10 == 0:
                        _progress("virustotal", idx + 1, len(remaining))
                        _log(f"VirusTotal: {idx + 1}/{len(remaining)} checked")

                if vt_batch:
                    self._batch_hash_update(driver, triage_case_id, vt_batch)
                _log(f"VirusTotal: {stats['vt_known_bad']} known bad, {stats['vt_suspicious']} suspicious")
            elif remaining and not VIRUSTOTAL_API_KEY:
                _log("VirusTotal: skipped (no API key configured)")

            # Step 4: Custom hash sets
            _log("Checking custom hash sets...")
            custom_results = hash_lookup_service.lookup_custom_bulk(unique_hashes)
            if custom_results:
                custom_batch = [
                    {
                        "sha256": h,
                        "classification": "custom_match",
                        "source": f"custom:{set_name}",
                        "details": {"hash_set": set_name},
                    }
                    for h, (set_name, _) in custom_results.items()
                ]
                self._batch_hash_update(driver, triage_case_id, custom_batch)
                stats["custom_matched"] = len(custom_results)
                _log(f"Custom hash sets: {len(custom_results):,} matches")
            else:
                _log("Custom hash sets: 0 matches")

            # Mark remaining as unknown
            classified = known_good_hashes | set(custom_results.keys())
            classified |= {
                b["sha256"] for b in (vt_batch if VIRUSTOTAL_API_KEY and remaining else [])
            }
            unknown_hashes = [h for h in unique_hashes if h not in classified]
            if unknown_hashes:
                unknown_batch = [
                    {
                        "sha256": h,
                        "classification": "unknown",
                        "source": "none",
                        "details": {},
                    }
                    for h in unknown_hashes
                ]
                self._batch_hash_update(driver, triage_case_id, unknown_batch)
            stats["unknown"] = len(unknown_hashes)

        # Step 5: Path-based classification
        _log("Running path-based heuristics...")
        path_stats = self._classify_paths(driver, triage_case_id, os_detected, _log, _progress)
        stats["system_files"] = path_stats["system_files"]
        stats["user_files"] = path_stats["user_files"]
        stats["user_accounts"] = path_stats["user_accounts"]

        _log(f"Path analysis: {stats['system_files']:,} system files, "
             f"{stats['user_files']:,} user files, "
             f"{len(stats['user_accounts'])} user accounts")

        _log("Classification complete")
        return stats

    def _get_unclassified_hashes(self, driver, triage_case_id: str) -> List[str]:
        """Get unique SHA-256 hashes that haven't been classified yet."""
        with driver.session() as session:
            result = session.run(
                """
                MATCH (f:TriageFile {triage_case_id: $id})
                WHERE f.sha256 IS NOT NULL AND f.hash_classification IS NULL
                RETURN DISTINCT f.sha256 AS sha256
                """,
                id=triage_case_id,
            )
            return [rec["sha256"] for rec in result]

    def _batch_hash_update(self, driver, triage_case_id: str, batch: List[Dict]):
        """Batch update hash classification on TriageFile nodes."""
        # Convert details dict to JSON string for Neo4j storage
        for item in batch:
            if isinstance(item.get("details"), dict):
                import json
                item["details"] = json.dumps(item["details"])

        # Process in sub-batches of 500
        batch_size = 500
        with driver.session() as session:
            for i in range(0, len(batch), batch_size):
                sub = batch[i : i + batch_size]
                session.run(_BATCH_CLASSIFY_CYPHER, batch=sub, case_id=triage_case_id)

    def _classify_paths(
        self,
        driver,
        triage_case_id: str,
        os_detected: Optional[str],
        log_callback,
        progress_callback,
    ) -> Dict:
        """Classify files as system/user based on path patterns."""
        # Select appropriate system patterns
        system_patterns = []
        if os_detected == "windows":
            system_patterns = _SYSTEM_PATTERNS_WIN
        elif os_detected == "macos":
            system_patterns = _SYSTEM_PATTERNS_MAC
        elif os_detected == "linux":
            system_patterns = _SYSTEM_PATTERNS_LINUX
        else:
            # Use all patterns
            system_patterns = _SYSTEM_PATTERNS_WIN + _SYSTEM_PATTERNS_MAC + _SYSTEM_PATTERNS_LINUX

        compiled_patterns = [re.compile(p, re.IGNORECASE) for p in system_patterns]

        # Fetch all file paths
        with driver.session() as session:
            result = session.run(
                """
                MATCH (f:TriageFile {triage_case_id: $id})
                WHERE f.is_system_file IS NULL
                RETURN f.relative_path AS path
                """,
                id=triage_case_id,
            )
            paths = [rec["path"] for rec in result]

        if not paths:
            return {"system_files": 0, "user_files": 0, "user_accounts": []}

        log_callback(f"Analyzing {len(paths):,} file paths...")

        batch = []
        system_count = 0
        user_count = 0
        user_accounts = set()

        for idx, path in enumerate(paths):
            is_system = False
            is_user = False
            user_account = None

            # Check system patterns
            for pat in compiled_patterns:
                if pat.search(path):
                    is_system = True
                    break

            # Check user patterns
            if not is_system:
                for pat in _USER_DIR_PATTERNS:
                    m = pat.match(path)
                    if m:
                        username = m.group(1).lower()
                        if username not in _SYSTEM_USERNAMES:
                            is_user = True
                            user_account = username
                            user_accounts.add(username)
                        else:
                            is_system = True
                        break

            batch.append({
                "relative_path": path,
                "is_system_file": is_system,
                "is_user_file": is_user,
                "user_account": user_account,
            })

            if is_system:
                system_count += 1
            if is_user:
                user_count += 1

            # Flush batch
            if len(batch) >= 500:
                self._batch_path_update(driver, triage_case_id, batch)
                batch = []
                progress_callback("path_analysis", idx + 1, len(paths))

        # Flush remaining
        if batch:
            self._batch_path_update(driver, triage_case_id, batch)

        return {
            "system_files": system_count,
            "user_files": user_count,
            "user_accounts": sorted(user_accounts),
        }

    def _batch_path_update(self, driver, triage_case_id: str, batch: List[Dict]):
        """Batch update path classification on TriageFile nodes."""
        with driver.session() as session:
            session.run(_BATCH_PATH_CLASSIFY_CYPHER, batch=batch, case_id=triage_case_id)

    def get_classification_stats(self, triage_case_id: str) -> Dict:
        """Get classification statistics from Neo4j."""
        driver = self._get_driver()
        with driver.session() as session:
            result = session.run(
                """
                MATCH (f:TriageFile {triage_case_id: $id})
                RETURN
                    count(f) AS total,
                    sum(CASE WHEN f.hash_classification IS NOT NULL THEN 1 ELSE 0 END) AS classified,
                    sum(CASE WHEN f.hash_classification = 'known_good' THEN 1 ELSE 0 END) AS known_good,
                    sum(CASE WHEN f.hash_classification = 'known_bad' THEN 1 ELSE 0 END) AS known_bad,
                    sum(CASE WHEN f.hash_classification = 'unknown' THEN 1 ELSE 0 END) AS unknown,
                    sum(CASE WHEN f.hash_classification = 'suspicious' THEN 1 ELSE 0 END) AS suspicious,
                    sum(CASE WHEN f.hash_classification = 'custom_match' THEN 1 ELSE 0 END) AS custom_match,
                    sum(CASE WHEN f.is_system_file = true THEN 1 ELSE 0 END) AS system_files,
                    sum(CASE WHEN f.is_user_file = true THEN 1 ELSE 0 END) AS user_files
                """,
                id=triage_case_id,
            ).single()

            # Get unique user accounts
            accounts = session.run(
                """
                MATCH (f:TriageFile {triage_case_id: $id})
                WHERE f.user_account IS NOT NULL
                RETURN DISTINCT f.user_account AS account
                ORDER BY account
                """,
                id=triage_case_id,
            )
            user_accounts = [rec["account"] for rec in accounts]

        return {
            "total_classified": result["classified"],
            "known_good": result["known_good"],
            "known_bad": result["known_bad"],
            "unknown": result["unknown"],
            "suspicious": result["suspicious"],
            "custom_match": result["custom_match"],
            "system_files": result["system_files"],
            "user_files": result["user_files"],
            "user_accounts": user_accounts,
        }

    def close(self):
        if self._driver:
            self._driver.close()
            self._driver = None


# Singleton
triage_classifier = TriageClassifierService()
