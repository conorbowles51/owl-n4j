"""Read one member of an uploaded ZIP or UFDR straight from its recorded position (cb-media item F; 01 D6).

The capture records each member's local header offset, compressed size, compression method and CRC-32 in
``phone_container_entries``. Opening the member then costs one seek and a 30-byte header read, not a read of the
archive's whole directory (live C9.zip: 58,215 entries, 310-480 ms per directory read, measured 3 Nov).

Stored and deflated members are read here. The CRC-32 and the size are checked as the last byte is read; a member
that does not match raises ``MemberDamaged`` rather than handing back wrong bytes. Any other method, or a header
that does not match the record, is ``None`` from ``open_at`` so the caller falls back to the directory lookup.
"""
from __future__ import annotations

import io
import struct
import zlib

LOCAL_HEADER = struct.Struct("<4sHHHHHIIIHH")
LOCAL_SIGNATURE = b"PK\x03\x04"
STORED, DEFLATED = 0, 8


class MemberDamaged(OSError):
    pass


class _Member(io.RawIOBase):
    """One member's bytes. Seekable, so a byte range can be served (206): a stored member seeks in place; a
    deflated one decompresses up to the position; a backward seek starts the member again. The CRC-32 is checked
    when every byte from the start has passed through; after a stored member's in-place skip it cannot be, and
    the size is still checked."""

    def __init__(self, fh, compressed_size, method, crc, size):
        self._fh = fh
        self._start = fh.tell()
        self._csize = compressed_size
        self._method = method
        self._want_crc = crc
        self._size = size
        self._restart()

    def _restart(self):
        self._fh.seek(self._start)
        self._left = self._csize
        self._z = zlib.decompressobj(-15) if self._method == DEFLATED else None
        self._crc = 0
        self._out = 0
        self._buf = b""
        self._done = False
        self._pos = 0

    def readable(self):
        return True

    def seekable(self):
        return True

    def tell(self):
        return self._pos

    def seek(self, offset, whence=io.SEEK_SET):
        if whence == io.SEEK_SET:
            target = offset
        elif whence == io.SEEK_CUR:
            target = self._pos + offset
        elif whence == io.SEEK_END and self._size is not None:
            target = self._size + offset
        else:
            raise io.UnsupportedOperation("this member can be sought from its start or the current position")
        if target < 0:
            raise ValueError("negative seek position")
        if target < self._pos:
            self._restart()
        skip = target - self._pos
        if skip and self._z is None and self._out is not None:  # stored: skip in place, past what is buffered
            take = min(skip, len(self._buf))
            self._buf = self._buf[take:]
            self._pos += take
            jump = min(skip - take, self._left)
            if jump:
                self._fh.seek(jump, io.SEEK_CUR)
                self._left -= jump
                self._out += jump
                self._pos += jump
                self._crc = None  # the skipped bytes were never read, so the CRC cannot be checked
            skip = target - self._pos
        while skip > 0:
            got = self.read(min(skip, 1 << 20))
            if not got:
                break
            skip -= len(got)
        return self._pos

    def _fill(self, n):
        while len(self._buf) < n and not self._done:
            chunk = self._fh.read(min(1 << 20, self._left)) if self._left > 0 else b""
            self._left -= len(chunk)
            if self._z is None:
                data = chunk
            else:
                try:
                    data = self._z.decompress(chunk) if chunk else b""
                    if not chunk or self._left <= 0:
                        data += self._z.flush()
                except zlib.error:
                    raise MemberDamaged("This file's bytes inside the uploaded archive could not be read: the "
                                        "archive is damaged at this file.") from None
            if not chunk or self._left <= 0:
                self._done = True
            if self._crc is not None:
                self._crc = zlib.crc32(data, self._crc)
            self._out += len(data)
            self._buf += data
        if self._done and self._out is not None:
            if (self._crc is not None and (self._crc & 0xFFFFFFFF) != (self._want_crc & 0xFFFFFFFF)) or \
                    (self._size is not None and self._out != self._size):
                raise MemberDamaged("This file's bytes inside the uploaded archive do not match the archive's own "
                                    "record of them.")
            self._out = None  # checked once

    def read(self, n=-1):
        if n is None or n < 0:
            self._fill(float("inf"))
            data, self._buf = self._buf, b""
            self._pos += len(data)
            return data
        self._fill(n)
        data, self._buf = self._buf[:n], self._buf[n:]
        self._pos += len(data)
        return data

    def readinto(self, b):
        data = self.read(len(b))
        b[:len(data)] = data
        return len(data)

    def close(self):
        try:
            self._fh.close()
        finally:
            super().close()


def open_at(archive_path, header_offset, compressed_size, method, crc, size):
    """A file-like reader of one member, or None when the recorded position cannot be used here (another method,
    or the bytes at the offset are not that member's header). The caller closes it."""
    if header_offset is None or compressed_size is None or method not in (STORED, DEFLATED) or crc is None:
        return None
    fh = open(archive_path, "rb")
    try:
        fh.seek(int(header_offset))
        head = fh.read(LOCAL_HEADER.size)
        if len(head) != LOCAL_HEADER.size:
            fh.close()
            return None
        sig, _ver, flags, hmethod, _t, _d, _crc, _cs, _us, name_len, extra_len = LOCAL_HEADER.unpack(head)
        if sig != LOCAL_SIGNATURE or hmethod != method or flags & 0x1:  # encrypted members are never read here
            fh.close()
            return None
        fh.seek(name_len + extra_len, 1)
        return io.BufferedReader(_Member(fh, int(compressed_size), method, int(crc), size), buffer_size=1 << 16)
    except Exception:
        fh.close()
        raise
