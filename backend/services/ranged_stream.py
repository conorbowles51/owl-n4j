"""Byte ranges for files the app streams itself (RFC 9110 section 14).

Browsers seek audio and video with a ``Range: bytes=...`` request and Safari will not play media at all from a server
that does not answer one with 206. ``FileResponse`` already does this for a plain file on disk; this is the same for
a file read through an opener (a member of a zip, a file in a phone production). One range per request: a request
for several ranges is answered whole with 200, which the RFC allows."""

from __future__ import annotations

import re
from typing import Callable, Dict, Optional, Tuple, Union

CHUNK = 1024 * 1024
_ONE = re.compile(r"^\s*bytes\s*=\s*(\d*)\s*-\s*(\d*)\s*$", re.IGNORECASE)
UNSATISFIABLE = "unsatisfiable"


def parse_range(header: Optional[str], size: int) -> Union[None, str, Tuple[int, int]]:
    """``(start, end)`` inclusive for one satisfiable range, ``UNSATISFIABLE`` for one that is not, ``None`` when
    the whole file is to be sent (no header, several ranges, or a header that is not a byte range)."""
    if not header:
        return None
    m = _ONE.match(header)
    if not m:
        return None
    first, last = m.group(1), m.group(2)
    if first == "" and last == "":
        return None
    if first == "":  # the final N bytes
        n = int(last)
        if n == 0 or size == 0:
            return UNSATISFIABLE
        return max(0, size - n), size - 1
    start = int(first)
    end = size - 1 if last == "" else min(int(last), size - 1)
    if last != "" and int(last) < start:
        return None  # not a valid range: ignored, the whole file is sent
    if start >= size:
        return UNSATISFIABLE
    return start, end


def ranged_response(range_header: Optional[str], opener: Callable, size: int, media_type: str,
                    headers: Dict[str, str]):
    """A 200 with the whole file, a 206 with the asked range, or a 416, always with ``Accept-Ranges: bytes``.
    The opener's file is seeked to the start (a zip member decompresses up to it) and closed when the body ends."""
    from fastapi.responses import Response, StreamingResponse

    headers = dict(headers)
    headers["Accept-Ranges"] = "bytes"
    wanted = parse_range(range_header, size)
    if wanted == UNSATISFIABLE:
        headers.pop("Content-Length", None)
        headers["Content-Range"] = "bytes */%d" % size
        return Response(status_code=416, headers=headers)
    start, end = (0, size - 1) if wanted is None else wanted
    length = max(0, end - start + 1)
    fh = opener()
    try:
        if start:
            fh.seek(start)
    except Exception:
        fh.close()
        raise

    def chunks():
        try:
            left = length
            while left > 0:
                block = fh.read(min(CHUNK, left))
                if not block:
                    break
                left -= len(block)
                yield block
        finally:
            fh.close()
    headers["Content-Length"] = str(length)
    if wanted is None:
        return StreamingResponse(chunks(), status_code=200, media_type=media_type, headers=headers)
    headers["Content-Range"] = "bytes %d-%d/%d" % (start, end, size)
    return StreamingResponse(chunks(), status_code=206, media_type=media_type, headers=headers)
