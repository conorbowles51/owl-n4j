"""What an evidence file says it is, what its first bytes say it is, and whether the two agree.

The name of a file is a claim made by whoever named it; its first bytes are the file's own. Both are recorded on the row
at registration (``file_type_stated``, ``file_type_detected``, ``file_type_match``). A disagreement is a mark and nothing
more: evidence is never refused or dropped for one, because a mislabelled file can be the point of a case.

``file_type_match`` is ``match``, ``mismatch``, ``empty`` (no bytes to read), ``no_file`` (a row with no file of its own)
or ``unknown`` (the name makes no claim, or the bytes are not recognised). Only a recognised type against a recognised
claim is a mismatch: a phone's ``.exo`` cache file, or a ``.dat`` of anything, says nothing to disagree with.

Executable content is the one case with a consequence: a program (Windows, Linux, macOS, or Android or Java bytecode)
is held from model reading until a person releases it, and stays in the case with that state shown. Scripts are text and
are not held: a shell script on a seized laptop is a document to read.

Standard library only, and no I/O beyond the first ``HEAD_BYTES`` of the file. The media signatures are the engine's
(``evidence-engine/app/pipeline/phone_media.py``), so the two never disagree on what a file is.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Iterable, Optional
from uuid import UUID


HEAD_BYTES = 4096

MATCH, MISMATCH, UNKNOWN, EMPTY, NO_FILE = 'match', 'mismatch', 'unknown', 'empty', 'no_file'
EXECUTABLE = 'executable'

# Plain words for a detected type, shown beside the file.
TYPE_WORDS = {
    'pdf': 'PDF document', 'image': 'image', 'audio': 'audio', 'video': 'video', 'text': 'text',
    'zip': 'ZIP archive', 'archive': 'compressed archive', 'ole': 'older Microsoft Office file',
    'sqlite': 'SQLite database', 'pe': 'Windows program', 'elf': 'Linux program', 'macho': 'macOS program',
    'dex': 'Android program', 'java': 'Java program',
}
EXECUTABLE_TYPES = frozenset(('pe', 'elf', 'macho', 'dex', 'java'))


def _suffixes(family: str, *names: str) -> dict:
    return {'.' + name: family for name in names}


# A name's claim, as the type its bytes would show. A format that is a ZIP inside states ``zip``.
STATED = {
    **_suffixes('pdf', 'pdf'),
    **_suffixes('image', 'jpg', 'jpeg', 'jpe', 'png', 'gif', 'webp', 'bmp', 'tif', 'tiff', 'heic', 'heif'),
    **_suffixes('audio', 'mp3', 'm4a', 'wav', 'ogg', 'oga', 'opus', 'flac', 'amr', 'aac', 'caf', 'aif', 'aiff'),
    **_suffixes('video', 'mp4', 'mov', 'm4v', '3gp', '3g2', 'mkv', 'webm', 'avi', 'mpg', 'mpeg'),
    **_suffixes('text', 'txt', 'log', 'csv', 'tsv', 'json', 'xml', 'yaml', 'yml', 'html', 'htm', 'md', 'markdown',
                'eml', 'vcf', 'rtf', 'sri', 'ini', 'js', 'css', 'plist'),
    **_suffixes('zip', 'zip', 'docx', 'xlsx', 'pptx', 'odt', 'ods', 'odp', 'epub', 'apk', 'jar', 'ipa', 'ufdr', 'ufd'),
    **_suffixes('archive', 'gz', 'tgz', 'bz2', 'xz', '7z', 'rar', 'tar'),
    **_suffixes('ole', 'doc', 'xls', 'ppt', 'msg', 'msi'),
    **_suffixes('sqlite', 'db', 'sqlite', 'sqlite3'),
    **_suffixes('pe', 'exe', 'dll', 'sys', 'scr', 'com'),
    **_suffixes('elf', 'so', 'elf'),
    **_suffixes('dex', 'dex', 'odex'),
    **_suffixes('java', 'class'),
}
# A name that may honestly hold more than one thing. A ``.plist`` is XML or Apple's binary form; a ``.db`` is a database
# or a phone's private format; a ``.mpeg`` may be audio only; an ``.odex`` on Android 8 and later is an ELF file; an
# MP4 brand names the box format, so an ``.m4a`` can read as video (the census of 5 Nov 2026 found each of these).
ALSO_STATED = {
    '.plist': ('bplist',), '.db': (None,), '.mpeg': ('audio',), '.mpg': ('audio',), '.3gp': ('audio',),
    '.mp4': ('audio',), '.webm': ('audio',), '.ogg': ('video',), '.com': ('text',),
    '.json': ('bplist',), '.xml': ('bplist',), '.odex': ('elf',), '.m4a': ('video',),
}


@dataclass(frozen=True)
class Signature:
    stated: Optional[str]
    detected: Optional[str]
    match: str

    @property
    def executable(self) -> bool:
        return self.detected in EXECUTABLE_TYPES


def _portable_executable(head: bytes) -> bool:
    """A Windows program: ``MZ`` and, at the offset the DOS header gives, ``PE``. A text starting "MZ" has neither."""
    if head[:2] != b'MZ' or len(head) < 64:
        return False
    at = int.from_bytes(head[60:64], 'little')
    if at + 4 <= len(head):
        return head[at:at + 4] == b'PE\x00\x00'
    return b'\x00' in head[:64]  # the PE header lies past the bytes read; a DOS header holds zero bytes, text does not


def _executable(head: bytes) -> Optional[str]:
    if _portable_executable(head):
        return 'pe'
    if head[:4] == b'\x7fELF':
        return 'elf'
    if head[:4] in (b'\xfe\xed\xfa\xce', b'\xce\xfa\xed\xfe', b'\xfe\xed\xfa\xcf', b'\xcf\xfa\xed\xfe'):
        return 'macho'
    if head[:4] == b'\xca\xfe\xba\xbe' and len(head) >= 8:
        # The same four bytes open a Java class (major version 45 and up) and a macOS universal binary (a small count).
        return 'java' if int.from_bytes(head[6:8], 'big') >= 45 else 'macho'
    if head[:4] in (b'dex\n', b'dey\n'):
        return 'dex'
    return None


def _container(head: bytes) -> Optional[str]:
    if head[:4] in (b'PK\x03\x04', b'PK\x05\x06', b'PK\x07\x08'):
        return 'zip'
    if head[:8] == b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1':
        return 'ole'
    if head[:16] == b'SQLite format 3\x00':
        return 'sqlite'
    if head[:8] == b'bplist00':
        return 'bplist'
    if head[:2] == b'\x1f\x8b' or head[:3] == b'BZh' or head[:6] == b'\xfd7zXZ\x00' or \
            head[:6] == b"7z\xbc\xaf'\x1c" or head[:6] == b'Rar!\x1a\x07' or head[257:262] == b'ustar':
        return 'archive'
    return None


def _is_text(head: bytes) -> bool:
    """Text in UTF-8 or a single-byte code page, or marked UTF-16/UTF-8; never a block holding NUL or control bytes."""
    if head[:2] in (b'\xff\xfe', b'\xfe\xff') or head[:3] == b'\xef\xbb\xbf':
        return True
    if b'\x00' in head:
        return False
    controls = sum(byte < 9 or 13 < byte < 32 and byte != 27 for byte in head)
    return controls * 100 <= len(head)


def detect(head: bytes) -> Optional[str]:
    """The file's type from its first bytes, or ``None`` when they are not recognised."""
    found = _executable(head) or _container(head)
    if found:
        return found
    from services.phone.derive import phone_media
    sniffed = phone_media().sniff_bytes(head)
    if sniffed.kind:
        return sniffed.kind
    if b'%PDF-' in head[:1024]:
        return 'pdf'  # readers accept a PDF that opens with a few stray bytes
    return 'text' if _is_text(head) else None


