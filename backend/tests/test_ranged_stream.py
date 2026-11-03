"""Phone media answers byte ranges (03 8.3: audio and video seek; Safari plays only from a server that answers 206).
Synthetic bytes; the case check and the phone's file lookup are faked, the route and the zip member read are real."""

from __future__ import annotations

import asyncio
import zipfile
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pytest

from routers import phones
from services.ranged_stream import UNSATISFIABLE, parse_range

BODY = bytes(range(256)) * 4096  # 1 MiB, every offset distinguishable


def _body(response):
    async def collect():
        out = b""
        async for block in response.body_iterator:
            out += block
        return out
    return asyncio.run(collect())


@pytest.fixture(params=["folder", "zip"])
def opener(request, tmp_path):
    if request.param == "folder":
        path = tmp_path / "voice.m4a"
        path.write_bytes(BODY)
        return lambda: open(path, "rb")
    zpath = tmp_path / "production.zip"
    with zipfile.ZipFile(zpath, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("files/voice.m4a", BODY)

    def open_member():
        z = zipfile.ZipFile(zpath)
        return z.open("files/voice.m4a")
    return open_member


def _get(opener, range_header):
    with patch.object(phones, "authorize_case"), \
            patch("services.phone.media.content", return_value=("voice.m4a", len(BODY), opener)):
        return phones.phone_media_content(uuid4(), uuid4(), SimpleNamespace(connection=lambda: None),
                                          SimpleNamespace(), range_header)


def test_a_range_request_is_answered_206_with_exactly_those_bytes(opener):
    r = _get(opener, "bytes=500000-500099")
    assert r.status_code == 206
    assert r.headers["content-range"] == "bytes 500000-500099/%d" % len(BODY)
    assert r.headers["content-length"] == "100" and r.headers["accept-ranges"] == "bytes"
    assert _body(r) == BODY[500000:500100]


def test_open_ended_and_suffix_ranges(opener):
    r = _get(opener, "bytes=1048000-")
    assert r.status_code == 206 and _body(r) == BODY[1048000:]
    r = _get(opener, "bytes=-10")
    assert r.status_code == 206 and _body(r) == BODY[-10:]
    assert r.headers["content-range"] == "bytes %d-%d/%d" % (len(BODY) - 10, len(BODY) - 1, len(BODY))


def test_no_range_is_the_whole_file_with_accept_ranges(opener):
    r = _get(opener, None)
    assert r.status_code == 200 and r.headers["accept-ranges"] == "bytes"
    assert r.headers["content-length"] == str(len(BODY)) and _body(r) == BODY


def test_a_range_past_the_end_is_416(opener):
    r = _get(opener, "bytes=%d-" % len(BODY))
    assert r.status_code == 416 and r.headers["content-range"] == "bytes */%d" % len(BODY)


def test_parse_range_edges():
    assert parse_range(None, 10) is None
    assert parse_range("bytes=0-0", 10) == (0, 0)
    assert parse_range("bytes=2-99", 10) == (2, 9)
    assert parse_range("bytes=0-1,4-5", 10) is None  # several ranges: the whole file
    assert parse_range("bytes=5-2", 10) is None
    assert parse_range("items=0-1", 10) is None
    assert parse_range("bytes=-0", 10) == UNSATISFIABLE
    assert parse_range("bytes=-20", 10) == (0, 9)
    assert parse_range("bytes=10-", 10) == UNSATISFIABLE
