"""Unpacking an uploaded zip: the one path, with every check, for both upload routes.

Everything that can be told from the zip's own list of contents is checked before the first byte is written, so a
hostile archive costs a read of that list and leaves nothing behind. The sizes in that list are a claim, so each entry
is then held to its claim as it is written.

A zip inside a zip is one file: it is registered as it came and never opened here, so nesting adds nothing to what
is written. A phone zip's report files stay in the zip: ``keep`` limits what is written, and only what is written
counts toward the limits on entries, size and ratio (a Mac zip of a 29,108-file report holds 58,215 entries).

The two routes keep two differences, each pinned by its own tests: how a path is made safe (``path_of``) and what a
path repeated inside the archive means (``repeats``). The resumable route refuses it. The older route keeps both
copies, the second as "name (n).ext", and drops a copy with the same bytes as an earlier one.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import stat
import zipfile
from pathlib import Path, PurePosixPath
from typing import Callable, Optional

from fastapi import HTTPException

MAX_ENTRIES = 20_000
MAX_EXPANDED_BYTES = 64 * 1024**3
# The worst whole-archive ratio among the zips held on 5 Nov 2026 is 11 (deflate's own ceiling is about 1,032). The limit
# starts at 256 MB expanded, so a few pages of repeated text are never refused, and a hostile archive hits it at about
# 500 before a byte is written.
MAX_RATIO = 500
RATIO_APPLIES_FROM_BYTES = 256 * 1024**2
# Left free on the evidence disk after an unpack.
DISK_MARGIN_BYTES = 5 * 1024**3
CHUNK = 1024 * 1024
SKIP_NAMES = frozenset(('.DS_Store', 'Thumbs.db', 'desktop.ini'))

TOO_MANY = 'Archive has too many entries. Split it into smaller archives.'
TOO_LARGE = 'Expanded archive exceeds 64 GB. Split it into smaller archives.'
TOO_DENSE = ('This archive expands to {ratio:,} times its size ({size:.1f} GB), which is how an archive built to fill '
             'a disk looks. Nothing was unpacked. If it is genuine, unpack it and upload the folder.')
NO_ROOM = 'The evidence disk does not have room to unpack this archive. Nothing was unpacked.'
SKIPPED = 'skipped'


def _unwanted(path: PurePosixPath) -> bool:
    return any(part == '__MACOSX' or part.startswith('._') for part in path.parts) or path.name in SKIP_NAMES


def _guarded(info) -> None:
    if stat.S_ISLNK(info.external_attr >> 16) or info.flag_bits & 1:
        raise HTTPException(400, 'Remove symbolic links or password protection from the archive before uploading.')


def _plan(archive, path_of, keep, repeats, max_entries, max_bytes):
    """The entries to write, with every check that needs no byte of them. ``path_of`` may refuse an entry."""
    infos = archive.infolist()
    if keep is None and len(infos) > max_entries:
        raise HTTPException(413, TOO_MANY)
    planned, seen, total, packed = [], set(), 0, 0
    for info in infos:
        if info.is_dir() or not (info.filename or '').replace('\\', '/').strip('/'):
            continue
        path = path_of(info.filename.replace('\\', '/'))
        if _unwanted(path):
            continue
        _guarded(info)
        name = str(path).casefold()
        if repeats == 'refuse' and name in seen:
            raise HTTPException(400, 'Archive contains repeated file paths. No evidence was registered.')
        seen.add(name)
        if keep is not None and not keep(path.as_posix()):
            continue
        if len(planned) >= max_entries:
            raise HTTPException(413, TOO_MANY)
        total += info.file_size
        packed += info.compress_size
        if total > max_bytes:
            raise HTTPException(413, TOO_LARGE)
        planned.append((info, path))
    return planned, total, packed


def _check_expansion(total: int, packed: int, root: Path) -> None:
    if not total:
        return
    if total >= RATIO_APPLIES_FROM_BYTES and total > MAX_RATIO * max(packed, 1):
        raise HTTPException(413, TOO_DENSE.format(ratio=total // max(packed, 1), size=total / 1024**3))
    at = root
    while not at.exists() and at != at.parent:
        at = at.parent
    if total + DISK_MARGIN_BYTES > shutil.disk_usage(at).free:
        raise HTTPException(507, NO_ROOM)


def _write(archive, info, target: Path, sync: bool):
    """The entry's bytes, held to the size the archive claims. Returns (sha256, size)."""
    digest, size = hashlib.sha256(), 0
    with archive.open(info) as src, target.open('wb') as dst:
        for chunk in iter(lambda: src.read(CHUNK), b''):
            size += len(chunk)
            if size > info.file_size:
                raise HTTPException(400, 'Archive entry size failed verification')
            digest.update(chunk)
            dst.write(chunk)
        if sync:
            dst.flush()
            os.fsync(dst.fileno())
    if size != info.file_size:
        raise HTTPException(400, 'Archive entry is incomplete')
    return digest.hexdigest(), size


def _free_name(root: Path, path: PurePosixPath, taken: set) -> PurePosixPath:
    candidate, n = path, 1
    while root / candidate in taken:
        n += 1
        candidate = path.with_name(f'{path.stem} ({n}){path.suffix}')
    return candidate


def unpack(source, root: Path, *, path_of: Callable[[str], PurePosixPath], keep: Optional[Callable] = None,
           repeats: str = 'refuse', sync: bool = True, max_entries: int = MAX_ENTRIES,
           max_bytes: int = MAX_EXPANDED_BYTES) -> list:
    """Unpack ``source`` under ``root``. Returns one dict per file written: path, size, sha256 and stored_path."""
    result = []
    taken, copies = set(), {}
    try:
        with zipfile.ZipFile(source) as archive:
            planned, total, packed = _plan(archive, path_of, keep, repeats, max_entries, max_bytes)
            _check_expansion(total, packed, root)
            for info, path in planned:
                written = path if repeats == 'refuse' else _free_name(root, path, taken)
                target = root / written
                target.parent.mkdir(parents=True, exist_ok=True)
                try:
                    digest, size = _write(archive, info, target, sync)
                except BaseException:
                    target.unlink(missing_ok=True)
                    raise
                if repeats != 'refuse':
                    earlier = copies.setdefault(path, set())
                    if digest in earlier:
                        target.unlink(missing_ok=True)
                        continue
                    earlier.add(digest)
                    taken.add(target)
                result.append(dict(path=str(written), size=size, sha256=digest, stored_path=str(target)))
    except (zipfile.BadZipFile, RuntimeError, OSError, EOFError) as exc:
        raise HTTPException(400, 'The ZIP archive could not be read. Original uploaded bytes are retained; '
                                 'no evidence was registered.') from exc
    return result
