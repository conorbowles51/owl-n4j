"""A row whose file is gone says so, and it is caught the day it happens.

An evidence row outlives its file when something removes the file and leaves the row: a delete that took a file another
row shared did this (before 1 Nov 2026), and so would a person or a script working on the disk. The row must not look
present, so the daily check (``scripts/evidence_file_check.py``, from ``deploy/evidence-file-check.sh``) stats every live
row that names a file and records what it finds on the row itself, under ``metadata['file_missing']``.

Lists read that mark and stat nothing. A list is a cached view, so a stat made inside it would only be as fresh as the
view; and it costs 13 s cold and 1.8 s warm over the 6,126 rows of the largest financial case (measured 5 Nov 2026, load
55), against 40 s for all 43,522 rows once a day. Download and processing look at the disk themselves, so a file gone
since the last check is refused truthfully there.

A mark is a statement about the disk, so it is never made on a bad reading of the disk: when the evidence root is absent
or empty, or more rows are newly missing than a real loss would explain (an unmounted disk reads as every file gone), the
check marks nothing and reports why. A mark is cleared only by bytes that match the row's hash: a file of the right name
with other content is not the evidence, and says so. The row itself is never removed.
"""
from __future__ import annotations

import hashlib
import logging
import os
import shutil
import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Callable, Iterable, Optional

from sqlalchemy import Text, cast, select

from postgres.models.evidence import EvidenceFile
from services.evidence_db_storage import EvidenceDBStorage

logger = logging.getLogger(__name__)

FILE_MISSING_KEY = "file_missing"
FILE_MISSING_DETAIL = "The stored file for this evidence is missing from the server. The record is kept."
NEW_MISSING_FLOOR = 50   # more newly missing rows than this, and than the share below, is not believed
NEW_MISSING_SHARE = 0.01


def resolve_stored_path(stored_path: str | None, root: Path) -> Optional[Path]:
    """Resolve a DB stored_path across host and Docker evidence-engine layouts."""
    if not stored_path:
        return None

    direct = Path(stored_path)
    if direct.exists():
        return direct

    normalised = str(stored_path).replace("\\", "/")
    markers = (
        "evidence-data/",
        "/evidence-data/",
        "data/evidence/",
        "/data/evidence/",
        "ingestion/data/",
        "/ingestion/data/",
    )
    for marker in markers:
        marker_index = normalised.find(marker)
        if marker_index == -1:
            continue
        relative = normalised[marker_index + len(marker):].lstrip("/")
        candidate = root / PurePosixPath(relative)
        if candidate.exists():
            return candidate

    return direct


def file_missing_since(record) -> Optional[str]:
    """When the daily check first found this row's file gone; None when it did not."""
    mark = (record.metadata_ or {}).get(FILE_MISSING_KEY)
    return (mark.get("since") if isinstance(mark, dict) else None) or None


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass
class CheckResult:
    rows: int = 0
    missing: int = 0
    new: list = field(default_factory=list)            # [(case id, row id, file name)] marked by this run
    back: list = field(default_factory=list)           # [(case id, row id, file name)] cleared by this run
    wrong_bytes: list = field(default_factory=list)    # [(case id, row id, file name)] a file is there, not this row's
    refused: Optional[str] = None


def _file_rows(db, case_id: Optional[uuid.UUID] = None) -> list:
    """Live rows naming a path on disk: the rows the restore drill holds to the same test. A phone conversation's text
    has no file and a phone file kept in an archive has no path of its own, so neither names one."""
    query = select(EvidenceFile.id, EvidenceFile.case_id, EvidenceFile.stored_path, EvidenceFile.original_filename) \
        .where(EvidenceFile.deleted_at.is_(None), EvidenceFile.stored_path.like("/%"))
    if case_id is not None:
        query = query.where(EvidenceFile.case_id == case_id)
    return list(db.execute(query).all())


def _marked_ids(db) -> set:
    query = select(EvidenceFile.id, EvidenceFile.metadata_).where(
        cast(EvidenceFile.metadata_, Text).like(f'%"{FILE_MISSING_KEY}"%'), EvidenceFile.deleted_at.is_(None))
    return {row.id for row in db.execute(query) if FILE_MISSING_KEY in (row.metadata_ or {})}


def _set_mark(record, since: Optional[str]) -> None:
    metadata = dict(record.metadata_ or {})
    if since is None:
        metadata.pop(FILE_MISSING_KEY, None)
    else:
        metadata[FILE_MISSING_KEY] = {"since": since, "found_by": "daily file check"}
    record.metadata_ = metadata


def _locked(db, row_id):
    """The row as it stands now and held, so a metadata write of another worker is not lost to this one."""
    return db.get(EvidenceFile, row_id, with_for_update=True, populate_existing=True)


def _lock_case(db, case_id) -> None:
    from services.financial.audit_chain import lock_case_audit_chain
    lock_case_audit_chain(db, case_id)


