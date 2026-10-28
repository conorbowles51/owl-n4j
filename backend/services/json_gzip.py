"""Gzip for JSON API responses only.

Large Financial reads are JSON (a case's payments were 61 MB uncompressed). Browsers decompress gzip
transparently, so the same bytes reach the page in a fraction of the transfer. Only application/json is
compressed: downloads (zip, PDF, CSV), event streams and anything already encoded pass through unchanged,
so archive digests, download sizes and streaming behave exactly as before. Level 1 keeps compression
quick, because it runs on the event loop.
"""
from starlette.datastructures import Headers
from starlette.middleware.gzip import GZipMiddleware, GZipResponder, IdentityResponder


class _JSONGZipResponder(GZipResponder):
    async def send_with_compression(self, message):
        if message['type'] == 'http.response.start':
            await super().send_with_compression(message)
            if not Headers(raw=message['headers']).get('content-type', '').startswith('application/json'):
                self.content_type_is_excluded = True
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
