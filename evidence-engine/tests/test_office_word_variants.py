"""Word files that are not plain .docx zips are read or refused with the real reason (OPDMD63, 10 Nov 2026).

Before: two Word templates (.DOTX) failed as "Unsupported file type: .dotx"; a ".DOCX" whose bytes are a
compound file (Microsoft rights management) failed as "not a valid ZIP-based file"; a 54 x 42 inch PDF page
failed as "exceeds the configured OCR pixel limit even at 150 DPI"; every Word 97-2003 .doc was refused.
"""

from __future__ import annotations

import io
import struct
import zipfile
from pathlib import Path
from types import SimpleNamespace

import docx
import pytest

from app.pipeline import pdf_extraction
from app.pipeline.extract_text import extract_text

END, FREE, FATSECT = 0xFFFFFFFE, 0xFFFFFFFF, 0xFFFFFFFD


def _compound_file(streams: dict[str, bytes]) -> bytes:
    """A minimal [MS-CFB] version 3 file. Each stream is padded to 4096 bytes or more so it lives in the main FAT."""
    sector = 512
    padded = {name: data + b"\0" * max(0, 4096 - len(data)) for name, data in streams.items()}
    chains: list[tuple[str, int, int, bytes]] = []
    next_sector = 2  # sector 0 = FAT, sector 1 = directory
    for name, data in padded.items():
        count = -(-len(data) // sector)
        chains.append((name, next_sector, len(streams[name]) if len(streams[name]) >= 4096 else len(data), data))
        next_sector += count
    assert next_sector <= 128 and len(streams) + 1 <= 4
    fat = [FREE] * 128
    fat[0], fat[1] = FATSECT, END
    for _name, start, _size, data in chains:
        count = -(-len(data) // sector)
        for offset in range(count):
            fat[start + offset] = start + offset + 1 if offset < count - 1 else END

    def entry(name: str, kind: int, start: int, size: int) -> bytes:
        encoded = (name + "\0").encode("utf-16-le")
        raw = encoded.ljust(64, b"\0") + struct.pack("<HBB", len(encoded), kind, 1)
        raw += struct.pack("<III", FREE, FREE, FREE) + b"\0" * 16 + b"\0" * 4 + b"\0" * 16
        raw += struct.pack("<IQ", start, size)
        assert len(raw) == 128
        return raw

    directory = entry("Root Entry", 5, END, 0)
    for name, start, size, _data in chains:
        directory += entry(name, 2, start, size)
    directory = directory.ljust(sector, b"\0")

    header = bytearray(512)
    header[0:8] = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
    struct.pack_into("<HHHHH", header, 0x18, 0x3E, 3, 0xFFFE, 9, 6)
    struct.pack_into("<IIIIIIIII", header, 0x28, 0, 1, 1, 0, 4096, END, 0, END, 0)
    struct.pack_into("<109I", header, 0x4C, 0, *([FREE] * 108))
    body = struct.pack("<128I", *fat) + directory
    for _name, _start, _size, data in chains:
        body += data.ljust(-(-len(data) // sector) * sector, b"\0")
    return bytes(header) + body


def _word_97(pieces: list[tuple[str, bool]], body_chars: int) -> bytes:
    """A Word 97-2003 file whose text is the given pieces; True = one byte per character (cp1252)."""
    text_offset = 0x800
    word = bytearray(text_offset)
    struct.pack_into("<HH", word, 0, 0xA5EC, 0x00C1)
    struct.pack_into("<H", word, 0x0A, 0x0200)  # text table is 1Table
    struct.pack_into("<i", word, 0x4C, body_chars)
    cps, descriptors, cp = [0], b"", 0
    for text, compressed in pieces:
        offset = len(word)
        if compressed:
            word += text.encode("cp1252")
            fc = (offset * 2) | 0x40000000
        else:
            word += text.encode("utf-16-le")
            fc = offset
        cp += len(text)
        cps.append(cp)
        descriptors += struct.pack("<HIH", 0, fc, 0)
    plc = struct.pack(f"<{len(cps)}I", *cps) + descriptors
    table = b"\x00" * 16 + b"\x02" + struct.pack("<I", len(plc)) + plc
    struct.pack_into("<II", word, 0x1A2, 16, len(table) - 16)
    return _compound_file({"WordDocument": bytes(word), "1Table": table})


def _docx_bytes(paragraphs: list[str]) -> bytes:
    document = docx.Document()
    for paragraph in paragraphs:
        document.add_paragraph(paragraph)
    out = io.BytesIO()
    document.save(out)
    return out.getvalue()


def _relabel(package: bytes, label: str) -> bytes:
    source, out = zipfile.ZipFile(io.BytesIO(package)), io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as copy:
        for item in source.infolist():
            data = source.read(item)
            if item.filename == "[Content_Types].xml":
                data = data.replace(
                    b"application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml",
                    label.encode())
            copy.writestr(item, data)
    return out.getvalue()


@pytest.mark.asyncio
@pytest.mark.parametrize(("name", "label"), [
    ("324001509_46_0_S_3099401.DOTX",
     "application/vnd.openxmlformats-officedocument.wordprocessingml.template.main+xml"),
    ("letter.docm", "application/vnd.ms-word.document.macroEnabled.main+xml"),
    ("letter.dotm", "application/vnd.ms-word.template.macroEnabledTemplate.main+xml"),
])
async def test_word_template_and_macro_files_are_read_as_word(tmp_path: Path, name: str, label: str) -> None:
    source = tmp_path / name
    source.write_bytes(_relabel(_docx_bytes(["Subpoena return", "Account 4471 opened 3 May 2024"]), label))

    result = await extract_text(str(source), source.name)

    assert result.text == "Subpoena return\n\nAccount 4471 opened 3 May 2024"
    assert result.metadata["file_type"] == "docx"


@pytest.mark.asyncio
async def test_plain_docx_is_unchanged(tmp_path: Path) -> None:
    source = tmp_path / "plain.docx"
    source.write_bytes(_docx_bytes(["One", "Two"]))

    assert (await extract_text(str(source), source.name)).text == "One\n\nTwo"


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["memo.doc", "memo saved as.DOCX"])
async def test_word_97_file_is_read_by_its_bytes(tmp_path: Path, name: str) -> None:
    source = tmp_path / name
    body = 'Pagó $1,200 a Héctor\r\x13 HYPERLINK "https://x.example" \x14see receipt\x15 now\rCell\x07Two\x07\x07'
    source.write_bytes(_word_97([(body[:21], True), (body[21:] + "Zoë – ✓\r", False), ("Footnote one\r", True)],
                                body_chars=len(body) + len("Zoë – ✓\r")))

    result = await extract_text(str(source), source.name)

    assert result.text == "Pagó $1,200 a Héctor\nsee receipt now\nCell\tTwo\t\tZoë – ✓\n\nFootnote one"
    assert result.metadata["file_type"] == "doc"
    assert result.metadata["word_binary"]["other_characters"] == len("Footnote one")


def _xml(text: str) -> bytes:
    return text.encode("latin-1")


@pytest.mark.asyncio
async def test_rights_managed_word_file_is_refused_naming_who_locked_it(tmp_path: Path) -> None:
    licence = _xml(
        "<XrML><ISSUEDTIME>2008-04-23T19:12</ISSUEDTIME><NAME>Microsoft DRM Production CA</NAME>"
        "<ISSUER><OBJECT><NAME>Office of the Attorney General</NAME></OBJECT>"
        "<ADDRESS type=\"URL\">mailto:clerk@example.gov</ADDRESS><NAME>clerk@example.gov</NAME></ISSUER>"
        "<ISSUEDTIME>2025-10-23T16:07</ISSUEDTIME>Microsoft.Metadata.DRMTransform</XrML>")
    source = tmp_path / "324001509_50_0_S_3102292.DOCX"
    source.write_bytes(_compound_file({
        "\x06Primary": licence, "DRMEncryptedDataSpace": b"DRMEncryptedTransform",
        "EncryptedPackage": b"\x01" * 5000,
    }))

    with pytest.raises(ValueError) as caught:
        await extract_text(str(source), source.name)

    assert str(caught.value) == (
        "This Office document is locked with Microsoft rights management by Office of the Attorney General "
        "(clerk@example.gov) on 2025-10-23. Only an account it was shared with can open it, so its text cannot be "
        "read here. An unlocked copy from the sender can be read.")


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["locked.docx", "locked.xlsx"])
async def test_password_protected_office_file_says_so(tmp_path: Path, name: str) -> None:
    source = tmp_path / name
    source.write_bytes(_compound_file({"EncryptionInfo": b"\x04\x00\x04\x00", "EncryptedPackage": b"\x02" * 5000}))

    with pytest.raises(ValueError, match="password-protected"):
        await extract_text(str(source), source.name)


@pytest.mark.asyncio
async def test_compound_file_without_word_text_names_what_it_holds(tmp_path: Path) -> None:
    source = tmp_path / "book.docx"
    source.write_bytes(_compound_file({"Workbook": b"\x09\x08" * 3000}))

    with pytest.raises(ValueError, match="not a Word 97-2003 file; streams: Workbook"):
        await extract_text(str(source), source.name)


def test_oversized_pdf_page_is_read_at_the_largest_resolution_that_fits(monkeypatch) -> None:
    monkeypatch.setattr(pdf_extraction.settings, "pdf_ocr_dpi", 300)
    monkeypatch.setattr(pdf_extraction.settings, "pdf_ocr_max_pixels", 25_000_000)
    poster = SimpleNamespace(rect=SimpleNamespace(width=3902.0, height=3005.0))  # OPDMD63 page, 54 x 42 inches

    dpi = pdf_extraction._render_dpi(poster)

    assert dpi == 105
    assert (3902 * dpi / 72) * (3005 * dpi / 72) <= 25_000_000
    letter = SimpleNamespace(rect=SimpleNamespace(width=612.0, height=792.0))
    assert pdf_extraction._render_dpi(letter) == 300
    a_large = SimpleNamespace(rect=SimpleNamespace(width=1684.0, height=2384.0))  # A1: reduced, still above 150
    assert pdf_extraction._render_dpi(a_large) == 179
