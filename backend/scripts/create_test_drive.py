#!/usr/bin/env python3
"""
Create Test USB Drive

Generates a realistic Windows 10 USB forensic image directory structure
for testing the Evidence Triage Workbench end-to-end.

Usage:
    python backend/scripts/create_test_drive.py

Output:
    backend/data/test_usb_drive/  (~50 files across all categories)
"""

import io
import os
import struct
import zipfile
from datetime import datetime
from pathlib import Path

# ── Output directory ──────────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).parent
BASE_DIR = SCRIPT_DIR.parent
OUTPUT_DIR = BASE_DIR / "data" / "test_usb_drive"


# ── Magic byte generators ────────────────────────────────────────────

def _pdf_bytes(text: str = "Sample PDF content", pages: int = 3) -> bytes:
    """Minimal valid-looking PDF with realistic text."""
    lines = [
        b"%PDF-1.4",
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj",
        b"2 0 obj<</Type/Pages/Count 1/Kids[3 0 R]>>endobj",
        b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]>>endobj",
    ]
    body = b"\n".join(lines)
    # Pad with the text content as a comment
    body += b"\n% " + text.encode("utf-8", errors="replace")
    body += b"\n" * pages * 200  # Add some bulk
    body += b"\n%%EOF"
    return body


def _jpeg_bytes(size: int = 8192) -> bytes:
    """Minimal JPEG with JFIF header."""
    header = bytes([
        0xFF, 0xD8, 0xFF, 0xE0,  # SOI + APP0
        0x00, 0x10,              # Length 16
        0x4A, 0x46, 0x49, 0x46, 0x00,  # "JFIF\0"
        0x01, 0x01,              # Version 1.1
        0x00,                    # Aspect ratio units
        0x00, 0x01, 0x00, 0x01, # X/Y density
        0x00, 0x00,              # No thumbnail
    ])
    padding = bytes([0x00] * (size - len(header) - 2))
    footer = bytes([0xFF, 0xD9])  # EOI
    return header + padding + footer


def _png_bytes(size: int = 4096) -> bytes:
    """Minimal PNG signature + IHDR."""
    sig = bytes([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A])  # PNG signature
    # Minimal IHDR chunk
    ihdr_data = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)  # 1x1 RGB
    ihdr_len = struct.pack(">I", len(ihdr_data))
    ihdr = ihdr_len + b"IHDR" + ihdr_data
    # Pad to requested size
    padding = bytes([0x00] * max(0, size - len(sig) - len(ihdr)))
    return sig + ihdr + padding


def _exe_bytes(size: int = 16384) -> bytes:
    """Minimal MZ/PE header."""
    mz_header = b"MZ" + bytes([0x90, 0x00] * 30)  # DOS header stub
    mz_header += b"This program cannot be run in DOS mode.\r\n"
    padding = bytes([0x00] * max(0, size - len(mz_header)))
    return mz_header + padding


def _dll_bytes(size: int = 12288) -> bytes:
    """Same as EXE (DLLs share MZ format)."""
    return _exe_bytes(size)


def _sqlite_bytes(tables: str = "", size: int = 4096) -> bytes:
    """SQLite file header."""
    header = b"SQLite format 3\x00"
    # Page size = 4096
    header += struct.pack(">H", 4096)
    # Fill rest of first page
    padding = bytes([0x00] * max(0, size - len(header)))
    return header + padding


def _registry_bytes(size: int = 8192) -> bytes:
    """Windows Registry hive header (regf)."""
    header = b"regf" + bytes([0x00] * 508)  # regf + padding to 512 bytes
    padding = bytes([0x00] * max(0, size - len(header)))
    return header + padding


def _zip_bytes(filenames: dict = None) -> bytes:
    """Create a real ZIP archive with dummy content."""
    if filenames is None:
        filenames = {"readme.txt": b"Archive contents.\n"}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in filenames.items():
            zf.writestr(name, content)
    return buf.getvalue()


