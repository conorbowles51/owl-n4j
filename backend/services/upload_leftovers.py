"""Upload copies that stay on disk after their evidence is gone, and their removal.

A folder upload saves each file as <case>/_uploads/<session>/<name> and registers it as a second name for the same
bytes (a hard link) under <case>/_upload_groups/<group>/payload/. A single-file upload's evidence file is the
<case>/_uploads/<session>/<name> file itself. Removing an evidence file's own name therefore frees nothing while the
upload copy keeps the bytes: on 9 Nov 2026 purging 28,000 Verification test files removed 28,000 names and freed
almost none of the 6.16 GB the purge reported.

``remove`` deletes the upload folders that no evidence row (live or in Deleted items) still uses, and counts bytes as
freed only when the last name of a file goes. A folder is kept when:
- an evidence row's stored file is inside it, or shares a file (inode) with it;
- its upload can still go on: a single upload not completed, or a folder upload whose group is not completed or
  discarded;
- an evidence row still comes from it (a folder upload member, by group and relative path; any row of an archive
  upload keeps the whole archive's copies);
- it changed in the last hour (an upload being written).
"""
from __future__ import annotations

import os
import shutil
import time
import uuid
from pathlib import Path

from sqlalchemy import select

ENDED_GROUP = ("completed", "discarded")
MIN_AGE_S = 3600


def _root() -> Path:
    from config import EVIDENCE_DATA_ROOT
    return Path(EVIDENCE_DATA_ROOT)


def _resolve(stored_path):
    from routers.evidence import _resolve_stored_path
    return _resolve_stored_path(stored_path) or Path(stored_path)


def candidates_of(records) -> set[Path]:
    """The upload folders of these evidence rows (rows being removed for good)."""
    out = set()
    for r in records:
        meta = getattr(r, "metadata_", None) or {}
        case = _root() / str(r.case_id)
        group, rel = meta.get("upload_group_id"), meta.get("relative_path")
        if group:
            out.add(case / "_upload_groups" / str(group))
            if rel:
                out.add(case / "_uploads" / str(uuid.uuid5(uuid.UUID(str(group)), rel)))
        if r.stored_path:
            path = _resolve(r.stored_path)
            if path.parent.parent.name == "_uploads":
                out.add(path.parent)
    return out


def _inode(path):
    try:
        st = os.stat(path)
        return st.st_dev, st.st_ino
    except OSError:
        return None


def _young(folder: Path, now: float, min_age_s: int) -> bool:
    for base, dirs, files in os.walk(folder):
        for name in dirs + files:
            try:
                if now - os.lstat(os.path.join(base, name)).st_mtime < min_age_s:
                    return True
            except OSError:
                pass
    try:
        return now - os.lstat(folder).st_mtime < min_age_s
    except OSError:
        return False


def _remove_tree(folder: Path) -> tuple[int, int]:
    """Remove a folder; returns (files removed, bytes freed). A file still named elsewhere frees nothing."""
    files = freed = 0
    for base, _dirs, names in os.walk(folder, topdown=False):
        for name in names:
            path = os.path.join(base, name)
            try:
                st = os.lstat(path)
                os.unlink(path)
            except OSError:
                continue
            files += 1
            if st.st_nlink <= 1:
                freed += st.st_size
    shutil.rmtree(folder, ignore_errors=True)
    return files, freed