def stated(filename: Optional[str]) -> Optional[str]:
    """The type the file's name claims, or ``None`` when it makes no claim this table knows."""
    return STATED.get(PurePosixPath(filename or '').suffix.lower())


def signature(filename: Optional[str], head: bytes) -> Signature:
    claim = stated(filename)
    if not head:
        return Signature(claim, None, EMPTY)
    found = detect(head)
    if claim is None or found is None:
        return Signature(claim, found, UNKNOWN)
    suffix = PurePosixPath(filename or '').suffix.lower()
    agrees = found == claim or found in ALSO_STATED.get(suffix, ()) or None in ALSO_STATED.get(suffix, ())
    return Signature(claim, found, MATCH if agrees else MISMATCH)


def read_head(path) -> bytes:
    with open(path, 'rb') as handle:
        return handle.read(HEAD_BYTES)


def signature_of_file(filename: Optional[str], path) -> Signature:
    """The file's signature, or ``no_file`` when its bytes cannot be read: never a reason to stop a registration."""
    try:
        return signature(filename, read_head(path))
    except OSError:
        return Signature(stated(filename), None, NO_FILE)


def stamp(row, sig: Signature) -> None:
    """Record the signature on the row. Executable content starts held from model reading, with the reason."""
    row.file_type_stated, row.file_type_detected, row.file_type_match = sig.stated, sig.detected, sig.match
    if sig.executable and row.reading_hold is None:
        row.reading_hold, row.reading_hold_reason = 'held', EXECUTABLE


def hold(row, reason: str, detail: Optional[str] = None) -> None:
    """Hold a file from model reading, whatever was decided before: a later finding outranks an earlier release."""
    row.reading_hold, row.reading_hold_reason, row.reading_hold_detail = 'held', reason, detail
    row.reading_released_by, row.reading_released_at = None, None


