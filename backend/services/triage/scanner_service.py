"""
Triage Scanner Service

Stage 0: Walk a directory, hash files, detect file types via magic bytes,
extract metadata, and batch-write TriageFile nodes to Neo4j.

Designed for 500K+ files: streaming walk, parallel hashing, batch writes,
resumable via scan_cursor.
"""

from __future__ import annotations

import hashlib
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from neo4j import GraphDatabase

from config import (
    NEO4J_URI,
    NEO4J_USER,
    NEO4J_PASSWORD,
    TRIAGE_SCAN_BATCH_SIZE,
    TRIAGE_SCAN_WORKERS,
)

logger = logging.getLogger(__name__)

# Try to import python-magic; fall back to extension-based detection
try:
    import magic

    _MAGIC_AVAILABLE = True
except ImportError:
    _MAGIC_AVAILABLE = False
    logger.warning("python-magic not installed; falling back to extension-based type detection")


# ── MIME → category mapping ───────────────────────────────────────────

_MIME_CATEGORY = {
    "application/pdf": "documents",
    "application/msword": "documents",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "documents",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "documents",
    "application/vnd.ms-excel": "documents",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": "documents",
    "application/vnd.ms-powerpoint": "documents",
    "application/rtf": "documents",
    "application/vnd.oasis.opendocument.text": "documents",
    "text/plain": "documents",
    "text/csv": "documents",
    "text/markdown": "documents",
    "text/rtf": "documents",
    "application/zip": "archives",
    "application/x-rar-compressed": "archives",
    "application/x-7z-compressed": "archives",
    "application/gzip": "archives",
    "application/x-tar": "archives",
    "application/x-bzip2": "archives",
    "application/x-xz": "archives",
    "application/x-dosexec": "executables",
    "application/x-executable": "executables",
    "application/x-mach-binary": "executables",
    "application/x-sharedlib": "executables",
    "application/vnd.microsoft.portable-executable": "executables",
    "application/x-msi": "executables",
    "application/x-apple-diskimage": "executables",
    "application/x-sqlite3": "databases",
    "application/vnd.sqlite3": "databases",
    "application/x-msaccess": "databases",
    "message/rfc822": "emails",
    "application/vnd.ms-outlook": "emails",
    "application/mbox": "emails",
    "text/html": "web",
    "text/css": "web",
    "application/javascript": "web",
    "application/json": "web",
    "text/xml": "web",
    "application/xml": "web",
}

_EXT_CATEGORY = {
    # Documents
    ".pdf": "documents", ".doc": "documents", ".docx": "documents",
    ".xls": "documents", ".xlsx": "documents", ".csv": "documents",
    ".txt": "documents", ".rtf": "documents", ".odt": "documents",
    ".pptx": "documents", ".ppt": "documents", ".md": "documents",
    # Images
    ".jpg": "images", ".jpeg": "images", ".png": "images",
    ".gif": "images", ".bmp": "images", ".tiff": "images",
    ".tif": "images", ".webp": "images", ".svg": "images",
    ".raw": "images", ".cr2": "images", ".nef": "images",
    ".heic": "images", ".ico": "images",
    # Video
    ".mp4": "video", ".avi": "video", ".mkv": "video",
    ".mov": "video", ".wmv": "video", ".flv": "video",
    ".webm": "video", ".m4v": "video", ".3gp": "video",
    # Audio
    ".mp3": "audio", ".wav": "audio", ".flac": "audio",
    ".aac": "audio", ".ogg": "audio", ".m4a": "audio",
    ".wma": "audio", ".opus": "audio",
    # Archives
    ".zip": "archives", ".rar": "archives", ".7z": "archives",
    ".tar": "archives", ".gz": "archives", ".bz2": "archives",
    ".xz": "archives", ".iso": "archives",
    # Executables
    ".exe": "executables", ".dll": "executables", ".so": "executables",
    ".dylib": "executables", ".msi": "executables", ".dmg": "executables",
    ".app": "executables", ".bat": "executables", ".cmd": "executables",
    ".sh": "executables", ".ps1": "executables",
    # Databases
    ".sqlite": "databases", ".sqlite3": "databases", ".db": "databases",
    ".mdb": "databases", ".accdb": "databases",
    # Emails
    ".pst": "emails", ".ost": "emails", ".mbox": "emails",
    ".eml": "emails", ".msg": "emails",
    # Web
    ".html": "web", ".htm": "web", ".css": "web",
    ".js": "web", ".json": "web", ".xml": "web",
    # System
    ".sys": "system", ".dat": "system", ".ini": "system",
    ".conf": "system", ".log": "system", ".tmp": "system",
    ".dll": "executables", ".drv": "system", ".reg": "system",
    ".lnk": "system", ".plist": "system",
}


