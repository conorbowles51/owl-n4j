"""HSTS for a site served over HTTPS. Off on the plain http address, where it has no effect and would mislead."""
from __future__ import annotations

from config import LOUPE_HTTPS

HSTS_VALUE = b"max-age=31536000"


class StrictTransportMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        async def with_header(message):
            if message["type"] == "http.response.start":
                message.setdefault("headers", []).append((b"strict-transport-security", HSTS_VALUE))
            await send(message)

        return await self.app(scope, receive, with_header)


def install(app, enabled: bool | None = None) -> bool:
    enabled = LOUPE_HTTPS if enabled is None else enabled
    if enabled:
        app.add_middleware(StrictTransportMiddleware)
    return enabled
