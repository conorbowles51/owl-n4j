"""The package format: one tar file, written and read as a stream.

Members, in order: JSON-lines parts compressed with gzip (``pg/<table>.jsonl.gz``, ``people.jsonl.gz``,
``ids.txt.gz``, ``neo4j/nodes.jsonl.gz``, ``neo4j/relationships.jsonl.gz``, ``vectors/<collection>.jsonl.gz``,
``evidence-index.jsonl.gz``), the evidence files as stored (``evidence/<path inside the case folder>``), then
``manifest.json`` and ``manifest.sha256``. The manifest gives each part's rows, bytes and SHA-256; the evidence index
gives each file's size and SHA-256. ``<package>.sha256`` beside the tar is the hash of the whole file.

The package is written under a ``.partial`` name and takes its real name only when complete, so a stopped export can
never be mistaken for a whole one. The hashes catch damage, not a forger: anyone able to rewrite a package can rewrite
its hashes, so a package moves between sites by a channel the sites trust.
"""
from __future__ import annotations

import gzip
import hashlib
import io
import json
import os
import tarfile
import zlib
from pathlib import Path

FORMAT = "loupe.case_package"
FORMAT_VERSION = 1
SUPPORTED_FORMAT_VERSIONS = (1,)
SUFFIX = ".loupecase.tar"
PARTIAL = ".partial"
CHUNK = 1024 * 1024


class HashingFile:
    """A write-only file that hashes everything passing through it."""

    def __init__(self, raw):
        self.raw = raw
        self.sha256 = hashlib.sha256()
        self.size = 0

    def write(self, data):
        self.raw.write(data)
        self.sha256.update(data)
        self.size += len(data)
        return len(data)

    def tell(self):
        return self.size

    def flush(self):
        self.raw.flush()


class PartWriter:
    """Lines into a gzip file beside the package, hashed; add_part moves it into the tar."""

    def __init__(self, path: Path):
        self.path = path
        self.raw = open(path, "wb")
        self.hashing = HashingFile(self.raw)
        self.gz = gzip.GzipFile(fileobj=self.hashing, mode="wb", compresslevel=4, mtime=0)
        self.rows = 0

    def write_line(self, text: str):
        self.gz.write(text.encode("utf-8", "surrogatepass"))
        self.gz.write(b"\n")
        self.rows += 1

    def close(self):
        self.gz.close()
        self.raw.close()


class PackageWriter:
    def __init__(self, target: Path):
        self.target = Path(target)
        self.partial = self.target.with_name(self.target.name + PARTIAL)
        self.raw = open(self.partial, "wb")
        self.hashing = HashingFile(self.raw)
        self.tar = tarfile.open(fileobj=self.hashing, mode="w|", format=tarfile.PAX_FORMAT)
        self.parts: dict = {}
        self.scratch = self.partial.with_name(self.partial.name + ".part")

    def part(self) -> PartWriter:
        return PartWriter(self.scratch)

    def add_part(self, name: str, writer: PartWriter):
        writer.close()
        self.parts[name] = {"rows": writer.rows, "bytes": writer.hashing.size,
                            "sha256": writer.hashing.sha256.hexdigest()}
        self._add_file(name, self.scratch, writer.hashing.size)
        os.unlink(self.scratch)

    def _add_file(self, name, path, size):
        info = tarfile.TarInfo(name)
        info.size = size
        with open(path, "rb") as f:
            self.tar.addfile(info, f)

    def add_evidence(self, name: str, path: Path) -> dict | None:
        """Add one file, hashing what is really read. A file that changes while it is read fails the export."""
        size = os.path.getsize(path)
        info = tarfile.TarInfo(name)
        info.size = size
        digest = hashlib.sha256()

        class Reader:
            def __init__(self, f):
                self.f = f

            def read(self, n=-1):
                data = self.f.read(n)
                digest.update(data)
                return data

        with open(path, "rb") as f:
            self.tar.addfile(info, Reader(f))
        return {"size": size, "sha256": digest.hexdigest()}

    def add_bytes(self, name: str, data: bytes):
        info = tarfile.TarInfo(name)
        info.size = len(data)
        self.tar.addfile(info, io.BytesIO(data))

    def finish(self, manifest: dict) -> dict:
        """Write the manifest, close, and only now give the package its name. Returns path, size, sha256."""
        manifest = {**manifest, "parts": self.parts}
        body = json.dumps(manifest, indent=1, sort_keys=True).encode()
        self.add_bytes("manifest.json", body)
        self.add_bytes("manifest.sha256", hashlib.sha256(body).hexdigest().encode())
        self.tar.close()
        self.raw.flush()
        os.fsync(self.raw.fileno())
        self.raw.close()
        digest = self.hashing.sha256.hexdigest()
        side = self.target.with_name(self.target.name + ".sha256")
        side.write_text(f"{digest}  {self.target.name}\n")
        os.replace(self.partial, self.target)
        return {"path": str(self.target), "size": self.hashing.size, "sha256": digest}

    def abandon(self):
        """Remove everything of an export that did not finish."""
        for closing in (self.tar, self.raw):
            try:
                closing.close()
            except Exception:  # noqa: BLE001 - already failing; the files go below
                pass
        for path in (self.partial, self.scratch):
            try:
                os.unlink(path)
            except FileNotFoundError:
                pass