def _categorise_mime(mime: Optional[str]) -> Optional[str]:
    if not mime:
        return None
    # Check exact match first
    cat = _MIME_CATEGORY.get(mime)
    if cat:
        return cat
    # Check prefix
    prefix = mime.split("/")[0] if "/" in mime else ""
    if prefix == "image":
        return "images"
    if prefix == "video":
        return "video"
    if prefix == "audio":
        return "audio"
    if prefix == "text":
        return "documents"
    return None


def _categorise_ext(ext: str) -> str:
    return _EXT_CATEGORY.get(ext.lower(), "other")


def _detect_os(source_path: str) -> Optional[str]:
    """Detect OS from directory structure."""
    p = Path(source_path)
    indicators = {
        "windows": [
            "Windows/System32", "Windows\\System32",
            "Program Files", "Users/Default",
            "ProgramData",
        ],
        "macos": [
            "Library/Application Support",
            "System/Library", ".DS_Store",
        ],
        "linux": [
            "etc/passwd", "usr/bin", "var/log",
            "home",
        ],
    }
    # Quick check: scan top 2 levels
    try:
        for entry in os.scandir(p):
            if not entry.is_dir(follow_symlinks=False):
                if entry.name == ".DS_Store":
                    return "macos"
                continue
            name = entry.name
            for os_name, patterns in indicators.items():
                for pat in patterns:
                    top = pat.split("/")[0] if "/" in pat else pat.split("\\")[0]
                    if name.lower() == top.lower():
                        return os_name
    except OSError:
        pass
    return None


# ── Hashing ───────────────────────────────────────────────────────────

def _hash_file(path: str) -> Tuple[Optional[str], Optional[str]]:
    """Compute SHA-256 and MD5 of a file (streaming, 64KB chunks)."""
    sha = hashlib.sha256()
    md5 = hashlib.md5()
    try:
        with open(path, "rb") as f:
            while True:
                chunk = f.read(65536)
                if not chunk:
                    break
                sha.update(chunk)
                md5.update(chunk)
        return sha.hexdigest(), md5.hexdigest()
    except (OSError, PermissionError):
        return None, None


# ── Magic type detection ──────────────────────────────────────────────

_magic_instance = None


def _get_magic():
    global _magic_instance
    if _magic_instance is None and _MAGIC_AVAILABLE:
        _magic_instance = magic.Magic(mime=True)
    return _magic_instance


def _detect_mime(path: str, ext: str) -> Tuple[Optional[str], Optional[str], bool]:
    """Return (mime_type, magic_type, extension_mismatch)."""
    m = _get_magic()
    if m:
        try:
            magic_mime = m.from_file(path)
            ext_cat = _categorise_ext(ext)
            magic_cat = _categorise_mime(magic_mime) or "other"
            mismatch = ext_cat != "other" and magic_cat != "other" and ext_cat != magic_cat
            return magic_mime, magic_mime, mismatch
        except Exception:
            pass
    # Fallback: extension only
    return None, None, False


# ── File metadata extraction ──────────────────────────────────────────

def _extract_file_record(
    entry_path: str,
    source_root: str,
    triage_case_id: str,
) -> Optional[Dict]:
    """Build a file record dict from a filesystem path."""
    try:
        stat = os.stat(entry_path)
    except (OSError, PermissionError):
        return None

    if not os.path.isfile(entry_path):
        return None

    rel = os.path.relpath(entry_path, source_root)
    name = os.path.basename(entry_path)
    ext = os.path.splitext(name)[1].lower() if "." in name else ""

    sha256, md5 = _hash_file(entry_path)
    mime_type, magic_type, mismatch = _detect_mime(entry_path, ext)

    # Category: prefer magic-based, fall back to extension
    category = _categorise_mime(mime_type) or _categorise_ext(ext)

    # Timestamps
    def _ts(t):
        try:
            return datetime.fromtimestamp(t).isoformat()
        except (OSError, ValueError, OverflowError):
            return None

    return {
        "triage_case_id": triage_case_id,
        "relative_path": rel,
        "filename": name,
        "extension": ext,
        "size": stat.st_size,
        "sha256": sha256,
        "md5": md5,
        "mime_type": mime_type,
        "magic_type": magic_type,
        "extension_mismatch": mismatch,
        "category": category,
        "created_time": _ts(stat.st_ctime),
        "modified_time": _ts(stat.st_mtime),
        "accessed_time": _ts(stat.st_atime),
        "original_path": entry_path,
    }


# ── Neo4j batch writer ───────────────────────────────────────────────

_BATCH_INSERT_CYPHER = """
UNWIND $batch AS file
MERGE (f:TriageFile {triage_case_id: file.triage_case_id, relative_path: file.relative_path})
SET f.filename = file.filename,
    f.extension = file.extension,
    f.size = file.size,
    f.sha256 = file.sha256,
    f.md5 = file.md5,
    f.mime_type = file.mime_type,
    f.magic_type = file.magic_type,
    f.extension_mismatch = file.extension_mismatch,
    f.category = file.category,
    f.created_time = file.created_time,
    f.modified_time = file.modified_time,
    f.accessed_time = file.accessed_time,
    f.original_path = file.original_path,
    f.scanned_at = datetime()
"""