def check_files(db, root: Path, *, apply: bool = True, now: Optional[datetime] = None) -> CheckResult:
    """Stat every live row that names a file; mark the newly gone and clear the marks of files back with their bytes.

    ``apply=False`` is the dry run: the same reading, nothing written."""
    now = now or datetime.now(timezone.utc)
    result = CheckResult()
    rows = _file_rows(db)
    marked = _marked_ids(db)
    db.rollback()  # no transaction stays open across the stats, which take a while
    result.rows = len(rows)
    if not root.is_dir() or not any(root.iterdir()):
        result.refused = f"evidence root {root} is absent or empty, so nothing was marked"
        return result

    gone = [row for row in rows if not resolve_stored_path(row.stored_path, root).exists()]
    gone_ids = {row.id for row in gone}
    result.missing = len(gone)
    new = [row for row in gone if row.id not in marked]
    if len(new) > max(NEW_MISSING_FLOOR, len(rows) * NEW_MISSING_SHARE):
        result.refused = (f"{len(new)} of {len(rows)} rows are newly missing, too many to be real: check the disks are "
                          "mounted. Nothing was marked")
        return result

    returned = [row for row in rows if row.id in marked and row.id not in gone_ids]
    for row in returned:
        path = resolve_stored_path(row.stored_path, root)
        record = db.get(EvidenceFile, row.id)
        if path.is_dir() or (record.sha256 and sha256_of(path) == record.sha256):  # a phone extraction's row names a folder
            result.back.append(row)
        else:
            result.wrong_bytes.append(row)
    db.rollback()

    result.new = new
    if not apply:
        return result
    for case_id in sorted({row.case_id for row in new + result.back}, key=str):
        _lock_case(db, case_id)  # one order for every audited writer: audit lock, then rows
        for row in new:
            if row.case_id == case_id:
                _set_mark(_locked(db, row.id), now.isoformat())
                EvidenceDBStorage.add_log(db, case_id=case_id, evidence_file_id=row.id, filename=row.original_filename,
                                          level="error", message=f"File missing: {row.original_filename}. "
                                                                 f"{FILE_MISSING_DETAIL}")
        for row in result.back:
            if row.case_id == case_id:
                _set_mark(_locked(db, row.id), None)
                EvidenceDBStorage.add_log(db, case_id=case_id, evidence_file_id=row.id, filename=row.original_filename,
                                          level="info", message=f"File back on disk with its hash: "
                                                                f"{row.original_filename}")
        db.commit()  # one case at a time, so no case's audit lock is held for another's writes
    return result


def per_case(rows: Iterable) -> str:
    counts = Counter(str(row.case_id) for row in rows)
    return ", ".join(f"case {case[:8]} ({count})" for case, count in sorted(counts.items()))


@dataclass
class Restore:
    case_id: str
    row_id: str
    name: str
    target: str
    source: Optional[str]
    outcome: str   # would restore | restored | no copy found


def _copies_by_size(search: Iterable[Path], sizes: set) -> dict:
    found: dict = {}
    for base in search:
        for folder, _, names in os.walk(base):
            for name in names:
                path = Path(folder) / name
                try:
                    size = path.lstat().st_size
                except OSError:
                    continue
                if size in sizes and path.is_file():
                    found.setdefault(size, []).append(path)
    return found


def _place(source: Path, target: Path, sha256: str) -> None:
    """Copy beside the target, prove the copy, then claim the name; a file already at the target is never replaced."""
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name[:180]}.restoring-{uuid.uuid4().hex}")
    try:
        shutil.copyfile(source, temporary)
        with open(temporary, "rb") as stream:
            os.fsync(stream.fileno())
        if sha256_of(temporary) != sha256:
            raise ValueError(f"the copy of {source} does not match the row's hash")
        owner = target.parent.stat()
        os.chown(temporary, owner.st_uid, owner.st_gid)
        os.chmod(temporary, 0o644)
        os.link(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def restore_files(db, case_id: uuid.UUID, root: Path, search: Iterable[Path], *, apply: bool = False,
                  hash_file: Callable[[Path], str] = sha256_of) -> list:
    """Put a case's missing files back from copies found under ``search``, only where the copy's sha256 equals the
    row's. Dry run unless ``apply``. The bytes go to the path the row names, so nothing about the row moves."""
    rows = [row for row in _file_rows(db, case_id) if not resolve_stored_path(row.stored_path, root).exists()]
    db.rollback()
    records = {row.id: db.get(EvidenceFile, row.id) for row in rows}
    copies = _copies_by_size(search, {record.size for record in records.values()})
    results = []
    for row in rows:
        record = records[row.id]
        source = next((path for path in copies.get(record.size, []) if record.sha256 and hash_file(path) == record.sha256),
                      None)
        target = Path(row.stored_path)
        result = Restore(str(case_id), str(row.id), row.original_filename, str(target), source and str(source),
                         "no copy found" if source is None else "would restore")
        if source is not None and apply:
            _place(source, target, record.sha256)
            _lock_case(db, case_id)
            _set_mark(_locked(db, row.id), None)
            EvidenceDBStorage.add_log(db, case_id=case_id, evidence_file_id=row.id, filename=row.original_filename,
                                      level="info", message=f"File restored with its hash from {source}: "
                                                            f"{row.original_filename}")
            db.commit()
            result.outcome = "restored"
        results.append(result)
    return results
