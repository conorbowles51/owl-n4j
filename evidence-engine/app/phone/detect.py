"""Intake detection (01 section 2, unit 1.2). Detection never writes and never extracts.

``classify(path)`` takes a directory, a zip or UFDR, or a single XML document and returns the
``IntakeClassification`` of 01 section 2.5 as a plain dict (``schemas.IntakeClassification`` validates it).
A container is read through ``Source`` (``FolderSource`` or ``ZipSource``) so detection, capture and file
verification read folders and zips the same way, zips in place (decision D6).
"""
from __future__ import annotations

import os
import re
import stat
import zipfile
from pathlib import PurePosixPath

PA_NS = b"http://pa.cellebrite.com/report/2.0"
ZIP_MAGIC = (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")
PROTECTED_MAGIC = bytes.fromhex("2D06526D")
HEADER_STRINGS = (b"project id", b"extractionType", b"sourceExtractions")
SECTION_RE = re.compile(r"^\.xml[A-Z][A-Za-z]+$")
SECTION_ROLES = {".xmlModel": "model", ".xmlTagged": "tagged", ".xmlExtra": "extra", ".xmlLast": "last",
                 ".xmlMdfSource": "mdf_source", ".xmlModelSource": "model_source", ".xmlNodeSource": "node_source",
                 ".xmlTranslation": "translation"}
SNIFF = 8192
TAIL = 4096
SKIP_FINAL = {".DS_Store": "ds_store", "Thumbs.db": "thumbs_db", "desktop.ini": "desktop_ini"}
V1_REPORT = "owl_ingest_report.json"

READABLE = "readable"
PROTECTED_NO_PASSWORD = "protected_no_password"
PROTECTED_PASSWORD = "protected_password"
PROTECTED_OR_INVALID = "protected_or_invalid"
NOT_A_PHONE_REPORT = "not_a_phone_report"
PROTECTED = (PROTECTED_NO_PASSWORD, PROTECTED_PASSWORD, PROTECTED_OR_INVALID)


def skip_rule(relpath: str):
    """The skip-set rule an entry matches (01 section 2.3 step 2), or None."""
    parts = [p for p in relpath.split("/") if p]
    if not parts:
        return None
    if "__MACOSX" in parts:
        return "__MACOSX"
    final = parts[-1]
    if final.startswith("._"):
        return "appledouble"
    return SKIP_FINAL.get(final)


def section_suffix(name: str):
    """The split-section suffix of a file name (``.xmlModel``), or None."""
    stem, dot, suffix = name.rpartition(".")
    if not dot or not stem:
        return None
    suffix = "." + suffix
    return suffix if SECTION_RE.match(suffix) else None


class FolderSource:
    kind = "folder"

    def __init__(self, root: str):
        self.root = root

    def entries(self):
        """(relpath, size) for every regular file, '/' separators, sorted. Symbolic links are not followed."""
        out = []
        for dirpath, dirnames, filenames in os.walk(self.root, followlinks=False):
            dirnames.sort()
            for f in filenames:
                full = os.path.join(dirpath, f)
                st = os.lstat(full)
                if not stat.S_ISREG(st.st_mode):
                    continue
                rel = os.path.relpath(full, self.root).replace(os.sep, "/")
                out.append((rel, st.st_size))
        out.sort()
        return out

    def open(self, relpath: str):
        return open(os.path.join(self.root, *relpath.split("/")), "rb")

    def read_head(self, relpath, n=SNIFF):
        with self.open(relpath) as fh:
            return fh.read(n)

    def read_tail(self, relpath, size, n=TAIL):
        with self.open(relpath) as fh:
            fh.seek(max(0, size - n))
            return fh.read(n)

    def close(self):
        pass


class ZipSource:
    kind = "zip"

    def __init__(self, path: str):
        self.path = path
        self.zf = zipfile.ZipFile(path)
        self._info = {i.filename: i for i in self.zf.infolist() if not i.is_dir()}

    def entries(self):
        return sorted((name.rstrip("/"), i.file_size) for name, i in self._info.items())

    def info(self, relpath):
        return self._info[relpath]

    def location(self, relpath):
        """(local header offset, compressed size, compression method, CRC-32) of a member: enough to read it
        later by seeking straight to it, without the archive's directory (cb-media item F)."""
        i = self._info[relpath]
        return i.header_offset, i.compress_size, i.compress_type, i.CRC

    def open(self, relpath):
        return self.zf.open(self._info[relpath])

    def read_head(self, relpath, n=SNIFF):
        with self.open(relpath) as fh:
            return fh.read(n)

    def read_tail(self, relpath, size, n=TAIL):
        # a deflated member cannot seek cheaply; stream it, keeping the last n bytes
        tail = b""
        with self.open(relpath) as fh:
            while True:
                b = fh.read(1 << 20)
                if not b:
                    break
                tail = (tail + b)[-n:]
        return tail

    def close(self):
        self.zf.close()


def open_source(path: str):
    if os.path.isdir(path):
        return FolderSource(path)
    return ZipSource(path)


def _first_start_tag(head: bytes):
    m = re.search(rb"<([A-Za-z_][\w.\-]*:)?([A-Za-z_][\w.\-]*)[\s/>]", _strip_prolog(head))
    return m.group(2).decode("ascii", "replace") if m else None


def _strip_prolog(head: bytes) -> bytes:
    h = head.lstrip(b"\xef\xbb\xbf \t\r\n")
    while True:
        if h.startswith(b"<?"):
            end = h.find(b"?>")
            if end < 0:
                return b""
            h = h[end + 2:].lstrip()
        elif h.startswith(b"<!--"):
            end = h.find(b"-->")
            if end < 0:
                return b""
            h = h[end + 3:].lstrip()
        elif h.startswith(b"<!"):
            end = h.find(b">")
            if end < 0:
                return b""
            h = h[end + 1:].lstrip()
        else:
            return h


def _ends_complete(tail: bytes, root_element: str) -> bool:
    t = tail.rstrip(b" \t\r\n")
    return bool(re.search(rb"</([A-Za-z_][\w.\-]*:)?" + re.escape(root_element.encode()) + rb"\s*>$", t))


def _document(source, relpath, size):
    """A report-candidate decision for one entry, or None when it is not a report document."""
    name = relpath.rsplit("/", 1)[-1]
    suffix = section_suffix(name)
    is_xml = name.lower().endswith(".xml")
    if not (is_xml or suffix):
        return None
    if size == 0:
        if suffix:
            return {"path": relpath, "role": SECTION_ROLES.get(suffix, "unknown"), "size": 0, "empty": True,
                    "root_element": None, "has_namespace": False, "suspected_truncated": False, "section": True}
        return None
    head = source.read_head(relpath)
    has_ns = PA_NS in head
    root = _first_start_tag(head)
    if not suffix and has_ns and root == "project":
        return {"path": relpath, "role": "full", "size": size, "empty": False, "root_element": root,
                "has_namespace": True, "suspected_truncated": False, "section": False}
    if suffix and (has_ns or root == "decodedData"):
        return {"path": relpath, "role": SECTION_ROLES.get(suffix, "unknown"), "size": size, "empty": False,
                "root_element": root, "has_namespace": has_ns, "suspected_truncated": False, "section": True}
    return None


def _parent(relpath):
    p = str(PurePosixPath(relpath).parent)
    return "" if p == "." else p


def _stem(name):
    return name[:-len(section_suffix(name))] if section_suffix(name) else name


def _is_ancestor(a, b):
    return a != b and (a == "" or b.startswith(a + "/"))


def _ufdr_check(zs: ZipSource):
    for name in ("report.xml", "Report.xml"):
        if name in zs._info:
            info = zs._info[name]
            if info.flag_bits & 0x1:
                return PROTECTED_PASSWORD, name
            try:
                head = zs.read_head(name, 1024)
            except RuntimeError:  # zipfile refuses an encrypted member without a password
                return PROTECTED_PASSWORD, name
            if head[:4] == PROTECTED_MAGIC:
                return PROTECTED_NO_PASSWORD, name
            if not any(s in head for s in HEADER_STRINGS):
                return PROTECTED_OR_INVALID, name
            return READABLE, name
    return None, None


def _messages(c):
    msgs = []
    roots = c["roots"]
    o = c["outcome"]
    if o == PROTECTED_NO_PASSWORD:
        msgs.append(("protected_no_password", "This UFDR file is protected. Loupe does not open protected UFDRs. An "
                     "unprotected copy, or the report exported as an XML report folder, is needed from whoever "
                     "produced it."))
    elif o == PROTECTED_PASSWORD:
        msgs.append(("protected_password", "This UFDR file is password protected. Loupe does not open protected "
                     "UFDRs. An unprotected copy, or the report exported as an XML report folder, is needed from "
                     "whoever produced it."))
    elif o == PROTECTED_OR_INVALID:
        msgs.append(("protected_or_invalid", "The report inside this UFDR file cannot be read. It may be protected. "
                     "An unprotected copy, or the report exported as an XML report folder, is needed from whoever "
                     "produced it."))
    elif o == NOT_A_PHONE_REPORT:
        msgs.append(("not_a_phone_report", "No phone report was found in this upload. The files are kept as "
                     "ordinary evidence."))
    elif len(roots) > 1:
        msgs.append(("several_roots", "%d phone reports found in this upload. Each is read and checked separately."
                     % len(roots)))
    for r in roots:
        if r["form"] == "split_sections":
            data = [d for d in r["documents"] if not d["empty"]]
            empty = [d for d in r["documents"] if d["empty"]]
            msgs.append(("split_sections", "This report was exported in sections. %d sections contain data and will "
                         "be read: %s. %d sections are empty." % (
                             len(data), ", ".join(d["path"].rsplit("/", 1)[-1] for d in data), len(empty))))
            for d in data:
                if d["suspected_truncated"]:
                    msgs.append(("suspected_truncated", "The %s section of this report ends partway through. "
                                 "Everything up to that point will be read and kept, and the report will be marked "
                                 "incomplete. The full section would be needed from whoever produced it to see the "
                                 "rest." % d["path"].rsplit("/", 1)[-1]))
        elif len(roots) == 1 and o == READABLE:
            full = [d for d in r["documents"] if d["role"] == "full"]
            msgs.append(("report_found", "Phone report found: %s. It will be read in full and checked element by "
                         "element." % (full[0]["path"].rsplit("/", 1)[-1] if full else r["root_path"] or "report")))
        if len([d for d in r["documents"] if d["role"] == "full"]) > 1:
            msgs.append(("multiple_reports_in_folder", "%d full reports are in one folder. Each is read separately "
                         "and shares the folder's files." % len([d for d in r["documents"] if d["role"] == "full"])))
        for n in r["nested_report_ignored"]:
            msgs.append(("nested_report_ignored", "A second report was found inside this one at %s. It is treated "
                         "as part of the outer report." % n))
    skipped = sum(v for k, v in c["skipped_entries"].items() if k != "v1_ingest_report")
    if skipped:
        msgs.append(("skipped_entries", "%d system files added by the computer that made this archive were left out "
                     "(for example Mac resource files). They are not part of the export." % skipped))
    return [{"code": code, "text": text} for code, text in msgs]


def classify_source(source, container_kind, name=""):
    skipped = {}
    entries = []
    for rel, size in source.entries():
        rule = skip_rule(rel)
        if rule is None and rel.rsplit("/", 1)[-1] == V1_REPORT:
            rule = "v1_ingest_report"  # written by Loupe v1 into the server folders; not part of the production
        if rule is not None:
            skipped[rule] = skipped.get(rule, 0) + 1
            continue
        entries.append((rel, size))
    c = {"container_kind": container_kind, "outcome": NOT_A_PHONE_REPORT, "skipped_entries": skipped, "roots": [],
         "messages": [], "entry_count": len(entries), "entry_bytes": sum(s for _, s in entries)}
    if isinstance(source, ZipSource):
        outcome, report = _ufdr_check(source)
        if outcome is not None:
            c["container_kind"] = "ufdr"
            c["outcome"] = outcome
            if outcome == READABLE:
                size = source.info(report).file_size
                c["roots"] = [{"root_path": "", "form": "ufdr", "nested_report_ignored": [], "documents": [
                    {"path": report, "role": "full", "size": size, "empty": size == 0, "root_element": "project",
                     "has_namespace": True, "suspected_truncated": False}]}]
            c["messages"] = _messages(c)
            return c
        if name.lower().endswith(".ufdr"):
            c["container_kind"] = "ufdr"
            c["outcome"] = PROTECTED_OR_INVALID
            c["messages"] = _messages(c)
            return c
    docs = [d for d in (_document(source, rel, size) for rel, size in entries) if d is not None]
    # group into roots: a full document's directory; a stem group of sections in one directory
    by_dir = {}
    for d in docs:
        by_dir.setdefault(_parent(d["path"]), []).append(d)
    candidates = {}
    for dirpath, ds in by_dir.items():
        full = [d for d in ds if d["role"] == "full"]
        sections = {}
        for d in ds:
            if d.get("section"):
                sections.setdefault(_stem(d["path"].rsplit("/", 1)[-1]), []).append(d)
        groups = {s: g for s, g in sections.items() if any(not x["empty"] for x in g)}
        if full or groups:
            candidates[dirpath] = (full, groups)
    root_paths = sorted(candidates)
    roots = []
    for rp in root_paths:
        outer = [o for o in root_paths if _is_ancestor(o, rp)]
        if outer:
            continue
        full, groups = candidates[rp]
        nested = [o for o in root_paths if _is_ancestor(rp, o)]
        documents = []
        form = "full"
        if full:
            documents = sorted(full, key=lambda d: d["path"])
        else:
            form = "split_sections"
            for stem in sorted(groups):
                documents.extend(sorted(groups[stem], key=lambda d: d["path"]))
        for d in documents:
            if not d["empty"] and d.get("section") and d["root_element"]:
                d["suspected_truncated"] = not _ends_complete(source.read_tail(d["path"], d["size"]),
                                                              d["root_element"])
        for d in documents:
            d.pop("section", None)
        roots.append({"root_path": rp, "form": form, "documents": documents, "nested_report_ignored": nested})
    c["roots"] = roots
    if roots:
        c["outcome"] = READABLE
    c["messages"] = _messages(c)
    return c


def classify(path: str, name: str = "") -> dict:
    """Classify a directory, a zip or UFDR, or a single document (01 section 2.3)."""
    name = name or os.path.basename(path.rstrip("/"))
    if os.path.isdir(path):
        return classify_source(FolderSource(path), "folder", name)
    with open(path, "rb") as fh:
        magic = fh.read(4)
    if magic in ZIP_MAGIC:
        zs = ZipSource(path)
        try:
            return classify_source(zs, "zip", name)
        finally:
            zs.close()
    if name.lower().endswith(".ufdr"):
        c = {"container_kind": "ufdr", "outcome": PROTECTED_OR_INVALID, "skipped_entries": {}, "roots": [],
             "messages": [], "entry_count": 1, "entry_bytes": os.path.getsize(path)}
        if magic == PROTECTED_MAGIC:
            c["outcome"] = PROTECTED_NO_PASSWORD
        c["messages"] = _messages(c)
        return c
    folder = os.path.dirname(path)
    single = _SingleSource(folder, os.path.basename(path))
    c = classify_source(single, "single_document", name)
    return c


class _SingleSource(FolderSource):
    """One document on its own: the only entry is the file itself."""

    def __init__(self, folder, filename):
        super().__init__(folder)
        self.filename = filename

    def entries(self):
        return [(self.filename, os.path.getsize(os.path.join(self.root, self.filename)))]