class _HashingReader:
    def __init__(self, raw):
        self.raw = raw
        self.sha256 = hashlib.sha256()
        self.size = 0

    def read(self, n=-1):
        data = self.raw.read(n)
        self.sha256.update(data)
        self.size += len(data)
        return data


def _read_member(tar, member, *, gz: bool):
    """Stream one member: its SHA-256, and its line count when it is a gzip part. Returns (sha, bytes, rows, error)."""
    digest = hashlib.sha256()
    size = 0
    rows = 0
    inflate = zlib.decompressobj(zlib.MAX_WBITS | 16) if gz else None
    error = None
    source = tar.extractfile(member)
    while True:
        data = source.read(CHUNK)
        if not data:
            break
        digest.update(data)
        size += len(data)
        if inflate is not None and error is None:
            try:
                rows += inflate.decompress(data).count(b"\n")
            except zlib.error as exc:
                error = f"cannot be decompressed ({exc})"
    return digest.hexdigest(), size, rows, error


def verify(path) -> dict:
    """Read a package end to end. Returns {"ok", "problems", "notes", "manifest", "sha256", "size"}.

    Every member is hashed and every part's lines counted; the whole file is checked against its ``.sha256`` when that
    is present. Nothing is written and nothing is trusted before the end: the manifest comes last in the file."""
    path = Path(path)
    problems: list = []
    notes: list = []
    seen: dict = {}
    evidence_seen: dict = {}
    index_bytes = None
    manifest_bytes = None
    manifest_hash = None
    with open(path, "rb") as raw:
        reader = _HashingReader(raw)
        try:
            with tarfile.open(fileobj=reader, mode="r|") as tar:
                for member in tar:
                    if not member.isfile():
                        problems.append(f"{member.name}: not a file")
                        continue
                    name = member.name
                    if name == "manifest.json":
                        manifest_bytes = tar.extractfile(member).read()
                    elif name == "manifest.sha256":
                        manifest_hash = tar.extractfile(member).read().decode("ascii", "replace").strip()
                    elif name == "evidence-index.jsonl.gz":
                        index_bytes = tar.extractfile(member).read()
                        seen[name] = (hashlib.sha256(index_bytes).hexdigest(), len(index_bytes),
                                      _gunzip_lines(index_bytes), None)
                    elif name.startswith("evidence/"):
                        sha, size, _, _ = _read_member(tar, member, gz=False)
                        evidence_seen[name[len("evidence/"):]] = (sha, size)
                    else:
                        seen[name] = _read_member(tar, member, gz=True)
        except (tarfile.TarError, EOFError, OSError) as exc:
            problems.append(f"the package cannot be read to its end: {exc}")
        while reader.read(CHUNK):
            pass
    total_sha = reader.sha256.hexdigest()
    side = path.with_name(path.name + ".sha256")
    if side.exists():
        recorded = side.read_text().split()[0] if side.read_text().split() else ""
        if recorded != total_sha:
            problems.append(f"the whole file's SHA-256 is {total_sha}, its .sha256 file says {recorded}")
    else:
        notes.append("no .sha256 file beside the package: the whole-file hash was not checked (each part still was)")
    manifest = None
    if manifest_bytes is None:
        problems.append("manifest.json is missing")
    else:
        if hashlib.sha256(manifest_bytes).hexdigest() != manifest_hash:
            problems.append("manifest.json does not match manifest.sha256")
        try:
            manifest = json.loads(manifest_bytes)
        except ValueError as exc:
            problems.append(f"manifest.json cannot be read: {exc}")
    if manifest is None:
        return dict(ok=False, problems=problems, notes=notes, manifest=None, sha256=total_sha, size=reader.size)
    if manifest.get("format") != FORMAT:
        problems.append(f"this is not a case package (format {manifest.get('format')!r})")
    for name, want in (manifest.get("parts") or {}).items():
        got = seen.pop(name, None)
        if got is None:
            problems.append(f"{name}: missing from the package")
            continue
        sha, size, rows, error = got
        if error:
            problems.append(f"{name}: {error}")
        if sha != want.get("sha256"):
            problems.append(f"{name}: SHA-256 is {sha}, the manifest says {want.get('sha256')}")
        if size != want.get("bytes"):
            problems.append(f"{name}: {size} bytes, the manifest says {want.get('bytes')}")
        if rows != want.get("rows"):
            problems.append(f"{name}: {rows} rows, the manifest says {want.get('rows')}")
    for name in sorted(seen):
        problems.append(f"{name}: in the package but not in the manifest")
    index = {}
    if index_bytes is not None:
        for line in gzip.decompress(index_bytes).splitlines():
            entry = json.loads(line)
            index[entry["path"]] = entry
    for rel, entry in index.items():
        got = evidence_seen.pop(rel, None)
        if got is None:
            problems.append(f"evidence file {rel}: missing from the package")
        elif got[0] != entry["sha256"]:
            problems.append(f"evidence file {rel}: SHA-256 is {got[0]}, the index says {entry['sha256']}")
        elif got[1] != entry["size"]:
            problems.append(f"evidence file {rel}: {got[1]} bytes, the index says {entry['size']}")
    for rel in sorted(evidence_seen):
        problems.append(f"evidence file {rel}: in the package but not in the index")
    return dict(ok=not problems, problems=problems, notes=notes, manifest=manifest, sha256=total_sha, size=reader.size)


def _gunzip_lines(data: bytes) -> int:
    return gzip.decompress(data).count(b"\n")


class PackageReader:
    """Random access to a verified package for the import."""

    def __init__(self, path):
        self.tar = tarfile.open(path, "r:")
        self.members = {m.name: m for m in self.tar.getmembers()}

    def lines(self, name: str):
        """The part's lines as text, one at a time, without the newline."""
        member = self.members.get(name)
        if member is None:
            return
        with gzip.GzipFile(fileobj=self.tar.extractfile(member)) as gz:
            for line in io.TextIOWrapper(gz, encoding="utf-8", errors="surrogatepass", newline="\n"):
                yield line.rstrip("\n")

    def copy_evidence(self, rel: str, target: Path) -> str:
        """Write one evidence file out, returning the SHA-256 of what was written."""
        digest = hashlib.sha256()
        source = self.tar.extractfile(self.members["evidence/" + rel])
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "wb") as out:
            while True:
                data = source.read(CHUNK)
                if not data:
                    break
                digest.update(data)
                out.write(data)
        return digest.hexdigest()

    def close(self):
        self.tar.close()
