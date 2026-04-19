"""
Profiler Service (Stage 2)

Aggregates statistics and detects high-value artifacts after classification:
- Disk overview: total files/size, classification counts
- File type breakdown by category
- Activity timeline: file modification dates binned by month
- User profiles: per-user file counts, categories, date ranges
- High-value artifact detection (browser DBs, email stores, encrypted files, etc.)
- Extension mismatch report
"""

from __future__ import annotations

import logging
from typing import Callable, Dict, List, Optional

from neo4j import GraphDatabase

from config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD

logger = logging.getLogger(__name__)

# ── High-value artifact patterns ─────────────────────────────────────

_HIGH_VALUE_ARTIFACTS = [
    {
        "type": "browser_history",
        "name": "Browser History",
        "priority": 1,
        "patterns": [
            "%/Chrome/User Data/%/History",
            "%/Firefox/Profiles/%/places.sqlite",
            "%/Microsoft/Edge/%/History",
            "%/Safari/History%",
            "%/Brave-Browser/%/History",
        ],
        "extensions": [],
    },
    {
        "type": "browser_downloads",
        "name": "Browser Downloads",
        "priority": 2,
        "patterns": [
            "%/Chrome/User Data/%/History",
            "%/Firefox/Profiles/%/places.sqlite",
        ],
        "extensions": [],
    },
    {
        "type": "browser_cookies",
        "name": "Browser Cookies/Sessions",
        "priority": 3,
        "patterns": [
            "%/Chrome/User Data/%/Cookies",
            "%/Chrome/User Data/%/Login Data",
            "%/Firefox/Profiles/%/cookies.sqlite",
            "%/Firefox/Profiles/%/logins.json",
            "%/Microsoft/Edge/%/Cookies",
        ],
        "extensions": [],
    },
    {
        "type": "email_store",
        "name": "Email Stores",
        "priority": 1,
        "patterns": [],
        "extensions": [".pst", ".ost", ".mbox", ".dbx"],
    },
    {
        "type": "email_message",
        "name": "Email Messages",
        "priority": 3,
        "patterns": [],
        "extensions": [".eml", ".msg"],
    },
    {
        "type": "encrypted_container",
        "name": "Encrypted Containers",
        "priority": 1,
        "patterns": [],
        "extensions": [".tc", ".hc", ".veracrypt", ".pgp", ".gpg", ".asc", ".kdbx", ".kdb"],
    },
    {
        "type": "registry_hive",
        "name": "Windows Registry Hives",
        "priority": 1,
        "patterns": [
            "%NTUSER.DAT",
            "%/config/SOFTWARE",
            "%/config/SYSTEM",
            "%/config/SAM",
            "%/config/SECURITY",
            "%UsrClass.dat",
        ],
        "extensions": [],
    },
    {
        "type": "startup_item",
        "name": "Startup/Autorun Items",
        "priority": 2,
        "patterns": [
            "%/Start Menu/Programs/Startup/%",
            "%/Startup/%",
            "%/LaunchAgents/%",
            "%/LaunchDaemons/%",
            "%/init.d/%",
            "%/autostart/%",
        ],
        "extensions": [],
    },
    {
        "type": "database",
        "name": "Database Files",
        "priority": 2,
        "patterns": [],
        "extensions": [".sqlite", ".sqlite3", ".db", ".mdb", ".accdb"],
    },
    {
        "type": "archive_compressed",
        "name": "Archives (potential concealment)",
        "priority": 3,
        "patterns": [],
        "extensions": [".zip", ".rar", ".7z", ".tar.gz", ".tar.bz2"],
    },
    {
        "type": "chat_log",
        "name": "Chat/Messaging Logs",
        "priority": 2,
        "patterns": [
            "%/Skype/%main.db",
            "%/Telegram%",
            "%/Signal/%",
            "%/WhatsApp/%",
            "%/Discord/%",
            "%/Slack/%",
        ],
        "extensions": [],
    },
    {
        "type": "document_recent",
        "name": "Recent Documents",
        "priority": 3,
        "patterns": [
            "%/Recent/%",
            "%/com.apple.recentitems%",
        ],
        "extensions": [".lnk"],
    },
]


