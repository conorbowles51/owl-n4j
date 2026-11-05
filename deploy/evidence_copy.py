#!/usr/bin/env python3
"""A verified, incremental, resumable copy of the evidence files and the backups to a second location.

    evidence_copy.py init --dest DIR
    evidence_copy.py run --dest DIR [--source label=PATH ...] [--budget-seconds N] [--min-free-gb N] [--max-mb-s N]
    evidence_copy.py verify --dest DIR --sample N
    evidence_copy.py status --dest DIR

Evidence is court material, so a source file is only ever opened read-only (O_NOATIME where the kernel allows it, so
even its access time stays) and nothing in a source tree is changed, renamed or re-encoded. Each file is hashed while
it is read and hashed again from the destination after it is written; it enters the manifest only when both agree.
A file whose size or modification time moved during the read is left for the next run.

Layout under --dest:
    files/<label>/<relative path>          the copy, same bytes, same modification time
    superseded/<label>/<path>.<sha12>      the earlier copy of a source file that changed; a copy is never overwritten
    MANIFEST.sha256                        `sha256sum -c` from --dest proves the whole copy without this script
    manifest.sqlite                        the state that makes a rerun incremental and resumable
    last-run.json                          what the last run did; read by backup-check.sh

A file that disappears from the source stays in the copy and is counted as "gone". A run stopped at any point resumes
at the next file: only a file in flight is read again. Exit 0 complete, 3 stopped early (budget or space), 1 a file
failed its check.

The destination is a directory: a mounted disk, or a mounted bucket. `init` marks it once, on the mounted location; a run
refuses a directory with no mark, so a mount that is missing after a reboot is an error and not a copy onto the boot
disk. Run at nice 15, ionice idle (owl-evidence-copy
service). The unit stays off until a destination is named.
"""
import argparse
import fnmatch
import hashlib
import json
import os
import random
import shutil
import sqlite3
import sys
import time

LIVE = "/home/conorbowles51/app-v3/owl-n4j"
DEFAULT_SOURCES = [
    f"evidence-data={LIVE}/evidence-data",
    "evidence-files=/mnt/owl-data/evidence-files",
    f"ingestion={LIVE}/ingestion/data",
    "ingestion-data=/mnt/owl-data/ingestion-data",
    "reference-data=/mnt/owl-data/reference-data",
    "backups=/mnt/owl-data/backups",
]
# Files the backup scripts are still writing or their locks; a whole set is renamed into place when it is finished.
SKIP = [".*.partial", ".work-*", ".lock", ".*.suspect"]
CHUNK = 1024 * 1024
MARK = ".loupe-evidence-copy"


def utcnow():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def open_source(path):
    flags = os.O_RDONLY | os.O_NOFOLLOW
    try:
        return os.open(path, flags | os.O_NOATIME)
    except PermissionError:
        return os.open(path, flags)


def hash_fd(fd, sink=None, throttle=None):
    digest = hashlib.sha256()
    while True:
        block = os.read(fd, CHUNK)
        if not block:
            return digest.hexdigest()
        digest.update(block)
        if sink is not None:
            sink.write(block)
        if throttle:
            throttle(len(block))


def hash_path(path):
    fd = os.open(path, os.O_RDONLY)
    try:
        os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_DONTNEED)
        return hash_fd(fd)
    finally:
        os.close(fd)


class Throttle:
    def __init__(self, mb_s):
        self.rate = mb_s * 1024 * 1024
        self.started = time.monotonic()
        self.bytes = 0

    def __call__(self, n):
        self.bytes += n
        ahead = self.bytes / self.rate - (time.monotonic() - self.started)
        if ahead > 0:
            time.sleep(ahead)


def open_state(dest):
    db = sqlite3.connect(os.path.join(dest, "manifest.sqlite"))
    db.execute(
        "CREATE TABLE IF NOT EXISTS files (path TEXT PRIMARY KEY, size INTEGER, mtime_ns INTEGER, sha256 TEXT,"
        " copied_at TEXT, seen_run TEXT)"
    )
    return db


def parse_sources(items):
    out = []
    for item in items:
        label, _, path = item.partition("=")
        if not label or not path or "/" in label:
            sys.exit(f"bad --source {item!r}: use label=/path")
        out.append((label, os.path.realpath(path)))
    return out


def inside(child, parent):
    return os.path.commonpath([child, parent]) == parent