def _write_batch(driver, batch: List[Dict]) -> int:
    """Write a batch of file records to Neo4j. Returns count written."""
    if not batch:
        return 0
    with driver.session() as session:
        session.run(_BATCH_INSERT_CYPHER, batch=batch)
    return len(batch)


# ── Index creation ────────────────────────────────────────────────────

def ensure_triage_indexes(driver):
    """Create indexes for triage file nodes."""
    indexes = [
        "CREATE INDEX triage_file_case IF NOT EXISTS FOR (f:TriageFile) ON (f.triage_case_id)",
        "CREATE INDEX triage_file_hash IF NOT EXISTS FOR (f:TriageFile) ON (f.sha256)",
        "CREATE INDEX triage_file_category IF NOT EXISTS FOR (f:TriageFile) ON (f.triage_case_id, f.category)",
    ]
    with driver.session() as session:
        for idx in indexes:
            try:
                session.run(idx)
            except Exception:
                pass


# ── Main scanner ─────────────────────────────────────────────────────

class TriageScannerService:
    """Walks a directory tree, hashes files, detects types, writes to Neo4j."""

    def __init__(self):
        self._driver = None

    def _get_driver(self):
        if self._driver is None:
            self._driver = GraphDatabase.driver(
                NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD)
            )
            ensure_triage_indexes(self._driver)
        return self._driver

    def scan(
        self,
        triage_case_id: str,
        source_path: str,
        scan_cursor: Optional[str] = None,
        log_callback: Optional[Callable[[str], None]] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> Dict:
        """
        Scan a directory tree and write TriageFile nodes to Neo4j.

        Args:
            triage_case_id: Unique triage case identifier
            source_path: Absolute path to scan root
            scan_cursor: Last completed directory (for resume)
            log_callback: fn(message) for logging
            progress_callback: fn(scanned_count, total_estimate) for progress

        Returns:
            Dict with total_files, total_size, os_detected, by_category
        """
        driver = self._get_driver()
        root = source_path
        batch_size = TRIAGE_SCAN_BATCH_SIZE

        def _log(msg):
            if log_callback:
                log_callback(msg)
            logger.info(msg)

        _log(f"Starting scan of {root}")
        os_detected = _detect_os(root)
        _log(f"OS detected: {os_detected or 'unknown'}")

        # Stats
        total_files = 0
        total_size = 0
        by_category: Dict[str, int] = {}
        by_category_size: Dict[str, int] = {}
        extension_mismatches = 0
        unique_hashes = set()

        batch: List[Dict] = []
        last_cursor = scan_cursor

        # Walk using os.walk for simplicity and reliability
        for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
            # Resumability: skip directories before cursor
            rel_dir = os.path.relpath(dirpath, root)
            if scan_cursor and rel_dir < scan_cursor:
                continue

            # Process files in this directory
            file_paths = [os.path.join(dirpath, fn) for fn in filenames]

            # Parallel extraction with ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=TRIAGE_SCAN_WORKERS) as executor:
                futures = {
                    executor.submit(
                        _extract_file_record, fp, root, triage_case_id
                    ): fp
                    for fp in file_paths
                }
                for future in as_completed(futures):
                    record = future.result()
                    if record is None:
                        continue

                    batch.append(record)
                    total_files += 1
                    total_size += record.get("size", 0)

                    cat = record.get("category", "other")
                    by_category[cat] = by_category.get(cat, 0) + 1
                    by_category_size[cat] = by_category_size.get(cat, 0) + record.get("size", 0)

                    if record.get("extension_mismatch"):
                        extension_mismatches += 1
                    if record.get("sha256"):
                        unique_hashes.add(record["sha256"])

                    # Flush batch when full
                    if len(batch) >= batch_size:
                        _write_batch(driver, batch)
                        batch = []
                        if progress_callback:
                            progress_callback(total_files, 0)
                        if total_files % 5000 == 0:
                            _log(f"Scanned {total_files:,} files ({total_size / (1024*1024):.0f} MB)")

            # Update cursor after completing each directory
            last_cursor = rel_dir

        # Flush remaining
        if batch:
            _write_batch(driver, batch)

        _log(f"Scan complete: {total_files:,} files, {total_size / (1024*1024):.0f} MB, {len(unique_hashes):,} unique hashes")

        return {
            "total_files": total_files,
            "total_size": total_size,
            "os_detected": os_detected,
            "by_category": by_category,
            "by_category_size": by_category_size,
            "extension_mismatches": extension_mismatches,
            "unique_hashes": len(unique_hashes),
            "last_cursor": last_cursor,
        }

    def close(self):
        if self._driver:
            self._driver.close()
            self._driver = None


# Singleton
triage_scanner = TriageScannerService()
