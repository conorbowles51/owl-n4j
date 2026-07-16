from __future__ import annotations

from urllib.parse import quote

EXPORT_SECURITY_HEADERS = {
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
}


def _header_filename(filename: str) -> str:
    cleaned = str(filename or "").replace("\r", "").replace("\n", "").strip()
    return cleaned or "download"


def content_disposition(filename: str, disposition: str = "attachment") -> str:
    safe_filename = _header_filename(filename)
    ascii_filename = safe_filename.encode("ascii", "ignore").decode("ascii")
    ascii_filename = (
        ascii_filename.replace("\\", "")
        .replace('"', "")
        .replace("\r", "")
        .replace("\n", "")
        .strip()
        or "download"
    )
    return (
        f'{disposition}; filename="{ascii_filename}"; '
        f"filename*=UTF-8''{quote(safe_filename, safe='')}"
    )