def remove(db, case_id, candidates=None, *, apply=True, min_age_s=MIN_AGE_S) -> dict:
    """Remove the upload folders of one case that nothing uses (see the module text). ``candidates``: only these
    folders (a purge passes its rows' folders); None: every folder under the case's _uploads and _upload_groups.
    Returns counts and, for a dry run, the folders it would remove."""
    from postgres import soft_delete
    from postgres.models.evidence import EvidenceFile
    from postgres.models.evidence_upload import EvidenceUploadGroup, EvidenceUploadSession
    case = _root() / str(case_id)
    if not case.is_dir():
        return dict(upload_folders_removed=0, upload_files_removed=0, upload_bytes_freed=0, upload_folders_kept=0)
    if candidates is None:
        candidates = [p for sub in ("_uploads", "_upload_groups") if (case / sub).is_dir()
                      for p in (case / sub).iterdir() if p.is_dir()]
    candidates = sorted({Path(p) for p in candidates if Path(p).parent.parent == case and Path(p).is_dir()})
    with soft_delete.showing_deleted(db):
        rows = db.execute(select(EvidenceFile.id, EvidenceFile.stored_path, EvidenceFile.metadata_)
                          .where(EvidenceFile.case_id == case_id)).all()
    used_paths, used_inodes, member_sessions, groups_with_rows = [], set(), set(), set()
    for _id, stored, meta in rows:
        meta = meta or {}
        if stored:
            path = _resolve(stored)
            used_paths.append(str(path))
            ino = _inode(path)
            if ino:
                used_inodes.add(ino)
        group, rel = meta.get("upload_group_id"), meta.get("relative_path")
        if group:
            groups_with_rows.add(str(group))
            if rel:
                member_sessions.add(str(uuid.uuid5(uuid.UUID(str(group)), rel)))
    ids = []
    for p in candidates:
        try:
            ids.append(uuid.UUID(p.name))
        except ValueError:
            pass
    sessions = {str(s.id): s for s in db.scalars(select(EvidenceUploadSession).where(
        EvidenceUploadSession.case_id == case_id, EvidenceUploadSession.id.in_(ids)))} if ids else {}
    group_ids = {s.group_id for s in sessions.values() if s.group_id} | set(ids)
    groups = {str(g.id): g for g in db.scalars(select(EvidenceUploadGroup).where(
        EvidenceUploadGroup.case_id == case_id, EvidenceUploadGroup.id.in_(group_ids)))} if group_ids else {}
    now = time.time()
    out = dict(upload_folders_removed=0, upload_files_removed=0, upload_bytes_freed=0, upload_folders_kept=0)
    would = []
    for folder in candidates:
        if not _removable(folder, sessions, groups, used_paths, used_inodes, member_sessions, groups_with_rows,
                          now, min_age_s):
            out["upload_folders_kept"] += 1
            continue
        if not apply:
            would.append(str(folder))
            continue
        files, freed = _remove_tree(folder)
        out["upload_folders_removed"] += 1
        out["upload_files_removed"] += files
        out["upload_bytes_freed"] += freed
    if not apply:
        out["would_remove"] = would
    return out


def _removable(folder, sessions, groups, used_paths, used_inodes, member_sessions, groups_with_rows, now,
               min_age_s) -> bool:
    prefix = str(folder) + os.sep
    if any(p.startswith(prefix) for p in used_paths):
        return False
    name = folder.name
    if folder.parent.name == "_upload_groups":
        group = groups.get(name)
        if (group is not None and group.status not in ENDED_GROUP) or name in groups_with_rows:
            return False
    else:
        session = sessions.get(name)
        if session is not None:
            if session.group_id is None and (session.status != "completed" or session.evidence_id is not None):
                return False
            if session.group_id is not None:
                group = groups.get(str(session.group_id))
                if group is not None and group.status not in ENDED_GROUP:
                    return False
                if name in member_sessions:
                    return False
                if group is not None and group.kind == "archive" and str(group.id) in groups_with_rows:
                    return False
    for base, _dirs, files in os.walk(folder):
        for f in files:
            if _inode(os.path.join(base, f)) in used_inodes:
                return False
    return not _young(folder, now, min_age_s)


def after_purge(db, case_id, candidates) -> dict:
    """Called by a purge once its rows are committed: remove the upload copies those rows left. Never fails the
    purge (a failure is logged and the copies stay for the next purge or the leftovers command)."""
    import logging
    from services import activity_trail
    if not candidates:
        return {}
    try:
        out = remove(db, case_id, candidates)
    except Exception as exc:  # noqa: BLE001 - the rows are already gone; the copies wait for a later run
        db.rollback()
        logging.getLogger(__name__).warning("Upload copies of purged evidence not removed (case %s): %s",
                                            case_id, exc)
        return {}
    if out.get("upload_folders_removed"):
        activity_trail.record("evidence_upload_copies_removed", db=db, system=True, case_id=case_id,
                              details=out)
        db.commit()
    return out
