"""Text of a Word 97-2003 binary document (.doc, or one saved with a .docx name).

Live: OPDMD63 holds a ".DOCX" whose bytes start D0 CF 11 E0, the compound-file signature of a Word 97-2003
document; the engine refused it as "not a valid ZIP-based file". The format is public ([MS-CFB], [MS-DOC]), so
the text is read here without a new dependency: the compound file gives the WordDocument and table streams, the
FIB gives the piece table, and the piece table gives the characters in order.
"""

from __future__ import annotations

import re
import struct

OLE_SIGNATURE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"

_FREESECT = 0xFFFFFFFF
_ENDOFCHAIN = 0xFFFFFFFE
_MAX_SECTORS = 1 << 22  # a 2 GB file at 512-byte sectors; anything longer is a loop


class WordBinaryError(ValueError):
    pass


def is_ole_file(file_path: str) -> bool:
    with open(file_path, "rb") as handle:
        return handle.read(8) == OLE_SIGNATURE


class _CompoundFile:
    def __init__(self, data: bytes):
        if len(data) < 512 or data[:8] != OLE_SIGNATURE:
            raise WordBinaryError("File is not a compound document")
        self.data = data
        sector_shift, mini_shift = struct.unpack_from("<HH", data, 0x1E)
        if sector_shift not in (9, 12) or mini_shift != 6:
            raise WordBinaryError("Compound document header is damaged")
        self.sector_size = 1 << sector_shift
        self.mini_size = 1 << mini_shift
        fat_count, dir_start = struct.unpack_from("<II", data, 0x2C)
        self.mini_cutoff, mini_fat_start, mini_fat_count, difat_start, difat_count = struct.unpack_from(
            "<IIIII", data, 0x38)

        fat_sectors = list(struct.unpack_from("<109I", data, 0x4C))
        next_difat, seen = difat_start, 0
        while next_difat not in (_FREESECT, _ENDOFCHAIN) and seen <= difat_count:
            words = struct.unpack_from(f"<{self.sector_size // 4}I", self._sector(next_difat))
            fat_sectors.extend(words[:-1])
            next_difat = words[-1]
            seen += 1
        fat_sectors = [s for s in fat_sectors[:fat_count] if s not in (_FREESECT, _ENDOFCHAIN)]
        self.fat: list[int] = []
        for sector in fat_sectors:
            self.fat.extend(struct.unpack_from(f"<{self.sector_size // 4}I", self._sector(sector)))

        directory = self._chain(dir_start)
        self.entries: dict[str, tuple[int, int, int]] = {}
        root = None
        for offset in range(0, len(directory) - 127, 128):
            name_len, kind = struct.unpack_from("<HB", directory, offset + 64)
            if kind not in (1, 2, 5) or not 2 <= name_len <= 64:
                continue
            name = directory[offset:offset + name_len - 2].decode("utf-16-le", "replace")
            start, size = struct.unpack_from("<IQ", directory, offset + 116)
            if self.sector_size == 512:
                size &= 0xFFFFFFFF
            if kind == 5:
                root = (start, size)
            elif kind == 2:
                self.entries.setdefault(name, (start, size, kind))
        self.mini_stream = self._chain(root[0])[:root[1]] if root and root[0] != _ENDOFCHAIN else b""
        self.mini_fat: list[int] = []
        if mini_fat_count and mini_fat_start not in (_FREESECT, _ENDOFCHAIN):
            raw = self._chain(mini_fat_start)
            self.mini_fat = list(struct.unpack_from(f"<{len(raw) // 4}I", raw))

    def _sector(self, index: int) -> bytes:
        start = (index + 1) * self.sector_size
        if start + self.sector_size > len(self.data) + self.sector_size or start >= len(self.data):
            raise WordBinaryError("Compound document points past its end")
        return self.data[start:start + self.sector_size]

    def _chain(self, start: int) -> bytes:
        parts, sector, steps = [], start, 0
        while sector not in (_ENDOFCHAIN, _FREESECT):
            if sector >= len(self.fat) or steps > _MAX_SECTORS:
                raise WordBinaryError("Compound document sector chain is damaged")
            parts.append(self._sector(sector))
            sector = self.fat[sector]
            steps += 1
        return b"".join(parts)

    def _mini_chain(self, start: int) -> bytes:
        parts, sector, steps = [], start, 0
        while sector not in (_ENDOFCHAIN, _FREESECT):
            if sector >= len(self.mini_fat) or steps > _MAX_SECTORS:
                raise WordBinaryError("Compound document mini chain is damaged")
            offset = sector * self.mini_size
            parts.append(self.mini_stream[offset:offset + self.mini_size])
            sector = self.mini_fat[sector]
            steps += 1
        return b"".join(parts)

    def stream_names(self) -> list[str]:
        return sorted(self.entries)

    def stream(self, name: str) -> bytes | None:
        entry = self.entries.get(name)
        if entry is None:
            return None
        start, size, _kind = entry
        if size < self.mini_cutoff:
            return self._mini_chain(start)[:size]
        return self._chain(start)[:size]