def release(db, row, user) -> None:
    """A named person lets the file be read. The reason for the hold stays on the row and in the activity trail."""
    from services import activity_trail
    name = getattr(user, 'name', None) or getattr(user, 'email', None) or 'unknown'
    row.reading_hold, row.reading_released_by = 'released', name[:255]
    row.reading_released_at = datetime.now(timezone.utc)
    activity_trail.record('evidence_hold_release', db=db, user=user, case_id=row.case_id, details=dict(
        reason=row.reading_hold_reason, detail=row.reading_hold_detail, files=activity_trail.file_entries([row])))


def split_held(db, case_id, file_ids, resolve_path) -> tuple:
    """(ids to send, ids held). A row not read yet is read here, so an older file cannot pass unread."""
    from sqlalchemy import select
    from postgres.models.evidence import EvidenceFile
    wanted = [(file_id, UUID(str(file_id))) for file_id in file_ids]
    held = set()
    for at in range(0, len(wanted), 500):
        for row in db.scalars(select(EvidenceFile).where(
                EvidenceFile.case_id == case_id, EvidenceFile.id.in_([key for _, key in wanted[at:at + 500]]))):
            if row.file_type_match in (None, NO_FILE) and row.source_type != 'phone_text':
                path = resolve_path(row.stored_path)
                if path is not None:
                    stamp(row, signature_of_file(row.original_filename, path))
            if row.reading_hold == 'held':
                held.add(row.id)
    return [given for given, key in wanted if key not in held], [given for given, key in wanted if key in held]


def read_unread(db, root, *, apply: bool = True) -> Counter:
    """The first bytes of every live row not read yet, through the same ``stamp`` as a registration (the daily file
    check runs this, so a row from before the check gets its mark). Written with its own statement: ``updated_at``
    stays what it was, because a row's reading has not changed. ``apply=False`` writes nothing."""
    from sqlalchemy import select, update
    from postgres.models.evidence import EvidenceFile as File
    from services.evidence_file_check import resolve_stored_path
    rows = list(db.execute(select(File.id, File.original_filename, File.stored_path).where(
        File.deleted_at.is_(None), File.file_type_match.is_(None), File.stored_path.like('/%'))).all())
    db.rollback()  # no transaction stays open across the reads
    counts = Counter()
    for at, row in enumerate(rows, 1):
        sig = signature_of_file(row.original_filename, resolve_stored_path(row.stored_path, root) or row.stored_path)
        counts[sig.match] += 1
        counts['held'] += sig.executable
        if apply:
            db.execute(update(File).where(File.id == row.id, File.file_type_match.is_(None)).values(
                updated_at=File.updated_at, file_type_stated=sig.stated, file_type_detected=sig.detected,
                file_type_match=sig.match, **(dict(reading_hold='held', reading_hold_reason=EXECUTABLE)
                                              if sig.executable else {})))
            if not at % 500:
                db.commit()
    db.commit()
    return counts


def held_words(count: int) -> str:
    return (f"{count:,} {'file holds' if count == 1 else 'files hold'} program code or a malware finding and "
            f"{'was' if count == 1 else 'were'} not sent for reading. Release {'it' if count == 1 else 'them'} "
            'from the file to read.')


def file_check_fields(row) -> dict:
    """The row's check as a list or detail answer gives it. Read from the row alone: no file and no query."""
    return dict(file_type_stated=row.file_type_stated, file_type_detected=row.file_type_detected,
                file_type_match=row.file_type_match, file_type_words=words(row.file_type_detected) if row.file_type_detected else None,
                reading_hold=row.reading_hold, reading_hold_reason=row.reading_hold_reason,
                reading_hold_detail=row.reading_hold_detail, reading_released_by=row.reading_released_by,
                reading_released_at=row.reading_released_at.isoformat() if row.reading_released_at else None,
                malware_scan=row.malware_scan)


def words(detected: Optional[str]) -> str:
    return TYPE_WORDS.get(detected or '', detected or 'unknown')


def group_counts(rows: Iterable) -> dict:
    """What an upload summary says: how many files are mislabelled and how many are held."""
    rows = list(rows)
    return dict(mismatched=sum(row.file_type_match == MISMATCH for row in rows),
                held=sum(row.reading_hold == 'held' for row in rows))


def summary_words(counts: dict) -> str:
    """The sentence an upload summary adds, or nothing when there is nothing to say."""
    parts = []
    if counts.get('mismatched'):
        count = counts['mismatched']
        parts.append(f"{count:,} {'file does' if count == 1 else 'files do'} not match {'its' if count == 1 else 'their'} "
                     'file type.')
    if counts.get('held'):
        count = counts['held']
        parts.append(f"{count:,} {'file holds' if count == 1 else 'files hold'} program code and "
                     f"{'is' if count == 1 else 'are'} held from reading until someone releases "
                     f"{'it' if count == 1 else 'them'}.")
    return ' '.join(parts)