def _tar_gz_bytes() -> bytes:
    """Minimal gzip header (magic bytes)."""
    import gzip
    buf = io.BytesIO()
    with gzip.open(buf, "wb") as gz:
        gz.write(b"photo1.jpg\nphoto2.jpg\nphoto3.jpg\n")
    return buf.getvalue()


def _pst_bytes(size: int = 16384) -> bytes:
    """Outlook PST file magic bytes."""
    header = b"!BDN"  # PST magic
    header += b"SM\x17\x00"  # Additional PST signature bytes
    padding = bytes([0x00] * max(0, size - len(header)))
    return header + padding


def _kdbx_bytes(size: int = 4096) -> bytes:
    """KeePass KDBX magic bytes."""
    header = bytes([0x03, 0xD9, 0xA2, 0x9A, 0x67, 0xFB, 0x4B, 0xB5])  # KDBX sig
    padding = bytes([0x00] * max(0, size - len(header)))
    return header + padding


def _docx_bytes(text: str = "Document content") -> bytes:
    """Create minimal DOCX (which is a ZIP with specific structure)."""
    content_types = """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>"""

    rels = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""

    document = f"""<?xml version="1.0" encoding="UTF-8"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p><w:r><w:t>{text}</w:t></w:r></w:p>
  </w:body>
</w:document>"""

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", rels)
        zf.writestr("word/document.xml", document)
    return buf.getvalue()


def _xlsx_bytes() -> bytes:
    """Create minimal XLSX (ZIP-based spreadsheet)."""
    content_types = """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
</Types>"""

    rels = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>"""

    workbook = """<?xml version="1.0" encoding="UTF-8"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheets><sheet name="Budget" sheetId="1" r:id="rId1" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"/></sheets>
