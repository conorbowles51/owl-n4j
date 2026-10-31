"""
The 422 reply to a request that fails validation.

FastAPI's own reply lists each error with an "input" item: the submitted value at that place, and for a missing
field the whole enclosing body. A sign-in sent with a wrong field name therefore echoed the password back (and into
any log or transcript that kept the reply). This reply keeps each error's type, place and message and never the
submitted values.
"""

import json

from fastapi import FastAPI, Request, WebSocket
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError, WebSocketRequestValidationError
from fastapi.responses import JSONResponse
from starlette.status import WS_1008_POLICY_VIOLATION

_KEPT = ("type", "loc", "msg")


def _without_input(error: dict) -> dict:
    return {k: error[k] for k in _KEPT if k in error}


async def validation_reply(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(status_code=422,
                        content=jsonable_encoder({"detail": [_without_input(e) for e in exc.errors()]}))


async def websocket_validation_reply(websocket: WebSocket, exc: WebSocketRequestValidationError) -> None:
    """FastAPI's own handler puts the errors, submitted values included, in the close reason."""
    await websocket.close(code=WS_1008_POLICY_VIOLATION,
                          reason=json.dumps(jsonable_encoder([_without_input(e) for e in exc.errors()])))


def install(app: FastAPI) -> None:
    app.add_exception_handler(RequestValidationError, validation_reply)
    app.add_exception_handler(WebSocketRequestValidationError, websocket_validation_reply)