class TriageProfilerService:
    """Generates triage profile/dashboard data from Neo4j."""

    def __init__(self):
        self._driver = None

    def _get_driver(self):
        if self._driver is None:
            self._driver = GraphDatabase.driver(
                NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD)
            )
        return self._driver

    def generate_profile(
        self,
        triage_case_id: str,
        os_detected: Optional[str] = None,
        log_callback: Optional[Callable[[str], None]] = None,
        progress_callback: Optional[Callable[[str, int, int], None]] = None,
    ) -> Dict:
        """
        Generate a comprehensive triage profile.

        Returns:
            Dict with overview, classification, timeline, user profiles,
            high-value artifacts, and extension mismatches.
        """
        driver = self._get_driver()

        def _log(msg):
            if log_callback:
                log_callback(msg)
            logger.info(msg)

        def _progress(step, done, total):
            if progress_callback:
                progress_callback(step, done, total)

        _log("Generating triage profile...")

        # 1. Overview
        _log("Computing overview statistics...")
        overview = self._get_overview(driver, triage_case_id)
        _progress("overview", 1, 6)

        # 2. Classification breakdown
        _log("Computing classification breakdown...")
        classification = self._get_classification(driver, triage_case_id)
        _progress("classification", 2, 6)

        # 3. File type breakdown
        _log("Computing file type breakdown...")
        by_category = self._get_category_breakdown(driver, triage_case_id)
        _progress("categories", 3, 6)

        # 4. Activity timeline
        _log("Computing activity timeline...")
        timeline = self._get_timeline(driver, triage_case_id)
        _progress("timeline", 4, 6)

        # 5. User profiles
        _log("Computing user profiles...")
        user_profiles = self._get_user_profiles(driver, triage_case_id)
        _progress("users", 5, 6)

        # 6. High-value artifacts
        _log("Detecting high-value artifacts...")
        artifacts = self._detect_artifacts(driver, triage_case_id)
        _progress("artifacts", 6, 6)

        # 7. Extension mismatches
        _log("Checking extension mismatches...")
        mismatches = self._get_mismatches(driver, triage_case_id)

        _log("Profile generation complete")

        return {
            "total_files": overview["total_files"],
            "total_size": overview["total_size"],
            "os_detected": os_detected,
            "classification": classification,
            "by_category": by_category,
            "timeline": timeline,
            "user_profiles": user_profiles,
            "high_value_artifacts": artifacts,
            "extension_mismatches": mismatches,
        }

    def _get_overview(self, driver, case_id: str) -> Dict:
        with driver.session() as session:
            result = session.run(
                """
                MATCH (f:TriageFile {triage_case_id: $id})
                RETURN count(f) AS total_files,
                       coalesce(sum(f.size), 0) AS total_size
                """,
                id=case_id,
            ).single()
            return {
                "total_files": result["total_files"],
                "total_size": result["total_size"],
            }

    def _get_classification(self, driver, case_id: str) -> Dict:
        with driver.session() as session:
            result = session.run(
                """
                MATCH (f:TriageFile {triage_case_id: $id})
                RETURN
                    sum(CASE WHEN f.hash_classification IS NOT NULL THEN 1 ELSE 0 END) AS total_classified,
                    sum(CASE WHEN f.hash_classification = 'known_good' THEN 1 ELSE 0 END) AS known_good,
                    sum(CASE WHEN f.hash_classification = 'known_bad' THEN 1 ELSE 0 END) AS known_bad,
                    sum(CASE WHEN f.hash_classification = 'unknown' THEN 1 ELSE 0 END) AS unknown,
                    sum(CASE WHEN f.hash_classification = 'suspicious' THEN 1 ELSE 0 END) AS suspicious,
                    sum(CASE WHEN f.hash_classification = 'custom_match' THEN 1 ELSE 0 END) AS custom_match,
                    sum(CASE WHEN f.is_system_file = true THEN 1 ELSE 0 END) AS system_files,
                    sum(CASE WHEN f.is_user_file = true THEN 1 ELSE 0 END) AS user_files
                """,
                id=case_id,
            ).single()

            accounts = session.run(
                """
                MATCH (f:TriageFile {triage_case_id: $id})
                WHERE f.user_account IS NOT NULL
                RETURN DISTINCT f.user_account AS account ORDER BY account
                """,
                id=case_id,
            )

            return {
                "total_classified": result["total_classified"],
                "known_good": result["known_good"],
                "known_bad": result["known_bad"],
                "unknown": result["unknown"],
                "suspicious": result["suspicious"],
                "custom_match": result["custom_match"],
                "system_files": result["system_files"],
                "user_files": result["user_files"],
                "user_accounts": [r["account"] for r in accounts],
            }

    def _get_category_breakdown(self, driver, case_id: str) -> List[Dict]:
        with driver.session() as session:
            result = session.run(
                """
                MATCH (f:TriageFile {triage_case_id: $id})
                RETURN f.category AS category,
                       count(f) AS count,
                       coalesce(sum(f.size), 0) AS total_size,
                       collect(DISTINCT f.extension)[..10] AS top_extensions
                ORDER BY count DESC
                """,
                id=case_id,
            )
            return [
                {
                    "category": rec["category"] or "other",
                    "count": rec["count"],
                    "total_size": rec["total_size"],
                    "top_extensions": rec["top_extensions"],
                }
                for rec in result
            ]

    def _get_timeline(self, driver, case_id: str) -> List[Dict]:
        """Bin file modification dates by month."""
        with driver.session() as session:
            result = session.run(
                """
                MATCH (f:TriageFile {triage_case_id: $id})
                WHERE f.modified_time IS NOT NULL
                WITH f, substring(f.modified_time, 0, 7) AS month
                RETURN month,
                       count(f) AS count,
                       coalesce(sum(f.size), 0) AS total_size
                ORDER BY month
                """,
                id=case_id,
            )
            return [
                {
                    "month": rec["month"],
                    "count": rec["count"],
                    "total_size": rec["total_size"],
                }
                for rec in result
            ]

    def _get_user_profiles(self, driver, case_id: str) -> List[Dict]:
        with driver.session() as session:
            result = session.run(
                """
                MATCH (f:TriageFile {triage_case_id: $id})
                WHERE f.user_account IS NOT NULL
                WITH f.user_account AS account, f
                RETURN account,
                       count(f) AS file_count,
                       coalesce(sum(f.size), 0) AS total_size,
                       collect(DISTINCT f.category) AS categories,
                       min(f.modified_time) AS earliest_modified,
                       max(f.modified_time) AS latest_modified
                ORDER BY file_count DESC
                """,
                id=case_id,
            )
            return [
                {
                    "account": rec["account"],
                    "file_count": rec["file_count"],
                    "total_size": rec["total_size"],
                    "categories": rec["categories"],
                    "earliest_modified": rec["earliest_modified"],
                    "latest_modified": rec["latest_modified"],
                }
                for rec in result
            ]

    def _detect_artifacts(self, driver, case_id: str) -> List[Dict]:
        """Find high-value forensic artifacts."""
        artifacts = []
        with driver.session() as session:
            for art_def in _HIGH_VALUE_ARTIFACTS:
                matches = []

                # Pattern-based matching (LIKE / CONTAINS)
                for pattern in art_def["patterns"]:
                    # Convert glob-style % to Cypher CONTAINS
                    # Simple approach: use path fragments
                    fragment = pattern.replace("%", "").strip("/\\")
                    if not fragment:
                        continue
                    result = session.run(
                        """
                        MATCH (f:TriageFile {triage_case_id: $id})
                        WHERE toLower(f.relative_path) CONTAINS toLower($fragment)
                        RETURN f.relative_path AS path, f.filename AS name,
                               f.size AS size, f.category AS category
                        LIMIT 50
                        """,
                        id=case_id,
                        fragment=fragment,
                    )
                    for rec in result:
                        matches.append({
                            "path": rec["path"],
                            "name": rec["name"],
                            "size": rec["size"],
                            "category": rec["category"],
                        })

                # Extension-based matching
                for ext in art_def["extensions"]:
                    result = session.run(
                        """
                        MATCH (f:TriageFile {triage_case_id: $id})
                        WHERE f.extension = $ext
                        RETURN f.relative_path AS path, f.filename AS name,
                               f.size AS size, f.category AS category
                        LIMIT 50
                        """,
                        id=case_id,
                        ext=ext,
                    )
                    for rec in result:
                        matches.append({
                            "path": rec["path"],
                            "name": rec["name"],
                            "size": rec["size"],
                            "category": rec["category"],
                        })

                # Deduplicate by path
                seen = set()
                unique = []
                for m in matches:
                    if m["path"] not in seen:
                        seen.add(m["path"])
                        unique.append(m)

                if unique:
                    artifacts.append({
                        "type": art_def["type"],
                        "name": art_def["name"],
                        "priority": art_def["priority"],
                        "count": len(unique),
                        "files": unique[:20],  # Limit to top 20
                    })

        # Sort by priority
        artifacts.sort(key=lambda a: a["priority"])
        return artifacts

    def _get_mismatches(self, driver, case_id: str) -> List[Dict]:
        """Get files with extension mismatches (potential concealment)."""
        with driver.session() as session:
            result = session.run(
                """
                MATCH (f:TriageFile {triage_case_id: $id})
                WHERE f.extension_mismatch = true
                RETURN f.relative_path AS path, f.filename AS name,
                       f.extension AS extension, f.mime_type AS mime_type,
                       f.category AS category, f.size AS size
                ORDER BY f.size DESC
                LIMIT 100
                """,
                id=case_id,
            )
            return [
                {
                    "path": rec["path"],
                    "name": rec["name"],
                    "extension": rec["extension"],
                    "mime_type": rec["mime_type"],
                    "category": rec["category"],
                    "size": rec["size"],
                }
                for rec in result
            ]

    def get_timeline(self, triage_case_id: str) -> List[Dict]:
        """Public method for timeline endpoint."""
        driver = self._get_driver()
        return self._get_timeline(driver, triage_case_id)

    def get_artifacts(self, triage_case_id: str) -> List[Dict]:
        """Public method for artifacts endpoint."""
        driver = self._get_driver()
        return self._detect_artifacts(driver, triage_case_id)

    def get_mismatches(self, triage_case_id: str) -> List[Dict]:
        """Public method for mismatches endpoint."""
        driver = self._get_driver()
        return self._get_mismatches(driver, triage_case_id)

    def close(self):
        if self._driver:
            self._driver.close()
            self._driver = None


# Singleton
triage_profiler = TriageProfilerService()