# Word marks structure with control characters inside the text stream ([MS-DOC] 2.8.25).
_FIELD_BEGIN, _FIELD_SEPARATOR, _FIELD_END = "\x13", "\x14", "\x15"
_REPLACE = {
    "\r": "\n",      # paragraph end
    "\x0b": "\n",    # line break
    "\x0c": "\n",    # page or section break
    "\x0e": "\n",    # column break
    "\x07": "\t",    # table cell end
    "\x1e": "-",     # non-breaking hyphen
    "\x1f": "",      # optional hyphen
    "\x01": "",      # picture anchor
    "\x08": "",      # drawn object anchor
    "\x02": "",      # footnote reference mark
    "\x05": "",      # comment reference mark
}


def _clean(text: str) -> str:
    out: list[str] = []
    depth_in_code: list[bool] = []  # one per open field: True while its instruction (not its result) is being read
    for char in text:
        if char == _FIELD_BEGIN:
            depth_in_code.append(True)
            continue
        if char == _FIELD_SEPARATOR:
            if depth_in_code:
                depth_in_code[-1] = False
            continue
        if char == _FIELD_END:
            if depth_in_code:
                depth_in_code.pop()
            continue
        if any(depth_in_code):
            continue  # a field instruction such as HYPERLINK "..." or PAGE: not document text
        out.append(_REPLACE.get(char, char))
    lines = [line.rstrip() for line in "".join(out).split("\n")]
    return "\n".join(lines).strip()


def _protection_refusal(compound: _CompoundFile) -> str | None:
    """Why an encrypted Office package cannot be read, naming who protected it when its licence says so.

    A password-protected .docx or .xlsx, and one under Microsoft rights management (Purview / Azure RMS message
    encryption), are compound files holding an EncryptedPackage stream. Rights management adds a DRM data space
    whose publishing licence names the issuing organisation and account in plain XML. Live: OPDMD63's
    324001509_50_0_S_3102292.DOCX, protected by the Office of the Attorney General on 23 Oct 2025."""
    if "EncryptedPackage" not in compound.entries:
        return None
    names = compound.stream_names()
    if not any("DRM" in name for name in names) and not any(
            b"DRMTransform" in (compound.stream(name) or b"") for name in names if name.endswith("Primary")):
        return "This Office document is password-protected. Without the password its text cannot be read."
    licence = b"".join(compound.stream(name) or b"" for name in names if name.endswith("Primary"))
    text = licence.decode("latin-1")
    issuer = next((m.group(1).strip() for m in re.finditer(r"<NAME>([^<]{2,120})</NAME>", text)
                   if not m.group(1).strip().startswith(("Microsoft", "DRM ", "EXO.", "LCID"))
                   and "@" not in m.group(1)), None)
    account = next((m.group(1) for m in re.finditer(r"mailto:([^<\s]{3,120})", text)), None)
    issued = sorted(m.group(1)[:10] for m in re.finditer(r"<ISSUEDTIME>(\d{4}-\d\d-\d\dT[^<]*)</ISSUEDTIME>", text))
    who = f"{issuer} ({account})" if issuer and account else issuer or account
    message = "This Office document is locked with Microsoft rights management"
    if who:
        message += f" by {who}"
    if issued:
        message += f" on {issued[-1]}"
    return (message + ". Only an account it was shared with can open it, so its text cannot be read here. "
            "An unlocked copy from the sender can be read.")


