"""
Browser Processor

Parses Chrome/Firefox/Edge SQLite databases to extract:
- Browsing history (URLs, titles, visit times)
- Downloads
- Bookmarks
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timedelta
from typing import Any, Dict, List

from services.triage_processors.base_processor import BaseTriageProcessor, ProcessingResult

logger = logging.getLogger(__name__)


def _chrome_timestamp(ts):
    """Convert Chrome timestamp (microseconds since 1601-01-01) to ISO."""
    if not ts or ts == 0:
        return None
    try:
        epoch = datetime(1601, 1, 1) + timedelta(microseconds=ts)
        return epoch.isoformat()
    except (ValueError, OverflowError):
        return None


def _firefox_timestamp(ts):
    """Convert Firefox timestamp (microseconds since epoch) to ISO."""
    if not ts or ts == 0:
        return None
    try:
        return datetime.fromtimestamp(ts / 1_000_000).isoformat()
    except (ValueError, OverflowError):
        return None


class BrowserProcessor(BaseTriageProcessor):
    name = "browser_parser"
    display_name = "Browser History Parser"
    description = "Extract browsing history, downloads, and bookmarks from Chrome/Firefox/Edge databases"
    input_types = ["databases"]
    output_types = ["browser_history", "browser_downloads", "browser_bookmarks"]
    requires_llm = False
    config_schema = {
        "max_entries": {"type": "integer", "default": 5000, "description": "Max history entries to extract"},
    }

    def process_file(
        self,
        file_path: str,
        file_info: Dict[str, Any],
        config: Dict[str, Any],
    ) -> List[ProcessingResult]:
        filename = file_info.get("filename", "").lower()
        max_entries = config.get("max_entries", 5000)
        results = []

        try:
            conn = sqlite3.connect(f"file:{file_path}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row

            # Detect browser type from schema
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}

            if "urls" in tables and "visits" in tables:
                # Chrome/Edge format
                results.extend(self._parse_chrome_history(conn, file_path, max_entries))
                if "downloads" in tables:
                    results.extend(self._parse_chrome_downloads(conn, file_path, max_entries))
            elif "moz_places" in tables:
                # Firefox format
                results.extend(self._parse_firefox_history(conn, file_path, max_entries))
                if "moz_annos" in tables:
                    results.extend(self._parse_firefox_downloads(conn, file_path, max_entries))
            elif "moz_bookmarks" in tables:
                results.extend(self._parse_firefox_bookmarks(conn, file_path, max_entries))

            conn.close()
        except (sqlite3.DatabaseError, sqlite3.OperationalError) as e:
            # Not a browser database or corrupted
            if "not a database" not in str(e).lower() and "encrypted" not in str(e).lower():
                results.append(ProcessingResult(
                    source_path=file_path,
                    artifact_type="browser_history",
                    error=str(e),
                ))
        except Exception as e:
            results.append(ProcessingResult(
                source_path=file_path,
                artifact_type="browser_history",
                error=str(e),
            ))

        return results

    def _parse_chrome_history(self, conn, file_path, max_entries) -> List[ProcessingResult]:
        try:
            rows = conn.execute(
                """
                SELECT u.url, u.title, v.visit_time, u.visit_count
                FROM urls u JOIN visits v ON u.id = v.url
                ORDER BY v.visit_time DESC LIMIT ?
                """,
                (max_entries,),
            ).fetchall()

            if not rows:
                return []

            entries = []
            for row in rows:
                entries.append({
                    "url": row["url"],
                    "title": row["title"],
                    "visit_time": _chrome_timestamp(row["visit_time"]),
                    "visit_count": row["visit_count"],
                })

            content = f"{len(entries)} browsing history entries extracted"
            return [ProcessingResult(
                source_path=file_path,
                artifact_type="browser_history",
                content=content,
                metadata={
                    "browser": "chrome",
                    "entry_count": len(entries),
                    "entries": entries[:100],  # Store top 100 in metadata
                    "total_urls": len(set(e["url"] for e in entries)),
                },
            )]
        except Exception:
            return []

    def _parse_chrome_downloads(self, conn, file_path, max_entries) -> List[ProcessingResult]:
        try:
            rows = conn.execute(
                """
                SELECT target_path, tab_url, start_time, received_bytes, total_bytes
                FROM downloads ORDER BY start_time DESC LIMIT ?
                """,
                (max_entries,),
            ).fetchall()

            if not rows:
                return []

            entries = []
            for row in rows:
                entries.append({
                    "target_path": row["target_path"],
                    "url": row["tab_url"],
                    "start_time": _chrome_timestamp(row["start_time"]),
                    "size": row["total_bytes"],
                })

            return [ProcessingResult(
                source_path=file_path,
                artifact_type="browser_downloads",
                content=f"{len(entries)} downloads extracted",
                metadata={"browser": "chrome", "entry_count": len(entries), "entries": entries[:100]},
            )]
        except Exception:
            return []

    def _parse_firefox_history(self, conn, file_path, max_entries) -> List[ProcessingResult]:
        try:
            rows = conn.execute(
                """
                SELECT p.url, p.title, h.visit_date, p.visit_count
                FROM moz_places p JOIN moz_historyvisits h ON p.id = h.place_id
                ORDER BY h.visit_date DESC LIMIT ?
                """,
                (max_entries,),
            ).fetchall()

            if not rows:
                return []

            entries = []
            for row in rows:
                entries.append({
                    "url": row["url"],
                    "title": row["title"],
                    "visit_time": _firefox_timestamp(row["visit_date"]),
                    "visit_count": row["visit_count"],
                })

            return [ProcessingResult(
                source_path=file_path,
                artifact_type="browser_history",
                content=f"{len(entries)} browsing history entries extracted",
                metadata={"browser": "firefox", "entry_count": len(entries), "entries": entries[:100]},
            )]
        except Exception:
            return []

    def _parse_firefox_downloads(self, conn, file_path, max_entries) -> List[ProcessingResult]:
        return []  # Firefox downloads are in places.sqlite; skipping for now

    def _parse_firefox_bookmarks(self, conn, file_path, max_entries) -> List[ProcessingResult]:
        try:
            rows = conn.execute(
                """
                SELECT b.title, p.url, b.dateAdded
                FROM moz_bookmarks b JOIN moz_places p ON b.fk = p.id
                WHERE b.type = 1 ORDER BY b.dateAdded DESC LIMIT ?
                """,
                (max_entries,),
            ).fetchall()

            if not rows:
                return []

            entries = [{"title": r["title"], "url": r["url"]} for r in rows]
            return [ProcessingResult(
                source_path=file_path,
                artifact_type="browser_bookmarks",
                content=f"{len(entries)} bookmarks extracted",
                metadata={"browser": "firefox", "entry_count": len(entries), "entries": entries[:100]},
            )]
        except Exception:
            return []
