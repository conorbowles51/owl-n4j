"""Gzip for JSON API responses only.

Large Financial reads are JSON (a case's payments were 61 MB uncompressed). Browsers decompress gzip
transparently, so the same bytes reach the page in a fraction of the transfer. Only application/json is
compressed: downloads (zip, PDF, CSV, and any response sent as a file: Content-Disposition, ranges, 206),
event streams and anything already encoded pass through unchanged, so archive digests, download sizes,
resumed downloads and streaming behave exactly as before. Level 1 keeps compression quick; a large body is
compressed in a worker thread so the event loop (event streams, other requests) never waits for it.
"""
import gzip
import inspect
import time

import anyio
from starlette.datastructures import Headers, MutableHeaders
from starlette.middleware.gzip import GZipMiddleware, GZipResponder, IdentityResponder

from services.request_speed import note_gzip

# Bodies at least this large are compressed off the event loop (60 MB takes ~0.4 s at level 1).
THREAD_MINIMUM_SIZE = 256 * 1024
_FILE_HEADERS = ('content-disposition', 'content-range', 'accept-ranges')


def _passes_through(message):
    headers = Headers(raw=message['headers'])
    return (not headers.get('content-type', '').startswith('application/json') or message.get('status') == 206
            or any(name in headers for name in _FILE_HEADERS))


class _JSONGZipResponder(GZipResponder):
    def __init__(self, app, minimum_size, compresslevel=9):
        super().__init__(app, minimum_size, compresslevel=compresslevel)
        self.compresslevel = compresslevel
        self.passing_through = False

    def apply_compression(self, body, *, more_body):
        began = time.perf_counter()
        compressed = super().apply_compression(body, more_body=more_body)
        if inspect.isawaitable(compressed):  # newer Starlette compresses asynchronously
            return self._timed(compressed, began)
        note_gzip(time.perf_counter() - began)
        return compressed

    @staticmethod
    async def _timed(compressing, began):
        try:
            return await compressing
        finally:
            note_gzip(time.perf_counter() - began)

    async def send_with_compression(self, message):
        # A response that passes through is sent here, start first, without the base class: when the base class
        # sends a held start differs between Starlette versions, and a body sent before its start breaks the
        # response (Starlette 1.10 holds the start of a 304 or a text download and never sends it).
        if message['type'] == 'http.response.start' and _passes_through(message):
            self.passing_through = True
            await self.send(message)
            return
        if self.passing_through:
            await self.send(message)
            return
        if message['type'] == 'http.response.start':
            await super().send_with_compression(message)
            return
        body = message.get('body', b'')
        if (message['type'] == 'http.response.body' and not self.started and not message.get('more_body', False)
                and not (self.content_encoding_set or self.content_type_is_excluded) and len(body) >= THREAD_MINIMUM_SIZE):
            self.started = True
            began = time.perf_counter()
            compressed = await anyio.to_thread.run_sync(lambda: gzip.compress(body, compresslevel=self.compresslevel))
            note_gzip(time.perf_counter() - began)
            headers = MutableHeaders(raw=self.initial_message['headers'])
            headers.add_vary_header('Accept-Encoding')
            headers['Content-Encoding'] = 'gzip'
            headers['Content-Length'] = str(len(compressed))
            await self.send(self.initial_message)
            await self.send({**message, 'body': compressed})
            return
        await super().send_with_compression(message)


BODY_LENGTH_HEADER = 'x-body-length'


def _with_body_length(app):
    """The answer's own (uncompressed) length as X-Body-Length, before any compression replaces Content-Length.

    The browser counts the decompressed bytes it reads, so this is the total its loading bar measures against
    (bytes received of total). Only an answer whose length is known up front carries it; nothing else changes.
    """
    async def wrapped(scope, receive, send):
        async def send_with_length(message):
            if message['type'] == 'http.response.start':
                headers = MutableHeaders(raw=list(message['headers']))
                length = headers.get('content-length')
                # An answer that arrives already encoded (a kept view's ready gzip copy) has the compressed size
                # as its Content-Length: it sets X-Body-Length itself, or carries none.
                if length is not None and BODY_LENGTH_HEADER not in headers and 'content-encoding' not in headers:
                    headers[BODY_LENGTH_HEADER] = length
                    message = {**message, 'headers': headers.raw}
            await send(message)
        await app(scope, receive, send_with_length)
    return wrapped


class JSONGZipMiddleware(GZipMiddleware):
    def __init__(self, app, minimum_size=4096, compresslevel=1):
        super().__init__(_with_body_length(app), minimum_size=minimum_size, compresslevel=compresslevel)

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or 'gzip' not in Headers(scope=scope).get('Accept-Encoding', ''):
            await self.app(scope, receive, send)
            return
        await _JSONGZipResponder(self.app, self.minimum_size, compresslevel=self.compresslevel)(scope, receive, send)