def office_package_refusal(file_path: str) -> str | None:
    """The reason an encrypted Office compound file cannot be read, or None when it is not one."""
    with open(file_path, "rb") as handle:
        data = handle.read()
    return _protection_refusal(_CompoundFile(data))


def read_word_binary(file_path: str) -> dict:
    """Return {"text", "body_characters", "other_characters", "streams"} or raise WordBinaryError."""
    with open(file_path, "rb") as handle:
        data = handle.read()
    compound = _CompoundFile(data)
    refusal = _protection_refusal(compound)
    if refusal:
        raise WordBinaryError(refusal)
    word = compound.stream("WordDocument")
    if word is None:
        found = ", ".join(compound.stream_names()[:8]) or "none"
        raise WordBinaryError(
            f"Compound document holds no Word text (it is not a Word 97-2003 file; streams: {found})")
    if len(word) < 0x1AA:
        raise WordBinaryError("Word document header is too short")
    ident, nfib = struct.unpack_from("<HH", word, 0)
    flags = struct.unpack_from("<H", word, 0x0A)[0]
    if ident != 0xA5EC:
        raise WordBinaryError("Word document header is damaged")
    if nfib < 101:
        raise WordBinaryError("Word 6 and Word 95 documents are not supported; save the file as .docx or PDF")
    if flags & 0x0100:
        raise WordBinaryError("Encrypted Word documents are not supported")
    table_name = "1Table" if flags & 0x0200 else "0Table"
    table = compound.stream(table_name)
    if table is None:
        raise WordBinaryError(f"Word document is missing its {table_name} stream")

    body_cp = struct.unpack_from("<i", word, 0x4C)[0]
    fc_clx, lcb_clx = struct.unpack_from("<II", word, 0x1A2)
    clx = table[fc_clx:fc_clx + lcb_clx]
    if not lcb_clx or len(clx) != lcb_clx:
        raise WordBinaryError("Word document has no readable piece table")
    position = 0
    while position < len(clx) and clx[position] == 0x01:  # Prc: formatting, skipped
        position += 3 + struct.unpack_from("<h", clx, position + 1)[0]
    if position >= len(clx) or clx[position] != 0x02:
        raise WordBinaryError("Word document piece table is damaged")
    plc_size = struct.unpack_from("<I", clx, position + 1)[0]
    plc = clx[position + 5:position + 5 + plc_size]
    pieces = (len(plc) - 4) // 12
    if pieces < 1:
        raise WordBinaryError("Word document piece table is empty")
    cps = struct.unpack_from(f"<{pieces + 1}I", plc, 0)
    chars: list[str] = []
    for index in range(pieces):
        count = cps[index + 1] - cps[index]
        if count <= 0:
            continue
        fc_value = struct.unpack_from("<I", plc, 4 * (pieces + 1) + 8 * index + 2)[0]
        if fc_value & 0x40000000:
            start = (fc_value & 0x3FFFFFFF) // 2
            chars.append(word[start:start + count].decode("cp1252", "replace"))
        else:
            start = fc_value & 0x3FFFFFFF
            chars.append(word[start:start + 2 * count].decode("utf-16-le", "replace"))
    full = "".join(chars)
    body_cp = max(0, min(body_cp, len(full)))
    body, rest = _clean(full[:body_cp]), _clean(full[body_cp:])
    text = body if not rest else f"{body}\n\n{rest}"
    return {
        "text": text,
        "body_characters": len(body),
        "other_characters": len(rest),
        "streams": compound.stream_names(),
    }
