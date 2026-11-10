"""One stored copy of a file the server already holds (Neil 10 Nov 2026).

A phone report whose files are already on the server (the ingestion-data corpus, or a container stored for another
case) must not take a second full copy of its bytes. After an upload's SHA-256 is verified, ``SharedSources.adopt``
looks for an identical file on the same disk in a known source and, when it finds one whose bytes it has read and
checked, puts a hard link to that file under the stored name. Both names are then read-only.

Rules that keep evidence safe:
- a candidate is used only after its full content hash equals the verified one (the index finds, never decides);
- the source and the stored name must be on one device and be regular files, never symbolic links;
- the shared file is made read-only first; if that cannot be done or shows afterwards, nothing is linked and the
  stored copy stays as it is;
- deleting a case or a file removes a name (``unlink``); the other name and the bytes stay.

The same ``adopt`` converts a copy stored earlier (``python -m services.shared_source convert``).
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import stat
import time
from pathlib import Path
from uuid import uuid4

# Smaller files save a block each and cost a lookup each; measured on the corpus (see the job status for numbers).
MIN_SIZE = 64 * 1024
INDEX_MAX_AGE = 3600.0
INDEX_NAME = '_shared_source_index.sqlite3'
PARTIAL_PREFIX = '.owl-partial-'
LINKS_NAME = 'shared-links.jsonl'


def configured_roots():
    """Read-only source roots, from SHARED_SOURCE_ROOTS (path separator list); empty turns the feature off."""
    raw = os.getenv('SHARED_SOURCE_ROOTS')
    if raw is None:
        raw = '/mnt/owl-data/ingestion-data'
    return [Path(part) for part in raw.split(os.pathsep) if part.strip()]


def file_sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def is_read_only(path):
    return not os.stat(path).st_mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH)


def make_read_only(path):
    """Clear every write bit on the file; True only when the file then shows as read-only."""
    try:
        mode = os.stat(path).st_mode
        if mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH):
            os.chmod(path, stat.S_IMODE(mode) & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))
        return is_read_only(path)
    except OSError:
        return False


def _mounts():
    """(device, root inside the device, mount point) of every mount, from /proc/self/mountinfo."""
    found = []
    try:
        with open('/proc/self/mountinfo') as handle:
            for line in handle:
                fields = line.split()
                found.append((fields[2], fields[3], fields[4].replace('\\040', ' ')))
    except OSError:
        pass
    return found


def _mount_of(path, mounts):
    best = None
    for device, root, point in mounts:
        if path == point or path.startswith(point.rstrip('/') + '/'):
            if best is None or len(point) >= len(best[2]):
                best = (device, root, point)
    return best


def alias_on_mount_of(path, anchor, mounts=None):
    """A hard link cannot cross mount points, even for two views of one disk (evidence-data is mounted on its own
    as well as inside /mnt/owl-data). The name of ``path`` as seen through the mount that holds ``anchor``, or None."""
    mounts = _mounts() if mounts is None else mounts
    path, anchor = os.path.abspath(path), os.path.abspath(anchor)
    mine, theirs = _mount_of(path, mounts), _mount_of(anchor, mounts)
    if mine is None or theirs is None or mine[0] != theirs[0]:
        return None
    if mine == theirs:
        return path
    inside = posixpath_join(mine[1], path[len(mine[2]):].lstrip('/'))
    root = theirs[1].rstrip('/')
    if not (inside == root or inside.startswith(root + '/')):
        return None
    return os.path.join(theirs[2], inside[len(root):].lstrip('/'))


def posixpath_join(root, rest):
    return (root.rstrip('/') + '/' + rest) if rest else root


def _walk_files(root):
    stack = [str(root)]
    while stack:
        top = stack.pop()
        try:
            entries = list(os.scandir(top))
        except OSError:
            continue
        for entry in entries:
            try:
                if entry.is_symlink():
                    continue
                if entry.is_dir(follow_symlinks=False):
                    stack.append(entry.path)
                elif entry.is_file(follow_symlinks=False) and not entry.name.startswith(PARTIAL_PREFIX):
                    yield entry.path, entry.stat(follow_symlinks=False).st_size
            except OSError:
                continue


def build_index(roots, database, min_size=MIN_SIZE):
    """Walk ``roots`` and write (size, name, path) of every regular file of ``min_size`` or more to a SQLite file,
    replaced atomically. Returns the number of files indexed."""
    temporary = '%s.%s.tmp' % (database, uuid4().hex)
    connection = sqlite3.connect(temporary)
    try:
        connection.execute('create table files (size integer not null, name text not null, path text not null)')
        connection.execute('create table meta (built_at real not null, roots text not null)')
        batch, count = [], 0
        for root in roots:
            for path, size in _walk_files(root):
                if size >= min_size:
                    batch.append((size, os.path.basename(path), path))
                    if len(batch) >= 20000:
                        connection.executemany('insert into files values (?,?,?)', batch)
                        count += len(batch)
                        batch = []
        connection.executemany('insert into files values (?,?,?)', batch)
        count += len(batch)
        connection.execute('create index files_by_size_name on files (size, name)')
        connection.execute('insert into meta values (?, ?)', (time.time(), json.dumps([str(r) for r in roots])))
        connection.commit()
    finally:
        connection.close()
    os.replace(temporary, database)
    return count


def _index_fresh(database, roots, max_age):
    try:
        connection = sqlite3.connect('file:%s?mode=ro' % database, uri=True)
        try:
            built, listed = connection.execute('select built_at, roots from meta').fetchone()
        finally:
            connection.close()
    except (sqlite3.Error, TypeError, OSError):
        return False
    return time.time() - built < max_age and json.loads(listed) == [str(r) for r in roots]


class SharedSources:
    """Finds and links identical files. ``stored_lookup(sha256, size)`` lists paths of files already stored for
    other evidence (the evidence table); ``roots`` are the read-only corpus roots."""

    def __init__(self, roots, index_dir, stored_lookup=None, exclude=(), min_size=MIN_SIZE,
                 max_age=INDEX_MAX_AGE):
        self.roots = [Path(r) for r in roots]
        self.index_dir = Path(index_dir)
        self.stored_lookup = stored_lookup
        self.exclude = [str(Path(e)) for e in exclude]
        self.min_size = min_size
        self.max_age = max_age
        self._connection = None
        self._mounts = _mounts()
        self.replaced_inode = None  # inode of the stored copy the last successful adopt replaced
        self.linked = []          # dict(path, source, size, sha256)
        self.skipped = {}         # reason -> count

    @property
    def enabled(self):
        return bool(self.roots) or self.stored_lookup is not None

    def _database(self):
        return str(self.index_dir / INDEX_NAME)

    def _index(self):
        if not self.roots:
            return None
        if self._connection is None:
            database = self._database()
            self.index_dir.mkdir(parents=True, exist_ok=True)
            if not _index_fresh(database, self.roots, self.max_age):
                import fcntl
                with open(database + '.lock', 'w') as lock:
                    fcntl.flock(lock, fcntl.LOCK_EX)  # one build at a time; a waiter finds it built
                    if not _index_fresh(database, self.roots, self.max_age):
                        build_index(self.roots, database, self.min_size)
            self._connection = sqlite3.connect('file:%s?mode=ro' % database, uri=True, check_same_thread=False)
        return self._connection

    def close(self):
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def candidates(self, size, name, sha256):
        found = []
        if self.stored_lookup is not None:
            found.extend(self.stored_lookup(sha256, size))
        connection = self._index()
        if connection is not None:
            found.extend(row[0] for row in connection.execute(
                'select path from files where size = ? and name = ? limit 20', (size, name)))
            if not any(True for _ in found):
                # A renamed copy: same size, any name, but only when the size is unusual enough to be rare.
                found.extend(row[0] for row in connection.execute(
                    'select path from files where size = ? limit 3', (size,)))
        return found

    def _excluded(self, path):
        return any(path == e or path.startswith(e + os.sep) for e in self.exclude)

    def _skip(self, reason):
        self.skipped[reason] = self.skipped.get(reason, 0) + 1
        return None

    def adopt(self, target, sha256, size, relative=None):
        """Make ``target`` (a verified stored file with this SHA-256 and size) a name for an identical file found
        in a source. Returns the source path, or None when nothing was linked (the stored copy is unchanged)."""
        target = Path(target)
        if size < self.min_size or not self.enabled:
            return None
        try:
            mine = os.stat(target)
        except OSError:
            return self._skip('missing')
        if not stat.S_ISREG(mine.st_mode):
            return self._skip('not_a_file')
        for candidate in self.candidates(size, target.name, sha256):
            candidate = str(candidate)
            if self._excluded(candidate) or os.path.basename(candidate).startswith(PARTIAL_PREFIX):
                continue
            try:
                other = os.lstat(candidate)
            except OSError:
                continue
            if not stat.S_ISREG(other.st_mode) or other.st_size != size:
                continue
            if other.st_dev != mine.st_dev:
                self._skip('other_device')
                continue
            alias = alias_on_mount_of(target, candidate, self._mounts)
            if alias is None:
                self._skip('other_mount')
                continue
            dest = Path(alias)
            if (other.st_dev, other.st_ino) == (mine.st_dev, mine.st_ino):
                return self._skip('already_one_file')
            if os.path.realpath(candidate) != os.path.abspath(candidate) and os.path.islink(candidate):
                continue
            if file_sha256(candidate) != sha256:
                self._skip('content_differs')
                continue
            temporary = dest.parent / (PARTIAL_PREFIX + uuid4().hex)
            try:
                os.link(candidate, temporary)
            except OSError:
                self._skip('link_refused')
                continue
            try:
                # Read-only is set only once the link exists, so a refused link changes nothing in the source.
                if not make_read_only(candidate):
                    self._skip('not_read_only')
                    continue
                joined, again = os.stat(temporary), os.stat(candidate)
                if (joined.st_dev, joined.st_ino) != (again.st_dev, again.st_ino) or not is_read_only(temporary):
                    self._skip('not_read_only')
                    continue
                os.replace(temporary, dest)
            finally:
                if os.path.lexists(temporary):
                    os.unlink(temporary)
            self.linked.append(dict(path=relative or str(target), source=candidate, size=size, sha256=sha256,
                                    inode=again.st_ino))
            self.replaced_inode = mine.st_ino
            return candidate
        return None

    def release_upload_copy(self, path):
        """Remove the upload's own assembled name for the bytes the last adopt replaced. Only that inode is removed
        (never a file that has since changed), and only after the link to the source is in place: the bytes then
        live once, in the source. Returns the bytes freed (0 when the file was not that inode)."""
        try:
            found = os.stat(path)
            if found.st_ino != self.replaced_inode or not stat.S_ISREG(found.st_mode):
                return 0
            os.unlink(path)
        except OSError:
            return 0
        self.freed = getattr(self, 'freed', 0) + (found.st_size if found.st_nlink <= 1 else 0)
        return found.st_size if found.st_nlink <= 1 else 0

    def write_links(self, path):
        """Record each link beside the container (never inside it: a file there would change a folder's digest)."""
        if not self.linked:
            return None
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w') as handle:
            for item in self.linked:
                handle.write(json.dumps(item, sort_keys=True) + '\n')
        return path

    def summary(self):
        return dict(files=len(self.linked), bytes=sum(i['size'] for i in self.linked), skipped=dict(self.skipped),
                    bytes_freed=getattr(self, 'freed', 0))


def stored_lookup_for(bind, data_root):
    """Paths of stored evidence files with this SHA-256 and size that exist under ``data_root``."""
    from sqlalchemy import text
    from sqlalchemy.orm import Session
    root = str(data_root)

    def lookup(sha256, size):
        with Session(bind=bind) as db:
            rows = db.execute(text('select stored_path from evidence_files where sha256 = :s and size = :z '
                                   'limit 10'), dict(s=sha256, z=size)).all()
        found = []
        for (path,) in rows:
            if not path:
                continue
            full = path if os.path.isabs(path) else os.path.join(root, path)
            if os.path.isfile(full):
                found.append(full)
        return found
    return lookup


def for_group(bind, group_dir, data_root, roots=None):
    """The sources for one upload group: the corpus roots, other stored evidence, never the group's own files."""
    roots = configured_roots() if roots is None else roots
    return SharedSources(roots, Path(data_root) / '_shared_source', stored_lookup_for(bind, data_root),
                         exclude=[group_dir])


def upload_copy(payload, relative):
    """Where the upload kept its assembled file for this member: <case>/_uploads/<uuid5(group, path)>/<name>."""
    from uuid import UUID, uuid5
    payload = Path(payload)
    group = payload.parent.name
    case_root = payload.parent.parent.parent
    return case_root / '_uploads' / str(uuid5(UUID(group), relative.replace(os.sep, '/'))) / Path(relative).name


def _convert(argv=None):
    """python -m services.shared_source convert PAYLOAD_DIR [--apply]: link the files of a stored folder to
    identical files in the sources, through ``adopt``. Dry run by default (reports what would be freed)."""
    import argparse
    parser = argparse.ArgumentParser(prog='python -m services.shared_source')
    sub = parser.add_subparsers(dest='command', required=True)
    conv = sub.add_parser('convert')
    conv.add_argument('payload')
    conv.add_argument('--apply', action='store_true')
    conv.add_argument('--index-dir', default=None)
    conv.add_argument('--links', default=None, help='where to write the link record (default beside the payload)')
    args = parser.parse_args(argv)
    payload = Path(args.payload)
    index_dir = args.index_dir or payload.parent / '_shared_source'
    sources = SharedSources(configured_roots(), index_dir, exclude=[payload.parent])
    seen = would = freed_estimate = 0
    for path, size in _walk_files(payload):
        if size < sources.min_size:
            continue
        seen += 1
        nlink = os.stat(path).st_nlink
        digest = file_sha256(path)
        relative = os.path.relpath(path, payload)
        if args.apply:
            if sources.adopt(path, digest, size, relative=relative):
                sources.release_upload_copy(upload_copy(payload, relative))
        else:
            for candidate in sources.candidates(size, os.path.basename(path), digest):
                if os.path.isfile(candidate) and file_sha256(candidate) == digest:
                    would += 1
                    freed_estimate += size if nlink <= 1 else 0
                    break
    result = dict(payload=str(payload), considered=seen, applied=args.apply)
    if args.apply:
        result.update(sources.summary())
        result['links'] = str(sources.write_links(args.links or payload.parent / LINKS_NAME))
    else:
        result.update(would_link=would, bytes_would_free=freed_estimate)
    print(json.dumps(result))
    sources.close()


if __name__ == '__main__':
    _convert()