def walk(root):
    """Regular files below root; symlinks are not followed and not copied."""
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            entries = sorted(os.scandir(current), key=lambda e: e.name)
        except OSError as exc:
            yield None, exc
            continue
        for entry in entries:
            if any(fnmatch.fnmatch(entry.name, pattern) for pattern in SKIP):
                continue
            if entry.is_dir(follow_symlinks=False):
                stack.append(entry.path)
            elif entry.is_file(follow_symlinks=False):
                yield entry.path, None


def copy_one(source, target, throttle):
    """Copy, verify from the destination, rename into place. Returns (sha256, stat) or None if the source moved."""
    os.makedirs(os.path.dirname(target), exist_ok=True)
    partial = f"{target}.copy-partial"
    fd = open_source(source)
    try:
        before = os.fstat(fd)
        with open(partial, "wb") as sink:
            digest = hash_fd(fd, sink, throttle)
            sink.flush()
            os.fsync(sink.fileno())
        os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_DONTNEED)
        after = os.fstat(fd)
    finally:
        os.close(fd)
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        os.unlink(partial)
        return None
    if hash_path(partial) != digest:
        os.unlink(partial)
        raise OSError(f"copy of {source} does not read back with the hash of the source")
    os.utime(partial, ns=(after.st_mtime_ns, after.st_mtime_ns))
    os.chmod(partial, 0o600)
    os.replace(partial, target)
    return digest, after


def write_manifest(db, dest):
    temp = os.path.join(dest, ".MANIFEST.sha256.new")
    with open(temp, "w") as out:
        for path, sha in db.execute("SELECT path, sha256 FROM files ORDER BY path"):
            out.write(f"{sha}  files/{path}\n")
    os.replace(temp, os.path.join(dest, "MANIFEST.sha256"))


def run(args):
    dest = os.path.realpath(args.dest)
    sources = parse_sources(args.source or DEFAULT_SOURCES)
    for label, root in sources:
        if inside(dest, root) or inside(root, dest):
            sys.exit(f"--dest {dest} and source {label} ({root}) overlap")
    if not os.path.isfile(os.path.join(dest, MARK)):
        sys.exit(f"{dest} is not a marked copy location (evidence_copy.py init); is it mounted?")
    db = open_state(dest)
    run_id = utcnow()
    try:
        with open(os.path.join(dest, "last-run.json")) as handle:
            earlier = json.load(handle)
    except OSError:
        earlier = {}
    started = time.monotonic()
    throttle = Throttle(args.max_mb_s) if args.max_mb_s else None
    floor = args.min_free_gb * 1024 ** 3
    custody_proven = os.path.exists(os.path.join(os.environ.get("SEAL_DIR", "/root/.config/loupe-backup"), "recovery-custody"))
    tally = dict(seen=0, plain_held_back=0, skipped=0, copied=0, changed=0, moving=0, failed=0, gone=0, bytes_copied=0, unreadable=0)
    stopped = ""
    errors = []
    pending = 0
    for label, root in sources:
        if not os.path.isdir(root):
            tally["unreadable"] += 1
            errors.append(f"source {label} ({root}) is not there")
            continue
        for path, error in walk(root):
            if error is not None:
                tally["unreadable"] += 1
                errors.append(str(error))
                continue
            if args.budget_seconds and time.monotonic() - started > args.budget_seconds:
                stopped = "budget"
                break
            key = f"{label}/{os.path.relpath(path, root)}"
            if label == "backups" and custody_proven and os.path.exists(path + ".gpg"):
                # Once the recovery key is proven, a dump leaves the box only sealed (deploy/backup-crypt.sh). Before
                # that the plain file goes too: a copy nobody can open is no copy.
                tally["plain_held_back"] += 1
                continue
            tally["seen"] += 1
            try:
                info = os.lstat(path)
            except FileNotFoundError:
                continue
            row = db.execute("SELECT size, mtime_ns, sha256 FROM files WHERE path = ?", (key,)).fetchone()
            target = os.path.join(dest, "files", key)
            if row and row[0] == info.st_size and row[1] == info.st_mtime_ns and os.path.exists(target):
                db.execute("UPDATE files SET seen_run = ? WHERE path = ?", (run_id, key))
                tally["skipped"] += 1
            else:
                free = shutil.disk_usage(dest).free
                if free - info.st_size < floor:
                    stopped = "space"
                    break
                try:
                    if row and os.path.exists(target):
                        kept = os.path.join(dest, "superseded", f"{key}.{row[2][:12]}")
                        os.makedirs(os.path.dirname(kept), exist_ok=True)
                        if not os.path.exists(kept):
                            shutil.copy2(target, kept)
                        tally["changed"] += 1
                    done = copy_one(path, target, throttle)
                except FileNotFoundError:
                    continue
                except OSError as exc:
                    tally["failed"] += 1
                    errors.append(f"{key}: {exc}")
                    continue
                if done is None:
                    tally["moving"] += 1
                    continue
                digest, final = done
                db.execute(
                    "INSERT OR REPLACE INTO files (path, size, mtime_ns, sha256, copied_at, seen_run)"
                    " VALUES (?, ?, ?, ?, ?, ?)",
                    (key, final.st_size, final.st_mtime_ns, digest, run_id, run_id),
                )
                tally["copied"] += 1
                tally["bytes_copied"] += final.st_size
            pending += 1
            if pending >= 200:
                db.commit()
                pending = 0
        if stopped:
            break
    db.commit()
    if not stopped and not errors:
        labels = [label for label, _ in sources]
        tally["gone"] = sum(
            db.execute(
                "SELECT count(*) FROM files WHERE path LIKE ? AND seen_run <> ?", (f"{label}/%", run_id)
            ).fetchone()[0]
            for label in labels
        )
    write_manifest(db, dest)
    total_files, total_bytes = db.execute("SELECT count(*), coalesce(sum(size), 0) FROM files").fetchone()
    complete = not stopped and not errors and not tally["moving"]
    report = dict(
        first_started=earlier.get("first_started", run_id),
        last_complete=utcnow() if complete else earlier.get("last_complete", ""),
        started=run_id, finished=utcnow(), seconds=round(time.monotonic() - started), complete=complete,
        stopped=stopped, tally=tally, files_in_copy=total_files, bytes_in_copy=total_bytes,
        sources=dict(sources), errors=errors[:50], errors_total=len(errors),
    )
    temp = os.path.join(dest, ".last-run.new")
    with open(temp, "w") as out:
        json.dump(report, out, indent=2)
    os.replace(temp, os.path.join(dest, "last-run.json"))
    print(json.dumps(report))
    if tally["failed"] or errors:
        return 1
    return 3 if stopped else 0


