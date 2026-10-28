"""Gzip for JSON API responses only.

Large Financial reads are JSON (a case's payments were 61 MB uncompressed). Browsers decompress gzip
transparently, so the same bytes reach the page in a fraction of the transfer. Only application/json is
compressed: downloads (zip, PDF, CSV, and any response sent as a file: Content-Disposition, ranges, 206),
event streams and anything already encoded pass through unchanged, so archive digests, download sizes,
resumed downloads and streaming behave exactly as before. Level 1 keeps compression quick; a large body is
compressed in a worker thread so the event loop (event streams, other requests) never waits for it.
"""
import gzip

import anyio
from starlette.datastructures import Headers, MutableHeaders
from starlette.middleware.gzip import GZipMiddleware, GZipResponder, IdentityResponder

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

    async def send_with_compression(self, message):
        if message['type'] == 'http.response.start':
            await super().send_with_compression(message)
            if _passes_through(message):
                self.content_type_is_excluded = True
            return
        body = message.get('body', b'')
        if (message['type'] == 'http.response.body' and not self.started and not message.get('more_body', False)
                and not (self.content_encoding_set or self.content_type_is_excluded) and len(body) >= THREAD_MINIMUM_SIZE):
            self.started = True
            compressed = await anyio.to_thread.run_sync(lambda: gzip.compress(body, compresslevel=self.compresslevel))
            headers = MutableHeaders(raw=self.initial_message['headers'])
            headers.add_vary_header('Accept-Encoding')
            headers['Content-Encoding'] = 'gzip'
            headers['Content-Length'] = str(len(compressed))
            await self.send(self.initial_message)
            await self.send({**message, 'body': compressed})
            return
        await super().send_with_compression(message)


class JSONGZipMiddleware(GZipMiddleware):
    def __init__(self, app, minimum_size=4096, compresslevel=1):
        super().__init__(app, minimum_size=minimum_size, compresslevel=compresslevel)

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or 'gzip' not in Headers(scope=scope).get('Accept-Encoding', ''):
            await self.app(scope, receive, send)
            return
        await _JSONGZipResponder(self.app, self.minimum_size, compresslevel=self.compresslevel)(scope, receive, send)