</workbook>"""

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", rels)
        zf.writestr("xl/workbook.xml", workbook)
    return buf.getvalue()


# ── File definitions ─────────────────────────────────────────────────

FILES = {
    # ── User 1: JohnSmith ─────────────────────────────────────────
    "Users/JohnSmith/Desktop/budget_2024.xlsx": _xlsx_bytes,
    "Users/JohnSmith/Desktop/meeting_notes.docx": lambda: _docx_bytes(
        "Meeting with Brian Murphy re: property transaction at 14 Elm Street. "
        "Agreed deposit of EUR 45,000. Solicitor to review contracts by Friday."
    ),
    "Users/JohnSmith/Desktop/todo.txt": lambda: (
        "URGENT TASKS - Jan 2024\n"
        "========================\n"
        "1. Transfer funds to offshore account (Cayman - acct ending 8847)\n"
        "2. Delete browser history before audit\n"
        "3. Meet contact at Buswell's Hotel - Thursday 3pm\n"
        "4. Shred documents from filing cabinet B\n"
        "5. Change passwords on all accounts\n"
        "6. Call accountant re: discrepancy in Q3 figures\n"
    ).encode("utf-8"),

    "Users/JohnSmith/Documents/contract_draft.pdf": lambda: _pdf_bytes(
        "CONFIDENTIAL - Property Development Agreement\n"
        "Between: John Smith (Party A) and Meridian Holdings Ltd (Party B)\n"
        "Re: Development at Docklands Site 7, Dublin\n"
        "Total consideration: EUR 2,350,000\n"
        "Payment schedule: 30% on signing, 70% on completion\n"
        "Clause 14.2: Non-disclosure provisions apply for 5 years"
    ),
    "Users/JohnSmith/Documents/tax_return_2023.pdf": lambda: _pdf_bytes(
        "Revenue Commissioners - Income Tax Return 2023\n"
        "Name: John Smith\n"
        "PPS Number: 1234567T\n"
        "Employment Income: EUR 85,000\n"
        "Rental Income: EUR 24,000\n"
        "Declared Foreign Income: EUR 0\n"
        "Tax Paid: EUR 31,200"
    ),
    "Users/JohnSmith/Documents/passwords.kdbx": _kdbx_bytes,

    "Users/JohnSmith/Downloads/installer.exe": lambda: _exe_bytes(24576),
    "Users/JohnSmith/Downloads/invoice_scan.jpg": lambda: _jpeg_bytes(12288),
    "Users/JohnSmith/Downloads/vacation_photo.png": lambda: _png_bytes(16384),
    # Extension mismatch: .jpg extension but ZIP content
    "Users/JohnSmith/Downloads/suspicious_file.jpg": lambda: _zip_bytes({
        "accounts.csv": b"Date,Amount,Recipient\n2024-01-15,50000,Offshore Holdings Ltd\n2024-02-01,25000,Shell Company B\n",
        "contacts.txt": b"Viktor M. - +372 555 1234\nMarcos R. - +34 612 345 678\n",
    }),

    "Users/JohnSmith/Pictures/family_photo.jpg": lambda: _jpeg_bytes(32768),
    "Users/JohnSmith/Pictures/screenshot_2024.png": lambda: _png_bytes(8192),

    # Browser artifacts (Chrome)
    "Users/JohnSmith/AppData/Local/Google/Chrome/User Data/Default/History": lambda: _sqlite_bytes(size=32768),
    "Users/JohnSmith/AppData/Local/Google/Chrome/User Data/Default/Cookies": lambda: _sqlite_bytes(size=16384),
    "Users/JohnSmith/AppData/Local/Google/Chrome/User Data/Default/Login Data": lambda: _sqlite_bytes(size=8192),

    # Email store
    "Users/JohnSmith/AppData/Local/Microsoft/Outlook/john.ost": lambda: _pst_bytes(32768),

    # Registry hive
    "Users/JohnSmith/NTUSER.DAT": lambda: _registry_bytes(16384),

    # ── User 2: SarahConnor ───────────────────────────────────────
    "Users/SarahConnor/Desktop/project_plan.docx": lambda: _docx_bytes(
        "Operation Nightfall - Phase 2 Timeline\n"
        "Target completion: March 2024\n"
        "Budget allocation: EUR 180,000\n"
        "Key personnel: J. Smith, M. Rodriguez, T. Chen"
    ),
    "Users/SarahConnor/Documents/report_final.pdf": lambda: _pdf_bytes(
        "INTERNAL REPORT - Financial Irregularities Investigation\n"
        "Subject: Discrepancies in accounts receivable, Q2-Q4 2023\n"
        "Finding: Approximately EUR 340,000 in unreconciled transactions\n"
        "Recommendation: Refer to external forensic accountant"
    ),
    "Users/SarahConnor/Documents/encrypted_notes.pgp": lambda: (
        "-----BEGIN PGP MESSAGE-----\n"
        "Version: GnuPG v2.2.27\n\n"
        "hQEMA8p3VGNIPMHRAQf+KLGbqZmzU3rnOGKg9nO3k4A\n"
        "mNVF+3k7qQeN5g8x2nD7N8r+j+Vj3LzO1pqR5mA9KzW\n"
        "xY7vBQf8CqA3lO2k+L8F9nHj7N3V2bP5q4mZlX1oRd3p\n"
        "A7vBQf8CqA3lO2k+L8F9nHj7N3V2bP5q4mZlX1oRd3p\n"
        "=a4Xj\n"
        "-----END PGP MESSAGE-----\n"
    ).encode("utf-8"),

    "Users/SarahConnor/Downloads/chat_backup.zip": lambda: _zip_bytes({
        "whatsapp_chat_2024.txt": (
            "[15/01/2024, 09:32] John: Did you move the funds?\n"
            "[15/01/2024, 09:33] Sarah: Done. Account in Zurich confirmed.\n"
            "[15/01/2024, 09:35] John: Delete this conversation after reading.\n"
            "[15/01/2024, 09:36] Sarah: Understood. Meeting at the usual place tomorrow.\n"
        ).encode(),
        "signal_export.json": b'{"messages": [{"sender": "John", "text": "Use the new burner phone"}]}',
    }),
    "Users/SarahConnor/Downloads/photo_album.tar.gz": _tar_gz_bytes,

    # ── Windows System Files ──────────────────────────────────────
    "Windows/System32/kernel32.dll": lambda: _dll_bytes(32768),
    "Windows/System32/notepad.exe": lambda: _exe_bytes(16384),
    "Windows/System32/drivers/tcpip.sys": lambda: _exe_bytes(8192),
    "Windows/System32/config/SOFTWARE": lambda: _registry_bytes(65536),
    "Windows/System32/config/SAM": lambda: _registry_bytes(16384),
    "Windows/System32/config/SYSTEM": lambda: _registry_bytes(32768),

    # ── Program Files ─────────────────────────────────────────────
    "Program Files/Mozilla Firefox/firefox.exe": lambda: _exe_bytes(20480),
    "Program Files/Mozilla Firefox/xul.dll": lambda: _dll_bytes(16384),
    "Program Files/Telegram Desktop/Telegram.exe": lambda: _exe_bytes(24576),
    "Program Files/Telegram Desktop/tdata/data": lambda: _sqlite_bytes(size=8192),

    # ── ProgramData ───────────────────────────────────────────────
    "ProgramData/Microsoft/Windows Defender/Scans/scan_log.log": lambda: (
        "2024-01-20 08:00:01 [INFO] Scheduled scan started\n"
        "2024-01-20 08:15:33 [WARN] Suspicious file: C:\\Users\\JohnSmith\\Downloads\\suspicious_file.jpg\n"
        "2024-01-20 08:45:12 [INFO] Scan completed. 1 threat(s) found.\n"
    ).encode("utf-8"),

    # ── Recycle Bin ───────────────────────────────────────────────
    "$Recycle.Bin/S-1-5-21-3842345737/$R1A2B3C.pdf": lambda: _pdf_bytes(
        "DELETED - Wire transfer confirmation\n"
        "From: First National Bank\n"
        "Reference: WTX-2024-00847\n"
        "Amount: EUR 150,000\n"
        "Beneficiary: Meridian Holdings Ltd\n"
        "Account: CH93 0076 2011 6238 5295 7"
    ),
    "$Recycle.Bin/S-1-5-21-3842345737/$R4D5E6F.docx": lambda: _docx_bytes(
        "DELETED DOCUMENT - Draft email to M. Rodriguez regarding shipment timing"
    ),

    # ── Recovery partition ────────────────────────────────────────
    "Recovery/boot.sdi": lambda: bytes([0x00] * 4096),
    "Recovery/BCD": lambda: b"regf" + bytes([0x00] * 4092),

    # ── Root system files ─────────────────────────────────────────
    "pagefile.sys": lambda: bytes([0x00] * 65536),
    "hiberfil.sys": lambda: bytes([0x00] * 32768),
    "bootmgr": lambda: _exe_bytes(8192),

    # ── Web content (user browsing cache) ─────────────────────────
    "Users/JohnSmith/AppData/Local/Temp/cache/index.html": lambda: (
        "<!DOCTYPE html><html><head><title>Banking Portal</title></head>"
        "<body><h1>Secure Login</h1><form action='/login'>"
        "<input name='account'/><input name='password' type='password'/>"
        "</form></body></html>"
    ).encode("utf-8"),
    "Users/JohnSmith/AppData/Local/Temp/cache/styles.css": lambda: (
        "body { font-family: Arial; } .account-balance { color: green; }"
    ).encode("utf-8"),
    "Users/JohnSmith/AppData/Local/Temp/cache/api_response.json": lambda: (
        '{"status": "success", "balance": 247500.00, '
        '"last_transaction": {"amount": -50000, "to": "Offshore Holdings Ltd"}}'
    ).encode("utf-8"),

    # ── Email files ───────────────────────────────────────────────
    "Users/JohnSmith/Documents/important_email.eml": lambda: (
        "From: john.smith@example.com\r\n"
        "To: m.rodriguez@offshore-holdings.com\r\n"
        "Subject: Re: Transfer Confirmation\r\n"
        "Date: Mon, 15 Jan 2024 14:32:00 +0000\r\n"
        "Content-Type: text/plain\r\n"
        "\r\n"
        "Marcus,\r\n\r\n"
        "Transfer of EUR 50,000 confirmed to the Zurich account.\r\n"
        "Please confirm receipt and destroy this email.\r\n\r\n"
        "Regards,\r\n"
        "John\r\n"
    ).encode("utf-8"),

    # ── Database files ────────────────────────────────────────────
    "Users/JohnSmith/AppData/Local/app_data/contacts.db": lambda: _sqlite_bytes(size=8192),

    # ── Startup / Autorun ─────────────────────────────────────────
    "ProgramData/Microsoft/Windows/Start Menu/Programs/Startup/updater.exe": lambda: _exe_bytes(8192),
}


# ── Main ─────────────────────────────────────────────────────────────

def create_test_drive():
    """Generate the test USB drive directory structure."""
    if OUTPUT_DIR.exists():
        print(f"Removing existing test drive at {OUTPUT_DIR}")
        import shutil
        shutil.rmtree(OUTPUT_DIR)

    print(f"Creating test USB drive at {OUTPUT_DIR}")
    print(f"Files to create: {len(FILES)}")
    print()

    total_size = 0
    categories = {}

    for rel_path, content_fn in sorted(FILES.items()):
        full_path = OUTPUT_DIR / rel_path
        full_path.parent.mkdir(parents=True, exist_ok=True)

        content = content_fn()
        if isinstance(content, str):
            content = content.encode("utf-8")

        full_path.write_bytes(content)
        size = len(content)
        total_size += size

        # Categorize for summary
        ext = full_path.suffix.lower()
        cat = _guess_category(rel_path, ext)
        categories[cat] = categories.get(cat, 0) + 1

        print(f"  {rel_path:70s} {size:>8,} bytes  [{cat}]")

    print()
    print(f"{'=' * 80}")
    print(f"Total: {len(FILES)} files, {total_size:,} bytes ({total_size / 1024:.1f} KB)")
    print()
    print("Categories:")
    for cat, count in sorted(categories.items(), key=lambda x: -x[1]):
        print(f"  {cat:20s} {count:3d} files")
    print()
    print(f"Output directory: {OUTPUT_DIR}")
    print()
    print("Key test features:")
    print("  - Windows OS detection (Windows/System32/, Users/, Program Files/)")
    print("  - 2 user accounts (JohnSmith, SarahConnor)")
    print("  - Extension mismatch (suspicious_file.jpg is actually a ZIP)")
    print("  - Browser artifacts (Chrome History, Cookies, Login Data)")
    print("  - Email stores (john.ost, important_email.eml)")
    print("  - Encrypted containers (passwords.kdbx, encrypted_notes.pgp)")
    print("  - Registry hives (NTUSER.DAT, SOFTWARE, SAM, SYSTEM)")
    print("  - Chat artifacts (Telegram tdata)")
    print("  - Deleted files ($Recycle.Bin)")
    print("  - Startup persistence (Startup/updater.exe)")
    print("  - Realistic investigative content in documents")


def _guess_category(path: str, ext: str) -> str:
    """Quick category guess for the summary output."""
    ext_map = {
        ".pdf": "documents", ".docx": "documents", ".xlsx": "documents",
        ".txt": "documents", ".eml": "emails",
        ".jpg": "images", ".png": "images",
        ".exe": "executables", ".dll": "executables", ".sys": "executables",
        ".zip": "archives", ".gz": "archives",
        ".db": "databases", ".sqlite3": "databases",
        ".html": "web", ".css": "web", ".json": "web",
        ".log": "system", ".dat": "system", ".kdbx": "system",
        ".pgp": "system", ".ost": "emails",
    }
    if ext in ext_map:
        return ext_map[ext]
    # No extension - guess from path
    lower = path.lower()
    if "history" in lower or "cookies" in lower or "login" in lower:
        return "databases"
    if "software" in lower or "sam" in lower or "system" in lower or "bcd" in lower:
        return "system"
    if "pagefile" in lower or "hiberfil" in lower or "boot" in lower:
        return "system"
    if "tdata" in lower:
        return "databases"
    return "other"


if __name__ == "__main__":
    create_test_drive()