def init(args):
    dest = os.path.realpath(args.dest)
    os.makedirs(dest, exist_ok=True)
    with open(os.path.join(dest, MARK), "w") as out:
        out.write(f"Loupe evidence copy, marked {utcnow()}\n")
    print(f"marked {dest}")
    return 0


def verify(args):
    dest = os.path.realpath(args.dest)
    db = open_state(dest)
    rows = db.execute("SELECT path, sha256 FROM files").fetchall()
    sample = random.sample(rows, min(args.sample, len(rows)))
    bad = []
    for path, sha in sample:
        try:
            if hash_path(os.path.join(dest, "files", path)) != sha:
                bad.append(path)
        except OSError as exc:
            bad.append(f"{path}: {exc}")
    print(json.dumps(dict(sampled=len(sample), of=len(rows), bad=bad[:50], bad_total=len(bad))))
    return 1 if bad else 0


def status(args):
    with open(os.path.join(args.dest, "last-run.json")) as handle:
        print(handle.read())
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    one = sub.add_parser("run")
    one.add_argument("--dest", required=True)
    one.add_argument("--source", action="append")
    one.add_argument("--budget-seconds", type=int, default=0)
    one.add_argument("--min-free-gb", type=float, default=20)
    one.add_argument("--max-mb-s", type=float, default=0)
    one.set_defaults(handler=run)
    two = sub.add_parser("verify")
    two.add_argument("--dest", required=True)
    two.add_argument("--sample", type=int, default=200)
    two.set_defaults(handler=verify)
    four = sub.add_parser("init")
    four.add_argument("--dest", required=True)
    four.set_defaults(handler=init)
    three = sub.add_parser("status")
    three.add_argument("--dest", required=True)
    three.set_defaults(handler=status)
    args = parser.parse_args()
    os.umask(0o077)
    os.nice(15)
    return args.handler(args)


if __name__ == "__main__":
    sys.exit(main())
